// SPDX-License-Identifier: MIT
//
// tuner_core::msq_value_formatter — port of MsqWriteService._format_value.
// Sub-slice 75 of Phase 14 Slice 4.
//
// Formats tune values (scalar, string, table) for MSQ XML output,
// matching TunerStudio's formatting conventions.

#pragma once

#include <string>
#include <variant>
#include <vector>

namespace tuner_core::msq_value_formatter {

using Value = std::variant<double, std::string, std::vector<double>>;

/// Format a scalar number the way TunerStudio does: integers without decimals.
std::string format_scalar(double value);

/// Format a tune value for MSQ XML text content.
/// - double: formatted via format_scalar
/// - string: returned as-is
/// - vector<double>: formatted as multi-line table with given rows×cols
std::string format_value(const Value& value, int rows = 0, int cols = 0);

}  // namespace tuner_core::msq_value_formatter
