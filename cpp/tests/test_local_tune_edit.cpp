// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::local_tune_edit — forty-ninth sub-slice.

#include <doctest.h>

#include "tuner_core/local_tune_edit.hpp"

#include <string>
#include <vector>

namespace lte = tuner_core::local_tune_edit;

static lte::TuneFile make_tune() {
    lte::TuneFile tf;
    tf.signature = "test";
    tf.constants = {
        {"reqFuel", 10.0, "ms", 2, 0, 0},
        {"nCylinders", 6.0, "count", 0, 0, 0},
        {"veTable", std::vector<double>(16, 80.0), "%", 0, 4, 4},
    };
    return tf;
}

// -----------------------------------------------------------------------
// 1. Get base value
// -----------------------------------------------------------------------
TEST_CASE("lte: get base value") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    auto* v = svc.get_value("reqFuel");
    REQUIRE(v != nullptr);
    CHECK(std::get<double>(v->value) == 10.0);
}

// -----------------------------------------------------------------------
// 2. Stage scalar
// -----------------------------------------------------------------------
TEST_CASE("lte: stage scalar") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "12.5");
    auto* v = svc.get_value("reqFuel");
    REQUIRE(v != nullptr);
    CHECK(std::get<double>(v->value) == doctest::Approx(12.5));
    CHECK(svc.is_dirty("reqFuel"));
}

// -----------------------------------------------------------------------
// 3. Stage list cell
// -----------------------------------------------------------------------
TEST_CASE("lte: stage list cell") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_list_cell("veTable", 0, 95.0);
    auto* v = svc.get_value("veTable");
    REQUIRE(v != nullptr);
    auto& list = std::get<std::vector<double>>(v->value);
    CHECK(list[0] == 95.0);
    CHECK(list[1] == 80.0);  // unchanged
}

// -----------------------------------------------------------------------
// 4. Undo/redo scalar
// -----------------------------------------------------------------------
TEST_CASE("lte: undo redo scalar") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "12.0");
    svc.stage_scalar_value("reqFuel", "15.0");

    CHECK(svc.can_undo("reqFuel"));
    svc.undo("reqFuel");
    CHECK(std::get<double>(svc.get_value("reqFuel")->value) == doctest::Approx(12.0));

    CHECK(svc.can_redo("reqFuel"));
    svc.redo("reqFuel");
    CHECK(std::get<double>(svc.get_value("reqFuel")->value) == doctest::Approx(15.0));
}

// -----------------------------------------------------------------------
// 5. Revert single parameter
// -----------------------------------------------------------------------
TEST_CASE("lte: revert single") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "99.0");
    CHECK(svc.is_dirty("reqFuel"));
    svc.revert("reqFuel");
    CHECK(!svc.is_dirty("reqFuel"));
    CHECK(std::get<double>(svc.get_value("reqFuel")->value) == 10.0);
}

// -----------------------------------------------------------------------
// 6. Revert all
// -----------------------------------------------------------------------
TEST_CASE("lte: revert all") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "99.0");
    svc.stage_scalar_value("nCylinders", "8.0");
    CHECK(svc.staged_count() == 2);
    svc.revert_all();
    CHECK(!svc.has_any_staged());
}

// -----------------------------------------------------------------------
// 7. Replace list
// -----------------------------------------------------------------------
TEST_CASE("lte: replace list") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    std::vector<double> new_values(16, 90.0);
    svc.replace_list("veTable", new_values);
    auto& list = std::get<std::vector<double>>(svc.get_value("veTable")->value);
    CHECK(list[0] == 90.0);
    CHECK(list[15] == 90.0);
}

// -----------------------------------------------------------------------
// 8. Scalar values dict
// -----------------------------------------------------------------------
TEST_CASE("lte: scalar values dict") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "12.0");
    auto dict = svc.get_scalar_values_dict();
    CHECK(dict["reqFuel"] == doctest::Approx(12.0));
    CHECK(dict["nCylinders"] == doctest::Approx(6.0));
    // veTable is a list, should not appear.
    CHECK(dict.find("veTable") == dict.end());
}

// -----------------------------------------------------------------------
// 9. Unknown parameter throws
// -----------------------------------------------------------------------
TEST_CASE("lte: unknown parameter throws") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    CHECK_THROWS(svc.stage_scalar_value("nonexistent", "1.0"));
}

