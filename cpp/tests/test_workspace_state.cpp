// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/workspace_state.hpp"

namespace ws = tuner_core::workspace_state;

TEST_SUITE("workspace_state") {

TEST_CASE("empty workspace") {
    ws::Workspace w;
    auto snap = w.snapshot();
    CHECK(snap.total_pages == 0);
    CHECK(snap.staged_count == 0);
    CHECK(snap.sync_state == ws::SyncState::OFFLINE);
}

TEST_CASE("set_pages initializes all as clean") {
    ws::Workspace w;
    w.set_pages({"page1", "page2", "page3"});
    auto snap = w.snapshot();
    CHECK(snap.total_pages == 3);
    CHECK(snap.active_page_id == "page1");
    CHECK(snap.active_page_state == ws::PageState::CLEAN);
}

TEST_CASE("select_page changes active") {
    ws::Workspace w;
    w.set_pages({"page1", "page2"});
    w.select_page("page2");
    CHECK(w.active_page() == "page2");
}

TEST_CASE("stage_edit transitions to STAGED") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "reqFuel");
    CHECK(w.page_state("page1") == ws::PageState::STAGED);
    CHECK(w.staged_count() == 1);
}

TEST_CASE("multiple edits accumulate count") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "reqFuel");
    w.stage_edit("page1", "nCylinders");
    w.stage_edit("page1", "dwell");
    CHECK(w.staged_count() == 3);
}

TEST_CASE("mark_written transitions state") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "reqFuel");
    w.mark_written("page1");
    CHECK(w.page_state("page1") == ws::PageState::WRITTEN);
}

TEST_CASE("mark_burned clears staged count") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "reqFuel");
    w.mark_burned("page1");
    CHECK(w.page_state("page1") == ws::PageState::BURNED);
    CHECK(w.staged_count() == 0);
}

TEST_CASE("revert_page returns to clean") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "reqFuel");
    w.revert_page("page1");
    CHECK(w.page_state("page1") == ws::PageState::CLEAN);
    CHECK(w.staged_count() == 0);
}

TEST_CASE("revert_all clears everything") {
    ws::Workspace w;
    w.set_pages({"page1", "page2"});
    w.stage_edit("page1", "a");
    w.stage_edit("page2", "b");
    w.revert_all();
    CHECK(w.staged_count() == 0);
    CHECK(w.page_state("page1") == ws::PageState::CLEAN);
    CHECK(w.page_state("page2") == ws::PageState::CLEAN);
}

TEST_CASE("sync state reflected in snapshot") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.set_sync_state(ws::SyncState::SYNCED);
    CHECK(w.snapshot().sync_state == ws::SyncState::SYNCED);
    CHECK(w.snapshot().status_text.find("Synced") != std::string::npos);
}

TEST_CASE("status text includes staged count") {
    ws::Workspace w;
    w.set_pages({"page1"});
    w.stage_edit("page1", "a");
    w.stage_edit("page1", "b");
    auto text = w.snapshot().status_text;
    CHECK(text.find("2 staged") != std::string::npos);
}

TEST_CASE("cross-page staged edits tracked independently") {
    ws::Workspace w;
    w.set_pages({"page1", "page2"});
    w.stage_edit("page1", "a");
    w.stage_edit("page2", "b");
    w.stage_edit("page2", "c");
    CHECK(w.staged_count() == 3);
    w.revert_page("page1");
    CHECK(w.staged_count() == 2);
    CHECK(w.page_state("page1") == ws::PageState::CLEAN);
    CHECK(w.page_state("page2") == ws::PageState::STAGED);
}

// Sub-slice 92: per-page staged count accessor used by the TUNE tab's
// live per-page staged indicator chip.
TEST_CASE("staged_count_for reports per-page totals") {
    ws::Workspace w;
    w.set_pages({"page1", "page2", "page3"});
    w.stage_edit("page1", "a");
    w.stage_edit("page2", "b");
    w.stage_edit("page2", "c");
    CHECK(w.staged_count_for("page1") == 1);
    CHECK(w.staged_count_for("page2") == 2);
    CHECK(w.staged_count_for("page3") == 0);
    CHECK(w.staged_count_for("nonexistent") == 0);
    w.revert_page("page2");
    CHECK(w.staged_count_for("page2") == 0);
    w.mark_burned("page1");
    CHECK(w.staged_count_for("page1") == 0);
}

// Sub-slice 95: aggregate_state + pages_in_state used by the three-zoom
// UI helpers to pick color and by the "Write to RAM" action to iterate
// only the pages that actually need writing.
TEST_CASE("aggregate_state reports the highest-priority page state") {
    ws::Workspace w;
    w.set_pages({"p1", "p2", "p3"});
    CHECK(w.aggregate_state() == ws::PageState::CLEAN);

    w.stage_edit("p1", "a");
    CHECK(w.aggregate_state() == ws::PageState::STAGED);

    w.mark_written("p1");
    // p1 is now WRITTEN, p2/p3 are CLEAN → aggregate should be WRITTEN.
    CHECK(w.aggregate_state() == ws::PageState::WRITTEN);

    w.stage_edit("p2", "b");
    // p1 WRITTEN, p2 STAGED → STAGED wins (highest priority).
    CHECK(w.aggregate_state() == ws::PageState::STAGED);

    w.mark_burned("p1");
    w.mark_burned("p2");
    w.revert_page("p2");  // needed because mark_burned clears count but keeps state
    // After burn: p1 BURNED, p2 was CLEANed by revert, p3 CLEAN.
    // Aggregate walks BURNED as the fallback before CLEAN.
    CHECK(w.aggregate_state() == ws::PageState::BURNED);
}

TEST_CASE("pages_in_state enumerates pages by state in insertion order") {
    ws::Workspace w;
    w.set_pages({"p1", "p2", "p3", "p4"});
    w.stage_edit("p2", "x");
    w.stage_edit("p4", "y");
    w.stage_edit("p1", "z");
    w.mark_written("p2");  // p2 is now WRITTEN, p1/p4 still STAGED

    auto staged = w.pages_in_state(ws::PageState::STAGED);
    REQUIRE(staged.size() == 2);
    CHECK(staged[0] == "p1");  // insertion order
    CHECK(staged[1] == "p4");

    auto written = w.pages_in_state(ws::PageState::WRITTEN);
    REQUIRE(written.size() == 1);
    CHECK(written[0] == "p2");

    auto clean = w.pages_in_state(ws::PageState::CLEAN);
    REQUIRE(clean.size() == 1);
    CHECK(clean[0] == "p3");

    CHECK(w.pages_in_state(ws::PageState::BURNED).empty());
}

}  // TEST_SUITE
