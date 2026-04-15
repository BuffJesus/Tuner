// SPDX-License-Identifier: MIT
#include "tuner_core/wideband_calibration.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace tuner_core::wideband_calibration {

const std::vector<Preset>& presets() {
    static const std::vector<Preset> p = {
        {"Innovate LC-1 / LC-2 / LM-1 / LM-2 (default)",
         0.0, 7.35, 5.0, 22.39,
         "Innovate factory linear default; programmable on the device."},
        {"AEM 30-0300 / 30-4110 / X-Series",
         0.0, 10.0, 5.0, 20.0,
         "AEM analog output #1 — 10 AFR @ 0 V, 20 AFR @ 5 V."},
        {"14Point7 Spartan 2",
         0.0, 9.996, 5.0, 19.992,
         "Spartan 2 default linear output (10–20 AFR across 0–5 V)."},
        {"Tech Edge 2J9 / WBo2",
         0.0, 9.0, 5.0, 19.0,
         "Tech Edge default 0–5 V linear (9–19 AFR)."},
        {"PLX SM-AFR / DM-6",
         0.0, 10.0, 5.0, 20.0,
         "PLX 0–5 V linear default (10–20 AFR)."},
    };
    return p;
}

const Preset* preset_by_name(const std::string& name) {
    for (const auto& p : presets()) {
        if (p.name == name) return &p;
    }
    return nullptr;
}

CalibrationResult generate(const Preset& preset) {
    if (preset.voltage_high == preset.voltage_low) {
        throw std::invalid_argument("Preset has zero voltage span.");
    }
    double slope = (preset.afr_at_voltage_high - preset.afr_at_voltage_low) /
                   (preset.voltage_high - preset.voltage_low);
    CalibrationResult result;
    result.preset_name = preset.name;
    result.afrs.reserve(ADC_COUNT);
    for (int i = 0; i < ADC_COUNT; ++i) {
        int adc = i * 33;
        double voltage = adc * SUPPLY_V / ADC_MAX;
        double afr;
        if (voltage <= preset.voltage_low)
            afr = preset.afr_at_voltage_low;
        else if (voltage >= preset.voltage_high)
            afr = preset.afr_at_voltage_high;
        else
            afr = preset.afr_at_voltage_low + slope * (voltage - preset.voltage_low);
        afr = std::max(AFR_MIN, std::min(AFR_MAX, afr));
        result.afrs.push_back(std::round(afr * 100.0) / 100.0);
    }
    return result;
}

std::vector<uint8_t> CalibrationResult::encode_payload() const {
    std::vector<uint8_t> result;
    result.reserve(64);
    for (double afr : afrs) {
        int val = std::max(-32768, std::min(32767, static_cast<int>(std::round(afr * 10.0))));
        auto u = static_cast<uint16_t>(val);
        result.push_back(static_cast<uint8_t>(u >> 8));
        result.push_back(static_cast<uint8_t>(u & 0xFF));
    }
    return result;
}

std::vector<uint8_t> CalibrationResult::encode_speeduino_o2_table() const {
    // Speeduino firmware reads 1024 bytes and stores every 32nd as an
    // 8-bit AFR*10 value in o2Calibration_values[i]. Any byte outside
    // position i*32 is ignored by firmware; zero-fill keeps the wire
    // shape stable.
    std::vector<uint8_t> out(1024, 0);
    const std::size_t slot_count =
        afrs.size() < 32 ? afrs.size() : static_cast<std::size_t>(32);
    for (std::size_t i = 0; i < slot_count; ++i) {
        int val = static_cast<int>(std::round(afrs[i] * 10.0));
        if (val < 0) val = 0;
        if (val > 255) val = 255;
        out[i * 32] = static_cast<uint8_t>(val);
    }
    return out;
}

double CalibrationResult::afr_at_voltage(double voltage) const {
    int adc = std::max(0, std::min(ADC_MAX, static_cast<int>(std::round(voltage * ADC_MAX / SUPPLY_V))));
    int index = std::min(ADC_COUNT - 1, adc / 33);
    return afrs[index];
}

}  // namespace tuner_core::wideband_calibration
