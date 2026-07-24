# Albatross Pi HUD & Control Specification

## 0. High-Level Mission
- Raspberry Pi is primary HUD brain and coordinator.
- Drives 11″ display using Pygame with retro 80s aesthetic.
- Translates rider inputs and environment into mode logic and targets.
- Orchestrates CAN traffic between MS3Pro Mini ECU and Teensy actuators (AWC/TCS).
- Logs data, runs POST/diagnostics, enforces fail-safes, supervises OTA updates.
- Real-time torque cuts handled on Teensy/MS3; Pi supervises and displays only.

## 1. Processes, Timing, and Threads
- **Supervisor (`main.py`)**: starts all subsystems and monitors health.
- **CAN RX/TX thread**: SocketCAN interface with 1 kHz receive loop and prioritized transmit queue.
- **State machine thread**: runs at 50–100 Hz for evaluating modes, limits, and requests.
- **HUD renderer thread**: Pygame loop targeting 60 FPS with double buffering and vsync off.
- **Fault logger**: readable summaries, complete JSONL snapshots, and a 30 s rolling pre-fault timeline sampled at 10 Hz.
- **Audio thread**: non-blocking mixer for sound effects and prompts.
- **IO inputs thread**: handles buttons/NFC/touch with 200 Hz debouncing.
- **OTA updater**: on-demand signed update verifier/applicator.
- **Tick budgets**:
  - CAN parse + state update ≤ 2 ms per frame.
  - HUD frame render ≤ 12 ms.
  - Log batch write ≤ 8 ms.
  - Watchdogs: state machine hang > 200 ms or HUD renderer hang > 300 ms triggers alarm and safe UI.

## 2. CAN Responsibilities (SocketCAN)
- **Interface**: `can0` at 500 kbps or 1 Mbps per MS3/Teensy configuration.
- **ID ownership**:
  - MS3Pro Mini: broadcasts engine channels plus oil pressure, oil temperature, and flex fuel; receives ECU-safe map/limit requests.
  - Teensy: broadcasts IMU/wheel speeds/Air Shot/WMI status, receives targets/flags.
  - Pi: sends requests/targets, receives telemetry, initiates POST.
- **Pi → Teensy frames** (examples):
  - `0x120`: Boost target command (PSI × 10) forwarded to the Teensy actuator layer.
  - `0x121`: Mode selector (1 byte: 1=ECO … 5=ALBATROSS) for synchronized HUD/actuator state.
  - `0x140`: NFC authentication acknowledgement (0x00 fail / 0x01 success).
- **Pi → MS3 frames** (examples):
  - Fuel profile/table requests (`0x150`), spark-table requests (`0x151`), and rev-limiter strategy requests (`0x152`, 0=fuel cut, 1=ignition/spark cut for flame mode).
  - Timing bias requests and torque ceiling trims (ECU firmware track).
  - Launch RPM ceilings and boost caps linked to current fuel/WMI status.
- **Teensy/MS3 → Pi frames** (examples): ECU telemetry (`0x100`-`0x10F`) covering RPM, throttle, average boost, optional left/right boost, AFRs, knock, oil pressure/temp, coolant, fuel level, gear, load, IAT, dual-bank EGT, battery voltage, flex-fuel ethanol content, and injector pulse width/duty; Teensy status (`0x130`-`0x13F`, `0x145`-`0x147`) for Air Shot, AWC, tank pressure, twin turbo boost feedback, wastegate duty, wheel speed, WMI, lighting, fuel type, traction status, service sensor voltages, service pin/relay states, firmware version, and limp status.
- **Updated ID map**: canonical enumerations captured in ``albatross_pi/canbus/ids.py`` cover ECU telemetry (`0x100`-`0x10F`), Pi HUD commands, Pi-to-ECU map requests, Teensy supervisory status/service frames (`0x130`-`0x13F`, `0x145`-`0x147`), and bidirectional POST/test utility frames (`0x1F0`-`0x1F1`). Run `py -3.12 tools/audit_can_pins.py` after CAN or pin changes.
- **MS3Pro Mini build note**: oil pressure, oil temperature, flex fuel, and injector pulse width/duty are MS3-owned inputs. The current HUD extension adds `0x10D` for flex-fuel ethanol percentage, `0x10E` for injector status, and optional `0x10F` for left/right boost pressure; wheel speed and WMI status remain Teensy-owned.
- **Timeouts & fallbacks**:
  - Loss of MS3 data: independently tracked from real `0x100`-`0x10F` RX timestamps; Pi safety supervisor derates after 500 ms and HUD reports stale after 1.5 s.
  - Loss of Teensy heartbeat: independently tracked from real controller status RX timestamps; Pi safety supervisor derates after 500 ms and HUD reports stale after 1.5 s.
  - WMI requested but flow low for 250 ms: drop requested boost and display fault banner.

