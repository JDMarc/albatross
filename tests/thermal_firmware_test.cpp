#include <cassert>
#include <cstdio>
#include "analog_adc_driver.h"
#include "rtd_driver.h"
#include "sensor_conversion.h"
#include "sensor_validation.h"
#include "sensor_processing.h"
uint32_t fake_ms=0;int selected_cs=-1;
TwoWire Wire,Wire1;FakeSPI SPI;
void digitalWrite(int pin,int value){selected_cs=value==LOW?pin:-1;}
int main(){
  const auto& ntc=SENSOR_CONFIG[4];
  assert(fabs(convertNtcToCelsius(ntc,13200,3.3f)-25)<.01);
  assert(fabs(convertNtcToCelsius(ntc,12800,3.2f)-25)<.01);
  assert(!isfinite(convertNtcToCelsius(ntc,-1,3.3f)));
  assert(!isfinite(convertNtcToCelsius(ntc,26400,3.3f)));
  assert(!isfinite(convertNtcToCelsius(ntc,1000,NAN)));
  for(float t:{-40.f,0.f,100.f,250.f}){
    using namespace ThermalHardware;
    float r=1000*(1+RTD_A*t+RTD_B*t*t+(t<0?RTD_C*(t-100)*t*t*t:0));
    auto raw=uint16_t(lroundf(r/4300*32768));assert(fabs(convertRtdToCelsius(raw)-t)<.06);
  }
  assert(!isfinite(convertRtdToCelsius(0)) && !isfinite(convertRtdToCelsius(32767)));
  assert(validateNtc(ntc,26400,3.3f,NAN,NAN,0)==SensorStatus::OUT_OF_RANGE);
  SensorRuntime runtime;AcquisitionSample s;s.set(13200,100,SensorStatus::VALID);
  acceptSample(runtime,ntc,s,25,SensorStatus::VALID);assert(runtime.status==SensorStatus::STALE);
  acceptSample(runtime,ntc,s,25,SensorStatus::VALID);assert(runtime.good_samples==1);
  s.set(13200,150,SensorStatus::VALID);acceptSample(runtime,ntc,s,25,SensorStatus::VALID);
  assert(runtime.status==SensorStatus::VALID);
  s.status=SensorStatus::FRONT_END_FAULT;acceptSample(runtime,ntc,s,NAN,s.status);
  assert(runtime.status==SensorStatus::FRONT_END_FAULT && !isfinite(runtime.filtered_c));
  s.set(13200,200,SensorStatus::VALID);acceptSample(runtime,ntc,s,25,SensorStatus::VALID);
  assert(runtime.status!=SensorStatus::VALID);
  AnalogAdcDriver adc;adc.begin();
  for(fake_ms=0;fake_ms<200;++fake_ms)adc.poll(fake_ms);
  float exc=0;assert(adc.excitation(fake_ms,exc)&&fabs(exc-3.3f)<.001);
  assert(adc.sample(0,fake_ms).status==SensorStatus::VALID);
  Wire.fail=true;
  for(;fake_ms<220;++fake_ms)adc.poll(fake_ms);
  for(int i=0;i<12;++i)assert(adc.sample(i,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  assert(adc.sample(12,fake_ms).status==SensorStatus::VALID);
  Wire.fail=false;Wire1.short_read=true;
  for(;fake_ms<240;++fake_ms)adc.poll(fake_ms);
  assert(!adc.excitation(fake_ms,exc));
  Wire1.short_read=false;
  for(;fake_ms<500;++fake_ms)adc.poll(fake_ms);
  assert(adc.excitation(fake_ms,exc));
  assert(adc.sample(0,fake_ms+751).status==SensorStatus::STALE);
  Wire.wrong_config=true;
  for(;fake_ms<520;++fake_ms)adc.poll(fake_ms);
  assert(adc.sample(0,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  Wire.wrong_config=false;Wire.busy=true;
  for(;fake_ms<750;++fake_ms)adc.poll(fake_ms);
  assert(adc.sample(0,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  Wire.busy=false;
  // Wraparound timing still permits recovery and fresh conversion.
  fake_ms=0xfffffff0U;for(int i=0;i<500;++i,++fake_ms)adc.poll(fake_ms);
  assert(adc.sample(0,fake_ms).status==SensorStatus::VALID);
  RtdDriver rtd;
  for(auto pin:ThermalHardware::RTD_CS){uint16_t raw=uint16_t(lroundf(1000.f/4300*32768))<<1;SPI.regs[pin][1]=raw>>8;SPI.regs[pin][2]=raw;}
  rtd.begin();fake_ms=0;
  for(;fake_ms<99;++fake_ms)rtd.poll(fake_ms);
  assert(rtd.sample(0,fake_ms).status==SensorStatus::VALID);
  assert(fabs(convertRtdToCelsius(rtd.sample(0,fake_ms).raw))<.05);
  assert(!(SPI.regs[2][0]&0x80)); // bias disabled between acquisitions
  SPI.absent[2]=true;
  for(;fake_ms<199;++fake_ms)rtd.poll(fake_ms);
  assert(rtd.sample(0,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  assert(rtd.sample(1,fake_ms).status==SensorStatus::VALID);
  SPI.absent[2]=false;SPI.stuck=true;
  for(;fake_ms<299;++fake_ms)rtd.poll(fake_ms);
  assert(rtd.sample(0,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  SPI.stuck=false;
  for(;fake_ms<399;++fake_ms)rtd.poll(fake_ms);
  assert(rtd.sample(0,fake_ms).status==SensorStatus::VALID);
  SPI.regs[3][7]=0x20;
  for(;fake_ms<499;++fake_ms)rtd.poll(fake_ms);
  assert(rtd.sample(1,fake_ms).status==SensorStatus::FRONT_END_FAULT);
  assert(rtd.sample(0,fake_ms+751).status==SensorStatus::STALE);
  puts("PASS thermal native: NTC excitation, CVD, recovery, ADC faults/timeout/wrap, RTD disconnect/fault/bias");
}
