"""Audit CAN ID and Arduino Mega pin assignments."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARDUINO_SKETCH = ROOT / "arduino" / "albatross_controller" / "albatross_controller.ino"

_ids_spec = importlib.util.spec_from_file_location("albatross_can_ids", ROOT / "albatross_pi" / "canbus" / "ids.py")
if _ids_spec is None or _ids_spec.loader is None:
    raise RuntimeError("Unable to load CAN ID definitions")
_ids = importlib.util.module_from_spec(_ids_spec)
_ids_spec.loader.exec_module(_ids)

ArduinoToEcuID = _ids.ArduinoToEcuID
ArduinoToHudID = _ids.ArduinoToHudID
ECUToHudID = _ids.ECUToHudID
PiToArduinoID = _ids.PiToArduinoID
PiToEcuID = _ids.PiToEcuID
SystemCommandID = _ids.SystemCommandID


EXPECTED_ARDUINO_CAN_NAMES = {
    ECUToHudID.ENGINE_RPM: "ECU_RPM",
    ECUToHudID.THROTTLE_POSITION: "ECU_TPS",
    ECUToHudID.BOOST_PRESSURE: "ECU_BOOST",
    ECUToHudID.AFR_BANKS: "ECU_AFR",
    ECUToHudID.KNOCK_STATUS: "ECU_KNOCK",
    ECUToHudID.OIL_PRESSURE_TEMP: "ECU_OIL",
    ECUToHudID.COOLANT_TEMP: "ECU_CLT",
    ECUToHudID.FUEL_LEVEL: "ECU_FUEL_LEVEL",
    ECUToHudID.GEAR_POSITION: "ECU_GEAR",
    ECUToHudID.ENGINE_LOAD: "ECU_LOAD",
    ECUToHudID.INTAKE_AIR_TEMP: "ECU_IAT",
    ECUToHudID.EXHAUST_GAS_TEMP: "ECU_EGT",
    ECUToHudID.BATTERY_VOLTAGE: "ECU_BATTERY",
    ECUToHudID.FLEX_FUEL: "ECU_FLEX_FUEL",
    PiToArduinoID.BOOST_TARGET_COMMAND: "PI_BOOST_TARGET",
    PiToArduinoID.MODE_SELECTION: "PI_MODE_SELECT",
    PiToArduinoID.FLAME_MODE: "PI_FLAME_MODE",
    PiToArduinoID.LIMP_MODE: "PI_LIMP_MODE",
    PiToArduinoID.TRACTION_LEVEL: "PI_TRACTION_LEVEL",
    PiToArduinoID.ENGINE_RUN_SWITCH: "PI_ENGINE_RUN_SWITCH",
    PiToArduinoID.WMI_ENABLE: "PI_WMI_ENABLE",
    PiToArduinoID.FUEL_TYPE_SELECT: "PI_FUEL_TYPE_SELECT",
    PiToArduinoID.NFC_AUTH: "PI_NFC_AUTH",
    ArduinoToHudID.AIR_SHOT_STATUS: "ARD_AIR_SHOT_STATUS",
    ArduinoToHudID.AWC_STATE: "ARD_AWC_STATE",
    ArduinoToHudID.RGB_LIGHTING: "ARD_RGB_LIGHTING",
    ArduinoToHudID.TANK_PRESSURE: "ARD_TANK_PRESSURE",
    ArduinoToHudID.TWIN_TURBO_STATUS: "ARD_TWIN_TURBO_STATUS",
    ArduinoToHudID.WASTEGATE_STATUS: "ARD_WASTEGATE_STATUS",
    ArduinoToHudID.GEAR_POSITION: "ARD_GEAR_POSITION",
    ArduinoToHudID.WHEEL_SPEED: "ARD_WHEEL_SPEED",
    ArduinoToHudID.FUEL_LEVEL: "ARD_FUEL_LEVEL",
    ArduinoToHudID.WMI_STATUS: "ARD_WMI_STATUS",
    ArduinoToHudID.CLUTCH_SLIP_STATUS: "ARD_CLUTCH_SLIP_STATUS",
    ArduinoToHudID.LIGHT_STATUS: "ARD_LIGHT_STATUS",
    ArduinoToHudID.OIL_PRESSURE_STATUS: "ARD_OIL_PRESSURE_STATUS",
    ArduinoToHudID.FUEL_TYPE_STATUS: "ARD_FUEL_TYPE_STATUS",
    ArduinoToHudID.TRACTION_STATUS: "ARD_TRACTION_STATUS",
    ArduinoToEcuID.TORQUE_CUT_REQUEST: "ARD_TO_ECU_TORQUE_CUT",
    ArduinoToEcuID.TRACTION_SLIP_REQUEST: "ARD_TO_ECU_TRACTION_SLIP",
    SystemCommandID.POST_REQUEST: "POST_REQUEST",
    SystemCommandID.POST_RESPONSE: "POST_RESPONSE",
}


MEGA_PWM_PINS = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 44, 45, 46}
MEGA_INTERRUPT_PINS = {2, 3, 18, 19, 20, 21}
ANALOG_WRITE_PINS = {"WG1_PWM_PIN", "WG2_PWM_PIN", "WMI_PUMP_PIN"}
INTERRUPT_PINS = {"CAN_INT_PIN", "FRONT_WHEEL_HALL_PIN", "REAR_WHEEL_HALL_PIN", "WMI_FLOW_SENSOR_PIN"}


def _parse_arduino_constants() -> tuple[dict[str, int], dict[str, str]]:
    text = ARDUINO_SKETCH.read_text(encoding="utf-8")
    can = {
        name: int(value, 16)
        for name, value in re.findall(r"constexpr\s+uint16_t\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+)", text)
    }
    pins = dict(re.findall(r"static\s+constexpr\s+uint8_t\s+(\w+)\s*=\s*([A-Za-z0-9_]+)", text))
    return can, pins


def _pin_number(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def main() -> None:
    errors: list[str] = []
    enums = (ECUToHudID, ArduinoToHudID, ArduinoToEcuID, PiToArduinoID, PiToEcuID, SystemCommandID)
    seen: dict[int, str] = {}
    for enum in enums:
        for member in enum:
            previous = seen.setdefault(member.value, f"{enum.__name__}.{member.name}")
            if previous != f"{enum.__name__}.{member.name}":
                errors.append(f"Duplicate Python CAN ID 0x{member.value:03X}: {previous} and {enum.__name__}.{member.name}")

    arduino_can, pins = _parse_arduino_constants()
    for member, arduino_name in EXPECTED_ARDUINO_CAN_NAMES.items():
        actual = arduino_can.get(arduino_name)
        if actual is None:
            errors.append(f"Arduino missing CAN constant {arduino_name}")
        elif actual != member.value:
            errors.append(f"{arduino_name} is 0x{actual:03X}; expected 0x{member.value:03X} from {member}")

    used_pins: dict[str, str] = {}
    for name, value in pins.items():
        previous = used_pins.setdefault(value, name)
        if previous != name:
            errors.append(f"Duplicate Arduino pin assignment {value}: {previous} and {name}")

    for name in ANALOG_WRITE_PINS:
        pin = _pin_number(pins.get(name, ""))
        if pin not in MEGA_PWM_PINS:
            errors.append(f"{name}={pins.get(name)} is not a Mega 2560 PWM pin")

    for name in INTERRUPT_PINS:
        pin = _pin_number(pins.get(name, ""))
        if pin not in MEGA_INTERRUPT_PINS:
            errors.append(f"{name}={pins.get(name)} is not a Mega 2560 interrupt-capable pin")

    if errors:
        raise SystemExit("\n".join(errors))
    print("CAN IDs and Mega pin assignments look consistent.")


if __name__ == "__main__":
    main()
