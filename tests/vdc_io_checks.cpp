#include <cassert>
#include <cstdio>
#include "vdc_fixture.h"
#include "../arduino/teensy41/albatross_controller_teensy41/vdc_io.h"
static uint32_t sent_id;static uint8_t sent[8],sent_len;static int count;
void capture(uint32_t id,const uint8_t* d,uint8_t n){sent_id=id;sent_len=n;memcpy(sent,d,n);count++;}
void captureStandard(uint16_t id,const uint8_t* d,uint8_t n){capture(id,d,n);}
uint32_t reply(){uint16_t token=(uint16_t(sent[1])<<3)|(sent[2]>>5);return (uint32_t(token)<<18)|(2<<15)|(10<<11)|(9<<7)|(6<<3);}
int main(){
 vdc::IO io;io.c=testCalibration();io.controller=vdc::Controller(io.c);
 io.poll(10,capture);assert(count==0); // unverified installation emits no polling
 io.hw.dbwx2_v092_verified=true;io.hw.mount_verified=true;io.hw.dbwx2_custom_receive_verified=true;io.hw.watchdog_verified=true;
 io.hw.throttle_body_verified=io.hw.independent_kill_verified=true;
 io.poll(10,capture);assert(sent_id==((1<<15)|(9<<11)|(10<<7)|(5<<3))&&sent_len==3&&sent[2]==8);
 uint8_t pairs[]={0xDC,0x05,0xAC,0x0D,0xF4,0x01,0x94,0x11}; // LE 1500,3500,500,4500
 io.receiveExtended(reply()+8,8,pairs,11);assert(!io.inputs.aps_valid);
 io.receiveExtended(reply(),7,pairs,11);assert(!io.inputs.aps_valid);
 io.receiveExtended(reply(),8,pairs,11);assert(io.inputs.aps_valid&&io.inputs.aps[0]==1500&&io.inputs.aps[1]==3500&&io.inputs.tps[1]==4500);
 io.poll(15,capture);assert(sent_id>>18==64);
 uint8_t current[]={123,0,0,0};io.receiveExtended(reply(),4,current,16);assert(fabs(io.inputs.motor_current-1.23)<.001);
 io.poll(20,capture);uint8_t status[]={0,0,0,0,1,0,0,0};io.receiveExtended(reply(),8,status,21);
 io.poll(25,capture);uint8_t channel[]={1,0,1,0};io.receiveExtended(reply(),4,channel,26);
 uint8_t accel[]={0,100,0,200,3,232};io.receive(0x470,6,accel,27);
 assert(fabs(io.inputs.accel[0]-1.96133)<.001&&fabs(io.inputs.accel[1]-.980665)<.001&&fabs(io.inputs.accel[2]-9.80665)<.001);
 uint8_t gyro[]={0,1,0,2,0xFF,0xFF};io.receive(0x471,6,gyro,27);
 assert(fabs(io.inputs.gyro[0]+.36)<.001&&fabs(io.inputs.gyro[1]-.72)<.001&&fabs(io.inputs.gyro[2]-.36)<.001);
 io.update(28);assert(io.inputs.dbw_valid&&io.inputs.imu_valid&&!io.inputs.driver_fault);
 io.hw.independent_kill_verified=false;io.update(29);assert(!io.inputs.dbw_valid&&!io.controller.out.dbw_enable);io.hw.independent_kill_verified=true;
 io.update(300);assert(!io.inputs.dbw_valid&&!io.inputs.imu_valid&&!io.inputs.aps_valid);
 uint8_t settings[]={1,0,1,2,1,0,50,0};io.receive(0x208,8,settings,301);assert(io.controller.settings.tcs==vdc::Level::MED);
 settings[7]=0xA5;io.receive(0x208,8,settings,302);assert(io.controller.settings.tcs==vdc::Level::OFF&&io.request_ack==50);
 // A boot without feedback must recover after fresh valid data, not latch absence.
 auto c=testCalibration();vdc::Controller core(c);vdc::Inputs in;in.now=1;core.update(in);
 in.front_valid=in.rear_valid=in.imu_valid=in.aps_valid=in.tps_valid=in.dbw_valid=in.engine_valid=true;
 in.aps[0]=in.tps[0]=500;in.aps[1]=in.tps[1]=4500;in.accel[2]=c.gravity;in.rpm=3000;
 for(int n=1;n<50;n++){in.now=1+n*10;core.update(in);}
 assert(core.out.faults==0&&core.out.dbw_enable);
 vdc::Controller held(c);in.aps[0]=3700;in.aps[1]=1300;
 for(int n=1;n<50;n++){in.now=1+n*10;held.update(in);assert(!held.out.dbw_enable);}
 in.aps[0]=500;in.aps[1]=4500;
 for(int n=50;n<80;n++){in.now=1+n*10;held.update(in);}
 assert(held.out.faults==0&&held.out.dbw_enable);
 held.stop();in.aps[0]=3700;in.aps[1]=1300;
 for(int n=80;n<180;n++){in.now=1+n*10;held.settings.tcs=held.settings.awc=vdc::Level::OFF;held.update(in);
   assert(held.out.faults&vdc::MASTER_STOP);assert(!held.out.dbw_enable&&!held.out.air_allowed&&held.out.permitted==0&&held.out.boost_target==0);
 }
 uint8_t stop[]={1,'S','T','O','P',0xA5};
 io.receive(0x20A,5,stop,400);assert(!io.controller.stopped());
 stop[5]=0;io.receive(0x20A,6,stop,401);assert(!io.controller.stopped());
 stop[5]=0xA5;io.receive(0x20A,6,stop,402);assert(io.controller.stopped());
 io.receive(0x208,8,settings,403);io.update(404);assert(io.controller.stopped());
 io.command(captureStandard);assert(sent_id==0x210&&sent_len==8&&sent[0]==0&&sent[1]==0&&sent[3]==0);
 in.tps[0]=2500;in.tps[1]=2500;held.update(in);assert(held.out.throttle_actual==40&&!held.out.dbw_enable); // stuck-open feedback stays visible
 vdc::Controller unset(vdc::Config{});unset.stop();unset.update(in);assert((unset.out.faults&(vdc::MASTER_STOP|vdc::CALIBRATION))==(vdc::MASTER_STOP|vdc::CALIBRATION));
 puts("PASS native DBWX2, RaceGrade, freshness, commands, cold-start recovery");
}
