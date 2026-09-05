"""Settings accessibility and truthful Air Shot request/result presentation."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import sys
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.airshot import AirShotV2,REASONS
from albatross_pi.hud.airshot_status import AirShotRequest,airshot_status,REASON_TEXT
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.hud.widgets.airshot_panel import AirShotPanel
from albatross_pi.state.snapshot import EngineState
from albatross_pi.thermal.simulation import ThermalSimulator
from albatross_pi.thermal.summary import primary_temperatures


def check():
    assert set(REASONS)==set(REASON_TEXT)
    air=AirShotV2(online=True,mode="MANUAL",state="READY",reason="NONE")
    for reason in REASONS:
        assert all(airshot_status(replace(air,reason=reason)))
    req=AirShotRequest("AUTO",10)
    assert "WAITING" in airshot_status(air,req,10.2)[1]
    assert "NOT CONFIRMED" in airshot_status(air,req,12)[1]
    assert "SEND FAILED" in airshot_status(air,replace(req,mode_send_error=True),12)[1]
    assert "DATA STALE" in airshot_status(replace(air,online=False),req,12)[1]
    assert "FIRE NOT CONFIRMED" in airshot_status(air,AirShotRequest(fire_held=True))[1]
    assert "LOW PRESSURE" in airshot_status(replace(air,state="INHIBITED",reason="LOW PRESSURE"))[1]
    assert "SHADOW" in airshot_status(replace(air,state="FIRING",flags=8))[1]
    assert airshot_status(replace(air,state="FIRING"))[1]=="FIRING"
    output=os.environ.get("ALBATROSS_REQUEST_PREVIEWS")
    for size in ((1280,480),(1920,720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"),patch("albatross_pi.hud.renderer.PiNetworkManager"):
            hud=HUDRenderer(size,use_display=False,preferences_path=None)
        hud._post_complete=True;hud._post_fault_active=False
        hud._navigation.online_enabled=False
        hud._network.active_ssid=""
        hud._network.status="OFFLINE"
        hud._auto_dim_enabled=False;hud._brightness_index=len(hud._brightness_levels)-1
        hud._save_preferences=Mock()
        hud.state=replace(hud.state,engine=EngineState(speed_mph=35,rpm=4000,gear="3"),thermal=ThermalSimulator().step(40))
        hud.state=replace(hud.state,temps=primary_temperatures(hud.state.temps,hud.state.thermal))
        hud._set_home_focus_target("SETTINGS");hud._handle_select()
        assert hud._active_menu=="settings" and "STOP" in hud._settings_edit_reason()
        hud._settings_cursor=hud._setting_items.index("THEME")
        original=hud._theme_index
        hud._handle_dpad_right();hud._handle_dpad_left();hud._handle_select()
        assert hud._theme_index==original
        if output and size==(1280,480):
            Path(output).mkdir(parents=True,exist_ok=True)
            pygame.image.save(hud.capture_frame(),str(Path(output)/"settings-read-only.png"))
        hud.state=replace(hud.state,engine=EngineState(speed_mph=0,rpm=1000,gear="1"))
        assert "NEUTRAL" in hud._settings_edit_reason()
        hud.state=replace(hud.state,engine=EngineState(speed_mph=0,rpm=0,gear="1"))
        assert not hud._settings_edit_reason()
        hud._handle_dpad_right();assert hud._theme_index!=original
        hud._theme_index=0
        for index,mode in enumerate(hud._modes):
            hud._mode_index=index;hud._mode_layout_state={};hud._create_widgets()
            hud.state=replace(hud.state,air_shot=replace(hud.state.air_shot,v2=replace(air,state="INHIBITED",reason="LOW PRESSURE",tank_psi=25,pressure_valid=True)))
            hud._active_menu="home";hud._set_home_focus_target("AIR")
            hud._air_requested_mode="MANUAL"
            frame=hud.capture_frame()
            tile=next(w for w in hud.widgets if isinstance(w,AirShotPanel))
            assert tile.rect.height>=62 and frame.get_rect().contains(tile.rect)
            if output and size==(1280,480) and index in (0,2):
                pygame.image.save(frame,str(Path(output)/f"air-request-{mode.lower()}.png"))
        hud._active_menu="airshot"
        if output and size==(1280,480):pygame.image.save(hud.capture_frame(),str(Path(output)/"air-request-info.png"))
    pygame.quit()
    print("PASS Settings browse/edit gates and Air Shot request/result scenarios")


if __name__=="__main__":check()
