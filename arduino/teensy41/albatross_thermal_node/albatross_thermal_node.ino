// Dedicated Teensy 4.1 thermal acquisition node. It never depends on the Pi.
#include <Arduino.h>
#include <Watchdog_t4.h>
#include "analog_adc_driver.h"
#include "can_transport.h"
#include "diagnostics.h"
#include "sensor_config.h"
#include "sensor_conversion.h"
#include "sensor_filtering.h"
#include "sensor_validation.h"
#include "thermal_protocol.h"
#include "thermocouple_driver.h"

AnalogAdcDriver analog_adc;
ThermocoupleDriver thermocouples;
ThermalCanTransport can_transport;
WDT_T4<WDT1> watchdog;
SensorRuntime sensors[THERMAL_SENSOR_COUNT];

void acquireSensor(uint8_t index, uint32_t now) {
  const SensorConfig& config = SENSOR_CONFIG[index]; SensorRuntime& runtime = sensors[index];
  if (!config.enabled) { runtime.status=SensorStatus::NOT_CONFIGURED; return; }
  if (now-runtime.last_sample_ms < config.sample_period_ms) return;
  const float dt=(runtime.last_sample_ms==0)?0.0f:(now-runtime.last_sample_ms)/1000.0f; const float previous=runtime.instantaneous_c; runtime.last_sample_ms=now;
  float value=NAN; SensorStatus status=SensorStatus::VALID;
  if(config.bus==SourceBus::MAX31856){ if(!thermocouples.read(config.channel,value,status)){runtime.status=status;return;} }
  else { uint16_t raw=0; if(!analog_adc.read(config.channel,raw)){runtime.status=SensorStatus::FRONT_END_FAULT;return;} runtime.raw=raw; value=convertAnalogToCelsius(config,raw); status=validateAnalog(config,raw,value,previous,dt); }
  runtime.status=status; if(status==SensorStatus::VALID) updateFilter(runtime,value,dt,config.filter_tau_s,config.derivative_tau_s);
}

void setup() {
  analog_adc.begin(); thermocouples.begin(); can_transport.begin();
  WDT_timings_t timings{}; timings.trigger=1; timings.timeout=2; watchdog.begin(timings);
}

void loop() {
  const uint32_t now=millis();
  for(uint8_t index=0;index<THERMAL_SENSOR_COUNT;++index) acquireSensor(index,now);
  static uint32_t last_values=0,last_status=0,last_heartbeat=0,last_config=0,last_raw=0; static uint8_t sequence=0;
  if(now-last_values>=40){last_values=now;can_transport.publishValues(sensors,now);}
  if(now-last_status>=ThermalProtocol::STATUS_PERIOD_MS){last_status=now;can_transport.publishStatus(sensors);}
  if(now-last_heartbeat>=ThermalProtocol::HEARTBEAT_PERIOD_MS){last_heartbeat=now;can_transport.publishHeartbeat(sequence++);}
  if(now-last_config>=ThermalProtocol::CONFIG_PERIOD_MS){last_config=now;can_transport.publishConfiguration();}
  if(now-last_raw>=ThermalProtocol::RAW_DIAGNOSTIC_PERIOD_MS){last_raw=now;can_transport.publishRaw(sensors);}
  watchdog.feed();
}
