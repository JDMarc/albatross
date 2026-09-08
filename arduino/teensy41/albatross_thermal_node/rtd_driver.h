#pragma once
#include <SPI.h>
#include "diagnostics.h"
#include "thermal_hardware.h"

class RtdDriver {
 public:
  void begin();
  void poll(uint32_t now);
  AcquisitionSample sample(uint8_t channel,uint32_t now) const;
 private:
  struct Device { uint8_t phase=0; uint32_t since=0,started=0; };
  Device devices_[7];
  AcquisitionSample samples_[7];
  uint8_t read8(uint8_t channel,uint8_t reg);
  uint16_t read16(uint8_t channel,uint8_t reg);
  void write8(uint8_t channel,uint8_t reg,uint8_t value);
};
