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
    FUEL_NAMES,
    MODE_NAMES,
    PiToArduinoID,
    PiToEcuID,
    SystemCommandID,
)
from ..state.snapshot import (
    AirShotState,
    CANFrameRecord,
    ClutchState,
    EngineState,
    EnvironmentState,
    EconomyState,
    LightingState,
    ServiceFlag,
    ServiceReading,
    ServiceStatus,
    StateSnapshot,
    TemperaturesState,
    TractionState,
    WMIState,
)


TRACTION_LEVEL_NAMES = {
    0x01: "LOW",
    0x02: "MED",
    0x03: "HIGH",
    0x04: "OFF",
}


_FRAME_NAMES: dict[int, str] = {}
for _enum in (ECUToHudID, ArduinoToHudID, PiToArduinoID, PiToEcuID, SystemCommandID):
    for _member in _enum:
        _FRAME_NAMES[int(_member)] = f"{_enum.__name__}.{_member.name}"

_FIRMWARE_DEVICE_NAMES = {
    0x01: "Arduino controller",
    0x02: "Pi HUD",
    0x03: "MS3 ECU",
}


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
            "gear": "?",
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
            "coolant_temp_f": -1.0,
            "oil_temp_f": -1.0,
            "oil_pressure_psi": 0.0,
            "battery_voltage": -1.0,
            "intake_temp_f": 0.0,
            "exhaust_temp_f": 0.0,
            "alternator_temp_f": 0.0,
        }
        self._airshot = AirShotState()
        self._wmi = WMIState()
        self._traction = TractionState()
        self._clutch = ClutchState()
        self._lighting = LightingState()
        self._environment = replace(EnvironmentState(), fuel_level_pct=-1.0)
        self._economy = EconomyState()
        self._service = ServiceStatus(
            firmware_versions=(ServiceReading("Pi HUD", "local/dev"),)
        )
        self._faults: Dict[int, str] = {}
        self._shift_light = False
        self._last_snapshot = StateSnapshot(
            engine=replace(EngineState(), rpm_redline=rpm_redline),
            service=self._service,
        )
        self._dirty = False
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def apply_frame(self, arbitration_id: int, data: bytes, direction: str = "RX") -> None:
        """Decode the provided frame and update internal state."""
        handler = _FRAME_DISPATCH.get(arbitration_id)
        with self._condition:
            self._record_can_frame(arbitration_id, data, direction)
            if handler is not None:
                handler(self, data)
            env_dict = self._environment.__dict__.copy()
            env_dict["time"] = datetime.now()
            self._environment = EnvironmentState(**env_dict)
            self._shift_light = self._engine_data.get("rpm", 0) >= 10000
            self._last_snapshot = StateSnapshot(
                engine=EngineState(**self._engine_data),
                temps=TemperaturesState(
                    coolant_temp_f=self._temps_data.get("coolant_temp_f", -1.0),
                    oil_temp_f=self._temps_data.get("oil_temp_f", -1.0),
                    oil_pressure_psi=self._temps_data.get("oil_pressure_psi", 0.0),
                    battery_voltage=self._temps_data.get("battery_voltage", -1.0),
                    intake_temp_f=self._temps_data.get("intake_temp_f", 0.0),
                    exhaust_temp_f=self._temps_data.get("exhaust_temp_f", 0.0),
                    alternator_temp_f=self._temps_data.get("alternator_temp_f", 0.0),
                ),
                air_shot=self._airshot,
                wmi=self._wmi,
                traction=self._traction,
                clutch=self._clutch,
                lighting=self._lighting,
                environment=self._environment,
                economy=self._economy,
                service=self._service,
                shift_light=self._shift_light,
                faults=tuple(sorted(self._faults.values())),
            )
            self._dirty = True
            self._condition.notify_all()

    def mark_sent_frame(self, arbitration_id: int, data: bytes) -> None:
        """Apply locally transmitted frames to keep state in sync."""
        self.apply_frame(arbitration_id, data, direction="TX")

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
    def _record_can_frame(self, arbitration_id: int, data: bytes, direction: str) -> None:
        record = CANFrameRecord(
            arbitration_id=arbitration_id,
            name=_FRAME_NAMES.get(arbitration_id, "UNKNOWN"),
            data_hex=data.hex(" ").upper(),
            direction=direction,
            timestamp=datetime.now(),
        )
        frames = (record,) + self._service.recent_can_frames
        self._service = replace(self._service, recent_can_frames=frames[:18])

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

    def _update_arduino_oil_pressure(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (pressure_raw,) = struct.unpack_from(">H", data)
        self._temps_data["oil_pressure_psi"] = pressure_raw / 10.0

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

    def _update_arduino_fuel(self, data: bytes) -> None:
        if not data:
            return
        level = max(0, min(100, data[0]))
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


    def _update_battery_voltage(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (raw_mv,) = struct.unpack_from(">H", data)
        self._temps_data["battery_voltage"] = raw_mv / 1000.0

    def _update_flex_fuel(self, data: bytes) -> None:
        if not data:
            return
        ethanol_pct = max(0.0, min(100.0, float(data[0])))
        env_dict = self._environment.__dict__.copy()
        env_dict["ethanol_content_pct"] = ethanol_pct
        self._environment = EnvironmentState(**env_dict)

    def _update_injector_status(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (pulse_width_x100,) = struct.unpack_from(">H", data)
        duty_x10 = 0
        if len(data) >= 4:
            (duty_x10,) = struct.unpack_from(">H", data, 2)
        self._economy = replace(
            self._economy,
            injector_pulse_width_ms=max(0.0, pulse_width_x100 / 100.0),
            injector_duty_pct=max(0.0, min(100.0, duty_x10 / 10.0)),
        )

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
        if len(data) >= 2:
            lean_raw = struct.unpack_from(">b", data, 1)[0]
            lean_deg = float(lean_raw)
        self._traction = replace(
            self._traction,
            intervention_level="ON" if active else "OFF",
            wheelie_pitch_deg=lean_deg,
            slip_pct=self._traction.slip_pct,
        )

    def _update_clutch_slip_status(self, data: bytes) -> None:
        if len(data) < 2:
            return
        slip_pct = float(max(0, min(100, data[0])))
        severity_code = data[1]
        severity_map = {0: "NONE", 1: "MILD", 2: "MODERATE", 3: "SEVERE"}
        self._clutch = replace(
            self._clutch,
            slip_pct=slip_pct,
            severity=severity_map.get(severity_code, self._clutch.severity),
        )

    def _update_traction_status(self, data: bytes) -> None:
        if len(data) < 4:
            return
        slip_x10 = struct.unpack_from(">h", data)[0]
        torque_cut = max(0, min(100, data[2]))
        flags = data[3]
        self._traction = replace(
            self._traction,
            slip_pct=max(0.0, slip_x10 / 10.0),
            torque_cut_pct=float(torque_cut),
            active=bool(flags & 0x01),
            sensor_fault=bool(flags & 0x02),
        )

    def _update_service_sensor_voltages(self, data: bytes) -> None:
        if len(data) < 4:
            return
        oil_mv, wmi_mv = struct.unpack_from(">HH", data[:4])
        readings = [
            ServiceReading("Oil pressure sensor", f"{oil_mv / 1000.0:.2f} V"),
            ServiceReading("WMI tank sender", f"{wmi_mv / 1000.0:.2f} V"),
        ]
        if len(data) >= 6:
            (supply_mv,) = struct.unpack_from(">H", data, 4)
            readings.append(ServiceReading("Arduino 5V rail", f"{supply_mv / 1000.0:.2f} V"))
        if len(data) >= 8:
            (spare_mv,) = struct.unpack_from(">H", data, 6)
            readings.append(ServiceReading("Service spare", f"{spare_mv / 1000.0:.2f} V"))
        self._service = replace(self._service, sensor_voltages=tuple(readings))

    def _update_service_digital_states(self, data: bytes) -> None:
        if len(data) < 4:
            return
        input_bits, output_bits, command_bits, fault_bits = data[:4]
        pin_labels = (
            ("Left indicator", 0x01),
            ("Right indicator", 0x02),
            ("High beam", 0x04),
            ("Neutral switch", 0x08),
            ("Brake light", 0x10),
            ("Oil warning lamp", 0x20),
            ("WMI pressure OK", 0x40),
            ("CAN INT low", 0x80),
        )
        relay_labels = (
            ("WG1 enable", 0x01),
            ("WG2 enable", 0x02),
            ("WMI pump", 0x04),
            ("Flame enable", 0x08),
            ("Air shot solenoid", 0x10),
            ("Air compressor", 0x20),
            ("WG1 direction", 0x40),
            ("WG2 direction", 0x80),
        )
        command_labels = (
            ("NFC OK", 0x01),
            ("Flame requested", 0x02),
            ("Limp requested", 0x04),
            ("Run switch", 0x08),
            ("WMI armed", 0x10),
        )
        fault_labels = (
            ("ECU CAN stale", 0x01),
            ("Pi command stale", 0x02),
            ("WMI fault", 0x04),
            ("Traction sensor fault", 0x08),
        )
        pins = [ServiceFlag(label, bool(input_bits & bit)) for label, bit in pin_labels]
        pins.extend(ServiceFlag(label, bool(command_bits & bit)) for label, bit in command_labels)
        pins.extend(ServiceFlag(label, bool(fault_bits & bit)) for label, bit in fault_labels)
        relays = tuple(ServiceFlag(label, bool(output_bits & bit)) for label, bit in relay_labels)
        self._service = replace(self._service, pin_states=tuple(pins), relay_states=relays)

    def _update_service_firmware_version(self, data: bytes) -> None:
        if len(data) < 6:
            return
        device = _FIRMWARE_DEVICE_NAMES.get(data[0], f"Device 0x{data[0]:02X}")
        build = (int(data[4]) << 8) | int(data[5])
        version = f"{data[1]}.{data[2]}.{data[3]}+{build}"
        versions = {reading.label: reading.value for reading in self._service.firmware_versions}
        versions[device] = version
        self._service = replace(
            self._service,
            firmware_versions=tuple(ServiceReading(label, value) for label, value in sorted(versions.items())),
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
        # Turbo feedback is not a boost request. The HUD request display is
        # sourced only from Pi BOOST_TARGET_COMMAND frames.

    def _update_wastegate_status(self, data: bytes) -> None:
        if len(data) < 2:
            return
        duty1, duty2 = data[0], data[1]
        self._engine_data["wastegate_duty_pct"] = (duty1 + duty2) / 2.0

    def _update_wheel_speed(self, data: bytes) -> None:
        if len(data) < 4:
            return
        front_mps_raw, rear_mps_raw = struct.unpack_from(">HH", data[:4])
        mps = max(front_mps_raw, rear_mps_raw) / 100.0
        self._engine_data["speed_mph"] = mps * 2.236936

    def _update_boost_command(self, data: bytes) -> None:
        if len(data) < 2:
            return
        (raw_target,) = struct.unpack_from(">H", data)
        self._engine_data["target_boost_psi"] = raw_target / 10.0

    def _update_wmi_status(self, data: bytes) -> None:
        if len(data) < 6:
            return
        tank = data[0]
        commanded, actual, fault = struct.unpack_from(">HHB", data, 1)
        self._wmi = replace(
            self._wmi,
            tank_level_pct=float(max(0, min(100, tank))),
            commanded_flow_cc_min=float(commanded),
            actual_flow_cc_min=float(actual),
            fault_active=bool(fault),
        )

    def _update_mode_selection(self, data: bytes) -> None:
        if not data:
            return
        mode_code = data[0]
        env_dict = self._environment.__dict__.copy()
        env_dict["mode"] = MODE_NAMES.get(mode_code, env_dict.get("mode", "ECO"))
        self._environment = EnvironmentState(**env_dict)

    def _update_traction_level(self, data: bytes) -> None:
        if not data:
            return
        level = TRACTION_LEVEL_NAMES.get(data[0])
        if level is None:
            return
        self._traction = replace(
            self._traction,
            intervention_level=level,
        )

    def _update_light_status(self, data: bytes) -> None:
        if not data:
            return
        flags = data[0]
        self._lighting = LightingState(
            left_indicator=bool(flags & 0x01),
            right_indicator=bool(flags & 0x02),
            high_beam=bool(flags & 0x04),
            neutral=bool(flags & 0x08),
            brake=bool(flags & 0x10),
            oil_warning=bool(flags & 0x20),
        )

    def _update_fuel_type(self, data: bytes) -> None:
        if not data:
            return
        env_dict = self._environment.__dict__.copy()
        env_dict["fuel_type"] = FUEL_NAMES.get(data[0], env_dict.get("fuel_type", "93"))
        self._environment = EnvironmentState(**env_dict)

    def _update_ecu_fuel_profile(self, data: bytes) -> None:
        if not data:
            return
        self._update_fuel_type(data[:1])

    def _update_ecu_spark_table(self, data: bytes) -> None:
        if not data:
            return
        table = "PERF" if data[0] else "INITIAL"
        env_dict = self._environment.__dict__.copy()
        env_dict["message_line"] = f"SPARK {table}"
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
    int(ECUToHudID.BATTERY_VOLTAGE): CANStateAggregator._update_battery_voltage,
    int(ECUToHudID.FLEX_FUEL): CANStateAggregator._update_flex_fuel,
    int(ECUToHudID.INJECTOR_STATUS): CANStateAggregator._update_injector_status,
    int(ArduinoToHudID.AIR_SHOT_STATUS): CANStateAggregator._update_air_shot_status,
    int(ArduinoToHudID.AWC_STATE): CANStateAggregator._update_awc_state,
    int(ArduinoToHudID.RGB_LIGHTING): lambda self, data: None,
    int(ArduinoToHudID.TANK_PRESSURE): CANStateAggregator._update_tank_pressure,
    int(ArduinoToHudID.TWIN_TURBO_STATUS): CANStateAggregator._update_twin_turbo,
    int(ArduinoToHudID.WASTEGATE_STATUS): CANStateAggregator._update_wastegate_status,
    int(ArduinoToHudID.GEAR_POSITION): CANStateAggregator._update_gear,
    int(ArduinoToHudID.WHEEL_SPEED): CANStateAggregator._update_wheel_speed,
    int(ArduinoToHudID.FUEL_LEVEL): CANStateAggregator._update_arduino_fuel,
    int(ArduinoToHudID.WMI_STATUS): CANStateAggregator._update_wmi_status,
    int(ArduinoToHudID.CLUTCH_SLIP_STATUS): CANStateAggregator._update_clutch_slip_status,
    int(ArduinoToHudID.LIGHT_STATUS): CANStateAggregator._update_light_status,
    int(ArduinoToHudID.OIL_PRESSURE_STATUS): CANStateAggregator._update_arduino_oil_pressure,
    int(ArduinoToHudID.FUEL_TYPE_STATUS): CANStateAggregator._update_fuel_type,
    int(ArduinoToHudID.TRACTION_STATUS): CANStateAggregator._update_traction_status,
    int(ArduinoToHudID.SERVICE_SENSOR_VOLTAGES): CANStateAggregator._update_service_sensor_voltages,
    int(ArduinoToHudID.SERVICE_DIGITAL_STATES): CANStateAggregator._update_service_digital_states,
    int(ArduinoToHudID.SERVICE_FIRMWARE_VERSION): CANStateAggregator._update_service_firmware_version,
    int(PiToArduinoID.BOOST_TARGET_COMMAND): CANStateAggregator._update_boost_command,
    int(PiToArduinoID.MODE_SELECTION): CANStateAggregator._update_mode_selection,
    int(PiToArduinoID.TRACTION_LEVEL): CANStateAggregator._update_traction_level,
    int(PiToArduinoID.FUEL_TYPE_SELECT): CANStateAggregator._update_fuel_type,
    int(PiToArduinoID.NFC_AUTH): CANStateAggregator._update_nfc_auth,
    int(PiToEcuID.FUEL_PROFILE_SELECT): CANStateAggregator._update_ecu_fuel_profile,
    int(PiToEcuID.SPARK_TABLE_SELECT): CANStateAggregator._update_ecu_spark_table,
    int(SystemCommandID.POST_REQUEST): CANStateAggregator._update_post_frame,
    int(SystemCommandID.POST_RESPONSE): CANStateAggregator._update_post_frame,
}
