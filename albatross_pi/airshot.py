"""Air Shot V2 telemetry, raw-frame recorder and replay.

No valve control is computed on the Pi. The deterministic Teensy controller
remains authoritative; this service decodes observations and records traces.
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Full
import json
import struct
import threading
import time

MODES = ("OFF", "MANUAL", "AUTO")
STATES = ("DISABLED", "READY", "ARMED", "REQUESTED", "PRECHECK", "FIRING", "TAPERING", "RECOVERY", "INHIBITED", "FAULT")
REASONS = ("NONE","OFF","UNCALIBRATED","CAN STALE","PRESSURE SENSOR","LOW PRESSURE","REGULATOR","ENGINE COLD","RPM RANGE","TORQUE LOW","DBW","TRACTION","WHEELIE","THERMAL","WMI","ECU PROTECTION","DRIVER","ALREADY BOOSTED","RECOVERY","MAX DURATION","RELEASED","SPOOL COMPLETE","OVERBOOST","BUDGET","WASTEGATE","SHADOW","SERVICE","FUEL")
PROFILES = ("LAUNCH","MID TRANSIENT","BOOST RECOVERY","HIGH RPM","LEFT LAG","RIGHT LAG")
TELEMETRY_IDS = set(range(0x180,0x185))
INPUT_IDS = {0x190,0x191,0x192,0x193,0x194,0x195,*range(0x198,0x19c)}

@dataclass(frozen=True)
class AirShotV2:
    online: bool = False
    mode: str = "OFF"
    state: str = "DISABLED"
    reason: str = "UNCALIBRATED"
    profile: str = "MID TRANSIENT"
    demand_pct: int = 0
    available_pct: int = 0
    valves_pct: tuple = (0,0,0,0)
    predicted_pct: tuple = (0,0,0,0)
    tank_psi: float | None = None
    regulated_psi: float | None = None
    pressure_used_psi: float | None = None
    pressure_valid: bool = False
    event_id: int = 0
    last_duration_ms: int = 0
    tank_before_psi: float | None = None
    flags: int = 0
    driver_faults: int = 0
    stage: int = 0
    calibration_version: int = 0
    currents_a: tuple = (None,None,None,None)
    input_context: dict = field(default_factory=dict)
    logging_fault: bool = False
    compressor: str = "OFF"

    @property
    def alerts(self):
        result=[]
        if not self.online: return ("AIR DATA STALE",)
        if self.driver_faults: result.append("AIR DRIVER FAULT")
        if self.compressor=="FAULT": result.append("AIR COMPRESSOR FAULT")
        if self.reason in ("PRESSURE SENSOR","REGULATOR","OVERBOOST","THERMAL","DBW","CAN STALE","LOW PRESSURE","WMI","WASTEGATE","UNCALIBRATED") and self.mode!="OFF":
            result.append("AIR " + self.reason)
        if self.logging_fault: result.append("AIR LOGGING FAULT")
        return tuple(result)

class AirShotService:
    def __init__(self, log_directory=None, clock=time.monotonic):
        self.clock=clock
        self.value=AirShotV2()
        self.stamps={}
        self.logging_fault=False
        self.config_ack=0
        self.config_ack_at=0.0
        self.config_ack_token=None
        self.queue=Queue(maxsize=8192)
        self.file=None
        if log_directory:
            directory=Path(log_directory); directory.mkdir(parents=True,exist_ok=True)
            self.file=directory/("airshot_"+datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".jsonl")
            self.worker=threading.Thread(target=self._writer,daemon=True,name="airshot-log")
            self.worker.start()

    def _writer(self):
        try:
            with self.file.open("a",encoding="utf-8") as handle:
                while True:
                    row=self.queue.get()
                    if row is None: handle.flush(); return
                    handle.write(json.dumps(row,allow_nan=False,separators=(",",":"))+"\n")
                    if self.queue.empty(): handle.flush()
        except (OSError,ValueError):
            self.logging_fault=True

    def close(self):
        if self.file and self.worker.is_alive():
            try: self.queue.put(None,timeout=1)
            except Full: self.logging_fault=True
            self.worker.join(timeout=2)

    def ingest(self, frame_id, data, direction="RX"):
        now=self.clock()
        if self.file:
            try:
                self.queue.put_nowait(dict(timestamp=datetime.now(timezone.utc).isoformat(),monotonic_s=now,
                    frame_id=frame_id,data=bytes(data).hex(),direction=direction,
                    calibration_version=self.value.calibration_version,event_id=self.value.event_id))
            except Full: self.logging_fault=True
        if direction!="RX" or not data or data[0]!=2: return
        v=self.value
        if frame_id==0x185 and len(data)==8:
            self.config_ack=data[1]
            self.config_ack_at=now
            self.config_ack_token=int.from_bytes(data[6:8],"big")
            return
        if frame_id in TELEMETRY_IDS and len(data)==8:
            if frame_id==0x180:
                _,mode,state,reason,profile,demand,available,flags=data
                if mode>=len(MODES) or state>=len(STATES) or reason>=len(REASONS) or profile>=len(PROFILES) or demand>100 or available>100: return
                v=replace(v,mode=MODES[mode],state=STATES[state],reason=REASONS[reason],profile=PROFILES[profile],demand_pct=demand,available_pct=available,flags=flags)
            elif frame_id==0x181:
                if any(x>100 for x in data[1:5]): return
                v=replace(v,valves_pct=tuple(data[1:5]),driver_faults=data[5],event_id=int.from_bytes(data[6:8],"big"))
            elif frame_id==0x182:
                tank,reg,used=struct.unpack(">HHH",data[1:7])
                v=replace(v,tank_psi=tank/10,regulated_psi=reg/10,pressure_used_psi=used/10,pressure_valid=bool(data[7]))
            elif frame_id==0x183:
                event,duration,before=struct.unpack(">HHH",data[1:7])
                v=replace(v,event_id=event,last_duration_ms=duration,tank_before_psi=before/10,stage=data[7])
            elif frame_id==0x184:
                if any(x>100 for x in data[1:5]) or data[7]>3:return
                v=replace(v,predicted_pct=tuple(data[1:5]),calibration_version=int.from_bytes(data[5:7],"big"),compressor=("OFF","FILLING","COOLDOWN","FAULT")[data[7]])
            self.stamps[frame_id]=now
        elif frame_id in INPUT_IDS:
            context=dict(v.input_context)
            context[hex(frame_id)]={"data":bytes(data).hex(),"at":now}
            v=replace(v,input_context=context)
            if 0x198<=frame_id<=0x19b and len(data)==5:
                currents=list(v.currents_a);currents[frame_id-0x198]=int.from_bytes(data[1:3],"big")/1000
                v=replace(v,currents_a=tuple(currents))
        self.value=v

    def snapshot(self):
        now=self.clock()
        online=all(frame in self.stamps and now-self.stamps[frame]<=0.3 for frame in TELEMETRY_IDS)
        return replace(self.value,online=online,logging_fault=self.logging_fault)

def mode_frame(mode):
    if mode not in MODES: raise ValueError("Air Shot mode must be OFF, MANUAL or AUTO")
    return 0x190,bytes((2,MODES.index(mode),0xA5))

def fire_frame(pressed,sequence):
    return 0x191,struct.pack(">BBHB",2,int(bool(pressed)),sequence & 0xffff,0)

def replay(path,service=None):
    service=service or AirShotService()
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            row=json.loads(line)
            # Preserve recorded monotonic timing, including data-timeout gaps.
            service.clock=lambda t=row["monotonic_s"]:t
            service.ingest(row["frame_id"],bytes.fromhex(row["data"]),row["direction"])
            yield service.snapshot()
