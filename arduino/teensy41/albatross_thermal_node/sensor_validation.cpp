#include "sensor_validation.h"
#include "thermal_hardware.h"
#include <math.h>

SensorStatus validateTemperature(const SensorConfig& c,float value,float previous,float dt) {
  if(!c.enabled) return SensorStatus::NOT_CONFIGURED;
  if(!isfinite(value) || value<c.minimum_c || value>c.maximum_c) return SensorStatus::OUT_OF_RANGE;
  // Existing repository limits, not newly tuned protection thresholds.
  const float maximum_rate=c.technology==SensorTechnology::K_TYPE?600.0f:50.0f;
  if(isfinite(previous) && dt>0 && fabsf(value-previous)/dt>maximum_rate)
    return SensorStatus::IMPLAUSIBLE_RATE;
  return SensorStatus::VALID;
}
SensorStatus validateNtc(const SensorConfig& c,int16_t raw,float exc,float value,float previous,float dt) {
  if(!isfinite(exc) || exc<3.0f || exc>3.6f) return SensorStatus::FRONT_END_FAULT;
  if(raw<=0) return SensorStatus::SHORT_TO_GROUND;
  const float v=raw*ThermalHardware::ADC_LSB_V;
  // An open NTC and a signal shorted to excitation are indistinguishable here.
  // Report generic out-of-range rather than an unproven electrical diagnosis.
  if(v>=exc || raw==32767) return SensorStatus::OUT_OF_RANGE;
  return validateTemperature(c,value,previous,dt);
}
