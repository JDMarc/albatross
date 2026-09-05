"""Synthetic HUD telemetry only. No DBWX2 target, raw-sensor spoof or calibration writes."""
from dataclasses import replace
import hashlib,json,math,struct,time
from pathlib import Path
from . import dynamics as vd
from . import airshot as air
from .thermal import ThermalService,SensorStatus
from .thermal.simulation import ThermalSimulator,SCENARIOS
from .thermal.config import DEFAULT_CONFIG_PATH
from .thermal.summary import primary_temperatures

# key, label, initial value, choices (None = numeric entry). Values are DEMO ONLY.
DYNAMICS_FIELDS=[
 ("vdc_stream","Transmit dynamics telemetry",True,None),
 ("vdc_state","State","TCS MONITOR",vd.STATES),("vdc_event","Event","NORMAL",vd.EVENTS),
 ("vdc_tcs","TCS","MED",vd.LEVELS),("vdc_awc","AWC","MED",vd.LEVELS),
 ("vdc_curve","Curve",0,(0,1,2,3)),("vdc_weather","Weather","UNKNOWN",vd.WEATHER),
 ("vdc_weather_assist","Weather assist",True,None),("vdc_calibrated","Simulated calibration-valid flag",False,None),
 ("vdc_hash_match","Match local config fingerprint",True,None),
 ("vdc_flags","Flags: TCS=1 AWC=2 lift=4 air=8 DBW=16",16,None),
 ("vdc_ack","Settings ACK byte",0,None),
 *[("vdc_"+k,label,v,None) for k,label,v in (
  ("rider","Rider torque %",40),("permitted","Permitted torque %",40),
  ("tcs_limit","TCS limit %",100),("awc_limit","AWC limit %",100),("lean_limit","Lean limit %",100),
  ("engine_limit","Engine limit %",100),("mode_limit","Mode limit %",100),
  ("front","Front speed m/s",20),("rear","Rear speed m/s",20),("speed","Estimated speed m/s",20),
  ("pitch","Pitch deg",0),("lean","Lean deg",0),("pitch_rate","Pitch rate deg/s",0),
  ("slip","Rear slip %",0),("slip_target","Slip target %",9),
  ("slip_confidence","Slip confidence %",0),("wheelie_confidence","Lift confidence %",0),
  ("front_contact","Front contact %",100),("sensor_confidence","Sensor confidence %",100),
  ("throttle_target","DBW target deg",20),("throttle_actual","DBW actual deg",20),
  ("boost_target","Boost target psi",4),("air_margin","Air Shot margin %",100),
  ("wheelie_target","Wheelie target deg (demo)",0),("wheelie_max","Wheelie maximum deg (demo)",0),
  ("lean_left","Left lean bound deg (demo)",0),("lean_right","Right lean bound deg (demo)",0))]]
AIR_FIELDS=[
 ("air_stream","Transmit Air Shot V2 telemetry",True,None),
 ("air_mode","Mode","OFF",air.MODES),("air_state","State","DISABLED",air.STATES),
 ("air_reason","Reason","OFF",air.REASONS),("air_profile","Profile","MID TRANSIENT",air.PROFILES),
 ("air_pressure_valid","Pressure valid",True,None),("air_compressor","Compressor","OFF",("OFF","FILLING","COOLDOWN","FAULT")),
 *[("air_"+k,label,v,None) for k,label,v in (
  ("demand","Demand %",0),("available","Available %",80),("flags","Request/accepted/shadow flags",0),
  ("intake_l","Intake left %",0),("intake_r","Intake right %",0),("turbine_l","Turbine left %",0),("turbine_r","Turbine right %",0),
  ("predicted_il","Shadow intake left %",0),("predicted_ir","Shadow intake right %",0),("predicted_tl","Shadow turbine left %",0),("predicted_tr","Shadow turbine right %",0),
  ("driver_faults","Driver fault mask",0),("event_id","Event ID",0),("tank","Tank psi",120),("regulated","Regulated psi",60),
  ("used","Pressure used psi",0),("duration","Last duration ms",0),("tank_before","Tank before psi",120),
  ("stage","Stage",0),("calibration_version","Calibration version",0),
  ("config_ack","Configuration ACK status",0),("config_pins","Configured pins flag",0),("config_count","Configuration field count",0),("config_token","Configuration token",0))]]

