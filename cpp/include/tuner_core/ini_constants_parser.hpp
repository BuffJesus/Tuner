// SPDX-License-Identifier: MIT
//
// tuner_core::IniConstantsParser — first INI section parser ported
// from `IniParser._parse_constant_definitions` in
// `src/tuner/parsers/ini_parser.py`. Handles the `[Constants]` section
// grammar:
//
//   page = N                                          ; current page
//   name = scalar,  TYPE, offset, "units", scale, translate, lo, hi, digits
//   name = array,   TYPE, offset, [rows x cols], "units", scale, ...
//   name = array,   TYPE, offset, [N],            "units", ...
//   name = bits,    TYPE, offset, [bit_offset:bit_end], "label0", "label1", ...
//
// Special offset value `lastOffset` resolves to the running offset
// from the previous entry on the same page.
//
// This is the foundation for the rest of the INI parser port: every
// later section (`[TableEditor]`, `[CurveEditor]`, `[OutputChannels]`,
// `[Menu]`, etc.) references constants by name, so getting the
// scalar/array catalog right is the prerequisite.
//
// Python is the oracle: every behaviour here matches the Python
// implementation byte-for-byte across the existing fixture suite.
//
// **Out of scope for v1** (deferred to later slices):
//   - page title inference (heuristic, not grammar)
//   - bit option [Defines] expansion (depends on a [Defines] section
//     parser we haven't ported yet)
//   - `string` entries (rare)
//   - {expression} scale/translate placeholders
//   - bit field options validation

#pragma once

#include "tuner_core/ini_defines_parser.hpp"

#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

struct IniScalar {
    std::string name;
    std::string data_type;
    std::optional<std::string> units;
    std::optional<int> page;
    std::optional<int> offset;
    std::optional<double> scale;
    std::optional<double> translate;
    std::optional<int> digits;
    std::optional<double> min_value;
    std::optional<double> max_value;
    // For `bits` entries: option labels are stored in declaration order;
    // empty strings are skipped to match the Python behaviour.
    std::vector<std::string> options;
    std::optional<int> bit_offset;
    std::optional<int> bit_length;
};

struct IniArray {
    std::string name;
    std::string data_type;
    int rows = 0;
    int columns = 0;
    std::optional<std::string> units;
    std::optional<int> page;
    std::optional<int> offset;
    std::optional<double> scale;
    std::optional<double> translate;
    std::optional<int> digits;
    std::optional<double> min_value;
    std::optional<double> max_value;
};

struct IniConstantsSection {
    std::vector<IniScalar> scalars;
    std::vector<IniArray> arrays;
};

// Parse the `[Constants]` section out of pre-preprocessed INI text.
// The caller has already run the source through `preprocess_ini_text`
// (or knows there are no `#if` directives to worry about).
//
// `defines` is consulted by `bits` entries to expand `$macroName`
// references in the option label list. Pass an empty map to skip
// expansion (matches the Python behaviour when `defines=None`).
IniConstantsSection parse_constants_section(
    std::string_view text,
    const IniDefines& defines = {});

// Convenience overload that accepts the source as `vector<string>`,
// matching the Python `_parse_constant_definitions` line-iteration
// model directly.
IniConstantsSection parse_constants_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// **Composed pipeline**: preprocess + collect defines + parse in one
// call. Mirrors what `IniParser.parse()` does on the Python side —
// runs the slice 3 preprocessor with the given `active_settings`
// first, walks the surviving lines once to collect every `#define`
// from slice 5, then parses the same lines as `[Constants]` with
// the defines map wired in for bit-option expansion. This is the
// entry point for the "full equality" parity claim against the
// production INI.
IniConstantsSection parse_constants_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
