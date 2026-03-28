from __future__ import annotations

import shutil
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


def main() -> int:
    status = "PASS"
    unity_copied = 0
    python_ok = False
    matlab_ok = False
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
        except Exception as exc:
            print(f"MATLAB stage failed: {exc}")
            return 1

    print("Step 3: Unity StreamingAssets sync")
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

    print("Pipeline complete.")
    print(f"Python SIL:  {annual_yield_kwh:.2f} kWh/yr  [from CDO_sil_run_2023_summary.txt]")
    print(f"MATLAB delta: {matlab_delta_text}            [from matlab_validation_summary.csv]")
    print(f"Unity sync:  {unity_copied} files copied")
    print(f"Status: {status}")

    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
