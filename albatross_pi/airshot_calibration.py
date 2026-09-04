"""HUD-editable calibration and transactional CAN transfer."""
from pathlib import Path
import json
import math
import struct
import time
import secrets

ROOT=Path(__file__).resolve().parents[1]
FIELDS=json.loads((ROOT/"config/airshot_fields.json").read_text(encoding="utf-8"))

class CalibrationEditor:
    def __init__(self,path=Path("settings/airshot_v2.json")):
        self.path=Path(path); self.cursor=0; self.status="EDIT VALUES"; self.confirm=False
        source=self.path if self.path.exists() else ROOT/"config/airshot_v2.json"
        self.data=json.loads(source.read_text(encoding="utf-8"))
        self.send_callback=None
        self.busy=False
    def get(self,index):
        value=self.data
        for part in FIELDS[index]["path"].split("."):
            value=value[int(part)] if isinstance(value,list) else value[part]
        return value
    def set(self,index,value):
        parts=FIELDS[index]["path"].split(".");node=self.data
        for p in parts[:-1]:node=node[int(p)] if isinstance(node,list) else node[p]
        node[int(parts[-1]) if isinstance(node,list) else parts[-1]]=value
        self.confirm=False
    def move(self,delta): self.cursor=(self.cursor+delta)%(len(FIELDS)+1);self.confirm=False
    def adjust(self,delta):
        if self.cursor>=len(FIELDS): return
        field=FIELDS[self.cursor];value=self.get(self.cursor)
        if field["type"]=="bool": self.set(self.cursor,delta>0);return
        key=field["cpp"]
        step=0.05 if any(s in key for s in ("gain","trim","intake","turbine","minimum","maximum","auto_","balance","gear[","fuel[","ride[")) and not key.endswith("_ms") else 1
        if "rpm" in key:step=100
        if key.endswith("_ms"):step=10
        if "current" in key:step=0.05
        if key.endswith("pwm_hz"):step=10
        self.set(self.cursor,round(max(-1 if "pin" in key else 0,(0 if value is None else value)+delta*step),3))
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".tmp");temp.write_text(json.dumps(self.data,indent=2),encoding="utf-8");temp.replace(self.path)
    def select(self,stopped):
        if self.busy:return
        if not stopped:self.status="STOP ENGINE TO APPLY";return
        self.save()
        if self.cursor<len(FIELDS):self.status="DRAFT SAVED";return
        missing=[FIELDS[n]["cpp"] for n in range(len(FIELDS)) if self.get(n) is None]
        if missing:self.status="SET "+missing[0];return
        if not self.confirm:self.confirm=True;self.status="SELECT AGAIN TO APPLY TO TEENSY";return
        self.confirm=False
        if not self.send_callback:self.status="CAN UNAVAILABLE";return
        self.send_callback(self)
    def frames(self):
        self.token=secrets.randbits(16)
        values=[self.get(n) for n in range(len(FIELDS))]
        if any(v is None or not math.isfinite(float(v)) for v in values):raise ValueError("missing/nonfinite calibration")
        yield 0x19c,bytes((2,1,0xA5,self.token>>8,self.token&255,0,0,0))
        checksum=2166136261
        for n,v in enumerate(values):
            payload=struct.pack(">BHfB",2,n,float(v),0)
            for byte in payload[3:7]:checksum=((checksum^byte)*16777619)&0xffffffff
            yield 0x19d,payload
        yield 0x19e,struct.pack(">BIHB",2,checksum,len(values),0xA5)

def draw_calibration(surface,editor,colors):
    import pygame
    from .hud.widgets.ui_utils import font,fit_font_size
    bg,bright,glow,fault=colors
    w,h=surface.get_size();rect=pygame.Rect(24,54,w-48,h-84)
    pygame.draw.rect(surface,bg,rect);pygame.draw.rect(surface,glow,rect,2)
    surface.blit(font(18,bold=True).render("SETTINGS / AIR SHOT CALIBRATION",True,bright),(rect.x+14,rect.y+10))
    rows=max(1,(rect.height-105)//24);start=max(0,min(editor.cursor-rows//2,len(FIELDS)+1-rows))
    for y,n in enumerate(range(start,min(len(FIELDS)+1,start+rows))):
        selected=n==editor.cursor; color=bright if selected else glow
        label="APPLY TO CONTROLLER" if n==len(FIELDS) else FIELDS[n]["cpp"]
        value="" if n==len(FIELDS) else str(editor.get(n) if editor.get(n) is not None else "SET ME")
        line=f"{'> ' if selected else '  '}{label}"
        surface.blit(font(13,bold=selected).render(line,True,color),(rect.x+15,rect.y+42+y*24))
        surface.blit(font(13,bold=True).render(value,True,color),(rect.x+int(rect.width*.73),rect.y+42+y*24))
    surface.blit(font(12,bold=True).render(editor.status,True,bright),(rect.x+16,rect.bottom-48))
    surface.blit(font(11).render("UP/DOWN: FIELD | LEFT/RIGHT: VALUE | SELECT: SAVE/APPLY | ESC: BACK",True,glow),(rect.x+16,rect.bottom-25))
