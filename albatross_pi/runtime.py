"""Runtime supervision helpers for Raspberry Pi deployment."""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

from .state.snapshot import StateSnapshot

LOGGER = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[1]


def is_raspberry_pi() -> bool:
    try:
        model = Path("/proc/device-tree/model").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "raspberry pi" in model.lower()


class SystemdNotifier:
    """Send READY and render-loop watchdog messages to systemd without extra packages."""

    def __init__(self) -> None:
        self._socket_path = os.environ.get("NOTIFY_SOCKET")
        self._last_watchdog_s = 0.0

    def notify(self, message: str) -> bool:
        if not self._socket_path:
            return False
        address: str | bytes = self._socket_path
        if address.startswith("@"):
            address = b"\0" + address[1:].encode("utf-8")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(address)
                sock.sendall(message.encode("utf-8"))
            return True
        except OSError as exc:
            LOGGER.debug("systemd notify failed: %s", exc)
            return False

    def ready(self) -> None:
        self.notify("READY=1\nSTATUS=HUD render loop started")

    def watchdog(self) -> None:
        now = time.monotonic()
        if now - self._last_watchdog_s < 1.0:
            return
        if self.notify("WATCHDOG=1"):
            self._last_watchdog_s = now

    def stopping(self) -> None:
        self.notify("STOPPING=1")


def request_poweroff_if_raspberry_pi() -> bool:
    """Request an orderly halt; external hold-up hardware removes power afterward."""
    if os.environ.get("ALBATROSS_SKIP_POWEROFF") or not is_raspberry_pi():
        return False
    command = ["systemctl", "poweroff"] if shutil.which("systemctl") else ["sudo", "poweroff"]
    subprocess.Popen(command, cwd=str(REPO_ROOT))
    return True


class PiPowerSupervisor:
    """Request a controlled halt for sustained low voltage after the engine has stopped."""

    def __init__(self, *, threshold_v: float = 11.8, hold_s: float = 15.0, enabled: bool = True) -> None:
        self.threshold_v = float(threshold_v)
        self.hold_s = float(hold_s)
        self.enabled = bool(enabled)
        self._low_voltage_since: float | None = None
        self._shutdown_requested = False

    def observe(self, snapshot: StateSnapshot) -> None:
        if not self.enabled or self._shutdown_requested:
            return
        voltage = snapshot.temps.battery_voltage
        safe_to_poweroff = snapshot.engine.rpm <= 0 and snapshot.engine.speed_mph < 1.0
        low_voltage = 0.0 < voltage < self.threshold_v
        if not (safe_to_poweroff and low_voltage):
            self._low_voltage_since = None
            return
        now = time.monotonic()
        if self._low_voltage_since is None:
            self._low_voltage_since = now
            return
        if now - self._low_voltage_since < self.hold_s:
            return
        LOGGER.warning("Requesting controlled Pi shutdown after sustained %.2f V supply", voltage)
        self._shutdown_requested = request_poweroff_if_raspberry_pi()
