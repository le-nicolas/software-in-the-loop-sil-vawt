# viz9_dpcbf_sphere_3d.py
# CDO VAWT — DPCBF-Inspired 3D Wind Capture Sphere
# Standalone visualization. No existing files modified.
#
# Physics:
#   Wind decomposition: U_total = U_mean + u' - omega×r
#   CBF capture ODE:    dh/dt >= -alpha * h(t), h = particle_density * cp_effective
#   Sphere zones:       inner r=0.375m (Savonius/drag), outer r=0.75m (Darrieus/lift)
#
# Design insight:
#   Particle density + direction histogram → blade orientation signal
#   CBF alert → when turbulence overwhelms lift regime, Savonius cups activate
#
# Data: CDO_wind_2023_hourly.csv (NASA POWER + ERA5, CDO 2023, UTC+8)
# requires: numpy pandas plotly

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from CDO_project_constants import (
    CP_GENERIC,
    CUT_IN_MS,
    DRIVETRAIN_DAMPING_NMS,
    ROTOR_INERTIA_KGM2,
    ROTOR_RADIUS_M,
    STANDARD_AIR_DENSITY,
    SWEPT_AREA_M2,
    TSR_OPT,
    TSR_SPREAD,
)
from sil_plant_model import cp_curve

ALPHA_CBF = 0.3
DT_DATA_S = 3600.0
DT_VIZ_S = 0.5
N_PARTICLES = 80
MONTH_FRAMES = 720
RNG_SEED_COMPONENTS = 42
RNG_SEED_PARTICLES = 314

SEASON_COLORS = {
    "Amihan": "#2563eb",
    "Habagat": "#16a34a",
    "Transition_DryDown": "#f59e0b",
    "Transition_Rampup": "#7c3aed",
}

PARTICLE_COLORSCALE = [
    [0.0, "navy"],
    [0.33, "cyan"],
    [0.66, "yellow"],
    [1.0, "red"],
]


def load_dataset(csv_path: Path) -> pd.DataFrame:
    required_columns = [
        "wind_speed_15m_ms",
        "wind_direction_10m_deg",
        "air_density_kgm3",
        "season",
        "hour_of_year",
    ]
    df = pd.read_csv(csv_path, usecols=required_columns)
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df


def compute_wind_components(df: pd.DataFrame) -> dict[str, np.ndarray]:
    u_mean = df["wind_speed_15m_ms"].to_numpy(dtype=float)
    theta_deg = np.mod(df["wind_direction_10m_deg"].to_numpy(dtype=float), 360.0)
    theta_rad = np.deg2rad(theta_deg)
    rho = df["air_density_kgm3"].to_numpy(dtype=float)
    seasons = df["season"].astype(str).to_numpy()
    hours = df["hour_of_year"].to_numpy(dtype=int)

    rng = np.random.default_rng(RNG_SEED_COMPONENTS)
    sigma_u = 0.1 * u_mean
    u_prime = sigma_u * rng.standard_normal(len(df))

    omega_rad_s = (TSR_OPT * u_mean) / ROTOR_RADIUS_M
    omega_cross_r = omega_rad_s * ROTOR_RADIUS_M
    tsr = np.where(
        u_mean >= CUT_IN_MS,
        (omega_rad_s * ROTOR_RADIUS_M) / np.maximum(u_mean, 0.1),
        0.0,
    )
    cp_effective = np.where(u_mean >= CUT_IN_MS, cp_curve(tsr), 0.0)
    v_rel = u_mean + u_prime - omega_cross_r
    v_rel_mag = np.abs(v_rel)

    return {
        "u_mean": u_mean,
        "theta_deg": theta_deg,
        "theta_rad": theta_rad,
        "rho": rho,
        "seasons": seasons,
        "hours": hours,
        "sigma_u": sigma_u,
        "u_prime": u_prime,
        "omega_rad_s": omega_rad_s,
        "omega_cross_r": omega_cross_r,
        "tsr": tsr,
        "cp_effective": cp_effective,
        "v_rel": v_rel,
        "v_rel_mag": v_rel_mag,
    }


