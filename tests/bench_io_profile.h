#pragma once
#include "../arduino/bench/dbw_bench/bench_core.h"
// Native fake-hardware tests ONLY. Not a commissioned hardware profile.
inline bench::Config fixtureConfig(){
 bench::Config c;c.verified=true;c.lease_ms=100;c.feedback_ms=150;c.arm_ms=500;c.run_ms=400;c.tracking_ms=100;
 c.max_pct=30;c.hard_actual_pct=35;c.rise_pct_s=100;c.current_a=2;c.pair_error_pct=5;c.tracking_pct=10;c.start_pct=3;
 c.rail_low=50;c.rail_high=4050;c.tps_closed[0]=100;c.tps_open[0]=3900;c.tps_closed[1]=3900;c.tps_open[1]=100;return c;
}
constexpr int BENCH_KEY_PIN=1,DEADMAN_PIN=2,PERMIT_PIN=3;
constexpr bool INTERLOCK_VERIFIED=true,DBWX2_092_VERIFIED=true,CUSTOM_RECEIVE_VERIFIED=true,COMMAND_LOSS_VERIFIED=true;
constexpr float WATCHDOG_SECONDS=1;
constexpr uint32_t POLL_MS=5,COMMAND_MS=10,PROFILE_REVISION=7;
constexpr uint16_t DBWX2_COMMAND_ID=0x210;
constexpr uint8_t LOCAL_NODE=9,DBWX2_NODE=10;
