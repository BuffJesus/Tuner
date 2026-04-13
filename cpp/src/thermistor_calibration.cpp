// SPDX-License-Identifier: MIT
#include "tuner_core/thermistor_calibration.hpp"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

namespace tuner_core::thermistor_calibration {

// -----------------------------------------------------------------------
// Built-in presets — mirrored from the Python PRESETS tuple
// -----------------------------------------------------------------------

static std::vector<Preset> build_presets() {
    std::vector<Preset> v;
    auto add = [&](const char* name, double pullup,
                   Point p1, Point p2, Point p3,
                   bool clt = true, bool iat = true,
                   const char* note = "Generic thermistor preset mirrored from the Speeduino / legacy preset catalog.",
                   const char* url = "") {
        Preset p;
        p.name = name;
        p.pullup_ohms = pullup;
        p.point1 = p1;
        p.point2 = p2;
        p.point3 = p3;
        p.applicable_clt = clt;
        p.applicable_iat = iat;
        p.source_note = note;
        p.source_url = url;
        v.push_back(p);
    };

    add("GM", 2490.0,
        {-40.0, 100700.0}, {30.0, 2238.0}, {99.0, 177.0});
    add("Chrysler 85+", 2490.0,
        {5.5, 24500.0}, {30.5, 8100.0}, {88.3, 850.0});
    add("Ford", 2490.0,
        {0.0, 94000.0}, {50.0, 11000.0}, {98.0, 2370.0});
    add("Saab / Bosch", 2490.0,
        {0.0, 5800.0}, {80.0, 320.0}, {100.0, 180.0});
    add("Mazda", 50000.0,
        {-40.0, 2022000.0}, {21.0, 68273.0}, {99.0, 3715.0});
    add("Mitsubishi", 2490.0,
        {-40.0, 100490.0}, {30.0, 1875.0}, {99.0, 125.0});
    add("Toyota", 2490.0,
        {-40.0, 101890.0}, {30.0, 2268.0}, {99.0, 156.0});
    add("Mazda RX-7 CLT (S4/S5)", 2490.0,
        {-20.0, 16200.0}, {20.0, 2500.0}, {80.0, 300.0},
        true, false);
    add("Mazda RX-7 IAT (S5)", 42200.0,
        {20.0, 41500.0}, {50.0, 11850.0}, {85.0, 3500.0},
        false, true);
    add("VW L-Jet Cylinder Head", 1100.0,
        {-13.888, 11600.0}, {53.888, 703.0}, {95.555, 207.0},
        true, false);
    add("BMW E30 325i", 2490.0,
        {-10.0, 9300.0}, {20.0, 2500.0}, {80.0, 335.0},
        true, false);
    add("BMW M50 IAT", 2490.0,
        {-30.0, 26114.0}, {20.0, 2500.0}, {80.0, 323.0},
        false, true,
        "MS4X publishes the BMW M50 IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        "https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data");
    add("BMW M52 / M52TU / M54 IAT", 2490.0,
        {-39.8, 168058.0}, {30.0, 4025.0}, {99.8, 343.0},
        false, true,
        "MS4X publishes the BMW M52/M52TU/M54 IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        "https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data");
    add("BMW M52 / M52TU / M54 CLT", 828.0,
        {-30.0, 39366.0}, {20.3, 2826.0}, {90.0, 207.0},
        true, false,
        "MS4X publishes the BMW M52/M52TU/M54 CLT resistance curve for the MS42/MS43 828 ohm pull-up context.",
        "https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data");
    add("Bosch 4 Bar TMAP IAT", 2490.0,
        {-40.0, 45395.0}, {20.0, 2500.0}, {80.0, 323.0},
        false, true,
        "MS4X publishes the Bosch 4 Bar TMAP IAT resistance curve for the MS42/MS43 2.49k pull-up context.",
        "https://www.ms4x.net/index.php?title=Aftermarket_Upgrade_Sensor_Data");

    return v;
}

const std::vector<Preset>& presets() {
    static const std::vector<Preset> instance = build_presets();
    return instance;
}

std::vector<Preset> presets_for_sensor(Sensor sensor) {
    std::vector<Preset> result;
    for (const auto& p : presets()) {
        if ((sensor == Sensor::CLT && p.applicable_clt) ||
            (sensor == Sensor::IAT && p.applicable_iat)) {
            result.push_back(p);
        }
    }
    return result;
}

const Preset* preset_by_name(const std::string& name) {
    for (const auto& p : presets()) {
        if (p.name == name) return &p;
    }
    return nullptr;
}

std::string source_confidence_label(const Preset& preset) {
    if (preset.source_url.empty()) return "Generic";
    // Check for ms4x.net domain.
    if (preset.source_url.find("ms4x.net") != std::string::npos) {
        return "Trusted Secondary";
    }
    return "Sourced";
}

// -----------------------------------------------------------------------
// Steinhart-Hart
// -----------------------------------------------------------------------

SHCoefficients steinhart_hart_coefficients(
    const Point& p1, const Point& p2, const Point& p3) {
    double L1 = std::log(p1.resistance_ohms);
    double L2 = std::log(p2.resistance_ohms);
    double L3 = std::log(p3.resistance_ohms);
    double Y1 = 1.0 / (p1.temp_c + KELVIN_OFFSET);
    double Y2 = 1.0 / (p2.temp_c + KELVIN_OFFSET);
    double Y3 = 1.0 / (p3.temp_c + KELVIN_OFFSET);

    double g2 = (Y2 - Y1) / (L2 - L1);
    double g3 = (Y3 - Y1) / (L3 - L1);

    SHCoefficients sh;
    sh.C = (g3 - g2) / (L3 - L2) / (L1 + L2 + L3);
    sh.B = g2 - sh.C * (L1 * L1 + L1 * L2 + L2 * L2);
    sh.A = Y1 - (sh.B + L1 * L1 * sh.C) * L1;
    return sh;
}

double temp_at_adc(int adc, double pullup_ohms, const SHCoefficients& sh) {
    if (adc == 0) return TEMP_MAX_C;
    if (adc >= ADC_MAX) return TEMP_MIN_C;
    double V = adc * SUPPLY_V / ADC_MAX;
    double R = pullup_ohms * V / (SUPPLY_V - V);
    if (R <= 0.0) return TEMP_MAX_C;
    double L = std::log(R);
    double T_inv = sh.A + sh.B * L + sh.C * L * L * L;
    if (T_inv == 0.0) return TEMP_MAX_C;
    double T_kelvin = 1.0 / T_inv;
    return T_kelvin - KELVIN_OFFSET;
}

CalibrationResult generate(const Preset& preset, Sensor sensor) {
    auto sh = steinhart_hart_coefficients(
        preset.point1, preset.point2, preset.point3);
    CalibrationResult result;
    result.sensor = sensor;
    result.preset_name = preset.name;
    result.temperatures_c.reserve(ADC_COUNT);
    for (int i = 0; i < ADC_COUNT; ++i) {
        int adc = i * 33;
        double t = temp_at_adc(adc, preset.pullup_ohms, sh);
        t = std::max(TEMP_MIN_C, std::min(TEMP_MAX_C, t));
        // Round to 1 decimal place.
        t = std::round(t * 10.0) / 10.0;
        result.temperatures_c.push_back(t);
    }
    return result;
}

// -----------------------------------------------------------------------
// CalibrationResult methods
// -----------------------------------------------------------------------

std::vector<uint8_t> CalibrationResult::encode_payload() const {
    std::vector<uint8_t> result;
    result.reserve(64);
    for (double t_c : temperatures_c) {
        double t_f = t_c * 9.0 / 5.0 + 32.0;
        int val = static_cast<int>(std::round(t_f * 10.0));
        val = std::max(-32768, std::min(32767, val));
        auto u = static_cast<uint16_t>(val);
        result.push_back(static_cast<uint8_t>(u >> 8));    // big-endian
        result.push_back(static_cast<uint8_t>(u & 0xFF));
    }
    return result;
}

std::vector<std::pair<int, double>> CalibrationResult::preview_points() const {
    static const int indices[] = {0, 4, 8, 12, 15, 16, 20, 24, 28, 31};
    std::vector<std::pair<int, double>> result;
    for (int idx : indices) {
        if (idx < static_cast<int>(temperatures_c.size())) {
            result.push_back({idx * 33, temperatures_c[idx]});
        }
    }
    return result;
}

}  // namespace tuner_core::thermistor_calibration
