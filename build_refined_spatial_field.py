from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import ALPHA_CDO_CANONICAL, FINAL_CSV_SCHEMA, FINAL_CSV_SHAPE


MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
MANUAL_INPUT_CSV = Path("CDO_gwa_manual_template.csv")
LONG_OUTPUT = Path("CDO_grid_wind_2023_long_refined.csv")
WIDE_OUTPUT = Path("CDO_grid_wind_2023_wide_refined.csv")

REFINED_DATA_SOURCE = "GWA_manual_refined"
REFINED_SPATIAL_METHOD = "MERRA2_center * manual_speed_multiplier + manual_direction_offset"
REFINED_SPATIAL_LABEL = (
    "Spatial field: MERRA-2 center time series refined with manually entered "
    "Global Wind Atlas point adjustments. Speed and direction refinements are "
    "user-supplied, not automatically fetched."
)


@dataclass(frozen=True)
class ManualPoint:
    grid_id: str
    grid_row: int
    grid_col: int
    latitude: float
    longitude: float
    speed_multiplier: float
    direction_offset_deg: float


def load_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_CSV)
    if list(df.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema mismatch")
    if df.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape mismatch: expected {FINAL_CSV_SHAPE}, got {df.shape}")
    return df


def load_manual_points() -> list[ManualPoint]:
    df = pd.read_csv(MANUAL_INPUT_CSV)
    required_cols = [
        "grid_id",
        "grid_row",
        "grid_col",
        "latitude",
        "longitude",
        "speed_multiplier",
        "direction_offset_deg",
        "ready_for_refined_build",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required manual-input columns: {missing}")
    if len(df) != 25:
        raise ValueError(f"Manual input must contain exactly 25 grid points, got {len(df)}")
    if set(df["grid_id"]) != {f"R{r}C{c}" for r in range(5) for c in range(5)}:
        raise ValueError("Manual input grid_id set is incomplete or invalid")
    if not (df["ready_for_refined_build"] == 1).all():
        raise ValueError(
            "Manual input template is not marked ready. Set ready_for_refined_build = 1 for all 25 rows once manual GWA values are entered."
        )
    if (df["speed_multiplier"] <= 0).any():
        raise ValueError("speed_multiplier must be positive for all grid points")
    return [
        ManualPoint(
            grid_id=row.grid_id,
            grid_row=int(row.grid_row),
            grid_col=int(row.grid_col),
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            speed_multiplier=float(row.speed_multiplier),
            direction_offset_deg=float(row.direction_offset_deg),
        )
        for row in df.sort_values(["grid_row", "grid_col"]).itertuples(index=False)
    ]


def build_long_frame(master: pd.DataFrame, points: list[ManualPoint]) -> pd.DataFrame:
    ws10_factor = (15.0 / 10.0) ** ALPHA_CDO_CANONICAL
    ws50_factor = (50.0 / 10.0) ** ALPHA_CDO_CANONICAL
    base = master[
        [
            "hour_of_year",
            "datetime",
            "month",
            "hour_of_day",
            "season",
            "air_temp_c",
            "relative_humidity_pct",
            "air_density_kgm3",
            "wind_speed_15m_ms",
            "wind_direction_10m_deg",
        ]
    ].copy()

    frames: list[pd.DataFrame] = []
    for point in points:
        frame = base.copy()
        frame["grid_id"] = point.grid_id
        frame["grid_row"] = point.grid_row
        frame["grid_col"] = point.grid_col
        frame["latitude"] = point.latitude
        frame["longitude"] = point.longitude
        frame["wind_speed_15m_ms"] = frame["wind_speed_15m_ms"] * point.speed_multiplier
        frame["wind_direction_10m_deg"] = np.mod(frame["wind_direction_10m_deg"] + point.direction_offset_deg, 360.0)
        frame["wind_speed_10m_ms"] = frame["wind_speed_15m_ms"] / ws10_factor
        frame["wind_speed_50m_ms"] = frame["wind_speed_10m_ms"] * ws50_factor
        max_wind = frame[["wind_speed_10m_ms", "wind_speed_15m_ms", "wind_speed_50m_ms"]].max(axis=1)
        frame["outlier_flag"] = np.where(max_wind > 40.0, 1, 0)
        frame["data_source"] = REFINED_DATA_SOURCE
        frame["spatial_method"] = REFINED_SPATIAL_METHOD
        frame["spatial_field_label"] = REFINED_SPATIAL_LABEL
        frames.append(frame)

    long_df = pd.concat(frames, ignore_index=True)
    return long_df[
        [
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
            "data_source",
            "spatial_method",
            "spatial_field_label",
        ]
    ]


def build_wide_frame(long_df: pd.DataFrame) -> pd.DataFrame:
    wide = long_df[["hour_of_year", "datetime"]].drop_duplicates().sort_values("hour_of_year").reset_index(drop=True)
    ordered_ids = [f"R{r}C{c}" for r in range(5) for c in range(5)]
    for grid_id in ordered_ids:
        point_df = long_df.loc[long_df["grid_id"] == grid_id, ["hour_of_year", "wind_speed_15m_ms", "wind_direction_10m_deg"]]
        point_df = point_df.sort_values("hour_of_year")
        wide[f"{grid_id}_ws15"] = point_df["wind_speed_15m_ms"].to_numpy()
        wide[f"{grid_id}_wd"] = point_df["wind_direction_10m_deg"].to_numpy()
    return wide


def main() -> None:
    master = load_master()
    points = load_manual_points()
    long_df = build_long_frame(master, points)
    wide_df = build_wide_frame(long_df)
    long_df.to_csv(LONG_OUTPUT, index=False)
    wide_df.to_csv(WIDE_OUTPUT, index=False)
    print(f"Saved refined long CSV to {LONG_OUTPUT.resolve()}")
    print(f"Saved refined wide CSV to {WIDE_OUTPUT.resolve()}")
    print("Refined build source: manual Global Wind Atlas pipeline scaffold")


if __name__ == "__main__":
    main()
