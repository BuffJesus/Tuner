// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/datalog_replay.hpp"

#include <stdexcept>

namespace dr = tuner_core::datalog_replay;

TEST_SUITE("datalog_replay") {

TEST_CASE("empty records throws") {
    CHECK_THROWS_AS(dr::select_row({}, 0), std::invalid_argument);
}

TEST_CASE("index clamped to valid range") {
    std::vector<dr::Record> recs = {
        {"2026-04-10T12:00:00Z", {{"rpm", 2500}, {"map", 95}}},
        {"2026-04-10T12:00:01Z", {{"rpm", 2600}, {"map", 96}}},
    };
    auto s = dr::select_row(recs, 99);
    CHECK(s.selected_index == 1);
    auto s2 = dr::select_row(recs, -5);
    CHECK(s2.selected_index == 0);
}

TEST_CASE("summary text contains row number and count") {
    std::vector<dr::Record> recs = {
        {"2026-04-10T12:00:00Z", {{"rpm", 2500}, {"map", 95}, {"tps", 42}}},
    };
    auto s = dr::select_row(recs, 0);
    CHECK(s.summary_text.find("row 1 of 1") != std::string::npos);
    CHECK(s.summary_text.find("3 channel(s)") != std::string::npos);
    CHECK(s.total_rows == 1);
    CHECK(s.channel_count == 3);
}

TEST_CASE("preview shows first 8 channels") {
    dr::Record rec;
    rec.timestamp_iso = "2026-04-10T00:00:00Z";
    for (int i = 0; i < 12; ++i)
        rec.values.push_back({"ch" + std::to_string(i), double(i)});
    auto s = dr::select_row({rec}, 0);
    // Should show ch0 through ch7, not ch8+.
    CHECK(s.preview_text.find("ch0=") != std::string::npos);
    CHECK(s.preview_text.find("ch7=") != std::string::npos);
    CHECK(s.preview_text.find("ch8=") == std::string::npos);
}

}  // TEST_SUITE
