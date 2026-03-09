from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import numpy as np
import pandas as pd


BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
LATITUDE = 8.482
LONGITUDE = 124.647
LOCATION_NAME = "Cagayan de Oro, Misamis Oriental, Philippines"
PARAMETERS = ["WS10M", "WD10M", "WS50M", "T2M", "RH2M"]
COMMUNITY = "RE"
FORMAT = "JSON"
START = "20230101"
END = "20231231"
OUTPUT_CSV = Path("CDO_wind_2023_hourly.csv")
OUTLIER_THRESHOLD_MS = 40.0
CUT_IN_SPEED_MS = 2.5
RATED_SPEED_MS = 12.0
POWER_LAW_EXPONENT = 0.18
STANDARD_PRESSURE_PA = 101325.0
STANDARD_AIR_DENSITY = 1.225


def build_url(start: str, end: str) -> str:
    params = ",".join(PARAMETERS)
    return (
        f"{BASE_URL}?parameters={params}&community={COMMUNITY}&format={FORMAT}"
        f"&latitude={LATITUDE}&longitude={LONGITUDE}&start={start}&end={end}"
    )


def fetch_json(url: str) -> dict:
    try:
        with urlopen(url) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print("API returned an HTTP error:")
        print(error_body)
        raise
    except URLError:
        raise
    return json.loads(body)


def season_for_month(month: int) -> str:
    if month in {11, 12, 1, 2}:
        return "Amihan"
    if month in {6, 7, 8, 9}:
        return "Habagat"
    if month in {3, 4, 5}:
        return "Transition_DryDown"
    if month == 10:
        return "Transition_Rampup"
    raise ValueError(f"Unexpected month: {month}")


def convert_lst_to_civil_hour(raw_key: str, longitude: float) -> tuple[datetime, datetime, datetime]:
    lst_dt = datetime.strptime(raw_key, "%Y%m%d%H")
    lst_offset = timedelta(hours=longitude / 15.0)
    utc_dt = lst_dt - lst_offset
    civil_dt = utc_dt + timedelta(hours=8)
    rounded_civil = (pd.Timestamp(civil_dt).round("h")).to_pydatetime()
    return lst_dt, utc_dt, rounded_civil


def build_dataframe(payload: dict) -> pd.DataFrame:
    parameter_data = payload["properties"]["parameter"]
    available_keys = set(parameter_data)
    expected_keys = set(PARAMETERS)
    if available_keys != expected_keys:
        raise KeyError(
            f"Unexpected parameter keys. Expected {sorted(expected_keys)}, got {sorted(available_keys)}"
        )

    timestamps = sorted(
        {
            ts
            for values in parameter_data.values()
            for ts in values.keys()
        }
    )

    records = []
    for raw_ts in timestamps:
        lst_dt, utc_dt, civil_dt = convert_lst_to_civil_hour(raw_ts, LONGITUDE)
        records.append(
            {
                "raw_lst_key": raw_ts,
                "raw_lst_datetime": lst_dt,
                "utc_datetime": utc_dt,
                "datetime": civil_dt,
                "wind_speed_10m_ms": parameter_data["WS10M"].get(raw_ts, np.nan),
                "wind_direction_10m_deg": parameter_data["WD10M"].get(raw_ts, np.nan),
                "wind_speed_50m_ms": parameter_data["WS50M"].get(raw_ts, np.nan),
                "air_temp_c": parameter_data["T2M"].get(raw_ts, np.nan),
                "relative_humidity_pct": parameter_data["RH2M"].get(raw_ts, np.nan),
            }
        )

    df = pd.DataFrame.from_records(records)
    fill_value = payload["header"].get("fill_value", -999.0)
    value_columns = [
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "air_temp_c",
        "relative_humidity_pct",
    ]
    for col in value_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").replace(fill_value, np.nan)

    return df


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["wind_speed_15m_ms"] = df["wind_speed_10m_ms"] * (15.0 / 10.0) ** POWER_LAW_EXPONENT
    df["air_density_kgm3"] = (
        STANDARD_AIR_DENSITY
        * (273.15 / (273.15 + df["air_temp_c"]))
        * (STANDARD_PRESSURE_PA / 101325.0)
    )
    df["month"] = df["datetime"].dt.month
    df["hour_of_day"] = df["datetime"].dt.hour
    df["season"] = df["month"].map(season_for_month)
    max_wind = df[["wind_speed_10m_ms", "wind_speed_50m_ms", "wind_speed_15m_ms"]].max(axis=1, skipna=True)
    df["outlier_flag"] = np.where(max_wind > OUTLIER_THRESHOLD_MS, 1, 0)
    return df


