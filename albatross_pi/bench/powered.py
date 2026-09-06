"""USB requests to the dedicated bench Teensy, never direct DBWX2 CAN writes."""
import json
import math
import time

STATES = ('IDLE','ARMED','ACTIVE','FAULT LATCHED')
REASONS = ('READY','CONFIGURATION REQUIRED','ARM REQUIRES RELEASED DEADMAN / START POSITION','BENCH KEY OFF','DEADMAN RELEASED',
 'HOST LEASE EXPIRED','ARM EXPIRED','RUN DURATION ENDED','FEEDBACK INVALID / STALE',
 'DBWX2 DRIVER / STATUS FAULT','CURRENT FAULT','TPS PLAUSIBILITY FAULT',
 'TRACKING FAULT','STOP REQUESTED','LINK / SCHEDULING FAULT','OTHER CAN COMMAND WRITER')


class PoweredLink:
    def __init__(self, port, profile, *, factory=None, clock=time.monotonic):
        if type(profile) is not int or profile <= 0: raise ValueError('A nonzero fixture revision is required')
        if factory is None:
            import serial
            factory = serial.Serial
        self.serial = factory(port=port,baudrate=115200,timeout=0,write_timeout=.05)
        self.clock=clock; self.profile=profile; self.status={}; self.at=None
        self.buffer=bytearray(); self.error=''; self.seq=0; self.holding=False
        self.inhibited=True; self.last_send=-math.inf; self.rows=[]
        self.arm_pending=None
        self.send('STOP')

    def send(self, command):
        wire=(command+'\n').encode('ascii')
        try:
            if self.serial.write(wire)!=len(wire): raise OSError('Incomplete USB write')
            self.rows.append(dict(event='TX',time_s=self.clock(),command=command))
            return True
        except Exception as exc:
            self.error='USB WRITE FAILED: '+str(exc); self.inhibited=True; self.holding=False
            return False

    def fresh(self):
        budget=min(.25,max(.001,self.status.get('lease_ms',0)/1000)) if self.status.get('configured') else .25
        return self.at is not None and 0 <= self.clock()-self.at < budget

    def ready(self):
        return self.fresh() and self.status.get('configured')==1 and self.status.get('profile')==self.profile and self.status.get('lease_ms',0)>0 and self.status.get('max',0)>0

    def poll(self):
        try:
            data=self.serial.read(4096)
            self.buffer.extend(data)
            if len(self.buffer)>8192: raise ValueError('Oversized USB telemetry')
            while b'\n' in self.buffer:
                line,_,remaining=self.buffer.partition(b'\n'); self.buffer=bytearray(remaining)
                row=json.loads(line)
                required=('protocol','profile','configured','epoch','seq','state','reason','key','deadman','permit','good','target','actual','current_ma','max','lease_ms')
                if not isinstance(row,dict) or any(type(row.get(k)) is not int for k in required): raise ValueError('Malformed bench status')
                if row['protocol']!=1 or not 0<=row['state']<len(STATES) or not 0<=row['reason']<len(REASONS): raise ValueError('Unsupported bench firmware')
                if any(row[k] not in (0,1) for k in ('configured','key','deadman','permit','good')): raise ValueError('Invalid status flags')
                if not 0<row['epoch']<=0xffffffff or not 0<=row['seq']<=0xffffffff or not 0<=row['max']<=1000 or not 0<=row['target']<=1000 or not 0<=row['lease_ms']<0x80000000: raise ValueError('Invalid status bounds')
                if row['epoch']!=self.status.get('epoch',row['epoch']) or row['state']==3:
                    self.arm_pending=None
                    self.inhibited=True; self.holding=False
                self.status=row; self.at=self.clock()
                if self.arm_pending==row['epoch'] and row['state']==1 and self.ready() and not self.error:
                    self.arm_pending=None; self.inhibited=False
                elif row['state']==0:
                    self.inhibited=True; self.holding=False
                self.rows.append(dict(event='RX',time_s=self.at,status=dict(row)))
        except Exception as exc:
            self.error='USB TELEMETRY FAILED: '+str(exc); self.stop()
        if not self.ready() and not self.inhibited: self.stop()
        if len(self.rows)>500: self.rows=self.rows[-500:]

    def arm(self):
        s=self.status
        if self.error or not self.ready() or s['state']!=0 or not s['good'] or not s['key'] or s['deadman']: return False
        self.seq=0; self.holding=False
        # Wait for ARMED acknowledgement before permitting HOLD transmission.
        sent=self.send('ARM '+str(s['epoch']))
        self.inhibited=True
        self.arm_pending=s['epoch'] if sent else None
        return sent

    def drive(self, held, target):
        s=self.status
        if not held:
            if self.holding: self.stop()
            return
        if self.error or self.inhibited or not self.ready() or s.get('state') not in (1,2): return
        if not s.get('key') or not s.get('deadman') or not s.get('good'):
            if self.holding: self.stop()
            return
        if type(target) is not int or not 0<=target<=s['max']: self.stop(); return
        now=self.clock()
        if now-self.last_send < .02: return  # 50 Hz host lease stream
        self.seq+=1
        if self.seq>0xffffffff: self.stop(); return
        if self.send(f'HOLD {s["epoch"]} {self.seq} {target}'):
            self.holding=True; self.last_send=now

    def stop(self):
        self.arm_pending=None
        self.inhibited=True; self.holding=False
        self.send('STOP')

    def close(self):
        try: self.stop()
        finally: self.serial.close()
