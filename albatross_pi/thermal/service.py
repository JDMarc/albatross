"""CAN-independent thermal data service used by live, simulated, and replay data."""
from __future__ import annotations

from dataclasses import replace
import binascii
import math
import struct
import time
from pathlib import Path
from typing import Mapping

from .analytics import derived_metrics, interpolate_curve, severity, valid_temp
from .baseline import BaselineStore
from .config import ThermalConfig, load_thermal_config
from .logger import ThermalLogger
from .model import SensorStatus, ThermalReading, ThermalSnapshot


class ThermalService:
    """Owns protocol decoding, timestamps, analytics, alerts, and logging.

    Drawing code consumes :class:`ThermalSnapshot`; it never parses CAN.
    Baseline learning is disabled until explicitly authorized by commissioning.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        *,
        baseline_path: Path | str | None = None,
        log_directory: Path | str | None = None,
        clock=time.monotonic,
    ) -> None:
        self.config: ThermalConfig = load_thermal_config(config_path)
        self.clock = clock
        self.baselines = BaselineStore(baseline_path)
        self.logger = ThermalLogger(log_directory, self.config) if log_directory else None
        self._temperatures: list[float | None] = [None] * 32
        self._raw_values: list[int | None] = [None] * 32
        self._statuses: list[SensorStatus] = [
            SensorStatus.STALE if definition.enabled else SensorStatus.NOT_CONFIGURED
            for definition in self.config.sensors
        ]
        self._last_value_s: list[float | None] = [None] * 32
        self._derivatives: list[float] = [0.0] * 32
        self._maxima: list[float | None] = [None] * 32
        self._last_heartbeat_s: float | None = None
        self._last_log_s: float | None = None
        self._protocol_version = 0
        self._node_id = 0
        self._uptime_s = 0
        self._sequence = 0
        self._config_crc32 = 0
        self._vehicle: dict[str, float] = {}
        self._alert_since: dict[str, float] = {}

    @property
    def can_ids(self) -> set[int]:
        protocol = self.config.protocol
        return (
            {protocol.heartbeat_id, protocol.config_id}
            | set(range(protocol.value_base_id, protocol.value_base_id + 8))
            | set(range(protocol.status_base_id, protocol.status_base_id + 4))
            | set(range(protocol.fault_base_id, protocol.fault_base_id + 4))
            | set(range(protocol.raw_base_id, protocol.raw_base_id + 8))
        )

    def set_vehicle_context(self, values: Mapping[str, float]) -> None:
        self._vehicle = {key: float(value) for key, value in values.items() if value is not None}

    def authorize_baseline_learning(self, enabled: bool) -> None:
        self.baselines.authorized_learning = bool(enabled)

    def apply_can_frame(self, arbitration_id: int, data: bytes) -> bool:
        protocol = self.config.protocol
        now = self.clock()
        if arbitration_id == protocol.heartbeat_id:
            if len(data) < 8:
                return True
            self._protocol_version, self._node_id, _flags, self._uptime_s, self._sequence = struct.unpack(">BBBIB", data[:8])
            self._last_heartbeat_s = now
            return True
        if protocol.value_base_id <= arbitration_id < protocol.value_base_id + 8:
            offset = (arbitration_id - protocol.value_base_id) * 4
            if len(data) < 8:
                return True
            for position, raw in enumerate(struct.unpack(">hhhh", data[:8])):
                index = offset + position
                if raw == protocol.invalid_raw:
                    # A received invalid sample is fresh fault evidence, not a
                    # missing packet. Keep its explicit status visible at startup.
                    self._last_value_s[index] = now
                    self._temperatures[index] = None
                    continue
                value = raw * protocol.temperature_scale_c
                definition = self.config.sensors[index]
                if not (definition.valid_c[0] <= value <= definition.valid_c[1]):
                    self._statuses[index] = SensorStatus.OUT_OF_RANGE
                    continue
                previous = self._temperatures[index]
                previous_at = self._last_value_s[index]
                if previous is not None and previous_at is not None and now > previous_at:
                    raw_rate = (value - previous) / (now - previous_at)
                    alpha = min(1.0, (now - previous_at) / max(0.001, definition.derivative_tau_s))
                    self._derivatives[index] += alpha * (raw_rate - self._derivatives[index])
                self._temperatures[index] = value
                self._last_value_s[index] = now
                maximum = self._maxima[index]
                self._maxima[index] = value if maximum is None else max(maximum, value)
            return True
        if protocol.status_base_id <= arbitration_id < protocol.status_base_id + 4:
            offset = (arbitration_id - protocol.status_base_id) * 8
            for byte_index, packed in enumerate(data[:4]):
                for nibble_index, status_raw in enumerate((packed >> 4, packed & 0x0F)):
                    index = offset + byte_index * 2 + nibble_index
                    try:
                        self._statuses[index] = SensorStatus(status_raw)
                    except ValueError:
                        self._statuses[index] = SensorStatus.FRONT_END_FAULT
            return True
        if arbitration_id == protocol.config_id:
            if len(data) >= 4:
                (self._config_crc32,) = struct.unpack(">I", data[:4])
            return True
        if protocol.fault_base_id <= arbitration_id < protocol.fault_base_id + 4:
            # Fault frames are a redundant one-bit-per-channel summary. Detailed
            # status remains in the nibble-packed status frames.
            offset = (arbitration_id - protocol.fault_base_id) * 8
            mask = data[0] if data else 0
            for bit in range(8):
                if mask & (1 << bit) and self._statuses[offset + bit] == SensorStatus.VALID:
                    self._statuses[offset + bit] = SensorStatus.FRONT_END_FAULT
            return True
        if protocol.raw_base_id <= arbitration_id < protocol.raw_base_id + 8:
            offset = (arbitration_id - protocol.raw_base_id) * 4
            if len(data) >= 8:
                for position, raw in enumerate(struct.unpack(">HHHH", data[:8])):
                    self._raw_values[offset + position] = raw
            return True
        return False

    def snapshot(self) -> ThermalSnapshot:
        now = self.clock()
        timeout_s = self.config.protocol.heartbeat_timeout_ms / 1000.0
        can_age_s = math.inf if self._last_heartbeat_s is None else max(0.0, now - self._last_heartbeat_s)
        online = can_age_s <= timeout_s and self._protocol_version == self.config.protocol.version
        ambient_index = self.config.by_key["AMBIENT_AIR"].sensor_id - 1
        ambient = self._temperatures[ambient_index] if self._statuses[ambient_index] == SensorStatus.VALID else None
        readings: dict[str, ThermalReading] = {}
        for index, definition in enumerate(self.config.sensors):
            last = self._last_value_s[index]
            age_s = math.inf if last is None else max(0.0, now - last)
            stale_limit = max(timeout_s, 3.0 / max(0.1, definition.report_hz))
            status = self._statuses[index]
            if not definition.enabled:
                status = SensorStatus.NOT_CONFIGURED
            elif not online or age_s > stale_limit:
                status = SensorStatus.STALE
            elif status == SensorStatus.VALID and self._temperatures[index] is None:
                status = SensorStatus.FRONT_END_FAULT
            value = self._temperatures[index]
            expected, samples, sigma = self.baselines.expected(definition.key, self._vehicle)
            residual = None if value is None or expected is None else value - expected
            dev = 0.0 if residual is None else min(120.0, abs(residual) / max(2.0, sigma) * 25.0)
            absolute = 0.0 if value is None else max(0.0, min(140.0, interpolate_curve(value, definition.curve)))
            ambient_delta = value - ambient if value is not None and ambient is not None and definition.ambient_reference else None
            reading = ThermalReading(
                sensor_id=definition.sensor_id, key=definition.key, name=definition.name,
                temperature_c=value, filtered_temperature_c=value, raw_value=self._raw_values[index],
                status=status, age_ms=age_s * 1000.0, thermal_abs=absolute,
                expected_c=expected, residual_c=residual, thermal_dev=dev,
                derivative_c_s=self._derivatives[index], ambient_delta_c=ambient_delta,
                baseline_samples=samples, maximum_c=self._maxima[index],
            )
            readings[definition.key] = reading
            if reading.valid and value is not None:
                self.baselines.observe(definition.key, value, self._vehicle)

        pressure_ratio_l = self._vehicle.get("pressure_ratio_left")
        pressure_ratio_r = self._vehicle.get("pressure_ratio_right")
        derived = derived_metrics(readings, pressure_ratio_l, pressure_ratio_r)
        alerts, overall = self._alerts(readings, derived, online, now)
        thermal_state = self._thermal_state(readings, online)
        populated = sum(1 for reading in readings.values() if reading.baseline_samples >= self.baselines.minimum_samples)
        baseline_status = "BASELINE READY" if populated >= 20 else ("BASELINE LEARNING" if self.baselines.authorized_learning else "INSUFFICIENT BASELINE")
        result = ThermalSnapshot(
            online=online, protocol_version=self._protocol_version, node_id=self._node_id,
            uptime_s=self._uptime_s, sequence=self._sequence, config_crc32=self._config_crc32,
            config_version=self.config.configuration_version, can_age_ms=can_age_s * 1000.0,
            readings=readings, derived=derived, overall_status=overall,
            thermal_state=thermal_state, alerts=alerts, baseline_status=baseline_status,
        )
        if self.logger and (self._last_log_s is None or now - self._last_log_s >= 0.1):
            self.logger.log(result, self._vehicle, now)
            self._last_log_s = now
        return result

    def _alerts(self, readings: Mapping[str, ThermalReading], derived: Mapping[str, float | None], online: bool, now: float) -> tuple[tuple[str, ...], str]:
        conditions: dict[str, tuple[bool, float]] = {"THERMAL NODE OFFLINE": (not online, 0.0)}
        max_severity = 0.0
        has_data_fault = not online
        for definition in self.config.sensors:
            reading = readings[definition.key]
            score = severity(reading, definition)
            max_severity = max(max_severity, score)
            if online and definition.enabled and reading.status != SensorStatus.VALID:
                has_data_fault = True
                conditions[f"{definition.key} SENSOR {reading.status.name.replace('_', ' ')}"] = (True, 0.25)
            if reading.valid and reading.temperature_c is not None:
                conditions[f"{definition.key} TEMP HIGH"] = (definition.warning_c <= reading.temperature_c < definition.critical_c, 1.0)
                conditions[f"{definition.key} TEMP CRITICAL"] = (reading.temperature_c >= definition.critical_c, 0.0)
                conditions[f"{definition.key} DEVIATION"] = (reading.thermal_dev >= 80.0, 2.0)
        head_delta = derived.get("HEAD_COOLANT_LR_DELTA")
        conditions["HEAD L/R IMBALANCE"] = (head_delta is not None and abs(head_delta) >= 10.0, 2.0)
        for side, short in (("LEFT", "L"), ("RIGHT", "R")):
            effectiveness = derived.get(f"IC_EFFECTIVENESS_{side}")
            conditions[f"IC-{short} PERFORMANCE LOW"] = (effectiveness is not None and effectiveness < 45.0 and self._vehicle.get("load_pct", 0) > 50, 3.0)
        wmi_drop = derived.get("WMI_DROP")
        conditions["WMI THERMAL RESPONSE LOW"] = (self._vehicle.get("wmi_command", 0) > 0 and wmi_drop is not None and wmi_drop < 2.0, 3.0)

        active: list[str] = []
        # A disappearing condition (invalid -> valid, or valid -> unavailable)
        # must end its episode as well as reset its persistence timer.
        self._alert_since = {name: since for name, since in self._alert_since.items() if name in conditions}
        for name, (condition, persistence_s) in conditions.items():
            if condition:
                since = self._alert_since.setdefault(name, now)
                if now - since >= persistence_s:
                    active.append(name)
            else:
                self._alert_since.pop(name, None)
        if max_severity >= 100:
            overall = "CRITICAL"
        elif has_data_fault:
            overall = "DATA FAULT"
        elif max_severity >= 90:
            overall = "WARNING"
        elif max_severity >= 75:
            overall = "CHECK"
        elif max_severity >= 60:
            overall = "ELEVATED"
        else:
            overall = "OK"
        return tuple(sorted(active)), overall

    def _thermal_state(self, readings: Mapping[str, ThermalReading], online: bool) -> str:
        if not online:
            return "THERMAL FAULT"
        oil = valid_temp(readings, "OIL_GALLERY")
        cool_l = valid_temp(readings, "HEAD_COOLANT_LEFT")
        cool_r = valid_temp(readings, "HEAD_COOLANT_RIGHT")
        head_l = valid_temp(readings, "HEAD_METAL_LEFT")
        head_r = valid_temp(readings, "HEAD_METAL_RIGHT")
        critical = any(
            reading.valid and reading.temperature_c is not None and reading.temperature_c >= self.config.by_key[key].critical_c
            for key, reading in readings.items() if key in self.config.by_key
        )
        if critical:
            return "THERMAL FAULT"
        core = [value for value in (oil, cool_l, cool_r, head_l, head_r) if value is not None]
        if not core or max(core) < 55:
            return "COLD"
        if oil is None or oil < 75 or min(core) < 65:
            return "WARMING"
        turbine_hot = max(filter(lambda value: value is not None, (
            valid_temp(readings, "TURBINE_OUT_LEFT"), valid_temp(readings, "TURBINE_OUT_RIGHT")
        )), default=0.0) > 500
        if self._vehicle.get("rpm", 0) < 500 and turbine_hot:
            return "COOLDOWN RECOMMENDED"
        if max(core) > 115:
            return "HOT"
        return "OPERATING"

    @staticmethod
    def config_crc32(path: Path | str) -> int:
        return binascii.crc32(Path(path).read_bytes()) & 0xFFFFFFFF
