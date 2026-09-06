#pragma once
constexpr int WDT1=1;
struct WDT_timings_t {double timeout=0,trigger=0;};
template<int>struct WDT_T4 {void begin(WDT_timings_t){}void feed(){}};
