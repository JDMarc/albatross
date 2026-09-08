#include "rtd_driver.h"
using namespace ThermalHardware;

void RtdDriver::begin() {
  SPI.begin();
  for(auto pin:RTD_CS) {digitalWrite(pin,HIGH);pinMode(pin,OUTPUT);}
}
uint8_t RtdDriver::read8(uint8_t ch,uint8_t reg) {
  SPI.beginTransaction(SPISettings(1000000,MSBFIRST,SPI_MODE1));
  digitalWrite(RTD_CS[ch],LOW); delayMicroseconds(1);
  SPI.transfer(reg&0x7F); const uint8_t v=SPI.transfer(0);
  digitalWrite(RTD_CS[ch],HIGH); SPI.endTransaction(); return v;
}
uint16_t RtdDriver::read16(uint8_t ch,uint8_t reg) {
  SPI.beginTransaction(SPISettings(1000000,MSBFIRST,SPI_MODE1));
  digitalWrite(RTD_CS[ch],LOW); delayMicroseconds(1);
  SPI.transfer(reg&0x7F); uint16_t v=uint16_t(SPI.transfer(0))<<8;v|=SPI.transfer(0);
  digitalWrite(RTD_CS[ch],HIGH);SPI.endTransaction();return v;
}
void RtdDriver::write8(uint8_t ch,uint8_t reg,uint8_t value) {
  SPI.beginTransaction(SPISettings(1000000,MSBFIRST,SPI_MODE1));
  digitalWrite(RTD_CS[ch],LOW);delayMicroseconds(1);
  SPI.transfer(reg|0x80);SPI.transfer(value);
  digitalWrite(RTD_CS[ch],HIGH);SPI.endTransaction();
}
void RtdDriver::poll(uint32_t now) {
  for(uint8_t ch=0;ch<7;++ch) {
    auto& d=devices_[ch];
    // 50Hz notch; two/four wire share register setting, three wire sets bit4.
    const uint8_t base=0x81U | (RTD_WIRES[ch]==3?0x10U:0);
    if(d.phase==0) {
      if(samples_[ch].generation && uint32_t(now-d.started)<RTD_PERIOD_MS) continue;
      d.started=now;d.since=now;
      write8(ch,0,base|0x02); // clear previous fault and enable bias
      if((read8(ch,0)&~0x02U)!=base) {
        samples_[ch].set(0,now,SensorStatus::FRONT_END_FAULT);continue;
      }
      d.phase=1;continue;
    }
    if(d.phase==1) {
      if(uint32_t(now-d.since)<RTD_BIAS_MS) continue;
      write8(ch,0,base|0x04);d.since=now;d.phase=2;continue; // automatic fault cycle
    }
    if(d.phase==2) {
      if(uint32_t(now-d.since)<1) continue; // datasheet automatic fault cycle <=600us
      if(read8(ch,0)!=base || read8(ch,7)!=0) {
        samples_[ch].set(0,now,SensorStatus::FRONT_END_FAULT);
        write8(ch,0,base&~0x80U);d.phase=0;continue;
      }
      write8(ch,0,base|0x20);d.since=now;d.phase=3;continue;
    }
    if(uint32_t(now-d.since)<RTD_CONVERSION_MS) continue;
    const uint8_t cfg=read8(ch,0);
    SensorStatus status=SensorStatus::VALID;uint16_t raw=0;
    // One-shot bit must self-clear. Static 0x00/0xFF or reset config is not a sensor value.
    if(cfg!=base) status=SensorStatus::FRONT_END_FAULT;
    else {
      const uint16_t word=read16(ch,1);raw=word>>1;
      const uint8_t fault=read8(ch,7);
      // Reference/common-mode faults are ambiguous; never claim exact failed lead.
      if(fault&0x3C) status=SensorStatus::FRONT_END_FAULT;
      else if((fault&0x80) || raw==32767) status=SensorStatus::OPEN_CIRCUIT;
      else if((fault&0x40) || raw==0) status=SensorStatus::OUT_OF_RANGE;
      else if((word&1) || fault) status=SensorStatus::FRONT_END_FAULT;
    }
    samples_[ch].set(raw,now,status);
    write8(ch,0,base&~0x80U); // bias off between samples
    d.phase=0;
  }
}
AcquisitionSample RtdDriver::sample(uint8_t ch,uint32_t now) const {
  if(ch>=7) return {};
  auto s=samples_[ch];
  if(s.status==SensorStatus::VALID && uint32_t(now-s.captured_ms)>STALE_MS) s.status=SensorStatus::STALE;
  return s;
}
