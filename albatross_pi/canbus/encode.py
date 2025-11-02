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
