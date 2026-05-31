# Navigation Setup

The Pi HUD includes road navigation with actual raster map tiles, persistent
waypoints, and OSRM-compatible road routing.

## Rider Experience

- ECO and NORMAL replace the large temperature table with a map. A slim safety
  strip keeps coolant temperature, oil temperature, oil pressure, and battery
  voltage visible.
- SPORT, RACE, and ALBATROSS keep their performance layout and show a compact
  next-turn banner.
- Select `NAV` from the home focus cycle to open the waypoint menu.
- `SAVE CURRENT LOCATION` opens a D-pad keyboard.
- Existing waypoints can be routed to over roads or deleted.
- Waypoints persist in `settings/navigation.json`.
- The last downloaded route is cached in
  `settings/navigation_route_cache.json` as a fallback if connectivity drops.

## GPS Input

Phone telemetry UDP JSON may provide:

```json
{
  "gps_lock": true,
  "gps_lat": 42.3314,
  "gps_lon": -83.0458
}
```

The same `EnvironmentState.gps_latitude` and `gps_longitude` fields can later
be populated by a dedicated USB or UART GNSS receiver.

## Map Tiles

The default development source is OpenStreetMap's standard raster tile server.
The HUD requests only tiles currently visible on screen and caches them under:

```text
maps/tiles/{zoom}/{x}/{y}.png
```

Do not bulk-download or prefetch from `tile.openstreetmap.org`. The OpenStreetMap
Foundation tile policy prohibits offline bulk downloading from that public
service. It is suitable for development and ordinary visible-tile requests,
with the required on-screen attribution already rendered by the HUD.

Policy reference: <https://operations.osmfoundation.org/policies/tiles/>

For a roadgoing installation, configure `tile_url` in
`settings/navigation.json` to use a provider whose terms permit vehicle use and
offline regions, or copy an offline XYZ tile pack into `maps/tiles/`. The HUD
uses local files first, so preloaded tiles work without a network connection.

Example configuration:

```json
{
  "map_enabled": true,
  "online_enabled": true,
  "zoom": 15,
  "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  "router_url": "https://router.project-osrm.org/route/v1/driving",
  "waypoints": []
}
```

## Road Routing

The router must implement the OSRM route API. The default public OSRM endpoint
is useful for bench development. Do not depend on it for a production vehicle.

API reference: <https://project-osrm.org/docs/v5.24.0/api/#route-service>

For dependable road navigation, run an OSRM backend on a reachable local
network service or choose a managed routing provider. Fully offline routing on
the bike can be added by pointing `router_url` at a local OSRM-compatible
service running on the Pi or a companion computer with the required regional
map extract.

## Updates

The `maps/` directory is runtime data. USB and online Pi update overlays skip it
so downloaded or preloaded tiles survive firmware updates.
