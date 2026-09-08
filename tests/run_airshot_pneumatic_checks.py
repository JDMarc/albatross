"""Air Shot pneumatic annunciators must not manufacture readiness."""
import sys
from pathlib import Path
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from albatross_pi.airshot import AirShotV2, AirShotService
from albatross_pi.fault_manager.telemetry import FaultSnapshot
from albatross_pi.hud.airshot_status import airshot_pneumatic_status

air = AirShotV2(online=True, compressor="FILLING", pressure_valid=True,
                tank_psi=145, regulated_psi=90, state="FIRING")
master = FaultSnapshot(online=True, master_isolation={"configured":True,"commanded_open":True})
assert airshot_pneumatic_status(air, master) == ("PRIMED ?", "COMP ON CMD")
assert airshot_pneumatic_status(replace(air, online=False), master) == ("PRIMED --", "COMP --")
assert airshot_pneumatic_status(air, replace(master, online=False))[0] == "PRIMED --"
assert airshot_pneumatic_status(air, replace(master, master_isolation={}))[0] == "PRIMED --"
for configured, opened, expected in ((False,False,"PRIMED SETUP"),(True,False,"PRIMED NO")):
    m=replace(master,master_isolation={"configured":configured,"commanded_open":opened})
    assert airshot_pneumatic_status(air,m)[0]==expected
for status,label in (("OFF","COMP OFF"),("COOLDOWN","COMP WAIT"),("FAULT","COMP FAULT")):
    assert airshot_pneumatic_status(replace(air,compressor=status))[1]==label
# A stale telemetry bundle must also suppress a previously reported compressor.
clock=[0.0]
service=AirShotService(clock=lambda:clock[0])
service.value=air
service.stamps={fid:0.0 for fid in range(0x180,0x185)}
clock[0]=0.31
assert airshot_pneumatic_status(service.snapshot(),master)==("PRIMED --","COMP --")
print("PASS pneumatic command/proof distinction, unavailable and stale states")

from albatross_pi.fault_manager.telemetry import FaultService
for code,label in ((3,"PRIMING"),(4,"PRIMED"),(5,"PRIME FAULT"),(6,"PRIMED SIM")):
    svc=FaultService(clock=lambda:1.0)
    svc.ingest(0x245,bytes((1,1,int(code in (3,4)),3,1,code,0,0)))
    m=replace(master,master_isolation=svc.master)
    assert airshot_pneumatic_status(air,m)[0]==label
    old=dict(svc.master)
    svc.ingest(0x245,bytes((1,1,1,3,1,7,0,0)))
    assert svc.master==old
print("PASS versioned controller priming proof and malformed telemetry rejection")
