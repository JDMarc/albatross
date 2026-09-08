#include "thermocouple_driver.h"
#include "sensor_config.h"
void ThermocoupleDriver::begin() {
  for(auto& d:devices_) {d.begin();d.setThermocoupleType(MAX31856_TCTYPE_K);d.setConversionMode(MAX31856_ONESHOT_NOWAIT);}
}
void ThermocoupleDriver::poll(uint32_t now) {
  for(uint8_t ch=0;ch<4;++ch) {
    auto& d=devices_[ch];
    if(!pending_[ch]) {
      if(samples_[ch].generation && uint32_t(now-started_[ch])<SENSOR_CONFIG[ch].sample_period_ms) continue;
      started_[ch]=now;
      d.setThermocoupleType(MAX31856_TCTYPE_K);d.setConversionMode(MAX31856_ONESHOT_NOWAIT);
      if(d.getThermocoupleType()!=MAX31856_TCTYPE_K) {
        samples_[ch].set(0,now,SensorStatus::FRONT_END_FAULT);continue;
      }
      d.triggerOneShot();pending_[ch]=true;continue;
    }
    if(!d.conversionComplete()) {
      if(uint32_t(now-started_[ch])>ThermalHardware::STALE_MS) {
        samples_[ch].set(0,now,SensorStatus::STALE);pending_[ch]=false;
      }
      continue;
    }
    pending_[ch]=false; SensorStatus status=SensorStatus::VALID;
    const uint8_t fault=d.readFault();
    if(d.getThermocoupleType()!=MAX31856_TCTYPE_K) status=SensorStatus::FRONT_END_FAULT;
    else if(fault&MAX31856_FAULT_OPEN) status=SensorStatus::OPEN_CIRCUIT;
    else if(fault) status=SensorStatus::FRONT_END_FAULT;
    float value=status==SensorStatus::VALID?d.readThermocoupleTemperature():NAN;
    if(status==SensorStatus::VALID && !isfinite(value)) status=SensorStatus::FRONT_END_FAULT;
    values_[ch]=value;
    // Raw diagnostic TC word is signed tenths C (full chip raw is >16 bits).
    samples_[ch].set(isfinite(value)?uint16_t(int16_t(lroundf(value*10))):0,now,status);
  }
}
AcquisitionSample ThermocoupleDriver::sample(uint8_t ch,uint32_t now) const {
  if(ch>=4) return {};
  auto s=samples_[ch];
  if(s.status==SensorStatus::VALID && uint32_t(now-s.captured_ms)>ThermalHardware::STALE_MS) s.status=SensorStatus::STALE;
  return s;
}
