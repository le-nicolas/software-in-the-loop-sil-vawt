from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import (
    GRID_IDS_ROW_MAJOR,
    GRID_LATITUDES,
    GRID_LONGITUDES,
    OPENMETEO_ARCHIVE_URL,
    OPENMETEO_ELEVATION_URL,
    OPENMETEO_REFINED_DATA_SOURCE,
    OPENMETEO_REFINED_SPATIAL_LABEL,
    OPENMETEO_REFINED_SPATIAL_METHOD,
    STANDARD_AIR_DENSITY,
)


LONG_OUTPUT = Path("CDO_grid_wind_2023_long_openmeteo.csv")
WIDE_OUTPUT = Path("CDO_grid_wind_2023_wide_openmeteo.csv")

HOURLY_VARIABLES = [
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_speed_100m",
    "wind_direction_100m",
    "temperature_2m",
    "relative_humidity_2m",
]


@dataclass(frozen=True)
class GridPoint:
    grid_id: str
    grid_row: int
    grid_col: int
    requested_latitude: float
    requested_longitude: float


def row_major_grid_points() -> list[GridPoint]:
    points: list[GridPoint] = []
    for row, latitude in enumerate(GRID_LATITUDES):
        for col, longitude in enumerate(GRID_LONGITUDES):
            points.append(
                GridPoint(
                    grid_id=f"R{row}C{col}",
                    grid_row=row,
                    grid_col=col,
                    requested_latitude=float(latitude),
                    requested_longitude=float(longitude),
                )
            )
    if [point.grid_id for point in points] != GRID_IDS_ROW_MAJOR:
        raise ValueError("GRID_IDS_ROW_MAJOR does not match the generated row-major grid")
    return points


def fetch_json(base_url: str, params: dict[str, str]) -> dict | list:
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    print(url)
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def fetch_openmeteo_grid(points: list[GridPoint]) -> list[dict]:
    params = {
        "latitude": ",".join(str(point.requested_latitude) for point in points),
        "longitude": ",".join(str(point.requested_longitude) for point in points),
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "Asia/Manila",
        "models": "era5_seamless",
    }
    payload = fetch_json(OPENMETEO_ARCHIVE_URL, params)
    if not isinstance(payload, list) or len(payload) != len(points):
        raise ValueError(f"Expected list payload of length {len(points)}, got {type(payload).__name__}")
    return payload


def fetch_openmeteo_elevation(points: list[GridPoint]) -> list[float]:
    params = {
        "latitude": ",".join(str(point.requested_latitude) for point in points),
        "longitude": ",".join(str(point.requested_longitude) for point in points),
    }
    payload = fetch_json(OPENMETEO_ELEVATION_URL, params)
    elevations = payload.get("elevation")
    if not isinstance(elevations, list) or len(elevations) != len(points):
        raise ValueError(f"Expected elevation list of length {len(points)}, got {elevations}")
    return [float(value) for value in elevations]


def wrap_degrees(degrees: np.ndarray) -> np.ndarray:
    return np.mod(degrees, 360.0)


def circular_difference_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b + 180.0) % 360.0 - 180.0


def interpolate_direction_deg(direction_10m: np.ndarray, direction_100m: np.ndarray, height_m: float) -> np.ndarray:
    ratio = (height_m - 10.0) / (100.0 - 10.0)
    delta = circular_difference_deg(direction_100m, direction_10m)
    return wrap_degrees(direction_10m + ratio * delta)


