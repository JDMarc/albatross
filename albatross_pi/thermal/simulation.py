"""Synthetic thermal scenarios that feed the same service as live CAN."""
from __future__ import annotations

import math
import struct
from typing import Iterator

from .model import SensorStatus, ThermalSnapshot
from .service import ThermalService


SCENARIOS = (
    "cold_start", "normal_warmup", "highway_cruise", "full_boost_pull", "heat_soak",
    "wmi_activation", "failed_intercooler", "left_cylinder_hot", "blocked_radiator",
    "failed_thermocouple", "can_dropout", "rapid_head_overtemperature",
)


class ThermalSimulator:
    def __init__(self, service: ThermalService | None = None, scenario: str = "normal_warmup") -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario!r}")
        self.service = service or ThermalService()
        self.scenario = scenario
        self.elapsed_s = 0.0

    def step(self, dt_s: float = 0.05) -> ThermalSnapshot:
        self.elapsed_s += dt_s
        p = self.service.config.protocol
        if self.scenario != "can_dropout" or self.elapsed_s < 8.0:
            heartbeat = struct.pack(">BBBIB", p.version, p.node_id, 0, int(self.elapsed_s), int(self.elapsed_s * 10) & 0xFF)
            self.service.apply_can_frame(p.heartbeat_id, heartbeat)
        temperatures = self._temperatures()
        for frame_index in range(8):
            values = temperatures[frame_index * 4 : frame_index * 4 + 4]
            payload = struct.pack(">hhhh", *(int(round(value * 10)) for value in values))
            self.service.apply_can_frame(p.value_base_id + frame_index, payload)
        statuses = [SensorStatus.VALID if definition.enabled else SensorStatus.NOT_CONFIGURED for definition in self.service.config.sensors]
        if self.scenario == "failed_thermocouple" and self.elapsed_s > 4.0:
            statuses[1] = SensorStatus.OPEN_CIRCUIT
        for frame_index in range(4):
            group = statuses[frame_index * 8 : frame_index * 8 + 8]
            payload = bytes((int(group[i]) << 4) | int(group[i + 1]) for i in range(0, 8, 2))
            self.service.apply_can_frame(p.status_base_id + frame_index, payload)
        return self.service.snapshot()

    def stream(self, rate_hz: float = 20.0) -> Iterator[ThermalSnapshot]:
        dt = 1.0 / max(1.0, rate_hz)
        while True:
            yield self.step(dt)

    def _temperatures(self) -> list[float]:
        t = self.elapsed_s
        warm = min(1.0, t / 30.0)
        ambient = 24.0
        egt = 24 + 710 * min(1.0, t / 5.0)
        coolant = 24 + 73 * warm
        head = 24 + 92 * warm
        oil = 24 + 78 * min(1.0, t / 42.0)
        comp_out = ambient + 48 * warm
        ic_out = ambient + 14 * warm
        values = [
            egt, egt + 7, egt - 165, egt - 155,
            ambient + 2, ambient + 2.5, comp_out, comp_out + 2,
            comp_out - 1, comp_out + 1, ic_out, ic_out + 1,
            ic_out + 1, ic_out, ic_out + 2, ic_out + 4, ic_out + 5,
            coolant, coolant + 1, head, head + 2, coolant + 3, coolant - 4,
            oil, oil + 5, oil - 3, oil + 20, oil + 22, ambient,
            oil + 28, oil + 30, ambient,
        ]
        if self.scenario == "full_boost_pull" and t > 5:
            pulse = max(0.0, math.sin(min(math.pi, (t - 5) / 8 * math.pi)))
            values[0] += 220 * pulse; values[1] += 225 * pulse
            values[6] += 85 * pulse; values[7] += 88 * pulse
            values[10] += 18 * pulse; values[11] += 20 * pulse
        elif self.scenario == "wmi_activation" and t > 8:
            values[13] = values[12] - 18
        elif self.scenario == "failed_intercooler" and t > 6:
            values[11] = values[9] - 2
        elif self.scenario == "left_cylinder_hot" and t > 6:
            values[0] += 120; values[17] += 18; values[19] += 28
        elif self.scenario == "blocked_radiator" and t > 8:
            values[17] += (t - 8) * 1.5; values[18] += (t - 8) * 1.5
            values[21] += (t - 8) * 1.5; values[22] = values[21] - 2
        elif self.scenario == "rapid_head_overtemperature" and t > 7:
            values[20] += (t - 7) * 6.0
        elif self.scenario == "heat_soak":
            values[4] += 20 * warm; values[5] += 22 * warm; values[14] += 25 * warm
        return values
