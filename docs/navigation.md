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
- `SEARCH ADDRESS` opens the same bike-usable keyboard and, while online,
  returns selectable address matches that route over roads.
- Existing waypoints can be routed to over roads or deleted.
- Arriving within 50 yards of a searched destination opens a themed prompt to
  save that location as a permanent waypoint.
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

For a desktop bench without GPS hardware, run:

```text
py -3.12 can_demo_controls.py --dry-run
```

Use the `Navigation GPS -> HUD` fields to enter decimal latitude and longitude
coordinates and toggle the simulated GPS lock.

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
  "geocoder_url": "https://nominatim.openstreetmap.org/search",
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

## Address Search

Address search uses a configurable Nominatim-compatible endpoint. The default
public OpenStreetMap Nominatim service is appropriate for light interactive
bench testing only. It is not an autocomplete service, and the HUD performs a
single lookup only after the rider selects `SEARCH`.

API reference: <https://nominatim.org/release-docs/latest/api/Search/>

Usage policy: <https://operations.osmfoundation.org/policies/nominatim/>

For regular road use, set `geocoder_url` in `settings/navigation.json` to a
managed or self-hosted Nominatim-compatible service.

## Pi Network Settings

The HUD `SETTINGS -> NETWORK` overlay controls the Pi Wi-Fi radio, rescans
nearby networks, shows signal strength and security, and connects to a selected
network through a D-pad password keyboard. Blank passwords allow reconnecting
to a saved profile or joining an open network.

The adapter uses Raspberry Pi OS NetworkManager through `nmcli`. On a Windows
demo or a Pi image without NetworkManager, the overlay stays usable and reports
`NMCLI UNAVAILABLE` instead of failing.

NetworkManager CLI reference:
<https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nmcli.html>

## Updates

The `maps/` directory is runtime data. USB and online Pi update overlays skip it
so downloaded or preloaded tiles survive firmware updates.
