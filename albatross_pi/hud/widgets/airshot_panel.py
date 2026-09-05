"""Air Shot tile: controller-confirmed mode remains visible during faults."""
from __future__ import annotations
import pygame
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot
from ..airshot_status import AirShotRequest, airshot_status

class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 150.0, max_shots: int = 3) -> None:
        self.rect=rect
        self.request=AirShotRequest()

    def draw(self,surface: pygame.Surface,state: StateSnapshot) -> None:
        previous=surface.get_clip();surface.set_clip(self.rect)
        try:
            air=state.air_shot.v2;pad=7
            fault=not air.online or air.state=="FAULT"
            pygame.draw.rect(surface,AMBER_BG,self.rect)
            pygame.draw.rect(surface,FAULT_AMBER if fault else AMBER_DARK,self.rect,1)
            intent,status,_reason=airshot_status(air,self.request)
            title="AIR / "+intent
            text=font(fit_font_size(title,self.rect.width-pad*2,16,start_size=12,bold=True),bold=True).render(title,True,AMBER_BRIGHT)
            surface.blit(text,(self.rect.x+pad,self.rect.y+4))
            pressure="--" if not air.online or not air.pressure_valid or air.tank_psi is None else f"{air.tank_psi:.0f} PSI"
            value=font(12,bold=True).render(pressure,True,AMBER_GLOW)
            surface.blit(value,(self.rect.right-value.get_width()-pad,self.rect.y+23))
            actual="CTRL "+(air.mode if air.online else "--")
            size=fit_font_size(actual,self.rect.width-value.get_width()-pad*3,14,start_size=11,bold=True)
            surface.blit(font(size,bold=True).render(actual,True,AMBER_GLOW),(self.rect.x+pad,self.rect.y+23))
            size=fit_font_size(status,self.rect.width-pad*2,14,start_size=11,bold=True)
            text=font(size,bold=True).render(status,True,FAULT_AMBER if fault else AMBER_GLOW)
            surface.blit(text,(self.rect.x+pad,self.rect.bottom-18))
        finally:surface.set_clip(previous)
