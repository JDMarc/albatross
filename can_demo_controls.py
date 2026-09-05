"""Quick CAN demo control panel with sliders/buttons/text boxes.

Emits ECU and controller HUD frames by default. HUD-owned command frames and
Controller-to-ECU intervention requests are opt-in so the panel can stay connected
without fighting the real HUD controls.

Usage:
  python can_demo_controls.py --channel can0
  python can_demo_controls.py --canable COM5
  python can_demo_controls.py --interface slcan --channel COM5 --bitrate 500000
  python can_demo_controls.py --candlelight
  python can_demo_controls.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import tkinter as tk
from tkinter import ttk,messagebox
from albatross_pi.demo_systems import DemoSystems,DYNAMICS_FIELDS,AIR_FIELDS
from albatross_pi.dynamics import FAULTS,LEVELS
from albatross_pi.airshot import mode_frame,fire_frame
from albatross_pi.thermal import SensorStatus
from albatross_pi.thermal.simulation import SCENARIOS

from albatross_pi.canbus.encode import (
    build_air_shot_request_frame,
    build_boost_target_frame,
    build_ecu_fuel_profile_frame,
    build_ecu_rev_limiter_strategy_frame,
    build_ecu_spark_table_frame,
    build_engine_run_switch_frame,
    build_flame_mode_frame,
    build_fuel_type_frame,
    build_limp_mode_frame,
    build_mode_selection_frame,
    build_nfc_auth_frame,
    build_traction_level_frame,
    build_wmi_enable_frame,
)
from albatross_pi.canbus.ids import ArduinoToEcuID, ArduinoToHudID, ECUToHudID, LIMP_REASON_CODES
from albatross_pi.canbus.iface import PythonCANInterface, SocketCANInterface


class App:
    def __init__(
        self,
        root: tk.Tk,
        *,
        interface: str,
        channel: str,
        bitrate: int,
        tty_baudrate: int | None,
        dry_run: bool,
        udp_target: str,
        send_hud_commands: bool,
    ) -> None:
        self.root = root
        self.root.title("Albatross CAN Demo Controls")
        self.dry_run = dry_run
        self.can_interface_name = interface
        self.can_channel_name = channel
        self.can_bitrate = bitrate
        self.tty_baudrate=tty_baudrate
        self.systems=DemoSystems();self.fire_held=False;self.fire_sequence=0
        self.iface = None if dry_run else self._open_can_interface(interface, channel, bitrate, tty_baudrate)
        self.udp_host, self.udp_port = udp_target.split(":")
        self.udp_port = int(self.udp_port)
        self.udp_ports = sorted({self.udp_port, 5505})
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.iface:
            try:
                self.iface.start()
            except Exception as exc:
                print(f"[can-demo] {exc}")
                print("[can-demo] Falling back to --dry-run (printing frames).")
                self.iface = None
                self.dry_run = True

        self.vars = {
            "rpm": tk.IntVar(value=2000),
            "tps": tk.IntVar(value=20),
            "boost": tk.DoubleVar(value=4.0),
            "boost_l": tk.DoubleVar(value=4.0),
            "boost_r": tk.DoubleVar(value=4.0),
            "afr_l": tk.DoubleVar(value=12.5),
            "afr_r": tk.DoubleVar(value=12.6),
            "knock_mask": tk.IntVar(value=0),
            "oilp": tk.DoubleVar(value=58.0),
            "oilt": tk.DoubleVar(value=205.0),
            "clt": tk.DoubleVar(value=190.0),
            "batt_v": tk.DoubleVar(value=13.8),
            "fuel": tk.IntVar(value=75),
            "ethanol_pct": tk.IntVar(value=10),
            "inj_pw_ms": tk.DoubleVar(value=3.5),
            "inj_duty_pct": tk.DoubleVar(value=0.0),
            "fuel_type": tk.StringVar(value="93"),
            "gear": tk.StringVar(value="N"),
            "load": tk.IntVar(value=35),
            "iat": tk.DoubleVar(value=90.0),
            "egt_b1": tk.DoubleVar(value=1450.0),
            "egt_b2": tk.DoubleVar(value=1470.0),
            "speed": tk.DoubleVar(value=25.0),
            "airshot_charges": tk.IntVar(value=3),
            "airshot_firing": tk.BooleanVar(value=False),
            "tank_psi": tk.DoubleVar(value=120.0),
            "wmi_tank": tk.IntVar(value=65),
            "wmi_commanded": tk.IntVar(value=250),
            "wmi_actual": tk.IntVar(value=250),
            "wmi_fault": tk.BooleanVar(value=False),
            "awc_enabled": tk.BooleanVar(value=True),
            "lean_deg": tk.DoubleVar(value=1.5),
            "traction": tk.StringVar(value="MED"),
            "traction_slip": tk.DoubleVar(value=0.0),
            "torque_cut": tk.IntVar(value=0),
            "traction_active": tk.BooleanVar(value=False),
            "traction_fault": tk.BooleanVar(value=False),
            "clutch_slip_pct": tk.IntVar(value=0),
            "clutch_slip_severity": tk.StringVar(value="NONE"),
            "turbo1": tk.DoubleVar(value=6.0),
            "turbo2": tk.DoubleVar(value=6.0),
            "wg1": tk.IntVar(value=45),
            "wg2": tk.IntVar(value=45),
            "mode": tk.StringVar(value="NORMAL"),
            "nfc_ok": tk.BooleanVar(value=True),
            "send_hud_commands": tk.BooleanVar(value=send_hud_commands),
            "send_ecu_requests": tk.BooleanVar(value=False),
            "boost_target": tk.DoubleVar(value=0.0),
            "wmi_arm": tk.BooleanVar(value=True),
            "flame_mode": tk.BooleanVar(value=False),
            "limp_mode": tk.BooleanVar(value=False),
            "limp_reason": tk.StringVar(value="PI REQUEST"),
            "engine_run": tk.BooleanVar(value=True),
            "left_indicator": tk.BooleanVar(value=False),
            "right_indicator": tk.BooleanVar(value=False),
            "high_beam": tk.BooleanVar(value=False),
            "neutral_light": tk.BooleanVar(value=True),
            "brake_light": tk.BooleanVar(value=False),
            "oil_warning": tk.BooleanVar(value=False),
            "wmi_pressure_ok": tk.BooleanVar(value=True),
            "oil_sensor_v": tk.DoubleVar(value=2.75),
            "wmi_tank_v": tk.DoubleVar(value=3.25),
            "air_tank_v": tk.DoubleVar(value=2.95),
            "arduino_5v": tk.DoubleVar(value=3.30),
            "air_compressor": tk.BooleanVar(value=False),
            "arduino_fw": tk.StringVar(value="0.1.0+1"),
            "gps_lock": tk.BooleanVar(value=True),
            "gps_lat": tk.StringVar(value="42.3314"),
            "gps_lon": tk.StringVar(value="-83.0458"),
            "msg": tk.StringVar(value="ECU OK | ARDUINO OK | CAN OK"),
        }
        for key,_,initial,_ in DYNAMICS_FIELDS+AIR_FIELDS:
            cls=tk.BooleanVar if type(initial) is bool else tk.StringVar if isinstance(initial,str) else tk.DoubleVar
            self.vars[key]=cls(value=initial)
        self.fault_vars=[tk.BooleanVar(value=False) for _ in FAULTS]
        self.demo_status=tk.StringVar(value="SYNTHETIC HUD DATA — isolate from the vehicle powertrain")
        self.thermal_stream=tk.BooleanVar(value=True);self.thermal_scenario=tk.StringVar(value="normal_warmup")
        self.thermal_sensor=tk.StringVar(value=self.systems.thermal.service.config.sensors[0].key)
        self.thermal_temperature=tk.StringVar(value="800");self.thermal_status=tk.StringVar(value="VALID");self.thermal_raw=tk.StringVar(value="0")
        self._build()
        self._build_system_tabs()
        self._tick()

    @staticmethod
    def _open_can_interface(interface: str, channel: str, bitrate: int, tty_baudrate: int | None):
        if interface == "candlelight":
            interface = "gs_usb"
        if interface == "socketcan":
            return SocketCANInterface(channel=channel, bitrate=bitrate)
        if interface == "gs_usb" and str(channel).isdigit():
            channel = int(channel)  # type: ignore[assignment]
        return PythonCANInterface(interface=interface, channel=channel, bitrate=bitrate, tty_baudrate=tty_baudrate)

    def _build(self) -> None:
        self.notebook=ttk.Notebook(self.root);self.notebook.grid(sticky="nsew")
        shell = ttk.Frame(self.notebook);self.notebook.add(shell,text="ECU / Bike / Legacy")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        rootf = ttk.Frame(canvas, padding=8)
        canvas_window = canvas.create_window((0, 0), window=rootf, anchor="nw")
        rootf.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(canvas_window, width=event.width))

        def scroll_units(delta: int) -> None:
            canvas.yview_scroll(delta, "units")

        def on_mousewheel(event) -> None:
            delta = getattr(event, "delta", 0)
            if delta:
                scroll_units(-1 if delta > 0 else 1)

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind("<Enter>", lambda event: canvas.bind_all("<MouseWheel>", on_mousewheel))
        canvas.bind_all("<Button-4>", lambda _event: scroll_units(-1))
        canvas.bind_all("<Button-5>", lambda _event: scroll_units(1))

        rootf.columnconfigure(0, weight=1)
        rootf.columnconfigure(1, weight=1)

        tty_status = f" / serial {self.tty_baudrate}" if self.tty_baudrate else ""
        status = "DRY RUN" if self.dry_run else f"{self.can_interface_name} / {self.can_channel_name} / {self.can_bitrate}{tty_status}"
        ttk.Label(rootf, text=f"CAN output: {status}").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ecu = ttk.LabelFrame(rootf, text="ECU -> HUD", padding=8)
        ecu.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        ard = ttk.LabelFrame(rootf, text="Controller -> HUD", padding=8)
        ard.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        cmds = ttk.LabelFrame(rootf, text="Command Simulation / Misc", padding=8)
        cmds.grid(row=2, column=0, columnspan=2, sticky="nsew")

        ecu_sliders = [
            ("RPM", "rpm", 0, 14000),
            ("TPS %", "tps", 0, 100),
            ("Boost avg psi", "boost", 0, 30),
            ("Boost Left", "boost_l", 0, 30),
            ("Boost Right", "boost_r", 0, 30),
            ("AFR Left", "afr_l", 8.0, 20.0),
            ("AFR Right", "afr_r", 8.0, 20.0),
            ("Knock Bitmask", "knock_mask", 0, 255),
            ("Oil P psi", "oilp", 0, 120),
            ("Oil T F", "oilt", 70, 320),
            ("Coolant F", "clt", 70, 280),
            ("Battery V", "batt_v", 8.0, 16.0),
            ("Fuel %", "fuel", 0, 100),
            ("Flex Ethanol %", "ethanol_pct", 0, 100),
            ("Injector PW ms", "inj_pw_ms", 0.0, 30.0),
            ("Injector Duty %", "inj_duty_pct", 0.0, 100.0),
            ("Engine Load %", "load", 0, 100),
            ("Intake F", "iat", 40, 250),
            ("EGT Bank1 F", "egt_b1", 500, 2000),
            ("EGT Bank2 F", "egt_b2", 500, 2000),
            ("Speed mph", "speed", 0, 220),
        ]
        for row, (label, key, lo, hi) in enumerate(ecu_sliders):
            self._slider(ecu, label, key, lo, hi, row)

        ard_sliders = [
            ("Tank Pressure psi", "tank_psi", 0, 200),
            ("WMI Tank %", "wmi_tank", 0, 100),
            ("WMI Cmd cc/min", "wmi_commanded", 0, 1000),
            ("WMI Act cc/min", "wmi_actual", 0, 1000),
            ("AWC Lean deg", "lean_deg", -15, 15),
            ("Turbo1 psi", "turbo1", 0, 30),
            ("Turbo2 psi", "turbo2", 0, 30),
            ("Wastegate1 %", "wg1", 0, 100),
            ("Wastegate2 %", "wg2", 0, 100),
            ("Clutch Slip %", "clutch_slip_pct", 0, 100),
        ]
        for row, (label, key, lo, hi) in enumerate(ard_sliders):
            self._slider(ard, label, key, lo, hi, row)

        row = len(ard_sliders)
        ttk.Label(ard, text="Airshot Charges").grid(row=row, column=0, sticky="w")
        ttk.Combobox(ard, textvariable=self.vars["airshot_charges"], values=[0, 1, 2, 3], width=8, state="readonly").grid(row=row, column=1, sticky="w")
        ttk.Checkbutton(ard, text="Airshot Firing", variable=self.vars["airshot_firing"]).grid(row=row, column=2, sticky="w")

        row += 1
        ttk.Checkbutton(ard, text="AWC Enabled", variable=self.vars["awc_enabled"]).grid(row=row, column=0, sticky="w")
        ttk.Checkbutton(ard, text="WMI Fault", variable=self.vars["wmi_fault"]).grid(row=row, column=1, sticky="w")
        ttk.Label(ard, text="Slip Severity").grid(row=row, column=2, sticky="e")
        ttk.Combobox(ard, textvariable=self.vars["clutch_slip_severity"], values=["NONE", "MILD", "MODERATE", "SEVERE"], width=12, state="readonly").grid(row=row, column=3, sticky="w")

        ttk.Label(cmds, text="Gear").grid(row=0, column=0, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["gear"], values=["N", "1", "2", "3", "4", "5", "6"], width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(cmds, text="Fuel Type").grid(row=0, column=2, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["fuel_type"], values=["87", "91", "93", "100", "E85", "C16"], width=8).grid(row=0, column=3, sticky="w")
        ttk.Label(cmds, text="Mode").grid(row=0, column=4, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["mode"], values=["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"], width=12).grid(row=0, column=5, sticky="w")
        ttk.Label(cmds, text="Traction").grid(row=0, column=6, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["traction"], values=["LOW", "MED", "HIGH", "OFF"], width=8).grid(row=0, column=7, sticky="w")

        ttk.Checkbutton(cmds, text="Send HUD Commands", variable=self.vars["send_hud_commands"]).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(cmds, text="Send ECU Requests", variable=self.vars["send_ecu_requests"]).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(cmds, text="NFC Auth OK", variable=self.vars["nfc_ok"]).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(cmds, text="TC Active", variable=self.vars["traction_active"]).grid(row=1, column=6, sticky="w")
        ttk.Checkbutton(cmds, text="TC Fault", variable=self.vars["traction_fault"]).grid(row=1, column=7, sticky="w")
        ttk.Label(cmds, text="Message").grid(row=2, column=0, sticky="w")
        ttk.Entry(cmds, textvariable=self.vars["msg"], width=60).grid(row=2, column=1, columnspan=5, sticky="ew")
        self._slider(cmds, "Boost Target psi", "boost_target", 0, 30, 3)
        self._slider(cmds, "Traction Slip %", "traction_slip", 0, 30, 4)
        self._slider(cmds, "Torque Cut %", "torque_cut", 0, 100, 5)

        ttk.Checkbutton(cmds, text="WMI Arm", variable=self.vars["wmi_arm"]).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(cmds, text="Flame", variable=self.vars["flame_mode"]).grid(row=6, column=1, sticky="w")
        ttk.Checkbutton(cmds, text="Limp", variable=self.vars["limp_mode"]).grid(row=6, column=2, sticky="w")
        ttk.Checkbutton(cmds, text="Run Switch", variable=self.vars["engine_run"]).grid(row=6, column=3, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["limp_reason"], values=[name for name in LIMP_REASON_CODES if name != "NONE"], width=18, state="readonly").grid(row=6, column=4, columnspan=2, sticky="w")
        ttk.Button(cmds, text="Air Shot V2 controls →", command=lambda:self.notebook.select(self.air_tab)).grid(row=6, column=6, sticky="w")

        ttk.Button(cmds, text="Send Once", command=self.send_all).grid(row=7, column=0, sticky="w", pady=(6, 0))
        ttk.Button(cmds, text="Quit", command=self.close).grid(row=7, column=1, sticky="w", pady=(6, 0))

        lighting = ttk.LabelFrame(rootf, text="Motorcycle Lighting -> HUD", padding=8)
        lighting.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        ttk.Checkbutton(lighting, text="Left Indicator", variable=self.vars["left_indicator"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(lighting, text="Right Indicator", variable=self.vars["right_indicator"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(lighting, text="High Beam", variable=self.vars["high_beam"]).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(lighting, text="Neutral", variable=self.vars["neutral_light"]).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(lighting, text="Brake", variable=self.vars["brake_light"]).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(lighting, text="Oil Warning", variable=self.vars["oil_warning"]).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(lighting, text="WMI Pressure OK", variable=self.vars["wmi_pressure_ok"]).grid(row=1, column=3, sticky="w")

        service = ttk.LabelFrame(rootf, text="Service Mode Data", padding=8)
        service.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        self._slider(service, "Oil Sensor V", "oil_sensor_v", 0.0, 5.0, 0)
        self._slider(service, "WMI Tank V", "wmi_tank_v", 0.0, 5.0, 1)
        self._slider(service, "Controller 3.3V", "arduino_5v", 3.0, 3.5, 2)
        self._slider(service, "Air Tank V", "air_tank_v", 0.0, 5.0, 3)
        ttk.Checkbutton(service, text="Air Compressor Relay", variable=self.vars["air_compressor"]).grid(row=4, column=0, sticky="w")
        ttk.Label(service, text="Controller FW").grid(row=4, column=1, sticky="e")
        ttk.Entry(service, textvariable=self.vars["arduino_fw"], width=12).grid(row=4, column=2, sticky="w")

        navigation = ttk.LabelFrame(rootf, text="Navigation GPS -> HUD", padding=8)
        navigation.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        ttk.Checkbutton(navigation, text="GPS Lock", variable=self.vars["gps_lock"]).grid(row=0, column=0, sticky="w")
        ttk.Label(navigation, text="Latitude").grid(row=0, column=1, sticky="e", padx=(16, 4))
        ttk.Entry(navigation, textvariable=self.vars["gps_lat"], width=16).grid(row=0, column=2, sticky="w")
        ttk.Label(navigation, text="Longitude").grid(row=0, column=3, sticky="e", padx=(16, 4))
        ttk.Entry(navigation, textvariable=self.vars["gps_lon"], width=16).grid(row=0, column=4, sticky="w")

    def _build_system_tabs(self):
        def tab(title):
            shell=ttk.Frame(self.notebook);self.notebook.add(shell,text=title)
            canvas=tk.Canvas(shell,highlightthickness=0);bar=ttk.Scrollbar(shell,orient="vertical",command=canvas.yview)
            canvas.configure(yscrollcommand=bar.set);canvas.pack(side="left",fill="both",expand=True);bar.pack(side="right",fill="y")
            body=ttk.Frame(canvas,padding=10);window=canvas.create_window((0,0),window=body,anchor="nw")
            body.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>",lambda e:canvas.itemconfigure(window,width=e.width))
            canvas.bind("<Enter>",lambda e:canvas.bind_all("<MouseWheel>",lambda event:canvas.yview_scroll(-1 if event.delta>0 else 1,"units")))
            ttk.Label(body,textvariable=self.demo_status,wraplength=850).grid(row=0,column=0,columnspan=4,sticky="w",pady=8)
            return shell,body
        def fields(body,metadata):
            for row,(key,label,initial,choices) in enumerate(metadata,1):
                ttk.Label(body,text=label).grid(row=row,column=0,sticky="w")
                if type(initial) is bool:widget=ttk.Checkbutton(body,variable=self.vars[key])
                elif choices:widget=ttk.Combobox(body,textvariable=self.vars[key],values=choices,state="readonly",width=28)
                else:widget=ttk.Entry(body,textvariable=self.vars[key],width=16)
                widget.grid(row=row,column=1,sticky="w",padx=10)
        _,d=tab("Dynamics / DBW / TCS / AWC");fields(d,DYNAMICS_FIELDS)
        faults=ttk.LabelFrame(d,text="Simulated fault mask (no hardware reset)",padding=8);faults.grid(row=1,column=2,rowspan=20,sticky="nw")
        for n,name in enumerate(FAULTS):ttk.Checkbutton(faults,text=name,variable=self.fault_vars[n]).grid(row=n,column=0,sticky="w")
        for n,name in enumerate(("Normal","Controlled lift","Rear slip","Lift + slip","Touchdown","DBW fault","Powertrain stopped")):
            ttk.Button(faults,text=name,command=lambda name=name:self._preset(name)).grid(row=len(FAULTS)+n,column=0,sticky="ew")
        ttk.Checkbutton(faults,text="Allow command transmission (shared opt-in)",variable=self.vars["send_hud_commands"]).grid(row=22,column=0)
        ttk.Button(faults,text="Send rider levels / curve / weather",command=self._dynamics_settings).grid(row=23,column=0,sticky="ew")
        ttk.Button(faults,text="Request LATCHED powertrain STOP",command=self._powertrain_stop).grid(row=24,column=0,sticky="ew")
        for n,(key,label) in enumerate((("wheelie_target","target"),("wheelie_max","maximum"),("lean_left","left lean"),("lean_right","right lean"))):
            ttk.Button(faults,text="Send rider "+label,command=lambda n=n,key=key:self._rider_envelope(n,key)).grid(row=25+n,column=0,sticky="ew")
        self.air_tab,a=tab("Air Shot V2");fields(a,AIR_FIELDS)
        controls=ttk.LabelFrame(a,text="Explicit commands — isolated bench only",padding=8);controls.grid(row=1,column=2,rowspan=10,sticky="nw")
        ttk.Checkbutton(controls,text="Allow command transmission",variable=self.vars["send_hud_commands"]).pack(anchor="w")
        ttk.Button(controls,text="Send selected OFF / MANUAL / AUTO",command=self._air_mode).pack(fill="x")
        fire=ttk.Button(controls,text="Hold to request Air Shot")
        fire.pack(fill="x");fire.bind("<ButtonPress-1>",lambda e:self._hold_air(True));fire.bind("<ButtonRelease-1>",lambda e:self._hold_air(False));fire.bind("<Leave>",lambda e:self._hold_air(False))
        ttk.Label(controls,text="Telemetry sliders do not operate valves.\nNo calibration upload or DBWX2 motor target\nis emitted by these new controls.").pack(anchor="w",pady=12)
        _,t=tab("Thermal node / 32 channels")
        ttk.Checkbutton(t,text="Transmit thermal node (uncheck for dropout)",variable=self.thermal_stream).grid(row=1,column=0,sticky="w")
        ttk.Combobox(t,textvariable=self.thermal_scenario,values=SCENARIOS,state="readonly",width=30).grid(row=2,column=0,sticky="w")
        ttk.Button(t,text="Restart scenario",command=self._thermal_restart).grid(row=2,column=1)
        ttk.Combobox(t,textvariable=self.thermal_sensor,values=[s.key for s in self.systems.thermal.service.config.sensors],state="readonly",width=35).grid(row=3,column=0,sticky="w")
        ttk.Label(t,text="Temperature °C").grid(row=4,column=0,sticky="w");ttk.Entry(t,textvariable=self.thermal_temperature).grid(row=4,column=1)
        ttk.Combobox(t,textvariable=self.thermal_status,values=[s.name for s in SensorStatus],state="readonly").grid(row=5,column=0,sticky="w")
        ttk.Button(t,text="Override selected sensor",command=self._thermal_override).grid(row=5,column=1)
        ttk.Button(t,text="Clear all overrides",command=self.systems.thermal_overrides.clear).grid(row=6,column=1)
        ttk.Label(t,text="Raw front-end diagnostic (synthetic)").grid(row=7,column=0,sticky="w");ttk.Entry(t,textvariable=self.thermal_raw).grid(row=7,column=1)
        ttk.Button(t,text="Set selected raw value",command=self._thermal_raw_override).grid(row=8,column=1)
        for n,s in enumerate(self.systems.thermal.service.config.sensors,10):ttk.Label(t,text=f"{s.sensor_id:02d}  {s.key} — {s.name}").grid(row=n,column=0,columnspan=2,sticky="w")
    def _thermal_restart(self):
        self.systems.thermal.scenario=self.thermal_scenario.get();self.systems.thermal.elapsed_s=0
    def _thermal_override(self):
        import math
        try:
            value=float(self.thermal_temperature.get())
            if not math.isfinite(value):raise ValueError()
            self.systems.thermal_overrides[self.thermal_sensor.get()]=(value,SensorStatus[self.thermal_status.get()])
        except (ValueError,KeyError):self.demo_status.set("Invalid thermal override")
    def _thermal_raw_override(self):
        try:
            value=int(self.thermal_raw.get())
            if not 0<=value<=65535:raise ValueError()
            self.systems.thermal_raw[self.thermal_sensor.get()]=value
        except ValueError:self.demo_status.set("Raw diagnostic must be an integer 0–65535")
    def _preset(self,name):
        for key,_,initial,_ in DYNAMICS_FIELDS:self.vars[key].set(initial)
        for v in self.fault_vars:v.set(False)
        changes={
            "Controlled lift":dict(state="AWC TRACKING",event="CONTROLLED LIFT",flags=28,pitch=9,front=16,rear=20,front_contact=0,wheelie_confidence=100),
            "Rear slip":dict(state="TCS ACTIVE",event="REAR SLIP",flags=17,rear=24,slip=20,slip_confidence=100,permitted=20,tcs_limit=20),
            "Lift + slip":dict(state="TCS + AWC",event="LIFT + SLIP",flags=23,pitch=25,rear=24,slip=20,front_contact=0,slip_confidence=100,wheelie_confidence=100,permitted=10,tcs_limit=20,awc_limit=10),
            "Touchdown":dict(state="TCS MONITOR",event="TOUCHDOWN",flags=16,pitch_rate=-10,permitted=20,air_margin=0),
            "DBW fault":dict(state="FAULT",flags=0,permitted=0,boost_target=0,air_margin=0),
            "Powertrain stopped":dict(state="FAULT",flags=0,permitted=0,boost_target=0,air_margin=0),
        }.get(name,{})
        for key,value in changes.items():self.vars["vdc_"+key].set(value)
        if name=="DBW fault":self.fault_vars[8].set(True)
        if name=="Powertrain stopped":self.fault_vars[13].set(True)
    def _command_allowed(self):
        allowed=bool(self.vars["send_hud_commands"].get())
        if not allowed:self.demo_status.set("Command blocked: enable command transmission explicitly")
        return allowed
    def _dynamics_settings(self):
        if not self._command_allowed():return
        self.fire_sequence=(self.fire_sequence+1)&255
        self._send(0x208,bytes((1,LEVELS.index(self.vars["vdc_tcs"].get()),LEVELS.index(self.vars["vdc_awc"].get()),int(self.vars["vdc_curve"].get()),int(self.vars["vdc_weather_assist"].get()),0,self.fire_sequence,0xA5)))
    def _air_mode(self):
        if self._command_allowed():self._send(*mode_frame(self.vars["air_mode"].get()))
    def _rider_envelope(self,parameter,key):
        import math
        if not self._command_allowed():return
        value=float(self.vars["vdc_"+key].get())
        if not math.isfinite(value) or value<0 or (parameter!=0 and value==0):
            self.demo_status.set("Invalid rider envelope; controller engineering limits remain authoritative");return
        self.fire_sequence=(self.fire_sequence+1)&255
        self._send(0x209,struct.pack(">BBfBB",1,parameter,value,self.fire_sequence,0xA5))
    def _hold_air(self,held):
        if held and not self._command_allowed():return
        was_held=self.fire_held;self.fire_held=held
        if held or was_held:
            self.fire_sequence=(self.fire_sequence+1)&65535;self._send(*fire_frame(held,self.fire_sequence))
    def _powertrain_stop(self):
        if self._command_allowed() and messagebox.askyesno("Latched powertrain stop","Send STOP to the controller? This removes torque authority and cannot be cleared by a run-ON command."):
            self._send(0x20A,b'\x01STOP\xa5')
    def _slider(self, parent, label, key, lo, hi, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        s = ttk.Scale(parent, from_=lo, to=hi, variable=self.vars[key], orient="horizontal")
        s.grid(row=row, column=1, columnspan=2, sticky="ew")
        ttk.Label(parent, textvariable=self.vars[key], width=10).grid(row=row, column=3, sticky="e")
        parent.columnconfigure(1, weight=1)

    def _send(self, arb_id: int, payload: bytes) -> None:
        if self.iface:
            self.iface.send(arb_id, payload)
        else:
            print(f"TX 0x{arb_id:03X} {payload.hex()}")

    def _fire_air_shot(self) -> None:
        self._hold_air(True)

    @staticmethod
    def _f_to_cx10(temp_f: float) -> int:
        return int(max(0.0, (temp_f - 32.0) * 5.0 / 9.0) * 10)

    @staticmethod
    def _version_part(value: str, limit: int) -> int:
        try:
            return max(0, min(limit, int(value or 0)))
        except ValueError:
            return 0

    @staticmethod
    def _coordinate(value: object, lo: float, hi: float) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if lo <= parsed <= hi else None

    def send_all(self) -> None:
        self.systems.values.update({key:self.vars[key].get() for key,_,_,_ in DYNAMICS_FIELDS+AIR_FIELDS})
        self.systems.faults=sum(1<<n for n,v in enumerate(self.fault_vars) if v.get())
        self.systems.thermal_stream=self.thermal_stream.get();self.systems.thermal.scenario=self.thermal_scenario.get()
        system_frames=self.systems.frames() # validate before transmitting this cycle
        for fid,data in system_frames:self._send(fid,data)
        if self.fire_held:
            if self._command_allowed():self._hold_air(True)
            else:self._hold_air(False)
        gear_map = {"N": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
        fuel_type_map = {"87": 0, "91": 1, "93": 2, "100": 3, "E85": 4, "C16": 5}
        mode_map = {"ECO": 1, "NORMAL": 2, "SPORT": 3, "RACE": 4, "ALBATROSS": 5}
        trac_map = {"LOW": 1, "MED": 2, "HIGH": 3, "OFF": 4}
        slip_sev_map = {"NONE": 0, "MILD": 1, "MODERATE": 2, "SEVERE": 3}

        rpm = int(self.vars["rpm"].get())
        speed_mps100 = int(max(0.0, float(self.vars["speed"].get()) / 2.236936) * 100)
        oil_t_c10 = self._f_to_cx10(float(self.vars["oilt"].get()))
        clt_c10 = self._f_to_cx10(float(self.vars["clt"].get()))
        iat_c10 = self._f_to_cx10(float(self.vars["iat"].get()))
        egt1_c10 = self._f_to_cx10(float(self.vars["egt_b1"].get()))
        egt2_c10 = self._f_to_cx10(float(self.vars["egt_b2"].get()))
        lean_raw = int(float(self.vars["lean_deg"].get()) * 10)
        mode_code = mode_map[self.vars["mode"].get()]
        fuel_code = fuel_type_map[self.vars["fuel_type"].get()]
        traction_level_code = trac_map[self.vars["traction"].get()]
        traction_slip_x10 = int(max(-100.0, min(100.0, float(self.vars["traction_slip"].get()))) * 10)
        torque_cut_pct = max(0, min(100, int(self.vars["torque_cut"].get())))

        self._send(int(ECUToHudID.ENGINE_RPM), struct.pack(">H", max(0, min(65535, rpm))))
        self._send(int(ECUToHudID.THROTTLE_POSITION), bytes((max(0, min(100, int(self.vars["tps"].get()))),)))
        self._send(int(ECUToHudID.BOOST_PRESSURE), struct.pack(">H", int(max(0.0, float(self.vars["boost"].get())) * 10)))
        self._send(
            int(ECUToHudID.BOOST_PRESSURE_BANKS),
            struct.pack(
                ">HH",
                int(max(0.0, float(self.vars["boost_l"].get())) * 10),
                int(max(0.0, float(self.vars["boost_r"].get())) * 10),
            ),
        )
        self._send(int(ECUToHudID.AFR_BANKS), struct.pack(">HH", int(float(self.vars["afr_l"].get()) * 100), int(float(self.vars["afr_r"].get()) * 100)))
        self._send(int(ECUToHudID.KNOCK_STATUS), struct.pack(">H", max(0, min(0xFFFF, int(self.vars["knock_mask"].get())))))
        self._send(int(ECUToHudID.OIL_PRESSURE_TEMP), struct.pack(">HH", int(max(0.0, float(self.vars["oilp"].get())) * 10), oil_t_c10))
        self._send(int(ECUToHudID.COOLANT_TEMP), struct.pack(">H", clt_c10))
        self._send(int(ECUToHudID.BATTERY_VOLTAGE), struct.pack(">H", int(max(0.0, float(self.vars["batt_v"].get())) * 1000)))
        self._send(int(ECUToHudID.FUEL_LEVEL), bytes((max(0, min(100, int(self.vars["fuel"].get()))),)))
        self._send(int(ECUToHudID.FLEX_FUEL), bytes((max(0, min(100, int(self.vars["ethanol_pct"].get()))),)))
        self._send(
            int(ECUToHudID.INJECTOR_STATUS),
            struct.pack(
                ">HH",
                max(0, min(65535, int(float(self.vars["inj_pw_ms"].get()) * 100))),
                max(0, min(1000, int(float(self.vars["inj_duty_pct"].get()) * 10))),
            ),
        )
        self._send(int(ECUToHudID.GEAR_POSITION), bytes((gear_map[self.vars["gear"].get()],)))
        self._send(int(ECUToHudID.ENGINE_LOAD), bytes((max(0, min(100, int(self.vars["load"].get()))),)))
        self._send(int(ECUToHudID.INTAKE_AIR_TEMP), struct.pack(">H", iat_c10))
        self._send(int(ECUToHudID.EXHAUST_GAS_TEMP), struct.pack(">HH", egt1_c10, egt2_c10))

        airshot_flags = 0x01 if bool(self.vars["airshot_firing"].get()) else 0x00
        self._send(int(ArduinoToHudID.AIR_SHOT_STATUS), bytes((max(0, min(3, int(self.vars["airshot_charges"].get()))), airshot_flags)))
        self._send(int(ArduinoToHudID.AWC_STATE), bytes((1 if bool(self.vars["awc_enabled"].get()) else 0, max(-127, min(127, int(lean_raw / 10))) & 0xFF)))
        self._send(int(ArduinoToHudID.TANK_PRESSURE), struct.pack(">H", int(max(0.0, float(self.vars["tank_psi"].get())) * 10)))
        self._send(int(ArduinoToHudID.TWIN_TURBO_STATUS), struct.pack(">HH", int(max(0.0, float(self.vars["turbo1"].get())) * 10), int(max(0.0, float(self.vars["turbo2"].get())) * 10)))
        self._send(int(ArduinoToHudID.WASTEGATE_STATUS), bytes((max(0, min(100, int(self.vars["wg1"].get()))), max(0, min(100, int(self.vars["wg2"].get()))))))
        self._send(int(ArduinoToHudID.GEAR_POSITION), bytes((gear_map[self.vars["gear"].get()],)))
        self._send(int(ArduinoToHudID.WHEEL_SPEED), struct.pack(">HH", speed_mps100, speed_mps100))
        self._send(int(ArduinoToHudID.FUEL_LEVEL), bytes((max(0, min(100, int(self.vars["fuel"].get()))),)))
        if bool(self.vars["send_hud_commands"].get()):
            self._send(int(ArduinoToHudID.FUEL_TYPE_STATUS), bytes((fuel_type_map[self.vars["fuel_type"].get()],)))
        self._send(int(ArduinoToHudID.OIL_PRESSURE_STATUS), struct.pack(">H", int(max(0.0, float(self.vars["oilp"].get())) * 10)))
        self._send(
            int(ArduinoToHudID.WMI_STATUS),
            struct.pack(
                ">BHHB",
                max(0, min(100, int(self.vars["wmi_tank"].get()))),
                max(0, min(65535, int(self.vars["wmi_commanded"].get()))),
                max(0, min(65535, int(self.vars["wmi_actual"].get()))),
                1 if bool(self.vars["wmi_fault"].get()) else 0,
            ),
        )
        self._send(
            int(ArduinoToHudID.CLUTCH_SLIP_STATUS),
            bytes(
                (
                    max(0, min(100, int(self.vars["clutch_slip_pct"].get()))),
                    slip_sev_map.get(self.vars["clutch_slip_severity"].get(), 0),
                )
            ),
        )
        tc_flags = 0
        tc_flags |= 0x01 if bool(self.vars["traction_active"].get()) else 0
        tc_flags |= 0x02 if bool(self.vars["traction_fault"].get()) else 0
        self._send(
            int(ArduinoToHudID.TRACTION_STATUS),
            struct.pack(
                ">hBB",
                traction_slip_x10,
                torque_cut_pct,
                tc_flags,
            ),
        )

        if bool(self.vars["send_ecu_requests"].get()):
            self._send(int(ArduinoToEcuID.TORQUE_CUT_REQUEST), bytes((torque_cut_pct,)))
            self._send(int(ArduinoToEcuID.TRACTION_SLIP_REQUEST), struct.pack(">hB", traction_slip_x10, tc_flags))

        if bool(self.vars["send_hud_commands"].get()):
            self._send(*build_boost_target_frame(float(self.vars["boost_target"].get())))
            self._send(*build_mode_selection_frame(mode_code))
            self._send(*build_traction_level_frame(traction_level_code))
            self._send(*build_fuel_type_frame(fuel_code))
            self._send(*build_nfc_auth_frame(bool(self.vars["nfc_ok"].get())))
            self._send(*build_wmi_enable_frame(bool(self.vars["wmi_arm"].get())))
            self._send(*build_flame_mode_frame(bool(self.vars["flame_mode"].get())))
            self._send(*build_ecu_rev_limiter_strategy_frame(bool(self.vars["flame_mode"].get())))
            self._send(*build_limp_mode_frame(bool(self.vars["limp_mode"].get()), str(self.vars["limp_reason"].get())))
            self._send(*build_engine_run_switch_frame(bool(self.vars["engine_run"].get())))
            self._send(*build_ecu_fuel_profile_frame(fuel_code))
            self._send(*build_ecu_spark_table_frame(mode_code))
        light_flags = 0
        light_flags |= 0x01 if bool(self.vars["left_indicator"].get()) else 0
        light_flags |= 0x02 if bool(self.vars["right_indicator"].get()) else 0
        light_flags |= 0x04 if bool(self.vars["high_beam"].get()) else 0
        light_flags |= 0x08 if bool(self.vars["neutral_light"].get()) else 0
        light_flags |= 0x10 if bool(self.vars["brake_light"].get()) else 0
        light_flags |= 0x20 if bool(self.vars["oil_warning"].get()) else 0
        self._send(int(ArduinoToHudID.LIGHT_STATUS), bytes((light_flags,)))

        sensor_mv = (
            max(0, min(65535, int(float(self.vars["oil_sensor_v"].get()) * 1000))),
            max(0, min(65535, int(float(self.vars["wmi_tank_v"].get()) * 1000))),
            max(0, min(65535, int(float(self.vars["arduino_5v"].get()) * 1000))),
            max(0, min(65535, int(float(self.vars["air_tank_v"].get()) * 1000))),
        )
        self._send(int(ArduinoToHudID.SERVICE_SENSOR_VOLTAGES), struct.pack(">HHHH", *sensor_mv))
        input_bits = light_flags
        input_bits |= 0x40 if bool(self.vars["wmi_pressure_ok"].get()) else 0
        output_bits = 0
        output_bits |= 0x01 if int(self.vars["wg1"].get()) > 0 else 0
        output_bits |= 0x02 if int(self.vars["wg2"].get()) > 0 else 0
        output_bits |= 0x04 if bool(self.vars["wmi_arm"].get()) else 0
        output_bits |= 0x08 if bool(self.vars["flame_mode"].get()) else 0
        output_bits |= 0x10 if bool(self.vars["airshot_firing"].get()) else 0
        output_bits |= 0x20 if bool(self.vars["air_compressor"].get()) else 0
        output_bits |= 0x40 if int(self.vars["wg1"].get()) > 0 else 0
        output_bits |= 0x80 if int(self.vars["wg2"].get()) > 0 else 0
        command_bits = 0
        command_bits |= 0x01 if bool(self.vars["nfc_ok"].get()) else 0
        command_bits |= 0x02 if bool(self.vars["flame_mode"].get()) else 0
        command_bits |= 0x04 if bool(self.vars["limp_mode"].get()) else 0
        command_bits |= 0x08 if bool(self.vars["engine_run"].get()) else 0
        command_bits |= 0x10 if bool(self.vars["wmi_arm"].get()) else 0
        fault_bits = 0
        fault_bits |= 0x04 if bool(self.vars["wmi_fault"].get()) else 0
        fault_bits |= 0x08 if bool(self.vars["traction_fault"].get()) else 0
        self._send(int(ArduinoToHudID.SERVICE_DIGITAL_STATES), bytes((input_bits, output_bits, command_bits, fault_bits)))
        limp_active = bool(self.vars["limp_mode"].get())
        limp_reason_code = LIMP_REASON_CODES.get(str(self.vars["limp_reason"].get()).upper(), LIMP_REASON_CODES["PI REQUEST"])
        self._send(int(ArduinoToHudID.LIMP_STATUS), bytes((1 if limp_active else 0, limp_reason_code if limp_active else 0)))
        fw = str(self.vars["arduino_fw"].get()).replace("+", ".").split(".")
        major, minor, patch, build = (fw + ["0", "0", "0", "0"])[:4]
        build_no = self._version_part(build, 65535)
        self._send(
            int(ArduinoToHudID.SERVICE_FIRMWARE_VERSION),
            bytes(
                (
                    0x04,
                    self._version_part(major, 255),
                    self._version_part(minor, 255),
                    self._version_part(patch, 255),
                    (build_no >> 8) & 0xFF,
                    build_no & 0xFF,
                )
            ),
        )

        payload = {k: (v.get() if hasattr(v, "get") else v) for k, v in self.vars.items()}
        gps_lat = self._coordinate(payload.get("gps_lat"), -85.0, 85.0)
        gps_lon = self._coordinate(payload.get("gps_lon"), -180.0, 180.0)
        if gps_lat is None or gps_lon is None:
            payload.pop("gps_lat", None)
            payload.pop("gps_lon", None)
        else:
            payload["gps_lat"] = gps_lat
            payload["gps_lon"] = gps_lon
        if not bool(self.vars["send_hud_commands"].get()):
            for key in ("mode", "fuel_type", "traction", "boost_target", "wmi_arm", "flame_mode", "engine_run", "nfc_ok"):
                payload.pop(key, None)
        payload["msg"] = self.vars["msg"].get()
        payload["demo_system_frames"]=[[fid,data.hex()] for fid,data in system_frames]
        packet = json.dumps(payload).encode("utf-8")
        for p in self.udp_ports:
            self.sock.sendto(packet, (self.udp_host, p))

    def _tick(self) -> None:
        try:self.send_all()
        except (ValueError,TypeError,tk.TclError,struct.error) as exc:self.demo_status.set(f"Invalid demo value: {exc}")
        finally:self.root.after(100, self._tick)

    def close(self) -> None:
        self._hold_air(False)
        if self.iface:
            self.iface.stop()
        self.sock.close()
        self.root.destroy()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--interface", default="socketcan", help="python-can backend: socketcan, slcan, pcan, gs_usb/candlelight, etc.")
    p.add_argument("--channel", default="can0", help="CAN channel, e.g. can0 on Linux or COM5 for CANable SLCAN on Windows")
    p.add_argument("--bitrate", type=int, default=500_000, help="CAN bus bitrate; Albatross defaults to 500000")
    p.add_argument("--tty-baudrate", type=int, default=None, help="optional SLCAN serial baud rate, e.g. 115200 or 2000000")
    p.add_argument("--canable", metavar="COM_PORT", help="shortcut for CANable/CANtact SLCAN firmware, e.g. --canable COM5")
    p.add_argument("--candlelight", action="store_true", help="shortcut for CANable/candleLight gs_usb firmware; does not use a COM port")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--udp-target", default="127.0.0.1:5005")
    p.add_argument("--send-hud-commands", action="store_true", help="also emit Pi/HUD-owned command frames")
    args = p.parse_args()
    if args.canable:
        args.interface = "slcan"
        args.channel = args.canable
        if args.tty_baudrate is None:
            args.tty_baudrate = 2_000_000
    if args.candlelight:
        args.interface = "gs_usb"
        args.channel = "0"

    root = tk.Tk()
    app = App(
        root,
        interface=args.interface,
        channel=args.channel,
        bitrate=args.bitrate,
        tty_baudrate=args.tty_baudrate,
        dry_run=args.dry_run,
        udp_target=args.udp_target,
        send_hud_commands=args.send_hud_commands,
    )
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
