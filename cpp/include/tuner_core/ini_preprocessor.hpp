// SPDX-License-Identifier: MIT
//
// tuner_core::IniPreprocessor — C++ port of the Python
// `tuner.parsers.common.preprocess_ini_lines()` function.
//
// Evaluates `#if` / `#else` / `#endif` and `#set` / `#unset` directives
// in INI source text. Returns only the lines that belong to active
// conditional branches. Used by every INI section parser as the
// first stage; isolating it as its own slice means later C++ section
// parsers can rely on a fully-validated preprocessor.
//
// Python is the oracle: every behaviour here matches the Python
// implementation byte-for-byte across the existing
// `test_ini_preprocessor.py` fixture suite.
//
// Semantics summary (verbatim from the Python docstring):
//
//   - active_settings (constructor argument) takes precedence over
//     file-level #set/#unset defaults
//   - the file is scanned in two passes:
//       Phase 1: collect file-scope #set/#unset defaults (only at
//                file scope — directives nested inside #if blocks are
//                ignored in this phase)
//       Phase 2: walk the lines applying conditional logic with
//                effective = file_defaults | active_settings
//   - nesting is supported
//   - empty lines are preserved when inside an active branch
//   - lines starting with `#` (comments, #define, unrecognised) are
//     dropped while inside an inactive branch
//   - #set/#unset are consumed (never emitted in the output)

#pragma once

#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// Process INI source lines and return only those belonging to active
// conditional branches.
std::vector<std::string> preprocess_ini_lines(
    const std::vector<std::string>& raw_lines,
    const std::set<std::string>& active_settings = {});

// Convenience overload that accepts the source as one blob and splits
// on `\n` (matching Python's `text.splitlines()` semantics — `\r\n`
// and `\r` line endings are normalized).
std::vector<std::string> preprocess_ini_text(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
