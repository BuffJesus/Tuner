// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/hardware_presets.hpp"

namespace hp = tuner_core::hardware_presets;

TEST_CASE("hw_presets: 8 ignition presets") {
    CHECK(hp::ignition_presets().size() == 8);
}

TEST_CASE("hw_presets: GM LS lookup") {
    auto* p = hp::ignition_preset_by_key("gm_ls_10457730");
    REQUIRE(p != nullptr);
    CHECK(p->running_dwell_ms == 5.0);
    CHECK(p->cranking_dwell_ms == 5.0);
}

TEST_CASE("hw_presets: unknown key returns null") {
    CHECK(hp::ignition_preset_by_key("nonexistent") == nullptr);
}

TEST_CASE("hw_presets: confidence label - official") {
    CHECK(hp::source_confidence_label("Holley test", "https://documents.holley.com/x.pdf") == "Official");
}

TEST_CASE("hw_presets: confidence label - trusted secondary") {
    CHECK(hp::source_confidence_label("MSExtra", "https://www.msextra.com/doc/x.html") == "Trusted Secondary");
}

TEST_CASE("hw_presets: confidence label - inferred") {
    CHECK(hp::source_confidence_label("Conservative inferred starter preset.", "") == "Starter");
}

TEST_CASE("hw_presets: all presets have positive dwell") {
    for (const auto& p : hp::ignition_presets()) {
        CHECK(p.running_dwell_ms > 0);
        CHECK(p.cranking_dwell_ms > 0);
    }
}
