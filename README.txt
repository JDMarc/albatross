Hello All,

This my major project, which has been active for years, ever since I bought my bike.
A 1982 Honda GL500, which is exactly what this "albatross" project is for.
In essence, we are building a twin turbocharged motorcycle in homage to the 80s and the cx500 turbo as a whole, 
this is done through fault correction and tuning coordinated by the Pi, ECU,
two separate Teensy 4.1 boards, DBWX2 throttle controller and RaceGrade CAN IMU.

What this repo is trying to accomplish
--------------------------------------

Current DBWX2 + RaceGrade unified DBW/TCS/AWC implementation and commissioning
requirements: docs/vehicle_dynamics.md. This is not a road-qualified calibration.
The Pi now provides a D-pad Dynamics menu with rider curves and event telemetry.

At a practical level, this repository exists to do four things reliably:

1) Render a useful rider HUD at speed
   - Fast Pygame rendering with a consistent layout and scalable resolution.
   - Priority status/warning indicators that are visible under stress.

2) Decode and normalize CAN data into one coherent state
   - ECU + controller frames are merged into a single StateSnapshot model.
   - HUD code reads that snapshot instead of dealing with raw frame parsing.

3) Enforce safe supervisory behavior
   - Detect key out-of-bounds conditions and request conservative actions.
   - Keep the UI and outbound requests in sync during fault transitions.

4) Stay testable during long development cycles
   - Works in simulator/demo mode for desktop iteration.
   - Works in live CAN mode on Pi hardware with SocketCAN.

System roles 
--------------------------------------

This is the short version of how this stuff works:

- Raspberry Pi
  - Runs HUD, handles top-level state presentation, and sends high-level requests.
  - Supervises and coordinates behavior; does not try to be hard real-time torque control.

- MS3Pro Mini ECU
  - Owns core engine management, primary telemetry, and ECU-side strategy.
  - Receives selected control intents/limits from the network.
  - Publishes injector pulse width/duty on `0x10E` so the Pi can calculate
    fuel burn, MPG, and range from actual injection data.
  - Optionally publishes left/right boost pressure on `0x10F` so split-tract
    boost mismatch is visible instead of hidden by the average boost display.

- Teensy 4.1 controller (arduino/teensy41/albatross_controller_teensy41)
  - Runs dual electronic wastegate actuator outputs (PWM/DIR/EN per channel).
  - Manages Air Shot V2: four independent PWM valves, OFF/MANUAL/AUTO, demand,
    pressure/driver checks, profile tapering and a separate compressor controller.
  - Runs the unified dynamics estimator, rear-slip TCS, pitch-based AWC and
    torque arbitration using wheel Hall inputs, RaceGrade IMU and DBWX2 feedback.
  - Requests physical throttle travel from DBWX2 and retains ECU torque-reduction
    requests (0x12A/0x12B) for integration with engine protection.
  - Enforces automatic demand-driven WMI interlocks, provisional CAN-level flame intent, and limp-aware behavior.
  - Uses a hardware watchdog so stalled controller firmware resets into inactive outputs.

- Dedicated Teensy 4.1 thermal node (arduino/teensy41/albatross_thermal_node)
  - Acquires the 32-channel thermal array through proper thermocouple front ends and precision SPI ADC hardware.
  - Converts, validates, filters, diagnoses, and broadcasts versioned thermal CAN frames independently of the Pi.
  - Feeds the Pi thermal service/HUD and the main Teensy's direct degraded/protective path. See docs/thermal_system.md.

- DBWX2 + RaceGrade 6-Axis CAN IMU
  - DBWX2 owns throttle servo control and redundant APS/TPS checking; the current
    adapter supervises channel 1 for the intended 2026 MT-07 throttle assembly.
  - RaceGrade supplies acceleration/angular-rate CAN data to the main Teensy.
  - Device configuration, throttle connector wiring and independent kill circuit
    require verification; see docs/vehicle_dynamics.md for the exact boundary.

Two-board wiring and firmware quick reference
---------------------------------------------

Both Teensy boards use CAN1 RX pin 22 and TX pin 23 through SEPARATE external
3.3 V CAN transceivers on the same 500 kbit/s backbone. Pin numbers are local
to each board. Do not combine pins just because their numbers match.

Thermal Teensy hardware SPI: MOSI 11, MISO 12, SCK 13.
Thermal MAX31856 chip-select pins: 10 = left EGT, 9 = right EGT,
8 = left turbine outlet, 7 = right turbine outlet.
Thermal ADS7953 chip-select pins: 6 = device 0 (analog channels 0-15),
5 = device 1 (analog channels 16-31).
The thermal configuration has 32 stable sensor IDs: 29 enabled, 3 reserved.
The full pin tables and sensor-ID-to-ADC-channel map are in arduino/README.md.

