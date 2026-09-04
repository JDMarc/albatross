#pragma once
#include "airshot_config.h"
namespace airshot {
Profile selectProfile(const Config&,const Inputs&,bool recovery);
void mix(const Config&,const Inputs&,Profile,float demand,float progress,float* commands);
}
