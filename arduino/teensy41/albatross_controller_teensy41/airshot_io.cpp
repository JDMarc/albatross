#include "airshot_io.h"
#include "airshot_fields.h"
#include "airshot_persistence.h"
namespace airshot {
static uint16_t u16(const uint8_t* p) {return (uint16_t(p[0])<<8)|p[1];}
static void put16(uint8_t* p,uint16_t v) {p[0]=v>>8;p[1]=v;}
static bool validPins(const Config& c) {
  bool configured_pins=validConfig(c);
  const int reserved[]={0,1,2,3,4,5,6,9,10,12,14,15,16,18,19,20,22,23,24,25,26,27,28,29,30,31};
  for(int n=0;n<4;n++) {
    const auto& v=c.valves[n];
    if(v.pin<0 || v.pin>41 || !digitalPinHasPWM(v.pin)) configured_pins=false;
    for(int pin:reserved) if(v.pin==pin) configured_pins=false;
    for(int k=0;k<n;k++) if(c.valves[k].pin==v.pin) configured_pins=false;
    // Teensy 4.1 paired PWM outputs share a frequency (installed core pwm.c).
    for(int k=0;k<n;k++) {
      int other=c.valves[k].pin;
      bool shared=((v.pin==7 || v.pin==8) && (other==7 || other==8)) ||
                  ((v.pin==36 || v.pin==37) && (other==36 || other==37));
      if(shared && c.valves[k].pwm_hz!=v.pwm_hz) configured_pins=false;
    }
    if(v.pin==c.fire_pin || v.pin==c.service_pin) configured_pins=false;
  }
  if(c.fire_pin < -1 || c.fire_pin>41 || c.service_pin < -1 || c.service_pin>41 || (c.fire_pin>=0 && c.service_pin==c.fire_pin)) configured_pins=false;
  if(c.fire_pin==12 || c.service_pin==12) configured_pins=false; // legacy setup holds this output low
  for(int pin:reserved) if(c.fire_pin==pin || c.service_pin==pin) configured_pins=false;
  return configured_pins;
}
void IO::begin() {
  loadConfig(c); controller.configure(c);
  pinMode(12,OUTPUT); digitalWrite(12,LOW);
  configured_pins=validPins(c);
  if(configured_pins) {
    analogWriteResolution(8);
    for(auto& v:c.valves) {pinMode(v.pin,OUTPUT);digitalWrite(v.pin,LOW);analogWriteFrequency(v.pin,v.pwm_hz);}
    if(c.fire_pin>=0) pinMode(c.fire_pin,INPUT_PULLUP);
    if(c.service_pin>=0) pinMode(c.service_pin,INPUT_PULLUP);
  }
}
void IO::receive(uint16_t id,uint8_t len,const uint8_t* d,uint32_t now) {
  // All V2 frames have an explicit version byte. Unknown versions never refresh leases.
  if(!len || d[0]!=2) return;
  if(id==0x190 && len==3 && d[1]<=2 && d[2]==0xA5) controller.setMode(Mode(d[1]));
  if(id==0x191 && len==5) {
    uint16_t seq=u16(d+2);
    if(!have_request || (uint16_t(seq-request_sequence)<0x8000U && seq!=request_sequence) || now-request_at>1000) {
      request_sequence=seq;have_request=true;remote_request=d[1]==1;request_at=now;
    }
  }
  if(id==0x192 && len==8 && d[1]<=100 && d[2]<=100 && d[3]<=100) {
    inputs.rider=d[1];inputs.dbw_command=d[2];inputs.dbw_actual=d[3];
    inputs.dbw_valid=d[4]&1;inputs.ecu_protection=d[4]&2;inputs.awc=d[4]&4;
    inputs.target=u16(d+5)/10.0f;dbw_at=now;
  }
  if(id==0x193 && len==8) {
    inputs.regulated=u16(d+1)/10.0f;inputs.pressure_valid=d[7]&1;pressure_at=now;
  }
  if(id==0x194 && len==6 && d[1]<=100 && d[2]<=100 && d[3]<=100 && d[4]<=100) {
    inputs.wg_command[0]=d[1];inputs.wg_command[1]=d[2];inputs.wg_position[0]=d[3];inputs.wg_position[1]=d[4];inputs.wg_valid=d[5]&1;wg_at=now;
  }
  if(id>=0x198 && id<=0x19B && len==5) {
    int n=id-0x198;inputs.currents[n]=u16(d+1)/1000.0f;driver_at[n]=now;
    if(d[3]) {inputs.driver_faults|=1<<n;driver_latched=true;}
  }
  if(id>=0x19C && id<=0x19E && len==8) {
    if(id==0x19C) config_token=u16(d+3);
    bool stopped=inputs.can_valid && inputs.rpm==0 && inputs.speed<=1;
    if(!stopped) {config_active=false;config_status=3;return;}
    if(id==0x19C && d[1]==1 && d[2]==0xA5) {
      controller.setMode(Mode::OFF);
      if(configured_pins) for(auto& v:c.valves) analogWrite(v.pin,0);
      pending=c; config_started=now;config_count=0;config_hash=2166136261UL;
      config_active=true;config_status=1;return;
    }
    if(!config_active || now-config_started>5000) {config_status=4;config_active=false;return;}
    if(id==0x19D) {
      uint16_t field=u16(d+1);uint32_t bits=(uint32_t(d[3])<<24)|(uint32_t(d[4])<<16)|(uint32_t(d[5])<<8)|d[6];
      float value;memcpy(&value,&bits,4);
      if(field!=config_count || !setField(pending,field,value)) {config_active=false;config_status=4;return;}
      config_hash=hashBytes(d+3,4,config_hash);++config_count;
    }
    if(id==0x19E) {
      uint32_t expected=(uint32_t(d[1])<<24)|(uint32_t(d[2])<<16)|(uint32_t(d[3])<<8)|d[4];
      config_active=false;
      if(d[7]!=0xA5 || config_count!=FIELD_COUNT || u16(d+5)!=FIELD_COUNT || config_hash!=expected || !validConfig(pending)) {config_status=4;return;}
      if(!validPins(pending)) {config_status=5;return;}
      storeConfig(pending);begin();config_status=configured_pins?2:5;
    }
  }
}
void IO::update(uint32_t now) {
  inputs.now=now;
  inputs.dbw_valid=inputs.dbw_valid && dbw_at && now-dbw_at<=c.timeout_ms;
  inputs.pressure_valid=inputs.pressure_valid && pressure_at && now-pressure_at<=c.timeout_ms;
  inputs.wg_valid=inputs.wg_valid && wg_at && now-wg_at<=c.timeout_ms;
  inputs.driver_valid=configured_pins;
  for(int n=0;n<4;n++) {
    if(!driver_at[n] || now-driver_at[n]>c.timeout_ms) inputs.driver_valid=false;
    const auto& v=c.valves[n];
    float command=controller.output().valve[n];
    if(isfinite(inputs.currents[n]) && inputs.currents[n]>v.max_current && v.max_current>0) driver_latched=true;
    bool on=command>0;
    if(on!=command_on[n]) {command_on[n]=on;command_changed[n]=now;}
    float settle=on?v.opening_ms:v.closing_ms;
    if(now-command_changed[n]>settle+c.timeout_ms && isfinite(inputs.currents[n])) {
      if(!on && inputs.currents[n]>v.min_current && v.min_current>0) driver_latched=true;
      if(on && inputs.currents[n]<v.min_current) driver_latched=true;
    }
  }
  if(driver_latched) inputs.driver_faults|=0x80;
  inputs.manual=(configured_pins && c.fire_pin>=0 && digitalRead(c.fire_pin)==LOW) ||
    (remote_request && now-request_at<=c.request_lease_ms);
  const auto& o=controller.update(inputs);
  for(int n=0;n<4;n++) if(configured_pins) analogWrite(c.valves[n].pin,uint8_t(o.valve[n]*255));
}
void IO::publish(void (*send)(uint16_t,const uint8_t*,uint8_t)) {
  const auto& o=controller.output();
  uint8_t status[8]={2,uint8_t(controller.getMode()),uint8_t(o.state),uint8_t(o.reason),uint8_t(o.profile),uint8_t(o.demand*100),uint8_t(o.available*100),uint8_t((o.manual_request?1:0)|(o.auto_request?2:0)|(o.accepted?4:0)|(o.shadow?8:0))};
  send(0x180,status,8);
  uint8_t commands[8]={2};
  for(int n=0;n<4;n++) commands[n+1]=uint8_t(o.valve[n]*100);
  commands[5]=inputs.driver_faults;put16(commands+6,uint16_t(o.event_id));send(0x181,commands,8);
  uint8_t pressure[8]={2};put16(pressure+1,uint16_t(inputs.tank*10));put16(pressure+3,uint16_t(inputs.regulated*10));put16(pressure+5,uint16_t(o.pressure_used*10));pressure[7]=inputs.pressure_valid;send(0x182,pressure,8);
  uint8_t event[8]={2};put16(event+1,uint16_t(o.event_id));put16(event+3,uint16_t(o.last_duration));put16(event+5,uint16_t(o.tank_before*10));event[7]=c.stage;send(0x183,event,8);
  uint8_t shadow[8]={2};for(int n=0;n<4;n++)shadow[n+1]=uint8_t(o.predicted[n]*100);put16(shadow+5,uint16_t(c.version));shadow[7]=uint8_t(compressor);send(0x184,shadow,8);
  uint8_t ack[8]={2,config_status,uint8_t(configured_pins),uint8_t(c.stage)};put16(ack+4,config_count);put16(ack+6,config_token);send(0x185,ack,8);
}
}
