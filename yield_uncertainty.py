from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import ROTOR_RADIUS_M, SWEPT_AREA_M2, TSR_CP_LOOKUP_DMST, TURBINE_RATED_KW


N_SAMPLES = 1000
MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
BASELINE_CSV = Path("CDO_sil_run_2023_hourly.csv")
RESULTS_JSON = Path("yield_uncertainty_results.json")


def interp_cp(tsr: np.ndarray) -> np.ndarray:
    lookup = np.asarray(TSR_CP_LOOKUP_DMST, dtype=float)
    return np.interp(tsr, lookup[:, 0], lookup[:, 1], left=0.0, right=0.0)


def run_monte_carlo(n_samples: int = N_SAMPLES, seed: int = 2026) -> np.ndarray:
    master = pd.read_csv(MASTER_CSV)
    baseline = pd.read_csv(BASELINE_CSV)
    base_tsr = baseline["mean_tip_speed_ratio"].to_numpy(dtype=float)
    base_wind = master["wind_speed_15m_ms"].to_numpy(dtype=float)
    base_rho = master["air_density_kgm3"].to_numpy(dtype=float)

    rng = np.random.default_rng(seed)
    yields = np.zeros(n_samples, dtype=float)

    for i in range(n_samples):
        wind_scale = max(0.1, rng.normal(1.0, 0.08))
        cp_scale = max(0.1, rng.normal(1.0, 0.15))
        rho_scale = max(0.1, rng.normal(1.0, 0.03))

        wind = base_wind * wind_scale
        rho = base_rho * rho_scale
        cp = np.clip(interp_cp(base_tsr) * cp_scale, 0.0, 0.593)
        power_kw = 0.5 * rho * SWEPT_AREA_M2 * (wind**3) * cp / 1000.0
        power_kw = np.minimum(power_kw, TURBINE_RATED_KW)
        yields[i] = float(np.sum(power_kw))

    return yields


def summarize(yields_kwh: np.ndarray) -> dict[str, float]:
    p10 = float(np.percentile(yields_kwh, 10))
    p50 = float(np.percentile(yields_kwh, 50))
    p90 = float(np.percentile(yields_kwh, 90))
    mean = float(np.mean(yields_kwh))
    std = float(np.std(yields_kwh, ddof=1))
    daily_p50 = p50 * 1000.0 / 365.0
    daily_p10 = p10 * 1000.0 / 365.0
    daily_p90 = p90 * 1000.0 / 365.0
    return {
        "mean_yield_kwh": mean,
        "std_yield_kwh": std,
        "p10_yield_kwh": p10,
        "p50_yield_kwh": p50,
        "p90_yield_kwh": p90,
        "daily_p50_wh": daily_p50,
        "daily_p10_wh": daily_p10,
        "daily_p90_wh": daily_p90,
    }


def main() -> None:
    yields = run_monte_carlo()
    summary = summarize(yields)

    baseline_daily_wh = 45.0
    p10_better = summary["daily_p10_wh"] / baseline_daily_wh
    p50_better = summary["daily_p50_wh"] / baseline_daily_wh

    print(f"Mean yield          : {summary['mean_yield_kwh']:.3f} kWh/yr")
    print(f"Std deviation       : \u00b1 {summary['std_yield_kwh']:.3f} kWh/yr")
    print(f"P10 (pessimistic)   : {summary['p10_yield_kwh']:.3f} kWh/yr")
    print(f"P50 (median)        : {summary['p50_yield_kwh']:.3f} kWh/yr")
    print(f"P90 (optimistic)    : {summary['p90_yield_kwh']:.3f} kWh/yr")
    print(f"Daily P50           : {summary['daily_p50_wh']:.3f} Wh/day")
    print(f"Daily P10\u2013P90 range : {summary['daily_p10_wh']:.3f} \u2013 {summary['daily_p90_wh']:.3f} Wh/day")
    print(
        f"vs Lazada unit (~45 Wh/day): P10 is {p10_better:.2f}x better, "
        f"P50 is {p50_better:.2f}x better"
    )

    RESULTS_JSON.write_text(
        json.dumps(
            {
                "samples": len(yields),
                "yields_kwh": yields.tolist(),
                "summary": summary,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
