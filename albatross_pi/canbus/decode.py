"""Frame decoding and state aggregation for CAN telemetry."""
from __future__ import annotations

import struct
from dataclasses import replace
from datetime import datetime
from threading import Condition, Lock
from typing import Callable, Dict, Optional

from .ids import (
    ArduinoToHudID,
    ECUToHudID,
    MODE_NAMES,
    PiToArduinoID,
    SystemCommandID,
)
from ..state.snapshot import (
    AirShotState,
    EngineState,
    EnvironmentState,
    StateSnapshot,
    TemperaturesState,
    TractionState,
    WMIState,
)


def _c_to_f(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0


class CANStateAggregator:
    """Maintains the latest HUD snapshot derived from CAN frames."""

    def __init__(self, rpm_redline: int = 12000) -> None:
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._engine_data: Dict[str, float | int | str] = {
            "rpm": 0,
            "rpm_redline": rpm_redline,
            "speed_mph": 0.0,
            "gear": "N",
            "boost_psi": 0.0,
            "target_boost_psi": 0.0,
            "wastegate_duty_pct": 0.0,
            "afr_left": 0.0,
            "afr_right": 0.0,
            "spark_advance_deg": 0.0,
            "knock_events": 0,
            "throttle_pct": 0.0,
            "engine_load_pct": 0.0,
        }
        self._temps_data: Dict[str, float] = {
            "coolant_temp_f": 0.0,
            "oil_temp_f": 0.0,
            "oil_pressure_psi": 0.0,
            "battery_voltage": 12.5,
            "intake_temp_f": 0.0,
            "exhaust_temp_f": 0.0,
            "alternator_temp_f": 0.0,
        }
        self._airshot = AirShotState()
        self._wmi = WMIState()
        self._traction = TractionState()
        self._environment = EnvironmentState()
        self._faults: Dict[int, str] = {}
        self._shift_light = False
        self._last_snapshot = StateSnapshot(
            engine=replace(EngineState(), rpm_redline=rpm_redline),
        )
        self._dirty = False
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def apply_frame(self, arbitration_id: int, data: bytes) -> None:
        """Decode the provided frame and update internal state."""
        handler = _FRAME_DISPATCH.get(arbitration_id)
        if handler is None:
            return
        with self._condition:
            handler(self, data)
            env_dict = self._environment.__dict__.copy()
            env_dict["time"] = datetime.now()
            self._environment = EnvironmentState(**env_dict)
            self._shift_light = self._engine_data.get("rpm", 0) >= 10000
            self._last_snapshot = StateSnapshot(
                engine=EngineState(**self._engine_data),
                temps=TemperaturesState(
                    coolant_temp_f=self._temps_data.get("coolant_temp_f", 0.0),
                    oil_temp_f=self._temps_data.get("oil_temp_f", 0.0),
                    oil_pressure_psi=self._temps_data.get("oil_pressure_psi", 0.0),
                    battery_voltage=self._temps_data.get("battery_voltage", 12.5),
                    intake_temp_f=self._temps_data.get("intake_temp_f", 0.0),
                    exhaust_temp_f=self._temps_data.get("exhaust_temp_f", 0.0),
                    alternator_temp_f=self._temps_data.get("alternator_temp_f", 0.0),
                ),
                air_shot=self._airshot,
                wmi=self._wmi,
                traction=self._traction,
                environment=self._environment,
                shift_light=self._shift_light,
                faults=tuple(sorted(self._faults.values())),
            )
            self._dirty = True
            self._condition.notify_all()

    def mark_sent_frame(self, arbitration_id: int, data: bytes) -> None:
        """Apply locally transmitted frames to keep state in sync."""
        self.apply_frame(arbitration_id, data)

    def wait_for_snapshot(self, timeout: Optional[float] = None) -> StateSnapshot:
        with self._condition:
            if not self._dirty:
                self._condition.wait(timeout)
            self._dirty = False
            return self._last_snapshot

    def current_snapshot(self) -> StateSnapshot:
        with self._lock:
            return self._last_snapshot
    # ------------------------------------------------------------------
    # Frame handlers
    # ------------------------------------------------------------------
    def _update_engine_rpm(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (rpm,) = struct.unpack_from(">H", data)
        self._engine_data["rpm"] = rpm

    def _update_throttle(self, data: bytes) -> None:
        if not data:
            return
        self._engine_data["throttle_pct"] = min(100.0, data[0])

    def _update_boost(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (raw_boost,) = struct.unpack_from(">H", data)
        self._engine_data["boost_psi"] = raw_boost / 10.0

    def _update_afr(self, data: bytes) -> None:
        if len(data) < 4:
            return
        left, right = struct.unpack_from(">HH", data)
        self._engine_data["afr_left"] = left / 100.0
        self._engine_data["afr_right"] = right / 100.0

    def _update_knock(self, data: bytes) -> None:
        if not data:
            return
        flags = int.from_bytes(data[: min(len(data), 2)], "big")
        self._engine_data["knock_events"] = int(bin(flags).count("1"))

    def _update_oil(self, data: bytes) -> None:
        if len(data) < 4:
            return
        pressure_raw, temp_raw = struct.unpack_from(">HH", data)
        self._temps_data["oil_pressure_psi"] = pressure_raw / 10.0
        self._temps_data["oil_temp_f"] = _c_to_f(temp_raw / 10.0)

    def _update_coolant(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (temp_raw,) = struct.unpack_from(">H", data)
        self._temps_data["coolant_temp_f"] = _c_to_f(temp_raw / 10.0)

    def _update_fuel(self, data: bytes) -> None:
        if not data:
            return
        level = data[0]
        env_dict = self._environment.__dict__.copy()
        env_dict["fuel_level_pct"] = level
        self._environment = EnvironmentState(**env_dict)

    def _update_gear(self, data: bytes) -> None:
        if not data:
            return
        gear_code = data[0]
        gear_map = {0: "N", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6"}
        self._engine_data["gear"] = gear_map.get(gear_code, "?")

    def _update_engine_load(self, data: bytes) -> None:
        if not data:
            return
        self._engine_data["engine_load_pct"] = min(100.0, data[0])

    def _update_intake_temp(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (temp_raw,) = struct.unpack_from(">H", data)
        self._temps_data["intake_temp_f"] = _c_to_f(temp_raw / 10.0)

    def _update_exhaust_temp(self, data: bytes) -> None:
        if len(data) < 4:
            return
        bank1, bank2 = struct.unpack_from(">HH", data[:4])
        average = (bank1 + bank2) / 20.0
        self._temps_data["exhaust_temp_f"] = _c_to_f(average)

    def _update_air_shot_status(self, data: bytes) -> None:
        if not data:
            return
        charges = data[0]
        is_firing = False
        if len(data) > 1:
            is_firing = bool(data[1] & 0x01)
        self._airshot = replace(
            self._airshot,
            charges_remaining=charges,
            is_firing=is_firing,
        )

    def _update_awc_state(self, data: bytes) -> None:
        if not data:
            return
        active = bool(data[0])
        lean_deg = 0.0
        if len(data) >= 3:
            (lean_raw,) = struct.unpack_from(">h", data, 1)
            lean_deg = lean_raw / 10.0
        self._traction = replace(
            self._traction,
            intervention_level="ON" if active else "OFF",
            wheelie_pitch_deg=lean_deg,
            slip_pct=self._traction.slip_pct if active else 0.0,
        )

    def _update_tank_pressure(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (pressure_raw,) = struct.unpack_from(">H", data)
        self._airshot = replace(
            self._airshot,
            pressure_psi=pressure_raw / 10.0,
        )

    def _update_twin_turbo(self, data: bytes) -> None:
        if len(data) < 4:
            return
        turbo1, turbo2 = struct.unpack_from(">HH", data[:4])
        average = (turbo1 + turbo2) / 20.0
        self._engine_data["target_boost_psi"] = average

    def _update_wastegate_status(self, data: bytes) -> None:
        if len(data) < 2:
            return
        duty1, duty2 = data[0], data[1]
        self._engine_data["wastegate_duty_pct"] = (duty1 + duty2) / 2.0

    def _update_boost_command(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (raw_target,) = struct.unpack_from(">H", data)
        self._engine_data["target_boost_psi"] = raw_target / 10.0

    def _update_mode_selection(self, data: bytes) -> None:
        if not data:
            return
        mode_code = data[0]
        env_dict = self._environment.__dict__.copy()
        env_dict["mode"] = MODE_NAMES.get(mode_code, env_dict.get("mode", "ECO"))
        self._environment = EnvironmentState(**env_dict)

    def _update_nfc_auth(self, data: bytes) -> None:
        if not data:
            return
        status = data[0]
        env_dict = self._environment.__dict__.copy()
        env_dict["message_line"] = "NFC OK" if status else "NFC FAIL"
        self._environment = EnvironmentState(**env_dict)

    def _update_post_frame(self, data: bytes) -> None:
        env_dict = self._environment.__dict__.copy()
        if not data:
            env_dict["message_line"] = "POST"
        else:
            env_dict["message_line"] = f"POST 0x{data[0]:02X}"
        self._environment = EnvironmentState(**env_dict)

# Mapping from arbitration ID to handler method.
_FRAME_DISPATCH: Dict[int, Callable[[CANStateAggregator, bytes], None]] = {
    int(ECUToHudID.ENGINE_RPM): CANStateAggregator._update_engine_rpm,
    int(ECUToHudID.THROTTLE_POSITION): CANStateAggregator._update_throttle,
    int(ECUToHudID.BOOST_PRESSURE): CANStateAggregator._update_boost,
    int(ECUToHudID.AFR_BANKS): CANStateAggregator._update_afr,
    int(ECUToHudID.KNOCK_STATUS): CANStateAggregator._update_knock,
    int(ECUToHudID.OIL_PRESSURE_TEMP): CANStateAggregator._update_oil,
    int(ECUToHudID.COOLANT_TEMP): CANStateAggregator._update_coolant,
    int(ECUToHudID.FUEL_LEVEL): CANStateAggregator._update_fuel,
    int(ECUToHudID.GEAR_POSITION): CANStateAggregator._update_gear,
    int(ECUToHudID.ENGINE_LOAD): CANStateAggregator._update_engine_load,
    int(ECUToHudID.INTAKE_AIR_TEMP): CANStateAggregator._update_intake_temp,
    int(ECUToHudID.EXHAUST_GAS_TEMP): CANStateAggregator._update_exhaust_temp,
    int(ArduinoToHudID.AIR_SHOT_STATUS): CANStateAggregator._update_air_shot_status,
    int(ArduinoToHudID.AWC_STATE): CANStateAggregator._update_awc_state,
    int(ArduinoToHudID.RGB_LIGHTING): lambda self, data: None,
    int(ArduinoToHudID.TANK_PRESSURE): CANStateAggregator._update_tank_pressure,
    int(ArduinoToHudID.TWIN_TURBO_STATUS): CANStateAggregator._update_twin_turbo,
    int(ArduinoToHudID.WASTEGATE_STATUS): CANStateAggregator._update_wastegate_status,
    int(PiToArduinoID.BOOST_TARGET_COMMAND): CANStateAggregator._update_boost_command,
    int(PiToArduinoID.MODE_SELECTION): CANStateAggregator._update_mode_selection,
    int(PiToArduinoID.NFC_AUTH): CANStateAggregator._update_nfc_auth,
    int(SystemCommandID.POST_REQUEST): CANStateAggregator._update_post_frame,
    int(SystemCommandID.POST_RESPONSE): CANStateAggregator._update_post_frame,
}