def defaults():
    return {k:v for k,_,v,_ in DYNAMICS_FIELDS+AIR_FIELDS}

def number(values,key,lo,hi,scale=1):
    value=float(values[key])
    if not math.isfinite(value):raise ValueError(f"{key}: finite number required")
    return round(max(lo,min(hi,value))*scale)

class DemoSystems:
    def __init__(self):
        self.values=defaults();self.faults=0;self.thermal=ThermalSimulator();self.sequence=0
        self.thermal_stream=True;self.thermal_overrides={};self.thermal_raw={}
        self.thermal_crc=ThermalService.config_crc32(DEFAULT_CONFIG_PATH)
        data=json.loads((Path(__file__).resolve().parents[1]/"config/vdc_engineering.json").read_text())
        self.fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).digest()[:8]
    def frames(self):
        v=self.values;out=[]
        def n(k,lo=0,hi=100,scale=1):return number(v,k,lo,hi,scale)
        if v["vdc_stream"]:
            flags=n("vdc_flags",0,31);faults=self.faults
            out += [(0x229,self.fingerprint if v["vdc_hash_match"] else bytes(8)),
             (0x220,bytes((1,vd.STATES.index(v["vdc_state"]),vd.EVENTS.index(v["vdc_event"]),vd.LEVELS.index(v["vdc_tcs"]),vd.LEVELS.index(v["vdc_awc"]),n("vdc_curve",0,3),flags,n("vdc_ack",0,255)))),
             (0x221,bytes([1]+[n("vdc_"+k) for k in ("rider","permitted","tcs_limit","awc_limit","lean_limit","engine_limit","mode_limit")])),
             (0x222,struct.pack(">BHHHB",1,*[n("vdc_"+k,0,655.35,100) for k in ("front","rear","speed")],n("vdc_sensor_confidence"))),
             (0x223,struct.pack(">BhhhB",1,*[n("vdc_"+k,-327.68,327.67,100) for k in ("pitch","lean","pitch_rate")],0)),
             (0x224,struct.pack(">BhhBBB",1,n("vdc_slip",-327.68,327.67,100),n("vdc_slip_target",-327.68,327.67,100),n("vdc_slip_confidence"),n("vdc_wheelie_confidence"),n("vdc_front_contact"))),
             (0x225,struct.pack(">BHHHB",1,n("vdc_throttle_target",0,655.35,100),n("vdc_throttle_actual",0,655.35,100),n("vdc_boost_target",0,6553.5,10),n("vdc_air_margin"))),
             (0x226,struct.pack(">BIBBB",1,faults,n("vdc_sensor_confidence"),vd.WEATHER.index(v["vdc_weather"]),bool(v["vdc_calibrated"]))),
             (0x227,struct.pack(">BHHBBB",1,n("vdc_wheelie_target",0,655.35,100),n("vdc_wheelie_max",0,655.35,100),n("vdc_lean_left",0,255),n("vdc_lean_right",0,255),bool(v["vdc_weather_assist"]))),
             (0x228,struct.pack(">BfBBB",1,float(v["vdc_boost_target"]),0,0,0))]
        if v["air_stream"]:
            out += [(0x180,bytes((2,air.MODES.index(v["air_mode"]),air.STATES.index(v["air_state"]),air.REASONS.index(v["air_reason"]),air.PROFILES.index(v["air_profile"]),n("air_demand"),n("air_available"),n("air_flags",0,255)))),
             (0x181,struct.pack(">BBBBBBH",2,*[n("air_"+k) for k in ("intake_l","intake_r","turbine_l","turbine_r")],n("air_driver_faults",0,255),n("air_event_id",0,65535))),
             (0x182,struct.pack(">BHHHB",2,*[n("air_"+k,0,6553.5,10) for k in ("tank","regulated","used")],bool(v["air_pressure_valid"]))),
             (0x183,struct.pack(">BHHHB",2,n("air_event_id",0,65535),n("air_duration",0,65535),n("air_tank_before",0,6553.5,10),n("air_stage",0,255))),
             (0x184,struct.pack(">BBBBBHB",2,*[n("air_predicted_"+k) for k in ("il","ir","tl","tr")],n("air_calibration_version",0,65535),("OFF","FILLING","COOLDOWN","FAULT").index(v["air_compressor"]))),
             (0x185,struct.pack(">BBBBHH",2,n("air_config_ack",0,255),n("air_config_pins",0,1),n("air_stage",0,255),n("air_config_count",0,65535),n("air_config_token",0,65535)))]
        if self.thermal_stream:
            snap=self.thermal.step(.1);p=self.thermal.service.config.protocol;self.sequence=(self.sequence+1)&255
            if self.thermal.scenario!="can_dropout" or self.thermal.elapsed_s<8:out.append((p.heartbeat_id,struct.pack(">BBBIB",p.version,p.node_id,0,int(self.thermal.elapsed_s),self.sequence)))
            values=[];statuses=[]
            for sensor in self.thermal.service.config.sensors:
                reading=snap.get(sensor.key);value,status=self.thermal_overrides.get(sensor.key,(reading.temperature_c,reading.status))
                values.append(p.invalid_raw if value is None or status!=SensorStatus.VALID else number({"t":value},"t",-3276.7,3276.7,10));statuses.append(int(status))
            for g in range(8):out.append((p.value_base_id+g,struct.pack(">hhhh",*values[g*4:g*4+4])))
            for g in range(4):
                s=statuses[g*8:g*8+8];out.append((p.status_base_id+g,bytes((s[k]<<4)|s[k+1] for k in range(0,8,2))))
                out.append((p.fault_base_id+g,bytes((sum(1<<k for k,status in enumerate(s) if status not in (0,8)),))))
            version=[int(x) for x in self.thermal.service.config.configuration_version.removeprefix('thermal-').split('.')[:3]]
            out.append((p.config_id,struct.pack(">IBBBB",self.thermal_crc,*(version+[0]*3)[:3],32)))
            sensors=self.thermal.service.config.sensors
            for g in range(8):
                raw=[number({"raw":self.thermal_raw.get(sensor.key,0)},"raw",0,65535) for sensor in sensors[g*4:g*4+4]]
                out.append((p.raw_base_id+g,struct.pack(">HHHH",*raw)))
        return out

