"""Check CAN reference coverage without importing the HUD or opening hardware."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "arduino/teensy41/albatross_controller_teensy41"


def check():
    document = (ROOT / "docs/can_id_reference.md").read_text(encoding="utf-8")
    listed = [int(value, 16) for value in re.findall(r"^\| 0x([0-9A-F]{3}) \|", document, re.M)]
    assert len(listed) == len(set(listed)), "Duplicate standard-ID rows"
    expected = set()
    tree = ast.parse((ROOT / "albatross_pi/canbus/ids.py").read_text())
    for item in tree.body:
        if isinstance(item, ast.ClassDef):
            for entry in item.body:
                if isinstance(entry, ast.Assign) and isinstance(entry.value, ast.Constant):
                    if isinstance(entry.value.value, int):
                        expected.add(entry.value.value)
    main = (MAIN / "albatross_controller_teensy41.ino").read_text()
    expected.update(int(x, 16) for x in re.findall(r"constexpr uint16_t \w+ = 0x([0-9A-Fa-f]{3});", main))
    for name in ("airshot_io.cpp", "vdc_io.cpp", "vdc_io.h", "fault_manager/telemetry.h"):
        content = (MAIN / name).read_text()
        expected.update(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{3})(?![0-9A-Fa-f])", content)
                        if int(x, 16) < 0x7ff)
    expected.update(range(0x198, 0x19c))
    expected.update((0x245, 0x471, 0x195))
    missing = expected - set(listed)
    assert not missing, f"Undocumented IDs: {[hex(x) for x in sorted(missing)]}"
    assert "29-bit" in document and "LITTLE-endian" in document and "offset << 18" in document
    wiring = (ROOT / "docs/wiring_pinout.md").read_text()
    assert "| 12 | Output, active high | Master NC" in wiring
    assert "A0 / 14" in wiring and "A1 / 15" in wiring and "A2 / 16" in wiring
    assert "0x470" in wiring and "0x300" in wiring and "can_id_reference.md" in wiring
    for path in (ROOT / "docs/wiring_pinout.md", ROOT / "docs/can_id_reference.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" not in target and not target.startswith("#"):
                assert (path.parent / target.split("#")[0]).exists(), (path, target)
    print(f"PASS CAN reference: {len(listed)} unique standard-ID rows, source coverage, extended addressing and local links")


if __name__ == "__main__":
    check()
