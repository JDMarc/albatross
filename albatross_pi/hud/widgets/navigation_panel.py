"""Theme-aware road-navigation map and compact next-turn banner."""
from __future__ import annotations

import math
from pathlib import Path

import pygame

from ...navigation import TILE_SIZE, NavigationManager, latlon_to_world_px
from ...state.snapshot import StateSnapshot
from .base import Widget
from .ui_utils import AMBER_BG, AMBER_BRIGHT, AMBER_DARK, AMBER_GLOW, FAULT_AMBER, fit_font_size, font


def _distance_text(distance_m: float) -> str:
    if distance_m >= 1609.344:
        return f"{distance_m / 1609.344:.1f} MI"
    return f"{max(0.0, distance_m) * 3.28084:.0f} FT"


class NavigationPanel(Widget):
    def __init__(self, rect: pygame.Rect, navigation: NavigationManager, *, compact: bool = False) -> None:
        self.rect = rect
        self.navigation = navigation
        self.compact = compact
        self._tile_surfaces: dict[Path, pygame.Surface] = {}

    def draw(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        if self.compact:
            self._draw_compact(surface)
            return
        self._draw_full_map(surface, state)

    def _draw_compact(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        pygame.draw.rect(surface, AMBER_DARK, self.rect, 1)
        maneuver = self.navigation.next_maneuver()
        if not self.navigation.active:
            self._draw_text(surface, "NAV STANDBY", self.rect.x + 10, self.rect.centery, AMBER_GLOW, 13, center_y=True)
            return
        if maneuver is None:
            label = self.navigation.route_status
            self._draw_text(surface, label, self.rect.x + 10, self.rect.centery, AMBER_BRIGHT, 14, bold=True, center_y=True)
            return
        instruction, road, distance_m = maneuver
        left_w = max(110, int(self.rect.width * 0.2))
        self._draw_text(surface, _distance_text(distance_m), self.rect.x + 10, self.rect.centery, AMBER_BRIGHT, 16, bold=True, center_y=True)
        self._draw_text(surface, instruction, self.rect.x + left_w, self.rect.y + 5, AMBER_BRIGHT, 15, bold=True)
        self._draw_text(surface, road or "FOLLOW ROUTE", self.rect.x + left_w, self.rect.y + 24, AMBER_GLOW, 12)

    def _draw_full_map(self, surface: pygame.Surface, state: StateSnapshot) -> None:
        pygame.draw.rect(surface, AMBER_BG, self.rect)
        location = self.navigation.current_location
        map_rect = self.rect.inflate(-2, -2)
        safety_h = max(28, min(38, int(self.rect.height * 0.13)))
        header_h = max(36, min(48, int(self.rect.height * 0.16)))
        viewport = pygame.Rect(map_rect.x, map_rect.y + header_h, map_rect.width, max(20, map_rect.height - header_h - safety_h))
        pygame.draw.rect(surface, (4, 5, 4), viewport)

        if not self.navigation.map_enabled:
            self._draw_center_status(surface, viewport, "MAP DISABLED")
        elif location is None:
            self._draw_center_status(surface, viewport, "GPS LOCK REQUIRED")
        else:
            self._draw_tiles(surface, viewport, location[0], location[1])
            self._draw_route(surface, viewport, location[0], location[1])
            self._draw_waypoints(surface, viewport, location[0], location[1])
            self._draw_bike_marker(surface, viewport)
            attribution = font(9, bold=True).render("(C) OPENSTREETMAP CONTRIBUTORS", True, AMBER_GLOW)
            surface.blit(attribution, (viewport.right - attribution.get_width() - 5, viewport.bottom - attribution.get_height() - 3))

        self._draw_header(surface, map_rect)
        self._draw_safety_strip(surface, state, pygame.Rect(map_rect.x, map_rect.bottom - safety_h, map_rect.width, safety_h))
        pygame.draw.rect(surface, AMBER_GLOW, map_rect, 1)

    def _draw_tiles(self, surface: pygame.Surface, viewport: pygame.Rect, latitude: float, longitude: float) -> None:
        zoom = self.navigation.zoom
        center_x, center_y = latlon_to_world_px(latitude, longitude, zoom)
        world_left = center_x - viewport.width / 2
        world_top = center_y - viewport.height / 2
        first_x = math.floor(world_left / TILE_SIZE)
        last_x = math.floor((world_left + viewport.width) / TILE_SIZE)
        first_y = math.floor(world_top / TILE_SIZE)
        last_y = math.floor((world_top + viewport.height) / TILE_SIZE)
        previous_clip = surface.get_clip()
        surface.set_clip(viewport)
        for tile_x in range(first_x, last_x + 1):
            for tile_y in range(first_y, last_y + 1):
                px = viewport.x + int(tile_x * TILE_SIZE - world_left)
                py = viewport.y + int(tile_y * TILE_SIZE - world_top)
                tile_rect = pygame.Rect(px, py, TILE_SIZE, TILE_SIZE)
                path = self.navigation.request_tile(zoom, tile_x, tile_y)
                tile = self._load_tile(path)
                if tile is None:
                    pygame.draw.rect(surface, (8, 10, 8), tile_rect)
                    pygame.draw.rect(surface, AMBER_DARK, tile_rect, 1)
                else:
                    surface.blit(tile, tile_rect.topleft)
        tint = pygame.Surface(viewport.size, pygame.SRCALPHA)
        tint.fill((0, 8, 0, 96))
        surface.blit(tint, viewport.topleft)
        surface.set_clip(previous_clip)

    def _load_tile(self, path: Path) -> pygame.Surface | None:
        cached = self._tile_surfaces.get(path)
        if cached is not None:
            return cached
        if not path.exists():
            return None
        try:
            tile = pygame.image.load(path.as_posix())
            if pygame.display.get_surface() is not None:
                tile = tile.convert()
        except pygame.error:
            return None
        self._tile_surfaces[path] = tile
        if len(self._tile_surfaces) > 96:
            self._tile_surfaces.pop(next(iter(self._tile_surfaces)))
        return tile

    def _world_to_view(
        self,
        viewport: pygame.Rect,
        center_lat: float,
        center_lon: float,
        latitude: float,
        longitude: float,
    ) -> tuple[int, int]:
        center_x, center_y = latlon_to_world_px(center_lat, center_lon, self.navigation.zoom)
        x, y = latlon_to_world_px(latitude, longitude, self.navigation.zoom)
        return viewport.centerx + int(x - center_x), viewport.centery + int(y - center_y)

    def _draw_route(self, surface: pygame.Surface, viewport: pygame.Rect, latitude: float, longitude: float) -> None:
        if len(self.navigation.route_coordinates) < 2:
            return
        points = [
            self._world_to_view(viewport, latitude, longitude, route_lat, route_lon)
            for route_lat, route_lon in self.navigation.route_coordinates
        ]
        previous_clip = surface.get_clip()
        surface.set_clip(viewport)
        pygame.draw.lines(surface, (10, 15, 8), False, points, 6)
        pygame.draw.lines(surface, AMBER_BRIGHT, False, points, 3)
        surface.set_clip(previous_clip)

    def _draw_waypoints(self, surface: pygame.Surface, viewport: pygame.Rect, latitude: float, longitude: float) -> None:
        previous_clip = surface.get_clip()
        surface.set_clip(viewport)
        for waypoint in self.navigation.waypoints:
            x, y = self._world_to_view(viewport, latitude, longitude, waypoint.latitude, waypoint.longitude)
            active = waypoint.waypoint_id == self.navigation.active_waypoint_id
            color = FAULT_AMBER if active else AMBER_BRIGHT
            pygame.draw.circle(surface, (8, 8, 4), (x, y), 8)
            pygame.draw.circle(surface, color, (x, y), 7, 2)
            pygame.draw.line(surface, color, (x, y + 7), (x, y + 15), 2)
            label = font(10, bold=active).render(waypoint.name[:14], True, color)
            surface.blit(label, (x + 10, y - label.get_height() // 2))
        surface.set_clip(previous_clip)

    @staticmethod
    def _draw_bike_marker(surface: pygame.Surface, viewport: pygame.Rect) -> None:
        x, y = viewport.center
        pygame.draw.polygon(surface, (0, 0, 0), [(x, y - 12), (x - 10, y + 10), (x, y + 6), (x + 10, y + 10)])
        pygame.draw.polygon(surface, AMBER_BRIGHT, [(x, y - 12), (x - 10, y + 10), (x, y + 6), (x + 10, y + 10)], 2)

    def _draw_header(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        header = pygame.Rect(rect.x, rect.y, rect.width, max(36, min(48, int(rect.height * 0.16))))
        pygame.draw.rect(surface, (7, 5, 0), header)
        pygame.draw.line(surface, AMBER_DARK, (header.x, header.bottom - 1), (header.right, header.bottom - 1), 1)
        self._draw_text(surface, "NAV", header.x + 9, header.y + 5, AMBER_BRIGHT, 16, bold=True)
        waypoint = self.navigation.active_waypoint
        status = waypoint.name if waypoint else self.navigation.route_status
        self._draw_text(surface, status[:22], header.x + 60, header.y + 6, AMBER_GLOW, 14, bold=True)
        maneuver = self.navigation.next_maneuver()
        if maneuver:
            instruction, road, distance_m = maneuver
            self._draw_text(surface, f"{_distance_text(distance_m)}  {instruction}"[:38], header.x + 60, header.y + 24, AMBER_BRIGHT, 12, bold=True)
            if road:
                max_w = max(40, header.width // 3)
                text = road[:22]
                sz = fit_font_size(text, max_w, 18, start_size=12, bold=True)
                road_surface = font(sz, bold=True).render(text, True, AMBER_GLOW)
                surface.blit(road_surface, (header.right - road_surface.get_width() - 8, header.y + 7))

    def _draw_safety_strip(self, surface: pygame.Surface, state: StateSnapshot, rect: pygame.Rect) -> None:
        pygame.draw.rect(surface, (7, 5, 0), rect)
        pygame.draw.line(surface, AMBER_DARK, (rect.x, rect.y), (rect.right, rect.y), 1)
        values = (
            f"CLT {state.temps.coolant_temp_f:.0f}F",
            f"OIL {state.temps.oil_temp_f:.0f}F",
            f"OIL P {state.temps.oil_pressure_psi:.0f}",
            f"BAT {state.temps.battery_voltage:.1f}V",
        )
        cell_w = max(1, rect.width // len(values))
        for idx, value in enumerate(values):
            sz = fit_font_size(value, cell_w - 8, rect.height - 4, start_size=12, bold=True)
            self._draw_text(surface, value, rect.x + idx * cell_w + 5, rect.centery, AMBER_GLOW, sz, bold=True, center_y=True)

    def _draw_center_status(self, surface: pygame.Surface, rect: pygame.Rect, text: str) -> None:
        size = fit_font_size(text, rect.width - 24, 30, start_size=18, bold=True)
        label = font(size, bold=True).render(text, True, AMBER_GLOW)
        surface.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))

    @staticmethod
    def _draw_text(
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        color,
        size: int,
        *,
        bold: bool = False,
        center_y: bool = False,
    ) -> None:
        label = font(size, bold=bold).render(text, True, color)
        surface.blit(label, (x, y - label.get_height() // 2 if center_y else y))
