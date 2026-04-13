// SPDX-License-Identifier: MIT
//
// tuner_core::tuning_page_builder — port of TuningPageService core flow.
// Sub-slice 73 of Phase 14 Slice 4.
//
// Compiles layout pages + table editors from the parsed definition into
// grouped TuningPage objects with resolved parameters.  Pure logic.

#pragma once

#include "definition_layout.hpp"
#include "tuning_page_grouping.hpp"
#include "ecu_definition_compiler.hpp"

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::tuning_page_builder {

// -----------------------------------------------------------------------
// TuningPage — the compiled page model for the workspace
// -----------------------------------------------------------------------

enum class PageKind { PARAMETER_LIST, TABLE, CURVE };

struct PageParameter {
    std::string name;
    std::string label;
    std::string kind;    // "scalar", "table", "array"
    std::string units;
    std::string role;    // "scalar", "table", "x_axis", "y_axis", "auxiliary"
    std::optional<int> page;
    std::optional<int> offset;
};

struct PageSection {
    std::string title;
    std::vector<std::string> parameter_names;
    std::string notes;
};

struct TuningPage {
    std::string page_id;
    std::string title;
    std::string group_id;
    std::string group_title;
    PageKind kind = PageKind::PARAMETER_LIST;
    std::string summary;
    std::vector<PageParameter> parameters;
    std::vector<PageSection> sections;
    // Table-specific.
    std::string table_id;
    std::string table_name;
    std::string x_axis_name;
    std::string y_axis_name;
    std::string x_axis_label;
    std::string y_axis_label;
};

struct TuningPageGroup {
    std::string group_id;
    std::string title;
    std::vector<TuningPage> pages;
};

// -----------------------------------------------------------------------
// Builder
// -----------------------------------------------------------------------

/// Build grouped tuning pages from a compiled EcuDefinition.
std::vector<TuningPageGroup> build_pages(const NativeEcuDefinition& definition);

}  // namespace tuner_core::tuning_page_builder