No dedicated flame-mode output pin is allocated. Main-controller pin 11 is
unassigned. Air Shot V2 needs four configured PWM driver outputs; the shipped
configuration does not invent their pin assignments. Main pin 12 is a legacy
output initialized low, not an automatically assigned V2 solenoid output.
See docs/wiring_pinout.md for the rest of the harness and voltage conditioning.

Controller firmware notes (important)

   Both current sketch targets are Teensy 4.1 with native CAN1 through a
   3.3 V CAN transceiver. The old Mega/MCP2515 sketch is retained under
   arduino/legacy/mega2560.

Quick references:

- Main sketch: arduino/teensy41/albatross_controller_teensy41/albatross_controller_teensy41.ino
- Thermal sketch: arduino/teensy41/albatross_thermal_node/albatross_thermal_node.ino
- Controller details/tuning notes: arduino/README.md

What the controller currently publishes for the HUD/stack:

- Air Shot status (0x130)
- AWC/lean status (0x131)
- Tank pressure (0x133)
- Twin turbo feedback (0x134)
- Wastegate status (0x135)
- WMI, clutch slip, motorcycle lamp, oil-pressure fallback, and fuel-type status frames (0x139-0x13D)
- Gear + wheel speed/fuel support frames (0x136–0x138)

Bring-up reminder for this repo architecture:

1) Identify and label both USB boards; flash each matching sketch independently.
   Existing single-controller update bundles must not be assumed to flash the
   thermal board. Build/library instructions are in arduino/README.md.
2) Confirm Pi receives expected IDs on can0.
3) Then validate HUD rendering/state transitions.

New telemetry: thermal 0x160-0x17D, Air Shot V2 0x180-0x185, and unified
dynamics 0x220-0x229. DBWX2 also uses extended 29-bit polling/replies.
Protocol details: docs/thermal_can_protocol.md, docs/airshot_v2.md,
docs/vehicle_dynamics.md. The latched powertrain stop is 0x20A; run-ON cannot
clear it. This is a software stop request, with independent kill hardware
and recovery requirements described in the dynamics document.

HUD controls and calibration
----------------------------

Thermal warning catalogue and confirmed IGNORE ERROR behavior:
docs/thermal_alerts.md. Thermal errors now join the main HUD/audio warning path.
Ignoring silences only the current occurrence; a resolved error warns again if
it returns. ECU/controller protections and fault logging remain active.

Left/right on the top bar runs ECO, NORMAL, SPORT, RACE, ALBATROSS, then SETTINGS
and MEDIA. Down enters NAV on the right. Up/down follows the visible panels:
NAV, System Vitals (where present), TCS/AWC, then AIR. The bottom does not wrap
back to NAV. ECO/NORMAL place TEMP and AIR side by side; left/right moves between
them. Up from NAV or Back from the home panels returns to the last top-bar item.
Left from the panel column accesses active errors, otherwise the top bar;
Right from errors returns to the previous panel. Settings always opens for browsing;
editing requires stopped speed and either neutral/park or an engine-off bench state.
Air Shot separates requested mode/FIRE, confirmed controller mode, and the reported
inhibit reason. Missing acknowledgements are shown as unconfirmed, not as success.
Controller-confirmed FIRING has its own bordered annunciator inside Air Shot;
text/background invert every 250 ms. Offline and shadow telemetry cannot flash
the active-firing badge. Instrument bezels and a segmented boost gauge follow
the selected theme without adding scanlines or screen overlays. Visual regression:
python tests/run_instrument_style_checks.py
The COMMS / MEDIA menu has theme-matched instrument styling, separate track and
artist lines, elapsed/remaining time, labeled transport buttons and request feedback.
DEVICES opens a scrolling picker; Back returns to the player before exiting to
the HUD. Unknown duration and unavailable controls are explicit. Media requests
do not assert successful playback or connection. No seek/volume/shuffle support
is assumed. Run python tests/run_media_checks.py for UI/command regressions.

