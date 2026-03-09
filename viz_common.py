from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.io as pio

from CDO_project_constants import FINAL_CSV_SCHEMA, FINAL_CSV_SHAPE

CSV_PATH = Path("CDO_wind_2023_hourly.csv")
OUTPUT_DIR = Path("CDO_wind_visualizations_2023")
SEASON_COLORS = {
    "Amihan": "#00b4ff",
    "Habagat": "#ff6060",
    "Transition_DryDown": "#ffc800",
    "Transition_Rampup": "#00c864",
}
REQUIRED_COLUMNS = FINAL_CSV_SCHEMA


def ensure_output_dir() -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR


def load_and_validate_csv(csv_path: Path = CSV_PATH) -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(csv_path)
    warnings: list[str] = []

    print("CSV column names:")
    for col in df.columns:
        print(col)

    print(f"CSV shape: {df.shape}")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")

    if df.shape != FINAL_CSV_SHAPE:
        raise ValueError(f"Expected shape {FINAL_CSV_SHAPE}, got {df.shape}")

    ws15_min = float(df["wind_speed_15m_ms"].min())
    ws15_max = float(df["wind_speed_15m_ms"].max())
    ws15_mean = float(df["wind_speed_15m_ms"].mean())
    print(
        f"wind_speed_15m_ms stats: min={ws15_min:.6f}, max={ws15_max:.6f}, mean={ws15_mean:.6f}"
    )
    if ws15_mean < 2.5 or ws15_mean > 6.5:
        raise ValueError(
            f"wind_speed_15m_ms mean {ws15_mean:.6f} is outside the expected 2.5 to 6.5 m/s range"
        )

    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S", errors="raise")
    df = df.sort_values("hour_of_year").reset_index(drop=True)
    if not np.array_equal(df["hour_of_year"].to_numpy(), np.arange(1, len(df) + 1)):
        raise ValueError("hour_of_year is not a continuous 1..8760 sequence")

    ordered = list(df.columns) == REQUIRED_COLUMNS
    if not ordered:
        warnings.append("CSV column order does not match the requested schema order.")
        print("Warning: CSV column order does not match the requested schema order.")

    return df, warnings


def dropna_for_plot(df: pd.DataFrame, required_cols: list[str], plot_name: str) -> pd.DataFrame:
    cleaned = df.dropna(subset=required_cols).copy()
    dropped = len(df) - len(cleaned)
    print(f"{plot_name}: dropped {dropped} rows with NaN before plotting")
    return cleaned


def energy_density_wm2(df: pd.DataFrame) -> pd.Series:
    return 0.5 * df["air_density_kgm3"] * np.power(df["wind_speed_15m_ms"], 3)


def generation_power_w(df: pd.DataFrame) -> pd.Series:
    power = 0.5 * df["air_density_kgm3"] * 4.0 * 0.35 * np.power(df["wind_speed_15m_ms"], 3)
    return power.where(df["wind_speed_15m_ms"] >= 2.5, 0.0)


def save_figure(fig, output_path: Path) -> None:
    fig.write_html(output_path, include_plotlyjs=True, full_html=True)
    print(f"Saved {output_path.resolve()}")


def copy_csv_to_output(csv_path: Path = CSV_PATH) -> Path:
    output_dir = ensure_output_dir()
    dest = output_dir / csv_path.name
    shutil.copy2(csv_path, dest)
    print(f"Copied CSV to {dest.resolve()}")
    return dest


def month_label_map() -> dict[int, str]:
    return {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }


pio.templates.default = "plotly_white"
