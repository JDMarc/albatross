"""Reject malformed/uncommissioned protection settings before code generation."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.generate_fault_config import generate,ROOT
from tools.replay_fault_log import replay

def check():
    original=json.loads((ROOT/'config/fault_manager.json').read_text())
    generate(original)
    def reject(mutate):
        config=copy.deepcopy(original);mutate(config)
        try:generate(config)
        except (ValueError,TypeError):return
        raise AssertionError('invalid configuration accepted')
    reject(lambda c:c['rules'].reverse())
    reject(lambda c:c['rules'][0].update(confirm_ms=-1))
    reject(lambda c:c['rules'][0].update(torque=True))
    reject(lambda c:c['rules'][0].update(severity='UNKNOWN'))
    reject(lambda c:c['monitors']['fuel_dp'].update(enabled=True))
    reject(lambda c:c['monitors']['fuel_dp'].update(confirm_ms=-1))
    reject(lambda c:c.update(fuel_fusion_enabled=True))
    reject(lambda c:c['master_air_isolation'].update(driver_verified='false'))
    # Feed the same wire bundle through the production decoder, no CAN adapter.
    frames=[(0x240,bytes((1,0,3,255,0,0,0,1))),
            (0x241,bytes((1,100,255,255,255,255,0,1))),
            (0x243,bytes((1,0,0,0,0,0,0,1)))]
    rows=[dict(time_s=1+n*.01,frame_id=fid,data=data.hex(),direction='RX') for n,(fid,data) in enumerate(frames)]
    events=list(replay(rows));assert events[-1]['online'] and events[-1]['rideability']=='FULL'
    print('PASS fault configuration guards and read-only telemetry replay')

if __name__=='__main__':check()
