from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from viz_common import SEASON_COLORS, dropna_for_plot, ensure_output_dir, generation_power_w, save_figure


def _sphere_surface(radius: float = 0.3, resolution: int = 18):
    theta = np.linspace(0, 2 * np.pi, resolution)
    phi = np.linspace(0, np.pi, resolution)
    x = radius * np.outer(np.cos(theta), np.sin(phi))
    y = radius * np.outer(np.sin(theta), np.sin(phi))
    z = radius * np.outer(np.ones_like(theta), np.cos(phi))
    return x, y, z


def _slider_labels(hours):
    labels = {}
    for idx in range(0, len(hours), 720):
        labels[idx + 1] = hours.iloc[idx]["datetime"].strftime("%b")
    return labels


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha:.4f})"


def estimate_viz3_build_seconds(df) -> float:
    n = len(df)
    # Conservative estimate based on frame count and 72-hour trail payload.
    return n * 0.0085


def build_viz3_interactive_slider(
    df,
    warn_threshold_seconds: float = 60.0,
    allow_exceed_threshold: bool = False,
) -> tuple[Path, float]:
    plot_df = dropna_for_plot(
        df,
        ["hour_of_year", "datetime", "wind_speed_15m_ms", "wind_direction_10m_deg", "season", "air_density_kgm3"],
        "Visualization 3",
    ).reset_index(drop=True)

    estimate_seconds = estimate_viz3_build_seconds(plot_df)
    print(f"Visualization 3 estimated build time: {estimate_seconds:.2f} seconds")
    if estimate_seconds > warn_threshold_seconds and not allow_exceed_threshold:
        raise RuntimeError(
            f"Visualization 3 is estimated to exceed {warn_threshold_seconds:.0f} seconds. "
            "Ask the user before downsampling."
        )

    radians = np.deg2rad(plot_df["wind_direction_10m_deg"].to_numpy())
    unit_u = np.sin(radians)
    unit_v = np.cos(radians)
    speeds = plot_df["wind_speed_15m_ms"].to_numpy()
    cone_u = unit_u * speeds
    cone_v = unit_v * speeds
    cone_w = np.zeros_like(cone_u)

    power_w = generation_power_w(plot_df).to_numpy()
    cumulative_kwh = np.cumsum(power_w) / 1000.0
    generating = (speeds >= 2.5).astype(int)
    cumulative_generating = np.cumsum(generating)
    rated_power_w = 0.5 * float(plot_df["air_density_kgm3"].mean()) * 4.0 * 0.35 * (12.0 ** 3)
    capacity_factor = cumulative_kwh / ((plot_df["hour_of_year"].to_numpy()) * rated_power_w / 1000.0)
    capacity_factor = np.nan_to_num(capacity_factor, nan=0.0, posinf=0.0, neginf=0.0)

    sphere_x, sphere_y, sphere_z = _sphere_surface()

    fig = go.Figure()
    fig.add_trace(
        go.Surface(
            x=sphere_x,
            y=sphere_y,
            z=sphere_z,
            showscale=False,
            opacity=0.6,
            colorscale=[[0, "#9a9a9a"], [1, "#9a9a9a"]],
            name="Rotor",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Cone(
            x=[0.0],
            y=[0.0],
            z=[0.0],
            u=[cone_u[0]],
            v=[cone_v[0]],
            w=[cone_w[0]],
            sizemode="absolute",
            sizeref=max(speeds.max() / 2.5, 1.0),
            anchor="tail",
            colorscale=[[0, SEASON_COLORS[plot_df.loc[0, "season"]]], [1, SEASON_COLORS[plot_df.loc[0, "season"]]]],
            showscale=False,
            name="Wind",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0.0],
            y=[0.0],
            z=[0.0],
            mode="markers",
            marker={"size": [3], "color": [_hex_to_rgba(SEASON_COLORS[plot_df.loc[0, "season"]], 1.0)], "opacity": 1.0},
            name="Ghost trail",
            hoverinfo="skip",
            showlegend=False,
        )
    )

    def annotation_text(i: int) -> tuple[str, str]:
        info_left = (
            f"Date/Time: {plot_df.loc[i, 'datetime']:%Y-%m-%d %H:%M:%S}<br>"
            f"Wind Speed: {plot_df.loc[i, 'wind_speed_15m_ms']:.3f} m/s<br>"
            f"Direction: {plot_df.loc[i, 'wind_direction_10m_deg']:.1f}°<br>"
            f"Season: {plot_df.loc[i, 'season']}<br>"
            f"Air Density: {plot_df.loc[i, 'air_density_kgm3']:.4f} kg/m³"
        )
        info_right = (
            f"Energy This Year: {cumulative_kwh[i]:.3f} kWh<br>"
            f"Hours Generating: {int(cumulative_generating[i])} of {int(plot_df.loc[i, 'hour_of_year'])}<br>"
            f"Capacity Factor So Far: {capacity_factor[i] * 100:.2f}%"
        )
        return info_left, info_right

    frames = []
    frame_build_start = time.perf_counter()
    for i in range(len(plot_df)):
        if i % 1000 == 0:
            print(f"Visualization 3 progress: building frame {i + 1} of {len(plot_df)}")
        trail_start = max(0, i - 71)
        trail_idx = np.arange(trail_start, i + 1)
        opacities = np.linspace(0.1, 1.0, len(trail_idx))
        sizes = np.linspace(2.0, 5.0, len(trail_idx))
        trail_colors = [
            _hex_to_rgba(SEASON_COLORS[season], alpha)
            for season, alpha in zip(plot_df.loc[trail_idx, "season"], opacities)
        ]
        left_text, right_text = annotation_text(i)
        frames.append(
            go.Frame(
                name=str(int(plot_df.loc[i, "hour_of_year"])),
                data=[
                    go.Cone(
                        x=[0.0],
                        y=[0.0],
                        z=[0.0],
                        u=[cone_u[i]],
                        v=[cone_v[i]],
                        w=[0.0],
                        sizemode="absolute",
                        sizeref=max(speeds.max() / 2.5, 1.0),
                        anchor="tail",
                        colorscale=[[0, SEASON_COLORS[plot_df.loc[i, "season"]]], [1, SEASON_COLORS[plot_df.loc[i, "season"]]]],
                        showscale=False,
                    ),
                    go.Scatter3d(
                        x=unit_u[trail_idx] * speeds[trail_idx],
                        y=unit_v[trail_idx] * speeds[trail_idx],
                        z=plot_df.loc[trail_idx, "hour_of_year"].to_numpy(),
                        mode="markers",
                        marker={
                            "size": sizes.tolist(),
                            "color": trail_colors,
                            "opacity": 1.0,
                        },
                        hovertemplate=(
                            "Datetime: %{customdata[0]}<br>"
                            "Speed: %{customdata[1]:.3f} m/s<br>"
                            "Direction: %{customdata[2]:.1f}°<br>"
                            "Season: %{customdata[3]}<extra></extra>"
                        ),
                        customdata=np.stack(
                            [
                                plot_df.loc[trail_idx, "datetime"].dt.strftime("%Y-%m-%d %H:%M:%S"),
                                plot_df.loc[trail_idx, "wind_speed_15m_ms"],
                                plot_df.loc[trail_idx, "wind_direction_10m_deg"],
                                plot_df.loc[trail_idx, "season"],
                            ],
                            axis=-1,
                        ),
                        showlegend=False,
                    ),
                ],
                traces=[1, 2],
                layout=go.Layout(
                    annotations=[
                        {
                            "text": left_text,
                            "xref": "paper",
                            "yref": "paper",
                            "x": 0.01,
                            "y": 0.99,
                            "showarrow": False,
                            "align": "left",
                            "bgcolor": "rgba(255,255,255,0.85)",
                        },
                        {
                            "text": right_text,
                            "xref": "paper",
                            "yref": "paper",
                            "x": 0.99,
                            "y": 0.01,
                            "showarrow": False,
                            "align": "right",
                            "bgcolor": "rgba(255,255,255,0.85)",
                        },
                    ]
                ),
            )
        )
    build_seconds = time.perf_counter() - frame_build_start
    print(f"Visualization 3 frame generation time: {build_seconds:.2f} seconds")

    first_left, first_right = annotation_text(0)
    labels = _slider_labels(plot_df)
    fig.frames = frames
    fig.update_layout(
        title="CDO Wind Playback 2023 — Interactive Slider",
        scene={
            "xaxis_title": "u direction",
            "yaxis_title": "v direction",
            "zaxis_title": "hour_of_year",
            "xaxis": {"range": [-max(speeds) * 1.1, max(speeds) * 1.1]},
            "yaxis": {"range": [-max(speeds) * 1.1, max(speeds) * 1.1]},
            "zaxis": {"range": [1, 8760]},
            "camera": {"eye": {"x": 1.6, "y": 1.6, "z": 1.1}},
        },
        annotations=[
            {
                "text": first_left,
                "xref": "paper",
                "yref": "paper",
                "x": 0.01,
                "y": 0.99,
                "showarrow": False,
                "align": "left",
                "bgcolor": "rgba(255,255,255,0.85)",
            },
            {
                "text": first_right,
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 0.01,
                "showarrow": False,
                "align": "right",
                "bgcolor": "rgba(255,255,255,0.85)",
            },
        ],
        updatemenus=[
            {
                "type": "buttons",
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": 50, "redraw": False}, "fromcurrent": True}],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                    },
                ],
            }
        ],
        sliders=[
            {
                "active": 0,
                "currentvalue": {"prefix": "Hour: "},
                "steps": [
                    {
                        "label": labels.get(hour, ""),
                        "method": "animate",
                        "args": [
                            [str(hour)],
                            {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"},
                        ],
                    }
                    for hour in plot_df["hour_of_year"]
                ],
            }
        ],
        showlegend=False,
    )

    output_path = ensure_output_dir() / "viz3_interactive_slider.html"
    save_figure(fig, output_path)
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Visualization 3 file size: {file_size_mb:.2f} MB")
    return output_path, float(cumulative_kwh[-1]), file_size_mb
