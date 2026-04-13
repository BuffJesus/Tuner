// SPDX-License-Identifier: MIT

#include "tuner_core/virtual_dyno.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>

namespace tuner_core::virtual_dyno {

namespace {

// Physical constants.
constexpr double R_AIR = 287.058;         // J/(kg·K) — specific gas constant for air
constexpr double LHV_GASOLINE = 43.0e6;   // J/kg — lower heating value of gasoline
constexpr double PI = 3.14159265358979;

}  // anon

DynoResult calculate(
    const std::vector<DataPoint>& data,
    const EngineSpec& spec) {

    DynoResult result;
    if (data.size() < 3) {
        result.summary_text = "Insufficient data — need at least 3 WOT data points.";
        return result;
    }

    double disp_m3 = spec.displacement_cc / 1.0e6;  // cc → m³
    double rev_per_cycle = spec.four_stroke ? 2.0 : 1.0;

    // Group by RPM bucket (round to nearest 100 RPM) and average.
    std::map<int, std::vector<const DataPoint*>> buckets;
    for (const auto& dp : data) {
        int bucket = static_cast<int>(std::round(dp.rpm / 100.0)) * 100;
        if (bucket > 0) buckets[bucket].push_back(&dp);
    }

    for (const auto& [rpm_bucket, points] : buckets) {
        double avg_map = 0, avg_iat = 0, avg_afr = 0, avg_ve = 0;
        for (const auto* p : points) {
            avg_map += p->map_kpa;
            avg_iat += p->iat_celsius;
            avg_afr += p->afr;
            avg_ve += p->ve_percent;
        }
        double n = static_cast<double>(points.size());
        avg_map /= n;
        avg_iat /= n;
        avg_afr /= n;
        avg_ve /= n;

        double rpm = static_cast<double>(rpm_bucket);
        double iat_k = avg_iat + 273.15;
        double map_pa = avg_map * 1000.0;  // kPa → Pa
        double ve = avg_ve / 100.0;        // percent → fraction

        // Mass air flow (kg/s):
        // MAF = VE × displacement × (RPM / rev_per_cycle / 60) × (MAP / (R × T))
        double volume_flow = ve * disp_m3 * (rpm / (rev_per_cycle * 60.0));
        double air_density = map_pa / (R_AIR * iat_k);
        double maf = volume_flow * air_density;  // kg/s

        // Fuel mass flow (kg/s):
        double fuel_flow = maf / avg_afr;

        // Indicated power (W):
        // P_indicated = fuel_flow × LHV × thermal_efficiency
        double p_indicated = fuel_flow * LHV_GASOLINE * spec.thermal_efficiency;

        // Brake power (W):
        double p_brake = p_indicated * spec.mechanical_efficiency;

        // Torque (Nm):
        // P = T × omega  →  T = P / (2π × RPM/60)
        double omega = 2.0 * PI * rpm / 60.0;
        double torque = (omega > 0) ? p_brake / omega : 0.0;

        // Horsepower:
        double hp = p_brake / 745.7;  // W → HP

        DynoPoint dp;
        dp.rpm = rpm;
        dp.torque_nm = std::round(torque * 10.0) / 10.0;  // 0.1 Nm precision
        dp.horsepower = std::round(hp * 10.0) / 10.0;     // 0.1 HP precision
        result.points.push_back(dp);

        if (torque > result.peak_torque_nm) {
            result.peak_torque_nm = torque;
            result.peak_torque_rpm = rpm;
        }
        if (hp > result.peak_hp) {
            result.peak_hp = hp;
            result.peak_hp_rpm = rpm;
        }
    }

    // Round peaks for display.
    result.peak_torque_nm = std::round(result.peak_torque_nm * 10.0) / 10.0;
    result.peak_hp = std::round(result.peak_hp * 10.0) / 10.0;

    char buf[256];
    std::snprintf(buf, sizeof(buf),
        "Virtual Dyno: %.1f HP @ %.0f RPM / %.1f Nm @ %.0f RPM "
        "(%d data points, %d RPM buckets)",
        result.peak_hp, result.peak_hp_rpm,
        result.peak_torque_nm, result.peak_torque_rpm,
        static_cast<int>(data.size()),
        static_cast<int>(result.points.size()));
    result.summary_text = buf;

    return result;
}

}  // namespace tuner_core::virtual_dyno
