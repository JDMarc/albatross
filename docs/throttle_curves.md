# Rider throttle curves

The Dynamics menu offers COMFORT, ROAD, RESPONSE and 1:1. These map normalized
grip input to requested torque, before TCS/AWC, lean, engine and mode limits.
They do not map directly to throttle-motor angle. DBWX2 actuator maps, sensor
plausibility and all other engineering limits remain separate.

| Grip input | COMFORT | ROAD | RESPONSE | 1:1 |
| --- | --- | --- | --- | --- |
| 0% | 0% | 0% | 0% | 0% |
| 25% | 15% | 20% | 30% | 25% |
| 50% | 35% | 45% | 55% | 50% |
| 75% | 65% | 70% | 80% | 75% |
| 100% | 100% | 100% | 100% | 100% |

These are baseline rider-response shapes, not measured motor/engine calibration.
The firmware interpolates linearly between fixed grip knots. Curve 3 (1:1) is
built-in identity: requested torque equals normalized grip, subject to subsequent
limits. Its points are intentionally read-only. This does not bypass protection.

## Editing on the HUD

Focus TCS/AWC and Select to open Dynamics. On THROTTLE CURVE, Left/Right requests
a controller curve selection; Select opens CURVE POINTS. In the editor:

- Up/Down selects the curve selector, a point, RESET BASELINE or SAVE CALIBRATION SOURCE.
- Left/Right on CURVE chooses which curve to edit; switching curves discards the unsaved draft.
- Left/Right on the 25/50/75% grip rows changes requested torque by 1 percentage point.
- Endpoints stay at 0/100%. Points cannot cross adjacent points or leave 0–100%.
- Select on RESET BASELINE restores that curve's baseline into the draft.
- Select on SAVE CALIBRATION SOURCE atomically updates `config/vdc_engineering.json`.
- Back returns to rider controls. Editing/saving requires engine RPM zero and speed at most 1 mph.

Plots update immediately. A local preview is available without CAN or a matching
firmware fingerprint and is explicitly labeled as such. Curve selection for the
controller still requires configuration matching and uses the existing request/ACK.

## Applying saved calibration

Saving points does **not** upload them over CAN. It clears the local engineering
`validated` flag and marks the display configuration unconfirmed. Review the
complete engineering calibration before validating it; the baseline curves alone
cannot commission the motorcycle. Then, from the repository containing the saved file:

```sh
python tools/generate_vdc_config.py
python tools/generate_vdc_config.py --check
arduino-cli compile --fqbn teensy:avr:teensy41 arduino/teensy41/albatross_controller_teensy41
```

Flash the resulting main-controller firmware and deploy the identical engineering
JSON on the Pi. Restart the HUD so its telemetry service reloads the calibration
identity. No thermal-board update is needed for this change. Old main-controller
firmware does not accept curve index 3. Existing unmeasured engineering values
remain unset, and the shipped overall configuration remains unvalidated.

`python tests/run_curve_checks.py` verifies the editor's bounds, stopped gate,
source persistence, fixed identity points and four-option telemetry decoding.
