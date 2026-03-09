from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.interpolate import griddata

from dash import Dash, Input, Output, State, callback, dcc, html


LONG_CSV = "CDO_grid_wind_2023_long_openmeteo.csv"
PORT = 8051
GRID_AXIS = np.array([-8.0, -4.0, 0.0, 4.0, 8.0], dtype=float)
INTERP_AXIS = np.linspace(-8.0, 8.0, 35, dtype=float)
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


@dataclass(frozen=True)
class PreparedData:
    meta: pd.DataFrame
    real_x: np.ndarray
    real_y: np.ndarray
    interp_x: np.ndarray
    interp_y: np.ndarray
    wpd15_matrix: np.ndarray
    ws15_matrix: np.ndarray
    wd15_matrix: np.ndarray
    hotspot_grid_id: np.ndarray
    north_row_mean: np.ndarray
    south_row_mean: np.ndarray
    overall_min_wpd: float
    overall_max_wpd: float


def load_data() -> PreparedData:
    df = pd.read_csv(LONG_CSV)
    if len(df) != 219000 or df["grid_id"].nunique() != 25:
        raise ValueError("Expected CDO_grid_wind_2023_long_openmeteo.csv with 25 x 8760 rows")

    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    df["wpd_15"] = 0.5 * df["air_density_kgm3"] * np.power(df["wind_speed_15m_ms"], 3)

    meta = (
        df.loc[df["grid_id"] == "R2C2", ["hour_of_year", "datetime", "season"]]
        .sort_values("hour_of_year")
        .reset_index(drop=True)
    )

    grid_ids = [f"R{row}C{col}" for row in range(5) for col in range(5)]
    ordered = df.copy()
    ordered["grid_sort"] = ordered["grid_id"].map({gid: idx for idx, gid in enumerate(grid_ids)})
    ordered = ordered.sort_values(["hour_of_year", "grid_sort"]).reset_index(drop=True)

    wpd15_matrix = ordered["wpd_15"].to_numpy(dtype=float).reshape(8760, 25)
    ws15_matrix = ordered["wind_speed_15m_ms"].to_numpy(dtype=float).reshape(8760, 25)
    wd15_matrix = ordered["wind_direction_15m_deg"].to_numpy(dtype=float).reshape(8760, 25)
    hotspot_idx = np.nanargmax(wpd15_matrix, axis=1)
    hotspot_grid_id = np.array([grid_ids[idx] for idx in hotspot_idx], dtype=object)

    row_index = np.array([int(gid[1]) for gid in grid_ids], dtype=int)
    north_row_mean = wpd15_matrix[:, row_index == 4].mean(axis=1)
    south_row_mean = wpd15_matrix[:, row_index == 0].mean(axis=1)

    grid_points = [(x, y) for y in GRID_AXIS for x in GRID_AXIS]
    real_x = np.array([pt[0] for pt in grid_points], dtype=float)
    real_y = np.array([pt[1] for pt in grid_points], dtype=float)
    interp_mesh_x, interp_mesh_y = np.meshgrid(INTERP_AXIS, INTERP_AXIS)

    return PreparedData(
        meta=meta,
        real_x=real_x,
        real_y=real_y,
        interp_x=interp_mesh_x,
        interp_y=interp_mesh_y,
        wpd15_matrix=wpd15_matrix,
        ws15_matrix=ws15_matrix,
        wd15_matrix=wd15_matrix,
        hotspot_grid_id=hotspot_grid_id,
        north_row_mean=north_row_mean,
        south_row_mean=south_row_mean,
        overall_min_wpd=float(np.nanmin(wpd15_matrix)),
        overall_max_wpd=float(np.nanmax(wpd15_matrix)),
    )


def interpolate_surface(data: PreparedData, idx: int) -> np.ndarray:
    values = data.wpd15_matrix[idx]
    surface = griddata(
        points=np.column_stack([data.real_x, data.real_y]),
        values=values,
        xi=(data.interp_x, data.interp_y),
        method="cubic",
    )
    if np.isnan(surface).any():
        linear = griddata(
            points=np.column_stack([data.real_x, data.real_y]),
            values=values,
            xi=(data.interp_x, data.interp_y),
            method="linear",
        )
        nearest = griddata(
            points=np.column_stack([data.real_x, data.real_y]),
            values=values,
            xi=(data.interp_x, data.interp_y),
            method="nearest",
        )
        surface = np.where(np.isnan(surface), linear, surface)
        surface = np.where(np.isnan(surface), nearest, surface)
    return surface


