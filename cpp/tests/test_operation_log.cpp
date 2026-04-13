// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::operation_log.

#include "doctest.h"

#include "tuner_core/operation_log.hpp"

#include <string>

using namespace tuner_core::operation_log;

namespace {

constexpr TimeOfDay T(int h, int m, int s) { return TimeOfDay{h, m, s}; }

}  // namespace

// ---------------------------------------------------------------------------
// summary_line per kind
// ---------------------------------------------------------------------------

TEST_CASE("summary_line: STAGED uses → and zero-padded HH:MM:SS") {
    OperationEntry e;
    e.kind = OperationKind::STAGED;
    e.parameter_name = "reqFuel";
    e.old_value = "10.0";
    e.new_value = "12.5";
    e.timestamp = T(9, 5, 3);
    CHECK(e.summary_line() == "09:05:03  staged   reqFuel: 10.0 \xe2\x86\x92 12.5");
}

TEST_CASE("summary_line: REVERTED uses ← arrow") {
    OperationEntry e;
    e.kind = OperationKind::REVERTED;
    e.parameter_name = "reqFuel";
    e.old_value = "10.0";
    e.new_value = "12.5";
    e.timestamp = T(14, 30, 0);
    CHECK(e.summary_line() == "14:30:00  reverted reqFuel: 12.5 \xe2\x86\x90 10.0");
}

TEST_CASE("summary_line: WRITTEN uses '=' separator") {
    OperationEntry e;
    e.kind = OperationKind::WRITTEN;
    e.parameter_name = "reqFuel";
    e.new_value = "12.5";
    e.timestamp = T(0, 0, 1);
    CHECK(e.summary_line() == "00:00:01  written  reqFuel = 12.5");
}

TEST_CASE("summary_line: BURNED uses '=' separator") {
    OperationEntry e;
    e.kind = OperationKind::BURNED;
    e.parameter_name = "reqFuel";
    e.new_value = "12.5";
    e.timestamp = T(23, 59, 59);
    CHECK(e.summary_line() == "23:59:59  burned   reqFuel = 12.5");
}

// ---------------------------------------------------------------------------
// OperationLog state
// ---------------------------------------------------------------------------

TEST_CASE("OperationLog: empty summary text") {
    OperationLog log;
    CHECK(log.summary_text() == "No operations recorded this session.");
    CHECK(log.entries().empty());
}

TEST_CASE("OperationLog: record_staged appends an entry") {
    OperationLog log;
    log.record_staged("reqFuel", "10.0", "12.5", T(10, 0, 0));
    REQUIRE(log.entries().size() == 1);
    CHECK(log.entries()[0].kind == OperationKind::STAGED);
    CHECK(log.entries()[0].parameter_name == "reqFuel");
}

TEST_CASE("OperationLog: record_written stores value in both old/new fields") {
    OperationLog log;
    log.record_written("reqFuel", "12.5", T(10, 0, 0));
    REQUIRE(log.entries().size() == 1);
    CHECK(log.entries()[0].old_value == "12.5");
    CHECK(log.entries()[0].new_value == "12.5");
}

TEST_CASE("OperationLog: recent returns the last N entries") {
    OperationLog log;
    for (int i = 0; i < 5; ++i) {
        log.record_staged("p" + std::to_string(i), "0", "1", T(0, 0, i));
    }
    auto last3 = log.recent(3);
    REQUIRE(last3.size() == 3);
    CHECK(last3[0].parameter_name == "p2");
    CHECK(last3[2].parameter_name == "p4");
}

TEST_CASE("OperationLog: recent caps at total entry count") {
    OperationLog log;
    log.record_staged("p", "0", "1", T(0, 0, 0));
    auto all = log.recent(50);
    CHECK(all.size() == 1);
}

TEST_CASE("OperationLog: summary_text reverses recent so newest is first") {
    OperationLog log;
    log.record_staged("p1", "0", "1", T(0, 0, 1));
    log.record_staged("p2", "0", "2", T(0, 0, 2));
    auto text = log.summary_text();
    auto p1_pos = text.find("p1");
    auto p2_pos = text.find("p2");
    REQUIRE(p1_pos != std::string::npos);
    REQUIRE(p2_pos != std::string::npos);
    CHECK(p2_pos < p1_pos);  // p2 (newer) comes first
}

TEST_CASE("OperationLog: clear empties the entry list") {
    OperationLog log;
    log.record_staged("p", "0", "1", T(0, 0, 0));
    log.clear();
    CHECK(log.entries().empty());
    CHECK(log.summary_text() == "No operations recorded this session.");
}

TEST_CASE("to_string mirrors Python OperationKind values") {
    CHECK(to_string(OperationKind::STAGED) == "staged");
    CHECK(to_string(OperationKind::REVERTED) == "reverted");
    CHECK(to_string(OperationKind::WRITTEN) == "written");
    CHECK(to_string(OperationKind::BURNED) == "burned");
}
