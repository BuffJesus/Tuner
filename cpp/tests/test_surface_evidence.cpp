// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::surface_evidence.

#include "doctest.h"

#include "tuner_core/surface_evidence.hpp"

using namespace tuner_core::surface_evidence;

TEST_CASE("offline empty inputs render the offline default summary") {
    Inputs in;
    in.connection_state_text = "disconnected";
    auto s = build(in);
    CHECK(s.connection_text == "Connection  disconnected");
    CHECK(s.connection_severity == "info");
    CHECK(s.source_text == "Source  Project Tune");
    CHECK(s.source_severity == "ok");
    CHECK(s.sync_text == "Sync  unavailable");
    CHECK(s.changes_text == "Changes  0 staged");
    CHECK(s.log_text == "Ops  idle");
    CHECK(s.runtime_text == "Runtime  offline");
    CHECK(s.summary_text.find("Offline context only.") != std::string::npos);
}

TEST_CASE("connected with ECU RAM picks accent source") {
    Inputs in;
    in.connected = true;
    in.connection_state_text = "connected";
    in.sync_state_present = true;
    in.sync_has_ecu_ram = true;
    auto s = build(in);
    CHECK(s.source_text == "Source  ECU RAM");
    CHECK(s.source_severity == "accent");
    CHECK(s.sync_text == "Sync  clean");
    CHECK(s.runtime_text == "Runtime  waiting");
    CHECK(s.runtime_severity == "warning");
}

TEST_CASE("staged changes change source and changes pills") {
    Inputs in;
    in.staged_count = 3;
    in.connection_state_text = "disconnected";
    auto s = build(in);
    CHECK(s.source_text == "Source  Staged Tune");
    CHECK(s.changes_text == "Changes  3 staged");
    CHECK(s.changes_severity == "accent");
    CHECK(s.summary_text.find("Staged changes exist") != std::string::npos);
}

TEST_CASE("mismatches dominate the summary copy") {
    Inputs in;
    in.connected = true;
    in.connection_state_text = "connected";
    in.sync_state_present = true;
    in.mismatch_count = 2;
    auto s = build(in);
    CHECK(s.sync_text == "Sync  2 mismatch(s)");
    CHECK(s.sync_severity == "warning");
    CHECK(s.summary_text.find("Review sync mismatches") != std::string::npos);
}

TEST_CASE("unwritten ops mark the log pill warning") {
    Inputs in;
    in.connection_state_text = "disconnected";
    in.log_count = 5;
    in.has_unwritten = true;
    in.operation_log_summary_text = "  09:00:01  staged   p: 0 -> 1\n";
    auto s = build(in);
    CHECK(s.log_text == "Ops  5 event(s) pending");
    CHECK(s.log_severity == "warning");
    CHECK(s.summary_text.find("Unwritten operation history") != std::string::npos);
    CHECK(s.summary_text.find("Latest op: 09:00:01  staged") != std::string::npos);
}

TEST_CASE("runtime stale when age above 30s") {
    Inputs in;
    in.connected = true;
    in.connection_state_text = "connected";
    in.sync_state_present = true;
    in.runtime_present = true;
    in.runtime_value_count = 12;
    in.runtime_age_seconds = 75.0;
    auto s = build(in);
    CHECK(s.runtime_text == "Runtime  stale (1m 15s)");
    CHECK(s.runtime_severity == "warning");
    CHECK(s.summary_text.find("present but stale") != std::string::npos);
}

TEST_CASE("runtime fresh produces accent pill") {
    Inputs in;
    in.connected = true;
    in.connection_state_text = "connected";
    in.sync_state_present = true;
    in.runtime_present = true;
    in.runtime_value_count = 12;
    in.runtime_age_seconds = 4.0;
    auto s = build(in);
    CHECK(s.runtime_text == "Runtime  12 channel(s)");
    CHECK(s.runtime_severity == "accent");
    CHECK(s.summary_text.find("Live runtime evidence is available") != std::string::npos);
}

TEST_CASE("cached runtime when offline but snapshot present") {
    Inputs in;
    in.connection_state_text = "disconnected";
    in.runtime_present = true;
    in.runtime_value_count = 7;
    auto s = build(in);
    CHECK(s.runtime_text == "Runtime  7 cached");
    CHECK(s.runtime_severity == "info");
}

TEST_CASE("format_age formats seconds, minutes, hours") {
    CHECK(format_age(0) == "0s");
    CHECK(format_age(45) == "45s");
    CHECK(format_age(60) == "1m 0s");
    CHECK(format_age(125) == "2m 5s");
    CHECK(format_age(3600) == "1h 0m");
    CHECK(format_age(3725) == "1h 2m");
}
