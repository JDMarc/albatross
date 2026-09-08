#include "sensor_conversion.h"
#include "thermal_hardware.h"
#include <math.h>

float convertNtcToCelsius(const SensorConfig& c,int16_t raw,float excitation_v) {
  const float v=raw*ThermalHardware::ADC_LSB_V;
  if(!isfinite(excitation_v) || excitation_v<=0 || v<=0 || v>=excitation_v ||
     c.pullup_ohm<=0 || c.r0_ohm<=0 || c.beta_k<=0) return NAN;
  const float r=c.pullup_ohm*v/(excitation_v-v);
  return 1.0f/(1.0f/(c.t0_c+273.15f)+logf(r/c.r0_ohm)/c.beta_k)-273.15f;
}
float convertRtdToCelsius(uint16_t raw) {
  using namespace ThermalHardware;
  if(raw==0 || raw>=32767) return NAN;
  const float ratio=(raw/32768.0f)*RTD_RREF/RTD_R0;
  // Invert Callendar-Van Dusen over the platinum RTD domain.
  // Bisection avoids cancellation around zero and handles the negative-C term.
  float lo=-200,hi=850;
  for(uint8_t n=0;n<32;++n) {
    const float t=(lo+hi)*0.5f;
    const float r=1+RTD_A*t+RTD_B*t*t+(t<0?RTD_C*(t-100)*t*t*t:0);
    if(r<ratio) lo=t;else hi=t;
  }
  const float t=(lo+hi)*0.5f;
  if(t<=-199.99f || t>=849.99f) return NAN;
  return t;
}