// -----------------------------------------------------------------------
// 10. Base value unchanged after staging
// -----------------------------------------------------------------------
TEST_CASE("lte: base unchanged after staging") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "99.0");
    auto* base = svc.get_base_value("reqFuel");
    REQUIRE(base != nullptr);
    CHECK(std::get<double>(base->value) == 10.0);
}

// -----------------------------------------------------------------------
// 11. Set tune file clears state
// -----------------------------------------------------------------------
TEST_CASE("lte: set tune file clears state") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    svc.stage_scalar_value("reqFuel", "99.0");
    CHECK(svc.has_any_staged());

    svc.set_tune_file(&tune);
    CHECK(!svc.has_any_staged());
}

// -----------------------------------------------------------------------
// 12. staged_names enumerates pending edits in alphabetical order
// -----------------------------------------------------------------------
// Sub-slice 93: used by the TUNE-tab staged changes review popup.
TEST_CASE("lte: staged_names enumerates pending edits") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);

    CHECK(svc.staged_names().empty());

    svc.stage_scalar_value("reqFuel", "9.0");
    svc.stage_scalar_value("nCylinders", "8.0");
    svc.stage_list_cell("veTable", 0, 80.0);

    auto names = svc.staged_names();
    REQUIRE(names.size() == 3);
    // Alphabetical — deterministic regardless of insertion order.
    CHECK(names[0] == "nCylinders");
    CHECK(names[1] == "reqFuel");
    CHECK(names[2] == "veTable");

    svc.revert("reqFuel");
    auto after_revert = svc.staged_names();
    CHECK(after_revert.size() == 2);
    CHECK(after_revert[0] == "nCylinders");
    CHECK(after_revert[1] == "veTable");

    svc.revert_all();
    CHECK(svc.staged_names().empty());
}

// -----------------------------------------------------------------------
// 13. clamp_value honours explicit min/max (display units)
// -----------------------------------------------------------------------
TEST_CASE("lte: clamp_value honours explicit min/max") {
    lte::EditService svc;
    svc.set_limits_provider([](const std::string& name) -> std::optional<lte::ParameterLimits> {
        if (name == "aseTaperTime") {
            lte::ParameterLimits lim;
            lim.min_value = 0.0;
            lim.max_value = 25.5;
            lim.data_type = "U08";
            return lim;
        }
        return std::nullopt;
    });
    CHECK(svc.clamp_value("aseTaperTime", 10.0) == 10.0);
    CHECK(svc.clamp_value("aseTaperTime", -5.0) == 0.0);
    CHECK(svc.clamp_value("aseTaperTime", 99.0) == 25.5);
    // Unknown param passes through untouched.
    CHECK(svc.clamp_value("unknown", 9999.0) == 9999.0);
}

// -----------------------------------------------------------------------
// 14. clamp_value falls back to data_type range with scale + translate
// -----------------------------------------------------------------------
TEST_CASE("lte: clamp_value falls back to data_type range") {
    lte::EditService svc;
    svc.set_limits_provider([](const std::string& name) -> std::optional<lte::ParameterLimits> {
        if (name == "rawU08") {
            lte::ParameterLimits lim;
            lim.data_type = "U08";  // no explicit min/max
            return lim;
        }
        if (name == "scaled") {
            lte::ParameterLimits lim;
            lim.data_type = "U08";
            lim.scale = 0.1;           // display = raw * 0.1 → [0.0, 25.5]
            lim.translate = 0.0;
            return lim;
        }
        if (name == "signed16") {
            lte::ParameterLimits lim;
            lim.data_type = "S16";
            return lim;
        }
        return std::nullopt;
    });
    CHECK(svc.clamp_value("rawU08", 500.0) == 255.0);
    CHECK(svc.clamp_value("rawU08", -1.0)  == 0.0);
    CHECK(svc.clamp_value("scaled", 50.0) == doctest::Approx(25.5));
    CHECK(svc.clamp_value("scaled", -2.0) == 0.0);
    CHECK(svc.clamp_value("signed16", 99999.0) == 32767.0);
    CHECK(svc.clamp_value("signed16", -99999.0) == -32768.0);
}

