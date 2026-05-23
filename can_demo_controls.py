"""Quick CAN demo control panel with sliders/buttons/text boxes.

Emits ECU and Arduino HUD frames by default. HUD-owned command frames and
Arduino-to-ECU intervention requests are opt-in so the panel can stay connected
without fighting the real HUD controls.

Usage:
  python can_demo_controls.py --channel can0
  python can_demo_controls.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import tkinter as tk
from tkinter import ttk

from albatross_pi.canbus.encode import (
    build_boost_target_frame,
    build_ecu_fuel_profile_frame,
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
from albatross_pi.canbus.ids import ArduinoToEcuID, ArduinoToHudID, ECUToHudID
from albatross_pi.canbus.iface import SocketCANInterface


class App:
    def __init__(self, root: tk.Tk, channel: str, dry_run: bool, udp_target: str, send_hud_commands: bool) -> None:
        self.root = root
        self.root.title("Albatross CAN Demo Controls")
        self.dry_run = dry_run
        self.iface = None if dry_run else SocketCANInterface(channel=channel)
        self.udp_host, self.udp_port = udp_target.split(":")
        self.udp_port = int(self.udp_port)
        self.udp_ports = sorted({self.udp_port, 5505})
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.iface:
            try:
                self.iface.start()
            except RuntimeError as exc:
                print(f"[can-demo] {exc}")
                print("[can-demo] Falling back to --dry-run (printing frames).")
                self.iface = None
                self.dry_run = True

        self.vars = {
            "rpm": tk.IntVar(value=2000),
            "tps": tk.IntVar(value=20),
            "boost": tk.DoubleVar(value=4.0),
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
            "arduino_5v": tk.DoubleVar(value=5.00),
            "air_compressor": tk.BooleanVar(value=False),
            "arduino_fw": tk.StringVar(value="0.1.0+1"),
            "msg": tk.StringVar(value="ECU OK | ARDUINO OK | CAN OK"),
        }
        self._build()
        self._tick()

    def _build(self) -> None:
        rootf = ttk.Frame(self.root, padding=8)
        rootf.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        rootf.columnconfigure(0, weight=1)
        rootf.columnconfigure(1, weight=1)

        ecu = ttk.LabelFrame(rootf, text="ECU -> HUD", padding=8)
        ecu.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        ard = ttk.LabelFrame(rootf, text="Arduino -> HUD", padding=8)
        ard.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        cmds = ttk.LabelFrame(rootf, text="Command Simulation / Misc", padding=8)
        cmds.grid(row=1, column=0, columnspan=2, sticky="nsew")

        ecu_sliders = [
            ("RPM", "rpm", 0, 14000),
            ("TPS %", "tps", 0, 100),
            ("Boost psi", "boost", 0, 30),
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
        ttk.Combobox(ard, textvariable=self.vars["airshot_charges"], values=[0, 1, 2, 3, 4, 5], width=8, state="readonly").grid(row=row, column=1, sticky="w")
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

        ttk.Button(cmds, text="Send Once", command=self.send_all).grid(row=7, column=0, sticky="w", pady=(6, 0))
        ttk.Button(cmds, text="Quit", command=self.close).grid(row=7, column=1, sticky="w", pady=(6, 0))

        lighting = ttk.LabelFrame(rootf, text="Motorcycle Lighting -> HUD", padding=8)
        lighting.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        ttk.Checkbutton(lighting, text="Left Indicator", variable=self.vars["left_indicator"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(lighting, text="Right Indicator", variable=self.vars["right_indicator"]).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(lighting, text="High Beam", variable=self.vars["high_beam"]).grid(row=0, column=2, sticky="w")
        ttk.Checkbutton(lighting, text="Neutral", variable=self.vars["neutral_light"]).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(lighting, text="Brake", variable=self.vars["brake_light"]).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(lighting, text="Oil Warning", variable=self.vars["oil_warning"]).grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(lighting, text="WMI Pressure OK", variable=self.vars["wmi_pressure_ok"]).grid(row=1, column=3, sticky="w")

        service = ttk.LabelFrame(rootf, text="Service Mode Data", padding=8)
        service.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        self._slider(service, "Oil Sensor V", "oil_sensor_v", 0.0, 5.0, 0)
        self._slider(service, "WMI Tank V", "wmi_tank_v", 0.0, 5.0, 1)
        self._slider(service, "Arduino 5V", "arduino_5v", 4.5, 5.3, 2)
        ttk.Checkbutton(service, text="Air Compressor Relay", variable=self.vars["air_compressor"]).grid(row=3, column=0, sticky="w")
        ttk.Label(service, text="Arduino FW").grid(row=3, column=1, sticky="e")
        ttk.Entry(service, textvariable=self.vars["arduino_fw"], width=12).grid(row=3, column=2, sticky="w")

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

    @staticmethod
    def _f_to_cx10(temp_f: float) -> int:
        return int(max(0.0, (temp_f - 32.0) * 5.0 / 9.0) * 10)

    @staticmethod
    def _version_part(value: str, limit: int) -> int:
        try:
            return max(0, min(limit, int(value or 0)))
        except ValueError:
            return 0

    def send_all(self) -> None:
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
        self._send(int(ArduinoToHudID.AIR_SHOT_STATUS), bytes((max(0, min(255, int(self.vars["airshot_charges"].get()))), airshot_flags)))
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
            self._send(*build_limp_mode_frame(bool(self.vars["limp_mode"].get())))
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
            0,
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
        fw = str(self.vars["arduino_fw"].get()).replace("+", ".").split(".")
        major, minor, patch, build = (fw + ["0", "0", "0", "0"])[:4]
        build_no = self._version_part(build, 65535)
        self._send(
            int(ArduinoToHudID.SERVICE_FIRMWARE_VERSION),
            bytes(
                (
                    0x01,
                    self._version_part(major, 255),
                    self._version_part(minor, 255),
                    self._version_part(patch, 255),
                    (build_no >> 8) & 0xFF,
                    build_no & 0xFF,
                )
            ),
        )

        payload = {k: (v.get() if hasattr(v, "get") else v) for k, v in self.vars.items()}
        if not bool(self.vars["send_hud_commands"].get()):
            for key in ("mode", "fuel_type", "traction", "boost_target", "wmi_arm", "flame_mode", "limp_mode", "engine_run", "nfc_ok"):
                payload.pop(key, None)
        payload["msg"] = self.vars["msg"].get()
        packet = json.dumps(payload).encode("utf-8")
        for p in self.udp_ports:
            self.sock.sendto(packet, (self.udp_host, p))

    def _tick(self) -> None:
        self.send_all()
        self.root.after(100, self._tick)

    def close(self) -> None:
        if self.iface:
            self.iface.stop()
        self.root.destroy()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--channel", default="can0")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--udp-target", default="127.0.0.1:5005")
    p.add_argument("--send-hud-commands", action="store_true", help="also emit Pi/HUD-owned command frames")
    args = p.parse_args()

    root = tk.Tk()
    app = App(root, args.channel, args.dry_run, args.udp_target, args.send_hud_commands)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
