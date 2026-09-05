"""Thermal warning lifecycle, live HUD propagation, ignore and audio regression."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from unittest.mock import Mock, patch
import pygame
from albatross_pi.thermal import ThermalService, SensorStatus
from albatross_pi.thermal.model import ThermalReading
from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.hud.renderer import HUDRenderer, EvaAlertAudio, RETRO_ERROR_BEEP


def thermal_lifecycle():
    service = ThermalService()
    readings = {d.key: ThermalReading(d.sensor_id, d.key, d.name, temperature_c=20,
                status=SensorStatus.VALID if d.enabled else SensorStatus.NOT_CONFIGURED)
                for d in service.config.sensors}
    def alerts(t, derived=None, online=True):
        return service._alerts(readings, derived or {}, online, t)[0]
    key = "EGT_LEFT"
    d = service.config.by_key[key]
    original = readings[key]
    readings[key] = replace(original, temperature_c=d.warning_c)
    assert key+" TEMP HIGH" not in alerts(0)
    assert key+" TEMP HIGH" in alerts(1.1)
    readings[key] = replace(original, temperature_c=d.critical_c)
    assert key+" TEMP CRITICAL" in alerts(1.2)
    assert key+" TEMP HIGH" not in alerts(1.2)
    readings[key] = original
    assert not alerts(1.3)
    readings[key] = replace(original, temperature_c=None, status=SensorStatus.OPEN_CIRCUIT)
    assert not alerts(2)
    assert key+" SENSOR OPEN CIRCUIT" in alerts(2.3)
    readings[key] = original
    assert not alerts(2.4)
    readings[key] = replace(original, temperature_c=None, status=SensorStatus.OPEN_CIRCUIT)
    assert not alerts(2.5)  # Persistence must restart, not reuse the old timestamp.
    assert key+" SENSOR OPEN CIRCUIT" in alerts(2.8)
    assert alerts(3, online=False) == ("THERMAL NODE OFFLINE",)
    readings[key] = original
    service.set_vehicle_context({"load_pct":75, "wmi_command":100})
    derived = {"IC_EFFECTIVENESS_LEFT":20, "IC_EFFECTIVENESS_RIGHT":20,
               "HEAD_COOLANT_LR_DELTA":11, "WMI_DROP":1}
    alerts(4, derived)
    result = alerts(7.1, derived)
    assert {"IC-L PERFORMANCE LOW", "IC-R PERFORMANCE LOW", "HEAD L/R IMBALANCE", "WMI THERMAL RESPONSE LOW"} <= set(result)
    assert not alerts(7.2)
    for definition in service.config.sensors:
        if not definition.enabled:
            continue
        key = definition.key; original = readings[key]
        readings[key] = replace(original, temperature_c=definition.warning_c)
        alerts(10)
        assert key+" TEMP HIGH" in alerts(11.1)
        readings[key] = replace(original, temperature_c=definition.critical_c)
        assert key+" TEMP CRITICAL" in alerts(11.2)
        readings[key] = original
        assert not alerts(11.3)


def ignore_episode():
    with patch("albatross_pi.hud.renderer.EvaAlertAudio"):
        hud = HUDRenderer((1280,480), use_display=False, preferences_path=None)
    hud._post_complete = True
    hud._dynamics_menu.preview_only = True
    hud._navigation.online_enabled = False
    fault = "EGT_LEFT TEMP CRITICAL"
    definition = ThermalService().config.by_key["EGT_LEFT"]
    reading = ThermalReading(1, "EGT_LEFT", "Left exhaust gas", temperature_c=definition.critical_c, status=SensorStatus.VALID)
    state = replace(StateSnapshot(), thermal=replace(StateSnapshot().thermal, alerts=(fault,), readings={"EGT_LEFT":reading}))
    assert fault in hud._runtime_faults(state, 10)  # Live loop must keep subsystem alerts.
    hud.capture_frame(state)
    assert fault in hud._visible_faults
    hud._active_menu = "fault_detail"
    hud._handle_down(); hud._handle_select()
    assert hud._active_menu == "fault_ignore_confirm" and not hud._ignore_confirm_yes
    hud._handle_select()  # Default cancel must be harmless.
    assert not hud._ignored_faults
    hud._handle_down(); hud._handle_select(); hud._handle_dpad_right(); hud._handle_select()
    assert fault in hud._ignored_faults
    hud.capture_frame(state)
    assert fault not in hud._visible_faults and hud.state.thermal.alerts == (fault,)
    assert fault in hud._runtime_faults(state, 11)  # Ignoring never affects fault generation.
    critical = "OIL_GALLERY TEMP CRITICAL"
    # Another fault is never hidden by this acknowledgement.
    assert critical in hud._presentation_faults((fault, critical))
    hud.capture_frame(StateSnapshot())
    assert not hud._ignored_faults
    hud.capture_frame(state)
    assert fault in hud._visible_faults
    # A confirmation cannot survive resolution and silence a later episode.
    hud._active_menu = "fault_detail"; hud._fault_menu_action=1; hud._handle_select()
    hud.capture_frame(StateSnapshot())
    assert hud._ignore_target is None and hud._active_menu == "fault_detail"
    hud.capture_frame(state)
    if os.environ.get("ALBATROSS_ALERT_PREVIEWS"):
        output = Path(os.environ["ALBATROSS_ALERT_PREVIEWS"]); output.mkdir(parents=True, exist_ok=True)
        hud._active_menu="fault_detail"; hud._fault_menu_action=1
        pygame.image.save(hud.capture_frame(state), str(output/"thermal-error-menu.png"))
        hud._handle_select()
        pygame.image.save(hud.capture_frame(state), str(output/"thermal-ignore-confirmation.png"))
    pygame.quit()


def audio_lifecycle():
    audio = EvaAlertAudio.__new__(EvaAlertAudio)
    audio._enabled=True; audio._channel=Mock(); audio._channel.get_busy.return_value=False
    beep=object(); voice=object()
    audio._sounds={RETRO_ERROR_BEEP:beep, "EGT HIGH":voice}
    audio._active_faults=set(); audio._played_faults=set(); audio._pending_faults=[]; audio._playing_fault=None
    a="EGT_LEFT TEMP CRITICAL"; b="OIL_GALLERY TEMP HIGH"
    audio.update((a,b), allow_playback=True)
    audio._channel.play.assert_called_with(voice)
    audio.update((), allow_playback=False)
    assert not audio._pending_faults and not audio._played_faults
    audio._channel.stop.assert_called_once()
    audio.update((b,), allow_playback=True)
    audio._channel.play.assert_called_with(beep)
    count=audio._channel.play.call_count
    audio.update((b,), allow_playback=True)
    assert audio._channel.play.call_count==count
    audio.update((), allow_playback=True); audio.update((b,), allow_playback=True)
    assert audio._channel.play.call_count==count+1


if __name__ == "__main__":
    for test in (thermal_lifecycle, ignore_episode, audio_lifecycle):
        test(); print("PASS", test.__name__)
