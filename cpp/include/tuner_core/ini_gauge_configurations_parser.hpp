// SPDX-License-Identifier: MIT
//
// tuner_core::IniGaugeConfigurationsParser — port of
// `IniParser._parse_gauge_configurations`. Parses the
// `[GaugeConfigurations]` section that defines named gauge presets:
// each entry pairs a runtime channel with display metadata (title,
// units, lo/hi range, warn/danger thresholds, decimal places) plus
// an optional category for grouping in the configuration UI.
//
// Format::
//
//     name = channel, "title", "units", lo, hi, loD, loW, hiW, hiD, vd, ld
//
// Categories are introduced by `gaugeCategory = "Name"` lines and
// apply to every subsequent gauge entry until the next category line.
// Threshold values that contain inline TunerStudio expressions
// (e.g. `{rpmhigh}`) cannot be evaluated at parse time and are
// stored as nullopt — they're frozen and never auto-resolved.
//
// Why this slice matters: the gauge catalog is what the dashboard
// reads to know how to display every named gauge — RPM, MAP, AFR,
// CLT, etc. Combined with `[FrontPage]` (next slice), it drives the
// default dashboard layout the operator sees on startup.

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One gauge configuration entry. Mirrors the Python `GaugeConfiguration`
// dataclass field-for-field.
struct IniGaugeConfiguration {
    std::string name;
    std::string channel;
    std::string title;
    std::string units;
    std::optional<double> lo;
    std::optional<double> hi;
    std::optional<double> lo_danger;
    std::optional<double> lo_warn;
    std::optional<double> hi_warn;
    std::optional<double> hi_danger;
    int value_digits = 0;
    int label_digits = 0;
    std::optional<std::string> category;
};

struct IniGaugeConfigurationsSection {
    std::vector<IniGaugeConfiguration> gauges;
};

// Parse `[GaugeConfigurations]` from pre-preprocessed INI text. The
// optional `defines` map is currently unused but is present for
// signature consistency.
IniGaugeConfigurationsSection parse_gauge_configurations_section(
    std::string_view text,
    const IniDefines& defines = {});

IniGaugeConfigurationsSection parse_gauge_configurations_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniGaugeConfigurationsSection parse_gauge_configurations_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
