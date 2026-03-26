# viz10_blade_azimuth_dpcbf.py
# CDO VAWT — explicit blade-azimuth relative velocity and DPCBF capture
# Standalone visualization bridging rotor ODE, wind decomposition, and per-particle capture.
#
# Physics:
#   U(t) = U_mean + u'(t), with u' made explicit as an AR(1) turbulence process
#   dx/dt = U_mean*sin(theta), dy/dt = U_mean*cos(theta), dz/dt = 0
#   domega/dt = (T_aero - T_gen - B*omega) / J, using the existing SIL plant/controller
#   v_rel(phi) = v_wind_vector - omega*R*tangent(phi), evaluated around the full rotor circle
#   h(x) = v_rel,x + lambda(d)*v_rel,y^2 + mu(d), evaluated per particle
#
# Design insight:
#   This script makes the missing link explicit:
#   the rotor does not see one disk-averaged relative speed, it sees a blade-azimuth field.
#
# Data: CDO_wind_2023_hourly.csv (NASA POWER + ERA5, CDO 2023, UTC+8)
# requires: numpy pandas plotly

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from CDO_project_constants import (
    CP_GENERIC,
    DRIVETRAIN_DAMPING_NMS,
    ROTOR_INERTIA_KGM2,
    ROTOR_RADIUS_M,
    STANDARD_AIR_DENSITY,
    SWEPT_AREA_M2,
    TSR_OPT,
    TSR_SPREAD,
)
from sil_controller import ControllerSensors, SimpleVAWTController
from sil_plant_model import SimpleVAWTPlant


MONTH_FRAMES = 720
DT_DATA_S = 3600.0
DT_VIZ_S = 0.5
PLANT_SUBSTEPS_PER_HOUR = 60
AR1_PERSISTENCE = 0.85
TURBULENCE_INTENSITY = 0.10
N_PARTICLES = 90
N_AZIMUTH = 72
RNG_SEED = 2027

PARTICLE_COLORSCALE = [
    [0.0, "#991b1b"],
    [0.45, "#f59e0b"],
    [0.5, "#fef3c7"],
    [0.55, "#86efac"],
    [1.0, "#166534"],
]


def load_dataset(csv_path: Path) -> pd.DataFrame:
    required_columns = [
        "wind_speed_15m_ms",
        "wind_direction_10m_deg",
        "air_density_kgm3",
        "season",
        "hour_of_year",
    ]
    return pd.read_csv(csv_path, usecols=required_columns)


