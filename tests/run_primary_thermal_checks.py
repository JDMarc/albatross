"""Primary thermal routing cannot be overwritten by ECU or aged readings."""
import sys,struct
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.demo_systems import DemoSystems
from albatross_pi.canbus.decode import CANStateAggregator
from albatross_pi.thermal.summary import primary_temperatures
from albatross_pi.thermal.model import SensorStatus
from albatross_pi.state.snapshot import TemperaturesState


def check():
    demo=DemoSystems()
    demo.thermal_overrides.update({key:(value,SensorStatus.VALID) for key,value in
        (("HEAD_COOLANT_LEFT",90),("HEAD_COOLANT_RIGHT",95),("OIL_GALLERY",100),
         ("PLENUM_IAT",35),("EGT_LEFT",700),("EGT_RIGHT",750))})
    aggregator=CANStateAggregator();now=[10.0];aggregator._thermal.clock=lambda:now[0]
    for fid,data in demo.frames():aggregator.apply_frame(fid,data)
    snap=aggregator.current_snapshot();t=snap.temps
    assert (t.coolant_temp_f,t.oil_temp_f,t.intake_temp_f,t.exhaust_temp_f)==(203,212,95,1382)
    for fid,data in ((0x105,struct.pack(">HH",500,3000)),(0x106,struct.pack(">H",1400)),
                     (0x10A,struct.pack(">H",1200)),(0x10B,struct.pack(">HH",12000,12000))):
        aggregator.apply_frame(fid,data)
    assert aggregator.current_snapshot().temps.coolant_temp_f==203
    assert aggregator.current_snapshot().temps.oil_temp_f==212
    assert aggregator.current_snapshot().temps.oil_pressure_psi==50
    assert aggregator.current_snapshot().temps.intake_temp_f==95
    assert aggregator.current_snapshot().temps.exhaust_temp_f==1382
    readings=dict(snap.thermal.readings)
    readings["HEAD_COOLANT_RIGHT"]=replace(readings["HEAD_COOLANT_RIGHT"],status=SensorStatus.OPEN_CIRCUIT)
    projected=primary_temperatures(t,replace(snap.thermal,readings=readings))
    assert projected.coolant_temp_f==-1 and projected.oil_temp_f==212
    now[0]+=1
    for fid,data in demo.frames():
        if not 0x169<=fid<=0x16C:aggregator.apply_frame(fid,data)
    assert aggregator.current_snapshot().thermal.online
    assert aggregator.current_snapshot().temps.oil_temp_f==-1
    for fid,data in demo.frames():aggregator.apply_frame(fid,data)
    assert aggregator.current_snapshot().temps.oil_temp_f==212
    now[0]+=10
    expired=aggregator.current_snapshot().temps
    assert expired.coolant_temp_f==expired.oil_temp_f==expired.intake_temp_f==expired.exhaust_temp_f==-1
    assert expired.oil_pressure_psi==50
    print("PASS primary thermal mapping, retired-source rejection, partial failure and stale expiry")


if __name__=="__main__":check()
