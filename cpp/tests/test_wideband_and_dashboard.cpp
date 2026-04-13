// SPDX-License-Identifier: MIT
// Combined tests for sub-slices 50 (wideband_calibration) and 51 (dashboard_layout).

#include <doctest.h>
#include "tuner_core/wideband_calibration.hpp"
#include "tuner_core/dashboard_layout.hpp"
#include <cmath>

namespace wc = tuner_core::wideband_calibration;
namespace dl = tuner_core::dashboard_layout;

// =====================================================================
// Wideband calibration (sub-slice 50)
// =====================================================================

TEST_CASE("wb: 5 presets") { CHECK(wc::presets().size() == 5); }

TEST_CASE("wb: AEM lookup") {
    auto* p = wc::preset_by_name("AEM 30-0300 / 30-4110 / X-Series");
    REQUIRE(p != nullptr);
    CHECK(p->afr_at_voltage_low == doctest::Approx(10.0));
}

TEST_CASE("wb: unknown null") { CHECK(wc::preset_by_name("x") == nullptr); }

TEST_CASE("wb: 32 values") {
    auto r = wc::generate(wc::presets()[0]);
    CHECK(r.afrs.size() == 32);
}

TEST_CASE("wb: monotonic AEM") {
    auto* p = wc::preset_by_name("AEM 30-0300 / 30-4110 / X-Series");
    auto r = wc::generate(*p);
    for (std::size_t i = 1; i < r.afrs.size(); ++i)
        CHECK(r.afrs[i] >= r.afrs[i - 1]);
}

TEST_CASE("wb: all presets in bounds") {
    for (const auto& p : wc::presets()) {
        auto r = wc::generate(p);
        for (double a : r.afrs) {
            CHECK(a >= wc::AFR_MIN);
            CHECK(a <= wc::AFR_MAX);
        }
    }
}

TEST_CASE("wb: payload 64 bytes") {
    auto r = wc::generate(wc::presets()[0]);
    CHECK(r.encode_payload().size() == 64);
}

TEST_CASE("wb: encode 14.7") {
    wc::CalibrationResult r;
    r.afrs = {14.7};
    auto p = r.encode_payload();
    int16_t val = static_cast<int16_t>((p[0] << 8) | p[1]);
    CHECK(val == 147);
}

TEST_CASE("wb: voltage lookup") {
    auto* p = wc::preset_by_name("AEM 30-0300 / 30-4110 / X-Series");
    auto r = wc::generate(*p);
    CHECK(r.afr_at_voltage(2.5) == doctest::Approx(15.0).epsilon(0.5));
}

TEST_CASE("wb: Innovate endpoints") {
    auto* p = wc::preset_by_name("Innovate LC-1 / LC-2 / LM-1 / LM-2 (default)");
    auto r = wc::generate(*p);
    CHECK(r.afrs.front() == doctest::Approx(7.35).epsilon(0.01));
    CHECK(r.afrs.back() == doctest::Approx(22.39).epsilon(0.01));
}

TEST_CASE("wb: zero span throws") {
    wc::Preset bad; bad.name = "bad"; bad.voltage_low = 2.5; bad.voltage_high = 2.5;
    CHECK_THROWS(wc::generate(bad));
}

// =====================================================================
// Dashboard layout (sub-slice 51)
// =====================================================================

TEST_CASE("dash: default layout has 11 widgets") {
    auto layout = dl::default_layout();
    CHECK(layout.widgets.size() == 11);
    CHECK(layout.name == "Default Speeduino");
}

TEST_CASE("dash: RPM widget is first and is a dial") {
    auto layout = dl::default_layout();
    REQUIRE(!layout.widgets.empty());
    CHECK(layout.widgets[0].widget_id == "rpm");
    CHECK(layout.widgets[0].kind == "dial");
    CHECK(layout.widgets[0].max_value == 8000.0);
}

TEST_CASE("dash: RPM has 3 color zones") {
    auto layout = dl::default_layout();
    CHECK(layout.widgets[0].color_zones.size() == 3);
    CHECK(layout.widgets[0].color_zones[0].color == "ok");
    CHECK(layout.widgets[0].color_zones[2].color == "danger");
}

TEST_CASE("dash: AFR has 5 color zones") {
    auto layout = dl::default_layout();
    bool found = false;
    for (const auto& w : layout.widgets) {
        if (w.widget_id == "afr") {
            CHECK(w.color_zones.size() == 5);
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("dash: all widgets have source") {
    auto layout = dl::default_layout();
    for (const auto& w : layout.widgets) {
        CHECK(!w.source.empty());
    }
}

TEST_CASE("dash: battery has zones") {
    auto layout = dl::default_layout();
    for (const auto& w : layout.widgets) {
        if (w.widget_id == "batt") {
            CHECK(w.color_zones.size() == 5);
            CHECK(w.min_value == 8.0);
            CHECK(w.max_value == 16.0);
        }
    }
}
