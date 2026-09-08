#include "analog_adc_driver.h"
using namespace ThermalHardware;

TwoWire& AnalogAdcDriver::wire(uint8_t b) { return ADC_BUS[b] ? Wire1 : Wire; }
void AnalogAdcDriver::begin() {
  Wire.begin(); Wire.setClock(I2C_HZ);
  Wire1.begin(); Wire1.setClock(I2C_HZ);
}
bool AnalogAdcDriver::write16(uint8_t b,uint8_t reg,uint16_t value) {
  auto& w=wire(b); w.beginTransmission(ADC_ADDRESS[b]);
  w.write(reg); w.write(uint8_t(value>>8)); w.write(uint8_t(value));
  return w.endTransmission()==0;
}
bool AnalogAdcDriver::read16(uint8_t b,uint8_t reg,uint16_t& value) {
  auto& w=wire(b); w.beginTransmission(ADC_ADDRESS[b]); w.write(reg);
  if(w.endTransmission(false)!=0) return false;
  if(w.requestFrom(ADC_ADDRESS[b],uint8_t(2))!=2) return false;
  value=uint16_t(w.read())<<8; value|=uint8_t(w.read()); return true;
}
void AnalogAdcDriver::fail(uint8_t b,uint32_t now) {
  // Invalidate the whole board together, including N4 excitation if affected.
  for(uint8_t c=0;c<(b==4?3:4);++c)
    samples_[b*4+c].set(0,now,SensorStatus::FRONT_END_FAULT);
  boards_[b].waiting=false; boards_[b].retry=true; boards_[b].since=now;
}
void AnalogAdcDriver::poll(uint32_t now) {
  // Bound work to one board per call; Teensy Wire has bounded hardware timeouts.
  const uint8_t b=cursor_; cursor_=(cursor_+1)%5; auto& s=boards_[b];
  if(s.retry && uint32_t(now-s.since)<RETRY_MS) return;
  // MUX=AINx/GND, PGA=+/-4.096V, single-shot, 860SPS, comparator off.
  const uint16_t expected=uint16_t(0x03E3U | ((4U+s.channel)<<12));
  if(!s.waiting) {
    s.retry=false;
    if(!write16(b,1,expected|0x8000U)) {fail(b,now);return;}
    s.waiting=true;s.since=now;return;
  }
  if(uint32_t(now-s.since)<2) return; // >= one conversion incl oscillator tolerance
  uint16_t config=0;
  if(!read16(b,1,config) || (config&0x7FFFU)!=expected) {fail(b,now);return;}
  if(!(config&0x8000U)) {
    if(uint32_t(now-s.since)>=ADC_TIMEOUT_MS) fail(b,now);
    return;
  }
  uint16_t raw=0;
  if(!read16(b,0,raw)) {fail(b,now);return;}
  samples_[b*4+s.channel].set(raw,millis(),SensorStatus::VALID);
  s.channel=(s.channel+1)%(b==4?3:4);s.waiting=false;
}
AcquisitionSample AnalogAdcDriver::sample(uint8_t ch,uint32_t now) const {
  if(ch>=19) return {};
  auto s=samples_[ch];
  if(s.status==SensorStatus::VALID && uint32_t(now-s.captured_ms)>STALE_MS)
    s.status=SensorStatus::STALE;
  return s;
}
bool AnalogAdcDriver::excitation(uint32_t now,float& volts) const {
  const auto s=sample(18,now); volts=int16_t(s.raw)*ADC_LSB_V;
  // Shared 3.3V domain: MAX31865 specified operating range is 3.0..3.6V.
  return s.status==SensorStatus::VALID && volts>=3.0f && volts<=3.6f;
}
