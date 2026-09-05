"""Rendered annunciator phase/safety checks and native HUD styling previews."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.hud.widgets.airshot_panel import AirShotPanel
from albatross_pi.hud.widgets.ui_utils import apply_theme, AMBER_BG, AMBER_BRIGHT
from albatross_pi.airshot import AirShotV2
from albatross_pi.thermal.simulation import ThermalSimulator
from albatross_pi.thermal.summary import primary_temperatures


def check():
    output = os.environ.get("ALBATROSS_STYLE_PREVIEWS")
    if output: Path(output).mkdir(parents=True, exist_ok=True)
    for size in ((1280,480),(1920,720)):
        with patch("albatross_pi.hud.renderer.EvaAlertAudio"), patch("albatross_pi.hud.renderer.PiNetworkManager"):
            hud = HUDRenderer(size, use_display=False, preferences_path=None)
        hud._post_complete=True; hud._post_fault_active=False
        hud._navigation.online_enabled=False
        hud._network.active_ssid=""; hud._network.status="OFFLINE"
        hud._auto_dim_enabled=False; hud._brightness_index=len(hud._brightness_levels)-1
        thermal=ThermalSimulator().step(40)
        air=AirShotV2(online=True,mode="AUTO",state="FIRING",reason="NONE",pressure_valid=True,tank_psi=105)
        hud.state=replace(hud.state,thermal=thermal,
            temps=replace(primary_temperatures(hud.state.temps,thermal),battery_voltage=13.8,oil_pressure_psi=48),
            engine=replace(hud.state.engine,rpm=6400,speed_mph=52,gear="3",boost_psi=9.5,target_boost_psi=12,wastegate_duty_pct=38),
            dynamics=replace(hud.state.dynamics,online=True),
            air_shot=replace(hud.state.air_shot,v2=air),
            environment=replace(hud.state.environment,fuel_level_pct=72))
        for theme_index,theme in enumerate(hud._themes):
            hud._theme_index=theme_index
            apply_theme(theme)
            for mode_index,mode in enumerate(hud._modes):
                hud._mode_index=mode_index;hud._mode_layout_state={};hud._create_widgets()
                hud.state=replace(hud.state,environment=replace(hud.state.environment,mode=mode))
                hud._active_menu="home";hud._set_home_focus_target("AIR")
                tile=next(w for w in hud.widgets if isinstance(w,AirShotPanel))
                assert tile.rect.contains(tile.firing_rect())
                frames=[];outside_badge=[]
                for ticks in (100,350):
                    with patch("pygame.time.get_ticks",return_value=ticks):
                        frame=hud.capture_frame()
                    frames.append(frame.copy())
                    # Also test unmodified widget pixels independent of HUD brightness.
                    raw=pygame.Surface(size);raw.fill((17,19,23))
                    with patch("pygame.time.get_ticks",return_value=ticks):tile.draw(raw,hud.state)
                    box=tile.firing_rect()
                    expected=AMBER_BRIGHT if ticks==100 else AMBER_BG
                    assert tuple(raw.get_at((box.x+2,box.y+2)))[:3]==tuple(expected)
                    opposite=AMBER_BG if ticks==100 else AMBER_BRIGHT
                    assert any(tuple(raw.get_at((x,y)))[:3]==tuple(opposite)
                               for x in range(box.x+15,box.right-15) for y in range(box.y+3,box.bottom-3))
                    assert tuple(raw.get_at((tile.rect.x-1,tile.rect.y)))[:3]==(17,19,23)
                    pygame.draw.rect(raw,(0,0,0),box)
                    outside_badge.append(pygame.image.tostring(raw.subsurface(tile.rect),"RGB"))
                assert outside_badge[0]==outside_badge[1], "Flash must remain inside its own box"
                for changed in (replace(air,online=False),replace(air,flags=8),replace(air,state="READY"),replace(air,state="TAPERING")):
                    state=replace(hud.state,air_shot=replace(hud.state.air_shot,v2=changed))
                    raws=[]
                    for ticks in (100,350):
                        raw=pygame.Surface(size)
                        with patch("pygame.time.get_ticks",return_value=ticks):tile.draw(raw,state)
                        raws.append(pygame.image.tostring(raw.subsurface(tile.rect),"RGB"))
                    assert raws[0]==raws[1], "Only live non-shadow FIRING may blink"
                if output and size==(1280,480) and mode_index in (0,2) and theme_index in (0,2):
                    name=f"instrument-{mode.lower()}-{theme.lower().replace(' ','-')}"
                    pygame.image.save(frames[0],str(Path(output)/(name+".png")))
                    pygame.image.save(frames[1],str(Path(output)/(name+"-inverse.png")))
    pygame.quit()
    print("PASS FIRING inversion and stale/shadow suppression; all themes, modes and sizes")


if __name__=="__main__":check()
