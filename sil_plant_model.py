from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from CDO_project_constants import (
    CP_GENERIC,
    DRIVETRAIN_DAMPING_NMS,
    GENERATOR_EFFICIENCY,
    MAX_ROTOR_RPM,
    ROTOR_INERTIA_KGM2,
    ROTOR_RADIUS_M,
    STARTUP_TORQUE_COEFF,
    SWEPT_AREA_M2,
    TSR_OPT,
    TSR_SPREAD,
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


def cp_curve(tsr: float) -> float:
    deviation = (tsr - TSR_OPT) / TSR_SPREAD
    return float(max(0.0, CP_GENERIC * (1.0 - deviation * deviation)))


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
    ) -> PlantOutputs:
        omega = float(state.omega_rad_s)
        wind_speed = max(float(wind_speed_ms), 0.1)
        rho = float(air_density_kgm3)

        tsr = omega * ROTOR_RADIUS_M / wind_speed if wind_speed > 0.0 else 0.0
        cp = cp_curve(tsr)

        # Prevent singular startup torque when omega is near zero.
        omega_aero = max(omega, 0.3, 0.25 * TSR_OPT * wind_speed / max(ROTOR_RADIUS_M, 1e-6))
        aerodynamic_power_w = 0.5 * rho * SWEPT_AREA_M2 * cp * (wind_speed**3)
        startup_torque_nm = 0.5 * rho * SWEPT_AREA_M2 * STARTUP_TORQUE_COEFF * (wind_speed**2) * ROTOR_RADIUS_M
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
        )
