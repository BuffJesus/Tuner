// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/trigger_log_visualization.hpp"

namespace tlv = tuner_core::trigger_log_visualization;

static tlv::Row make_row(std::initializer_list<std::pair<std::string, std::string>> fields) {
    tlv::Row r; r.fields.assign(fields.begin(), fields.end()); return r;
}

TEST_SUITE("trigger_log_visualization") {

TEST_CASE("empty rows produce no-data snapshot") {
    auto snap = tlv::build_from_rows({}, {"Time", "Crank"});
    CHECK(snap.trace_count == 0);
    CHECK(snap.summary_text.find("needs a time column") != std::string::npos);
}

TEST_CASE("no time column produces error snapshot") {
    auto row = make_row({{"voltage", "3.3"}});
    auto snap = tlv::build_from_rows({row}, {"voltage"});
    CHECK(snap.trace_count == 0);
    CHECK(snap.summary_text.find("needs a time column") != std::string::npos);
}

TEST_CASE("single numeric trace") {
    std::vector<tlv::Row> rows;
    for (int i = 0; i < 5; ++i)
        rows.push_back(make_row({{"Time_ms", std::to_string(i * 10)}, {"RPM", std::to_string(1000 + i * 100)}}));
    auto snap = tlv::build_from_rows(rows, {"Time_ms", "RPM"});
    CHECK(snap.trace_count == 1);
    CHECK(snap.point_count == 5);
    CHECK(snap.traces[0].name == "RPM");
    CHECK(snap.traces[0].x_values.size() == 5);
    CHECK(snap.summary_text.find("1 numeric trace") != std::string::npos);
}

TEST_CASE("digital signal detection") {
    std::vector<tlv::Row> rows;
    rows.push_back(make_row({{"Time", "0"}, {"crank", "0"}}));
    rows.push_back(make_row({{"Time", "1"}, {"crank", "1"}}));
    rows.push_back(make_row({{"Time", "2"}, {"crank", "0"}}));
    rows.push_back(make_row({{"Time", "3"}, {"crank", "1"}}));
    auto snap = tlv::build_from_rows(rows, {"Time", "crank"});
    REQUIRE(snap.trace_count == 1);
    CHECK(snap.traces[0].is_digital == true);
}

TEST_CASE("digital crank signal produces edge annotations") {
    std::vector<tlv::Row> rows;
    for (int i = 0; i < 8; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i)}, {"crankSignal", std::to_string(i % 2)}}));
    auto snap = tlv::build_from_rows(rows, {"Time", "crankSignal"});
    CHECK(snap.trace_count == 1);
    // Should have up to 6 edge annotations (cap).
    bool has_rising = false, has_falling = false;
    for (const auto& a : snap.annotations) {
        if (a.label.find("rising") != std::string::npos) has_rising = true;
        if (a.label.find("falling") != std::string::npos) has_falling = true;
    }
    CHECK(has_rising);
    CHECK(has_falling);
    CHECK(snap.annotations.size() <= 7);  // 6 edges + possible gap
}

TEST_CASE("gap annotation detects missing tooth") {
    // 10 samples with uniform spacing except one gap > 1.6× median.
    std::vector<tlv::Row> rows;
    double t = 0;
    for (int i = 0; i < 10; ++i) {
        rows.push_back(make_row({{"Time", std::to_string(t)}, {"tooth", std::to_string(i % 2)}}));
        t += (i == 5) ? 10.0 : 1.0;  // Gap at i=5.
    }
    auto snap = tlv::build_from_rows(rows, {"Time", "tooth"});
    bool has_gap = false;
    for (const auto& a : snap.annotations) {
        if (a.label.find("missing-tooth") != std::string::npos) {
            has_gap = true;
            CHECK(a.severity == "warning");
        }
    }
    CHECK(has_gap);
}

TEST_CASE("non-numeric column is skipped") {
    std::vector<tlv::Row> rows;
    rows.push_back(make_row({{"Time", "0"}, {"label", "hello"}}));
    rows.push_back(make_row({{"Time", "1"}, {"label", "world"}}));
    auto snap = tlv::build_from_rows(rows, {"Time", "label"});
    CHECK(snap.trace_count == 0);
    CHECK(snap.summary_text.find("no numeric signal") != std::string::npos);
}

TEST_CASE("multiple traces stacked with offset") {
    std::vector<tlv::Row> rows;
    for (int i = 0; i < 4; ++i) {
        rows.push_back(make_row({
            {"Time", std::to_string(i)},
            {"signal_a", std::to_string(i * 10)},
            {"signal_b", std::to_string(i * 5)},
        }));
    }
    auto snap = tlv::build_from_rows(rows, {"Time", "signal_a", "signal_b"});
    CHECK(snap.trace_count == 2);
    // Second trace should have a positive offset.
    CHECK(snap.traces[1].offset > 0);
}

}  // TEST_SUITE
