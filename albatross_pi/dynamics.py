"""VDC telemetry and bounded pre/post-event recorder. No actuator math on the Pi."""
from dataclasses import dataclass,replace
from collections import deque
from datetime import datetime,timezone
from pathlib import Path
from queue import Queue,Full
import json,struct,threading,time,hashlib

LEVELS=("OFF","LOW","MED","HIGH")
STATES=("INIT","SELF TEST","READY","NORMAL","TCS MONITOR","TCS ACTIVE","AWC TRACKING","AWC ACTIVE","TCS + AWC","DEGRADED","FAULT")
EVENTS=("NORMAL","ACCELERATING","BRAKING","CORNERING","POSSIBLE SLIP","REAR SLIP","POSSIBLE WHEELIE","CONTROLLED LIFT","EXCESSIVE LIFT","TOUCHDOWN","SENSOR DISAGREEMENT","UNKNOWN","LIFT + SLIP")
WEATHER=("VALID","STALE","PHONE OFFLINE","INTERNET OFFLINE","UNKNOWN")
FAULTS=("ENGINEERING CALIBRATION","FRONT WSS LOST","REAR WSS LOST","IMU LOST","IMU IMPLAUSIBLE","APS DISAGREEMENT","TPS DISAGREEMENT","DBW COMM LOSS","DBW POSITION ERROR","DBW DRIVER","MS3 CAN LOSS","APS RATE","IMU DRIFT")
IDS=set(range(0x220,0x228))

@dataclass(frozen=True)
class Dynamics:
    online:bool=False
    state:str="INIT"
    event:str="UNKNOWN"
    tcs:int=2
    awc:int=2
    curve:int=0
    flags:int=0
    ack:int=0
    rider:float=0
    permitted:float=0
    tcs_limit:float=100
    awc_limit:float=100
    lean_limit:float=100
    engine_limit:float=0
    mode_limit:float=0
    front:float=0
    rear:float=0
    speed:float=0
    pitch:float=0
    lean:float=0
    pitch_rate:float=0
    slip:float=0
    slip_target:float=0
    slip_confidence:float=0
    wheelie_confidence:float=0
    front_contact:float=0
    sensor_confidence:float=0
    throttle_target:float=0
    throttle_actual:float=0
    boost_target:float=0
    air_margin:float=0
    faults:int=0
    weather:int=4
    calibrated:bool=False
    calibration_matches:bool=False
    wheelie_target:float=0
    wheelie_max:float=0
    lean_left:float=0
    lean_right:float=0
    weather_assist:bool=True
    history:tuple=()
    logging_fault:bool=False
    @property
    def alerts(self):
        a=[] if self.online else ["VDC DATA STALE"]
        a.extend("VDC "+name for n,name in enumerate(FAULTS) if self.faults&(1<<n))
        if self.logging_fault:a.append("VDC LOGGING FAULT")
        if self.online and not self.calibration_matches:a.append("VDC CALIBRATION VERSION MISMATCH")
        return tuple(a)

