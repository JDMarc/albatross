"""Read-only wire observations. Exact IDs/layouts from the current firmware.

Does not infer raw APS/TPS from aggregate percentages. DBWX2 native read replies
are decoded only when explicitly enabled for verified 0.92 layouts and matched
to an observed request. No polling or command packets are generated.
"""
import struct
from ..fault_manager.telemetry import FaultService


def msid(offset, kind, sender, receiver, table):
    return (offset << 18) | (kind << 15) | (sender << 11) | (receiver << 7) | (table << 3)


class BenchDecoder:
    def __init__(self, model, *, native_v092=False, local_node=9, dbwx2_node=10):
        if not (0 <= local_node <= 14 and 0 <= dbwx2_node <= 14 and local_node != dbwx2_node):
            raise ValueError('Invalid/duplicate native node IDs')
        self.model = model
        self.native = native_v092
        self.local_node = local_node
        self.dbwx2_node = dbwx2_node
        self.pending = None
        self.faults = FaultService(clock=lambda: model.time)

    def ingest(self, fid, data, *, extended=False, remote=False, error=False, direction='RX'):
        m = self.model
        if error:
            m.transport_error = 'CAN error frame observed'
        if remote or error or direction != 'RX' or len(data) > 8:
            m.rejected += 1
            return
        m.frames += 1
        if extended:
            self._native(fid, data)
            return
        if fid > 0x7ff:
            m.rejected += 1
            return
        self.faults.ingest(fid, data)
        if fid == 0x225 and len(data) == 8 and data[0] == 1:
            target, actual, boost = struct.unpack('>HHH', data[1:7])
            # VDC serialization can turn unavailable values into zero. Mark
            # this as reported telemetry, not independently verified feedback.
            m.put('DBW target', target/100, 'deg', source=m.mode+' / VDC reported')
            m.put('DBW reported raw', actual/100, 'deg', source=m.mode+' / VDC unverified')
            m.put('Boost target', boost/10, 'psi')
        elif fid == 0x226 and len(data) == 8 and data[0] == 1:
            m.put('VDC faults', int.from_bytes(data[1:5], 'big'), 'mask')
            m.put('VDC calibrated', data[7], 'flag', valid=data[7] <= 1)
        elif fid == 0x194 and len(data) == 6 and data[0] == 2:
            good = data[5] == 1 and all(v <= 100 for v in data[1:5])
            for n, axis in enumerate(('EWG LEFT', 'EWG RIGHT')):
                m.put(axis+' target', data[n+1], '%', valid=good)
                m.put(axis+' actual', data[n+3], '%', valid=good)
        elif fid == 0x100 and len(data) == 2:
            m.put('RPM', int.from_bytes(data, 'big'), 'rpm')
        elif fid == 0x10c and len(data) == 2:
            m.put('Battery', int.from_bytes(data, 'big')/1000, 'V')
        elif fid == 0x182 and len(data) == 8 and data[0] == 2:
            for n, key in enumerate(('Air tank', 'Air regulated')):
                m.put(key, int.from_bytes(data[1+n*2:3+n*2], 'big')/10, 'psi', valid=data[7] == 1)
        elif 0x198 <= fid <= 0x19b and len(data) == 5 and data[0] == 2:
            n = fid-0x198
            m.put('Air valve '+str(n+1)+' current', int.from_bytes(data[1:3], 'big')/1000, 'A')
            m.put('Air valve '+str(n+1)+' fault', data[3], 'mask')

    def _native(self, fid, data):
        if not self.native: return
        m = self.model
        for offset, length in ((0,8), (64,4), (76,8), (60,4)):
            request = msid(offset, 1, self.local_node, self.dbwx2_node, 5)
            if fid == request and len(data) == 3 and data[0] == 6 and data[2] & 31 == length:
                token = (data[1] << 3) | (data[2] >> 5)
                self.pending = (msid(token, 2, self.dbwx2_node, self.local_node, 6), offset, length, m.time)
                return
        if self.pending is None: return
        reply, offset, length, at = self.pending
        if m.time-at > .3:
            self.pending = None
            return
        if fid != reply or len(data) != length: return
        self.pending = None
        if offset == 0:
            for key, value in zip(('APS1 raw', 'APS2 raw', 'TPS1 raw', 'TPS2 raw'), struct.unpack('<HHHH', data)):
                m.put(key, value, 'counts', source=m.mode+' / DBWX2 0.92')
        elif offset == 64:
            m.put('DBW current', int.from_bytes(data[:2], 'little')*.01, 'A', source=m.mode+' / DBWX2 0.92')
        elif offset == 76:
            bad = int.from_bytes(data[:2], 'little') != 0 or data[4] != 1 or data[5] != 0 or data[7] & 0x1c != 0
            m.put('DBWX2 status fault', int(bool(bad)), 'flag')
        elif offset == 60:
            m.put('DBWX2 channel fault', int(bool(data[0] & 0x3e or data[1])), 'flag')

    def refresh(self):
        m = self.model
        raw = m.readings.get('DBW reported raw')
        if raw is not None:
            from dataclasses import replace
            faults = m.get('VDC faults')
            m.readings['DBW actual'] = replace(raw, valid=faults is not None and not int(faults) & (64|128|256|512))
        f = self.faults.snapshot()
        self.model.fault_names = list(f.alerts) + list(f.advisories)
        if f.online:
            self.model.reason = 'Fault manager: '+f.rideability+' / hardware commands unavailable'
        else:
            self.model.reason = 'Fault manager unavailable / health unknown / no hardware commands'
