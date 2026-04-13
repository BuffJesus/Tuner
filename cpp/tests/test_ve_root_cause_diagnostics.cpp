// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::ve_root_cause_diagnostics.

#include "doctest.h"

#include "tuner_core/ve_root_cause_diagnostics.hpp"

namespace rcd = tuner_core::ve_root_cause_diagnostics;
namespace vps = tuner_core::ve_proposal_smoothing;

namespace {

vps::Proposal make(int r, int c, double cf) {
    vps::Proposal p;
    p.row_index = r;
    p.col_index = c;
    p.current_ve = 100.0;
    p.proposed_ve = 100.0 * cf;
    p.correction_factor = cf;
    p.sample_count = 1;
    return p;
}

}  // namespace

TEST_CASE("below MIN_PROPOSALS produces an empty report with explanatory text") {
    std::vector<vps::Proposal> ps;
    for (int i = 0; i < 3; ++i) ps.push_back(make(0, i, 1.10));
    auto r = rcd::diagnose(ps);
    CHECK(r.diagnostics.empty());
    CHECK_FALSE(r.has_findings());
    CHECK(r.summary_text.find("only 3 proposal") != std::string::npos);
}

TEST_CASE("healthy data produces no diagnostics") {
    std::vector<vps::Proposal> ps;
    // Mixed corrections, none big, no correlation.
    ps.push_back(make(0, 0, 1.01));
    ps.push_back(make(0, 1, 0.99));
    ps.push_back(make(1, 0, 1.00));
    ps.push_back(make(1, 1, 1.02));
    ps.push_back(make(2, 0, 0.98));
    ps.push_back(make(2, 1, 1.01));
    auto r = rcd::diagnose(ps);
    CHECK(r.diagnostics.empty());
    CHECK(r.summary_text.find("no systemic patterns") != std::string::npos);
}

TEST_CASE("uniform lean bias fires injector_flow_error") {
    std::vector<vps::Proposal> ps;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c)
            ps.push_back(make(r, c, 1.10));  // 10% lean everywhere
    auto rep = rcd::diagnose(ps);
    bool found = false;
    for (const auto& d : rep.diagnostics) {
        if (d.rule == "injector_flow_error") {
            found = true;
            CHECK(d.severity == "warning");
            CHECK(d.message.find("lean") != std::string::npos);
        }
    }
    CHECK(found);
}

TEST_CASE("uniform rich bias fires injector_flow_error with rich label") {
    std::vector<vps::Proposal> ps;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c)
            ps.push_back(make(r, c, 0.90));
    auto rep = rcd::diagnose(ps);
    bool found = false;
    for (const auto& d : rep.diagnostics) {
        if (d.rule == "injector_flow_error") {
            found = true;
            CHECK(d.message.find("rich") != std::string::npos);
        }
    }
    CHECK(found);
}

TEST_CASE("high variance suppresses injector_flow_error") {
    std::vector<vps::Proposal> ps;
    // Mean ~1.10 but huge variance — should not fire uniform-bias rule.
    ps.push_back(make(0, 0, 1.30));
    ps.push_back(make(0, 1, 0.90));
    ps.push_back(make(1, 0, 1.30));
    ps.push_back(make(1, 1, 0.90));
    ps.push_back(make(2, 0, 1.30));
    ps.push_back(make(2, 1, 0.90));
    auto rep = rcd::diagnose(ps);
    for (const auto& d : rep.diagnostics) {
        CHECK(d.rule != "injector_flow_error");
    }
}

TEST_CASE("deadtime error fires when low-load region is biased more than rest") {
    std::vector<vps::Proposal> ps;
    // 4x4 grid; bottom-left quadrant strongly lean, rest near unity.
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            double cf = (r <= 1 && c <= 1) ? 1.20 : 1.00;
            ps.push_back(make(r, c, cf));
        }
    }
    auto rep = rcd::diagnose(ps);
    bool found = false;
    for (const auto& d : rep.diagnostics) {
        if (d.rule == "deadtime_error") {
            found = true;
            CHECK(d.severity == "warning");
        }
    }
    CHECK(found);
}

TEST_CASE("opposite high/low load bias fires target_table_error") {
    std::vector<vps::Proposal> ps;
    // 4 rows; low rows lean (cf>1), high rows rich (cf<1).
    for (int c = 0; c < 3; ++c) {
        ps.push_back(make(0, c, 1.08));
        ps.push_back(make(1, c, 1.07));
        ps.push_back(make(2, c, 0.93));
        ps.push_back(make(3, c, 0.92));
    }
    auto rep = rcd::diagnose(ps);
    bool found = false;
    for (const auto& d : rep.diagnostics) {
        if (d.rule == "target_table_error") {
            found = true;
            CHECK(d.severity == "info");
        }
    }
    CHECK(found);
}

TEST_CASE("strong load-axis correlation fires sensor_calibration_error") {
    std::vector<vps::Proposal> ps;
    // Linear ramp: row index 0..5 → cf 1.00..1.25
    for (int r = 0; r < 6; ++r) {
        ps.push_back(make(r, 0, 1.00 + 0.05 * r));
    }
    auto rep = rcd::diagnose(ps);
    bool found = false;
    for (const auto& d : rep.diagnostics) {
        if (d.rule == "sensor_calibration_error") {
            found = true;
            CHECK(d.severity == "info");
            CHECK(d.message.find("Pearson r=") != std::string::npos);
        }
    }
    CHECK(found);
}

TEST_CASE("input is never mutated") {
    std::vector<vps::Proposal> ps;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c)
            ps.push_back(make(r, c, 1.10));
    rcd::diagnose(ps);
    CHECK(ps.size() == 9);
    CHECK(ps[0].correction_factor == doctest::Approx(1.10));
}

TEST_CASE("summary text format pin for findings") {
    std::vector<vps::Proposal> ps;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c)
            ps.push_back(make(r, c, 1.10));
    auto rep = rcd::diagnose(ps);
    CHECK(rep.has_findings());
    CHECK(rep.summary_text.find("Root-cause diagnostics:") == 0);
    CHECK(rep.summary_text.find("pattern(s) found") != std::string::npos);
}
