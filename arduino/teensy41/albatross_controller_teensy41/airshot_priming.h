#pragma once
#include "airshot_config.h"
namespace airshot {
enum class PrimeState:uint8_t { UNCONFIGURED, OFF, INHIBITED, FILLING, PRIMED, FAULT, SHADOW };
struct PrimeConfig {
  bool commissioned=false; // Includes verified post-master location of 0x193.
  float tank_rearm_psi=NAN;
  uint32_t stable_ms=0, fill_timeout_ms=0;
};
// Pure state machine; actuator writes remain in the main-controller IO layer.
class Priming {
 public:
  PrimeState state=PrimeState::UNCONFIGURED;
  bool open=false, ready=false;
  bool fault()const{return latched;}
  void update(const PrimeConfig& p,const Config& c,const Inputs& i,Mode mode,bool permit) {
    ready=false;
    if(mode==Mode::OFF){reset();latched=false;state=PrimeState::OFF;return;}
    if(latched){reset();state=PrimeState::FAULT;return;}
    const bool configured=p.commissioned && validConfig(c) &&
      isfinite(p.tank_rearm_psi) && p.tank_rearm_psi>c.min_tank && p.tank_rearm_psi<=c.full_tank &&
      p.stable_ms>0 && p.stable_ms<0x80000000U && p.fill_timeout_ms>p.stable_ms && p.fill_timeout_ms<0x80000000U;
    if(!configured){reset();state=PrimeState::UNCONFIGURED;return;}
    if(c.auto_shadow || c.stage==7){reset();state=PrimeState::SHADOW;return;}
    // Valid but low manifold pressure is expected before opening. Invalid or
    // stale pressure is never an excuse to energize the master blindly.
    bool healthy=permit && i.can_valid && i.pressure_valid && i.driver_valid && !i.driver_faults &&
      i.dbw_valid && i.vdc_valid && !i.ecu_protection && !i.traction_fault && !i.tcs && !i.awc &&
      i.wg_valid && i.thermal_valid && !i.wmi_fault && isfinite(i.rpm) && i.rpm>0 &&
      isfinite(i.tank) && i.tank>=c.min_tank && isfinite(i.regulated) && i.regulated>=0 &&
      i.regulated<=c.max_regulated && isfinite(i.target) && isfinite(i.coolant) && isfinite(i.oil) &&
      i.coolant>=c.min_coolant && i.oil>=c.min_oil;
    for(int n=0;n<2;n++)healthy=healthy && isfinite(i.boost[n]) && i.boost[n]<=i.target+c.overboost_margin &&
      isfinite(i.head[n]) && i.head[n]<c.thermal_head && isfinite(i.egt[n]) && i.egt[n]<c.thermal_egt &&
      isfinite(i.turbine[n]) && i.turbine[n]<c.thermal_turbine && isfinite(i.charge[n]) && i.charge[n]<c.thermal_charge &&
      isfinite(i.ic[n]) && i.ic[n]<c.thermal_ic;
    if(!healthy){reset();state=PrimeState::INHIBITED;return;}
    if(!open){
      if(i.tank<p.tank_rearm_psi){state=PrimeState::INHIBITED;return;}
      open=true;started=i.now;stable=false;state=PrimeState::FILLING;
    }
    const bool pressure_ok=i.regulated>=c.min_regulated && i.regulated>=meanBoost(i)+c.min_headroom;
    if(state==PrimeState::PRIMED){
      if(!pressure_ok){latched=true;reset();state=PrimeState::FAULT;return;}
      ready=true;return;
    }
    if(pressure_ok){if(!stable){stable=true;stable_since=i.now;}}
    else stable=false;
    // Timeout wins at the boundary; no repeated automatic fill/leak cycling.
    if(i.now-started>=p.fill_timeout_ms){latched=true;reset();state=PrimeState::FAULT;return;}
    if(stable && i.now-stable_since>=p.stable_ms){state=PrimeState::PRIMED;ready=true;}
  }
 private:
  bool latched=false,stable=false;
  uint32_t started=0,stable_since=0;
  void reset(){open=false;ready=false;stable=false;}
};
}
