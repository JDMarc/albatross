// ISOLATED BENCH FIXTURE ONLY. Never flash this image onto an installed vehicle.
#include <FlexCAN_T4.h>
#include <Watchdog_t4.h>
#ifdef ALBATROSS_BENCH_NATIVE_TEST
#ifdef ARDUINO
#error Synthetic native-test profile must never be compiled for an Arduino board
#endif
#include "../../../tests/bench_io_profile.h"
#else
#include "bench_config.h"
#endif
#include <stdio.h>
#include <string.h>
FlexCAN_T4<CAN1,RX_SIZE_256,TX_SIZE_16> bus;
// WDT1's library interface is seconds with half-second resolution. Do not
// substitute WDT3: the installed library uses different timeout scaling there.
WDT_T4<WDT1> watchdog;
bench::Core core(fixtureConfig());
bool configured=false,pending=false;
uint32_t poll_at=0,command_at=0,status_at=0,reply_id=0;
uint16_t token=0;uint8_t group=0;
const uint16_t offsets[]={0,64,76,60};const uint8_t lengths[]={8,4,8,4};
char line[96];size_t used=0;bool overflow=false;
uint32_t msid(uint16_t offset,uint8_t kind,uint8_t from,uint8_t to,uint8_t table){return (uint32_t(offset)<<18)|(uint32_t(kind)<<15)|(from<<11)|(to<<7)|(table<<3);}
uint16_t le(const uint8_t* d){return uint16_t(d[0])|(uint16_t(d[1])<<8);}
bool allowedPin(int p){return p>=0&&p<=41&&p!=13&&p!=22&&p!=23;}
void permitOff(){if(allowedPin(PERMIT_PIN))digitalWrite(PERMIT_PIN,LOW);}
bool send(uint32_t id,bool ext,const uint8_t* d,uint8_t len){
 CAN_message_t m;m.id=id;m.flags.extended=ext;m.len=len;memcpy(m.buf,d,len);
 if(!bus.write(m)){core.stop(bench::LINK,true);permitOff();return false;}return true;
}
void parse(){
 if(!strcmp(line,"STOP")){core.stop();permitOff();return;}
 unsigned long epoch=0,seq=0,target=0;char tail;
 if(sscanf(line,"ARM %lu %c",&epoch,&tail)==1){core.arm(epoch);return;}
 if(sscanf(line,"HOLD %lu %lu %lu %c",&epoch,&seq,&target,&tail)==3&&target<=1000){core.hold(epoch,seq,target);return;}
 core.stop(bench::LINK,true);permitOff();
}
void setup(){
 permitOff();if(allowedPin(PERMIT_PIN)){pinMode(PERMIT_PIN,OUTPUT);permitOff();}
 Serial.begin(115200);
 configured=bench::valid(core.c)&&INTERLOCK_VERIFIED&&DBWX2_092_VERIFIED&&CUSTOM_RECEIVE_VERIFIED&&COMMAND_LOSS_VERIFIED&&PROFILE_REVISION&&
  allowedPin(BENCH_KEY_PIN)&&allowedPin(DEADMAN_PIN)&&allowedPin(PERMIT_PIN)&&BENCH_KEY_PIN!=DEADMAN_PIN&&BENCH_KEY_PIN!=PERMIT_PIN&&DEADMAN_PIN!=PERMIT_PIN&&
  LOCAL_NODE<=14&&DBWX2_NODE<=14&&LOCAL_NODE!=DBWX2_NODE&&DBWX2_COMMAND_ID>0&&DBWX2_COMMAND_ID<=0x7ff&&
  isfinite(WATCHDOG_SECONDS)&&WATCHDOG_SECONDS>=0.5f&&WATCHDOG_SECONDS<=128&&floorf(WATCHDOG_SECONDS*2)==WATCHDOG_SECONDS*2&&POLL_MS&&COMMAND_MS&&COMMAND_MS<core.c.lease_ms;
 if(!configured){core.c.verified=false;return;}
 core.reason=bench::NOT_READY;
 pinMode(BENCH_KEY_PIN,INPUT_PULLUP);pinMode(DEADMAN_PIN,INPUT_PULLUP);
 bus.begin();bus.setBaudRate(500000);
 WDT_timings_t timing={};timing.trigger=0;timing.timeout=WATCHDOG_SECONDS;watchdog.begin(timing);
}
void loop(){
 uint32_t now=millis();
 core.tick(now,configured&&digitalRead(BENCH_KEY_PIN)==LOW,configured&&digitalRead(DEADMAN_PIN)==LOW);
 // Remove permit before USB/CAN work. External independent kill remains required.
 if(!core.permit)permitOff();
 if(!Serial&&(core.state==bench::ARMED||core.state==bench::ACTIVE))core.stop(bench::LINK);
 for(int n=0;n<128&&Serial.available();n++){
  char ch=Serial.read();if(ch=='\r')continue;
  if(ch=='\n'){if(overflow){core.stop(bench::LINK,true);permitOff();}else{line[used]=0;parse();}used=0;overflow=false;}
  else if(used<sizeof(line)-1)line[used++]=ch;else overflow=true;
 }
 if(configured){
  CAN_message_t m;
  for(int n=0;n<64&&bus.read(m);n++){
   if(m.flags.remote)continue;
   if(!m.flags.extended&&m.id==DBWX2_COMMAND_ID){core.stop(bench::FOREIGN_WRITER,true);permitOff();}
   if(!pending||!m.flags.extended||m.id!=reply_id||m.len!=lengths[group]||now-poll_at>core.c.feedback_ms)continue;
   const uint8_t* d=m.buf;
   if(group==0){core.f.tps[0]=le(d+4);core.f.tps[1]=le(d+6);}
   if(group==1)core.f.current=le(d)*.01f;
   if(group==2)core.f.status_bad=le(d)!=0||d[4]!=1||d[5]!=0||(d[7]&0x1c)!=0;
   if(group==3)core.f.channel_bad=(d[0]&0x3e)!=0||d[1]!=0;
   core.f.seen[group]=true;core.f.at[group]=now;pending=false;token=(token+1)&2047;group=(group+1)%4;
  }
  if(pending&&now-poll_at>core.c.feedback_ms){pending=false;token=(token+1)&2047;group=(group+1)%4;}
  if(!pending&&now-poll_at>=POLL_MS){
   uint8_t d[]={6,uint8_t(token>>3),uint8_t(((token&7)<<5)|lengths[group])};
   reply_id=msid(token,2,DBWX2_NODE,LOCAL_NODE,6);poll_at=now;
   pending=send(msid(offsets[group],1,LOCAL_NODE,DBWX2_NODE,5),true,d,3);
  }
  // Recheck newly received faults before energizing the fixture permit.
  core.tick(now,digitalRead(BENCH_KEY_PIN)==LOW,digitalRead(DEADMAN_PIN)==LOW);
  digitalWrite(PERMIT_PIN,core.permit?HIGH:LOW);
  if(now-command_at>=COMMAND_MS){
   command_at=now;uint16_t value=core.permit?uint16_t(core.command*10):0;
   uint8_t d[8]={uint8_t(value>>8),uint8_t(value),0,0,0,0,0,0};send(DBWX2_COMMAND_ID,false,d,8);
  }
 }
 if(now-status_at>=50&&Serial.availableForWrite()>=300){
  status_at=now;char out[300];
  // Integer sentinels avoid invalid JSON NaN. Validity is an explicit field.
  bool good=core.health()==bench::NONE;
  snprintf(out,sizeof(out),"{\"protocol\":1,\"profile\":%lu,\"configured\":%d,\"epoch\":%lu,\"seq\":%lu,\"state\":%d,\"reason\":%d,\"key\":%d,\"deadman\":%d,\"permit\":%d,\"good\":%d,\"target\":%d,\"actual\":%d,\"current_ma\":%d,\"max\":%d,\"lease_ms\":%lu}\n",
   (unsigned long)PROFILE_REVISION,configured,(unsigned long)core.epoch,(unsigned long)core.sequence,int(core.state),int(core.reason),core.key,core.deadman,core.permit,good,
   int(core.command*10),good?int(core.position(0)*10):-1,good?int(core.f.current*1000):-1,configured?int(core.c.max_pct*10):0,(unsigned long)core.c.lease_ms);
  Serial.print(out);
 }
 if(configured)watchdog.feed();
}
