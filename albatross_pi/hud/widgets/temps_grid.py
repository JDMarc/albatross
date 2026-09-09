"""Readable rotating vitals. Selection is display-only, never protection."""
import math
import pygame
from .base import Widget
from .ui_utils import AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font, instrument_frame
from ...thermal.model import SensorStatus


class TempsGrid(Widget):
    PAGE_MS = 4000  # UI dwell only, not a protection timeout.

    def __init__(self, rect, *, split=False):
        self.rect=rect
        self.split=split
        self._page=None
        self._keys=()
        self._scan=0
        self._focus_label="HOT"

    @staticmethod
    def _temperature(value):
        return "--" if value is None or not math.isfinite(value) or value==-1 else f"{value:.0f}F"

    @staticmethod
    def _finite(value):
        return value if value is not None and math.isfinite(value) else 0.0

    def selected_rows(self,state,now_ms):
        thermal=state.thermal
        page=now_ms//self.PAGE_MS
        readings=sorted((r for r in thermal.readings.values()
                         if r.status!=SensorStatus.NOT_CONFIGURED),key=lambda r:r.sensor_id)
        if page!=self._page:
            self._page=page
            self._keys=()
            if readings:
                faults=[r for r in readings if not r.valid or not math.isfinite(r.temperature_c)]
                valid=[r for r in readings if r not in faults]
                if faults:
                    focus=faults[page%len(faults)]
                    self._focus_label="FAULT"
                elif page%2:
                    focus=max(valid,key=lambda r:self._finite(r.derivative_c_s))
                    self._focus_label="RISE"
                else:
                    focus=max(valid,key=lambda r:max(self._finite(r.thermal_abs),self._finite(r.thermal_dev)))
                    self._focus_label="HOT"
                others=[r for r in readings if r.key!=focus.key]
                scan=others[self._scan%len(others)] if others else focus
                self._scan+=1
                self._keys=(focus.key,scan.key)

        def cell(index):
            r=thermal.get(self._keys[index]) if len(self._keys)>index else None
            if not thermal.online:return ("THERMAL","OFFLINE",True)
            if r is None:return ("SENSOR","--",True)
            label=r.key.replace("_LEFT"," L").replace("_RIGHT"," R").replace("_"," ")
            for long,short in (("HEAD COOLANT","COOLANT"),("TURBO OIL DRAIN","TURBO DRAIN"),
                               ("OIL COOLER","OIL CLR"),("UNDER FAIRING","FAIRING"),
                               ("AMBIENT AIR","AMBIENT"),("RUNNER IAT","RUNNER")):
                label=label.replace(long,short)
            if not r.valid or not math.isfinite(r.temperature_c):
                return (label,r.status.name.replace("_"," "),True)
            return (label,self._temperature(r.temperature_c*1.8+32),False)

        utility=[
            ("BATTERY",f"{state.temps.battery_voltage:.2f}V" if state.temps.battery_voltage>=0 else "--",False),
            ("WMI TANK",f"{state.wmi.tank_level_pct:.0f}%",False),
            ("WMI FLOW",f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f}",False),
        ][page%3]
        if state.wmi.fault_active:utility=("WMI","FAULT",True)
        return [cell(0),cell(1),("OIL PRESSURE",f"{state.temps.oil_pressure_psi:.1f}psi",False),utility]

    def draw(self,surface,state):
        previous=surface.get_clip()
        surface.set_clip(self.rect)
        try:
            instrument_frame(surface,self.rect)
            rows=self.selected_rows(state,pygame.time.get_ticks())
            title=f"VITALS / {self._focus_label} + SCAN" if state.thermal.online else "VITALS / THERMAL OFFLINE"
            size=fit_font_size(title,self.rect.width-16,13,start_size=11,bold=True)
            surface.blit(font(size,bold=True).render(title,True,AMBER_BRIGHT),(self.rect.x+8,self.rect.y+2))
            top=self.rect.y+17
            width=self.rect.width//2
            height=max(1,(self.rect.bottom-top-3)//2)
            for index,(label,value,fault) in enumerate(rows):
                x=self.rect.x+(index%2)*width
                y=top+(index//2)*height
                pygame.draw.line(surface,AMBER_DARK,(x+6,y),(x+width-6,y))
                label_w=int(width*.60)-12
                value_w=width-label_w-20
                size=fit_font_size(label,label_w,height-3,start_size=13,bold=True)
                value_size=fit_font_size(value,value_w,height-3,start_size=16,bold=True)
                a=font(size,bold=True).render(label,True,AMBER_GLOW)
                b=font(value_size,bold=True).render(value,True,FAULT_AMBER if fault else AMBER_BRIGHT)
                surface.blit(a,(x+7,y+max(1,(height-a.get_height())//2)))
                surface.blit(b,(x+width-7-b.get_width(),y+max(1,(height-b.get_height())//2)))
        finally:surface.set_clip(previous)
