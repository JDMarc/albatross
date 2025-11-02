# Albatross Pi HUD & Control Specification

## 0. High-Level Mission
- Raspberry Pi is primary HUD brain and coordinator.
- Drives 11″ display using Pygame with retro 80s aesthetic.
- Translates rider inputs and environment into mode logic and targets.
- Orchestrates CAN traffic between MS3Pro Mini ECU and Arduino actuators (AWC/TCS/eTRAC).
- Logs data, runs POST/diagnostics, enforces fail-safes, supervises OTA updates.
- Real-time torque cuts handled on Arduino/MS3; Pi supervises and displays only.

## 1. Processes, Timing, and Threads
- **Supervisor (`main.py`)**: starts all subsystems and monitors health.
- **CAN RX/TX thread**: SocketCAN interface with 1 kHz receive loop and prioritized transmit queue.
- **State machine thread**: runs at 50–100 Hz for evaluating modes, limits, and requests.
- **HUD renderer thread**: Pygame loop targeting 60 FPS with double buffering and vsync off.
- **Logger thread**: asynchronous SD logging with 30 s ring buffer and batch writes every 100–250 ms.
- **Audio thread**: non-blocking mixer for sound effects and prompts.
- **IO inputs thread**: handles buttons/NFC/touch with 200 Hz debouncing.
- **OTA updater**: on-demand signed update verifier/applicator.
- **Tick budgets**:
  - CAN parse + state update ≤ 2 ms per frame.
  - HUD frame render ≤ 12 ms.
  - Log batch write ≤ 8 ms.
  - Watchdogs: state machine hang > 200 ms or HUD renderer hang > 300 ms triggers alarm and safe UI.

## 2. CAN Responsibilities (SocketCAN)
- **Interface**: `can0` at 500 kbps or 1 Mbps per MS3/Arduino configuration.
- **ID ownership**:
  - MS3Pro Mini: broadcasts engine channels, receives commands.
  - Arduino: broadcasts IMU/wheel speeds/Air Shot/WMI status, receives targets/flags.
  - Pi: sends requests/targets, receives telemetry, initiates POST.
- **Pi → Arduino frames** (examples):
  - `0x112`: Requested boost PSI (u16, 0.1 psi) with mode, fuel, WMI status, traction profile, timestamp.
  - `0x116`: AWC/ATC/eTRAC profile (slip %, gains, wheelie pitch target, torque rate).
  - `0x118`: Flame-mode request, launch control arm, Air Shot fire, brightness.
  - `0x11A`: Mode change with reason code.
  - `0x11C`: POST request with 2 s response window requiring ACK.
- **Pi → MS3 frames** (examples):
  - `0x120`: Timing bias, soft torque cut request, boost ceiling PSI.
  - `0x122`: Fuel-map selector, AFR bias, launch RPM target.
- **Arduino/MS3 → Pi frames** (examples): telemetry including RPM, boost, AFRs, spark, temps, pressures, battery voltage, knock counts, duty cycles, gear, TPS; wheel speeds, IMU, slip %, wheelie flags; Air Shot and WMI status; POST results heartbeat; fault codes.
- **Timeouts & fallbacks**:
  - Loss of MS3 data > 200 ms: HUD banner “ECU LINK LOST”, Pi stops performance requests, commands Safe Mode to Arduino.
  - Loss of Arduino heartbeat > 200 ms: HUD banner “CONTROL LINK LOST”, Pi orders MS3 conservative boost ceiling and shows Limp overlay.
  - WMI requested but flow low for 250 ms: drop requested boost and display fault banner.

## 3. State Machines (Brains)
- **Top-level modes**: ECO, NORMAL, SPORT, RACE, ALBATROSS.
- **Sub-states**: BOOT → POST → READY → DRIVE → LIMP → SHUTDOWN; transient states include LAUNCH_ARMED, LAUNCH_ACTIVE, FLAME_ACTIVE.
- **Mode parameters**: per-mode boost caps, throttle shaping, AWC/ATC aggressiveness, HUD brightness, flame/launch enablement.
- **eTRAC selector**: chooses traction profile (DRY, DAMP, RAIN, COLD, GRAVEL) via weather/temp/GPS cues, defining slip targets, gains, wheelie pitch window, torque ramp rates.
- **Fuel logic**: HUD fuel selection enforces max boost caps, timing bias windows, WMI strategy; Pi enforces caps and distributes to Arduino/MS3.
- **Launch control**: arming requires clutch/temperature/gear/knock conditions; per-mode RPM setpoint with HUD messaging.
- **Safety escalations**: knock bursts trigger timing pull and boost reduction; persistent issues enter LIMP; high EGT/thermal load reduces requests and triggers “TURBO HOT” banner.