FAULT MANAGEMENT: main-Teensy capabilities and fault torque/boost ceilings now
coordinate existing protections without changing the error HUD. Pi loss is
noncritical; thermal redundancy and calibrated dynamics-only degradation retain
limited rideability where supported. Optional master NC Air Shot isolation uses
reserved pin 12 after explicit hardware configuration. Read docs/fault_management.md
before commissioning: many additional detectors require sensor mappings and
engineering limits, and requested PDM/fan/RPM/EWG actions are not assumed applied.
The Pi receives atomic fault telemetry and records bounded pre/post CAN windows.
HUD coolant/oil/plenum/EGT now come from the dedicated thermal Teensy, not legacy
ECU temperature frames. See docs/thermal_system.md for source and failure behavior.
TCS/AWC now has a larger panel with separate levels and intervention status.

- TEMPS: Focus System Vitals (SPORT/RACE/ALBATROSS) or the small TEMP tile
  (ECO/NORMAL), then Select to open the page menu. Hovering does not open it.
  Up/down chooses a page; Select opens it. Includes overview,
  ABS/DEV heat maps, intake/turbos, cooling, oil, sensor status and history.
  Heat maps now draw the actual system architecture as a twin-turbo transverse
  V-twin schematic with separate charge/exhaust, cooling and oil paths. Moving
  flow arrows and smoothly rotating turbo rotors animate the map; each bank's
  boost drives its visual speed (common-boost fallback, not measured shaft RPM).
  Backgrounds, scanlines and decorative details follow the selected HUD theme;
  temperature and fluid-path colors stay consistent across themes.
  All four D-pad directions move to visible neighboring sensor callouts. Select or Back
  returns to the menu; Back again
  returns to the focused vitals/TEMP tile. TEMP label color reflects thermal
  severity, with cold/warming/operating/hot/cooldown or fault state below it.
- TCS/AWC: Select opens Dynamics. Up/down chooses a row; left/right requests
  levels, throttle curve, weather assist or bounded rider envelopes. Telemetry,
  event history and confirmed latched-stop controls are available here.
  Select on THROTTLE CURVE opens the five-point editor with COMFORT/ROAD/RESPONSE
  baselines and fixed 1:1. Saved points require rebuilding/flashing the main
  Teensy and restarting the HUD. See docs/throttle_curves.md.
- AIR: Select once, then left/right requests OFF/MANUAL/AUTO. Select again opens
  detailed Air Shot information. The USB three-position switch also sends modes.
- SETTINGS: AIR SHOT CALIBRATION edits drafts and transfers while stopped;
  AIR MODE SWITCH learns USB switch positions. FIRE uses the grip controller.

Rider settings do not replace measured engineering limits. The configuration
sources are config/thermal_system.json, config/airshot_v2.json and
config/vdc_engineering.json. Missing physical calibration values remain unset;
curve visualizations show configured data and require matching firmware identity.

Repository layout
-----------------

- main.py  
  Flexible development entrypoint (desktop/demo/snapshot/live-CAN capable).

- pi_main.py  
  Pi-focused launcher used for deployment/autostart defaults.

- albatross_pi/canbus/  
  CAN IDs, frame encode/decode, and CANStateAggregator.

- albatross_pi/hud/  
  Renderer + HUD widgets.

- albatross_pi/state/  
  Snapshot dataclasses and simulator.

- logs/
  Created on first startup. Faults are written as both raw JSONL
  (`fault_events_YYYY-MM-DD.jsonl`) and a readable one-line summary
  (`fault_events_YYYY-MM-DD.txt`). Each fault also writes a readable
  `pre_fault_*.txt` timeline containing approximately 30 seconds of lead-in
  data. Use the text files for quick diagnosis; use JSONL when you need the
  complete trigger snapshot and machine-readable timeline.

- settings/
  Created when rider-adjustable HUD preferences are changed. The default
  `hud_settings.json` remembers selected mode, traction level, fuel type,
  brightness, phone link, theme, and auto-dim across power cycles.

- maps/
  Created by the navigation system for cached or preloaded XYZ raster tiles.
  ECO/NORMAL show a selectable road map with persistent waypoints; performance
  modes retain their gauges and use a compact next-turn banner. See
  `docs/navigation.md` before configuring a production tile/router provider.

- deploy/albatross-hud.service  
  Example systemd unit for power-on auto-launch on Raspberry Pi.

- deploy/can@.service
  SocketCAN systemd unit for can0/can1 bring-up at 500 kbit/s.

- deploy/config.txt.waveshare-2ch-can.fragment
  Raspberry Pi boot config fragment for the Waveshare 2-CH MCP2515 CAN HAT.

- deploy/config.txt.power.fragment
  Raspberry Pi GPIO overlay fragment for controlled key-off shutdown and
  external power-latch handoff. See `docs/power_nfc_watchdogs.md`.

