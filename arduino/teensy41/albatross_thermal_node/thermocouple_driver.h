#pragma once
#include <Adafruit_MAX31856.h>
#include "diagnostics.h"

class ThermocoupleDriver {
 public:
  void begin();
  bool read(uint8_t channel, float& temperature_c, SensorStatus& status);
 private:
  Adafruit_MAX31856 devices_[4] = {
    Adafruit_MAX31856(10), Adafruit_MAX31856(9), Adafruit_MAX31856(8), Adafruit_MAX31856(7)
  };
};
