"""Pygame HUD renderer for the Albatross project."""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List

import pygame

from .widgets.airshot_panel import AirShotPanel
from .widgets.afr_panel import AfrPanel
from .widgets.alert_panel import AlertPanel
from .widgets.boost_panel import BoostPanel
from .widgets.fuel_panel import FuelPanel
from .widgets.header_bar import HeaderBar
from .widgets.message_line import MessageLine
from .widgets.rpm_bar import RpmBar
from .widgets.speed_gear import SpeedGear
from .widgets.temps_grid import TempsGrid
from .widgets.traction_panel import TractionPanel
from .widgets.ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_GLOW, FAULT_AMBER, fit_font_size, font
from ..state.snapshot import StateSnapshot

SCREEN_SIZE = (1920, 720)
TARGET_FPS = 60
LOGGER = logging.getLogger(__name__)


class EvaAlertAudio:
    """Fault-to-voice alert mapper for EVA Chrysler prompts."""

    def __init__(self) -> None:
        self._enabled = False
        self._channel: pygame.mixer.Channel | None = None
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._last_played: dict[str, float] = {}
        self._cooldown_s = 8.0
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._channel = pygame.mixer.Channel(2)
            cache_dir = Path.home() / ".cache" / "albatross" / "eva24"
            cache_dir.mkdir(parents=True, exist_ok=True)
            base_url = "https://raw.githubusercontent.com/jnewb1/eva-sounds/main/sounds_eva24"
            mapping = {
                "CRITICAL OIL PRESS": "your_engine_oil_pressure_is_critical_engine_damage_may_occur.wav",
                "LOW OIL PRESS": "your_engine_oil_pressure_is_critical_engine_damage_may_occur.wav",
                "COOLANT HOT": "your_engine_is_overheating_prompt_service_is_required.wav",
                "EGT HOT": "your_engine_temperature_is_above_normal.wav",
                "LOW FUEL": "please_check_your_fuel_level.wav",
                "KNOCK": "long_beeps.wav",
                "KNOCK ESCALATE": "long_beeps.wav",
                "WMI FLOW LOW": "long_beeps.wav",
                "CAN STALE": "long_beeps.wav",
                "ECU STALE": "long_beeps.wav",
                "CLUTCH SLIP": "long_beeps.wav",
                "SPEED SENSOR": "long_beeps.wav",
                "GEAR SENSOR": "long_beeps.wav",
            }
            resolved: dict[str, Path] = {}
            for name in sorted(set(mapping.values())):
                wav_path = cache_dir / name
                if not wav_path.exists():
                    try:
                        urllib.request.urlretrieve(f"{base_url}/{name}", wav_path)
                    except Exception as exc:
                        LOGGER.warning("Failed downloading EVA clip %s: %s", name, exc)
                        continue
                resolved[name] = wav_path
            for fault, name in mapping.items():
                wav_path = resolved.get(name)
                if wav_path is not None:
                    self._sounds[fault] = pygame.mixer.Sound(str(wav_path))
            self._enabled = bool(self._sounds)
        except pygame.error as exc:
            LOGGER.warning("Audio alerts disabled (pygame mixer init failed): %s", exc)

    def update(self, faults: tuple[str, ...], *, allow_playback: bool) -> None:
        if not self._enabled or not allow_playback:
            return
        now = time.monotonic()
        for fault in faults:
            sound = self._sounds.get(fault)
            if sound is None:
                continue
            if (now - self._last_played.get(fault, 0.0)) < self._cooldown_s:
                continue
            if self._channel is not None and not self._channel.get_busy():
                self._channel.play(sound)
                self._last_played[fault] = now
                return


