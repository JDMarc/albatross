"""Persistent TCS/AWC levels and measured event feedback on the main HUD."""
import pygame
from .base import Widget
from .ui_utils import AMBER_BG,AMBER_BRIGHT,AMBER_DARK,AMBER_GLOW,FAULT_AMBER,font,fit_font_size
from ...dynamics import LEVELS

class TractionPanel(Widget):
    def __init__(self,rect):self.rect=rect;self.intensity=0.0;self.last=0
    def draw(self,surface,state):
        old=surface.get_clip();surface.set_clip(self.rect)
        try:
            d=state.dynamics;now=pygame.time.get_ticks();dt=(now-self.last)/1000 if self.last else 0;self.last=now
            correction=max(0,d.rider-d.permitted) if d.online else 0
            self.intensity=max(correction,self.intensity-dt*100)
            pygame.draw.rect(surface,AMBER_BG,self.rect)
            pygame.draw.rect(surface,FAULT_AMBER if d.faults or not d.online else AMBER_BRIGHT if d.flags&3 else AMBER_DARK,self.rect,1)
            pad=7;half=(self.rect.width-2*pad)//2
            for n,(label,level) in enumerate((("TCS",d.tcs),("AWC",d.awc))):
                text=label+" "+LEVELS[level]
                size=fit_font_size(text,half,18,start_size=16,bold=True)
                color=FAULT_AMBER if level==0 else AMBER_BRIGHT if d.flags&(1<<n) else AMBER_GLOW
                surface.blit(font(size,bold=True).render(text,True,color),(self.rect.x+pad+n*half,self.rect.y+5))
            status="DATA STALE" if not d.online else "POWERTRAIN STOP" if d.faults&8192 else "SENSOR FAULT" if d.faults else "AWC + TCS" if d.flags&3==3 else "TCS // CORRECTING" if d.flags&1 else "AWC // CORRECTING" if d.flags&2 else f"LIFT {d.pitch:.1f} DEG" if d.flags&4 else "DYNAMICS // MONITOR"
            size=fit_font_size(status,self.rect.width-2*pad,16,start_size=12,bold=True)
            surface.blit(font(size,bold=True).render(status,True,AMBER_BRIGHT),(self.rect.x+pad,self.rect.bottom-21))
            pygame.draw.rect(surface,AMBER_BRIGHT,(self.rect.x+pad,self.rect.bottom-5,int((self.rect.width-2*pad)*self.intensity/100),2))
        finally:surface.set_clip(old)
