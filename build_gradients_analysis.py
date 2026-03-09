from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from CDO_project_constants import (
    CP_GENERIC,
    FINAL_CSV_SCHEMA,
    FINAL_CSV_SHAPE,
    STANDARD_AIR_DENSITY,
    SWEPT_AREA_M2,
    TURBINE_RATED_KW,
)


MASTER_CSV = Path("CDO_wind_2023_hourly.csv")
OUTPUT_CSV = Path("CDO_wind_2023_gradients.csv")


def beaufort_category(speed: float) -> int:
    if pd.isna(speed):
        return np.nan
    if speed < 0.5:
        return 0
    if speed < 1.5:
        return 1
    if speed < 3.3:
        return 2
    if speed < 5.4:
        return 3
    if speed < 7.9:
        return 4
    if speed < 10.7:
        return 5
    if speed < 13.8:
        return 6
    if speed < 17.1:
        return 7
    return 8


def turbulence_class(ti: float) -> str:
    if pd.isna(ti):
        return np.nan
    if ti < 0.12:
        return "A"
    if ti <= 0.14:
        return "B"
    return "C"


def main() -> None:
    df = pd.read_csv(MASTER_CSV)
    if list(df.columns) != FINAL_CSV_SCHEMA:
        raise ValueError("Master CSV schema does not match FINAL_CSV_SCHEMA")
    if df.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Master CSV shape does not match {FINAL_CSV_SHAPE}")

    out = df[["hour_of_year", "datetime", "season"]].copy()

    speeds = {
        10: df["wind_speed_10m_ms"],
        15: df["wind_speed_15m_ms"],
        20: df["wind_speed_20m_ms"],
        25: df["wind_speed_25m_ms"],
        30: df["wind_speed_30m_ms"],
        40: df["wind_speed_40m_ms"],
        50: df["wind_speed_50m_ms_derived"],
    }

    shear_pairs = [(10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 50)]
    for h1, h2 in shear_pairs:
        out[f"shear_{h1}_{h2}"] = (speeds[h2] - speeds[h1]) / (h2 - h1)

    out["dv_dt"] = df["wind_speed_15m_ms"].diff()
    out["abs_dv_dt"] = out["dv_dt"].abs()

    roll_24_std = df["wind_speed_15m_ms"].rolling(window=24, min_periods=24).std()
    roll_24_mean = df["wind_speed_15m_ms"].rolling(window=24, min_periods=24).mean()
    roll_168_std = df["wind_speed_15m_ms"].rolling(window=168, min_periods=168).std()
    roll_168_mean = df["wind_speed_15m_ms"].rolling(window=168, min_periods=168).mean()
    out["TI_24h"] = roll_24_std / roll_24_mean
    out["TI_168h"] = roll_168_std / roll_168_mean
    out["turbulence_class"] = out["TI_24h"].apply(turbulence_class)

    for height, speed_series in speeds.items():
        out[f"WPD_{height}"] = 0.5 * df["air_density_kgm3"] * np.power(speed_series, 3)

    wpd_pairs = [(10, 15), (15, 20), (20, 25), (25, 30), (30, 40), (40, 50)]
    for h1, h2 in wpd_pairs:
        out[f"dWPD_dh_{h1}_{h2}"] = (out[f"WPD_{h2}"] - out[f"WPD_{h1}"]) / (h2 - h1)

    for height in [15, 25, 30]:
        out[f"P_available_{height}"] = (out[f"WPD_{height}"] * SWEPT_AREA_M2 * CP_GENERIC / 1000.0).clip(upper=TURBINE_RATED_KW)

    out["KEF_15"] = out["WPD_15"] * SWEPT_AREA_M2
    out["KEF_25"] = out["WPD_25"] * SWEPT_AREA_M2
    out["density_anomaly"] = df["air_density_kgm3"] - STANDARD_AIR_DENSITY
    out["beaufort"] = df["wind_speed_15m_ms"].apply(beaufort_category)

    output_columns = [
        "hour_of_year",
        "datetime",
        "season",
        "shear_10_15",
        "shear_15_20",
        "shear_20_25",
        "shear_25_30",
        "shear_30_40",
        "shear_40_50",
        "dv_dt",
        "abs_dv_dt",
        "TI_24h",
        "TI_168h",
        "turbulence_class",
        "WPD_10",
        "WPD_15",
        "WPD_20",
        "WPD_25",
        "WPD_30",
        "WPD_40",
        "WPD_50",
        "dWPD_dh_10_15",
        "dWPD_dh_15_20",
        "dWPD_dh_20_25",
        "dWPD_dh_25_30",
        "dWPD_dh_30_40",
        "dWPD_dh_40_50",
        "P_available_15",
        "P_available_25",
        "P_available_30",
        "KEF_15",
        "KEF_25",
        "density_anomaly",
        "beaufort",
    ]
    out = out[output_columns]
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved gradients analysis CSV to {OUTPUT_CSV.resolve()}")

    print("Mean WPD by height (W/m^2):")
    mean_wpd = {}
    for height in [10, 15, 20, 25, 30, 40, 50]:
        mean_val = float(out[f"WPD_{height}"].mean())
        mean_wpd[height] = mean_val
        print(f"{height}m: {mean_val:.6f}")

    print("Hours per turbulence class:")
    for cls in ["A", "B", "C"]:
        print(f"{cls}: {int((out['turbulence_class'] == cls).sum())}")

    print("Hours per Beaufort category:")
    beaufort_counts = out["beaufort"].value_counts(dropna=False).sort_index()
    for category, count in beaufort_counts.items():
        print(f"{category}: {int(count)}")

    mean_density_anomaly = float(out["density_anomaly"].mean())
    print(f"Mean density anomaly: {mean_density_anomaly:.6f}")

    max_gust_idx = out["abs_dv_dt"].idxmax()
    print(
        f"Max abs_dv_dt: {out.loc[max_gust_idx, 'abs_dv_dt']:.6f} at {out.loc[max_gust_idx, 'datetime']}"
    )

    best_height = max(mean_wpd, key=mean_wpd.get)
    print(f"Highest mean WPD height: {best_height}m")

    print("Season breakdown of turbulence class C hours:")
    class_c = out.loc[out["turbulence_class"] == "C"]
    season_c_counts = class_c["season"].value_counts().sort_index()
    for season, count in season_c_counts.items():
        print(f"{season}: {int(count)}")

    placeholder_constants = [
        "SWEPT_AREA_M2",
        "CP_GENERIC",
        "TURBINE_RATED_KW",
    ]
    print("Placeholder constants in CDO_project_constants.py:")
    for name in placeholder_constants:
        print(name)


if __name__ == "__main__":
    main()