- docs/  
  Project spec, ECU setup notes, and Raspberry Pi deployment notes. See
  `docs/pi_deployment.md` for the CAN HAT and fast autostart path.

- updates/
  Created by USB bundle and online repository update installs. USB bundles can
  install Pi app overlays and flash the USB-connected Teensy controller; online
  updates fast-forward the Pi application from the configured Git branch. See
  `docs/update_bundles.md`.
  Build bundles with `py -3.12 tools\make_update_bundle.py`.

Running the project
-------------------

Desktop / demo iteration:


python main.py --width 1280 --height 480


For desktop CAN/demo control testing without a GPS receiver, run
`py -3.12 can_demo_controls.py --dry-run` and use the `Navigation GPS -> HUD`
fields to enter latitude, longitude, and simulated GPS-lock state.

The demo also has Dynamics, Air Shot V2 and Thermal tabs, per-channel overrides,
fault presets and subsystem stream-pause controls for stale-data warnings.
Dry-run prints CAN and sends local UDP to the HUD; use the default HUD launch
without --simulator or a live CAN interface. Hardware commands are opt-in.
See docs/can_demo_controls.md for units, command behavior and isolated-bus use.

Regression checks: python tests/run_can_demo_checks.py,
python tests/run_dynamics_checks.py, python tests/run_airshot_checks.py,
python tests/run_thermal_checks.py. Shared configuration checks and both firmware
build commands are listed in arduino/README.md.


Live CAN mode (SocketCAN):


python main.py --can-interface can0 --width 1280 --height 480


Pi-focused launch path (recommended on hardware):


python pi_main.py --can-interface can0 --width 1280 --height 480


Headless screenshot capture:


python main.py --width 1920 --height 720 --snapshot docs/assets/hud_demo.png


Power-on autostart on Raspberry Pi (systemd)
--------------------------------------------

1. Copy service template:


sudo cp deploy/albatross-hud.service /etc/systemd/system/albatross-hud.service


2. Edit user/path/flags for your install:


sudo nano /etc/systemd/system/albatross-hud.service


3. Enable and start:


sudo systemctl daemon-reload
sudo systemctl enable albatross-hud.service
sudo systemctl start albatross-hud.service


4. Verify:


systemctl status albatross-hud.service
journalctl -u albatross-hud.service -f


Notes
------------------------

- python-can must be installed on Pi for SocketCAN mode.
- can0 must be configured and up before expecting live telemetry.
- If CAN is quiet at startup, HUD can still boot, but safety/fault behavior depends on incoming data quality.
- Keep main.py for flexible dev/testing; keep pi_main.py as deployment entrypoint.

Advice for others porting this to their own build
-------------------------------------------------

If you are adapting this to a different bike/car/ECU stack:

FIRSTLY, know that i may branch this eventually with a release that has everything you need to edit in the headers of the code,
but i cant be bothered to do this right now (as of 5/16/26)

1) Start with your CAN map first
   - Update IDs/scaling in albatross_pi/canbus/ids.py and decode paths.
   - Mirror those changes in your controller firmware map so both sides agree.
   - Validate with logged sample frames before touching UI styling.

2) Define your safety contract early
   - Decide what conditions trigger limp/derate and what exact outbound actions happen.
   - Keep those rules centralized and auditable.

3) Separate demo and deployment entrypoints
   - You will want different defaults for desktop iteration vs vehicle boot.
   - Keep your autostart path boring and explicit.

4) Design UI around glanceability, not density
   - Prioritize warning hierarchy and readability over showing every metric at once.

5) Treat this as supervisory, not absolute authority*
   - Hard real-time controls should remain in dedicated controller/ECU layers.
   - Let the Pi coordinate, visualize, and request safe limits.

6) Log aggressively during integration
   - Bring-up is mostly about proving assumptions wrong safely.
   - Keep a reproducible test loop: capture frames -> replay -> verify state -> verify actions.
*NOTE: This is something you SHOULD do but you dont HAVE to, i have a lot of error handling on my MS3, 
but a lot is also done by the rest of the system (mainly the pi) to ensure major faults do not occur,
now i trust them to be fast enough and responsive enough to do this, but if you do the same,
I AM NOT RESPONSIBLE IF SOMETHING BLOWS UP!!!!!!

MS3Pro-specific setup details are in docs/ms3_tunerstudio_setup.md.
Full project vision/spec notes are in docs/albatross_pi_spec.md.
Production NFC authorization, watchdogs, and controlled Pi shutdown hardware
are documented in docs/power_nfc_watchdogs.md.
