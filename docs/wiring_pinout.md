# Albatross Wiring And Pinout Checklist

This is the current wiring map implied by the code. It is intended as a harness
planning checklist, not as a substitute for the MS3Pro Mini manual, the Teensy
4.1 pinout, or the datasheets for the exact CAN, relay, driver, and sensor
modules installed on the bike.

Reviewed against the current firmware and thermal configuration 2.0.0.
Companion references: [complete CAN ID table](can_id_reference.md),
[thermal wiring pack](thermal_wiring.md), [bench-only interface](bench_hud.md).
A listed pin is a software allocation, not proof that the driver, protection,
connector or sensor calibration is installed or verified.

## CAN Backbone

Use one 500 kbit/s CAN backbone shared by:

- MS3Pro Mini
- Raspberry Pi CAN interface
- Teensy 4.1 controller CAN transceiver
- Second Teensy 4.1 thermal-node CAN transceiver
- DBWX2 throttle controller and RaceGrade 6-Axis CAN IMU
- Any future CAN sensor modules

Wire the bus as a trunk with short stubs, not as a star.

| Signal | Hookup |
| --- | --- |
| CANH | CANH on MS3Pro Mini, Pi CAN HAT/interface, both Teensy transceivers, DBWX2 and IMU |
| CANL | CANL on MS3Pro Mini, Pi CAN HAT/interface, both Teensy transceivers, DBWX2 and IMU |
| Ground reference | Common chassis/sensor ground between non-isolated CAN nodes |
| Termination | 120 ohm at exactly the two physical ends of the CAN trunk |

Only two devices on the entire bus should have termination enabled. Many CAN
HATs and transceiver breakout boards include a 120 ohm resistor or jumper;
remove/disable extras once the final physical bus ends are known.

For Windows HUD testing with a CANable running SLCAN firmware, use an isolated
test CANH/CANL backbone. The demo impersonates live nodes; do not connect its
synthetic telemetry to an operating powertrain. Run:

```text
py -3.12 can_demo_controls.py --canable COM5
```

Replace `COM5` with the port shown in Windows Device Manager. The shortcut is
equivalent to `--interface slcan --channel COM5 --bitrate 500000`. If the
adapter is running a different firmware/backend, use the lower-level python-can
flags instead, for example `--interface pcan --channel PCAN_USBBUS1` for a PEAK
adapter. If Device Manager names the CANable as `gs_usb`, use
`py -3.12 can_demo_controls.py --candlelight` instead of a COM port.

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

The table above is a GENERIC single-controller example. For the project's
Waveshare 2-CH template, use the following separate CS/interrupt allocation;
do not combine its interrupts with that example:

| HAT channel | Chip select | Interrupt | Physical pins |
| --- | --- | --- | --- |
| CAN0 | GPIO8 / CE0 | GPIO23 | CS24, INT16 |
| CAN1 | GPIO7 / CE1 | GPIO25 | CS26, INT22 |

Both controllers share SPI MOSI/MISO/SCLK. Two Pi CAN ports do not require two
motorcycle buses; avoid attaching two active demo publishers to one backbone.

Repository Raspberry Pi OS template:

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

The existing project MS3Pro Mini connector reference is below. Confirm it
against the exact unit/manual before terminating a harness; the hardware
revision has not been established here. Do not apply it to a MicroSquirt
connector merely because the product names are similar:

| MS3Pro Mini pin | Signal | Connects to |
| ---: | --- | --- |
| 24 | CAN Low | CANL backbone |
| 25 | CAN High | CANH backbone |
| 21 | Sensor ground | Sensor returns as required by MS3 wiring plan |
| 22, 23 | Power grounds | Engine/chassis ground per MS3 wiring plan |

Project ownership assumptions:

- MS3 owns engine/fueling protection and engine telemetry. Retain its independent
  coolant, IAT and oil-temperature sensors; ECU replacement inputs from the
  thermal node have not been commissioned. Oil pressure remains ECU-owned.
- The dedicated thermal Teensy supplies primary HUD/main temperature data:
  18 NTCs, seven PT1000s, four K-type probes. Old main-controller temperature
  inputs are retired; do not reconnect them as duplicate thermistor loads.
