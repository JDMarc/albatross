"""Run directly. Real decoders and a withdrawn Tk UI; no CAN/network hardware."""
from pathlib import Path
import sys,math,tkinter as tk
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.demo_systems import DemoSystems,DemoReceiver
from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.thermal import SensorStatus
from albatross_pi.thermal.simulation import SCENARIOS
from can_demo_controls import App

def protocol():
    demo=DemoSystems();now=[10.];rx=DemoReceiver(clock=lambda:now[0])
    demo.values.update(vdc_pitch=-12.5,vdc_slip=-2.5,air_mode="AUTO",air_state="FIRING",air_intake_l=45,air_event_id=42)
    demo.thermal_overrides["EGT_LEFT"]=(800,SensorStatus.VALID)
    demo.thermal_overrides["EGT_RIGHT"]=(None,SensorStatus.OPEN_CIRCUIT)
    demo.thermal_raw["EGT_LEFT"]=12345
    frames=demo.frames();assert all(1<=len(data)<=8 and fid in rx.allowed for fid,data in frames)
    state=rx.apply(StateSnapshot(),[[fid,data.hex()] for fid,data in frames])
    assert state.dynamics.online and state.dynamics.pitch==-12.5 and state.dynamics.slip==-2.5 and state.dynamics.calibration_matches
    assert state.air_shot.v2.online and state.air_shot.v2.mode=="AUTO" and state.air_shot.v2.valves_pct[0]==45 and state.air_shot.v2.event_id==42
    assert state.thermal.online and state.thermal.get("EGT_LEFT").temperature_c==800
    assert state.thermal.get("EGT_RIGHT").status==SensorStatus.OPEN_CIRCUIT
    assert state.thermal.get("EGT_LEFT").raw_value==12345
    assert state.thermal.config_crc32==demo.thermal_crc
    for scenario in SCENARIOS:
        demo.thermal.scenario=scenario
        assert all(1<=len(data)<=8 for _,data in demo.frames())
    for row in ([[0x210,"0000000000000000"]],[[0x20A,"0153544f50a5"]],[[0x220,"00"*9]],[[0x220,"zz"]]):
        try:rx.apply(state,row)
        except ValueError:pass
        else:raise AssertionError("Unsafe or invalid demo frame accepted")
    demo.values["vdc_hash_match"]=False
    state=rx.apply(state,[[fid,data.hex()] for fid,data in demo.frames()]);assert not state.dynamics.calibration_matches
    now[0]+=1;state=rx.apply(state,[])
    assert not state.dynamics.online and not state.air_shot.v2.online and not state.thermal.online
    demo.values["vdc_pitch"]=float("nan")
    try:demo.frames()
    except ValueError:pass
    else:raise AssertionError("NaN accepted")

def panel():
    root=tk.Tk();root.withdraw()
    try:
        with patch("can_demo_controls.socket.socket",return_value=Mock()),patch.object(App,"_tick"):
            app=App(root,interface="slcan",channel="TEST",bitrate=500000,tty_baudrate=2000000,dry_run=True,udp_target="127.0.0.1:5005",send_hud_commands=False)
        sent=[];app._send=lambda fid,data:sent.append((fid,data))
        app.send_all();assert {0x160,0x180,0x185,0x220,0x229}.issubset({fid for fid,_ in sent})
        assert not any(fid in (0x190,0x191,0x208,0x20A,0x210) for fid,_ in sent)
        sent.clear();app._air_mode();app._hold_air(True);app._dynamics_settings();assert not sent
        app.vars["send_hud_commands"].set(True);app.vars["air_mode"].set("MANUAL")
        app._air_mode();app._hold_air(True);app._hold_air(False);app._dynamics_settings()
        assert sent[0]==(0x190,bytes((2,1,0xA5))) and sent[1][1][1]==1 and sent[2][1][1]==0 and sent[3][0]==0x208
        app._preset("Controlled lift");assert app.vars["vdc_pitch"].get()==9 and app.vars["vdc_flags"].get()==28
        app._preset("Powertrain stopped");assert app.fault_vars[13].get()
        with patch("can_demo_controls.messagebox.askyesno",return_value=True):app._powertrain_stop()
        assert sent[-1]==(0x20A,b'\x01STOP\xa5')
        app.vars["vdc_stream"].set(False);app.vars["air_stream"].set(False);app.thermal_stream.set(False)
        app.vars["send_hud_commands"].set(False);sent.clear();app.send_all()
        assert app.systems.frames()==[]
        assert not any(0x180<=fid<=0x185 or 0x220<=fid<=0x229 or fid==0x160 for fid,_ in sent)
        app.close()
    finally:
        try:root.destroy()
        except tk.TclError:pass

if __name__=="__main__":
    for check in (protocol,panel):check();print("PASS",check.__name__)
