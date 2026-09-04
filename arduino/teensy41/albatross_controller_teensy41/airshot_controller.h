#pragma once
#include "airshot_safety.h"
#include "airshot_profiles.h"
namespace airshot {
class Controller {
 public:
  explicit Controller(const Config& config):c(config){}
  void setMode(Mode next) { mode=next; }
  Mode getMode() const { return mode; }
  void configure(const Config& next) { *this=Controller(next); }
  const Outputs& update(const Inputs&);
  const Outputs& output() const { return out; }
 private:
  Config c; Mode mode=Mode::OFF; Outputs out;
  uint32_t last=0, started=0, recovery_until=0, window=0, used=0, button_since=0, taper_start=0;
  float last_rider=0,last_boost=0, taper_from[4]={0};
  bool initialized=false, button_raw=false, button=false, auto_latched=false, manual_event=false, had_event=false;
  void end(const Inputs&,Reason,bool immediate);
};
}