- DBWX2 owns dual APS/TPS checks and the throttle motor inner loop; the main
  Teensy supplies supervised position demand. Main A0 is not an APS/TPS input.
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
| 22 | CAN1 TX | Transceiver TXD |
| 23 | CAN1 RX | Transceiver RXD |
| 3.3 V | Logic power | 3.3 V transceiver VCC if required |
| GND | Ground | Transceiver ground and common reference |
| CANH/CANL | Bus pair | Transceiver CANH/CANL to CAN backbone |

Use a 3.3 V-compatible CAN transceiver. Do not connect Teensy pins directly to
the CAN bus, and do not feed 5 V logic into Teensy pins.

## Main Teensy 4.1 Harness Pinout

Four Air Shot V2 valve PWM pins are installation configuration, not fixed entries
in this table. Assign intake L/R and turbine L/R drivers through the validated
Air Shot configuration; see [Air Shot V2](airshot_v2.md). FIRE and the three-position
mode switch normally connect to the Pi's USB grip controller, not new Teensy inputs.

### Main board fixed pins

| Teensy pin | Direction | Function | Hookup notes |
| --- | --- | --- | --- |
| 2 | Output PWM | Wastegate actuator 1 PWM | To actuator power driver/H-bridge command input |
| 3 | Output | Wastegate actuator 1 direction | To actuator power driver/H-bridge direction input |
| 4 | Output | Wastegate actuator 1 enable | To actuator power driver/H-bridge enable input |
| 5 | Output PWM | Wastegate actuator 2 PWM | To actuator power driver/H-bridge command input |
| 6 | Output | Wastegate actuator 2 direction | To actuator power driver/H-bridge direction input |
| 9 | Output | Wastegate actuator 2 enable | To actuator power driver/H-bridge enable input |
| 10 | Output PWM | WMI pump command | Drive relay/MOSFET module, active high |
| 11 | Unassigned | No dedicated flame output | Flame intent remains on CAN |
| 12 | Output, active high | Master NC Air Shot isolation driver | Reserved; LOW at boot. External protected driver/pulldown required; not available to the four performance valves |
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
| A0 / 14 | Analog input | Fallback oil pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |
| A1 / 15 | Analog input | WMI tank level | 0-5 V analog sender scaled to 0-3.3 V |
| A2 / 16 | Analog input | Air Shot tank pressure | 0.5-4.5 V sender scaled to about 0.33-3.0 V at Teensy |

### Air Shot wiring not yet assigned

The planned five-valve system uses one on/off NC master and four proportional
metering valves. A post-master four-port distribution block supplies two
three-port branch splitters and a pressure sensor. See the
[valve shortlist and priming/wiring plan](airshot_valve_selection.md).
This sensor measures common manifold pressure, not individual branch flow or
verified master closure. Its hardware input and priming thresholds remain
unassigned; the controller precharge sequence stays disabled until these
engineering settings and the post-master sensor location are commissioned.

Four performance-valve PWM pins remain installation configuration in
config/airshot_v2.json, not arbitrary free pins. Current validation excludes
the fixed main pins, analog aliases 14/15/16, CAN22/23, and reserved pin 12.
It also checks PWM capability, duplicates and shared timer frequencies.
Do not wire valves from a list of apparently unused numbers.

- Main pin 12 -> active-high protected driver -> master NC valve coil.
  Use an external pulldown, fused coil supply and suitable suppression.
  Plumbing: tank -> regulator -> master NC -> four performance valves.
- config/fault_manager.json ships with master_air_isolation.pin null and
  driver_verified false. Pin 12 is allocated but not commissioned/enabled.
  After hardware verification, set the documented configuration and regenerate
  the fault configuration before rebuilding. Physical closure feedback is not
  implemented; commanded LOW is not proof of isolation.
- Regulated-pressure feedback (CAN 0x193), EWG command/position feedback
  (0x194), and four valve-current/fault feedback frames (0x198-0x19B) need
  actual hardware publishers. No regulator ADC pin or current-monitor pin map
  has been supplied for those external devices.
- The OFF/MANUAL/AUTO switch and FIRE button go to the Pi USB grip controller.
  Optional local FIRE/service inputs default to -1 (not connected).
- Compressor pin 24 controls a rated relay/driver only. An independent pneumatic
  kill must isolate stored air, not merely stop the compressor.

Air Shot compressor relay behavior is buffer-based in firmware: it starts only
when the bike is stationary, throttle is low, the engine is not cranking,
voltage is healthy, no undervoltage/limp report is active, tank pressure is at
or below 95 psi, and its restart delay has expired. It stops at 145 psi or as
soon as any inhibit appears.

