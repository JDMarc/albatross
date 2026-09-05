"""Convert event raw CAN to 10ms held-input replay; invoke the native VDC binary.

Offline analysis, never a CAN transmitter. Wheel speeds/engine ceilings are sampled
telemetry, not original ISR timing: replay is not guaranteed bit-identical. Use a
matching compiled calibration and verified installation axis map. A pre-trigger
window cannot recreate unlogged earlier estimator history.
"""
import argparse,json,struct,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.dynamics import DynamicsService

def inputs(rows,timeout,accel_axis=(1,0,2),gyro_axis=(2,1,0),accel_sign=(1,1,1),gyro_sign=(1,1,1),imu_base=0x470,node=10):
    rows=sorted((r for r in rows if "frame_id" in r),key=lambda r:r["monotonic_s"])
    if not rows:return
    at=[rows[0]["monotonic_s"]];service=DynamicsService(clock=lambda:at[0]);stamps={};requests={}
    v=[0.]*38;v[30:33]=[2,2,0];v[33:37]=[float("nan")]*4
    origin=at[0];next_tick=origin;driver_fault=False;channel_fault=False
    def fresh(key):return key in stamps and at[0]-stamps[key]<=timeout
    def sample():
        d=service.snapshot();v[0]=round((at[0]-origin)*1000)+1
        v[1:3]=[d.front,d.rear];v[7:9]=[d.engine_limit/100,d.mode_limit/100]
        # The original front-valid decision is recorded in the fault mask. Raw
        # pulse timeout cannot distinguish an airborne slow wheel from a wire fault.
        v[20:22]=[int(fresh("wheels") and not d.faults&2),int(fresh("wheels") and not d.faults&4)]
        v[22]=int(fresh("accel") and fresh("gyro"));v[23]=v[24]=int(fresh("pairs"))
        v[25]=int(fresh("current") and fresh("status") and fresh("channel"))
        v[26]=int(all(fresh(fid) for fid in (0x100,0x101,0x102,0x105,0x106,0x104,0x108,0x10C)) and fresh("limits"))
        v[27]=int(driver_fault or channel_fault);v[29]=int(fresh("weather") and v[29] and d.weather_assist)
        v[30:33]=[d.tcs,d.awc,d.curve]
        if d.calibrated:v[33:37]=[d.wheelie_target,d.wheelie_max,d.lean_left,d.lean_right]
        return ','.join(str(x) for x in v)
    for row in rows:
        when=row["monotonic_s"]
        while next_tick<when:
            at[0]=next_tick;yield sample();next_tick+=.01
        at[0]=when;fid=row["frame_id"];data=bytes.fromhex(row["data"])
        service.ingest(fid,data,row.get("direction","RX"))
        if (fid==0x20A and data==b'\x01STOP\xa5') or (fid==0x127 and len(data)>=1 and data[0]==0):v[37]=1
        if fid==0x226 and len(data)==8 and data[0]==1 and int.from_bytes(data[1:5],"big")&8192:v[37]=1
        if fid in (imu_base,imu_base+1) and len(data) in (6,8):
            rate=fid==imu_base+1;raw=struct.unpack(">hhh",data[:6]);axis=gyro_axis if rate else accel_axis;sign=gyro_sign if rate else accel_sign
            v[12 if rate else 9:15 if rate else 12]=[raw[axis[n]]*sign[n]*(.36 if rate else .00980665) for n in range(3)]
            stamps["gyro" if rate else "accel"]=when
        if fid>0x7FF:
            offset=fid>>18;kind=(fid>>15)&7;source=(fid>>11)&15;dest=(fid>>7)&15;table=(fid>>3)&15
            if kind==1 and dest==node and table==5 and len(data)==3:
                requests[(source,(data[1]<<3)|(data[2]>>5))]=(offset,data[2]&31,when)
            if kind==2 and source==node and table==6:
                request=requests.pop((dest,offset),None)
                if request and len(data)==request[1] and when-request[2]<=timeout:
                    remote=request[0]
                    if remote==0 and len(data)==8:v[15:19]=struct.unpack("<HHHH",data);stamps["pairs"]=when
                    elif remote==64 and len(data)==4:v[19]=int.from_bytes(data[:2],"little")*.01;stamps["current"]=when
                    elif remote==76 and len(data)==8:driver_fault=int.from_bytes(data[:2],"little")!=0 or data[4]!=1 or data[5]!=0 or bool(data[7]&0x1C);stamps["status"]=when
                    elif remote==60 and len(data)==4:channel_fault=bool(data[0]&0x3E) or data[1]!=0;stamps["channel"]=when
        required={0x100:2,0x101:1,0x102:2,0x105:4,0x106:2,0x104:1,0x108:1,0x10C:2}
        if fid in required and len(data)>=required[fid]:stamps[fid]=when
        if fid==0x100 and len(data)>=2:v[3]=int.from_bytes(data[:2],"big")
        if fid==0x108 and len(data)>=1:v[4]=data[0]
        if fid==0x102 and len(data)>=2:v[5]=int.from_bytes(data[:2],"big")/10
        if fid==0x207 and len(data)==4 and data[0]==1:v[28]=int(data[2]==1);v[29]=int(data[1]==0);stamps["weather"]=when
        if fid==0x221 and len(data)==8:stamps["limits"]=when
        if fid==0x222 and len(data)==8:stamps["wheels"]=when
        # Original requested boost is separately logged by the main Teensy.
        if fid==0x228 and len(data)==8 and data[0]==1:v[6]=struct.unpack(">f",data[1:5])[0]
    at[0]=max(next_tick,at[0]);yield sample();service.close()

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("log",type=Path);p.add_argument("--binary",required=True);p.add_argument("--installation",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();rows=[json.loads(line) for line in a.log.read_text(encoding="utf-8").splitlines()]
    hw=json.loads(a.installation.read_text());timeout=rows[0]["context"]["calibration"]["values"]["timeout_ms"]
    if not timeout:raise SystemExit("Log has no measured timeout calibration; use a validated engineering log.")
    recorded=rows[0]["context"].get("firmware_calibration_fingerprint")
    binary_hash=subprocess.run([a.binary,"--fingerprint"],capture_output=True,text=True,check=True).stdout.strip()
    if not recorded or recorded!=binary_hash or recorded!=rows[0]["context"]["calibration_sha256"][:16]:raise SystemExit("Replay binary, logged firmware and logged calibration must match.")
    content='\n'.join(inputs(rows,timeout/1000,**hw))+'\n'
    result=subprocess.run([a.binary],input=content,text=True,capture_output=True,check=True)
    a.output.write_text(result.stdout,encoding="utf-8");print(result.stderr,file=sys.stderr)
    print("Offline replay written. Verify calibration hash matches binary; sampled telemetry is not ISR-exact.")
