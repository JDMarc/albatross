"""Raspberry Pi Wi-Fi control through NetworkManager's nmcli interface."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    active: bool


def _split_escaped_fields(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    fields.append("".join(current))
    return fields


class PiNetworkManager:
    """Non-blocking HUD adapter for Raspberry Pi OS NetworkManager."""

    def __init__(self) -> None:
        self.available = shutil.which("nmcli") is not None
        self.wifi_enabled = False
        self.active_ssid = ""
        self.networks: list[WifiNetwork] = []
        self.status = "READY" if self.available else "NMCLI UNAVAILABLE"
        self.busy = False
        self._lock = threading.Lock()

    def refresh_async(self) -> None:
        self._start(self.refresh)

    def refresh(self) -> None:
        if not self.available:
            self.status = "NMCLI UNAVAILABLE"
            return
        try:
            wifi_state = self._run("-t", "-f", "WIFI", "general").strip().lower()
            output = self._run("-t", "--escape", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes")
            networks: list[WifiNetwork] = []
            for line in output.splitlines():
                fields = _split_escaped_fields(line)
                if len(fields) < 4 or not fields[1]:
                    continue
                networks.append(WifiNetwork(fields[1], int(fields[2] or 0), fields[3] or "OPEN", fields[0] == "*"))
            deduplicated: dict[str, WifiNetwork] = {}
            for network in sorted(networks, key=lambda item: (item.active, item.signal), reverse=True):
                deduplicated.setdefault(network.ssid, network)
            self.wifi_enabled = wifi_state == "enabled"
            self.networks = list(deduplicated.values())
            self.active_ssid = next((item.ssid for item in self.networks if item.active), "")
            self.status = "CONNECTED" if self.active_ssid else "NOT CONNECTED"
        except Exception:
            LOGGER.exception("Wi-Fi refresh failed")
            self.status = "SCAN FAILED"

    def set_wifi_enabled_async(self, enabled: bool) -> None:
        self._start(self._set_wifi_enabled, enabled)

    def _set_wifi_enabled(self, enabled: bool) -> None:
        if not self.available:
            self.status = "NMCLI UNAVAILABLE"
            return
        try:
            self._run("radio", "wifi", "on" if enabled else "off")
            self.refresh()
        except Exception:
            LOGGER.exception("Unable to change Wi-Fi radio state")
            self.status = "WIFI CONTROL FAILED"

    def connect_async(self, ssid: str, password: str = "") -> None:
        self._start(self._connect, ssid, password)

    def _connect(self, ssid: str, password: str) -> None:
        if not self.available:
            self.status = "NMCLI UNAVAILABLE"
            return
        self.status = "CONNECTING"
        try:
            args = ["device", "wifi", "connect", ssid]
            if password:
                args.extend(["password", password])
            self._run(*args, timeout=20.0)
            self.refresh()
        except Exception:
            LOGGER.exception("Unable to connect to Wi-Fi network %r", ssid)
            self.status = "CONNECT FAILED"

    def _start(self, callback, *args) -> None:
        with self._lock:
            if self.busy:
                return
            self.busy = True

        def run() -> None:
            try:
                callback(*args)
            finally:
                with self._lock:
                    self.busy = False

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _run(*args: str, timeout: float = 10.0) -> str:
        completed = subprocess.run(["nmcli", *args], check=True, capture_output=True, text=True, timeout=timeout)
        return completed.stdout
