# Thermal subsystem wiring pack - Revision C

[Printable 10-sheet vector PDF](../output/pdf/albatross-thermal-wiring.pdf)
and [32-ID sensor wire schedule](../output/pdf/thermal-sensor-wire-schedule.csv).

Revision C replaces the proposed ADS7953 arrangement with **five Adafruit
ADS1115 #1085 boards and seven Adafruit MAX31865 PT1000 #3648 boards**.
Four MAX31856 thermocouple boards remain. This is a functional harness plan,
not a released automotive PCB/protection schematic.

**Firmware now implements the Rev B electrical allocation.** Revision C records
the implementation (thermal configuration 2.0.0), with hardware commissioning
still required. Do not use an older ADS7953 binary: pins 5/6 now select RTDs.

## Board and bus allocation

| Boards | Interface | Teensy pins | Selection |
|---|---|---|---|
| TC0-TC3 MAX31856 | SPI | MOSI11, MISO12, SCK13 | CS10,9,8,7 |
| R0-R6 MAX31865 PT1000 | SPI | MOSI11, MISO12, SCK13 | CS2,3,4,5,6,14,15 |
| N0,N1,N2 ADS1115 | Wire | SDA18, SCL19 | 0x48,0x49,0x4A |
| N3,N4 ADS1115 | Wire1 | SDA17, SCL16 | 0x48,0x49 |
| CAN transceiver | CAN1 | TX22, RX23 | 500 kbit/s |

N0/N3 ADDR -> GND; N1/N4 ADDR -> VDD; N2 ADDR -> its own SDA.
Verify the purchased board's default address link before applying straps.
Keep buses separate and account for parallel onboard I2C pull-ups.

The 18 thermistors are assigned in ID order: 5-19,22,23,29 across N0.A0
through N4.A1. N4.A2 measures EXC_NTC at the excitation distribution point;
N4.A3 is unconnected and not sampled. It is not an extra temperature ID.
R0-R6 serve IDs 20,21,24,25,26,27,28 respectively.
IDs 30-32 remain disabled with no physical hardware allocation.

## Power and sensor wiring

- Protected regulated 5 V feeds Teensy VIN. Isolate VUSB for simultaneous USB
  and external power. A separately budgeted 3.3 V peripheral rail supplies
  ADS1115 VDD and all MAX board VIN pins. Leave MAX 3Vo outputs unconnected.
- Each NTC uses its own precision pull-up, protection/filter network and
  dedicated SGND return. Existing provisional pull-ups are 10k for air and
  2.49k for coolant. Confirm actual probe resistance tables before calibration.
- EXC_NTC is a quiet nominal 3.3 V supply. The ADS1115 uses an internal reference;
  conversion uses measured excitation and configured ADC gain:
  Rntc = Rpullup * Vin / (Vexc - Vin). Reject invalid excitation and open/short
  conditions first. The configured +/-4.096 V PGA range does not permit inputs
  above ADC VDD. Protection and source-impedance/settling values remain TBD.
- The CSV retains a **two-wire PT1000 baseline**: A -> RTD+, B -> RTD-,
  with F+ bridged to RTD+ and F- bridged to RTD- on each board. **Do not connect
  RTD- to SGND or add the previous 500 uA current source.**
- Sheet 07 also illustrates optional three-/four-wire arrangements. Changing
  lead mode requires matching board jumpers, firmware configuration and harness
  documentation. Four-wire probes need independent sense/force leads from
  each element end. Two-wire lead resistance remains part of the measurement.
- Use the PT1000 board with 4300 ohm reference, not the PT100 version.
- K-type pairs remain dedicated alloy/polarity wiring to MAX31856 terminals.
  Shield bonds are separate from sensor returns; do not ground TC minus.
- Retain independent ECU coolant, IAT and oil-temperature inputs. This pack
  does not authorize replacement ECU signals or paralleling sensor inputs.

## Commissioning holds

The firmware includes two-bus ADS1115 acquisition, seven MAX31865 front ends,
signed/gain-aware conversion, excitation monitoring, CVD PT1000 conversion,
asynchronous scheduling and per-board failure handling. Generate configuration
with tools/generate_thermal_config.py; verify with tools/check_thermal_config.py.

Bench-verify real cadence, settling and fault recovery. ADS1115 uses 100 kHz I2C,
+/-4.096 V PGA and 860 SPS per conversion (not per probe). RTDs use 10 ms bias
settling, automatic fault detection and a 66 ms conversion wait. Thermocouples
request asynchronous single shots at 5 Hz. Cached samples never renew timestamps.
Acquisition is invalid after 750 ms; recovery requires two distinct good samples.
These acquisition settings require bench validation, not road acceptance.

NTC excitation on N4.A2 must be 3.0-3.6 V; losing it invalidates all NTCs.
Zero/negative input indicates short-to-ground; rail readings are out-of-range
because an open probe and short-to-excitation cannot be distinguished by this
divider alone. Board failures invalidate its assigned channels. Existing
temperature warning and critical thresholds were not changed.

Exact probe parts, sealed connector cavities, fuse/DC/DC/transient devices,
CAN module, NTC protection/filter values and shield bonding remain to be
specified. Logical Txx-A/B labels are not manufacturer connector pin numbers.

## Sources / purchasing

- [ADS1115 board #1085](https://www.adafruit.com/product/1085)
- [TI ADS1115 datasheet](https://www.ti.com/lit/ds/symlink/ads1115.pdf)
- [PT1000 MAX31865 board #3648](https://www.adafruit.com/product/3648)
- [MAX31865 lead wiring and jumpers](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/rtd-wiring-config)
- [MAX31865 power and SPI pins](https://learn.adafruit.com/adafruit-max31865-rtd-pt100-amplifier/pinouts)
- [MAX31856 pinouts](https://learn.adafruit.com/adafruit-max31856-thermocouple-amplifier/pinouts)
- [PJRC I2C ports](https://www.pjrc.com/teensy/td_libs_Wire.html)
- [PJRC CAN/pin card](https://www.pjrc.com/teensy/card11a_rev4_web.pdf)

## Regenerate

Run `python tools/render_thermal_wiring.py` with ReportLab installed.
`tools/thermal_wiring_rev_b.py` validates the firmware allocation.
Sensor sources, addresses, chip selects and lead modes are checked against
config/thermal_system.json before output.
Generation asserts full active-sensor coverage, unique inputs, unique per-bus
addresses and no Teensy pin collisions. Render and inspect all ten pages.
