"""CAN message identifiers for the Albatross HUD network."""
from __future__ import annotations

from enum import IntEnum


class ECUToHudID(IntEnum):
    """Message identifiers published by the MS3Pro Mini ECU."""

    ENGINE_RPM = 0x100
    THROTTLE_POSITION = 0x101
    BOOST_PRESSURE = 0x102
    AFR_BANKS = 0x103
    KNOCK_STATUS = 0x104
    OIL_PRESSURE_TEMP = 0x105
    COOLANT_TEMP = 0x106
    FUEL_LEVEL = 0x107
    GEAR_POSITION = 0x108
    ENGINE_LOAD = 0x109
    INTAKE_AIR_TEMP = 0x10A
    EXHAUST_GAS_TEMP = 0x10B
    BATTERY_VOLTAGE = 0x10C
    FLEX_FUEL = 0x10D
    INJECTOR_STATUS = 0x10E


class ArduinoToHudID(IntEnum):
    """Message identifiers published by the Arduino supervisory controller."""

    AIR_SHOT_STATUS = 0x130
    AWC_STATE = 0x131
    RGB_LIGHTING = 0x132
    TANK_PRESSURE = 0x133
    TWIN_TURBO_STATUS = 0x134
    WASTEGATE_STATUS = 0x135
    GEAR_POSITION = 0x136
    WHEEL_SPEED = 0x137
    FUEL_LEVEL = 0x138
    WMI_STATUS = 0x139
    CLUTCH_SLIP_STATUS = 0x13A
    LIGHT_STATUS = 0x13B
    OIL_PRESSURE_STATUS = 0x13C
    FUEL_TYPE_STATUS = 0x13D
    TRACTION_STATUS = 0x13E
    SERVICE_SENSOR_VOLTAGES = 0x13F
    SERVICE_DIGITAL_STATES = 0x145
    SERVICE_FIRMWARE_VERSION = 0x146
    LIMP_STATUS = 0x147


class ArduinoToEcuID(IntEnum):
    """Messages that originate from Arduino and are consumed by the ECU."""

    TORQUE_CUT_REQUEST = 0x12A
    TRACTION_SLIP_REQUEST = 0x12B


class PiToEcuID(IntEnum):
    """Messages that originate from the Raspberry Pi and are consumed by the ECU."""

    FUEL_PROFILE_SELECT = 0x150
    SPARK_TABLE_SELECT = 0x151
    REV_LIMITER_STRATEGY = 0x152


class PiToArduinoID(IntEnum):
    """Messages that originate from the Raspberry Pi HUD to the Arduino."""

    BOOST_TARGET_COMMAND = 0x120
    MODE_SELECTION = 0x121
    FLAME_MODE = 0x122
    LIMP_MODE = 0x123
    TRACTION_LEVEL = 0x124
    AIR_SHOT_REQUEST = 0x125
    MEDIA_CONTROL = 0x14A
    PHONE_LINK = 0x126
    ENGINE_RUN_SWITCH = 0x127
    WMI_ENABLE = 0x128
    FUEL_TYPE_SELECT = 0x129
    NFC_AUTH = 0x140


class SystemCommandID(IntEnum):
    """Bidirectional utility frames shared across the network."""

    POST_REQUEST = 0x1F0
    POST_RESPONSE = 0x1F1


MODE_NAMES = {
    0x01: "ECO",
    0x02: "NORMAL",
    0x03: "SPORT",
    0x04: "RACE",
    0x05: "ALBATROSS",
}


FUEL_NAMES = {
    0x00: "87",
    0x01: "91",
    0x02: "93",
    0x03: "100",
    0x04: "E85",
    0x05: "C16",
}


LIMP_REASON_NAMES = {
    0x00: "NONE",
    0x01: "PI REQUEST",
    0x02: "ENGINE RUN OFF",
    0x03: "ECU CAN STALE",
    0x04: "PI COMMAND STALE",
    0x05: "THERMAL",
    0x06: "LOW OIL PRESS",
    0x07: "BATTERY VOLTAGE",
    0x08: "KNOCK",
    0x09: "ECU SENSOR",
    0x0A: "NFC AUTH",
    0x0B: "SAFETY SUPERVISOR",
    0x0C: "OVERBOOST",
    0x0D: "WMI FAULT",
    0x0E: "CLUTCH SLIP",
}


LIMP_REASON_CODES = {name: code for code, name in LIMP_REASON_NAMES.items()}


FAULT_CODE_MAP = {
    0x0001: "WMI FLOW LOW",
    0x0002: "EGT HIGH",
    0x0004: "CAN TIMEOUT",
    0x0008: "IMU FAULT",
    0x0010: "AIR SHOT LOW",
    0x0020: "LOW OIL PRESS",
    0x0040: "OVERBOOST",
    0x0080: "KNOCK ESCALATE",
    0x0100: "CRITICAL OIL PRESS",
    0x0200: "COOLANT HOT",
    0x0400: "ECU STALE",
    0x0800: "CAN STALE",
    0x1000: "SPEED SENSOR",
    0x2000: "GEAR SENSOR",
    0x4000: "CLUTCH SLIP",
    0x8000: "LOW FUEL",
    0x0001_0000: "WMI TANK EMPTY",
    0x0002_0000: "WMI PUMP FAULT",
    0x0004_0000: "WMI PRESSURE LOW",
    0x0008_0000: "WASTEGATE STUCK",
    0x0010_0000: "BOOST CONTROL ERROR",
    0x0020_0000: "CYL EGT BOOST MISMATCH",
    0x0040_0000: "INTAKE AIR HOT",
    0x0080_0000: "BATTERY LOW",
    0x0100_0000: "BATTERY HIGH",
    0x0200_0000: "SENSOR RANGE FAULT",
    0x0400_0000: "ENGINE RUN SWITCH OFF",
    0x0800_0000: "ENGINE SHUTDOWN REQUEST",
    0x1000_0000: "SLOW TURBO SPOOL",
}