// -----------------------------------------------------------------------
// 15. stage_scalar_value clamps out-of-range input and reports the flag
// -----------------------------------------------------------------------
TEST_CASE("lte: stage_scalar_value clamps and flags") {
    lte::TuneFile tf;
    tf.signature = "test";
    tf.constants = {{"boostPercent", 50.0, "%", 0, 0, 0}};
    lte::EditService svc;
    svc.set_tune_file(&tf);
    svc.set_limits_provider([](const std::string& name) -> std::optional<lte::ParameterLimits> {
        if (name == "boostPercent") {
            lte::ParameterLimits lim;
            lim.min_value = 0.0;
            lim.max_value = 100.0;
            lim.data_type = "U08";
            return lim;
        }
        return std::nullopt;
    });

    bool clamped = false;
    svc.stage_scalar_value("boostPercent", "75", &clamped);
    CHECK_FALSE(clamped);
    CHECK(std::get<double>(svc.get_value("boostPercent")->value) == 75.0);

    svc.stage_scalar_value("boostPercent", "250", &clamped);
    CHECK(clamped);
    CHECK(std::get<double>(svc.get_value("boostPercent")->value) == 100.0);

    svc.stage_scalar_value("boostPercent", "-10", &clamped);
    CHECK(clamped);
    CHECK(std::get<double>(svc.get_value("boostPercent")->value) == 0.0);
}

// -----------------------------------------------------------------------
// 16. stage_list_cell clamps cell edits to the declared range
// -----------------------------------------------------------------------
TEST_CASE("lte: stage_list_cell clamps table cells") {
    lte::TuneFile tf;
    tf.signature = "test";
    tf.constants = {{"veTable", std::vector<double>(16, 80.0), "%", 0, 4, 4}};
    lte::EditService svc;
    svc.set_tune_file(&tf);
    svc.set_limits_provider([](const std::string& name) -> std::optional<lte::ParameterLimits> {
        if (name == "veTable") {
            lte::ParameterLimits lim;
            lim.min_value = 0.0;
            lim.max_value = 200.0;
            lim.data_type = "U08";
            return lim;
        }
        return std::nullopt;
    });

    bool clamped = false;
    svc.stage_list_cell("veTable", 0, 150.0, &clamped);
    CHECK_FALSE(clamped);
    CHECK(std::get<std::vector<double>>(svc.get_value("veTable")->value)[0] == 150.0);

    svc.stage_list_cell("veTable", 1, 999.0, &clamped);
    CHECK(clamped);
    CHECK(std::get<std::vector<double>>(svc.get_value("veTable")->value)[1] == 200.0);

    svc.stage_list_cell("veTable", 2, -50.0, &clamped);
    CHECK(clamped);
    CHECK(std::get<std::vector<double>>(svc.get_value("veTable")->value)[2] == 0.0);
}

// -----------------------------------------------------------------------
// 17. replace_list clamps every cell — covers proposals and smoothing
// -----------------------------------------------------------------------
TEST_CASE("lte: replace_list clamps generator output") {
    lte::TuneFile tf;
    tf.signature = "test";
    tf.constants = {{"boostTable", std::vector<double>(4, 0.0), "%", 0, 2, 2}};
    lte::EditService svc;
    svc.set_tune_file(&tf);
    svc.set_limits_provider([](const std::string& name) -> std::optional<lte::ParameterLimits> {
        if (name == "boostTable") {
            lte::ParameterLimits lim;
            lim.min_value = 0.0;
            lim.max_value = 100.0;
            lim.data_type = "U08";
            return lim;
        }
        return std::nullopt;
    });

    svc.replace_list("boostTable", {-5.0, 50.0, 200.0, 75.0});
    const auto& v = std::get<std::vector<double>>(svc.get_value("boostTable")->value);
    CHECK(v[0] == 0.0);
    CHECK(v[1] == 50.0);
    CHECK(v[2] == 100.0);
    CHECK(v[3] == 75.0);
}

// -----------------------------------------------------------------------
// 18. No provider installed → no clamping (backwards compatible)
// -----------------------------------------------------------------------
TEST_CASE("lte: no provider, no clamp") {
    auto tune = make_tune();
    lte::EditService svc;
    svc.set_tune_file(&tune);
    // Provider deliberately not set.
    bool clamped = true;
    svc.stage_scalar_value("reqFuel", "99999", &clamped);
    CHECK_FALSE(clamped);
    CHECK(std::get<double>(svc.get_value("reqFuel")->value) == 99999.0);
}
