// SPDX-License-Identifier: MIT
//
// tuner_core::datalog_import — port of DatalogImportService.
// Sub-slice 74 of Phase 14 Slice 4.
//
// Imports CSV datalog rows into a structured datalog with time
// detection, channel extraction, and summary/preview text.

#pragma once

#include <map>
#include <string>
#include <vector>

namespace tuner_core::datalog_import {

struct Record {
    double timestamp_seconds = 0;
    std::map<std::string, double> values;
};

struct ImportSnapshot {
    int row_count = 0;
    std::vector<std::string> channel_names;
    std::vector<Record> records;
    std::string summary_text;
    std::string preview_text;
};

/// Row: column_name → value_string.
using CsvRow = std::vector<std::pair<std::string, std::string>>;

/// Import datalog from pre-parsed CSV rows.
/// Throws std::invalid_argument if no numeric rows found.
ImportSnapshot import_rows(
    const std::vector<std::string>& headers,
    const std::vector<CsvRow>& rows,
    const std::string& source_name = "datalog");

}  // namespace tuner_core::datalog_import
