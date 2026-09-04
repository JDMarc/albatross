#pragma once
#include <Arduino.h>
#include "airshot_controller.h"
#include "airshot_calibration.h"
namespace airshot {
class IO {
 public:
  Config c=calibration();
  Controller controller{c};
  Inputs inputs;
  uint32_t dbw_at=0,pressure_at=0,wg_at=0,driver_at[4]={0},request_at=0;
  bool remote_request=false,configured_pins=false;
  uint8_t config_status=0;
  void begin();
  void receive(uint16_t id,uint8_t len,const uint8_t* data,uint32_t now);
  void update(uint32_t now);
  void publish(void (*send)(uint16_t,const uint8_t*,uint8_t));
 private:
  uint16_t request_sequence=0;
  bool have_request=false,driver_latched=false;
  bool command_on[4]={false};
  uint32_t command_changed[4]={0};
  Config pending;
  uint32_t config_started=0, config_hash=2166136261UL;
  uint16_t config_count=0;
  uint16_t config_token=0;
 public:
  CompressorState compressor=CompressorState::OFF;
 private:
  bool config_active=false;
};
}
