"""Air Shot status widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class AirShotPanel(Widget):
    def __init__(self, rect: pygame.Rect, max_pressure: float = 150.0, max_shots: int = 3) -> None:
        self.rect = rect
        self.max_pressure = max_pressure
        self.max_shots = max(1, max_shots)

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        pygame.draw.rect(surface, FAULT_AMBER if state.air_shot.is_firing else AMBER_DARK, self.rect, width=1)
        padding = max(6, min(12, int(self.rect.height * 0.12)))
        pressure = state.air_shot.pressure_psi
        charges = max(0, min(self.max_shots, state.air_shot.charges_remaining))
        inner = self.rect.inflate(-2 * padding, -2 * padding)
        flash_on = state.air_shot.is_firing and (pygame.time.get_ticks() // 180) % 2 == 0

        if inner.height < 56:
            self._draw_compact(surface, inner, pressure, charges, state.air_shot.is_firing, flash_on)
            surface.set_clip(previous_clip)
            return

        header_h = max(14, min(24, int(inner.height * 0.24)))
        charge_h = max(10, min(20, int(inner.height * 0.22)))
        firing_h = max(13, min(22, int(inner.height * 0.24)))
        pressure_h = max(12, inner.height - header_h - charge_h - firing_h - 6)

        label_size = fit_font_size("AIR SHOT", inner.width, header_h, start_size=22, bold=True)
        label = font(label_size, bold=True).render("AIR SHOT", True, AMBER_GLOW)
        surface.blit(label, (inner.centerx - label.get_width() // 2, inner.y))

        charge_y = inner.y + header_h + 2
        gap = 6
        slot_w = max(10, (inner.width - (self.max_shots - 1) * gap) // self.max_shots)
        for i in range(self.max_shots):
            r = pygame.Rect(inner.x + i * (slot_w + gap), charge_y, slot_w, charge_h)
            pygame.draw.rect(surface, AMBER_DARK, r, width=2)
            if i < charges:
                pygame.draw.rect(surface, AMBER_BRIGHT, r.inflate(-4, -4))

        pressure_y = charge_y + charge_h + 3
        psi_text = "EMPTY" if charges == 0 else f"{pressure:.0f} PSI"
        psi_color = FAULT_AMBER if charges == 0 else AMBER_GLOW
        psi_size = fit_font_size(psi_text, inner.width, pressure_h, start_size=26, bold=True)
        psi = font(psi_size, bold=True).render(psi_text, True, psi_color)
        surface.blit(psi, (inner.centerx - psi.get_width() // 2, pressure_y + max(0, (pressure_h - psi.get_height()) // 2)))

        firing_text = "FIRING!!"
        firing_color = (255, 230, 210) if flash_on else (90, 56, 24)
        if state.air_shot.is_firing and not flash_on:
            firing_color = FAULT_AMBER
        firing_size = fit_font_size(firing_text, inner.width, firing_h, start_size=22, bold=True)
        firing = font(firing_size, bold=True).render(firing_text, True, firing_color)
        firing_y = inner.bottom - firing_h + max(0, (firing_h - firing.get_height()) // 2)
        surface.blit(firing, (inner.centerx - firing.get_width() // 2, firing_y))
        surface.set_clip(previous_clip)

    def _draw_compact(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        pressure: float,
        charges: int,
        firing: bool,
        flash_on: bool,
    ) -> None:
        status = "FIRING!!"
        status_color = (255, 230, 210) if flash_on else ((90, 56, 24) if not firing else FAULT_AMBER)
        label = "AIR"
        psi = "EMPTY" if charges == 0 else f"{pressure:.0f}PSI"
        gap = max(6, int(rect.width * 0.012))
        label_w = max(26, int(rect.width * 0.16))
        status_w = max(54, int(rect.width * 0.30))
        psi_w = max(58, int(rect.width * 0.18))
        pip_area_w = max(
            self.max_shots * 18 + (self.max_shots - 1) * gap,
            rect.width - label_w - status_w - psi_w - 3 * gap,
        )
        pip_gap = max(5, min(12, int(pip_area_w * 0.05)))
        pip_w = max(18, (pip_area_w - (self.max_shots - 1) * pip_gap) // self.max_shots)
        pip_h = max(10, min(18, int(rect.height * 0.48)))
        pip_total_w = self.max_shots * pip_w + (self.max_shots - 1) * pip_gap

        label_size = fit_font_size(label, label_w, rect.height, start_size=16, bold=True)
        psi_size = fit_font_size(psi, psi_w, rect.height, start_size=18, bold=True)
        status_size = fit_font_size(status, status_w, rect.height, start_size=15, bold=True)
        y_center = rect.centery
        label_s = font(label_size, bold=True).render(label, True, AMBER_GLOW)
        psi_s = font(psi_size, bold=True).render(psi, True, FAULT_AMBER if charges == 0 else AMBER_BRIGHT)
        status_s = font(status_size, bold=True).render(status, True, status_color)
        x = rect.x
        surface.blit(label_s, (x, y_center - label_s.get_height() // 2))
        x += label_w + gap
        surface.blit(psi_s, (x, y_center - psi_s.get_height() // 2))
        x += psi_w + gap
        pip_y = y_center - pip_h // 2
        for i in range(self.max_shots):
            r = pygame.Rect(x + i * (pip_w + pip_gap), pip_y, pip_w, pip_h)
            pygame.draw.rect(surface, AMBER_DARK, r, width=1)
            if i < charges:
                pygame.draw.rect(surface, AMBER_BRIGHT, r.inflate(-3, -3))
        surface.blit(status_s, (rect.right - status_s.get_width(), y_center - status_s.get_height() // 2))
