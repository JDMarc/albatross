from __future__ import annotations

import struct

from albatross_pi.canbus.decode import CANStateAggregator
from albatross_pi.thermal import SensorStatus, ThermalService, load_thermal_config
from albatross_pi.thermal.analytics import intercooler_effectiveness, interpolate_curve
from albatross_pi.thermal.simulation import SCENARIOS, ThermalSimulator


def test_shared_config_has_32_contiguous_channels() -> None:
    config = load_thermal_config()
    assert [sensor.sensor_id for sensor in config.sensors] == list(range(1, 33))
    assert config.protocol.can_bitrate == 500_000
    assert config.by_key["EGT_LEFT"].technology == "k_type"
    assert not config.by_key["CHRA_TEMP_LEFT"].enabled


def test_piecewise_normalization_and_safe_effectiveness() -> None:
    assert interpolate_curve(50, ((0, 0), (100, 100))) == 50
    assert abs(intercooler_effectiveness(100, 50, 25) - 200 / 3) < 1e-9
    assert intercooler_effectiveness(25, 24, 24) is None


def test_protocol_propagates_fault_instead_of_fake_zero() -> None:
    service = ThermalService()
    p = service.config.protocol
    service.apply_can_frame(p.heartbeat_id, struct.pack(">BBBIB", 1, 5, 0, 12, 1))
    service.apply_can_frame(p.value_base_id, struct.pack(">hhhh", 8000, 8100, 6500, 6600))
    statuses = [SensorStatus.VALID] * 8
    statuses[1] = SensorStatus.OPEN_CIRCUIT
    packed = bytes((int(statuses[i]) << 4) | int(statuses[i + 1]) for i in range(0, 8, 2))
    service.apply_can_frame(p.status_base_id, packed)
    snapshot = service.snapshot()
    assert snapshot.get("EGT_LEFT").temperature_c == 800.0
    assert snapshot.get("EGT_RIGHT").status == SensorStatus.OPEN_CIRCUIT
    assert not snapshot.get("EGT_RIGHT").valid


def test_all_requested_simulation_scenarios_feed_common_model() -> None:
    for scenario in SCENARIOS:
        snapshot = ThermalSimulator(scenario=scenario).step()
        assert len(snapshot.readings) == 32
        assert snapshot.protocol_version == 1


def test_can_aggregator_includes_thermal_snapshot_and_alerts() -> None:
    aggregator = CANStateAggregator()
    config = load_thermal_config(); p = config.protocol
    aggregator.apply_frame(p.heartbeat_id, struct.pack(">BBBIB", 1, 5, 0, 100, 7))
    aggregator.apply_frame(p.value_base_id, struct.pack(">hhhh", 9900, 8000, 7000, 7000))
    aggregator.apply_frame(p.status_base_id, b"\x00\x00\x00\x00")
    snapshot = aggregator.current_snapshot()
    assert snapshot.thermal.online
    assert snapshot.thermal.get("EGT_LEFT").temperature_c == 990.0
