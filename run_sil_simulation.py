from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import FINAL_CSV_SCHEMA, FINAL_CSV_SHAPE, GRID_IDS_ROW_MAJOR, ROTOR_RADIUS_M, TURBINE_RATED_KW
from sil_controller import ControllerSensors, SimpleVAWTController
from sil_plant_model import PlantState, SimpleVAWTPlant
from spatial_turbulence_model import CorrelatedTurbulenceGenerator, GridLayout, default_grid_layout


REFINED_WIDE_CSV = Path("CDO_grid_wind_2023_wide_openmeteo.csv")
REFINED_LONG_CSV = Path("CDO_grid_wind_2023_long_openmeteo.csv")
MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
GRADIENTS_CSV = Path("CDO_wind_2023_gradients.csv")
HOURLY_OUTPUT = Path("CDO_sil_run_2023_hourly.csv")
SUMMARY_OUTPUT = Path("CDO_sil_run_2023_summary.txt")

SECONDS_PER_SUBSTEP = 60.0
SUBSTEPS_PER_HOUR = int(3600 / SECONDS_PER_SUBSTEP)
ROTOR_RING_SAMPLES = 24


@dataclass(frozen=True)
class PreparedForcing:
    wide: pd.DataFrame
    density_matrix: np.ndarray
    season: np.ndarray
    datetime_text: np.ndarray
    ti_24h: np.ndarray
    grid_weights: np.ndarray
    ws15_matrix: np.ndarray
    wd15_matrix: np.ndarray
    layout: GridLayout
    ring_phi_rad: np.ndarray
    ring_interpolation_weights: np.ndarray
    forcing_label: str


def build_ring_interpolation(layout: GridLayout, ring_radius_m: float = ROTOR_RADIUS_M) -> tuple[np.ndarray, np.ndarray]:
    phi = np.linspace(0.0, 2.0 * np.pi, ROTOR_RING_SAMPLES, endpoint=False)
    ring_xy = np.column_stack([ring_radius_m * np.cos(phi), ring_radius_m * np.sin(phi)])
    source_xy = layout.coordinates

    deltas = ring_xy[:, None, :] - source_xy[None, :, :]
    distances = np.sqrt(np.sum(deltas**2, axis=-1))
    weights = 1.0 / np.maximum(distances, 1e-3) ** 2
    weights = weights / weights.sum(axis=1, keepdims=True)
    return phi, weights


