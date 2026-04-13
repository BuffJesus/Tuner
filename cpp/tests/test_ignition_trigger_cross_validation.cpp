// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/ignition_trigger_cross_validation.hpp"

#include <map>

namespace itcv = tuner_core::ignition_trigger_cross_validation;
using itcv::ChecklistItem;
using itcv::Status;
using itcv::Page;
using itcv::Parameter;

using VM = std::map<std::string, double>;

static itcv::ValueGetter make_gv(VM& m) {
    return [&m](const std::string& name) -> std::optional<double> {
        auto it = m.find(name); return it != m.end() ? std::optional(it->second) : std::nullopt;
    };
}

static itcv::OptionLabelGetter no_labels = [](const Parameter&) -> std::string { return ""; };

TEST_SUITE("ignition_trigger_cross_validation") {

TEST_CASE("null pages produce needed items") {
    VM vals;
    auto gv = make_gv(vals);
    auto items = itcv::validate(nullptr, nullptr, gv, no_labels);
    CHECK(!items.empty());
    bool has_dwell = false, has_angle = false;
    for (const auto& i : items) {
        if (i.key == "dwell_configured") has_dwell = true;
        if (i.key == "reference_angle") has_angle = true;
    }
    CHECK(has_dwell); CHECK(has_angle);
}

TEST_CASE("zero dwell produces ERROR") {
    VM vals = {{"dwellRun", 0.0}};
    auto gv = make_gv(vals);
    Page ign; ign.parameters = {{"dwellRun", "Running Dwell", {}, {}}};
    auto items = itcv::validate(&ign, nullptr, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "dwell_configured") { CHECK(i.status == Status::ERROR); return; }
    }
    FAIL("dwell_configured not found");
}

TEST_CASE("normal dwell produces OK") {
    VM vals = {{"dwellRun", 3.5}};
    auto gv = make_gv(vals);
    Page ign; ign.parameters = {{"dwellRun", "Running Dwell", {}, {}}};
    auto items = itcv::validate(&ign, nullptr, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "dwell_configured") { CHECK(i.status == Status::OK); return; }
    }
    FAIL("dwell_configured not found");
}

TEST_CASE("high dwell produces ERROR") {
    VM vals = {{"dwellRun", 15.0}};
    auto gv = make_gv(vals);
    Page ign; ign.parameters = {{"dwellRun", "Running Dwell", {}, {}}};
    auto items = itcv::validate(&ign, nullptr, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "dwell_configured") { CHECK(i.status == Status::ERROR); return; }
    }
    FAIL("dwell_configured not found");
}

TEST_CASE("reference angle zero produces WARNING") {
    VM vals = {{"TriggerAngle", 0.0}};
    auto gv = make_gv(vals);
    Page trig; trig.parameters = {{"TriggerAngle", "TDC Angle", {}, {}}};
    auto items = itcv::validate(nullptr, &trig, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "reference_angle") { CHECK(i.status == Status::WARNING); return; }
    }
    FAIL("reference_angle not found");
}

TEST_CASE("trigger geometry valid 36-1") {
    VM vals = {{"nTeeth", 36.0}, {"missingTeeth", 1.0}};
    auto gv = make_gv(vals);
    Page trig; trig.parameters = {
        {"nTeeth", "Tooth Count", {}, {}},
        {"missingTeeth", "Missing Teeth", {}, {}},
    };
    auto items = itcv::validate(nullptr, &trig, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "trigger_geometry") {
            CHECK(i.status == Status::OK);
            CHECK(i.detail.find("36-1") != std::string::npos);
            return;
        }
    }
    FAIL("trigger_geometry not found");
}

TEST_CASE("trigger geometry missing > teeth produces ERROR") {
    VM vals = {{"nTeeth", 10.0}, {"missingTeeth", 12.0}};
    auto gv = make_gv(vals);
    Page trig; trig.parameters = {
        {"nTeeth", "Tooth Count", {}, {}},
        {"missingTeeth", "Missing Teeth", {}, {}},
    };
    auto items = itcv::validate(nullptr, &trig, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "trigger_geometry") { CHECK(i.status == Status::ERROR); return; }
    }
    FAIL("trigger_geometry not found");
}

TEST_CASE("sequential on crank-only produces WARNING") {
    VM vals = {{"TrigPattern", 3.0}, {"sparkMode", 3.0}};  // GM 7X + sequential ign
    auto gv = make_gv(vals);
    Page ign; ign.parameters = {
        {"TrigPattern", "Trigger Pattern", {}, {}},
        {"sparkMode", "Spark Mode", {}, {}},
    };
    auto items = itcv::validate(&ign, nullptr, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "sequential_cam_sync") {
            CHECK(i.status == Status::WARNING);
            CHECK(i.detail.find("crank-only") != std::string::npos);
            return;
        }
    }
    FAIL("sequential_cam_sync not found");
}

TEST_CASE("sequential with configured cam produces OK") {
    VM vals = {{"TrigPattern", 0.0}, {"sparkMode", 3.0}, {"trigPatternSec", 0.0}};
    auto gv = make_gv(vals);
    Page ign; ign.parameters = {{"TrigPattern", "Pattern", {}, {}}, {"sparkMode", "Spark", {}, {}}};
    Page trig; trig.parameters = {{"trigPatternSec", "Secondary", {}, {}}};
    auto items = itcv::validate(&ign, &trig, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "sequential_cam_sync") {
            CHECK(i.status == Status::OK);
            CHECK(i.detail.find("Single tooth cam") != std::string::npos);
            return;
        }
    }
    FAIL("sequential_cam_sync not found");
}

TEST_CASE("trigger topology summary produced") {
    VM vals = {{"TrigPattern", 0.0}, {"nTeeth", 36.0}, {"missingTeeth", 1.0}};
    auto gv = make_gv(vals);
    Page trig; trig.parameters = {
        {"TrigPattern", "Pattern", {}, {}},
        {"nTeeth", "Teeth", {}, {}},
        {"missingTeeth", "Missing", {}, {}},
    };
    auto items = itcv::validate(nullptr, &trig, gv, no_labels);
    for (const auto& i : items) {
        if (i.key == "trigger_topology") {
            CHECK(i.status == Status::INFO);
            CHECK(i.detail.find("36-1") != std::string::npos);
            return;
        }
    }
    FAIL("trigger_topology not found");
}

}  // TEST_SUITE
