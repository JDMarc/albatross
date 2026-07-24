"""USB update bundle installer for Pi app and controller firmware."""
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
from typing import Any, Callable, Iterable

from .diagnostics.fault_logger import find_usb_log_destination
from .state.snapshot import StateSnapshot

LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATE_STATE_DIR = REPO_ROOT / "updates"
PENDING_HEALTH_PATH = UPDATE_STATE_DIR / "pending_health.json"
RESTART_REQUIRED_PATH = UPDATE_STATE_DIR / "restart_required"
MAX_UNCONFIRMED_STARTS = 2
RUNTIME_DIR_NAMES = {".git", ".venv", "__pycache__", "logs", "maps", "settings", "updates"}
DEFAULT_ARDUINO_FQBN = "teensy:avr:teensy41"
DEFAULT_ARDUINO_BAUD = 115200
DEFAULT_GITHUB_REMOTE = "origin"
DEFAULT_GITHUB_BRANCH = "main"
DEFAULT_ONLINE_MIN_BATTERY_VOLTAGE = 12.2
ProgressCallback = Callable[[str, int, int], None]


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


def _progress(callback: ProgressCallback | None, stage: str, current: int = 0, total: int = 0) -> None:
    if callback is not None:
        callback(stage, current, total)


def _run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        check=check,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _git_output(*args: str) -> str | None:
    try:
        result = _run_git(*args)
        return result.stdout.strip() or None
    except Exception:
        return None


def _current_git_commit() -> str | None:
    return _git_output("rev-parse", "HEAD")


def _git_has_tracked_changes() -> bool:
    result = _run_git("status", "--porcelain", "--untracked-files=no")
    return bool(result.stdout.strip())


