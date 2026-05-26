"""Mode-specific operating stats panel."""
from __future__ import annotations

import math

import pygame

from ...economy import fallback_mpg_estimate
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ...state.snapshot import StateSnapshot

KNOWN_MODES = {"ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"}


def _fmt(value: float | None, suffix: str = "", precision: int = 0) -> str:
    if value is None or not math.isfinite(value):
        return "--"
    if precision <= 0:
        return f"{value:.0f}{suffix}"
    return f"{value:.{precision}f}{suffix}"


class ModeStatsPanel(Widget):
    def __init__(self, rect: pygame.Rect) -> None:
        self.rect = rect

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        padding = max(6, int(min(self.rect.width, self.rect.height) * 0.07))
        mode = state.environment.mode if state.environment.mode in KNOWN_MODES else "NORMAL"
        rows = self._rows_for_mode(mode, state)
        title = mode
        title_font = fit_font_size(title, self.rect.width - 2 * padding, max(12, int(self.rect.height * 0.18)), start_size=max(12, int(self.rect.height * 0.16)), bold=True)
        title_surface = font(title_font, bold=True).render(title, True, AMBER_BRIGHT)
        surface.blit(title_surface, (self.rect.x + padding, self.rect.y + max(3, padding // 2)))

        y = self.rect.y + max(4, padding // 2) + title_surface.get_height() + 2
        available_h = max(18, self.rect.bottom - y - max(4, padding // 2))
        row_h = max(11, available_h // max(1, len(rows)))
        row_gap = 1 if row_h < 17 else 2
        for idx, (label, value, fault) in enumerate(rows):
            row_y = y + idx * row_h
            row_rect = pygame.Rect(self.rect.x + padding, row_y, self.rect.width - 2 * padding, max(8, row_h - row_gap))
            color = FAULT_AMBER if fault else AMBER_GLOW
            label_color = AMBER_GLOW if not fault else FAULT_AMBER
            value_color = AMBER_BRIGHT if not fault else color
            self._draw_row(surface, row_rect, label, value, label_color, value_color)
        surface.set_clip(previous_clip)

    @staticmethod
    def _draw_row(
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        value: str,
        label_color: tuple[int, int, int] | list[int],
        value_color: tuple[int, int, int] | list[int],
    ) -> None:
        gap = 6
        value_w = max(42, min(int(rect.width * 0.48), rect.width - 54))
        label_w = max(36, rect.width - value_w - gap)
        start_size = max(8, min(15, int(rect.height * 0.78)))
        label_size = fit_font_size(label, label_w, rect.height, start_size=start_size, bold=True, min_size=8)
        value_size = fit_font_size(value, value_w, rect.height, start_size=max(9, min(16, int(rect.height * 0.86))), bold=True, min_size=8)
        label_surface = font(label_size, bold=True).render(label, True, label_color)
        value_surface = font(value_size, bold=True).render(value, True, value_color)

        if (
            rect.height >= 24
            and (
                label_surface.get_width() > label_w
                or value_surface.get_width() > value_w
                or label_surface.get_width() + value_surface.get_width() + gap > rect.width
            )
        ):
            half_h = max(8, rect.height // 2)
            label_size = fit_font_size(label, rect.width, half_h, start_size=max(8, min(13, half_h)), bold=True, min_size=8)
            value_size = fit_font_size(value, rect.width, rect.height - half_h, start_size=max(8, min(14, rect.height - half_h)), bold=True, min_size=8)
            label_surface = font(label_size, bold=True).render(label, True, label_color)
            value_surface = font(value_size, bold=True).render(value, True, value_color)
            surface.blit(label_surface, (rect.x, rect.y))
            surface.blit(value_surface, (rect.right - value_surface.get_width(), rect.y + half_h - 1))
            return

        label_y = rect.y + max(0, (rect.height - label_surface.get_height()) // 2)
        value_y = rect.y + max(0, (rect.height - value_surface.get_height()) // 2)
        surface.blit(label_surface, (rect.x, label_y))
        surface.blit(value_surface, (rect.right - value_surface.get_width(), value_y))

    def _rows_for_mode(self, mode: str, state: StateSnapshot) -> list[tuple[str, str, bool]]:
        instant_mpg = state.economy.instant_mpg if state.economy.instant_mpg > 0 else fallback_mpg_estimate(state)
        average_mpg = state.economy.average_mpg if state.economy.average_mpg > 0 else instant_mpg
        mte = state.economy.miles_to_empty if state.economy.miles_to_empty > 0 else None
        economy_label = "AVG MPG" if state.economy.source == "INJECTOR" else "EST MPG"
        fuel_low = 0 <= state.environment.fuel_level_pct <= 15
        wmi_flow = f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f}"
        boost_error = abs(state.engine.boost_psi - state.engine.target_boost_psi) > 3.0 and state.engine.target_boost_psi > 4.0
        if mode == "ECO":
            return [
                (economy_label, _fmt(average_mpg, precision=1), average_mpg is not None and average_mpg < 24),
                ("RANGE", _fmt(mte, "mi"), fuel_low),
                ("FUEL", _fmt(state.environment.fuel_level_pct, "%") if state.environment.fuel_level_pct >= 0 else "--", fuel_low),
                ("BOOST", "LOCKED", state.engine.target_boost_psi > 0.5),
            ]
        if mode == "NORMAL":
            return [
                (economy_label, _fmt(average_mpg, precision=1), average_mpg is not None and average_mpg < 20),
                ("RANGE", _fmt(mte, "mi"), fuel_low),
                ("FUEL FLOW", _fmt(state.economy.fuel_flow_cc_min, "ccm") if state.economy.source == "INJECTOR" else "--", False),
                ("BOOST", "LOCKED", state.engine.target_boost_psi > 0.5),
            ]
        if mode == "SPORT":
            return [
                ("REQ BOOST", f"{state.engine.target_boost_psi:.1f} psi", boost_error),
                ("WG DUTY", f"{state.engine.wastegate_duty_pct:.0f}%", state.engine.wastegate_duty_pct > 85),
                ("TC SLIP", f"{state.traction.slip_pct:.1f}%", state.traction.sensor_fault),
                ("KNOCK", f"{state.engine.knock_events:.0f}", state.engine.knock_events > 0),
            ]
        if mode == "RACE":
            return [
                ("BOOST", f"{state.engine.boost_psi:.1f}/{state.engine.target_boost_psi:.1f}psi", boost_error),
                ("EGT", f"{state.temps.exhaust_temp_f:.0f}F", state.temps.exhaust_temp_f > 1600),
                ("WMI FLOW", wmi_flow, state.wmi.fault_active or state.wmi.actual_flow_cc_min < state.wmi.commanded_flow_cc_min * 0.6),
                ("TC CUT", f"{state.traction.torque_cut_pct:.0f}%", state.traction.sensor_fault),
            ]
        return [
            ("AIR SHOT", f"{state.air_shot.pressure_psi:.0f} psi", state.air_shot.pressure_psi < 35 and state.engine.target_boost_psi > 6),
            ("WMI FLOW", wmi_flow, state.wmi.fault_active),
            ("IAT/EGT", f"{state.temps.intake_temp_f:.0f}/{state.temps.exhaust_temp_f:.0f}F", state.temps.intake_temp_f > 155 or state.temps.exhaust_temp_f > 1600),
            ("BOOST", f"{state.engine.boost_psi:.1f}/{state.engine.target_boost_psi:.1f}psi", boost_error),
        ]