def initialize_particles(count: int, theta_rad: float, rng: np.random.Generator) -> np.ndarray:
    base = np.zeros((count, 3), dtype=float)
    base[:, 0] = -3.0 * ROTOR_RADIUS_M * np.cos(theta_rad)
    base[:, 1] = -3.0 * ROTOR_RADIUS_M * np.sin(theta_rad)
    base[:, 2] = rng.uniform(-0.8 * ROTOR_RADIUS_M, 0.8 * ROTOR_RADIUS_M, size=count)

    crosswind = np.array([-np.sin(theta_rad), np.cos(theta_rad), 0.0], dtype=float)
    lateral_scatter = rng.uniform(-0.5 * ROTOR_RADIUS_M, 0.5 * ROTOR_RADIUS_M, size=count)
    base[:, 0] += lateral_scatter * crosswind[0]
    base[:, 1] += lateral_scatter * crosswind[1]
    return base


def simulate_particles(components: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    n_steps = len(components["u_mean"])
    frame_count = min(MONTH_FRAMES, n_steps)
    positions = np.zeros((frame_count, N_PARTICLES, 3), dtype=float)
    particle_density = np.zeros(n_steps, dtype=float)
    n_inner = np.zeros(n_steps, dtype=int)
    n_outer = np.zeros(n_steps, dtype=int)

    rng = np.random.default_rng(RNG_SEED_PARTICLES)
    pos = initialize_particles(N_PARTICLES, components["theta_rad"][0], rng)

    for idx in range(n_steps):
        if idx > 0:
            speed = components["u_mean"][idx] + components["u_prime"][idx]
            vx = speed * np.cos(components["theta_rad"][idx])
            vy = speed * np.sin(components["theta_rad"][idx])
            vz = 0.1 * components["u_prime"][idx]
            pos = pos + np.array([vx, vy, vz], dtype=float) * DT_VIZ_S

        r_now = np.linalg.norm(pos, axis=1)
        escaped = r_now > (2.5 * ROTOR_RADIUS_M)
        if np.any(escaped):
            pos[escaped] = initialize_particles(int(np.count_nonzero(escaped)), components["theta_rad"][idx], rng)
            r_now = np.linalg.norm(pos, axis=1)

        in_outer = r_now <= ROTOR_RADIUS_M
        in_inner = r_now <= (0.5 * ROTOR_RADIUS_M)

        n_outer[idx] = int(np.count_nonzero(in_outer))
        n_inner[idx] = int(np.count_nonzero(in_inner))
        particle_density[idx] = n_outer[idx] / N_PARTICLES

        if idx < frame_count:
            positions[idx] = pos

    return {
        "positions": positions,
        "particle_density": particle_density,
        "n_inner": n_inner,
        "n_outer": n_outer,
    }


def compute_capture_metrics(
    components: dict[str, np.ndarray],
    particle_state: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    h = particle_state["particle_density"] * components["cp_effective"]
    dh_dt = np.zeros_like(h)
    dh_dt[1:] = np.diff(h) / DT_DATA_S
    alert = (dh_dt + ALPHA_CBF * h) < 0.0
    return {"h": h, "dh_dt": dh_dt, "alert": alert}


def sphere_mesh(radius: float, n_phi: int = 30, n_theta: int = 30) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    phi = np.linspace(0.0, 2.0 * np.pi, n_phi)
    theta = np.linspace(0.0, np.pi, n_theta)
    x = radius * np.outer(np.cos(phi), np.sin(theta))
    y = radius * np.outer(np.sin(phi), np.sin(theta))
    z = radius * np.outer(np.ones(n_phi), np.cos(theta))
    return x, y, z


def solid_surface(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    color: str,
    opacity: float,
    name: str,
) -> go.Surface:
    return go.Surface(
        x=x,
        y=y,
        z=z,
        surfacecolor=np.zeros_like(x),
        colorscale=[[0.0, color], [1.0, color]],
        opacity=opacity,
        showscale=False,
        name=name,
        hoverinfo="skip",
        contours={
            "x": {"show": True, "color": color, "width": 1},
            "y": {"show": True, "color": color, "width": 1},
            "z": {"show": True, "color": color, "width": 1},
        },
    )


def direction_statistics(
    components: dict[str, np.ndarray],
) -> dict[str, np.ndarray | tuple[int, int]]:
    edges = np.linspace(0.0, 360.0, 37)
    centers = edges[:-1] + 5.0
    bins = np.floor(np.mod(components["theta_deg"], 360.0) / 10.0).astype(int) % 36

    mean_cp = np.full(36, np.nan, dtype=float)
    mean_u = np.full(36, np.nan, dtype=float)
    counts = np.zeros(36, dtype=int)

    for idx in range(36):
        mask = bins == idx
        counts[idx] = int(np.count_nonzero(mask))
        if counts[idx] > 0:
            mean_cp[idx] = float(np.mean(components["cp_effective"][mask]))
            mean_u[idx] = float(np.mean(components["u_mean"][mask]))

    score = np.nan_to_num(mean_cp, nan=-1.0) + 1e-3 * np.nan_to_num(mean_u, nan=0.0)
    dominant_idx = int(np.argmax(score))
    top3 = np.argsort(np.nan_to_num(mean_cp, nan=-1.0) + 1e-3 * np.nan_to_num(mean_u, nan=0.0))[-3:]
    top3 = top3[np.argsort(score[top3])[::-1]]

    return {
        "edges": edges,
        "centers": centers,
        "mean_cp": mean_cp,
        "mean_u": mean_u,
        "counts": counts,
        "dominant_sector": (int(edges[dominant_idx]), int(edges[dominant_idx + 1])),
        "top3": top3,
    }


def print_summary(
    components: dict[str, np.ndarray],
    capture: dict[str, np.ndarray],
    direction_stats: dict[str, np.ndarray | tuple[int, int]],
) -> None:
    power_w = (
        0.5
        * components["rho"]
        * SWEPT_AREA_M2
        * np.clip(components["u_mean"], a_min=0.0, a_max=None) ** 3
        * components["cp_effective"]
    )
    annual_energy_mwh = float(np.sum(power_w) / 1_000_000.0)

    v_rel_mag = components["v_rel_mag"]
    alert = capture["alert"]
    dominant_start, dominant_end = direction_stats["dominant_sector"]

    savonius_condition = alert | (v_rel_mag < np.maximum(components["u_mean"] * 0.8, 0.5))
    savonius_activation = int(
        np.count_nonzero(savonius_condition)
    )
    darrieus_prime = int(
        np.count_nonzero((~savonius_condition) & (v_rel_mag > (components["u_mean"] * 0.8)))
    )
    alert_hours = int(np.count_nonzero(alert))

    print("=== CDO VAWT CAPTURE SUMMARY (2023) ===")
    print(f"Mean wind speed (15m): {np.mean(components['u_mean']):.3f} m/s")
    print(f"Mean Cp (TSR-weighted): {np.mean(components['cp_effective']):.4f}")
    print(f"Mean v_rel: {np.mean(v_rel_mag):.3f} m/s")
    print(
        "Hours in CAPTURE ALERT (CBF violated): "
        f"{alert_hours}/8760 ({100.0 * alert_hours / len(alert):.1f}%)"
    )
    print(f"Dominant wind sector: {dominant_start}-{dominant_end}°")
    print(f"Savonius activation hours: {savonius_activation} (high turbulence, low v_rel)")
    print(f"Darrieus prime hours: {darrieus_prime} (v_rel > U_mean * 0.8, good lift)")
    print(
        "Estimated annual energy (MWh): "
        f"{annual_energy_mwh:.2f}"
    )
    print(f"(assuming SWEPT_AREA_M2={SWEPT_AREA_M2:.1f}, CP_GENERIC={CP_GENERIC:.2f}, continuous operation)")


def export_sphere_metrics(
    output_dir: Path,
    components: dict[str, np.ndarray],
    particle_state: dict[str, np.ndarray],
    capture: dict[str, np.ndarray],
) -> Path:
    export_path = output_dir / "viz9_sphere_hourly_metrics.csv"
    df = pd.DataFrame(
        {
            "hour_of_year": components["hours"],
            "season": components["seasons"],
            "u_mean_ms": components["u_mean"],
            "u_prime_ms": components["u_prime"],
            "omega_rad_s": components["omega_rad_s"],
            "omega_cross_r_ms": components["omega_cross_r"],
            "tsr": components["tsr"],
            "cp_effective": components["cp_effective"],
            "v_rel_ms": components["v_rel"],
            "v_rel_mag_ms": components["v_rel_mag"],
            "particle_density": particle_state["particle_density"],
            "n_inner": particle_state["n_inner"],
            "n_outer": particle_state["n_outer"],
            "h_capture": capture["h"],
            "dh_dt": capture["dh_dt"],
            "capture_alert": capture["alert"].astype(int),
        }
    )
    df.to_csv(export_path, index=False)
    print(f"Saved sphere metrics: {export_path.name} ({len(df)} rows)")
    return export_path


def make_dynamic_annotations(
    frame_idx: int,
    month_hours: np.ndarray,
    month_u: np.ndarray,
    month_tsr: np.ndarray,
    month_cp: np.ndarray,
    month_inner: np.ndarray,
    month_outer: np.ndarray,
    month_alert: np.ndarray,
) -> list[dict]:
    title_text = (
        f"Hour {int(month_hours[frame_idx])} | "
        f"U={month_u[frame_idx]:.1f} m/s | "
        f"TSR={month_tsr[frame_idx]:.2f} | "
        f"Cp={month_cp[frame_idx]:.3f}"
    )

    info_lines = [
        f"Inner zone (Savonius): {int(month_inner[frame_idx])} particles | drag regime",
        f"Outer zone (Darrieus): {int(month_outer[frame_idx])} particles | lift regime",
    ]
    if month_alert[frame_idx]:
        info_lines.append("<b><span style='color:#dc2626'>ALERT: Savonius needed</span></b>")

    return [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.19,
            "y": 0.99,
            "showarrow": False,
            "align": "center",
            "text": title_text,
            "font": {"size": 15, "color": "#0f172a"},
            "bgcolor": "rgba(255,255,255,0.92)",
            "bordercolor": "#94a3b8",
            "borderwidth": 1,
            "borderpad": 4,
        },
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.03,
            "y": 0.82,
            "showarrow": False,
            "align": "left",
            "text": "<br>".join(info_lines),
            "font": {"size": 11, "color": "#111827"},
            "bgcolor": "rgba(255,255,255,0.9)",
            "bordercolor": "#dc2626" if month_alert[frame_idx] else "#2563eb",
            "borderwidth": 1,
            "borderpad": 6,
        },
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.88,
            "y": 0.05,
            "showarrow": False,
            "align": "center",
            "text": "High bars = orient Darrieus blades here",
            "font": {"size": 11, "color": "#334155"},
            "bgcolor": "rgba(255,255,255,0.8)",
            "bordercolor": "#cbd5e1",
            "borderwidth": 1,
            "borderpad": 4,
        },
    ]


