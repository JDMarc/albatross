"""Learn and poll a USB grip-controller three-position mode switch."""
import json
import time
from pathlib import Path
import pygame
from .airshot import MODES

class AirModeSwitch:
    def __init__(self,path=Path("settings/airshot_switch.json")):
        self.path=Path(path);self.device=None;self.mapping={};self.samples={}
        self.cursor=0;self.capture_at=None;self.last=None;self.candidate=None;self.since=0
        self.status="SELECT OFF / MANUAL / AUTO TO LEARN EACH POSITION"
        try:
            candidate=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(candidate,dict) or set(candidate.get("patterns",{}))!=set(MODES):raise ValueError("invalid mapping")
            controls=candidate.get("controls",[])
            if not controls or any(k not in ("buttons","axes") or not isinstance(n,int) or n<0 for k,n in controls):raise ValueError("invalid controls")
            if any(len(p)!=len(controls) for p in candidate["patterns"].values()):raise ValueError("invalid patterns")
            self.mapping=candidate
        except (OSError,ValueError,TypeError):pass

    def connect(self):
        if self.device and self.device.get_init():return
        if not pygame.joystick.get_init():pygame.joystick.init()
        for n in range(pygame.joystick.get_count()):
            device=pygame.joystick.Joystick(n);device.init()
            if not self.mapping or device.get_guid()==self.mapping.get("guid"):
                self.device=device;return

    def snapshot(self):
        self.connect()
        if not self.device:return None
        return {
            "buttons":[int(self.device.get_button(n)) for n in range(self.device.get_numbuttons())],
            "axes":[-1 if self.device.get_axis(n)<-0.65 else 1 if self.device.get_axis(n)>0.65 else 0 for n in range(self.device.get_numaxes())]
        }

    def learn(self):
        self.capture_at=time.monotonic()+1.5
        self.status="MOVE SWITCH TO "+MODES[self.cursor]+" / CAPTURE IN 1.5s"

    def poll(self,excluded_buttons=()):
        try:state=self.snapshot()
        except pygame.error:
            self.device=None
            changed=self.last not in (None,"OFF")
            self.last="OFF";self.candidate=None
            return "OFF" if changed else None
        if state is None:return None
        now=time.monotonic()
        if self.capture_at and now>=self.capture_at:
            self.capture_at=None;self.samples[MODES[self.cursor]]=state
            self.status="CAPTURED "+MODES[self.cursor]
            if len(self.samples)==3:
                controls=[]
                for kind in ("buttons","axes"):
                    for n in range(len(state[kind])):
                        if kind=="buttons" and n in excluded_buttons:continue
                        if len({self.samples[m][kind][n] for m in MODES})>1:controls.append((kind,n))
                patterns={m:[self.samples[m][k][n] for k,n in controls] for m in MODES}
                if not controls or len({tuple(v) for v in patterns.values()})<3:
                    self.status="POSITIONS NOT DISTINCT / RELEARN";return None
                self.mapping={"guid":self.device.get_guid(),"controls":controls,"patterns":patterns}
                self.path.parent.mkdir(parents=True,exist_ok=True)
                self.path.write_text(json.dumps(self.mapping,indent=2),encoding="utf-8")
                self.status="SWITCH MAPPING SAVED";self.last=None
        if not self.mapping:return None
        try:actual=[state[k][n] for k,n in self.mapping["controls"]]
        except (IndexError,KeyError,TypeError):
            self.status="CONTROLLER MAPPING MISMATCH"
            changed=self.last!="OFF";self.last="OFF"
            return "OFF" if changed else None
        mode=next((m for m,p in self.mapping["patterns"].items() if p==actual),None)
        # Debounce transitions, but do not continuously override D-pad selection.
        if mode!=self.candidate:self.candidate=mode;self.since=now
        if mode and now-self.since>=0.06 and mode!=self.last:
            self.last=mode;return mode
        return None

    def draw(self,surface,colors):
        from .hud.widgets.ui_utils import font
        bg,bright,glow,fault=colors;w,h=surface.get_size()
        rect=pygame.Rect(30,64,w-60,h-110);pygame.draw.rect(surface,bg,rect);pygame.draw.rect(surface,glow,rect,2)
        lines=["AIR SHOT / USB THREE-POSITION SWITCH","Select a position, then move the switch when prompted.","Keep other controller axes and buttons unchanged."]
        for n,line in enumerate(lines):surface.blit(font(15,bold=n==0).render(line,True,bright if n==0 else glow),(rect.x+18,rect.y+15+n*28))
        for n,mode in enumerate(MODES):
            label=("> " if n==self.cursor else "  ")+mode+(" / CAPTURED" if mode in self.samples else "")
            surface.blit(font(18,bold=True).render(label,True,bright if n==self.cursor else glow),(rect.x+24,rect.y+112+n*34))
        surface.blit(font(12).render(self.status,True,bright),(rect.x+18,rect.bottom-55))
        surface.blit(font(12).render("UP/DOWN: POSITION | SELECT: LEARN | ESC: BACK",True,glow),(rect.x+18,rect.bottom-26))
