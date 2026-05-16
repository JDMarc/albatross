"""Bluetooth phone bridge for media controls + metadata + phone telemetry ingestion."""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class PhoneStatus:
    connected: bool = False
    track: str = ""
    artist: str = ""
    ambient_temp_f: float | None = None
    gps_lock: bool | None = None
    rain: bool | None = None


class PhoneBridge:
    """Best-effort phone integration.

    - Connects to paired phone over Bluetooth classic.
    - Uses playerctl/MPRIS for metadata and media commands only (no audio routing control).
    - Accepts optional phone telemetry JSON over UDP (weather/GPS).
    """

    def __init__(self, mac: str, on_status: Callable[[PhoneStatus], None], telemetry_udp: str = "127.0.0.1:5010") -> None:
        self._mac = mac
        self._on_status = on_status
        self._telemetry_udp = telemetry_udp
        self._status = PhoneStatus()
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._connect_loop, daemon=True, name="phone-bt-connect").start()
        threading.Thread(target=self._metadata_loop, daemon=True, name="phone-metadata").start()
        threading.Thread(target=self._telemetry_loop, daemon=True, name="phone-telemetry").start()

    def stop(self) -> None:
        self._stop.set()

    def set_link(self, enabled: bool) -> None:
        if enabled:
            self._run_bt("connect", self._mac)
        else:
            self._run_bt("disconnect", self._mac)

    def media_command(self, command: str) -> None:
        cmd_map = {"prev": "previous", "play_pause": "play-pause", "next": "next"}
        mapped = cmd_map.get(command)
        if mapped:
            subprocess.run(["playerctl", mapped], check=False, capture_output=True)

    def _connect_loop(self) -> None:
        while not self._stop.is_set():
            out = self._run_bt("info", self._mac)
            connected = "Connected: yes" in out
            self._status.connected = connected
            self._on_status(self._status)
            if not connected:
                self._run_bt("connect", self._mac)
            time.sleep(5.0)

    def _metadata_loop(self) -> None:
        while not self._stop.is_set():
            try:
                res = subprocess.run(
                    ["playerctl", "metadata", "--format", "{{artist}}|{{title}}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                line = (res.stdout or "").strip()
                if "|" in line:
                    artist, title = line.split("|", 1)
                    self._status.artist = artist.strip()
                    self._status.track = title.strip()
                    self._on_status(self._status)
            except Exception:
                logging.exception("Phone metadata polling failed")
            time.sleep(1.0)

    def _telemetry_loop(self) -> None:
        host, port_s = self._telemetry_udp.split(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, int(port_s)))
        sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                data, _ = sock.recvfrom(4096)
                obj = json.loads(data.decode("utf-8"))
                if "ambient_temp_f" in obj:
                    self._status.ambient_temp_f = float(obj["ambient_temp_f"])
                if "gps_lock" in obj:
                    self._status.gps_lock = bool(obj["gps_lock"])
                if "rain" in obj:
                    self._status.rain = bool(obj["rain"])
                self._on_status(self._status)
            except socket.timeout:
                continue
            except Exception:
                logging.exception("Phone telemetry parse failed")

    @staticmethod
    def _run_bt(*cmd: str) -> str:
        p = subprocess.run(["bluetoothctl", *cmd], check=False, capture_output=True, text=True)
        return (p.stdout or "") + (p.stderr or "")

