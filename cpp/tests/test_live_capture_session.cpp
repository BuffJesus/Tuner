// SPDX-License-Identifier: MIT
//
// doctest cases for `live_capture_session.hpp` — port of the
// pure-logic helpers in `LiveCaptureSessionService`.

#include "doctest.h"

#include "tuner_core/live_capture_session.hpp"

#include <string>
#include <unordered_map>
#include <vector>

using namespace tuner_core::live_capture_session;

namespace {

CapturedRecord rec(double elapsed_ms,
                   std::initializer_list<std::pair<std::string, double>> kvs) {
    CapturedRecord r;
    r.elapsed_ms = elapsed_ms;
    for (const auto& [k, v] : kvs) {
        r.keys.push_back(k);
        r.values.push_back(v);
    }
    return r;
}

}  // namespace

TEST_CASE("status_text: ready when no rows and not recording") {
    CHECK(status_text(false, 0, 0.0) == "Ready");
    CHECK(status_text(false, 0, 12.5) == "Ready");
}

TEST_CASE("status_text: recording shape") {
    CHECK(status_text(true, 0, 0.0) == "Recording: 0 rows (0.0s)");
    CHECK(status_text(true, 5, 1.234) == "Recording: 5 rows (1.2s)");
    CHECK(status_text(true, 1234, 95.67) == "Recording: 1234 rows (95.7s)");
}

TEST_CASE("status_text: stopped-with-rows uses em dash") {
    // 0xE2 0x80 0x94 = U+2014 EM DASH
    const std::string em = "\xe2\x80\x94";
    CHECK(status_text(false, 5, 1.5)
          == "Stopped " + em + " 5 rows captured (1.5s)");
    CHECK(status_text(false, 100, 60.0)
          == "Stopped " + em + " 100 rows captured (60.0s)");
}

TEST_CASE("ordered_column_names: profile-first, records contribute extras") {
    std::vector<std::string> profile = {"rpm", "map", "afr"};
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"rpm", 800.0}, {"map", 30.0}, {"clt", 90.0}}),
        rec(10.0, {{"rpm", 850.0}, {"afr", 14.7}, {"iat", 25.0}}),
    };
    auto cols = ordered_column_names(profile, records);
    REQUIRE(cols.size() == 5);
    CHECK(cols[0] == "rpm");
    CHECK(cols[1] == "map");
    CHECK(cols[2] == "afr");
    CHECK(cols[3] == "clt");
    CHECK(cols[4] == "iat");
}

TEST_CASE("ordered_column_names: empty profile falls back to record insertion order") {
    std::vector<std::string> profile;
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"a", 1.0}, {"b", 2.0}}),
        rec(10.0, {{"b", 3.0}, {"c", 4.0}}),
        rec(20.0, {{"c", 5.0}, {"a", 6.0}}),
    };
    auto cols = ordered_column_names(profile, records);
    REQUIRE(cols.size() == 3);
    CHECK(cols[0] == "a");
    CHECK(cols[1] == "b");
    CHECK(cols[2] == "c");
}

TEST_CASE("ordered_column_names: profile names not seen in records still survive") {
    std::vector<std::string> profile = {"x", "y", "z"};
    std::vector<CapturedRecord> records;
    auto cols = ordered_column_names(profile, records);
    CHECK(cols == std::vector<std::string>{"x", "y", "z"});
}

TEST_CASE("ordered_column_names: empty profile + empty records yields empty list") {
    auto cols = ordered_column_names({}, {});
    CHECK(cols.empty());
}

TEST_CASE("format_value: positive digits use fixed format") {
    CHECK(format_value(3.14159, 2) == "3.14");
    CHECK(format_value(0.0, 3) == "0.000");
    CHECK(format_value(-1.5, 1) == "-1.5");
    CHECK(format_value(100.0, 0) == "100");
}

TEST_CASE("format_value: negative digits fall back to Python repr") {
    // Whole-number floats keep the .0 suffix.
    CHECK(format_value(42.0, -1) == "42.0");
    CHECK(format_value(0.0, -1) == "0.0");
    // Decimals round-trip via shortest repr.
    CHECK(format_value(3.14, -1) == "3.14");
    CHECK(format_value(-1.5, -1) == "-1.5");
}

TEST_CASE("format_csv: empty records returns empty string") {
    std::vector<CapturedRecord> records;
    std::vector<std::string> columns = {"rpm", "map"};
    std::unordered_map<std::string, int> digits;
    CHECK(format_csv(records, columns, digits).empty());
}

TEST_CASE("format_csv: single row with all columns present") {
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"rpm", 800.0}, {"map", 30.5}, {"afr", 14.72}}),
    };
    std::vector<std::string> columns = {"rpm", "map", "afr"};
    std::unordered_map<std::string, int> digits = {
        {"rpm", 0}, {"map", 1}, {"afr", 2},
    };
    auto out = format_csv(records, columns, digits);
    CHECK(out == "Time_ms,rpm,map,afr\r\n0,800,30.5,14.72\r\n");
}

TEST_CASE("format_csv: multiple rows + missing-cell fallback to empty") {
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"rpm", 800.0}, {"map", 30.0}}),
        rec(123.4, {{"rpm", 850.0}}),  // map missing -> empty cell
    };
    std::vector<std::string> columns = {"rpm", "map"};
    std::unordered_map<std::string, int> digits = {{"rpm", 0}, {"map", 0}};
    auto out = format_csv(records, columns, digits);
    CHECK(out == "Time_ms,rpm,map\r\n0,800,30\r\n123,850,\r\n");
}

TEST_CASE("format_csv: column missing from digits map uses repr") {
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"v", 3.14}}),
    };
    std::vector<std::string> columns = {"v"};
    std::unordered_map<std::string, int> digits;  // empty -> use repr
    auto out = format_csv(records, columns, digits);
    CHECK(out == "Time_ms,v\r\n0,3.14\r\n");
}

TEST_CASE("format_csv: header order follows the columns vector exactly") {
    std::vector<CapturedRecord> records = {
        rec(0.0, {{"a", 1.0}, {"b", 2.0}, {"c", 3.0}}),
    };
    std::vector<std::string> columns = {"c", "a", "b"};
    std::unordered_map<std::string, int> digits = {
        {"a", 0}, {"b", 0}, {"c", 0},
    };
    auto out = format_csv(records, columns, digits);
    CHECK(out == "Time_ms,c,a,b\r\n0,3,1,2\r\n");
}
