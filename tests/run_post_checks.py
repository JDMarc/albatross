"""POST evidence, timing, fault cases and both supported screen layouts."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from unittest.mock import patch
from albatross_pi.diagnostics.post import PowerOnSelfTest, RX_LENGTHS
from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.thermal.model import ThermalReading, SensorStatus
from albatross_pi.fault_manager.telemetry import FaultSnapshot
from albatross_pi.canbus.decode import CANStateAggregator


def statuses(post):
    return {r.name: r.status for r in post.results}


def healthy(now):
    p = PowerOnSelfTest()
    s = StateSnapshot(telemetry_observed_at=now, telemetry_age_s={fid: 0 for fid in RX_LENGTHS})
    readings = {d.key: ThermalReading(d.sensor_id, d.key, d.name, temperature_c=25,
                                    status=SensorStatus.VALID, age_ms=0)
                for d in p.config.sensors if d.enabled}
    return replace(s, dynamics=replace(s.dynamics, online=True, state="READY", calibrated=True, calibration_matches=True),
                   thermal=replace(s.thermal, online=True, config_crc32=p.expected_crc, readings=readings),
                   air_shot=replace(s.air_shot, v2=replace(s.air_shot.v2, online=True, pressure_valid=True)),
                   fault_management=FaultSnapshot(online=True),
                   temps=replace(s.temps, battery_voltage=12.5),
                   environment=replace(s.environment, fuel_level_pct=50))


def check():
    p = PowerOnSelfTest()
    p.update(StateSnapshot(), 0)
    assert not p.complete and statuses(p)["ECU TELEMETRY"] == "WAIT"
    duration = p.duration_s
    assert 8 < duration < 15
    p.update(StateSnapshot(), duration)
    assert p.complete and p.needs_ack
    assert statuses(p)["ECU TELEMETRY"] == "UNVERIFIED"
    p = PowerOnSelfTest()
    p.update(healthy(0), 0)
    assert not p.needs_ack and not p.complete
    assert statuses(p)["OIL PRESSURE"] == "DEFER"
    assert statuses(p)["MASTER NC VALVE"] == "DEFER"
    assert statuses(p)["ECU TELEMETRY"] == "OK"  # Actual received zero, not a default.
    p.update(healthy(duration), duration)
    assert p.complete and not p.needs_ack
    p = PowerOnSelfTest()
    p.update(StateSnapshot(), 0)
    p.update(healthy(duration), duration)
    assert p.complete and not p.needs_ack  # Late telemetry accepted.
    p = PowerOnSelfTest()
    p.update(healthy(0), 0)
    p.update(healthy(0), duration)  # A frozen snapshot must age out.
    assert p.needs_ack and statuses(p)["DBWX2 / APS / TPS"] == "UNVERIFIED"
    s = healthy(0)
    for changed, name in (
        (replace(s, dynamics=replace(s.dynamics, faults=1 << 5)), "DBWX2 / APS / TPS"),
        (replace(s, dynamics=replace(s.dynamics, faults=1 << 3)), "IMU"),
        (replace(s, thermal=replace(s.thermal, config_crc32=0)), "THERMAL CONFIG"),
        (replace(s, fault_management=replace(s.fault_management, missing_calibration=True)), "FAULT MANAGER"),
        (replace(s, air_shot=replace(s.air_shot, v2=replace(s.air_shot.v2, driver_faults=1))), "AIR SHOT V2"),
    ):
        q = PowerOnSelfTest()
        q.update(changed, 0)
        assert statuses(q)[name] == "FAULT", name
    q = PowerOnSelfTest()
    q.update(replace(s, dynamics=replace(s.dynamics, calibrated=False)), 0)
    assert statuses(q)["DBWX2 / APS / TPS"] == "WAIT"
    agg = CANStateAggregator()
    agg.apply_frame(0x100, b"\x00\x00", "TX")
    agg.apply_frame(0x100, b"\x00")
    agg.apply_frame(0x777, b"\x01" * 8)
    assert 0x100 not in agg.current_snapshot().telemetry_age_s
    agg.apply_frame(0x100, b"\x00\x00")
    assert agg.current_snapshot().telemetry_age_s[0x100] < 1
    import pygame
    from albatross_pi.hud.renderer import HUDRenderer
    out = Path(__file__).resolve().parents[1] / "output" / "post"
    out.mkdir(parents=True, exist_ok=True)
    for size in ((1280, 480), (1920, 720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"), patch("albatross_pi.hud.renderer.NavigationManager"), patch("albatross_pi.hud.renderer.PiNetworkManager"):
            hud = HUDRenderer(size, use_display=False, preferences_path=None)
        hud._post.update(StateSnapshot(), 0)
        hud._post.update(StateSnapshot(), duration)
        hud._post_lines = hud._post.results
        hud._post_started_at = 0
        hud._post_complete = hud._post_fault_active = True
        with patch("albatross_pi.hud.renderer.time.monotonic", return_value=duration):
            hud._render_post_overlay()
        pygame.image.save(hud.screen, str(out / f"startup-post-{size[0]}.png"))
        before = hud.state
        repeat = pygame.event.Event(pygame.KEYDOWN, key=hud._ack_key, repeat=True)
        assert not hud._acknowledge_post(repeat)
        hud._post_complete = False
        press = pygame.event.Event(pygame.KEYDOWN, key=hud._ack_key, repeat=False)
        assert not hud._acknowledge_post(press)
        hud._post_complete = True
        assert hud._acknowledge_post(press)
        assert not hud._post_fault_active and hud.state is before
        hud._post_fault_active = True
        assert hud._acknowledge_post(pygame.event.Event(pygame.JOYBUTTONDOWN, button=hud._joy_select_button))
        assert hud.state is before and hud._post.needs_ack
    print(f"POST checks passed: {len(p.results)} checks, {duration:.1f}s staged sequence; two layouts rendered.")


if __name__ == "__main__":
    check()
