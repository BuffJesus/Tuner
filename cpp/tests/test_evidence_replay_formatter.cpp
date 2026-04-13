// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/evidence_replay_formatter.hpp"

namespace erfmt = tuner_core::evidence_replay_formatter;
namespace er = tuner_core::evidence_replay;

static er::Snapshot make_snap() {
    er::Snapshot s;
    s.captured_at_iso = "2026-04-10T12:00:00Z";
    s.session_state = "connected";
    s.connection_text = "COM3 @ 115200";
    s.source_text = "ECU-RAM";
    s.sync_summary_text = "Synced";
    s.staged_summary_text = "2 changes staged.";
    s.operation_summary_text = "3 operations.";
    s.operation_session_count = 1;
    s.latest_write_text = "reqFuel = 6.1";
    s.latest_burn_text = "Page 0 burned";
    s.runtime_summary_text = "Runtime OK";
    s.runtime_channel_count = 2;
    s.runtime_age_seconds = 1.5;
    s.runtime_channels = {{"rpm", 2500, "RPM"}, {"map", 95, "kPa"}};
    s.evidence_summary_text = "All good.";
    return s;
}

TEST_SUITE("evidence_replay_formatter") {

TEST_CASE("to_text contains key sections") {
    auto s = make_snap();
    auto text = erfmt::to_text(s);
    CHECK(text.find("Captured: 2026-04-10") != std::string::npos);
    CHECK(text.find("Session: connected") != std::string::npos);
    CHECK(text.find("COM3") != std::string::npos);
    CHECK(text.find("Latest write: reqFuel") != std::string::npos);
    CHECK(text.find("Latest burn: Page 0") != std::string::npos);
    CHECK(text.find("Runtime values:") != std::string::npos);
    CHECK(text.find("rpm = 2500") != std::string::npos);
    CHECK(text.find("Evidence Summary:") != std::string::npos);
    CHECK(text.find("Operation Evidence:") != std::string::npos);
}

TEST_CASE("to_json produces valid JSON with sorted keys") {
    auto s = make_snap();
    auto json = erfmt::to_json(s);
    CHECK(json.find("\"captured_at\"") != std::string::npos);
    CHECK(json.find("\"session_state\"") != std::string::npos);
    CHECK(json.find("\"runtime_channels\"") != std::string::npos);
    CHECK(json.find("2500") != std::string::npos);
}

TEST_CASE("to_text handles empty channels") {
    er::Snapshot s;
    s.captured_at_iso = "2026-04-10T00:00:00Z";
    auto text = erfmt::to_text(s);
    CHECK(text.find("Runtime channels captured: 0") != std::string::npos);
    CHECK(text.find("Runtime values:") == std::string::npos);
}

TEST_CASE("to_json null runtime_age when absent") {
    er::Snapshot s;
    s.captured_at_iso = "2026-04-10T00:00:00Z";
    auto json = erfmt::to_json(s);
    CHECK(json.find("\"runtime_age_seconds\": null") != std::string::npos);
}

}  // TEST_SUITE
