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
