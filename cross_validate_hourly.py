from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
PYTHON_HOURLY = REPO_ROOT / "CDO_sil_run_2023_hourly.csv"
MATLAB_HOURLY = REPO_ROOT / "matlab_design_outputs" / "matlab_sil_hourly.csv"
SUMMARY_PATH = REPO_ROOT / "cross_validation_summary.txt"
PLOT_PATH = REPO_ROOT / "cross_validation_hourly.png"

PYTHON_MODE_NORMALIZATION = {
    "idle": "idle",
    "startup": "startup",
    "adaptive_mppt": "mppt",
    "mppt": "mppt",
    "brake": "brake",
}

MATLAB_MODE_NORMALIZATION = {
    1: "idle",
    2: "startup",
    3: "mppt",
    4: "brake",
}


def _fail(message: str) -> None:
    raise SystemExit(f"Cross-validation stopped: {message}")


def _read_hourly_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        _fail(f"{label} file not found: {path}")

    frame = pd.read_csv(path)
    if len(frame) != 8760:
        _fail(f"{label} row count is {len(frame)}, expected 8760")

    if "hour_of_year" not in frame.columns:
        _fail(f"{label} is missing the 'hour_of_year' column")

    if frame["hour_of_year"].isna().any():
        _fail(f"{label} contains missing hour_of_year values")

    if frame["hour_of_year"].duplicated().any():
        _fail(f"{label} contains duplicate hour_of_year values")

    expected_hours = np.arange(1, 8761)
    actual_hours = np.sort(frame["hour_of_year"].astype(int).to_numpy())
    if not np.array_equal(actual_hours, expected_hours):
        _fail(f"{label} hour_of_year coverage does not match 1..8760")

    return frame.sort_values("hour_of_year").reset_index(drop=True)


def _normalize_python_mode(value: object) -> str:
    mode = str(value).strip().lower()
    return PYTHON_MODE_NORMALIZATION.get(mode, mode)


def _normalize_matlab_mode(value: object) -> str:
    if pd.isna(value):
        return "unknown"
    try:
        mode_id = int(round(float(value)))
    except (TypeError, ValueError):
        return "unknown"
    return MATLAB_MODE_NORMALIZATION.get(mode_id, "unknown")


def _format_float(value: float, digits: int = 3) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value:.{digits}f}"


def _build_summary_table(merged: pd.DataFrame, abs_diff_w: np.ndarray) -> pd.DataFrame:
    python_modes = merged["control_mode"].map(_normalize_python_mode)
    matlab_modes = merged["mode_id"].map(_normalize_matlab_mode)

    top = merged.copy()
    top["abs_diff_w"] = abs_diff_w
    top["python_mode"] = python_modes
    top["matlab_mode"] = matlab_modes
    top["python_power_w"] = top["python_power_kw"] * 1000.0
    top["matlab_power_w"] = top["matlab_power_kw"] * 1000.0
    top["python_wind_speed_ms"] = top["effective_wind_speed_ms"]
    top["python_tsr"] = top["mean_tip_speed_ratio"]
    top["matlab_wind_speed_ms"] = top["wind_speed_15m_ms"]
    top["matlab_tsr"] = top["tsr"]

    columns = [
        "hour_of_year",
        "datetime_py",
        "abs_diff_w",
        "python_power_w",
        "matlab_power_w",
        "python_wind_speed_ms",
        "python_tsr",
        "python_mode",
        "matlab_wind_speed_ms",
        "matlab_tsr",
        "matlab_mode",
    ]
    top = top.rename(columns={"datetime": "datetime_py"})
    top = top.sort_values("abs_diff_w", ascending=False).head(10)[columns].reset_index(drop=True)
    return top


