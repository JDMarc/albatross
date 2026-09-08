#pragma once
#include <cstdint>
#include <cstddef>
#include <cmath>
#include <cstring>
using std::isfinite;
constexpr int HIGH=1,LOW=0,OUTPUT=1;
extern uint32_t fake_ms;
extern int selected_cs;
inline uint32_t millis(){return fake_ms;}
inline void pinMode(int,int){}
void digitalWrite(int,int);
inline void delayMicroseconds(int){}
