"""Build a USB-ready Albatross update bundle from the current repo."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {".git", ".venv", "__pycache__", "dist", "logs", "settings", "updates", ".pytest_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _default_version() -> str:
    stamp = datetime.now().strftime("%Y.%m.%d_%H%M")
    commit = _git_commit()
    return f"{stamp}_{commit}" if commit else stamp


def _safe_name(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    return "".join(ch if ch in allowed else "_" for ch in value.strip()) or _default_version()


def _should_include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if any(part.startswith(".bundle_work_") for part in rel.parts):
        return False
    if path.name.startswith("albatross_update") and path.suffix.lower() == ".zip":
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_app_archive(output: Path) -> None:
    files = [path for path in sorted(ROOT.rglob("*")) if path.is_file() and _should_include(path)]
    print(f"Packaging {len(files)} files into pi/app.zip...", flush=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, path.relative_to(ROOT).as_posix())


def _write_bundle(bundle_path: Path, manifest: dict, app_archive: Path, arduino_hex: Path | None) -> None:
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        zf.write(app_archive, "pi/app.zip")
        if arduino_hex is not None:
            zf.write(arduino_hex, "arduino/albatross_controller.hex")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a USB-ready Albatross update bundle")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist", help="directory for the generated bundle")
    parser.add_argument("--version", default=_default_version(), help="bundle version string")
    parser.add_argument("--arduino-hex", type=Path, help="optional prebuilt Arduino Mega .hex to include")
    parser.add_argument("--arduino-port", help="optional Arduino serial port hint for manifest")
    parser.add_argument("--arduino-fqbn", default="arduino:avr:mega", help="Arduino FQBN for arduino-cli upload")
    parser.add_argument("--arduino-baud", type=int, default=115200, help="avrdude upload baud fallback")
    parser.add_argument("--min-battery-voltage", type=float, default=12.2)
    parser.add_argument("--allow-engine-running", action="store_true", help="do not require engine-off preflight")
    args = parser.parse_args()

    version = _safe_name(args.version)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = args.output_dir / f".bundle_work_{version}"
    if work_dir.exists():
        raise SystemExit(f"Work directory already exists: {work_dir}")
    work_dir.mkdir()
    try:
        app_archive = work_dir / "app.zip"
        _build_app_archive(app_archive)
        arduino_hex = args.arduino_hex.resolve() if args.arduino_hex else None
        if arduino_hex is not None and not arduino_hex.exists():
            raise SystemExit(f"Arduino hex not found: {arduino_hex}")

        manifest = {
            "version": version,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "requires_engine_off": not args.allow_engine_running,
            "min_battery_voltage": args.min_battery_voltage,
            "pi": {"app_archive": "pi/app.zip"},
            "sha256": {"pi/app.zip": _sha256(app_archive)},
        }
        commit = _git_commit()
        if commit:
            manifest["git_commit"] = commit
        if arduino_hex is not None:
            arduino_manifest = {
                "hex": "arduino/albatross_controller.hex",
                "fqbn": args.arduino_fqbn,
                "baud": args.arduino_baud,
            }
            if args.arduino_port:
                arduino_manifest["port"] = args.arduino_port
            manifest["arduino"] = arduino_manifest
            manifest["sha256"]["arduino/albatross_controller.hex"] = _sha256(arduino_hex)

        bundle_path = args.output_dir / f"albatross_update_{version}.zip"
        _write_bundle(bundle_path, manifest, app_archive, arduino_hex)
        print(bundle_path)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
