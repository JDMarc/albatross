# Albatross Wiring And Pinout Checklist

This is the current wiring map implied by the code. It is intended as a harness
planning checklist, not as a substitute for the MS3Pro Mini manual, the Teensy
4.1 pinout, or the datasheets for the exact CAN, relay, driver, and sensor
modules installed on the bike.

## CAN Backbone

Use one 500 kbit/s CAN backbone shared by:

- MS3Pro Mini
- Raspberry Pi CAN interface
- Teensy 4.1 controller CAN transceiver
- Any future CAN sensor modules

Wire the bus as a trunk with short stubs, not as a star.

| Signal | Hookup |
| --- | --- |
| CANH | CANH on MS3Pro Mini, Pi CAN HAT/interface, Teensy CAN transceiver |
| CANL | CANL on MS3Pro Mini, Pi CAN HAT/interface, Teensy CAN transceiver |
| Ground reference | Common chassis/sensor ground between non-isolated CAN nodes |
| Termination | 120 ohm at exactly the two physical ends of the CAN trunk |

Only two devices on the entire bus should have termination enabled. Many CAN
HATs and transceiver breakout boards include a 120 ohm resistor or jumper;
remove/disable extras once the final physical bus ends are known.

For Windows bench testing with a CANable running SLCAN firmware, connect the
CANable to the same CANH/CANL backbone and run:

```text
py -3.12 can_demo_controls.py --canable COM5
```

Replace `COM5` with the port shown in Windows Device Manager. The shortcut is
equivalent to `--interface slcan --channel COM5 --bitrate 500000`. If the
adapter is running a different firmware/backend, use the lower-level python-can
flags instead, for example `--interface pcan --channel PCAN_USBBUS1` for a PEAK
adapter.

## Raspberry Pi CAN

The Pi has no native CAN controller, so use SocketCAN through one of these:

1. A quality MCP2515-based CAN HAT.
2. A better isolated CAN HAT, preferred for a permanent motorcycle harness.
3. A SocketCAN-compatible USB-CAN adapter for bench work or temporary testing.

Typical MCP2515 HAT wiring, if not using a fully pinned HAT:

| Pi signal | Physical pin | Connects to |
| --- | ---: | --- |
| 3.3 V | 1 or 17 | CAN controller logic power, if board expects 3.3 V |
| GND | 6, 9, 14, 20, 25, 30, 34, or 39 | CAN interface ground |
| GPIO10 / SPI0 MOSI | 19 | MCP2515 SI |
| GPIO9 / SPI0 MISO | 21 | MCP2515 SO |
| GPIO11 / SPI0 SCLK | 23 | MCP2515 SCK |
| GPIO8 / SPI0 CE0 | 24 | MCP2515 CS, common default |
| GPIO25 | 22 | MCP2515 INT, common default |
| CANH/CANL | HAT screw terminal | CAN backbone |

Typical Raspberry Pi OS setup:

```ini
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=23
dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=25
```

Then bring the interface up:

```sh
sudo ip link set can0 up type can bitrate 500000
sudo ip link set can1 up type can bitrate 500000
```

Use the oscillator value printed for the exact HAT. The Waveshare 2-CH CAN HAT
uses 16 MHz MCP2515 oscillators and defaults CAN0 INT to GPIO23 and CAN1 INT to
GPIO25. See `deploy/config.txt.waveshare-2ch-can.fragment` and
`docs/pi_deployment.md`.

## Raspberry Pi Controlled Shutdown

The external Pi power supply must remain latched on after key-off long enough
for Linux to halt cleanly. Merge `deploy/config.txt.power.fragment` into the Pi
boot configuration after checking the CAN HAT pin use:

| Pi signal | Physical pin | Connects to |
| --- | ---: | --- |
| GPIO17 | 11 | Active-low shutdown request from ignition-off supervisor or pushbutton circuit |
| GPIO27 | 13 | External power latch/supervisor safe-to-remove-power input |

GPIO27 changes state only after Linux has halted. The external latch should
remove Pi power then, with a bounded timeout fallback. Protect the Pi supply
with fused input power, reverse-polarity protection, automotive transient
suppression, and a suitable DC/DC converter. See `docs/power_nfc_watchdogs.md`.

## MS3Pro Mini CAN Hookup

The MS3Pro Mini pinout uses:

| MS3Pro Mini pin | Signal | Connects to |
| ---: | --- | --- |
| 24 | CAN Low | CANL backbone |
| 25 | CAN High | CANH backbone |
| 21 | Sensor ground | Sensor returns as required by MS3 wiring plan |
| 22, 23 | Power grounds | Engine/chassis ground per MS3 wiring plan |

Project ownership assumptions:

- MS3 owns RPM, TPS, MAP/boost, AFR, knock, coolant, IAT, EGT if fitted,
  battery voltage, oil pressure, oil temperature, flex fuel, fuel level if
  wired there, and injector pulse width/duty telemetry.
- Teensy owns wheel speed, WMI tank/flow/status, light-status sensing, Air Shot
  hardware, compressor relay, and boost control. It directly commands the
  electronic wastegate actuator power stages; there is no separate boost
  controller module.
- Pi owns HUD/settings decisions and publishes boost target, mode, fuel profile,
  spark table select, NFC/start authority, and safety requests. WMI is
  automatic on the Teensy; the old Pi WMI-enable frame is legacy-only.

## Teensy 4.1 CAN Interface

