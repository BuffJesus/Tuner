// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::NativeFormat. Mirrors the Python
// suite in tests/unit/test_native_format_service.py — same shape of
// fixtures and assertions so cross-validation is direct.

#include "doctest.h"

#include "tuner_core/native_format.hpp"

#include <variant>

namespace {

tuner_core::NativeDefinition sample_definition() {
    tuner_core::NativeDefinition def;
    def.name = "speeduino 202501-T41";
    def.firmware_signature = "speeduino 202501-T41";

    tuner_core::NativeParameter req;
    req.semantic_id = "reqFuel";
    req.legacy_name = "reqFuel";
    req.label = "Required fuel";
    req.units = "ms";
    req.min_value = 0.0;
    req.max_value = 20.0;
    def.parameters.push_back(req);

    tuner_core::NativeAxis rpm;
    rpm.semantic_id = "rpmBins";
    rpm.legacy_name = "rpmBins";
    rpm.length = 16;
    rpm.units = "rpm";
    def.axes.push_back(rpm);

    tuner_core::NativeTable ve;
    ve.semantic_id = "veTable";
    ve.legacy_name = "veTable";
    ve.rows = 16;
    ve.columns = 16;
    ve.units = "%";
    def.tables.push_back(ve);

    return def;
}

}  // namespace

TEST_CASE("dump_definition emits schema_version field") {
    auto def = sample_definition();
    auto text = tuner_core::dump_definition(def);
    CHECK(text.find("\"schema_version\": \"1.0\"") != std::string::npos);
    CHECK(text.find("\"name\": \"speeduino 202501-T41\"") != std::string::npos);
    CHECK(text.find("\"firmware_signature\": \"speeduino 202501-T41\"") != std::string::npos);
}

TEST_CASE("dump_definition includes parameters axes tables curves arrays") {
    auto def = sample_definition();
    auto text = tuner_core::dump_definition(def);
    CHECK(text.find("\"parameters\":") != std::string::npos);
    CHECK(text.find("\"axes\":") != std::string::npos);
    CHECK(text.find("\"tables\":") != std::string::npos);
    CHECK(text.find("\"curves\":") != std::string::npos);
    CHECK(text.find("\"semantic_id\": \"reqFuel\"") != std::string::npos);
    CHECK(text.find("\"semantic_id\": \"rpmBins\"") != std::string::npos);
    CHECK(text.find("\"semantic_id\": \"veTable\"") != std::string::npos);
}

TEST_CASE("definition round trip is structurally lossless") {
    auto original = sample_definition();
    auto text = tuner_core::dump_definition(original);
    auto reloaded = tuner_core::load_definition(text);
    auto re_text = tuner_core::dump_definition(reloaded);
    CHECK(re_text == text);
}

TEST_CASE("tune round trip preserves scalar list and string values") {
    tuner_core::NativeTune tune;
    tune.definition_signature = "speeduino 202501-T41";
    tune.values["reqFuel"] = 8.5;
    tune.values["veTable"] = std::vector<double>{50.0, 55.0, 60.0, 65.0};
    tune.values["label"] = std::string("shop tune");

    auto text = tuner_core::dump_tune(tune);
    auto reloaded = tuner_core::load_tune(text);

    REQUIRE(reloaded.values.size() == 3);
    CHECK(std::get<double>(reloaded.values["reqFuel"]) == doctest::Approx(8.5));
    CHECK(std::get<std::string>(reloaded.values["label"]) == "shop tune");
    auto ve = std::get<std::vector<double>>(reloaded.values["veTable"]);
    REQUIRE(ve.size() == 4);
    CHECK(ve[0] == doctest::Approx(50.0));
    CHECK(ve[3] == doctest::Approx(65.0));
}

TEST_CASE("missing schema_version raises") {
    CHECK_THROWS_AS(
        tuner_core::load_definition("{\"name\": \"x\"}"),
        tuner_core::NativeFormatVersionError);
}

TEST_CASE("future major version raises") {
    CHECK_THROWS_AS(
        tuner_core::load_definition("{\"schema_version\": \"9.0\", \"name\": \"x\"}"),
        tuner_core::NativeFormatVersionError);
}

TEST_CASE("forward-compatible minor bump accepted") {
    auto def = tuner_core::load_definition(
        "{\"schema_version\": \"1.5\", \"name\": \"x\"}");
    CHECK(def.name == "x");
    CHECK(def.schema_version == "1.5");
}

TEST_CASE("unparsable schema_version raises") {
    CHECK_THROWS_AS(
        tuner_core::load_definition("{\"schema_version\": \"abc\", \"name\": \"x\"}"),
        tuner_core::NativeFormatVersionError);
}

TEST_CASE("invalid JSON raises runtime error not version error") {
    CHECK_THROWS_AS(
        tuner_core::load_definition("{not json"),
        std::runtime_error);
}

// -----------------------------------------------------------------------
// Multi-tune slot metadata (v1.1 — forward-compatible)
// -----------------------------------------------------------------------

TEST_CASE("tune round trip preserves slot_index and slot_name") {
    tuner_core::NativeTune tune;
    tune.definition_signature = "speeduino 202501-T41";
    tune.slot_index = 2;
    tune.slot_name = "Race Gas";
    tune.values["reqFuel"] = 8.5;

    auto text = tuner_core::dump_tune(tune);
    auto reloaded = tuner_core::load_tune(text);

    REQUIRE(reloaded.slot_index.has_value());
    CHECK(*reloaded.slot_index == 2);
    REQUIRE(reloaded.slot_name.has_value());
    CHECK(*reloaded.slot_name == "Race Gas");
}

TEST_CASE("tune without slot fields loads as nullopt (legacy v1.0)") {
    auto reloaded = tuner_core::load_tune(
        "{\"schema_version\": \"1.0\", \"values\": {}}");
    CHECK_FALSE(reloaded.slot_index.has_value());
    CHECK_FALSE(reloaded.slot_name.has_value());
}

TEST_CASE("tune slot_index only (no name) round-trips") {
    tuner_core::NativeTune tune;
    tune.slot_index = 0;
    auto text = tuner_core::dump_tune(tune);
    auto reloaded = tuner_core::load_tune(text);
    REQUIRE(reloaded.slot_index.has_value());
    CHECK(*reloaded.slot_index == 0);
    CHECK_FALSE(reloaded.slot_name.has_value());
}

TEST_CASE("tune slot_name serialised as null when nullopt") {
    tuner_core::NativeTune tune;
    tune.slot_index = 1;
    // Deliberately leave slot_name empty.
    auto text = tuner_core::dump_tune(tune);
    CHECK(text.find("\"slot_name\": null") != std::string::npos);
    CHECK(text.find("\"slot_index\": 1") != std::string::npos);
    // And it round-trips as nullopt.
    auto reloaded = tuner_core::load_tune(text);
    CHECK_FALSE(reloaded.slot_name.has_value());
    REQUIRE(reloaded.slot_index.has_value());
    CHECK(*reloaded.slot_index == 1);
}

TEST_CASE("non-object root raises") {
    CHECK_THROWS_AS(
        tuner_core::load_definition("[]"),
        std::runtime_error);
}
