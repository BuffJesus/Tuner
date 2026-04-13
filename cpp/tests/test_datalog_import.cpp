// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/datalog_import.hpp"

#include <stdexcept>

namespace di = tuner_core::datalog_import;

static di::CsvRow make_row(std::initializer_list<std::pair<std::string, std::string>> f) {
    di::CsvRow r; r.assign(f.begin(), f.end()); return r;
}

TEST_SUITE("datalog_import") {

TEST_CASE("empty rows throws") {
    CHECK_THROWS_AS(di::import_rows({"rpm", "map"}, {}, "test"), std::invalid_argument);
}

TEST_CASE("imports numeric rows") {
    std::vector<std::string> headers = {"Time_ms", "rpm", "map", "afr"};
    std::vector<di::CsvRow> rows = {
        make_row({{"Time_ms", "0"}, {"rpm", "800"}, {"map", "30"}, {"afr", "14.7"}}),
        make_row({{"Time_ms", "100"}, {"rpm", "1200"}, {"map", "45"}, {"afr", "14.5"}}),
        make_row({{"Time_ms", "200"}, {"rpm", "2500"}, {"map", "65"}, {"afr", "14.2"}}),
    };
    auto snap = di::import_rows(headers, rows, "test.csv");
    CHECK(snap.row_count == 3);
    CHECK(snap.channel_names.size() == 3);  // rpm, map, afr (Time_ms excluded)
    CHECK(snap.records.size() == 3);
    CHECK(snap.summary_text.find("3 datalog row(s)") != std::string::npos);
    CHECK(snap.summary_text.find("test.csv") != std::string::npos);
}

TEST_CASE("time_ms detected and converted to seconds") {
    std::vector<std::string> headers = {"Time_ms", "rpm"};
    std::vector<di::CsvRow> rows = {
        make_row({{"Time_ms", "1000"}, {"rpm", "800"}}),
        make_row({{"Time_ms", "2000"}, {"rpm", "900"}}),
    };
    auto snap = di::import_rows(headers, rows);
    CHECK(snap.records[0].timestamp_seconds == doctest::Approx(1.0));
    CHECK(snap.records[1].timestamp_seconds == doctest::Approx(2.0));
}

TEST_CASE("time_s detected and used directly") {
    std::vector<std::string> headers = {"Time", "rpm"};
    std::vector<di::CsvRow> rows = {
        make_row({{"Time", "5.5"}, {"rpm", "800"}}),
    };
    auto snap = di::import_rows(headers, rows);
    CHECK(snap.records[0].timestamp_seconds == doctest::Approx(5.5));
}

TEST_CASE("non-numeric values skipped") {
    std::vector<std::string> headers = {"rpm", "label"};
    std::vector<di::CsvRow> rows = {
        make_row({{"rpm", "800"}, {"label", "hello"}}),
    };
    auto snap = di::import_rows(headers, rows);
    CHECK(snap.records[0].values.count("rpm"));
    CHECK_FALSE(snap.records[0].values.count("label"));
    CHECK(snap.channel_names.size() == 1);
}

TEST_CASE("preview shows first 3 rows") {
    std::vector<std::string> headers = {"rpm"};
    std::vector<di::CsvRow> rows;
    for (int i = 0; i < 10; ++i)
        rows.push_back(make_row({{"rpm", std::to_string(800 + i * 100)}}));
    auto snap = di::import_rows(headers, rows);
    CHECK(snap.preview_text.find("Row 1") != std::string::npos);
    CHECK(snap.preview_text.find("Row 3") != std::string::npos);
    CHECK(snap.preview_text.find("Row 4") == std::string::npos);
}

TEST_CASE("channel names capped at 8 in summary") {
    std::vector<std::string> headers;
    di::CsvRow row;
    for (int i = 0; i < 12; ++i) {
        std::string name = "ch" + std::to_string(i);
        headers.push_back(name);
        row.push_back({name, "1.0"});
    }
    auto snap = di::import_rows(headers, {row});
    CHECK(snap.summary_text.find("...") != std::string::npos);
}

}  // TEST_SUITE
