from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import ALPHA_CDO_CANONICAL, CDO_CENTER_WS15_MEAN, FINAL_CSV_SCHEMA, FINAL_CSV_SHAPE
from CDO_spatial_multipliers import DATA_SOURCE, SPATIAL_FIELD_LABEL, SPATIAL_METHOD, SPATIAL_MULTIPLIERS


MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
LONG_OUTPUT = Path("CDO_grid_wind_2023_long.csv")
WIDE_OUTPUT = Path("CDO_grid_wind_2023_wide.csv")
LATITUDES = [8.282, 8.382, 8.482, 8.582, 8.682]
LONGITUDES = [124.447, 124.547, 124.647, 124.747, 124.847]


@dataclass(frozen=True)
class GridPoint:
    grid_row: int
    grid_col: int
    latitude: float
    longitude: float

    @property
    def grid_id(self) -> str:
        return f"R{self.grid_row}C{self.grid_col}"


def grid_points() -> list[GridPoint]:
    return [
        GridPoint(grid_row=row, grid_col=col, latitude=lat, longitude=lon)
        for row, lat in enumerate(LATITUDES)
        for col, lon in enumerate(LONGITUDES)
    ]


def load_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_CSV)
    if list(df.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema mismatch")
    if df.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape mismatch: expected {FINAL_CSV_SHAPE}, got {df.shape}")
    return df


def build_long_frame(master: pd.DataFrame) -> pd.DataFrame:
    ws10_factor = (15.0 / 10.0) ** ALPHA_CDO_CANONICAL
    ws50_factor = (50.0 / 10.0) ** ALPHA_CDO_CANONICAL
    base = master[
        [
            "hour_of_year",
            "datetime",
            "month",
            "hour_of_day",
            "season",
            "wind_direction_10m_deg",
            "air_temp_c",
            "relative_humidity_pct",
            "air_density_kgm3",
        ]
    ].copy()

    frames: list[pd.DataFrame] = []
    for point in grid_points():
        multiplier = SPATIAL_MULTIPLIERS[point.grid_id]
        frame = base.copy()
        frame["grid_id"] = point.grid_id
        frame["grid_row"] = point.grid_row
        frame["grid_col"] = point.grid_col
        frame["latitude"] = point.latitude
        frame["longitude"] = point.longitude
        frame["data_source"] = DATA_SOURCE
        frame["spatial_method"] = SPATIAL_METHOD
        frame["spatial_field_label"] = SPATIAL_FIELD_LABEL
        frame["wind_speed_15m_ms"] = master["wind_speed_15m_ms"] * multiplier
        frame["wind_speed_10m_ms"] = frame["wind_speed_15m_ms"] / ws10_factor
        frame["wind_speed_50m_ms"] = frame["wind_speed_10m_ms"] * ws50_factor
        max_wind = frame[["wind_speed_10m_ms", "wind_speed_15m_ms", "wind_speed_50m_ms"]].max(axis=1)
        frame["outlier_flag"] = np.where(max_wind > 40.0, 1, 0)
        frames.append(frame)

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
        "data_source",
        "spatial_method",
        "spatial_field_label",
    ]
    return long_df[long_columns]


def build_wide_frame(long_df: pd.DataFrame) -> pd.DataFrame:
    wide = long_df[["hour_of_year", "datetime"]].drop_duplicates().sort_values("hour_of_year").reset_index(drop=True)
    ordered_ids = [point.grid_id for point in grid_points()]
    for grid_id in ordered_ids:
        point_df = long_df.loc[long_df["grid_id"] == grid_id, ["hour_of_year", "wind_speed_15m_ms", "wind_direction_10m_deg"]]
        point_df = point_df.sort_values("hour_of_year")
        wide[f"{grid_id}_ws15"] = point_df["wind_speed_15m_ms"].to_numpy()
        wide[f"{grid_id}_wd"] = point_df["wind_direction_10m_deg"].to_numpy()
    return wide


def print_summary(long_df: pd.DataFrame, master: pd.DataFrame) -> None:
    summary = (
        long_df.groupby(["grid_id", "grid_row", "grid_col", "latitude", "longitude"], as_index=False)
        .agg(mean_ws15=("wind_speed_15m_ms", "mean"))
        .sort_values(["grid_row", "grid_col"])
        .reset_index(drop=True)
    )
    print("Revised spatial summary:")
    print(summary.to_string(index=False))

    north_mean = summary.loc[summary["grid_row"] == 4, "mean_ws15"].mean()
    center_mean = summary.loc[summary["grid_id"] == "R2C2", "mean_ws15"].iloc[0]
    south_mean = summary.loc[summary["grid_row"] == 0, "mean_ws15"].mean()
    print(
        f"North > center > south check: north={north_mean:.6f}, center={center_mean:.6f}, south={south_mean:.6f}, "
        f"passes={north_mean > center_mean > south_mean}"
    )
    print(f"Macajalar Bay gradient visible: {north_mean > south_mean}")

    center_master_mean = float(master["wind_speed_15m_ms"].mean())
    center_match = np.isclose(center_mean, center_master_mean, rtol=1e-6)
    print(
        f"Center mean check R2C2 vs master: grid={center_mean:.6f}, master={center_master_mean:.6f}, matches={center_match}"
    )
    if not center_match:
        raise ValueError("R2C2 mean does not match current master CSV within rtol=1e-6")
    if not np.isclose(center_master_mean, CDO_CENTER_WS15_MEAN, rtol=1e-6):
        raise ValueError("CDO_CENTER_WS15_MEAN constant does not match current master mean within rtol=1e-6")


def main() -> None:
    master = load_master()
    long_df = build_long_frame(master)
    wide_df = build_wide_frame(long_df)

    long_df.to_csv(LONG_OUTPUT, index=False)
    wide_df.to_csv(WIDE_OUTPUT, index=False)
    print(f"Saved hybrid long CSV to {LONG_OUTPUT.resolve()}")
    print(f"Saved hybrid wide CSV to {WIDE_OUTPUT.resolve()}")
    print_summary(long_df, master)


if __name__ == "__main__":
    main()
