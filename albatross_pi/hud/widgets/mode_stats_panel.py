"""Mode-specific operating stats panel."""
from __future__ import annotations

import math

import pygame

from ...economy import fallback_mpg_estimate
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
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
        grid_gap = max(4, min(8, padding))
        columns = 2
        grid_rows = max(1, math.ceil(len(rows) / columns))
        cell_w = max(32, (self.rect.width - 2 * padding - grid_gap * (columns - 1)) // columns)
        cell_h = max(12, (available_h - grid_gap * (grid_rows - 1)) // grid_rows)
        for idx, (label, value, fault) in enumerate(rows):
            col = idx % columns
            row = idx // columns
            row_rect = pygame.Rect(
                self.rect.x + padding + col * (cell_w + grid_gap),
                y + row * (cell_h + grid_gap),
                cell_w,
                cell_h,
            )
            color = FAULT_AMBER if fault else AMBER_GLOW
            label_color = AMBER_GLOW if not fault else FAULT_AMBER
            value_color = AMBER_BRIGHT if not fault else color
            self._draw_cell(surface, row_rect, label, value, label_color, value_color, fault)
        surface.set_clip(previous_clip)

    @staticmethod
    def _draw_cell(
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        value: str,
        label_color: tuple[int, int, int] | list[int],
        value_color: tuple[int, int, int] | list[int],
        fault: bool,
    ) -> None:
        if fault:
            accent = pygame.Rect(rect.x, rect.y + 3, 2, max(1, rect.height - 6))
            pygame.draw.rect(surface, FAULT_AMBER, accent)
            pygame.draw.line(surface, FAULT_AMBER, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 1)
        else:
            pygame.draw.line(surface, AMBER_DARK, (rect.x, rect.bottom - 1), (rect.right, rect.bottom - 1), 1)
        inner = rect.inflate(-8 if fault else -4, -4)
        if fault:
            inner.x += 4
            inner.width = max(1, inner.width - 4)
        label_h = max(8, min(13, int(inner.height * 0.42)))
        value_h = max(8, inner.height - label_h)
        label_size = fit_font_size(label, inner.width, label_h, start_size=max(8, min(12, label_h)), bold=True, min_size=8)
        value_size = fit_font_size(value, inner.width, value_h, start_size=max(8, min(16, value_h + 2)), bold=True, min_size=8)
        label_surface = font(label_size, bold=True).render(label, True, label_color)
        value_surface = font(value_size, bold=True).render(value, True, value_color)
        surface.blit(label_surface, (inner.x, inner.y))
        surface.blit(value_surface, (inner.right - value_surface.get_width(), inner.y + label_h - 1))

    def _rows_for_mode(self, mode: str, state: StateSnapshot) -> list[tuple[str, str, bool]]:
        # Context, not duplicates of BoostPanel, FuelPanel, TempsGrid or AirShotPanel.
        e,d,a=state.engine,state.dynamics,state.air_shot.v2
        instant=state.economy.instant_mpg if state.economy.instant_mpg>0 else fallback_mpg_estimate(state)
        average=state.economy.average_mpg if state.economy.average_mpg>0 else instant
        economy_label="AVG MPG" if state.economy.source=="INJECTOR" else "EST MPG"
        range_value=state.economy.miles_to_empty if state.economy.miles_to_empty>0 else None
        if mode in {"ECO","NORMAL"}:
            return [
                (economy_label,_fmt(average,precision=1),False),
                ("EST RANGE",_fmt(range_value," mi"),False),
                ("TRIP",_fmt(state.economy.distance_miles," mi",1),False),
                ("FUEL USED",_fmt(state.economy.fuel_used_gal," gal",2) if state.economy.source=="INJECTOR" else "--",False),
            ]
        limiter="OFFLINE"
        if d.online:
            limits={"TCS":d.tcs_limit,"AWC":d.awc_limit,"LEAN":d.lean_limit,
                    "ENGINE":d.engine_limit,"MODE":d.mode_limit}
            floor=min(limits.values())
            if d.permitted>=d.rider:limiter="RIDER"
            elif floor<d.rider and floor<=d.permitted:
                names=[name for name,value in limits.items() if value==floor]
                limiter=names[0] if len(names)==1 else "MULTIPLE"
            else:limiter="OTHER / RAMP"
        # These are observed differences, not new fault thresholds or diagnoses.
        boost_gap=f"{e.boost_psi-d.boost_target:+.1f} psi" if d.online and not d.faults&(1<<10) else "--"
        dbw_error=f"{d.throttle_actual-d.throttle_target:+.1f} deg" if d.online and not d.faults&(1<<7) else "--"
        shared=[("TQ LIMITER",limiter,not d.online),("BOOST GAP",boost_gap,False)]
        if mode=="SPORT":
            return shared+[
                ("REAR SLIP",_fmt(d.slip,"%",1) if d.online and d.slip_confidence>0 else "--",False),
                ("DBW ERROR",dbw_error,False),
            ]
        if mode=="RACE":
            afr=f"{e.afr_left:.1f}/{e.afr_right:.1f}" if e.afr_left>0 and e.afr_right>0 else "--"
            return shared+[
                ("AFR L/R",afr,False),
                ("PERMIT TQ",_fmt(d.permitted,"%") if d.online else "--",False),
            ]
        return shared+[
            ("LAST AIR",_fmt(a.last_duration_ms," ms") if a.online and a.event_id else "--",False),
            ("AIR USED",_fmt(a.pressure_used_psi," psi",1) if a.online and a.event_id and a.pressure_valid else "--",False),
        ]
