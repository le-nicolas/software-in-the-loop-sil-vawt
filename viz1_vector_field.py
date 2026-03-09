from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from viz_common import SEASON_COLORS, dropna_for_plot, ensure_output_dir, save_figure


def build_viz1_vector_field(df):
    plot_df = dropna_for_plot(
        df,
        ["hour_of_year", "wind_speed_15m_ms", "wind_direction_10m_deg", "season", "datetime"],
        "Visualization 1",
    )
    radians = np.deg2rad(plot_df["wind_direction_10m_deg"].to_numpy())
    plot_df["u"] = plot_df["wind_speed_15m_ms"].to_numpy() * np.sin(radians)
    plot_df["v"] = plot_df["wind_speed_15m_ms"].to_numpy() * np.cos(radians)

    marker_sizes = np.interp(
        plot_df["wind_speed_15m_ms"],
        (plot_df["wind_speed_15m_ms"].min(), plot_df["wind_speed_15m_ms"].max()),
        (3.0, 12.0),
    )

    fig = go.Figure()
    for season, season_df in plot_df.groupby("season", sort=False):
        fig.add_trace(
            go.Scatter3d(
                x=season_df["u"],
                y=season_df["v"],
                z=season_df["hour_of_year"],
                mode="markers",
                name=season,
                marker={
                    "size": marker_sizes[season_df.index],
                    "color": SEASON_COLORS[season],
                    "opacity": 0.75,
                },
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
                    "Speed (15m): %{customdata[1]:.3f} m/s<br>"
                    "Direction: %{customdata[2]:.1f}°<br>"
                    "Season: %{customdata[3]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="CDO Wind Vectors — Full Year 2023 (15m height, civil UTC+8)",
        scene={
            "xaxis_title": "u east-west (m/s)",
            "yaxis_title": "v north-south (m/s)",
            "zaxis_title": "hour_of_year",
            "camera": {"eye": {"x": 1.5, "y": 1.5, "z": 1.0}},
        },
        legend={"title": {"text": "Season"}},
    )

    output_path = ensure_output_dir() / "viz1_vector_field.html"
    save_figure(fig, output_path)
    return output_path
