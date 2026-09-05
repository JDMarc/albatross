"""Thermal pages and a navigable twin-turbo transverse V-twin schematic."""
from __future__ import annotations

import math
import pygame

from .widgets.ui_utils import fit_font_size, font
from .thermal_architecture import draw_architecture, neighbor, FlowAnimation
from .thermal_style import thermal_chrome
from ..state.snapshot import StateSnapshot
from ..thermal.model import SensorStatus, ThermalReading


THERMAL_MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("OVERVIEW", "thermal_overview"),
    ("THERMAL MAP", "thermal_abs"),
    ("THERMAL Δ / DEV", "thermal_dev"),
    ("INTAKE / TURBOS", "thermal_intake"),
    ("ENGINE / COOLING", "thermal_engine"),
    ("OIL SYSTEM", "thermal_oil"),
    ("SENSOR STATUS", "thermal_status"),
    ("HISTORY / LOGS", "thermal_history"),
)


MAP_KEYS = (
    "AMBIENT_AIR", "COMP_IN_LEFT", "COMP_IN_RIGHT", "COMP_OUT_LEFT", "COMP_OUT_RIGHT",
    "IC_IN_LEFT", "IC_IN_RIGHT", "IC_OUT_LEFT", "IC_OUT_RIGHT", "PRE_WMI", "POST_WMI",
    "PLENUM_IAT", "RUNNER_IAT_LEFT", "RUNNER_IAT_RIGHT", "HEAD_METAL_LEFT", "HEAD_METAL_RIGHT",
    "HEAD_COOLANT_LEFT", "HEAD_COOLANT_RIGHT", "EGT_LEFT", "EGT_RIGHT", "TURBINE_OUT_LEFT",
    "TURBINE_OUT_RIGHT", "TURBO_OIL_DRAIN_LEFT", "TURBO_OIL_DRAIN_RIGHT", "OIL_GALLERY",
    "RAD_IN", "RAD_OUT", "OIL_COOLER_IN", "OIL_COOLER_OUT",
)