def build_figure(
    components: dict[str, np.ndarray],
    particle_state: dict[str, np.ndarray],
    capture: dict[str, np.ndarray],
    direction_stats: dict[str, np.ndarray | tuple[int, int]],
) -> go.Figure:
    frame_count = min(MONTH_FRAMES, len(components["hours"]))
    month_slice = slice(0, frame_count)
    month_hours = components["hours"][month_slice]
    month_u = components["u_mean"][month_slice]
    month_u_prime = components["u_prime"][month_slice]
    month_omega_cross_r = components["omega_cross_r"][month_slice]
    month_v_rel = components["v_rel"][month_slice]
    month_v_rel_mag = components["v_rel_mag"][month_slice]
    month_tsr = components["tsr"][month_slice]
    month_cp = components["cp_effective"][month_slice]
    month_h = capture["h"][month_slice]
    month_alert = capture["alert"][month_slice]
    month_positions = particle_state["positions"]
    month_inner = particle_state["n_inner"][month_slice]
    month_outer = particle_state["n_outer"][month_slice]
    month_theta = components["theta_rad"][month_slice]
    month_seasons = components["seasons"][month_slice]

    h_ymax = max(1.0, float(np.nanmax(month_h)) + 0.05)
    vel_min = float(min(np.min(month_u_prime), np.min(month_v_rel), -0.5))
    vel_max = float(max(np.max(month_u), np.max(month_omega_cross_r), np.max(month_v_rel)) + 0.5)
    color_max = max(float(np.percentile(components["v_rel_mag"], 99.0)), 1.0)

    outer_mesh = sphere_mesh(ROTOR_RADIUS_M)
    inner_mesh = sphere_mesh(ROTOR_RADIUS_M * 0.5)
    initial_outer_opacity = 0.15 + 0.20 * (month_outer[0] / N_PARTICLES)
    initial_inner_opacity = 0.35 if month_alert[0] else 0.15
    initial_particle_size = np.full(N_PARTICLES, 5.0 + 10.0 * (month_v_rel_mag[0] / color_max))

    initial_speed = month_u[0] + month_u_prime[0]
    arrow_start = np.array(
        [-2.0 * ROTOR_RADIUS_M * np.cos(month_theta[0]), -2.0 * ROTOR_RADIUS_M * np.sin(month_theta[0]), 0.0]
    )
    arrow_end = arrow_start + np.array(
        [0.6 * initial_speed * np.cos(month_theta[0]), 0.6 * initial_speed * np.sin(month_theta[0]), 0.0]
    )

    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "polar"}],
        ],
        subplot_titles=(
            "3D Wind Capture Sphere",
            "CBF Capture Function h(t)",
            "Wind Vector Decomposition — CDO 2023 (Month 1)",
            "Blade Orientation Signal — Full Year Cp by Direction",
        ),
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    fig.add_trace(
        solid_surface(
            *outer_mesh,
            color="rgba(37,99,235,1.0)",
            opacity=initial_outer_opacity,
            name="Darrieus Lift Zone",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        solid_surface(
            *inner_mesh,
            color="rgba(249,115,22,1.0)",
            opacity=initial_inner_opacity,
            name="Savonius Drag Zone",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=month_positions[0, :, 0],
            y=month_positions[0, :, 1],
            z=month_positions[0, :, 2],
            mode="markers",
            name="Wind particles",
            marker={
                "size": initial_particle_size,
                "color": np.full(N_PARTICLES, month_v_rel_mag[0]),
                "colorscale": PARTICLE_COLORSCALE,
                "cmin": 0.0,
                "cmax": color_max,
                "opacity": 0.9,
                "line": {"width": 0.4, "color": "white"},
                "colorbar": {
                    "title": "|v_rel| m/s",
                    "len": 0.4,
                    "x": 0.43,
                    "y": 0.81,
                },
            },
            text=[f"|v_rel|={month_v_rel_mag[0]:.2f} m/s"] * N_PARTICLES,
            hovertemplate="x=%{x:.2f} m<br>y=%{y:.2f} m<br>z=%{z:.2f} m<br>%{text}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=[arrow_start[0], arrow_end[0]],
            y=[arrow_start[1], arrow_end[1]],
            z=[arrow_start[2], arrow_end[2]],
            mode="lines+markers",
            name="Wind direction",
            line={"color": "#111827", "width": 8},
            marker={"size": [1, 5], "color": "#111827"},
            hovertemplate="Incoming wind direction<extra></extra>",
        ),
        row=1,
        col=1,
    )

    alert_fill = np.where(month_alert, month_h, np.nan)
    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=alert_fill,
            mode="lines",
            line={"width": 0},
            fill="tozeroy",
            fillcolor="rgba(239,68,68,0.18)",
            name="Capture alert region",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=month_h,
            mode="lines",
            line={"color": "#2563eb", "width": 2},
            name="h(t)",
            hovertemplate="Hour %{x}<br>h=%{y:.3f}<extra></extra>",
        ),
        row=1,
        col=2,
    )

    unique_month_seasons = pd.unique(month_seasons)
    for season_name in unique_month_seasons:
        mask = month_seasons == season_name
        fig.add_trace(
            go.Scatter(
                x=month_hours[mask],
                y=month_h[mask],
                mode="markers",
                marker={
                    "size": 4,
                    "color": SEASON_COLORS.get(season_name, "#64748b"),
                    "opacity": 0.6,
                },
                name=f"{season_name} season",
                hovertemplate=f"{season_name}<br>Hour %{{x}}<br>h=%{{y:.3f}}<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=2,
        )

    fig.add_trace(
        go.Scatter(
            x=[month_hours[0], month_hours[-1]],
            y=[0.1, 0.1],
            mode="lines",
            line={"color": "#64748b", "width": 1.5, "dash": "dash"},
            name="alert threshold",
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )
    panel2_time_trace_idx = len(fig.data)
    fig.add_trace(
        go.Scatter(
            x=[month_hours[0], month_hours[0]],
            y=[0.0, h_ymax],
            mode="lines",
            line={"color": "#dc2626", "width": 2},
            name="Current hour",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=month_u,
            mode="lines",
            line={"color": "#2563eb", "width": 2},
            name="Mean — carries blade",
            hovertemplate="Hour %{x}<br>U_mean=%{y:.2f} m/s<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=month_u_prime,
            mode="lines",
            line={"color": "#f97316", "width": 1.8, "dash": "dash"},
            name="Fluctuation — stresses blade",
            hovertemplate="Hour %{x}<br>u'=%{y:.2f} m/s<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=month_omega_cross_r,
            mode="lines",
            line={"color": "#16a34a", "width": 1.8, "dash": "dot"},
            name="ω×r — wraps around blade",
            hovertemplate="Hour %{x}<br>ω×r=%{y:.2f} m/s<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=month_hours,
            y=month_v_rel,
            mode="lines",
            line={"color": "#111827", "width": 3},
            name="v_rel = U - ω×r + u' (Darrieus sees this)",
            hovertemplate="Hour %{x}<br>v_rel=%{y:.2f} m/s<extra></extra>",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=[month_hours[0], month_hours[0]],
            y=[vel_min, vel_max],
            mode="lines",
            line={"color": "#dc2626", "width": 2},
            name="Current hour marker",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    panel3_time_trace_idx = len(fig.data) - 1

    polar_r = np.nan_to_num(direction_stats["mean_cp"], nan=0.0)
    polar_color = np.nan_to_num(direction_stats["mean_u"], nan=0.0)
    fig.add_trace(
        go.Barpolar(
            theta=direction_stats["centers"],
            r=polar_r,
            width=np.full(36, 10.0),
            marker={
                "color": polar_color,
                "colorscale": "Viridis",
                "line": {"color": "white", "width": 1},
                "colorbar": {
                    "title": "Mean U (m/s)",
                    "len": 0.35,
                    "x": 1.02,
                    "y": 0.16,
                },
            },
            opacity=0.9,
            name="Mean Cp by direction",
            hovertemplate="Dir %{theta:.0f}°<br>Mean Cp=%{r:.3f}<br>Mean U=%{marker.color:.2f} m/s<extra></extra>",
        ),
        row=2,
        col=2,
    )

    top3 = direction_stats["top3"]
    top_theta = np.asarray(direction_stats["centers"])[top3]
    top_r = polar_r[top3] + 0.02
    fig.add_trace(
        go.Scatterpolar(
            theta=top_theta,
            r=top_r,
            mode="markers+text",
            marker={"symbol": "star", "size": 14, "color": "#f59e0b", "line": {"color": "#111827", "width": 1}},
            text=["Primary wind sector"] * len(top3),
            textposition="top center",
            name="Orientation targets",
            hovertemplate="Priority sector %{theta:.0f}°<extra></extra>",
        ),
        row=2,
        col=2,
    )

    fig.update_scenes(
        xaxis={"title": "x (m)", "range": [-2.2, 2.2], "backgroundcolor": "rgb(248,250,252)"},
        yaxis={"title": "y (m)", "range": [-2.2, 2.2], "backgroundcolor": "rgb(248,250,252)"},
        zaxis={"title": "z (m)", "range": [-1.3, 1.3], "backgroundcolor": "rgb(248,250,252)"},
        aspectmode="cube",
        camera={"eye": {"x": 1.5, "y": 1.5, "z": 1.5}},
    )
    fig.update_xaxes(title_text="Hour of year", row=1, col=2)
    fig.update_yaxes(title_text="h(t)", range=[0.0, h_ymax], row=1, col=2)
    fig.update_xaxes(title_text="Hour of year", row=2, col=1)
    fig.update_yaxes(title_text="Velocity (m/s)", range=[vel_min, vel_max], row=2, col=1)
    fig.update_polars(
        radialaxis={"title": "Mean Cp", "range": [0.0, max(0.4, float(np.nanmax(polar_r)) + 0.05)]},
        angularaxis={"direction": "clockwise", "rotation": 90},
        bgcolor="rgb(248,250,252)",
    )

    initial_annotations = make_dynamic_annotations(
        0,
        month_hours,
        month_u,
        month_tsr,
        month_cp,
        month_inner,
        month_outer,
        month_alert,
    )

    fig.update_layout(
        template="plotly_white",
        title={"text": "CDO VAWT DPCBF Capture Sphere Explorer", "x": 0.5},
        height=980,
        width=1400,
        margin={"l": 40, "r": 40, "t": 90, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.08, "xanchor": "left", "x": 0.0},
        annotations=initial_annotations,
    )

    frame_traces = [0, 1, 2, 3, panel2_time_trace_idx, panel3_time_trace_idx]
    frames = []
    for idx in range(frame_count):
        outer_opacity = 0.15 + 0.20 * (month_outer[idx] / N_PARTICLES)
        inner_opacity = 0.35 if month_alert[idx] else 0.15
        particle_size = np.full(N_PARTICLES, 5.0 + 10.0 * (month_v_rel_mag[idx] / color_max))

        speed = month_u[idx] + month_u_prime[idx]
        arrow_start = np.array(
            [-2.0 * ROTOR_RADIUS_M * np.cos(month_theta[idx]), -2.0 * ROTOR_RADIUS_M * np.sin(month_theta[idx]), 0.0]
        )
        arrow_end = arrow_start + np.array(
            [0.6 * speed * np.cos(month_theta[idx]), 0.6 * speed * np.sin(month_theta[idx]), 0.0]
        )

        frame = go.Frame(
            name=str(int(month_hours[idx])),
            data=[
                go.Surface(opacity=outer_opacity),
                go.Surface(opacity=inner_opacity),
                go.Scatter3d(
                    x=month_positions[idx, :, 0],
                    y=month_positions[idx, :, 1],
                    z=month_positions[idx, :, 2],
                    marker={
                        "size": particle_size,
                        "color": np.full(N_PARTICLES, month_v_rel_mag[idx]),
                        "colorscale": PARTICLE_COLORSCALE,
                        "cmin": 0.0,
                        "cmax": color_max,
                        "opacity": 0.9,
                        "line": {"width": 0.4, "color": "white"},
                    },
                    text=[f"|v_rel|={month_v_rel_mag[idx]:.2f} m/s"] * N_PARTICLES,
                ),
                go.Scatter3d(
                    x=[arrow_start[0], arrow_end[0]],
                    y=[arrow_start[1], arrow_end[1]],
                    z=[arrow_start[2], arrow_end[2]],
                ),
                go.Scatter(
                    x=[month_hours[idx], month_hours[idx]],
                    y=[0.0, h_ymax],
                ),
                go.Scatter(
                    x=[month_hours[idx], month_hours[idx]],
                    y=[vel_min, vel_max],
                ),
            ],
            traces=frame_traces,
            layout={"annotations": make_dynamic_annotations(
                idx,
                month_hours,
                month_u,
                month_tsr,
                month_cp,
                month_inner,
                month_outer,
                month_alert,
            )},
        )
        frames.append(frame)

    fig.frames = frames

    slider_steps = []
    for idx in range(frame_count):
        slider_steps.append(
            {
                "args": [
                    [str(int(month_hours[idx]))],
                    {"frame": {"duration": 80, "redraw": True}, "mode": "immediate", "transition": {"duration": 0}},
                ],
                "label": str(int(month_hours[idx])),
                "method": "animate",
            }
        )

    fig.update_layout(
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.08,
                "y": 1.16,
                "showactive": False,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [
                            None,
                            {"frame": {"duration": 80, "redraw": True}, "fromcurrent": True, "transition": {"duration": 0}},
                        ],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {"frame": {"duration": 0, "redraw": False}, "mode": "immediate", "transition": {"duration": 0}},
                        ],
                    },
                ],
            }
        ],
        sliders=[
            {
                "x": 0.08,
                "y": 1.09,
                "len": 0.84,
                "pad": {"b": 10, "t": 20},
                "currentvalue": {"prefix": "Hour of year: "},
                "steps": slider_steps,
            }
        ],
    )

    return fig


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    csv_path = repo_root / "CDO_wind_2023_hourly.csv"
    output_dir = repo_root / "CDO_wind_visualizations_2023"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "viz9_dpcbf_sphere_3d.html"

    df = load_dataset(csv_path)
    components = compute_wind_components(df)
    particle_state = simulate_particles(components)
    capture = compute_capture_metrics(components, particle_state)
    direction_stats = direction_statistics(components)

    print_summary(components, capture, direction_stats)
    export_sphere_metrics(output_dir, components, particle_state, capture)

    fig = build_figure(components, particle_state, capture, direction_stats)
    fig.write_html(output_path, include_plotlyjs="cdn")
    fig.show()


if __name__ == "__main__":
    main()
