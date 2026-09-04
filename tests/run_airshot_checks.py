"""Run with Python directly; includes headless real HUD integration checks."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import struct
from dataclasses import replace
from unittest.mock import patch
import pygame
from albatross_pi.airshot import AirShotService, AirShotV2, mode_frame, fire_frame, replay
from albatross_pi.airshot_calibration import CalibrationEditor, FIELDS
from albatross_pi.airshot_switch import AirModeSwitch
from albatross_pi.hud.renderer import HUDRenderer
from albatross_pi.hud.airshot_view import draw_airshot
from albatross_pi.airshot_calibration import draw_calibration

def telemetry(service):
    for frame,data in [(0x180,bytes((2,1,5,0,1,70,80,5))),
        (0x181,bytes((2,30,31,70,72,0,0,1))),
        (0x182,struct.pack(">BHHHB",2,1500,600,100,1)),
        (0x183,struct.pack(">BHHHB",2,1,500,1600,4)),
        (0x184,bytes((2,30,31,70,72,0,2,0)))]:service.ingest(frame,data)

def test_telemetry():
    now=[10.0];s=AirShotService(clock=lambda:now[0]);telemetry(s)
    v=s.snapshot();assert v.online and v.mode=="MANUAL" and v.valves_pct==(30,31,70,72)
    s.ingest(0x180,bytes((2,255,5,0,1,70,80,5)));assert s.snapshot().mode=="MANUAL"
    now[0]+=0.31;assert not s.snapshot().online and "AIR DATA STALE" in s.snapshot().alerts
    assert mode_frame("AUTO")== (0x190,bytes((2,2,0xA5)))
    assert fire_frame(False,65536)==(0x191,bytes((2,0,0,0,0)))
    with tempfile.TemporaryDirectory() as d:
        s=AirShotService(d);telemetry(s);s.close();rows=list(replay(s.file))
        assert rows[-1].online and rows[-1].event_id==1

def test_calibration():
    with tempfile.TemporaryDirectory() as d:
        e=CalibrationEditor(Path(d)/"cal.json")
        for n in range(len(FIELDS)):e.set(n,1)
        e.save();assert CalibrationEditor(e.path).get(0)==1
        frames=list(e.frames());assert len(frames)==len(FIELDS)+2
        checksum=2166136261
        for n,(fid,data) in enumerate(frames[1:-1]):
            assert fid==0x19d and len(data)==8 and int.from_bytes(data[1:3],"big")==n
            for b in data[3:7]:checksum=((checksum^b)*16777619)&0xffffffff
        assert int.from_bytes(frames[-1][1][1:5],"big")==checksum
        e.cursor=len(FIELDS);e.select(False);assert e.status=="STOP ENGINE TO APPLY"

def test_switch():
    s=AirModeSwitch(Path("/nonexistent-air-switch.json"))
    s.mapping={"controls":[["buttons",0],["buttons",1]],"patterns":{"OFF":[1,0],"MANUAL":[0,0],"AUTO":[0,1]}}
    values={"buttons":[1,0],"axes":[]};s.snapshot=lambda:values
    now=[0.0]
    with patch("albatross_pi.airshot_switch.time.monotonic",side_effect=lambda:now[0]):
        assert s.poll() is None;now[0]=.1;assert s.poll()=="OFF"
        values["buttons"]=[0,1];assert s.poll() is None
        now[0]=.2;assert s.poll()=="AUTO"
        now[0]=.3;assert s.poll() is None # physical state does not undo D-pad choice

def test_hud():
    with patch("albatross_pi.hud.renderer.EvaAlertAudio"):
        hud=HUDRenderer(use_display=False,preferences_path=None)
    modes=[];hud._air_mode_callback=modes.append
    hud._set_home_focus_target("AIR");hud._handle_select();assert hud._active_menu=="air_selected"
    hud._handle_dpad_right();hud._handle_dpad_right();hud._handle_dpad_left()
    assert modes==["MANUAL","AUTO","MANUAL"]
    hud._handle_select();assert hud._active_menu=="airshot"
    hud.state=replace(hud.state,air_shot=replace(hud.state.air_shot,v2=AirShotV2(online=True,mode="AUTO",calibration_version=2)))
    draw_airshot(hud.screen,hud.state,hud._theme_colors())
    hud._post_complete=True
    hud.capture_frame()
    if os.environ.get("ALBATROSS_TEST_PREVIEW"):
        pygame.image.save(hud.screen,os.environ["ALBATROSS_TEST_PREVIEW"])
    hud._handle_back();assert hud._active_menu=="air_selected"
    hud._handle_back();assert hud._active_menu=="home"
    hud.capture_frame()
    hud._active_menu="settings";hud._settings_cursor=hud._setting_items.index("AIR SHOT CALIBRATION")
    hud._handle_select();assert hud._active_menu=="airshot_calibration"
    draw_calibration(hud.screen,hud._air_calibration,hud._theme_colors())
    hud._air_switch.draw(hud.screen,hud._theme_colors())
    fired=[];hud._air_shot_callback=fired.append;hud._request_air_shot(True);assert not fired
    pygame.quit()

if __name__=="__main__":
    for test in (test_telemetry,test_calibration,test_switch,test_hud):
        test();print("PASS",test.__name__)
