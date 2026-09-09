"""Main-panel context and production CAN dropout/recovery, with real rendering."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import sys
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.demo_systems import DemoSystems
from albatross_pi.canbus.decode import CANStateAggregator
from albatross_pi.hud.widgets.mode_stats_panel import ModeStatsPanel
from albatross_pi.hud.widgets.airshot_panel import AirShotPanel
from albatross_pi.hud.renderer import HUDRenderer

def check():
    demo=DemoSystems()
    demo.values.update(air_mode="MANUAL",air_state="FIRING",air_reason="NONE",air_flags=5,
                       air_event_id=1,air_duration=450,air_used=12,air_intake_l=40,
                       vdc_slip=8,vdc_slip_confidence=90,vdc_tcs_limit=20,vdc_permitted=20)
    now=[10.]
    agg=CANStateAggregator()
    agg.airshot_service.clock=lambda:now[0]
    agg.dynamics_service.clock=lambda:now[0]
    agg._thermal.clock=lambda:now[0]
    for fid,data in demo.frames():agg.apply_frame(fid,data)
    state=agg.current_snapshot()
    assert state.air_shot.v2.online and state.dynamics.online and state.thermal.online
    state=replace(state,engine=replace(state.engine,rpm=4500,speed_mph=45,gear="3",
                  boost_psi=12,target_boost_psi=14,wastegate_duty_pct=45),
                  dynamics=replace(state.dynamics,boost_target=14,flags=17),
                  environment=replace(state.environment,fuel_level_pct=70))
    # Legacy telemetry cannot override V2 FIRING or VDC slip.
    agg.apply_frame(0x130,bytes((0,0)))
    agg.apply_frame(0x133,bytes((0,0)))
    assert agg.current_snapshot().air_shot.v2.state=="FIRING"
    panel=ModeStatsPanel(pygame.Rect(0,0,400,180))
    rows=dict((k,v) for k,v,_ in panel._rows_for_mode("SPORT",state))
    assert rows["TQ LIMITER"]=="TCS" and rows["REAR SLIP"]=="8.0%"
    for mode in ("ECO","NORMAL","SPORT","RACE","ALBATROSS"):
        labels={k for k,_,_ in panel._rows_for_mode(mode,state)}
        assert not labels & {"BOOST","REQ BOOST","WG DUTY","FUEL","AIR SHOT","AIR SHOT V2","EGT","IAT/EGT","WMI FLOW"}
    now[0]+=1
    stale=agg.current_snapshot()
    assert not stale.air_shot.v2.online and not stale.dynamics.online and not stale.thermal.online
    assert dict((k,v) for k,v,_ in panel._rows_for_mode("ALBATROSS",stale))["LAST AIR"]=="--"
    for fid,data in demo.frames():agg.apply_frame(fid,data)
    state=agg.current_snapshot()
    assert state.air_shot.v2.online and state.dynamics.online and state.thermal.online
    with patch("albatross_pi.hud.renderer.EvaAlertAudio"),patch("albatross_pi.hud.renderer.PiNetworkManager"):
        hud=HUDRenderer((1280,480),use_display=False,preferences_path=None)
    hud._post_complete=True;hud._post_fault_active=False;hud._navigation.online_enabled=False
    hud._auto_dim_enabled=False;hud._brightness_index=len(hud._brightness_levels)-1
    output=os.environ.get("ALBATROSS_CONTEXT_PREVIEW")
    state=replace(state,engine=replace(state.engine,rpm=4500,speed_mph=45,gear="3",
                  boost_psi=12,target_boost_psi=14,wastegate_duty_pct=45),
                  dynamics=replace(state.dynamics,boost_target=14,flags=17),
                  environment=replace(state.environment,fuel_level_pct=70))
    for index,mode in enumerate(hud._modes):
        hud._mode_index=index;hud._mode_layout_state={};hud._create_widgets()
        hud.state=replace(state,environment=replace(state.environment,mode=mode))
        hud.capture_frame()
        if output and mode=="ALBATROSS":
            Path(output).parent.mkdir(parents=True,exist_ok=True)
            pygame.image.save(hud.capture_frame(),output)
    tile=AirShotPanel(pygame.Rect(0,0,340,96))
    images=[]
    for ticks in (0,250):
        image=pygame.Surface((340,96))
        with patch("pygame.time.get_ticks",return_value=ticks):tile.draw(image,state)
        images.append(pygame.image.tostring(image.subsurface(tile.firing_rect()),"RGB"))
    assert images[0]!=images[1],"FIRING badge must invert"
    for air in (replace(state.air_shot.v2,online=False),replace(state.air_shot.v2,flags=8)):
        images=[]
        for ticks in (0,250):
            image=pygame.Surface((340,96))
            with patch("pygame.time.get_ticks",return_value=ticks):
                tile.draw(image,replace(state,air_shot=replace(state.air_shot,v2=air)))
            images.append(pygame.image.tostring(image,"RGB"))
        assert images[0]==images[1],"Stale/shadow data must not flash FIRING"
    pygame.quit()
    print("PASS context-only panel, production CAN recovery and FIRING inversion")

if __name__=="__main__":check()
