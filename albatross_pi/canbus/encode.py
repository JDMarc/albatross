"""Frame builders for Pi-originated CAN commands."""
from __future__ import annotations

import struct

from .calibration import fuel_profile_for_code, spark_table_for_mode
from .ids import LIMP_REASON_CODES, PiToArduinoID, PiToEcuID


def build_boost_target_frame(target_psi: float) -> tuple[int, bytes]:
    """Return the arbitration ID and payload for a boost target command."""
    clamped = max(0.0, min(6553.5, float(target_psi)))
    payload = struct.pack(">H", int(round(clamped * 10)))
    return int(PiToArduinoID.BOOST_TARGET_COMMAND), payload


def build_mode_selection_frame(mode_code: int) -> tuple[int, bytes]:
    """Return the frame announcing the requested riding mode."""
    payload = bytes((mode_code & 0xFF,))
    return int(PiToArduinoID.MODE_SELECTION), payload


def build_nfc_auth_frame(success: bool) -> tuple[int, bytes]:
    """Return the NFC authentication acknowledgement frame."""
    payload = bytes((0x01 if success else 0x00,))
    return int(PiToArduinoID.NFC_AUTH), payload


def build_flame_mode_frame(enabled: bool) -> tuple[int, bytes]:
    """Return the frame toggling flame mode (Pi is source of truth)."""
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.FLAME_MODE), payload


def build_limp_mode_frame(enabled: bool, reason: str = "") -> tuple[int, bytes]:
    """Return the frame commanding limp mode.

    Payload byte 0: 0/1 active request.
    Payload byte 1: reason code, using LIMP_REASON_NAMES in ids.py.
    Older Arduino firmware that only reads byte 0 will safely ignore byte 1.
    """
    reason_code = 0x00 if not enabled else LIMP_REASON_CODES.get(reason.upper(), LIMP_REASON_CODES["SAFETY SUPERVISOR"])
    payload = bytes((0x01 if enabled else 0x00, reason_code & 0xFF))
    return int(PiToArduinoID.LIMP_MODE), payload


def build_traction_level_frame(level_code: int) -> tuple[int, bytes]:
    """Return the frame selecting Arduino traction aggressiveness."""
    payload = bytes((level_code & 0xFF,))
    return int(PiToArduinoID.TRACTION_LEVEL), payload


def build_air_shot_request_frame() -> tuple[int, bytes]:
    """Return a momentary rider request to fire Air Shot.

    Arduino still owns all Air Shot safety gates and latching.
    """
    return int(PiToArduinoID.AIR_SHOT_REQUEST), bytes((0x01,))


def build_media_control_frame(command_code: int, value: int) -> tuple[int, bytes]:
    """Return a frame for phone/media navigation control events."""
    payload = bytes((command_code & 0xFF, value & 0xFF))
    return int(PiToArduinoID.MEDIA_CONTROL), payload


def build_phone_link_frame(enabled: bool) -> tuple[int, bytes]:
    """Return a frame to request phone link enable/disable."""
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.PHONE_LINK), payload


def build_fuel_type_frame(fuel_code: int) -> tuple[int, bytes]:
    """Return a frame selecting the active fuel table/type."""
    payload = bytes((fuel_code & 0xFF,))
    return int(PiToArduinoID.FUEL_TYPE_SELECT), payload


def build_ecu_fuel_profile_frame(fuel_code: int) -> tuple[int, bytes]:
    """Return a frame selecting the ECU fuel table and stoich/AFR profile."""
    profile = fuel_profile_for_code(fuel_code)
    payload = struct.pack(">BBH", profile.code & 0xFF, profile.fuel_table & 0xFF, int(round(profile.stoich_afr * 100)))
    return int(PiToEcuID.FUEL_PROFILE_SELECT), payload


def build_ecu_spark_table_frame(mode_code: int) -> tuple[int, bytes]:
    """Return a frame selecting initial or performance spark table by ride mode."""
    payload = bytes((spark_table_for_mode(mode_code) & 0xFF,))
    return int(PiToEcuID.SPARK_TABLE_SELECT), payload


def build_ecu_rev_limiter_strategy_frame(flame_mode_enabled: bool) -> tuple[int, bytes]:
    """Return a frame selecting MS3 rev limiter strategy.

    Payload byte 0: 0=fuel cut, 1=ignition/spark cut. MS3/TunerStudio must map
    this request to a real table/switch input; wasted-spark ignition mode itself
    is not treated as a live CAN-toggleable setting here.
    """
    payload = bytes((0x01 if flame_mode_enabled else 0x00,))
    return int(PiToEcuID.REV_LIMITER_STRATEGY), payload


def build_engine_run_switch_frame(enabled: bool) -> tuple[int, bytes]:
    """Return a frame to emulate an engine run switch over CAN.

    True => engine may run.
    False => engine run switch OFF (cut ignition/fuel via ECU mapping).
    """
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.ENGINE_RUN_SWITCH), payload


def build_wmi_enable_frame(enabled: bool) -> tuple[int, bytes]:
    """Return the frame arming/disarming Arduino-managed WMI strategy."""
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.WMI_ENABLE), payload
