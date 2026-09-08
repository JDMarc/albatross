#pragma once
#include "sensor_filtering.h"
#include "sensor_config.h"
#include "thermal_hardware.h"

inline void invalidateSensor(SensorRuntime& r,SensorStatus status) {
  r.status=status;r.filtered_c=NAN;r.derivative_c_s=0;r.good_samples=0;
}
inline void acceptSample(SensorRuntime& r,const SensorConfig& c,
                         const AcquisitionSample& s,float value,SensorStatus status) {
  // Re-reading a cache never renews its age or counts as recovery evidence.
  if(s.status!=SensorStatus::VALID) {invalidateSensor(r,s.status);return;}
  if(s.generation==r.generation) return;
  const float dt=r.generation?uint32_t(s.captured_ms-r.last_sample_ms)/1000.0f:0;
  r.generation=s.generation;r.last_sample_ms=s.captured_ms;r.raw=s.raw;
  if(status!=SensorStatus::VALID) {
    invalidateSensor(r,status);
    // Keep the candidate as the rate baseline so a stable step can recover.
    r.instantaneous_c=isfinite(value)?value:NAN;
    return;
  }
  r.instantaneous_c=value;
  if(r.good_samples<ThermalHardware::RECOVERY_SAMPLES) ++r.good_samples;
  if(r.good_samples<ThermalHardware::RECOVERY_SAMPLES) {
    r.status=SensorStatus::STALE;return;
  }
  updateFilter(r,value,dt,c.filter_tau_s,c.derivative_tau_s);r.status=SensorStatus::VALID;
}
