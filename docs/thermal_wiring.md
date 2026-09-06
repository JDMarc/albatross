# Thermal subsystem wiring pack

[Printable 10-sheet vector PDF](../output/pdf/albatross-thermal-wiring.pdf)
and [32-ID sensor wire schedule](../output/pdf/thermal-sensor-wire-schedule.csv).

Revision A is a complete **functional wiring/harness plan**, not a released
acquisition-PCB schematic or a pin-order drawing for unidentified breakout boards.
It follows the current 29 active sensors: four K thermocouples, 14 air/ambient
NTCs, four coolant NTCs and seven PT1000s. The three disabled IDs remain reserved.
The dedicated thermal Teensy is separate from the main controller.

Sheets cover the system overview, protected power/returns/CAN, shared SPI and
individual chip selects, four thermocouple pairs, the required analog board
connections, NTC and RTD conditioning, both ADC channel maps, and commissioning.
Logical Txx-A/B labels are proposed harness identifiers, not manufacturer cavity
numbers. Exact probe, connector, ADC module, protection, current-source, reference
and CAN transceiver part numbers still need to be selected.

## Findings that block fabrication/commissioning

The older wiring documentation reversed CAN1 pins. This pack corrects them:
**Teensy pin 22 -> transceiver TXD; transceiver RXD -> Teensy pin 23**. This matches
the [PJRC pin card](https://www.pjrc.com/teensy/card11a_rev4_web.pdf) and the installed
FlexCAN_T4 default routing. No firmware rerouting is needed.

- `sensor_conversion.cpp` uses a 3.3 V full scale for PT1000 conversion, while the
  ADS7953 reference/range configuration is not established by the hardware design.
  Do not wire a 3.3 V reference on the assumption that this is valid. The PDF
  proposes a 2.5 V reference and matching buffered NTC excitation as a design
  direction, explicitly requiring matching firmware and calibration work.
- `analog_adc_driver.cpp` selects a channel then reads one following frame.
  Verify and repair the manual-mode pipeline, power-on priming and channel-tag
  checks before treating analog values as trustworthy.
- A plain ADS7953 breakout is not a complete analog acquisition board. It still
  needs the appropriate reference, multiplexer-to-ADC path, excitation networks,
  filtering, input protection and ground strategy. See the
  [TI ADS7953 datasheet](https://www.ti.com/lit/ds/symlink/ads7953.pdf).
- All probe calibration constants remain engineering assumptions, particularly
  the coolant profile's 2.50 kOhm at 80 C. Obtain actual probe curves and validate
  the PT1000 conversion across its intended range.

No firmware, live settings or electrical outputs are changed by this wiring-pack
task. Independent ECU coolant, IAT and oil-temperature inputs remain connected.

## Regenerate

With ReportLab installed, run `python tools/render_thermal_wiring.py` from the
repository root. The PDF embeds the current source commit, and the CSV is built
from `config/thermal_system.json`. Render and inspect all pages after changes.
Changing a generated diagram does not configure or validate hardware.
