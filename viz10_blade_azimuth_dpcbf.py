# viz10_blade_azimuth_dpcbf.py
# CDO VAWT — explicit blade-azimuth relative velocity and DPCBF capture
# Standalone visualization bridging rotor ODE, wind decomposition, and per-particle capture.
#
# Physics:
#   U(t) = U_mean + u'(t), with u' made explicit as an AR(1) turbulence process
#   dx/dt = v_air,x, dy/dt = v_air,y, dz/dt = v_air,z
#   dv_air/dt = (v_infty + v_induced - v_air) / tau_air
#   domega/dt = (T_aero - T_gen - B*omega) / J, using the existing SIL plant/controller
#   v_rel(phi) = v_wind_vector - omega*R*tangent(phi), evaluated around the full rotor circle
#   h(x) = v_rel,los_x + lambda(d,|v_rel|)*v_rel,los_y^2 + mu(d), evaluated in the LoS frame
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
SAFE_CORE_RADIUS_M = 0.55 * ROTOR_RADIUS_M
AMBIENT_RELAXATION_S = 1.8
INDUCED_SWIRL_GAIN = 0.65
INDUCED_DECAY_RADIUS_M = 1.15 * ROTOR_RADIUS_M
INDUCED_VERTICAL_GAIN = 0.04
K_LAMBDA = 0.9
K_MU = 0.6

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
    ring_x = ROTOR_RADIUS_M * np.cos(phi)
    ring_y = ROTOR_RADIUS_M * np.sin(phi)
    p_rel_x = -ring_x
    p_rel_y = -ring_y
    p_rel_norm = np.sqrt(p_rel_x**2 + p_rel_y**2)
    los_angle = np.arctan2(p_rel_y, p_rel_x)

    tangent_x = -np.sin(phi)
    tangent_y = np.cos(phi)

    tip_vel_x = rotor["omega"][:, None] * ROTOR_RADIUS_M * tangent_x[None, :]
    tip_vel_y = rotor["omega"][:, None] * ROTOR_RADIUS_M * tangent_y[None, :]

    v_rel_x = state["wind_vec_x"][:, None] - tip_vel_x
    v_rel_y = state["wind_vec_y"][:, None] - tip_vel_y
    v_rel_mag = np.sqrt(v_rel_x**2 + v_rel_y**2)
    cos_los = np.cos(los_angle)[None, :]
    sin_los = np.sin(los_angle)[None, :]
    v_rel_los_x = cos_los * v_rel_x + sin_los * v_rel_y
    v_rel_los_y = -sin_los * v_rel_x + cos_los * v_rel_y

    d_tip = np.sqrt(np.maximum(p_rel_norm**2 - SAFE_CORE_RADIUS_M**2, 1e-9))[None, :]
    lambda_tip = K_LAMBDA * d_tip / np.maximum(v_rel_mag, 0.1)
    mu_tip = np.broadcast_to(K_MU * d_tip, v_rel_mag.shape)
    h_tip = v_rel_los_x + lambda_tip * (v_rel_los_y**2) + mu_tip

    return {
        "phi": phi,
        "ring_x": ring_x,
        "ring_y": ring_y,
        "v_rel_x": v_rel_x,
        "v_rel_y": v_rel_y,
        "v_rel_mag": v_rel_mag,
        "v_rel_los_x": v_rel_los_x,
        "v_rel_los_y": v_rel_los_y,
        "lambda_tip": lambda_tip,
        "mu_tip": mu_tip,
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
    clipped = np.clip(distance_norm, 0.0, 2.0)
    lambda_d = K_LAMBDA * clipped
    mu_d = K_MU * clipped
    return lambda_d, mu_d


def induced_air_velocity(position_xy: np.ndarray, omega: float) -> np.ndarray:
    x, y = position_xy
    radius = float(np.hypot(x, y))
    if radius < 1e-9:
        tangent = np.array([0.0, 0.0], dtype=float)
    else:
        tangent = np.array([-y, x], dtype=float) / radius
    swirl_strength = INDUCED_SWIRL_GAIN * omega * ROTOR_RADIUS_M * np.exp(-(radius / INDUCED_DECAY_RADIUS_M) ** 2)
    return swirl_strength * tangent


def simulate_particles(
    state: dict[str, np.ndarray],
    rotor: dict[str, np.ndarray],
    azimuth: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    n_steps = len(state["hours"])
    frame_count = min(MONTH_FRAMES, n_steps)
    rng = np.random.default_rng(RNG_SEED + 99)

    positions = np.zeros((frame_count, N_PARTICLES, 3), dtype=float)
    h_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    v_rel_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    v_rel_los_x_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    v_rel_los_y_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    lambda_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    mu_particle = np.zeros((n_steps, N_PARTICLES), dtype=float)
    d_clearance = np.zeros((n_steps, N_PARTICLES), dtype=float)
    capture_fraction = np.zeros(n_steps, dtype=float)
    mean_h = np.zeros(n_steps, dtype=float)
    mean_radius = np.zeros(n_steps, dtype=float)

    particles = np.stack([upstream_spawn(state["theta_rad"][0], rng) for _ in range(N_PARTICLES)], axis=0)
    velocities = np.zeros((N_PARTICLES, 3), dtype=float)
    velocities[:, 0] = state["u_mean"][0] * np.sin(state["theta_rad"][0])
    velocities[:, 1] = state["u_mean"][0] * np.cos(state["theta_rad"][0])

    for idx in range(n_steps):
        ambient_target = np.array(
            [
                state["u_mean"][idx] * np.sin(state["theta_rad"][idx]),
                state["u_mean"][idx] * np.cos(state["theta_rad"][idx]),
                INDUCED_VERTICAL_GAIN * state["u_prime"][idx],
            ],
            dtype=float,
        )

        if idx > 0:
            for p_idx in range(N_PARTICLES):
                induced_xy = induced_air_velocity(particles[p_idx, :2], rotor["omega"][idx])
                induced = np.array([induced_xy[0], induced_xy[1], 0.0], dtype=float)
                dv_dt = (ambient_target + induced - velocities[p_idx]) / AMBIENT_RELAXATION_S
                velocities[p_idx] = velocities[p_idx] + dv_dt * DT_VIZ_S
            particles = particles + velocities * DT_VIZ_S

        r_now = np.linalg.norm(particles, axis=1)
        escaped = r_now > (2.5 * ROTOR_RADIUS_M)
        if np.any(escaped):
            particles[escaped] = np.stack(
                [upstream_spawn(state["theta_rad"][idx], rng) for _ in range(int(np.count_nonzero(escaped)))],
                axis=0,
            )
            velocities[escaped, 0] = ambient_target[0]
            velocities[escaped, 1] = ambient_target[1]
            velocities[escaped, 2] = ambient_target[2]
            r_now = np.linalg.norm(particles, axis=1)

        p_rel_x = -particles[:, 0]
        p_rel_y = -particles[:, 1]
        p_rel_norm = np.sqrt(p_rel_x**2 + p_rel_y**2)
        los_angle = np.arctan2(p_rel_y, p_rel_x)
        cos_los = np.cos(los_angle)
        sin_los = np.sin(los_angle)

        phi_particle = np.mod(np.arctan2(particles[:, 1], particles[:, 0]), 2.0 * np.pi)
        local_air_x = velocities[:, 0]
        local_air_y = velocities[:, 1]
        tip_vel_x = rotor["omega"][idx] * ROTOR_RADIUS_M * (-np.sin(phi_particle))
        tip_vel_y = rotor["omega"][idx] * ROTOR_RADIUS_M * (np.cos(phi_particle))
        local_vrel_x = local_air_x - tip_vel_x
        local_vrel_y = local_air_y - tip_vel_y
        local_vrel_mag = np.sqrt(local_vrel_x**2 + local_vrel_y**2)
        local_vrel_los_x = cos_los * local_vrel_x + sin_los * local_vrel_y
        local_vrel_los_y = -sin_los * local_vrel_x + cos_los * local_vrel_y

        clearance = np.sqrt(np.maximum(p_rel_norm**2 - SAFE_CORE_RADIUS_M**2, 1e-9))
        lambda_d = K_LAMBDA * clearance / np.maximum(local_vrel_mag, 0.1)
        mu_d = K_MU * clearance
        h_now = local_vrel_los_x + lambda_d * (local_vrel_los_y**2) + mu_d

        if idx < frame_count:
            positions[idx] = particles
        h_particle[idx] = h_now
        v_rel_particle[idx] = local_vrel_mag
        v_rel_los_x_particle[idx] = local_vrel_los_x
        v_rel_los_y_particle[idx] = local_vrel_los_y
        lambda_particle[idx] = lambda_d
        mu_particle[idx] = mu_d
        d_clearance[idx] = clearance
        capture_fraction[idx] = float(np.mean(h_now >= 0.0))
        mean_h[idx] = float(np.mean(h_now))
        mean_radius[idx] = float(np.mean(r_now))

    return {
        "positions": positions,
        "h_particle": h_particle,
        "v_rel_particle": v_rel_particle,
        "v_rel_los_x_particle": v_rel_los_x_particle,
        "v_rel_los_y_particle": v_rel_los_y_particle,
        "lambda_particle": lambda_particle,
        "mu_particle": mu_particle,
        "d_clearance": d_clearance,
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
    print("Assumption note: lambda ~ k_lambda*d/|v_rel| and mu ~ k_mu*d are paper-inspired mappings adapted to the rotor sphere.")


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
            "v_rel_los_x_ms": azimuth["v_rel_los_x"][:frame_count].reshape(-1),
            "v_rel_los_y_ms": azimuth["v_rel_los_y"][:frame_count].reshape(-1),
            "v_rel_mag_ms": azimuth["v_rel_mag"][:frame_count].reshape(-1),
            "lambda_tip": azimuth["lambda_tip"][:frame_count].reshape(-1),
            "mu_tip": azimuth["mu_tip"][:frame_count].reshape(-1),
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
            "v_rel_los_x_ms": particles["v_rel_los_x_particle"][:frame_count].reshape(-1),
            "v_rel_los_y_ms": particles["v_rel_los_y_particle"][:frame_count].reshape(-1),
            "d_clearance_m": particles["d_clearance"][:frame_count].reshape(-1),
            "lambda_particle": particles["lambda_particle"][:frame_count].reshape(-1),
            "mu_particle": particles["mu_particle"][:frame_count].reshape(-1),
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
    particle_state = simulate_particles(state, rotor, azimuth)

    print_summary(state, rotor, azimuth, particle_state)
    export_sphere_metrics(output_dir, state, rotor, azimuth, particle_state)

    fig = build_figure(state, rotor, azimuth, particle_state)
    fig.write_html(output_path, include_plotlyjs="cdn")
    fig.show()


if __name__ == "__main__":
    main()
