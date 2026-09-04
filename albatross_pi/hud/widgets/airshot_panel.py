"""Air Shot tile: controller-confirmed mode remains visible during faults."""
from __future__ import annotations
import pygame
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot

class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 150.0, max_shots: int = 3) -> None:
        self.rect=rect

    def draw(self,surface: pygame.Surface,state: StateSnapshot) -> None:
        previous=surface.get_clip();surface.set_clip(self.rect)
        try:
            air=state.air_shot.v2;pad=7
            fault=not air.online or air.state=="FAULT"
            pygame.draw.rect(surface,AMBER_BG,self.rect)
            pygame.draw.rect(surface,FAULT_AMBER if fault else AMBER_DARK,self.rect,1)
            title="AIR / "+air.mode
            text=font(fit_font_size(title,self.rect.width*.58,16,start_size=13,bold=True),bold=True).render(title,True,AMBER_BRIGHT)
            surface.blit(text,(self.rect.x+pad,self.rect.y+4))
            pressure="--" if not air.online or not air.pressure_valid or air.tank_psi is None else f"{air.tank_psi:.0f} PSI"
            value=font(12,bold=True).render(pressure,True,AMBER_GLOW)
            surface.blit(value,(self.rect.right-value.get_width()-pad,self.rect.y+4))
            status="DATA STALE" if not air.online else air.reason if air.state in ("INHIBITED","FAULT") else air.state
            if air.online and air.flags&8:status="SHADOW / "+status
            bar=pygame.Rect(self.rect.x+pad,self.rect.bottom-10,self.rect.width//4,5)
            pygame.draw.rect(surface,AMBER_DARK,bar)
            if air.online:pygame.draw.rect(surface,AMBER_BRIGHT,(bar.x,bar.y,int(bar.width*air.available_pct/100),bar.height))
            size=fit_font_size(status,int(self.rect.width*.65),14,start_size=11,bold=True)
            text=font(size,bold=True).render(status,True,FAULT_AMBER if fault else AMBER_GLOW)
            surface.blit(text,(self.rect.right-text.get_width()-pad,self.rect.bottom-17))
        finally:surface.set_clip(previous)
