// SPDX-License-Identifier: MIT
//
// tuner_core::IniDefinesParser — port of `IniParser._collect_defines`
// and `IniParser._expand_options`.
//
// Speeduino INI files use `#define` lines anywhere in the document
// to declare named option lists. Bit-field entries in `[Constants]`
// reference these by `$name` to share enum labels:
//
//     #define injectorTypes = "Off","Throttle Body","Single Point","Multi-port"
//     [Constants]
//     injType = bits, U08, 5, [0:1], $injectorTypes
//
// This slice ports both halves: the collector that walks the file
// gathering every `#define` into a name → list-of-tokens map, and
// the recursive `$macroName` expander that resolves option lists at
// constants-parse time. Composed into the existing constants parser
// in a follow-up step so bit-option labels match Python output
// byte-for-byte on the production INI.
//
// Python is the oracle: matches `_collect_defines` and
// `_expand_options` byte-for-byte across the existing fixture suite.

#pragma once

#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// Map from define name (without `$` prefix) to its expanded list of
// string tokens. Single-value defines are stored as a one-element
// list to keep the consumer code simple — Python does the same.
using IniDefines = std::map<std::string, std::vector<std::string>>;

// Walk an INI document collecting every `#define name = ...` line.
// The text should already be preprocessed (`#if`/`#else` resolved).
// Lines that don't start with `#define` or that lack `=` are ignored.
IniDefines collect_defines(std::string_view text);
IniDefines collect_defines_lines(const std::vector<std::string>& lines);

// Expand `$name` references in an option-list against a defines map.
// Recursively follows nested defines (capped at 10 levels to guard
// against circular references — matches Python). Tokens that begin
// with `{` (inline visibility expressions that leaked into the
// options list) are dropped. Unresolved `$name` references are
// silently dropped rather than emitting raw `$undefined` labels.
std::vector<std::string> expand_options(
    const std::vector<std::string>& parts,
    const IniDefines& defines);

}  // namespace tuner_core