def build_figure(data: PreparedData, idx: int) -> go.Figure:
    row = data.meta.iloc[idx]
    surface = interpolate_surface(data, idx)
    point_values = data.wpd15_matrix[idx]
    point_speeds = data.ws15_matrix[idx]
    point_dirs = data.wd15_matrix[idx]

    fig = go.Figure()
    fig.add_trace(
        go.Surface(
            x=data.interp_x,
            y=data.interp_y,
            z=surface,
            colorscale="Viridis",
            cmin=data.overall_min_wpd,
            cmax=data.overall_max_wpd,
            opacity=0.92,
            colorbar={"title": "WPD 15m (W/m²)"},
            contours={
                "z": {
                    "show": True,
                    "usecolormap": True,
                    "project": {"z": True},
                    "width": 1,
                }
            },
            hoverinfo="skip",
            showscale=True,
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=data.real_x,
            y=data.real_y,
            z=point_values,
            mode="markers+text",
            marker={
                "size": 5,
                "color": point_values,
                "colorscale": "Viridis",
                "cmin": data.overall_min_wpd,
                "cmax": data.overall_max_wpd,
                "line": {"color": "rgba(20,20,20,0.45)", "width": 1},
            },
            text=[f"R{row_idx}C{col_idx}" for row_idx in range(5) for col_idx in range(5)],
            textposition="top center",
            textfont={"size": 9, "color": "#24364d"},
            hovertext=[
                (
                    f"Grid: R{row_idx}C{col_idx}<br>"
                    f"WPD: {wpd:.2f} W/m²<br>"
                    f"WS15: {ws:.2f} m/s<br>"
                    f"WD15: {wd:.1f}°"
                )
                for row_idx in range(5)
                for col_idx, (wpd, ws, wd) in enumerate(
                    zip(
                        point_values[row_idx * 5:(row_idx + 1) * 5],
                        point_speeds[row_idx * 5:(row_idx + 1) * 5],
                        point_dirs[row_idx * 5:(row_idx + 1) * 5],
                    )
                )
            ],
            hoverinfo="text",
            showlegend=False,
        )
    )

    hotspot_id = str(data.hotspot_grid_id[idx])
    center_idx = 12
    fig.update_layout(
        title="CDO Refined Spatial Wind Power Density 2023 — Open-Meteo ERA5-Seamless",
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
        paper_bgcolor="#f5f7fb",
        scene={
            "xaxis": {"title": "East-West", "range": [-9.5, 9.5], "backgroundcolor": "#eef3fb"},
            "yaxis": {"title": "North-South", "range": [-9.5, 9.5], "backgroundcolor": "#eef3fb"},
            "zaxis": {
                "title": "WPD at 15m (W/m²)",
                "range": [0, max(data.overall_max_wpd * 1.02, np.nanmax(surface) * 1.05)],
                "backgroundcolor": "#f8fbff",
            },
            "camera": {"eye": {"x": 1.55, "y": 1.55, "z": 0.9}},
            "aspectmode": "manual",
            "aspectratio": {"x": 1.0, "y": 1.0, "z": 0.55},
        },
        annotations=[
            {
                "x": 0.01,
                "y": 0.92,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "align": "left",
                "text": (
                    f"Date/Time: {row['datetime']}<br>"
                    f"Season: {row['season']}<br>"
                    f"Center WPD (R2C2): {point_values[center_idx]:.2f} W/m²<br>"
                    f"Center WS15: {point_speeds[center_idx]:.2f} m/s<br>"
                    f"Center WD15: {point_dirs[center_idx]:.1f}°"
                ),
                "font": {"size": 15, "color": "#24364d"},
            },
            {
                "x": 0.99,
                "y": 0.12,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "align": "right",
                "text": (
                    f"Hotspot: {hotspot_id}<br>"
                    f"North Row Mean: {data.north_row_mean[idx]:.2f} W/m²<br>"
                    f"South Row Mean: {data.south_row_mean[idx]:.2f} W/m²<br>"
                    f"North > South: {data.north_row_mean[idx] > data.south_row_mean[idx]}"
                ),
                "font": {"size": 15, "color": "#24364d"},
            },
        ],
    )
    return fig


DATA = load_data()
print(f"Refined long CSV loaded with shape {(219000, 30)}")
print(
    f"WPD range: min={DATA.overall_min_wpd:.6f} W/m², "
    f"max={DATA.overall_max_wpd:.6f} W/m²"
)
print(
    f"Hour 1 hotspot={DATA.hotspot_grid_id[0]} "
    f"north_mean={DATA.north_row_mean[0]:.6f} south_mean={DATA.south_row_mean[0]:.6f}"
)

app = Dash(__name__)
app.title = "CDO Refined Spatial WPD 2023"

app.layout = html.Div(
    [
        html.H1("CDO Refined Spatial WPD 2023", style={"marginBottom": "0.3rem"}),
        html.Div(
            "Hourly 15m wind power density over the 5x5 refined Open-Meteo grid.",
            style={"fontSize": "1.1rem", "color": "#314866", "marginBottom": "0.8rem"},
        ),
        dcc.Graph(id="wpd-graph", figure=build_figure(DATA, 0), style={"height": "78vh"}),
        html.Div(
            [
                html.Button("Play", id="play-btn", n_clicks=0, style={"marginRight": "0.5rem"}),
                html.Button("Pause", id="pause-btn", n_clicks=0, style={"marginRight": "1rem"}),
                dcc.Slider(
                    id="hour-slider",
                    min=1,
                    max=8760,
                    step=1,
                    value=1,
                    marks=MONTH_MARKS,
                    tooltip={"placement": "bottom"},
                ),
            ],
            style={"padding": "0 1rem 1rem 1rem"},
        ),
        dcc.Interval(id="play-interval", interval=180, disabled=True),
    ],
    style={"backgroundColor": "#f5f7fb", "padding": "0.6rem 0.8rem"},
)


@callback(
    Output("hour-slider", "value"),
    Output("play-interval", "disabled"),
    Input("play-btn", "n_clicks"),
    Input("pause-btn", "n_clicks"),
    Input("play-interval", "n_intervals"),
    State("hour-slider", "value"),
    State("play-interval", "disabled"),
)
def advance_slider(play_clicks: int, pause_clicks: int, n_intervals: int, current_value: int, disabled: bool):
    trigger = ctx_trigger()
    if trigger == "play-btn":
        return current_value, False
    if trigger == "pause-btn":
        return current_value, True
    if trigger == "play-interval" and not disabled:
        return 1 if current_value >= 8760 else current_value + 1, False
    return current_value, disabled


@callback(Output("wpd-graph", "figure"), Input("hour-slider", "value"))
def update_figure(hour_of_year: int):
    return build_figure(DATA, hour_of_year - 1)


def ctx_trigger() -> str | None:
    try:
        from dash import ctx
    except ImportError:
        return None
    if not ctx.triggered:
        return None
    return ctx.triggered_id


if __name__ == "__main__":
    app.run(debug=False, port=PORT)
