from __future__ import annotations

from pathlib import Path

import numpy as np

from dmst_model import build_lookup_table


REPORT_PATH = Path("validation_report.txt")

R = 0.6
H = 1.6
c = 0.066
B = 2
rho = 1.20
V = 5.0

PAPERS = {
    "Irawan et al. 2023": {
        "tsr": np.array([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5], dtype=float),
        "cp": np.array([0.05, 0.10, 0.18, 0.25, 0.33, 0.26, 0.10], dtype=float),
    },
    "Hosseini & Goudarzi 2019": {
        "tsr": np.array([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5], dtype=float),
        "cp": np.array([0.12, 0.22, 0.30, 0.40, 0.38, 0.28, 0.15, 0.05], dtype=float),
    },
    "Puspitasari & Sahim 2019": {
        "tsr": np.array([0.5, 0.7, 1.0, 1.5, 2.0], dtype=float),
        "cp": np.array([0.04, 0.07, 0.10, 0.14, 0.18], dtype=float),
    },
}


def main() -> None:
    lookup = build_lookup_table(R, c, B, H, rho, V)
    tsr_grid = lookup[:, 0]
    cp_grid = lookup[:, 1]

    report_lines = []
    average_percent_errors = []
    worst_point = (None, None, -1.0)

    for paper_name, data in PAPERS.items():
        report_lines.append(f"=== {paper_name} ===")
        report_lines.append("TSR | Published Cp | DMST Cp | Error | % Error | Flag")

        errors = []
        percent_errors = []
        for tsr, published in zip(data["tsr"], data["cp"]):
            dmst_cp = float(np.interp(tsr, tsr_grid, cp_grid, left=0.0, right=0.0))
            error = abs(dmst_cp - published)
            percent_error = 100.0 * error / max(published, 1e-6)
            flag = "HIGH_DEVIATION" if percent_error > 30.0 else "-"
            report_lines.append(
                f"{tsr:.2f} | {published:.3f} | {dmst_cp:.3f} | {error:.3f} | {percent_error:.1f}% | {flag}"
            )
            errors.append(error)
            percent_errors.append(percent_error)
            if percent_error > worst_point[2]:
                worst_point = (paper_name, tsr, percent_error)

        rmse = float(np.sqrt(np.mean(np.square(errors))))
        mean_pct = float(np.mean(percent_errors))
        average_percent_errors.append(mean_pct)
        report_lines.append(f"RMSE: {rmse:.4f}")
        report_lines.append(f"Mean % error: {mean_pct:.2f}%")
        report_lines.append("")

    overall_mean = float(np.mean(average_percent_errors))
    report_lines.append(
        f"DMST model agrees within {overall_mean:.1f}% of literature on average. "
        f"Largest deviation at TSR {worst_point[1]:.2f} ({worst_point[2]:.1f}%). "
        "Config differences: the simplified DMST surrogate does not fully capture blade-to-blade wake "
        "interaction, exact dynamic stall timing, or the published test-section blockage and support losses."
    )

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("\n".join(report_lines))


if __name__ == "__main__":
    main()
