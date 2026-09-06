#pragma once
#include <stdint.h>
#include <math.h>

// Bench-only supervisor. This is NOT the DBWX2 motor PID or road VDC.
namespace bench {
struct Config {
 bool verified=false;
 uint32_t lease_ms=0, feedback_ms=0, arm_ms=0, run_ms=0, tracking_ms=0;
 float max_pct=NAN, hard_actual_pct=NAN, rise_pct_s=NAN, current_a=NAN, pair_error_pct=NAN;
 float tracking_pct=NAN, start_pct=NAN, rail_low=NAN, rail_high=NAN;
 float tps_closed[2]={NAN,NAN},tps_open[2]={NAN,NAN};
};
inline bool valid(const Config& c) {
 if(!c.verified||!c.lease_ms||!c.feedback_ms||!c.arm_ms||!c.run_ms||!c.tracking_ms)return false;
 if(c.lease_ms>=0x80000000U||c.feedback_ms>=0x80000000U||c.arm_ms>=0x80000000U||c.run_ms>=0x80000000U||c.tracking_ms>=0x80000000U)return false;
 const float vals[]={c.max_pct,c.hard_actual_pct,c.rise_pct_s,c.current_a,c.pair_error_pct,c.tracking_pct,c.start_pct,c.rail_low,c.rail_high,c.tps_closed[0],c.tps_closed[1],c.tps_open[0],c.tps_open[1]};
 for(float v:vals)if(!isfinite(v))return false;
 if(c.hard_actual_pct<c.max_pct||c.hard_actual_pct>100)return false;
 if(c.max_pct<=0||c.max_pct>100||c.rise_pct_s<=0||c.current_a<=0||c.pair_error_pct<=0||c.pair_error_pct>100||c.tracking_pct<=0||c.tracking_pct>100||c.start_pct<0||c.start_pct>c.max_pct||c.rail_low<0||c.rail_high>65535||c.rail_low>=c.rail_high)return false;
 for(int n=0;n<2;n++)if(c.tps_closed[n]==c.tps_open[n]||c.tps_closed[n]<=c.rail_low||c.tps_closed[n]>=c.rail_high||c.tps_open[n]<=c.rail_low||c.tps_open[n]>=c.rail_high)return false;
 return true;
}
struct Feedback {
 float tps[2]={NAN,NAN},current=NAN;
 bool seen[4]={false,false,false,false},status_bad=true,channel_bad=true;
 uint32_t at[4]={0,0,0,0};
};
enum State {IDLE,ARMED,ACTIVE,FAULT};
enum Reason {NONE,CONFIG,NOT_READY,KEY_OFF,RELEASED,LEASE,ARM_EXPIRED,RUN_ENDED,FEEDBACK,DRIVER,CURRENT,TPS,TRACKING,STOPPED,LINK,FOREIGN_WRITER};
class Core {
 public:
 Config c; Feedback f; State state=IDLE; Reason reason=CONFIG;
 bool key=false,deadman=false,permit=false;
 uint32_t epoch=1,sequence=0; float request=0,command=0;
 uint32_t now=0,last_tick=0,armed_at=0,last_hold=0,run_at=0,bad_at=0;
 bool tracking_bad=false,have_tick=false;
 explicit Core(Config config):c(config){}
 float position(int n)const{return (f.tps[n]-c.tps_closed[n])*100/(c.tps_open[n]-c.tps_closed[n]);}
 Reason health()const {
  if(!valid(c))return CONFIG;
  for(int n=0;n<4;n++)if(!f.seen[n]||uint32_t(now-f.at[n])>c.feedback_ms)return FEEDBACK;
  if(f.status_bad||f.channel_bad)return DRIVER;
  if(!isfinite(f.current)||f.current<0||f.current>c.current_a)return CURRENT;
  for(float t:f.tps)if(!isfinite(t)||t<=c.rail_low||t>=c.rail_high)return TPS;
  if(fabsf(position(0)-position(1))>c.pair_error_pct)return TPS;
  for(int n=0;n<2;n++)if(position(n)<-c.pair_error_pct||position(n)>100+c.pair_error_pct)return TPS;
  return NONE;
 }
 void stop(Reason why=STOPPED,bool latch=false){
  if(state==FAULT)return;
  state=latch?FAULT:IDLE;reason=why;permit=false;request=command=0;tracking_bad=false;
  ++epoch;if(!epoch)++epoch;sequence=0;
 }
 bool arm(uint32_t token){
  if(state!=IDLE||token!=epoch)return false;
  reason=health();if(reason!=NONE)return false;
  if(!key){reason=KEY_OFF;return false;}
  if(deadman||position(0)>c.start_pct||position(1)>c.start_pct){reason=NOT_READY;return false;}
  state=ARMED;reason=NONE;armed_at=now;sequence=0;return true;
 }
 bool hold(uint32_t token,uint32_t seq,uint16_t permille){
  if((state!=ARMED&&state!=ACTIVE)||token!=epoch||seq<=sequence||seq==0||permille>1000||permille/10.0f>c.max_pct||!key||!deadman||health()!=NONE)return false;
  if(state==ARMED){state=ACTIVE;run_at=now;}
  sequence=seq;last_hold=now;request=permille/10.0f;return true;
 }
 void tick(uint32_t time,bool bench_key,bool held){
  uint32_t dt=have_tick?time-last_tick:0;now=time;last_tick=time;have_tick=true;
  key=bench_key;deadman=held;
  if(state==FAULT){permit=false;command=0;return;}
  if(state==ARMED||state==ACTIVE){
   if(!key){stop(KEY_OFF);return;}
   Reason h=health();if(h!=NONE){stop(h,true);return;}
   if(dt>c.lease_ms){stop(LINK,true);return;}
  }
  if(state==ARMED&&uint32_t(now-armed_at)>=c.arm_ms){stop(ARM_EXPIRED);return;}
  if(state==ACTIVE){
   if(position(0)>c.hard_actual_pct||position(1)>c.hard_actual_pct){stop(TPS,true);return;}
   if(!deadman){stop(RELEASED);return;}
   if(uint32_t(now-last_hold)>=c.lease_ms){stop(LEASE);return;}
   if(uint32_t(now-run_at)>=c.run_ms){stop(RUN_ENDED);return;}
   command=fminf(request,command+c.rise_pct_s*dt/1000.0f);
   bool bad=fabsf(position(0)-command)>c.tracking_pct||fabsf(position(1)-command)>c.tracking_pct;
   if(bad&&!tracking_bad){bad_at=now;tracking_bad=true;}
   if(!bad)tracking_bad=false;
   if(tracking_bad&&uint32_t(now-bad_at)>=c.tracking_ms){stop(TRACKING,true);return;}
   permit=true;
  }else{permit=false;command=0;}
 }
};
}