class HUDRenderer:
    """Render loop that drives Pygame surfaces."""

    def __init__(
        self,
        screen_size: tuple[int, int] = SCREEN_SIZE,
        *,
        use_display: bool = True,
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
        self._modes = ["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]
        self._mode_index = 0
        self._mode_layout_state = {"boost": 0.30, "afr": 0.25, "temps": 0.62}
        self._traction_levels = ["LOW", "MED", "HIGH", "OFF"]
        self._traction_index = 1
        self._traction_callback = None
        self._mode_callback = None
        self._media_callback = None
        self._focus_targets = ["SETTINGS", "MEDIA"]
        self._focus_index = 0
        self._active_menu = "home"
        self._settings_cursor = 0
        self._media_items = ["PREV", "PLAY", "NEXT", "DEVICES"]
        self._media_index = 0
        self._media_device_cursor = 0
        self._media_device_menu_open = False
        self._setting_items = ["TRACTION", "BRIGHTNESS", "MODE", "PHONE LINK", "THEME", "AUTO DIM"]
        self._phone_link_enabled = False
        self._brightness_levels = [25, 40, 55, 70, 85, 100]
        self._brightness_index = 3
        self._themes = ["AMBER", "NIGHT", "HIGH-CON"]
        self._theme_index = 0
        self._auto_dim_enabled = True
        self._phone_track = ""
        self._phone_artist = ""
        self._phone_position_s = 0.0
        self._phone_length_s = 0.0
        self._available_devices: tuple[tuple[str, str], ...] = ()
        self._last_snapshot_time = self.state.environment.time
        self._last_can_fresh_monotonic = time.monotonic()
        self._display_time_anchor = self.state.environment.time
        self._display_time_anchor_monotonic = self._last_can_fresh_monotonic
        self._audio = EvaAlertAudio()
        self._create_widgets()

    def _runtime_faults(self, state: StateSnapshot, now_s: float) -> tuple[str, ...]:
        active: set[str] = set()
        can_age_s = max(0.0, now_s - self._last_can_fresh_monotonic)
        if can_age_s > 1.5:
            active.add("CAN STALE")
        if state.temps.oil_pressure_psi < 12 and state.engine.rpm > 1800:
            active.add("LOW OIL PRESS")
        if state.temps.coolant_temp_f > 235:
            active.add("COOLANT HOT")
        if state.temps.exhaust_temp_f > 1600:
            active.add("EGT HOT")
        if state.engine.boost_psi > max(1.0, state.engine.target_boost_psi + 3.0):
            active.add("OVERBOOST")
        if state.engine.knock_events >= 2:
            active.add("KNOCK ESCALATE")
        if state.environment.fuel_level_pct <= 12:
            active.add("LOW FUEL")
        if state.wmi.fault_active:
            active.add("WMI FLOW LOW")
        if state.engine.gear == "?":
            active.add("GEAR SENSOR")

        # Return only currently active faults; AlertPanel handles post-clear hold timing.
        return tuple(sorted(active))

    def configure_traction_callback(self, callback) -> None:
        self._traction_callback = callback

    def configure_mode_callback(self, callback) -> None:
        self._mode_callback = callback

    def configure_media_callback(self, callback) -> None:
        self._media_callback = callback

    def update_phone_status(self, *, artist: str, track: str, position_s: float, length_s: float, devices: tuple[tuple[str, str], ...]) -> None:
        self._phone_artist = artist
        self._phone_track = track
        self._phone_position_s = max(0.0, position_s)
        self._phone_length_s = max(0.0, length_s)
        self._available_devices = devices

    def _mode_ratios(self, mode: str) -> dict[str, float]:
        profiles = {
            "ECO": {"boost": 0.28, "afr": 0.24, "temps": 0.64},
            "NORMAL": {"boost": 0.32, "afr": 0.25, "temps": 0.60},
            "SPORT": {"boost": 0.40, "afr": 0.24, "temps": 0.52},
            "RACE": {"boost": 0.42, "afr": 0.23, "temps": 0.53},
            "ALBATROSS": {"boost": 0.46, "afr": 0.22, "temps": 0.50},
        }
        target = profiles.get(mode, profiles["NORMAL"])
        # Soft animation toward target ratios so gauges move smoothly.
        for key in self._mode_layout_state:
            self._mode_layout_state[key] += (target[key] - self._mode_layout_state[key]) * 0.25
        return dict(self._mode_layout_state)

    def _create_widgets(self) -> None:
        # Defensive initialization for partially-merged working copies.
        if not hasattr(self, "_modes"):
            self._modes = ["ECO", "NORMAL", "SPORT", "RACE", "ALBATROSS"]
        if not hasattr(self, "_mode_index"):
            self._mode_index = 0
        if not hasattr(self, "_mode_layout_state"):
            self._mode_layout_state = {"boost": 0.30, "afr": 0.25, "temps": 0.62}

        width, height = self.screen.get_size()
        padding = max(int(width * 0.02), 24)
        gutter = max(int(height * 0.02), 18)
        top_bar_height = max(int(height * 0.12), 80)
        message_height = max(int(height * 0.06), 40)
        rpm_height = max(int(height * 0.07), 50)

        top_bar_rect = pygame.Rect(0, 0, width, top_bar_height)
        message_rect = pygame.Rect(0, height - message_height, width, message_height)
        rpm_rect = pygame.Rect(padding, top_bar_height + gutter, width - 2 * padding, rpm_height)

        content_top = rpm_rect.bottom + gutter
        content_height = max(height - message_height - content_top - gutter, 200)

        available_width = width - 2 * padding
        column_gutter = max(int(width * 0.015), 16)
        usable_width = max(available_width - 2 * column_gutter, 300)

        min_left = max(int(width * 0.16), 200)
        min_center = max(int(width * 0.22), 230)
        min_right = max(int(width * 0.3), 320)
        if usable_width <= min_left + min_center + min_right:
            scale = usable_width / float(min_left + min_center + min_right)
            left_width = max(int(min_left * scale), 160)
            center_width = max(int(min_center * scale), 180)
            right_width = max(usable_width - left_width - center_width, 160)
        else:
            leftover = usable_width - (min_left + min_center + min_right)
            left_width = min_left + leftover // 6
            center_width = min_center + leftover // 3
            right_width = usable_width - left_width - center_width

        left_x = padding
        center_x = left_x + left_width + column_gutter
        right_x = center_x + center_width + column_gutter

        alert_height = max(int(content_height * 0.32), int(height * 0.18))
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

        panel_gap = max(int(height * 0.02), 18)
        mode = self._modes[self._mode_index]
        ratios = self._mode_ratios(mode)
        boost_ratio = ratios["boost"]
        afr_ratio = ratios["afr"]
        boost_height = max(int(content_height * boost_ratio), int(height * 0.2))
        afr_height = max(int(content_height * afr_ratio), int(height * 0.15))
        center_remaining = content_height - boost_height - afr_height - panel_gap
        if center_remaining < 80:
            afr_height = max(afr_height + center_remaining - 80, 80)
            center_remaining = 80
        boost_rect = pygame.Rect(center_x, content_top, center_width, boost_height)
        afr_rect = pygame.Rect(center_x, boost_rect.bottom + panel_gap, center_width, afr_height)

        temps_ratio = ratios["temps"]
        temps_height = max(int(content_height * temps_ratio), int(height * 0.34))
        fuel_height = max(int(content_height * 0.16), int(height * 0.11))
        traction_height = max(int(content_height * 0.14), int(height * 0.1))
        airshot_height = max(int(content_height * 0.14), int(height * 0.09))
        # WMI panel removed; WMI readouts are merged into TempsGrid.
        extra_right = max(content_height - temps_height - traction_height - airshot_height - 2 * panel_gap, 0)
        temps_height += extra_right
        temps_rect = pygame.Rect(right_x, content_top, right_width, temps_height)
        # Fuel gauge moved to center-lower zone (under AFR/SPARK and right of alert panel).
        fuel_width = center_width
        fuel_x = center_x
        fuel_rect = pygame.Rect(fuel_x, afr_rect.bottom + panel_gap, fuel_width, fuel_height)
        traction_rect = pygame.Rect(right_x, temps_rect.bottom + panel_gap, right_width, traction_height)
        airshot_rect = pygame.Rect(right_x, traction_rect.bottom + panel_gap, right_width, airshot_height)
        # Prevent lower panels from overlapping the message line.
        bottom_limit = message_rect.y - panel_gap
        for r in (temps_rect, traction_rect, airshot_rect):
            if r.bottom > bottom_limit:
                r.height = max(36, r.height - (r.bottom - bottom_limit))

        prior_fault_latch_until: dict[str, float] = {}
        for widget in self.widgets:
            if isinstance(widget, AlertPanel):
                prior_fault_latch_until = dict(widget._fault_latch_until)
                break

        self.widgets = [
            HeaderBar(top_bar_rect),
            MessageLine(message_rect),
            RpmBar(rpm_rect),
            SpeedGear(speed_rect, gear_rect),
            BoostPanel(boost_rect),
            AfrPanel(afr_rect),
            AlertPanel(alert_rect),
            TempsGrid(temps_rect),
            FuelPanel(fuel_rect),
            TractionPanel(traction_rect),
            AirShotPanel(airshot_rect),
        ]
        for widget in self.widgets:
            if isinstance(widget, AlertPanel):
                widget._fault_latch_until = prior_fault_latch_until
                break

    def configure_input_bindings(self, ack_key: int) -> None:
        self._ack_key = ack_key

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
        age_s = max(0.0, (datetime.now() - state.environment.time).total_seconds())
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
            ("CAN LINK", has_can_signal or bool(state.environment.message_line)),
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
                    if event.key in (pygame.K_TAB, pygame.K_m):
                        self._mode_index = (self._mode_index + 1) % len(self._modes)
                        if self._mode_callback:
                            self._mode_callback(self._mode_index + 1)
                        self._create_widgets()
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
                    elif event.key in (pygame.K_RIGHTBRACKET, pygame.K_PERIOD):
                        self._traction_index = (self._traction_index + 1) % len(self._traction_levels)
                        if self._traction_callback:
                            self._traction_callback(self._traction_index + 1)

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
            if state.environment.mode in self._modes:
                self._mode_index = self._modes.index(state.environment.mode)

            # Keep the HUD clock moving even when telemetry timestamps stop updating.
            display_time = self._display_time_anchor + timedelta(
                seconds=max(0.0, now_s - self._display_time_anchor_monotonic)
            )
            state = replace(state, environment=replace(state.environment, time=display_time))

            # keep animating mode-based layout transitions
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
                    ),
                    environment=state.environment,
                    shift_light=state.shift_light,
                    faults=state.faults,
                )

            if not self._post_complete:
                self._run_post(state)

            if self._post_complete and self._post_fault_active:
                pressed = pygame.key.get_pressed()
                if pressed[self._ack_key]:
                    self._post_fault_active = False
            self._audio.update(
                state.faults,
                allow_playback=self._post_complete and not self._post_fault_active,
            )
            self._render_frame(state)
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
        self._render_frame(state, present=False)
        return self.screen.copy()

    def _render_frame(self, state: StateSnapshot, *, present: bool = True) -> None:
        self.screen.fill((0, 0, 0))
        for widget in self.widgets:
            widget.draw(self.screen, state)
        self._apply_theme_overlay_pre_ui()
        self._render_top_right_media_tile()
        if self._active_menu == "settings":
            self._render_modal_dimmer()
            self._render_settings_overlay()
        elif self._active_menu == "media":
            self._render_media_overlay()
        self._render_global_hints()
        self._apply_brightness_overlay(state)
        if (not self._post_complete) or self._post_fault_active:
            self._render_post_overlay()
        if present and self._use_display:
            pygame.display.flip()

    def _render_post_overlay(self) -> None:
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        self.screen.blit(overlay, (0, 0))
        x = 24
        y = 24
        elapsed = max(0.0, time.monotonic() - self._post_started_at)
        title_full = "POWER ON SELF TEST"
        title_chars = min(len(title_full), int(elapsed / 0.045))
        title = font(18, bold=True).render(title_full[:title_chars], True, AMBER_BRIGHT)
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
                color = AMBER_GLOW
            else:
                out = f"{prefix} {result}"
                color = AMBER_GLOW if ok else FAULT_AMBER
            sz = fit_font_size(out, self.screen.get_width() - 48, 20, start_size=16)
            surf = font(sz).render(out, True, color)
            self.screen.blit(surf, (x, y))
            y += 20
        # Hold 1s after last line before allow ack prompt
        done_time = 1.0 + len(self._post_lines) * 2.0 + 1.0
        if elapsed < done_time:
            return
        ack = f"FAULT ACK REQUIRED: PRESS {pygame.key.name(self._ack_key).upper()}"
        ack_s = font(16, bold=True).render(ack, True, FAULT_AMBER)
        self.screen.blit(ack_s, (x, self.screen.get_height() - 40))

    def _handle_dpad_right(self) -> None:
        if self._active_menu == "settings":
            item = self._setting_items[self._settings_cursor]
            if item == "TRACTION":
                self._traction_index = (self._traction_index + 1) % len(self._traction_levels)
                if self._traction_callback:
                    self._traction_callback(self._traction_index + 1)
            elif item == "BRIGHTNESS":
                self._brightness_index = min(self._brightness_index + 1, len(self._brightness_levels) - 1)
            elif item == "MODE":
                self._mode_index = (self._mode_index + 1) % len(self._modes)
                if self._mode_callback:
                    self._mode_callback(self._mode_index + 1)
            elif item == "PHONE LINK":
                self._phone_link_enabled = True
                if self._media_callback:
                    self._media_callback("phone_link", 1)
            elif item == "THEME":
                self._theme_index = (self._theme_index + 1) % len(self._themes)
            elif item == "AUTO DIM":
                self._auto_dim_enabled = True
            return
        if self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor + 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index + 1) % len(self._media_items)
            return
        self._focus_index = (self._focus_index + 1) % len(self._focus_targets)

    def _handle_dpad_left(self) -> None:
        if self._active_menu == "settings":
            item = self._setting_items[self._settings_cursor]
            if item == "TRACTION":
                self._traction_index = (self._traction_index - 1) % len(self._traction_levels)
                if self._traction_callback:
                    self._traction_callback(self._traction_index + 1)
            elif item == "BRIGHTNESS":
                self._brightness_index = max(self._brightness_index - 1, 0)
            elif item == "MODE":
                self._mode_index = (self._mode_index - 1) % len(self._modes)
                if self._mode_callback:
                    self._mode_callback(self._mode_index + 1)
            elif item == "PHONE LINK":
                self._phone_link_enabled = False
                if self._media_callback:
                    self._media_callback("phone_link", 0)
            elif item == "THEME":
                self._theme_index = (self._theme_index - 1) % len(self._themes)
            elif item == "AUTO DIM":
                self._auto_dim_enabled = False
            return
        if self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor - 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index - 1) % len(self._media_items)
            return
        self._focus_index = (self._focus_index - 1) % len(self._focus_targets)

    def _handle_up(self) -> None:
        if self._active_menu == "settings":
            self._settings_cursor = (self._settings_cursor - 1) % len(self._setting_items)
        elif self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor - 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index - 1) % len(self._media_items)

    def _handle_down(self) -> None:
        if self._active_menu == "settings":
            self._settings_cursor = (self._settings_cursor + 1) % len(self._setting_items)
        elif self._active_menu == "media":
            if self._media_device_menu_open and self._available_devices:
                self._media_device_cursor = (self._media_device_cursor + 1) % len(self._available_devices)
            else:
                self._media_index = (self._media_index + 1) % len(self._media_items)

    def _handle_select(self) -> None:
        if self._active_menu == "home":
            target = self._focus_targets[self._focus_index]
            if target == "SETTINGS":
                cur = self.state
                if cur.engine.gear == "N" and cur.engine.speed_mph <= 0.1:
                    self._active_menu = "settings"
            elif target == "MEDIA":
                self._active_menu = "media"
            return
        if self._active_menu == "media":
            self._activate_media_action()
            return
        if self._active_menu == "settings" and self._setting_items[self._settings_cursor] == "PHONE LINK":
            self._phone_link_enabled = not self._phone_link_enabled
            if self._media_callback:
                self._media_callback("phone_link", 1 if self._phone_link_enabled else 0)

    def _handle_back(self) -> None:
        if self._active_menu != "home":
            if self._active_menu == "media" and self._media_device_menu_open:
                self._media_device_menu_open = False
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
        for idx, item in enumerate(self._setting_items):
            active = idx == self._settings_cursor
            color = bright if active else glow
            value = self._settings_value(item)
            text = font(17, bold=active).render(f"{item:<12} {value}", True, color)
            row_y = panel.y + 52 + idx * 34
            self.screen.blit(text, (panel.x + 16, row_y))
            if active:
                pygame.draw.line(self.screen, bright, (panel.x + 14, row_y + 24), (panel.right - 14, row_y + 24), 1)
        y = panel.bottom - 26
        dev_title = font(12, bold=True).render("BT DEVICES", True, glow)
        self.screen.blit(dev_title, (panel.x + 16, y))
        if self._available_devices:
            devs = ", ".join(self._available_devices[:3])
            self.screen.blit(font(12).render(devs[:44], True, bright), (panel.x + 100, y))

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
        if item == "BRIGHTNESS":
            return f"{self._brightness_levels[self._brightness_index]}%"
        if item == "MODE":
            return self._modes[self._mode_index]
        if item == "PHONE LINK":
            return "ON" if self._phone_link_enabled else "OFF"
        if item == "THEME":
            return self._themes[self._theme_index]
        return "ON" if self._auto_dim_enabled else "OFF"

    def _render_global_hints(self) -> None:
        _bg, _bright, glow, _fault = self._theme_colors()
        hint = "ARROWS: NAV  |  ENTER: SELECT  |  ESC: BACK"
        s = font(12).render(hint, True, glow)
        self.screen.blit(s, (self.screen.get_width() - s.get_width() - 24, self.screen.get_height() - 20))

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
        focused = self._active_menu == "home" and self._focus_targets[self._focus_index] == "MEDIA"
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
        s_focused = self._active_menu == "home" and self._focus_targets[self._focus_index] == "SETTINGS"
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
        elif theme == "HIGH-CON":
            tint = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            tint.fill((0, 0, 0, 80))
            self.screen.blit(tint, (0, 0))
