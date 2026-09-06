#pragma once
#include "bench_core.h"
// Complete this dedicated FIXTURE profile after measurement/review. Never copy
// the synthetic test constants into this file. No road configuration is edited.
inline bench::Config fixtureConfig(){return bench::Config{};}
constexpr int BENCH_KEY_PIN=-1;     // maintained contact to ground, INPUT_PULLUP
constexpr int DEADMAN_PIN=-1;       // momentary contact to ground, INPUT_PULLUP
constexpr int PERMIT_PIN=-1;        // active HIGH, external pull-down REQUIRED
constexpr bool INTERLOCK_VERIFIED=false;
constexpr bool DBWX2_092_VERIFIED=false;
constexpr bool CUSTOM_RECEIVE_VERIFIED=false;
constexpr bool COMMAND_LOSS_VERIFIED=false;
constexpr float WATCHDOG_SECONDS=0; // WDT1: reviewed 0.5..128 seconds, 0.5s steps
constexpr uint32_t POLL_MS=5;        // protocol scheduling, not actuator calibration
constexpr uint32_t COMMAND_MS=10;
constexpr uint16_t DBWX2_COMMAND_ID=0x210;
constexpr uint8_t LOCAL_NODE=9,DBWX2_NODE=10;
constexpr uint32_t PROFILE_REVISION=0; // assign a nonzero fixture revision
// CAN1 is fixed to Teensy 4.1 TX 22 / RX 23 through a 3.3V CAN transceiver.
// No Air Shot GPIOs are configured or driven by this sketch.
