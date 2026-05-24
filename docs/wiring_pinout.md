# Albatross Wiring And Pinout Checklist

This is the current wiring map implied by the code. It is intended as a harness
planning checklist, not as a substitute for the MS3Pro Mini manual, the Arduino
Mega pinout, or the datasheets for the exact CAN, relay, driver, and sensor
modules installed on the bike.

## CAN Backbone

Use one 500 kbit/s CAN backbone shared by:

- MS3Pro Mini
- Raspberry Pi CAN interface
- Arduino Mega MCP2515 CAN interface
- Any future CAN sensor modules

Wire the bus as a trunk with short stubs, not as a star.

| Signal | Hookup |
| --- | --- |
| CANH | CANH on MS3Pro Mini, Pi CAN HAT/interface, Arduino MCP2515 module |
| CANL | CANL on MS3Pro Mini, Pi CAN HAT/interface, Arduino MCP2515 module |
| Ground reference | Common chassis/sensor ground between non-isolated CAN nodes |
| Termination | 120 ohm at exactly the two physical ends of the CAN trunk |

Only two devices on the entire bus should have termination enabled. Many
MCP2515 modules and CAN HATs include a 120 ohm resistor or jumper; remove/disable
extras once the final physical bus ends are known.

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
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
```

Then bring the interface up:

```sh
sudo ip link set can0 up type can bitrate 500000
```

Use the oscillator value printed for the exact HAT. Many Pi HATs are 16 MHz;
the Arduino MCP2515 module in this project is configured in firmware as 8 MHz.

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
- Arduino owns wheel speed, WMI tank/flow/status, light-status sensing, Air
  Shot hardware, compressor relay, and boost control. It directly commands the
  electronic wastegate actuator power stages; there is no separate boost
  controller module.
- Pi owns HUD/settings decisions and publishes boost target, mode, fuel profile,
  spark table select, WMI enable, and safety requests.

## Arduino Mega CAN Interface

The Arduino sketch targets a Mega 2560 Rev3 plus an MCP2515 CAN module at
500 kbit/s, with an 8 MHz MCP2515 oscillator.

| Mega pin | Signal | Connects to |
| --- | --- | --- |
| D10 | MCP2515 CS | MCP2515 CS input |
| D2 | MCP2515 INT | MCP2515 INT output, interrupt-capable |
| D50 | SPI MISO | MCP2515 SO |
| D51 | SPI MOSI | MCP2515 SI |
| D52 | SPI SCK | MCP2515 SCK |
| D53 | Hardware SS | Leave as output/high; do not use as module CS |
| 5V/GND | Module power | 5 V-compatible MCP2515 module power and ground |
| CANH/CANL | CAN transceiver | CAN backbone |

## Arduino Mega Harness Pinout

| Mega pin | Direction | Function | Hookup notes |
| --- | --- | --- | --- |
| D5 | Output PWM | Wastegate actuator 1 PWM | To actuator power driver/H-bridge command input |
| D22 | Output | Wastegate actuator 1 direction | To actuator power driver/H-bridge direction input |
| D23 | Output | Wastegate actuator 1 enable | To actuator power driver/H-bridge enable input |
| D6 | Output PWM | Wastegate actuator 2 PWM | To actuator power driver/H-bridge command input |
| D24 | Output | Wastegate actuator 2 direction | To actuator power driver/H-bridge direction input |
| D25 | Output | Wastegate actuator 2 enable | To actuator power driver/H-bridge enable input |
| D7 | Output PWM | WMI pump command | Drive relay/MOSFET module, active high |
| D8 | Output | Flame mode interlock | Drive external interlock circuit, active high |
| D9 | Output | Air Shot solenoid | Drive MOSFET/relay, active high |
| D27 | Output | Air compressor relay | Drive relay/MOSFET module, active high |
| D3 | Input pullup | Front wheel Hall sensor | Open collector/open drain or conditioned 5 V pulse |
| D18 | Input pullup | Rear wheel Hall sensor | Open collector/open drain or conditioned 5 V pulse |
| D26 | Input pullup | Neutral switch/lamp | Active low; switch pulls to ground when neutral |
| D28 | Input | Left indicator lamp sense | Condition bike voltage to 5 V logic, external pulldown |
| D29 | Input | Right indicator lamp sense | Condition bike voltage to 5 V logic, external pulldown |
| D30 | Input | High beam lamp sense | Condition bike voltage to 5 V logic, external pulldown |
| D31 | Input | Brake lamp sense | Condition bike voltage to 5 V logic, external pulldown |
| D32 | Input | Stock oil warning lamp sense | Status only; not the real oil pressure gauge path |
| D33 | Input pullup | WMI pressure/status OK | Active low by default; switch pulls to ground when OK |
| D19 | Input pullup | WMI flow sensor | Pulse input, interrupt-capable, 450 pulses/L default |
| A0 | Analog input | Fallback oil pressure | 0.5-4.5 V, 0-100 psi fallback/bench path only |
| A1 | Analog input | WMI tank level | 0-5 V analog sender, scaled 0-100% |
| A2 | Analog input | Air Shot tank pressure | 0.5-4.5 V, 0-200 psi sender; compressor relay turns off below tank rating |

## Electrical Protection Notes

- Do not connect 12-14 V bike lamp feeds directly to Arduino pins. Use an
  optocoupler, automotive digital input conditioner, or divider plus clamp/TVS
  and a known pulldown.
- Do not drive relays, solenoids, pumps, compressor motors, or wastegate motors
  directly from Arduino pins. Use fused power, a driver/MOSFET/relay module,
  and flyback suppression for inductive loads.
- Hall and flow inputs should present clean 0-5 V logic to the Mega. The sketch
  enables internal pullups on those inputs.
- Analog inputs must stay inside 0-5 V. Add filtering and input protection for
  anything exposed to the motorcycle harness.
- For the production bike, oil pressure and oil temperature should be wired to
  the MS3Pro Mini. Arduino A0 is only retained as a fallback path if ECU CAN oil
  pressure is unavailable during bench testing.

## Current CAN ID Ownership

| Range / ID | Owner | Purpose |
| --- | --- | --- |
| 0x100-0x10E | MS3/ECU to HUD | Engine telemetry, fuel/flex, injector data |
| 0x110-0x112 | MS3/ECU to Arduino | Flame, WMI trigger, engine status |
| 0x120-0x129 | Pi to Arduino | Boost target, mode, limp, traction, Air Shot request, WMI, fuel type |
| 0x12A-0x12B | Arduino to MS3/ECU | Torque cut and traction slip requests |
| 0x130-0x13F | Arduino to HUD | Air Shot, wheel speed, WMI, lights, traction, fallback statuses, service sensor voltages |
| 0x140 | Pi to Arduino | NFC authorization |
| 0x145-0x147 | Arduino to HUD | Service pin/relay states, firmware version, limp status |
| 0x150-0x152 | Pi to MS3/ECU | Fuel profile select, spark table select, rev limiter strategy |
| 0x1F0-0x1F1 | System | POST request/response |
