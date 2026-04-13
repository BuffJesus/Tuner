// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::operation_evidence.

#include "doctest.h"

#include "tuner_core/operation_evidence.hpp"

#include <vector>

using namespace tuner_core::operation_evidence;
using tuner_core::operation_log::OperationEntry;
using tuner_core::operation_log::OperationKind;
using tuner_core::operation_log::TimeOfDay;

namespace {

OperationEntry make_entry(OperationKind kind, std::string name, int s) {
    OperationEntry e;
    e.kind = kind;
    e.parameter_name = std::move(name);
    e.old_value = "0";
    e.new_value = "1";
    e.timestamp = TimeOfDay{0, 0, s};
    return e;
}

}  // namespace

TEST_CASE("build: empty entries returns idle summary") {
    auto snap = build({}, false);
    CHECK(snap.summary_text == "No operations recorded this session.");
    CHECK(snap.session_count == 0);
    CHECK_FALSE(snap.latest_write_entry.has_value());
    CHECK_FALSE(snap.latest_burn_entry.has_value());
    CHECK_FALSE(snap.active_session.has_value());
}

TEST_CASE("build: single staged entry → one session, no write or burn") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::STAGED, "p1", 0),
    };
    auto snap = build(entries, true);
    CHECK(snap.session_count == 1);
    REQUIRE(snap.active_session.has_value());
    CHECK(snap.active_session->entry_count == 1);
    CHECK_FALSE(snap.active_session->has_burn);
    CHECK_FALSE(snap.active_session->has_write);
    CHECK(snap.active_session->has_unwritten_stage);
    CHECK(snap.summary_text.find("unwritten staged changes") != std::string::npos);
}

TEST_CASE("build: write+burn closes a session and starts a new one on next staged") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::STAGED,  "p1", 0),
        make_entry(OperationKind::WRITTEN, "p1", 1),
        make_entry(OperationKind::BURNED,  "p1", 2),
        make_entry(OperationKind::STAGED,  "p2", 3),
    };
    auto snap = build(entries, false);
    CHECK(snap.session_count == 2);
    REQUIRE(snap.active_session.has_value());
    CHECK(snap.active_session->sequence == 2);
    CHECK(snap.active_session->entry_count == 1);
}

TEST_CASE("build: latest_write_entry and latest_burn_entry are populated") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::WRITTEN, "p1", 1),
        make_entry(OperationKind::BURNED,  "p1", 2),
    };
    auto snap = build(entries, false);
    REQUIRE(snap.latest_write_entry.has_value());
    CHECK(snap.latest_write_entry->parameter_name == "p1");
    REQUIRE(snap.latest_burn_entry.has_value());
    CHECK(snap.latest_burn_entry->parameter_name == "p1");
}

TEST_CASE("build: summary text mentions latest write and burn") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::WRITTEN, "reqFuel", 1),
        make_entry(OperationKind::BURNED,  "reqFuel", 2),
    };
    auto snap = build(entries, false);
    CHECK(snap.summary_text.find("Last write") != std::string::npos);
    CHECK(snap.summary_text.find("Last burn") != std::string::npos);
    CHECK(snap.summary_text.find("burned; verify persisted values") != std::string::npos);
}

TEST_CASE("build: recent operations list reverses entry order") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::STAGED, "first", 1),
        make_entry(OperationKind::STAGED, "second", 2),
    };
    auto snap = build(entries, true);
    auto first_pos = snap.summary_text.find("first");
    auto second_pos = snap.summary_text.find("second");
    REQUIRE(first_pos != std::string::npos);
    REQUIRE(second_pos != std::string::npos);
    // "Recent operations:" header is followed by entries in reverse order.
    auto recent_pos = snap.summary_text.find("Recent operations:");
    REQUIRE(recent_pos != std::string::npos);
    CHECK(second_pos < first_pos);
    CHECK(recent_pos < second_pos);
}

TEST_CASE("build: limit caps the recent operations list") {
    std::vector<OperationEntry> entries;
    for (int i = 0; i < 20; ++i) {
        entries.push_back(make_entry(OperationKind::STAGED, "p" + std::to_string(i), i));
    }
    auto snap = build(entries, true, 5);
    // Only the last 5 should appear in the recent operations list.
    CHECK(snap.summary_text.find("p19") != std::string::npos);
    CHECK(snap.summary_text.find("p15") != std::string::npos);
    CHECK(snap.summary_text.find("p14") == std::string::npos);
}

TEST_CASE("build: write-without-burn produces 'written but not burned' status") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::WRITTEN, "p1", 1),
    };
    auto snap = build(entries, false);
    CHECK(snap.summary_text.find("written to RAM but not burned") != std::string::npos);
}

TEST_CASE("build: idle session history with no writes") {
    std::vector<OperationEntry> entries{
        make_entry(OperationKind::REVERTED, "p1", 1),
    };
    auto snap = build(entries, false);
    CHECK(snap.summary_text.find("session history exists, but no writes") != std::string::npos);
}
