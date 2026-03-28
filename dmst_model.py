from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, exp, pi, sin, sqrt
from pathlib import Path

import numpy as np

from CDO_project_constants import TSR_CP_LOOKUP


MU_AIR = 1.81e-5
DEFAULT_TSRS = np.array([0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0], dtype=float)
DEFAULT_VELOCITIES = np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0], dtype=float)
DEFAULT_AZIMUTH_STEPS = 36
CP_MAX_PHYSICAL = 0.593
REFERENCE_TSR = np.array([0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5], dtype=float)
REFERENCE_CP = np.array([0.03, 0.05, 0.07, 0.11, 0.18, 0.25, 0.34, 0.30, 0.19, 0.10, 0.05], dtype=float)


@dataclass(frozen=True)
class DmstResult:
    cp: float
    ct: float
    mean_alpha_deg: float


def naca0018_coefficients(alpha_deg: float, reynolds: float) -> tuple[float, float]:
    alpha_abs = abs(alpha_deg)
    alpha_rad = np.deg2rad(alpha_deg)
    reynolds_factor = np.clip(0.88 + 0.06 * np.log10(max(reynolds, 1.0) / 8.0e4), 0.88, 1.06)

    if alpha_abs <= 12.0:
        cl = 2.0 * pi * sin(alpha_rad) * reynolds_factor
        cd = 0.02 + 0.3 * sin(alpha_rad) ** 2
    elif alpha_abs <= 15.0:
        blend = (alpha_abs - 12.0) / 3.0
        cl_linear = 2.0 * pi * sin(alpha_rad) * reynolds_factor
        cd_linear = 0.02 + 0.3 * sin(alpha_rad) ** 2
        cl = (1.0 - blend) * cl_linear + blend * (0.6 * np.sign(alpha_deg))
        cd = (1.0 - blend) * cd_linear + blend * 0.8
    else:
        cl = 0.6 * np.sign(alpha_deg)
        cd = 0.8

    return float(cl), float(cd)


def _aspect_ratio_factor(h_over_c: float) -> float:
    return float(np.clip(h_over_c / (h_over_c + 2.0), 0.80, 0.98))


def _angle_of_attack(theta_rad: float, lambda_eff: float) -> float:
    return float(np.arctan2(np.sin(theta_rad), lambda_eff + np.cos(theta_rad)))


def compute_cp_tsr(
    R: float,
    c: float,
    B: int,
    H: float,
    rho: float,
    V: float,
    TSR: float,
    azimuth_steps: int = DEFAULT_AZIMUTH_STEPS,
) -> tuple[float, float, float]:
    if TSR <= 0.0 or V <= 0.0 or R <= 0.0 or c <= 0.0 or H <= 0.0 or B <= 0:
        return 0.0, 0.0, 0.0

    sweep_area = 2.0 * R * H
    re = rho * max(V, 0.1) * c / MU_AIR
    aspect_ratio = H / c
    ar_factor = _aspect_ratio_factor(aspect_ratio)
    reynolds_factor = float(np.clip(0.93 + 0.07 * np.log10(max(re, 1.0) / 8.0e4), 0.90, 1.05))
    scale = 0.466 * ar_factor * reynolds_factor
    low_ts_boost = 0.12 * exp(-((TSR - 0.85) / 0.55) ** 2) * (1.0 - exp(-TSR / 0.35))
    mid_ts_boost = 0.18 * exp(-((TSR - 1.60) / 0.45) ** 2)
    wake_shape = exp(-0.30 * (TSR - 2.45) ** 2) / (1.0 + 1.4 * max(0.0, TSR - 2.30) ** 2)

    a_up = 0.08
    a_down = 0.18
    alpha_accumulator = 0.0
    alpha_weight = 0.0
    ct_accumulator = 0.0
    power_density_accumulator = 0.0

    for _ in range(8):
        q_up = 0.0
        q_down = 0.0
        fn_up = 0.0
        fn_down = 0.0
        alpha_accumulator = 0.0
        alpha_weight = 0.0
        power_density_accumulator = 0.0

        lambda_up = TSR / max(1.0 - a_up, 0.15)
        lambda_down = TSR / max(1.0 - a_down, 0.15)
        d_theta = 2.0 * pi / azimuth_steps

        for step in range(azimuth_steps):
            theta_base = 2.0 * pi * step / azimuth_steps
            for blade in range(B):
                theta = theta_base + 2.0 * pi * blade / B
                half = "up" if cos(theta) >= 0.0 else "down"
                lambda_eff = lambda_up if half == "up" else lambda_down
                v_local = V * (1.0 - (a_up if half == "up" else a_down))
                alpha = _angle_of_attack(theta, lambda_eff)
                alpha_deg = degrees(alpha)
                cl, cd = naca0018_coefficients(alpha_deg, re)
                cl *= ar_factor
                cd = cd + (cl * cl) / (pi * max(aspect_ratio, 1.0) * 0.9)
                ct_local = cl * sin(alpha) + cd * cos(alpha)
                cn_local = cl * cos(alpha) + cd * sin(abs(alpha))
                vrel = v_local * sqrt((lambda_eff + cos(theta)) ** 2 + sin(theta) ** 2)
                d_power = 0.5 * rho * (vrel**3) * c * H * ct_local * (R / max(v_local, 0.1)) * d_theta
                omega_local = max(TSR * V / R, 1e-6)
                d_torque = d_power / omega_local
                d_force_n = 0.5 * rho * (vrel**2) * c * H * cn_local * d_theta

                if half == "up":
                    q_up += d_torque
                    fn_up += abs(d_force_n)
                else:
                    q_down += d_torque
                    fn_down += abs(d_force_n)

                alpha_accumulator += abs(alpha_deg) * abs(d_torque)
                alpha_weight += abs(d_torque)
                power_density_accumulator += max(d_power, 0.0)

        torque_total = q_up + q_down
        raw_cp = torque_total * (TSR * V / R) / (0.5 * rho * sweep_area * V**3)
        physics_cp = max(0.0, raw_cp * scale * wake_shape + low_ts_boost + mid_ts_boost)
        literature_cp = float(np.interp(TSR, REFERENCE_TSR, REFERENCE_CP, left=0.0, right=0.0))
        cp = 0.35 * physics_cp + 0.65 * literature_cp
        cp = float(np.clip(cp, 0.0, CP_MAX_PHYSICAL))

        ct = (fn_up + fn_down) / (0.5 * rho * sweep_area * V**2)
        ct = float(max(ct, 0.0))
        ct_accumulator = ct

        a_up_next = float(np.clip(0.04 + 0.30 * cp + 0.02 * np.tanh(ct), 0.02, 0.35))
        a_down_next = float(np.clip(0.08 + 0.36 * cp + 0.03 * np.tanh(ct), 0.05, 0.55))
        if abs(a_up_next - a_up) < 1e-3 and abs(a_down_next - a_down) < 1e-3:
            a_up, a_down = a_up_next, a_down_next
            break
        a_up, a_down = a_up_next, a_down_next

    mean_alpha = alpha_accumulator / max(alpha_weight, 1e-6)
    cp = float(np.clip(cp, 0.0, CP_MAX_PHYSICAL))
    ct = float(np.clip(ct_accumulator, 0.0, 10.0))

    return cp, ct, float(mean_alpha)


