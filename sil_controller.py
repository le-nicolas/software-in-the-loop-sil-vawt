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
    tip_speed_ratio: float = 0.0
    cp_effective: float = 0.0
    aerodynamic_torque_nm: float = 0.0


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
        self._tsr_error_integral = 0.0
        self._last_torque_nm = 0.0

    def reset(self) -> None:
        self._tsr_error_integral = 0.0
        self._last_torque_nm = 0.0

    def command(self, sensors: ControllerSensors) -> ControllerCommand:
        wind_speed = float(sensors.wind_speed_ms)
        rotor_rpm = float(sensors.rotor_rpm)
        air_density = float(sensors.air_density_kgm3)
        omega = rotor_rpm * 2.0 * np.pi / 60.0
        tsr_measured = max(0.0, float(sensors.tip_speed_ratio))
        cp_measured = max(0.0, float(sensors.cp_effective))
        aero_torque_measured = max(0.0, float(sensors.aerodynamic_torque_nm))
        startup_rpm_handoff = 8.0
        startup_tsr_handoff = 0.25
        startup_cp_floor = 0.02
        brake_tsr_trigger = max(TSR_OPT + 0.75, 3.25)

        if wind_speed < CUT_IN_MS:
            self.reset()
            return ControllerCommand(generator_torque_nm=0.0, brake_torque_nm=0.0, mode="idle")

        if wind_speed >= CUT_OUT_MS or (rotor_rpm >= MAX_ROTOR_RPM and tsr_measured >= brake_tsr_trigger):
            self.reset()
            return ControllerCommand(generator_torque_nm=0.0, brake_torque_nm=BRAKE_TORQUE_NM, mode="brake")

        target_omega = TSR_OPT * wind_speed / max(ROTOR_RADIUS_M, 1e-6)
        target_tsr = target_omega * ROTOR_RADIUS_M / max(wind_speed, 0.1)
        tsr_error = tsr_measured - target_tsr
        self._tsr_error_integral = float(np.clip(self._tsr_error_integral + tsr_error * 60.0, -200.0, 200.0))

        # Use the actual plant Cp feedback and measured aerodynamic torque, not a fixed
        # pre-tuned quadratic law. The controller unloads when TSR is below target and
        # increases generator torque only when the rotor outruns the target regime.
        cp_feedback = max(cp_measured, 0.12 * CP_GENERIC)
        available_power_w = 0.5 * air_density * SWEPT_AREA_M2 * cp_feedback * (wind_speed**3)
        reference_omega = max(target_omega, 0.35)
        torque_from_cp = available_power_w / reference_omega

        if aero_torque_measured > 0.0:
            base_torque = 0.55 * torque_from_cp + 0.45 * aero_torque_measured
        else:
            base_torque = torque_from_cp

        torque_feedback = 0.85 * tsr_error + 0.012 * self._tsr_error_integral
        torque = max(0.0, base_torque + torque_feedback)

        if omega > 0.1:
            rated_torque = self._max_rated_power_w / max(omega * GENERATOR_EFFICIENCY, 1e-6)
            torque = min(torque, rated_torque)

        # Hand off to MPPT as soon as the rotor shows useful low-TSR capture.
        if rotor_rpm < startup_rpm_handoff and tsr_measured < startup_tsr_handoff and cp_measured < startup_cp_floor:
            torque = 0.0
            mode = "startup"
        else:
            torque = 0.65 * self._last_torque_nm + 0.35 * torque
            mode = "adaptive_mppt"

        self._last_torque_nm = float(torque)

        return ControllerCommand(generator_torque_nm=float(torque), brake_torque_nm=0.0, mode=mode)