def _git_is_ancestor(older: str, newer: str) -> bool:
    result = _run_git("merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "Unable to compare repository history")
    return result.returncode == 0


def _restore_git_commit(commit: str) -> None:
    normalized = commit.strip().lower()
    if len(normalized) != 40 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("Invalid rollback commit")
    _run_git("reset", "--hard", normalized)


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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


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


def _github_remote() -> str:
    return os.environ.get("ALBATROSS_GITHUB_REMOTE", DEFAULT_GITHUB_REMOTE).strip() or DEFAULT_GITHUB_REMOTE


def _github_branch() -> str:
    return os.environ.get("ALBATROSS_GITHUB_BRANCH", DEFAULT_GITHUB_BRANCH).strip() or DEFAULT_GITHUB_BRANCH


def _fetch_repository_head(progress: ProgressCallback | None = None) -> tuple[str, str, str]:
    remote = _github_remote()
    branch = _github_branch()
    if not (REPO_ROOT / ".git").exists():
        raise RuntimeError("HUD install is not a Git repository")
    if _git_output("remote", "get-url", remote) is None:
        raise RuntimeError(f"Git remote {remote!r} is not configured")
    _progress(progress, "DOWNLOADING", 0, 1)
    _run_git("fetch", "--quiet", "--no-tags", remote, branch)
    _progress(progress, "DOWNLOADING", 1, 1)
    target = _git_output("rev-parse", "FETCH_HEAD")
    if not target:
        raise RuntimeError("Fetched repository state has no commit")
    return remote, branch, target


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
    value = manifest.get("arduino_hex") or manifest.get("controller_hex")
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
        raise FileNotFoundError(f"Controller firmware hex missing: {hex_rel}")
    arduino = manifest.get("arduino") if isinstance(manifest.get("arduino"), dict) else {}
    port = _detect_arduino_port(manifest)
    if port is None:
        raise RuntimeError("Controller port not found; set ALBATROSS_ARDUINO_PORT or manifest arduino.port")
    fqbn = str(arduino.get("fqbn", DEFAULT_ARDUINO_FQBN))
    baud = int(arduino.get("baud", DEFAULT_ARDUINO_BAUD))
    if _flash_with_arduino_cli(hex_path, port, fqbn):
        return True
    if fqbn == "arduino:avr:mega" and _flash_with_avrdude(hex_path, port, baud):
        return True
    raise RuntimeError("arduino-cli is required for Teensy controller flashing")


def _preflight(manifest: dict[str, Any], snapshot: StateSnapshot) -> str | None:
    if manifest.get("requires_engine_off", True) and snapshot.engine.rpm > 0:
        return "ENGINE RUNNING"
    min_voltage = float(manifest.get("min_battery_voltage", 0.0) or 0.0)
    voltage = snapshot.temps.battery_voltage
    if min_voltage > 0 and voltage > 0 and voltage < min_voltage:
        return "BATTERY LOW"
    return None


def install_update_bundle(
    bundle: Path,
    snapshot: StateSnapshot,
    *,
    source: str | None = None,
    progress: ProgressCallback | None = None,
) -> UpdateResult:
    temp: tempfile.TemporaryDirectory[str] | None = None
    try:
        _progress(progress, "VERIFYING")
        bundle_root, manifest, temp = _load_bundle(bundle)
        _verify_hashes(bundle_root, manifest)
        blocked = _preflight(manifest, snapshot)
        if blocked:
            return UpdateResult(blocked)
        version = _safe_name(str(manifest.get("version", bundle.stem)))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        backup_root = UPDATE_STATE_DIR / "backups" / f"{timestamp}_{version}"
        _progress(progress, "BACKUP")
        _backup_runtime_dirs(backup_root)
        _progress(progress, "INSTALLING")
        pi_updated = _install_pi_app(bundle_root, manifest, backup_root)
        arduino_updated = _install_arduino(bundle_root, manifest)
        state = {
            "version": version,
            "installed_at": datetime.now().isoformat(timespec="seconds"),
            "bundle": str(bundle),
            "source": source or str(bundle),
            "pi_updated": pi_updated,
            "arduino_updated": arduino_updated,
            "backup": str(backup_root),
            "restart_required": pi_updated,
        }
        _write_json_atomic(UPDATE_STATE_DIR / "last_update.json", state)
        if pi_updated:
            _write_json_atomic(RESTART_REQUIRED_PATH, state)
            _write_json_atomic(
                PENDING_HEALTH_PATH,
                {
                    "version": version,
                    "backup": str(backup_root),
                    "installed_at": state["installed_at"],
                    "startup_attempts": 0,
                },
            )
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


def install_update_from_usb(snapshot: StateSnapshot) -> UpdateResult:
    bundle = find_update_bundle()
    if bundle is None:
        return UpdateResult("NO UPDATE")
    return install_update_bundle(bundle, snapshot, source="usb")


def install_update_from_repository(snapshot: StateSnapshot, progress: ProgressCallback | None = None) -> UpdateResult:
    """Fast-forward the installed HUD to the configured repository branch."""
    try:
        _progress(progress, "CHECKING")
        current = _current_git_commit()
        if not current:
            return UpdateResult("NO GIT REPO")
        try:
            remote, branch, target = _fetch_repository_head(progress)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            LOGGER.exception("Repository update fetch failed")
            return UpdateResult("NET FAIL", exc.__class__.__name__)

        if _git_has_tracked_changes():
            return UpdateResult("LOCAL CHANGES")
        if current == target:
            return UpdateResult("UP TO DATE")

        if not _git_is_ancestor(current, target):
            if _git_is_ancestor(target, current):
                return UpdateResult("LOCAL AHEAD")
            return UpdateResult("GIT DIVERGED")

        blocked = _preflight(
            {
                "requires_engine_off": True,
                "min_battery_voltage": DEFAULT_ONLINE_MIN_BATTERY_VOLTAGE,
            },
            snapshot,
        )
        if blocked:
            return UpdateResult(blocked)

        version = f"git_{target[:12]}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        UPDATE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        backup_root = UPDATE_STATE_DIR / "backups" / f"{timestamp}_{version}"
        _progress(progress, "BACKUP")
        _backup_runtime_dirs(backup_root)
        _backup_current_app(backup_root)

        _progress(progress, "INSTALLING")
        merge_completed = False
        try:
            _run_git("merge", "--ff-only", target)
            merge_completed = True
            installed_at = datetime.now().isoformat(timespec="seconds")
            source = f"github:{remote}/{branch}"
            state = {
                "version": version,
                "installed_at": installed_at,
                "bundle": None,
                "source": source,
                "pi_updated": True,
                "arduino_updated": False,
                "backup": str(backup_root),
                "restart_required": True,
                "previous_git_commit": current,
                "target_git_commit": target,
            }
            _write_json_atomic(UPDATE_STATE_DIR / "last_update.json", state)
            _write_json_atomic(RESTART_REQUIRED_PATH, state)
            _write_json_atomic(
                PENDING_HEALTH_PATH,
                {
                    "version": version,
                    "backup": str(backup_root),
                    "installed_at": installed_at,
                    "startup_attempts": 0,
                    "previous_git_commit": current,
                    "target_git_commit": target,
                    "source": source,
                },
            )
        except Exception:
            if merge_completed:
                LOGGER.exception("Repository update transaction failed; restoring previous commit")
                _restore_git_commit(current)
                _copytree_overlay(backup_root / "app", REPO_ROOT)
            raise
        return UpdateResult("PI OK", "RESTART")
    except Exception as exc:
        LOGGER.exception("Repository update failed")
        return UpdateResult("UPDATE FAIL", exc.__class__.__name__)


def install_update_from_github(snapshot: StateSnapshot, progress: ProgressCallback | None = None) -> UpdateResult:
    """Backward-compatible name for repository-based online updates."""
    return install_update_from_repository(snapshot, progress)


def request_reboot_if_raspberry_pi() -> bool:
    if os.environ.get("ALBATROSS_SKIP_REBOOT"):
        return False
    model_path = Path("/proc/device-tree/model")
    try:
        model = model_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        model = ""
    if "raspberry pi" not in model.lower():
        return False
    command = ["systemctl", "reboot"] if shutil.which("systemctl") else ["sudo", "reboot"]
    subprocess.Popen(command, cwd=str(REPO_ROOT))
    return True


def register_startup_attempt_or_rollback() -> bool:
    """Rollback an unconfirmed Pi overlay after repeated failed runtime starts."""
    if not PENDING_HEALTH_PATH.exists():
        return False
    try:
        pending = json.loads(PENDING_HEALTH_PATH.read_text(encoding="utf-8"))
        attempts = int(pending.get("startup_attempts", 0)) + 1
        pending["startup_attempts"] = attempts
        if attempts <= MAX_UNCONFIRMED_STARTS:
            _write_json_atomic(PENDING_HEALTH_PATH, pending)
            LOGGER.warning("Pi update health confirmation pending; startup attempt %s/%s", attempts, MAX_UNCONFIRMED_STARTS)
            return False
        backup_root = Path(str(pending["backup"]))
        app_backup = backup_root / "app"
        if not app_backup.is_dir():
            raise FileNotFoundError(f"Rollback app backup missing: {app_backup}")
        previous_git_commit = str(pending.get("previous_git_commit") or "")
        if previous_git_commit:
            _restore_git_commit(previous_git_commit)
        _copytree_overlay(app_backup, REPO_ROOT)
        rollback_state = {
            "rolled_back_at": datetime.now().isoformat(timespec="seconds"),
            "failed_version": pending.get("version", "unknown"),
            "backup": str(backup_root),
            "startup_attempts": attempts,
            "restored_git_commit": previous_git_commit or None,
        }
        _write_json_atomic(UPDATE_STATE_DIR / "last_rollback.json", rollback_state)
        PENDING_HEALTH_PATH.unlink(missing_ok=True)
        RESTART_REQUIRED_PATH.unlink(missing_ok=True)
        LOGGER.error("Rolled back unconfirmed Pi update after %s failed starts", attempts - 1)
        return True
    except Exception:
        LOGGER.exception("Unable to evaluate or rollback pending Pi update")
        return False


def confirm_pending_update_health() -> None:
    """Mark a Pi overlay healthy after the HUD render loop remains alive."""
    if not PENDING_HEALTH_PATH.exists():
        return
    try:
        pending = json.loads(PENDING_HEALTH_PATH.read_text(encoding="utf-8"))
        pending["confirmed_at"] = datetime.now().isoformat(timespec="seconds")
        _write_json_atomic(UPDATE_STATE_DIR / "last_confirmed_update.json", pending)
        PENDING_HEALTH_PATH.unlink(missing_ok=True)
        RESTART_REQUIRED_PATH.unlink(missing_ok=True)
        LOGGER.info("Confirmed Pi update health")
    except Exception:
        LOGGER.exception("Unable to confirm Pi update health")
