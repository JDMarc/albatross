"""Receive-only CAN transport, bounded recording, and offline replay.

Application-level no-TX is not electrically silent CAN: an adapter can still
acknowledge frames. Configure adapter listen-only separately where required.
"""
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Full
import csv
import hashlib
import json
import math
import threading


class ReceiveOnlyCAN:
    def __init__(self, interface, channel, bitrate=500000, *, tty_baudrate=None, bus_factory=None):
        if bus_factory is None:
            import can
            if interface == 'gs_usb':
                from ..canbus.iface import _prefer_libusb_package_backend
                _prefer_libusb_package_backend()
            bus_factory = can.Bus
        options = dict(interface=interface, channel=channel, bitrate=bitrate)
        if tty_baudrate is not None: options['tty_baudrate'] = tty_baudrate
        self._bus = bus_factory(**options)
        self.error = ''

    def poll(self, maximum=128):
        rows = []
        try:
            for _ in range(maximum):
                frame = self._bus.recv(timeout=0)
                if frame is None: break
                rows.append(dict(frame_id=frame.arbitration_id, data=bytes(frame.data),
                    extended=frame.is_extended_id, remote=frame.is_remote_frame,
                    error=frame.is_error_frame, direction='RX' if frame.is_rx else 'TX'))
        except Exception as exc:
            self.error = 'CAN receive failed: '+str(exc)
        return rows

    def close(self):
        self._bus.shutdown()


class Journal:
    def __init__(self, directory, source, *, hardware_tx=False):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
        self.path = directory/('bench_'+source.lower()+'_'+stamp+'.jsonl')
        self.queue = Queue(maxsize=8192)
        self.failed = False
        self.dropped = 0
        self.closed = False
        self.thread = threading.Thread(target=self._write, daemon=True, name='bench-journal')
        root = Path(__file__).resolve().parents[2]
        hashes = {name:hashlib.sha256((root/'config'/name).read_bytes()).hexdigest()
                  for name in ('vdc_engineering.json', 'fault_manager.json', 'airshot_v2.json')}
        self.thread.start()
        self.add(dict(event='SESSION', schema='albatross-bench-1', source=source,
                      utc=datetime.now(timezone.utc).isoformat(), config_sha256=hashes,
                      hardware_tx=hardware_tx, hardware_acceptance=False))

    def add(self, row):
        if self.closed: return
        try: self.queue.put_nowait(row)
        except Full:
            self.failed = True
            self.dropped += 1

    def _write(self):
        try:
            with self.path.open('x', encoding='utf-8') as handle:
                while True:
                    row = self.queue.get()
                    if row is None: break
                    handle.write(json.dumps(row, allow_nan=False, separators=(',', ':'))+'\n')
                    if self.queue.empty(): handle.flush()
        except (OSError, ValueError, TypeError):
            self.failed = True

    def close(self):
        if self.closed: return
        self.add(dict(event='SESSION_END', dropped=self.dropped, recording_failed=self.failed))
        self.closed = True
        if self.thread.is_alive():
            try: self.queue.put(None, timeout=.5)
            except Full: self.failed = True
            self.thread.join(timeout=2)
            if self.thread.is_alive(): self.failed = True


def export_report(directory, model, journal=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = 'bench_report_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%f')
    path = directory/(stem+'.json')
    report = model.report()
    report['recording_failed'] = bool(journal and journal.failed)
    report['dropped_rows'] = journal.dropped if journal else 0
    report['journal'] = str(journal.path) if journal else None
    report['trace_axis'] = ('DBW', 'EWG LEFT', 'EWG RIGHT')[model.axis]
    with path.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    with path.with_suffix('.csv').open('x', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(('source', 'axis', 'position_unit', 'time_s', 'target', 'actual', 'current_a'))
        unit = 'deg' if model.axis == 0 and model.mode != 'SIM' else '%'
        for row in model.trace: writer.writerow((model.mode, report['trace_axis'], unit, *row))
    return path


class Replay:
    """Load bounded raw-CAN rows. A malformed log fails, rather than being healed."""
    def __init__(self, path):
        self.rows = []
        self.cursor = 0
        first = None
        previous = -math.inf
        with Path(path).open(encoding='utf-8') as handle:
            for line in handle:
                if len(line) > 262144: raise ValueError('Oversized log row')
                row = json.loads(line)
                if not isinstance(row, dict): raise ValueError('Log row must be an object')
                if 'frame_id' not in row: continue
                if len(self.rows) >= 200000: raise ValueError('Replay exceeds 200000 frames; split the log')
                at = row.get('time_s', row.get('monotonic_s'))
                if type(at) not in (int,float) or not math.isfinite(at) or at < previous:
                    raise ValueError('Frame timestamps must be finite and chronological')
                previous = at
                if first is None: first = at
                fid = row['frame_id']
                if type(fid) is not int or not 0 <= fid <= 0x1fffffff: raise ValueError('Invalid CAN ID')
                if not isinstance(row.get('data'), str): raise ValueError('CAN data must be a hex string')
                data = bytes.fromhex(row['data'])
                if len(data) > 8: raise ValueError('Only classic CAN is supported')
                # Older logs omit frame format. Infer extended only when ID
                # cannot be standard; never reinterpret a standard ID as native.
                flags = dict(extended=row.get('extended', fid > 0x7ff),
                             remote=row.get('remote', False), error=row.get('error', False))
                if any(type(v) is not bool for v in flags.values()): raise ValueError('Invalid CAN flags')
                direction = row.get('direction', 'RX')
                if direction not in ('RX','TX'): raise ValueError('Invalid direction')
                self.rows.append((at-first, dict(frame_id=fid, data=data, direction=direction, **flags)))
        if not self.rows: raise ValueError('No raw CAN frames in this log; SIM journals contain observations, not wire replay')
        self.duration = self.rows[-1][0]

    @property
    def finished(self):
        return self.cursor >= len(self.rows)

    def due(self, now, maximum=512):
        rows = []
        while not self.finished and self.rows[self.cursor][0] <= now and len(rows) < maximum:
            rows.append(self.rows[self.cursor])
            self.cursor += 1
        return rows
