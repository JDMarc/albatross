"""Raspberry Pi-focused entrypoint for Albatross HUD runtime.

Keeps `main.py` available for Windows/demo iteration while providing a stable
boot target for Pi + SocketCAN deployments.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from albatross_pi.updater import register_startup_attempt_or_rollback


REPO_ROOT = Path(__file__).resolve().parent
MAIN_PY = REPO_ROOT / "main.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Albatross HUD in Raspberry Pi mode")
    parser.add_argument("--can-interface", default="can0", help="SocketCAN interface name (default: can0)")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--can-bitrate", type=int, help="Bitrate hint for SocketCAN setup")
    parser.add_argument("--can-rate", type=float, default=60.0, help="HUD update rate when using CAN")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    parser.add_argument("--bind-inputs", action="store_true", help="Prompt keyboard bindings for demo controls")
    parser.add_argument("--nfc-config", type=Path, default=Path("settings/nfc_auth.json"), help="USB NFC authorization configuration")
    parser.add_argument("--nfc-bypass", action="store_true", help="bench-only: permit engine run without an NFC scan")
    parser.add_argument("--disable-low-voltage-shutdown", action="store_true", help="disable orderly Pi halt after sustained engine-off undervoltage")
    args = parser.parse_args()

    register_startup_attempt_or_rollback()

    cmd = [
        sys.executable,
        str(MAIN_PY),
        "--can-interface",
        args.can_interface,
        "--width",
        str(args.width),
        "--height",
        str(args.height),
        "--can-rate",
        str(args.can_rate),
        "--log-level",
        args.log_level,
        "--nfc-config",
        str(args.nfc_config),
    ]
    if args.can_bitrate is not None:
        cmd.extend(["--can-bitrate", str(args.can_bitrate)])
    if args.bind_inputs:
        cmd.append("--bind-inputs")
    if args.nfc_bypass:
        cmd.append("--nfc-bypass")
    if args.disable_low_voltage_shutdown:
        cmd.append("--disable-low-voltage-shutdown")

    raise SystemExit(subprocess.call(cmd, cwd=str(REPO_ROOT)))


if __name__ == "__main__":
    main()
