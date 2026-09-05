"""Fault CAN atomicity/staleness, event windows and existing HUD fault routing."""
import sys,struct,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.fault_manager import FaultService
from albatross_pi.fault_manager.snapshot_logger import SnapshotLogger
from albatross_pi.canbus.decode import CANStateAggregator

def bundle(seq=1,mask=2):
    return ((0x240,bytes((1,1,3,0xF1,0,1,0,seq))),
            (0x241,bytes((1,100,0,80,255,255,0,seq))),
            (0x243,bytes((1,))+struct.pack('>I',mask)+bytes((0,0,seq))))
def check():
    now=[1.0];s=FaultService(clock=lambda:now[0]);frames=bundle()
    for fid,data in frames[:2]:s.ingest(fid,data)
    assert not s.snapshot().online
    s.ingest(*frames[2]);snap=s.snapshot();assert snap.online and 'THERMAL OFFLINE' in snap.alerts
    assert snap.torque_ceiling==1 and snap.boost_ceiling==8 and snap.rpm_ceiling is None
    s.ingest(0x245,bytes((1,1,1,3,0,0,0,0)))
    assert s.snapshot().master_isolation['commanded_open']
    assert s.snapshot().master_isolation['physical_quality']=='INVALID'
    for fid,data in bundle(2,0):s.ingest(fid,data,'TX')
    assert s.snapshot().active==2
    # Mixed generations cannot refresh a complete bundle.
    s.ingest(*bundle(2)[0]);s.ingest(*bundle(3)[1]);s.ingest(*bundle(2)[2]);now[0]=1.31
    assert not s.snapshot().online and s.snapshot().torque_ceiling is None
    for fid,data in bundle(4,0):s.ingest(fid,data)
    assert s.snapshot().online and not s.snapshot().alerts
    assert not s.snapshot().master_isolation
    aggregator=CANStateAggregator()
    for fid,data in bundle():aggregator.apply_frame(fid,data)
    assert 'THERMAL OFFLINE' in aggregator.current_snapshot().faults
    for fid,data in bundle(2,0):aggregator.apply_frame(fid,data)
    assert 'THERMAL OFFLINE' not in aggregator.current_snapshot().faults
    with tempfile.TemporaryDirectory() as directory:
        log=SnapshotLogger(directory,clock=lambda:now[0],pre_s=10,post_s=20)
        now[0]=2;log.observe(0x100,b'pre','RX',s.snapshot())
        for fid,data in bundle(5,2):s.ingest(fid,data)
        log.observe(0x243,b'fault','RX',s.snapshot())
        now[0]=3
        for fid,data in bundle(6,0):s.ingest(fid,data)
        log.observe(0x100,b'post','RX',s.snapshot())
        now[0]=23;log.observe(0x100,b'end','RX',s.snapshot());log.close()
        assert not log.failed
        rows=[json.loads(line) for line in log.path.read_text().splitlines()]
        assert any(row.get('event')=='FAULT' for row in rows)
        assert any(row.get('data')==b'pre'.hex() for row in rows)
        assert any(row.get('data')==b'post'.hex() for row in rows)
        assert rows[-1]['event']=='WINDOW_END'
    print('PASS fault bundles, TX rejection, staleness, clear/recur routing and pre/post event capture')
if __name__=='__main__':check()