class DemoReceiver:
    """UDP demo-mode-only bridge into production decoders. Never sends CAN."""
    def __init__(self,clock=time.monotonic):
        self.dynamics=vd.DynamicsService(clock=clock);self.air=air.AirShotService(clock=clock);self.thermal=ThermalService(clock=clock)
        self.allowed=self.thermal.can_ids|set(range(0x180,0x186))|set(range(0x220,0x22A));self.active=False;self.alerts=set()
    def apply(self,state,frames):
        if not isinstance(frames,list) or len(frames)>64:raise ValueError("Invalid demo frame list")
        parsed=[]
        for row in frames:
            if not isinstance(row,(list,tuple)) or len(row)!=2 or type(row[0]) is not int or row[0] not in self.allowed or not isinstance(row[1],str):raise ValueError("Not HUD telemetry")
            data=bytes.fromhex(row[1])
            if not 1<=len(data)<=8:raise ValueError("Invalid DLC")
            parsed.append((row[0],data))
        if parsed:self.active=True
        if not self.active:return state
        for fid,data in parsed:
            self.dynamics.ingest(fid,data);self.air.ingest(fid,data);self.thermal.apply_can_frame(fid,data)
        self.thermal.set_vehicle_context({"rpm":state.engine.rpm,"load_pct":state.engine.engine_load_pct,"boost_psi":state.engine.boost_psi,"ambient_c":(state.environment.ambient_temp_f-32)*5/9,"wmi_command":state.wmi.commanded_flow_cc_min})
        d,a,t=self.dynamics.snapshot(),self.air.snapshot(),self.thermal.snapshot()
        alerts=set(d.alerts)|set(a.alerts)|set(t.alerts);faults=(set(state.faults)-self.alerts)|alerts;self.alerts=alerts
        return replace(state,dynamics=d,air_shot=replace(state.air_shot,v2=a),thermal=t,
                       temps=primary_temperatures(state.temps,t),faults=tuple(sorted(faults)))
