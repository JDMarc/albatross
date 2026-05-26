"""RPM bar widget."""
from __future__ import annotations

import pygame

from .base import Widget
from .ui_utils import AMBER_BRIGHT, AMBER_DARK, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot


class RpmBar(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect
        self.gauge_max = 14000
        self.red_start = 12500

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        engine = state.engine
        pygame.draw.rect(surface, AMBER_DARK, self.rect)
        pct = min(1.0, engine.rpm / max(1, self.gauge_max))
        fill_width = int(self.rect.width * pct)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
        over_red = engine.rpm >= self.red_start
        color = FAULT_AMBER if over_red and (pygame.time.get_ticks() // 150) % 2 == 0 else AMBER_BRIGHT
        pygame.draw.rect(surface, color, fill_rect)

        # Red zone segment overlay
        rz_x = self.rect.x + int((self.red_start / self.gauge_max) * self.rect.width)
        rz = pygame.Rect(rz_x, self.rect.y, self.rect.right - rz_x, self.rect.height)
        pygame.draw.rect(surface, (110, 20, 10), rz, 1)

        text_size = fit_font_size("RPM 14000", self.rect.width // 2, self.rect.height - 4, start_size=max(18, int(self.rect.height * 0.58)), bold=True)
        rpm_text = f"RPM {engine.rpm:5d}"
        x_cursor = self.rect.x + 10
        y_text = self.rect.centery - font(text_size, bold=True).get_height() // 2
        for ch in rpm_text:
            glyph = font(text_size, bold=True).render(ch, True, AMBER_BRIGHT)
            cx = x_cursor + glyph.get_width() // 2
            over_fill = cx <= fill_rect.right
            glyph = font(text_size, bold=True).render(ch, True, (0, 0, 0) if over_fill else AMBER_BRIGHT)
            surface.blit(glyph, (x_cursor, y_text))
            x_cursor += glyph.get_width()

        # Tick markers above bar at 1k increments and red-zone labels.
        tick_y = self.rect.y - 10
        for k in range(1, 15):
            rpm = k * 1000
            x = self.rect.x + int((rpm / self.gauge_max) * self.rect.width)
            pygame.draw.line(surface, AMBER_BRIGHT, (x, self.rect.y - 6), (x, self.rect.y - 2), 1)
            label = f"{k}k"
            if rpm in (13000, 14000):
                label = "13k" if rpm == 13000 else "14k"
            if rpm >= self.red_start:
                l = font(10, bold=True).render(label, True, FAULT_AMBER)
            else:
                l = font(10).render(label, True, AMBER_BRIGHT)
            surface.blit(l, (x - l.get_width() // 2, tick_y - l.get_height()))
        rz_label = font(10, bold=True).render("12.5k", True, FAULT_AMBER)
        rz_label_x = self.rect.x + int((self.red_start / self.gauge_max) * self.rect.width)
        surface.blit(rz_label, (rz_label_x - rz_label.get_width() // 2, tick_y - rz_label.get_height() - 10))

        if over_red:
            plate_w = min(max(int(self.rect.width * 0.13), 112), int(self.rect.width * 0.22))
            plate_h = max(18, self.rect.height - 10)
            plate = pygame.Rect(
                self.rect.right - plate_w - 8,
                self.rect.y + (self.rect.height - plate_h) // 2,
                plate_w,
                plate_h,
            )
            pygame.draw.rect(surface, (12, 2, 0), plate)
            pygame.draw.rect(surface, FAULT_AMBER, plate, 2)
            stripe_step = max(12, plate.height // 2)
            previous_clip = surface.get_clip()
            surface.set_clip(plate)
            for x in range(plate.x - plate.height, plate.right, stripe_step):
                pygame.draw.line(surface, (75, 12, 6), (x, plate.bottom - 2), (x + plate.height, plate.y + 2), 2)
            surface.set_clip(previous_clip)
            pygame.draw.rect(surface, FAULT_AMBER, plate, 2)
            label = "REDLINE"
            label_size = fit_font_size(label, plate.width - 16, plate.height - 8, start_size=max(14, int(plate.height * 0.65)), bold=True)
            label_surface = font(label_size, bold=True).render(label, True, (255, 210, 190))
            surface.blit(
                label_surface,
                (
                    plate.centerx - label_surface.get_width() // 2,
                    plate.centery - label_surface.get_height() // 2,
                ),
            )
