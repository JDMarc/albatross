"""Frame builders for Pi-originated CAN commands."""
from __future__ import annotations

import struct

from .ids import PiToArduinoID


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


def build_limp_mode_frame(enabled: bool) -> tuple[int, bytes]:
    """Return the frame commanding limp mode."""
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.LIMP_MODE), payload


def build_traction_level_frame(level_code: int) -> tuple[int, bytes]:
    """Return the frame selecting Arduino traction aggressiveness."""
    payload = bytes((level_code & 0xFF,))
    return int(PiToArduinoID.TRACTION_LEVEL), payload


def build_media_control_frame(command_code: int, value: int) -> tuple[int, bytes]:
    """Return a frame for phone/media navigation control events."""
    payload = bytes((command_code & 0xFF, value & 0xFF))
    return int(PiToArduinoID.MEDIA_CONTROL), payload


def build_phone_link_frame(enabled: bool) -> tuple[int, bytes]:
    """Return a frame to request phone link enable/disable."""
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.PHONE_LINK), payload


def build_engine_run_switch_frame(enabled: bool) -> tuple[int, bytes]:
    """Return a frame to emulate an engine run switch over CAN.

    True => engine may run.
    False => engine run switch OFF (cut ignition/fuel via ECU mapping).
    """
    payload = bytes((0x01 if enabled else 0x00,))
    return int(PiToArduinoID.ENGINE_RUN_SWITCH), payload
