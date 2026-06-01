# Power, NFC, And Watchdogs

This document defines the production hardware contract around the Pi and
Teensy. The software provisions are implemented, but they do not replace the
external protected power stage or a hardwired motorcycle kill switch.

## Automatic WMI

WMI is demand-driven. It does not require a rider-facing arm switch.

The Teensy enables its WMI pump only when all of these are true:

- NFC authorization is valid for the current power cycle.
- Neither limp mode nor a stale Pi command link is active.
- Requested or measured boost is at least 6 psi.
- RPM is above 3300 and TPS is above 38%.

The pump command is proportional to boost, target boost, engine load, RPM, and
the selected fuel's WMI dependence. The legacy Pi `0x128` WMI-arm frame remains
decoded for old bench tools, but no longer gates normal WMI operation. The ECU
`0x111` WMI trigger remains accepted as an additional compatibility trigger.

## USB NFC Start Authorization

Use a USB serial/CDC NFC reader that emits one tag value per line. Keyboard
wedge readers need a USB-HID adapter layer and are not handled by the current
runtime.

Create `settings/nfc_auth.json`:

```json
{
  "reader_device": "/dev/ttyACM1",
  "allowed_tag_sha256": [
    "replace_with_sha256"
  ]
}
```

Generate a hash from the exact line emitted by the reader:

```sh
py -3.12 tools/hash_nfc_tag.py TAG_VALUE
```

At startup the Pi repeatedly publishes NFC authorization (`0x140`) and the
engine-run switch (`0x127`) every 250 ms. Engine-run remains OFF until an
allowed tag has been scanned. Authorization latches only for the current
runtime/power cycle. The Teensy also treats missing NFC authorization as a
local limp condition, disabling boost, flame mode, WMI, and Air Shot.

The MS3 must map Pi `0x127` to a run/start inhibit input. This network inhibit
is an additional layer. Retain a physical hardwired kill switch that can stop
fuel and ignition without the Pi, Teensy, or CAN bus.

For bench testing only, `pi_main.py --nfc-bypass` permits startup without a
reader. Do not use that flag on the installed bike.

## CAN Freshness

The Pi tracks real RX timestamps independently:

- MS3 telemetry frames `0x100`-`0x10F`
- Teensy status frames `0x130`-`0x13F` and `0x145`-`0x147`

Local Pi TX echoes and unrelated frames do not refresh these clocks. The Pi
safety supervisor reacts after 500 ms; the HUD raises its rider-facing stale
banner after 1.5 seconds. The Teensy independently enforces its own ECU and Pi
command timeouts.

## Watchdogs

The production Teensy sketch uses the `Watchdog_t4` library with a two-second
hardware reset threshold. Install `Watchdog_t4` alongside `FlexCAN_T4` before
building. On reset, setup immediately drives wastegate enables, WMI, flame,
Air Shot, and compressor outputs inactive. External driver inputs must also
have physical pulldowns so reset or disconnected-controller states are safe.

The Pi service uses `Type=notify`, `NotifyAccess=all`, and `WatchdogSec=5`.
`main.py` sends watchdog notifications from the render loop. If rendering
hangs, systemd restarts the full HUD process.

## Controlled Pi Shutdown Hardware

Merge `deploy/config.txt.power.fragment` into `/boot/firmware/config.txt` after
checking CAN-HAT pin use:

- GPIO17 accepts an active-low shutdown request from the ignition-off
  supervisor or pushbutton circuit.
- GPIO27 goes high after Linux has halted. Feed it to the external power latch
  or supervisor as the "safe to remove Pi power" signal.

The external Pi supply should include:

- A fused ignition-switched input and separate fused battery feed where needed.
- Reverse-polarity protection.
- Automotive TVS/transient suppression and a DC/DC converter selected for
  motorcycle charging-system transients.
- A latch, timer, or supervisor that keeps the Pi powered after key-off until
  GPIO27 indicates halt complete, with a bounded timeout fallback.
- Enough hold-up time for a controlled shutdown. Size this from measured Pi,
  display, and CAN-HAT current rather than assuming a capacitor value.

The runtime also requests an orderly `systemctl poweroff` if the stopped,
stationary bike remains below 11.8 V for 15 seconds. The GPIO overlay path is
still required for normal key-off shutdown.

## Update Recovery

Pi overlay updates preserve a versioned app backup. A new update must keep the
HUD render loop alive through POST and 15 seconds of runtime. If two startup
attempts fail to confirm health, `pi_main.py` restores the backup overlay on
the next launch. This is application-level automatic rollback, not a full
dual-partition OS image. A future full filesystem A/B scheme can build on the
same health-confirmation marker.