def point_frame(point: GridPoint, point_payload: dict, elevation_dem_m: float) -> pd.DataFrame:
    hourly = point_payload["hourly"]
    hourly_units = point_payload["hourly_units"]
    if hourly_units["wind_speed_10m"] != "km/h" or hourly_units["wind_speed_100m"] != "km/h":
        raise ValueError(f"Unexpected wind speed units: {hourly_units}")

    datetimes = pd.to_datetime(hourly["time"], format="%Y-%m-%dT%H:%M")
    if len(datetimes) != 8760:
        raise ValueError(f"{point.grid_id} expected 8760 hourly rows, got {len(datetimes)}")

    ws10_ms = np.array(hourly["wind_speed_10m"], dtype=float) / 3.6
    ws100_ms = np.array(hourly["wind_speed_100m"], dtype=float) / 3.6
    wd10_deg = np.array(hourly["wind_direction_10m"], dtype=float)
    wd100_deg = np.array(hourly["wind_direction_100m"], dtype=float)
    temp_c = np.array(hourly["temperature_2m"], dtype=float)
    rh_pct = np.array(hourly["relative_humidity_2m"], dtype=float)

    alpha = np.full_like(ws10_ms, np.nan, dtype=float)
    valid_alpha = (ws10_ms > 0.0) & (ws100_ms > 0.0)
    alpha[valid_alpha] = np.log(ws100_ms[valid_alpha] / ws10_ms[valid_alpha]) / np.log(100.0 / 10.0)

    ws15_ms = np.full_like(ws10_ms, np.nan, dtype=float)
    ws25_ms = np.full_like(ws10_ms, np.nan, dtype=float)
    ws40_ms = np.full_like(ws10_ms, np.nan, dtype=float)
    ws15_ms[valid_alpha] = ws10_ms[valid_alpha] * (15.0 / 10.0) ** alpha[valid_alpha]
    ws25_ms[valid_alpha] = ws10_ms[valid_alpha] * (25.0 / 10.0) ** alpha[valid_alpha]
    ws40_ms[valid_alpha] = ws10_ms[valid_alpha] * (40.0 / 10.0) ** alpha[valid_alpha]

    wd15_deg = interpolate_direction_deg(wd10_deg, wd100_deg, 15.0)
    air_density = STANDARD_AIR_DENSITY * (273.15 / (273.15 + temp_c))
    season = np.where(
        datetimes.month.isin([11, 12, 1, 2]),
        "Amihan",
        np.where(
            datetimes.month.isin([6, 7, 8, 9]),
            "Habagat",
            np.where(datetimes.month.isin([3, 4, 5]), "Transition_DryDown", "Transition_Rampup"),
        ),
    )
    max_wind = np.nanmax(np.column_stack([ws10_ms, ws15_ms, ws25_ms, ws40_ms, ws100_ms]), axis=1)

    return pd.DataFrame(
        {
            "grid_id": point.grid_id,
            "grid_row": point.grid_row,
            "grid_col": point.grid_col,
            "requested_latitude": point.requested_latitude,
            "requested_longitude": point.requested_longitude,
            "source_latitude": float(point_payload["latitude"]),
            "source_longitude": float(point_payload["longitude"]),
            "elevation_model_m": float(point_payload["elevation"]),
            "elevation_dem_m": elevation_dem_m,
            "hour_of_year": np.arange(1, len(datetimes) + 1, dtype=int),
            "datetime": datetimes.strftime("%Y-%m-%d %H:%M:%S"),
            "month": datetimes.month.astype(int),
            "hour_of_day": datetimes.hour.astype(int),
            "season": season,
            "wind_speed_10m_ms": ws10_ms,
            "wind_direction_10m_deg": wd10_deg,
            "wind_speed_15m_ms": ws15_ms,
            "wind_direction_15m_deg": wd15_deg,
            "wind_speed_25m_ms": ws25_ms,
            "wind_speed_40m_ms": ws40_ms,
            "wind_speed_100m_ms": ws100_ms,
            "wind_direction_100m_deg": wd100_deg,
            "alpha_10_100": alpha,
            "air_temp_c": temp_c,
            "relative_humidity_pct": rh_pct,
            "air_density_kgm3": air_density,
            "outlier_flag": np.where(max_wind > 40.0, 1, 0),
            "data_source": OPENMETEO_REFINED_DATA_SOURCE,
            "spatial_method": OPENMETEO_REFINED_SPATIAL_METHOD,
            "spatial_field_label": OPENMETEO_REFINED_SPATIAL_LABEL,
        }
    )


