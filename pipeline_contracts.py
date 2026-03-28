from __future__ import annotations

from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent

PYTHON_OUTPUTS = [
    "CDO_sil_run_2023_hourly.csv",
    "CDO_sil_run_2023_summary.txt",
    "yield_uncertainty_results.json",
    "validation_report.txt",
]

MATLAB_INPUTS = PYTHON_OUTPUTS

MATLAB_OUTPUTS = [
    "matlab_validation_summary.csv",
    "matlab_cp_tsr_comparison.csv",
    "matlab_sil_summary.mat",
]

UNITY_INPUTS = PYTHON_OUTPUTS + MATLAB_OUTPUTS

STREAMING_ASSETS_PATH = REPO_ROOT / "UnityVAWT" / "Assets" / "StreamingAssets"


def _resolve_root_path(file_name: str) -> Path:
    return REPO_ROOT / file_name


def resolve_source_path(file_name: str) -> Path:
    """
    Resolve a contract file for downstream copying.

    The canonical path is the repository root. For backward compatibility,
    MATLAB outputs are also accepted from matlab_design_outputs/ if a root copy
    does not yet exist.
    """

    root_path = _resolve_root_path(file_name)
    if root_path.exists():
        return root_path

    legacy_path = REPO_ROOT / "matlab_design_outputs" / file_name
    if legacy_path.exists():
        return legacy_path

    return root_path


def validate_contracts(expected_files: Iterable[str] | None = None) -> bool:
    """
    Check that a contract file set exists at the repository root.

    Returns True when every file is present, otherwise False.
    """

    files = list(expected_files if expected_files is not None else (PYTHON_OUTPUTS + MATLAB_OUTPUTS))
    all_present = True
    print("Validating pipeline contracts:")
    for file_name in files:
        path = _resolve_root_path(file_name)
        if path.exists():
            print(f"  [PASS] {file_name}")
        else:
            print(f"  [FAIL] {file_name}")
            all_present = False
    print("Contract validation:", "PASS" if all_present else "FAIL")
    return all_present
