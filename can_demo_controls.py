"""Quick CAN demo control panel with sliders/buttons/text boxes.

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

from albatross_pi.canbus.ids import ArduinoToHudID, ECUToHudID, PiToArduinoID
from albatross_pi.canbus.iface import SocketCANInterface


class App:
    def __init__(self, root: tk.Tk, channel: str, dry_run: bool, udp_target: str) -> None:
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
            "fuel": tk.IntVar(value=75),
            "gear": tk.StringVar(value="N"),
            "load": tk.IntVar(value=35),
            "iat": tk.DoubleVar(value=90.0),
            "egt_b1": tk.DoubleVar(value=1450.0),
            "egt_b2": tk.DoubleVar(value=1470.0),
            "speed": tk.DoubleVar(value=25.0),
            "airshot_charges": tk.IntVar(value=3),
            "airshot_firing": tk.BooleanVar(value=False),
            "tank_psi": tk.DoubleVar(value=120.0),
            "awc_enabled": tk.BooleanVar(value=True),
            "lean_deg": tk.DoubleVar(value=1.5),
            "traction": tk.StringVar(value="MED"),
            "turbo1": tk.DoubleVar(value=6.0),
            "turbo2": tk.DoubleVar(value=6.0),
            "wg1": tk.IntVar(value=45),
            "wg2": tk.IntVar(value=45),
            "mode": tk.StringVar(value="NORMAL"),
            "nfc_ok": tk.BooleanVar(value=True),
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
        cmds = ttk.LabelFrame(rootf, text="Pi Commands / Misc", padding=8)
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
            ("Fuel %", "fuel", 0, 100),
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
            ("AWC Lean deg", "lean_deg", -15, 15),
            ("Turbo1 psi", "turbo1", 0, 30),
            ("Turbo2 psi", "turbo2", 0, 30),
            ("Wastegate1 %", "wg1", 0, 100),
            ("Wastegate2 %", "wg2", 0, 100),
        ]
        for row, (label, key, lo, hi) in enumerate(ard_sliders):
            self._slider(ard, label, key, lo, hi, row)

        row = len(ard_sliders)
        ttk.Label(ard, text="Airshot Charges").grid(row=row, column=0, sticky="w")
        ttk.Combobox(ard, textvariable=self.vars["airshot_charges"], values=[0, 1, 2, 3, 4, 5], width=8, state="readonly").grid(row=row, column=1, sticky="w")
        ttk.Checkbutton(ard, text="Airshot Firing", variable=self.vars["airshot_firing"]).grid(row=row, column=2, sticky="w")

        row += 1
        ttk.Checkbutton(ard, text="AWC Enabled", variable=self.vars["awc_enabled"]).grid(row=row, column=0, sticky="w")

        ttk.Label(cmds, text="Gear").grid(row=0, column=0, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["gear"], values=["N", "1", "2", "3", "4", "5", "6"], width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(cmds, text="Mode").grid(row=0, column=2, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["mode"], values=["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"], width=12).grid(row=0, column=3, sticky="w")
        ttk.Label(cmds, text="Traction").grid(row=0, column=4, sticky="w")
        ttk.Combobox(cmds, textvariable=self.vars["traction"], values=["LOW", "MED", "HIGH", "OFF"], width=8).grid(row=0, column=5, sticky="w")

        ttk.Checkbutton(cmds, text="NFC Auth OK", variable=self.vars["nfc_ok"]).grid(row=1, column=0, sticky="w")
        ttk.Label(cmds, text="Message").grid(row=1, column=1, sticky="e")
        ttk.Entry(cmds, textvariable=self.vars["msg"], width=60).grid(row=1, column=2, columnspan=4, sticky="ew")

        ttk.Button(cmds, text="Send Once", command=self.send_all).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Button(cmds, text="Quit", command=self.close).grid(row=2, column=1, sticky="w", pady=(6, 0))
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

    def send_all(self) -> None:
        gear_map = {"N": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
        mode_map = {"ECO": 1, "NORMAL": 2, "SPORT": 3, "RACE": 4, "ALBATROSS": 5}
        trac_map = {"LOW": 1, "MED": 2, "HIGH": 3, "OFF": 4}

        rpm = int(self.vars["rpm"].get())
        speed_mps100 = int(max(0.0, float(self.vars["speed"].get()) / 2.236936) * 100)
        oil_t_c10 = self._f_to_cx10(float(self.vars["oilt"].get()))
        clt_c10 = self._f_to_cx10(float(self.vars["clt"].get()))
        iat_c10 = self._f_to_cx10(float(self.vars["iat"].get()))
        egt1_c10 = self._f_to_cx10(float(self.vars["egt_b1"].get()))
        egt2_c10 = self._f_to_cx10(float(self.vars["egt_b2"].get()))
        lean_raw = int(float(self.vars["lean_deg"].get()) * 10)

        self._send(int(ECUToHudID.ENGINE_RPM), struct.pack(">H", max(0, min(65535, rpm))))
        self._send(int(ECUToHudID.THROTTLE_POSITION), bytes((max(0, min(100, int(self.vars["tps"].get()))),)))
        self._send(int(ECUToHudID.BOOST_PRESSURE), struct.pack(">H", int(max(0.0, float(self.vars["boost"].get())) * 10)))
        self._send(int(ECUToHudID.AFR_BANKS), struct.pack(">HH", int(float(self.vars["afr_l"].get()) * 100), int(float(self.vars["afr_r"].get()) * 100)))
        self._send(int(ECUToHudID.KNOCK_STATUS), struct.pack(">H", max(0, min(0xFFFF, int(self.vars["knock_mask"].get())))))
        self._send(int(ECUToHudID.OIL_PRESSURE_TEMP), struct.pack(">HH", int(max(0.0, float(self.vars["oilp"].get())) * 10), oil_t_c10))
        self._send(int(ECUToHudID.COOLANT_TEMP), struct.pack(">H", clt_c10))
        self._send(int(ECUToHudID.FUEL_LEVEL), bytes((max(0, min(100, int(self.vars["fuel"].get()))),)))
        self._send(int(ECUToHudID.GEAR_POSITION), bytes((gear_map[self.vars["gear"].get()],)))
        self._send(int(ECUToHudID.ENGINE_LOAD), bytes((max(0, min(100, int(self.vars["load"].get()))),)))
        self._send(int(ECUToHudID.INTAKE_AIR_TEMP), struct.pack(">H", iat_c10))
        self._send(int(ECUToHudID.EXHAUST_GAS_TEMP), struct.pack(">HH", egt1_c10, egt2_c10))

        airshot_flags = 0x01 if bool(self.vars["airshot_firing"].get()) else 0x00
        self._send(int(ArduinoToHudID.AIR_SHOT_STATUS), bytes((max(0, min(255, int(self.vars["airshot_charges"].get()))), airshot_flags)))
        self._send(int(ArduinoToHudID.AWC_STATE), bytes((1 if bool(self.vars["awc_enabled"].get()) else 0,)) + struct.pack(">h", lean_raw))
        self._send(int(ArduinoToHudID.TANK_PRESSURE), struct.pack(">H", int(max(0.0, float(self.vars["tank_psi"].get())) * 10)))
        self._send(int(ArduinoToHudID.TWIN_TURBO_STATUS), struct.pack(">HH", int(max(0.0, float(self.vars["turbo1"].get())) * 10), int(max(0.0, float(self.vars["turbo2"].get())) * 10)))
        self._send(int(ArduinoToHudID.WASTEGATE_STATUS), bytes((max(0, min(100, int(self.vars["wg1"].get()))), max(0, min(100, int(self.vars["wg2"].get()))))))
        self._send(int(ArduinoToHudID.GEAR_POSITION), bytes((gear_map[self.vars["gear"].get()],)))
        self._send(int(ArduinoToHudID.WHEEL_SPEED), struct.pack(">HH", speed_mps100, speed_mps100))
        self._send(int(ArduinoToHudID.FUEL_LEVEL), bytes((max(0, min(100, int(self.vars["fuel"].get()))),)))

        self._send(int(PiToArduinoID.MODE_SELECTION), bytes((mode_map[self.vars["mode"].get()],)))
        self._send(int(PiToArduinoID.TRACTION_LEVEL), bytes((trac_map[self.vars["traction"].get()],)))
        self._send(int(PiToArduinoID.NFC_AUTH), bytes((1 if bool(self.vars["nfc_ok"].get()) else 0,)))

        payload = {k: (v.get() if hasattr(v, "get") else v) for k, v in self.vars.items()}
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
    args = p.parse_args()

    root = tk.Tk()
    app = App(root, args.channel, args.dry_run, args.udp_target)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
