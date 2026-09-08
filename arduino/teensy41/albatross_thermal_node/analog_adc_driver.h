#pragma once
#include <Wire.h>
#include "diagnostics.h"
#include "thermal_hardware.h"

// One single-shot conversion in flight per board. No conversion sleeps.
class AnalogAdcDriver {
 public:
  void begin();
  void poll(uint32_t now);
  AcquisitionSample sample(uint8_t channel, uint32_t now) const;
  bool excitation(uint32_t now, float& volts) const;
 private:
  struct Board { uint8_t channel=0; bool waiting=false, retry=false; uint32_t since=0; };
  Board boards_[5];
  AcquisitionSample samples_[19];
  uint8_t cursor_=0;
  TwoWire& wire(uint8_t board);
  bool write16(uint8_t board, uint8_t reg, uint16_t value);
  bool read16(uint8_t board, uint8_t reg, uint16_t& value);
  void fail(uint8_t board, uint32_t now);
};
