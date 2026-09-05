#pragma once
#include <Arduino.h>
namespace fm {
// Reclaimed legacy single-shot pin. External active-high protected driver,
// pulldown, fuse and NC pneumatic valve required; never drive a coil from GPIO.
class AirIsolation {
 public:
 bool configured=false,commanded_open=false;
 void begin(bool verified){configured=verified;commanded_open=false;pinMode(12,OUTPUT);digitalWrite(12,LOW);}
 void update(bool request_open){commanded_open=configured&&request_open;digitalWrite(12,commanded_open?HIGH:LOW);}
};
}
