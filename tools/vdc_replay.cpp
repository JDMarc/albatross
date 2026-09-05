// Offline ONLY: CSV inputs run through the exact firmware classifier/controller.
#include <iostream>
#include <sstream>
#include <vector>
#include <cstdio>
#include <cstring>
#include "../arduino/teensy41/albatross_controller_teensy41/vdc_calibration.h"
#ifdef VDC_SYNTHETIC_TEST
#include "../tests/vdc_fixture.h"
#endif
int main(int argc,char** argv){
 if(argc==2&&strcmp(argv[1],"--fingerprint")==0){
#ifdef VDC_SYNTHETIC_TEST
  puts("synthetic-test-only");
#else
  for(auto v:vdc::calibrationFingerprint)printf("%02x",v);puts("");
#endif
  return 0;
 }
#ifdef VDC_SYNTHETIC_TEST
 auto config=testCalibration();std::cerr<<"SYNTHETIC TEST CALIBRATION - NOT FOR VEHICLE USE\n";
#else
 auto config=vdc::engineeringCalibration();
#endif
 vdc::Controller core(config);std::string line;uint32_t last=0;bool seen=false;
 std::cout<<"ms,state,event,faults,pitch,lean,slip,rider,permitted,throttle,boost,tcs,awc,air\n";
 while(std::getline(std::cin,line)){
  if(line.empty()||line[0]=='#')continue;
  std::stringstream row(line);std::string cell;std::vector<float> v;
  try{while(std::getline(row,cell,','))v.push_back(std::stof(cell));}catch(...){std::cerr<<"Invalid CSV number\n";return 2;}
  if(v.size()!=38||!std::isfinite(v[0])||v[0]<0||v[0]>4294967040.0f){std::cerr<<"Expected 38 input columns\n";return 2;}
  if(v[37]!=0&&v[37]!=1)return 2;
  if(v[37])core.stop();
  if(!std::isfinite(v[4])||v[4]<0||v[4]>6)return 2;
  for(int n=30;n<33;n++)if(!std::isfinite(v[n])||v[n]!=std::floor(v[n]))return 2;
  vdc::Inputs i;i.now=uint32_t(v[0]);if(seen&&i.now<=last){std::cerr<<"Non-monotonic replay\n";return 2;}seen=true;last=i.now;
  i.front=v[1];i.rear=v[2];i.rpm=v[3];i.gear=uint8_t(v[4]);i.boost=v[5];i.boost_request=v[6];i.engine_limit=v[7];i.mode_limit=v[8];
  for(int n=0;n<3;n++){i.accel[n]=v[9+n];i.gyro[n]=v[12+n];}
  i.aps[0]=v[15];i.aps[1]=v[16];i.tps[0]=v[17];i.tps[1]=v[18];i.motor_current=v[19];
  for(int n=20;n<30;n++)if(v[n]!=0&&v[n]!=1){std::cerr<<"Invalid flag\n";return 2;}
  i.front_valid=v[20];i.rear_valid=v[21];i.imu_valid=v[22];i.aps_valid=v[23];i.tps_valid=v[24];i.dbw_valid=v[25];i.engine_valid=v[26];i.driver_fault=v[27];i.rain=v[28];i.weather_valid=v[29];
  if(v[30]<0||v[30]>3||v[31]<0||v[31]>3||v[32]<0||v[32]>2)return 2;
  core.settings.tcs=vdc::Level(int(v[30]));core.settings.awc=vdc::Level(int(v[31]));core.settings.curve=uint8_t(v[32]);
  core.settings.wheelie_target=v[33];core.settings.wheelie_max=v[34];core.settings.lean_left=v[35];core.settings.lean_right=v[36];
  auto o=core.update(i);
  std::cout<<i.now<<','<<int(o.state)<<','<<int(o.event)<<','<<o.faults<<','<<o.pitch<<','<<o.lean<<','<<o.slip<<','<<o.rider<<','<<o.permitted<<','<<o.throttle_target<<','<<o.boost_target<<','<<o.tcs_active<<','<<o.awc_active<<','<<o.air_allowed<<'\n';
 }
}
