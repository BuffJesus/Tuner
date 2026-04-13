// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/trigger_log_analysis.hpp"

#include <map>

namespace tla = tuner_core::trigger_log_analysis;

static tla::Row make_row(std::initializer_list<std::pair<std::string, std::string>> f) {
    tla::Row r; r.fields.assign(f.begin(), f.end()); return r;
}

TEST_SUITE("trigger_log_analysis") {

TEST_CASE("empty rows produce warning") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    auto s = tla::analyze_rows({}, {"Time", "tooth"}, dc);
    CHECK(s.severity == "warning");
    CHECK(s.sample_count == 0);
    CHECK(!s.findings.empty());
}

TEST_CASE("detect log kind from column names") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    // Tooth log.
    auto s1 = tla::analyze_rows({make_row({{"Time", "0"}, {"toothTime", "100"}})},
                                 {"Time", "toothTime"}, dc);
    CHECK(s1.log_kind == "tooth");
    // Composite log.
    auto s2 = tla::analyze_rows({make_row({{"Time", "0"}, {"compositeLevel", "1"}})},
                                 {"Time", "compositeLevel"}, dc);
    CHECK(s2.log_kind == "composite");
}

TEST_CASE("missing time column produces warning") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    auto s = tla::analyze_rows({make_row({{"voltage", "3.3"}})}, {"voltage"}, dc);
    CHECK(s.severity == "warning");
    bool found = false;
    for (const auto& f : s.findings)
        if (f.find("time column") != std::string::npos) found = true;
    CHECK(found);
}

TEST_CASE("non-increasing timestamps produce warning") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    std::vector<tla::Row> rows;
    for (int i = 0; i < 25; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i == 15 ? 5 : i)}, {"tooth", "1"}}));
    auto s = tla::analyze_rows(rows, {"Time", "tooth"}, dc);
    bool found = false;
    for (const auto& f : s.findings)
        if (f.find("not strictly increasing") != std::string::npos) found = true;
    CHECK(found);
}

TEST_CASE("missing tooth gap plausible for 36-1") {
    tla::DecoderContext dc;
    dc.decoder_name = "Missing Tooth";
    dc.cam_mode = "cam_optional";
    dc.tooth_count = 36.0;
    dc.missing_teeth = 1.0;
    // Build 36-1 pattern: 35 normal teeth + 1 gap = 2x spacing.
    std::vector<tla::Row> rows;
    double t = 0;
    for (int rev = 0; rev < 3; ++rev) {
        for (int tooth = 0; tooth < 36; ++tooth) {
            rows.push_back(make_row({{"Time_ms", std::to_string(t)}, {"toothTime", "1"}}));
            t += (tooth == 35) ? 2.0 : 1.0;
        }
    }
    auto s = tla::analyze_rows(rows, {"Time_ms", "toothTime"}, dc);
    bool plausible = false;
    for (const auto& f : s.findings)
        if (f.find("plausible") != std::string::npos) plausible = true;
    CHECK(plausible);
}

TEST_CASE("sequential on crank-only produces warning") {
    tla::DecoderContext dc;
    dc.decoder_name = "GM 7X";
    dc.cam_mode = "crank_only";
    dc.sequential_requested = true;
    std::vector<tla::Row> rows;
    for (int i = 0; i < 30; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i)}, {"tooth", "1"}}));
    auto s = tla::analyze_rows(rows, {"Time", "tooth"}, dc);
    CHECK(s.severity == "warning");
    bool found = false;
    for (const auto& f : s.findings)
        if (f.find("crank-only") != std::string::npos) found = true;
    CHECK(found);
}

TEST_CASE("full sync not present produces warning") {
    tla::DecoderContext dc;
    dc.decoder_name = "Missing Tooth";
    dc.cam_mode = "unknown";
    dc.full_sync = false;
    std::vector<tla::Row> rows;
    for (int i = 0; i < 30; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i)}, {"tooth", "1"}}));
    auto s = tla::analyze_rows(rows, {"Time", "tooth"}, dc);
    bool found = false;
    for (const auto& f : s.findings)
        if (f.find("full sync is not present") != std::string::npos) found = true;
    CHECK(found);
}

TEST_CASE("build_decoder_context produces reasonable defaults") {
    std::map<std::string, double> vals = {{"TrigPattern", 0}, {"nTeeth", 36}, {"missingTeeth", 1}};
    auto dc = tla::build_decoder_context(
        [&](const std::string& name) -> std::optional<double> {
            auto it = vals.find(name); return it != vals.end() ? std::optional(it->second) : std::nullopt;
        });
    CHECK(dc.decoder_name == "Missing Tooth");
    CHECK(dc.wheel_summary.find("36-1") != std::string::npos);
    CHECK(dc.cam_mode == "cam_optional");
}

TEST_CASE("build_decoder_context with runtime fullSync") {
    auto dc = tla::build_decoder_context(
        [](const std::string&) -> std::optional<double> { return std::nullopt; },
        0x10);  // bit 4 = fullSync
    REQUIRE(dc.full_sync.has_value());
    CHECK(*dc.full_sync == true);
}

TEST_CASE("capture summary text format") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    std::vector<tla::Row> rows;
    for (int i = 0; i < 30; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i)}, {"toothTime", "1"}}));
    auto s = tla::analyze_rows(rows, {"Time", "toothTime"}, dc);
    CHECK(s.capture_summary_text.find("30 row(s)") != std::string::npos);
    CHECK(s.capture_summary_text.find("tooth log") != std::string::npos);
}

TEST_CASE("preview text shows first 8 rows") {
    tla::DecoderContext dc; dc.decoder_name = "Missing Tooth"; dc.cam_mode = "unknown";
    std::vector<tla::Row> rows;
    for (int i = 0; i < 20; ++i)
        rows.push_back(make_row({{"Time", std::to_string(i)}, {"v", std::to_string(i * 10)}}));
    auto s = tla::analyze_rows(rows, {"Time", "v"}, dc);
    CHECK(s.preview_text.find("...") != std::string::npos);
}

}  // TEST_SUITE
