#pragma once
#include <stdint.h>
#include <string>
#include <deque>
#include <vector>
#include <cstring>
constexpr int LOW=0,HIGH=1,OUTPUT=1,INPUT_PULLUP=2,CAN1=1,RX_SIZE_256=256,TX_SIZE_16=16;
inline uint32_t test_now=0;inline int pins[42];inline int outputs[42];
inline uint32_t millis(){return test_now;}
inline void digitalWrite(int p,int value){outputs[p]=value;}
inline int digitalRead(int p){return pins[p];}
inline void pinMode(int,int){}
struct SerialStub {
 bool connected=true;std::string input,output;
 void begin(int){} operator bool()const{return connected;}
 int available(){return input.size();}
 char read(){char c=input.front();input.erase(0,1);return c;}
 int availableForWrite(){return 2048;}
 void print(const char* s){output+=s;}
};
inline SerialStub Serial;
struct CAN_message_t {uint32_t id=0;struct{bool extended=false,remote=false;}flags;uint8_t len=0,buf[8]={};};
template<int,int,int>struct FlexCAN_T4 {
 std::deque<CAN_message_t> incoming;std::vector<CAN_message_t> outgoing;bool fail=false;
 void begin(){}void setBaudRate(int){}
 bool write(const CAN_message_t& m){if(fail)return false;outgoing.push_back(m);return true;}
 bool read(CAN_message_t& m){if(incoming.empty())return false;m=incoming.front();incoming.pop_front();return true;}
};
