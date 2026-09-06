"""Host protocol tests with a fake USB fixture. Never sends to hardware."""
import json
import os
import tempfile
from unittest.mock import patch
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from albatross_pi.bench.powered import PoweredLink


class Serial:
    def __init__(self,**kwargs): self.incoming=b'';self.writes=[];self.closed=False
    def read(self,n): data=self.incoming[:n];self.incoming=self.incoming[n:];return data
    def write(self,data): self.writes.append(data);return len(data)
    def close(self):self.closed=True


def check():
    clock=[0.0];link=PoweredLink('FAKE',7,factory=Serial,clock=lambda:clock[0])
    assert link.serial.writes==[b'STOP\n']
    status=dict(protocol=1,profile=7,configured=1,epoch=1,seq=0,state=0,reason=0,key=1,deadman=0,permit=0,good=1,target=0,actual=0,current_ma=0,max=300,lease_ms=100)
    def publish(**updates):
        status.update(updates);link.serial.incoming+=json.dumps(status).encode()+b'\n';link.poll()
    publish();assert link.arm();link.drive(True,200)
    assert not any(x.startswith(b'HOLD') for x in link.serial.writes)
    publish() # old idle telemetry while ARM is in flight must not discard request
    publish(state=1);assert not link.inhibited
    publish(deadman=1);link.drive(True,200)
    assert link.serial.writes[-1]==b'HOLD 1 1 200\n'
    link.drive(False,200);assert link.serial.writes[-1]==b'STOP\n'
    before=len(link.serial.writes);link.drive(True,200);assert len(link.serial.writes)==before
    publish(epoch=2,state=0,deadman=0);assert link.arm();publish(state=1,deadman=1)
    clock[0]=.05;link.drive(True,200);clock[0]=.2;link.poll()
    assert link.inhibited and link.serial.writes[-1]==b'STOP\n'
    publish();link.drive(True,200);assert link.serial.writes[-1]==b'STOP\n'
    publish(epoch=3,state=0,deadman=0,profile=8);assert not link.arm()
    publish(profile=7,good=0);assert not link.arm()
    publish(good=1);assert link.arm();publish(state=1,deadman=1)
    link.drive(True,301);assert link.inhibited
    link.serial.incoming=b'{bad}\n';link.poll();assert link.error and link.inhibited
    link.close();assert link.serial.closed
    os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    import pygame
    import dbw_bench_hud
    fixture=PoweredLink('FAKE',7,factory=Serial)
    with tempfile.TemporaryDirectory() as tmp:
        with patch('albatross_pi.bench.powered.PoweredLink',return_value=fixture), patch('pygame.event.get',return_value=[pygame.event.Event(pygame.QUIT)]):
            assert dbw_bench_hud.main(['--port','FAKE','--profile','7','--logs',tmp])==0
        records=[json.loads(row) for row in next(Path(tmp).glob('*.jsonl')).read_text().splitlines()]
        assert records[0]['hardware_tx'] is True
        assert fixture.serial.closed and all(w==b'STOP\n' for w in fixture.serial.writes)
    print('PASS powered bench USB: handshake, dual hold, release, stale lease, profile mismatch, bounds, malformed data, stop-on-close')


if __name__=='__main__':check()
