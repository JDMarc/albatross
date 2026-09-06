#include <cassert>
#include <cstdio>
#include <algorithm>
#define ALBATROSS_BENCH_NATIVE_TEST
#include "../arduino/bench/dbw_bench/dbw_bench.ino"
void healthy(){
 for(int n=0;n<4;n++){core.f.seen[n]=true;core.f.at[n]=test_now;}
 core.f.tps[0]=100;core.f.tps[1]=3900;core.f.current=.1;core.f.status_bad=core.f.channel_bad=false;
}
void reset(){
 core=bench::Core(fixtureConfig());pending=false;token=group=0;poll_at=command_at=status_at=0;used=0;overflow=false;
 Serial=SerialStub{};bus.outgoing.clear();bus.incoming.clear();bus.fail=false;std::fill_n(pins,42,HIGH);test_now=1;setup();healthy();
 assert(configured&&outputs[PERMIT_PIN]==LOW);
}
void step(uint32_t now,const char* command=""){test_now=now;Serial.input+=command;loop();}
uint16_t lastCommand(){for(auto it=bus.outgoing.rbegin();it!=bus.outgoing.rend();++it)if(it->id==DBWX2_COMMAND_ID&&!it->flags.extended)return uint16_t(it->buf[0])<<8|it->buf[1];assert(false);return 0;}
int main(){
 reset();pins[BENCH_KEY_PIN]=LOW;step(10,"ARM 1\n");assert(core.state==bench::ARMED&&lastCommand()==0&&outputs[PERMIT_PIN]==LOW);
 pins[DEADMAN_PIN]=LOW;step(20,"HOLD 1 1 200\n");step(30);assert(core.state==bench::ACTIVE&&lastCommand()>0&&lastCommand()<=300&&outputs[PERMIT_PIN]==HIGH);
 step(40,"STOP\n");assert(core.state==bench::IDLE&&lastCommand()==0&&outputs[PERMIT_PIN]==LOW);
 step(50,"HOLD 1 2 200\n");assert(core.state==bench::IDLE&&lastCommand()==0);
 assert(Serial.output.find("\"protocol\":1")!=std::string::npos);
 reset();pins[BENCH_KEY_PIN]=LOW;step(10,"ARM 1\n");pins[DEADMAN_PIN]=LOW;step(20,"HOLD 1 1 200\n");
 CAN_message_t foreign;foreign.id=DBWX2_COMMAND_ID;foreign.len=8;bus.incoming.push_back(foreign);step(30);
 assert(core.state==bench::FAULT&&core.reason==bench::FOREIGN_WRITER&&lastCommand()==0&&outputs[PERMIT_PIN]==LOW);
 reset();step(10);assert(pending);auto request=bus.outgoing.front();assert(request.flags.extended);
 CAN_message_t reply;reply.id=reply_id;reply.flags.extended=true;reply.len=8;
 uint8_t raw[]={0,0,0,0,0x64,0,0x3c,0x0f};memcpy(reply.buf,raw,8);bus.incoming.push_back(reply);step(11);
 assert(!pending&&group==1&&core.f.tps[0]==100&&core.f.tps[1]==3900);
 reset();pins[BENCH_KEY_PIN]=LOW;step(10,"ARM 1\n");pins[DEADMAN_PIN]=LOW;step(20,"HOLD 1 1 200\n");bus.fail=true;step(30);
 assert(core.state==bench::FAULT&&outputs[PERMIT_PIN]==LOW);
 reset();step(10,"BOGUS\n");assert(core.state==bench::FAULT);
 reset();Serial.input=std::string(100,'x')+"\n";step(10);assert(core.state==bench::FAULT);
 puts("PASS bench sketch fake IO: parser, real-format CAN demand, zero/permit removal, stale epoch, foreign writer, native reply, TX failure, overflow");
}
