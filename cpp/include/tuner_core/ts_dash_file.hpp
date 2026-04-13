// SPDX-License-Identifier: MIT
//
// tuner_core::ts_dash_file — port of TsDashFileService parse/export.
// Sub-slice 70 of Phase 14 Slice 4.
//
// Parses TSDash .dash XML format into DashboardLayout widgets and
// exports back to XML.  Pure logic, no file I/O.

#pragma once

#include "dashboard_layout.hpp"

#include <string>
#include <vector>

namespace tuner_core::ts_dash_file {

/// Parse a .dash XML string into a DashboardLayout.
/// Throws std::invalid_argument on malformed XML.
dashboard_layout::Layout parse_text(const std::string& xml_text);

/// Export a DashboardLayout to .dash XML string.
std::string export_text(const dashboard_layout::Layout& layout);

}  // namespace tuner_core::ts_dash_file
