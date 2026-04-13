// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/live_analyze_session.hpp"

namespace las = tuner_core::live_analyze_session;

TEST_SUITE("live_analyze_session") {

TEST_CASE("ve_inactive produces correct status") {
    auto s = las::ve_inactive();
    CHECK_FALSE(s.is_active);
    CHECK(s.accepted_count == 0);
    CHECK(s.status_text == "VE Analyze: inactive.");
}

TEST_CASE("ve_active produces correct counts and text") {
    auto s = las::ve_active(42, 8);
    CHECK(s.is_active);
    CHECK(s.accepted_count == 42);
    CHECK(s.rejected_count == 8);
    CHECK(s.total_count == 50);
    CHECK(s.status_text.find("42 accepted") != std::string::npos);
    CHECK(s.status_text.find("8 rejected") != std::string::npos);
    CHECK(s.status_text.find("50 frame(s)") != std::string::npos);
}

TEST_CASE("wue_inactive produces correct status") {
    auto s = las::wue_inactive();
    CHECK_FALSE(s.is_active);
    CHECK(s.status_text == "WUE Analyze: inactive.");
}

TEST_CASE("wue_active produces correct counts and text") {
    auto s = las::wue_active(15, 3);
    CHECK(s.is_active);
    CHECK(s.total_count == 18);
    CHECK(s.status_text.find("WUE Analyze live") != std::string::npos);
}

TEST_CASE("zero counts") {
    auto s = las::ve_active(0, 0);
    CHECK(s.is_active);
    CHECK(s.total_count == 0);
    CHECK(s.status_text.find("0 frame(s)") != std::string::npos);
}

}  // TEST_SUITE
