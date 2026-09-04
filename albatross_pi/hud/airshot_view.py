"""Air Shot detail page using existing HUD colors, fonts and input actions."""
import pygame
import time
from .widgets.ui_utils import font, fit_font_size

def draw_airshot(surface,state,colors):
    bg,bright,glow,fault=colors
    w,h=surface.get_size();panel=pygame.Rect(22,56,w-44,h-88)
    pygame.draw.rect(surface,bg,panel,border_radius=8);pygame.draw.rect(surface,glow,panel,2,border_radius=8)
    air=state.air_shot.v2
    surface.blit(font(19,bold=True).render("AIR SHOT / CONTROL & DIAGNOSTICS",True,bright),(panel.x+14,panel.y+10))
    def number(v,suffix=""): return "--" if v is None else f"{v:.1f}{suffix}"
    permission=air.input_context.get("0x192",{})
    data=bytes.fromhex(permission.get("data",""))
    fresh=len(data)==8 and time.monotonic()-permission.get("at",0)<=.3
    rows=[
        ("MODE / STATE",f"{air.mode} / {air.state}" if air.online else "OFFLINE"),
        ("REASON",air.reason),("PROFILE",air.profile),("DEMAND / AIR",f"{air.demand_pct}% / {air.available_pct}%"),
        ("TANK / REG",number(air.tank_psi," psi")+" / "+number(air.regulated_psi," psi")),
        ("INTAKE L / R",f"{air.valves_pct[0]}% / {air.valves_pct[1]}%"),
        ("TURBINE L / R",f"{air.valves_pct[2]}% / {air.valves_pct[3]}%"),
        ("SHADOW",str(air.predicted_pct) if air.flags&8 else "INACTIVE"),
        ("DRIVER FAULTS",f"0x{air.driver_faults:02X}"),
        ("STAGE / CONFIG",f"{air.stage} / {air.calibration_version}"),
        ("LAST DURATION",f"{air.last_duration_ms} ms"),
        ("TANK PRESSURE USED",number(air.pressure_used_psi," psi (not air mass)")),
        ("BOOST / TARGET",f"{state.engine.boost_psi:.1f} / {state.engine.target_boost_psi:.1f} psi"),
        ("TCS / AWC",f"{'ACTIVE' if state.traction.active else 'INACTIVE'} / "+("ACTIVE" if data[4]&4 else "INACTIVE") if fresh else "PERMISSION DATA STALE"),
        ("RIDER / DBW CMD / ACT",f"{data[1]} / {data[2]} / {data[3]} %" if fresh else "DATA STALE"),
        ("VALVE CURRENTS", " / ".join(number(v,"A") for v in air.currents_a)),
        ("COMPRESSOR",air.compressor),
        ("EVENT / LOGGING",f"{air.event_id} / "+("FAULT" if air.logging_fault else "OK")),
        ("WMI", "FAULT" if state.wmi.fault_active else f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f} cc/min"),
        ("THERMAL",state.thermal.overall_status),
    ]
    n=(len(rows)+1)//2;colw=(panel.width-36)//2;rowh=max(20,(panel.height-80)//n)
    for idx,(label,value) in enumerate(rows):
        col,row=divmod(idx,n);x=panel.x+12+col*colw;y=panel.y+48+row*rowh
        label_size=max(10,min(18,int(rowh*.3)))
        surface.blit(font(label_size,bold=True).render(label,True,glow),(x,y))
        size=fit_font_size(value,colw-20,max(10,rowh-label_size-3),start_size=max(12,min(24,int(rowh*.4))),bold=True)
        text=font(size,bold=True).render(value,True,fault if "FAULT" in value or value=="OFFLINE" else bright)
        surface.blit(text,(x,y+label_size+2))
    surface.blit(font(11).render("ESC: MAIN AIR BOX  |  FIRE: REQUEST  |  CALIBRATION: SETTINGS > AIR SHOT",True,glow),(panel.x+14,panel.bottom-24))
