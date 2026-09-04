"""Protected condition-binned expected-temperature baselines."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping


@dataclass
class BinStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def stddev(self) -> float:
        return (self.m2 / max(1, self.count - 1)) ** 0.5


class BaselineStore:
    """Keeps factory, long-term, and recent models distinct and opt-in."""

    def __init__(self, path: Path | str | None = None, minimum_samples: int = 120) -> None:
        self.path = Path(path) if path is not None else None
        self.minimum_samples = minimum_samples
        self.authorized_learning = False
        self.models: dict[str, dict[str, BinStats]] = {"factory": {}, "long_term": {}, "recent": {}}
        if self.path and self.path.exists():
            self._load()

    @staticmethod
    def operating_bin(vehicle: Mapping[str, float]) -> str:
        rpm = int(float(vehicle.get("rpm", 0)) // 1000)
        load = int(float(vehicle.get("load_pct", 0)) // 20)
        ambient = int((float(vehicle.get("ambient_c", 20)) + 40) // 10)
        boost = int(max(0.0, float(vehicle.get("boost_psi", 0))) // 5)
        wmi = 1 if float(vehicle.get("wmi_command", 0)) > 0 else 0
        return f"r{rpm}:l{load}:a{ambient}:b{boost}:w{wmi}"

    def expected(self, sensor_key: str, vehicle: Mapping[str, float]) -> tuple[float | None, int, float]:
        bin_key = f"{sensor_key}|{self.operating_bin(vehicle)}"
        for model in ("factory", "long_term", "recent"):
            stats = self.models[model].get(bin_key)
            if stats and stats.count >= self.minimum_samples:
                return stats.mean, stats.count, max(2.0, stats.stddev)
        return None, 0, 5.0

    def observe(self, sensor_key: str, value: float, vehicle: Mapping[str, float]) -> None:
        if not self.authorized_learning:
            return
        bin_key = f"{sensor_key}|{self.operating_bin(vehicle)}"
        for model in ("long_term", "recent"):
            self.models[model].setdefault(bin_key, BinStats()).observe(value)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            model: {key: vars(stats) for key, stats in bins.items()}
            for model, bins in self.models.items()
        }
        self.path.write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        for model in self.models:
            self.models[model] = {key: BinStats(**stats) for key, stats in raw.get(model, {}).items()}
