from dataclasses import dataclass,field,replace
from pathlib import Path
import json,time

CONFIG=json.loads((Path(__file__).resolve().parents[2]/'config/fault_manager.json').read_text())
REGISTRY=CONFIG['rules']
STATES=('NORMAL','SUSPECT','CONFIRMED','ACTIVE','MITIGATING','DEGRADED','RECOVERING','CLEARED','LATCHED')
RIDES=('FULL','DEGRADED','LIMP','STOP_REQUIRED','ENGINE_PROTECT')
RESULTS=('NOT_REQUESTED','REQUESTED','CONTAINED','FAILED','UNAVAILABLE')

@dataclass(frozen=True)
class FaultSnapshot:
    online:bool=False
    rideability:str='UNKNOWN'
    available:int=0
    actions:int=0
    torque_ceiling:float|None=None
    boost_ceiling:float|None=None
    rpm_ceiling:float|None=None
    missing_calibration:bool=False
    active:int=0
    details:dict=field(default_factory=dict)
    alerts:tuple=()
    advisories:tuple=()
    estimates:dict=field(default_factory=dict)
    master_isolation:dict=field(default_factory=dict)

class FaultService:
    def __init__(self,clock=time.monotonic,timeout_s=.3):
        # Matches existing main ECU supervision timeout (300 ms), not a new
        # sensor calibration. Incomplete bundles never refresh freshness.
        self.clock=clock;self.timeout_s=timeout_s;self.at=None;self.pending={};self.details={};self.value=FaultSnapshot();self.seen=False;self.last_seq=None
        self.master={}
    def ingest(self,fid,data,direction='RX'):
        if direction!='RX' or fid not in (0x240,0x241,0x242,0x243,0x245) or len(data)!=8 or data[0]!=1:return
        now=self.clock()
        if fid==0x245:
            if data[1]>1 or data[2]>1 or data[3]>3:return
            self.master=dict(configured=bool(data[1]),commanded_open=bool(data[2]),
                physical_quality=('VALID','ESTIMATED','DEGRADED','INVALID')[data[3]],received_at=now)
            return
        if fid==0x242:
            _,index,state,severity,confidence,result,hi,lo=data
            if index>=len(REGISTRY) or state>=len(STATES) or severity>2 or confidence>100 or result>=len(RESULTS):return
            self.details[index]=dict(id=REGISTRY[index]['id'],source=REGISTRY[index]['source'],state=STATES[state],severity=severity,
                confidence=confidence,mitigation_result=RESULTS[result],count=(hi<<8)|lo,received_at=now)
            return
        seq=data[7]
        if self.pending and self.pending.get('seq')!=seq:self.pending={}
        self.pending['seq']=seq;self.pending[fid]=bytes(data)
        if not all(key in self.pending for key in (0x240,0x241,0x243)):return
        a,b,c=(self.pending[key] for key in (0x240,0x241,0x243));self.pending={}
        if seq==self.last_seq:return
        if a[1]>=len(RIDES) or b[1]>100 or a[6]>1:return
        mask=int.from_bytes(c[1:5],'big');available=int.from_bytes(a[2:4],'big')
        if available&~1023:return
        names=[r['name'] for index,r in enumerate(REGISTRY) if mask&(1<<index)]
        alerts=tuple(name for name in names if name!='PI OFFLINE')
        if a[6]:alerts+=('FAULT LIMIT CALIBRATION MISSING',)
        advisories=('PI OFFLINE',) if 'PI OFFLINE' in names else ()
        boost=int.from_bytes(b[2:4],'big');rpm=int.from_bytes(b[4:6],'big')
        self.value=FaultSnapshot(True,RIDES[a[1]],available,int.from_bytes(a[4:6],'big'),b[1]/100,
            None if boost==65535 else boost/10,None if rpm==65535 else rpm,bool(a[6]),mask,{},alerts,advisories)
        self.at=now;self.seen=True;self.last_seq=seq
    def snapshot(self):
        if self.at is None or self.clock()-self.at>self.timeout_s:
            return FaultSnapshot(alerts=('FAULT MANAGER DATA STALE',) if self.seen else ())
        # Details rotate more slowly; they are historical evidence with explicit
        # timestamps, not a source of current actuation authority.
        master=dict(self.master) if self.master and self.clock()-self.master['received_at']<=self.timeout_s else {}
        return replace(self.value,details=dict(self.details),master_isolation=master)
