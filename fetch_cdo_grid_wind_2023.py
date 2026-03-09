from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import numpy as np
import pandas as pd

from CDO_project_constants import ALPHA_CDO_CANONICAL, STANDARD_AIR_DENSITY


BASE_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETERS = ["WS10M", "WD10M", "WS50M", "T2M", "RH2M"]
COMMUNITY = "RE"
FORMAT = "JSON"
START = "20221231"
END = "20240101"
REQUEST_DELAY_SECONDS = 2
RETRY_DELAY_SECONDS = 10
LONG_OUTPUT = Path("CDO_grid_wind_2023_long.csv")
WIDE_OUTPUT = Path("CDO_grid_wind_2023_wide.csv")


@dataclass(frozen=True)
class GridPoint:
    grid_row: int
    grid_col: int
    latitude: float
    longitude: float

    @property
    def grid_id(self) -> str:
        return f"R{self.grid_row}C{self.grid_col}"


def build_url(latitude: float, longitude: float) -> str:
    params = ",".join(PARAMETERS)
    return (
        f"{BASE_URL}?parameters={params}&community={COMMUNITY}&format={FORMAT}"
        f"&latitude={latitude:.3f}&longitude={longitude:.3f}&start={START}&end={END}"
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


def expected_civil_hours() -> pd.DatetimeIndex:
    return pd.date_range(start="2023-01-01 00:00:00", end="2023-12-31 23:00:00", freq="h")


def convert_lst_key(raw_key: str, longitude: float) -> datetime:
    lst_dt = datetime.strptime(raw_key, "%Y%m%d%H")
    lst_offset = timedelta(hours=longitude / 15.0)
    utc_dt = lst_dt - lst_offset
    civil_dt = utc_dt + timedelta(hours=8)
    return pd.Timestamp(civil_dt).round("h").to_pydatetime()


def build_nan_point_frame(point: GridPoint) -> pd.DataFrame:
    expected = expected_civil_hours()
    df = pd.DataFrame({"datetime": expected})
    df["grid_id"] = point.grid_id
    df["grid_row"] = point.grid_row
    df["grid_col"] = point.grid_col
    df["latitude"] = point.latitude
    df["longitude"] = point.longitude
    df["hour_of_year"] = np.arange(1, len(df) + 1, dtype=int)
    df["month"] = df["datetime"].dt.month
    df["hour_of_day"] = df["datetime"].dt.hour
    df["season"] = df["month"].map(season_for_month)
    for col in [
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "wind_speed_15m_ms",
        "air_temp_c",
        "relative_humidity_pct",
        "air_density_kgm3",
    ]:
        df[col] = np.nan
    df["outlier_flag"] = np.nan
    return df


def point_payload_to_frame(payload: dict, point: GridPoint) -> pd.DataFrame:
    parameter_data = payload["properties"]["parameter"]
    available = set(parameter_data.keys())
    expected = set(PARAMETERS)
    if available != expected:
        raise KeyError(f"Unexpected parameter keys for {point.grid_id}: {sorted(available)}")

    rows = []
    fill_value = payload["header"].get("fill_value", -999.0)
    for raw_key in sorted({key for values in parameter_data.values() for key in values.keys()}):
        civil_dt = convert_lst_key(raw_key, point.longitude)
        rows.append(
            {
                "datetime": civil_dt,
                "wind_speed_10m_ms": parameter_data["WS10M"].get(raw_key, np.nan),
                "wind_direction_10m_deg": parameter_data["WD10M"].get(raw_key, np.nan),
                "wind_speed_50m_ms": parameter_data["WS50M"].get(raw_key, np.nan),
                "air_temp_c": parameter_data["T2M"].get(raw_key, np.nan),
                "relative_humidity_pct": parameter_data["RH2M"].get(raw_key, np.nan),
            }
        )
    df = pd.DataFrame(rows)
    for col in [
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "air_temp_c",
        "relative_humidity_pct",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce").replace(fill_value, np.nan)

    duplicate_mask = df["datetime"].duplicated(keep=False)
    if duplicate_mask.any():
        print(f"Duplicate rounded timestamps for {point.grid_id}:")
        print(df.loc[duplicate_mask, ["datetime"]].to_string(index=False))
        raise ValueError(f"Duplicate timestamps for {point.grid_id}")

    df = df[(df["datetime"] >= pd.Timestamp("2023-01-01 00:00:00")) & (df["datetime"] <= pd.Timestamp("2023-12-31 23:00:00"))]
    df = df.set_index("datetime").sort_index().reindex(expected_civil_hours())
    df.index.name = "datetime"
    df = df.reset_index()

    df["grid_id"] = point.grid_id
    df["grid_row"] = point.grid_row
    df["grid_col"] = point.grid_col
    df["latitude"] = point.latitude
    df["longitude"] = point.longitude
    df["hour_of_year"] = np.arange(1, len(df) + 1, dtype=int)
    df["month"] = df["datetime"].dt.month
    df["hour_of_day"] = df["datetime"].dt.hour
    df["season"] = df["month"].map(season_for_month)
    df["wind_speed_15m_ms"] = df["wind_speed_10m_ms"] * (15.0 / 10.0) ** ALPHA_CDO_CANONICAL
    df["air_density_kgm3"] = STANDARD_AIR_DENSITY * (273.15 / (273.15 + df["air_temp_c"]))
    max_wind = df[["wind_speed_10m_ms", "wind_speed_50m_ms", "wind_speed_15m_ms"]].max(axis=1, skipna=True)
    df["outlier_flag"] = np.where(max_wind > 40.0, 1, 0)
    return df


def fetch_point_with_retry(point: GridPoint) -> pd.DataFrame:
    url = build_url(point.latitude, point.longitude)
    try:
        payload = fetch_json(url)
        return point_payload_to_frame(payload, point)
    except Exception as exc:
        print(f"Fetch failed for {point.grid_id} on first attempt: {exc}")
        print(f"Waiting {RETRY_DELAY_SECONDS} seconds before retry...")
        time.sleep(RETRY_DELAY_SECONDS)
        try:
            payload = fetch_json(url)
            return point_payload_to_frame(payload, point)
        except Exception as retry_exc:
            print(f"Retry failed for {point.grid_id}: {retry_exc}")
            print(f"Filling {point.grid_id} with NaN for all hours.")
            return build_nan_point_frame(point)


def validation_summary(long_df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        long_df.groupby(["grid_id", "grid_row", "grid_col", "latitude", "longitude"], as_index=False)
        .agg(
            row_count=("hour_of_year", "count"),
            missing_pct=("wind_speed_10m_ms", lambda s: float(s.isna().mean() * 100.0)),
            mean_ws15=("wind_speed_15m_ms", "mean"),
        )
        .sort_values(["grid_row", "grid_col"])
        .reset_index(drop=True)
    )
    print("Per-point validation summary:")
    print(grouped.to_string(index=False))
    for _, row in grouped.iterrows():
        flags = []
        if row["missing_pct"] > 5.0:
            flags.append("missing > 5%")
        if pd.notna(row["mean_ws15"]) and (row["mean_ws15"] < 1.5 or row["mean_ws15"] > 8.0):
            flags.append("mean wind speed out of range")
        if row["row_count"] != 8760:
            flags.append("row_count != 8760")
        if flags:
            print(f"Flagged {row['grid_id']}: {', '.join(flags)}")
    return grouped


def north_south_gradient_check(summary_df: pd.DataFrame) -> None:
    north_mean = summary_df.loc[summary_df["grid_row"] == 4, "mean_ws15"].mean()
    south_mean = summary_df.loc[summary_df["grid_row"] == 0, "mean_ws15"].mean()
    exists = bool(pd.notna(north_mean) and pd.notna(south_mean) and north_mean > south_mean)
    print(
        f"North-south gradient check: north row mean={north_mean:.6f}, south row mean={south_mean:.6f}, exists={exists}"
    )
    if not exists:
        print("North-south gradient not evident. MERRA-2 resolution may be too coarse to resolve it.")


def build_wide_frame(long_df: pd.DataFrame) -> pd.DataFrame:
    wide = long_df[["hour_of_year", "datetime"]].drop_duplicates().sort_values("hour_of_year").reset_index(drop=True)
    for grid_id in sorted(long_df["grid_id"].unique(), key=lambda x: (int(x[1]), int(x[3]))):
        point_df = long_df.loc[long_df["grid_id"] == grid_id, ["hour_of_year", "wind_speed_15m_ms", "wind_direction_10m_deg"]]
        point_df = point_df.sort_values("hour_of_year")
        wide[f"{grid_id}_ws15"] = point_df["wind_speed_15m_ms"].to_numpy()
        wide[f"{grid_id}_wd"] = point_df["wind_direction_10m_deg"].to_numpy()
    return wide


def main() -> None:
    started = time.perf_counter()
    latitudes = [8.282, 8.382, 8.482, 8.582, 8.682]
    longitudes = [124.447, 124.547, 124.647, 124.747, 124.847]
    points = [
        GridPoint(grid_row=row, grid_col=col, latitude=lat, longitude=lon)
        for row, lat in enumerate(latitudes)
        for col, lon in enumerate(longitudes)
    ]

    frames = []
    for idx, point in enumerate(points, start=1):
        print(
            f"Fetching point {idx} of 25: lat={point.latitude}, lon={point.longitude}, id={point.grid_id}"
        )
        frame = fetch_point_with_retry(point)
        frames.append(frame)
        if idx < len(points):
            time.sleep(REQUEST_DELAY_SECONDS)

    long_df = pd.concat(frames, ignore_index=True)
    long_columns = [
        "grid_id",
        "grid_row",
        "grid_col",
        "latitude",
        "longitude",
        "hour_of_year",
        "datetime",
        "month",
        "hour_of_day",
        "season",
        "wind_speed_10m_ms",
        "wind_direction_10m_deg",
        "wind_speed_50m_ms",
        "wind_speed_15m_ms",
        "air_temp_c",
        "relative_humidity_pct",
        "air_density_kgm3",
        "outlier_flag",
    ]
    long_df["datetime"] = pd.to_datetime(long_df["datetime"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    long_df = long_df[long_columns]
    long_df.to_csv(LONG_OUTPUT, index=False)
    print(f"Saved long format to {LONG_OUTPUT.resolve()}")

    wide_df = build_wide_frame(long_df.copy())
    wide_df.to_csv(WIDE_OUTPUT, index=False)
    print(f"Saved wide format to {WIDE_OUTPUT.resolve()}")

    summary_df = validation_summary(long_df)
    north_south_gradient_check(summary_df)

    elapsed = time.perf_counter() - started
    print(f"Elapsed time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
