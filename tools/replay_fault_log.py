"""Read-only replay of received fault telemetry; never opens CAN or drives outputs.

This reuses the live Pi decoder, not a simulation of unlogged physical signals
or a rerun of the embedded controller. Event metadata is not control evidence.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.fault_manager.telemetry import FaultService

def replay(rows):
    now=[0.0];service=FaultService(clock=lambda:now[0]);previous=None
    for row in rows:
        if 'frame_id' not in row:continue
        timestamp=float(row['time_s'])
        if timestamp<now[0]:raise ValueError('CAN rows must be chronological')
        now[0]=timestamp
        service.ingest(int(row['frame_id']),bytes.fromhex(row['data']),row.get('direction','RX'))
        snapshot=service.snapshot()
        state=(snapshot.online,snapshot.rideability,snapshot.active,snapshot.available,snapshot.actions,
               snapshot.torque_ceiling,snapshot.boost_ceiling,snapshot.rpm_ceiling)
        if state!=previous:
            yield dict(time_s=timestamp,online=snapshot.online,rideability=snapshot.rideability,
                active=snapshot.active,available=snapshot.available,actions=snapshot.actions,
                torque_ceiling=snapshot.torque_ceiling,boost_ceiling=snapshot.boost_ceiling,
                rpm_ceiling=snapshot.rpm_ceiling,alerts=snapshot.alerts)
            previous=state

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('log',type=Path)
    args=parser.parse_args()
    with args.log.open(encoding='utf-8') as handle:
        for event in replay(json.loads(line) for line in handle if line.strip()):print(json.dumps(event))
