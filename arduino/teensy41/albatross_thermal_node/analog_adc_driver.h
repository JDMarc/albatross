#pragma once
#include <Arduino.h>
#include <SPI.h>

class AnalogAdcDriver {
 public:
  void begin();
  bool read(uint8_t logical_channel, uint16_t& value);
 private:
  static constexpr uint8_t CS_PINS[2] = {6, 5};
};
