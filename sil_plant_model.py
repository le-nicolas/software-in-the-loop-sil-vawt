from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from CDO_project_constants import (
    DRIVETRAIN_DAMPING_NMS,
    GENERATOR_EFFICIENCY,
    MAX_ROTOR_RPM,
    ROTOR_INERTIA_KGM2,
    ROTOR_RADIUS_M,
    STARTUP_TORQUE_COEFF,
    SWEPT_AREA_M2,
    TSR_OPT,
    TSR_CP_LOOKUP_DMST,
    TURBINE_RATED_KW,
)
from sil_controller import ControllerCommand


@dataclass(frozen=True)
class PlantState:
    omega_rad_s: float

    @property
    def rotor_rpm(self) -> float:
        return self.omega_rad_s * 60.0 / (2.0 * np.pi)


@dataclass(frozen=True)
class PlantOutputs:
    state: PlantState
    aerodynamic_torque_nm: float
    electrical_power_kw: float
    tip_speed_ratio: float
    cp_effective: float
    upwind_face_speed_ms: float
    downwind_face_speed_ms: float
    azimuthal_speed_std_ms: float
    spatial_asymmetry_index: float

TSR_CP_LOOKUP = np.array(TSR_CP_LOOKUP_DMST, dtype=float)


def cp_curve(tsr: float) -> float:
    tsr_array = np.asarray(tsr, dtype=float)
    cp = np.interp(tsr_array, TSR_CP_LOOKUP[:, 0], TSR_CP_LOOKUP[:, 1], left=0.0, right=0.0)
    if np.ndim(cp) == 0:
        return float(cp)
    return cp


class SimpleVAWTPlant:
    """
    Minimal dynamic VAWT plant model for early SIL use.

    It captures inertia, aerodynamic torque, generator loading, damping, and a
    hard power cap. It is intentionally simple but stateful.
    """

    def __init__(self) -> None:
        self._rated_power_kw = TURBINE_RATED_KW
        self._omega_limit = MAX_ROTOR_RPM * 2.0 * np.pi / 60.0

    def initial_state(self) -> PlantState:
        return PlantState(omega_rad_s=0.0)

    def step(
        self,
        state: PlantState,
        wind_speed_ms: float,
        air_density_kgm3: float,
        command: ControllerCommand,
        dt_seconds: float,
        inflow_direction_deg: float | None = None,
        ring_speed_ms: np.ndarray | None = None,
        ring_direction_deg: np.ndarray | None = None,
        ring_density_kgm3: np.ndarray | None = None,
        ring_phi_rad: np.ndarray | None = None,
    ) -> PlantOutputs:
        omega = float(state.omega_rad_s)
        wind_speed = max(float(wind_speed_ms), 0.1)
        rho = float(air_density_kgm3)

        tsr = omega * ROTOR_RADIUS_M / wind_speed if wind_speed > 0.0 else 0.0
        cp = cp_curve(tsr)

        upwind_face_speed_ms = wind_speed
        downwind_face_speed_ms = wind_speed
        azimuthal_speed_std_ms = 0.0
        spatial_asymmetry_index = 0.0

        if ring_speed_ms is not None and len(ring_speed_ms) > 0:
            local_speed = np.clip(np.asarray(ring_speed_ms, dtype=float), 0.1, None)
            local_phi = np.asarray(ring_phi_rad, dtype=float)
            if ring_density_kgm3 is None:
                local_density = np.full_like(local_speed, rho)
            else:
                local_density = np.asarray(ring_density_kgm3, dtype=float)
            if ring_direction_deg is None:
                local_theta = np.full_like(local_speed, np.deg2rad(float(inflow_direction_deg or 0.0)))
            else:
                local_theta = np.deg2rad(np.asarray(ring_direction_deg, dtype=float))

            wind_hat_x = np.sin(local_theta)
            wind_hat_y = np.cos(local_theta)
            radial_x = np.cos(local_phi)
            radial_y = np.sin(local_phi)
            upwind_exposure = -(wind_hat_x * radial_x + wind_hat_y * radial_y)
            upwind_mask = upwind_exposure >= 0.0
            downwind_mask = ~upwind_mask

            if np.any(upwind_mask):
                upwind_face_speed_ms = float(np.mean(local_speed[upwind_mask]))
            if np.any(downwind_mask):
                downwind_face_speed_ms = float(np.mean(local_speed[downwind_mask]))

            azimuthal_speed_std_ms = float(np.std(local_speed))
            spatial_asymmetry_index = float(
                (upwind_face_speed_ms - downwind_face_speed_ms) / max(float(np.mean(local_speed)), 0.1)
            )

            local_tsr = omega * ROTOR_RADIUS_M / np.maximum(local_speed, 0.1)
            local_cp = np.asarray(cp_curve(local_tsr), dtype=float)
            capture_weight = 0.55 + 0.45 * np.maximum(upwind_exposure, 0.0)
            capture_weight = capture_weight / max(float(np.mean(capture_weight)), 1e-6)
            sector_area = SWEPT_AREA_M2 / max(len(local_speed), 1)
            aerodynamic_power_w = float(
                np.sum(0.5 * local_density * sector_area * local_cp * (local_speed**3) * capture_weight)
            )
            startup_torque_nm = float(
                0.5
                * np.mean(local_density * (local_speed**2))
                * SWEPT_AREA_M2
                * STARTUP_TORQUE_COEFF
                * ROTOR_RADIUS_M
                * (1.0 + 0.4 * max(spatial_asymmetry_index, 0.0))
            )
        else:
            aerodynamic_power_w = 0.5 * rho * SWEPT_AREA_M2 * cp * (wind_speed**3)
            startup_torque_nm = 0.5 * rho * SWEPT_AREA_M2 * STARTUP_TORQUE_COEFF * (wind_speed**2) * ROTOR_RADIUS_M

        # Prevent singular startup torque when omega is near zero.
        omega_aero = max(omega, 0.3, 0.25 * TSR_OPT * wind_speed / max(ROTOR_RADIUS_M, 1e-6))
        aerodynamic_torque_nm = max(aerodynamic_power_w / omega_aero, startup_torque_nm)

        net_torque = (
            aerodynamic_torque_nm
            - float(command.generator_torque_nm)
            - float(command.brake_torque_nm)
            - DRIVETRAIN_DAMPING_NMS * omega
        )
        omega_next = max(0.0, omega + (net_torque / ROTOR_INERTIA_KGM2) * dt_seconds)
        omega_next = min(omega_next, self._omega_limit)

        electrical_power_kw = min(
            self._rated_power_kw,
            max(0.0, float(command.generator_torque_nm) * omega_next * GENERATOR_EFFICIENCY / 1000.0),
        )

        next_state = PlantState(omega_rad_s=omega_next)
        next_tsr = omega_next * ROTOR_RADIUS_M / wind_speed if wind_speed > 0.0 else 0.0
        next_cp = cp_curve(next_tsr)
        return PlantOutputs(
            state=next_state,
            aerodynamic_torque_nm=float(aerodynamic_torque_nm),
            electrical_power_kw=float(electrical_power_kw),
            tip_speed_ratio=float(next_tsr),
            cp_effective=float(next_cp),
            upwind_face_speed_ms=float(upwind_face_speed_ms),
            downwind_face_speed_ms=float(downwind_face_speed_ms),
            azimuthal_speed_std_ms=float(azimuthal_speed_std_ms),
            spatial_asymmetry_index=float(spatial_asymmetry_index),
        )