## 3. State Machines (Brains)
- **Top-level modes**: ECO, NORMAL, SPORT, RACE, ALBATROSS.
- **Sub-states**: BOOT → POST → READY → DRIVE → LIMP → SHUTDOWN; transient states include LAUNCH_ARMED, LAUNCH_ACTIVE, FLAME_ACTIVE.
- **Mode parameters**: per-mode boost caps, throttle shaping, AWC/ATC aggressiveness, HUD brightness, flame/launch enablement.
- **TCS profile selector**: chooses traction profile (DRY, DAMP, RAIN, COLD, GRAVEL) via weather/temp/GPS cues, defining slip targets, gains, wheelie pitch window, torque ramp rates.
- **Fuel logic**: HUD fuel selection enforces max boost caps, timing bias windows, WMI strategy, and ECU fuel/stoich profile selection; Pi enforces caps and distributes to Teensy/MS3.
- **Launch control**: arming requires clutch/temperature/gear/knock conditions; per-mode RPM setpoint with HUD messaging.
- **Safety escalations**: knock bursts trigger timing pull and boost reduction; persistent issues enter LIMP; high EGT/thermal load reduces requests and triggers “TURBO HOT” banner.

## 4. HUD Visual Design & Rendering (Pygame)
- Retro aesthetic with pixel fonts (amber/orange) on black background and subtle scanlines.
- Boot flicker and POST scroll (“FUEL INJECTION SYSTEM… OK”).
- 60 FPS target with pre-rendered static assets and cached text surfaces.
- **Layout**:
  - Top bar: mode, fuel icon, time, ambient temp, GPS lock, rain badge.
  - Primary cluster: RPM bar with numeric RPM and “SHIFT!” badge ≥10k; speed, gear; boost gauge with target and duty %, overboost warning; high-mode AFR/timing stats with knock indication; temperatures/pressures (coolant, oil temp, oil pressure, battery V, IAT, EGT); Air Shot indicators; WMI metrics and fault lamp; TCS/AWC slip bars, wheelie indicator, intervention icons; scrolling message line; GL500 heritage alert panel highlights priority warnings.
- **Mode-specific layouts**: ECO (economy emphasis), SPORT (boost/temps focus), RACE (lap timer, G-meter, slip bar), ALBATROSS (flame icon, warnings, bold tach).
- **Service mode**: settings-accessible diagnostic overlay for raw recent CAN frames, sensor voltage/status, digital pin states, relay/output states, and firmware versions.
- **Navigation**: ECO/NORMAL replace the large temperature grid with a themed
  road map and compact safety strip. SPORT/RACE/ALBATROSS show a next-turn
  banner and split two-column vitals grid. Persistent named waypoints, online
  address search, 50-yard arrival waypoint prompts, D-pad text entry, cached
  visible raster tiles, and OSRM-compatible road routes are documented in
  `docs/navigation.md`.
- **Network settings**: settings-accessible NetworkManager Wi-Fi radio, scan,
  signal/security list, and D-pad hotspot password entry via `nmcli`.
- **Brightness/night modes**: auto-dim via ambient sensor/time with manual override; night adds subtle starfield.
- **Performance**: pre-render static grids/labels; cache text by value buckets; use integer scaling and dirty rectangles where applicable.

