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

from albatross_pi.canbus.ids import ECUToHudID, PiToArduinoID
from albatross_pi.canbus.iface import SocketCANInterface


class App:
    def __init__(self, root: tk.Tk, channel: str, dry_run: bool, udp_target: str) -> None:
        self.root = root
        self.root.title("Albatross CAN Demo Controls")
        self.dry_run = dry_run
        self.iface = None if dry_run else SocketCANInterface(channel=channel)
        self.udp_host, self.udp_port = udp_target.split(":")
        self.udp_port = int(self.udp_port)
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
            "speed": tk.DoubleVar(value=25.0),
            "oilp": tk.DoubleVar(value=58.0),
            "oilt": tk.DoubleVar(value=205.0),
            "clt": tk.DoubleVar(value=190.0),
            "fuel": tk.IntVar(value=75),
            "gear": tk.StringVar(value="N"),
            "mode": tk.StringVar(value="NORMAL"),
            "traction": tk.StringVar(value="MED"),
            "msg": tk.StringVar(value="ECU OK | ARDUINO OK | CAN OK"),
        }
        self._build()
        self._tick()

    def _build(self) -> None:
        f = ttk.Frame(self.root, padding=8)
        f.grid(sticky="nsew")
        self.root.columnconfigure(0, weight=1)

        self._slider(f, "RPM", "rpm", 0, 14000, 0)
        self._slider(f, "TPS %", "tps", 0, 100, 1)
        self._slider(f, "Boost psi", "boost", 0, 30, 2)
        self._slider(f, "Speed mph", "speed", 0, 220, 3)
        self._slider(f, "Oil P psi", "oilp", 0, 120, 4)
        self._slider(f, "Oil T F", "oilt", 70, 320, 5)
        self._slider(f, "Coolant F", "clt", 70, 280, 6)
        self._slider(f, "Fuel %", "fuel", 0, 100, 7)

        ttk.Label(f, text="Gear").grid(row=8, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.vars["gear"], values=["N", "1", "2", "3", "4", "5", "6"], width=8).grid(row=8, column=1, sticky="w")
        ttk.Label(f, text="Mode").grid(row=8, column=2, sticky="w")
        ttk.Combobox(f, textvariable=self.vars["mode"], values=["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"], width=12).grid(row=8, column=3, sticky="w")

        ttk.Label(f, text="Traction").grid(row=9, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.vars["traction"], values=["LOW", "MED", "HIGH", "OFF"], width=8).grid(row=9, column=1, sticky="w")

        ttk.Label(f, text="Message").grid(row=10, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.vars["msg"], width=50).grid(row=10, column=1, columnspan=3, sticky="ew")

        ttk.Button(f, text="Send Once", command=self.send_all).grid(row=11, column=0, sticky="w")
        ttk.Button(f, text="Quit", command=self.close).grid(row=11, column=1, sticky="w")

    def _slider(self, parent, label, key, lo, hi, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        s = ttk.Scale(parent, from_=lo, to=hi, variable=self.vars[key], orient="horizontal")
        s.grid(row=row, column=1, columnspan=2, sticky="ew")
        ttk.Label(parent, textvariable=self.vars[key], width=8).grid(row=row, column=3, sticky="e")
        parent.columnconfigure(1, weight=1)

    def _send(self, arb_id: int, payload: bytes) -> None:
        if self.iface:
            self.iface.send(arb_id, payload)
        else:
            print(f"TX 0x{arb_id:03X} {payload.hex()}")

    def send_all(self) -> None:
        rpm = int(self.vars["rpm"].get())
        tps = int(self.vars["tps"].get())
        boost = float(self.vars["boost"].get())
        speed_mps = float(self.vars["speed"].get()) / 2.236936
        oilp = float(self.vars["oilp"].get())
        oilt_c = (float(self.vars["oilt"].get()) - 32.0) * 5.0 / 9.0
        clt_c = (float(self.vars["clt"].get()) - 32.0) * 5.0 / 9.0
        fuel = int(self.vars["fuel"].get())
        gear_map = {"N": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
        mode_map = {"ECO": 1, "NORMAL": 2, "SPORT": 3, "RACE": 4, "ALBATROSS": 5}
        trac_map = {"LOW": 1, "MED": 2, "HIGH": 3, "OFF": 4}

        self._send(int(ECUToHudID.ENGINE_RPM), struct.pack(">H", max(0, min(65535, rpm))))
        self._send(int(ECUToHudID.THROTTLE_POSITION), bytes((max(0, min(100, tps)),)))
        self._send(int(ECUToHudID.BOOST_PRESSURE), struct.pack(">H", int(max(0, boost) * 10)))
        self._send(int(ECUToHudID.OIL_PRESSURE_TEMP), struct.pack(">HH", int(max(0, oilp) * 10), int(max(0, oilt_c) * 10)))
        self._send(int(ECUToHudID.COOLANT_TEMP), struct.pack(">H", int(max(0, clt_c) * 10)))
        self._send(int(ECUToHudID.FUEL_LEVEL), bytes((max(0, min(100, fuel)),)))
        self._send(int(ECUToHudID.GEAR_POSITION), bytes((gear_map[self.vars["gear"].get()],)))
        mps100 = int(max(0.0, speed_mps) * 100)
        self._send(0x137, struct.pack(">HH", mps100, mps100))
        self._send(int(PiToArduinoID.MODE_SELECTION), bytes((mode_map[self.vars["mode"].get()],)))
        self._send(int(PiToArduinoID.TRACTION_LEVEL), bytes((trac_map[self.vars["traction"].get()],)))
        payload = {
            "rpm": rpm,
            "tps": tps,
            "boost": boost,
            "speed_mph": float(self.vars["speed"].get()),
            "oilp": oilp,
            "oilt_f": float(self.vars["oilt"].get()),
            "clt_f": float(self.vars["clt"].get()),
            "fuel": fuel,
            "gear": self.vars["gear"].get(),
            "mode": self.vars["mode"].get(),
            "traction": self.vars["traction"].get(),
            "msg": self.vars["msg"].get(),
        }
        self.sock.sendto(json.dumps(payload).encode("utf-8"), (self.udp_host, self.udp_port))

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
