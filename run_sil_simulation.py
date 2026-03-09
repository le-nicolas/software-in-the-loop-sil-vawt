from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import FINAL_CSV_SCHEMA, FINAL_CSV_SHAPE, GRID_IDS_ROW_MAJOR, TURBINE_RATED_KW
from sil_controller import ControllerSensors, SimpleVAWTController
from sil_plant_model import PlantState, SimpleVAWTPlant
from spatial_turbulence_model import CorrelatedTurbulenceGenerator, default_grid_layout


REFINED_WIDE_CSV = Path("CDO_grid_wind_2023_wide_openmeteo.csv")
REFINED_LONG_CSV = Path("CDO_grid_wind_2023_long_openmeteo.csv")
MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
GRADIENTS_CSV = Path("CDO_wind_2023_gradients.csv")
HOURLY_OUTPUT = Path("CDO_sil_run_2023_hourly.csv")
SUMMARY_OUTPUT = Path("CDO_sil_run_2023_summary.txt")

SECONDS_PER_SUBSTEP = 60.0
SUBSTEPS_PER_HOUR = int(3600 / SECONDS_PER_SUBSTEP)


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
    forcing_label: str


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

    return PreparedForcing(
        wide=wide,
        density_matrix=density_matrix,
        season=meta["season"].to_numpy(),
        datetime_text=meta["datetime"].to_numpy(),
        ti_24h=meta["TI_24h"].to_numpy(dtype=float),
        grid_weights=grid_weights,
        ws15_matrix=ws15_matrix,
        wd15_matrix=wd15_matrix,
        forcing_label=(
            "NASA master center magnitude blended with Open-Meteo refined "
            "per-point speed ratios and direction deltas"
        ),
    )


def weighted_effective_inflow(
    speed: np.ndarray,
    direction_deg: np.ndarray,
    density: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, float, float]:
    radians = np.deg2rad(direction_deg)
    u = speed * np.sin(radians)
    v = speed * np.cos(radians)
    u_eff = float(np.sum(weights * u))
    v_eff = float(np.sum(weights * v))
    speed_eff = float(np.hypot(u_eff, v_eff))
    direction_eff = float(np.mod(np.degrees(np.arctan2(u_eff, v_eff)), 360.0))
    density_eff = float(np.sum(weights * density))
    return speed_eff, direction_eff, density_eff


def run() -> pd.DataFrame:
    forcing = load_forcing()
    turbulence = CorrelatedTurbulenceGenerator(seed=2026)
    controller = SimpleVAWTController()
    plant = SimpleVAWTPlant()
    state = plant.initial_state()

    records: list[dict[str, object]] = []
    cumulative_kwh = 0.0
    hours_generating = 0

    for idx in range(8760):
        mean_speed = forcing.ws15_matrix[idx]
        mean_direction = forcing.wd15_matrix[idx]
        density = forcing.density_matrix[idx]
        ti = float(forcing.ti_24h[idx])

        disturbed = turbulence.step(mean_speed=mean_speed, mean_direction_deg=mean_direction, ti=ti)
        inflow_speed, inflow_direction, inflow_density = weighted_effective_inflow(
            disturbed["speed"],
            disturbed["direction_deg"],
            density,
            forcing.grid_weights,
        )

        power_integral_kwh = 0.0
        aero_torque_samples: list[float] = []
        tsr_samples: list[float] = []
        cp_samples: list[float] = []
        mode_counts: dict[str, int] = {}

        for _ in range(SUBSTEPS_PER_HOUR):
            sensors = ControllerSensors(
                wind_speed_ms=inflow_speed,
                rotor_rpm=state.rotor_rpm,
                air_density_kgm3=inflow_density,
            )
            command = controller.command(sensors)
            outputs = plant.step(
                state=state,
                wind_speed_ms=inflow_speed,
                air_density_kgm3=inflow_density,
                command=command,
                dt_seconds=SECONDS_PER_SUBSTEP,
            )
            state = outputs.state
            power_integral_kwh += outputs.electrical_power_kw * (SECONDS_PER_SUBSTEP / 3600.0)
            aero_torque_samples.append(outputs.aerodynamic_torque_nm)
            tsr_samples.append(outputs.tip_speed_ratio)
            cp_samples.append(outputs.cp_effective)
            mode_counts[command.mode] = mode_counts.get(command.mode, 0) + 1

        mean_power_kw = power_integral_kwh
        cumulative_kwh += power_integral_kwh
        if mean_power_kw > 0.0:
            hours_generating += 1

        dominant_mode = max(mode_counts.items(), key=lambda item: item[1])[0]
        records.append(
            {
                "hour_of_year": idx + 1,
                "datetime": forcing.datetime_text[idx],
                "season": forcing.season[idx],
                "ti_24h": ti,
                "effective_wind_speed_ms": inflow_speed,
                "effective_wind_direction_deg": inflow_direction,
                "effective_air_density_kgm3": inflow_density,
                "rotor_rpm_end": state.rotor_rpm,
                "mean_power_kw": mean_power_kw,
                "cumulative_kwh": cumulative_kwh,
                "hours_generating": hours_generating,
                "capacity_factor_so_far_pct": 100.0 * cumulative_kwh / ((idx + 1) * TURBINE_RATED_KW),
                "mean_aerodynamic_torque_nm": float(np.mean(aero_torque_samples)),
                "mean_tip_speed_ratio": float(np.mean(tsr_samples)),
                "mean_cp_effective": float(np.mean(cp_samples)),
                "control_mode": dominant_mode,
                "forcing_label": forcing.forcing_label,
            }
        )

        if idx in {0, 999, 4499, 8759}:
            print(
                f"Hour {idx + 1}: wind={inflow_speed:.3f} m/s dir={inflow_direction:.1f} deg "
                f"rpm_end={state.rotor_rpm:.2f} power={mean_power_kw:.4f} kW mode={dominant_mode}"
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
        f"Mean rotor RPM: {df['rotor_rpm_end'].mean():.6f}",
        f"Max rotor RPM: {df['rotor_rpm_end'].max():.6f}",
        f"Mean power: {df['mean_power_kw'].mean():.6f} kW",
        f"Peak power: {df['mean_power_kw'].max():.6f} kW",
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
