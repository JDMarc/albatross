"""Pygame HUD renderer for the Albatross project."""
from __future__ import annotations

import logging
import math
import sunau
import threading
import time
import urllib.request
import wave
import audioop
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, List

import pygame

from ..diagnostics.fault_logger import engine_status, fault_action, fault_reason
from ..economy import EconomyTracker
from ..navigation import NavigationManager
from ..networking import PiNetworkManager
from .widgets.airshot_panel import AirShotPanel
from .widgets.alert_panel import AlertPanel
from .widgets.boost_panel import BoostPanel
from .widgets.fuel_panel import FuelPanel
from .widgets.header_bar import HeaderBar
from .widgets.message_line import MessageLine
from .widgets.mode_stats_panel import ModeStatsPanel
from .widgets.navigation_panel import NavigationPanel
from .widgets.rpm_bar import RpmBar
from .widgets.speed_gear import SpeedGear
from .widgets.temps_grid import TempsGrid
from .widgets.traction_panel import TractionPanel
from .widgets.ui_utils import apply_theme, fit_font_size, font
from .preferences import HUDPreferences
from ..state.snapshot import StateSnapshot

SCREEN_SIZE = (1920, 720)
TARGET_FPS = 60
LOGGER = logging.getLogger(__name__)
RETRO_ERROR_BEEP = "__retro_error_beep__"
AUDIO_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "audio"
RETRO_ERROR_BEEP_PATH = AUDIO_ASSET_DIR / "new_error_sound.wav"