## 5. Input Handling
- Physical controls are currently modeled as a D-pad plus three buttons: Select, Back, and momentary Air Shot request. Keyboard defaults are arrows, Enter/Space, Esc/Backspace, and `F` for Air Shot; joystick defaults are hat/D-pad, button 0 Select, button 1 Back, button 2 Air Shot.
- Inputs are handled through Pygame keyboard/joystick events; physical controls should either debounce in hardware/USB encoder firmware or present clean HID button events to the Pi.
- Air Shot firing is a momentary Pi request over CAN; Teensy owns the actual latch, mode/rpm/tps/gear/tank/boost safety gates, 10 second max latch timeout, tank-pressure-vs-manifold-pressure shutoff, compressor relay control, and shutoff when requested boost is reached. Compressor refill is buffer-based rather than shot-demand-based: it starts only when stationary/low throttle/not cranking, voltage is healthy, no undervoltage/limp report is active, tank pressure is at or below 95 psi, and the restart delay has expired; it stops at 145 psi or immediately on inhibit. During an active shot and a short decay window after it closes, wastegate control ignores small Air Shot-only MAP overshoot so the shot does not open the wastegates and slow turbo spool.

## 6. Pi-Side Calculations
- **Boost target**: derived from selected fuel strategy, MS3 flex-fuel ethanol content, WMI health, mode, IAT with derates for knock, injector duty limits, WMI failures, high EGT, coolant/oil over-temp. Flex content verifies/derates E85 requests; it does not raise 87/91/93 selections above their own caps.
- **Fuel economy/range**: Pi integrates distance from speed against fuel burn from MS3 injector pulse width/duty. Current default assumes two 1100 cc/min injectors and stock GL500 17.5 L / 4.62 US gal tank capacity; heuristic MPG is only a fallback when injector telemetry is absent.
- **TCS profile**: weather + sensors select traction profile; GPS/sensor fusion can switch to GRAVEL/ROUGH.
- **Timing bias**: suggest advance for high-octane fuels with clean knock history; otherwise neutral/retard.
- **Launch setpoint**: mode-based and conditioned on temps/pressures.
- **Fuel prompts**: detect refuel events (GPS + fuel level change) and prompt for fuel type updates.

## 7. Logging & Black Box
- **Fault logs**: daily JSONL event log plus readable daily summary.
- **Black box**: 30 s RAM ring buffer at 10 Hz for critical channels, persisted as a readable tab-separated timeline whenever a fault is thrown.
- **Fields**: comprehensive engine, traction, intervention, electrical, fuel, mode, and command data.
- **Export**: USB mass-storage or Wi-Fi share on demand.

## 8. Audio UX
- Retro voice (“Power On Self Test… OK”) and minimal alert sounds for knock, overheat, low oil pressure, WMI fault, CAN fault.
- Launch-armed tone and “SHIFT!” ping at 10k.
- Cool-down periods to avoid spam; duck other audio on critical alerts.

## 9. Configuration System
- YAML/JSON files (`modes.yaml`, `fuels.yaml`, `tcs.yaml`, `canmap.yaml`, `ui.yaml`).
- Runtime edits via settings menu with schema validation and atomic swaps.
- Rider presets stored and linked to NFC tags.

## 10. POST & Diagnostics
- 3–5 s power-on self-test sequence verifying filesystem, RTC, CPU temp.
- Sends POST request `0x1F0` and waits for `0x1F1` responses with Teensy/MS3 module status, sensor checks, actuator tests.
- Displays pass/fail summary; critical failures block DRIVE (LIMP override optional).
- On-ride diagnostics: graph pages (boost vs RPM, AFRs, knock, slip) and fault detail view referencing last 30 s snapshot.

## 11. Safety & Fail-Safes
- Thread watchdog heartbeats; supervisor forces LIMP UI on failure.
- Sensor plausibility checks enforce conservative defaults.
- Immediate derates for WMI failures; Air Shot safety gates (pressure, temps, lean angle, traction status).
- Throttle-by-wire supervision with plausibility checks and fast stop commands on mismatch.

