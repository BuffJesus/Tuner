// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::sync_state.

#include "doctest.h"

#include "tuner_core/sync_state.hpp"

using namespace tuner_core::sync_state;

namespace {

DefinitionInputs make_def(std::string sig, std::vector<std::size_t> pages = {}) {
    DefinitionInputs d;
    d.firmware_signature = std::move(sig);
    d.page_sizes = std::move(pages);
    return d;
}

TuneFileInputs make_tune(
    std::string sig,
    std::optional<std::size_t> page_count = std::nullopt,
    std::vector<std::pair<std::string, ScalarOrList>> base = {}) {
    TuneFileInputs t;
    t.signature = std::move(sig);
    t.page_count = page_count;
    t.base_values = std::move(base);
    return t;
}

}  // namespace

TEST_CASE("build: no inputs → clean state") {
    auto s = build(std::nullopt, std::nullopt, std::nullopt, false, "offline");
    CHECK(s.is_clean());
    CHECK_FALSE(s.has_ecu_ram);
    CHECK(s.connection_state == "offline");
}

TEST_CASE("build: signature mismatch produces SIGNATURE_MISMATCH") {
    auto s = build(
        make_def("speeduino 202501-T41"),
        make_tune("speeduino 202501-MEGA"),
        std::nullopt, false, "connected");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].kind == MismatchKind::SIGNATURE_MISMATCH);
    CHECK(s.mismatches[0].detail.find("Definition expects") != std::string::npos);
}

TEST_CASE("build: matching signatures produce no mismatch") {
    auto s = build(
        make_def("speeduino 202501-T41"),
        make_tune("speeduino 202501-T41"),
        std::nullopt, false, "connected");
    CHECK(s.is_clean());
}

TEST_CASE("build: page-count mismatch produces PAGE_SIZE_MISMATCH") {
    auto s = build(
        make_def("sig", {128, 256, 128}),
        make_tune("sig", 5),
        std::nullopt, false, "connected");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].kind == MismatchKind::PAGE_SIZE_MISMATCH);
    CHECK(s.mismatches[0].detail.find("declares 3 page(s)") != std::string::npos);
    CHECK(s.mismatches[0].detail.find("saved with 5 page(s)") != std::string::npos);
}

TEST_CASE("build: ECU vs tune diff produces ECU_VS_TUNE with preview") {
    auto def = make_def("sig", {128});
    auto tune = make_tune("sig", 1, {
        {"reqFuel", ScalarOrList{12.5}},
        {"nCylinders", ScalarOrList{4.0}},
    });
    auto ram = std::vector<std::pair<std::string, ScalarOrList>>{
        {"reqFuel", ScalarOrList{10.0}},   // diff
        {"nCylinders", ScalarOrList{4.0}}, // same
    };
    auto s = build(def, tune, ram, false, "connected");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].kind == MismatchKind::ECU_VS_TUNE);
    CHECK(s.mismatches[0].detail.find("1 parameter(s) differ") != std::string::npos);
    CHECK(s.mismatches[0].detail.find("reqFuel") != std::string::npos);
}

TEST_CASE("build: ECU diff with more than 5 entries gets ellipsis suffix") {
    auto def = make_def("sig", {128});
    std::vector<std::pair<std::string, ScalarOrList>> base;
    std::vector<std::pair<std::string, ScalarOrList>> ram;
    for (int i = 0; i < 6; ++i) {
        base.emplace_back("p" + std::to_string(i), ScalarOrList{0.0});
        ram.emplace_back("p" + std::to_string(i), ScalarOrList{double(i + 1)});
    }
    auto s = build(def, make_tune("sig", 1, std::move(base)), ram, false, "connected");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].detail.find("...") != std::string::npos);
    CHECK(s.mismatches[0].detail.find("6 parameter(s) differ") != std::string::npos);
}

TEST_CASE("build: stale_staged when has_staged and no ECU RAM") {
    auto s = build(std::nullopt, std::nullopt, std::nullopt, true, "offline");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].kind == MismatchKind::STALE_STAGED);
}

TEST_CASE("build: has_staged with ECU RAM does NOT trigger stale_staged") {
    auto def = make_def("sig", {128});
    auto tune = make_tune("sig", 1);
    auto ram = std::vector<std::pair<std::string, ScalarOrList>>{};
    auto s = build(def, tune, ram, true, "connected");
    for (const auto& m : s.mismatches) {
        CHECK(m.kind != MismatchKind::STALE_STAGED);
    }
}

TEST_CASE("build: ECU diff with list values uses element equality") {
    auto def = make_def("sig", {128});
    auto tune = make_tune("sig", 1, {
        {"veRow", ScalarOrList{std::vector<double>{70, 75, 80}}},
    });
    auto ram = std::vector<std::pair<std::string, ScalarOrList>>{
        {"veRow", ScalarOrList{std::vector<double>{70, 75, 81}}},  // last cell differs
    };
    auto s = build(def, tune, ram, false, "connected");
    REQUIRE(s.mismatches.size() == 1);
    CHECK(s.mismatches[0].kind == MismatchKind::ECU_VS_TUNE);
}

TEST_CASE("to_string mirrors Python SyncMismatchKind values") {
    CHECK(to_string(MismatchKind::SIGNATURE_MISMATCH) == "signature_mismatch");
    CHECK(to_string(MismatchKind::PAGE_SIZE_MISMATCH) == "page_size_mismatch");
    CHECK(to_string(MismatchKind::ECU_VS_TUNE) == "ecu_vs_tune");
    CHECK(to_string(MismatchKind::STALE_STAGED) == "stale_staged");
}
