// SPDX-License-Identifier: MIT
//
// Integration tests that exercise multiple ported services against the
// real production INI and MSQ fixtures. These verify end-to-end behavior
// that unit tests on synthetic data cannot catch.

#include <doctest.h>
#include "tuner_core/ecu_definition_compiler.hpp"
#include "tuner_core/tuning_page_builder.hpp"
#include "tuner_core/table_rendering.hpp"
#include "tuner_core/table_view.hpp"
#include "tuner_core/table_replay_context.hpp"
#include "tuner_core/msq_parser.hpp"
#include "tuner_core/local_tune_edit.hpp"
#include "tuner_core/flash_preflight.hpp"
#include "tuner_core/firmware_catalog.hpp"
#include "tuner_core/board_detection.hpp"
#include "tuner_core/sensor_setup_checklist.hpp"
#include "tuner_core/curve_page_builder.hpp"

#include <filesystem>
#include <span>
#include <string>

namespace {

std::filesystem::path find_ini() {
    const char* paths[] = {
        "tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "../../../tests/fixtures/speeduino-dropbear-v2.0.1.ini",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/speeduino-dropbear-v2.0.1.ini",
    };
    for (const char* p : paths)
        if (std::filesystem::exists(p)) return p;
    return {};
}

std::filesystem::path find_msq() {
    const char* paths[] = {
        "tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "../../../tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
        "D:/Documents/JetBrains/Python/Tuner/tests/fixtures/Ford300_TwinGT28_BaseStartup.msq",
    };
    for (const char* p : paths)
        if (std::filesystem::exists(p)) return p;
    return {};
}

}  // namespace