The production controller sketch targets a Teensy 4.1 using native CAN1 through
an external 3.3 V CAN transceiver. Teensy pins are not CANH/CANL directly.

| Teensy pin | Signal | Connects to |
| --- | --- | --- |
| 22 | CAN1 RX | Transceiver RXD |
| 23 | CAN1 TX | Transceiver TXD |
| 3.3 V | Logic power | 3.3 V transceiver VCC if required |
| GND | Ground | Transceiver ground and common reference |
| CANH/CANL | Bus pair | Transceiver CANH/CANL to CAN backbone |

Use a 3.3 V-compatible CAN transceiver. Do not connect Teensy pins directly to
the CAN bus, and do not feed 5 V logic into Teensy pins.

## Teensy 4.1 Harness Pinout

| Teensy pin | Direction | Function | Hookup notes |
| --- | --- | --- | --- |
| 2 | Output PWM | Wastegate actuator 1 PWM | To actuator power driver/H-bridge command input |
| 3 | Output | Wastegate actuator 1 direction | To actuator power driver/H-bridge direction input |
| 4 | Output | Wastegate actuator 1 enable | To actuator power driver/H-bridge enable input |
| 5 | Output PWM | Wastegate actuator 2 PWM | To actuator power driver/H-bridge command input |
| 6 | Output | Wastegate actuator 2 direction | To actuator power driver/H-bridge direction input |
| 9 | Output | Wastegate actuator 2 enable | To actuator power driver/H-bridge enable input |
| 10 | Output PWM | WMI pump command | Drive relay/MOSFET module, active high |
| 11 | Output | Flame mode interlock | Drive external interlock circuit, active high |
| 12 | Output | Air Shot solenoid | Drive MOSFET/relay, active high |
| 24 | Output | Air compressor relay | Drive relay/MOSFET module, active high |
| 18 | Input pullup | Front wheel Hall sensor | Open collector/open drain or conditioned 3.3 V pulse |
| 19 | Input pullup | Rear wheel Hall sensor | Open collector/open drain or conditioned 3.3 V pulse |
| 20 | Input pullup | WMI flow sensor | Pulse input, 450 pulses/L default |
| 25 | Input pullup | Neutral switch/lamp | Active low; condition to 3.3 V |
| 26 | Input | Left indicator lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 27 | Input | Right indicator lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 28 | Input | High beam lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 29 | Input | Brake lamp sense | Condition bike voltage to 3.3 V logic, external pulldown |
| 30 | Input | Stock oil warning lamp sense | Status only; not the real oil pressure gauge path |
| 31 | Input pullup | WMI pressure/status OK | Active low by default; switch pulls to ground when OK |
| A0 | Analog input | Fallback oil pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |
| A1 | Analog input | WMI tank level | 0-5 V analog sender scaled to 0-3.3 V |
| A2 | Analog input | Air Shot tank pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |

Air Shot compressor relay behavior is buffer-based in firmware: it starts only
when the bike is stationary, throttle is low, the engine is not cranking,
voltage is healthy, no undervoltage/limp report is active, tank pressure is at
or below 95 psi, and its restart delay has expired. It stops at 145 psi or as
soon as any inhibit appears.

## Electrical Protection Notes

- Do not connect 12-14 V bike lamp feeds directly to Teensy pins. Use an
  optocoupler, automotive digital input conditioner, or divider plus clamp/TVS
  and a known pulldown.
- Do not connect 5 V logic to Teensy pins. Teensy 4.1 GPIO and ADC pins are
  3.3 V only and are not 5 V tolerant.
- Do not drive relays, solenoids, pumps, compressor motors, or wastegate motors
  directly from Teensy pins. Use fused power, a driver/MOSFET/relay module, and
  flyback suppression for inductive loads.
- Hall and flow inputs should present clean 0-3.3 V logic to the Teensy. The
  sketch enables internal pullups on those inputs.
- Analog inputs must stay inside 0-3.3 V. Add filtering and input protection
  for anything exposed to the motorcycle harness.
- For the production bike, oil pressure and oil temperature should be wired to
  the MS3Pro Mini. Teensy A0 is only retained as a fallback path if ECU CAN oil
  pressure is unavailable during bench testing.

## Current CAN ID Ownership

The Python enum names still use `Arduino` for compatibility, but the production
controller is now Teensy 4.1.

| Range / ID | Owner | Purpose |
| --- | --- | --- |
| 0x100-0x10F | MS3/ECU to HUD/controller | Engine telemetry, fuel/flex, injector data, optional left/right boost |
| 0x110-0x112 | MS3/ECU to controller | Flame, WMI trigger, engine status |
| 0x120-0x129 | Pi to controller | Boost target, mode, limp, traction, Air Shot request, WMI, fuel type |
| 0x12A-0x12B | Controller to MS3/ECU | Torque cut and traction slip requests |
| 0x130-0x13F | Controller to HUD | Air Shot, wheel speed, WMI, lights, traction, fallback statuses, service sensor voltages |
| 0x140 | Pi to controller | NFC authorization |
| 0x145-0x147 | Controller to HUD | Service pin/relay states, firmware version, limp status |
| 0x150-0x152 | Pi to MS3/ECU | Fuel profile select, spark table select, rev limiter strategy |
| 0x1F0-0x1F1 | System | POST request/response |

## Legacy Mega 2560

The old Arduino Mega 2560 + MCP2515 firmware remains in
`arduino/legacy/mega2560/albatross_controller/`. It is not the production
target anymore.
