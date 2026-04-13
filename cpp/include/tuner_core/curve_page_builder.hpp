// SPDX-License-Identifier: MIT
//
// tuner_core::curve_page_builder — port of CurvePageService.build_curve_pages.
// Sub-slice 57 of Phase 14 Slice 4.
//
// Builds curve page snapshots from the CurveDefinition list on the
// parsed EcuDefinition.  Composes the already-ported curve_page_classifier
// for group assignment and summary text.  Pure logic, no Qt.

#pragma once

#include "curve_page_classifier.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::curve_page_builder {

// -----------------------------------------------------------------------
// Curve page model — minimal representation for the workspace
// -----------------------------------------------------------------------

struct CurveParameter {
    std::string name;
    std::string label;
    std::string units;
    std::string role;  // "x_axis" or "y_axis"
};

struct CurvePage {
    std::string page_id;       // "curve:{name}"
    std::string title;
    std::string group_id;      // "curve-fuel", "curve-idle", etc.
    std::string group_title;
    int group_order = 99;
    std::string summary;
    std::string help_topic;
    std::string x_axis_label;
    std::string y_axis_label;
    std::string curve_name;
    std::string curve_x_bins_param;
    std::string curve_x_channel;
    std::vector<std::string> curve_y_bins_params;
    std::vector<std::string> curve_line_labels;
    std::string curve_gauge;
    std::vector<CurveParameter> parameters;
};

struct CurvePageGroup {
    std::string group_id;
    std::string title;
    std::vector<CurvePage> pages;
};

// -----------------------------------------------------------------------
// Input types — what the builder reads from the parsed definition
// -----------------------------------------------------------------------

struct YBins {
    std::string param;
    std::string label;
};

struct CurveDefinition {
    std::string name;
    std::string title;
    std::string x_bins_param;
    std::string x_channel;
    std::string x_label;
    std::string y_label;
    std::vector<YBins> y_bins_list;
    std::string gauge;
    std::string topic_help;
};

struct ParamInfo {
    std::string name;
    std::string label;
    std::string units;
    std::string help_text;
};

// -----------------------------------------------------------------------
// Builder
// -----------------------------------------------------------------------

/// Build grouped curve pages from curve definitions.
/// `find_param` resolves a parameter name to its info (from scalars or
/// arrays in the definition).
using ParamFinder = std::optional<ParamInfo>(*)(const std::string& name, void* user);

std::vector<CurvePageGroup> build_curve_pages(
    const std::vector<CurveDefinition>& curves,
    ParamFinder find_param,
    void* find_param_user);

}  // namespace tuner_core::curve_page_builder
