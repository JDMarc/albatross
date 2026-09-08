// Dedicated Teensy 4.1 thermal node, Rev B breakout hardware. No Pi dependency.
#include <Arduino.h>
#include <Watchdog_t4.h>
#include "analog_adc_driver.h"
#include "rtd_driver.h"
#include "can_transport.h"
#include "sensor_conversion.h"
#include "sensor_validation.h"
#include "sensor_processing.h"
#include "thermal_protocol.h"
#include "thermocouple_driver.h"

AnalogAdcDriver analog_adc;
RtdDriver rtds;
ThermocoupleDriver thermocouples;
ThermalCanTransport can_transport;
WDT_T4<WDT1> watchdog;
SensorRuntime sensors[THERMAL_SENSOR_COUNT];

void acquireSensor(uint8_t index,uint32_t now) {
  const auto& c=SENSOR_CONFIG[index];auto& r=sensors[index];
  if(!c.enabled) {r.status=SensorStatus::NOT_CONFIGURED;return;}
  AcquisitionSample s;float value=NAN,exc=NAN;
  if(c.bus==SourceBus::ADS1115) {
    s=analog_adc.sample(c.channel,now);
    if(!analog_adc.excitation(now,exc)) {
      r.generation=s.generation; // discard samples captured without trusted excitation
      r.instantaneous_c=NAN;
      invalidateSensor(r,SensorStatus::FRONT_END_FAULT);return;
    }
    value=convertNtcToCelsius(c,int16_t(s.raw),exc);
  } else if(c.bus==SourceBus::MAX31865) {
    s=rtds.sample(c.channel,now);value=convertRtdToCelsius(s.raw);
  } else if(c.bus==SourceBus::MAX31856) {
    s=thermocouples.sample(c.channel,now);value=thermocouples.temperature(c.channel);
  } else {invalidateSensor(r,SensorStatus::NOT_CONFIGURED);return;}
  const float dt=r.generation?uint32_t(s.captured_ms-r.last_sample_ms)/1000.0f:0;
  const SensorStatus health=c.bus==SourceBus::ADS1115?
    validateNtc(c,int16_t(s.raw),exc,value,r.instantaneous_c,dt):
    validateTemperature(c,value,r.instantaneous_c,dt);
  acceptSample(r,c,s,value,health);
}

void setup() {
  // All shared-bus selects high before any library starts clocking.
  for(auto pin:ThermalHardware::TC_CS) {digitalWrite(pin,HIGH);pinMode(pin,OUTPUT);}
  for(auto pin:ThermalHardware::RTD_CS) {digitalWrite(pin,HIGH);pinMode(pin,OUTPUT);}
  can_transport.begin();
  WDT_timings_t timings{};timings.trigger=1;timings.timeout=2;watchdog.begin(timings);
  analog_adc.begin();rtds.begin();thermocouples.begin();
}

void loop() {
  analog_adc.poll(millis());rtds.poll(millis());thermocouples.poll(millis());
  const uint32_t now=millis();
  for(uint8_t i=0;i<THERMAL_SENSOR_COUNT;++i) acquireSensor(i,now);
  static uint32_t last_values=0,last_status=0,last_heartbeat=0,last_config=0,last_raw=0;
  static uint8_t sequence=0;
  if(now-last_values>=40){last_values=now;can_transport.publishValues(sensors,now);}
  if(now-last_status>=ThermalProtocol::STATUS_PERIOD_MS){last_status=now;can_transport.publishStatus(sensors);}
  if(now-last_heartbeat>=ThermalProtocol::HEARTBEAT_PERIOD_MS){last_heartbeat=now;can_transport.publishHeartbeat(sequence++);}
  if(now-last_config>=ThermalProtocol::CONFIG_PERIOD_MS){last_config=now;can_transport.publishConfiguration();}
  if(now-last_raw>=ThermalProtocol::RAW_DIAGNOSTIC_PERIOD_MS){last_raw=now;can_transport.publishRaw(sensors);}
  watchdog.feed();
}