class EventRecorder:
    def __init__(self,directory=None,pre=3.,post=3.,clock=time.monotonic):
        config_path=Path(__file__).resolve().parents[1]/"config/vdc_engineering.json"
        calibration=json.loads(config_path.read_text(encoding="utf-8"))
        self.context={"calibration_sha256":hashlib.sha256(json.dumps(calibration,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"calibration":calibration}
        self.clock=clock;self.pre=pre;self.post=post;self.ring=deque(maxlen=20000);self.active=None;self.history=deque(maxlen=32)
        self.queue=Queue(maxsize=4);self.failed=False;self.directory=Path(directory) if directory else None
        if self.directory:
            try:
                self.directory.mkdir(parents=True,exist_ok=True)
                self.thread=threading.Thread(target=self._writer,daemon=True,name="vdc-events");self.thread.start()
            except OSError:self.failed=True;self.directory=None
    def _writer(self):
        try:
            while True:
                item=self.queue.get()
                if item is None:return
                with (self.directory/item["name"]).open("x",encoding="utf-8") as f:
                    f.write(json.dumps(item["meta"])+"\n")
                    for row in item["rows"]:f.write(json.dumps(row,separators=(",",":"))+"\n")
        except (OSError,ValueError):self.failed=True
    def record(self,fid,data,direction):
        now=self.clock();row={"monotonic_s":now,"frame_id":fid,"data":bytes(data).hex(),"direction":direction}
        self.ring.append(row)
        while self.ring and now-self.ring[0]["monotonic_s"]>self.pre:self.ring.popleft()
        if self.active:
            self.active["rows"].append(row)
            if now>=self.active["until"] or len(self.active["rows"])>=20000:self.finish()
    def trigger(self,value):
        now=self.clock();label=datetime.now(timezone.utc).isoformat()
        summary=f"{label[11:19]}  {value.event}  {value.slip:+.1f}% / {value.pitch:.1f}deg  TQ {value.permitted:.0f}%"
        self.history.appendleft(summary)
        if self.active:
            self.active["until"]=min(self.active["start"]+12,now+self.post);return
        self.active={"name":"vdc_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")+".jsonl","start":now,"until":now+self.post,
            "meta":{"schema":1,"trigger_utc":label,"event":value.event,"faults":value.faults,"weather":WEATHER[value.weather],"context":dict(self.context)},"rows":list(self.ring)}
    def finish(self):
        if self.active and self.directory:
            try:self.queue.put_nowait(self.active)
            except Full:self.failed=True
        self.active=None
    def close(self):
        self.finish()
        if self.directory and self.thread.is_alive():
            try:self.queue.put(None,timeout=1)
            except Full:self.failed=True
            self.thread.join(timeout=3)

class DynamicsService:
    def __init__(self,directory=None,clock=time.monotonic):
        self.clock=clock;self.value=Dynamics();self.stamps={};self.recorder=EventRecorder(directory,clock=clock);self.previous_trigger=(0,0);self.was_online=False
    def ingest(self,fid,data,direction="RX"):
        self.recorder.record(fid,data,direction)
        if fid==0x229 and len(data)==8 and direction=="RX":
            self.recorder.context["firmware_calibration_fingerprint"]=bytes(data).hex()
            self.value=replace(self.value,calibration_matches=bytes(data).hex()==self.recorder.context["calibration_sha256"][:16])
            self.stamps[fid]=self.clock();return
        if direction!="RX" or fid not in IDS or len(data)!=8 or data[0]!=1:return
        v=self.value
        if fid==0x220:
            if data[1]>=len(STATES) or data[2]>=len(EVENTS) or data[3]>3 or data[4]>3 or data[5]>2:return
            v=replace(v,state=STATES[data[1]],event=EVENTS[data[2]],tcs=data[3],awc=data[4],curve=data[5],flags=data[6],ack=data[7])
        elif fid==0x221:
            if any(x>100 for x in data[1:]):return
            v=replace(v,**dict(zip(("rider","permitted","tcs_limit","awc_limit","lean_limit","engine_limit","mode_limit"),data[1:])))
        elif fid==0x222:
            if data[7]>100:return
            f,r,s=struct.unpack(">HHH",data[1:7]);v=replace(v,front=f/100,rear=r/100,speed=s/100,sensor_confidence=data[7])
        elif fid==0x223:
            p,l,r=struct.unpack(">hhh",data[1:7]);v=replace(v,pitch=p/100,lean=l/100,pitch_rate=r/100)
        elif fid==0x224:
            if any(x>100 for x in data[5:]):return
            slip,target=struct.unpack(">hh",data[1:5]);v=replace(v,slip=slip/100,slip_target=target/100,slip_confidence=data[5],wheelie_confidence=data[6],front_contact=data[7])
        elif fid==0x225:
            if data[7]>100:return
            cmd,actual,boost=struct.unpack(">HHH",data[1:7]);v=replace(v,throttle_target=cmd/100,throttle_actual=actual/100,boost_target=boost/10,air_margin=data[7])
        elif fid==0x226:
            if data[6]>=len(WEATHER) or data[5]>100 or data[7]>1:return
            v=replace(v,faults=int.from_bytes(data[1:5],"big"),sensor_confidence=data[5],weather=data[6],calibrated=bool(data[7]))
        elif fid==0x227:
            if data[7]>1:return
            target,maximum=struct.unpack(">HH",data[1:5]);v=replace(v,wheelie_target=target/100,wheelie_max=maximum/100,lean_left=data[5],lean_right=data[6],weather_assist=bool(data[7]))
        self.stamps[fid]=self.clock();self.value=v
        trigger=(v.flags&7,v.faults)
        # First complete telemetry set prevents fabricated zero-valued startup
        # event summaries before pitch/torque frames have arrived.
        if IDS.issubset(self.stamps):
            if trigger!=self.previous_trigger and any(trigger):self.recorder.trigger(v)
            self.previous_trigger=trigger
    def snapshot(self):
        now=self.clock()
        online=all(fid in self.stamps and now-self.stamps[fid]<=.3 for fid in IDS)
        if self.was_online and not online:self.recorder.trigger(replace(self.value,event="TELEMETRY LOST"))
        self.was_online=online
        if self.recorder.active and now>=self.recorder.active["until"]:self.recorder.finish()
        return replace(self.value,online=online,calibration_matches=self.value.calibration_matches and 0x229 in self.stamps and now-self.stamps[0x229]<=.3,history=tuple(self.recorder.history),logging_fault=self.recorder.failed)
    def close(self):self.recorder.close()