def load_forcing() -> PreparedForcing:
    wide = pd.read_csv(REFINED_WIDE_CSV)
    long_df = pd.read_csv(REFINED_LONG_CSV)
    master = pd.read_csv(MASTER_CSV)
    gradients = pd.read_csv(GRADIENTS_CSV)[["hour_of_year", "TI_24h"]]

    if wide.shape != (8760, 52):
        raise ValueError(f"Refined wide CSV shape mismatch: expected (8760, 52), got {wide.shape}")
    if long_df["grid_id"].nunique() != 25 or len(long_df) != 219000:
        raise ValueError("Refined long CSV does not contain the expected 25-point x 8760 structure")
    if list(master.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema mismatch")
    if master.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape mismatch: expected {FINAL_CSV_SHAPE}, got {master.shape}")

    meta = (
        long_df.loc[long_df["grid_id"] == "R2C2", ["hour_of_year", "datetime", "season"]]
        .sort_values("hour_of_year")
        .merge(gradients, on="hour_of_year", how="left")
    )
    meta["TI_24h"] = meta["TI_24h"].fillna(0.15)

    openmeteo_ws15 = np.column_stack([wide[f"{gid}_ws15"].to_numpy() for gid in GRID_IDS_ROW_MAJOR])
    openmeteo_wd15 = np.column_stack([wide[f"{gid}_wd"].to_numpy() for gid in GRID_IDS_ROW_MAJOR])
    density_matrix = np.column_stack(
        [
            long_df.loc[long_df["grid_id"] == gid, "air_density_kgm3"].sort_index().to_numpy()
            for gid in GRID_IDS_ROW_MAJOR
        ]
    )
    master_ws15 = master["wind_speed_15m_ms"].to_numpy(dtype=float)
    master_wd10 = master["wind_direction_10m_deg"].to_numpy(dtype=float)

    center_openmeteo_ws15 = openmeteo_ws15[:, 12]
    ws_ratio = np.divide(
        openmeteo_ws15,
        center_openmeteo_ws15[:, None],
        out=np.ones_like(openmeteo_ws15),
        where=center_openmeteo_ws15[:, None] > 0.0,
    )
    direction_delta = (openmeteo_wd15 - openmeteo_wd15[:, [12]] + 180.0) % 360.0 - 180.0
    ws15_matrix = master_ws15[:, None] * ws_ratio
    wd15_matrix = np.mod(master_wd10[:, None] + direction_delta, 360.0)

    layout = default_grid_layout()
    radius = np.sqrt(layout.x**2 + layout.y**2)
    grid_weights = np.exp(-(radius**2) / (2.0 * (4.5**2)))
    grid_weights = grid_weights / grid_weights.sum()

    ring_phi_rad, ring_interpolation_weights = build_ring_interpolation(layout)

    return PreparedForcing(
        wide=wide,
        density_matrix=density_matrix,
        season=meta["season"].to_numpy(),
        datetime_text=meta["datetime"].to_numpy(),
        ti_24h=meta["TI_24h"].to_numpy(dtype=float),
        grid_weights=grid_weights,
        ws15_matrix=ws15_matrix,
        wd15_matrix=wd15_matrix,
        layout=layout,
        ring_phi_rad=ring_phi_rad,
        ring_interpolation_weights=ring_interpolation_weights,
        forcing_label=(
            "NASA master center magnitude blended with Open-Meteo refined "
            "per-point speed ratios and direction deltas, preserved through "
            "a ring-resolved inflow reconstruction before disk summary"
        ),
    )


def resolved_rotor_inflow(
    speed: np.ndarray,
    direction_deg: np.ndarray,
    density: np.ndarray,
    weights: np.ndarray,
    ring_phi_rad: np.ndarray,
    ring_interpolation_weights: np.ndarray,
) -> dict[str, np.ndarray | float]:
    radians = np.deg2rad(direction_deg)
    u = speed * np.sin(radians)
    v = speed * np.cos(radians)
    u_eff = float(np.sum(weights * u))
    v_eff = float(np.sum(weights * v))
    disk_speed = float(np.hypot(u_eff, v_eff))
    disk_direction = float(np.mod(np.degrees(np.arctan2(u_eff, v_eff)), 360.0))
    disk_density = float(np.sum(weights * density))

    ring_u = ring_interpolation_weights @ u
    ring_v = ring_interpolation_weights @ v
    ring_density = ring_interpolation_weights @ density
    ring_speed = np.hypot(ring_u, ring_v)
    ring_direction_deg = np.mod(np.degrees(np.arctan2(ring_u, ring_v)), 360.0)

    wind_hat = np.array([np.sin(np.deg2rad(disk_direction)), np.cos(np.deg2rad(disk_direction))], dtype=float)
    ring_radial = np.column_stack([np.cos(ring_phi_rad), np.sin(ring_phi_rad)])
    upwind_mask = (ring_radial @ wind_hat) <= 0.0
    downwind_mask = ~upwind_mask
    upwind_speed = float(np.mean(ring_speed[upwind_mask])) if np.any(upwind_mask) else disk_speed
    downwind_speed = float(np.mean(ring_speed[downwind_mask])) if np.any(downwind_mask) else disk_speed

    return {
        "disk_speed_ms": disk_speed,
        "disk_direction_deg": disk_direction,
        "disk_density_kgm3": disk_density,
        "ring_u_ms": ring_u,
        "ring_v_ms": ring_v,
        "ring_speed_ms": ring_speed,
        "ring_direction_deg": ring_direction_deg,
        "ring_density_kgm3": ring_density,
        "ring_phi_rad": ring_phi_rad,
        "upwind_face_speed_ms": upwind_speed,
        "downwind_face_speed_ms": downwind_speed,
        "azimuthal_speed_std_ms": float(np.std(ring_speed)),
        "spatial_asymmetry_index": float((upwind_speed - downwind_speed) / max(float(np.mean(ring_speed)), 0.1)),
    }


def run() -> pd.DataFrame:
    forcing = load_forcing()
    turbulence = CorrelatedTurbulenceGenerator(seed=2026)
    controller = SimpleVAWTController()
    plant = SimpleVAWTPlant()
    state = plant.initial_state()
    previous_outputs = None

    records: list[dict[str, object]] = []
    cumulative_kwh = 0.0
    hours_generating = 0

    for idx in range(8760):
        mean_speed = forcing.ws15_matrix[idx]
        mean_direction = forcing.wd15_matrix[idx]
        density = forcing.density_matrix[idx]
        ti = float(forcing.ti_24h[idx])

        disturbed = turbulence.step(mean_speed=mean_speed, mean_direction_deg=mean_direction, ti=ti)
        inflow = resolved_rotor_inflow(
            disturbed["speed"],
            disturbed["direction_deg"],
            density,
            forcing.grid_weights,
            forcing.ring_phi_rad,
            forcing.ring_interpolation_weights,
        )

        power_integral_kwh = 0.0
        aero_torque_samples: list[float] = []
        tsr_samples: list[float] = []
        cp_samples: list[float] = []
        power_kw_samples: list[float] = []
        upwind_speed_samples: list[float] = []
        downwind_speed_samples: list[float] = []
        asymmetry_samples: list[float] = []
        mode_counts: dict[str, int] = {}

        for _ in range(SUBSTEPS_PER_HOUR):
            sensors = ControllerSensors(
                wind_speed_ms=float(inflow["disk_speed_ms"]),
                rotor_rpm=state.rotor_rpm,
                air_density_kgm3=float(inflow["disk_density_kgm3"]),
                tip_speed_ratio=0.0 if previous_outputs is None else previous_outputs.tip_speed_ratio,
                cp_effective=0.0 if previous_outputs is None else previous_outputs.cp_effective,
                aerodynamic_torque_nm=0.0 if previous_outputs is None else previous_outputs.aerodynamic_torque_nm,
            )
            command = controller.command(sensors)
            outputs = plant.step(
                state=state,
                wind_speed_ms=float(inflow["disk_speed_ms"]),
                air_density_kgm3=float(inflow["disk_density_kgm3"]),
                command=command,
                dt_seconds=SECONDS_PER_SUBSTEP,
                inflow_direction_deg=float(inflow["disk_direction_deg"]),
                ring_speed_ms=np.asarray(inflow["ring_speed_ms"], dtype=float),
                ring_direction_deg=np.asarray(inflow["ring_direction_deg"], dtype=float),
                ring_density_kgm3=np.asarray(inflow["ring_density_kgm3"], dtype=float),
                ring_phi_rad=np.asarray(inflow["ring_phi_rad"], dtype=float),
            )
            state = outputs.state
            previous_outputs = outputs
            power_integral_kwh += outputs.electrical_power_kw * (SECONDS_PER_SUBSTEP / 3600.0)
            aero_torque_samples.append(outputs.aerodynamic_torque_nm)
            tsr_samples.append(outputs.tip_speed_ratio)
            cp_samples.append(outputs.cp_effective)
            power_kw_samples.append(outputs.electrical_power_kw)
            upwind_speed_samples.append(outputs.upwind_face_speed_ms)
            downwind_speed_samples.append(outputs.downwind_face_speed_ms)
            asymmetry_samples.append(outputs.spatial_asymmetry_index)
            mode_counts[command.mode] = mode_counts.get(command.mode, 0) + 1

        hourly_energy_kwh = power_integral_kwh
        mean_power_kw = hourly_energy_kwh / ((SECONDS_PER_SUBSTEP * SUBSTEPS_PER_HOUR) / 3600.0)
        cumulative_kwh += hourly_energy_kwh
        if hourly_energy_kwh > 0.0:
            hours_generating += 1

        dominant_mode = max(mode_counts.items(), key=lambda item: item[1])[0]
        records.append(
            {
                "hour_of_year": idx + 1,
                "datetime": forcing.datetime_text[idx],
                "season": forcing.season[idx],
                "ti_24h": ti,
                "effective_wind_speed_ms": float(inflow["disk_speed_ms"]),
                "effective_wind_direction_deg": float(inflow["disk_direction_deg"]),
                "effective_air_density_kgm3": float(inflow["disk_density_kgm3"]),
                "upwind_face_speed_ms": float(np.mean(upwind_speed_samples)),
                "downwind_face_speed_ms": float(np.mean(downwind_speed_samples)),
                "azimuthal_speed_std_ms": float(inflow["azimuthal_speed_std_ms"]),
                "spatial_asymmetry_index": float(np.mean(asymmetry_samples)),
                "rotor_rpm_end": state.rotor_rpm,
                "mean_power_kw": mean_power_kw,
                "hourly_energy_kwh": hourly_energy_kwh,
                "cumulative_kwh": cumulative_kwh,
                "hours_generating": hours_generating,
                "capacity_factor_so_far_pct": 100.0 * cumulative_kwh / ((idx + 1) * TURBINE_RATED_KW),
                "mean_aerodynamic_torque_nm": float(np.mean(aero_torque_samples)),
                "mean_tip_speed_ratio": float(np.mean(tsr_samples)),
                "mean_cp_effective": float(np.mean(cp_samples)),
                "mean_electrical_power_kw": float(np.mean(power_kw_samples)),
                "control_mode": dominant_mode,
                "forcing_label": forcing.forcing_label,
            }
        )

        if idx in {0, 999, 4499, 8759}:
            print(
                f"Hour {idx + 1}: wind={float(inflow['disk_speed_ms']):.3f} m/s "
                f"dir={float(inflow['disk_direction_deg']):.1f} deg "
                f"rpm_end={state.rotor_rpm:.2f} mean_power={mean_power_kw:.4f} kW "
                f"energy={hourly_energy_kwh:.4f} kWh asym={float(inflow['spatial_asymmetry_index']):.3f} "
                f"mode={dominant_mode}"
            )

    return pd.DataFrame.from_records(records)


def write_summary(df: pd.DataFrame) -> None:
    summary_lines = [
        "CDO SIL Run 2023 Summary",
        f"Source forcing: {df['forcing_label'].iloc[0]}",
        f"Hourly rows: {len(df)}",
        f"Final annual kWh: {df['cumulative_kwh'].iloc[-1]:.6f}",
        f"Hours generating: {int(df['hours_generating'].iloc[-1])}",
        f"Mean effective wind speed: {df['effective_wind_speed_ms'].mean():.6f} m/s",
        f"Mean upwind face speed: {df['upwind_face_speed_ms'].mean():.6f} m/s",
        f"Mean downwind face speed: {df['downwind_face_speed_ms'].mean():.6f} m/s",
        f"Mean spatial asymmetry index: {df['spatial_asymmetry_index'].mean():.6f}",
        f"Mean rotor RPM: {df['rotor_rpm_end'].mean():.6f}",
        f"Max rotor RPM: {df['rotor_rpm_end'].max():.6f}",
        f"Mean power: {df['mean_power_kw'].mean():.6f} kW",
        f"Mean electrical power from substeps: {df['mean_electrical_power_kw'].mean():.6f} kW",
        f"Peak power: {df['mean_power_kw'].max():.6f} kW",
        f"Annual energy cross-check (sum hourly_energy_kwh): {df['hourly_energy_kwh'].sum():.6f}",
        "Mode counts:",
    ]
    for mode, count in df["control_mode"].value_counts().items():
        summary_lines.append(f"- {mode}: {int(count)}")
    SUMMARY_OUTPUT.write_text("\n".join(summary_lines) + "\n", encoding="ascii")


def main() -> None:
    df = run()
    df.to_csv(HOURLY_OUTPUT, index=False)
    write_summary(df)
    print(f"Saved {HOURLY_OUTPUT.resolve()}")
    print(f"Saved {SUMMARY_OUTPUT.resolve()}")
    print(f"Final annual kWh: {df['cumulative_kwh'].iloc[-1]:.6f}")
    print(f"Hours generating: {int(df['hours_generating'].iloc[-1])}")
    print(f"Max rotor RPM: {df['rotor_rpm_end'].max():.6f}")


if __name__ == "__main__":
    main()
