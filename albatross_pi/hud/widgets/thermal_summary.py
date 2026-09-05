"""Compact entry point when the main layout has no system-vitals panel."""
import pygame
from .base import Widget
from .ui_utils import instrument_frame
from .ui_utils import AMBER_BG, AMBER_GLOW, FAULT_AMBER, font, fit_font_size


class ThermalSummary(Widget):
    def __init__(self, rect):
        self.rect = rect

    def draw(self, surface, state):
        thermal = state.thermal
        status = thermal.overall_status
        text = thermal.thermal_state if thermal.online else "DATA OFFLINE"
        color = ((80, 170, 240) if text in {"COLD", "WARMING"} else (80, 220, 140))
        if status in {"CHECK", "ELEVATED"} or text in {"HOT", "COOLDOWN RECOMMENDED"}:
            color = (255, 190, 50)
        if status in {"WARNING", "CRITICAL", "DATA FAULT"} or not thermal.online:
            color = FAULT_AMBER
            text = "DATA FAULT" if thermal.online and status == "DATA FAULT" else status if thermal.online else text
        if text == "COOLDOWN RECOMMENDED":
            text = "COOLDOWN"
        instrument_frame(surface, self.rect, color=color)
        surface.blit(font(14, bold=True).render("TEMP", True, color), (self.rect.x+7, self.rect.y+3))
        size = fit_font_size(text, self.rect.width-14, 13, start_size=11, bold=True)
        surface.blit(font(size, bold=True).render(text, True, AMBER_GLOW), (self.rect.x+7, self.rect.bottom-15))
