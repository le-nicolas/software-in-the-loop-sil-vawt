from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from viz_common import dropna_for_plot, energy_density_wm2, ensure_output_dir, save_figure


DIRECTION_LABELS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def make_cuboid(x0, x1, y0, y1, z0, z1, color, opacity, name, showscale=False, color_value=None, color_scale="Viridis", cmin=None, cmax=None):
    x = [x0, x1, x1, x0, x0, x1, x1, x0]
    y = [y0, y0, y1, y1, y0, y0, y1, y1]
    z = [z0, z0, z0, z0, z1, z1, z1, z1]
    i = [0, 0, 0, 1, 1, 2, 4, 4, 5, 6, 4, 3]
    j = [1, 2, 4, 2, 5, 3, 5, 7, 6, 7, 0, 7]
    k = [2, 4, 1, 5, 2, 7, 7, 5, 7, 3, 3, 6]
    mesh_kwargs = {
        "x": x,
        "y": y,
        "z": z,
        "i": i,
        "j": j,
        "k": k,
        "name": name,
        "opacity": opacity,
        "flatshading": True,
        "hoverinfo": "skip",
        "showscale": showscale,
    }
    if color_value is None:
        mesh_kwargs["color"] = color
    else:
        mesh_kwargs["intensity"] = np.full(8, color_value, dtype=float)
        mesh_kwargs["colorscale"] = color_scale
        mesh_kwargs["cmin"] = cmin
        mesh_kwargs["cmax"] = cmax
        mesh_kwargs["colorbar"] = {"title": "Mean speed (m/s)"} if showscale else None
    return go.Mesh3d(**mesh_kwargs)


def build_viz2_wind_rose(df):
    plot_df = dropna_for_plot(
        df,
        ["wind_speed_15m_ms", "wind_direction_10m_deg", "air_density_kgm3"],
        "Visualization 2",
    )
    directions = np.mod(plot_df["wind_direction_10m_deg"].to_numpy(), 360.0)
    bins = np.arange(-11.25, 371.25, 22.5)
    indices = pd.Series(
        pd.cut(directions, bins=bins, labels=False, include_lowest=True, right=False)
    )
    indices = indices.fillna(0).astype(int) % 16
    plot_df["direction_bin"] = [DIRECTION_LABELS[i] for i in indices]
    plot_df["energy_density"] = energy_density_wm2(plot_df)

    summary = (
        plot_df.groupby("direction_bin", sort=False)
        .agg(
            frequency=("hour_of_year", "count"),
            mean_speed=("wind_speed_15m_ms", "mean"),
            energy_content=("energy_density", "sum"),
        )
        .reindex(DIRECTION_LABELS)
        .fillna(0.0)
        .reset_index()
    )

    angles = np.deg2rad(np.arange(0, 360, 22.5))
    radius = 1.0
    summary["x"] = radius * np.sin(angles)
    summary["y"] = radius * np.cos(angles)

    energy_max = float(summary["energy_content"].max())
    freq_max = float(summary["frequency"].max())
    mean_speed_min = float(summary["mean_speed"].min())
    mean_speed_max = float(summary["mean_speed"].max())

    fig = go.Figure()
    bar_half = 0.12
    for idx, row in summary.iterrows():
        energy_height = 0.0 if energy_max == 0 else (row["energy_content"] / energy_max) * 10.0
        freq_height = 0.0 if freq_max == 0 else (row["frequency"] / freq_max) * 4.0
        fig.add_trace(
            make_cuboid(
                row["x"] - bar_half,
                row["x"] + bar_half,
                row["y"] - bar_half,
                row["y"] + bar_half,
                0.0,
                energy_height,
                color=None,
                opacity=0.95,
                name=row["direction_bin"],
                showscale=idx == 0,
                color_value=row["mean_speed"],
                cmin=mean_speed_min,
                cmax=mean_speed_max,
            )
        )
        fig.add_trace(
            make_cuboid(
                row["x"] - bar_half / 2.0,
                row["x"] + bar_half / 2.0,
                row["y"] - bar_half / 2.0,
                row["y"] + bar_half / 2.0,
                0.0,
                freq_height,
                color="rgba(80,80,80,0.35)",
                opacity=0.35,
                name=f"{row['direction_bin']} frequency",
            )
        )
        fig.add_trace(
            go.Scatter3d(
                x=[row["x"]],
                y=[row["y"]],
                z=[max(energy_height, freq_height) + 0.35],
                mode="text",
                text=[row["direction_bin"]],
                showlegend=False,
                hovertemplate=(
                    f"Direction: {row['direction_bin']}<br>"
                    f"Frequency: {int(row['frequency'])}<br>"
                    f"Mean speed: {row['mean_speed']:.3f} m/s<br>"
                    f"Energy content: {row['energy_content']:.3f} W/m²·h<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title="CDO Wind Rose 2023 — Energy Content by Direction",
        scene={
            "xaxis_title": "Compass X",
            "yaxis_title": "Compass Y",
            "zaxis_title": "Relative height",
            "camera": {"eye": {"x": 1.5, "y": 1.5, "z": 1.2}},
        },
        showlegend=False,
    )

    output_path = ensure_output_dir() / "viz2_wind_rose_3d.html"
    save_figure(fig, output_path)
    dominant_direction = summary.loc[summary["energy_content"].idxmax(), "direction_bin"]
    return output_path, summary, dominant_direction
