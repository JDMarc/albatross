"""Bluetooth phone bridge for media controls + metadata + phone telemetry ingestion."""
from __future__ import annotations

import json
import logging
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


@dataclass
class PhoneStatus:
    connected: bool = False
    track: str = ""
    artist: str = ""
    ambient_temp_f: float | None = None
    gps_lock: bool | None = None
    rain: bool | None = None
    position_s: float = 0.0
    length_s: float = 0.0
    devices: tuple[tuple[str, str], ...] = ()
    phone_time: datetime | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None


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
        threading.Thread(target=self._device_scan_loop, daemon=True, name="phone-device-scan").start()

    def stop(self) -> None:
        self._stop.set()

    def set_link(self, enabled: bool) -> None:
        if enabled:
            self._run_bt("connect", self._mac)
        else:
            self._run_bt("disconnect", self._mac)

    def connect_device(self, mac: str) -> None:
        if mac:
            self._run_bt("connect", mac)

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
                    ["playerctl", "metadata", "--format", "{{artist}}|{{title}}|{{position}}|{{mpris:length}}"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                line = (res.stdout or "").strip()
                parts = line.split("|")
                if len(parts) >= 4:
                    artist, title, pos_s, len_us = parts[:4]
                    self._status.artist = artist.strip()
                    self._status.track = title.strip()
                    self._status.position_s = float(pos_s or 0.0)
                    self._status.length_s = max(0.0, float(len_us or 0.0) / 1_000_000.0)
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
                phone_time_raw = obj.get("phone_time")
                if phone_time_raw:
                    try:
                        self._status.phone_time = datetime.fromisoformat(str(phone_time_raw).replace("Z", "+00:00"))
                    except ValueError:
                        logging.debug("Invalid phone_time payload: %s", phone_time_raw)
                if "gps_lat" in obj:
                    self._status.gps_lat = float(obj["gps_lat"])
                if "gps_lon" in obj:
                    self._status.gps_lon = float(obj["gps_lon"])
                self._on_status(self._status)
            except socket.timeout:
                continue
            except Exception:
                logging.exception("Phone telemetry parse failed")

    @staticmethod
    def _run_bt(*cmd: str) -> str:
        p = subprocess.run(["bluetoothctl", *cmd], check=False, capture_output=True, text=True)
        return (p.stdout or "") + (p.stderr or "")

    def _device_scan_loop(self) -> None:
        while not self._stop.is_set():
            out = self._run_bt("devices")
            devices: list[tuple[str, str]] = []
            for line in out.splitlines():
                if not line.startswith("Device "):
                    continue
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    devices.append((parts[1].strip(), parts[2].strip()))
            self._status.devices = tuple(devices[:8])
            self._on_status(self._status)
            time.sleep(8.0)
