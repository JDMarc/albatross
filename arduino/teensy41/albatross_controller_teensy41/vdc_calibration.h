#pragma once
#include "vdc.h"
namespace vdc {
static const uint8_t calibrationFingerprint[8]={71,185,56,209,215,17,182,134};
inline Config engineeringCalibration(){
 Config c;
 c.aid[0].slip=0.12;
 c.curves[0][0]=0;
 c.curves[0][1]=0.15;
 c.curves[0][2]=0.35;
 c.curves[0][3]=0.65;
 c.curves[0][4]=1;
 c.aid[1].slip=0.09;
 c.curves[1][0]=0;
 c.curves[1][1]=0.2;
 c.curves[1][2]=0.45;
 c.curves[1][3]=0.7;
 c.curves[1][4]=1;
 c.aid[2].slip=0.06;
 c.curves[2][0]=0;
 c.curves[2][1]=0.3;
 c.curves[2][2]=0.55;
 c.curves[2][3]=0.8;
 c.curves[2][4]=1;
 c.validated=false;
 return c;
}
}