def _scatter_plot(python_power_w: np.ndarray, matlab_power_w: np.ndarray, metrics: dict[str, float]) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 8.2), dpi=160)
    ax.scatter(
        python_power_w,
        matlab_power_w,
        s=10,
        alpha=0.28,
        color="#2563eb",
        edgecolors="none",
    )

    combined_min = float(min(np.min(python_power_w), np.min(matlab_power_w)))
    combined_max = float(max(np.max(python_power_w), np.max(matlab_power_w)))
    padding = max(5.0, 0.05 * (combined_max - combined_min))
    lower = max(0.0, combined_min - padding)
    upper = combined_max + padding
    ax.plot([lower, upper], [lower, upper], color="#dc2626", linestyle="--", linewidth=1.6, label="1:1 line")

    ax.set_xlim(lower, upper)
    ax.set_ylim(lower, upper)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Python SIL power (W)")
    ax.set_ylabel("MATLAB Simulink power (W)")
    ax.set_title("Hourly cross-validation: Python SIL vs MATLAB Simulink")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")

    annotation = "\n".join(
        [
            f"RMSE: {_format_float(metrics['rmse_w'], 2)} W",
            f"MAPE: {_format_float(metrics['mape_pct'], 2)}%",
            f"Pearson r: {_format_float(metrics['pearson_r'], 4)}",
            f"Mode alignment: {_format_float(metrics['mode_alignment_pct'], 2)}%",
        ]
    )
    ax.text(
        0.03,
        0.97,
        annotation,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#9ca3af", alpha=0.92),
    )

    fig.tight_layout()
    fig.savefig(PLOT_PATH, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    python_df = _read_hourly_csv(PYTHON_HOURLY, "Python SIL hourly CSV")
    matlab_df = _read_hourly_csv(MATLAB_HOURLY, "MATLAB Simulink hourly CSV")

    merged = python_df.merge(matlab_df, on="hour_of_year", how="inner", suffixes=("_py", "_mat"))
    if len(merged) != 8760:
        _fail(f"aligned row count is {len(merged)}, expected 8760")

    if merged["hour_of_year"].duplicated().any():
        _fail("hour_of_year alignment produced duplicate rows")

    required_python_cols = ["effective_wind_speed_ms", "mean_tip_speed_ratio", "control_mode", "mean_electrical_power_kw"]
    required_matlab_cols = ["wind_speed_15m_ms", "tsr", "mode_id", "electrical_power_kw"]
    for col in required_python_cols:
        if col not in merged.columns:
            _fail(f"Python SIL output missing required column: {col}")
    for col in required_matlab_cols:
        if col not in merged.columns:
            _fail(f"MATLAB output missing required column: {col}")

    python_power_w = merged["mean_electrical_power_kw"].astype(float).to_numpy() * 1000.0
    matlab_power_w = merged["electrical_power_kw"].astype(float).to_numpy() * 1000.0
    power_diff_w = python_power_w - matlab_power_w
    abs_diff_w = np.abs(power_diff_w)

    rmse_w = float(np.sqrt(np.mean(np.square(power_diff_w))))
    matlab_nonzero_mask = np.abs(matlab_power_w) > 1e-9
    if np.any(matlab_nonzero_mask):
        mape_pct = float(np.mean(np.abs(power_diff_w[matlab_nonzero_mask]) / np.abs(matlab_power_w[matlab_nonzero_mask])) * 100.0)
    else:
        mape_pct = float("nan")
    pearson_r = float(np.corrcoef(python_power_w, matlab_power_w)[0, 1])

    python_mode = merged["control_mode"].map(_normalize_python_mode).to_numpy()
    matlab_mode = merged["mode_id"].map(_normalize_matlab_mode).to_numpy()
    mode_alignment_pct = float(np.mean(python_mode == matlab_mode) * 100.0)

    worst_table = _build_summary_table(
        merged.assign(
            python_power_kw=merged["mean_electrical_power_kw"].astype(float),
            matlab_power_kw=merged["electrical_power_kw"].astype(float),
        ),
        abs_diff_w,
    )

    metrics = {
        "rmse_w": rmse_w,
        "mape_pct": mape_pct,
        "pearson_r": pearson_r,
        "mode_alignment_pct": mode_alignment_pct,
    }

    _scatter_plot(python_power_w, matlab_power_w, metrics)

    zero_denominator_hours = int((~matlab_nonzero_mask).sum())
    summary_lines = [
        "Cross-validation summary",
        "========================",
        f"Python file: {PYTHON_HOURLY}",
        f"MATLAB file: {MATLAB_HOURLY}",
        "Alignment key: hour_of_year",
        f"Python rows: {len(python_df)}",
        f"MATLAB rows: {len(matlab_df)}",
        f"Aligned rows: {len(merged)}",
        "",
        "Power comparison (W):",
        f"  RMSE: {_format_float(rmse_w, 3)} W",
        f"  MAPE: {_format_float(mape_pct, 3)} % (computed against MATLAB power; {zero_denominator_hours} zero-power MATLAB hours excluded)",
        f"  Pearson correlation: {_format_float(pearson_r, 6)}",
        "",
        "Mode alignment:",
        f"  {mode_alignment_pct:.2f}% of hours match after normalizing adaptive_mppt -> mppt and MATLAB mode_id 3 -> mppt",
        "",
        "Worst 10 hours by absolute power difference:",
        worst_table.to_string(
            index=False,
            formatters={
                "datetime_py": lambda v: str(v),
                "abs_diff_w": lambda v: f"{v:.3f}",
                "python_power_w": lambda v: f"{v:.3f}",
                "matlab_power_w": lambda v: f"{v:.3f}",
                "python_wind_speed_ms": lambda v: f"{v:.3f}",
                "python_tsr": lambda v: f"{v:.3f}",
                "matlab_wind_speed_ms": lambda v: f"{v:.3f}",
                "matlab_tsr": lambda v: f"{v:.3f}",
            },
        ),
        "",
        f"Scatter plot saved to: {PLOT_PATH}",
    ]

    SUMMARY_PATH.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("\n".join(summary_lines))
    print("Cross-validation complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
