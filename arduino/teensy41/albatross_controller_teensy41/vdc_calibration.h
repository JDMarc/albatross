#pragma once
#include "vdc.h"
namespace vdc {
static const uint8_t calibrationFingerprint[8]={66,173,0,2,201,36,242,112};
inline Config engineeringCalibration(){
 Config c;
 c.aid[0].slip=0.12;
 c.aid[1].slip=0.09;
 c.aid[2].slip=0.06;
 c.validated=false;
 return c;
}
}
