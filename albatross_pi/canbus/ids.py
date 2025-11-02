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


class ArduinoToHudID(IntEnum):
    """Message identifiers published by the Arduino supervisory controller."""

    AIR_SHOT_STATUS = 0x130
    AWC_STATE = 0x131
    RGB_LIGHTING = 0x132
    TANK_PRESSURE = 0x133
    TWIN_TURBO_STATUS = 0x134
    WASTEGATE_STATUS = 0x135


class PiToArduinoID(IntEnum):
    """Messages that originate from the Raspberry Pi HUD to the Arduino."""

    BOOST_TARGET_COMMAND = 0x120
    MODE_SELECTION = 0x121
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


FAULT_CODE_MAP = {
    0x0001: "WMI FLOW LOW",
    0x0002: "EGT HIGH",
    0x0004: "CAN TIMEOUT",
    0x0008: "IMU FAULT",
    0x0010: "AIR SHOT LOW",
    0x0020: "LOW OIL PRESS",
    0x0040: "OVERBOOST",
    0x0080: "KNOCK ESCALATE",
}
