#pragma once
#include <stdint.h>
namespace airshot {
// Trailing-window active-time accounting, independent of mode and event boundaries.
// Adjacent FIRING/TAPERING ticks coalesce. At capacity, merge the oldest intervals
// INCLUDING their idle gap: conservative overcount, never forgotten usage.
class RollingBudget {
 public:
  void advance(uint32_t now, uint32_t dt, bool active, uint32_t window) {
    if(!window || dt>=window) count=0;
    uint8_t retained=0;
    for(uint8_t n=0;n<count;n++) {
      uint32_t age=now-entries[n].end;
      if(age>=window) continue;
      Interval value=entries[n];
      if(value.duration>window-age) value.duration=window-age;
      entries[retained++]=value;
    }
    count=retained;
    if(active && dt && window) {
      uint32_t duration=dt<window?dt:window;
      uint32_t start=now-duration;
      if(count && entries[count-1].end==start) {
        entries[count-1].end=now;
        entries[count-1].duration+=duration;
      } else {
        if(count==capacity) {
          entries[1].duration=entries[1].end-(entries[0].end-entries[0].duration);
          for(uint8_t n=1;n<count;n++) entries[n-1]=entries[n];
          --count;
        }
        entries[count++]={now,duration};
      }
    }
    used=0;
    for(uint8_t n=0;n<count;n++) used+=entries[n].duration;
  }
  uint32_t usage() const {return used;}
 private:
  struct Interval {uint32_t end=0,duration=0;};
  static constexpr uint8_t capacity=64;
  Interval entries[capacity];
  uint8_t count=0;
  uint32_t used=0;
};
}
