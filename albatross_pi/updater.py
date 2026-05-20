"""USB update bundle installer for Pi app and Arduino firmware."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .diagnostics.fault_logger import find_usb_log_destination
from .state.snapshot import StateSnapshot

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATE_STATE_DIR = REPO_ROOT / "updates"
RUNTIME_DIR_NAMES = {".git", ".venv", "__pycache__", "logs", "settings", "updates"}
DEFAULT_ARDUINO_FQBN = "arduino:avr:mega"
DEFAULT_ARDUINO_BAUD = 115200


@dataclass(frozen=True)
class UpdateResult:
    status: str
    detail: str = ""

    def display(self) -> str:
        return f"{self.status} {self.detail}".strip()


def _safe_name(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned = "".join(ch if ch in allowed else "_" for ch in value.strip())
    return cleaned or datetime.now().strftime("%Y%m%d_%H%M%S")


def _copytree_overlay(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        if item.name in RUNTIME_DIR_NAMES:
            continue
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _backup_runtime_dirs(backup_root: Path) -> None:
    backup_root.mkdir(parents=True, exist_ok=True)
    for name in ("settings", "logs"):
        source = REPO_ROOT / name
        if source.exists():
            shutil.copytree(source, backup_root / name, dirs_exist_ok=True)


def _backup_current_app(backup_root: Path) -> None:
    app_backup = backup_root / "app"
    app_backup.mkdir(parents=True, exist_ok=True)
    for item in REPO_ROOT.iterdir():
        if item.name in RUNTIME_DIR_NAMES:
            continue
        target = app_backup / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _ensure_within(parent: Path, child: Path) -> Path:
    resolved_parent = parent.resolve()
    resolved_child = child.resolve()
    if resolved_child != resolved_parent and resolved_parent not in resolved_child.parents:
        raise ValueError(f"Update archive contains unsafe path: {child}")
    return resolved_child


def _extract_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                _ensure_within(destination, destination / member.filename)
            zf.extractall(destination)
    elif archive.name.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                if member.issym() or member.islnk():
                    raise ValueError(f"Update archive contains link: {member.name}")
                _ensure_within(destination, destination / member.name)
            tf.extractall(destination)
    else:
        raise ValueError(f"Unsupported Pi app archive type: {archive.name}")
    children = [child for child in destination.iterdir() if child.name not in {"__MACOSX"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination


def _load_bundle(bundle: Path) -> tuple[Path, dict[str, Any], tempfile.TemporaryDirectory[str] | None]:
    if bundle.is_dir():
        manifest_path = bundle / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Missing manifest.json in {bundle}")
        return bundle, json.loads(manifest_path.read_text(encoding="utf-8")), None
    if bundle.suffix.lower() != ".zip":
        raise ValueError(f"Unsupported update bundle: {bundle.name}")
    temp = tempfile.TemporaryDirectory(prefix="albatross_update_")
    root = Path(temp.name)
    with zipfile.ZipFile(bundle) as zf:
        for member in zf.infolist():
            _ensure_within(root, root / member.filename)
        zf.extractall(root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        temp.cleanup()
        raise FileNotFoundError(f"Missing manifest.json in {bundle}")
    return root, json.loads(manifest_path.read_text(encoding="utf-8")), temp


def _bundle_candidates(root: Path) -> Iterable[Path]:
    for pattern in ("albatross_update*.zip", "albatross-update*.zip"):
        yield from root.glob(pattern)
    for child in root.iterdir():
        if child.is_dir() and (child / "manifest.json").exists() and child.name.lower().startswith(("albatross_update", "albatross-update")):
            yield child


def find_update_bundle() -> Path | None:
    explicit = os.environ.get("ALBATROSS_UPDATE_BUNDLE")
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return path
    usb_root = find_usb_log_destination()
    if usb_root is None:
        return None
    candidates = sorted(_bundle_candidates(usb_root), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _manifest_pi_archive(manifest: dict[str, Any]) -> str | None:
    pi = manifest.get("pi")
    if isinstance(pi, dict):
        value = pi.get("app_archive") or pi.get("archive")
        return str(value) if value else None
    value = manifest.get("pi_app")
    return str(value) if value else None


def _manifest_arduino_hex(manifest: dict[str, Any]) -> str | None:
    arduino = manifest.get("arduino")
    if isinstance(arduino, dict):
        value = arduino.get("hex") or arduino.get("firmware")
        return str(value) if value else None
    value = manifest.get("arduino_hex")
    return str(value) if value else None


def _verify_hashes(bundle_root: Path, manifest: dict[str, Any]) -> None:
    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        return
    for rel_path, expected in hashes.items():
        target = _ensure_within(bundle_root, bundle_root / str(rel_path))
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Hashed payload missing: {rel_path}")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest.lower() != str(expected).lower():
            raise ValueError(f"SHA256 mismatch for {rel_path}")


def _detect_arduino_port(manifest: dict[str, Any]) -> str | None:
    arduino = manifest.get("arduino") if isinstance(manifest.get("arduino"), dict) else {}
    requested = os.environ.get("ALBATROSS_ARDUINO_PORT") or arduino.get("port")
    if requested:
        return str(requested)
    candidates = [Path("/dev/ttyACM0"), Path("/dev/ttyUSB0")]
    candidates.extend(sorted(Path("/dev").glob("ttyACM*")) if Path("/dev").exists() else [])
    candidates.extend(sorted(Path("/dev").glob("ttyUSB*")) if Path("/dev").exists() else [])
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _flash_with_arduino_cli(hex_path: Path, port: str, fqbn: str) -> bool:
    arduino_cli = shutil.which("arduino-cli")
    if not arduino_cli:
        return False
    cmd = [arduino_cli, "upload", "-p", port, "--fqbn", fqbn, "-i", str(hex_path)]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    return True


def _flash_with_avrdude(hex_path: Path, port: str, baud: int) -> bool:
    avrdude = shutil.which("avrdude")
    if not avrdude:
        return False
    cmd = [
        avrdude,
        "-v",
        "-patmega2560",
        "-cwiring",
        "-P",
        port,
        "-b",
        str(baud),
        "-D",
        "-U",
        f"flash:w:{hex_path}:i",
    ]
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    return True


def _install_pi_app(bundle_root: Path, manifest: dict[str, Any], backup_root: Path) -> bool:
    archive_rel = _manifest_pi_archive(manifest)
    if not archive_rel:
        return False
    archive = _ensure_within(bundle_root, bundle_root / archive_rel)
    if not archive.exists():
        raise FileNotFoundError(f"Pi app archive missing: {archive_rel}")
    _backup_current_app(backup_root)
    with tempfile.TemporaryDirectory(prefix="albatross_app_") as temp_dir:
        extracted_root = _extract_archive(archive, Path(temp_dir))
        _copytree_overlay(extracted_root, REPO_ROOT)
    return True


def _install_arduino(bundle_root: Path, manifest: dict[str, Any]) -> bool:
    hex_rel = _manifest_arduino_hex(manifest)
    if not hex_rel:
        return False
    hex_path = _ensure_within(bundle_root, bundle_root / hex_rel)
    if not hex_path.exists():
        raise FileNotFoundError(f"Arduino hex missing: {hex_rel}")
    arduino = manifest.get("arduino") if isinstance(manifest.get("arduino"), dict) else {}
    port = _detect_arduino_port(manifest)
    if port is None:
        raise RuntimeError("Arduino port not found; set ALBATROSS_ARDUINO_PORT or manifest arduino.port")
    fqbn = str(arduino.get("fqbn", DEFAULT_ARDUINO_FQBN))
    baud = int(arduino.get("baud", DEFAULT_ARDUINO_BAUD))
    if _flash_with_arduino_cli(hex_path, port, fqbn):
        return True
    if _flash_with_avrdude(hex_path, port, baud):
        return True
    raise RuntimeError("Neither arduino-cli nor avrdude is available for Arduino flashing")


def _preflight(manifest: dict[str, Any], snapshot: StateSnapshot) -> str | None:
    if manifest.get("requires_engine_off", True) and snapshot.engine.rpm > 0:
        return "ENGINE RUNNING"
    min_voltage = float(manifest.get("min_battery_voltage", 0.0) or 0.0)
    voltage = snapshot.temps.battery_voltage
    if min_voltage > 0 and voltage > 0 and voltage < min_voltage:
        return "BATTERY LOW"
    return None


def install_update_from_usb(snapshot: StateSnapshot) -> UpdateResult:
    bundle = find_update_bundle()
    if bundle is None:
        return UpdateResult("NO UPDATE")
    temp: tempfile.TemporaryDirectory[str] | None = None
    try:
        bundle_root, manifest, temp = _load_bundle(bundle)
        _verify_hashes(bundle_root, manifest)
        blocked = _preflight(manifest, snapshot)
        if blocked:
            return UpdateResult(blocked)
        version = _safe_name(str(manifest.get("version", bundle.stem)))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        backup_root = UPDATE_STATE_DIR / "backups" / f"{timestamp}_{version}"
        _backup_runtime_dirs(backup_root)
        pi_updated = _install_pi_app(bundle_root, manifest, backup_root)
        arduino_updated = _install_arduino(bundle_root, manifest)
        state = {
            "version": version,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "bundle": str(bundle),
            "pi_updated": pi_updated,
            "arduino_updated": arduino_updated,
            "backup": str(backup_root),
            "restart_required": pi_updated,
        }
        (UPDATE_STATE_DIR / "last_update.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if pi_updated:
            (UPDATE_STATE_DIR / "restart_required").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if pi_updated and arduino_updated:
            return UpdateResult("PI+ARD OK", "RESTART")
        if pi_updated:
            return UpdateResult("PI OK", "RESTART")
        if arduino_updated:
            return UpdateResult("ARD OK")
        return UpdateResult("NO PAYLOAD")
    except Exception as exc:
        LOGGER.exception("Update install failed")
        return UpdateResult("UPDATE FAIL", exc.__class__.__name__)
    finally:
        if temp is not None:
            temp.cleanup()
