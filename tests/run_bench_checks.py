"""Offline bench tool regression checks; no CAN hardware required."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pygame
from albatross_pi.bench.model import BenchModel
from albatross_pi.bench.decoder import BenchDecoder, msid
from albatross_pi.bench.io import ReceiveOnlyCAN, Journal, Replay, export_report
from albatross_pi.bench.view import BenchView


def check():
    for mode in ('LIVE', 'REPLAY'):
        m = BenchModel(mode)
        assert not m.arm() and not m.run() and not m.configure(limit=80)
        assert not m.stop()
        assert not m.readings
    m = BenchModel()
    assert not m.run()
    assert not m.configure(axis=1, duration=-1) and m.axis == 0
    assert m.arm() and not m.configure(limit=80)
    m.tick(10)
    assert not m.run() and m.state == 'DISARMED'
    assert m.arm() and m.run()
    for n in range(1, 102): m.tick(10+n*.05)
    assert m.results[-1]['outcome'] == 'COMPLETED'
    assert m.results[-1]['hardware_acceptance'] is False
    for scenario in range(5):
        m = BenchModel()
        m.configure(scenario=scenario)
        m.arm(); m.run(); m.tick(.05)
        if scenario >= 3: assert m.results[-1]['outcome'] == 'ABORTED'
        else:
            m.tick(.4)
            assert m.results[-1]['reason'] == 'Application scheduling gap'
    m = BenchModel('LIVE'); d = BenchDecoder(m, native_v092=True)
    d.ingest(0x100, b'\x12\x34', extended=True)
    d.ingest(0x100, b'\x12\x34', direction='TX')
    d.ingest(0x100, b'\x12\x34', remote=True)
    assert m.get('RPM') is None
    d.ingest(0x100, b'\x12\x34')
    assert m.get('RPM') == 0x1234
    m.tick(.31)
    assert m.quality('RPM') == 'STALE'
    d.ingest(0x225, struct.pack('>BHHHB',1,2000,1900,100,0)); d.refresh()
    assert m.get('DBW actual') is None
    d.ingest(0x226, struct.pack('>BIBBB',1,0,100,0,1)); d.refresh()
    assert m.get('DBW actual') == 19
    d.ingest(0x226, struct.pack('>BIBBB',1,64,100,0,1)); d.refresh()
    assert m.get('DBW actual') is None
    token = 7
    reply = msid(token,2,10,9,6)
    raw = struct.pack('<HHHH',101,202,303,404)
    d.ingest(reply,raw,extended=True)
    assert m.get('APS1 raw') is None
    d.ingest(msid(0,1,9,10,5),bytes((6,token>>3,((token&7)<<5)|8)),extended=True)
    d.ingest(reply,raw,extended=True)
    assert m.get('TPS2 raw') == 404
    d.ingest(msid(64,1,9,10,5),bytes((6,0,4)),extended=True)
    m.tick(.7)
    d.ingest(msid(0,2,10,9,6),b'\x64\x00\x00\x00',extended=True)
    assert m.get('DBW current') is None

    class Bus:
        def __init__(self, **kwargs): self.once = True; self.closed = False
        def recv(self, timeout):
            assert timeout == 0
            if not self.once: return None
            self.once = False
            return SimpleNamespace(arbitration_id=0x100,data=b'\x00\x00',is_extended_id=False,
                is_remote_frame=False,is_error_frame=False,is_rx=True)
        def shutdown(self): self.closed = True
        def send(self, *args, **kwargs): raise AssertionError('TRANSMISSION FORBIDDEN')
    transport = ReceiveOnlyCAN('fake','fake',bus_factory=Bus)
    assert not hasattr(transport,'send')
    assert len(transport.poll()) == 1
    transport.close(); assert transport._bus.closed

    with tempfile.TemporaryDirectory() as tmp:
        journal = Journal(tmp,'LIVE')
        journal.add(dict(time_s=1,frame_id=0x100,data='0000',extended=False))
        journal.add(dict(time_s=2,frame_id=0x100,data='0100',extended=False))
        journal.close(); assert not journal.failed
        replay = Replay(journal.path)
        assert len(replay.due(0)) == 1 and not replay.finished
        assert len(replay.due(1)) == 1 and replay.finished
        path = export_report(tmp,m,journal)
        report = json.loads(path.read_text())
        assert not report['hardware_acceptance']
        assert report['signals']['RPM']['value'] is None
        assert 'position_unit' in path.with_suffix('.csv').read_text()
    pygame.init()
    surface = pygame.Surface((1280,720))
    for theme in ('green','amber','cyan'):
        m = BenchModel(); v = BenchView(m,theme)
        v.render(surface)
        v.click((338,220)); assert m.axis == 1
        v.focus = 4; v.key(pygame.K_RETURN)
        assert v.confirm and m.state == 'DISARMED'
        v.key(pygame.K_RETURN); assert m.state == 'ARMED'
        v.focus = 5; v.key(pygame.K_RETURN); assert m.state == 'RUNNING'
        v.key(pygame.K_SPACE); assert m.state == 'DISARMED'
        for tab in range(4): v.tab = tab; v.render(surface)
    pygame.quit()
    import bench_hud
    with tempfile.TemporaryDirectory() as tmp:
        with patch('pygame.event.get', return_value=[pygame.event.Event(pygame.QUIT)]):
            assert bench_hud.main(['--logs', tmp]) == 0
        assert list(Path(tmp).glob('bench_report_*.json'))
        for invalid in ('[]', '{"time_s":0,"frame_id":256,"data":null}'):
            path = Path(tmp)/'bad.jsonl'
            path.write_text(invalid)
            try: Replay(path)
            except ValueError: pass
            else: raise AssertionError('Malformed replay accepted')
    print('Bench checks passed: guards, freshness, decoding, no-TX, logging, replay, navigation, rendering')


if __name__ == '__main__': check()
