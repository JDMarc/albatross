"""Compile explicit engineering calibration into the supervisor, never rider-editable."""
import argparse,json,math,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data["schema_version"]!=1:raise ValueError("VDC schema")
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":")).encode()).digest()[:8]
    lines=['#pragma once','#include "vdc.h"','namespace vdc {','static const uint8_t calibrationFingerprint[8]={'+','.join(str(x) for x in digest)+'};','inline Config engineeringCalibration(){',' Config c;']
    for name,value in data["values"].items():
        if not re.fullmatch(r"[a-z_]+(?:\[[0-4]\])*(?:\.[a-z_]+(?:\[[0-4]\])*)?",name):raise ValueError(name)
        if value is None:continue
        if not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(name)
        lines.append(f" c.{name}={value};")
    lines.extend([" c.validated="+str(bool(data["validated"])).lower()+";"," return c;","}","}",""])
    return "\n".join(lines)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--check",action="store_true");a=p.parse_args()
    target=ROOT/"arduino/teensy41/albatross_controller_teensy41/vdc_calibration.h"
    content=generate(ROOT/"config/vdc_engineering.json")
    if a.check:
        if target.read_text(encoding="utf-8")!=content:raise SystemExit("VDC calibration header differs")
    else:target.write_text(content,encoding="utf-8")
