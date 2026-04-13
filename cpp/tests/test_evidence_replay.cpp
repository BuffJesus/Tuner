// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/evidence_replay.hpp"

namespace er = tuner_core::evidence_replay;

TEST_SUITE("evidence_replay") {

TEST_CASE("empty inputs produce default snapshot") {
    er::Inputs inp;
    inp.captured_at_iso = "2026-04-10T12:00:00Z";
    inp.session_state = "disconnected";
    auto snap = er::build(inp);
    CHECK(snap.captured_at_iso == "2026-04-10T12:00:00Z");
    CHECK(snap.session_state == "disconnected");
    CHECK(snap.staged_summary_text == "No staged changes.");
    CHECK(snap.operation_summary_text == "No operations recorded this session.");
    CHECK(snap.runtime_channel_count == 0);
    CHECK(snap.evidence_summary_text.find("Captured:") != std::string::npos);
    CHECK(snap.evidence_summary_text.find("none") != std::string::npos);
}

TEST_CASE("runtime channels populate count and summary") {
    er::Inputs inp;
    inp.captured_at_iso = "2026-04-10T12:00:00Z";
    inp.session_state = "connected";
    inp.runtime_channels = {
        {"rpm", 2500.0, "RPM"},
        {"map", 95.0, "kPa"},
        {"tps", 42.0, "%"},
    };
    inp.runtime_age_seconds = 1.5;
    auto snap = er::build(inp);
    CHECK(snap.runtime_channel_count == 3);
    CHECK(snap.evidence_summary_text.find("3") != std::string::npos);
    CHECK(snap.evidence_summary_text.find("old") != std::string::npos);
}

TEST_CASE("mismatch details appear in summary") {
    er::Inputs inp;
    inp.captured_at_iso = "2026-04-10T12:00:00Z";
    inp.sync_mismatch_details = {"Page 1 differs", "Page 3 differs"};
    auto snap = er::build(inp);
    CHECK(snap.sync_mismatch_details.size() == 2);
    CHECK(snap.evidence_summary_text.find("Sync mismatch: Page 1") != std::string::npos);
    CHECK(snap.evidence_summary_text.find("Sync mismatch: Page 3") != std::string::npos);
}

TEST_CASE("write and burn text appear in summary") {
    er::Inputs inp;
    inp.captured_at_iso = "2026-04-10T12:00:00Z";
    inp.latest_write_text = "reqFuel = 6.1";
    inp.latest_burn_text = "Page 0 burned";
    auto snap = er::build(inp);
    CHECK(snap.evidence_summary_text.find("Latest write: reqFuel") != std::string::npos);
    CHECK(snap.evidence_summary_text.find("Latest burn: Page 0") != std::string::npos);
}

TEST_CASE("staged summary forwarded when provided") {
    er::Inputs inp;
    inp.captured_at_iso = "2026-04-10T12:00:00Z";
    inp.staged_summary_text = "3 changes staged.";
    auto snap = er::build(inp);
    CHECK(snap.staged_summary_text == "3 changes staged.");
}

}  // TEST_SUITE