## Dedicated thermal Teensy: complete board/bus allocation

**Thermal configuration 2.0.0 implements the Rev B harness.** See the
[Revision C wiring pack](thermal_wiring.md): five ADS1115s on two I2C buses and seven
MAX31865 PT1000 boards. Hardware commissioning is still required.

The second Teensy has its own transceiver and shares the CAN backbone with the
main Teensy, Pi, ECU, DBWX2 and RaceGrade IMU. Both boards use TX 22 / RX 23,
but these are separate local pins. Thermal SPI uses MOSI 11 / MISO 12 / SCK 13;
MAX31856 selects are 10,9,8,7; MAX31865 selects are 2,3,4,5,6,14,15.
ADS1115 Wire SDA18/SCL19 hosts 0x48/0x49/0x4A; Wire1 SDA17/SCL16 hosts 0x48/0x49.
See the [firmware README](../arduino/README.md#dedicated-thermal-teensy-pin-map)
for every thermal sensor's front-end/channel assignment and power/conditioning notes.

### Thermal power and sensor rules

| Thermal node connection | Assignment |
| --- | --- |
| MOSI / MISO / SCK | 11 / 12 / 13, shared by eleven SPI front ends |
| TC0-TC3 CS | 10 / 9 / 8 / 7 |
| R0-R6 PT1000 CS | 2 / 3 / 4 / 5 / 6 / 14 / 15 |
| N0 / N1 / N2 ADS1115 | Wire SDA18/SCL19; 0x48 / 0x49 / 0x4A |
| N3 / N4 ADS1115 | Wire1 SDA17/SCL16; 0x48 / 0x49 |
| CAN1 TX / RX | 22 / 23, through its own transceiver |
| VIN / GND | Protected regulated 5 V; isolate VUSB for simultaneous USB power |
| Breakout supply | Independently budgeted 3.3 V rail -> ADS VDD and MAX VIN; MAX 3Vo unconnected |

N0/N3 ADDR -> GND; N1/N4 ADDR -> VDD; N2 ADDR -> its own SDA.
NTC IDs 5-19,22,23,29 occupy N0.A0 through N4.A1 in that order.
N4.A2 measures nominal 3.3 V excitation; N4.A3 is unused and not sampled.
R0-R6 serve IDs 20,21,24,25,26,27,28. IDs30-32 remain disabled.

PT1000 boards are the 4300-ohm-reference variant. Baseline two-wire jumpers tie
F+ to RTD+ and F- to RTD-. Do NOT connect RTD minus to SGND or add the old
external current source. NTCs use dedicated signal returns and measured
excitation. Keep I2C/SPI inside the acquisition enclosure. The
[10-sheet pack and wire schedule](thermal_wiring.md) contain individual probes,
connector-net labels, power constraints and commissioning holds.

## DBWX2, IMU and independent interlocks

DBWX2 connects the grip's redundant APS and throttle body's redundant TPS and
motor according to the verified device/donor pinouts. The current adapter
supervises channel 1 only. No Yamaha connector or independent-kill pin assignment
has been established in this repository. RaceGrade uses CAN, with its bitrate,
base ID and mounting transform verified as described in
[vehicle dynamics](vehicle_dynamics.md#installation-prerequisites).

PDM load channels, final wastegate actuator connectors/H-bridges, DBWX2
donor connector cavities, and independent kill/interlock components are not
fully specified. Do not infer those connections from a CAN message definition.
The separate powered-bench firmware/profile is not the on-bike pin map.

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

The complete [CAN ID reference](can_id_reference.md) replaces the former partial
range table. It includes thermal, Air Shot V2/configuration, VDC, fault management,
RaceGrade standard IDs and DBWX2 extended polling, with legacy/unused boundaries.

In particular, DBWX2's default broadcast base 0x100 conflicts with ECU RPM.
The adapter proposes 0x300; configure and verify the actual device before
connection. RaceGrade's proposed base is 0x470 (acceleration) / 0x471 (rates).
CAN interfaces must allow the 29-bit DBWX2 polling traffic as well as standard frames.

## Legacy Mega 2560

The old Arduino Mega 2560 + MCP2515 firmware remains in
`arduino/legacy/mega2560/albatross_controller/`. It is not the production
target anymore.
