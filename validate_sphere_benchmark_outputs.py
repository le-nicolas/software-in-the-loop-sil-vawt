# validate_sphere_benchmark_outputs.py
# Numeric validation for sphere exports and Fusion360 benchmark outputs.
# requires: pandas numpy

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    root = Path(__file__).resolve().parent
    viz_dir = root / "CDO_wind_visualizations_2023"
    bench_dir = root / "design_benchmarks"

    viz9 = pd.read_csv(viz_dir / "viz9_sphere_hourly_metrics.csv")
    viz10_hourly = pd.read_csv(viz_dir / "viz10_sphere_hourly_metrics.csv")
    viz10_azimuth = pd.read_csv(viz_dir / "viz10_blade_azimuth_month1.csv")
    viz10_particle = pd.read_csv(viz_dir / "viz10_particle_capture_month1.csv")
    params = pd.read_csv(bench_dir / "fusion360_design_parameters.csv")
    load_cases = pd.read_csv(bench_dir / "fusion360_load_cases.csv")

    assert len(viz9) == 8760
    assert len(viz10_hourly) == 8760
    assert len(viz10_azimuth) == 720 * 72
    assert len(viz10_particle) == 720 * 90
    assert len(load_cases) == 4

    for df in (viz9, viz10_hourly, viz10_azimuth, viz10_particle, params, load_cases):
        assert not df.isna().any().any()

    assert viz9["particle_density"].between(0.0, 1.0).all()
    assert set(viz9["capture_alert"].unique()).issubset({0, 1})
    assert (viz9["n_inner"] <= viz9["n_outer"]).all()
    assert (viz10_hourly["particle_capture_fraction"].between(0.0, 1.0)).all()
    assert np.isfinite(viz10_hourly["particle_mean_h"]).all()
    assert np.isfinite(viz10_hourly["domega_dt"]).all()
    assert (viz10_azimuth.groupby("hour_of_year").size() == 72).all()
    assert (viz10_particle.groupby("hour_of_year").size() == 90).all()
    assert (viz10_azimuth["v_rel_mag_ms"] >= 0.0).all()

    param_map = dict(zip(params["parameter"], params["value"]))
    required_params = [
        "rotor_radius_m",
        "rotor_diameter_m",
        "rotor_height_m",
        "wind_operating_p50_ms",
        "wind_operating_p90_ms",
        "rotor_rpm_p50",
        "rotor_rpm_p90",
        "aero_torque_nm_p90",
        "aero_torque_nm_p95",
        "recommended_design_torque_nm",
        "recommended_peak_torque_nm",
    ]
    for key in required_params:
        assert key in param_map

    assert param_map["rotor_diameter_m"] == 2.0 * param_map["rotor_radius_m"]
    assert param_map["wind_operating_p90_ms"] >= param_map["wind_operating_p50_ms"]
    assert param_map["rotor_rpm_p90"] >= param_map["rotor_rpm_p50"]
    assert param_map["aero_torque_nm_p95"] >= param_map["aero_torque_nm_p90"]
    assert param_map["recommended_peak_torque_nm"] >= param_map["recommended_design_torque_nm"]

    print("SPHERE + BENCHMARK VALIDATION PASSED")
    print(f"viz9 alerts={int(viz9['capture_alert'].sum())}, density_mean={viz9['particle_density'].mean():.4f}")
    print(f"viz10 capture_fraction_mean={viz10_hourly['particle_capture_fraction'].mean():.4f}, mean_h_mean={viz10_hourly['particle_mean_h'].mean():.4f}")
    print(f"Fusion360 nominal rpm={param_map['rotor_rpm_p50']:.2f}, design torque={param_map['recommended_design_torque_nm']:.3f} N*m")


if __name__ == "__main__":
    main()
