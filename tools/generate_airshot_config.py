"""Generate reviewed C++ calibration assignments from versioned JSON."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def generate(source):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    if data["schema_version"] != 2:
        raise ValueError("unsupported Air Shot schema")
    def literal(v):
        if isinstance(v, bool): return str(v).lower()
        if isinstance(v, (int, float)) and abs(v) < 1e9: return str(v)
        raise ValueError("calibration values must be finite numbers")
    lines = ['#pragma once', '#include "airshot_config.h"', 'namespace airshot {', 'inline Config calibration() {', '  Config c;']
    def assign(prefix, values):
        for key, value in values.items():
            if key == "name" or value is None: continue
            if not key.replace("_", "").isalnum(): raise ValueError("invalid field")
            if isinstance(value, list):
                for n, item in enumerate(value):
                    if item is not None: lines.append(f"  {prefix}{key}[{n}] = {literal(item)};")
            else: lines.append(f"  {prefix}{key} = {literal(value)};")
    assign("c.",data["parameters"])
    if len(data["valves"]) != 4 or len(data["profiles"]) != 6: raise ValueError("wrong calibration dimensions")
    for n, v in enumerate(data["valves"]): assign(f"c.valves[{n}].",v)
    for n, p in enumerate(data["profiles"]): assign(f"c.profiles[{n}].",p)
    lines.extend(["  return c;", "}", "}", ""])
    return "\n".join(lines)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--config",type=Path,default=ROOT/"config/airshot_v2.json")
    p.add_argument("--check",action="store_true")
    args=p.parse_args()
    path=ROOT/"arduino/teensy41/albatross_controller_teensy41/airshot_calibration.h"
    content=generate(args.config)
    if args.check:
        if path.read_text(encoding="utf-8") != content: raise SystemExit("Air Shot generated configuration differs")
    else: path.write_text(content,encoding="utf-8")
