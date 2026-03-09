from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from CDO_project_constants import (
    CP_GENERIC,
    FINAL_CSV_SCHEMA,
    FINAL_CSV_SHAPE,
    STANDARD_AIR_DENSITY,
    SWEPT_AREA_M2,
    TURBINE_RATED_KW,
)
from viz_common import CSV_PATH, SEASON_COLORS, ensure_output_dir, save_figure


MONTH_TICKS = {
    1: "Jan",
    745: "Feb",
    1417: "Mar",
    2161: "Apr",
    2881: "May",
    3625: "Jun",
    4345: "Jul",
    5089: "Aug",
    5833: "Sep",
    6553: "Oct",
    7273: "Nov",
    7993: "Dec",
}
SEASON_ORDER = ["Amihan", "Habagat", "Transition_DryDown", "Transition_Rampup"]
SCALE = 0.8


def _load_master_csv() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    if list(df.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema does not match FINAL_CSV_SCHEMA")
    if df.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Expected shape {FINAL_CSV_SHAPE}, got {df.shape}")
    ws15_mean = float(df["wind_speed_15m_ms"].mean())
    if not (3.4 <= ws15_mean <= 3.9):
        raise ValueError(f"wind_speed_15m_ms mean is not approximately 3.69 m/s: {ws15_mean:.6f}")
    invalid_dir = df[(df["wind_direction_10m_deg"] < 0) | (df["wind_direction_10m_deg"] > 360)]
    if not invalid_dir.empty:
        raise ValueError("wind_direction_10m_deg contains values outside 0-360")
    print(f"CSV loads with shape {df.shape}")
    print(f"wind_speed_15m_ms mean: {ws15_mean:.6f}")
    print("wind_direction_10m_deg outside 0-360: 0")
    print("Season groups and row count:")
    print(df["season"].value_counts().sort_index().to_string())
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    return df


def build_viz6_quiver_field() -> Path:
    # Touch imported constants so this module is explicitly bound to project constants.
    _ = (CP_GENERIC, STANDARD_AIR_DENSITY, SWEPT_AREA_M2, TURBINE_RATED_KW)

    df = _load_master_csv()
    radians = np.deg2rad(df["wind_direction_10m_deg"].to_numpy())
    df["u"] = df["wind_speed_15m_ms"].to_numpy() * np.sin(radians)
    df["v"] = df["wind_speed_15m_ms"].to_numpy() * np.cos(radians)
    df["w"] = 0.0
    df["tip_x"] = df["u"] * SCALE
    df["tip_y"] = df["v"] * SCALE
    df["tip_z"] = df["hour_of_year"]

    print("U stats:")
    print(f"min={df['u'].min():.6f}, max={df['u'].max():.6f}, mean={df['u'].mean():.6f}")
    print("V stats:")
    print(f"min={df['v'].min():.6f}, max={df['v'].max():.6f}, mean={df['v'].mean():.6f}")
    print("Season groups and row count:")
    print(df["season"].value_counts().sort_index().to_string())

    first3 = pd.DataFrame(
        {
            "hour_of_year": df["hour_of_year"].head(3),
            "base_x": 0.0,
            "base_y": 0.0,
            "base_z": df["hour_of_year"].head(3),
            "tip_x": df["tip_x"].head(3),
            "tip_y": df["tip_y"].head(3),
            "tip_z": df["tip_z"].head(3),
        }
    )
    print("First 3 arrow base/tip rows:")
    print(first3.to_string(index=False))

    fig = go.Figure()
    for season in SEASON_ORDER:
        season_df = df.loc[df["season"] == season].copy()
        xs: list[float | None] = []
        ys: list[float | None] = []
        zs: list[float | None] = []
        for _, row in season_df.iterrows():
            xs.extend([0.0, row["tip_x"], None])
            ys.extend([0.0, row["tip_y"], None])
            zs.extend([row["hour_of_year"], row["hour_of_year"], None])

        fig.add_trace(
            go.Scatter3d(
                x=xs,
                y=ys,
                z=zs,
                mode="lines",
                line={"color": SEASON_COLORS[season], "width": 3},
                name=season,
                hoverinfo="skip",
                showlegend=True,
            )
        )
        fig.add_trace(
            go.Scatter3d(
                x=season_df["tip_x"],
                y=season_df["tip_y"],
                z=season_df["tip_z"],
                mode="markers",
                marker={"size": 2, "color": SEASON_COLORS[season], "opacity": 0.9},
                name=f"{season} tips",
                legendgroup=season,
                showlegend=False,
                customdata=np.stack(
                    [
                        season_df["datetime"].dt.strftime("%Y-%m-%d %H:%M:%S"),
                        season_df["wind_speed_15m_ms"],
                        season_df["wind_direction_10m_deg"],
                        season_df["season"],
                    ],
                    axis=-1,
                ),
                hovertemplate=(
                    "Datetime: %{customdata[0]}<br>"
                    "Wind speed: %{customdata[1]:.3f} m/s<br>"
                    "Direction: %{customdata[2]:.1f}°<br>"
                    "Season: %{customdata[3]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="CDO Wind Quiver Field 2023 — All Hours Simultaneous (15m, civil UTC+8)",
        scene={
            "xaxis_title": "U east-west (m/s)",
            "yaxis_title": "V north-south (m/s)",
            "zaxis_title": "hour_of_year",
            "xaxis": {"range": [-8, 8]},
            "yaxis": {"range": [-8, 8]},
            "zaxis": {
                "range": [1, 8760],
                "tickvals": list(MONTH_TICKS.keys()),
                "ticktext": list(MONTH_TICKS.values()),
            },
            "camera": {"eye": {"x": 1.5, "y": 1.5, "z": 0.8}},
            "aspectmode": "manual",
            "aspectratio": {"x": 1.0, "y": 1.0, "z": 2.1},
        },
        legend={"title": {"text": "Season"}},
    )

    output_path = ensure_output_dir() / "viz6_quiver_field.html"
    save_figure(fig, output_path)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"viz6 file size: {file_size_mb:.2f} MB")
    return output_path


if __name__ == "__main__":
    build_viz6_quiver_field()