class EvaAlertAudio:
    """Fault-to-voice alert mapper for EVA Chrysler prompts."""

    def __init__(self) -> None:
        self._enabled = False
        self._channel: pygame.mixer.Channel | None = None
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._active_faults: set[str] = set()
        self._played_faults: set[str] = set()
        self._pending_faults: list[str] = []
        self._mapping = {
            "CRITICAL OIL PRESS": "your_engine_oil_pressure_is_critical_engine_damage_may_occur.wav",
            "LOW OIL PRESS": "LOW-OIL-PRESS.wav",
            "COOLANT HOT": "your_engine_is_overheating_prompt_service_is_required.wav",
            "EGT HIGH": "EGT-HIGH.wav",
            "LOW FUEL": "please_check_your_fuel_level.wav",
            "CAN TIMEOUT": "CAN-TIMEOUT.wav",
            "IMU FAULT": "IMU-FAULT.wav",
            "AIR SHOT LOW": "AIR-SHOT-LOW.wav",
            "KNOCK": RETRO_ERROR_BEEP,
            "KNOCK ESCALATE": "KNOCK-ESCALATE.wav",
            "WMI FLOW LOW": "WMI-FLOW-LOW.wav",
            "WMI TANK EMPTY": "WMI-TANK-EMPTY.wav",
            "WMI PUMP FAULT": "WMI-PUMP-FAULT.wav",
            "WMI PRESSURE LOW": "WMI-PRESSURE-LOW.wav",
            "CAN STALE": "CAN-STALE.wav",
            "ECU STALE": "ECU-STALE.wav",
            "CLUTCH SLIP": "CLUTCH-SLIP.wav",
            "CYL EGT BOOST MISMATCH": "CYL-EGT-BOOST-MISMATCH.wav",
            "CYL BOOST MISMATCH": "CYL-EGT-BOOST-MISMATCH.wav",
            "CYL EGT MISMATCH": "CYL-EGT-BOOST-MISMATCH.wav",
            "CYL AFR MISMATCH": "CYL-EGT-BOOST-MISMATCH.wav",
            "OVERBOOST": "OVERBOOST.wav",
            "BOOST CONTROL ERROR": "BOOST-CONTROL-ERROR.wav",
            "SLOW TURBO SPOOL": "SLOW-TURBO-SPOOL.wav",
            "WASTEGATE STUCK": "WASTEGATE-STUCK.wav",
            "SPEED SENSOR": "SPEED-SENSOR.wav",
            "GEAR SENSOR": "GEAR-SENSOR.wav",
            "INTAKE AIR HOT": "INTAKE-AIR-HOT.wav",
            "BATTERY LOW": "BATTERY-LOW.wav",
            "BATTERY HIGH": "BATTERY-HIGH.wav",
            "SENSOR RANGE FAULT": "SENSOR-RANGE-FAULT.wav",
        }
        if not self._init_mixer():
            return
        self._channel = pygame.mixer.Channel(2)
        self._load_sounds()
        self._enabled = bool(self._sounds)

    def _init_mixer(self) -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(44100, -16, 2, 512)
                pygame.mixer.init()
            return True
        except pygame.error as exc:
            LOGGER.warning("Audio alerts disabled (pygame mixer init failed): %s", exc)
            return False

    def _load_sounds(self) -> None:
        cache_dir = Path.home() / ".cache" / "albatross" / "eva24"
        cache_dir.mkdir(parents=True, exist_ok=True)
        base_url = "https://raw.githubusercontent.com/jnewb1/eva-sounds/main/sounds_eva24"
        resolved: dict[str, Path] = {}
        for name in sorted(set(self._mapping.values())):
            local_path = AUDIO_ASSET_DIR / name
            if local_path.exists():
                resolved[name] = local_path
                continue
            if name == RETRO_ERROR_BEEP:
                continue
            wav_path = cache_dir / name
            if not wav_path.exists():
                try:
                    urllib.request.urlretrieve(f"{base_url}/{name}", wav_path)
                except Exception as exc:
                    LOGGER.warning("Failed downloading EVA clip %s: %s", name, exc)
                    continue
            resolved[name] = wav_path
        loaded_by_name: dict[str, pygame.mixer.Sound] = {}
        for name, source_path in resolved.items():
            try:
                loaded_by_name[name] = pygame.mixer.Sound(str(source_path))
                continue
            except pygame.error:
                pass
            transcoded_path = source_path.with_suffix(".pcm.wav")
            try:
                self._transcode_au_to_pcm_wav(source_path, transcoded_path)
                loaded_by_name[name] = pygame.mixer.Sound(str(transcoded_path))
            except Exception as exc:
                LOGGER.warning("Failed loading EVA clip %s (%s): %s", name, source_path, exc)
        try:
            loaded_by_name[RETRO_ERROR_BEEP] = pygame.mixer.Sound(str(RETRO_ERROR_BEEP_PATH))
        except pygame.error as exc:
            LOGGER.warning("Failed loading retro error beep %s: %s", RETRO_ERROR_BEEP_PATH, exc)
        for fault, name in self._mapping.items():
            sound = loaded_by_name.get(name)
            if sound is not None:
                self._sounds[fault] = sound

    @staticmethod
    def _transcode_au_to_pcm_wav(source_path: Path, dest_path: Path) -> None:
        with sunau.open(str(source_path), "rb") as src:
            nchannels = src.getnchannels()
            sampwidth = src.getsampwidth()
            framerate = src.getframerate()
            nframes = src.getnframes()
            frames = src.readframes(nframes)
        # pygame mixers are most compatible with 16-bit PCM wav.
        if sampwidth == 1:
            frames = audioop.ulaw2lin(frames, 2)
            sampwidth = 2
        elif sampwidth != 2:
            frames = audioop.lin2lin(frames, sampwidth, 2)
            sampwidth = 2
        # AU/SND linear PCM payloads are big-endian; WAV PCM expects little-endian.
        # Without this swap, audio plays as loud static/garbled noise.
        if sampwidth > 1:
            frames = audioop.byteswap(frames, sampwidth)
        with wave.open(str(dest_path), "wb") as out:
            out.setnchannels(nchannels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(frames)

    def update(self, faults: tuple[str, ...], *, allow_playback: bool) -> None:
        if not self._enabled or not allow_playback:
            return
        current_faults = set(faults)
        cleared_faults = self._active_faults - current_faults
        for fault in cleared_faults:
            self._played_faults.discard(fault)
        self._active_faults = current_faults

        for fault in faults:
            if fault in self._played_faults or fault in self._pending_faults:
                continue
            if fault in self._sounds:
                self._pending_faults.append(fault)

        if self._channel is None or self._channel.get_busy() or not self._pending_faults:
            return
        fault = self._pending_faults.pop(0)
        sound = self._sounds.get(fault)
        if sound is None:
            return
        self._channel.play(sound)
        self._played_faults.add(fault)


class HUDRenderer:
    """Render loop that drives Pygame surfaces."""

    def __init__(
        self,
        screen_size: tuple[int, int] = SCREEN_SIZE,
        *,
        use_display: bool = True,
        preferences_path: Path | str | None = "settings/hud_settings.json",
    ) -> None:
        pygame.init()
        self._use_display = use_display
        self._screen_size = screen_size
        if use_display:
            self.screen = pygame.display.set_mode(screen_size, pygame.RESIZABLE)
            pygame.display.set_caption("Albatross HUD")
        else:
            self.screen = pygame.Surface(screen_size)
        self.clock = pygame.time.Clock()
        self.running = False
        self.state = StateSnapshot()
        self.state_lock = threading.Lock()
        self.widgets: List = []
        self._post_lines: list[tuple[str, bool]] = []
        self._post_started_at = 0.0
        self._post_fault_active = False
        self._post_complete = False
        self._ack_key = pygame.K_RETURN
        self._air_shot_key = pygame.K_f
        self._joy_select_button = 0
        self._joy_back_button = 1
        self._joy_air_shot_button = 2
        self._modes = ["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]
        self._mode_index = 0
        self._mode_selection_index = 0
        self._mode_layout_state = {
            "left": 0.18,
            "center": 0.34,
            "right": 0.48,
            "rpm": 0.07,
            "boost": 0.32,
            "afr": 0.22,
            "stats": 0.18,
            "fuel": 0.12,
            "temps": 0.62,
            "traction": 0.14,
            "airshot": 0.14,
            "alert": 0.32,
        }
        self._mode_layout_anim_until = 0.0
        self._traction_levels = ["LOW", "MED", "HIGH", "OFF"]
        self._traction_index = 1
        self._traction_callback = None
        self._mode_callback = None
        self._media_callback = None
        self._fuel_type_callback = None
        self._flame_callback = None
        self._air_shot_callback = None
        self._fault_log_callback: Callable[[tuple[str, ...], StateSnapshot], None] | None = None
        self._snapshot_log_callback: Callable[[StateSnapshot], None] | None = None
        self._can_freshness_callback: Callable[[], float] | None = None
        self._ecu_can_freshness_callback: Callable[[], float] | None = None
        self._controller_can_freshness_callback: Callable[[], float] | None = None
        self._runtime_heartbeat_callback: Callable[[], None] | None = None
        self._runtime_health_callback: Callable[[], None] | None = None
        self._runtime_health_confirmed = False
        self._runtime_started_monotonic = time.monotonic()
        self._log_export_callback: Callable[[], str] | None = None
        self._update_install_callback: Callable[[StateSnapshot], str] | None = None
        self._online_update_callback: Callable[[StateSnapshot, Callable[[str, int, int], None]], str] | None = None
        self._last_logged_faults: set[str] = set()
        self._fault_log_lock = threading.Lock()
        self._log_export_status = "READY"
        self._update_install_status = "READY"
        self._online_update_status = "READY"
        self._online_update_progress = 0.0
        self._online_update_busy = False
        self._online_update_lock = threading.Lock()
        self._focus_targets = ["NAV", "SETTINGS", "MEDIA", "FAULTS"]
        self._focus_index = 0
        self._active_menu = "home"
        self._fault_detail_index = 0
        self._visible_faults: tuple[str, ...] = ()
        self._settings_cursor = 0
        self._media_items = ["PREV", "PLAY", "NEXT", "DEVICES"]
        self._media_index = 0
        self._media_device_cursor = 0
        self._media_device_menu_open = False
        self._setting_items = ["TRACTION", "FUEL TYPE", "FLAME MODE", "BRIGHTNESS", "PHONE LINK", "THEME", "AUTO DIM", "NETWORK", "NAV MAP", "NAV ONLINE", "NAV ZOOM", "NAV CACHE", "EXPORT LOGS", "INSTALL UPDATE", "ONLINE UPDATE", "SERVICE MODE", "SENSOR CONF"]
        self._phone_link_enabled = False
        self._flame_mode_manual_enabled = False
        self._brightness_levels = [25, 40, 55, 70, 85, 100]
        self._brightness_index = 3
        self._fuel_types = ["87", "91", "93", "100", "E85", "C16"]
        self._fuel_type_index = self._fuel_types.index(self.state.environment.fuel_type) if self.state.environment.fuel_type in self._fuel_types else 2
        self._themes = ["AMBER", "NIGHT", "NIGHT OPS", "HIGH-CON"]
        self._theme_index = 0
        self._auto_dim_enabled = True
        self._preferences = HUDPreferences(preferences_path)
        self._load_preferences()
        navigation_settings = Path(preferences_path).parent / "navigation.json" if preferences_path is not None else Path("settings/navigation.json")
        self._navigation = NavigationManager(settings_path=navigation_settings)
        self._network = PiNetworkManager()
        self._nav_cursor = 0
        self._nav_action_cursor = 0
        self._nav_search_cursor = 0
        self._nav_arrival_cursor = 0
        self._nav_selected_waypoint_id: str | None = None
        self._nav_keyboard_text = ""
        self._nav_keyboard_purpose = "waypoint"
        self._nav_keyboard_row = 0
        self._nav_keyboard_col = 0
        self._network_cursor = 0
        self._network_password_text = ""
        self._network_password_uppercase = True
        self._network_password_row = 0
        self._network_password_col = 0
        self._network_selected_ssid = ""
        self._mode_layout_anim_until = time.monotonic() + 0.9
        apply_theme(self._themes[self._theme_index])
        self._phone_track = ""
        self._phone_artist = ""
        self._phone_position_s = 0.0
        self._phone_length_s = 0.0
        self._available_devices: tuple[tuple[str, str], ...] = ()
        self._last_snapshot_time = self.state.environment.time
        self._last_can_fresh_monotonic = time.monotonic()
        self._fault_condition_since: dict[str, float] = {}
        self._advisory_latch_until: dict[str, float] = {}
        self._last_iat_sample: tuple[float, float] | None = None
        self._display_time_anchor = self.state.environment.time
        self._display_time_anchor_monotonic = self._last_can_fresh_monotonic
        self._economy_tracker = EconomyTracker()
        self._audio = EvaAlertAudio()
        self._create_widgets()

    def _persistent_fault(self, name: str, condition: bool, now_s: float, hold_s: float) -> bool:
        if not condition:
            self._fault_condition_since.pop(name, None)
            return False
        started_at = self._fault_condition_since.setdefault(name, now_s)
        return now_s - started_at >= hold_s

    @staticmethod
    def _finite(value: float | int) -> bool:
        return math.isfinite(float(value))

    def _runtime_faults(self, state: StateSnapshot, now_s: float) -> tuple[str, ...]:
        active: set[str] = set()
        engine = state.engine
        temps = state.temps
        wmi = state.wmi
        air = state.air_shot
        gear = str(engine.gear).upper()
        in_drive = gear not in {"N", "?", ""}
        high_load = engine.throttle_pct > 55 or engine.engine_load_pct > 60

        if self._controller_can_age_s(now_s) > 1.5:
            active.add("CAN STALE")
        if self._ecu_can_age_s(now_s) > 1.5:
            active.add("ECU STALE")
        if temps.oil_pressure_psi < 5 and engine.rpm > 1200:
            active.add("CRITICAL OIL PRESS")
        elif temps.oil_pressure_psi < 12 and engine.rpm > 1800:
            active.add("LOW OIL PRESS")
        if temps.coolant_temp_f > 235:
            active.add("COOLANT HOT")
        if temps.exhaust_temp_f > 1600:
            active.add("EGT HIGH")
        if temps.intake_temp_f > 155:
            active.add("INTAKE AIR HOT")
        if 0.0 < temps.battery_voltage < 11.8 and engine.rpm > 900:
            active.add("BATTERY LOW")
        if temps.battery_voltage > 15.2:
            active.add("BATTERY HIGH")
        if engine.boost_psi > max(1.0, engine.target_boost_psi + 3.0):
            active.add("OVERBOOST")
        if engine.knock_events >= 2:
            active.add("KNOCK ESCALATE")
        if 0.0 <= state.environment.fuel_level_pct <= 12:
            active.add("LOW FUEL")
        if wmi.fault_active:
            active.add("WMI FLOW LOW")
        if wmi.tank_level_pct <= 5 and (wmi.commanded_flow_cc_min > 0 or engine.target_boost_psi > 6):
            active.add("WMI TANK EMPTY")
        if wmi.commanded_flow_cc_min >= 100 and wmi.actual_flow_cc_min < wmi.commanded_flow_cc_min * 0.6:
            if self._persistent_fault("WMI FLOW LOW", True, now_s, 0.25):
                active.add("WMI FLOW LOW")
        else:
            self._persistent_fault("WMI FLOW LOW", False, now_s, 0.25)
        if engine.gear == "?":
            active.add("GEAR SENSOR")
        if air.pressure_psi < 35 and (air.is_firing or engine.target_boost_psi > 6):
            active.add("AIR SHOT LOW")
        if state.clutch.severity in {"MODERATE", "SEVERE"} or state.clutch.slip_pct >= 25:
            active.add("CLUTCH SLIP")
        if state.traction.sensor_fault:
            active.add("SPEED SENSOR")

        slow_spool = (
            engine.target_boost_psi >= 6.0
            and high_load
            and engine.rpm >= 3500
            and in_drive
            and engine.wastegate_duty_pct >= 50
            and engine.boost_psi < max(engine.target_boost_psi * 0.55, engine.target_boost_psi - 5.0)
        )
        if self._persistent_fault("SLOW TURBO SPOOL", slow_spool, now_s, 2.0):
            active.add("SLOW TURBO SPOOL")

        boost_error = (
            engine.target_boost_psi >= 4.0
            and high_load
            and engine.rpm >= 3000
            and abs(engine.boost_psi - engine.target_boost_psi) > 4.0
        )
        if self._persistent_fault("BOOST CONTROL ERROR", boost_error, now_s, 1.5):
            active.add("BOOST CONTROL ERROR")

        wastegate_stuck = (engine.target_boost_psi <= 2.0 or engine.throttle_pct < 20) and engine.boost_psi > 5.0
        if self._persistent_fault("WASTEGATE STUCK", wastegate_stuck, now_s, 1.0):
            active.add("WASTEGATE STUCK")

        speed_sensor_fault = engine.rpm > 2800 and engine.throttle_pct > 25 and in_drive and engine.speed_mph < 2.0
        if self._persistent_fault("SPEED SENSOR", speed_sensor_fault, now_s, 1.0):
            active.add("SPEED SENSOR")

        egt_boost_mismatch = (
            high_load
            and engine.rpm > 4000
            and temps.exhaust_temp_f > 1500
            and engine.target_boost_psi > 6.0
            and engine.boost_psi < 2.0
        )
        if self._persistent_fault("CYL EGT BOOST MISMATCH", egt_boost_mismatch, now_s, 1.0):
            active.add("CYL EGT BOOST MISMATCH")

        boost_mismatch = (
            engine.boost_left_psi >= 0.0
            and engine.boost_right_psi >= 0.0
            and high_load
            and engine.rpm > 3000
            and (engine.target_boost_psi > 4.0 or engine.boost_psi > 4.0)
            and abs(engine.boost_left_psi - engine.boost_right_psi) >= 3.0
        )
        if self._persistent_fault("CYL BOOST MISMATCH", boost_mismatch, now_s, 0.6):
            active.add("CYL BOOST MISMATCH")

        egt_mismatch = (
            temps.exhaust_left_temp_f >= 0.0
            and temps.exhaust_right_temp_f >= 0.0
            and high_load
            and engine.rpm > 3000
            and abs(temps.exhaust_left_temp_f - temps.exhaust_right_temp_f) >= 150.0
        )
        if self._persistent_fault("CYL EGT MISMATCH", egt_mismatch, now_s, 0.8):
            active.add("CYL EGT MISMATCH")

        afr_mismatch = (
            engine.afr_left > 0.0
            and engine.afr_right > 0.0
            and high_load
            and engine.rpm > 2500
            and abs(engine.afr_left - engine.afr_right) >= 0.8
        )
        if self._persistent_fault("CYL AFR MISMATCH", afr_mismatch, now_s, 0.8):
            active.add("CYL AFR MISMATCH")

        sensor_values = (
            engine.boost_psi,
            engine.boost_left_psi,
            engine.boost_right_psi,
            engine.target_boost_psi,
            engine.throttle_pct,
            engine.engine_load_pct,
            temps.coolant_temp_f,
            temps.oil_temp_f,
            temps.oil_pressure_psi,
            temps.battery_voltage,
            temps.intake_temp_f,
            temps.exhaust_temp_f,
            temps.exhaust_left_temp_f,
            temps.exhaust_right_temp_f,
            wmi.tank_level_pct,
            wmi.commanded_flow_cc_min,
            wmi.actual_flow_cc_min,
        )
        sensor_range_fault = (
            not all(self._finite(value) for value in sensor_values)
            or engine.throttle_pct < 0
            or engine.throttle_pct > 100
            or engine.engine_load_pct < 0
            or engine.engine_load_pct > 100
            or temps.battery_voltage > 18
            or (temps.battery_voltage < -0.1 and temps.battery_voltage != -1)
            or temps.oil_pressure_psi < -1
            or wmi.tank_level_pct < 0
            or wmi.tank_level_pct > 100
            or wmi.actual_flow_cc_min < 0
            or wmi.commanded_flow_cc_min < 0
        )
        if sensor_range_fault:
            active.add("SENSOR RANGE FAULT")

        # Return only currently active faults; AlertPanel handles post-clear hold timing.
        return tuple(sorted(active))

    def _predictive_advisories(self, state: StateSnapshot, now_s: float) -> tuple[str, ...]:
        active: set[str] = set()
        faults = set(state.faults)
        temps = state.temps
        engine = state.engine
        fuel_level = state.environment.fuel_level_pct

        previous_iat = self._last_iat_sample
        if math.isfinite(float(temps.intake_temp_f)):
            if previous_iat is not None:
                prev_t, prev_iat = previous_iat
                dt = max(0.001, now_s - prev_t)
                rate_f_per_min = (temps.intake_temp_f - prev_iat) / dt * 60.0
                if (
                    "INTAKE AIR HOT" not in faults
                    and temps.intake_temp_f < 150.0
                    and temps.intake_temp_f > 110.0
                    and (rate_f_per_min > 8.0 or temps.intake_temp_f > 135.0)
                ):
                    active.add("IAT RISING")
            self._last_iat_sample = (now_s, temps.intake_temp_f)

        if "LOW FUEL" not in faults:
            range_critical = 0.0 <= state.economy.miles_to_empty <= 15.0
            level_near_reserve = 5.0 < fuel_level <= 10.0
            if range_critical or level_near_reserve:
                active.add("FUEL RANGE CRITICAL")

        if "BATTERY LOW" not in faults and "BATTERY HIGH" not in faults:
            if engine.rpm > 1600 and 12.0 <= temps.battery_voltage < 13.0:
                active.add("BATTERY NOT CHARGING")

        if "COOLANT HOT" not in faults and 225.0 < temps.coolant_temp_f <= 240.0:
            active.add("COOLANT TEMP CLIMBING")
        if "EGT HIGH" not in faults and 1550.0 < temps.exhaust_temp_f <= 1650.0:
            active.add("EGT NEAR LIMIT")
        if "LOW OIL PRESS" not in faults and engine.rpm > 1800 and 12.0 <= temps.oil_pressure_psi < 18.0:
            active.add("OIL PRESSURE MARGINAL")
        if temps.oil_temp_f > 260.0 and "COOLANT HOT" not in faults:
            active.add("OIL TEMP HIGH")
        if "KNOCK" not in faults and "KNOCK ESCALATE" not in faults and 0 < engine.knock_events < 3:
            active.add("KNOCK ACTIVITY")
        if "WMI TANK EMPTY" not in faults and 3.0 <= state.wmi.tank_level_pct < 12.0:
            active.add("WMI TANK LOW")
        if (
            "WMI FLOW LOW" not in faults
            and state.wmi.commanded_flow_cc_min > 0
            and state.wmi.actual_flow_cc_min < state.wmi.commanded_flow_cc_min * 0.85
        ):
            active.add("WMI FLOW TREND")
        if (
            "BOOST CONTROL ERROR" not in faults
            and "SLOW TURBO SPOOL" not in faults
            and engine.target_boost_psi >= 8.0
            and engine.throttle_pct > 35.0
            and engine.boost_psi < engine.target_boost_psi - 3.0
        ):
            active.add("BOOST LAG WATCH")

        for advisory in active:
            self._advisory_latch_until[advisory] = now_s + 3.5
        self._advisory_latch_until = {
            advisory: until for advisory, until in self._advisory_latch_until.items() if until > now_s
        }
        return tuple(sorted(self._advisory_latch_until))

    def configure_traction_callback(self, callback) -> None:
        self._traction_callback = callback

    def configure_mode_callback(self, callback) -> None:
        self._mode_callback = callback

    @staticmethod
    def _index_for_value(values: list, value, default: int) -> int:
        try:
            return values.index(value)
        except ValueError:
            return default

    def _load_preferences(self) -> None:
        preferences = self._preferences.load()
        self._mode_index = self._index_for_value(self._modes, preferences.get("mode"), self._mode_index)
        self._mode_selection_index = self._mode_index
        self._traction_index = self._index_for_value(self._traction_levels, preferences.get("traction_level"), self._traction_index)
        self._fuel_type_index = self._index_for_value(self._fuel_types, preferences.get("fuel_type"), self._fuel_type_index)
        self._theme_index = self._index_for_value(self._themes, preferences.get("theme"), self._theme_index)
        self._phone_link_enabled = bool(preferences.get("phone_link_enabled", self._phone_link_enabled))
        self._auto_dim_enabled = bool(preferences.get("auto_dim_enabled", self._auto_dim_enabled))
        self._flame_mode_manual_enabled = bool(preferences.get("flame_mode_enabled", self._flame_mode_manual_enabled))
        brightness = preferences.get("brightness_pct")
        if isinstance(brightness, (int, float)):
            closest = min(
                range(len(self._brightness_levels)),
                key=lambda idx: abs(self._brightness_levels[idx] - float(brightness)),
            )
            self._brightness_index = closest
        mode = self._modes[self._mode_index]
        fuel_type = self._fuel_types[self._fuel_type_index]
        traction_level = self._traction_levels[self._traction_index]
        self.state = replace(
            self.state,
            environment=replace(
                self.state.environment,
                mode=mode,
                fuel_type=fuel_type,
                flame_mode_enabled=self._effective_flame_mode_enabled(),
                rev_limiter_strategy="IGNITION CUT" if self._effective_flame_mode_enabled() else "FUEL CUT",
                brightness_pct=float(self._brightness_levels[self._brightness_index]),
            ),
            traction=replace(self.state.traction, intervention_level=traction_level),
        )

    def _save_preferences(self) -> None:
        self._preferences.save(
            {
                "version": 1,
                "mode": self._modes[self._mode_index],
                "traction_level": self._traction_levels[self._traction_index],
                "fuel_type": self._fuel_types[self._fuel_type_index],
                "flame_mode_enabled": self._flame_mode_manual_enabled,
                "brightness_pct": self._brightness_levels[self._brightness_index],
                "phone_link_enabled": self._phone_link_enabled,
                "theme": self._themes[self._theme_index],
                "auto_dim_enabled": self._auto_dim_enabled,
            }
        )

    def sync_persisted_controls(self) -> None:
        """Send persisted settings to connected controllers after callbacks attach."""
        if self._mode_callback:
            self._mode_callback(self._mode_index + 1)
        if self._traction_callback:
            self._traction_callback(self._traction_index + 1)
        if self._fuel_type_callback:
            self._fuel_type_callback(self._fuel_type_index)
        self._notify_flame_mode()
        if self._media_callback:
            self._media_callback("phone_link", 1 if self._phone_link_enabled else 0)

    def _effective_flame_mode_enabled(self, mode_index: int | None = None) -> bool:
        idx = self._mode_index if mode_index is None else mode_index
        mode = self._modes[max(0, min(idx, len(self._modes) - 1))]
        return self._flame_mode_manual_enabled or mode in {"RACE", "ALBATROSS"}

    def _notify_flame_mode(self) -> None:
        enabled = self._effective_flame_mode_enabled()
        with self.state_lock:
            self.state = replace(
                self.state,
                environment=replace(
                    self.state.environment,
                    flame_mode_enabled=enabled,
                    rev_limiter_strategy="IGNITION CUT" if enabled else "FUEL CUT",
                ),
            )
        if self._flame_callback:
            self._flame_callback(enabled)

    def _apply_mode_selection(self, mode_index: int, *, notify: bool = True) -> None:
        if not self._modes:
            return
        self._mode_index = max(0, min(mode_index, len(self._modes) - 1))
        self._mode_selection_index = self._mode_index
        mode = self._modes[self._mode_index]
        with self.state_lock:
            self.state = replace(
                self.state,
                environment=replace(self.state.environment, mode=mode),
            )
        if notify and self._mode_callback:
            self._mode_callback(self._mode_index + 1)
        if notify:
            self._notify_flame_mode()
        if notify:
            self._save_preferences()
        self._mode_layout_anim_until = time.monotonic() + 0.9
        self._create_widgets()

    def configure_media_callback(self, callback) -> None:
        self._media_callback = callback

    def configure_fuel_type_callback(self, callback) -> None:
        self._fuel_type_callback = callback

    def configure_flame_callback(self, callback) -> None:
        self._flame_callback = callback

    def configure_air_shot_callback(self, callback) -> None:
        self._air_shot_callback = callback

    def configure_fault_log_callback(self, callback: Callable[[tuple[str, ...], StateSnapshot], None]) -> None:
        self._fault_log_callback = callback

    def configure_snapshot_log_callback(self, callback: Callable[[StateSnapshot], None]) -> None:
        self._snapshot_log_callback = callback

    def configure_can_freshness_callback(
        self,
        callback: Callable[[], float],
        *,
        ecu_callback: Callable[[], float] | None = None,
        controller_callback: Callable[[], float] | None = None,
    ) -> None:
        self._can_freshness_callback = callback
        self._ecu_can_freshness_callback = ecu_callback
        self._controller_can_freshness_callback = controller_callback

    def configure_runtime_heartbeat_callback(self, callback: Callable[[], None]) -> None:
        self._runtime_heartbeat_callback = callback

    def configure_runtime_health_callback(self, callback: Callable[[], None]) -> None:
        self._runtime_health_callback = callback

    def _can_age_s(self, now_s: float | None = None) -> float:
        if self._can_freshness_callback is not None:
            try:
                return max(0.0, float(self._can_freshness_callback()))
            except Exception:
                LOGGER.exception("CAN freshness callback failed")
                return float("inf")
        current = time.monotonic() if now_s is None else now_s
        return max(0.0, current - self._last_can_fresh_monotonic)

    def _ecu_can_age_s(self, now_s: float | None = None) -> float:
        if self._ecu_can_freshness_callback is not None:
            try:
                return max(0.0, float(self._ecu_can_freshness_callback()))
            except Exception:
                LOGGER.exception("ECU CAN freshness callback failed")
                return float("inf")
        return self._can_age_s(now_s)

    def _controller_can_age_s(self, now_s: float | None = None) -> float:
        if self._controller_can_freshness_callback is not None:
            try:
                return max(0.0, float(self._controller_can_freshness_callback()))
            except Exception:
                LOGGER.exception("Controller CAN freshness callback failed")
                return float("inf")
        return self._can_age_s(now_s)

    def configure_log_export_callback(self, callback: Callable[[], str]) -> None:
        self._log_export_callback = callback

    def configure_update_install_callback(self, callback: Callable[[StateSnapshot], str]) -> None:
        self._update_install_callback = callback

    def configure_online_update_callback(self, callback: Callable[[StateSnapshot, Callable[[str, int, int], None]], str]) -> None:
        self._online_update_callback = callback

    def _log_new_faults(self, state: StateSnapshot, *, clear_missing: bool = True) -> None:
        current = set(state.faults)
        with self._fault_log_lock:
            new_faults = tuple(sorted(current - self._last_logged_faults))
            if clear_missing:
                self._last_logged_faults = current
            else:
                self._last_logged_faults.update(current)
        if new_faults and self._fault_log_callback:
            try:
                self._fault_log_callback(new_faults, state)
            except Exception:
                LOGGER.exception("Fault logging failed")

    def update_phone_status(self, *, artist: str, track: str, position_s: float, length_s: float, devices: tuple[tuple[str, str], ...]) -> None:
        self._phone_artist = artist
        self._phone_track = track
        self._phone_position_s = max(0.0, position_s)
        self._phone_length_s = max(0.0, length_s)
        self._available_devices = devices

    def _mode_ratios(self, mode: str) -> dict[str, float]:
        profiles = {
            "ECO": {
                "left": 0.24,
                "center": 0.30,
                "right": 0.46,
                "rpm": 0.060,
                "boost": 0.19,
                "afr": 0.16,
                "stats": 0.42,
                "fuel": 0.16,
                "temps": 0.62,
                "traction": 0.10,
                "airshot": 0.14,
                "alert": 0.24,
            },
            "NORMAL": {
                "left": 0.21,
                "center": 0.32,
                "right": 0.47,
                "rpm": 0.068,
                "boost": 0.25,
                "afr": 0.18,
                "stats": 0.34,
                "fuel": 0.14,
                "temps": 0.56,
                "traction": 0.12,
                "airshot": 0.14,
                "alert": 0.30,
            },
            "SPORT": {
                "left": 0.18,
                "center": 0.38,
                "right": 0.44,
                "rpm": 0.078,
                "boost": 0.38,
                "afr": 0.18,
                "stats": 0.24,
                "fuel": 0.10,
                "temps": 0.51,
                "traction": 0.17,
                "airshot": 0.14,
                "alert": 0.34,
            },
            "RACE": {
                "left": 0.16,
                "center": 0.42,
                "right": 0.42,
                "rpm": 0.088,
                "boost": 0.43,
                "afr": 0.16,
                "stats": 0.23,
                "fuel": 0.08,
                "temps": 0.48,
                "traction": 0.20,
                "airshot": 0.16,
                "alert": 0.38,
            },
            "ALBATROSS": {
                "left": 0.15,
                "center": 0.43,
                "right": 0.42,
                "rpm": 0.092,
                "boost": 0.43,
                "afr": 0.14,
                "stats": 0.25,
                "fuel": 0.07,
                "temps": 0.44,
                "traction": 0.17,
                "airshot": 0.22,
                "alert": 0.42,
            },
        }
        target = profiles.get(mode, profiles["NORMAL"])
        # Soft animation toward target ratios so gauges move smoothly.
        for key, value in target.items():
            current = self._mode_layout_state.setdefault(key, value)
            self._mode_layout_state[key] = current + (value - current) * 0.25
        return dict(self._mode_layout_state)

    def _create_widgets(self) -> None:
        # Defensive initialization for partially-merged working copies.
        if not hasattr(self, "_modes"):
            self._modes = ["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]
        if not hasattr(self, "_mode_index"):
            self._mode_index = 0
        if not hasattr(self, "_mode_selection_index"):
            self._mode_selection_index = self._mode_index
        if not hasattr(self, "_mode_layout_state"):
            self._mode_layout_state = {}
        for key, value in {
            "left": 0.18,
            "center": 0.34,
            "right": 0.48,
            "rpm": 0.07,
            "boost": 0.32,
            "afr": 0.22,
            "stats": 0.18,
            "fuel": 0.12,
            "temps": 0.62,
            "traction": 0.14,
            "airshot": 0.14,
            "alert": 0.32,
        }.items():
            self._mode_layout_state.setdefault(key, value)

        width, height = self.screen.get_size()
        padding = max(int(width * 0.02), 24)
        gutter = max(int(height * 0.02), 18)
        top_bar_height = max(int(height * 0.12), 80)
        message_height = max(int(height * 0.06), 40)
        mode = self._modes[self._mode_index]
        ratios = self._mode_ratios(mode)
        rpm_height = max(int(height * ratios["rpm"]), 44)

        top_bar_rect = pygame.Rect(0, 0, width, top_bar_height)
        message_rect = pygame.Rect(0, height - message_height, width, message_height)
        rpm_rect = pygame.Rect(padding, top_bar_height + gutter, width - 2 * padding, rpm_height)

        content_top = rpm_rect.bottom + gutter
        content_height = max(height - message_height - content_top - gutter, 200)

        available_width = width - 2 * padding
        column_gutter = max(int(width * 0.015), 16)
        usable_width = max(available_width - 2 * column_gutter, 300)

        min_left = max(int(width * 0.14), 180)
        min_center = max(int(width * 0.22), 230)
        min_right = max(int(width * 0.28), 300)
        if usable_width <= min_left + min_center + min_right:
            scale = usable_width / float(min_left + min_center + min_right)
            left_width = max(int(min_left * scale), 160)
            center_width = max(int(min_center * scale), 180)
            right_width = max(usable_width - left_width - center_width, 160)
        else:
            leftover = usable_width - (min_left + min_center + min_right)
            width_weight = max(ratios["left"] + ratios["center"] + ratios["right"], 1e-6)
            left_width = min_left + int(leftover * ratios["left"] / width_weight)
            center_width = min_center + int(leftover * ratios["center"] / width_weight)
            right_width = usable_width - left_width - center_width

        left_x = padding
        center_x = left_x + left_width + column_gutter
        right_x = center_x + center_width + column_gutter

        alert_height = max(int(content_height * ratios["alert"]), int(height * 0.14))
        speed_height = max(content_height - alert_height - gutter, int(height * 0.22))
        if speed_height + alert_height + gutter > content_height:
            alert_height = max(content_height - speed_height - gutter, 80)
        speed_area = pygame.Rect(left_x, content_top, left_width, speed_height)
        alert_rect = pygame.Rect(left_x, speed_area.bottom + gutter, left_width, alert_height)

        inner_gap = max(10, int(left_width * 0.05))
        gear_size = min(speed_area.height, max(int(left_width * 0.33), int(height * 0.15)))
        if speed_area.width - gear_size - inner_gap < max(int(left_width * 0.35), 140):
            stack_height = speed_area.height
            gear_height = min(gear_size, max(int(stack_height * 0.4), 90))
            speed_height_stack = max(stack_height - gear_height - inner_gap, int(stack_height * 0.45))
            if speed_height_stack + gear_height + inner_gap > stack_height:
                gear_height = max(stack_height - speed_height_stack - inner_gap, 60)
            speed_rect = pygame.Rect(speed_area.x, speed_area.y, speed_area.width, speed_height_stack)
            gear_rect = pygame.Rect(
                speed_area.x,
                speed_rect.bottom + inner_gap,
                speed_area.width,
                max(gear_height, stack_height - speed_height_stack - inner_gap),
            )
        else:
            speed_rect = pygame.Rect(speed_area.x, speed_area.y, speed_area.width - gear_size - inner_gap, speed_area.height)
            gear_rect = pygame.Rect(speed_rect.right + inner_gap, speed_area.y, gear_size, gear_size)

        panel_gap = max(int(height * 0.018), 12)
        boost_ratio = ratios["boost"]
        afr_ratio = ratios["afr"]
        stats_ratio = ratios["stats"] + afr_ratio
        fuel_height = max(int(content_height * ratios["fuel"]), int(height * 0.055))
        center_budget = max(content_height - fuel_height - 2 * panel_gap, 120)
        center_weight = max(boost_ratio + stats_ratio, 1e-6)
        boost_height = max(int(center_budget * boost_ratio / center_weight), int(height * 0.16))
        stats_height = max(int(center_budget * stats_ratio / center_weight), int(height * 0.13))
        center_total = boost_height + stats_height
        if center_total > center_budget:
            scale = center_budget / float(center_total)
            boost_height = max(int(boost_height * scale), 56)
            stats_height = max(int(stats_height * scale), 46)
        boost_rect = pygame.Rect(center_x, content_top, center_width, boost_height)
        stats_rect = pygame.Rect(center_x, boost_rect.bottom + panel_gap, center_width, stats_height)

        bottom_limit = message_rect.y - panel_gap
        compact_strip_height = max(36, min(46, int(height * 0.065)))
        airshot_height = compact_strip_height
        traction_height = compact_strip_height
        # Fuel gauge moved to center-lower zone under mode stats.
        fuel_width = center_width
        fuel_x = center_x
        fuel_rect = pygame.Rect(fuel_x, stats_rect.bottom + panel_gap, fuel_width, fuel_height)

        # WMI panel removed; WMI readouts are merged into TempsGrid. Anchor the
        # lower right panels from the bottom so Air Shot cannot disappear below
        # the global hint/message area when the window is short.
        map_mode = mode in {"ECO", "NORMAL"}
        right_panel_gap = panel_gap if map_mode else max(6, int(height * 0.01))
        airshot_rect = pygame.Rect(right_x, bottom_limit - airshot_height, right_width, airshot_height)
        traction_rect = pygame.Rect(right_x, airshot_rect.y - right_panel_gap - traction_height, right_width, traction_height)
        temps_bottom = traction_rect.y - right_panel_gap
        right_primary_height = max(36, temps_bottom - content_top)
        if map_mode:
            navigation_rect = pygame.Rect(right_x, content_top, right_width, right_primary_height)
            temps_rect = None
        else:
            nav_banner_height = max(36, min(44, int(height * 0.06)))
            navigation_rect = pygame.Rect(right_x, content_top, right_width, nav_banner_height)
            temps_rect = pygame.Rect(
                right_x,
                navigation_rect.bottom + right_panel_gap,
                right_width,
                max(36, temps_bottom - navigation_rect.bottom - right_panel_gap),
            )

        prior_fault_latch_until: dict[str, float] = {}
        for widget in self.widgets:
            if isinstance(widget, AlertPanel):
                prior_fault_latch_until = dict(widget._fault_latch_until)
                break

        widgets = [
            HeaderBar(top_bar_rect),
            MessageLine(message_rect),
            RpmBar(rpm_rect),
            SpeedGear(speed_rect, gear_rect),
            BoostPanel(boost_rect),
            ModeStatsPanel(stats_rect),
            AlertPanel(alert_rect),
            FuelPanel(fuel_rect),
            TractionPanel(traction_rect),
            AirShotPanel(airshot_rect),
        ]
        if temps_rect is not None:
            widgets.insert(7, TempsGrid(temps_rect, split=True))
            widgets.insert(7, NavigationPanel(navigation_rect, self._navigation, compact=True))
        else:
            widgets.insert(7, NavigationPanel(navigation_rect, self._navigation))
        self.widgets = widgets
        for widget in self.widgets:
            if isinstance(widget, AlertPanel):
                widget._fault_latch_until = prior_fault_latch_until
                break

    def configure_input_bindings(self, ack_key: int, air_shot_key: int | None = None) -> None:
        self._ack_key = ack_key
        if air_shot_key is not None:
            self._air_shot_key = air_shot_key

    def _run_post(self, state: StateSnapshot) -> None:
        if self._post_started_at <= 0.0:
            self._post_started_at = time.monotonic()
        has_ecu_signal = any(
            (
                state.engine.rpm > 0,
                state.engine.throttle_pct > 0,
                state.temps.coolant_temp_f > 0,
                state.temps.oil_temp_f > 0,
                state.temps.oil_pressure_psi > 0,
            )
        )
        has_arduino_signal = any(
            (
                state.air_shot.pressure_psi > 0,
                state.air_shot.charges_remaining > 0,
                state.wmi.commanded_flow_cc_min > 0,
                state.wmi.actual_flow_cc_min > 0,
                state.traction.slip_pct > 0,
                abs(state.traction.wheelie_pitch_deg) > 0.01,
            )
        )
        age_s = self._can_age_s()
        has_can_signal = (has_ecu_signal or has_arduino_signal or state.engine.speed_mph > 0 or state.engine.boost_psi > 0) and age_s <= 1.5

        checks = [
            ("DISPLAY BUS", self.screen.get_width() > 0 and self.screen.get_height() > 0),
            ("COOLANT SENSOR", state.temps.coolant_temp_f >= 0.0 or has_can_signal),
            ("OIL TEMP SENSOR", state.temps.oil_temp_f >= 0.0 or has_can_signal),
            ("OIL PRESS SENSOR", state.temps.oil_pressure_psi > 0),
            ("FUEL LEVEL SENSOR", has_can_signal and state.environment.fuel_level_pct >= 0.0),
            ("BATTERY VOLT", state.temps.battery_voltage >= 0.0 or has_can_signal),
            ("GEAR INPUT", has_can_signal and state.engine.gear in {"1", "2", "3", "4", "5", "6", "N"}),
            ("TRACTION INPUT", has_can_signal and state.traction.intervention_level != ""),
            ("CAN LINK", has_can_signal),
            ("USB INPUT", pygame.joystick.get_count() > 0),
        ]
        self._post_lines = [(f"TEST {name:<18} {'OK' if ok else 'FAULT'}", ok) for name, ok in checks]
        self._post_fault_active = any(not ok for _, ok in checks)

        # Keep POST live briefly so late-arriving telemetry can clear false startup faults.
        elapsed = time.monotonic() - self._post_started_at
        all_passed = not self._post_fault_active
        timed_out = elapsed >= 2.5
        self._post_complete = all_passed or timed_out

    def update_state(self, snapshot: StateSnapshot) -> None:
        with self.state_lock:
            self.state = snapshot
            self._last_can_fresh_monotonic = time.monotonic()
        if snapshot.faults:
            self._log_new_faults(snapshot, clear_missing=False)

    def run(self, state_source: Iterable[StateSnapshot] | None = None) -> None:
        self.running = True
        self._active_menu = "home"
        frame_duration = 1.0 / TARGET_FPS
        last_tick = time.perf_counter()

        state_iter = iter(state_source) if state_source else None
        if self._use_display:
            pygame.joystick.init()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE and self._use_display:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self._create_widgets()
                elif event.type == pygame.KEYDOWN:
                    if (not self._post_complete) or self._post_fault_active:
                        continue
                    if event.key == self._air_shot_key:
                        self._request_air_shot()
                    elif event.key in (pygame.K_TAB, pygame.K_m):
                        self._apply_mode_selection((self._mode_index + 1) % len(self._modes))
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self._handle_select()
                    elif event.key in (pygame.K_BACKSPACE, pygame.K_ESCAPE):
                        self._handle_back()
                    elif event.key == pygame.K_UP:
                        self._handle_up()
                    elif event.key == pygame.K_DOWN:
                        self._handle_down()
                    elif event.key == pygame.K_RIGHT:
                        self._handle_dpad_right()
                    elif event.key == pygame.K_LEFT:
                        self._handle_dpad_left()
                    elif event.key in (pygame.K_LEFTBRACKET, pygame.K_COMMA):
                        self._traction_index = (self._traction_index - 1) % len(self._traction_levels)
                        if self._traction_callback:
                            self._traction_callback(self._traction_index + 1)
                        self._save_preferences()
                    elif event.key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
                        self._traction_index = (self._traction_index + 1) % len(self._traction_levels)
                        if self._traction_callback:
                            self._traction_callback(self._traction_index + 1)
                        self._save_preferences()
                elif event.type == pygame.JOYBUTTONDOWN:
                    if (not self._post_complete) or self._post_fault_active:
                        continue
                    if event.button == self._joy_select_button:
                        self._handle_select()
                    elif event.button == self._joy_back_button:
                        self._handle_back()
                    elif event.button == self._joy_air_shot_button:
                        self._request_air_shot()
                elif event.type == pygame.JOYHATMOTION:
                    if (not self._post_complete) or self._post_fault_active:
                        continue
                    x, y = event.value
                    if y > 0:
                        self._handle_up()
                    elif y < 0:
                        self._handle_down()
                    if x > 0:
                        self._handle_dpad_right()
                    elif x < 0:
                        self._handle_dpad_left()

            if state_iter is not None:
                try:
                    snapshot = next(state_iter)
                    self.update_state(snapshot)
                except StopIteration:
                    state_iter = None

            with self.state_lock:
                state = self.state
            now_s = time.monotonic()
            if state.environment.time != self._last_snapshot_time:
                self._last_snapshot_time = state.environment.time
                self._last_can_fresh_monotonic = now_s
                self._display_time_anchor = state.environment.time
                self._display_time_anchor_monotonic = now_s
            state = replace(state, faults=self._runtime_faults(state, now_s))
            state = self._economy_tracker.update(state, now_s)
            state = replace(state, advisories=self._predictive_advisories(state, now_s))
            if self._snapshot_log_callback:
                try:
                    self._snapshot_log_callback(state)
                except Exception:
                    LOGGER.exception("Snapshot logging callback failed")
            previous_mode_index = self._mode_index
            if state.environment.mode in self._modes:
                self._mode_index = self._modes.index(state.environment.mode)
                self._mode_selection_index = self._mode_index
            if self._mode_index != previous_mode_index:
                self._mode_layout_anim_until = now_s + 0.9
            if state.environment.fuel_type in self._fuel_types:
                self._fuel_type_index = self._fuel_types.index(state.environment.fuel_type)

            # Keep the HUD clock moving even when telemetry timestamps stop updating.
            display_time = self._display_time_anchor + timedelta(
                seconds=max(0.0, now_s - self._display_time_anchor_monotonic)
            )
            state = replace(state, environment=replace(state.environment, time=display_time))

            if now_s < self._mode_layout_anim_until:
                self._create_widgets()
            # Respect externally supplied mode telemetry.
            desired_trac = self._traction_levels[self._traction_index]
            if state.traction.intervention_level != desired_trac:
                state = StateSnapshot(
                    engine=state.engine,
                    temps=state.temps,
                    air_shot=state.air_shot,
                    wmi=state.wmi,
                    traction=state.traction.__class__(
                        slip_pct=state.traction.slip_pct,
                        wheelie_pitch_deg=state.traction.wheelie_pitch_deg,
                        intervention_level=desired_trac,
                        torque_cut_pct=state.traction.torque_cut_pct,
                        active=state.traction.active,
                        sensor_fault=state.traction.sensor_fault,
                    ),
                    clutch=state.clutch,
                    lighting=state.lighting,
                    environment=state.environment,
                    economy=state.economy,
                    service=state.service,
                    system=state.system,
                    shift_light=state.shift_light,
                    faults=state.faults,
                    advisories=state.advisories,
                )

            if not self._post_complete:
                self._run_post(state)

            if self._post_complete and self._post_fault_active:
                pressed = pygame.key.get_pressed()
                if pressed[self._ack_key]:
                    self._post_fault_active = False
            self._log_new_faults(state)
            self._audio.update(
                state.faults,
                allow_playback=self._post_complete and not self._post_fault_active,
            )
            self._render_frame(state)
            if self._runtime_heartbeat_callback:
                self._runtime_heartbeat_callback()
            if (
                not self._runtime_health_confirmed
                and self._runtime_health_callback
                and self._post_complete
                and (now_s - self._runtime_started_monotonic) >= 15.0
            ):
                self._runtime_health_callback()
                self._runtime_health_confirmed = True
            self.clock.tick(TARGET_FPS)

            now = time.perf_counter()
            if now - last_tick < frame_duration:
                time.sleep(max(0.0, frame_duration - (now - last_tick)))
            last_tick = now

        pygame.quit()

    def capture_frame(self, state: StateSnapshot | None = None) -> pygame.Surface:
        """Render a single frame and return the surface copy."""
        if state is None:
            with self.state_lock:
                state = self.state
        else:
            with self.state_lock:
                self.state = state
        state = self._economy_tracker.update(state)
        state = replace(state, advisories=self._predictive_advisories(state, time.monotonic()))
        self._render_frame(state, present=False)
        return self.screen.copy()

    def _render_frame(self, state: StateSnapshot, *, present: bool = True) -> None:
        self._navigation.update_position(state.environment.gps_latitude, state.environment.gps_longitude)
        if self._navigation.arrival_prompt_pending and self._active_menu == "home":
            self._nav_arrival_cursor = 0
            self._active_menu = "nav_arrival"
        previous_focus_target = self._home_focus_target() if self._active_menu == "home" else ""
        previous_had_faults = bool(self._visible_faults)
        self._visible_faults = tuple(state.faults)
        self._normalize_home_focus(previous_focus_target, previous_had_faults)
        apply_theme(self._themes[self._theme_index])
        self.screen.fill((0, 0, 0))
        for widget in self.widgets:
            widget.draw(self.screen, state)
        self._render_home_mode_hover_underline(state)
        self._render_home_fault_focus_outline(state)
        self._render_home_navigation_focus_outline()
        self._apply_theme_overlay_pre_ui()
        self._render_top_right_media_tile()
        if self._active_menu == "settings":
            self._render_modal_dimmer()
            self._render_settings_overlay()
        elif self._active_menu == "media":
            self._render_media_overlay()
        elif self._active_menu == "fault_detail":
            self._render_modal_dimmer()
            self._render_fault_detail_overlay(state)
        elif self._active_menu == "service":
            self._render_modal_dimmer()
            self._render_service_overlay(state)
        elif self._active_menu == "sensor_confidence":
            self._render_modal_dimmer()
            self._render_sensor_confidence_overlay(state)
        elif self._active_menu == "nav_waypoints":
            self._render_modal_dimmer()
            self._render_navigation_waypoint_overlay()
        elif self._active_menu == "nav_actions":
            self._render_modal_dimmer()
            self._render_navigation_action_overlay()
        elif self._active_menu == "nav_keyboard":
            self._render_modal_dimmer()
            self._render_navigation_keyboard_overlay()
        elif self._active_menu == "nav_search_results":
            self._render_modal_dimmer()
            self._render_navigation_search_results_overlay()
        elif self._active_menu == "nav_arrival":
            self._render_modal_dimmer()
            self._render_navigation_arrival_overlay()
        elif self._active_menu == "network":
            self._render_modal_dimmer()
            self._render_network_overlay()
        elif self._active_menu == "network_password":
            self._render_modal_dimmer()
            self._render_network_password_overlay()
        self._render_global_hints()
        self._apply_brightness_overlay(state)
        if (not self._post_complete) or self._post_fault_active:
            self._render_post_overlay()
        if present and self._use_display:
            pygame.display.flip()

    def _render_post_overlay(self) -> None:
        _bg, bright, glow, fault = self._theme_colors()
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        self.screen.blit(overlay, (0, 0))
        x = 24
        y = 24
        elapsed = max(0.0, time.monotonic() - self._post_started_at)
        title_full = "POWER ON SELF TEST"
        title_chars = min(len(title_full), int(elapsed / 0.045))
        title = font(18, bold=True).render(title_full[:title_chars], True, bright)
        self.screen.blit(title, (x, y))
        y += 28
        t = elapsed - 1.0
        for idx, (line, ok) in enumerate(self._post_lines):
            phase = t - idx * 2.0
            if phase <= 0:
                continue
            prefix = f"TEST {line.split('TEST ', 1)[1].rsplit(' ',1)[0]}"
            result = "OK" if ok else "FAULT"
            if phase < 1.0:
                visible = min(len(prefix), int(phase / 0.04))
                out = prefix[:visible]
                color = glow
            else:
                out = f"{prefix} {result}"
                color = glow if ok else fault
            sz = fit_font_size(out, self.screen.get_width() - 48, 20, start_size=16)
            surf = font(sz).render(out, True, color)
            self.screen.blit(surf, (x, y))
            y += 20
        # Hold 1s after last line before allow ack prompt
        done_time = 1.0 + len(self._post_lines) * 2.0 + 1.0
        if elapsed < done_time:
            return
        ack = f"FAULT ACK REQUIRED: PRESS {pygame.key.name(self._ack_key).upper()}"
        ack_s = font(16, bold=True).render(ack, True, fault)
        self.screen.blit(ack_s, (x, self.screen.get_height() - 40))

    def _active_faults_for_detail(self, state: StateSnapshot) -> list[str]:
        return sorted(set(state.faults))

    def _cycle_fault_detail(self, delta: int) -> None:
        count = len(set(self._visible_faults))
        if count <= 0:
            return
        self._fault_detail_index = (self._fault_detail_index + delta) % count

    def _handle_dpad_right(self) -> None:
        if self._active_menu == "nav_arrival":
            self._nav_arrival_cursor = (self._nav_arrival_cursor + 1) % 2
            return
        if self._active_menu == "fault_detail":
            self._cycle_fault_detail(1)
            return
        if self._active_menu == "nav_keyboard":
            self._move_nav_keyboard(0, 1)
            return
        if self._active_menu == "network_password":
            self._move_network_password_keyboard(0, 1)
            return
        if self._active_menu in {"nav_waypoints", "nav_actions", "nav_search_results", "network"}:
            self._handle_down()
            return
        if self._active_menu == "settings":
            item = self._setting_items[self._settings_cursor]
            if item == "TRACTION":
                self._traction_index = (self._traction_index + 1) % len(self._traction_levels)
                if self._traction_callback:
                    self._traction_callback(self._traction_index + 1)
                self._save_preferences()
            elif item == "FUEL TYPE":
                self._apply_fuel_type_selection((self._fuel_type_index + 1) % len(self._fuel_types))
            elif item == "FLAME MODE":
                self._flame_mode_manual_enabled = True
                self._notify_flame_mode()
                self._save_preferences()
            elif item == "BRIGHTNESS":
                self._brightness_index = min(self._brightness_index + 1, len(self._brightness_levels) - 1)
                self._save_preferences()
            elif item == "PHONE LINK":
                self._phone_link_enabled = True
                if self._media_callback:
                    self._media_callback("phone_link", 1)
                self._save_preferences()
            elif item == "THEME":
                self._theme_index = (self._theme_index + 1) % len(self._themes)
                self._save_preferences()
            elif item == "AUTO DIM":
                self._auto_dim_enabled = True
                self._save_preferences()
            elif item == "EXPORT LOGS":
                self._export_logs()
            elif item == "INSTALL UPDATE":
                self._install_update()
            elif item == "ONLINE UPDATE":
                self._start_online_update()
            elif item == "SERVICE MODE":
                self._active_menu = "service"
            elif item == "SENSOR CONF":
                self._active_menu = "sensor_confidence"
            elif item == "NETWORK":
                self._network_cursor = 0
                self._network.refresh_async()
                self._active_menu = "network"
            elif item == "NAV MAP":
                self._navigation.set_map_enabled(True)
            elif item == "NAV ONLINE":
                self._navigation.set_online_enabled(True)
            elif item == "NAV ZOOM":
                self._navigation.set_zoom(self._navigation.zoom + 1)
            return
        if self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor + 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index + 1) % len(self._media_items)
            return
        self._focus_index = (self._focus_index + 1) % (len(self._home_focus_targets()) + len(self._modes))

    def _handle_dpad_left(self) -> None:
        if self._active_menu == "nav_arrival":
            self._nav_arrival_cursor = (self._nav_arrival_cursor - 1) % 2
            return
        if self._active_menu == "fault_detail":
            self._cycle_fault_detail(-1)
            return
        if self._active_menu == "nav_keyboard":
            self._move_nav_keyboard(0, -1)
            return
        if self._active_menu == "network_password":
            self._move_network_password_keyboard(0, -1)
            return
        if self._active_menu in {"nav_waypoints", "nav_actions", "nav_search_results", "network"}:
            self._handle_up()
            return
        if self._active_menu == "settings":
            item = self._setting_items[self._settings_cursor]
            if item == "TRACTION":
                self._traction_index = (self._traction_index - 1) % len(self._traction_levels)
                if self._traction_callback:
                    self._traction_callback(self._traction_index + 1)
                self._save_preferences()
            elif item == "FUEL TYPE":
                self._apply_fuel_type_selection((self._fuel_type_index - 1) % len(self._fuel_types))
            elif item == "FLAME MODE":
                self._flame_mode_manual_enabled = False
                self._notify_flame_mode()
                self._save_preferences()
            elif item == "BRIGHTNESS":
                self._brightness_index = max(self._brightness_index - 1, 0)
                self._save_preferences()
            elif item == "PHONE LINK":
                self._phone_link_enabled = False
                if self._media_callback:
                    self._media_callback("phone_link", 0)
                self._save_preferences()
            elif item == "THEME":
                self._theme_index = (self._theme_index - 1) % len(self._themes)
                self._save_preferences()
            elif item == "AUTO DIM":
                self._auto_dim_enabled = False
                self._save_preferences()
            elif item == "EXPORT LOGS":
                self._export_logs()
            elif item == "INSTALL UPDATE":
                self._install_update()
            elif item == "ONLINE UPDATE":
                self._start_online_update()
            elif item == "SERVICE MODE":
                self._active_menu = "service"
            elif item == "SENSOR CONF":
                self._active_menu = "sensor_confidence"
            elif item == "NETWORK":
                self._network_cursor = 0
                self._network.refresh_async()
                self._active_menu = "network"
            elif item == "NAV MAP":
                self._navigation.set_map_enabled(False)
            elif item == "NAV ONLINE":
                self._navigation.set_online_enabled(False)
            elif item == "NAV ZOOM":
                self._navigation.set_zoom(self._navigation.zoom - 1)
            return
        if self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor - 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index - 1) % len(self._media_items)
            return
        self._focus_index = (self._focus_index - 1) % (len(self._home_focus_targets()) + len(self._modes))

    def _handle_up(self) -> None:
        if self._active_menu == "nav_arrival":
            self._nav_arrival_cursor = (self._nav_arrival_cursor - 1) % 2
        elif self._active_menu == "fault_detail":
            self._cycle_fault_detail(-1)
        elif self._active_menu == "nav_waypoints":
            self._nav_cursor = (self._nav_cursor - 1) % max(1, len(self._navigation_menu_items()))
        elif self._active_menu == "nav_actions":
            self._nav_action_cursor = (self._nav_action_cursor - 1) % len(self._navigation_action_items())
        elif self._active_menu == "nav_keyboard":
            self._move_nav_keyboard(-1, 0)
        elif self._active_menu == "nav_search_results":
            self._nav_search_cursor = (self._nav_search_cursor - 1) % max(1, len(self._navigation_search_items()))
        elif self._active_menu == "network":
            self._network_cursor = (self._network_cursor - 1) % max(1, len(self._network_menu_items()))
        elif self._active_menu == "network_password":
            self._move_network_password_keyboard(-1, 0)
        elif self._active_menu == "settings":
            self._settings_cursor = (self._settings_cursor - 1) % len(self._setting_items)
        elif self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor - 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index - 1) % len(self._media_items)
        elif self._active_menu == "home":
            self._focus_index = (self._focus_index - 1) % (len(self._home_focus_targets()) + len(self._modes))

    def _handle_down(self) -> None:
        if self._active_menu == "nav_arrival":
            self._nav_arrival_cursor = (self._nav_arrival_cursor + 1) % 2
        elif self._active_menu == "fault_detail":
            self._cycle_fault_detail(1)
        elif self._active_menu == "nav_waypoints":
            self._nav_cursor = (self._nav_cursor + 1) % max(1, len(self._navigation_menu_items()))
        elif self._active_menu == "nav_actions":
            self._nav_action_cursor = (self._nav_action_cursor + 1) % len(self._navigation_action_items())
        elif self._active_menu == "nav_keyboard":
            self._move_nav_keyboard(1, 0)
        elif self._active_menu == "nav_search_results":
            self._nav_search_cursor = (self._nav_search_cursor + 1) % max(1, len(self._navigation_search_items()))
        elif self._active_menu == "network":
            self._network_cursor = (self._network_cursor + 1) % max(1, len(self._network_menu_items()))
        elif self._active_menu == "network_password":
            self._move_network_password_keyboard(1, 0)
        elif self._active_menu == "settings":
            self._settings_cursor = (self._settings_cursor + 1) % len(self._setting_items)
        elif self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor + 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index + 1) % len(self._media_items)
        elif self._active_menu == "home":
            self._focus_index = (self._focus_index + 1) % (len(self._home_focus_targets()) + len(self._modes))

    def _handle_select(self) -> None:
        if self._active_menu == "nav_arrival":
            if self._nav_arrival_cursor == 0:
                self._navigation.save_arrival_waypoint()
            else:
                self._navigation.dismiss_arrival_prompt()
            self._active_menu = "home"
            return
        if self._active_menu == "home":
            target = self._home_focus_target()
            if target.startswith("MODE:"):
                self._apply_mode_selection(int(target.split(":", 1)[1]))
                return
            if target == "FAULTS":
                if self._visible_faults:
                    self._fault_detail_index = 0
                    self._active_menu = "fault_detail"
                return
            if target == "NAV":
                self._nav_cursor = 0
                self._active_menu = "nav_waypoints"
                return
            if target == "SETTINGS":
                cur = self.state
                gear = (cur.engine.gear or "").strip().upper()
                stopped = cur.engine.speed_mph <= 1.0
                if gear in {"N", "P", "?"} and stopped:
                    self._active_menu = "settings"
            elif target == "MEDIA":
                self._active_menu = "media"
            return
        if self._active_menu == "media":
            self._activate_media_action()
            return
        if self._active_menu == "fault_detail":
            self._cycle_fault_detail(1)
            return
        if self._active_menu == "nav_waypoints":
            self._activate_navigation_menu_item()
            return
        if self._active_menu == "nav_actions":
            self._activate_navigation_action()
            return
        if self._active_menu == "nav_keyboard":
            self._activate_nav_keyboard_key()
            return
        if self._active_menu == "nav_search_results":
            self._activate_navigation_search_result()
            return
        if self._active_menu == "network":
            self._activate_network_menu_item()
            return
        if self._active_menu == "network_password":
            self._activate_network_password_key()
            return
        if self._active_menu == "settings":
            item = self._setting_items[self._settings_cursor]
            if item == "PHONE LINK":
                self._phone_link_enabled = not self._phone_link_enabled
                if self._media_callback:
                    self._media_callback("phone_link", 1 if self._phone_link_enabled else 0)
                self._save_preferences()
            elif item == "FLAME MODE":
                self._flame_mode_manual_enabled = not self._flame_mode_manual_enabled
                self._notify_flame_mode()
                self._save_preferences()
            elif item == "EXPORT LOGS":
                self._export_logs()
            elif item == "INSTALL UPDATE":
                self._install_update()
            elif item == "ONLINE UPDATE":
                self._start_online_update()
            elif item == "SERVICE MODE":
                self._active_menu = "service"
            elif item == "SENSOR CONF":
                self._active_menu = "sensor_confidence"
            elif item == "NETWORK":
                self._network_cursor = 0
                self._network.refresh_async()
                self._active_menu = "network"
            elif item == "NAV MAP":
                self._navigation.set_map_enabled(not self._navigation.map_enabled)
            elif item == "NAV ONLINE":
                self._navigation.set_online_enabled(not self._navigation.online_enabled)
            return

    def _request_air_shot(self) -> None:
        if self._air_shot_callback:
            try:
                self._air_shot_callback()
            except Exception:
                LOGGER.exception("Air Shot request callback failed")

    def _navigation_menu_items(self) -> list[tuple[str, str | None]]:
        items: list[tuple[str, str | None]] = [("SAVE CURRENT LOCATION", None), ("SEARCH ADDRESS", None)]
        if self._navigation.active:
            items.append(("STOP NAVIGATION", None))
        items.extend((waypoint.name, waypoint.waypoint_id) for waypoint in self._navigation.waypoints)
        return items

    @staticmethod
    def _navigation_action_items() -> tuple[str, ...]:
        return ("NAVIGATE", "DELETE", "BACK")

    def _navigation_keyboard_rows(self) -> tuple[tuple[str, ...], ...]:
        action = "SEARCH" if self._nav_keyboard_purpose == "address" else "SAVE"
        return (
            tuple("ABCDEFGH"),
            tuple("IJKLMNOP"),
            tuple("QRSTUVWX"),
            ("Y", "Z", "0", "1", "2", "3", "4", "5"),
            ("6", "7", "8", "9", "-", "SPACE", "DEL", action),
            ("CANCEL",),
        )

    def _activate_navigation_menu_item(self) -> None:
        items = self._navigation_menu_items()
        if not items:
            return
        self._nav_cursor %= len(items)
        label, waypoint_id = items[self._nav_cursor]
        if label == "SAVE CURRENT LOCATION":
            self._nav_keyboard_purpose = "waypoint"
            self._nav_keyboard_text = ""
            self._nav_keyboard_row = 0
            self._nav_keyboard_col = 0
            self._active_menu = "nav_keyboard"
            return
        if label == "SEARCH ADDRESS":
            self._nav_keyboard_purpose = "address"
            self._nav_keyboard_text = ""
            self._nav_keyboard_row = 0
            self._nav_keyboard_col = 0
            self._active_menu = "nav_keyboard"
            return
        if label == "STOP NAVIGATION":
            self._navigation.stop_navigation()
            self._nav_cursor = 0
            return
        if waypoint_id is not None:
            self._nav_selected_waypoint_id = waypoint_id
            self._nav_action_cursor = 0
            self._active_menu = "nav_actions"

    def _activate_navigation_action(self) -> None:
        waypoint_id = self._nav_selected_waypoint_id
        if waypoint_id is None:
            self._active_menu = "nav_waypoints"
            return
        action = self._navigation_action_items()[self._nav_action_cursor % len(self._navigation_action_items())]
        if action == "NAVIGATE":
            self._navigation.start_navigation(waypoint_id)
            self._active_menu = "home"
        elif action == "DELETE":
            self._navigation.delete_waypoint(waypoint_id)
            self._nav_selected_waypoint_id = None
            self._nav_cursor = 0
            self._active_menu = "nav_waypoints"
        else:
            self._active_menu = "nav_waypoints"

    def _move_nav_keyboard(self, row_delta: int, col_delta: int) -> None:
        rows = self._navigation_keyboard_rows()
        self._nav_keyboard_row = (self._nav_keyboard_row + row_delta) % len(rows)
        row = rows[self._nav_keyboard_row]
        self._nav_keyboard_col = (self._nav_keyboard_col + col_delta) % len(row)

    def _activate_nav_keyboard_key(self) -> None:
        rows = self._navigation_keyboard_rows()
        row = rows[self._nav_keyboard_row]
        key = row[self._nav_keyboard_col % len(row)]
        if key == "SPACE":
            if self._nav_keyboard_text and len(self._nav_keyboard_text) < (42 if self._nav_keyboard_purpose == "address" else 20):
                self._nav_keyboard_text += " "
        elif key == "DEL":
            self._nav_keyboard_text = self._nav_keyboard_text[:-1]
        elif key in {"SAVE", "SEARCH"}:
            if self._nav_keyboard_purpose == "address":
                self._navigation.request_address_search(self._nav_keyboard_text)
                self._nav_search_cursor = 0
                self._active_menu = "nav_search_results"
            elif self._navigation.add_current_waypoint(self._nav_keyboard_text) is not None:
                self._active_menu = "nav_waypoints"
                self._nav_cursor = max(0, len(self._navigation_menu_items()) - 1)
        elif key == "CANCEL":
            self._active_menu = "nav_waypoints"
        elif len(self._nav_keyboard_text) < (42 if self._nav_keyboard_purpose == "address" else 20):
            self._nav_keyboard_text += key

    def _navigation_search_items(self) -> list[tuple[str, str | None]]:
        items = [(row.display_name, row.result_id) for row in self._navigation.search_results]
        items.append(("BACK", None))
        return items

    def _activate_navigation_search_result(self) -> None:
        items = self._navigation_search_items()
        self._nav_search_cursor %= len(items)
        label, result_id = items[self._nav_search_cursor]
        if label == "BACK" or result_id is None:
            self._active_menu = "nav_waypoints"
            return
        self._navigation.start_navigation_to_search_result(result_id)
        self._active_menu = "home"

    def _network_menu_items(self) -> list[tuple[str, str | None]]:
        toggle = "WIFI RADIO ON" if self._network.wifi_enabled else "WIFI RADIO OFF"
        items: list[tuple[str, str | None]] = [(toggle, "toggle"), ("RESCAN NETWORKS", "rescan")]
        items.extend((network.ssid, network.ssid) for network in self._network.networks)
        return items

    def _activate_network_menu_item(self) -> None:
        items = self._network_menu_items()
        self._network_cursor %= max(1, len(items))
        _label, action = items[self._network_cursor]
        if action == "toggle":
            self._network.set_wifi_enabled_async(not self._network.wifi_enabled)
        elif action == "rescan":
            self._network.refresh_async()
        elif action:
            self._network_selected_ssid = action
            self._network_password_text = ""
            self._network_password_uppercase = True
            self._network_password_row = 0
            self._network_password_col = 0
            self._active_menu = "network_password"

    def _network_password_keyboard_rows(self) -> tuple[tuple[str, ...], ...]:
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if self._network_password_uppercase else "abcdefghijklmnopqrstuvwxyz"
        return (
            tuple(letters[0:8]),
            tuple(letters[8:16]),
            tuple(letters[16:24]),
            (letters[24], letters[25], "0", "1", "2", "3", "4", "5"),
            ("6", "7", "8", "9", "-", "_", "@", "."),
            ("!", "#", "SPACE", "CASE", "DEL", "CONNECT"),
            ("CANCEL",),
        )

    def _move_network_password_keyboard(self, row_delta: int, col_delta: int) -> None:
        rows = self._network_password_keyboard_rows()
        self._network_password_row = (self._network_password_row + row_delta) % len(rows)
        row = rows[self._network_password_row]
        self._network_password_col = (self._network_password_col + col_delta) % len(row)

    def _activate_network_password_key(self) -> None:
        rows = self._network_password_keyboard_rows()
        row = rows[self._network_password_row]
        key = row[self._network_password_col % len(row)]
        if key == "SPACE":
            if len(self._network_password_text) < 63:
                self._network_password_text += " "
        elif key == "CASE":
            self._network_password_uppercase = not self._network_password_uppercase
        elif key == "DEL":
            self._network_password_text = self._network_password_text[:-1]
        elif key == "CONNECT":
            self._network.connect_async(self._network_selected_ssid, self._network_password_text)
            self._active_menu = "network"
        elif key == "CANCEL":
            self._active_menu = "network"
        elif len(self._network_password_text) < 63:
            self._network_password_text += key

    def _handle_back(self) -> None:
        if self._active_menu != "home":
            if self._active_menu == "nav_arrival":
                self._navigation.dismiss_arrival_prompt()
                self._active_menu = "home"
                return
            if self._active_menu == "media" and self._media_device_menu_open:
                self._media_device_menu_open = False
                return
            if self._active_menu == "nav_actions":
                self._active_menu = "nav_waypoints"
                return
            if self._active_menu == "nav_keyboard":
                if self._nav_keyboard_text:
                    self._nav_keyboard_text = self._nav_keyboard_text[:-1]
                else:
                    self._active_menu = "nav_waypoints"
                return
            if self._active_menu == "nav_search_results":
                self._active_menu = "nav_waypoints"
                return
            if self._active_menu == "network_password":
                if self._network_password_text:
                    self._network_password_text = self._network_password_text[:-1]
                else:
                    self._active_menu = "network"
                return
            self._active_menu = "home"

    def _activate_media_action(self) -> None:
        action = self._media_items[self._media_index]
        if action == "PREV" and self._media_callback:
            self._media_callback("prev", 1)
        elif action == "PLAY" and self._media_callback:
            self._media_callback("play_pause", 1)
        elif action == "NEXT" and self._media_callback:
            self._media_callback("next", 1)
        elif action == "DEVICES":
            if self._media_device_menu_open and self._available_devices and self._media_callback:
                mac, _name = self._available_devices[self._media_device_cursor]
                self._media_callback(f"connect:{mac}", 1)
                self._media_device_menu_open = False
            else:
                self._media_device_menu_open = True

    def _export_logs(self) -> None:
        if self._log_export_callback is None:
            self._log_export_status = "UNAVAILABLE"
            return
        try:
            self._log_export_status = self._log_export_callback()
        except Exception as exc:
            LOGGER.exception("Log export failed")
            self._log_export_status = f"FAILED {exc.__class__.__name__}"

    def _install_update(self) -> None:
        if self._update_install_callback is None:
            self._update_install_status = "UNAVAILABLE"
            return
        try:
            with self.state_lock:
                snapshot = self.state
            self._update_install_status = self._update_install_callback(snapshot)
        except Exception as exc:
            LOGGER.exception("Update install failed")
            self._update_install_status = f"FAILED {exc.__class__.__name__}"

    def _update_online_progress(self, stage: str, current: int, total: int) -> None:
        pct = (current / total) if total > 0 else 0.0
        if stage != "DOWNLOADING":
            pct = 0.0
        with self._online_update_lock:
            self._online_update_progress = max(0.0, min(1.0, pct))
            self._online_update_status = f"{stage} {int(pct * 100):02d}%" if stage == "DOWNLOADING" else stage

    def _start_online_update(self) -> None:
        if self._online_update_callback is None:
            self._online_update_status = "UNAVAILABLE"
            return
        with self._online_update_lock:
            if self._online_update_busy:
                return
            self._online_update_busy = True
            self._online_update_progress = 0.0
            self._online_update_status = "CHECKING"
        with self.state_lock:
            snapshot = self.state

        def worker() -> None:
            try:
                result = self._online_update_callback(snapshot, self._update_online_progress)
            except Exception as exc:
                LOGGER.exception("Online update failed")
                result = f"FAILED {exc.__class__.__name__}"
            with self._online_update_lock:
                self._online_update_status = result
                self._online_update_progress = 1.0 if "OK" in result or "UP TO DATE" in result else 0.0
                self._online_update_busy = False

        threading.Thread(target=worker, name="online-update", daemon=True).start()

    @staticmethod
    def _wrap_words(text: str, max_width: int, font_size: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if font(font_size).size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            while font(font_size).size(current)[0] > max_width and len(current) > 1:
                split_at = max(1, len(current) - 1)
                while split_at > 1 and font(font_size).size(current[:split_at])[0] > max_width:
                    split_at -= 1
                lines.append(current[:split_at])
                current = current[split_at:]
        if current:
            lines.append(current)
        return lines or [""]

    def _render_fault_detail_overlay(self, state: StateSnapshot) -> None:
        bg, bright, glow, fault_color = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(920, sw - 80), min(540, sh - 70))
        panel.center = (sw // 2, sh // 2)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((12, 8, 0, 238))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, fault_color, panel, width=2, border_radius=8)

        faults = self._active_faults_for_detail(state)
        if not faults:
            title = font(22, bold=True).render("EVA FAULT DETAIL", True, bright)
            self.screen.blit(title, (panel.x + 18, panel.y + 14))
            msg = font(18, bold=True).render("NO ACTIVE FAULT", True, glow)
            self.screen.blit(msg, (panel.x + 18, panel.y + 58))
            return

        self._fault_detail_index %= len(faults)
        name = faults[self._fault_detail_index]
        status = engine_status(state)
        title = f"EVA FAULT DETAIL {self._fault_detail_index + 1}/{len(faults)}"
        self.screen.blit(font(22, bold=True).render(title, True, bright), (panel.x + 18, panel.y + 12))
        self.screen.blit(font(24, bold=True).render(name, True, fault_color), (panel.x + 18, panel.y + 48))

        text_x = panel.x + 18
        grid_x = panel.x + int(panel.width * 0.62)
        text_max_w = max(220, grid_x - text_x - 26)
        y = panel.y + 88
        for heading, body in (
            ("WHY", fault_reason(name, state)),
            ("ACTION", fault_action(name, state)),
        ):
            self.screen.blit(font(15, bold=True).render(heading, True, bright), (text_x, y))
            y += 18
            for line in self._wrap_words(body, text_max_w - 10, 14):
                if y > panel.bottom - 42:
                    break
                self.screen.blit(font(14).render(line, True, glow), (text_x + 10, y))
                y += 17
            y += 6

        rows = [
            ("RPM", f"{status['rpm']}"),
            ("SPD/GEAR", f"{status['speed_mph']} mph / {status['gear']}"),
            ("MODE/FUEL", f"{status['mode']} / {status['fuel_type']} E{status['ethanol_content_pct']}"),
            ("BOOST", f"{status['boost_psi']} / {status['target_boost_psi']} psi"),
            ("BOOST L/R", f"{status['boost_left_psi']} / {status['boost_right_psi']} psi"),
            ("WG/TPS", f"{status['wastegate_duty_pct']}% / {status['throttle_pct']}%"),
            ("AFR", f"{status['afr_left']} / {status['afr_right']}"),
            ("KNOCK", f"{status['knock_events']}"),
            ("OIL", f"{status['oil_pressure_psi']} psi / {status['oil_temp_f']} F"),
            ("CLT/IAT", f"{status['coolant_temp_f']} / {status['intake_temp_f']} F"),
            ("EGT/BATT", f"{status['exhaust_temp_f']} F / {status['battery_voltage']} V"),
            ("EGT L/R", f"{status['exhaust_left_temp_f']} / {status['exhaust_right_temp_f']} F"),
            ("WMI", f"{status['wmi_actual_flow_cc_min']}/{status['wmi_commanded_flow_cc_min']} ccm {status['wmi_tank_level_pct']}%"),
            ("TRAC", f"{status['traction_slip_pct']}% slip / {status['traction_torque_cut_pct']}% cut"),
        ]
        grid_y = panel.y + 88
        label_w = max(70, int(panel.width * 0.12))
        value_max_w = max(90, panel.right - grid_x - label_w - 24)
        row_h = max(18, min(25, (panel.bottom - grid_y - 42) // len(rows)))
        self.screen.blit(font(15, bold=True).render("CURRENT VALUES", True, bright), (grid_x, panel.y + 64))
        for idx, (label, value) in enumerate(rows):
            row_y = grid_y + idx * row_h
            self.screen.blit(font(13, bold=True).render(label, True, glow), (grid_x, row_y))
            value_size = fit_font_size(value, value_max_w, row_h, start_size=14, bold=True)
            self.screen.blit(font(value_size, bold=True).render(value, True, bright), (grid_x + label_w, row_y))

        hint = "ARROWS: NEXT FAULT  |  ENTER: NEXT  |  ESC: BACK"
        hint_surface = font(12, bold=True).render(hint, True, glow)
        self.screen.blit(hint_surface, (panel.right - hint_surface.get_width() - 18, panel.bottom - 24))

    def _render_navigation_waypoint_overlay(self) -> None:
        _bg, bright, glow, fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(720, sw - 80), min(500, sh - 64))
        panel.center = (sw // 2, sh // 2)
        self._draw_navigation_panel_shell(panel, "NAVIGATION / WAYPOINTS")
        location = self._navigation.current_location
        gps_text = f"GPS {location[0]:.5f}, {location[1]:.5f}" if location else "GPS LOCK REQUIRED"
        self.screen.blit(font(12, bold=True).render(gps_text, True, glow if location else fault), (panel.x + 18, panel.y + 42))
        items = self._navigation_menu_items()
        self._nav_cursor %= max(1, len(items))
        row_h = 30
        start_y = panel.y + 76
        visible_rows = max(1, (panel.height - 116) // row_h)
        first = min(max(0, self._nav_cursor - visible_rows // 2), max(0, len(items) - visible_rows))
        for row, (label, waypoint_id) in enumerate(items[first:first + visible_rows]):
            idx = first + row
            active = idx == self._nav_cursor
            color = bright if active else glow
            prefix = ">" if active else " "
            suffix = ""
            if waypoint_id == self._navigation.active_waypoint_id:
                suffix = "  [ACTIVE]"
            text = f"{prefix} {label}{suffix}"
            self.screen.blit(font(15, bold=active).render(text[:56], True, color), (panel.x + 18, start_y + row * row_h))
            if active:
                pygame.draw.line(self.screen, color, (panel.x + 18, start_y + row * row_h + 23), (panel.right - 18, start_y + row * row_h + 23), 1)
        status = self._navigation.route_status
        status_surface = font(12, bold=True).render(status[:48], True, bright)
        self.screen.blit(status_surface, (panel.x + 18, panel.bottom - 50))
        hint = font(12).render("ARROWS: MOVE  |  ENTER: SELECT  |  ESC: BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 28))

    def _render_navigation_action_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(520, sw - 80), min(250, sh - 80))
        panel.center = (sw // 2, sh // 2)
        waypoint = next((row for row in self._navigation.waypoints if row.waypoint_id == self._nav_selected_waypoint_id), None)
        self._draw_navigation_panel_shell(panel, "WAYPOINT ACTION")
        title = waypoint.name if waypoint else "WAYPOINT MISSING"
        self.screen.blit(font(18, bold=True).render(title[:28], True, bright), (panel.x + 18, panel.y + 50))
        for idx, action in enumerate(self._navigation_action_items()):
            active = idx == self._nav_action_cursor
            color = bright if active else glow
            prefix = ">" if active else " "
            self.screen.blit(font(15, bold=active).render(f"{prefix} {action}", True, color), (panel.x + 20, panel.y + 92 + idx * 30))
        hint = font(12).render("ARROWS: MOVE  |  ENTER: SELECT  |  ESC: BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 24))

    def _render_navigation_keyboard_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(760, sw - 72), min(520, sh - 56))
        panel.center = (sw // 2, sh // 2)
        title = "SEARCH ADDRESS" if self._nav_keyboard_purpose == "address" else "NAME WAYPOINT"
        self._draw_navigation_panel_shell(panel, title)
        entry_rect = pygame.Rect(panel.x + 18, panel.y + 50, panel.width - 36, 42)
        pygame.draw.rect(self.screen, (5, 4, 0), entry_rect)
        pygame.draw.rect(self.screen, glow, entry_rect, 1)
        entry_text = self._nav_keyboard_text or "_"
        entry_size = fit_font_size(entry_text, entry_rect.width - 20, entry_rect.height - 12, start_size=20, bold=True)
        self.screen.blit(font(entry_size, bold=True).render(entry_text, True, bright), (entry_rect.x + 10, entry_rect.y + 8))
        rows = self._navigation_keyboard_rows()
        top = panel.y + 104
        gap = 6
        row_h = 34
        for row_idx, keys in enumerate(rows):
            key_w = max(62, (panel.width - 36 - gap * (len(keys) - 1)) // len(keys))
            total_w = key_w * len(keys) + gap * (len(keys) - 1)
            x = panel.centerx - total_w // 2
            y = top + row_idx * (row_h + gap)
            for col_idx, key in enumerate(keys):
                active = row_idx == self._nav_keyboard_row and col_idx == self._nav_keyboard_col % len(keys)
                key_rect = pygame.Rect(x + col_idx * (key_w + gap), y, key_w, row_h)
                pygame.draw.rect(self.screen, (22, 14, 0), key_rect)
                pygame.draw.rect(self.screen, bright if active else glow, key_rect, 2 if active else 1)
                label_size = fit_font_size(key, key_rect.width - 10, key_rect.height - 8, start_size=15, bold=active)
                label = font(label_size, bold=active).render(key, True, bright if active else glow)
                self.screen.blit(label, (key_rect.centerx - label.get_width() // 2, key_rect.centery - label.get_height() // 2))
        hint = font(12).render("ARROWS: MOVE  |  ENTER: TYPE  |  ESC: DELETE/BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 22))

    def _render_navigation_search_results_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(920, sw - 72), min(500, sh - 64))
        panel.center = (sw // 2, sh // 2)
        self._draw_navigation_panel_shell(panel, "ADDRESS SEARCH")
        self.screen.blit(font(13, bold=True).render(self._navigation.search_status[:56], True, glow), (panel.x + 18, panel.y + 46))
        items = self._navigation_search_items()
        self._nav_search_cursor %= len(items)
        start_y = panel.y + 84
        row_h = 54
        for idx, (label, _result_id) in enumerate(items[:7]):
            active = idx == self._nav_search_cursor
            color = bright if active else glow
            row_y = start_y + idx * row_h
            clipped = label
            while font(14, bold=active).size(clipped)[0] > panel.width - 62 and len(clipped) > 4:
                clipped = f"{clipped[:-4]}..."
            self.screen.blit(font(14, bold=active).render(f"{'>' if active else ' '} {clipped}", True, color), (panel.x + 18, row_y))
            if active:
                pygame.draw.line(self.screen, color, (panel.x + 18, row_y + 22), (panel.right - 18, row_y + 22), 1)
        hint = font(12).render("ARROWS: MOVE  |  ENTER: ROUTE  |  ESC: BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 24))

    def _render_navigation_arrival_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(620, sw - 72), min(260, sh - 72))
        panel.center = (sw // 2, sh // 2)
        self._draw_navigation_panel_shell(panel, "DESTINATION REACHED")
        destination = self._navigation.arrival_prompt_destination
        name = destination.name if destination else "CURRENT LOCATION"
        self.screen.blit(font(17, bold=True).render(name[:32], True, bright), (panel.x + 18, panel.y + 62))
        self.screen.blit(font(15, bold=True).render("SAVE THIS LOCATION AS A WAYPOINT?", True, glow), (panel.x + 18, panel.y + 102))
        choices = ("YES", "NO")
        button_w = 128
        gap = 18
        left = panel.centerx - (button_w * 2 + gap) // 2
        for index, label in enumerate(choices):
            active = index == self._nav_arrival_cursor
            rect = pygame.Rect(left + index * (button_w + gap), panel.y + 150, button_w, 42)
            pygame.draw.rect(self.screen, (22, 14, 0), rect)
            pygame.draw.rect(self.screen, bright if active else glow, rect, 2 if active else 1)
            text = font(16, bold=active).render(label, True, bright if active else glow)
            self.screen.blit(text, (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2))
        hint = font(12).render("ARROWS: CHOOSE  |  ENTER: SELECT  |  ESC: DISMISS", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 22))

    def _render_network_overlay(self) -> None:
        _bg, bright, glow, fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(760, sw - 72), min(560, sh - 56))
        panel.center = (sw // 2, sh // 2)
        self._draw_navigation_panel_shell(panel, "NETWORK SETTINGS")
        status_color = glow if self._network.available else fault
        status = f"{self._network.status}  {self._network.active_ssid}".strip()
        self.screen.blit(font(13, bold=True).render(status[:64], True, status_color), (panel.x + 18, panel.y + 44))
        items = self._network_menu_items()
        self._network_cursor %= max(1, len(items))
        row_h = 30
        start_y = panel.y + 78
        visible_rows = max(1, (panel.height - 120) // row_h)
        first = min(max(0, self._network_cursor - visible_rows // 2), max(0, len(items) - visible_rows))
        networks = {network.ssid: network for network in self._network.networks}
        for row, (label, action) in enumerate(items[first:first + visible_rows]):
            idx = first + row
            active = idx == self._network_cursor
            color = bright if active else glow
            suffix = ""
            network = networks.get(action or "")
            if network:
                suffix = f"  {network.signal:>3}%  {network.security[:18]}"
                if network.active:
                    suffix += "  [ACTIVE]"
            self.screen.blit(font(14, bold=active).render(f"{'>' if active else ' '} {label[:34]}{suffix}", True, color), (panel.x + 18, start_y + row * row_h))
            if active:
                pygame.draw.line(self.screen, color, (panel.x + 18, start_y + row * row_h + 22), (panel.right - 18, start_y + row * row_h + 22), 1)
        hint = font(12).render("ARROWS: MOVE  |  ENTER: SELECT  |  ESC: BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 22))

    def _render_network_password_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(840, sw - 72), min(620, sh - 48))
        panel.center = (sw // 2, sh // 2)
        self._draw_navigation_panel_shell(panel, f"CONNECT / {self._network_selected_ssid[:36]}")
        entry_rect = pygame.Rect(panel.x + 18, panel.y + 50, panel.width - 36, 42)
        pygame.draw.rect(self.screen, (5, 4, 0), entry_rect)
        pygame.draw.rect(self.screen, glow, entry_rect, 1)
        hidden = "*" * len(self._network_password_text) or "BLANK USES SAVED OR OPEN NETWORK"
        hidden_size = fit_font_size(hidden, entry_rect.width - 20, entry_rect.height - 12, start_size=18, bold=True)
        self.screen.blit(font(hidden_size, bold=True).render(hidden, True, bright), (entry_rect.x + 10, entry_rect.y + 9))
        rows = self._network_password_keyboard_rows()
        top = panel.y + 104
        gap = 6
        row_h = 34
        for row_idx, keys in enumerate(rows):
            key_w = max(60, (panel.width - 36 - gap * (len(keys) - 1)) // len(keys))
            total_w = key_w * len(keys) + gap * (len(keys) - 1)
            x = panel.centerx - total_w // 2
            y = top + row_idx * (row_h + gap)
            for col_idx, key in enumerate(keys):
                active = row_idx == self._network_password_row and col_idx == self._network_password_col % len(keys)
                key_rect = pygame.Rect(x + col_idx * (key_w + gap), y, key_w, row_h)
                pygame.draw.rect(self.screen, (22, 14, 0), key_rect)
                pygame.draw.rect(self.screen, bright if active else glow, key_rect, 2 if active else 1)
                label_size = fit_font_size(key, key_rect.width - 10, key_rect.height - 8, start_size=14, bold=active)
                label = font(label_size, bold=active).render(key, True, bright if active else glow)
                self.screen.blit(label, (key_rect.centerx - label.get_width() // 2, key_rect.centery - label.get_height() // 2))
        hint = font(12).render("ARROWS: MOVE  |  ENTER: TYPE  |  ESC: DELETE/BACK", True, glow)
        self.screen.blit(hint, (panel.right - hint.get_width() - 18, panel.bottom - 22))

    def _draw_navigation_panel_shell(self, panel: pygame.Rect, title: str) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        overlay = pygame.Surface(panel.size, pygame.SRCALPHA)
        overlay.fill((8, 6, 0, 242))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, glow, panel, width=2, border_radius=8)
        self.screen.blit(font(20, bold=True).render(title, True, bright), (panel.x + 16, panel.y + 12))

    def _render_settings_overlay(self) -> None:
        bg, bright, glow, _fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(760, sw - 80), min(520, sh - 80))
        panel.center = (sw // 2, sh // 2)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((12, 8, 0, 230))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, glow, panel, width=2, border_radius=8)
        title = font(20, bold=True).render("SETTINGS", True, bright)
        self.screen.blit(title, (panel.x + 16, panel.y + 10))
        row_h = 34
        first_row_y = panel.y + 52
        footer_h = 42
        visible_rows = max(1, (panel.bottom - footer_h - first_row_y) // row_h)
        if len(self._setting_items) <= visible_rows:
            first_idx = 0
        else:
            first_idx = min(
                max(0, self._settings_cursor - visible_rows // 2),
                len(self._setting_items) - visible_rows,
            )
        visible_items = self._setting_items[first_idx:first_idx + visible_rows]
        if first_idx > 0:
            self.screen.blit(font(11, bold=True).render("MORE", True, glow), (panel.right - 54, first_row_y - 20))
        if first_idx + visible_rows < len(self._setting_items):
            self.screen.blit(font(11, bold=True).render("MORE", True, glow), (panel.right - 54, panel.bottom - footer_h + 4))
        for row, item in enumerate(visible_items):
            idx = first_idx + row
            active = idx == self._settings_cursor
            color = bright if active else glow
            value = self._settings_value(item)
            text = font(17, bold=active).render(f"{item:<12} {value}", True, color)
            row_y = first_row_y + row * row_h
            self.screen.blit(text, (panel.x + 16, row_y))
            if active:
                pygame.draw.line(self.screen, bright, (panel.x + 14, row_y + 24), (panel.right - 14, row_y + 24), 1)
            if item == "ONLINE UPDATE" and (self._online_update_busy or self._online_update_progress > 0):
                bar = pygame.Rect(panel.x + 300, row_y + 21, panel.width - 330, 7)
                pygame.draw.rect(self.screen, (45, 30, 0), bar, border_radius=3)
                fill = pygame.Rect(bar.x, bar.y, int(bar.width * max(0.0, min(1.0, self._online_update_progress))), bar.height)
                pygame.draw.rect(self.screen, bright, fill, border_radius=3)
            if item == "MODE" and active:
                self._render_mode_picker(panel, row_y + 28)
        y = panel.bottom - 26
        dev_title = font(12, bold=True).render("BT DEVICES", True, glow)
        self.screen.blit(dev_title, (panel.x + 16, y))
        if self._available_devices:
            devs = ", ".join(self._available_devices[:3])
            self.screen.blit(font(12).render(devs[:44], True, bright), (panel.x + 100, y))

    def _draw_service_group(self, title: str, rows: list[tuple[str, str, bool | None]], rect: pygame.Rect) -> None:
        _bg, bright, glow, fault = self._theme_colors()

        def fitted_surface(text: str, max_w: int, max_h: int, *, start_size: int, color: tuple[int, int, int], bold: bool = False) -> pygame.Surface:
            size = fit_font_size(text, max_w, max_h, start_size=start_size, bold=bold)
            clipped = text
            while font(size, bold=bold).size(clipped)[0] > max_w and len(clipped) > 4:
                clipped = f"{clipped[:-4]}..."
            return font(size, bold=bold).render(clipped, True, color)

        pygame.draw.rect(self.screen, (28, 18, 0), rect, width=1, border_radius=5)
        self.screen.blit(font(13, bold=True).render(title, True, bright), (rect.x + 10, rect.y + 8))
        if not rows:
            self.screen.blit(font(12).render("NO DATA", True, glow), (rect.x + 10, rect.y + 34))
            return
        y = rect.y + 30
        row_h = 16
        max_rows = max(1, (rect.bottom - y - 6) // row_h)
        for label, value, active in rows[:max_rows]:
            color = fault if active is False else (bright if active else glow)
            value_w = max(34, min(rect.width // 2, font(12, bold=bool(active)).size(value)[0]))
            value_surface = fitted_surface(value, value_w, row_h, start_size=12, color=color, bold=bool(active))
            value_x = rect.right - value_surface.get_width() - 10
            label_max_w = max(48, value_x - rect.x - 18)
            label_surface = fitted_surface(label, label_max_w, row_h, start_size=12, color=glow, bold=bool(active))
            self.screen.blit(label_surface, (rect.x + 10, y))
            self.screen.blit(value_surface, (value_x, y))
            y += row_h

    def _draw_can_frame_group(self, title: str, frames, rect: pygame.Rect, now) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        pygame.draw.rect(self.screen, (28, 18, 0), rect, width=1, border_radius=5)
        self.screen.blit(font(13, bold=True).render(title, True, bright), (rect.x + 10, rect.y + 8))
        if not frames:
            self.screen.blit(font(12).render("NO DATA", True, glow), (rect.x + 10, rect.y + 34))
            return
        y = rect.y + 30
        row_h = 16
        max_rows = max(1, (rect.bottom - y - 6) // row_h)
        id_x = rect.x + 10
        name_x = rect.x + 92
        age_w = 58
        age_x = rect.right - age_w - 10
        data_x = rect.x + int(rect.width * 0.54)
        data_w = max(48, age_x - data_x - 8)
        name_w = max(80, data_x - name_x - 8)

        for frame in frames[:max_rows]:
            age_ms = max(0, int((now - frame.timestamp).total_seconds() * 1000))
            id_text = f"{frame.direction:<2} {frame.arbitration_id:03X}"
            name = frame.name.rsplit(".", 1)[-1]
            name_size = fit_font_size(name, name_w, row_h, start_size=12)
            data_size = fit_font_size(frame.data_hex, data_w, row_h, start_size=12)
            age_text = f"{age_ms:>4}ms" if age_ms < 10000 else "9999ms"
            self.screen.blit(font(12, bold=True).render(id_text, True, bright), (id_x, y))
            self.screen.blit(font(name_size).render(name, True, glow), (name_x, y))
            self.screen.blit(font(data_size).render(frame.data_hex, True, glow), (data_x, y))
            self.screen.blit(font(12).render(age_text, True, glow), (age_x, y))
            y += row_h

    def _render_service_overlay(self, state: StateSnapshot) -> None:
        bg, bright, glow, fault = self._theme_colors()
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(1120, sw - 56), min(610, sh - 48))
        panel.center = (sw // 2, sh // 2)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((8, 6, 0, 238))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, glow, panel, width=2, border_radius=8)
        self.screen.blit(font(20, bold=True).render("SERVICE MODE", True, bright), (panel.x + 16, panel.y + 10))
        subtitle = "LIVE CAN / SENSORS / PINS / RELAYS / FIRMWARE"
        self.screen.blit(font(12, bold=True).render(subtitle, True, glow), (panel.x + 210, panel.y + 16))

        content_top = panel.y + 44
        content_bottom = panel.bottom - 32
        gap = 10
        left_w = max(300, int(panel.width * 0.47))
        left = pygame.Rect(panel.x + 14, content_top, left_w, content_bottom - content_top)
        right_x = left.right + gap
        right_w = panel.right - right_x - 14

        now = state.environment.time
        self._draw_can_frame_group("RAW CAN FRAMES", state.service.recent_can_frames, left, now)

        sensor_rows = [(reading.label, reading.value, None) for reading in state.service.sensor_voltages]
        sensor_rows.extend([
            ("Battery", f"{state.temps.battery_voltage:.2f} V", state.temps.battery_voltage >= 11.8 if state.temps.battery_voltage >= 0 else None),
            ("Oil pressure", f"{state.temps.oil_pressure_psi:.1f} psi", state.temps.oil_pressure_psi >= 12.0 if state.engine.rpm > 1800 else None),
            ("Coolant", f"{state.temps.coolant_temp_f:.1f} F", state.temps.coolant_temp_f < 230 if state.temps.coolant_temp_f >= 0 else None),
            ("IAT", f"{state.temps.intake_temp_f:.1f} F", state.temps.intake_temp_f < 180 if state.temps.intake_temp_f > 0 else None),
            ("EGT", f"{state.temps.exhaust_temp_f:.1f} F", state.temps.exhaust_temp_f < 1700 if state.temps.exhaust_temp_f > 0 else None),
            ("Flex fuel", f"{state.environment.ethanol_content_pct:.0f}%", state.environment.ethanol_content_pct >= 0 if state.environment.ethanol_content_pct >= 0 else None),
        ])

        pin_rows = [(flag.label, "HIGH" if flag.active else "LOW", True if flag.active else None) for flag in state.service.pin_states]
        relay_rows = [(flag.label, "ON" if flag.active else "OFF", True if flag.active else None) for flag in state.service.relay_states]
        firmware_rows = [(reading.label, reading.value, None) for reading in state.service.firmware_versions]
        firmware_rows.extend(
            [
                (
                    "Limp",
                    f"ACTIVE: {state.system.limp_mode_reason or 'REQUESTED'}"
                    if state.system.limp_mode_active
                    else "OFF",
                    False if state.system.limp_mode_active else None,
                ),
                ("Mode", state.environment.mode, None),
                (
                    "Fuel",
                    f"{state.environment.fuel_type} E{state.environment.ethanol_content_pct:.0f}"
                    if state.environment.ethanol_content_pct >= 0
                    else state.environment.fuel_type,
                    None,
                ),
                ("Traction", state.traction.intervention_level or "UNKNOWN", None),
                ("Flame", "ON" if state.environment.flame_mode_enabled else "OFF", True if state.environment.flame_mode_enabled else None),
                ("Rev limit", state.environment.rev_limiter_strategy, None),
            ]
        )

        group_h = max(96, (content_bottom - content_top - gap * 2) // 3)
        top_right = pygame.Rect(right_x, content_top, right_w, group_h)
        mid_right = pygame.Rect(right_x, top_right.bottom + gap, right_w, group_h)
        bottom_right = pygame.Rect(right_x, mid_right.bottom + gap, right_w, content_bottom - mid_right.bottom - gap)
        split = max(150, (mid_right.width - gap) // 2)
        pin_rect = pygame.Rect(mid_right.x, mid_right.y, split, mid_right.height)
        relay_rect = pygame.Rect(pin_rect.right + gap, mid_right.y, mid_right.right - pin_rect.right - gap, mid_right.height)

        self._draw_service_group("SENSOR VALUES", sensor_rows, top_right)
        self._draw_service_group("PIN STATES", pin_rows, pin_rect)
        self._draw_service_group("RELAY STATES", relay_rows, relay_rect)
        self._draw_service_group("FIRMWARE / CONTROL", firmware_rows, bottom_right)

        hint = "ESC: BACK"
        hint_surface = font(12, bold=True).render(hint, True, glow)
        self.screen.blit(hint_surface, (panel.right - hint_surface.get_width() - 16, panel.bottom - 22))

    def _sensor_confidence_rows(self, state: StateSnapshot) -> list[tuple[str, str, str]]:
        ecu_can_age_s = self._ecu_can_age_s()
        controller_can_age_s = self._controller_can_age_s()

        rows: list[tuple[str, str, str]] = []

        def add(name: str, value: str, status: str) -> None:
            rows.append((name, value, status))

        add("ECU CAN", f"{ecu_can_age_s:.1f}s", "OK" if ecu_can_age_s <= 0.5 else ("WARN" if ecu_can_age_s <= 1.5 else "ERR"))
        add("Control CAN", f"{controller_can_age_s:.1f}s", "OK" if controller_can_age_s <= 0.5 else ("WARN" if controller_can_age_s <= 1.5 else "ERR"))
        add("RPM", f"{state.engine.rpm}", "OK" if 0 <= state.engine.rpm <= 16000 else "ERR")
        add("TPS", f"{state.engine.throttle_pct:.0f}%", "OK" if 0 <= state.engine.throttle_pct <= 100 else "ERR")
        add("Boost/MAP", f"{state.engine.boost_psi:.1f} psi", "OK" if -2.0 <= state.engine.boost_psi <= 45.0 else "ERR")
        add("Fuel level", f"{state.environment.fuel_level_pct:.0f}%", "OK" if state.environment.fuel_level_pct >= 10 else ("WARN" if state.environment.fuel_level_pct >= 5 else "ERR"))
        add("Flex fuel", f"E{state.environment.ethanol_content_pct:.0f}", "OK" if 0 <= state.environment.ethanol_content_pct <= 100 else "WARN")
        add("Oil pressure", f"{state.temps.oil_pressure_psi:.1f} psi", "OK" if state.temps.oil_pressure_psi >= (12 if state.engine.rpm > 1800 else 3) else ("WARN" if state.temps.oil_pressure_psi >= 5 else "ERR"))
        add("Oil temp", f"{state.temps.oil_temp_f:.0f}F", "OK" if 50 <= state.temps.oil_temp_f <= 280 else ("WARN" if state.temps.oil_temp_f >= 0 else "ERR"))
        add("Coolant", f"{state.temps.coolant_temp_f:.0f}F", "OK" if 50 <= state.temps.coolant_temp_f <= 225 else ("WARN" if state.temps.coolant_temp_f <= 235 and state.temps.coolant_temp_f >= 0 else "ERR"))
        add("IAT", f"{state.temps.intake_temp_f:.0f}F", "OK" if 20 <= state.temps.intake_temp_f <= 130 else ("WARN" if state.temps.intake_temp_f <= 150 else "ERR"))
        add("EGT", f"{state.temps.exhaust_temp_f:.0f}F", "OK" if 0 <= state.temps.exhaust_temp_f <= 1500 else ("WARN" if state.temps.exhaust_temp_f <= 1650 else "ERR"))
        add("Battery", f"{state.temps.battery_voltage:.2f}V", "OK" if 13.0 <= state.temps.battery_voltage <= 14.8 else ("WARN" if 11.8 <= state.temps.battery_voltage <= 15.2 else "ERR"))
        add("Wheel speed", f"{state.engine.speed_mph:.1f} mph", "OK" if state.engine.speed_mph >= 0 and not state.traction.sensor_fault else "ERR")
        add("Gear", state.engine.gear, "OK" if state.engine.gear in {"N", "1", "2", "3", "4", "5", "6"} else "WARN")
        add("WMI tank", f"{state.wmi.tank_level_pct:.0f}%", "OK" if state.wmi.tank_level_pct >= 20 else ("WARN" if state.wmi.tank_level_pct >= 3 else "ERR"))
        wmi_status = "OK"
        if state.wmi.fault_active:
            wmi_status = "ERR"
        elif state.wmi.commanded_flow_cc_min > 0 and state.wmi.actual_flow_cc_min < state.wmi.commanded_flow_cc_min * 0.75:
            wmi_status = "WARN"
        add("WMI flow", f"{state.wmi.actual_flow_cc_min:.0f}/{state.wmi.commanded_flow_cc_min:.0f}", wmi_status)

        return rows

    def _render_sensor_confidence_overlay(self, state: StateSnapshot) -> None:
        _bg, bright, glow, fault = self._theme_colors()
        green = (80, 255, 155)
        yellow = (255, 214, 80)
        red = fault
        colors = {"OK": green, "WARN": yellow, "ERR": red}
        sw, sh = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(920, sw - 64), min(560, sh - 52))
        panel.center = (sw // 2, sh // 2)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((8, 10, 8, 238))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, glow, panel, width=2, border_radius=8)
        self.screen.blit(font(20, bold=True).render("SENSOR CONFIDENCE", True, bright), (panel.x + 16, panel.y + 12))

        rows = self._sensor_confidence_rows(state)
        cols = 2 if panel.width >= 620 else 1
        col_gap = 16
        col_w = (panel.width - 32 - col_gap * (cols - 1)) // cols
        row_h = 28
        start_y = panel.y + 52
        rows_per_col = max(1, (panel.bottom - start_y - 34) // row_h)
        for idx, (name, value, status) in enumerate(rows[: rows_per_col * cols]):
            col = idx // rows_per_col
            row = idx % rows_per_col
            x = panel.x + 16 + col * (col_w + col_gap)
            y = start_y + row * row_h
            color = colors.get(status, glow)
            pygame.draw.circle(self.screen, color, (x + 8, y + 9), 5)
            self.screen.blit(font(12, bold=True).render(status, True, color), (x + 20, y))
            self.screen.blit(font(13).render(name, True, glow), (x + 98, y))
            value_surface = font(13, bold=True).render(value, True, bright)
            self.screen.blit(value_surface, (x + col_w - value_surface.get_width() - 4, y))
            pygame.draw.line(self.screen, (28, 42, 34), (x, y + row_h - 5), (x + col_w, y + row_h - 5), 1)

        hint = "ESC: BACK"
        hint_surface = font(12, bold=True).render(hint, True, glow)
        self.screen.blit(hint_surface, (panel.right - hint_surface.get_width() - 16, panel.bottom - 22))

    def _render_media_overlay(self) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        panel = pygame.Rect(self.screen.get_width() - 520, 90, 460, 210)
        overlay = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
        overlay.fill((12, 8, 0, 230))
        self.screen.blit(overlay, panel.topleft)
        pygame.draw.rect(self.screen, glow, panel, width=2, border_radius=8)
        title = font(20, bold=True).render("MEDIA", True, bright)
        self.screen.blit(title, (panel.x + 16, panel.y + 10))
        title_line = f"{self._phone_artist} - {self._phone_track}".strip(" -") or "NO TRACK"
        self.screen.blit(font(14).render(title_line[:48], True, glow), (panel.x + 16, panel.y + 40))
        bar = pygame.Rect(panel.x + 16, panel.y + 66, panel.width - 32, 16)
        pygame.draw.rect(self.screen, (45, 30, 0), bar, border_radius=4)
        ratio = (self._phone_position_s / self._phone_length_s) if self._phone_length_s > 0 else 0.0
        fill = pygame.Rect(bar.x + 1, bar.y + 1, int((bar.width - 2) * max(0.0, min(1.0, ratio))), bar.height - 2)
        pygame.draw.rect(self.screen, bright, fill, border_radius=4)
        y = panel.y + 122
        self._draw_media_icons(panel.x + 72, y, active_index=self._media_index)
        if self._media_device_menu_open:
            self._render_device_submenu(panel)

    def _draw_media_icons(self, x: int, y: int, *, active_index: int) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        for idx in range(4):
            c = bright if idx == active_index else glow
            cx = x + idx * 92
            pygame.draw.rect(self.screen, bright if idx == active_index else (70, 45, 0), pygame.Rect(cx, y - 4, 64, 40), width=2, border_radius=5)
            if idx == 0:  # PREV (double left triangles)
                pygame.draw.polygon(self.screen, c, [(cx + 30, y), (cx + 6, y + 16), (cx + 30, y + 32)])
                pygame.draw.polygon(self.screen, c, [(cx + 52, y), (cx + 28, y + 16), (cx + 52, y + 32)])
            elif idx == 1:  # PLAY/PAUSE (toggle-style icon)
                pygame.draw.rect(self.screen, c, pygame.Rect(cx + 12, y + 2, 8, 28))
                pygame.draw.rect(self.screen, c, pygame.Rect(cx + 26, y + 2, 8, 28))
            elif idx == 2:  # NEXT (double right triangles)
                pygame.draw.polygon(self.screen, c, [(cx + 10, y), (cx + 34, y + 16), (cx + 10, y + 32)])
                pygame.draw.polygon(self.screen, c, [(cx + 32, y), (cx + 56, y + 16), (cx + 32, y + 32)])
            else:
                label = font(11, bold=True).render("BT", True, c)
                self.screen.blit(label, (cx + 20, y + 10))

    def _render_device_submenu(self, parent_panel: pygame.Rect) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        menu = pygame.Rect(parent_panel.x + 40, parent_panel.bottom + 6, parent_panel.width - 80, 140)
        overlay = pygame.Surface((menu.width, menu.height), pygame.SRCALPHA)
        overlay.fill((12, 8, 0, 230))
        self.screen.blit(overlay, menu.topleft)
        pygame.draw.rect(self.screen, glow, menu, width=2, border_radius=8)
        self.screen.blit(font(14, bold=True).render("BLUETOOTH DEVICES", True, bright), (menu.x + 10, menu.y + 8))
        rows = self._available_devices[:4]
        if not rows:
            self.screen.blit(font(12).render("No paired devices found.", True, glow), (menu.x + 10, menu.y + 40))
            return
        for idx, (_mac, name) in enumerate(rows):
            active = idx == self._media_device_cursor
            color = bright if active else glow
            prefix = ">" if active else " "
            self.screen.blit(font(12, bold=active).render(f"{prefix} {name[:36]}", True, color), (menu.x + 10, menu.y + 36 + idx * 22))

    def _settings_value(self, item: str) -> str:
        if item == "TRACTION":
            return self._traction_levels[self._traction_index]
        if item == "FUEL TYPE":
            return self._fuel_types[self._fuel_type_index]
        if item == "FLAME MODE":
            if self.state.environment.mode in {"RACE", "ALBATROSS"}:
                return "AUTO ON"
            return "ON" if self._flame_mode_manual_enabled else "OFF"
        if item == "BRIGHTNESS":
            return f"{self._brightness_levels[self._brightness_index]}%"
        if item == "PHONE LINK":
            return "ON" if self._phone_link_enabled else "OFF"
        if item == "THEME":
            return self._themes[self._theme_index]
        if item == "EXPORT LOGS":
            return self._log_export_status
        if item == "INSTALL UPDATE":
            return self._update_install_status
        if item == "ONLINE UPDATE":
            return self._online_update_status
        if item == "SERVICE MODE":
            return "OPEN"
        if item == "SENSOR CONF":
            return "OPEN"
        if item == "NETWORK":
            return self._network.active_ssid[:18] or self._network.status
        if item == "NAV MAP":
            return "ON" if self._navigation.map_enabled else "OFF"
        if item == "NAV ONLINE":
            return "ON" if self._navigation.online_enabled else "OFF"
        if item == "NAV ZOOM":
            return str(self._navigation.zoom)
        if item == "NAV CACHE":
            return f"{self._navigation.cached_tile_count} TILES"
        return "ON" if self._auto_dim_enabled else "OFF"

    def _apply_fuel_type_selection(self, fuel_type_index: int, *, notify: bool = True) -> None:
        if not self._fuel_types:
            return
        self._fuel_type_index = max(0, min(fuel_type_index, len(self._fuel_types) - 1))
        fuel_type = self._fuel_types[self._fuel_type_index]
        with self.state_lock:
            self.state = replace(
                self.state,
                environment=replace(self.state.environment, fuel_type=fuel_type),
            )
        if notify and self._fuel_type_callback:
            self._fuel_type_callback(self._fuel_type_index)
        if notify:
            self._save_preferences()

    def _render_mode_picker(self, panel: pygame.Rect, y: int) -> None:
        _bg, bright, glow, _fault = self._theme_colors()
        x = panel.x + 16
        for idx, mode in enumerate(self._modes):
            selected = idx == self._mode_selection_index
            applied = idx == self._mode_index
            color = bright if selected or applied else glow
            label = font(13, bold=selected).render(mode, True, color)
            self.screen.blit(label, (x, y))
            if selected:
                uy = y + label.get_height() + 1
                pygame.draw.line(self.screen, bright, (x, uy), (x + label.get_width(), uy), 2)
            x += label.get_width() + 16

    def _render_global_hints(self) -> None:
        _bg, _bright, glow, _fault = self._theme_colors()
        hint = "ARROWS: CYCLE SETTINGS/MEDIA/MODES  |  ENTER: SELECT  |  ESC: BACK"
        s = font(12).render(hint, True, glow)
        self.screen.blit(s, (self.screen.get_width() - s.get_width() - 24, self.screen.get_height() - 20))

    def _home_focus_target(self) -> str:
        targets = self._home_focus_targets()
        if self._focus_index < len(targets):
            return targets[self._focus_index]
        mode_idx = self._focus_index - len(targets)
        return f"MODE:{mode_idx}"

    def _home_focus_targets(self) -> list[str]:
        if self._visible_faults:
            return ["NAV", "FAULTS", "SETTINGS", "MEDIA"]
        return list(self._focus_targets)

    def _set_home_focus_target(self, target: str) -> None:
        targets = self._home_focus_targets()
        if target in targets:
            self._focus_index = targets.index(target)
            return
        if target.startswith("MODE:"):
            try:
                mode_idx = int(target.split(":", 1)[1])
            except ValueError:
                mode_idx = 0
            mode_idx = max(0, min(len(self._modes) - 1, mode_idx))
            self._focus_index = len(targets) + mode_idx
            return
        self._focus_index %= max(1, len(targets) + len(self._modes))

    def _normalize_home_focus(self, previous_target: str, previous_had_faults: bool) -> None:
        if self._active_menu != "home":
            return
        if self._visible_faults and not previous_had_faults:
            self._set_home_focus_target("FAULTS")
            return
        self._set_home_focus_target(previous_target)

    def _render_home_fault_focus_outline(self, state: StateSnapshot) -> None:
        if self._active_menu != "home" or self._home_focus_target() != "FAULTS":
            return
        alert_rect = next((w.rect for w in self.widgets if isinstance(w, AlertPanel)), None)
        if alert_rect is None:
            return
        _bg, bright, glow, fault = self._theme_colors()
        color = fault if state.faults else bright
        pygame.draw.rect(self.screen, color, alert_rect.inflate(6, 6), width=2, border_radius=6)
        label = "SELECT FAULT" if state.faults else "NO FAULT"
        surface = font(11, bold=True).render(label, True, color if state.faults else glow)
        self.screen.blit(surface, (alert_rect.x + 8, max(0, alert_rect.y - surface.get_height() - 2)))

    def _render_home_navigation_focus_outline(self) -> None:
        if self._active_menu != "home" or self._home_focus_target() != "NAV":
            return
        nav_rect = next((widget.rect for widget in self.widgets if isinstance(widget, NavigationPanel)), None)
        if nav_rect is None:
            return
        _bg, bright, _glow, _fault = self._theme_colors()
        pygame.draw.rect(self.screen, bright, nav_rect.inflate(6, 6), width=2, border_radius=6)
        label = font(11, bold=True).render("SELECT NAV", True, bright)
        self.screen.blit(label, (nav_rect.x + 8, max(0, nav_rect.y - label.get_height() - 2)))

    def _render_home_mode_hover_underline(self, state: StateSnapshot) -> None:
        _bg, bright, _glow, _fault = self._theme_colors()
        if self._active_menu != "home":
            return
        target = self._home_focus_target()
        if not target.startswith("MODE:"):
            return
        header_rect = next((w.rect for w in self.widgets if isinstance(w, HeaderBar)), None)
        if header_rect is None:
            return
        hover_idx = int(target.split(":", 1)[1])
        padding = max(8, int(header_rect.height * 0.15))
        line_height = max(16, int(header_rect.height * 0.35))
        mx = header_rect.x + padding
        my = header_rect.y + padding // 2
        for idx, mode in enumerate(self._modes):
            active = mode == state.environment.mode
            size = fit_font_size(mode, int(header_rect.width * 0.1), line_height, start_size=line_height + (5 if active else 0), bold=active)
            mode_surface = font(size, bold=active).render(mode, True, (0, 0, 0))
            if idx == hover_idx:
                uy = my + (0 if active else 3) + mode_surface.get_height() + 1
                if header_rect.y <= uy <= header_rect.bottom + 2:
                    pygame.draw.line(self.screen, bright, (mx, uy), (mx + mode_surface.get_width(), uy), 2)
                return
            mx += mode_surface.get_width() + 8

    def _apply_brightness_overlay(self, state: StateSnapshot) -> None:
        level = float(self._brightness_levels[self._brightness_index])
        if self._auto_dim_enabled:
            hour = state.environment.time.hour
            if hour >= 20 or hour < 6:
                level = min(level, 55.0)
        alpha = int(max(0.0, min(200.0, (100.0 - level) * 1.8)))
        if alpha > 0:
            shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            shade.fill((0, 0, 0, alpha))
            self.screen.blit(shade, (0, 0))

    def _render_top_right_media_tile(self) -> None:
        bg, bright, glow, fault = self._theme_colors()
        width = self.screen.get_width()
        # Right-side anchored cluster: settings then media.
        # Leave margin so ambient/GPS readouts at far-right stay visible.
        cluster_right = width - 150
        tile = pygame.Rect(cluster_right - 280, -2, 280, 54)
        settings_rect = pygame.Rect(tile.x - 8 - 128, -2, 128, 54)
        pygame.draw.rect(self.screen, bg, tile, border_radius=6)
        focused = self._active_menu == "home" and self._home_focus_target() == "MEDIA"
        pygame.draw.rect(self.screen, bright if focused else glow, tile, width=2 if focused else 1, border_radius=6)
        label = "BT LINK" if self._phone_link_enabled else "BT OFF"
        left = font(14, bold=True).render(label, True, bright if self._phone_link_enabled else fault)
        title_line = f"{self._phone_artist} - {self._phone_track}".strip(" -") or "NO TRACK"
        right = font(13).render(title_line[:32], True, glow)
        self.screen.blit(left, (tile.x + 10, tile.y + 8))
        self.screen.blit(right, (tile.x + 86, tile.y + 8))
        bar = pygame.Rect(tile.x + 10, tile.y + 34, 180, 10)
        pygame.draw.rect(self.screen, (45, 30, 0), bar, border_radius=3)
        ratio = (self._phone_position_s / self._phone_length_s) if self._phone_length_s > 0 else 0.0
        fill = pygame.Rect(bar.x + 1, bar.y + 1, int((bar.width - 2) * max(0.0, min(1.0, ratio))), bar.height - 2)
        pygame.draw.rect(self.screen, bright, fill, border_radius=3)
        if self._active_menu != "media":
            remaining = max(0.0, self._phone_length_s - self._phone_position_s)
            mm = int(remaining // 60)
            ss = int(remaining % 60)
            rem_text = font(13, bold=True).render(f"-{mm}:{ss:02d}", True, glow)
            self.screen.blit(rem_text, (tile.x + 214, tile.y + 32))

        pygame.draw.rect(self.screen, bg, settings_rect, border_radius=6)
        s_focused = self._active_menu == "home" and self._home_focus_target() == "SETTINGS"
        pygame.draw.rect(self.screen, bright if s_focused else glow, settings_rect, width=2 if s_focused else 1, border_radius=6)
        s_label = font(15, bold=True).render("SETTINGS", True, glow)
        s_hint = font(12).render("SELECT", True, glow)
        self.screen.blit(s_label, (settings_rect.x + 12, settings_rect.y + 10))
        self.screen.blit(s_hint, (settings_rect.x + 30, settings_rect.y + 32))

    def _render_modal_dimmer(self) -> None:
        dim = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        self.screen.blit(dim, (0, 0))

    def _theme_colors(self) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
        theme = self._themes[self._theme_index]
        if theme == "NIGHT OPS":
            return (1, 7, 10), (132, 245, 214), (58, 134, 130), (255, 92, 72)
        if theme == "NIGHT":
            return (14, 18, 28), (130, 190, 255), (88, 135, 190), (255, 90, 90)
        if theme == "HIGH-CON":
            return (0, 0, 0), (255, 255, 255), (220, 220, 220), (255, 80, 80)
        return (24, 14, 0), (255, 198, 64), (185, 134, 39), (255, 72, 36)

    def _apply_theme_overlay_pre_ui(self) -> None:
        theme = self._themes[self._theme_index]
        if theme == "NIGHT":
            tint = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            tint.fill((22, 26, 40, 70))
            self.screen.blit(tint, (0, 0))
        elif theme == "NIGHT OPS":
            tint = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            tint.fill((0, 20, 18, 105))
            self.screen.blit(tint, (0, 0))
        elif theme == "HIGH-CON":
            tint = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            tint.fill((0, 0, 0, 80))
            self.screen.blit(tint, (0, 0))
