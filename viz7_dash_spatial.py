from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from dash import Dash, Input, Output, State, callback, dcc, html

from CDO_project_constants import (
    CP_GENERIC,
    FINAL_CSV_SCHEMA,
    FINAL_CSV_SHAPE,
    SWEPT_AREA_M2,
    TURBINE_RATED_KW,
)


MASTER_CSV = "CDO_wind_2023_hourly.csv"
GRADIENTS_CSV = "CDO_wind_2023_gradients.csv"
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
BOX_MIN = -12.0
BOX_MAX = 12.0
FIELD_MIN = -10.0
FIELD_MAX = 10.0
ARROW_COUNT = 300
ARROW_SCALE = 0.5
PORT = 8050


@dataclass(frozen=True)
class FrameData:
    hour_of_year: int
    datetime: str
    season: str
    wind_speed_15m_ms: float
    wind_direction_10m_deg: float
    ti_24h: float
    turbulence_class: str
    u_mean: float
    v_mean: float
    x_pos: np.ndarray
    y_pos: np.ndarray
    z_pos: np.ndarray
    tip_x: np.ndarray
    tip_y: np.ndarray
    tip_z: np.ndarray
    speed_i: np.ndarray


def load_joined_data() -> pd.DataFrame:
    main = pd.read_csv(MASTER_CSV)
    gradients = pd.read_csv(GRADIENTS_CSV)[["hour_of_year", "TI_24h", "turbulence_class"]]

    if list(main.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema mismatch")
    if main.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape mismatch: expected {FINAL_CSV_SHAPE}, got {main.shape}")

    df = main.merge(gradients, on="hour_of_year", how="left")
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")

    radians = np.deg2rad(df["wind_direction_10m_deg"].to_numpy())
    df["U_mean"] = df["wind_speed_15m_ms"].to_numpy() * np.sin(radians)
    df["V_mean"] = df["wind_speed_15m_ms"].to_numpy() * np.cos(radians)
    df["TI_effective"] = df["TI_24h"].fillna(0.15)
    df["turbulence_class_effective"] = df.apply(
        lambda row: row["turbulence_class"]
        if pd.notna(row["turbulence_class"])
        else ("A" if row["TI_effective"] < 0.12 else "B" if row["TI_effective"] <= 0.14 else "C"),
        axis=1,
    )

    power_kw = (
        0.5
        * df["air_density_kgm3"]
        * np.power(df["wind_speed_15m_ms"], 3)
        * SWEPT_AREA_M2
        * CP_GENERIC
        / 1000.0
    ).clip(upper=TURBINE_RATED_KW)
    power_kw = power_kw.where(df["wind_speed_15m_ms"] >= 2.5, 0.0)
    df["power_available_kw"] = power_kw
    df["cumulative_kwh"] = power_kw.cumsum()
    df["hours_generating"] = (df["wind_speed_15m_ms"] >= 2.5).astype(int).cumsum()
    df["capacity_factor"] = df["cumulative_kwh"] / (df["hour_of_year"] * TURBINE_RATED_KW)
    df["capacity_factor"] = df["capacity_factor"].fillna(0.0)
    return df


def generate_spatial_field(row: pd.Series) -> FrameData:
    hour = int(row["hour_of_year"])
    rng = np.random.default_rng(hour)

    ti = float(row["TI_effective"])
    ws = float(row["wind_speed_15m_ms"])
    wd = float(row["wind_direction_10m_deg"])

    x_pos = rng.uniform(FIELD_MIN, FIELD_MAX, ARROW_COUNT)
    y_pos = rng.uniform(FIELD_MIN, FIELD_MAX, ARROW_COUNT)
    z_pos = rng.uniform(FIELD_MIN, FIELD_MAX, ARROW_COUNT)

    speed_i = ws * (1.0 + ti * rng.standard_normal(ARROW_COUNT))
    speed_i = np.clip(speed_i, 0.1, None)
    dir_i = wd + ti * 60.0 * rng.standard_normal(ARROW_COUNT)

    u_i = speed_i * np.sin(np.deg2rad(dir_i))
    v_i = speed_i * np.cos(np.deg2rad(dir_i))
    w_i = ti * ws * rng.standard_normal(ARROW_COUNT) * 0.3

    tip_x = x_pos + u_i * ARROW_SCALE
    tip_y = y_pos + v_i * ARROW_SCALE
    tip_z = z_pos + w_i * ARROW_SCALE

    return FrameData(
        hour_of_year=hour,
        datetime=row["datetime"].strftime("%Y-%m-%d %H:%M:%S"),
        season=str(row["season"]),
        wind_speed_15m_ms=ws,
        wind_direction_10m_deg=wd,
        ti_24h=ti,
        turbulence_class=str(row["turbulence_class_effective"]),
        u_mean=float(row["U_mean"]),
        v_mean=float(row["V_mean"]),
        x_pos=x_pos,
        y_pos=y_pos,
        z_pos=z_pos,
        tip_x=tip_x,
        tip_y=tip_y,
        tip_z=tip_z,
        speed_i=speed_i,
    )


def print_hour_diagnostics(df: pd.DataFrame, hour: int) -> None:
    row = df.loc[df["hour_of_year"] == hour].iloc[0]
    frame = generate_spatial_field(row)
    preview = pd.DataFrame(
        {
            "base_x": frame.x_pos[:5],
            "base_y": frame.y_pos[:5],
            "base_z": frame.z_pos[:5],
            "tip_x": frame.tip_x[:5],
            "tip_y": frame.tip_y[:5],
            "tip_z": frame.tip_z[:5],
        }
    )
    print(f"HOUR {hour}")
    print(
        f"Mean wind speed and direction: {frame.wind_speed_15m_ms:.6f} m/s, "
        f"{frame.wind_direction_10m_deg:.3f} deg"
    )
    print(f"TI_24h value: {frame.ti_24h:.6f}")
    print("First 5 generated arrow base/tip rows:")
    print(preview.to_string(index=False))
    print(f"Mean synthetic U/V: {np.mean(frame.tip_x - frame.x_pos):.6f}, {np.mean(frame.tip_y - frame.y_pos):.6f}")
    if hour == 1000:
        print(f"Reference center direction preserved at hour 1000: U={frame.u_mean:.6f}, V={frame.v_mean:.6f}")
    if hour == 4500:
        std_u = np.std(frame.tip_x - frame.x_pos)
        std_v = np.std(frame.tip_y - frame.y_pos)
        print(f"Scatter check: Habagat frame spread std(U,V) = {std_u:.6f}, {std_v:.6f}")
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
                opacity=0.06,
                colorscale=[[0, "#8ecae6"], [1, "#8ecae6"]],
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
            line={"color": "rgba(40,40,40,0.8)", "width": 3},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    return traces


def build_frame_figure(df: pd.DataFrame, hour: int) -> go.Figure:
    row = df.loc[df["hour_of_year"] == hour].iloc[0]
    frame = generate_spatial_field(row)
    fig = go.Figure()
    for trace in build_box_traces():
        fig.add_trace(trace)

    colors = sample_colorscale("RdYlBu_r", np.clip(frame.speed_i / 12.0, 0.0, 1.0))
    for i in range(ARROW_COUNT):
        fig.add_trace(
            go.Scatter3d(
                x=[frame.x_pos[i], frame.tip_x[i]],
                y=[frame.y_pos[i], frame.tip_y[i]],
                z=[frame.z_pos[i], frame.tip_z[i]],
                mode="lines",
                line={"color": colors[i], "width": 4},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    fig.add_trace(
        go.Scatter3d(
            x=frame.tip_x,
            y=frame.tip_y,
            z=frame.tip_z,
            mode="markers",
            marker={
                "size": 3,
                "color": frame.speed_i,
                "colorscale": "RdYlBu_r",
                "cmin": 0,
                "cmax": 12,
                "colorbar": {"title": "Wind Speed (m/s)"},
                "opacity": 0.95,
            },
            customdata=np.stack(
                [
                    np.full(ARROW_COUNT, frame.datetime),
                    frame.speed_i,
                    np.full(ARROW_COUNT, frame.wind_direction_10m_deg),
                    np.full(ARROW_COUNT, frame.season),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "Datetime: %{customdata[0]}<br>"
                "Wind speed: %{customdata[1]:.3f} m/s<br>"
                "Direction: %{customdata[2]:.1f}°<br>"
                "Season: %{customdata[3]}<extra></extra>"
            ),
            showlegend=False,
        )
    )

    for shadow_x, shadow_y, shadow_z in [
        (np.full(ARROW_COUNT, BOX_MIN), frame.tip_y, frame.tip_z),
        (frame.tip_x, np.full(ARROW_COUNT, BOX_MIN), frame.tip_z),
        (frame.tip_x, frame.tip_y, np.full(ARROW_COUNT, BOX_MIN)),
    ]:
        fig.add_trace(
            go.Scatter3d(
                x=shadow_x,
                y=shadow_y,
                z=shadow_z,
                mode="markers",
                marker={"size": 2, "color": "rgba(80,80,80,0.1)"},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    info_left = (
        f"Date/Time: {frame.datetime}<br>"
        f"Mean Wind: {frame.wind_speed_15m_ms:.3f} m/s<br>"
        f"Direction: {frame.wind_direction_10m_deg:.1f}°<br>"
        f"Season: {frame.season}<br>"
        f"Turbulence Intensity: {frame.ti_24h:.3f}<br>"
        f"Turbulence Class: {frame.turbulence_class}"
    )
    info_right = (
        f"Energy This Year: {row['cumulative_kwh']:.3f} kWh<br>"
        f"Hours Generating: {int(row['hours_generating'])} of {int(row['hour_of_year'])}<br>"
        f"Capacity Factor: {row['capacity_factor'] * 100:.2f}%"
    )

    fig.update_layout(
        title="CDO Wind Field 2023 — Mean + Synthetic Turbulence (NASA MERRA-2 + TI model)",
        scene={
            "xaxis_title": "East-West",
            "yaxis_title": "North-South",
            "zaxis_title": "Vertical",
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
        ],
        margin={"l": 0, "r": 0, "t": 60, "b": 0},
    )
    return fig


DATA = load_joined_data()
print_hour_diagnostics(DATA, 1000)
print_hour_diagnostics(DATA, 4500)

app = Dash(__name__)
app.layout = html.Div(
    [
        html.H2("CDO Wind Field 2023 — Mean + Synthetic Turbulence (NASA MERRA-2 + TI model)"),
        dcc.Graph(id="wind-field-graph", figure=build_frame_figure(DATA, 1), style={"height": "85vh"}),
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
                    marks={k: v for k, v in MONTH_MARKS.items()},
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


@callback(Output("wind-field-graph", "figure"), Input("hour-slider", "value"))
def update_figure(hour: int) -> go.Figure:
    return build_frame_figure(DATA, int(hour))


if __name__ == "__main__":
    print(f"Starting Dash app at http://127.0.0.1:{PORT}")
    app.run(host="127.0.0.1", port=PORT, debug=False)