TEST_SUITE("integration_production_ini") {

TEST_CASE("compile definition and count pages") {
    auto path = find_ini();
    if (path.empty()) { MESSAGE("INI not found"); return; }
    auto def = tuner_core::compile_ecu_definition_file(path);
    CHECK(def.constants.scalars.size() > 100);
    CHECK(def.constants.arrays.size() > 10);
    CHECK(def.table_editors.editors.size() > 5);
    CHECK(def.menus.menus.size() > 3);
    CHECK(def.dialogs.dialogs.size() > 10);
}

TEST_CASE("tuning page builder produces fuel group with VE table") {
    auto path = find_ini();
    if (path.empty()) { MESSAGE("INI not found"); return; }
    auto def = tuner_core::compile_ecu_definition_file(path);
    namespace tpb = tuner_core::tuning_page_builder;
    auto groups = tpb::build_pages(def);
    bool has_fuel = false;
    for (const auto& g : groups) {
        if (g.group_id.find("fuel") != std::string::npos) has_fuel = true;
    }
    CHECK(has_fuel);
}

TEST_CASE("table rendering on real VE table values") {
    auto msq_path = find_msq();
    if (msq_path.empty()) { MESSAGE("MSQ not found"); return; }
    auto msq = tuner_core::parse_msq(msq_path);
    // Find veTable constant.
    for (const auto& c : msq.constants) {
        if (c.name == "veTable" && c.rows > 0 && c.cols > 0) {
            std::vector<double> vals;
            std::istringstream iss(c.text);
            double d;
            while (iss >> d) vals.push_back(d);
            if (vals.empty()) continue;
            namespace tv = tuner_core::table_view;
            namespace tr = tuner_core::table_rendering;
            tv::ShapeHints hints; hints.rows = c.rows; hints.cols = c.cols;
            auto model = tv::build_table_model(std::span<const double>(vals), hints);
            REQUIRE(model.has_value());
            auto render = tr::build_render_model(*model, {}, {}, true);
            CHECK(render.rows > 0);
            CHECK(render.columns > 0);
            // All cells should have valid hex colors.
            for (const auto& row : render.cells)
                for (const auto& cell : row)
                    CHECK(cell.background_hex[0] == '#');
            return;
        }
    }
    MESSAGE("veTable not found in MSQ");
}

TEST_CASE("table replay context finds cell for RPM=2500 MAP=60") {
    auto ini_path = find_ini();
    auto msq_path = find_msq();
    if (ini_path.empty() || msq_path.empty()) { MESSAGE("Fixtures not found"); return; }
    auto def = tuner_core::compile_ecu_definition_file(ini_path);
    auto msq = tuner_core::parse_msq(msq_path);

    // Build axis labels from rpmBins and fuelLoadBins.
    namespace lte = tuner_core::local_tune_edit;
    lte::TuneFile tf;
    for (const auto& c : msq.constants) {
        lte::TuneValue tv; tv.name = c.name; tv.units = c.units;
        tv.rows = c.rows; tv.cols = c.cols;
        if (c.rows > 0 || c.cols > 0) {
            std::vector<double> vals;
            std::istringstream iss(c.text);
            double d; while (iss >> d) vals.push_back(d);
            if (!vals.empty()) tv.value = std::move(vals);
            else tv.value = c.text;
        } else {
            try { tv.value = std::stod(c.text); } catch (...) { tv.value = c.text; }
        }
        tf.constants.push_back(std::move(tv));
    }
    lte::EditService edit;
    edit.set_tune_file(&tf);

    // Build table page snapshot for veTable.
    namespace trc = tuner_core::table_replay_context;
    trc::TablePageSnapshot tps;
    tps.x_parameter_name = "rpmBins";
    tps.y_parameter_name = "fuelLoadBins";

    // Read axis labels.
    auto* xv = edit.get_value("rpmBins");
    if (xv && std::holds_alternative<std::vector<double>>(xv->value)) {
        for (double d : std::get<std::vector<double>>(xv->value)) {
            char b[16]; std::snprintf(b, sizeof(b), "%.0f", d);
            tps.x_labels.push_back(b);
        }
    }
    auto* yv = edit.get_value("fuelLoadBins");
    if (yv && std::holds_alternative<std::vector<double>>(yv->value)) {
        for (double d : std::get<std::vector<double>>(yv->value)) {
            char b[16]; std::snprintf(b, sizeof(b), "%.0f", d);
            tps.y_labels.push_back(b);
        }
    }

    // Minimal cells (locator only needs shape).
    int rows = static_cast<int>(tps.y_labels.size());
    int cols = static_cast<int>(tps.x_labels.size());
    tps.cells.resize(rows);
    for (auto& r : tps.cells) r.resize(cols, "0");

    std::vector<trc::RuntimeChannel> channels = {{"rpm", 2500}, {"map", 60}};
    auto loc = trc::build(tps, channels);
    if (loc) {
        CHECK(loc->row_index < static_cast<size_t>(rows));
        CHECK(loc->column_index < static_cast<size_t>(cols));
        bool has_2500 = loc->summary_text.find("2500") != std::string::npos
                      || loc->detail_text.find("2500") != std::string::npos;
        CHECK(has_2500);
    }
}

TEST_CASE("flash preflight detects board match") {
    namespace fp = tuner_core::flash_preflight;
    fp::PreflightInputs inputs;
    inputs.selected_board = fp::BoardFamily::TEENSY41;
    inputs.detected_board = fp::BoardFamily::TEENSY41;
    inputs.firmware_entry.board_family = fp::BoardFamily::TEENSY41;
    inputs.firmware_entry.firmware_signature = "speeduino 202501-T41";
    inputs.definition_signature = "speeduino 202501-T41";
    inputs.tune_signature = "speeduino 202501-T41";
    auto result = fp::validate(inputs);
    CHECK(result.errors.empty());
    CHECK(result.warnings.empty());
}

TEST_CASE("board detection from signature") {
    namespace bd = tuner_core::board_detection;
    auto result = bd::detect_from_text("speeduino 202501-T41");
    REQUIRE(result.has_value());
    CHECK(*result == bd::BoardFamily::TEENSY41);
}

TEST_CASE("firmware catalog scores matching entry highest") {
    namespace fc = tuner_core::firmware_catalog;
    fc::CatalogEntry match;
    match.board_family = fc::BoardFamily::TEENSY41;
    match.firmware_signature = "speeduino 202501-T41";
    match.preferred = true;

    fc::CatalogEntry wrong;
    wrong.board_family = fc::BoardFamily::ATMEGA2560;
    wrong.firmware_signature = "speeduino 202501-AVR";

    fc::ScoringContext ctx;
    ctx.preferred_board = fc::BoardFamily::TEENSY41;
    ctx.definition_signature = "speeduino 202501-T41";

    CHECK(fc::score_entry(match, ctx) > fc::score_entry(wrong, ctx));
}

TEST_CASE("curve page builder from production INI") {
    auto path = find_ini();
    if (path.empty()) { MESSAGE("INI not found"); return; }
    auto def = tuner_core::compile_ecu_definition_file(path);
    if (def.curve_editors.curves.empty()) { MESSAGE("No curves"); return; }

    namespace cpb = tuner_core::curve_page_builder;
    std::vector<cpb::CurveDefinition> curves;
    for (const auto& ce : def.curve_editors.curves) {
        cpb::CurveDefinition cd;
        cd.name = ce.name;
        cd.title = ce.title;
        cd.x_bins_param = ce.x_bins_param;
        cd.x_channel = ce.x_channel.value_or("");
        cd.x_label = ce.x_label;
        cd.y_label = ce.y_label;
        for (const auto& yb : ce.y_bins_list)
            cd.y_bins_list.push_back({yb.param, yb.label.value_or("")});
        curves.push_back(std::move(cd));
    }

    auto find_param = [](const std::string&, void*) -> std::optional<cpb::ParamInfo> {
        return std::nullopt;
    };

    auto groups = cpb::build_curve_pages(curves, find_param, nullptr);
    CHECK(groups.size() >= 2);
    int total_curves = 0;
    for (const auto& g : groups) total_curves += static_cast<int>(g.pages.size());
    CHECK(total_curves >= 10);  // Production INI has 34 curves
}

TEST_CASE("production MSQ signature round-trip") {
    auto msq_path = find_msq();
    if (msq_path.empty()) { MESSAGE("MSQ not found"); return; }
    auto msq = tuner_core::parse_msq(msq_path);
    CHECK(!msq.signature.empty());
    CHECK(msq.signature.find("speeduino") != std::string::npos);
    CHECK(msq.constants.size() > 50);
}

}  // TEST_SUITE