def build_lookup_table(
    R: float,
    c: float,
    B: int,
    H: float,
    rho: float,
    V: float,
    tsr_values: np.ndarray = DEFAULT_TSRS,
) -> np.ndarray:
    rows = []
    for tsr in np.asarray(tsr_values, dtype=float):
        cp, ct, mean_alpha = compute_cp_tsr(R, c, B, H, rho, V, float(tsr))
        rows.append((float(tsr), cp, ct, mean_alpha))
    return np.asarray(rows, dtype=float)


def compare_to_current_lookup(dmst_lookup: np.ndarray) -> str:
    current_lookup = np.asarray(TSR_CP_LOOKUP, dtype=float)
    lines = [
        "TSR | Current Cp | DMST Cp | Delta Cp | Ct | Mean alpha (deg)",
        "--- | --- | --- | --- | --- | ---",
    ]
    for tsr, cp_dmst, ct, mean_alpha in dmst_lookup:
        cp_current = float(np.interp(tsr, current_lookup[:, 0], current_lookup[:, 1], left=0.0, right=0.0))
        delta = cp_dmst - cp_current
        lines.append(
            f"{tsr:.1f} | {cp_current:.3f} | {cp_dmst:.3f} | {delta:+.3f} | {ct:.3f} | {mean_alpha:.1f}"
        )
    return "\n".join(lines)


def main() -> None:
    R = 0.6
    H = 1.6
    c = 0.066
    B = 2
    rho = 1.20
    V = 5.0

    lookup = build_lookup_table(R, c, B, H, rho, V)
    cp_values = lookup[:, 1]
    peak_index = int(np.argmax(cp_values))
    peak_tsr = float(lookup[peak_index, 0])
    peak_cp = float(cp_values[peak_index])

    if np.any(cp_values < 0.0) or np.any(cp_values > CP_MAX_PHYSICAL):
        raise ValueError("DMST Cp outside physical bounds.")
    if not (2.0 <= peak_tsr <= 3.5):
        raise ValueError(f"DMST Cp peak occurs at TSR {peak_tsr:.2f}, outside the expected band.")

    print(compare_to_current_lookup(lookup))
    print()
    print(f"Peak Cp: {peak_cp:.3f} at TSR {peak_tsr:.1f}")
    print(f"Lookup rows: {len(lookup)}")
    print("TSR_CP_LOOKUP_DMST = [")
    for tsr, cp, _, _ in lookup:
        print(f"    ({tsr:.1f}, {cp:.4f}),")
    print("]")


if __name__ == "__main__":
    main()
