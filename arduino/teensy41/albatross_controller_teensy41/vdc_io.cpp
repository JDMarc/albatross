#include "vdc_io.h"
namespace vdc {
static uint16_t u16(const uint8_t* d){return (uint16_t(d[0])<<8)|d[1];}
static void p16(uint8_t* d,float value){int v=isfinite(value)?int(clamp(value,-32768,65535)):0;d[0]=uint16_t(v)>>8;d[1]=uint16_t(v);}
static uint8_t pct(float v){return isfinite(v)?uint8_t(clamp(v)*100):0;}
static uint16_t le16(const uint8_t* d){return uint16_t(d[0])|(uint16_t(d[1])<<8);}
static uint32_t msid(uint16_t offset,uint8_t type,uint8_t from,uint8_t to,uint8_t table){
 return (uint32_t(offset)<<18)|(uint32_t(type)<<15)|(uint32_t(from)<<11)|(uint32_t(to)<<7)|(uint32_t(table)<<3);
}
// Read-only MegaSquirt protocol. Runtime payload is LITTLE endian in DBWX2
// 0.92, unlike its protocol addressing and the RaceGrade wire format.
static const uint16_t offsets[]={0,64,76,60};
static const uint8_t lengths[]={8,4,8,4};
void IO::poll(uint32_t now,void (*send)(uint32_t,const uint8_t*,uint8_t)){
 if(!hw.dbwx2_v092_verified||!c.timeout_ms||hw.local_node>14||hw.dbwx2_node>14||hw.local_node==hw.dbwx2_node)return;
 if(pending){if(now-poll_at<=c.timeout_ms)return;pending=false;token=(token+1)&2047;}
 if(now-poll_at<hw.poll_interval_ms)return;
 uint8_t d[3]={6,uint8_t(token>>3),uint8_t(((token&7)<<5)|lengths[group])};
 expected_reply=msid(token,2,hw.dbwx2_node,hw.local_node,6);pending=true;poll_at=now;
 send(msid(offsets[group],1,hw.local_node,hw.dbwx2_node,5),d,3);
}
void IO::receiveExtended(uint32_t id,uint8_t len,const uint8_t* d,uint32_t now){
 if(!hw.dbwx2_v092_verified||!pending||id!=expected_reply||len!=lengths[group]||now-poll_at>c.timeout_ms)return;
 if(group==0){inputs.aps[0]=le16(d);inputs.aps[1]=le16(d+2);inputs.tps[0]=le16(d+4);inputs.tps[1]=le16(d+6);inputs.aps_valid=inputs.tps_valid=true;stamps[0]=stamps[1]=now;}
 if(group==1){inputs.motor_current=le16(d)*.01f;current_at=now;}
 if(group==2){status_fault=le16(d)!=0||d[4]!=1||d[5]!=0||(d[7]&0x1C)!=0;status_at=now;}
 if(group==3){channel_fault=(d[0]&0x3E)!=0||d[1]!=0;channel_at=now;}
 pending=false;token=(token+1)&2047;group=(group+1)%4;
}
void IO::receive(uint16_t id,uint8_t len,const uint8_t* d,uint32_t now){
 static const uint8_t stop_message[]={1,'S','T','O','P',0xA5};
 if(id==0x20A&&len==sizeof(stop_message)&&memcmp(d,stop_message,sizeof(stop_message))==0){controller.stop();return;}
 // RaceGrade RG_SPEC-0027 v1.9 STANDARD mode. Signed big-endian axes.
 if((id==hw.racegrade_base||id==hw.racegrade_base+1)&&(len==6||len==8)){
  bool rate=id==hw.racegrade_base+1;float raw[3];
  for(int n=0;n<3;n++)raw[n]=int16_t(u16(d+2*n))*(rate?.360f:.00980665f);
  for(int n=0;n<3;n++){int axis=rate?hw.gyro_axis[n]:hw.accel_axis[n];if(axis<0||axis>2)return;}
  for(int n=0;n<3;n++)if(rate)inputs.gyro[n]=raw[hw.gyro_axis[n]]*hw.gyro_sign[n];else inputs.accel[n]=raw[hw.accel_axis[n]]*hw.accel_sign[n];
  stamps[rate?4:3]=now;return;
 }
 // Native MS-DBW aggregate feedback is diagnostic only: never duplicate one
 // aggregate value into two allegedly independent APS/TPS channels.
 if(id==hw.dbwx2_base&&len==8&&d[7]==0){
  native_pedal=u16(d)/1023.0f;native_throttle=u16(d+2)/1023.0f;return;
 }
 if(!len||d[0]!=1)return;
 if(id==0x207&&len==4&&d[1]<=4){weather_state=d[1];inputs.weather_valid=d[1]==0;inputs.rain=d[2]==1;stamps[5]=now;}
 if(id==0x208&&len==8&&d[7]==0xA5&&d[1]<=3&&d[2]<=3&&d[3]<4&&d[4]<=1){
  controller.settings.tcs=Level(d[1]);controller.settings.awc=Level(d[2]);controller.settings.curve=d[3];controller.settings.weather=d[4];request_ack=d[6];
 }
 if(id==0x209&&len==8&&d[7]==0xA5&&d[1]<4){
  uint32_t bits=(uint32_t(d[2])<<24)|(uint32_t(d[3])<<16)|(uint32_t(d[4])<<8)|d[5];float v;memcpy(&v,&bits,4);
  if(!isfinite(v)||v<0||!valid(c))return;
  if(d[1]==0&&v<=c.hard_pitch)controller.settings.wheelie_target=v;
  else if(d[1]==1&&v>0&&v<=c.hard_pitch)controller.settings.wheelie_max=v;
  else if(d[1]==2&&v>0&&v<=c.lean_left)controller.settings.lean_left=v;
  else if(d[1]==3&&v>0&&v<=c.lean_right)controller.settings.lean_right=v;
  else return;
  request_ack=d[6];
 }
}
const Output& IO::update(uint32_t now){
 inputs.now=now;
 inputs.aps_valid=inputs.aps_valid&&stamps[0]&&now-stamps[0]<=c.timeout_ms;
 inputs.tps_valid=inputs.tps_valid&&stamps[1]&&now-stamps[1]<=c.timeout_ms;
 inputs.driver_fault=status_fault||channel_fault;
 inputs.dbw_valid=hw.throttle_body_verified&&hw.independent_kill_verified&&hw.dbwx2_v092_verified&&hw.dbwx2_custom_receive_verified&&hw.watchdog_verified&&current_at&&status_at&&channel_at&&now-current_at<=c.timeout_ms&&now-status_at<=c.timeout_ms&&now-channel_at<=c.timeout_ms;
 inputs.imu_valid=hw.mount_verified&&stamps[3]&&stamps[4]&&now-stamps[3]<=c.timeout_ms&&now-stamps[4]<=c.timeout_ms;
 if(!stamps[5]||now-stamps[5]>2000){inputs.weather_valid=false;weather_state=1;}
 return controller.update(inputs);
}
void IO::command(void (*send)(uint16_t,const uint8_t*,uint8_t)){
 const auto& o=controller.out;bool enable=o.dbw_enable&&!controller.stopped()&&hw.throttle_body_verified&&hw.independent_kill_verified&&hw.dbwx2_custom_receive_verified&&hw.watchdog_verified;
 // DBWX2 "Custom CAN receive": unsigned16 BE at byte0, 0..1000 position x10%.
 // Its table maps this axis to throttle opening; not a torque==throttle shortcut.
 uint8_t d[8]={0};float opening=enable?(o.throttle_target-c.throttle_min)/(c.throttle_max-c.throttle_min):0;
 p16(d,clamp(opening)*1000);d[2]=++sequence;d[3]=enable; p16(d+4,o.permitted*1000);send(hw.command_id,d,8);
 // No generic GPIO write: the actual enable/fault interlock wiring is not supplied.
}
void IO::publish(void (*send)(uint16_t,const uint8_t*,uint8_t)){
 const auto& o=controller.out;const auto& s=controller.settings;
 uint8_t a[8]={1,uint8_t(o.state),uint8_t(o.event),uint8_t(s.tcs),uint8_t(s.awc),s.curve,uint8_t((o.tcs_active?1:0)|(o.awc_active?2:0)|(o.front_airborne?4:0)|(o.air_allowed?8:0)|(o.dbw_enable?16:0)),request_ack};send(0x220,a,8);
 uint8_t b[8]={1,pct(o.rider),pct(o.permitted),pct(o.tcs_limit),pct(o.awc_limit),pct(o.lean_limit),pct(o.engine_limit),pct(o.mode_limit)};send(0x221,b,8);
 uint8_t d[8]={1};p16(d+1,inputs.front*100);p16(d+3,inputs.rear*100);p16(d+5,o.speed*100);d[7]=pct(o.sensor_confidence);send(0x222,d,8);
 p16(d+1,clamp(o.pitch*100,-32768,32767));p16(d+3,clamp(o.lean*100,-32768,32767));p16(d+5,clamp(o.pitch_rate*100,-32768,32767));d[7]=0;send(0x223,d,8);
 p16(d+1,clamp(o.slip,-3,3)*10000);p16(d+3,clamp(o.slip_target,0,3)*10000);d[5]=pct(o.slip_confidence);d[6]=pct(o.wheelie_confidence);d[7]=pct(o.front_contact);send(0x224,d,8);
 p16(d+1,o.throttle_target*100);p16(d+3,o.throttle_actual*100);p16(d+5,o.boost_target*10);d[7]=pct(o.air_margin);send(0x225,d,8);
 d[1]=o.faults>>24;d[2]=o.faults>>16;d[3]=o.faults>>8;d[4]=o.faults;d[5]=pct(o.sensor_confidence);d[6]=weather_state;d[7]=valid(c);send(0x226,d,8);
 p16(d+1,o.wheelie_target*100);p16(d+3,o.wheelie_max*100);float ll=isfinite(s.lean_left)?s.lean_left:c.lean_left,lr=isfinite(s.lean_right)?s.lean_right:c.lean_right;d[5]=isfinite(ll)?uint8_t(clamp(ll,0,255)):0;d[6]=isfinite(lr)?uint8_t(clamp(lr,0,255)):0;d[7]=s.weather;send(0x227,d,8);
 uint32_t bits;memcpy(&bits,&inputs.boost_request,4);d[1]=bits>>24;d[2]=bits>>16;d[3]=bits>>8;d[4]=bits;d[5]=d[6]=d[7]=0;send(0x228,d,8);
 send(0x229,calibrationFingerprint,8);
}
}
