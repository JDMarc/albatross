"""Persistent waypoint navigation and actual map-tile caching for the Pi HUD."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_ROUTER_URL = "https://router.project-osrm.org/route/v1/driving"
USER_AGENT = "AlbatrossMotorcycleHUD/1.0 (+https://github.com/JDMarc/albatross)"
TILE_SIZE = 256


@dataclass(frozen=True)
class Waypoint:
    waypoint_id: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Maneuver:
    instruction: str
    road_name: str
    latitude: float
    longitude: float


def valid_location(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -85.0 <= latitude <= 85.0
        and -180.0 <= longitude <= 180.0
    )


def haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius_m = 6_371_000.0
    a_lat_r = math.radians(a_lat)
    b_lat_r = math.radians(b_lat)
    d_lat = b_lat_r - a_lat_r
    d_lon = math.radians(b_lon - a_lon)
    value = math.sin(d_lat / 2) ** 2 + math.cos(a_lat_r) * math.cos(b_lat_r) * math.sin(d_lon / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))


def latlon_to_world_px(latitude: float, longitude: float, zoom: int) -> tuple[float, float]:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    scale = TILE_SIZE * (2**zoom)
    x = (longitude + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(latitude))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


class NavigationManager:
    """Own persistent waypoints, route requests, and local XYZ tile cache."""

    def __init__(
        self,
        *,
        settings_path: Path | str = "settings/navigation.json",
        tile_cache_dir: Path | str = "maps/tiles",
    ) -> None:
        self.settings_path = Path(settings_path)
        self.tile_cache_dir = Path(tile_cache_dir)
        self.map_enabled = True
        self.online_enabled = True
        self.zoom = 15
        self.tile_url = DEFAULT_TILE_URL
        self.router_url = DEFAULT_ROUTER_URL
        self.current_latitude: float | None = None
        self.current_longitude: float | None = None
        self.waypoints: list[Waypoint] = []
        self.active_waypoint_id: str | None = None
        self.route_coordinates: tuple[tuple[float, float], ...] = ()
        self.maneuvers: tuple[Maneuver, ...] = ()
        self.route_distance_m = 0.0
        self.route_duration_s = 0.0
        self.route_status = "STANDBY"
        self._maneuver_index = 0
        self._tile_downloads: set[tuple[int, int, int]] = set()
        self._tile_retry_after: dict[tuple[int, int, int], float] = {}
        self._lock = threading.RLock()
        self._load()

    @property
    def current_location(self) -> tuple[float, float] | None:
        if not valid_location(self.current_latitude, self.current_longitude):
            return None
        return float(self.current_latitude), float(self.current_longitude)

    @property
    def active_waypoint(self) -> Waypoint | None:
        return next((waypoint for waypoint in self.waypoints if waypoint.waypoint_id == self.active_waypoint_id), None)

    @property
    def active(self) -> bool:
        return self.active_waypoint is not None

    @property
    def cached_tile_count(self) -> int:
        try:
            return sum(1 for _ in self.tile_cache_dir.rglob("*.png"))
        except OSError:
            return 0

    def _load(self) -> None:
        if not self.settings_path.exists():
            return
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Navigation settings could not be loaded: %s", exc)
            return
        self.map_enabled = bool(data.get("map_enabled", self.map_enabled))
        self.online_enabled = bool(data.get("online_enabled", self.online_enabled))
        self.zoom = max(12, min(18, int(data.get("zoom", self.zoom))))
        self.tile_url = str(data.get("tile_url", self.tile_url))
        self.router_url = str(data.get("router_url", self.router_url)).rstrip("/")
        rows = data.get("waypoints", [])
        if isinstance(rows, list):
            for row in rows:
                try:
                    waypoint = Waypoint(
                        waypoint_id=str(row["waypoint_id"]),
                        name=str(row["name"])[:20] or "WAYPOINT",
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if valid_location(waypoint.latitude, waypoint.longitude):
                    self.waypoints.append(waypoint)
        active_waypoint_id = str(data.get("active_waypoint_id", ""))
        active_waypoint = next((waypoint for waypoint in self.waypoints if waypoint.waypoint_id == active_waypoint_id), None)
        if active_waypoint is not None:
            self.active_waypoint_id = active_waypoint.waypoint_id
            self._load_route_cache(active_waypoint)

    def save(self) -> None:
        payload = {
            "version": 1,
            "map_enabled": self.map_enabled,
            "online_enabled": self.online_enabled,
            "zoom": self.zoom,
            "tile_url": self.tile_url,
            "router_url": self.router_url,
            "active_waypoint_id": self.active_waypoint_id,
            "waypoints": [asdict(waypoint) for waypoint in self.waypoints],
        }
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.settings_path.with_suffix(self.settings_path.suffix + ".tmp")
            temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            temp_path.replace(self.settings_path)
        except OSError as exc:
            LOGGER.warning("Navigation settings could not be saved: %s", exc)

    def update_position(self, latitude: float | None, longitude: float | None) -> None:
        if not valid_location(latitude, longitude):
            return
        self.current_latitude = float(latitude)
        self.current_longitude = float(longitude)
        self._advance_maneuver()

    def add_current_waypoint(self, name: str) -> Waypoint | None:
        location = self.current_location
        if location is None:
            self.route_status = "GPS REQUIRED"
            return None
        cleaned_name = " ".join(name.strip().upper().split())[:20] or f"WAYPOINT {len(self.waypoints) + 1}"
        waypoint_id = f"wp-{max([int(row.waypoint_id.split('-')[-1]) for row in self.waypoints if row.waypoint_id.startswith('wp-') and row.waypoint_id.split('-')[-1].isdigit()] or [0]) + 1}"
        waypoint = Waypoint(waypoint_id, cleaned_name, location[0], location[1])
        self.waypoints.append(waypoint)
        self.save()
        self.route_status = f"SAVED {cleaned_name}"
        return waypoint

    def delete_waypoint(self, waypoint_id: str) -> None:
        self.waypoints = [waypoint for waypoint in self.waypoints if waypoint.waypoint_id != waypoint_id]
        if self.active_waypoint_id == waypoint_id:
            self.stop_navigation()
        self.save()

    def set_map_enabled(self, enabled: bool) -> None:
        self.map_enabled = bool(enabled)
        self.save()

    def set_online_enabled(self, enabled: bool) -> None:
        self.online_enabled = bool(enabled)
        self.save()

    def set_zoom(self, zoom: int) -> None:
        self.zoom = max(12, min(18, int(zoom)))
        self.save()

    def stop_navigation(self) -> None:
        with self._lock:
            self.active_waypoint_id = None
            self.route_coordinates = ()
            self.maneuvers = ()
            self.route_distance_m = 0.0
            self.route_duration_s = 0.0
            self._maneuver_index = 0
            self.route_status = "STANDBY"
            self.save()

    def start_navigation(self, waypoint_id: str) -> None:
        waypoint = next((row for row in self.waypoints if row.waypoint_id == waypoint_id), None)
        if waypoint is None:
            self.route_status = "WAYPOINT MISSING"
            return
        if self.current_location is None:
            self.route_status = "GPS REQUIRED"
            return
        self.active_waypoint_id = waypoint.waypoint_id
        self.save()
        self.route_coordinates = ()
        self.maneuvers = ()
        self._maneuver_index = 0
        if not self.online_enabled:
            if not self._load_route_cache(waypoint):
                self.route_status = "OFFLINE ROUTER REQUIRED"
            return
        self.route_status = "ROUTE REQUEST"
        threading.Thread(target=self._download_route, args=(waypoint,), daemon=True, name="navigation-route").start()

    def _download_route(self, waypoint: Waypoint) -> None:
        location = self.current_location
        if location is None:
            self.route_status = "GPS REQUIRED"
            return
        start_lat, start_lon = location
        coordinates = f"{start_lon:.6f},{start_lat:.6f};{waypoint.longitude:.6f},{waypoint.latitude:.6f}"
        query = urllib.parse.urlencode({"overview": "full", "geometries": "geojson", "steps": "true"})
        url = f"{self.router_url}/{coordinates}?{query}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=8.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            route = payload["routes"][0]
            raw_coords = route["geometry"]["coordinates"]
            route_coordinates = tuple((float(lat), float(lon)) for lon, lat in raw_coords)
            maneuvers: list[Maneuver] = []
            for leg in route.get("legs", []):
                for step in leg.get("steps", []):
                    maneuver = step.get("maneuver", {})
                    raw_location = maneuver.get("location", [])
                    if len(raw_location) != 2:
                        continue
                    maneuvers.append(
                        Maneuver(
                            instruction=self._maneuver_text(str(maneuver.get("type", "continue")), str(maneuver.get("modifier", ""))),
                            road_name=str(step.get("name", "")).upper()[:28],
                            latitude=float(raw_location[1]),
                            longitude=float(raw_location[0]),
                        )
                    )
        except Exception as exc:
            LOGGER.warning("Navigation route request failed: %s", exc)
            if not self._load_route_cache(waypoint):
                self.route_status = "ROUTER UNAVAILABLE"
            return
        with self._lock:
            if self.active_waypoint_id != waypoint.waypoint_id:
                return
            self.route_coordinates = route_coordinates
            self.maneuvers = tuple(maneuvers)
            self.route_distance_m = float(route.get("distance", 0.0))
            self.route_duration_s = float(route.get("duration", 0.0))
            self._maneuver_index = 0
            self.route_status = "NAV ACTIVE"
            self._save_route_cache(waypoint)
            self._advance_maneuver()

    @staticmethod
    def _maneuver_text(kind: str, modifier: str) -> str:
        kind = kind.replace("_", " ").upper()
        modifier = modifier.replace("_", " ").upper()
        if kind in {"TURN", "CONTINUE", "NEW NAME", "END OF ROAD", "FORK", "MERGE", "ROUNDABOUT"} and modifier:
            return f"{kind} {modifier}"
        if kind == "DEPART":
            return "START ROUTE"
        if kind == "ARRIVE":
            return "ARRIVE"
        return kind or "CONTINUE"

    def _save_route_cache(self, waypoint: Waypoint) -> None:
        payload = {
            "waypoint": asdict(waypoint),
            "route_distance_m": self.route_distance_m,
            "route_duration_s": self.route_duration_s,
            "coordinates": self.route_coordinates,
            "maneuvers": [asdict(maneuver) for maneuver in self.maneuvers],
        }
        try:
            path = self.settings_path.parent / "navigation_route_cache.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            LOGGER.debug("Could not save navigation route cache: %s", exc)

    def _load_route_cache(self, waypoint: Waypoint) -> bool:
        path = self.settings_path.parent / "navigation_route_cache.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            cached_waypoint = payload["waypoint"]
            if str(cached_waypoint["waypoint_id"]) != waypoint.waypoint_id:
                return False
            route_coordinates = tuple((float(lat), float(lon)) for lat, lon in payload["coordinates"])
            maneuvers = tuple(
                Maneuver(
                    instruction=str(row["instruction"]),
                    road_name=str(row["road_name"]),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                )
                for row in payload.get("maneuvers", [])
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if len(route_coordinates) < 2:
            return False
        with self._lock:
            self.route_coordinates = route_coordinates
            self.maneuvers = maneuvers
            self.route_distance_m = float(payload.get("route_distance_m", 0.0))
            self.route_duration_s = float(payload.get("route_duration_s", 0.0))
            self._maneuver_index = 0
            self.route_status = "NAV CACHE"
            self._advance_maneuver()
        return True

    def _advance_maneuver(self) -> None:
        location = self.current_location
        if location is None or not self.maneuvers:
            return
        while self._maneuver_index < len(self.maneuvers) - 1:
            maneuver = self.maneuvers[self._maneuver_index]
            if haversine_m(location[0], location[1], maneuver.latitude, maneuver.longitude) > 38.0:
                break
            self._maneuver_index += 1

    def next_maneuver(self) -> tuple[str, str, float] | None:
        location = self.current_location
        if location is None or not self.maneuvers:
            return None
        maneuver = self.maneuvers[min(self._maneuver_index, len(self.maneuvers) - 1)]
        distance_m = haversine_m(location[0], location[1], maneuver.latitude, maneuver.longitude)
        return maneuver.instruction, maneuver.road_name, distance_m

    def remaining_distance_m(self) -> float:
        location = self.current_location
        if location is None or not self.route_coordinates:
            return self.route_distance_m
        nearest = min(
            range(len(self.route_coordinates)),
            key=lambda idx: haversine_m(location[0], location[1], self.route_coordinates[idx][0], self.route_coordinates[idx][1]),
        )
        points = self.route_coordinates[nearest:]
        remaining = haversine_m(location[0], location[1], points[0][0], points[0][1])
        for first, second in zip(points, points[1:]):
            remaining += haversine_m(first[0], first[1], second[0], second[1])
        return remaining

    def tile_path(self, zoom: int, x: int, y: int) -> Path:
        return self.tile_cache_dir / str(zoom) / str(x) / f"{y}.png"

    def request_tile(self, zoom: int, x: int, y: int) -> Path:
        limit = 2**zoom
        x %= limit
        if y < 0 or y >= limit:
            return self.tile_path(zoom, x, y)
        path = self.tile_path(zoom, x, y)
        key = (zoom, x, y)
        if path.exists() or not self.map_enabled or not self.online_enabled:
            return path
        with self._lock:
            if key in self._tile_downloads or self._tile_retry_after.get(key, 0.0) > time.monotonic():
                return path
            self._tile_downloads.add(key)
        threading.Thread(target=self._download_tile, args=(zoom, x, y, path), daemon=True, name="navigation-tile").start()
        return path

    def _download_tile(self, zoom: int, x: int, y: int, path: Path) -> None:
        key = (zoom, x, y)
        try:
            url = self.tile_url.format(z=zoom, x=x, y=y)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=5.0) as response:
                data = response.read()
            if not data.startswith(b"\x89PNG"):
                raise ValueError("tile response was not PNG data")
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(".tmp")
            temp_path.write_bytes(data)
            temp_path.replace(path)
            with self._lock:
                self._tile_retry_after.pop(key, None)
        except Exception as exc:
            LOGGER.debug("Map tile %s/%s/%s unavailable: %s", zoom, x, y, exc)
            with self._lock:
                self._tile_retry_after[key] = time.monotonic() + 30.0
        finally:
            with self._lock:
                self._tile_downloads.discard(key)
