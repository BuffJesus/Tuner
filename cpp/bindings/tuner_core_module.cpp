// SPDX-License-Identifier: MIT
//
// nanobind module exposing tuner_core::MsqParser to Python.
//
// Built as `tuner_core` and importable from Python as
// `tuner._native.tuner_core` once installed via the wheel built by
// cibuildwheel. The Python parity test gates on this import being
// available so a developer install without a compiler still works.

#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/filesystem.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/unordered_map.h>
#include <nanobind/stl/variant.h>
#include <nanobind/stl/vector.h>

#include "tuner_core/ini_constants_parser.hpp"
#include "tuner_core/ini_curve_editor_parser.hpp"
#include "tuner_core/ini_defines_parser.hpp"
#include "tuner_core/ini_menu_parser.hpp"
#include "tuner_core/ecu_definition_compiler.hpp"
#include "tuner_core/speeduino_framing.hpp"
#include "tuner_core/speeduino_protocol.hpp"
#include "tuner_core/speeduino_live_data_decoder.hpp"
#include "tuner_core/speeduino_param_codec.hpp"
#include "tuner_core/speeduino_value_codec.hpp"
#include "tuner_core/autotune_filter_gate_evaluator.hpp"
#include "tuner_core/board_detection.hpp"
#include "tuner_core/evidence_replay_comparison.hpp"
#include "tuner_core/gauge_color_zones.hpp"
#include "tuner_core/hardware_setup_validation.hpp"
#include "tuner_core/live_data_map_parser.hpp"
#include "tuner_core/pressure_sensor_calibration.hpp"
#include "tuner_core/release_manifest.hpp"
#include "tuner_core/required_fuel_calculator.hpp"
#include "tuner_core/sample_gate_helpers.hpp"
#include "tuner_core/staged_change.hpp"
#include "tuner_core/sync_state.hpp"
#include "tuner_core/table_edit.hpp"
#include "tuner_core/table_view.hpp"
#include "tuner_core/tune_value_preview.hpp"
#include "tuner_core/tuning_page_diff.hpp"
#include "tuner_core/visibility_expression.hpp"
#include "tuner_core/math_expression_evaluator.hpp"
#include "tuner_core/flash_target_detection.hpp"
#include "tuner_core/wue_analyze_helpers.hpp"
#include "tuner_core/ini_controller_commands_parser.hpp"
#include "tuner_core/ini_front_page_parser.hpp"
#include "tuner_core/ini_gauge_configurations_parser.hpp"
#include "tuner_core/ini_logger_definition_parser.hpp"
#include "tuner_core/ini_output_channels_parser.hpp"
#include "tuner_core/live_trigger_logger.hpp"
#include "tuner_core/live_capture_session.hpp"
#include "tuner_core/firmware_flash_builder.hpp"
#include "tuner_core/legacy_project_file.hpp"
#include "tuner_core/protocol_simulator.hpp"
#include "tuner_core/speeduino_connect_strategy.hpp"
#include "tuner_core/ini_setting_groups_parser.hpp"
#include "tuner_core/ini_setting_context_help_parser.hpp"
#include "tuner_core/ini_constants_extensions_parser.hpp"
#include "tuner_core/ini_tools_parser.hpp"
#include "tuner_core/ini_reference_tables_parser.hpp"
#include "tuner_core/ini_pc_variables_parser.hpp"
#include "tuner_core/ini_preprocessor.hpp"
#include "tuner_core/ini_table_editor_parser.hpp"
#include "tuner_core/msq_parser.hpp"
#include "tuner_core/native_format.hpp"

namespace nb = nanobind;

