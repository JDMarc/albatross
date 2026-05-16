"""Air Shot status widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 2200.0) -> None:
        self.rect = rect
        self.max_pressure = max_pressure

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        bg = FAULT_AMBER if state.air_shot.is_firing else AMBER_BG
        pygame.draw.rect(surface, bg, self.rect)
        padding = max(8, int(self.rect.height * 0.18))
        pressure = state.air_shot.pressure_psi
        charges = max(0, min(5, state.air_shot.charges_remaining))
        top = self.rect.y + padding
        label = font(fit_font_size("AIR SHOT", self.rect.width - 2 * padding, int(self.rect.height * 0.22), start_size=22, bold=True), bold=True).render("AIR SHOT", True, AMBER_GLOW)
        surface.blit(label, (self.rect.centerx - label.get_width() // 2, top))
        top += label.get_height() + 4
        slot_w = max(12, (self.rect.width - 2 * padding - 4 * 6) // 5)
        for i in range(5):
            r = pygame.Rect(self.rect.x + padding + i * (slot_w + 6), top, slot_w, max(12, int(self.rect.height * 0.18)))
            pygame.draw.rect(surface, AMBER_DARK, r, 2)
            if i < charges:
                pygame.draw.rect(surface, AMBER_BRIGHT, r.inflate(-4, -4))
        top += max(12, int(self.rect.height * 0.18)) + 4
        if charges == 0:
            empty = font(fit_font_size("EMPTY", self.rect.width - 2 * padding, int(self.rect.height * 0.26), start_size=30, bold=True), bold=True).render("EMPTY", True, FAULT_AMBER)
            surface.blit(empty, (self.rect.centerx - empty.get_width() // 2, top))
        else:
            psi_text = f"{pressure:4.0f} PSI"
            psi = font(fit_font_size(psi_text, self.rect.width - 2 * padding, int(self.rect.height * 0.24), start_size=24, bold=True), bold=True).render(psi_text, True, AMBER_GLOW)
            surface.blit(psi, (self.rect.centerx - psi.get_width() // 2, top))
        if state.air_shot.is_firing:
            firing = font(fit_font_size("FIRING", self.rect.width - 2 * padding, int(self.rect.height * 0.2), start_size=24, bold=True), bold=True).render("FIRING", True, (255, 220, 220))
            surface.blit(firing, (self.rect.centerx - firing.get_width() // 2, self.rect.bottom - firing.get_height() - 4))