def build_long_frame(points: list[GridPoint]) -> pd.DataFrame:
    payload = fetch_openmeteo_grid(points)
    elevations = fetch_openmeteo_elevation(points)

    frames: list[pd.DataFrame] = []
    for point, point_payload, elevation in zip(points, payload, elevations, strict=True):
        frame = point_frame(point, point_payload, elevation)
        frames.append(frame)

    long_df = pd.concat(frames, ignore_index=True)
    expected_rows = len(points) * 8760
    if len(long_df) != expected_rows:
        raise ValueError(f"Expected {expected_rows} long rows, got {len(long_df)}")
    return long_df


def build_wide_frame(long_df: pd.DataFrame) -> pd.DataFrame:
    wide = long_df[["hour_of_year", "datetime"]].drop_duplicates().sort_values("hour_of_year").reset_index(drop=True)
    for grid_id in GRID_IDS_ROW_MAJOR:
        point_df = long_df.loc[long_df["grid_id"] == grid_id, ["hour_of_year", "wind_speed_15m_ms", "wind_direction_15m_deg"]]
        point_df = point_df.sort_values("hour_of_year")
        wide[f"{grid_id}_ws15"] = point_df["wind_speed_15m_ms"].to_numpy()
        wide[f"{grid_id}_wd"] = point_df["wind_direction_15m_deg"].to_numpy()
    if wide.shape != (8760, 52):
        raise ValueError(f"Wide CSV shape mismatch: expected (8760, 52), got {wide.shape}")
    return wide


def print_validation(long_df: pd.DataFrame, wide_df: pd.DataFrame) -> None:
    print(f"Long shape: {long_df.shape}")
    print(f"Wide shape: {wide_df.shape}")

    summary = (
        long_df.groupby("grid_id", sort=True)
        .agg(
            mean_ws15=("wind_speed_15m_ms", "mean"),
            mean_wd15=("wind_direction_15m_deg", "mean"),
            mean_alpha=("alpha_10_100", "mean"),
            missing_ws15_pct=("wind_speed_15m_ms", lambda s: float(s.isna().mean() * 100.0)),
            elevation_dem_m=("elevation_dem_m", "first"),
        )
        .reset_index()
    )
    print("Per-point refined summary:")
    print(summary.to_string(index=False))

    center = summary.loc[summary["grid_id"] == "R2C2"].iloc[0]
    north_mean = summary.loc[summary["grid_id"].str.startswith("R4"), "mean_ws15"].mean()
    south_mean = summary.loc[summary["grid_id"].str.startswith("R0"), "mean_ws15"].mean()
    direction_std_at_hour_1000 = wide_df.filter(regex="_wd$").iloc[999].std()
    direction_std_at_hour_4500 = wide_df.filter(regex="_wd$").iloc[4499].std()

    print(f"Center R2C2 mean ws15: {center['mean_ws15']:.6f} m/s")
    print(f"North row mean ws15: {north_mean:.6f} m/s")
    print(f"South row mean ws15: {south_mean:.6f} m/s")
    print(f"North greater than south: {north_mean > south_mean}")
    print(f"Direction std across 25 points at hour 1000: {direction_std_at_hour_1000:.6f} deg")
    print(f"Direction std across 25 points at hour 4500: {direction_std_at_hour_4500:.6f} deg")

    sample_cols = ["hour_of_year", "datetime", "R0C0_ws15", "R0C0_wd", "R2C2_ws15", "R2C2_wd", "R4C4_ws15", "R4C4_wd"]
    print("Wide sample:")
    print(wide_df.loc[[0, 999, 4499], sample_cols].to_string(index=False))


def main() -> None:
    points = row_major_grid_points()
    long_df = build_long_frame(points)
    wide_df = build_wide_frame(long_df)
    long_df.to_csv(LONG_OUTPUT, index=False)
    wide_df.to_csv(WIDE_OUTPUT, index=False)
    print_validation(long_df, wide_df)
    print(f"Saved {LONG_OUTPUT.resolve()}")
    print(f"Saved {WIDE_OUTPUT.resolve()}")


if __name__ == "__main__":
    main()
