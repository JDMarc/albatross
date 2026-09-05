"""Headless HUD, recorder, weather and protocol checks; optional screenshot output."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
from pathlib import Path
import sys,tempfile,json,struct,math,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import pygame
from albatross_pi.dynamics import Dynamics,DynamicsService
from albatross_pi.dynamics_weather import WeatherService
from albatross_pi.hud.dynamics_view import DynamicsMenu,draw_dynamics
from albatross_pi.hud.renderer import HUDRenderer
from tools.replay_dynamics_log import inputs as replay_inputs

def replay():
    request=(1<<15)|(9<<11)|(10<<7)|(5<<3)
    response=(2<<15)|(10<<11)|(9<<7)|(6<<3)
    rows=[dict(monotonic_s=1.,frame_id=request,data="060008",direction="RX"),
          dict(monotonic_s=1.001,frame_id=response,data=struct.pack("<HHHH",1500,3500,500,4500).hex(),direction="RX"),
          dict(monotonic_s=1.002,frame_id=0x470,data=struct.pack(">hhh",100,200,1000).hex(),direction="RX"),
          dict(monotonic_s=1.05,frame_id=0x471,data=struct.pack(">hhh",1,2,3).hex(),direction="RX")]
    lines=list(replay_inputs(rows,.25));last=list(map(float,lines[-1].split(',')))
    assert last[15:19]==[1500,3500,500,4500] and last[23:25]==[1,1] and abs(last[9]-1.96133)<.001
    binary=os.environ.get("ALBATROSS_VDC_REPLAY")
    if binary:
        result=subprocess.run([binary],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True)
        assert len(result.stdout.splitlines())==len(lines)+1
        assert all(row.split(',')[3]=='1' for row in result.stdout.splitlines()[1:]) # uncalibrated production config fails closed

def packets(service):
    service.ingest(0x229,bytes.fromhex(service.recorder.context["calibration_sha256"][:16]))
    for fid,data in ((0x220,bytes((1,6,7,2,1,1,28,0))),
        (0x221,bytes((1,65,65,100,100,100,100,100))),
        (0x222,struct.pack(">BHHHB",1,1600,2000,2000,100)),
        (0x223,struct.pack(">BhhhB",1,900,100,50,0)),
        (0x224,struct.pack(">BhhBBB",1,0,1200,0,100,0)),
        (0x225,struct.pack(">BHHHB",1,2800,2800,100,55)),
        (0x226,bytes((1,0,0,0,0,100,0,1))),
        (0x227,struct.pack(">BHHBBB",1,1800,2500,50,50,1))):service.ingest(fid,data)

def telemetry():
    now=[10.]
    with tempfile.TemporaryDirectory() as directory:
        service=DynamicsService(directory,clock=lambda:now[0]);packets(service)
        d=service.snapshot();assert d.online and d.event=="CONTROLLED LIFT" and d.slip==0 and d.pitch==9 and not d.alerts
        service.ingest(0x221,bytes((1,255,0,0,0,0,0,0)));assert service.value.rider==65
        now[0]+=.31;assert not service.snapshot().online
        now[0]+=3;service.snapshot();service.close()
        logs=list(Path(directory).glob("*.jsonl"));assert logs
        rows=[json.loads(x) for x in logs[0].read_text().splitlines()]
        assert "calibration_sha256" in rows[0]["context"] and any(r.get("frame_id")==0x220 for r in rows[1:])

def weather():
    now=[10.];calls=[]
    def fetch(location):calls.append(location);return dict(temperature_2m=20,relative_humidity_2m=60,precipitation=1)
    w=WeatherService(lambda c:None,clock=lambda:now[0],fetch=fetch)
    assert w.poll().state==2
    status=SimpleNamespace(connected=True,gps_lat=40.123,gps_lon=-73.123)
    w.phone_status(status);assert w.poll().rain and calls==[(40.1,-73.1)]
    status.connected=False;w.phone_status(status);assert w.poll().state==2
    status.connected=True;w.phone_status(status);assert w.poll().state==0 and len(calls)==2
    now[0]+=700;w.phone_status(status);w.fetch=lambda loc:{"temperature_2m":float("nan")};assert w.poll().state==3

def shutdown():
    with tempfile.TemporaryDirectory() as directory:
        menu=DynamicsMenu(Path(directory)/"settings.json");sent=[];menu.callback=lambda fid,data:sent.append((fid,data));menu.cursor=11
        now=[10.]
        with patch("albatross_pi.hud.dynamics_view.time.monotonic",side_effect=lambda:now[0]):
            menu.select();assert not sent
            now[0]=14;menu.select();assert not sent # expired confirmation
            now[0]=14.1;menu.select();assert sent==[(0x20A,b'\x01STOP\xa5')]
            now[0]=14.3;menu.sync(Dynamics());assert len(sent)==2 and "UNCONFIRMED" in menu.status
            menu.sync(Dynamics(online=True,faults=8192));assert "LATCHED" in menu.status
    rows=[dict(monotonic_s=1.,frame_id=0x20A,data='0153544f50a5',direction='TX')]
    line=list(replay_inputs(rows,.25))[-1];assert line.split(',')[-1]=='1'
    binary=os.environ.get("ALBATROSS_VDC_REPLAY")
    if binary:
        result=subprocess.run([binary],input=line+'\n',text=True,capture_output=True,check=True)
        assert int(result.stdout.splitlines()[1].split(',')[3])&8192

def hud():
    with tempfile.TemporaryDirectory() as directory,patch("albatross_pi.hud.renderer.EvaAlertAudio"):
        h=HUDRenderer(use_display=False,preferences_path=None)
        h._dynamics_menu=DynamicsMenu(Path(directory)/"settings.json");menu=h._dynamics_menu;menu.restored=True
        # Home order follows the visible UI: the utility tiles come after the
        # final ride mode, in both navigation directions.
        h._visible_faults=()
        h._set_home_focus_target("MODE:4");h._handle_dpad_right();assert h._home_focus_target()=="SETTINGS"
        h._handle_dpad_left();assert h._home_focus_target()=="MODE:4"
        h._set_home_focus_target("SETTINGS");h._handle_dpad_left();assert h._home_focus_target()=="MODE:4"
        traction=next(w for w in h.widgets if w.__class__.__name__=="TractionPanel")
        assert traction.rect.height>=58
        sent=[];menu.callback=lambda fid,data:sent.append((fid,data))
        h._set_home_focus_target("DYNAMICS");h._handle_select();assert h._active_menu=="dynamics"
        h._handle_dpad_right();assert sent[-1][0]==0x208 and sent[-1][1][1]==3
        service=DynamicsService();packets(service);d=replace(service.snapshot(),ack=menu.sequence,tcs=3)
        menu.sync(d);assert menu.pending is None and menu.values["tcs"]==3
        menu.cursor=4;menu.adjust(1);assert menu.status=="ENGINEERING BOUND NOT SET"
        menu.cursor=9;h._handle_select();assert menu.page=="telemetry"
        h._handle_back();assert menu.page=="controls"
        h._handle_back();assert h._active_menu=="home"
        menu.path.write_text('{"persistence":"remember","tcs":999,"curve":-1}',encoding="utf-8")
        assert DynamicsMenu(menu.path).values["tcs"]==2
        # Screenshot fixtures are deliberately synthetic and not saved to config.
        out=os.environ.get("ALBATROSS_DYNAMICS_PREVIEWS")
        if out:
            output=Path(out);output.mkdir(parents=True,exist_ok=True)
            menu.preview_only=True;menu.restored=True;menu.pending=None
            for n in range(3):
                for k in range(5):
                    x=k/4;menu.engineering["values"][f"curves[{n}][{k}]"]=(x*x,x,math.sqrt(x))[n]
            h.state=replace(h.state,dynamics=d);h._post_complete=True;h._active_menu="dynamics";menu.cursor=2;menu.sync(d);menu.status="SYNTHETIC HUD PREVIEW / NO VEHICLE CONNECTED"
            for page,name in (("controls","albatross-dynamics-curves.png"),("telemetry","albatross-dynamics-telemetry.png"),("events","albatross-dynamics-events.png")):
                menu.page=page;h.capture_frame();pygame.image.save(h.screen,str(output/name))
            h._active_menu="home";h.capture_frame();pygame.image.save(h.screen,str(output/"albatross-dynamics-hud.png"))
        service.close();pygame.quit()

if __name__=="__main__":
    for check in (telemetry,weather,replay,shutdown,hud):check();print("PASS",check.__name__)
