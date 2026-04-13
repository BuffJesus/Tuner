// SPDX-License-Identifier: MIT
//
// tuner_core::mock_ecu_runtime — simulated ECU runtime for UI demos.
// Sub-slice 69 of Phase 14 Slice 4.
//
// Produces realistic-looking Speeduino channel values that vary over
// time: RPM with idle/cruise/WOT phases, MAP correlated with throttle,
// AFR tracking target with noise, CLT warming up, etc.

#pragma once

#include <cmath>
#include <map>
#include <string>

namespace tuner_core::mock_ecu_runtime {

struct Snapshot {
    std::map<std::string, double> channels;
    double get(const std::string& name, double fallback = 0) const {
        auto it = channels.find(name);
        return it != channels.end() ? it->second : fallback;
    }
};

class MockEcu {
public:
    explicit MockEcu(int seed = 12345) : seed_(seed) {}

    /// Advance one tick (~50ms equivalent) and produce a snapshot.
    Snapshot poll();

    int tick() const { return tick_; }

private:
    int seed_;
    int tick_ = 0;

    // Simple LCG PRNG for deterministic jitter.
    double jitter(double range) {
        seed_ = (seed_ * 1103515245 + 12345) & 0x7fffffff;
        return (static_cast<double>(seed_) / 0x7fffffff - 0.5) * 2.0 * range;
    }
};

inline Snapshot MockEcu::poll() {
    ++tick_;
    double t = tick_ * 0.05;  // seconds

    // Driving cycle: idle → cruise → WOT → cruise → idle (30s loop)
    double cycle = std::fmod(t, 30.0);
    double throttle;
    if (cycle < 5.0)       throttle = 0.0;          // idle
    else if (cycle < 8.0)  throttle = (cycle - 5.0) / 3.0 * 40.0;  // ramp up
    else if (cycle < 15.0) throttle = 40.0;          // cruise
    else if (cycle < 17.0) throttle = 40.0 + (cycle - 15.0) / 2.0 * 60.0; // WOT ramp
    else if (cycle < 20.0) throttle = 100.0;         // WOT
    else if (cycle < 23.0) throttle = 100.0 - (cycle - 20.0) / 3.0 * 60.0; // decel
    else if (cycle < 27.0) throttle = 40.0;          // cruise
    else                   throttle = 40.0 - (cycle - 27.0) / 3.0 * 40.0; // back to idle

    double rpm = 800 + throttle * 60.0 + jitter(30);
    double map_kpa = 30 + throttle * 0.7 + jitter(2);
    double tps = throttle + jitter(0.5);
    double afr = (throttle > 80) ? 11.5 + jitter(0.3)  // WOT rich
               : (throttle > 5)  ? 14.5 + jitter(0.2)  // cruise
               :                   14.7 + jitter(0.1);  // idle
    double advance = (throttle > 80) ? 18 + jitter(1) : 28 + jitter(1);
    double clt = std::min(92.0, 20.0 + t * 0.8) + jitter(0.3);
    double iat = 32 + jitter(0.5);
    double batt = 13.8 + jitter(0.1);
    double pw1 = 2.0 + throttle * 0.06 + jitter(0.1);
    double dwell = 3.5 + jitter(0.1);
    double ve = 70 + throttle * 0.2 + jitter(1);

    Snapshot s;
    s.channels = {
        {"rpm", std::round(rpm)},
        {"map", std::round(map_kpa * 10) / 10},
        {"tps", std::round(tps * 10) / 10},
        {"afr", std::round(afr * 100) / 100},
        {"advance", std::round(advance * 10) / 10},
        {"clt", std::round(clt * 10) / 10},
        {"iat", std::round(iat * 10) / 10},
        {"batt", std::round(batt * 100) / 100},
        {"pw1", std::round(pw1 * 100) / 100},
        {"dwell", std::round(dwell * 100) / 100},
        {"ve", std::round(ve * 10) / 10},
        {"syncLossCounter", 0},
    };
    return s;
}

}  // namespace tuner_core::mock_ecu_runtime