## 4. HUD Visual Design & Rendering (Pygame)
- Retro aesthetic with pixel fonts (amber/orange) on black background and subtle scanlines.
- Boot flicker and POST scroll (“FUEL INJECTION SYSTEM… OK”).
- 60 FPS target with pre-rendered static assets and cached text surfaces.
- **Layout**:
  - Top bar: mode, fuel icon, time, ambient temp, GPS lock, rain badge.
  - Primary cluster: RPM bar with numeric RPM and “SHIFT!” badge ≥10k; speed, gear; boost gauge with target and duty %, overboost warning; AFR/timing panel with knock light; temperatures/pressures (coolant, oil temp, oil pressure, battery V, IAT, EGT); Air Shot indicators; WMI metrics and fault lamp; eTRAC/AWC slip bars, wheelie indicator, intervention icons; scrolling message line; GL sprite reacting to conditions.
- **Mode-specific layouts**: ECO (economy emphasis), SPORT (boost/temps focus), RACE (lap timer, G-meter, slip bar), ALBATROSS (flame icon, warnings, bold tach).
- **Brightness/night modes**: auto-dim via ambient sensor/time with manual override; night adds subtle starfield.
- **Performance**: pre-render static grids/labels; cache text by value buckets; use integer scaling and dirty rectangles where applicable.

## 5. Input Handling
- Physical buttons (mode, confirm, back, optional joystick); NFC for rider presets; touch with large targets; Bluetooth for weather/GPS/time sync and lap triggers.
- Debounced inputs at 200 Hz with long-press requirements (≥1 s above 3 mph) for mode changes.
- Air Shot firing requires two-step confirmation and safety conditions.

## 6. Pi-Side Calculations
- **Boost target**: derived from fuel, WMI health, mode, IAT with derates for knock, injector duty limits, WMI failures, high EGT, coolant/oil over-temp.
- **eTRAC profile**: weather + sensors select traction profile; GPS/sensor fusion can switch to GRAVEL/ROUGH.
- **Timing bias**: suggest advance for high-octane fuels with clean knock history; otherwise neutral/retard.
- **Launch setpoint**: mode-based and conditioned on temps/pressures.
- **Fuel prompts**: detect refuel events (GPS + fuel level change) and prompt for fuel type updates.

## 7. Logging & Black Box
- **Realtime logs**: to SD (CSV/binary) capturing all CAN channels at 20–50 Hz with per-ride rotation and fsync cadence.
- **Black box**: 30 s RAM ring buffer at 100 Hz for critical channels, persisted on faults/shutdown.
- **Fields**: comprehensive engine, traction, intervention, electrical, fuel, mode, and command data.
- **Export**: USB mass-storage or Wi-Fi share on demand.

## 8. Audio UX
- Retro voice (“Power On Self Test… OK”) and minimal alert sounds for knock, overheat, low oil pressure, WMI fault, CAN fault.
- Launch-armed tone and “SHIFT!” ping at 10k.
- Cool-down periods to avoid spam; duck other audio on critical alerts.

## 9. Configuration System
- YAML/JSON files (`modes.yaml`, `fuels.yaml`, `etrac.yaml`, `canmap.yaml`, `ui.yaml`).
- Runtime edits via settings menu with schema validation and atomic swaps.
- Rider presets stored and linked to NFC tags.

## 10. POST & Diagnostics
- 3–5 s power-on self-test sequence verifying filesystem, RTC, CPU temp.
- Sends POST request `0x11C`; waits for Arduino/MS3 module status, sensor checks, actuator tests.
- Displays pass/fail summary; critical failures block DRIVE (LIMP override optional).
- On-ride diagnostics: graph pages (boost vs RPM, AFRs, knock, slip) and fault detail view referencing last 30 s snapshot.

## 11. Safety & Fail-Safes
- Thread watchdog heartbeats; supervisor forces LIMP UI on failure.
- Sensor plausibility checks enforce conservative defaults.
- Immediate derates for WMI failures; Air Shot safety gates (pressure, temps, lean angle, traction status).
- Throttle-by-wire supervision with plausibility checks and fast stop commands on mismatch.

## 12. Pygame Architecture & Project Layout
- Directory structure with modules for CAN, state, HUD widgets, IO, logging, audio, config, tools.
- Renderer pattern: pre-render static layers; widgets draw from immutable `StateSnapshot`.
- Bitmap fonts with pre-rendered numeric atlases; minimal timers; capped animation update rates.

## 13. Testing & Simulation
- `tools/sim_can.py` provides bench simulation from logs or synthetic sweeps.
- Unit tests for CAN encode/decode and derate logic.
- Hardware-in-the-loop bench with CAN USB dongle and Arduino simulator.

## 14. OTA & Security
- Signed `.tar.zst` update bundles; signature verification prior to apply.
- Config backups for rollback; optional PIN for Settings/Flame mode.
- Reject unsigned firmware over BLE/Wi-Fi.

## 15. Done-Done Checklist
- SocketCAN scripts; verified scaling; state machine/mode enforcement; POST exchange with HUD feedback; WMI fail-safe; Air Shot gating/logging; eTRAC selection; shift banner; brightness control; black box dump; audio cues; bench sim achieving 60 FPS and <40% CPU.

## 16. Phase 2 Nice-to-Haves
- Lap timer with GPS splits and track map.
- Theme variants (amber default, teal service mode).
- On-device graph viewer with pinch zoom (if touch).
- “Dyno view” page with enlarged gauges for tuning.
