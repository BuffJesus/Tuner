// SPDX-License-Identifier: MIT
#include <doctest.h>
#include "tuner_core/sensor_setup_checklist.hpp"

#include <map>
#include <optional>
#include <string>

namespace ssc = tuner_core::sensor_setup_checklist;

using ValueMap = std::map<std::string, double>;

static ssc::ValueGetter make_getter(ValueMap& m) {
    return [&m](const std::string& name) -> std::optional<double> {
        auto it = m.find(name);
        return (it != m.end()) ? std::optional(it->second) : std::nullopt;
    };
}

static ssc::OptionLabelGetter no_labels = [](const ssc::Parameter&) -> std::string { return ""; };

static ssc::Page make_page(std::initializer_list<ssc::Parameter> params) {
    ssc::Page p; p.parameters.assign(params.begin(), params.end()); return p;
}

TEST_SUITE("sensor_setup_checklist") {

TEST_CASE("empty pages produce no items") {
    ValueMap vals;
    auto gv = make_getter(vals);
    auto items = ssc::validate({}, gv, no_labels);
    CHECK(items.empty());
}

TEST_CASE("ego type disabled produces INFO") {
    ValueMap vals; vals["egoType"] = 0.0;
    auto gv = make_getter(vals);
    auto page = make_page({{"egoType", "EGO Sensor Type", {}, {}}});
    auto items = ssc::validate({page}, gv, no_labels);
    REQUIRE(!items.empty());
    CHECK(items[0].key == "ego_type_configured");
    CHECK(items[0].status == ssc::Status::INFO);
}

TEST_CASE("ego type wideband produces OK") {
    ValueMap vals; vals["egoType"] = 2.0;
    auto gv = make_getter(vals);
    auto page = make_page({{"egoType", "EGO Sensor Type", {}, {}}});
    auto items = ssc::validate({page}, gv, no_labels);
    REQUIRE(!items.empty());
    CHECK(items[0].status == ssc::Status::OK);
    CHECK(items[0].detail.find("Wide Band") != std::string::npos);
}

TEST_CASE("wideband cal needed when wideband selected but cal is zero") {
    ValueMap vals; vals["egoType"] = 2.0; vals["afrCal"] = 0.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"egoType", "EGO Type", {}, {}},
        {"afrCal", "Wideband Calibration", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "wideband_cal") { found = true; CHECK(item.status == ssc::Status::NEEDED); }
    }
    CHECK(found);
}

TEST_CASE("stoich out of range produces WARNING") {
    ValueMap vals; vals["stoich"] = 3.0;
    auto gv = make_getter(vals);
    auto page = make_page({{"stoich", "Stoich AFR", {}, {}}});
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "stoich_plausible") { found = true; CHECK(item.status == ssc::Status::WARNING); }
    }
    CHECK(found);
}

TEST_CASE("stoich petrol range produces OK with petrol label") {
    ValueMap vals; vals["stoich"] = 14.7;
    auto gv = make_getter(vals);
    auto page = make_page({{"stoich", "Stoich AFR", {}, {}}});
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "stoich_plausible") {
            found = true;
            CHECK(item.status == ssc::Status::OK);
            CHECK(item.detail.find("petrol") != std::string::npos);
        }
    }
    CHECK(found);
}

TEST_CASE("TPS inverted produces ERROR") {
    ValueMap vals; vals["tpsMin"] = 800.0; vals["tpsMax"] = 100.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"tpsMin", "TPS Min", {}, {}},
        {"tpsMax", "TPS Max", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "tps_range") { found = true; CHECK(item.status == ssc::Status::ERROR); }
    }
    CHECK(found);
}

TEST_CASE("TPS narrow range produces WARNING") {
    ValueMap vals; vals["tpsMin"] = 100.0; vals["tpsMax"] = 130.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"tpsMin", "TPS Min", {}, {}},
        {"tpsMax", "TPS Max", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "tps_range") { found = true; CHECK(item.status == ssc::Status::WARNING); }
    }
    CHECK(found);
}

TEST_CASE("MAP invalid range produces ERROR") {
    ValueMap vals; vals["mapMin"] = 200.0; vals["mapMax"] = 100.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"mapMin", "MAP Min", {}, {}},
        {"mapMax", "MAP Max", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "map_range") { found = true; CHECK(item.status == ssc::Status::ERROR); }
    }
    CHECK(found);
}

TEST_CASE("flex calibration high <= low produces ERROR") {
    ValueMap vals;
    vals["flexEnabled"] = 1.0;
    vals["flexFreqLow"] = 100.0;
    vals["flexFreqHigh"] = 50.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"flexEnabled", "Flex Sensor", {}, {}},
        {"flexFreqLow", "Low Freq", {}, {}},
        {"flexFreqHigh", "High Freq", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "flex_calibration") { found = true; CHECK(item.status == ssc::Status::ERROR); }
    }
    CHECK(found);
}

TEST_CASE("oil pressure calibration OK") {
    ValueMap vals;
    vals["oilPressureEnable"] = 1.0;
    vals["oilPressureMin"] = 0.0;
    vals["oilPressureMax"] = 10.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"oilPressureEnable", "Oil Pressure Enable", {}, {}},
        {"oilPressureMin", "Oil Min", {}, {}},
        {"oilPressureMax", "Oil Max", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "oil_calibration") { found = true; CHECK(item.status == ssc::Status::OK); }
    }
    CHECK(found);
}

TEST_CASE("baro calibration invalid range") {
    ValueMap vals;
    vals["useExtBaro"] = 1.0;
    vals["baroMin"] = 100.0;
    vals["baroMax"] = 50.0;
    auto gv = make_getter(vals);
    auto page = make_page({
        {"useExtBaro", "Use External Baro", {}, {}},
        {"baroMin", "Baro Min", {}, {}},
        {"baroMax", "Baro Max", {}, {}},
    });
    auto items = ssc::validate({page}, gv, no_labels);
    bool found = false;
    for (const auto& item : items) {
        if (item.key == "baro_calibration") { found = true; CHECK(item.status == ssc::Status::ERROR); }
    }
    CHECK(found);
}

}  // TEST_SUITE
