// SPDX-License-Identifier: MIT
//
// tuner_core::ini_pc_variables_parser — port of
// `IniParser._parse_pc_variables` from
// `src/tuner/parsers/ini_parser.py`. Parses the `[PcVariables]`
// section, which declares **host-side display variables**: scalars,
// bit fields, and arrays that live entirely in the workstation
// (e.g. operator-set preferences, computed dashboard channels)
// without any ECU storage. The grammar is a proper subset of
// `[Constants]`:
//
//   name = scalar, TYPE,        "units", scale, translate, lo, hi, digits
//   name = bits,   TYPE, [shape], "label0", "label1", ...
//   name = array,  TYPE, [shape], "units", scale, translate, lo, hi, digits
//
// Compared to `[Constants]` there's no `page = N` tracking, no
// `lastOffset` handling, no `offset` field at all, and no `string`
// entry kind. Every entry is emitted with `page = nullopt` and
// `offset = nullopt` so downstream services can tell PC-only entries
// apart from their ECU-storage constants-section neighbours.
//
// The output catalog reuses the existing `IniConstantsSection` POD
// (from `ini_constants_parser.hpp`) so the aggregator can merge the
// PC variables result into `NativeEcuDefinition.constants` directly,
// matching Python's behaviour of appending to the same
// `definition.scalars` / `definition.tables` lists.

#pragma once

#include "tuner_core/ini_constants_parser.hpp"
#include "tuner_core/ini_defines_parser.hpp"

#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// Parse the `[PcVariables]` section out of INI text.
IniConstantsSection parse_pc_variables_section(
    std::string_view text,
    const IniDefines& defines = {});

IniConstantsSection parse_pc_variables_lines(
    const std::vector<std::string>& lines,
    const IniDefines& defines = {});

// Composed pipeline: preprocess + collect defines + parse.
IniConstantsSection parse_pc_variables_section_preprocessed(
    std::string_view text,
    const std::set<std::string>& active_settings = {});

}  // namespace tuner_core
