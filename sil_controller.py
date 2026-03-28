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
    SIL controller state machine for the CDO hybrid VAWT.

    States:
    - idle: below cut-in wind speed; the controller resets and commands no torque.
    - startup: rotor is accelerating but has not yet shown sustained usable TSR.
    - adaptive_mppt: the rotor has entered the low-loss operating band and the
      controller applies a softened torque law around TSR_OPT.
    - brake: overspeed or cut-out protection; generator torque is removed and the
      brake is applied.

    Transition logic:
    - idle -> startup when wind speed rises above CUT_IN_MS.
    - startup -> adaptive_mppt only after TSR >= 0.30 for 3 consecutive control
      timesteps. This hysteresis matches the CDO working range, where the rotor
      often hovers near the startup band before settling into harvestable TSR.
    - adaptive_mppt -> startup only after TSR < 0.20 for 3 consecutive timesteps.
      This prevents gust-driven chattering when the rotor briefly dips below the
      entry threshold and then recovers.
    - any state -> brake when wind speed exceeds CUT_OUT_MS or rotor overspeed
      protection is triggered.

    Threshold rationale:
    - The CDO site mean wind is 3.64 m/s and most hours sit in the 2.5-7 m/s
      working band, so the controller must avoid zero-torque dead bands in the
      0.2-0.3 TSR zone.
    - The 0.30/0.20 hysteresis band is intentionally narrow enough to preserve
      responsiveness while wide enough to suppress mode chatter.

    Known limitations:
    - This is still a SIL controller, not an embedded firmware implementation.
    - It does not model converter current limits, thermal derating, or blade
      pitch actuation.
    - The torque law remains simplified and should be replaced with hardware
      identification once generator and inverter data are available.
    """

    def __init__(self) -> None:
        self._max_rated_power_w = TURBINE_RATED_KW * 1000.0
        self._tsr_error_integral = 0.0
        self._last_torque_nm = 0.0
        self._current_mode = "startup"
        self._mode_hold_counter = 0

    def reset(self) -> None:
        self._tsr_error_integral = 0.0
        self._last_torque_nm = 0.0
        self._current_mode = "startup"
        self._mode_hold_counter = 0

    def command(self, sensors: ControllerSensors) -> ControllerCommand:
        wind_speed = float(sensors.wind_speed_ms)
        rotor_rpm = float(sensors.rotor_rpm)
        air_density = float(sensors.air_density_kgm3)
        omega = rotor_rpm * 2.0 * np.pi / 60.0
        tsr_measured = max(0.0, float(sensors.tip_speed_ratio))
        cp_measured = max(0.0, float(sensors.cp_effective))
        aero_torque_measured = max(0.0, float(sensors.aerodynamic_torque_nm))
        startup_rpm_handoff = 8.0
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

        if self._current_mode == "adaptive_mppt":
            if tsr_measured < 0.20:
                self._mode_hold_counter += 1
                if self._mode_hold_counter >= 3:
                    self._current_mode = "startup"
                    self._mode_hold_counter = 0
            else:
                self._mode_hold_counter = 0
        else:
            if tsr_measured >= 0.30:
                self._mode_hold_counter += 1
                if self._mode_hold_counter >= 3:
                    self._current_mode = "adaptive_mppt"
                    self._mode_hold_counter = 0
            else:
                self._mode_hold_counter = 0

        if self._current_mode == "startup" and tsr_measured < 0.20 and rotor_rpm < startup_rpm_handoff and cp_measured < startup_cp_floor:
            torque = 0.0
        else:
            torque = 0.65 * self._last_torque_nm + 0.35 * torque

        mode = self._current_mode

        self._last_torque_nm = float(torque)

        return ControllerCommand(generator_torque_nm=float(torque), brake_torque_nm=0.0, mode=mode)
