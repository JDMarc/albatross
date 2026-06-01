"""Line-oriented USB NFC tag authorization for the Pi runtime."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import select
import threading
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


def tag_sha256(tag: str) -> str:
    """Hash a normalized reader value so raw tag identifiers need not be stored."""
    normalized = tag.strip().upper().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class NfcAuthorizer:
    """Latch engine-start authorization after a configured USB reader scans an allowed tag."""

    def __init__(
        self,
        *,
        device: str | None,
        allowed_tag_sha256: set[str],
        bypass: bool = False,
    ) -> None:
        self.device = device
        self.allowed_tag_sha256 = {value.lower() for value in allowed_tag_sha256}
        self.bypass = bool(bypass)
        self._authorized = bool(bypass)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @classmethod
    def from_config(cls, path: Path | str, *, bypass: bool = False) -> "NfcAuthorizer":
        config_path = Path(path)
        payload: dict[str, Any] = {}
        if config_path.exists():
            try:
                loaded = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.error("Unable to read NFC configuration %s: %s", config_path, exc)
        env_hashes = os.environ.get("ALBATROSS_NFC_TAG_SHA256", "")
        configured_hashes = payload.get("allowed_tag_sha256", [])
        hashes = set(str(value).strip().lower() for value in configured_hashes if str(value).strip())
        hashes.update(value.strip().lower() for value in env_hashes.split(",") if value.strip())
        device = os.environ.get("ALBATROSS_NFC_DEVICE") or payload.get("reader_device")
        return cls(device=str(device) if device else None, allowed_tag_sha256=hashes, bypass=bypass)

    @property
    def authorized(self) -> bool:
        with self._lock:
            return self._authorized

    @property
    def configured(self) -> bool:
        return bool(self.device and self.allowed_tag_sha256)

    def start(self) -> None:
        if self.bypass:
            LOGGER.warning("NFC authorization bypass is active")
            return
        if not self.configured:
            LOGGER.error("NFC authorization is not configured; engine-run authority remains OFF")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, name="nfc-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def accept_scan(self, raw_tag: str) -> bool:
        digest = tag_sha256(raw_tag)
        accepted = digest.lower() in self.allowed_tag_sha256
        with self._lock:
            if accepted:
                self._authorized = True
        if accepted:
            LOGGER.info("NFC tag authorized for this power cycle")
        else:
            LOGGER.warning("Rejected NFC tag scan")
        return accepted

    def _reader_loop(self) -> None:
        assert self.device is not None
        while not self._stop_event.is_set():
            try:
                self._read_device()
            except OSError as exc:
                LOGGER.error("NFC reader %s unavailable: %s", self.device, exc)
                self._stop_event.wait(2.0)

    def _read_device(self) -> None:
        assert self.device is not None
        fd = os.open(self.device, os.O_RDONLY | os.O_NONBLOCK)
        try:
            LOGGER.info("Reading NFC tags from %s", self.device)
            pending = bytearray()
            while not self._stop_event.is_set():
                readable, _, _ = select.select([fd], [], [], 0.5)
                if not readable:
                    continue
                data = os.read(fd, 256)
                if not data:
                    time.sleep(0.1)
                    continue
                pending.extend(data)
                while b"\n" in pending or b"\r" in pending:
                    newline_positions = [pos for pos in (pending.find(b"\n"), pending.find(b"\r")) if pos >= 0]
                    split_at = min(newline_positions)
                    raw = bytes(pending[:split_at])
                    del pending[: split_at + 1]
                    while bytes(pending[:1]) in {b"\n", b"\r"}:
                        del pending[:1]
                    tag = raw.decode("utf-8", errors="ignore").strip()
                    if tag:
                        self.accept_scan(tag)
        finally:
            os.close(fd)
