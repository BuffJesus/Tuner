// SPDX-License-Identifier: MIT
//
// End-to-end pipeline tests that chain multiple services together —
// the kind of integration that validates the seams work as a whole.

#include <doctest.h>
#include "tuner_core/ve_analyze_accumulator.hpp"
#include "tuner_core/ve_cell_hit_accumulator.hpp"
#include "tuner_core/ve_proposal_smoothing.hpp"
#include "tuner_core/ve_root_cause_diagnostics.hpp"
#include "tuner_core/ve_analyze_review.hpp"
#include "tuner_core/wue_analyze_accumulator.hpp"
#include "tuner_core/wue_analyze_review.hpp"
#include "tuner_core/mock_ecu_runtime.hpp"
#include "tuner_core/datalog_import.hpp"
#include "tuner_core/datalog_replay.hpp"
#include "tuner_core/datalog_profile.hpp"
#include "tuner_core/live_analyze_session.hpp"
#include "tuner_core/sensor_setup_checklist.hpp"
#include "tuner_core/ignition_trigger_cross_validation.hpp"
#include "tuner_core/operator_engine_context.hpp"
#include "tuner_core/hardware_setup_generator_context.hpp"
#include "tuner_core/required_fuel_calculator.hpp"
#include "tuner_core/ve_table_generator.hpp"
#include "tuner_core/afr_target_generator.hpp"
#include "tuner_core/spark_table_generator.hpp"
#include "tuner_core/idle_rpm_generator.hpp"
#include "tuner_core/startup_enrichment_generator.hpp"
#include "tuner_core/thermistor_calibration.hpp"
#include "tuner_core/trigger_log_analysis.hpp"
#include "tuner_core/trigger_log_visualization.hpp"
#include "tuner_core/table_rendering.hpp"
#include "tuner_core/table_view.hpp"
#include "tuner_core/firmware_catalog.hpp"

#include <span>

