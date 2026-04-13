// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::hardware_setup_validation.

#include "doctest.h"

#include "tuner_core/hardware_setup_validation.hpp"

#include <map>
#include <string>
#include <vector>

using namespace tuner_core::hardware_setup_validation;

namespace {

ValueLookup from_map(const std::map<std::string, double>& m) {
    return [m](std::string_view name) -> std::optional<double> {
        auto it = m.find(std::string(name));
        if (it == m.end()) return std::nullopt;
        return it->second;
    };
}

}  // namespace

TEST_CASE("dwell > 10 ms produces ERROR issue") {
    auto issues = validate({"dwellRun"}, from_map({{"dwellRun", 12.5}}));
    REQUIRE(issues.size() >= 1);
    bool found = false;
    for (const auto& i : issues) {
        if (i.severity == Severity::ERROR &&
            i.message.find("excessive") != std::string::npos) {
            found = true;
            CHECK(i.message.find("12.5 ms") != std::string::npos);
            CHECK(i.detail.has_value());
        }
    }
    CHECK(found);
}

TEST_CASE("dwell == 0 produces WARNING") {
    auto issues = validate({"dwellRun"}, from_map({{"dwellRun", 0.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.severity == Severity::WARNING &&
            i.message.find("is zero") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("dwellrun outside 1.5–6.0 ms produces implausible-range warning") {
    auto issues = validate({"dwellRun"}, from_map({{"dwellRun", 8.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("outside the typical 1.5–6.0 ms range") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("missing teeth >= total teeth is an ERROR") {
    auto issues = validate(
        {"nTeeth", "missingTeeth"},
        from_map({{"nTeeth", 36.0}, {"missingTeeth", 36.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.severity == Severity::ERROR &&
            i.message.find("must be less than total tooth count") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("missing teeth >= half is a WARNING") {
    auto issues = validate(
        {"nTeeth", "missingTeeth"},
        from_map({{"nTeeth", 36.0}, {"missingTeeth", 20.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.severity == Severity::WARNING &&
            i.message.find("more than half") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("injector dead time zero produces WARNING") {
    auto issues = validate({"injOpen"}, from_map({{"injOpen", 0.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("dead time 'injOpen' is zero") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("injector dead time > 5 ms produces implausibly-high WARNING") {
    auto issues = validate({"injOpen"}, from_map({{"injOpen", 7.5}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("implausibly high") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("injector flow zero produces WARNING") {
    auto issues = validate({"injectorFlow"}, from_map({{"injectorFlow", 0.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("Injector flow rate 'injectorFlow' is zero") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("required fuel zero produces WARNING") {
    auto issues = validate({"reqFuel"}, from_map({{"reqFuel", 0.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("Required fuel is zero") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("trigger angle zero produces WARNING") {
    auto issues = validate({"triggerAngle"}, from_map({{"triggerAngle", 0.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("Trigger angle 'triggerAngle' is zero") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("wideband selected with no calibration produces WARNING") {
    auto issues = validate({"egoType"}, from_map({{"egoType", 2.0}}));
    bool found = false;
    for (const auto& i : issues) {
        if (i.message.find("Wideband sensor selected but no calibration") != std::string::npos) {
            found = true;
        }
    }
    CHECK(found);
}

TEST_CASE("wideband with calibration table present is OK") {
    auto issues = validate(
        {"egoType", "afrCalTable"},
        from_map({{"egoType", 2.0}}));
    for (const auto& i : issues) {
        CHECK(i.message.find("Wideband sensor selected but no calibration") == std::string::npos);
    }
}

TEST_CASE("clean parameter set produces no issues") {
    auto issues = validate(
        {"dwellRun", "nTeeth", "missingTeeth", "injOpen", "injectorFlow",
         "reqFuel", "triggerAngle"},
        from_map({
            {"dwellRun", 3.0},
            {"nTeeth", 36.0},
            {"missingTeeth", 1.0},
            {"injOpen", 1.0},
            {"injectorFlow", 220.0},
            {"reqFuel", 12.5},
            {"triggerAngle", 60.0},
        }));
    CHECK(issues.empty());
}
