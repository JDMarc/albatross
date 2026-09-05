"""Bounded, asynchronous raw-CAN event windows; never part of protection."""
from collections import deque
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
from queue import Queue,Full
import json,threading,time

class SnapshotLogger:
    def __init__(self,directory=None,clock=time.monotonic,pre_s=10,post_s=20):
        self.clock=clock;self.pre_s=pre_s;self.post_s=post_s
        self.pre=deque(maxlen=50000);self.queue=Queue(maxsize=8192)
        self.last_mask=0;self.until=None;self.failed=False;self.dropped=0;self.worker=None;self.path=None
        if directory:
            try:
                directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
                self.path=directory/('fault_windows_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.jsonl')
                self.worker=threading.Thread(target=self._write,daemon=True);self.worker.start()
            except OSError:self.failed=True
    def _enqueue(self,row):
        if not self.path:return
        try:self.queue.put_nowait(row)
        except Full:self.failed=True;self.dropped+=1
    def observe(self,fid,data,direction,snapshot):
        now=self.clock()
        row=dict(time_s=now,frame_id=fid,data=bytes(data).hex(),direction=direction)
        while self.pre and now-self.pre[0]['time_s']>self.pre_s:self.pre.popleft()
        if snapshot.online:
            new=snapshot.active&~self.last_mask;self.last_mask=snapshot.active
            if new:
                starting=self.until is None
                self.until=now+self.post_s
                # Stream prehistory as individual rows, not one huge queued object.
                self._enqueue(dict(event='FAULT',utc=datetime.now(timezone.utc).isoformat(),new_mask=new,
                    fault_manager=asdict(snapshot),pre_truncated=len(self.pre)==self.pre.maxlen,dropped=self.dropped))
                if starting:
                    for sample in self.pre:self._enqueue(sample)
            if snapshot.active and self.until is not None:self.until=now+self.post_s
        # Never clear an episode just because the manager went offline.
        if self.until is not None:
            self._enqueue(row)
            if now>=self.until:self._enqueue(dict(event='WINDOW_END',time_s=now,dropped=self.dropped));self.until=None
        self.pre.append(row)
    def _write(self):
        try:
            with self.path.open('a',encoding='utf-8') as handle:
                while True:
                    row=self.queue.get()
                    if row is None:handle.flush();return
                    handle.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
                    if self.queue.empty():handle.flush()
        except (OSError,ValueError):self.failed=True
    def close(self):
        if self.worker and self.worker.is_alive():
            try:self.queue.put(None,timeout=1)
            except Full:self.failed=True
            self.worker.join(timeout=2)
