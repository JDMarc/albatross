#pragma once
#include "types.h"
namespace fm {
// Pure deterministic coordinator. No driver, GPIO, CAN or logging I/O here.
class Manager {
 public:
 Policy policies[count];Fault faults[count];Capabilities capabilities;
 void begin(uint32_t now) {
   dt=seen?now-last:0;last=now;seen=true;
   for(unsigned n=0;n<count;n++){auto& f=faults[n];if(f.active)f.total_active_ms+=dt;f.evidence=Evidence::UNKNOWN;observed[n]=false;}
 }
 void observe(Id id,Evidence e,uint8_t confidence=100,uint32_t primary=0,uint32_t corroborating=0,uint32_t suspected=0) {
   auto& f=faults[unsigned(id)];
   // BAD > UNKNOWN > GOOD, independent of monitor order. An unobserved slot
   // is distinct from an explicit UNKNOWN supplied by an enabled monitor.
   if(observed[unsigned(id)]&&(f.evidence==Evidence::BAD||(f.evidence==Evidence::UNKNOWN&&e==Evidence::GOOD)))return;
   observed[unsigned(id)]=true;
   f.evidence=e;f.confidence=confidence;f.primary_signal=primary;f.corroborating=corroborating;f.suspected=suspected;
 }
 void observe(Id id,bool bad){observe(id,bad?Evidence::BAD:Evidence::GOOD);}
 void verify(Id id,Result result){faults[unsigned(id)].result=result;}
 bool serviceClear(Id id,bool stopped,bool authorized) {
   auto& f=faults[unsigned(id)];auto policy=policies[unsigned(id)].clear;
   if(!stopped||!authorized||f.evidence!=Evidence::GOOD||policy!=Clear::SERVICE_CLEAR)return false;
   f.active=false;f.state=Life::CLEARED;f.stable=f.timing=false;return true;
 }
 const Capabilities& finish(uint32_t now) {
   capabilities=Capabilities{};
   for(unsigned n=0;n<count;n++) {
     auto& f=faults[n];const auto& p=policies[n];
     if(f.evidence==Evidence::BAD) {
       f.last_seen=now;f.stable=false;
       if(!f.active) {
         if(!f.timing){f.timing=true;f.since=now;f.state=Life::SUSPECT;}
         if(now-f.since>=p.confirm_ms){f.active=true;f.state=Life::CONFIRMED;f.timing=false;
           if(!f.episodes)f.first_seen=now;++f.episodes;f.result=Result::NOT_REQUESTED;}
       } else if(f.state==Life::CONFIRMED)f.state=Life::ACTIVE;
       else if(f.state==Life::ACTIVE&&(p.remove||p.actions)){f.state=Life::MITIGATING;f.result=Result::REQUESTED;}
       else if(f.result==Result::CONTAINED)f.state=Life::DEGRADED;
       else if(f.state==Life::RECOVERING)f.state=Life::MITIGATING;
     } else if(f.evidence==Evidence::GOOD) {
       f.timing=false;
       if(!f.active){if(f.state!=Life::CLEARED)f.state=Life::NORMAL;}
       else if(p.clear==Clear::AUTO_CLEAR){f.active=false;f.state=Life::CLEARED;}
       else if(p.clear==Clear::CLEAR_AFTER_STABLE&&p.recovery_configured){
         if(!f.stable){f.stable=true;f.since=now;}f.state=Life::RECOVERING;
         if(now-f.since>=p.recover_ms){f.active=false;f.stable=false;f.state=Life::CLEARED;}
       }
     } else {f.stable=false;f.timing=false;if(!f.active)f.state=Life::NORMAL;}
     if(!f.active)continue;
     if(unsigned(p.severity)>unsigned(f.worst))f.worst=p.severity;
     if(p.clear==Clear::LATCHED||p.clear==Clear::CLEAR_AFTER_KEY_CYCLE||p.clear==Clear::SERVICE_CLEAR)f.state=Life::LATCHED;
     capabilities.inhibited|=p.remove;capabilities.actions|=p.actions;
     if(unsigned(p.ride)>unsigned(capabilities.ride))capabilities.ride=p.ride;
     if(isfinite(p.torque))capabilities.torque=minimum(capabilities.torque,p.torque);
     if(isfinite(p.boost))capabilities.boost=minimum(capabilities.boost,p.boost);
     if(isfinite(p.rpm))capabilities.rpm=minimum(capabilities.rpm,p.rpm);
     if((p.remove&FULL_DBW)&&!isfinite(p.torque)){
       capabilities.missing_calibration=true;
       // Never publish full torque for an explicitly inhibited, uncalibrated
       // DBW envelope. Retain the project's zero-authority hard fallback.
       capabilities.torque=0;
     }
     if((p.remove&FULL_RPM)&&!isfinite(p.rpm))capabilities.missing_calibration=true;
   }
   capabilities.available=ALL&~capabilities.inhibited;
   capabilities.degraded=capabilities.inhibited;
   return capabilities;
 }
 private:uint32_t last=0,dt=0;bool seen=false,observed[count]={};
};
}