class ThermalViews:
    def __init__(self) -> None:
        self.menu_cursor = 0
        self.sensor_cursor = 0
        self.map_selected = "AMBIENT_AIR"
        self.map_rects = {}
        self.animation = FlowAnimation()

    def map_move(self, dx: int, dy: int) -> None:
        self.map_selected = neighbor(self.map_selected, dx, dy)

    def menu_move(self, delta: int) -> None:
        self.menu_cursor = (self.menu_cursor + delta) % len(THERMAL_MENU_ITEMS)

    def sensor_move(self, delta: int, state: StateSnapshot) -> None:
        keys = self._page_keys("thermal_abs", state)
        self.sensor_cursor = (self.sensor_cursor + delta) % max(1, len(keys))

    def selected_page(self) -> str:
        return THERMAL_MENU_ITEMS[self.menu_cursor][1]

    def draw_focus_submenu(self, surface: pygame.Surface, colors: tuple[tuple[int, int, int], ...]) -> None:
        _bg, bright, glow, _fault = colors
        sw, sh = surface.get_size()
        width = min(270, max(210, sw // 5))
        row_h = max(19, min(27, sh // 19))
        width = min(440, sw-48)
        panel = pygame.Rect(0, 0, width, row_h * len(THERMAL_MENU_ITEMS) + 60)
        panel.center = surface.get_rect().center
        shade = pygame.Surface(panel.size, pygame.SRCALPHA); shade.fill((*thermal_chrome(colors)["panel"], 235))
        surface.blit(shade, panel.topleft); pygame.draw.rect(surface, bright, panel, 2, border_radius=7)
        surface.blit(font(15, bold=True).render("TEMPS", True, bright), (panel.x + 12, panel.y + 8))
        for index, (label, _page) in enumerate(THERMAL_MENU_ITEMS):
            y = panel.y + 31 + index * row_h
            color = bright if index == self.menu_cursor else glow
            prefix = "▶ " if index == self.menu_cursor else "  "
            surface.blit(font(12, bold=index == self.menu_cursor).render(prefix + label, True, color), (panel.x + 12, y))
        surface.blit(font(11).render("UP/DOWN: PAGE | SELECT: OPEN | BACK: VITALS", True, glow), (panel.x+12, panel.bottom-20))

    def draw(self, surface: pygame.Surface, state: StateSnapshot, page: str, colors: tuple[tuple[int, int, int], ...]) -> None:
        bg, bright, glow, fault = colors
        sw, sh = surface.get_size()
        panel = pygame.Rect(20, 54, sw - 40, sh - 82)
        shade = pygame.Surface(panel.size, pygame.SRCALPHA); shade.fill((*thermal_chrome(colors)["panel"], 246))
        surface.blit(shade, panel.topleft)
        if page in {"thermal_abs", "thermal_dev"}:
            # Chamfered multi-function-display bezel; no decorative alert colors.
            x,y,r,b=panel.left,panel.top,panel.right-1,panel.bottom-1
            pygame.draw.lines(surface,glow,True,[(x+8,y),(r-8,y),(r,y+8),(r,b-8),
                                               (r-8,b),(x+8,b),(x,b-8),(x,y+8)],2)
        else:
            pygame.draw.rect(surface, glow, panel, 2, border_radius=8)
        title = next((label for label, target in THERMAL_MENU_ITEMS if target == page), "THERMAL")
        status = state.thermal.overall_status
        status_color = fault if status in {"WARNING", "CRITICAL", "DATA FAULT"} else bright
        surface.blit(font(19, bold=True).render(f"THERMAL / {title}", True, bright), (panel.x + 14, panel.y + 9))
        status_surface = font(15, bold=True).render(f"{status}  |  {state.thermal.thermal_state}", True, status_color)
        surface.blit(status_surface, (panel.right - status_surface.get_width() - 14, panel.y + 12))
        content = pygame.Rect(panel.x + 12, panel.y + 42, panel.width - 24, panel.height - 70)
        if page in {"thermal_abs", "thermal_dev"}:
            self._draw_map(surface, state, content, page == "thermal_dev", colors)
        elif page == "thermal_overview":
            self._draw_overview(surface, state, content, colors)
        elif page == "thermal_status":
            self._draw_status(surface, state, content, colors)
        elif page == "thermal_history":
            self._draw_history(surface, state, content, colors)
        else:
            self._draw_numeric_page(surface, state, content, page, colors)
        hint = "D-PAD: SENSOR | SELECT / BACK: TEMPS MENU" if page in {"thermal_abs", "thermal_dev"} else "LEFT/RIGHT: PAGE | SELECT / BACK: TEMPS MENU"
        surface.blit(font(11, bold=True).render(hint, True, glow), (panel.x + 14, panel.bottom - 21))

    @staticmethod
    def _score_color(score: float, valid: bool) -> tuple[int, int, int]:
        if not valid:
            return (70, 74, 78)
        anchors = ((0, (30, 80, 150)), (20, (40, 170, 190)), (55, (70, 200, 90)), (75, (245, 195, 45)), (90, (255, 110, 30)), (100, (255, 35, 25)), (120, (255, 0, 180)))
        value = max(0.0, min(120.0, score))
        for (x0, c0), (x1, c1) in zip(anchors, anchors[1:]):
            if value <= x1:
                ratio = (value - x0) / (x1 - x0)
                return tuple(int(c0[i] + ratio * (c1[i] - c0[i])) for i in range(3))
        return anchors[-1][1]

    def _component(self, surface: pygame.Surface, state: StateSnapshot, rect: pygame.Rect, key: str, label: str, dev: bool, selected: bool) -> None:
        reading = state.thermal.get(key)
        valid = reading is not None and reading.valid
        score = (reading.thermal_dev if dev else reading.thermal_abs) if reading else 0.0
        color = self._score_color(score, valid)
        pygame.draw.rect(surface, color, rect, border_radius=5)
        pygame.draw.rect(surface, (255, 255, 255) if selected else (12, 18, 22), rect, 3 if selected else 1, border_radius=5)
        label_size = fit_font_size(label, rect.width - 70, rect.height-6, start_size=12, bold=True)
        text = font(label_size, bold=True).render(label, True, (5, 8, 10))
        surface.blit(text, (rect.x+6, rect.centery-text.get_height()//2))
        value = "--" if not valid else f"{reading.temperature_c:.0f}°C"
        value_text = font(max(9, label_size - 1), bold=True).render(value, True, (5, 8, 10))
        surface.blit(value_text, (rect.right-value_text.get_width()-6, rect.centery-value_text.get_height()//2))

    def _draw_map(self, surface: pygame.Surface, state: StateSnapshot, area: pygame.Rect, dev: bool, colors) -> None:
        _bg, bright, glow, _fault = colors
        detail_w = max(255, area.width // 4)
        map_area = pygame.Rect(area.x, area.y, area.width-detail_w-12, area.height-18)
        self.animation.advance(state.engine,pygame.time.get_ticks())
        self.map_rects = draw_architecture(surface, map_area, state, self.map_selected, dev, self._score_color,self.animation,colors)
        self._draw_detail(surface, state, pygame.Rect(map_area.right+12, area.y, detail_w, area.height), self.map_selected, dev, colors)
        x=map_area.x+5
        for label,color in (("CHARGE AIR",(57,169,184)),("EXHAUST",(195,108,60)),("COOLANT",(72,125,175)),("OIL",(167,143,66))):
            pygame.draw.line(surface,color,(x,map_area.bottom+8),(x+13,map_area.bottom+8),2)
            surface.blit(font(9,bold=True).render(label,True,color),(x+18,map_area.bottom+3))
            x+=125
        surface.blit(font(9).render("SCHEMATIC / ALL VALUES C",True,glow),(map_area.right-205,map_area.bottom+3))

    def _draw_detail(self, surface: pygame.Surface, state: StateSnapshot, rect: pygame.Rect, key: str, dev: bool, colors: tuple[tuple[int, int, int], ...]) -> None:
        _bg, bright, glow, fault = colors
        pygame.draw.rect(surface, thermal_chrome(colors)["surface"], rect, border_radius=6); pygame.draw.rect(surface, glow, rect, 1, border_radius=6)
        reading = state.thermal.get(key)
        if reading is None: return
        title_size = fit_font_size(reading.name.upper(), rect.width-20, 20, start_size=14, bold=True)
        surface.blit(font(title_size, bold=True).render(reading.name.upper(), True, bright), (rect.x+10, rect.y+8))
        def fmt(value: float | None, suffix="°C") -> str: return "--" if value is None else f"{value:+.1f}{suffix}"
        rows = (
            ("ACTUAL", fmt(reading.temperature_c)), ("Δ AMBIENT", fmt(reading.ambient_delta_c)),
            ("EXPECTED", fmt(reading.expected_c)), ("DEVIATION", fmt(reading.residual_c)),
            ("ABS SCORE", f"{reading.thermal_abs:.0f}"), ("DEV SCORE", f"{reading.thermal_dev:.0f}"),
            ("dT/dt", fmt(reading.derivative_c_s, "°C/s")), ("SENSOR", reading.status.name.replace("_", " ")),
            ("LAST UPDATE", "--" if math.isinf(reading.age_ms) else f"{reading.age_ms:.0f} ms"),
            ("RAW", "--" if reading.raw_value is None else str(reading.raw_value)),
            ("MAX", fmt(reading.maximum_c)), ("BASELINE N", str(reading.baseline_samples)),
        )
        row_h = max(16, min(23, (rect.height-42)//len(rows)))
        for index, (label, value) in enumerate(rows):
            y = rect.y + 34 + index*row_h
            surface.blit(font(11, bold=True).render(label, True, glow), (rect.x+10, y))
            value_color = fault if reading.status != SensorStatus.VALID and label == "SENSOR" else bright
            value_s = font(11, bold=True).render(value, True, value_color)
            surface.blit(value_s, (rect.right-value_s.get_width()-9, y))
        legend = "DEV: BASELINE TO ANOMALY" if dev else "ABS: COLD TO CRITICAL"
        surface.blit(font(9,bold=True).render(legend,True,glow),(rect.x+10,rect.bottom-27))
        for n in range(100):
            x0=rect.x+10+(rect.width-20)*n//100
            x1=rect.x+10+(rect.width-20)*(n+1)//100
            pygame.draw.rect(surface,self._score_color(n,True),(x0,rect.bottom-12,max(1,x1-x0),4))

    def _draw_overview(self, surface: pygame.Surface, state: StateSnapshot, area: pygame.Rect, colors) -> None:
        _bg, bright, glow, fault = colors
        items = (("NODE", "ONLINE" if state.thermal.online else "OFFLINE"), ("CAN AGE", f"{state.thermal.can_age_ms:.0f} ms" if state.thermal.online else "--"), ("UPTIME", self._uptime(state.thermal.uptime_s)), ("CONFIG", state.thermal.config_version), ("BASELINE", state.thermal.baseline_status))
        for index, (label, value) in enumerate(items):
            y=area.y+index*31; surface.blit(font(14,bold=True).render(label,True,glow),(area.x+8,y)); surface.blit(font(14,bold=True).render(value,True,bright if value!="OFFLINE" else fault),(area.x+170,y))
        x = area.x + area.width//2
        alerts = state.thermal.alerts or ("NO ACTIVE THERMAL ALERTS",)
        surface.blit(font(15,bold=True).render("ACTIVE CONDITIONS",True,bright),(x,area.y))
        for index, alert in enumerate(alerts[:10]): surface.blit(font(13,bold=True).render(alert,True,fault if state.thermal.alerts else glow),(x+8,area.y+29+index*23))

    def _draw_numeric_page(self, surface: pygame.Surface, state: StateSnapshot, area: pygame.Rect, page: str, colors) -> None:
        _bg, bright, glow, fault = colors
        keys = self._page_keys(page, state); cols=2; col_w=area.width//cols; rows_per=max(1,(len(keys)+1)//2)
        for index,key in enumerate(keys):
            reading=state.thermal.get(key); col=index//rows_per; row=index%rows_per; x=area.x+col*col_w; y=area.y+row*26
            if not reading: continue
            color=bright if reading.valid else fault; value="--" if not reading.valid else f"{reading.temperature_c:.1f}°C"
            surface.blit(font(12).render(reading.name,True,glow),(x+5,y)); vs=font(12,bold=True).render(value,True,color); surface.blit(vs,(x+col_w-vs.get_width()-12,y))
        derived_y=area.bottom-78
        metrics = self._page_metrics(page)
        for index,key in enumerate(metrics[:6]):
            value=state.thermal.derived.get(key); text="--" if value is None else f"{value:+.1f}{'%' if 'EFFECTIVENESS' in key or 'EFFICIENCY' in key else '°C'}"
            x=area.x+(index%3)*(area.width//3); y=derived_y+(index//3)*27
            surface.blit(font(11,bold=True).render(key.replace("_"," "),True,glow),(x+4,y)); ts=font(11,bold=True).render(text,True,bright); surface.blit(ts,(x+area.width//3-ts.get_width()-8,y))

    def _draw_status(self, surface: pygame.Surface, state: StateSnapshot, area: pygame.Rect, colors) -> None:
        _bg, bright, glow, fault = colors
        readings=list(state.thermal.readings.values()); cols=2; rows_per=16; col_w=area.width//2; row_h=max(16,area.height//16)
        for index,reading in enumerate(readings[:32]):
            col=index//rows_per; row=index%rows_per; x=area.x+col*col_w; y=area.y+row*row_h
            ok=reading.status==SensorStatus.VALID; color=(80,255,155) if ok else ((115,120,125) if reading.status==SensorStatus.NOT_CONFIGURED else fault)
            pygame.draw.circle(surface,color,(x+6,y+7),4); surface.blit(font(10).render(reading.key,True,glow),(x+15,y))
            value="--" if reading.temperature_c is None else f"{reading.temperature_c:.1f}°C"
            status=f"{value}  {reading.status.name}"; ts=font(10,bold=True).render(status,True,color); surface.blit(ts,(x+col_w-ts.get_width()-8,y))

    def _draw_history(self, surface: pygame.Surface, state: StateSnapshot, area: pygame.Rect, colors) -> None:
        _bg, bright, glow, _fault=colors
        surface.blit(font(14,bold=True).render(state.thermal.baseline_status,True,bright),(area.x+6,area.y+2))
        surface.blit(font(12).render("Learning is opt-in; factory, long-term, and recent baselines are kept separate.",True,glow),(area.x+6,area.y+28))
        readings=[r for r in state.thermal.readings.values() if r.maximum_c is not None]
        for index,reading in enumerate(readings[:18]):
            col=index//9; row=index%9; x=area.x+col*(area.width//2); y=area.y+62+row*25
            surface.blit(font(11).render(reading.name,True,glow),(x+5,y)); value=f"MAX {reading.maximum_c:.1f}°C  dT/dt {reading.derivative_c_s:+.1f}"; ts=font(11,bold=True).render(value,True,bright); surface.blit(ts,(x+area.width//2-ts.get_width()-10,y))

    @staticmethod
    def _uptime(seconds: int) -> str:
        return f"{seconds//3600:02d}:{(seconds//60)%60:02d}:{seconds%60:02d}"

    @staticmethod
    def _page_keys(page: str, state: StateSnapshot) -> tuple[str, ...]:
        if page == "thermal_intake": return ("AMBIENT_AIR","COMP_IN_LEFT","COMP_IN_RIGHT","COMP_OUT_LEFT","COMP_OUT_RIGHT","IC_IN_LEFT","IC_IN_RIGHT","IC_OUT_LEFT","IC_OUT_RIGHT","PRE_WMI","POST_WMI","PLENUM_IAT","RUNNER_IAT_LEFT","RUNNER_IAT_RIGHT","EGT_LEFT","EGT_RIGHT","TURBINE_OUT_LEFT","TURBINE_OUT_RIGHT")
        if page == "thermal_engine": return ("HEAD_COOLANT_LEFT","HEAD_COOLANT_RIGHT","HEAD_METAL_LEFT","HEAD_METAL_RIGHT","RAD_IN","RAD_OUT","RUNNER_IAT_LEFT","RUNNER_IAT_RIGHT")
        if page == "thermal_oil": return ("OIL_GALLERY","OIL_COOLER_IN","OIL_COOLER_OUT","TURBO_OIL_DRAIN_LEFT","TURBO_OIL_DRAIN_RIGHT","CHRA_TEMP_LEFT","CHRA_TEMP_RIGHT")
        return tuple(key for key in MAP_KEYS if key in state.thermal.readings)

    @staticmethod
    def _page_metrics(page: str) -> tuple[str, ...]:
        if page == "thermal_intake": return ("COMP_RISE_LEFT","COMP_RISE_RIGHT","IC_DROP_LEFT","IC_DROP_RIGHT","IC_EFFECTIVENESS_LEFT","IC_EFFECTIVENESS_RIGHT","WMI_DROP","TURBINE_DROP_LEFT","TURBINE_DROP_RIGHT")
        if page == "thermal_engine": return ("HEAD_COOLANT_LR_DELTA","HEAD_METAL_LR_DELTA","HEAD_COOLANT_TO_METAL_LEFT","HEAD_COOLANT_TO_METAL_RIGHT","RAD_DELTA_T")
        return ("OIL_COOLER_DELTA_T","TURBO_DRAIN_LR_DELTA")
