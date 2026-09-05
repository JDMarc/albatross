# CAN demo controls

Start `python main.py` without a CAN interface or simulator, then run
`python can_demo_controls.py --dry-run` in another terminal from the repository root.
Dry-run prints CAN frames instead of transmitting them, but intentionally sends
local UDP demo data to the HUD. The HUD uses the production telemetry decoders.

The original ECU/bike controls remain in the first tab. Additional tabs provide:

- **Dynamics:** independent TCS/AWC levels, throttle-curve selection, torque limits,
  wheel speeds, pitch/lean/rate, traction and wheelie confidence, DBW target/actual,
  weather, engineering fingerprint match, all dynamics fault bits, and presets
  for controlled lift, rear slip, combined intervention, touchdown and shutdown.
- **Air Shot V2:** OFF/MANUAL/AUTO, state/reason/profile, pressure, valve outputs,
  shadow outputs, event history fields, compressor and driver faults, and simulated
  configuration acknowledgements.
- **Thermal:** all 32 channels, 12 scenarios, per-channel temperature/status/raw
  diagnostic overrides, heartbeat, fault summaries and configuration identity.

Pause each subsystem's telemetry to exercise stale-data warnings. Temperature
overrides use Celsius, dynamics speeds use metres/second, angles use degrees,
and slip/confidence/torque fields use percent. Preset values and raw diagnostics
are synthetic test data, not motorcycle calibration recommendations.

## Hardware command boundary

Use a physically isolated test CAN bus. Synthetic telemetry can impersonate real
nodes; do not connect this generator to an operating motorcycle powertrain.
Existing CAN adapter options remain available (`--help`).

Command transmission is disabled by default. Explicitly enabling the shared HUD
command checkbox enables the existing legacy command behavior and the new buttons
for dynamics settings, rider envelopes, Air Shot mode and hold-to-fire requests.
Held fire refreshes while held and releases on mouse release, leaving the button,
disabling commands, or normal application close. Controller timeouts are still
required for process crashes or link loss.

The latched powertrain-stop button requires an additional confirmation. There is
no reset/bypass button, direct DBWX2 motor-target output, engineering calibration
upload, or raw RaceGrade/DBWX2 sensor spoofing. Simulated calibration-valid and ACK
fields only change displayed telemetry; they do not commission or acknowledge
real hardware. Curve selection uses the existing local engineering configuration;
it does not fill in uncalibrated throttle maps.

Run `python tests/run_can_demo_checks.py` to test encoder/decoder round trips,
telemetry filtering and the withdrawn Tk panel with CAN/network mocked out.
