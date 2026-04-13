// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::thermistor_calibration — thirty-ninth sub-slice.

#include <doctest.h>

#include "tuner_core/thermistor_calibration.hpp"

#include <cmath>
#include <string>
#include <vector>

namespace tc = tuner_core::thermistor_calibration;

// -----------------------------------------------------------------------
// 1. Preset catalog has 15 entries
// -----------------------------------------------------------------------
TEST_CASE("therm: preset catalog has 15 entries") {
    CHECK(tc::presets().size() == 15);
}

// -----------------------------------------------------------------------
// 2. Preset lookup by name
// -----------------------------------------------------------------------
TEST_CASE("therm: preset_by_name finds GM") {
    auto* p = tc::preset_by_name("GM");
    REQUIRE(p != nullptr);
    CHECK(p->name == "GM");
    CHECK(p->pullup_ohms == doctest::Approx(2490.0));
}

TEST_CASE("therm: preset_by_name returns null for unknown") {
    CHECK(tc::preset_by_name("nonexistent") == nullptr);
}

// -----------------------------------------------------------------------
// 3. Presets filtered by sensor
// -----------------------------------------------------------------------
TEST_CASE("therm: presets_for_sensor filters correctly") {
    auto clt = tc::presets_for_sensor(tc::Sensor::CLT);
    auto iat = tc::presets_for_sensor(tc::Sensor::IAT);

    // GM is both CLT and IAT.
    bool gm_in_clt = false, gm_in_iat = false;
    for (const auto& p : clt) if (p.name == "GM") gm_in_clt = true;
    for (const auto& p : iat) if (p.name == "GM") gm_in_iat = true;
    CHECK(gm_in_clt);
    CHECK(gm_in_iat);

    // Mazda RX-7 CLT is CLT-only.
    bool rx7_clt_in_clt = false, rx7_clt_in_iat = false;
    for (const auto& p : clt) if (p.name == "Mazda RX-7 CLT (S4/S5)") rx7_clt_in_clt = true;
    for (const auto& p : iat) if (p.name == "Mazda RX-7 CLT (S4/S5)") rx7_clt_in_iat = true;
    CHECK(rx7_clt_in_clt);
    CHECK(!rx7_clt_in_iat);
}

// -----------------------------------------------------------------------
// 4. Source confidence labels
// -----------------------------------------------------------------------
TEST_CASE("therm: source_confidence_label") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    CHECK(tc::source_confidence_label(*gm) == "Generic");

    auto* bmw_m50 = tc::preset_by_name("BMW M50 IAT");
    REQUIRE(bmw_m50 != nullptr);
    CHECK(tc::source_confidence_label(*bmw_m50) == "Trusted Secondary");
}

// -----------------------------------------------------------------------
// 5. GM preset generates 32-point table
// -----------------------------------------------------------------------
TEST_CASE("therm: GM generates 32 temperatures") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto result = tc::generate(*gm, tc::Sensor::CLT);

    CHECK(result.temperatures_c.size() == 32);
    CHECK(result.sensor == tc::Sensor::CLT);
    CHECK(result.preset_name == "GM");
}

// -----------------------------------------------------------------------
// 6. Table is monotonically decreasing (hot→cold as ADC increases)
// -----------------------------------------------------------------------
TEST_CASE("therm: GM table is monotonically decreasing") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto result = tc::generate(*gm, tc::Sensor::CLT);

    for (std::size_t i = 1; i < result.temperatures_c.size(); ++i) {
        CHECK(result.temperatures_c[i] <= result.temperatures_c[i - 1]);
    }
}

// -----------------------------------------------------------------------
// 7. Edge cases: ADC 0 = max, ADC 1023 = min
// -----------------------------------------------------------------------
TEST_CASE("therm: edge cases ADC 0 and 1023") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto sh = tc::steinhart_hart_coefficients(gm->point1, gm->point2, gm->point3);

    CHECK(tc::temp_at_adc(0, gm->pullup_ohms, sh) == tc::TEMP_MAX_C);
    CHECK(tc::temp_at_adc(1023, gm->pullup_ohms, sh) == tc::TEMP_MIN_C);
}

// -----------------------------------------------------------------------
// 8. Known reference point validation (GM at 30°C = 2238 ohms)
// -----------------------------------------------------------------------
TEST_CASE("therm: GM Steinhart-Hart interpolates near reference points") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto sh = tc::steinhart_hart_coefficients(gm->point1, gm->point2, gm->point3);

    // At the reference resistance of 2238 ohms, the S-H equation should
    // return approximately 30°C.
    // ADC for 2238 ohms with 2490 pull-up at 5V supply:
    //   V = 5 * 2238 / (2490 + 2238) ≈ 2.366V
    //   ADC = 2.366 * 1023 / 5 ≈ 484
    double t = tc::temp_at_adc(484, gm->pullup_ohms, sh);
    CHECK(t == doctest::Approx(30.0).epsilon(2.0));
}

// -----------------------------------------------------------------------
// 9. Encode payload is 64 bytes
// -----------------------------------------------------------------------
TEST_CASE("therm: encode_payload produces 64 bytes") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto result = tc::generate(*gm, tc::Sensor::CLT);
    auto payload = result.encode_payload();

    CHECK(payload.size() == 64);
}

// -----------------------------------------------------------------------
// 10. Encode payload big-endian int16 for known value
// -----------------------------------------------------------------------
TEST_CASE("therm: encode_payload big-endian for 100C") {
    tc::CalibrationResult result;
    result.sensor = tc::Sensor::CLT;
    result.preset_name = "test";
    result.temperatures_c = {100.0};  // 100°C = 212°F → 2120 as int16

    auto payload = result.encode_payload();
    REQUIRE(payload.size() == 2);
    int16_t val = static_cast<int16_t>((payload[0] << 8) | payload[1]);
    CHECK(val == 2120);
}

// -----------------------------------------------------------------------
// 11. Preview points returns 10 entries for a full table
// -----------------------------------------------------------------------
TEST_CASE("therm: preview_points returns 10 entries") {
    auto* gm = tc::preset_by_name("GM");
    REQUIRE(gm != nullptr);
    auto result = tc::generate(*gm, tc::Sensor::CLT);
    auto preview = result.preview_points();

    CHECK(preview.size() == 10);
    // First entry should be ADC 0.
    CHECK(preview[0].first == 0);
    // Last entry should be ADC 31*33 = 1023.
    CHECK(preview.back().first == 1023);
}

// -----------------------------------------------------------------------
// 12. All presets generate valid tables
// -----------------------------------------------------------------------
TEST_CASE("therm: all presets generate valid 32-point tables") {
    for (const auto& preset : tc::presets()) {
        auto result = tc::generate(preset, tc::Sensor::CLT);
        CHECK(result.temperatures_c.size() == 32);
        // All values should be within bounds.
        for (double t : result.temperatures_c) {
            CHECK(t >= tc::TEMP_MIN_C);
            CHECK(t <= tc::TEMP_MAX_C);
        }
    }
}

// -----------------------------------------------------------------------
// 13. Negative temperature encoding
// -----------------------------------------------------------------------
TEST_CASE("therm: encode_payload handles negative temperatures") {
    tc::CalibrationResult result;
    result.sensor = tc::Sensor::CLT;
    result.preset_name = "test";
    result.temperatures_c = {-40.0};  // -40°C = -40°F → -400 as int16

    auto payload = result.encode_payload();
    REQUIRE(payload.size() == 2);
    int16_t val = static_cast<int16_t>((payload[0] << 8) | payload[1]);
    CHECK(val == -400);
}
