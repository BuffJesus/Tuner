// SPDX-License-Identifier: MIT
//
// tuner_core::IniFrontPageParser — port of `IniParser._parse_front_page`.
// Parses the `[FrontPage]` section that drives the default dashboard:
//
//   - `gauge1` ... `gaugeN` — ordered list of gauge slot names
//     (each value is the name of an entry in `[GaugeConfigurations]`)
//   - `indicator = { expr }, "off-label", "on-label",
//                  off-bg, off-fg, on-bg, on-fg`
//
// The output mirrors the Python `EcuDefinition.front_page_gauges`
// (positional list, missing slots filled with empty strings) and
// `EcuDefinition.front_page_indicators` (list of `FrontPageIndicator`).

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniFrontPageIndicator {
    std::string expression;
    std::string off_label;
    std::string on_label;
    std::string off_bg;
    std::string off_fg;
    std::string on_bg;
    std::string on_fg;
};

struct IniFrontPageSection {
    // Positional gauge slot list (gauge1..gaugeN). Missing slots are
    // empty strings, mirroring the Python builder.
    std::vector<std::string> gauges;
    std::vector<IniFrontPageIndicator> indicators;
};

IniFrontPageSection parse_front_page_section(
    std::string_view text,
    const IniDefines& defines = {});

IniFrontPageSection parse_front_page_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse, mirroring
// the Python `IniParser.parse()` flow.
IniFrontPageSection parse_front_page_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
