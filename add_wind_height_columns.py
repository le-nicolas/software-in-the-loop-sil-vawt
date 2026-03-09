from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from CDO_project_constants import FINAL_CSV_SCHEMA


CSV_PATH = Path("CDO_wind_2023_hourly.csv")
AIR_DENSITY_COL = "air_density_kgm3"
WS10_COL = "wind_speed_10m_ms"
WS50_RAW_COL = "wind_speed_50m_ms"
ALPHA_COL = "alpha_actual"
CUT_IN_MS = 2.5
SWEPT_AREA_M2 = 4.0
CP = 0.35

HEIGHT_COLUMNS = {
    15: "wind_speed_15m_ms",
    20: "wind_speed_20m_ms",
    25: "wind_speed_25m_ms",
    30: "wind_speed_30m_ms",
    40: "wind_speed_40m_ms",
    50: "wind_speed_50m_ms_derived",
}


def power_law_speed(ws10: pd.Series, height_m: int, alpha: float) -> pd.Series:
    return ws10 * (height_m / 10.0) ** alpha


def annual_kwh(df: pd.DataFrame, speed_col: str) -> float:
    power_w = 0.5 * df[AIR_DENSITY_COL] * SWEPT_AREA_M2 * CP * np.power(df[speed_col], 3)
    power_w = power_w.where(df[speed_col] >= CUT_IN_MS, 0.0)
    return float(power_w.sum() / 1000.0)


def summarize_alpha(series: pd.Series, label: str) -> None:
    print(label)
    print(f"  mean: {series.mean():.6f}")
    print(f"  median: {series.median():.6f}")
    print(f"  p10: {series.quantile(0.10):.6f}")
    print(f"  p90: {series.quantile(0.90):.6f}")


def validate_rewrite(df_before: pd.DataFrame, csv_path: Path) -> pd.DataFrame:
    df_after = pd.read_csv(csv_path)

    numeric_cols = [col for col in df_before.columns if is_numeric_dtype(df_before[col])]
    non_numeric_cols = [col for col in df_before.columns if col not in numeric_cols]

    pd.testing.assert_frame_equal(
        df_before[numeric_cols],
        df_after[numeric_cols],
        check_exact=False,
        rtol=1e-9,
    )

    for col in non_numeric_cols:
        if not df_before[col].astype(str).equals(df_after[col].astype(str)):
            raise ValueError(f"Exact equality failed for non-numeric column {col}")

    print("Validation passed — numeric values preserved within floating point tolerance")
    return df_after


def main() -> None:
    df = pd.read_csv(CSV_PATH)

    required = [WS10_COL, WS50_RAW_COL, AIR_DENSITY_COL, "season"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    valid_mask = (
        df[WS10_COL].notna()
        & df[WS50_RAW_COL].notna()
        & (df[WS10_COL] > 0)
        & (df[WS50_RAW_COL] > 0)
    )
    if not valid_mask.any():
        raise ValueError("No valid rows found for alpha calculation")

    ratio = df.loc[valid_mask, WS50_RAW_COL] / df.loc[valid_mask, WS10_COL]
    alpha_actual = np.log(ratio) / np.log(50.0 / 10.0)
    df[ALPHA_COL] = np.nan
    df.loc[valid_mask, ALPHA_COL] = alpha_actual.to_numpy()

    print("Alpha summary:")
    summarize_alpha(df.loc[valid_mask, ALPHA_COL], "Overall")
    print("Alpha by season:")
    for season, season_alpha in df.loc[valid_mask].groupby("season")[ALPHA_COL]:
        summarize_alpha(season_alpha, season)

    median_alpha = float(df.loc[valid_mask, ALPHA_COL].median())
    print(f"Using median alpha for corrected power-law exponent: {median_alpha:.6f}")

    for height_m, col_name in HEIGHT_COLUMNS.items():
        df[col_name] = power_law_speed(df[WS10_COL], height_m, median_alpha)

    df = df[FINAL_CSV_SCHEMA]

    df_before_write = df.copy(deep=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"Updated CSV: {CSV_PATH.resolve()}")
    df = validate_rewrite(df_before_write, CSV_PATH)

    mean_labels = [
        ("10m", WS10_COL),
        ("15m", "wind_speed_15m_ms"),
        ("20m", "wind_speed_20m_ms"),
        ("25m", "wind_speed_25m_ms"),
        ("30m", "wind_speed_30m_ms"),
        ("40m", "wind_speed_40m_ms"),
        ("50m", "wind_speed_50m_ms_derived"),
    ]
    print("Mean wind speed by height (m/s):")
    for label, col in mean_labels:
        print(f"{label}: {df[col].mean():.6f}")

    baseline_col = "wind_speed_15m_ms"
    baseline_kwh = annual_kwh(df, baseline_col)
    print("Revised annual energy yield estimate by height (kWh):")
    for label, col in mean_labels:
        kwh = annual_kwh(df, col)
        gain_pct = ((kwh - baseline_kwh) / baseline_kwh * 100.0) if baseline_kwh != 0 else np.nan
        baseline_note = " (baseline)" if col == baseline_col else ""
        print(f"{label}: {kwh:.6f}{baseline_note}")
        print(f"{label} gain vs 15m: {gain_pct:.6f}%")


if __name__ == "__main__":
    main()
