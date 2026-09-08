#pragma once
#include <Adafruit_MAX31856.h>
#include "diagnostics.h"
#include "thermal_hardware.h"
class ThermocoupleDriver {
 public:
  void begin();
  void poll(uint32_t now);
  AcquisitionSample sample(uint8_t ch,uint32_t now) const;
  float temperature(uint8_t ch) const {return ch<4?values_[ch]:NAN;}
 private:
  Adafruit_MAX31856 devices_[4] = {
    Adafruit_MAX31856(ThermalHardware::TC_CS[0]), Adafruit_MAX31856(ThermalHardware::TC_CS[1]),
    Adafruit_MAX31856(ThermalHardware::TC_CS[2]), Adafruit_MAX31856(ThermalHardware::TC_CS[3])
  };
  AcquisitionSample samples_[4];
  float values_[4]={NAN,NAN,NAN,NAN};
  bool pending_[4]={};
  uint32_t started_[4]={};
};
