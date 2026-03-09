from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from CDO_project_constants import (
    BRAKE_TORQUE_NM,
    CP_GENERIC,
    CUT_IN_MS,
    CUT_OUT_MS,
    GENERATOR_EFFICIENCY,
    MAX_ROTOR_RPM,
    ROTOR_RADIUS_M,
    SWEPT_AREA_M2,
    TSR_OPT,
    TURBINE_RATED_KW,
)


@dataclass(frozen=True)
class ControllerSensors:
    wind_speed_ms: float
    rotor_rpm: float
    air_density_kgm3: float


@dataclass(frozen=True)
class ControllerCommand:
    generator_torque_nm: float
    brake_torque_nm: float
    mode: str


class SimpleVAWTController:
    """
    Minimal SIL controller scaffold.

    This is not production control software. It provides a non-trivial closed-loop
    decision layer so plant and wind forcing can be exercised end-to-end.
    """

    def __init__(self) -> None:
        self._max_rated_power_w = TURBINE_RATED_KW * 1000.0

    def command(self, sensors: ControllerSensors) -> ControllerCommand:
        wind_speed = float(sensors.wind_speed_ms)
        rotor_rpm = float(sensors.rotor_rpm)
        air_density = float(sensors.air_density_kgm3)
        omega = rotor_rpm * 2.0 * np.pi / 60.0

        if wind_speed < CUT_IN_MS:
            return ControllerCommand(generator_torque_nm=0.0, brake_torque_nm=0.0, mode="idle")

        if wind_speed >= CUT_OUT_MS or rotor_rpm >= MAX_ROTOR_RPM:
            return ControllerCommand(generator_torque_nm=0.0, brake_torque_nm=BRAKE_TORQUE_NM, mode="brake")

        # MPPT-style torque law: T = K * omega^2 with power cap at rated output.
        k_mppt = 0.5 * air_density * SWEPT_AREA_M2 * CP_GENERIC * (ROTOR_RADIUS_M**3) / (TSR_OPT**3)
        torque = k_mppt * (omega**2)

        if omega > 0.1:
            rated_torque = self._max_rated_power_w / max(omega * GENERATOR_EFFICIENCY, 1e-6)
            torque = min(torque, rated_torque)

        # Give startup some assist by keeping generator unloaded at very low speed.
        if rotor_rpm < 20.0:
            torque = 0.0
            mode = "startup"
        else:
            mode = "mppt"

        return ControllerCommand(generator_torque_nm=float(torque), brake_torque_nm=0.0, mode=mode)
