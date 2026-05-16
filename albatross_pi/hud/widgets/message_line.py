"""Scrolling message line widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot



class MessageLine(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        has_ecu = (
            state.engine.rpm > 0
            or state.engine.throttle_pct > 0
            or state.temps.coolant_temp_f > 0
            or state.temps.oil_temp_f > 0
        )
        has_arduino = (
            state.air_shot.pressure_psi > 0
            or state.air_shot.charges_remaining > 0
            or state.wmi.commanded_flow_cc_min > 0
            or state.wmi.actual_flow_cc_min > 0
            or state.traction.slip_pct > 0
            or abs(state.traction.wheelie_pitch_deg) > 0.01
        )
        has_can = (
            has_ecu
            or has_arduino
            or state.engine.speed_mph > 0
            or state.engine.boost_psi > 0
            or state.environment.message_line != ""
        )

        comm_line = " | ".join(
            [
                f"ECU {'OK' if has_ecu else 'FAULT'}",
                f"ARDUINO {'OK' if has_arduino else 'FAULT'}",
                f"CAN {'OK' if has_can else 'FAULT'}",
            ]
        )
        text = state.environment.message_line or " | ".join(state.faults) or comm_line
        color = FAULT_AMBER if (state.faults or "FAULT" in text) else AMBER_BRIGHT
        font_size = fit_font_size(text, self.rect.width - 16, self.rect.height - 4, start_size=max(14, int(self.rect.height * 0.6)))
        text_surface = font(font_size).render(text, True, color)
        surface.blit(
            text_surface,
            (
                self.rect.x + 8,
                self.rect.centery - text_surface.get_height() // 2,
            ),
        )
