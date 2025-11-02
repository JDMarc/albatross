"""SocketCAN interface helpers."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

try:
    import can
except ImportError:  # pragma: no cover - optional dependency
    can = None  # type: ignore


LOGGER = logging.getLogger(__name__)


class SocketCANInterface:
    """Thin wrapper around python-can for SocketCAN access."""

    def __init__(
        self,
        channel: str = "can0",
        bitrate: Optional[int] = None,
        rx_callback: Optional[Callable[[int, bytes], None]] = None,
    ) -> None:
        self.channel = channel
        self.bitrate = bitrate
        self.rx_callback = rx_callback
        self._bus: Optional["can.BusABC"] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if can is None:
            raise RuntimeError(
                "python-can is required for SocketCAN interaction. Install it on the Pi runtime."
            )
        if self._bus is not None:
            return
        LOGGER.info("Opening SocketCAN channel %s", self.channel)
        self._bus = can.ThreadSafeBus(channel=self.channel, bustype="socketcan")
        if self.bitrate:
            try:
                self._bus.set_filters([])
                LOGGER.debug("SocketCAN bitrate requested: %s", self.bitrate)
            except NotImplementedError:
                LOGGER.warning("Bitrate configuration not supported by backend; skipping.")
        self._stop_event.clear()
        self._rx_thread = threading.Thread(target=self._rx_loop, name="can-rx", daemon=True)
        self._rx_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        if self._bus is not None:
            LOGGER.info("Closing SocketCAN channel %s", self.channel)
            self._bus.shutdown()
            self._bus = None

    def send(self, arbitration_id: int, data: bytes, timeout: Optional[float] = None) -> None:
        if self._bus is None:
            raise RuntimeError("SocketCANInterface.start() must be called before send().")
        message = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False)
        LOGGER.debug("CAN TX 0x%03X %s", arbitration_id, data.hex())
        self._bus.send(message, timeout=timeout)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _rx_loop(self) -> None:
        assert self._bus is not None
        LOGGER.info("Starting CAN RX loop")
        while not self._stop_event.is_set():
            try:
                message = self._bus.recv(timeout=0.1)
            except can.CanError as exc:  # pragma: no cover - hardware specific
                LOGGER.error("CAN receive error: %s", exc)
                continue
            if message is None:
                continue
            LOGGER.debug("CAN RX 0x%03X %s", message.arbitration_id, message.data.hex())
            if self.rx_callback:
                self.rx_callback(message.arbitration_id, bytes(message.data))
        LOGGER.info("CAN RX loop stopped")
