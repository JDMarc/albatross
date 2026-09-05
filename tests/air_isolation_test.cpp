// GPIO command test only: physical NC closure still requires hardware testing.
#include <assert.h>
#include <stdio.h>
constexpr int OUTPUT=1,LOW=0,HIGH=1;
static int last_level=-1;
void pinMode(int pin,int mode){assert(pin==12&&mode==OUTPUT);}
void digitalWrite(int pin,int level){assert(pin==12);last_level=level;}
#include "../arduino/teensy41/albatross_controller_teensy41/fault_manager/air_isolation.h"
int main(){
 fm::AirIsolation valve;
 valve.begin(false);assert(last_level==LOW&&!valve.commanded_open);
 valve.update(true);assert(last_level==LOW&&!valve.commanded_open);
 valve.begin(true);assert(last_level==LOW);
 valve.update(true);assert(last_level==HIGH&&valve.commanded_open);
 valve.update(false);assert(last_level==LOW&&!valve.commanded_open);
 valve.update(true);valve.begin(true);assert(last_level==LOW&&!valve.commanded_open);
 puts("PASS master isolation boot, uncommissioned inhibit, command closure and reinitialization");
}
