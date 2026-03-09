from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
from scipy.interpolate import griddata

from dash import Dash, Input, Output, State, callback, dcc, html

from CDO_project_constants import (
    ALPHA_CDO_CANONICAL,
    CP_GENERIC,
    FINAL_CSV_SCHEMA,
    FINAL_CSV_SHAPE,
    SWEPT_AREA_M2,
    TURBINE_RATED_KW,
)


WIDE_CSV = "CDO_grid_wind_2023_wide.csv"
MASTER_CSV = "CDO_wind_2023_hourly.csv"
GRADIENTS_CSV = "CDO_wind_2023_gradients.csv"
PORT = 8050
BOX_MIN = -12.0
BOX_MAX = 12.0
GRID_AXIS = np.array([-8.0, -4.0, 0.0, 4.0, 8.0])
INTERP_AXIS = np.linspace(-7.2, 7.2, 10)
ARROW_SCALE = 0.8
MONTH_MARKS = {
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
HEIGHT_LEVELS = {
    15: 0.0,
    25: 4.0,
    40: 8.0,
}
HEIGHT_STYLES = {
    15: {"width": 3, "opacity": 1.0, "marker_size": 6},
    25: {"width": 2, "opacity": 0.7, "marker_size": 4},
    40: {"width": 1.5, "opacity": 0.45, "marker_size": 3},
}


@dataclass(frozen=True)
class PreparedData:
    wide: pd.DataFrame
    meta: pd.DataFrame
    grid_ids: list[str]
    real_x: np.ndarray
    real_y: np.ndarray
    interp_x: np.ndarray
    interp_y: np.ndarray
    ws15_matrix: np.ndarray
    wd_matrix: np.ndarray
    u15_matrix: np.ndarray
    v15_matrix: np.ndarray
    cumulative_kwh: np.ndarray
    hours_generating: np.ndarray
    capacity_factor: np.ndarray


def load_data() -> PreparedData:
    wide = pd.read_csv(WIDE_CSV)
    master = pd.read_csv(MASTER_CSV)
    gradients = pd.read_csv(GRADIENTS_CSV)[["hour_of_year", "TI_24h", "turbulence_class"]]

    if list(master.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema mismatch")
    if master.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape mismatch: expected {FINAL_CSV_SHAPE}, got {master.shape}")
    if wide.shape != (8760, 52):
        raise ValueError(f"Wide CSV shape mismatch: expected (8760, 52), got {wide.shape}")

    master["datetime"] = pd.to_datetime(master["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    meta = master.merge(gradients, on="hour_of_year", how="left", suffixes=("", "_grad"))
    meta["TI_24h"] = meta["TI_24h"].fillna(0.15)
    meta["turbulence_class"] = meta["turbulence_class"].fillna(
        meta["TI_24h"].apply(lambda x: "A" if x < 0.12 else "B" if x <= 0.14 else "C")
    )

    power_kw = (
        0.5
        * meta["air_density_kgm3"]
        * np.power(meta["wind_speed_15m_ms"], 3)
        * SWEPT_AREA_M2
        * CP_GENERIC
        / 1000.0
    ).clip(upper=TURBINE_RATED_KW)
    power_kw = power_kw.where(meta["wind_speed_15m_ms"] >= 2.5, 0.0)
    cumulative_kwh = power_kw.cumsum().to_numpy()
    hours_generating = (meta["wind_speed_15m_ms"] >= 2.5).astype(int).cumsum().to_numpy()
    capacity_factor = np.nan_to_num(cumulative_kwh / (meta["hour_of_year"].to_numpy() * TURBINE_RATED_KW), nan=0.0)

    grid_ids = [f"R{r}C{c}" for r in range(5) for c in range(5)]
    ws15_matrix = np.column_stack([wide[f"{gid}_ws15"].to_numpy() for gid in grid_ids])
    wd_matrix = np.column_stack([wide[f"{gid}_wd"].to_numpy() for gid in grid_ids])
    radians = np.deg2rad(wd_matrix)
    u15_matrix = ws15_matrix * np.sin(radians)
    v15_matrix = ws15_matrix * np.cos(radians)

    grid_points = [(x, y) for y in GRID_AXIS for x in GRID_AXIS]
    real_x = np.array([pt[0] for pt in grid_points], dtype=float)
    real_y = np.array([pt[1] for pt in grid_points], dtype=float)
    interp_mesh_x, interp_mesh_y = np.meshgrid(INTERP_AXIS, INTERP_AXIS)

    return PreparedData(
        wide=wide,
        meta=meta,
        grid_ids=grid_ids,
        real_x=real_x,
        real_y=real_y,
        interp_x=interp_mesh_x.ravel(),
        interp_y=interp_mesh_y.ravel(),
        ws15_matrix=ws15_matrix,
        wd_matrix=wd_matrix,
        u15_matrix=u15_matrix,
        v15_matrix=v15_matrix,
        cumulative_kwh=cumulative_kwh,
        hours_generating=hours_generating,
        capacity_factor=capacity_factor,
    )


def print_hour_checks(data: PreparedData, hour: int) -> None:
    idx = hour - 1
    ws_row = data.ws15_matrix[idx]
    wd_row = data.wd_matrix[idx]
    table = ws_row.reshape(5, 5)
    print(f"HOUR {hour}")
    print("All 25 grid point ws15 values:")
    print("        C0      C1      C2      C3      C4")
    for r in range(4, -1, -1):
        vals = table[r]
        print(f"R{r} " + " ".join(f"{v:7.3f}" for v in vals))
    north_mean = table[4].mean()
    south_mean = table[0].mean()
    print(f"North row mean > south row mean: {north_mean:.6f} > {south_mean:.6f} = {north_mean > south_mean}")
    ref_dir = float(wd_row[12])
    print(f"Reference direction R2C2: {ref_dir:.6f} deg")
    identical_to_center = bool(np.allclose(wd_row, ref_dir, rtol=0.0, atol=0.0))
    print(f"All 25 grid points have identical wd to R2C2: {identical_to_center}")
    print()


def build_box_traces() -> list[go.BaseTraceType]:
    traces: list[go.BaseTraceType] = []
    floor_x = np.array([[BOX_MIN, BOX_MAX], [BOX_MIN, BOX_MAX]])
    floor_y = np.array([[BOX_MIN, BOX_MIN], [BOX_MAX, BOX_MAX]])
    floor_z = np.array([[BOX_MIN, BOX_MIN], [BOX_MIN, BOX_MIN]])
    left_x = np.array([[BOX_MIN, BOX_MIN], [BOX_MIN, BOX_MIN]])
    left_y = np.array([[BOX_MIN, BOX_MAX], [BOX_MIN, BOX_MAX]])
    left_z = np.array([[BOX_MIN, BOX_MIN], [BOX_MAX, BOX_MAX]])
    back_x = np.array([[BOX_MIN, BOX_MAX], [BOX_MIN, BOX_MAX]])
    back_y = np.array([[BOX_MIN, BOX_MIN], [BOX_MIN, BOX_MIN]])
    back_z = np.array([[BOX_MIN, BOX_MIN], [BOX_MAX, BOX_MAX]])
    for x, y, z in [(floor_x, floor_y, floor_z), (left_x, left_y, left_z), (back_x, back_y, back_z)]:
        traces.append(
            go.Surface(
                x=x,
                y=y,
                z=z,
                showscale=False,
                opacity=0.02 if np.array_equal(z, floor_z) else 0.012,
                colorscale=[[0, "rgba(200,220,255,0.012)"], [1, "rgba(200,220,255,0.012)"]],
                hoverinfo="skip",
            )
        )

    corners = [
        (BOX_MIN, BOX_MIN, BOX_MIN),
        (BOX_MAX, BOX_MIN, BOX_MIN),
        (BOX_MAX, BOX_MAX, BOX_MIN),
        (BOX_MIN, BOX_MAX, BOX_MIN),
        (BOX_MIN, BOX_MIN, BOX_MAX),
        (BOX_MAX, BOX_MIN, BOX_MAX),
        (BOX_MAX, BOX_MAX, BOX_MAX),
        (BOX_MIN, BOX_MAX, BOX_MAX),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    x_lines, y_lines, z_lines = [], [], []
    for a, b in edges:
        x_lines.extend([corners[a][0], corners[b][0], None])
        y_lines.extend([corners[a][1], corners[b][1], None])
        z_lines.extend([corners[a][2], corners[b][2], None])
    traces.append(
        go.Scatter3d(
            x=x_lines,
            y=y_lines,
            z=z_lines,
            mode="lines",
            line={"color": "rgba(100,120,150,0.25)", "width": 0.5},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    return traces


def add_arrow_trace(
    fig: go.Figure,
    base_x,
    base_y,
    base_z,
    tip_x,
    tip_y,
    tip_z,
    speeds,
    opacity: float,
    width: float,
    marker_size: int,
    hovertext,
    cmin: float,
    cmax: float,
    line_opacity_factor: float = 1.0,
) -> None:
    for i in range(len(base_x)):
        if cmax <= cmin:
            normalized = 0.5
        else:
            normalized = float(np.clip((speeds[i] - cmin) / (cmax - cmin), 0.0, 1.0))
        color = sample_colorscale("RdYlBu_r", [normalized])[0]
        fig.add_trace(
            go.Scatter3d(
                x=[base_x[i], tip_x[i]],
                y=[base_y[i], tip_y[i]],
                z=[base_z[i], tip_z[i]],
                mode="lines",
                line={"color": color, "width": width},
                opacity=opacity * line_opacity_factor,
                hoverinfo="skip",
                showlegend=False,
            )
        )
    fig.add_trace(
        go.Scatter3d(
            x=tip_x,
            y=tip_y,
            z=tip_z,
            mode="markers",
            marker={
                "size": marker_size,
                "color": speeds,
                "colorscale": "RdYlBu_r",
                "cmin": cmin,
                "cmax": cmax,
                "opacity": opacity,
                "colorbar": {"title": "Wind Speed (m/s)"} if opacity >= 0.95 else None,
            },
            hoverinfo="text",
            hovertext=hovertext,
            showlegend=False,
        )
    )


def build_frame_figure(data: PreparedData, hour: int) -> go.Figure:
    idx = hour - 1
    row = data.meta.iloc[idx]
    fig = go.Figure()
    for trace in build_box_traces():
        fig.add_trace(trace)

    base_x = data.real_x
    base_y = data.real_y
    max_ws15_this_hour = float(np.max(data.ws15_matrix[idx]))
    dynamic_scale = max(8.0 / max_ws15_this_hour, 0.5)
    cmin = max(0.0, float(np.min(data.ws15_matrix[idx])) * 0.85)
    cmax = max(float(np.max(data.ws15_matrix[idx])) * 1.05, cmin + 0.5)

    # Make the 5x5 real grid obvious even before reading arrow directions.
    fig.add_trace(
        go.Scatter3d(
            x=base_x,
            y=base_y,
            z=np.zeros_like(base_x),
            mode="markers",
            marker={"size": 3, "color": "rgba(40,70,110,0.85)", "symbol": "square"},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    # Real vertical stack at 15m, 25m, and 40m.
    for height_m, z_level in HEIGHT_LEVELS.items():
        speed_h = data.ws15_matrix[idx] * (height_m / 15.0) ** ALPHA_CDO_CANONICAL
        dir_h = data.wd_matrix[idx]
        rad_h = np.deg2rad(dir_h)
        u_h = speed_h * np.sin(rad_h)
        v_h = speed_h * np.cos(rad_h)
        tip_x = base_x + u_h * dynamic_scale
        tip_y = base_y + v_h * dynamic_scale
        tip_z = np.full_like(base_x, z_level)
        style = HEIGHT_STYLES[height_m]
        hovertext = [
            "datetime: "
            f"{row['datetime']:%Y-%m-%d %H:%M:%S}<br>"
            f"Speed: {speed_h[i]:.2f} m/s<br>"
            f"Direction: {dir_h[i]:.1f}°<br>"
            f"Season: {row['season']}<br>"
            f"Grid: {data.grid_ids[i]}<br>"
            f"Height: {height_m}m"
            for i in range(len(base_x))
        ]
        add_arrow_trace(
            fig,
            base_x=base_x,
            base_y=base_y,
            base_z=np.full_like(base_x, z_level),
            tip_x=tip_x,
            tip_y=tip_y,
            tip_z=tip_z,
            speeds=speed_h,
            opacity=style["opacity"],
            width=style["width"],
            marker_size=style["marker_size"],
            hovertext=hovertext,
            cmin=cmin,
            cmax=cmax,
            line_opacity_factor=1.0,
        )

    # Interpolated 10x10 interior grid at 15m level.
    interp_u = griddata(
        points=np.column_stack([data.real_x, data.real_y]),
        values=data.u15_matrix[idx],
        xi=np.column_stack([data.interp_x, data.interp_y]),
        method="cubic",
    )
    interp_v = griddata(
        points=np.column_stack([data.real_x, data.real_y]),
        values=data.v15_matrix[idx],
        xi=np.column_stack([data.interp_x, data.interp_y]),
        method="cubic",
    )
    if np.isnan(interp_u).any():
        interp_u = np.where(
            np.isnan(interp_u),
            griddata(
                points=np.column_stack([data.real_x, data.real_y]),
                values=data.u15_matrix[idx],
                xi=np.column_stack([data.interp_x, data.interp_y]),
                method="nearest",
            ),
            interp_u,
        )
    if np.isnan(interp_v).any():
        interp_v = np.where(
            np.isnan(interp_v),
            griddata(
                points=np.column_stack([data.real_x, data.real_y]),
                values=data.v15_matrix[idx],
                xi=np.column_stack([data.interp_x, data.interp_y]),
                method="nearest",
            ),
            interp_v,
        )

    interp_speed = np.sqrt(interp_u**2 + interp_v**2)
    interp_tip_x = data.interp_x + interp_u * dynamic_scale
    interp_tip_y = data.interp_y + interp_v * dynamic_scale
    interp_z = np.zeros_like(data.interp_x)
    interp_hovertext = [
        "Interpolated point<br>"
        f"Speed: {interp_speed[i]:.2f} m/s<br>"
        "(derived from 25-point grid)"
        for i in range(len(data.interp_x))
    ]
    add_arrow_trace(
        fig,
        base_x=data.interp_x,
        base_y=data.interp_y,
        base_z=interp_z,
        tip_x=interp_tip_x,
        tip_y=interp_tip_y,
        tip_z=interp_z,
        speeds=interp_speed,
        opacity=0.15,
        width=0.5,
        marker_size=1,
        hovertext=interp_hovertext,
        cmin=cmin,
        cmax=cmax,
        line_opacity_factor=0.35,
    )

    # Wall shadows from 15m real arrow tips and interpolated tips.
    real_speed_15 = data.ws15_matrix[idx]
    rad_15 = np.deg2rad(data.wd_matrix[idx])
    real_tip_x_15 = base_x + real_speed_15 * np.sin(rad_15) * dynamic_scale
    real_tip_y_15 = base_y + real_speed_15 * np.cos(rad_15) * dynamic_scale
    shadow_x = np.concatenate([np.full_like(real_tip_x_15, BOX_MIN), np.full_like(interp_tip_x, BOX_MIN)])
    shadow_y = np.concatenate([real_tip_y_15, interp_tip_y])
    shadow_z = np.concatenate([np.zeros_like(real_tip_x_15), np.zeros_like(interp_tip_x)])
    fig.add_trace(
        go.Scatter3d(
            x=shadow_x,
            y=shadow_y,
            z=shadow_z,
            mode="markers",
            marker={"size": 1, "color": "rgba(80,80,80,0.06)"},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    shadow_x_back = np.concatenate([real_tip_x_15, interp_tip_x])
    shadow_y_back = np.concatenate([np.full_like(real_tip_y_15, BOX_MIN), np.full_like(interp_tip_y, BOX_MIN)])
    shadow_z_back = np.concatenate([np.zeros_like(real_tip_x_15), np.zeros_like(interp_tip_x)])
    fig.add_trace(
        go.Scatter3d(
            x=shadow_x_back,
            y=shadow_y_back,
            z=shadow_z_back,
            mode="markers",
            marker={"size": 1, "color": "rgba(80,80,80,0.06)"},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    info_left = (
        f"Date/Time: {row['datetime']:%Y-%m-%d %H:%M:%S}<br>"
        f"Mean Wind (CDO center): {data.ws15_matrix[idx, 12]:.3f} m/s<br>"
        f"Direction: {data.wd_matrix[idx, 12]:.1f}°<br>"
        f"Season: {row['season']}<br>"
        f"Turbulence Intensity: {row['TI_24h']:.3f}<br>"
        f"Turbulence Class: {row['turbulence_class']}"
    )
    info_right = (
        f"Energy This Year: {data.cumulative_kwh[idx]:.3f} kWh<br>"
        f"Hours Generating: {int(data.hours_generating[idx])} of {int(row['hour_of_year'])}<br>"
        f"Capacity Factor: {data.capacity_factor[idx] * 100:.2f}%"
    )

    fig.update_layout(
        title="CDO Spatial Wind Field 2023 — Hybrid Terrain-Multiplier Grid + Vertical Shear",
        scene={
            "xaxis_title": "East-West",
            "yaxis_title": "North-South",
            "zaxis_title": "Vertical / Height Layer",
            "xaxis": {"range": [BOX_MIN, BOX_MAX]},
            "yaxis": {"range": [BOX_MIN, BOX_MAX]},
            "zaxis": {"range": [BOX_MIN, BOX_MAX]},
            "camera": {"eye": {"x": 1.45, "y": 1.55, "z": 0.95}},
            "aspectmode": "cube",
        },
        annotations=[
            {
                "text": info_left,
                "xref": "paper",
                "yref": "paper",
                "x": 0.01,
                "y": 0.98,
                "showarrow": False,
                "align": "left",
                "bgcolor": "rgba(255,255,255,0.85)",
            },
            {
                "text": info_right,
                "xref": "paper",
                "yref": "paper",
                "x": 0.99,
                "y": 0.02,
                "showarrow": False,
                "align": "right",
                "bgcolor": "rgba(255,255,255,0.85)",
            },
            {
                "text": "Z=0: 15m  Z=4: 25m  Z=8: 40m",
                "xref": "paper",
                "yref": "paper",
                "x": 0.88,
                "y": 0.95,
                "showarrow": False,
                "align": "right",
                "bgcolor": "rgba(255,255,255,0.75)",
            },
        ],
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
    )
    return fig


DATA = load_data()
print_hour_checks(DATA, 1000)
print_hour_checks(DATA, 4500)

app = Dash(__name__)
app.layout = html.Div(
    [
        html.H2("CDO Spatial Wind Field 2023"),
        dcc.Graph(id="spatial-field-graph", figure=build_frame_figure(DATA, 1), style={"height": "85vh"}),
        html.Div(
            [
                html.Button("Play", id="play-button", n_clicks=0),
                html.Button("Pause", id="pause-button", n_clicks=0, style={"marginLeft": "8px"}),
                dcc.Slider(
                    id="hour-slider",
                    min=1,
                    max=8760,
                    step=1,
                    value=1,
                    marks=MONTH_MARKS,
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                dcc.Interval(id="play-interval", interval=150, disabled=True, n_intervals=0),
            ],
            style={"padding": "0 20px 20px 20px"},
        ),
    ]
)


@callback(
    Output("play-interval", "disabled"),
    Input("play-button", "n_clicks"),
    Input("pause-button", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_playback(play_clicks: int, pause_clicks: int) -> bool:
    from dash import ctx

    trigger = ctx.triggered_id
    if trigger == "play-button":
        return False
    if trigger == "pause-button":
        return True
    raise RuntimeError("Unexpected playback trigger")


@callback(
    Output("hour-slider", "value"),
    Input("play-interval", "n_intervals"),
    State("hour-slider", "value"),
    prevent_initial_call=True,
)
def advance_hour(_: int, current_hour: int) -> int:
    next_hour = current_hour + 1
    if next_hour > 8760:
        return 1
    return next_hour


@callback(Output("spatial-field-graph", "figure"), Input("hour-slider", "value"))
def update_figure(hour: int) -> go.Figure:
    return build_frame_figure(DATA, int(hour))


if __name__ == "__main__":
    print(f"Starting Dash app at http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False)
