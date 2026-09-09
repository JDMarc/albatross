"""Display-only prioritization, stable dwell, faults, stale data and rendering."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
import sys
from pathlib import Path
from dataclasses import replace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.state.snapshot import StateSnapshot
from albatross_pi.thermal.model import ThermalSnapshot,ThermalReading,SensorStatus
from albatross_pi.hud.widgets.temps_grid import TempsGrid

pygame.init()
readings={k:ThermalReading(i,k,k,temperature_c=t,status=SensorStatus.VALID,
                          thermal_abs=heat,derivative_c_s=rate)
          for i,(k,t,heat,rate) in enumerate((
              ("EGT_LEFT",750,30,1),("HEAD_COOLANT_LEFT",95,80,0.2),
              ("PLENUM_IAT",40,20,5),("OIL_GALLERY",90,50,-10)))}
state=replace(StateSnapshot(),thermal=ThermalSnapshot(online=True,readings=readings))
w=TempsGrid(pygame.Rect(0,0,532,64),split=True)
rows=w.selected_rows(state,0)
assert w._keys[0]=="HEAD_COOLANT_LEFT"  # not the hottest raw degrees
first=w._keys
assert w.selected_rows(state,3999)==rows and w._keys==first
w.selected_rows(state,4000)
assert w._keys[0]=="PLENUM_IAT"  # heating, not rapid cooling
faults=dict(readings)
faults["EGT_LEFT"]=replace(readings["EGT_LEFT"],status=SensorStatus.OPEN_CIRCUIT,temperature_c=None)
bad=replace(state,thermal=replace(state.thermal,readings=faults))
assert w.selected_rows(bad,8000)[0][2] and w._keys[0]=="EGT_LEFT"
assert w.selected_rows(replace(state,thermal=replace(state.thermal,online=False)),8001)[0][1]=="OFFLINE"
assert not w.selected_rows(state,8002)[0][2]  # fresh value recovery, no stale latch
assert w.selected_rows(replace(state,wmi=replace(state.wmi,fault_active=True)),8002)[3]==("WMI","FAULT",True)
assert all(w.selected_rows(state,t)[2][0]=="OIL PRESSURE" for t in range(0,40000,4000))
for size in ((532,64),(700,120)):
    w.rect=pygame.Rect((0,0),size)
    for s in (state,bad,StateSnapshot()):
        canvas=pygame.Surface(size);w.draw(canvas,s)
        assert canvas.get_clip()==canvas.get_rect()
pygame.quit()
print("PASS vitals dwell, normalized heat, signed rise, faults, recovery and compact rendering")
