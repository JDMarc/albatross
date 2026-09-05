#pragma once
#include <Arduino.h>
#include "vdc_calibration.h"
namespace vdc {
// Installation settings, not final calibrations. Verify in service before enabling.
struct Hardware {
 uint16_t racegrade_base=0x470,dbwx2_base=0x300,command_id=0x210;
 bool mount_verified=false,dbwx2_custom_receive_verified=false,watchdog_verified=false;
 // Intended donor: 2026 Yamaha MT-07 assembly, one driven motor/channel.
 // Confirm actual motor/TPS wiring and independent kill circuit on hardware.
 bool throttle_body_verified=false,independent_kill_verified=false;
 // Firmware/runtime layout must match DBWX2 0.92 INI; node IDs must be unique.
 bool dbwx2_v092_verified=false;
 uint8_t local_node=9,dbwx2_node=10;
 uint32_t poll_interval_ms=5;
 int enable_pin=-1; // optional only after wiring review; no guessed GPIO assignment
 int accel_axis[3]={1,0,2},gyro_axis[3]={2,1,0};
 float accel_sign[3]={1,1,1},gyro_sign[3]={1,1,1};
};
class IO {
 public:Config c=engineeringCalibration();Hardware hw;Controller controller{c};Inputs inputs;
 uint8_t weather_state=4,request_ack=0;float native_pedal=NAN,native_throttle=NAN;
 void receive(uint16_t id,uint8_t len,const uint8_t* data,uint32_t now);
 void receiveExtended(uint32_t id,uint8_t len,const uint8_t* data,uint32_t now);
 void poll(uint32_t now,void (*send)(uint32_t,const uint8_t*,uint8_t));
 const Output& update(uint32_t now);
 void publish(void (*send)(uint16_t,const uint8_t*,uint8_t));
 void command(void (*send)(uint16_t,const uint8_t*,uint8_t));
 private:uint32_t stamps[6]={0};CommandWatchdog sensor_sequence[3];uint8_t sequence=0;
 uint32_t poll_at=0,current_at=0,status_at=0,channel_at=0,expected_reply=0;
 uint16_t token=0;uint8_t group=0;bool pending=false,status_fault=true,channel_fault=true;
};
}