def generate_ar1_turbulence(u_mean: np.ndarray, persistence: float, ti: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u_prime = np.zeros_like(u_mean, dtype=float)

    sigma = ti * u_mean
    if len(u_mean) == 0:
        return u_prime

    u_prime[0] = sigma[0] * rng.standard_normal()
    innovation_scale = np.sqrt(max(0.0, 1.0 - persistence**2))

    for idx in range(1, len(u_mean)):
        innovation_sigma = sigma[idx] * innovation_scale
        u_prime[idx] = persistence * u_prime[idx - 1] + innovation_sigma * rng.standard_normal()

    return u_prime


def build_wind_state(df: pd.DataFrame) -> dict[str, np.ndarray]:
    u_mean = df["wind_speed_15m_ms"].to_numpy(dtype=float)
    theta_deg = np.mod(df["wind_direction_10m_deg"].to_numpy(dtype=float), 360.0)
    theta_rad = np.deg2rad(theta_deg)
    rho = df["air_density_kgm3"].to_numpy(dtype=float)
    hours = df["hour_of_year"].to_numpy(dtype=int)
    seasons = df["season"].astype(str).to_numpy()

    u_prime = generate_ar1_turbulence(
        u_mean=u_mean,
        persistence=AR1_PERSISTENCE,
        ti=TURBULENCE_INTENSITY,
        seed=RNG_SEED,
    )
    u_total = np.clip(u_mean + u_prime, 0.1, None)
    wind_vec_x = u_total * np.sin(theta_rad)
    wind_vec_y = u_total * np.cos(theta_rad)

    return {
        "u_mean": u_mean,
        "u_prime": u_prime,
        "u_total": u_total,
        "theta_deg": theta_deg,
        "theta_rad": theta_rad,
        "rho": rho,
        "hours": hours,
        "seasons": seasons,
        "wind_vec_x": wind_vec_x,
        "wind_vec_y": wind_vec_y,
    }


def simulate_rotor_response(state: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    controller = SimpleVAWTController()
    plant = SimpleVAWTPlant()
    plant_state = plant.initial_state()
    substep_dt = DT_DATA_S / PLANT_SUBSTEPS_PER_HOUR

    omega = np.zeros_like(state["u_total"])
    rotor_rpm = np.zeros_like(state["u_total"])
    tsr = np.zeros_like(state["u_total"])
    cp = np.zeros_like(state["u_total"])
    t_aero = np.zeros_like(state["u_total"])
    p_elec_kw = np.zeros_like(state["u_total"])
    gen_torque = np.zeros_like(state["u_total"])
    brake_torque = np.zeros_like(state["u_total"])

    for idx in range(len(state["u_total"])):
        wind_speed = float(state["u_total"][idx])
        rho = float(state["rho"][idx])
        command = None
        outputs = None

        for _ in range(PLANT_SUBSTEPS_PER_HOUR):
            sensors = ControllerSensors(
                wind_speed_ms=wind_speed,
                rotor_rpm=float(plant_state.rotor_rpm),
                air_density_kgm3=rho,
            )
            command = controller.command(sensors)
            outputs = plant.step(
                state=plant_state,
                wind_speed_ms=wind_speed,
                air_density_kgm3=rho,
                command=command,
                dt_seconds=substep_dt,
            )
            plant_state = outputs.state

        omega[idx] = outputs.state.omega_rad_s
        rotor_rpm[idx] = outputs.state.rotor_rpm
        tsr[idx] = outputs.tip_speed_ratio
        cp[idx] = outputs.cp_effective
        t_aero[idx] = outputs.aerodynamic_torque_nm
        p_elec_kw[idx] = outputs.electrical_power_kw
        gen_torque[idx] = command.generator_torque_nm
        brake_torque[idx] = command.brake_torque_nm

    domega_dt = np.zeros_like(omega)
    domega_dt[1:] = np.diff(omega) / DT_DATA_S

    return {
        "omega": omega,
        "rotor_rpm": rotor_rpm,
        "omega_cross_r": omega * ROTOR_RADIUS_M,
        "tsr": tsr,
        "cp": cp,
        "t_aero": t_aero,
        "p_elec_kw": p_elec_kw,
        "gen_torque": gen_torque,
        "brake_torque": brake_torque,
        "domega_dt": domega_dt,
    }


def compute_azimuthal_relative_velocity(
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    phi = np.linspace(0.0, 2.0 * np.pi, N_AZIMUTH, endpoint=False)
    tangent_x = -np.sin(phi)
    tangent_y = np.cos(phi)

    tip_vel_x = rotor["omega"][:, None] * ROTOR_RADIUS_M * tangent_x[None, :]
    tip_vel_y = rotor["omega"][:, None] * ROTOR_RADIUS_M * tangent_y[None, :]

    v_rel_x = state["wind_vec_x"][:, None] - tip_vel_x
    v_rel_y = state["wind_vec_y"][:, None] - tip_vel_y
    v_rel_mag = np.sqrt(v_rel_x**2 + v_rel_y**2)

    lambda_tip = np.full_like(v_rel_x, 0.005)
    mu_tip = np.full_like(v_rel_x, -0.15)
    h_tip = v_rel_x + lambda_tip * (v_rel_y**2) + mu_tip

    return {
        "phi": phi,
        "v_rel_x": v_rel_x,
        "v_rel_y": v_rel_y,
        "v_rel_mag": v_rel_mag,
        "h_tip": h_tip,
    }


def upstream_spawn(theta_rad: float, rng: np.random.Generator) -> np.ndarray:
    wind_dir = np.array([np.sin(theta_rad), np.cos(theta_rad), 0.0], dtype=float)
    cross_dir = np.array([np.cos(theta_rad), -np.sin(theta_rad), 0.0], dtype=float)
    base = -3.0 * ROTOR_RADIUS_M * wind_dir
    lateral = rng.uniform(-0.6 * ROTOR_RADIUS_M, 0.6 * ROTOR_RADIUS_M)
    z0 = rng.uniform(-0.18 * ROTOR_RADIUS_M, 0.18 * ROTOR_RADIUS_M)
    return base + lateral * cross_dir + np.array([0.0, 0.0, z0], dtype=float)


def periodic_interp(sample_angles: np.ndarray, grid_angles: np.ndarray, values: np.ndarray) -> np.ndarray:
    grid_ext = np.concatenate([grid_angles, [2.0 * np.pi]])
    values_ext = np.concatenate([values, [values[0]]])
    return np.interp(sample_angles, grid_ext, values_ext)


def lambda_mu_from_distance(distance_norm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    clipped = np.clip(distance_norm, -1.0, 1.0)
    lambda_d = 0.005 + 0.025 * np.clip(clipped, 0.0, 1.0)
    mu_d = 0.40 * clipped - 0.15
    return lambda_d, mu_d


def simulate_particles(
    state: dict[str, np.ndarray],
    azimuth: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    n_steps = len(state["hours"])
    frame_count = min(MONTH_FRAMES, n_steps)
    rng = np.random.default_rng(RNG_SEED + 99)

    positions = np.zeros((frame_count, N_PARTICLES, 3), dtype=float)
    h_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    v_rel_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    capture_fraction = np.zeros(n_steps, dtype=float)
    mean_h = np.zeros(n_steps, dtype=float)
    mean_radius = np.zeros(n_steps, dtype=float)

    particles = np.stack([upstream_spawn(state["theta_rad"][0], rng) for _ in range(N_PARTICLES)], axis=0)

    for idx in range(n_steps):
        if idx > 0:
            vx = state["u_mean"][idx] * np.sin(state["theta_rad"][idx])
            vy = state["u_mean"][idx] * np.cos(state["theta_rad"][idx])
            particles[:, 0] += vx * DT_VIZ_S
            particles[:, 1] += vy * DT_VIZ_S

        r_now = np.linalg.norm(particles, axis=1)
        escaped = r_now > (2.5 * ROTOR_RADIUS_M)
        if np.any(escaped):
            particles[escaped] = np.stack(
                [upstream_spawn(state["theta_rad"][idx], rng) for _ in range(int(np.count_nonzero(escaped)))],
                axis=0,
            )
            r_now = np.linalg.norm(particles, axis=1)

        phi_particle = np.mod(np.arctan2(particles[:, 1], particles[:, 0]), 2.0 * np.pi)
        vrel_x_particle = periodic_interp(phi_particle, azimuth["phi"], azimuth["v_rel_x"][idx])
        vrel_y_particle = periodic_interp(phi_particle, azimuth["phi"], azimuth["v_rel_y"][idx])
        distance_norm = (ROTOR_RADIUS_M - r_now) / ROTOR_RADIUS_M
        lambda_d, mu_d = lambda_mu_from_distance(distance_norm)
        h_now = vrel_x_particle + lambda_d * (vrel_y_particle**2) + mu_d

        if idx < frame_count:
            positions[idx] = particles
        h_particle[idx] = h_now
        v_rel_particle[idx] = np.sqrt(vrel_x_particle**2 + vrel_y_particle**2)
        capture_fraction[idx] = float(np.mean(h_now >= 0.0))
        mean_h[idx] = float(np.mean(h_now))
        mean_radius[idx] = float(np.mean(r_now))

    return {
        "positions": positions,
        "h_particle": h_particle,
        "v_rel_particle": v_rel_particle,
        "capture_fraction": capture_fraction,
        "mean_h": mean_h,
        "mean_radius": mean_radius,
    }


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
        hoverinfo="skip",
        name=name,
        contours={
            "x": {"show": True, "color": color, "width": 1},
            "y": {"show": True, "color": color, "width": 1},
            "z": {"show": True, "color": color, "width": 1},
        },
    )


def print_summary(
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
    azimuth: dict[str, np.ndarray],
    particles: dict[str, np.ndarray],
) -> None:
    annual_energy_mwh = float(np.sum(rotor["p_elec_kw"]) / 1000.0)
    mean_ring_vrel = float(np.mean(azimuth["v_rel_mag"]))
    monthly_alert = particles["mean_h"] < 0.0
    annual_capture_proxy = float(np.mean(np.maximum(rotor["cp"], 0.0)))
    annual_omega = float(np.mean(rotor["omega"]))
    monthly_negative = int(np.count_nonzero(particles["mean_h"][:MONTH_FRAMES] < 0.0))

    annual_ring_mean = np.mean(azimuth["v_rel_mag"], axis=0)
    dominant_idx = int(np.argmax(annual_ring_mean))
    phi_deg = np.rad2deg(azimuth["phi"])
    sector_start = int(phi_deg[dominant_idx])
    sector_end = int((sector_start + 360 / N_AZIMUTH))

    print("=== CDO EXPLICIT BLADE-AZIMUTH DPCBF SUMMARY (2023) ===")
    print(f"Mean wind speed (15m): {np.mean(state['u_mean']):.3f} m/s")
    print(f"Mean turbulence u': {np.mean(state['u_prime']):.3f} m/s")
    print(f"Mean rotor speed omega: {annual_omega:.3f} rad/s")
    print(f"Mean Cp (plant): {annual_capture_proxy:.4f}")
    print(f"Mean |v_rel(phi)| around rotor: {mean_ring_vrel:.3f} m/s")
    print(
        "Hours with negative monthly mean h(x): "
        f"{monthly_negative}/{MONTH_FRAMES} "
        f"({100.0 * monthly_negative / MONTH_FRAMES:.1f}% of month-1 animation window)"
    )
    print(f"Peak azimuth sector by annual mean |v_rel|: {sector_start}-{sector_end} deg")
    print(f"Estimated annual electrical energy (plant, MWh): {annual_energy_mwh:.3f}")
    print("Assumption note: lambda(d) and mu(d) are distance-gated heuristic terms until the exact paper form is encoded.")


def export_sphere_metrics(
    output_dir: Path,
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
    azimuth: dict[str, np.ndarray],
    particles: dict[str, np.ndarray],
) -> tuple[Path, Path, Path]:
    hourly_path = output_dir / "viz10_sphere_hourly_metrics.csv"
    azimuth_path = output_dir / "viz10_blade_azimuth_month1.csv"
    particle_path = output_dir / "viz10_particle_capture_month1.csv"

    frame_count = min(MONTH_FRAMES, len(state["hours"]))
    hourly_df = pd.DataFrame(
        {
            "hour_of_year": state["hours"],
            "season": state["seasons"],
            "u_mean_ms": state["u_mean"],
            "u_prime_ms": state["u_prime"],
            "u_total_ms": state["u_total"],
            "theta_deg": state["theta_deg"],
            "wind_vec_x_ms": state["wind_vec_x"],
            "wind_vec_y_ms": state["wind_vec_y"],
            "omega_rad_s": rotor["omega"],
            "domega_dt": rotor["domega_dt"],
            "omega_cross_r_ms": rotor["omega_cross_r"],
            "rotor_rpm": rotor["rotor_rpm"],
            "tsr": rotor["tsr"],
            "cp_effective": rotor["cp"],
            "aero_torque_nm": rotor["t_aero"],
            "generator_torque_nm": rotor["gen_torque"],
            "brake_torque_nm": rotor["brake_torque"],
            "electrical_power_kw": rotor["p_elec_kw"],
            "particle_capture_fraction": particles["capture_fraction"],
            "particle_mean_h": particles["mean_h"],
            "particle_mean_radius_m": particles["mean_radius"],
        }
    )
    hourly_df.to_csv(hourly_path, index=False)

    hour_grid = np.repeat(state["hours"][:frame_count], N_AZIMUTH)
    phi_deg_grid = np.tile(np.rad2deg(azimuth["phi"]), frame_count)
    azimuth_df = pd.DataFrame(
        {
            "hour_of_year": hour_grid,
            "phi_deg": phi_deg_grid,
            "v_rel_x_ms": azimuth["v_rel_x"][:frame_count].reshape(-1),
            "v_rel_y_ms": azimuth["v_rel_y"][:frame_count].reshape(-1),
            "v_rel_mag_ms": azimuth["v_rel_mag"][:frame_count].reshape(-1),
            "h_tip": azimuth["h_tip"][:frame_count].reshape(-1),
        }
    )
    azimuth_df.to_csv(azimuth_path, index=False)

    particle_hour_grid = np.repeat(state["hours"][:frame_count], N_PARTICLES)
    particle_index_grid = np.tile(np.arange(N_PARTICLES, dtype=int), frame_count)
    particle_df = pd.DataFrame(
        {
            "hour_of_year": particle_hour_grid,
            "particle_index": particle_index_grid,
            "x_m": particles["positions"][:frame_count, :, 0].reshape(-1),
            "y_m": particles["positions"][:frame_count, :, 1].reshape(-1),
            "z_m": particles["positions"][:frame_count, :, 2].reshape(-1),
            "v_rel_particle_ms": particles["v_rel_particle"][:frame_count].reshape(-1),
            "h_particle": particles["h_particle"][:frame_count].reshape(-1),
        }
    )
    particle_df.to_csv(particle_path, index=False)

    print(f"Saved sphere metrics: {hourly_path.name} ({len(hourly_df)} rows)")
    print(f"Saved azimuth metrics: {azimuth_path.name} ({len(azimuth_df)} rows)")
    print(f"Saved particle metrics: {particle_path.name} ({len(particle_df)} rows)")
    return hourly_path, azimuth_path, particle_path


def make_annotations(
    idx: int,
    hours: np.ndarray,
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
    particles: dict[str, np.ndarray],
) -> list[dict]:
    alert_text = "DPCBF violated" if particles["mean_h"][idx] < 0.0 else "DPCBF satisfied"
    alert_color = "#dc2626" if particles["mean_h"][idx] < 0.0 else "#166534"
    return [
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.19,
            "y": 0.99,
            "showarrow": False,
            "text": (
                f"Hour {int(hours[idx])} | "
                f"U={state['u_mean'][idx]:.2f} m/s | "
                f"u'={state['u_prime'][idx]:.2f} m/s | "
                f"omega={rotor['omega'][idx]:.2f} rad/s"
            ),
            "bgcolor": "rgba(255,255,255,0.92)",
            "bordercolor": "#94a3b8",
            "borderwidth": 1,
            "borderpad": 4,
            "font": {"size": 14, "color": "#0f172a"},
        },
        {
            "xref": "paper",
            "yref": "paper",
            "x": 0.03,
            "y": 0.82,
            "showarrow": False,
            "align": "left",
            "text": (
                f"Mean particle h(x): {particles['mean_h'][idx]:.3f}<br>"
                f"Capture fraction: {100.0 * particles['capture_fraction'][idx]:.1f}%<br>"
                f"<b><span style='color:{alert_color}'>{alert_text}</span></b>"
            ),
            "bgcolor": "rgba(255,255,255,0.90)",
            "bordercolor": alert_color,
            "borderwidth": 1,
            "borderpad": 6,
            "font": {"size": 11, "color": "#111827"},
        },
    ]


def build_figure(
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
    azimuth: dict[str, np.ndarray],
    particles: dict[str, np.ndarray],
) -> go.Figure:
    frame_count = min(MONTH_FRAMES, len(state["hours"]))
    hours = state["hours"][:frame_count]
    phi_deg = np.rad2deg(azimuth["phi"])
    phi_closed = np.append(phi_deg, 360.0)
    month_mean_h = particles["mean_h"][:frame_count]
    month_capture_fraction = particles["capture_fraction"][:frame_count]

    outer_mesh = sphere_mesh(ROTOR_RADIUS_M)
    phi_ring = azimuth["phi"]
    ring_x = ROTOR_RADIUS_M * np.cos(phi_ring)
    ring_y = ROTOR_RADIUS_M * np.sin(phi_ring)
    ring_z = np.zeros_like(phi_ring)

    initial_ring_mag = azimuth["v_rel_mag"][0]
    initial_ring_h = azimuth["h_tip"][0]
    initial_particle_h = particles["h_particle"][0]
    initial_particle_vrel = particles["v_rel_particle"][0]
    particle_size = 4.0 + 8.0 * (initial_particle_vrel / max(1.0, np.percentile(initial_particle_vrel, 95)))

    arrow_start = np.array(
        [
            -2.0 * ROTOR_RADIUS_M * np.sin(state["theta_rad"][0]),
            -2.0 * ROTOR_RADIUS_M * np.cos(state["theta_rad"][0]),
            0.0,
        ]
    )
    arrow_end = arrow_start + np.array(
        [
            0.8 * state["u_mean"][0] * np.sin(state["theta_rad"][0]),
            0.8 * state["u_mean"][0] * np.cos(state["theta_rad"][0]),
            0.0,
        ]
    )

    ring_peak_idx = int(np.argmax(initial_ring_mag))
    peak_marker_x = np.array([ring_x[ring_peak_idx]])
    peak_marker_y = np.array([ring_y[ring_peak_idx]])
    peak_marker_z = np.array([0.0])

    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            "3D Sphere, Particles, and Rotor-Circle v_rel(phi)",
            "Blade-Azimuth Relative Velocity and DPCBF Boundary",
            "Wind Decomposition and Rotor ODE Response",
            "Per-Particle DPCBF Capture Metrics",
        ),
        horizontal_spacing=0.10,
        vertical_spacing=0.12,
    )

    fig.add_trace(
        solid_surface(*outer_mesh, color="rgba(37,99,235,1.0)", opacity=0.12, name="Capture sphere"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=np.append(ring_x, ring_x[0]),
            y=np.append(ring_y, ring_y[0]),
            z=np.append(ring_z, ring_z[0]),
            mode="lines",
            line={"color": "#334155", "width": 6},
            name="Rotor circle",
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=ring_x,
            y=ring_y,
            z=ring_z,
            mode="markers",
            name="v_rel(phi) samples",
            marker={
                "size": 5,
                "color": initial_ring_mag,
                "colorscale": "Turbo",
                "cmin": 0.0,
                "cmax": max(1.0, float(np.percentile(azimuth["v_rel_mag"], 99.0))),
                "colorbar": {"title": "|v_rel(phi)|", "len": 0.35, "x": 0.45, "y": 0.82},
            },
            hovertemplate="phi=%{customdata:.1f} deg<br>|v_rel|=%{marker.color:.2f}<extra></extra>",
            customdata=phi_deg,
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=particles["positions"][0, :, 0],
            y=particles["positions"][0, :, 1],
            z=particles["positions"][0, :, 2],
            mode="markers",
            name="Particles",
            marker={
                "size": particle_size,
                "color": initial_particle_h,
                "colorscale": PARTICLE_COLORSCALE,
                "cmin": -4.0,
                "cmax": 4.0,
                "opacity": 0.92,
                "line": {"width": 0.3, "color": "white"},
            },
            hovertemplate="h=%{marker.color:.2f}<extra></extra>",
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
            line={"color": "#111827", "width": 8},
            marker={"size": [1, 5], "color": "#111827"},
            name="Wind vector",
            hovertemplate="Incoming wind<extra></extra>",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter3d(
            x=peak_marker_x,
            y=peak_marker_y,
            z=peak_marker_z,
            mode="markers",
            marker={"size": 8, "color": "#ef4444", "symbol": "diamond"},
            name="Peak |v_rel| azimuth",
            hovertemplate="Peak azimuth<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=phi_closed,
            y=np.append(initial_ring_mag, initial_ring_mag[0]),
            mode="lines",
            line={"color": "#2563eb", "width": 2},
            name="|v_rel(phi)|",
            hovertemplate="phi=%{x:.1f} deg<br>|v_rel|=%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=phi_closed,
            y=np.append(initial_ring_h, initial_ring_h[0]),
            mode="lines",
            line={"color": "#f97316", "width": 2},
            name="h_tip(phi)",
            hovertemplate="phi=%{x:.1f} deg<br>h_tip=%{y:.2f}<extra></extra>",
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[0.0, 360.0],
            y=[0.0, 0.0],
            mode="lines",
            line={"color": "#64748b", "width": 1.2, "dash": "dash"},
            name="h=0",
            hoverinfo="skip",
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Scatter(
            x=hours,
            y=state["u_mean"][:frame_count],
            mode="lines",
            line={"color": "#2563eb", "width": 2},
            name="U_mean",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=hours,
            y=state["u_prime"][:frame_count],
            mode="lines",
            line={"color": "#f97316", "width": 1.8, "dash": "dash"},
            name="u'",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=hours,
            y=rotor["omega_cross_r"][:frame_count],
            mode="lines",
            line={"color": "#16a34a", "width": 1.8, "dash": "dot"},
            name="omega*R",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=hours,
            y=rotor["omega"][:frame_count],
            mode="lines",
            line={"color": "#111827", "width": 2.5},
            name="omega",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=[hours[0], hours[0]],
            y=[
                min(np.min(state["u_prime"][:frame_count]), np.min(rotor["omega"][:frame_count]), -0.5),
                max(np.max(state["u_mean"][:frame_count]), np.max(rotor["omega_cross_r"][:frame_count]), np.max(rotor["omega"][:frame_count])) + 0.5,
            ],
            mode="lines",
            line={"color": "#dc2626", "width": 2},
            name="Current hour",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    ode_vline_idx = len(fig.data) - 1

    fig.add_trace(
        go.Scatter(
            x=hours,
            y=month_mean_h,
            mode="lines",
            line={"color": "#7c3aed", "width": 2},
            name="mean h(x)",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=hours,
            y=month_capture_fraction,
            mode="lines",
            line={"color": "#059669", "width": 2},
            name="capture fraction",
            yaxis="y2",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[hours[0], hours[-1]],
            y=[0.0, 0.0],
            mode="lines",
            line={"color": "#64748b", "width": 1.2, "dash": "dash"},
            name="mean h=0",
            hoverinfo="skip",
        ),
        row=2,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=[hours[0], hours[0]],
            y=[float(np.min(month_mean_h) - 0.2), float(np.max(month_mean_h) + 0.2)],
            mode="lines",
            line={"color": "#dc2626", "width": 2},
            name="Current hour metric",
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=2,
    )
    metrics_vline_idx = len(fig.data) - 1

    fig.update_layout(
        template="plotly_white",
        title={"text": "CDO VAWT — explicit blade-azimuth relative velocity and DPCBF capture", "x": 0.5},
        height=980,
        width=1450,
        margin={"l": 40, "r": 40, "t": 90, "b": 40},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.08, "xanchor": "left", "x": 0.0},
        annotations=make_annotations(0, hours, state, rotor, particles),
    )

    fig.update_scenes(
        xaxis={"title": "x (m)", "range": [-2.2, 2.2], "backgroundcolor": "rgb(248,250,252)"},
        yaxis={"title": "y (m)", "range": [-2.2, 2.2], "backgroundcolor": "rgb(248,250,252)"},
        zaxis={"title": "z (m)", "range": [-0.8, 0.8], "backgroundcolor": "rgb(248,250,252)"},
        aspectmode="cube",
        camera={"eye": {"x": 1.55, "y": 1.55, "z": 1.3}},
    )
    fig.update_xaxes(title_text="Blade azimuth phi (deg)", row=1, col=2)
    fig.update_yaxes(title_text="Velocity / boundary value", row=1, col=2)
    fig.update_xaxes(title_text="Hour of year", row=2, col=1)
    fig.update_yaxes(title_text="Velocity / omega", row=2, col=1)
    fig.update_xaxes(title_text="Hour of year", row=2, col=2)
    fig.update_yaxes(title_text="mean h(x)", row=2, col=2)

    frame_traces = [2, 3, 4, 5, 6, 7, ode_vline_idx, metrics_vline_idx]
    frames = []
    vrel_cmax = max(1.0, float(np.percentile(azimuth["v_rel_mag"][:frame_count], 99.0)))

    for idx in range(frame_count):
        ring_mag = azimuth["v_rel_mag"][idx]
        ring_h = azimuth["h_tip"][idx]
        particle_h = particles["h_particle"][idx]
        particle_v = particles["v_rel_particle"][idx]
        particle_size = 4.0 + 8.0 * (particle_v / max(1.0, np.percentile(particle_v, 95)))

        arrow_start = np.array(
            [
                -2.0 * ROTOR_RADIUS_M * np.sin(state["theta_rad"][idx]),
                -2.0 * ROTOR_RADIUS_M * np.cos(state["theta_rad"][idx]),
                0.0,
            ]
        )
        arrow_end = arrow_start + np.array(
            [
                0.8 * state["u_mean"][idx] * np.sin(state["theta_rad"][idx]),
                0.8 * state["u_mean"][idx] * np.cos(state["theta_rad"][idx]),
                0.0,
            ]
        )

        ring_peak_idx = int(np.argmax(ring_mag))

        frames.append(
            go.Frame(
                name=str(int(hours[idx])),
                data=[
                    go.Scatter3d(
                        x=ring_x,
                        y=ring_y,
                        z=ring_z,
                        marker={
                            "size": 5,
                            "color": ring_mag,
                            "colorscale": "Turbo",
                            "cmin": 0.0,
                            "cmax": vrel_cmax,
                        },
                        customdata=phi_deg,
                    ),
                    go.Scatter3d(
                        x=particles["positions"][idx, :, 0],
                        y=particles["positions"][idx, :, 1],
                        z=particles["positions"][idx, :, 2],
                        marker={
                            "size": particle_size,
                            "color": particle_h,
                            "colorscale": PARTICLE_COLORSCALE,
                            "cmin": -4.0,
                            "cmax": 4.0,
                            "opacity": 0.92,
                            "line": {"width": 0.3, "color": "white"},
                        },
                    ),
                    go.Scatter3d(
                        x=[arrow_start[0], arrow_end[0]],
                        y=[arrow_start[1], arrow_end[1]],
                        z=[arrow_start[2], arrow_end[2]],
                    ),
                    go.Scatter3d(
                        x=[ring_x[ring_peak_idx]],
                        y=[ring_y[ring_peak_idx]],
                        z=[0.0],
                    ),
                    go.Scatter(
                        x=phi_closed,
                        y=np.append(ring_mag, ring_mag[0]),
                    ),
                    go.Scatter(
                        x=phi_closed,
                        y=np.append(ring_h, ring_h[0]),
                    ),
                    go.Scatter(
                        x=[hours[idx], hours[idx]],
                        y=[
                            min(np.min(state["u_prime"][:frame_count]), np.min(rotor["omega"][:frame_count]), -0.5),
                            max(np.max(state["u_mean"][:frame_count]), np.max(rotor["omega_cross_r"][:frame_count]), np.max(rotor["omega"][:frame_count])) + 0.5,
                        ],
                    ),
                    go.Scatter(
                        x=[hours[idx], hours[idx]],
                        y=[float(np.min(month_mean_h) - 0.2), float(np.max(month_mean_h) + 0.2)],
                    ),
                ],
                traces=frame_traces,
                layout={"annotations": make_annotations(idx, hours, state, rotor, particles)},
            )
        )

    fig.frames = frames

    slider_steps = [
        {
            "args": [
                [str(int(hours[idx]))],
                {"frame": {"duration": 80, "redraw": True}, "mode": "immediate", "transition": {"duration": 0}},
            ],
            "label": str(int(hours[idx])),
            "method": "animate",
        }
        for idx in range(frame_count)
    ]

    fig.update_layout(
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.08,
                "y": 1.15,
                "showactive": False,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": 80, "redraw": True}, "fromcurrent": True, "transition": {"duration": 0}}],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate", "transition": {"duration": 0}}],
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
    output_path = output_dir / "viz10_blade_azimuth_dpcbf.html"

    df = load_dataset(csv_path)
    state = build_wind_state(df)
    rotor = simulate_rotor_response(state)
    azimuth = compute_azimuthal_relative_velocity(state, rotor)
    particle_state = simulate_particles(state, azimuth)

    print_summary(state, rotor, azimuth, particle_state)
    export_sphere_metrics(output_dir, state, rotor, azimuth, particle_state)

    fig = build_figure(state, rotor, azimuth, particle_state)
    fig.write_html(output_path, include_plotlyjs="cdn")
    fig.show()


if __name__ == "__main__":
    main()