def validate_expected_hours(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    start_dt = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d") + timedelta(hours=23)
    expected_index = pd.date_range(start=start_dt, end=end_dt, freq="h")
    expected_rows = len(expected_index)
    actual_rows = len(df)
    print(f"Expected rows from date range: {expected_rows}")
    print(f"Actual rows before gap fill: {actual_rows}")

    duplicate_mask = df["datetime"].duplicated(keep=False)
    if duplicate_mask.any():
        print("Duplicate timestamps detected after rounding:")
        print(df.loc[duplicate_mask, ["raw_lst_key", "datetime"]].to_string(index=False))
        raise ValueError("Rounding produced duplicate civil timestamps. Stopping.")

    df = df.set_index("datetime").sort_index()
    missing_hours = expected_index.difference(df.index)
    if len(missing_hours) > 0:
        print("Missing hours identified and will be filled with NaN:")
        for ts in missing_hours:
            print(ts.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        print("No missing hours detected.")

    df = df.reindex(expected_index)
    df.index.name = "datetime"
    df["hour_of_year"] = np.arange(1, len(df) + 1, dtype=int)
    df["month"] = df.index.month
    df["hour_of_day"] = df.index.hour
    df["season"] = pd.Series(df.index.month, index=df.index).map(season_for_month)
    if "outlier_flag" in df:
        df["outlier_flag"] = df["outlier_flag"].fillna(0).astype(int)
    return df.reset_index()


def validate_ranges(df: pd.DataFrame) -> None:
    for col in ["wind_speed_10m_ms", "wind_speed_50m_ms", "wind_speed_15m_ms"]:
        negative = df[col].dropna() < 0
        if negative.any():
            raise ValueError(f"Negative values found in {col}")

    invalid_direction = df["wind_direction_10m_deg"].dropna()
    invalid_direction = invalid_direction[(invalid_direction < 0) | (invalid_direction > 360)]
    if not invalid_direction.empty:
        print("Wind direction values outside 0-360 detected:")
        print(invalid_direction.to_string())
        raise ValueError("Wind direction validation failed.")


def validate_derived_columns(df: pd.DataFrame) -> None:
    independent_ws15 = df["wind_speed_10m_ms"] * (15.0 / 10.0) ** POWER_LAW_EXPONENT
    independent_density = (
        STANDARD_AIR_DENSITY
        * (273.15 / (273.15 + df["air_temp_c"]))
        * (STANDARD_PRESSURE_PA / 101325.0)
    )

    ws15_ok = np.allclose(
        df["wind_speed_15m_ms"].to_numpy(),
        independent_ws15.to_numpy(),
        equal_nan=True,
        atol=1e-12,
    )
    density_ok = np.allclose(
        df["air_density_kgm3"].to_numpy(),
        independent_density.to_numpy(),
        equal_nan=True,
        atol=1e-12,
    )
    if not ws15_ok:
        raise ValueError("Derived column verification failed for wind_speed_15m_ms")
    if not density_ok:
        raise ValueError("Derived column verification failed for air_density_kgm3")


def print_spot_check(df: pd.DataFrame) -> None:
    sample_positions = [0, len(df) // 2, len(df) - 1]
    print("Timestamp conversion spot check:")
    for pos in sample_positions:
        row = df.iloc[pos]
        print(
            f"RAW_LST={row['raw_lst_datetime']:%Y-%m-%d %H:%M:%S} | "
            f"UTC={row['utc_datetime']:%Y-%m-%d %H:%M:%S.%f} | "
            f"CIVIL_PH_ROUNDED={row['datetime']:%Y-%m-%d %H:%M:%S}"
        )


def print_summary(df: pd.DataFrame) -> None:
    print("Validation report:")
    print(f"Total rows: {len(df)}")
    print("Missing value count per column:")
    print(df.isna().sum().to_string())

    for col in [
        "wind_speed_10m_ms",
        "wind_speed_15m_ms",
    ]:
        print(
            f"{col}: min={df[col].min(skipna=True):.6f}, "
            f"max={df[col].max(skipna=True):.6f}, "
            f"mean={df[col].mean(skipna=True):.6f}"
        )

    ws10_non_missing = df["wind_speed_10m_ms"].notna().sum()
    cut_in_count = (df["wind_speed_10m_ms"] > CUT_IN_SPEED_MS).sum()
    rated_count = (df["wind_speed_10m_ms"] > RATED_SPEED_MS).sum()
    cut_in_pct = (cut_in_count / ws10_non_missing * 100.0) if ws10_non_missing else np.nan
    rated_pct = (rated_count / ws10_non_missing * 100.0) if ws10_non_missing else np.nan
    print(f"Hours above cut-in speed ({CUT_IN_SPEED_MS} m/s): {cut_in_count} ({cut_in_pct:.2f}%)")
    print(f"Hours above rated speed ({RATED_SPEED_MS} m/s): {rated_count} ({rated_pct:.2f}%)")
    print(f"Outlier count: {int(df['outlier_flag'].sum())}")
    print("Breakdown of hours per season:")
    print(df["season"].value_counts(dropna=False).sort_index().to_string())


def enforce_missing_threshold(df: pd.DataFrame) -> None:
    threshold = len(df) * 0.05
    value_columns = [
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "wind_speed_15m_ms",
        "air_temp_c",
        "relative_humidity_pct",
        "air_density_kgm3",
    ]
    flagged = {col: int(df[col].isna().sum()) for col in value_columns if df[col].isna().sum() > threshold}
    if flagged:
        print("Warning: more than 5% missing values detected in these columns:")
        print(json.dumps(flagged, indent=2))
        raise RuntimeError("Missing-value threshold exceeded. Ask the user before proceeding.")


def main() -> None:
    url = build_url(START, END)
    print(f"Location: {LOCATION_NAME}")
    print(f"Full-year API URL: {url}")
    payload = fetch_json(url)
    print("Full-year response top-level keys:")
    print(list(payload.keys()))
    print("properties.parameter keys:")
    print(list(payload["properties"]["parameter"].keys()))

    df = build_dataframe(payload)
    print_spot_check(df)
    df = add_derived_columns(df)
    df = validate_expected_hours(df, START, END)
    validate_ranges(df)
    validate_derived_columns(df)
    enforce_missing_threshold(df)
    print_summary(df)

    final_columns = [
        "datetime",
        "hour_of_year",
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "wind_speed_15m_ms",
        "air_temp_c",
        "relative_humidity_pct",
        "air_density_kgm3",
        "month",
        "hour_of_day",
        "season",
        "outlier_flag",
    ]
    df["datetime"] = df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df.to_csv(OUTPUT_CSV, index=False, columns=final_columns)
    print(f"Saved CSV to {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
