from __future__ import annotations

import shutil
import re
import subprocess
import sys

import pandas as pd

from pipeline_contracts import MATLAB_OUTPUTS, PYTHON_OUTPUTS, REPO_ROOT, STREAMING_ASSETS_PATH, validate_contracts
from sync_to_unity import sync_to_unity


def _run_command(command: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    if result.returncode != 0 and not allow_failure:
        raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
    return result


def _read_python_summary() -> float:
    summary_path = REPO_ROOT / "CDO_sil_run_2023_summary.txt"
    text = summary_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("Final annual kWh:"):
            return float(line.split(":", 1)[1].strip())
    raise ValueError("Could not parse annual yield from CDO_sil_run_2023_summary.txt")


def _read_matlab_delta() -> float | None:
    validation_path = REPO_ROOT / "matlab_validation_summary.csv"
    if not validation_path.exists():
        return None
    df = pd.read_csv(validation_path)
    row = df.loc[df["metric"] == "annual_yield_kwh"]
    if row.empty:
        return None
    return float(row.iloc[0]["delta_pct"])


def _read_cross_validation_summary() -> dict[str, float] | None:
    summary_path = REPO_ROOT / "cross_validation_summary.txt"
    if not summary_path.exists():
        return None

    text = summary_path.read_text(encoding="utf-8")

    def _match(pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.MULTILINE)
        if not match:
            return None
        return float(match.group(1))

    rmse = _match(r"RMSE:\s*([0-9.]+)\s*W")
    pearson = _match(r"Pearson correlation:\s*([0-9.]+)")
    mode_alignment = _match(r"Mode alignment:\s*([0-9.]+)%")

    if rmse is None and pearson is None and mode_alignment is None:
        return None
    return {
        "rmse_w": rmse if rmse is not None else float("nan"),
        "pearson_r": pearson if pearson is not None else float("nan"),
        "mode_alignment_pct": mode_alignment if mode_alignment is not None else float("nan"),
    }


def main() -> int:
    status = "PASS"
    unity_copied = 0
    python_ok = False
    matlab_ok = False
    cross_validation_ok = False
    unity_ok = False

    print("Step 1: Python SIL and validation")
    try:
        _run_command([sys.executable, "run_sil_simulation.py"])
        _run_command([sys.executable, "yield_uncertainty.py"])
        _run_command([sys.executable, "validate_against_literature.py"])
        python_ok = validate_contracts(PYTHON_OUTPUTS)
        if not python_ok:
            status = "FAIL"
            return 1
    except Exception as exc:
        print(f"Python SIL stage failed: {exc}")
        return 1

    matlab_cmd = shutil.which("matlab")
    if matlab_cmd is None:
        print("Warning: MATLAB not found on PATH, skipping MATLAB batch step.")
        status = "PARTIAL"
    else:
        print("Step 2: MATLAB batch validation")
        try:
            _run_command([matlab_cmd, "-batch", "run_cdo_vawt_matlab_pipeline"])
            matlab_ok = validate_contracts(MATLAB_OUTPUTS)
            if not matlab_ok:
                status = "FAIL"
                return 1
            print("Step 3: Hourly cross-validation")
            _run_command([sys.executable, "cross_validate_hourly.py"])
            cross_validation_ok = True
        except Exception as exc:
            print(f"MATLAB / cross-validation stage failed: {exc}")
            return 1

    print("Step 4: Unity StreamingAssets sync")
    if STREAMING_ASSETS_PATH.exists():
        try:
            unity_copied, _ = sync_to_unity()
            unity_ok = True
        except Exception as exc:
            print(f"Unity sync failed: {exc}")
            status = "PARTIAL" if status == "PASS" else status
    else:
        print(f"Warning: Unity StreamingAssets path not found, skipping sync: {STREAMING_ASSETS_PATH}")
        status = "PARTIAL" if status == "PASS" else status

    annual_yield_kwh = _read_python_summary()
    matlab_delta = _read_matlab_delta()
    if matlab_delta is None:
        status = "PARTIAL" if status == "PASS" else status
        matlab_delta_text = "n/a"
    else:
        matlab_delta_text = f"{matlab_delta:.2f}%"

    if not matlab_ok and matlab_cmd is not None:
        status = "FAIL"
    elif not python_ok:
        status = "FAIL"
    elif not unity_ok:
        status = "PARTIAL" if status == "PASS" else status

    cross_validation = _read_cross_validation_summary()

    print("Pipeline complete.")
    print(f"Python SIL:  {annual_yield_kwh:.2f} kWh/yr  [from CDO_sil_run_2023_summary.txt]")
    print(f"MATLAB delta: {matlab_delta_text}            [from matlab_validation_summary.csv]")
    if cross_validation is not None:
        print(
            "Cross-validation: "
            f"{cross_validation['rmse_w']:.2f} W RMSE, "
            f"{cross_validation['pearson_r']:.3f} correlation, "
            f"{cross_validation['mode_alignment_pct']:.2f}% mode match"
        )
    print(f"Unity sync:  {unity_copied} files copied")
    print(f"Status: {status}")

    if matlab_cmd is not None and not cross_validation_ok:
        return 1
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
