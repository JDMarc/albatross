# CAN demo controls

Start `python main.py` without a CAN interface or simulator, then run
`python can_demo_controls.py --dry-run` in another terminal from the repository root.
Dry-run prints CAN frames instead of transmitting them, but intentionally sends
local UDP demo data to the HUD. The HUD uses the production telemetry decoders.

The first tab contains ECU/bike telemetry and an explicitly labelled ECU/HUD
command override. Retired Air Shot charges/firing/tank controls, legacy AWC/TCS
controls and torque/slip requests, duplicate turbo-pressure controls, and the
duplicate compressor relay checkbox have been removed. Use the V2/dynamics tabs.

The first tab's ECU coolant/IAT/oil temperatures represent independent ECU
telemetry. Change the Thermal tab channels to change primary HUD temperatures.
Legacy ECU EGT sliders/transmission have been removed. Thermal-node loss must
make primary temperatures unavailable rather than fall back to the ECU sliders.

Additional tabs provide:

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

Command transmission is disabled by default. Air Shot and dynamics have separate
opt-ins: enabling either does not transmit ECU/HUD commands or reset requested
boost, ride mode, fuel or engine-run state. Their buttons send explicit requests.
The first tab's repeat ECU/HUD override remains separate and intentionally sends
its displayed settings, including its boost target; leave it off for HUD-led tests.
Held fire refreshes while held and releases on mouse release, leaving the button,
disabling commands, or normal application close. Controller timeouts are still
required for process crashes or link loss.

The latched powertrain-stop button requires an additional confirmation. There is
no reset/bypass button, direct DBWX2 motor-target output, engineering calibration
upload, or raw RaceGrade/DBWX2 sensor spoofing. Simulated calibration-valid and ACK
fields only change displayed telemetry; they do not commission or acknowledge
real hardware. Curve selection uses the existing local engineering configuration;
it does not fill in uncalibrated throttle maps.

For a screen-only demonstration, use **Preview Firing (telemetry only)** in the
Air Shot tab. It sets consistent MANUAL/FIRING/request-accepted telemetry without
sending a FIRE command or altering boost settings. Ready/Inhibited/Off previews
are also available. A real FIRE request needs a controller to accept it; checking
the command opt-in alone must not produce FIRING. All previews remain synthetic
and must only be transmitted on an isolated bus.

Blank/nonfinite numeric edits pause only the affected Air Shot/dynamics stream;
other streams continue. Once corrected, that stream resumes automatically.
Basic ECU controls retain their previous synthetic value during an invalid edit,
reported in the status line. Command transmission pauses during invalid edits,
and a held FIRE request is released. CAN send errors do not prevent UDP delivery;
UDP errors do not stop subsequent timer cycles. The HUD also rejects malformed
demo packets without abandoning its receiving loop.

The central HUD panel now supplies context rather than duplicating its gauges:
ECO/NORMAL show economy, estimated range, trip and fuel used; SPORT shows a torque
limiter hint, boost gap, confidence-qualified rear slip and DBW tracking error;
RACE shows the limiter hint, boost gap, AFR L/R and permitted torque; ALBATROSS
shows the limiter hint, boost gap and last-shot duration/pressure usage.
Boost gap is measured boost minus the VDC-reported boost target (not the HUD
request). DBW error is actual minus target angle. Limiter hints use published
ceilings; ties read MULTIPLE and unaccounted/rate-limited reductions read
OTHER / RAMP. These observations add no new protection thresholds.
Offline V2/VDC fields show unavailable data instead of legacy fallback values.

System Vitals uses four cells. Two thermal readings dwell for four seconds:
the first prioritizes configured sensor faults, otherwise alternating normalized
heat/deviation and greatest signed temperature rise; the second scans other
configured sensors. Oil pressure is fixed, and battery/WMI tank/WMI flow rotate
in the remaining cell (WMI faults override that utility rotation). Names stay
stable during each dwell, while displayed values and validity update immediately.
This display ranking adds no protection thresholds, cannot suppress alerts, and
does not replace the full temperature view opened with Select.

Run `python tests/run_can_demo_checks.py` to test encoder/decoder round trips,
telemetry filtering and the withdrawn Tk panel with CAN/network mocked out.