NB_MODULE(tuner_core, m) {
    m.doc() = "tuner_core — native C++ MSQ parser bindings (Phase 13 first slice)";

    nb::class_<tuner_core::MsqConstant>(m, "MsqConstant")
        .def_rw("name", &tuner_core::MsqConstant::name)
        .def_rw("text", &tuner_core::MsqConstant::text)
        .def_rw("units", &tuner_core::MsqConstant::units)
        .def_rw("rows", &tuner_core::MsqConstant::rows)
        .def_rw("cols", &tuner_core::MsqConstant::cols)
        .def_rw("digits", &tuner_core::MsqConstant::digits);

    nb::class_<tuner_core::MsqDocument>(m, "MsqDocument")
        .def_rw("signature", &tuner_core::MsqDocument::signature)
        .def_rw("file_format", &tuner_core::MsqDocument::file_format)
        .def_rw("page_count", &tuner_core::MsqDocument::page_count)
        .def_rw("constants", &tuner_core::MsqDocument::constants);

    m.def(
        "parse_msq",
        [](const std::filesystem::path& path) {
            return tuner_core::parse_msq(path);
        },
        nb::arg("path"),
        "Parse an MSQ XML file into an MsqDocument.");

    m.def(
        "parse_msq_text",
        [](const std::string& xml) {
            return tuner_core::parse_msq_text(xml);
        },
        nb::arg("xml"),
        "Parse an MSQ XML string into an MsqDocument.");

    m.def(
        "write_msq",
        [](const std::filesystem::path& source,
           const std::filesystem::path& destination,
           const std::map<std::string, std::string>& updates) {
            return tuner_core::write_msq(source, destination, updates);
        },
        nb::arg("source"),
        nb::arg("destination"),
        nb::arg("updates"),
        "Update an MSQ XML file by replacing inner-text for the named "
        "constants. Mirrors MsqWriteService.save(insert_missing=False) — "
        "names not present in the source XML are silently dropped. "
        "Returns the count of constants that matched.");

    m.def(
        "write_msq_text",
        [](const std::string& source_xml,
           const std::map<std::string, std::string>& updates) {
            return tuner_core::write_msq_text(source_xml, updates);
        },
        nb::arg("source_xml"),
        nb::arg("updates"),
        "In-memory variant of write_msq for tests and parity harnesses.");

    nb::class_<tuner_core::MsqInsertion>(m, "MsqInsertion")
        .def(nb::init<>())
        .def_rw("name",   &tuner_core::MsqInsertion::name)
        .def_rw("text",   &tuner_core::MsqInsertion::text)
        .def_rw("units",  &tuner_core::MsqInsertion::units)
        .def_rw("rows",   &tuner_core::MsqInsertion::rows)
        .def_rw("cols",   &tuner_core::MsqInsertion::cols)
        .def_rw("digits", &tuner_core::MsqInsertion::digits);

    m.def(
        "format_msq_scalar",
        [](double value) { return tuner_core::format_msq_scalar(value); },
        nb::arg("value"),
        "Render a scalar with Python `MsqWriteService._fmt_scalar` "
        "semantics: integers lose their decimal, non-integer floats "
        "strip trailing zeros.");

    m.def(
        "format_msq_table",
        [](const std::vector<double>& values, int rows, int cols) {
            return tuner_core::format_msq_table(values, rows, cols);
        },
        nb::arg("values"), nb::arg("rows"), nb::arg("cols"),
        "Render a flat row-major table as the multi-line inner text "
        "Python `MsqWriteService._format_value` produces.");

    m.def(
        "write_msq_text_with_insertions",
        [](const std::string& source_xml,
           const std::map<std::string, std::string>& updates,
           const std::vector<tuner_core::MsqInsertion>& insertions) {
            return tuner_core::write_msq_text_with_insertions(
                source_xml, updates, insertions);
        },
        nb::arg("source_xml"),
        nb::arg("updates"),
        nb::arg("insertions"),
        "Update existing <constant> inner text and inject any "
        "insertions whose name is absent from the source document. "
        "Mirrors MsqWriteService.save(insert_missing=True).");

    // -----------------------------------------------------------------
    // NativeFormat (Future Phase 12 v1)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::NativeParameter>(m, "NativeParameter")
        .def(nb::init<>())
        .def_rw("semantic_id", &tuner_core::NativeParameter::semantic_id)
        .def_rw("legacy_name", &tuner_core::NativeParameter::legacy_name)
        .def_rw("label", &tuner_core::NativeParameter::label)
        .def_rw("units", &tuner_core::NativeParameter::units)
        .def_rw("kind", &tuner_core::NativeParameter::kind)
        .def_rw("min_value", &tuner_core::NativeParameter::min_value)
        .def_rw("max_value", &tuner_core::NativeParameter::max_value)
        .def_rw("default_value", &tuner_core::NativeParameter::default_value);

    nb::class_<tuner_core::NativeAxis>(m, "NativeAxis")
        .def(nb::init<>())
        .def_rw("semantic_id", &tuner_core::NativeAxis::semantic_id)
        .def_rw("legacy_name", &tuner_core::NativeAxis::legacy_name)
        .def_rw("length", &tuner_core::NativeAxis::length)
        .def_rw("units", &tuner_core::NativeAxis::units);

    nb::class_<tuner_core::NativeTable>(m, "NativeTable")
        .def(nb::init<>())
        .def_rw("semantic_id", &tuner_core::NativeTable::semantic_id)
        .def_rw("legacy_name", &tuner_core::NativeTable::legacy_name)
        .def_rw("rows", &tuner_core::NativeTable::rows)
        .def_rw("columns", &tuner_core::NativeTable::columns)
        .def_rw("label", &tuner_core::NativeTable::label)
        .def_rw("units", &tuner_core::NativeTable::units)
        .def_rw("x_axis_id", &tuner_core::NativeTable::x_axis_id)
        .def_rw("y_axis_id", &tuner_core::NativeTable::y_axis_id);

    nb::class_<tuner_core::NativeCurve>(m, "NativeCurve")
        .def(nb::init<>())
        .def_rw("semantic_id", &tuner_core::NativeCurve::semantic_id)
        .def_rw("legacy_name", &tuner_core::NativeCurve::legacy_name)
        .def_rw("point_count", &tuner_core::NativeCurve::point_count)
        .def_rw("label", &tuner_core::NativeCurve::label)
        .def_rw("units", &tuner_core::NativeCurve::units)
        .def_rw("x_axis_id", &tuner_core::NativeCurve::x_axis_id);

    nb::class_<tuner_core::NativeDefinition>(m, "NativeDefinition")
        .def(nb::init<>())
        .def_rw("schema_version", &tuner_core::NativeDefinition::schema_version)
        .def_rw("name", &tuner_core::NativeDefinition::name)
        .def_rw("firmware_signature", &tuner_core::NativeDefinition::firmware_signature)
        .def_rw("parameters", &tuner_core::NativeDefinition::parameters)
        .def_rw("axes", &tuner_core::NativeDefinition::axes)
        .def_rw("tables", &tuner_core::NativeDefinition::tables)
        .def_rw("curves", &tuner_core::NativeDefinition::curves);

    nb::class_<tuner_core::NativeTune>(m, "NativeTune")
        .def(nb::init<>())
        .def_rw("schema_version", &tuner_core::NativeTune::schema_version)
        .def_rw("definition_signature", &tuner_core::NativeTune::definition_signature)
        .def_rw("values", &tuner_core::NativeTune::values);

    m.def(
        "dump_definition",
        &tuner_core::dump_definition,
        nb::arg("definition"),
        nb::arg("indent") = 2,
        "Serialize a NativeDefinition to JSON. Matches the Python "
        "NativeFormatService.dump_definition() byte-for-byte.");

    m.def(
        "dump_tune",
        &tuner_core::dump_tune,
        nb::arg("tune"),
        nb::arg("indent") = 2,
        "Serialize a NativeTune to JSON.");

    m.def(
        "load_definition",
        [](const std::string& text) {
            return tuner_core::load_definition(text);
        },
        nb::arg("text"),
        "Parse a NativeDefinition from JSON. Raises ValueError on bad "
        "JSON or unsupported schema_version.");

    m.def(
        "load_tune",
        [](const std::string& text) {
            return tuner_core::load_tune(text);
        },
        nb::arg("text"),
        "Parse a NativeTune from JSON.");

    m.def(
        "load_definition_file",
        [](const std::filesystem::path& path) {
            return tuner_core::load_definition_file(path);
        },
        nb::arg("path"));

    m.def(
        "load_tune_file",
        [](const std::filesystem::path& path) {
            return tuner_core::load_tune_file(path);
        },
        nb::arg("path"));

    // -----------------------------------------------------------------
    // INI preprocessor (Phase 13 third slice)
    // -----------------------------------------------------------------

    m.def(
        "preprocess_ini_lines",
        [](const std::vector<std::string>& raw_lines,
           const std::set<std::string>& active_settings) {
            return tuner_core::preprocess_ini_lines(raw_lines, active_settings);
        },
        nb::arg("raw_lines"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Evaluate #if/#else/#endif/#set/#unset directives. Returns "
        "the lines belonging to active conditional branches. Matches "
        "tuner.parsers.common.preprocess_ini_lines() byte-for-byte.");

    m.def(
        "preprocess_ini_text",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::preprocess_ini_text(text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Convenience overload that splits a single source string on "
        "newlines (\\r\\n / \\r / \\n normalized) and forwards to "
        "preprocess_ini_lines.");

    // -----------------------------------------------------------------
    // INI [Constants] section parser (Phase 13 fourth slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniScalar>(m, "IniScalar")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniScalar::name)
        .def_rw("data_type", &tuner_core::IniScalar::data_type)
        .def_rw("units", &tuner_core::IniScalar::units)
        .def_rw("page", &tuner_core::IniScalar::page)
        .def_rw("offset", &tuner_core::IniScalar::offset)
        .def_rw("scale", &tuner_core::IniScalar::scale)
        .def_rw("translate", &tuner_core::IniScalar::translate)
        .def_rw("digits", &tuner_core::IniScalar::digits)
        .def_rw("min_value", &tuner_core::IniScalar::min_value)
        .def_rw("max_value", &tuner_core::IniScalar::max_value)
        .def_rw("options", &tuner_core::IniScalar::options)
        .def_rw("bit_offset", &tuner_core::IniScalar::bit_offset)
        .def_rw("bit_length", &tuner_core::IniScalar::bit_length);

    nb::class_<tuner_core::IniArray>(m, "IniArray")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniArray::name)
        .def_rw("data_type", &tuner_core::IniArray::data_type)
        .def_rw("rows", &tuner_core::IniArray::rows)
        .def_rw("columns", &tuner_core::IniArray::columns)
        .def_rw("units", &tuner_core::IniArray::units)
        .def_rw("page", &tuner_core::IniArray::page)
        .def_rw("offset", &tuner_core::IniArray::offset)
        .def_rw("scale", &tuner_core::IniArray::scale)
        .def_rw("translate", &tuner_core::IniArray::translate)
        .def_rw("digits", &tuner_core::IniArray::digits)
        .def_rw("min_value", &tuner_core::IniArray::min_value)
        .def_rw("max_value", &tuner_core::IniArray::max_value);

    nb::class_<tuner_core::IniConstantsSection>(m, "IniConstantsSection")
        .def(nb::init<>())
        .def_rw("scalars", &tuner_core::IniConstantsSection::scalars)
        .def_rw("arrays", &tuner_core::IniConstantsSection::arrays);

    m.def(
        "parse_constants_section",
        [](const std::string& text,
           const tuner_core::IniDefines& defines) {
            return tuner_core::parse_constants_section(text, defines);
        },
        nb::arg("text"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Parse the [Constants] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_constant_definitions byte-for-byte for "
        "scalar/array/bits entries; lastOffset auto-advance and page "
        "tracking are supported. String entries and {expression} scale "
        "placeholders are partially supported (matches Python). The "
        "optional `defines` map enables `$macroName` expansion in "
        "bit-option labels (Phase 13 fifth slice composition).");

    m.def(
        "parse_constants_lines",
        [](const std::vector<std::string>& lines,
           const tuner_core::IniDefines& defines) {
            return tuner_core::parse_constants_lines(lines, defines);
        },
        nb::arg("lines"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Convenience overload accepting a list[str] instead of a single "
        "source string. The optional `defines` map enables bit-option "
        "label expansion.");

    m.def(
        "parse_constants_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_constants_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: run preprocess_ini_text with the given "
        "active_settings, collect #define macros, then parse the "
        "[Constants] section with the defines wired in for bit-option "
        "expansion. Mirrors the Python IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [Defines] / #define macro collector (Phase 13 fifth slice)
    // -----------------------------------------------------------------

    m.def(
        "collect_defines",
        [](const std::string& text) {
            return tuner_core::collect_defines(text);
        },
        nb::arg("text"),
        "Walk an INI document collecting every #define name = ... line "
        "into a name → list-of-tokens map. Mirrors "
        "IniParser._collect_defines.");

    m.def(
        "expand_options",
        &tuner_core::expand_options,
        nb::arg("parts"),
        nb::arg("defines"),
        "Recursively expand $macroName references in an option list "
        "against a defines map. Drops {expression} placeholders and "
        "unresolved references. Caps recursion at 10 levels. Mirrors "
        "IniParser._expand_options.");

    // -----------------------------------------------------------------
    // INI [OutputChannels] section parser (Phase 14 first slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniOutputChannel>(m, "IniOutputChannel")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniOutputChannel::name)
        .def_rw("data_type", &tuner_core::IniOutputChannel::data_type)
        .def_rw("offset", &tuner_core::IniOutputChannel::offset)
        .def_rw("units", &tuner_core::IniOutputChannel::units)
        .def_rw("scale", &tuner_core::IniOutputChannel::scale)
        .def_rw("translate", &tuner_core::IniOutputChannel::translate)
        .def_rw("min_value", &tuner_core::IniOutputChannel::min_value)
        .def_rw("max_value", &tuner_core::IniOutputChannel::max_value)
        .def_rw("digits", &tuner_core::IniOutputChannel::digits)
        .def_rw("bit_offset", &tuner_core::IniOutputChannel::bit_offset)
        .def_rw("bit_length", &tuner_core::IniOutputChannel::bit_length)
        .def_rw("options", &tuner_core::IniOutputChannel::options);

    nb::class_<tuner_core::IniFormulaOutputChannel>(m, "IniFormulaOutputChannel")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniFormulaOutputChannel::name)
        .def_rw("formula_expression",
                &tuner_core::IniFormulaOutputChannel::formula_expression)
        .def_rw("units", &tuner_core::IniFormulaOutputChannel::units)
        .def_rw("digits", &tuner_core::IniFormulaOutputChannel::digits);

    nb::class_<tuner_core::IniOutputChannelsSection>(m, "IniOutputChannelsSection")
        .def(nb::init<>())
        .def_rw("channels", &tuner_core::IniOutputChannelsSection::channels)
        .def_rw("arrays", &tuner_core::IniOutputChannelsSection::arrays)
        .def_rw("formula_channels",
                &tuner_core::IniOutputChannelsSection::formula_channels);

    m.def(
        "parse_output_channels_section",
        [](const std::string& text, const tuner_core::IniDefines& defines) {
            return tuner_core::parse_output_channels_section(text, defines);
        },
        nb::arg("text"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Parse the [OutputChannels] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_output_channels byte-for-byte for "
        "scalar/bits/array entries; defaultValue lines populate the "
        "arrays map. Optional `defines` enables $macroName expansion "
        "in bit-field option labels.");

    m.def(
        "parse_output_channels_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_output_channels_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + collect defines + parse. "
        "Mirrors the Python IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [TableEditor] section parser (Phase 14 second parser slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniTableEditor>(m, "IniTableEditor")
        .def(nb::init<>())
        .def_rw("table_id", &tuner_core::IniTableEditor::table_id)
        .def_rw("map_id", &tuner_core::IniTableEditor::map_id)
        .def_rw("title", &tuner_core::IniTableEditor::title)
        .def_rw("page", &tuner_core::IniTableEditor::page)
        .def_rw("x_bins", &tuner_core::IniTableEditor::x_bins)
        .def_rw("y_bins", &tuner_core::IniTableEditor::y_bins)
        .def_rw("z_bins", &tuner_core::IniTableEditor::z_bins)
        .def_rw("x_channel", &tuner_core::IniTableEditor::x_channel)
        .def_rw("y_channel", &tuner_core::IniTableEditor::y_channel)
        .def_rw("x_label", &tuner_core::IniTableEditor::x_label)
        .def_rw("y_label", &tuner_core::IniTableEditor::y_label)
        .def_rw("topic_help", &tuner_core::IniTableEditor::topic_help)
        .def_rw("grid_height", &tuner_core::IniTableEditor::grid_height)
        .def_rw("grid_orient", &tuner_core::IniTableEditor::grid_orient)
        .def_rw("up_label", &tuner_core::IniTableEditor::up_label)
        .def_rw("down_label", &tuner_core::IniTableEditor::down_label);

    nb::class_<tuner_core::IniTableEditorSection>(m, "IniTableEditorSection")
        .def(nb::init<>())
        .def_rw("editors", &tuner_core::IniTableEditorSection::editors);

    m.def(
        "parse_table_editor_section",
        [](const std::string& text, const tuner_core::IniDefines& defines) {
            return tuner_core::parse_table_editor_section(text, defines);
        },
        nb::arg("text"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Parse the [TableEditor] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_table_editors byte-for-byte: stateful "
        "grammar where `table = ...` lines open new editors and "
        "subsequent key=value lines populate fields on the active "
        "editor. The defines map is currently unused but the parameter "
        "is present for signature consistency with other section parsers.");

    m.def(
        "parse_table_editor_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_table_editor_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + collect defines + parse. "
        "Mirrors the Python IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [CurveEditor] section parser (Phase 14 third parser slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::CurveYBins>(m, "CurveYBins")
        .def(nb::init<>())
        .def_rw("param", &tuner_core::CurveYBins::param)
        .def_rw("label", &tuner_core::CurveYBins::label);

    nb::class_<tuner_core::CurveAxisRange>(m, "CurveAxisRange")
        .def(nb::init<>())
        .def_rw("min", &tuner_core::CurveAxisRange::min)
        .def_rw("max", &tuner_core::CurveAxisRange::max)
        .def_rw("steps", &tuner_core::CurveAxisRange::steps);

    nb::class_<tuner_core::IniCurveEditor>(m, "IniCurveEditor")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniCurveEditor::name)
        .def_rw("title", &tuner_core::IniCurveEditor::title)
        .def_rw("x_bins_param", &tuner_core::IniCurveEditor::x_bins_param)
        .def_rw("x_channel", &tuner_core::IniCurveEditor::x_channel)
        .def_rw("y_bins_list", &tuner_core::IniCurveEditor::y_bins_list)
        .def_rw("x_label", &tuner_core::IniCurveEditor::x_label)
        .def_rw("y_label", &tuner_core::IniCurveEditor::y_label)
        .def_rw("x_axis", &tuner_core::IniCurveEditor::x_axis)
        .def_rw("y_axis", &tuner_core::IniCurveEditor::y_axis)
        .def_rw("topic_help", &tuner_core::IniCurveEditor::topic_help)
        .def_rw("gauge", &tuner_core::IniCurveEditor::gauge)
        .def_rw("size", &tuner_core::IniCurveEditor::size);

    nb::class_<tuner_core::IniCurveEditorSection>(m, "IniCurveEditorSection")
        .def(nb::init<>())
        .def_rw("curves", &tuner_core::IniCurveEditorSection::curves);

    m.def(
        "parse_curve_editor_section",
        [](const std::string& text, const tuner_core::IniDefines& defines) {
            return tuner_core::parse_curve_editor_section(text, defines);
        },
        nb::arg("text"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Parse the [CurveEditor] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_curve_editors byte-for-byte: stateful "
        "grammar where `curve = ...` lines open new curves and "
        "subsequent key=value lines populate fields. Multi-line curves "
        "accumulate yBins entries; lineLabel entries are matched onto "
        "y_bins positionally at flush time. The defines map is "
        "currently unused but the parameter is present for signature "
        "consistency with other section parsers.");

    m.def(
        "parse_curve_editor_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_curve_editor_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + collect defines + parse. "
        "Mirrors the Python IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [Menu] section parser (Phase 14 fifth parser slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniMenuItem>(m, "IniMenuItem")
        .def(nb::init<>())
        .def_rw("target", &tuner_core::IniMenuItem::target)
        .def_rw("label", &tuner_core::IniMenuItem::label)
        .def_rw("page", &tuner_core::IniMenuItem::page)
        .def_rw("visibility_expression", &tuner_core::IniMenuItem::visibility_expression);

    nb::class_<tuner_core::IniMenu>(m, "IniMenu")
        .def(nb::init<>())
        .def_rw("title", &tuner_core::IniMenu::title)
        .def_rw("items", &tuner_core::IniMenu::items);

    nb::class_<tuner_core::IniMenuSection>(m, "IniMenuSection")
        .def(nb::init<>())
        .def_rw("menus", &tuner_core::IniMenuSection::menus);

    m.def(
        "parse_menu_section",
        [](const std::string& text, const tuner_core::IniDefines& defines) {
            return tuner_core::parse_menu_section(text, defines);
        },
        nb::arg("text"),
        nb::arg("defines") = tuner_core::IniDefines{},
        "Parse the [Menu] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_menus byte-for-byte: stateful "
        "grammar where `menu = ...` opens a new menu and subsequent "
        "subMenu/groupChildMenu lines populate items. std_separator "
        "items are dropped. Page number and visibility expression "
        "may appear in either order after the label.");

    m.def(
        "parse_menu_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_menu_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + collect defines + parse. "
        "Mirrors the Python IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [GaugeConfigurations] section parser (Phase 14 sixth slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniGaugeConfiguration>(m, "IniGaugeConfiguration")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniGaugeConfiguration::name)
        .def_rw("channel", &tuner_core::IniGaugeConfiguration::channel)
        .def_rw("title", &tuner_core::IniGaugeConfiguration::title)
        .def_rw("units", &tuner_core::IniGaugeConfiguration::units)
        .def_rw("lo", &tuner_core::IniGaugeConfiguration::lo)
        .def_rw("hi", &tuner_core::IniGaugeConfiguration::hi)
        .def_rw("lo_danger", &tuner_core::IniGaugeConfiguration::lo_danger)
        .def_rw("lo_warn", &tuner_core::IniGaugeConfiguration::lo_warn)
        .def_rw("hi_warn", &tuner_core::IniGaugeConfiguration::hi_warn)
        .def_rw("hi_danger", &tuner_core::IniGaugeConfiguration::hi_danger)
        .def_rw("value_digits", &tuner_core::IniGaugeConfiguration::value_digits)
        .def_rw("label_digits", &tuner_core::IniGaugeConfiguration::label_digits)
        .def_rw("category", &tuner_core::IniGaugeConfiguration::category);

    nb::class_<tuner_core::IniGaugeConfigurationsSection>(m, "IniGaugeConfigurationsSection")
        .def(nb::init<>())
        .def_rw("gauges", &tuner_core::IniGaugeConfigurationsSection::gauges);

    m.def(
        "parse_gauge_configurations_section",
        [](const std::string& text) {
            return tuner_core::parse_gauge_configurations_section(text);
        },
        nb::arg("text"),
        "Parse the [GaugeConfigurations] section out of (preprocessed) "
        "INI text. Mirrors IniParser._parse_gauge_configurations.");

    m.def(
        "parse_gauge_configurations_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_gauge_configurations_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + parse. Mirrors the Python "
        "IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [FrontPage] section parser (Phase 14 ninth slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniFrontPageIndicator>(m, "IniFrontPageIndicator")
        .def(nb::init<>())
        .def_rw("expression", &tuner_core::IniFrontPageIndicator::expression)
        .def_rw("off_label", &tuner_core::IniFrontPageIndicator::off_label)
        .def_rw("on_label", &tuner_core::IniFrontPageIndicator::on_label)
        .def_rw("off_bg", &tuner_core::IniFrontPageIndicator::off_bg)
        .def_rw("off_fg", &tuner_core::IniFrontPageIndicator::off_fg)
        .def_rw("on_bg", &tuner_core::IniFrontPageIndicator::on_bg)
        .def_rw("on_fg", &tuner_core::IniFrontPageIndicator::on_fg);

    nb::class_<tuner_core::IniFrontPageSection>(m, "IniFrontPageSection")
        .def(nb::init<>())
        .def_rw("gauges", &tuner_core::IniFrontPageSection::gauges)
        .def_rw("indicators", &tuner_core::IniFrontPageSection::indicators);

    m.def(
        "parse_front_page_section",
        [](const std::string& text) {
            return tuner_core::parse_front_page_section(text);
        },
        nb::arg("text"),
        "Parse the [FrontPage] section out of (preprocessed) INI text. "
        "Mirrors IniParser._parse_front_page.");

    m.def(
        "parse_front_page_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_front_page_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + parse. Mirrors the Python "
        "IniParser.parse() flow.");

    // -----------------------------------------------------------------
    // INI [LoggerDefinition] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniLoggerRecordField>(m, "IniLoggerRecordField")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniLoggerRecordField::name)
        .def_rw("header", &tuner_core::IniLoggerRecordField::header)
        .def_rw("start_bit", &tuner_core::IniLoggerRecordField::start_bit)
        .def_rw("bit_count", &tuner_core::IniLoggerRecordField::bit_count)
        .def_rw("scale", &tuner_core::IniLoggerRecordField::scale)
        .def_rw("units", &tuner_core::IniLoggerRecordField::units);

    nb::class_<tuner_core::IniLoggerDefinition>(m, "IniLoggerDefinition")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniLoggerDefinition::name)
        .def_rw("display_name", &tuner_core::IniLoggerDefinition::display_name)
        .def_rw("kind", &tuner_core::IniLoggerDefinition::kind)
        .def_rw("start_command", &tuner_core::IniLoggerDefinition::start_command)
        .def_rw("stop_command", &tuner_core::IniLoggerDefinition::stop_command)
        .def_rw("data_read_command", &tuner_core::IniLoggerDefinition::data_read_command)
        .def_rw("data_read_timeout_ms", &tuner_core::IniLoggerDefinition::data_read_timeout_ms)
        .def_rw("continuous_read", &tuner_core::IniLoggerDefinition::continuous_read)
        .def_rw("record_header_len", &tuner_core::IniLoggerDefinition::record_header_len)
        .def_rw("record_footer_len", &tuner_core::IniLoggerDefinition::record_footer_len)
        .def_rw("record_len", &tuner_core::IniLoggerDefinition::record_len)
        .def_rw("record_count", &tuner_core::IniLoggerDefinition::record_count)
        .def_rw("record_fields", &tuner_core::IniLoggerDefinition::record_fields);

    nb::class_<tuner_core::IniLoggerDefinitionSection>(m, "IniLoggerDefinitionSection")
        .def(nb::init<>())
        .def_rw("loggers", &tuner_core::IniLoggerDefinitionSection::loggers);

    m.def(
        "parse_logger_definition_section",
        [](const std::string& text) {
            return tuner_core::parse_logger_definition_section(text);
        },
        nb::arg("text"),
        "Parse the [LoggerDefinition] section. Mirrors "
        "IniParser._parse_logger_definitions.");

    m.def(
        "parse_logger_definition_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_logger_definition_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + parse.");

    // -----------------------------------------------------------------
    // INI [ControllerCommands] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniControllerCommand>(m, "IniControllerCommand")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::IniControllerCommand::name)
        .def_rw("payload", &tuner_core::IniControllerCommand::payload);

    nb::class_<tuner_core::IniControllerCommandsSection>(m, "IniControllerCommandsSection")
        .def(nb::init<>())
        .def_rw("commands", &tuner_core::IniControllerCommandsSection::commands);

    m.def(
        "parse_controller_commands_section",
        [](const std::string& text) {
            return tuner_core::parse_controller_commands_section(text);
        },
        nb::arg("text"),
        "Parse the [ControllerCommands] section. Mirrors "
        "IniParser._parse_controller_commands.");

    m.def(
        "parse_controller_commands_section_preprocessed",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::parse_controller_commands_section_preprocessed(
                text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Composed pipeline: preprocess + parse.");

    // -----------------------------------------------------------------
    // Live trigger logger — pure-logic decode of raw tooth/composite
    // log buffers. Mirrors `LiveTriggerLoggerService.decode`. The
    // CSV temp-file write (`to_csv_path`) stays in Python.
    // -----------------------------------------------------------------

    nb::class_<tuner_core::live_trigger_logger::TriggerLogRow>(m, "TriggerLogRow")
        .def(nb::init<>())
        .def_rw("values", &tuner_core::live_trigger_logger::TriggerLogRow::values);

    nb::class_<tuner_core::live_trigger_logger::TriggerLogCapture>(m, "TriggerLogCapture")
        .def(nb::init<>())
        .def_rw("logger_name", &tuner_core::live_trigger_logger::TriggerLogCapture::logger_name)
        .def_rw("display_name", &tuner_core::live_trigger_logger::TriggerLogCapture::display_name)
        .def_rw("kind", &tuner_core::live_trigger_logger::TriggerLogCapture::kind)
        .def_rw("columns", &tuner_core::live_trigger_logger::TriggerLogCapture::columns)
        .def_rw("rows", &tuner_core::live_trigger_logger::TriggerLogCapture::rows)
        .def_prop_ro("record_count",
            &tuner_core::live_trigger_logger::TriggerLogCapture::record_count);

    m.def(
        "live_trigger_logger_decode",
        [](const tuner_core::IniLoggerDefinition& logger,
           nb::bytes raw) {
            const auto* data = reinterpret_cast<const std::uint8_t*>(raw.c_str());
            std::span<const std::uint8_t> span(data, raw.size());
            return tuner_core::live_trigger_logger::decode(logger, span);
        },
        nb::arg("logger"),
        nb::arg("raw"),
        "Decode a raw binary trigger log buffer into a TriggerLogCapture. "
        "Mirrors LiveTriggerLoggerService.decode.");

    m.def(
        "live_trigger_logger_extract_field",
        [](nb::bytes record, const tuner_core::IniLoggerRecordField& field) {
            const auto* data = reinterpret_cast<const std::uint8_t*>(record.c_str());
            std::span<const std::uint8_t> span(data, record.size());
            return tuner_core::live_trigger_logger::extract_field(span, field);
        },
        nb::arg("record"),
        nb::arg("field"),
        "Extract a single bit-level field from a record byte slice. "
        "Mirrors LiveTriggerLoggerService._extract_field.");

    // -----------------------------------------------------------------
    // Live capture session — pure-logic helpers (status text,
    // ordered column names, value formatting, CSV emission). I/O
    // (file open / stream-write / close) stays Python.
    // -----------------------------------------------------------------

    nb::class_<tuner_core::live_capture_session::CapturedRecord>(m, "CapturedRecord")
        .def(nb::init<>())
        .def_rw("elapsed_ms", &tuner_core::live_capture_session::CapturedRecord::elapsed_ms)
        .def_rw("keys", &tuner_core::live_capture_session::CapturedRecord::keys)
        .def_rw("values", &tuner_core::live_capture_session::CapturedRecord::values);

    m.def(
        "live_capture_session_status_text",
        &tuner_core::live_capture_session::status_text,
        nb::arg("recording"), nb::arg("row_count"), nb::arg("elapsed_seconds"),
        "Compose the live-capture status string. Mirrors "
        "CaptureSessionStatus.status_text.");

    m.def(
        "live_capture_session_ordered_column_names",
        &tuner_core::live_capture_session::ordered_column_names,
        nb::arg("profile_channel_names"), nb::arg("records"),
        "Order column names: profile-first then record-insertion fallback. "
        "Mirrors LiveCaptureSessionService._ordered_column_names.");

    m.def(
        "live_capture_session_format_value",
        &tuner_core::live_capture_session::format_value,
        nb::arg("value"), nb::arg("digits"),
        "Format one value: digits >= 0 -> fixed, else Python repr.");

    m.def(
        "live_capture_session_format_csv",
        &tuner_core::live_capture_session::format_csv,
        nb::arg("records"), nb::arg("columns"), nb::arg("format_digits"),
        "Render captured rows as a CSV string. Mirrors "
        "LiveCaptureSessionService.to_csv.");

    // -----------------------------------------------------------------
    // Firmware flash builder — pure-logic platform / argument helpers
    // from `FirmwareFlashService`. I/O (subprocess execution, file
    // checks, USB device write) stays Python.
    // -----------------------------------------------------------------

    namespace ffb = tuner_core::firmware_flash_builder;

    nb::enum_<ffb::FlashTool>(m, "FlashToolKind")
        .value("AVRDUDE",  ffb::FlashTool::AVRDUDE)
        .value("TEENSY",   ffb::FlashTool::TEENSY)
        .value("DFU_UTIL", ffb::FlashTool::DFU_UTIL);

    nb::class_<ffb::TeensyMcuSpec>(m, "TeensyMcuSpec")
        .def(nb::init<>())
        .def_rw("name",       &ffb::TeensyMcuSpec::name)
        .def_rw("code_size",  &ffb::TeensyMcuSpec::code_size)
        .def_rw("block_size", &ffb::TeensyMcuSpec::block_size);

    m.def("firmware_flash_builder_platform_dir",
          [](ffb::FlashTool tool, const std::string& sys, const std::string& machine) {
              return ffb::platform_dir(tool, sys, machine);
          },
          nb::arg("tool"), nb::arg("system_name"), nb::arg("machine_name"),
          "Mirrors FirmwareFlashService._platform_dir.");

    m.def("firmware_flash_builder_tool_filename",
          [](ffb::FlashTool tool, const std::string& sys) {
              return ffb::tool_filename(tool, sys);
          },
          nb::arg("tool"), nb::arg("system_name"),
          "Mirrors FirmwareFlashService._tool_filename.");

    m.def("firmware_flash_builder_linux_platform_dir",
          [](const std::string& prefix, const std::string& machine) {
              return ffb::linux_platform_dir(prefix, machine);
          },
          nb::arg("prefix"), nb::arg("machine_name"),
          "Mirrors FirmwareFlashService._linux_platform_dir.");

    m.def("firmware_flash_builder_supports_internal_teensy",
          [](const std::string& sys) { return ffb::supports_internal_teensy(sys); },
          nb::arg("system_name"),
          "Mirrors FirmwareFlashService._supports_internal_teensy.");

    m.def("firmware_flash_builder_teensy_cli_filename",
          [](const std::string& sys) { return ffb::teensy_cli_filename(sys); },
          nb::arg("system_name"),
          "Mirrors FirmwareFlashService._teensy_cli_filename.");

    m.def("firmware_flash_builder_teensy_mcu_spec",
          &ffb::teensy_mcu_spec,
          nb::arg("board_family"),
          "Mirrors FirmwareFlashService._teensy_mcu_spec.");

    m.def("firmware_flash_builder_avrdude_arguments",
          [](const std::string& serial_port, const std::string& config_path,
             const std::string& firmware_path) {
              return ffb::build_avrdude_arguments(serial_port, config_path, firmware_path);
          },
          nb::arg("serial_port"), nb::arg("config_path"), nb::arg("firmware_path"),
          "Mirrors the arguments=[...] block of _build_avrdude_command.");

    m.def("firmware_flash_builder_teensy_cli_arguments",
          [](const std::string& mcu_name, const std::string& firmware_path) {
              return ffb::build_teensy_cli_arguments(mcu_name, firmware_path);
          },
          nb::arg("mcu_name"), nb::arg("firmware_path"),
          "Mirrors the CLI branch arguments of _build_teensy_command.");

    m.def("firmware_flash_builder_teensy_legacy_arguments",
          [](const std::string& board_family_value, const std::string& firmware_stem,
             const std::string& firmware_parent, const std::string& tools_dir) {
              return ffb::build_teensy_legacy_arguments(
                  board_family_value, firmware_stem, firmware_parent, tools_dir);
          },
          nb::arg("board_family_value"), nb::arg("firmware_stem"),
          nb::arg("firmware_parent"), nb::arg("tools_dir"),
          "Mirrors the legacy teensy_post_compile branch arguments of _build_teensy_command.");

    m.def("firmware_flash_builder_internal_teensy_arguments",
          [](const std::string& mcu_name, const std::string& firmware_path) {
              return ffb::build_internal_teensy_arguments(mcu_name, firmware_path);
          },
          nb::arg("mcu_name"), nb::arg("firmware_path"),
          "Mirrors the internal-loader branch arguments of _build_teensy_command.");

    m.def("firmware_flash_builder_dfu_arguments",
          [](const std::string& vid, const std::string& pid, const std::string& firmware_path) {
              return ffb::build_dfu_arguments(vid, pid, firmware_path);
          },
          nb::arg("vid"), nb::arg("pid"), nb::arg("firmware_path"),
          "Mirrors the arguments=[...] block of _build_dfu_command.");

    // -----------------------------------------------------------------
    // Legacy `.project` text file format — pure-logic parse + write.
    // I/O (Path resolution, mkdir, file read/write) stays Python.
    // -----------------------------------------------------------------

    namespace lpf = tuner_core::legacy_project_file;

    nb::class_<lpf::ConnectionProfile>(m, "LegacyConnectionProfile")
        .def(nb::init<>())
        .def_rw("name",        &lpf::ConnectionProfile::name)
        .def_rw("transport",   &lpf::ConnectionProfile::transport)
        .def_rw("protocol",    &lpf::ConnectionProfile::protocol)
        .def_rw("host",        &lpf::ConnectionProfile::host)
        .def_rw("port",        &lpf::ConnectionProfile::port)
        .def_rw("serial_port", &lpf::ConnectionProfile::serial_port)
        .def_rw("baud_rate",   &lpf::ConnectionProfile::baud_rate);

    nb::class_<lpf::LegacyProjectModel>(m, "LegacyProjectModel")
        .def(nb::init<>())
        .def_rw("name",                 &lpf::LegacyProjectModel::name)
        .def_rw("ecu_definition_path",  &lpf::LegacyProjectModel::ecu_definition_path)
        .def_rw("tune_file_path",       &lpf::LegacyProjectModel::tune_file_path)
        .def_rw("dashboards",           &lpf::LegacyProjectModel::dashboards)
        .def_rw("active_settings",      &lpf::LegacyProjectModel::active_settings)
        .def_rw("connection_profiles",  &lpf::LegacyProjectModel::connection_profiles)
        .def_rw("metadata",             &lpf::LegacyProjectModel::metadata);

    m.def("legacy_project_parse_key_value_lines",
          &lpf::parse_key_value_lines,
          nb::arg("lines"),
          "Mirrors tuner.parsers.common.parse_key_value_lines.");

    m.def("legacy_project_parse_default_connection_profile",
          &lpf::parse_default_connection_profile,
          nb::arg("metadata"),
          "Mirrors ProjectParser._parse_default_connection_profile.");

    m.def("legacy_project_sanitize_name",
          [](const std::string& name) {
              return lpf::sanitize_project_name(name);
          },
          nb::arg("name"),
          "Mirrors ProjectService._sanitize_name.");

    m.def("legacy_project_format_file",
          &lpf::format_legacy_project_file,
          nb::arg("model"),
          "Mirrors the line-builder body of ProjectService.save_project.");

    // -----------------------------------------------------------------
    // Protocol simulator command dispatch — pure-logic half of
    // `ProtocolSimulatorServer`. Socket I/O stays Python.
    // -----------------------------------------------------------------

    namespace ps = tuner_core::protocol_simulator;

    nb::class_<ps::SimulatorState>(m, "ProtocolSimulatorStateCpp")
        .def(nb::init<>())
        .def_rw("tick",            &ps::SimulatorState::tick)
        .def_rw("parameters_json", &ps::SimulatorState::parameters_json);

    m.def("protocol_simulator_runtime_values",
          &ps::runtime_values,
          nb::arg("state"),
          "Mirrors SimulatorState.runtime_values. Increments tick "
          "and returns {rpm, map, afr}.");

    m.def("protocol_simulator_handle_command_json",
          [](ps::SimulatorState& state, const std::string& payload_json) {
              return ps::handle_command_json(state, payload_json);
          },
          nb::arg("state"), nb::arg("payload_json"),
          "Mirrors ProtocolSimulatorServer._handle. Takes a JSON string, "
          "returns the JSON response string (compact form).");

    // -----------------------------------------------------------------
    // Speeduino connect strategy — pure-logic helpers used by
    // SpeeduinoControllerClient orchestration. I/O (transport open /
    // baud rate set / signature probe loop) stays Python.
    // -----------------------------------------------------------------

    namespace scs = tuner_core::speeduino_connect_strategy;

    m.def("speeduino_connect_command_char",
          [](const std::string& raw, const std::string& fallback) {
              const char fb = fallback.empty() ? '\0' : fallback[0];
              char result = scs::command_char(raw, fb);
              return std::string(1, result);
          },
          nb::arg("raw"), nb::arg("fallback"),
          "Mirrors SpeeduinoControllerClient._command_char. Returns the "
          "first character of `raw` if non-empty, else `fallback`.");

    m.def("speeduino_connect_effective_blocking_factor",
          &scs::effective_blocking_factor,
          nb::arg("is_table"),
          nb::arg("firmware_blocking_factor"),
          nb::arg("firmware_table_blocking_factor"),
          nb::arg("definition_blocking_factor"),
          nb::arg("definition_table_blocking_factor"),
          "Mirrors SpeeduinoControllerClient._effective_blocking_factor.");

    m.def("speeduino_connect_signature_probe_candidates",
          [](const std::string& query_command, const std::string& version_info_command) {
              auto cands = scs::signature_probe_candidates(query_command, version_info_command);
              std::vector<std::string> out;
              for (char c : cands) out.push_back(std::string(1, c));
              return out;
          },
          nb::arg("query_command"), nb::arg("version_info_command"),
          "Mirrors SpeeduinoControllerClient._signature_probe_candidates.");

    m.def("speeduino_connect_baud_probe_candidates",
          &scs::baud_probe_candidates,
          nb::arg("current_baud"),
          "Mirrors SpeeduinoControllerClient._baud_probe_candidates.");

    m.def("speeduino_connect_delay_seconds",
          &scs::connect_delay_seconds,
          nb::arg("metadata"),
          "Mirrors SpeeduinoControllerClient._connect_delay_seconds.");

    nb::class_<scs::CapabilityHeader>(m, "SpeeduinoCapabilityHeader")
        .def(nb::init<>())
        .def_rw("parsed",                  &scs::CapabilityHeader::parsed)
        .def_rw("serial_protocol_version", &scs::CapabilityHeader::serial_protocol_version)
        .def_rw("blocking_factor",         &scs::CapabilityHeader::blocking_factor)
        .def_rw("table_blocking_factor",   &scs::CapabilityHeader::table_blocking_factor);

    nb::class_<scs::OutputChannelField>(m, "SpeeduinoOutputChannelField")
        .def(nb::init<>())
        .def_rw("name",      &scs::OutputChannelField::name)
        .def_rw("offset",    &scs::OutputChannelField::offset)
        .def_rw("data_type", &scs::OutputChannelField::data_type);

    auto bytes_to_vec = [](nb::bytes b) {
        const auto* data = reinterpret_cast<const std::uint8_t*>(b.c_str());
        return std::vector<std::uint8_t>(data, data + b.size());
    };

    m.def("speeduino_parse_capability_header",
          [bytes_to_vec](std::optional<nb::bytes> payload) {
              if (!payload.has_value()) {
                  return scs::parse_capability_header(std::nullopt);
              }
              auto v = bytes_to_vec(*payload);
              return scs::parse_capability_header(std::span<const std::uint8_t>(v));
          },
          nb::arg("payload").none(),
          "Mirrors the payload-parse half of "
          "SpeeduinoControllerClient._read_capabilities. Pass None for a "
          "missing payload.");

    m.def("speeduino_capability_source",
          &scs::capability_source,
          nb::arg("header"),
          "Returns 'serial+definition' when parsed, 'definition' otherwise.");

    m.def("speeduino_compute_live_data_size",
          &scs::compute_live_data_size,
          nb::arg("channels"),
          "Mirrors SpeeduinoControllerClient._live_data_size.");

    m.def("speeduino_has_any_output_channel",
          &scs::has_any_output_channel,
          nb::arg("channel_names"), nb::arg("targets"),
          "Mirrors SpeeduinoControllerClient._has_output_channel.");

    m.def("speeduino_is_experimental_u16p2_signature",
          [](const std::string& signature) {
              return scs::is_experimental_u16p2_signature(signature);
          },
          nb::arg("signature"),
          "Mirrors '\"U16P2\" in (firmware_signature or \"\").upper()'.");

    m.def("speeduino_should_accept_probe_response",
          [](const std::string& command, const std::string& response) {
              const char cmd = command.empty() ? '\0' : command[0];
              return scs::should_accept_probe_response(cmd, response);
          },
          nb::arg("command"), nb::arg("response"),
          "Mirrors the accept/reject filter inside "
          "SpeeduinoControllerClient._probe_signature.");

    // -----------------------------------------------------------------
    // INI [SettingGroups] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniSettingGroupOption>(m, "IniSettingGroupOption")
        .def(nb::init<>())
        .def_rw("symbol", &tuner_core::IniSettingGroupOption::symbol)
        .def_rw("label",  &tuner_core::IniSettingGroupOption::label);

    nb::class_<tuner_core::IniSettingGroup>(m, "IniSettingGroup")
        .def(nb::init<>())
        .def_rw("symbol",  &tuner_core::IniSettingGroup::symbol)
        .def_rw("label",   &tuner_core::IniSettingGroup::label)
        .def_rw("options", &tuner_core::IniSettingGroup::options);

    nb::class_<tuner_core::IniSettingGroupsSection>(m, "IniSettingGroupsSection")
        .def(nb::init<>())
        .def_rw("groups", &tuner_core::IniSettingGroupsSection::groups);

    m.def("parse_setting_groups_section",
          [](const std::string& text) {
              return tuner_core::parse_setting_groups_section(text);
          },
          nb::arg("text"),
          "Parse the [SettingGroups] section. Mirrors "
          "IniParser._parse_setting_groups.");

    m.def("parse_setting_groups_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_setting_groups_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [SettingContextHelp] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniSettingContextHelpSection>(m, "IniSettingContextHelpSection")
        .def(nb::init<>())
        .def_rw("help_by_name", &tuner_core::IniSettingContextHelpSection::help_by_name);

    m.def("parse_setting_context_help_section",
          [](const std::string& text) {
              return tuner_core::parse_setting_context_help_section(text);
          },
          nb::arg("text"),
          "Parse the [SettingContextHelp] section. Mirrors "
          "IniParser._parse_setting_context_help.");

    m.def("parse_setting_context_help_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_setting_context_help_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [ConstantsExtensions] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniConstantsExtensionsSection>(m, "IniConstantsExtensionsSection")
        .def(nb::init<>())
        .def_rw("requires_power_cycle",
                &tuner_core::IniConstantsExtensionsSection::requires_power_cycle);

    m.def("parse_constants_extensions_section",
          [](const std::string& text) {
              return tuner_core::parse_constants_extensions_section(text);
          },
          nb::arg("text"),
          "Parse the [ConstantsExtensions] section. Mirrors "
          "IniParser._parse_constants_extensions.");

    m.def("parse_constants_extensions_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_constants_extensions_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [Tools] section parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniToolDeclaration>(m, "IniToolDeclaration")
        .def(nb::init<>())
        .def_rw("tool_id",         &tuner_core::IniToolDeclaration::tool_id)
        .def_rw("label",           &tuner_core::IniToolDeclaration::label)
        .def_rw("target_table_id", &tuner_core::IniToolDeclaration::target_table_id);

    nb::class_<tuner_core::IniToolsSection>(m, "IniToolsSection")
        .def(nb::init<>())
        .def_rw("declarations", &tuner_core::IniToolsSection::declarations);

    m.def("parse_tools_section",
          [](const std::string& text) {
              return tuner_core::parse_tools_section(text);
          },
          nb::arg("text"),
          "Parse the [Tools] section. Mirrors IniParser._parse_tools.");

    m.def("parse_tools_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_tools_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [UserDefined] reference-tables parser
    // -----------------------------------------------------------------

    nb::class_<tuner_core::IniReferenceTableSolution>(m, "IniReferenceTableSolution")
        .def(nb::init<>())
        .def_rw("label",      &tuner_core::IniReferenceTableSolution::label)
        .def_rw("expression", &tuner_core::IniReferenceTableSolution::expression);

    nb::class_<tuner_core::IniReferenceTable>(m, "IniReferenceTable")
        .def(nb::init<>())
        .def_rw("table_id",         &tuner_core::IniReferenceTable::table_id)
        .def_rw("label",            &tuner_core::IniReferenceTable::label)
        .def_rw("topic_help",       &tuner_core::IniReferenceTable::topic_help)
        .def_rw("table_identifier", &tuner_core::IniReferenceTable::table_identifier)
        .def_rw("solutions_label",  &tuner_core::IniReferenceTable::solutions_label)
        .def_rw("solutions",        &tuner_core::IniReferenceTable::solutions);

    nb::class_<tuner_core::IniReferenceTablesSection>(m, "IniReferenceTablesSection")
        .def(nb::init<>())
        .def_rw("tables", &tuner_core::IniReferenceTablesSection::tables);

    m.def("parse_reference_tables_section",
          [](const std::string& text) {
              return tuner_core::parse_reference_tables_section(text);
          },
          nb::arg("text"),
          "Parse reference tables from the [UserDefined] section. "
          "Mirrors IniParser._parse_reference_tables.");

    m.def("parse_reference_tables_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_reference_tables_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [PcVariables] section parser. Reuses the existing
    // IniConstantsSection POD (from ini_constants_parser.hpp) since
    // the output shape is identical apart from page/offset being
    // nullopt.
    // -----------------------------------------------------------------

    m.def("parse_pc_variables_section",
          [](const std::string& text) {
              return tuner_core::parse_pc_variables_section(text);
          },
          nb::arg("text"),
          "Parse the [PcVariables] section. Mirrors "
          "IniParser._parse_pc_variables. Returns an "
          "IniConstantsSection with every entry having "
          "page=None and offset=None.");

    m.def("parse_pc_variables_section_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_pc_variables_section_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // INI [VeAnalyze] / [WueAnalyze] autotune sections parser
    // -----------------------------------------------------------------

    nb::enum_<tuner_core::GateOperator>(m, "GateOperator")
        .value("Lt",      tuner_core::GateOperator::Lt)
        .value("Gt",      tuner_core::GateOperator::Gt)
        .value("Le",      tuner_core::GateOperator::Le)
        .value("Ge",      tuner_core::GateOperator::Ge)
        .value("Eq",      tuner_core::GateOperator::Eq)
        .value("Ne",      tuner_core::GateOperator::Ne)
        .value("BitAnd",  tuner_core::GateOperator::BitAnd)
        .value("Unknown", tuner_core::GateOperator::Unknown);

    nb::class_<tuner_core::StandardGate>(m, "StandardGate")
        .def(nb::init<>())
        .def_rw("name", &tuner_core::StandardGate::name);

    nb::class_<tuner_core::ParameterisedGate>(m, "ParameterisedGate")
        .def(nb::init<>())
        .def_rw("name",            &tuner_core::ParameterisedGate::name)
        .def_rw("label",           &tuner_core::ParameterisedGate::label)
        .def_rw("channel",         &tuner_core::ParameterisedGate::channel)
        .def_rw("op",              &tuner_core::ParameterisedGate::op)
        .def_rw("threshold",       &tuner_core::ParameterisedGate::threshold)
        .def_rw("default_enabled", &tuner_core::ParameterisedGate::default_enabled);

    nb::class_<tuner_core::AutotuneMapDefinition>(m, "AutotuneMapDefinition")
        .def(nb::init<>())
        .def_rw("section_name",          &tuner_core::AutotuneMapDefinition::section_name)
        .def_rw("map_parts",             &tuner_core::AutotuneMapDefinition::map_parts)
        .def_rw("lambda_target_tables",  &tuner_core::AutotuneMapDefinition::lambda_target_tables)
        .def_ro("filter_gates",          &tuner_core::AutotuneMapDefinition::filter_gates);

    nb::class_<tuner_core::IniAutotuneSectionsResult>(m, "IniAutotuneSectionsResult")
        .def(nb::init<>())
        .def_rw("maps", &tuner_core::IniAutotuneSectionsResult::maps);

    m.def("parse_autotune_sections",
          [](const std::string& text) {
              return tuner_core::parse_autotune_sections(text);
          },
          nb::arg("text"),
          "Parse [VeAnalyze] and [WueAnalyze] sections. "
          "Mirrors IniParser._parse_autotune_sections.");

    m.def("parse_autotune_sections_preprocessed",
          [](const std::string& text, const std::set<std::string>& active_settings) {
              return tuner_core::parse_autotune_sections_preprocessed(
                  text, active_settings);
          },
          nb::arg("text"),
          nb::arg("active_settings") = std::set<std::string>{},
          "Composed pipeline: preprocess + collect defines + parse.");

    // -----------------------------------------------------------------
    // EcuDefinition compiler — top-level INI ingestion
    // -----------------------------------------------------------------

    nb::class_<tuner_core::NativeEcuDefinition>(m, "NativeEcuDefinition")
        .def(nb::init<>())
        .def_rw("constants", &tuner_core::NativeEcuDefinition::constants)
        .def_rw("output_channels", &tuner_core::NativeEcuDefinition::output_channels)
        .def_rw("table_editors", &tuner_core::NativeEcuDefinition::table_editors)
        .def_rw("curve_editors", &tuner_core::NativeEcuDefinition::curve_editors)
        .def_rw("menus", &tuner_core::NativeEcuDefinition::menus)
        .def_rw("gauge_configurations", &tuner_core::NativeEcuDefinition::gauge_configurations)
        .def_rw("front_page", &tuner_core::NativeEcuDefinition::front_page)
        .def_rw("logger_definitions", &tuner_core::NativeEcuDefinition::logger_definitions)
        .def_rw("controller_commands", &tuner_core::NativeEcuDefinition::controller_commands)
        .def_rw("setting_groups", &tuner_core::NativeEcuDefinition::setting_groups)
        .def_rw("setting_context_help", &tuner_core::NativeEcuDefinition::setting_context_help)
        .def_rw("constants_extensions", &tuner_core::NativeEcuDefinition::constants_extensions)
        .def_rw("tools", &tuner_core::NativeEcuDefinition::tools)
        .def_rw("reference_tables", &tuner_core::NativeEcuDefinition::reference_tables)
        .def_rw("autotune_sections", &tuner_core::NativeEcuDefinition::autotune_sections);

    m.def(
        "compile_ecu_definition_text",
        [](const std::string& text,
           const std::set<std::string>& active_settings) {
            return tuner_core::compile_ecu_definition_text(text, active_settings);
        },
        nb::arg("text"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Compile a NativeEcuDefinition from in-memory INI text. Mirrors "
        "the Python IniParser.parse() orchestration flow.");

    m.def(
        "compile_ecu_definition_file",
        [](const std::filesystem::path& path,
           const std::set<std::string>& active_settings) {
            return tuner_core::compile_ecu_definition_file(path, active_settings);
        },
        nb::arg("path"),
        nb::arg("active_settings") = std::set<std::string>{},
        "Compile a NativeEcuDefinition from an INI file on disk.");

    // -----------------------------------------------------------------
    // Speeduino TCP framing helpers (Phase 14 Slice 3 — comms layer)
    // -----------------------------------------------------------------

    m.def(
        "speeduino_crc32",
        [](const std::vector<std::uint8_t>& data) {
            return tuner_core::speeduino_framing::crc32(
                std::span<const std::uint8_t>(data.data(), data.size()));
        },
        nb::arg("data"),
        "Standard zlib CRC-32 of `data`. Equivalent to "
        "`zlib.crc32(data) & 0xFFFFFFFF`.");

    m.def(
        "speeduino_encode_frame",
        [](const std::vector<std::uint8_t>& payload) {
            return tuner_core::speeduino_framing::encode_frame(
                std::span<const std::uint8_t>(payload.data(), payload.size()));
        },
        nb::arg("payload"),
        "Wrap `payload` in Speeduino new-protocol framing: "
        "[u16 LE len][payload][u32 LE CRC32(payload)].");

    nb::class_<tuner_core::speeduino_framing::DecodedFrame>(m, "SpeeduinoDecodedFrame")
        .def_rw("payload", &tuner_core::speeduino_framing::DecodedFrame::payload)
        .def_rw("bytes_consumed", &tuner_core::speeduino_framing::DecodedFrame::bytes_consumed)
        .def_rw("crc_valid", &tuner_core::speeduino_framing::DecodedFrame::crc_valid);

    m.def(
        "speeduino_decode_frame",
        [](const std::vector<std::uint8_t>& buffer) {
            return tuner_core::speeduino_framing::decode_frame(
                std::span<const std::uint8_t>(buffer.data(), buffer.size()));
        },
        nb::arg("buffer"),
        "Decode one Speeduino new-protocol frame from the front of `buffer`. "
        "CRC field is read but not validated against the payload — see "
        "`crc_valid` on the result.");

    // -----------------------------------------------------------------
    // Speeduino protocol command shapes (Phase 14 Slice 3 — second sub-slice)
    // -----------------------------------------------------------------

    m.def(
        "speeduino_page_request",
        [](char command, std::uint8_t page,
           std::uint16_t offset, std::uint16_t length) {
            return tuner_core::speeduino_protocol::page_request(
                command, page, offset, length);
        },
        nb::arg("command"),
        nb::arg("page"),
        nb::arg("offset"),
        nb::arg("length"),
        "7-byte page request: [cmd, 0x00, page, off_lo, off_hi, len_lo, len_hi].");

    m.def(
        "speeduino_page_write_request",
        [](std::uint8_t page, std::uint16_t offset,
           const std::vector<std::uint8_t>& payload, char command) {
            return tuner_core::speeduino_protocol::page_write_request(
                page, offset,
                std::span<const std::uint8_t>(payload.data(), payload.size()),
                command);
        },
        nb::arg("page"),
        nb::arg("offset"),
        nb::arg("payload"),
        nb::arg("command") = tuner_core::speeduino_protocol::kDefaultPageWriteChar,
        "Build a page-write request: 7-byte header followed by payload bytes.");

    m.def(
        "speeduino_runtime_request",
        [](std::uint16_t offset, std::uint16_t length) {
            return tuner_core::speeduino_protocol::runtime_request(offset, length);
        },
        nb::arg("offset"),
        nb::arg("length"),
        "7-byte runtime poll request: ['r', 0x00, 0x30, off_lo, off_hi, len_lo, len_hi].");

    // -----------------------------------------------------------------
    // Speeduino raw value codec (Phase 14 Slice 3 — third sub-slice)
    // -----------------------------------------------------------------

    m.def(
        "speeduino_data_size_bytes",
        [](const std::string& tag) {
            return tuner_core::speeduino_value_codec::data_size_bytes(tag);
        },
        nb::arg("tag"),
        "Byte size of one value of the given Speeduino data type tag "
        "(U08, S08, U16, S16, U32, S32, F32).");

    m.def(
        "speeduino_encode_raw_value_int",
        [](std::int64_t value, const std::string& tag) {
            return tuner_core::speeduino_value_codec::encode_raw_value(
                tuner_core::speeduino_value_codec::RawValue{value}, tag);
        },
        nb::arg("value"),
        nb::arg("tag"),
        "Encode an integer value as the little-endian byte representation "
        "of the given Speeduino integer data type.");

    m.def(
        "speeduino_encode_raw_value_float",
        [](double value, const std::string& tag) {
            return tuner_core::speeduino_value_codec::encode_raw_value(
                tuner_core::speeduino_value_codec::RawValue{value}, tag);
        },
        nb::arg("value"),
        nb::arg("tag"),
        "Encode a float value as the little-endian IEEE-754 byte "
        "representation of the F32 data type.");

    m.def(
        "speeduino_decode_raw_value_int",
        [](const std::vector<std::uint8_t>& buf, const std::string& tag) {
            auto v = tuner_core::speeduino_value_codec::decode_raw_value(
                std::span<const std::uint8_t>(buf.data(), buf.size()), tag);
            return std::get<std::int64_t>(v);
        },
        nb::arg("buf"),
        nb::arg("tag"),
        "Decode `buf` as an integer of the given Speeduino integer "
        "data type. Throws if `tag` is F32 (use the float overload).");

    m.def(
        "speeduino_decode_raw_value_float",
        [](const std::vector<std::uint8_t>& buf, const std::string& tag) {
            auto v = tuner_core::speeduino_value_codec::decode_raw_value(
                std::span<const std::uint8_t>(buf.data(), buf.size()), tag);
            return std::get<double>(v);
        },
        nb::arg("buf"),
        nb::arg("tag"),
        "Decode `buf` as a float of the F32 data type.");

    // -----------------------------------------------------------------
    // Speeduino scalar/table parameter codec (Phase 14 Slice 3 — fourth sub-slice)
    // -----------------------------------------------------------------

    // -----------------------------------------------------------------
    // Speeduino runtime live-data decoder (Phase 14 Slice 3 — fifth sub-slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::speeduino_live_data_decoder::OutputChannelValue>(
        m, "SpeeduinoOutputChannelValue")
        .def_rw("name",
                &tuner_core::speeduino_live_data_decoder::OutputChannelValue::name)
        .def_rw("value",
                &tuner_core::speeduino_live_data_decoder::OutputChannelValue::value)
        .def_rw("units",
                &tuner_core::speeduino_live_data_decoder::OutputChannelValue::units);

    // Channels are passed as parallel arrays so the Python side
    // doesn't have to construct a custom struct per channel — the
    // parity test builds these arrays straight from
    // `EcuDefinition.output_channel_definitions`.
    auto build_channels = [](
        const std::vector<std::string>& names,
        const std::vector<std::string>& units,
        const std::vector<std::size_t>& offsets,
        const std::vector<std::string>& data_types,
        const std::vector<std::optional<double>>& scales,
        const std::vector<std::optional<double>>& translates,
        const std::vector<int>& bit_offsets,
        const std::vector<int>& bit_lengths) {
        std::vector<tuner_core::speeduino_live_data_decoder::OutputChannelLayout> out;
        out.reserve(names.size());
        for (std::size_t i = 0; i < names.size(); ++i) {
            tuner_core::speeduino_live_data_decoder::OutputChannelLayout ch;
            ch.name = names[i];
            ch.units = units[i];
            ch.layout.offset = offsets[i];
            ch.layout.data_type =
                tuner_core::speeduino_value_codec::parse_data_type(data_types[i]);
            ch.layout.scale = scales[i];
            ch.layout.translate = translates[i];
            ch.layout.bit_offset = bit_offsets[i];
            ch.layout.bit_length = bit_lengths[i];
            out.push_back(std::move(ch));
        }
        return out;
    };

    m.def(
        "speeduino_runtime_packet_size",
        [build_channels](
            const std::vector<std::string>& names,
            const std::vector<std::string>& units,
            const std::vector<std::size_t>& offsets,
            const std::vector<std::string>& data_types,
            const std::vector<std::optional<double>>& scales,
            const std::vector<std::optional<double>>& translates,
            const std::vector<int>& bit_offsets,
            const std::vector<int>& bit_lengths) {
            auto channels = build_channels(
                names, units, offsets, data_types,
                scales, translates, bit_offsets, bit_lengths);
            return tuner_core::speeduino_live_data_decoder::runtime_packet_size(
                std::span(channels.data(), channels.size()));
        },
        nb::arg("names"),
        nb::arg("units"),
        nb::arg("offsets"),
        nb::arg("data_types"),
        nb::arg("scales"),
        nb::arg("translates"),
        nb::arg("bit_offsets"),
        nb::arg("bit_lengths"),
        "Compute the minimum runtime packet length covering all channels. "
        "Mirrors the max(offset + data_size) calculation in "
        "SpeeduinoControllerClient.read_runtime.");

    m.def(
        "speeduino_decode_runtime_packet",
        [build_channels](
            const std::vector<std::string>& names,
            const std::vector<std::string>& units,
            const std::vector<std::size_t>& offsets,
            const std::vector<std::string>& data_types,
            const std::vector<std::optional<double>>& scales,
            const std::vector<std::optional<double>>& translates,
            const std::vector<int>& bit_offsets,
            const std::vector<int>& bit_lengths,
            const std::vector<std::uint8_t>& payload) {
            auto channels = build_channels(
                names, units, offsets, data_types,
                scales, translates, bit_offsets, bit_lengths);
            return tuner_core::speeduino_live_data_decoder::decode_runtime_packet(
                std::span(channels.data(), channels.size()),
                std::span(payload.data(), payload.size()));
        },
        nb::arg("names"),
        nb::arg("units"),
        nb::arg("offsets"),
        nb::arg("data_types"),
        nb::arg("scales"),
        nb::arg("translates"),
        nb::arg("bit_offsets"),
        nb::arg("bit_lengths"),
        nb::arg("payload"),
        "Decode the runtime packet against the channel layouts. Returns "
        "a list of SpeeduinoOutputChannelValue. Mirrors the list "
        "comprehension in SpeeduinoControllerClient.read_runtime.");

    m.def(
        "speeduino_encode_scalar",
        [](std::size_t offset, const std::string& data_type,
           std::optional<double> scale, std::optional<double> translate,
           int bit_offset, int bit_length,
           double value, const std::vector<std::uint8_t>& page) {
            tuner_core::speeduino_param_codec::ScalarLayout layout;
            layout.offset = offset;
            layout.data_type =
                tuner_core::speeduino_value_codec::parse_data_type(data_type);
            layout.scale = scale;
            layout.translate = translate;
            layout.bit_offset = bit_offset;
            layout.bit_length = bit_length;
            return tuner_core::speeduino_param_codec::encode_scalar(
                layout, value,
                std::span<const std::uint8_t>(page.data(), page.size()));
        },
        nb::arg("offset"),
        nb::arg("data_type"),
        nb::arg("scale"),
        nb::arg("translate"),
        nb::arg("bit_offset"),
        nb::arg("bit_length"),
        nb::arg("value"),
        nb::arg("page"),
        "Encode a physical scalar value through the scale/translate/"
        "bit-field layer. Pass bit_offset=-1 / bit_length=-1 for "
        "non-bit-field scalars. Mirrors SpeeduinoControllerClient._encode_scalar.");

    m.def(
        "speeduino_decode_scalar",
        [](std::size_t offset, const std::string& data_type,
           std::optional<double> scale, std::optional<double> translate,
           int bit_offset, int bit_length,
           const std::vector<std::uint8_t>& page) {
            tuner_core::speeduino_param_codec::ScalarLayout layout;
            layout.offset = offset;
            layout.data_type =
                tuner_core::speeduino_value_codec::parse_data_type(data_type);
            layout.scale = scale;
            layout.translate = translate;
            layout.bit_offset = bit_offset;
            layout.bit_length = bit_length;
            return tuner_core::speeduino_param_codec::decode_scalar(
                layout,
                std::span<const std::uint8_t>(page.data(), page.size()));
        },
        nb::arg("offset"),
        nb::arg("data_type"),
        nb::arg("scale"),
        nb::arg("translate"),
        nb::arg("bit_offset"),
        nb::arg("bit_length"),
        nb::arg("page"),
        "Decode a physical scalar value from a page slice. Mirrors "
        "SpeeduinoControllerClient._decode_scalar.");

    m.def(
        "speeduino_encode_table",
        [](std::size_t offset, const std::string& data_type,
           std::optional<double> scale, std::optional<double> translate,
           std::size_t rows, std::size_t columns,
           const std::vector<double>& values) {
            tuner_core::speeduino_param_codec::TableLayout layout;
            layout.offset = offset;
            layout.data_type =
                tuner_core::speeduino_value_codec::parse_data_type(data_type);
            layout.scale = scale;
            layout.translate = translate;
            layout.rows = rows;
            layout.columns = columns;
            return tuner_core::speeduino_param_codec::encode_table(
                layout,
                std::span<const double>(values.data(), values.size()));
        },
        nb::arg("offset"),
        nb::arg("data_type"),
        nb::arg("scale"),
        nb::arg("translate"),
        nb::arg("rows"),
        nb::arg("columns"),
        nb::arg("values"),
        "Encode a list of physical table values into the raw page bytes. "
        "Mirrors SpeeduinoControllerClient._encode_table.");

    m.def(
        "speeduino_decode_table",
        [](std::size_t offset, const std::string& data_type,
           std::optional<double> scale, std::optional<double> translate,
           std::size_t rows, std::size_t columns,
           const std::vector<std::uint8_t>& page) {
            tuner_core::speeduino_param_codec::TableLayout layout;
            layout.offset = offset;
            layout.data_type =
                tuner_core::speeduino_value_codec::parse_data_type(data_type);
            layout.scale = scale;
            layout.translate = translate;
            layout.rows = rows;
            layout.columns = columns;
            return tuner_core::speeduino_param_codec::decode_table(
                layout,
                std::span<const std::uint8_t>(page.data(), page.size()));
        },
        nb::arg("offset"),
        nb::arg("data_type"),
        nb::arg("scale"),
        nb::arg("translate"),
        nb::arg("rows"),
        nb::arg("columns"),
        nb::arg("page"),
        "Decode raw page bytes into a list of physical table values. "
        "Mirrors SpeeduinoControllerClient._decode_table.");

    // -----------------------------------------------------------------
    // Visibility expression evaluator (Phase 14 Slice 4 — first sub-slice)
    // -----------------------------------------------------------------

    // -----------------------------------------------------------------
    // Required fuel calculator (Phase 14 Slice 4 — second sub-slice)
    // -----------------------------------------------------------------

    nb::class_<tuner_core::required_fuel_calculator::Result>(m, "RequiredFuelResult")
        .def_rw("req_fuel_ms",
                &tuner_core::required_fuel_calculator::Result::req_fuel_ms)
        .def_rw("req_fuel_stored",
                &tuner_core::required_fuel_calculator::Result::req_fuel_stored)
        .def_rw("displacement_cc",
                &tuner_core::required_fuel_calculator::Result::displacement_cc)
        .def_rw("cylinder_count",
                &tuner_core::required_fuel_calculator::Result::cylinder_count)
        .def_rw("injector_flow_ccmin",
                &tuner_core::required_fuel_calculator::Result::injector_flow_ccmin)
        .def_rw("target_afr",
                &tuner_core::required_fuel_calculator::Result::target_afr)
        .def_rw("inputs_summary",
                &tuner_core::required_fuel_calculator::Result::inputs_summary)
        .def_rw("is_valid",
                &tuner_core::required_fuel_calculator::Result::is_valid);

    // -----------------------------------------------------------------
    // Table edit numeric transforms (Phase 14 Slice 4 — third sub-slice)
    // -----------------------------------------------------------------

    auto build_selection = [](std::size_t top, std::size_t left,
                              std::size_t bottom, std::size_t right) {
        tuner_core::table_edit::TableSelection sel;
        sel.top = top;
        sel.left = left;
        sel.bottom = bottom;
        sel.right = right;
        return sel;
    };

    m.def(
        "table_edit_fill_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right, double fill_value) {
            return tuner_core::table_edit::fill_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right), fill_value);
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"), nb::arg("fill_value"));

    m.def(
        "table_edit_fill_down_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right) {
            return tuner_core::table_edit::fill_down_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right));
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"));

    m.def(
        "table_edit_fill_right_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right) {
            return tuner_core::table_edit::fill_right_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right));
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"));

    m.def(
        "table_edit_interpolate_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right) {
            return tuner_core::table_edit::interpolate_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right));
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"));

    m.def(
        "table_edit_smooth_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right) {
            return tuner_core::table_edit::smooth_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right));
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"));

    m.def(
        "table_edit_paste_region",
        [build_selection](
            const std::vector<double>& values, std::size_t columns,
            std::size_t top, std::size_t left,
            std::size_t bottom, std::size_t right,
            const std::string& clipboard_text) {
            return tuner_core::table_edit::paste_region(
                std::span(values.data(), values.size()), columns,
                build_selection(top, left, bottom, right), clipboard_text);
        },
        nb::arg("values"), nb::arg("columns"),
        nb::arg("top"), nb::arg("left"),
        nb::arg("bottom"), nb::arg("right"), nb::arg("clipboard_text"));

    // -----------------------------------------------------------------
    // Sample gate helpers (Phase 14 Slice 4 — fourth sub-slice)
    // -----------------------------------------------------------------

    // -----------------------------------------------------------------
    // AutotuneFilterGateEvaluator (Phase 14 Slice 4 — fifth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace afge = tuner_core::autotune_filter_gate_evaluator;

        nb::class_<afge::Gate>(m, "AutotuneGate")
            .def(nb::init<>())
            .def_rw("name", &afge::Gate::name)
            .def_rw("label", &afge::Gate::label)
            .def_rw("channel", &afge::Gate::channel)
            .def_rw("op", &afge::Gate::op)
            .def_rw("threshold", &afge::Gate::threshold)
            .def_rw("default_enabled", &afge::Gate::default_enabled);

        nb::class_<afge::AxisContext>(m, "AutotuneAxisContext")
            .def(nb::init<>())
            .def_rw("x_value", &afge::AxisContext::x_value)
            .def_rw("x_min", &afge::AxisContext::x_min)
            .def_rw("x_max", &afge::AxisContext::x_max)
            .def_rw("y_value", &afge::AxisContext::y_value)
            .def_rw("y_min", &afge::AxisContext::y_min)
            .def_rw("y_max", &afge::AxisContext::y_max);

        nb::class_<afge::Eval>(m, "AutotuneGateEval")
            .def_rw("gate_name", &afge::Eval::gate_name)
            .def_rw("accepted", &afge::Eval::accepted)
            .def_rw("reason", &afge::Eval::reason);

        m.def(
            "autotune_evaluate_gate",
            [](const afge::Gate& gate,
               const std::vector<std::pair<std::string, double>>& values,
               const std::optional<afge::AxisContext>& axis_context) {
                if (axis_context.has_value()) {
                    return afge::evaluate(gate, values, &(*axis_context));
                }
                return afge::evaluate(gate, values, nullptr);
            },
            nb::arg("gate"),
            nb::arg("values"),
            nb::arg("axis_context") = std::nullopt);

        m.def(
            "autotune_evaluate_all_gates",
            [](const std::vector<afge::Gate>& gates,
               const std::vector<std::pair<std::string, double>>& values,
               const std::optional<afge::AxisContext>& axis_context,
               bool fail_fast) {
                if (axis_context.has_value()) {
                    return afge::evaluate_all(gates, values, &(*axis_context), fail_fast);
                }
                return afge::evaluate_all(gates, values, nullptr, fail_fast);
            },
            nb::arg("gates"),
            nb::arg("values"),
            nb::arg("axis_context") = std::nullopt,
            nb::arg("fail_fast") = true);

        m.def(
            "autotune_gate_label",
            [](const afge::Gate& gate) { return afge::gate_label(gate); },
            nb::arg("gate"));
    }

    // -----------------------------------------------------------------
    // LiveDataMapParser (Phase 14 Slice 4 — twenty-first sub-slice)
    // -----------------------------------------------------------------
    {
        namespace ldmp = tuner_core::live_data_map_parser;

        nb::enum_<ldmp::ChannelEncoding>(m, "ChannelEncoding")
            .value("U08", ldmp::ChannelEncoding::U08)
            .value("U08_BITS", ldmp::ChannelEncoding::U08_BITS)
            .value("U16_LE", ldmp::ChannelEncoding::U16_LE)
            .value("S16_LE", ldmp::ChannelEncoding::S16_LE)
            .value("U32_LE", ldmp::ChannelEncoding::U32_LE)
            .value("UNKNOWN", ldmp::ChannelEncoding::UNKNOWN);

        nb::class_<ldmp::ChannelEntry>(m, "ChannelEntry")
            .def_rw("name", &ldmp::ChannelEntry::name)
            .def_rw("byte_start", &ldmp::ChannelEntry::byte_start)
            .def_rw("byte_end", &ldmp::ChannelEntry::byte_end)
            .def_rw("readable_index", &ldmp::ChannelEntry::readable_index)
            .def_rw("encoding", &ldmp::ChannelEntry::encoding)
            .def_rw("field", &ldmp::ChannelEntry::field)
            .def_rw("notes", &ldmp::ChannelEntry::notes)
            .def_rw("locked", &ldmp::ChannelEntry::locked)
            .def("width", &ldmp::ChannelEntry::width);

        nb::class_<ldmp::ChannelContract>(m, "ChannelContract")
            .def_rw("log_entry_size", &ldmp::ChannelContract::log_entry_size)
            .def_rw("firmware_signature", &ldmp::ChannelContract::firmware_signature)
            .def_rw("entries", &ldmp::ChannelContract::entries)
            .def_rw("runtime_status_a_offset",
                    &ldmp::ChannelContract::runtime_status_a_offset)
            .def_rw("board_capability_flags_offset",
                    &ldmp::ChannelContract::board_capability_flags_offset)
            .def_rw("flash_health_status_offset",
                    &ldmp::ChannelContract::flash_health_status_offset);

        m.def(
            "live_data_map_parse_text",
            [](const std::string& text,
               const std::optional<std::string>& firmware_signature) {
                return ldmp::parse_text(text, firmware_signature);
            },
            nb::arg("text"),
            nb::arg("firmware_signature") = std::nullopt);
    }

    // -----------------------------------------------------------------
    // SyncStateService (Phase 14 Slice 4 — eighteenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace ss = tuner_core::sync_state;

        nb::enum_<ss::MismatchKind>(m, "SyncMismatchKind")
            .value("SIGNATURE_MISMATCH", ss::MismatchKind::SIGNATURE_MISMATCH)
            .value("PAGE_SIZE_MISMATCH", ss::MismatchKind::PAGE_SIZE_MISMATCH)
            .value("ECU_VS_TUNE", ss::MismatchKind::ECU_VS_TUNE)
            .value("STALE_STAGED", ss::MismatchKind::STALE_STAGED);

        nb::class_<ss::Mismatch>(m, "SyncMismatch")
            .def_rw("kind", &ss::Mismatch::kind)
            .def_rw("detail", &ss::Mismatch::detail);

        nb::class_<ss::State>(m, "SyncState")
            .def_rw("mismatches", &ss::State::mismatches)
            .def_rw("has_ecu_ram", &ss::State::has_ecu_ram)
            .def_rw("connection_state", &ss::State::connection_state)
            .def("is_clean", &ss::State::is_clean);

        nb::class_<ss::DefinitionInputs>(m, "SyncStateDefinitionInputs")
            .def(nb::init<>())
            .def_rw("firmware_signature", &ss::DefinitionInputs::firmware_signature)
            .def_rw("page_sizes", &ss::DefinitionInputs::page_sizes);

        nb::class_<ss::TuneFileInputs>(m, "SyncStateTuneFileInputs")
            .def(nb::init<>())
            .def_rw("signature", &ss::TuneFileInputs::signature)
            .def_rw("page_count", &ss::TuneFileInputs::page_count)
            .def_rw("base_values", &ss::TuneFileInputs::base_values);

        m.def(
            "sync_state_build",
            [](std::optional<ss::DefinitionInputs> definition,
               std::optional<ss::TuneFileInputs> tune_file,
               std::optional<std::vector<std::pair<std::string, ss::ScalarOrList>>> ecu_ram,
               bool has_staged,
               const std::string& connection_state) {
                return ss::build(
                    std::move(definition), std::move(tune_file),
                    std::move(ecu_ram), has_staged, connection_state);
            },
            nb::arg("definition"),
            nb::arg("tune_file"),
            nb::arg("ecu_ram"),
            nb::arg("has_staged"),
            nb::arg("connection_state"),
            "Mirror SyncStateService.build.");
    }

    // -----------------------------------------------------------------
    // GaugeColorZones (Phase 14 Slice 4 — sixteenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace gcz = tuner_core::gauge_color_zones;

        nb::class_<gcz::Zone>(m, "GaugeColorZone")
            .def(nb::init<>())
            .def_rw("lo", &gcz::Zone::lo)
            .def_rw("hi", &gcz::Zone::hi)
            .def_rw("color", &gcz::Zone::color);

        nb::class_<gcz::Thresholds>(m, "GaugeThresholds")
            .def(nb::init<>())
            .def_rw("lo_danger", &gcz::Thresholds::lo_danger)
            .def_rw("lo_warn", &gcz::Thresholds::lo_warn)
            .def_rw("hi_warn", &gcz::Thresholds::hi_warn)
            .def_rw("hi_danger", &gcz::Thresholds::hi_danger);

        m.def(
            "gauge_derive_color_zones",
            [](double lo, double hi, const gcz::Thresholds& t) {
                return gcz::derive_zones(lo, hi, t);
            },
            nb::arg("lo"), nb::arg("hi"), nb::arg("thresholds"),
            "Mirror DashboardLayoutService._zones_from_gauge_config.");
    }

    // -----------------------------------------------------------------
    // EvidenceReplayComparison (Phase 14 Slice 4 — fifteenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace erc = tuner_core::evidence_replay_comparison;

        nb::class_<erc::Channel>(m, "EvidenceReplayChannel")
            .def(nb::init<>())
            .def_rw("name", &erc::Channel::name)
            .def_rw("value", &erc::Channel::value)
            .def_rw("units", &erc::Channel::units);

        nb::class_<erc::Delta>(m, "EvidenceReplayChannelDelta")
            .def_rw("name", &erc::Delta::name)
            .def_rw("previous_value", &erc::Delta::previous_value)
            .def_rw("current_value", &erc::Delta::current_value)
            .def_rw("delta_value", &erc::Delta::delta_value)
            .def_rw("units", &erc::Delta::units);

        nb::class_<erc::Comparison>(m, "EvidenceReplayComparison")
            .def_rw("summary_text", &erc::Comparison::summary_text)
            .def_rw("detail_text", &erc::Comparison::detail_text)
            .def_rw("changed_channels", &erc::Comparison::changed_channels);

        m.def(
            "evidence_replay_compare_channels",
            [](const std::vector<erc::Channel>& baseline,
               const std::vector<erc::Channel>& current,
               const std::vector<std::string>& relevant) {
                return erc::compare_runtime_channels(baseline, current, relevant);
            },
            nb::arg("baseline_channels"),
            nb::arg("current_channels"),
            nb::arg("relevant_channel_names"),
            "Mirror EvidenceReplayComparisonService.build (channel diff "
            "only — caller handles the snapshot equality early-out).");
    }

    // -----------------------------------------------------------------
    // TableView model builder (Phase 14 Slice 4 — fourteenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace tv = tuner_core::table_view;

        nb::class_<tv::ShapeHints>(m, "TableViewShapeHints")
            .def(nb::init<>())
            .def_rw("rows", &tv::ShapeHints::rows)
            .def_rw("cols", &tv::ShapeHints::cols)
            .def_rw("shape_text", &tv::ShapeHints::shape_text);

        nb::class_<tv::ViewModel>(m, "TableViewModel")
            .def_rw("rows", &tv::ViewModel::rows)
            .def_rw("columns", &tv::ViewModel::columns)
            .def_rw("cells", &tv::ViewModel::cells);

        m.def(
            "table_view_resolve_shape",
            [](std::size_t value_count, const tv::ShapeHints& hints) {
                return tv::resolve_shape(value_count, hints);
            },
            nb::arg("value_count"), nb::arg("hints"));

        m.def(
            "table_view_build_model",
            [](const std::vector<double>& values, const tv::ShapeHints& hints) {
                return tv::build_table_model(
                    std::span<const double>(values.data(), values.size()), hints);
            },
            nb::arg("values"), nb::arg("hints"),
            "Mirror TableViewService.build_table_model.");
    }

    // -----------------------------------------------------------------
    // TuningPageDiffService (Phase 14 Slice 4 — thirteenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace tpd = tuner_core::tuning_page_diff;

        nb::class_<tpd::DiffEntry>(m, "TuningPageDiffEntry")
            .def_rw("name", &tpd::DiffEntry::name)
            .def_rw("before_preview", &tpd::DiffEntry::before_preview)
            .def_rw("after_preview", &tpd::DiffEntry::after_preview);

        nb::class_<tpd::DiffResult>(m, "TuningPageDiffResult")
            .def_rw("entries", &tpd::DiffResult::entries);

        m.def(
            "tuning_page_diff_build",
            [](const std::vector<std::string>& parameter_names,
               const std::set<std::string>& dirty_names,
               const std::vector<std::pair<std::string, tpd::ScalarOrList>>& staged_values,
               const std::vector<std::pair<std::string, tpd::ScalarOrList>>& base_values) {
                return tpd::build_page_diff(
                    parameter_names, dirty_names, staged_values, base_values);
            },
            nb::arg("parameter_names"),
            nb::arg("dirty_names"),
            nb::arg("staged_values"),
            nb::arg("base_values"),
            "Mirror TuningPageDiffService.build_page_diff.");

        m.def(
            "tuning_page_diff_summary",
            [](const tpd::DiffResult& r) { return tpd::summary(r); },
            nb::arg("result"));

        m.def(
            "tuning_page_diff_detail_text",
            [](const tpd::DiffResult& r) { return tpd::detail_text(r); },
            nb::arg("result"));
    }

    // -----------------------------------------------------------------
    // StagedChange.summarize (Phase 14 Slice 4 — twelfth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace sc = tuner_core::staged_change;

        nb::class_<sc::StagedEntry>(m, "StagedChangeEntry")
            .def_rw("name", &sc::StagedEntry::name)
            .def_rw("preview", &sc::StagedEntry::preview)
            .def_rw("before_preview", &sc::StagedEntry::before_preview)
            .def_rw("page_title", &sc::StagedEntry::page_title)
            .def_rw("is_written", &sc::StagedEntry::is_written);

        m.def(
            "staged_change_summarize",
            [](const std::vector<std::pair<std::string, sc::ScalarOrList>>& staged_values,
               const std::vector<std::pair<std::string, sc::ScalarOrList>>& base_values,
               const std::vector<std::pair<std::string, std::string>>& page_titles,
               const std::set<std::string>& written_names) {
                return sc::summarize(staged_values, base_values, page_titles, written_names);
            },
            nb::arg("staged_values"),
            nb::arg("base_values"),
            nb::arg("page_titles"),
            nb::arg("written_names"),
            "Mirror StagedChangeService.summarize.");
    }

    // -----------------------------------------------------------------
    // Tune value preview formatter (Phase 14 Slice 4 — eleventh sub-slice)
    // -----------------------------------------------------------------
    {
        namespace tvp = tuner_core::tune_value_preview;

        m.def(
            "tune_value_format_scalar_python_repr",
            [](double v) { return tvp::format_scalar_python_repr(v); },
            nb::arg("value"));

        m.def(
            "tune_value_format_list_preview",
            [](const std::vector<double>& v) {
                return tvp::format_list_preview(
                    std::span<const double>(v.data(), v.size()));
            },
            nb::arg("values"));
    }

    // -----------------------------------------------------------------
    // ReleaseManifest (Phase 14 Slice 4 — tenth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace rm = tuner_core::release_manifest;

        nb::enum_<rm::ArtifactKind>(m, "FirmwareArtifactKind")
            .value("STANDARD", rm::ArtifactKind::STANDARD)
            .value("DIAGNOSTIC", rm::ArtifactKind::DIAGNOSTIC);

        nb::class_<rm::FirmwareEntry>(m, "ReleaseManifestFirmwareEntry")
            .def_rw("file_name", &rm::FirmwareEntry::file_name)
            .def_rw("board_family", &rm::FirmwareEntry::board_family)
            .def_rw("version_label", &rm::FirmwareEntry::version_label)
            .def_rw("is_experimental", &rm::FirmwareEntry::is_experimental)
            .def_rw("artifact_kind", &rm::FirmwareEntry::artifact_kind)
            .def_rw("preferred", &rm::FirmwareEntry::preferred)
            .def_rw("definition_file_name", &rm::FirmwareEntry::definition_file_name)
            .def_rw("tune_file_name", &rm::FirmwareEntry::tune_file_name)
            .def_rw("firmware_signature", &rm::FirmwareEntry::firmware_signature);

        nb::class_<rm::Manifest>(m, "ReleaseManifest")
            .def_rw("firmware", &rm::Manifest::firmware);

        m.def(
            "release_manifest_parse_text",
            [](const std::string& text) { return rm::parse_manifest_text(text); },
            nb::arg("text"),
            "Parse a release_manifest.json document from in-memory text.");

        m.def(
            "release_manifest_load",
            [](const std::filesystem::path& release_root) {
                return rm::load_manifest(release_root);
            },
            nb::arg("release_root"),
            "Load <release_root>/release_manifest.json from disk.");
    }

    // -----------------------------------------------------------------
    // PressureSensorCalibration (Phase 14 Slice 4 — ninth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace psc = tuner_core::pressure_sensor_calibration;

        nb::enum_<psc::SensorKind>(m, "PressureSensorKind")
            .value("MAP", psc::SensorKind::MAP)
            .value("BARO", psc::SensorKind::BARO);

        nb::class_<psc::Preset>(m, "PressureSensorPreset")
            .def(nb::init<>())
            .def_rw("key", &psc::Preset::key)
            .def_rw("label", &psc::Preset::label)
            .def_rw("description", &psc::Preset::description)
            .def_rw("minimum_value", &psc::Preset::minimum_value)
            .def_rw("maximum_value", &psc::Preset::maximum_value)
            .def_rw("units", &psc::Preset::units)
            .def_rw("source_note", &psc::Preset::source_note)
            .def_rw("source_url", &psc::Preset::source_url);

        nb::class_<psc::Assessment>(m, "PressureCalibrationAssessment")
            .def_rw("minimum_value", &psc::Assessment::minimum_value)
            .def_rw("maximum_value", &psc::Assessment::maximum_value)
            .def_rw("matching_preset", &psc::Assessment::matching_preset)
            .def_rw("guidance", &psc::Assessment::guidance)
            .def_rw("warning", &psc::Assessment::warning);

        m.def(
            "pressure_find_matching_preset",
            [](double minimum_value, double maximum_value,
               const std::vector<psc::Preset>& presets) {
                return psc::find_matching_preset(minimum_value, maximum_value, presets);
            },
            nb::arg("minimum_value"),
            nb::arg("maximum_value"),
            nb::arg("presets"));

        m.def(
            "pressure_assess_calibration",
            [](std::optional<double> minimum_value,
               std::optional<double> maximum_value,
               const std::vector<psc::Preset>& presets,
               psc::SensorKind sensor_kind) {
                return psc::assess(minimum_value, maximum_value, presets, sensor_kind);
            },
            nb::arg("minimum_value"),
            nb::arg("maximum_value"),
            nb::arg("presets"),
            nb::arg("sensor_kind"));

        m.def(
            "pressure_source_confidence_label",
            [](const std::string& source_note,
               const std::optional<std::string>& source_url) {
                return psc::source_confidence_label(source_note, source_url);
            },
            nb::arg("source_note"),
            nb::arg("source_url"));
    }

    // -----------------------------------------------------------------
    // BoardDetection (Phase 14 Slice 4 — eighth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace bd = tuner_core::board_detection;
        nb::enum_<bd::BoardFamily>(m, "BoardFamily")
            .value("ATMEGA2560", bd::BoardFamily::ATMEGA2560)
            .value("TEENSY35", bd::BoardFamily::TEENSY35)
            .value("TEENSY36", bd::BoardFamily::TEENSY36)
            .value("TEENSY41", bd::BoardFamily::TEENSY41)
            .value("STM32F407_DFU", bd::BoardFamily::STM32F407_DFU);

        m.def(
            "board_detect_from_text",
            [](const std::string& text) { return bd::detect_from_text(text); },
            nb::arg("text"),
            "Regex-driven board family detection from a definition / "
            "signature / controller name string.");

        m.def(
            "board_detect_from_capabilities",
            [](bool experimental_u16p2, const std::string& signature) {
                return bd::detect_from_capabilities(experimental_u16p2, signature);
            },
            nb::arg("experimental_u16p2"),
            nb::arg("signature") = std::string{},
            "Capability-driven board detection: signature → text "
            "detector first, then U16P2 ⇒ TEENSY41 fallback.");
    }

    // -----------------------------------------------------------------
    // HardwareSetupValidationService (Phase 14 Slice 4 — seventh sub-slice)
    // -----------------------------------------------------------------
    {
        namespace hsv = tuner_core::hardware_setup_validation;

        nb::enum_<hsv::Severity>(m, "HardwareSetupSeverity")
            .value("WARNING", hsv::Severity::WARNING)
            .value("ERROR", hsv::Severity::ERROR);

        nb::class_<hsv::Issue>(m, "HardwareSetupIssue")
            .def_rw("severity", &hsv::Issue::severity)
            .def_rw("message", &hsv::Issue::message)
            .def_rw("parameter_name", &hsv::Issue::parameter_name)
            .def_rw("detail", &hsv::Issue::detail);

        // Caller passes parameter values as a parallel-array dict
        // (list of name→value pairs) so insertion order is preserved
        // across the FFI. The C++ side iterates in input order.
        m.def(
            "hardware_setup_validate",
            [](const std::vector<std::string>& parameter_names,
               const std::vector<std::pair<std::string, double>>& values) {
                auto lookup = [&values](std::string_view name) -> std::optional<double> {
                    for (const auto& [k, v] : values) {
                        if (k == name) return v;
                    }
                    return std::nullopt;
                };
                return hsv::validate(parameter_names, lookup);
            },
            nb::arg("parameter_names"),
            nb::arg("values"),
            "Run all hardware setup validation rules. Mirrors "
            "HardwareSetupValidationService.validate.");
    }

    // -----------------------------------------------------------------
    // WUE Analyze pure-logic helpers (Phase 14 Slice 4 — sixth sub-slice)
    // -----------------------------------------------------------------
    {
        namespace wah = tuner_core::wue_analyze_helpers;

        m.def("wue_confidence_label",
              [](int n) { return wah::confidence_label(n); }, nb::arg("sample_count"));

        m.def("wue_is_clt_axis",
              [](const std::string& s) { return wah::is_clt_axis(s); },
              nb::arg("param_name"));

        m.def("wue_clt_from_record",
              [](const std::vector<std::pair<std::string, double>>& v) {
                  return wah::clt_from_record(v);
              }, nb::arg("values"));

        m.def("wue_nearest_index",
              [](const std::vector<double>& axis, double value) {
                  return wah::nearest_index(
                      std::span<const double>(axis.data(), axis.size()), value);
              },
              nb::arg("axis"), nb::arg("value"));

        m.def("wue_numeric_axis",
              [](const std::vector<std::string>& labels) {
                  return wah::numeric_axis(
                      std::span<const std::string>(labels.data(), labels.size()));
              },
              nb::arg("labels"));

        m.def("wue_parse_cell_float",
              [](const std::optional<std::string>& cell) -> std::optional<double> {
                  if (!cell.has_value()) return std::nullopt;
                  return wah::parse_cell_float(*cell);
              },
              nb::arg("cell_text"));

        m.def("wue_target_lambda_from_cell",
              [](double raw, double scalar_fallback) {
                  return wah::target_lambda_from_cell(raw, scalar_fallback);
              },
              nb::arg("raw"), nb::arg("scalar_fallback"));
    }

    m.def(
        "sample_gate_normalise_operator",
        [](const std::string& op) {
            return tuner_core::sample_gate_helpers::normalise_operator(op);
        },
        nb::arg("op"));

    m.def(
        "sample_gate_apply_operator",
        [](double channel_value, const std::string& op, double threshold) {
            return tuner_core::sample_gate_helpers::apply_operator(
                channel_value, op, threshold);
        },
        nb::arg("channel_value"), nb::arg("op"), nb::arg("threshold"));

    // The Python parity test passes the record values as a list of
    // (key, value) tuples so insertion order is preserved across the
    // FFI boundary — the C++ side iterates in the order it sees.
    m.def(
        "sample_gate_resolve_channel",
        [](const std::string& name,
           const std::vector<std::pair<std::string, double>>& values) {
            return tuner_core::sample_gate_helpers::resolve_channel(name, values);
        },
        nb::arg("name"), nb::arg("values"));

    m.def(
        "sample_gate_lambda_value",
        [](const std::vector<std::pair<std::string, double>>& values) {
            return tuner_core::sample_gate_helpers::lambda_value(values);
        },
        nb::arg("values"));

    m.def(
        "sample_gate_afr_value",
        [](const std::vector<std::pair<std::string, double>>& values) {
            return tuner_core::sample_gate_helpers::afr_value(values);
        },
        nb::arg("values"));

    m.def(
        "calculate_required_fuel",
        [](double displacement_cc, int cylinder_count,
           double injector_flow_ccmin, double target_afr) {
            return tuner_core::required_fuel_calculator::calculate(
                displacement_cc, cylinder_count, injector_flow_ccmin, target_afr);
        },
        nb::arg("displacement_cc"),
        nb::arg("cylinder_count"),
        nb::arg("injector_flow_ccmin"),
        nb::arg("target_afr"),
        "Compute Speeduino required fuel from engine and injector parameters. "
        "Mirrors RequiredFuelCalculatorService.calculate.");

    m.def(
        "evaluate_visibility_expression",
        [](const std::string& expression,
           const std::map<std::string, double>& values,
           const std::optional<std::map<std::string, std::vector<double>>>& arrays) {
            if (arrays.has_value()) {
                return tuner_core::visibility_expression::evaluate(
                    expression, values, &(*arrays));
            }
            return tuner_core::visibility_expression::evaluate(
                expression, values, nullptr);
        },
        nb::arg("expression"),
        nb::arg("values"),
        nb::arg("arrays") = std::nullopt,
        "Evaluate a TunerStudio INI visibility expression. Mirrors "
        "VisibilityExpressionService.evaluate. Fail-open: any parse "
        "error returns True.");

    m.def(
        "evaluate_math_expression",
        [](const std::string& expression,
           const std::map<std::string, double>& values,
           const std::optional<std::map<std::string, std::vector<double>>>& arrays) {
            if (arrays.has_value()) {
                return tuner_core::math_expression_evaluator::evaluate(
                    expression, values, &(*arrays));
            }
            return tuner_core::math_expression_evaluator::evaluate(
                expression, values, nullptr);
        },
        nb::arg("expression"),
        nb::arg("values"),
        nb::arg("arrays") = std::nullopt,
        "Evaluate a TunerStudio formula output channel expression. "
        "Mirrors MathExpressionEvaluator.evaluate. Fail-safe: any parse "
        "error or division by zero returns 0.0.");

    m.def(
        "compute_formula_output_channels",
        [](const std::vector<tuner_core::IniFormulaOutputChannel>& formulas,
           const std::map<std::string, double>& values,
           const std::optional<std::map<std::string, std::vector<double>>>& arrays) {
            if (arrays.has_value()) {
                return tuner_core::math_expression_evaluator::compute_all(
                    formulas, values, &(*arrays));
            }
            return tuner_core::math_expression_evaluator::compute_all(
                formulas, values, nullptr);
        },
        nb::arg("formulas"),
        nb::arg("values"),
        nb::arg("arrays") = std::nullopt,
        "Compute every formula output channel in declaration order. "
        "Mirrors MathExpressionEvaluator.compute_all — each channel's "
        "result is folded back into the working snapshot so later "
        "formulas can reference earlier ones.");

    // -----------------------------------------------------------------
    // Flash target detection (sub-slice 99 — pure-logic classifier).
    // Reuses `BoardFamily` from the board_detection service (already
    // registered earlier in this file) so there's only one enum type
    // on the Python side.
    // -----------------------------------------------------------------

    nb::class_<tuner_core::flash_target_detection::DetectedFlashTarget>(
        m, "DetectedFlashTarget")
        .def(nb::init<>())
        .def_rw("board_family",
                &tuner_core::flash_target_detection::DetectedFlashTarget::board_family)
        .def_rw("source",
                &tuner_core::flash_target_detection::DetectedFlashTarget::source)
        .def_rw("description",
                &tuner_core::flash_target_detection::DetectedFlashTarget::description)
        .def_rw("serial_port",
                &tuner_core::flash_target_detection::DetectedFlashTarget::serial_port)
        .def_rw("usb_vid",
                &tuner_core::flash_target_detection::DetectedFlashTarget::usb_vid)
        .def_rw("usb_pid",
                &tuner_core::flash_target_detection::DetectedFlashTarget::usb_pid);

    nb::class_<tuner_core::flash_target_detection::TeensyIdentity>(m, "TeensyIdentity")
        .def(nb::init<>())
        .def_rw("board_family",
                &tuner_core::flash_target_detection::TeensyIdentity::board_family)
        .def_rw("label",
                &tuner_core::flash_target_detection::TeensyIdentity::label);

    m.def(
        "normalize_hex",
        [](const std::string& value) {
            return tuner_core::flash_target_detection::normalize_hex(value);
        },
        nb::arg("value"),
        "Normalize VID/PID/BCD string to uppercase 4-hex-digit form. "
        "Mirrors FlashTargetDetectionService._normalize_hex.");

    m.def(
        "teensy_identity_from_pid_or_bcd",
        [](const std::string& pid, const std::string& bcd) {
            return tuner_core::flash_target_detection::
                teensy_identity_from_pid_or_bcd(pid, bcd);
        },
        nb::arg("pid"), nb::arg("bcd_device"),
        "Look up Teensy identity from PID (serial mode) or bcdDevice "
        "(HalfKay HID mode). Mirrors _teensy_identity_from_pid_or_bcd.");

    m.def(
        "classify_serial_port",
        [](const std::string& vid, const std::string& pid,
           const std::string& device, const std::string& description) {
            return tuner_core::flash_target_detection::classify_serial_port(
                vid, pid, device, description);
        },
        nb::arg("vid"), nb::arg("pid"), nb::arg("device"), nb::arg("description"),
        "Classify one serial port descriptor into a DetectedFlashTarget. "
        "VID/PID must already be normalized. Returns None for unknown devices.");

    m.def(
        "classify_usb_device",
        [](const std::string& vid, const std::string& pid,
           const std::string& bcd, bool has_hid_interface) {
            return tuner_core::flash_target_detection::classify_usb_device(
                vid, pid, bcd, has_hid_interface);
        },
        nb::arg("vid"), nb::arg("pid"), nb::arg("bcd"), nb::arg("has_hid_interface"),
        "Classify one non-serial USB device into a DetectedFlashTarget. "
        "Returns None for unknown devices.");

    m.def(
        "speeduino_burn_request",
        [](std::uint8_t page, char command) {
            return tuner_core::speeduino_protocol::burn_request(page, command);
        },
        nb::arg("page"),
        nb::arg("command") = tuner_core::speeduino_protocol::kDefaultBurnChar,
        "3-byte burn request: [burn_cmd, 0x00, page].");
}
