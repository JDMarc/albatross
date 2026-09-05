#include "airshot_controller.h"
namespace airshot {
void Controller::end(const Inputs& i,Reason why,bool immediate) {
  out.reason=why;
  if(!immediate && out.state==State::FIRING) {
    out.state=State::TAPERING; taper_start=i.now;
    for(int n=0;n<4;n++) taper_from[n]=out.predicted[n];
    return;
  }
  out.last_duration=i.now-started; out.tank_after=i.tank;
  out.pressure_used=clamp(out.tank_before-i.tank,0,1e6f);
  out.state=State::RECOVERY; ended=i.now;
  for(int n=0;n<4;n++) out.valve[n]=out.predicted[n]=0;
  out.demand=0; recent_event=true;
}
const Outputs& Controller::update(const Inputs& i) {
  uint32_t dt=initialized?i.now-last:0;
  const bool was_active=out.state==State::FIRING || out.state==State::TAPERING;
  budget.advance(i.now,dt,was_active,c.budget_window_ms);
  const uint32_t used=budget.usage();
  // One existing recovery interval is the no-fire cooldown; one further interval
  // is the bounded RECOVERY-profile context. Long-idle events use normal profiles.
  if(recent_event && i.now-ended>=2*c.recovery_ms) recent_event=false;
  float rider_rate=dt?(i.rider-last_rider)*1000.0f/dt:0;
  float rate=dt?(meanBoost(i)-last_boost)*1000.0f/dt:0;
  if(dt) out.boost_rate+=(float(dt)/(100.0f+dt))*(rate-out.boost_rate);
  if(i.manual!=button_raw) {button_raw=i.manual;button_since=i.now;}
  bool edge=false;
  if(i.now-button_since>=c.debounce_ms && button!=button_raw) {button=button_raw;edge=button;}
  out.manual_request=button;
  last=i.now; last_rider=i.rider; last_boost=meanBoost(i); initialized=true;
  float error=i.target-meanBoost(i);
  out.demand=c.boost_full>0?clamp(error/c.boost_full,0,1)*clamp(1-out.boost_rate/c.spool_rate,0,1):0;
  bool candidate=out.demand>=c.auto_start && error>c.boost_start && rider_rate>=c.transient_rate;
  if(out.demand<c.auto_reset && !button) auto_latched=false;
  out.auto_request=mode==Mode::AUTO && candidate;
  out.available=c.full_tank>c.min_tank?clamp((i.tank-c.min_tank)/(c.full_tank-c.min_tank),0,1):0;
  bool request=edge || (out.auto_request && !auto_latched);
  if(out.auto_request && request) auto_latched=true;
  Reason safe=permissive(c,i);
  if(mode==Mode::OFF) {
    if(out.state==State::FIRING || out.state==State::TAPERING) end(i,Reason::OFF,true);
    out.state=State::DISABLED; out.reason=Reason::OFF; out.demand=0;
    for(int n=0;n<4;n++) out.valve[n]=out.predicted[n]=0;
    if(edge) {++out.event_id;out.accepted=false;}
    return out;
  }
  bool active=out.state==State::FIRING || out.state==State::TAPERING;
  if(active) {
    const auto& p=c.profiles[uint8_t(out.profile)];
    Reason terminate=Reason::NONE;
    if(safe!=Reason::NONE) terminate=safe;
    else if(used>=c.budget_ms) terminate=Reason::BUDGET;
    else if(i.now-started>=p.maximum_ms) terminate=Reason::MAX_DURATION;
    if(terminate!=Reason::NONE) {end(i,terminate,true);return out;}
    if(out.state==State::FIRING) {
      if(error<=c.boost_done || out.boost_rate>=c.spool_rate) end(i,Reason::SPOOL_COMPLETE,false);
      else if(manual_event && !button) end(i,Reason::RELEASED,false);
    }
    if(out.state==State::FIRING) mix(c,i,out.profile,out.demand,float(i.now-started)/p.maximum_ms,out.predicted);
    else if(out.state==State::TAPERING) {
      float remaining=clamp(1-float(i.now-taper_start)/c.taper_ms,0,1);
      for(int n=0;n<4;n++) out.predicted[n]=taper_from[n]*remaining;
      if(remaining<=0) {end(i,out.reason,true);return out;}
    }
    for(int n=0;n<4;n++) out.valve[n]=out.shadow?0:out.predicted[n];
    return out;
  }
  if(recent_event && i.now-ended<c.recovery_ms) {
    out.state=State::RECOVERY;
    if(request) {++out.event_id;out.accepted=false;out.reason=Reason::RECOVERY;}
    return out;
  }
  if(safe!=Reason::NONE) {out.state=safe==Reason::DRIVER?State::FAULT:State::INHIBITED;out.reason=safe;}
  else {out.state=mode==Mode::AUTO?State::ARMED:State::READY;out.reason=Reason::NONE;}
  if(!request) return out;
  ++out.event_id; out.accepted=false; out.manual_request=edge; manual_event=edge;
  out.state=State::REQUESTED;
  out.state=State::PRECHECK;
  if(safe==Reason::NONE && error<=c.boost_done) safe=Reason::ALREADY_BOOSTED;
  if(safe==Reason::NONE && used>=c.budget_ms) safe=Reason::BUDGET;
  // AUTO is available through mode selection; shadow remains an explicit tool.
  if(safe!=Reason::NONE) {out.state=State::INHIBITED;out.reason=safe;return out;}
  out.accepted=true; out.profile=selectProfile(c,i,recent_event);
  recent_event=false;
  out.shadow=c.auto_shadow || c.stage==7;
  // Shadow stage cannot be bypassed by FIRE.
  if(c.stage==7) out.shadow=true;
  out.reason=out.shadow?Reason::SHADOW:Reason::NONE;
  out.state=State::FIRING; started=i.now; out.tank_before=i.tank; out.tank_after=i.tank;
  mix(c,i,out.profile,out.demand,0,out.predicted);
  for(int n=0;n<4;n++) out.valve[n]=out.shadow?0:out.predicted[n];
  return out;
}
}