TEST_SUITE("integration_pipeline") {

TEST_CASE("full VE pipeline: accumulate → smooth → diagnose → review") {
    namespace vaa = tuner_core::ve_analyze_accumulator;
    namespace vps = tuner_core::ve_proposal_smoothing;
    namespace rcd = tuner_core::ve_root_cause_diagnostics;
    namespace var = tuner_core::ve_analyze_review;

    vaa::TableSnapshot table;
    table.x_param_name = "rpmBins";
    table.y_param_name = "mapBins";
    table.x_labels = {"1000", "2000", "3000", "4000"};
    table.y_labels = {"30", "50", "70", "100"};
    table.cells.resize(4);
    for (int r = 0; r < 4; ++r) {
        table.cells[r].resize(4);
        for (int c = 0; c < 4; ++c)
            table.cells[r][c] = std::to_string(70 + r * 5 + c * 2);
    }

    vaa::Accumulator acc;
    // Steady cruise: slightly lean.
    for (int i = 0; i < 20; ++i) {
        vaa::Record rec;
        rec.values = {{"rpm", 2500}, {"map", 60}, {"lambda1", 1.06}};
        rec.timestamp_seconds = 100.0 + i;
        acc.add_record(rec, table);
    }
    // WOT: richer.
    for (int i = 0; i < 10; ++i) {
        vaa::Record rec;
        rec.values = {{"rpm", 3800}, {"map", 95}, {"lambda1", 0.92}};
        rec.timestamp_seconds = 200.0 + i;
        acc.add_record(rec, table);
    }

    auto snap = acc.snapshot(table, 3, 0, 200);
    CHECK(snap.proposals.size() >= 2);

    auto smoothed = vps::smooth(snap.proposals, {});
    CHECK(smoothed.smoothed_count + smoothed.unchanged_count
          == static_cast<int>(snap.proposals.size()));

    auto diag = rcd::diagnose(snap.proposals);
    // Not enough cells for root-cause patterns, but should not crash.
    CHECK(diag.summary_text.find("Root-cause") != std::string::npos);

    auto review = var::build(snap, {}, &smoothed, &diag);
    CHECK(review.summary_text.find("VE Analyze") != std::string::npos);
    CHECK(!review.detail_text.empty());
}

TEST_CASE("full WUE pipeline: accumulate → review") {
    namespace waa = tuner_core::wue_analyze_accumulator;
    namespace war = tuner_core::wue_analyze_review;

    waa::TableAxis axis;
    axis.bins = {-20, 0, 20, 40, 60, 80};
    axis.along_y = true;
    std::vector<std::string> cells = {"180", "160", "140", "120", "110", "100"};

    waa::Accumulator acc;
    for (int i = 0; i < 15; ++i) {
        waa::Record rec;
        rec.values = {{"lambda1", 1.08}, {"coolant", 15.0}};
        acc.add_record(rec, axis, cells);
    }
    auto snap = acc.snapshot(cells, 3);
    CHECK(snap.proposals.size() >= 1);

    auto review = war::build(snap);
    CHECK(review.summary_text.find("WUE") != std::string::npos);
}

TEST_CASE("mock ECU generates 100 frames without crash") {
    tuner_core::mock_ecu_runtime::MockEcu ecu;
    for (int i = 0; i < 100; ++i) {
        auto snap = ecu.poll();
        CHECK(snap.channels.size() == 12);
    }
}

TEST_CASE("datalog import → replay → profile pipeline") {
    namespace di = tuner_core::datalog_import;
    namespace dr = tuner_core::datalog_replay;
    namespace dp = tuner_core::datalog_profile;

    std::vector<std::string> headers = {"Time_ms", "rpm", "map", "afr"};
    std::vector<di::CsvRow> rows;
    for (int i = 0; i < 20; ++i) {
        rows.push_back({
            {"Time_ms", std::to_string(i * 100)},
            {"rpm", std::to_string(800 + i * 100)},
            {"map", std::to_string(30 + i * 3)},
            {"afr", std::to_string(14.7 - i * 0.05)},
        });
    }
    auto imported = di::import_rows(headers, rows, "test.csv");
    CHECK(imported.row_count == 20);

    // Convert to replay format.
    std::vector<dr::Record> replay_recs;
    for (const auto& rec : imported.records) {
        dr::Record r;
        char ts[32]; std::snprintf(ts, sizeof(ts), "T+%.3fs", rec.timestamp_seconds);
        r.timestamp_iso = ts;
        for (const auto& [k, v] : rec.values)
            r.values.push_back({k, v});
        replay_recs.push_back(r);
    }
    auto sel = dr::select_row(replay_recs, 10);
    CHECK(sel.selected_index == 10);

    // Profile ordering.
    std::vector<dp::ChannelDef> defs = {
        {"afr", "AFR", "", 2}, {"rpm", "RPM", "RPM", 0}, {"map", "MAP", "kPa", 0},
    };
    auto profile = dp::default_profile(defs);
    CHECK(profile.channels[0].name == "rpm");  // highest priority
}

TEST_CASE("all 5 generator services produce valid output") {
    namespace vg = tuner_core::ve_table_generator;
    namespace ag = tuner_core::afr_target_generator;
    namespace sg = tuner_core::spark_table_generator;
    namespace ig = tuner_core::idle_rpm_generator;
    namespace seg = tuner_core::startup_enrichment_generator;

    vg::VeGeneratorContext ve_ctx;
    ve_ctx.displacement_cc = 2000; ve_ctx.cylinder_count = 4;
    auto ve = vg::generate(ve_ctx);
    CHECK(ve.values.size() == 256);

    ag::AfrGeneratorContext afr_ctx;
    auto afr = ag::generate(afr_ctx, ag::CalibrationIntent::FIRST_START);
    CHECK(afr.values.size() == 256);

    sg::SparkGeneratorContext spark_ctx;
    spark_ctx.compression_ratio = 10.0;
    auto spark = sg::generate(spark_ctx, sg::CalibrationIntent::FIRST_START);
    CHECK(spark.values.size() == 256);

    ig::GeneratorContext idle_ctx;
    auto idle = ig::generate(idle_ctx, ig::CalibrationIntent::FIRST_START);
    CHECK(idle.clt_bins.size() == 10);
    CHECK(idle.rpm_targets.size() == 10);

    seg::StartupContext wue_ctx;
    auto wue = seg::generate_wue(wue_ctx, seg::CalibrationIntent::FIRST_START);
    CHECK(wue.clt_bins.size() == 10);
    CHECK(wue.enrichment_pct.size() == 10);
}

TEST_CASE("thermistor calibration all 15 presets valid") {
    namespace tc = tuner_core::thermistor_calibration;
    auto presets = tc::presets();
    CHECK(presets.size() == 15);
    for (const auto& p : presets) {
        auto cal = tc::generate(p, tc::Sensor::CLT);
        CHECK(cal.temperatures_c.size() == 32);
        CHECK(cal.encode_payload().size() == 64);
    }
}

TEST_CASE("trigger analysis + visualization on synthetic 36-1") {
    namespace tla = tuner_core::trigger_log_analysis;
    namespace tlv = tuner_core::trigger_log_visualization;

    // Build 36-1 pattern.
    std::vector<tla::Row> analysis_rows;
    std::vector<tlv::Row> viz_rows;
    double t = 0;
    for (int rev = 0; rev < 2; ++rev) {
        for (int tooth = 0; tooth < 36; ++tooth) {
            tla::Row ar; ar.fields = {{"Time", std::to_string(t)}, {"tooth", "1"}};
            tlv::Row vr; vr.fields = {{"Time", std::to_string(t)}, {"tooth", std::to_string(tooth < 35 ? 1 : 0)}};
            analysis_rows.push_back(ar);
            viz_rows.push_back(vr);
            t += (tooth == 35) ? 2.0 : 1.0;
        }
    }

    auto decoder = tla::build_decoder_context(
        [](const std::string& name) -> std::optional<double> {
            if (name == "TrigPattern") return 0;
            if (name == "nTeeth") return 36;
            if (name == "missingTeeth") return 1;
            return std::nullopt;
        });
    CHECK(decoder.decoder_name == "Missing Tooth");

    auto analysis = tla::analyze_rows(analysis_rows, {"Time", "tooth"}, decoder);
    CHECK(analysis.sample_count == 72);

    auto viz = tlv::build_from_rows(viz_rows, {"Time", "tooth"});
    CHECK(viz.trace_count == 1);
}

TEST_CASE("table rendering 16x16 gradient completeness") {
    std::vector<double> values(256);
    for (int i = 0; i < 256; ++i) values[i] = static_cast<double>(i) / 2.55;
    namespace tv = tuner_core::table_view;
    namespace tr = tuner_core::table_rendering;
    tv::ShapeHints hints; hints.rows = 16; hints.cols = 16;
    auto model = tv::build_table_model(std::span<const double>(values), hints);
    REQUIRE(model.has_value());
    auto render = tr::build_render_model(*model, {}, {}, true);
    CHECK(render.rows == 16);
    CHECK(render.columns == 16);
    // Every cell should have a 7-char hex color like "#8aa8ff".
    for (const auto& row : render.cells)
        for (const auto& cell : row) {
            CHECK(cell.background_hex.size() == 7);
            CHECK(cell.foreground_hex.size() == 7);
        }
}

}  // TEST_SUITE
