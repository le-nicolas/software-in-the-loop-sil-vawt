# build_fusion360_design_benchmark.py
# Fusion360-facing benchmark builder from CDO wind, rotor ODE, and sphere/DPCBF metrics.
# requires: numpy pandas

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import CUT_IN_MS, ROTOR_RADIUS_M, SWEPT_AREA_M2, TSR_OPT
from viz10_blade_azimuth_dpcbf import (
    compute_azimuthal_relative_velocity,
    load_dataset,
    build_wind_state,
    simulate_particles,
    simulate_rotor_response,
)


def nearest_index(values: np.ndarray, target: float, mask: np.ndarray | None = None) -> int:
    if mask is None:
        mask = np.ones_like(values, dtype=bool)
    masked_idx = np.where(mask)[0]
    return int(masked_idx[np.argmin(np.abs(values[masked_idx] - target))])


def build_benchmark_tables(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    df = load_dataset(repo_root / "CDO_wind_2023_hourly.csv")
    state = build_wind_state(df)
    rotor = simulate_rotor_response(state)
    azimuth = compute_azimuthal_relative_velocity(state, rotor)
    particles = simulate_particles(state, rotor, azimuth)

    operating_mask = state["u_total"] >= CUT_IN_MS
    operating_hours = int(np.count_nonzero(operating_mask))
    diameter_m = 2.0 * ROTOR_RADIUS_M
    height_m = SWEPT_AREA_M2 / diameter_m

    mean_ring_vrel = azimuth["v_rel_mag"].mean(axis=1)
    peak_ring_vrel = azimuth["v_rel_mag"].max(axis=1)
    peak_sector_deg = np.rad2deg(azimuth["phi"][np.argmax(azimuth["v_rel_mag"], axis=1)])

    annual_sector_idx = int(np.argmax(np.mean(azimuth["v_rel_mag"], axis=0)))
    annual_sector_deg = float(np.rad2deg(azimuth["phi"][annual_sector_idx]))

    op_u = state["u_total"][operating_mask]
    op_rpm = rotor["rotor_rpm"][operating_mask]
    op_omega = rotor["omega"][operating_mask]
    op_torque = rotor["t_aero"][operating_mask]
    op_cp = rotor["cp"][operating_mask]
    op_ring_mean = mean_ring_vrel[operating_mask]
    op_ring_peak = peak_ring_vrel[operating_mask]
    op_capture = particles["capture_fraction"][operating_mask]
    op_h = particles["mean_h"][operating_mask]

    parameter_rows = [
        ("rotor_radius_m", ROTOR_RADIUS_M, "m", "Repo design constant"),
        ("rotor_diameter_m", diameter_m, "m", "2 * rotor_radius_m"),
        ("rotor_height_m", height_m, "m", "SWEPT_AREA_M2 / diameter"),
        ("swept_area_m2", SWEPT_AREA_M2, "m2", "Repo design constant"),
        ("cut_in_ms", CUT_IN_MS, "m/s", "Repo controller/plant threshold"),
        ("operating_hours_2023", operating_hours, "hours", "u_total >= cut-in"),
        ("wind_operating_p50_ms", np.percentile(op_u, 50), "m/s", "Operating-hour percentile"),
        ("wind_operating_p75_ms", np.percentile(op_u, 75), "m/s", "Operating-hour percentile"),
        ("wind_operating_p90_ms", np.percentile(op_u, 90), "m/s", "Operating-hour percentile"),
        ("wind_operating_p95_ms", np.percentile(op_u, 95), "m/s", "Operating-hour percentile"),
        ("rotor_rpm_p50", np.percentile(op_rpm, 50), "rpm", "Operating-hour percentile"),
        ("rotor_rpm_p90", np.percentile(op_rpm, 90), "rpm", "Operating-hour percentile"),
        ("rotor_rpm_p95", np.percentile(op_rpm, 95), "rpm", "Operating-hour percentile"),
        ("omega_rad_s_p50", np.percentile(op_omega, 50), "rad/s", "Operating-hour percentile"),
        ("omega_rad_s_p90", np.percentile(op_omega, 90), "rad/s", "Operating-hour percentile"),
        ("aero_torque_nm_p50", np.percentile(op_torque, 50), "N*m", "Operating-hour percentile"),
        ("aero_torque_nm_p90", np.percentile(op_torque, 90), "N*m", "Design-load proxy"),
        ("aero_torque_nm_p95", np.percentile(op_torque, 95), "N*m", "Peak-load proxy"),
        ("cp_operating_p50", np.percentile(op_cp, 50), "-", "Operating-hour percentile"),
        ("cp_operating_p90", np.percentile(op_cp, 90), "-", "Operating-hour percentile"),
        ("vrel_ring_mean_p50_ms", np.percentile(op_ring_mean, 50), "m/s", "Mean azimuthal relative speed"),
        ("vrel_ring_mean_p90_ms", np.percentile(op_ring_mean, 90), "m/s", "Mean azimuthal relative speed"),
        ("vrel_ring_peak_p95_ms", np.percentile(op_ring_peak, 95), "m/s", "Peak azimuthal relative speed"),
        ("capture_fraction_p10", np.percentile(op_capture, 10), "-", "Lower-tail monthly capture proxy"),
        ("capture_fraction_p50", np.percentile(op_capture, 50), "-", "Median monthly capture proxy"),
        ("capture_fraction_p90", np.percentile(op_capture, 90), "-", "Upper-tail monthly capture proxy"),
        ("mean_h_p10", np.percentile(op_h, 10), "-", "Lower-tail DPCBF mean h"),
        ("mean_h_p50", np.percentile(op_h, 50), "-", "Median DPCBF mean h"),
        ("mean_h_p90", np.percentile(op_h, 90), "-", "Upper-tail DPCBF mean h"),
        ("dominant_peak_sector_deg", annual_sector_deg, "deg", "Annual max-mean azimuth sector"),
        ("recommended_nominal_tsr", TSR_OPT, "-", "Use as Fusion360 motion baseline"),
        ("recommended_nominal_rpm", np.percentile(op_rpm, 50), "rpm", "Nominal CAD animation / design case"),
        ("recommended_upper_rpm", np.percentile(op_rpm, 90), "rpm", "Upper operating CAD animation case"),
        ("recommended_design_torque_nm", np.percentile(op_torque, 90), "N*m", "Design structural load case"),
        ("recommended_peak_torque_nm", np.percentile(op_torque, 95), "N*m", "Peak structural load case"),
        ("recommended_nominal_tip_speed_ms", np.percentile(op_omega, 50) * ROTOR_RADIUS_M, "m/s", "Blade-tip speed baseline"),
        ("recommended_upper_tip_speed_ms", np.percentile(op_omega, 90) * ROTOR_RADIUS_M, "m/s", "Blade-tip speed upper case"),
    ]
    parameters_df = pd.DataFrame(parameter_rows, columns=["parameter", "value", "units", "basis"])

    case_targets = {
        "cut_in_edge": CUT_IN_MS,
        "typical_operating": float(np.percentile(op_u, 50)),
        "design_operating": float(np.percentile(op_u, 90)),
        "upper_speed_case": float(np.percentile(op_u, 95)),
    }
    case_rows = []
    for label, target_speed in case_targets.items():
        idx = nearest_index(state["u_total"], target_speed, mask=operating_mask)
        peak_idx = int(np.argmax(azimuth["v_rel_mag"][idx]))
        case_rows.append(
            {
                "case": label,
                "hour_of_year": int(state["hours"][idx]),
                "season": state["seasons"][idx],
                "u_mean_ms": float(state["u_mean"][idx]),
                "u_prime_ms": float(state["u_prime"][idx]),
                "u_total_ms": float(state["u_total"][idx]),
                "theta_deg": float(state["theta_deg"][idx]),
                "omega_rad_s": float(rotor["omega"][idx]),
                "rotor_rpm": float(rotor["rotor_rpm"][idx]),
                "cp_effective": float(rotor["cp"][idx]),
                "aero_torque_nm": float(rotor["t_aero"][idx]),
                "generator_torque_nm": float(rotor["gen_torque"][idx]),
                "electrical_power_kw": float(rotor["p_elec_kw"][idx]),
                "hourly_energy_kwh": float(rotor["hourly_energy_kwh"][idx]),
                "mean_ring_vrel_ms": float(mean_ring_vrel[idx]),
                "peak_ring_vrel_ms": float(peak_ring_vrel[idx]),
                "peak_sector_deg": float(peak_sector_deg[idx]),
                "particle_capture_fraction": float(particles["capture_fraction"][idx]),
                "particle_mean_h": float(particles["mean_h"][idx]),
            }
        )
    load_cases_df = pd.DataFrame(case_rows)

    summary_text = "\n".join(
        [
            "=== Fusion360 Design Foundation Benchmark ===",
            f"Rotor radius: {ROTOR_RADIUS_M:.3f} m",
            f"Rotor diameter: {diameter_m:.3f} m",
            f"Rotor height from swept area: {height_m:.3f} m",
            f"Operating hours in 2023: {operating_hours}",
            f"Nominal operating wind: {np.percentile(op_u, 50):.3f} m/s",
            f"Design operating wind (P90): {np.percentile(op_u, 90):.3f} m/s",
            f"Nominal rotor speed: {np.percentile(op_rpm, 50):.2f} rpm",
            f"Upper rotor speed (P90): {np.percentile(op_rpm, 90):.2f} rpm",
            f"Design aero torque (P90): {np.percentile(op_torque, 90):.3f} N*m",
            f"Peak aero torque (P95): {np.percentile(op_torque, 95):.3f} N*m",
            f"Peak azimuth sector: {annual_sector_deg:.1f} deg",
            f"Lower-tail capture fraction (P10): {np.percentile(op_capture, 10):.3f}",
            f"Median capture fraction: {np.percentile(op_capture, 50):.3f}",
            "Use the load-case table for Fusion360 motion studies, interference envelopes, and first-pass structural load conditions.",
        ]
    )

    return parameters_df, load_cases_df, summary_text


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    output_dir = repo_root / "design_benchmarks"
    output_dir.mkdir(exist_ok=True)

    parameters_df, load_cases_df, summary_text = build_benchmark_tables(repo_root)
    parameters_path = output_dir / "fusion360_design_parameters.csv"
    load_cases_path = output_dir / "fusion360_load_cases.csv"
    summary_path = output_dir / "fusion360_design_summary.txt"

    parameters_df.to_csv(parameters_path, index=False)
    load_cases_df.to_csv(load_cases_path, index=False)
    summary_path.write_text(summary_text + "\n", encoding="utf-8")

    print(summary_text)
    print(f"Saved: {parameters_path.name} ({len(parameters_df)} rows)")
    print(f"Saved: {load_cases_path.name} ({len(load_cases_df)} rows)")
    print(f"Saved: {summary_path.name}")


if __name__ == "__main__":
    main()
