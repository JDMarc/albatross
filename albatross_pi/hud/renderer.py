"""Pygame HUD renderer for the Albatross project."""
from __future__ import annotations

import threading
import time
from typing import Iterable, List

import pygame

from .widgets.airshot_panel import AirShotPanel
from .widgets.afr_panel import AfrPanel
from .widgets.boost_panel import BoostPanel
from .widgets.gl_sprite import GLSprite
from .widgets.header_bar import HeaderBar
from .widgets.message_line import MessageLine
from .widgets.rpm_bar import RpmBar
from .widgets.speed_gear import SpeedGear
from .widgets.temps_grid import TempsGrid
from .widgets.traction_panel import TractionPanel
from .widgets.wmi_panel import WMIPanel
from ..state.snapshot import StateSnapshot

SCREEN_SIZE = (1920, 720)
TARGET_FPS = 60


class HUDRenderer:
    """Render loop that drives Pygame surfaces."""

    def __init__(self, screen_size: tuple[int, int] = SCREEN_SIZE) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("Albatross HUD")
        self.clock = pygame.time.Clock()
        self.running = False
        self.state = StateSnapshot()
        self.state_lock = threading.Lock()
        self.widgets: List = []
        self._create_widgets()

    def _create_widgets(self) -> None:
        width, height = self.screen.get_size()
        self.widgets = [
            HeaderBar(pygame.Rect(0, 0, width, 80)),
            MessageLine(pygame.Rect(0, height - 40, width, 40)),
            RpmBar(pygame.Rect(40, 100, width - 80, 40)),
            SpeedGear(
                speed_rect=pygame.Rect(60, 170, 200, 140),
                gear_rect=pygame.Rect(280, 170, 120, 120),
            ),
            BoostPanel(pygame.Rect(420, 170, 360, 90)),
            AfrPanel(pygame.Rect(420, 270, 360, 80)),
            TempsGrid(pygame.Rect(width - 280, 120, 240, 240)),
            TractionPanel(pygame.Rect(width - 280, 370, 240, 100)),
            AirShotPanel(pygame.Rect(width - 280, 480, 240, 80)),
            WMIPanel(pygame.Rect(width - 280, 570, 240, 80)),
            GLSprite(pygame.Rect(60, 340, 200, 200)),
        ]

    def update_state(self, snapshot: StateSnapshot) -> None:
        with self.state_lock:
            self.state = snapshot

    def run(self, state_source: Iterable[StateSnapshot] | None = None) -> None:
        self.running = True
        frame_duration = 1.0 / TARGET_FPS
        last_tick = time.perf_counter()

        state_iter = iter(state_source) if state_source else None

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

            if state_iter is not None:
                try:
                    snapshot = next(state_iter)
                    self.update_state(snapshot)
                except StopIteration:
                    state_iter = None

            with self.state_lock:
                state = self.state

            self._render_frame(state)
            self.clock.tick(TARGET_FPS)

            now = time.perf_counter()
            if now - last_tick < frame_duration:
                time.sleep(frame_duration - (now - last_tick))
            last_tick = now

        pygame.quit()

    def _render_frame(self, state: StateSnapshot) -> None:
        self.screen.fill((0, 0, 0))
        for widget in self.widgets:
            widget.draw(self.screen, state)
        pygame.display.flip()