### 11.1 Recommended PI fault throw conditions (exhaustive baseline)
- `WMI FLOW LOW`: WMI commanded flow > 0 and measured flow persistently below threshold (e.g., <60% commanded for 250 ms).
- `EGT HIGH`: Exhaust gas temp above soft thermal limit (e.g., >1650°F).
- `CAN TIMEOUT`: expected CAN source heartbeat missing beyond timeout budget.
- `IMU FAULT`: IMU data missing, stale, or outside sanity range.
- `AIR SHOT LOW`: bottle pressure below armed threshold.
- `LOW OIL PRESS`: oil pressure below operating envelope for current RPM.
- `OVERBOOST`: measured boost exceeds target + tolerance window.
- `KNOCK ESCALATE`: repeated knock events over a short rolling window.
- `CRITICAL OIL PRESS`: oil pressure below emergency floor for sustained interval.
- `COOLANT HOT`: coolant exceeds hard thermal ceiling.
- `ECU STALE`: throttle/load present but ECU RPM/telemetry implausibly stale/flat.
- `CAN STALE`: aggregate bus freshness outside UI safety window.
- `SPEED SENSOR`: RPM/gear imply motion but wheel speed remains implausible.
- `GEAR SENSOR`: invalid gear code or contradictory gear transitions.
- `CLUTCH SLIP`: high RPM + throttle with low wheel speed in-drive indicates slip.
- `LOW FUEL`: fuel level crosses critical reserve threshold.
- `WMI TANK EMPTY`: WMI tank level at/near empty while WMI requested.
- `WMI PUMP FAULT`: pump commanded on but electrical/current/flow response absent.
- `WMI PRESSURE LOW`: WMI line pressure below minimum while armed.
- `WASTEGATE STUCK`: duty changes command but boost response remains frozen.
- `BOOST CONTROL ERROR`: closed-loop boost control deviation persists outside margin.
- `SLOW TURBO SPOOL`: target boost is requested under high load but measured boost rises too slowly despite high wastegate duty.
- `CYL EGT BOOST MISMATCH`: high-load operation where EGT-derived load and boost diverge beyond plausibility window.
- `INTAKE AIR HOT`: IAT exceeds configured derate trigger.
- `BATTERY LOW`: bus voltage below under-voltage threshold.
- `BATTERY HIGH`: bus voltage above over-voltage threshold.
- `SENSOR RANGE FAULT`: any critical sensor returns out-of-range or NaN values.
- `ENGINE RUN SWITCH OFF`: safety supervisor has latched run-switch cut request.
- `ENGINE SHUTDOWN REQUEST`: shutdown escalation criteria met and issued.

## 12. Pygame Architecture & Project Layout
- Directory structure with modules for CAN, state, HUD widgets, IO, logging, audio, config, tools.
- Renderer pattern: pre-render static layers; widgets draw from immutable `StateSnapshot`.
- Bitmap fonts with pre-rendered numeric atlases; minimal timers; capped animation update rates.

## 13. Testing & Simulation
- `tools/sim_can.py` provides bench simulation from logs or synthetic sweeps.
- Unit tests for CAN encode/decode and derate logic.
- Hardware-in-the-loop bench with CAN USB dongle and Teensy simulator.

## 14. OTA & Security
- USB update bundles verify SHA-256 payload hashes before install.
- Online updates fast-forward from the configured Git branch only when the tracked worktree is clean and repository history has not diverged.
- Pi app overlays and repository updates preserve a versioned backup and automatically restore it after repeated unconfirmed starts.
- A line-oriented USB NFC reader gates engine-run authority for each power cycle. The MS3 run/start inhibit and a separate hardwired kill path remain required.
- Full signed-bundle verification and full filesystem A/B OS images remain future hardening work.

## 15. Done-Done Checklist
- SocketCAN scripts; verified scaling; state machine/mode enforcement; POST exchange with HUD feedback; WMI fail-safe; Air Shot gating/logging; TCS selection; shift banner; brightness control; black box dump; audio cues; bench sim achieving 60 FPS and <40% CPU.

## 16. Phase 2 Nice-to-Haves
- Lap timer with GPS splits and track map.
- Theme variants (amber default, teal service mode).
- On-device graph viewer with pinch zoom (if touch).
- “Dyno view” page with enlarged gauges for tuning.
