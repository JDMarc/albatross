#include "thermocouple_driver.h"

void ThermocoupleDriver::begin() {
  for (auto& device : devices_) {
    device.begin(); device.setThermocoupleType(MAX31856_TCTYPE_K);
    device.setConversionMode(MAX31856_CONTINUOUS);
  }
}

bool ThermocoupleDriver::read(uint8_t channel, float& temperature_c, SensorStatus& status) {
  if (channel >= 4) { status = SensorStatus::FRONT_END_FAULT; return false; }
  const uint8_t fault = devices_[channel].readFault();
  if (fault) {
    if (fault & MAX31856_FAULT_OPEN) status = SensorStatus::OPEN_CIRCUIT;
    else if (fault & (MAX31856_FAULT_OVUV | MAX31856_FAULT_TCRANGE)) status = SensorStatus::FRONT_END_FAULT;
    else status = SensorStatus::OUT_OF_RANGE;
    return false;
  }
  temperature_c = devices_[channel].readThermocoupleTemperature();
  status = isfinite(temperature_c) ? SensorStatus::VALID : SensorStatus::FRONT_END_FAULT;
  return status == SensorStatus::VALID;
}
