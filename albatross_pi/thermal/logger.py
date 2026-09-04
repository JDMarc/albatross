"""Session-independent JSONL logging and persistent exposure counters."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import math
from typing import Mapping

from .config import ThermalConfig
from .model import ThermalSnapshot


class ThermalLogger:
    def __init__(self, directory: Path | str, config: ThermalConfig) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.directory / f"thermal_{session}.jsonl"
        self.exposure_path = self.directory / "thermal_exposure.json"
        self.config = config
        self._last_time: float | None = None
        self._exposure = self._load_exposure()

    def log(self, snapshot: ThermalSnapshot, vehicle: Mapping[str, float], timestamp: float) -> None:
        dt = 0.0 if self._last_time is None else max(0.0, min(2.0, timestamp - self._last_time))
        self._last_time = timestamp
        readings = {}
        for key, reading in snapshot.readings.items():
            readings[key] = {
                "temp_c": reading.temperature_c, "raw": reading.raw_temperature_c,
                "status": reading.status.name, "age_ms": self._finite(reading.age_ms),
                "ambient_delta_c": reading.ambient_delta_c, "dt_dt_c_s": reading.derivative_c_s,
                "expected_c": reading.expected_c, "residual_c": reading.residual_c,
                "thermal_abs": self._finite(reading.thermal_abs), "thermal_dev": self._finite(reading.thermal_dev),
            }
            if reading.valid and reading.temperature_c is not None:
                exposure = self._exposure.setdefault(key, {"max_c": reading.temperature_c, "max_dt_dt": 0.0, "excursions": 0, "time_above_warning_s": 0.0, "above": False})
                definition = self.config.by_key[key]
                exposure["max_c"] = max(float(exposure["max_c"]), reading.temperature_c)
                exposure["max_dt_dt"] = max(float(exposure["max_dt_dt"]), abs(reading.derivative_c_s))
                above = reading.temperature_c >= definition.warning_c
                exposure["time_above_warning_s"] = float(exposure["time_above_warning_s"]) + (dt if above else 0.0)
                if above and not exposure["above"]:
                    exposure["excursions"] = int(exposure["excursions"]) + 1
                exposure["above"] = above
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "configuration_version": self.config.configuration_version,
            "node_online": snapshot.online, "node_uptime_s": snapshot.uptime_s,
            "overall_status": snapshot.overall_status, "thermal_state": snapshot.thermal_state,
            "readings": readings, "derived": dict(snapshot.derived), "vehicle": dict(vehicle),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
        self.exposure_path.write_text(json.dumps(self._exposure, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _finite(value: float | None) -> float | None:
        return value if value is not None and math.isfinite(value) else None

    def _load_exposure(self) -> dict:
        if not self.exposure_path.exists():
            return {}
        try:
            return json.loads(self.exposure_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
