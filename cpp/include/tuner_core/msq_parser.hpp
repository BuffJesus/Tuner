// SPDX-License-Identifier: MIT
//
// tuner_core::MsqParser — minimal MSQ XML reader/writer for the
// Python-as-oracle Phase 13 first slice. Handles only what the legacy
// Python `MsqParser` and `MsqWriteService.save()` (default
// insert_missing=False) handle: parsing <constant> nodes by name and
// updating their text content while leaving the rest of the document
// byte-stable.
//
// Design rules:
//   - C++20, stdlib only. No third-party deps in v1.
//   - Hand-rolled XML scanner because the MSQ format is structurally
//     simple (no DTD, no namespaces beyond the root xmlns, no entities
//     beyond the standard five) and pulling in pugixml/expat would
//     dwarf the slice.
//   - Python is the oracle. Every behaviour here must match
//     `src/tuner/services/msq_write_service.py` and
//     `src/tuner/parsers/msq_parser.py` byte-for-byte on the existing
//     fixture suite.

#pragma once

#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

// One <constant> entry as it appears in an MSQ document. Keeps the
// raw text payload (whitespace and all) so write_msq can return the
// document byte-stable when no edits are applied.
struct MsqConstant {
    std::string name;
    std::string text;          // inner-text payload, verbatim from source
    std::string units;         // attribute "units", may be empty
    int rows = 0;              // attribute "rows", 0 when absent
    int cols = 0;              // attribute "cols", 0 when absent
    int digits = -1;           // attribute "digits", -1 when absent
};

// Result of parsing an MSQ document.
struct MsqDocument {
    std::string signature;     // versionInfo/@signature
    std::string file_format;   // versionInfo/@fileFormat
    int page_count = 0;        // versionInfo/@nPages
    std::vector<MsqConstant> constants;
};

// Parse an MSQ document from disk. Throws std::runtime_error on
// missing file or fundamentally malformed XML.
MsqDocument parse_msq(const std::filesystem::path& path);

// Parse an MSQ document from a string. Same semantics as parse_msq().
MsqDocument parse_msq_text(std::string_view xml);

// Update an MSQ document on disk: read source, replace the inner-text
// of every <constant> whose name appears in `updates`, and write the
// result to destination. Mirrors the Python
// MsqWriteService.save(insert_missing=False) default — constants not
// present in the source XML are silently dropped.
//
// `updates` maps constant name → new inner-text. The text is written
// verbatim; the caller is responsible for matching legacy's
// formatting (multi-line table layout, etc.).
//
// Returns the number of constants whose text was actually updated.
std::size_t write_msq(
    const std::filesystem::path& source,
    const std::filesystem::path& destination,
    const std::map<std::string, std::string>& updates);

// In-memory variant for tests / bindings that prefer to work with
// strings. Returns the rewritten XML.
std::string write_msq_text(
    std::string_view source_xml,
    const std::map<std::string, std::string>& updates);

// ---------------------------------------------------------------------------
// Insert-missing mode (Fragile area #1 fix, sub-slice 89)
// ---------------------------------------------------------------------------
//
// Describes one <constant> node that should be injected into the first
// <page> element of the source document when the document doesn't
// already contain a constant with the same `name`. Mirrors the Python
// `MsqWriteService._insert_missing_constants` path — used by generators
// that produce staged table/scalar values for parameters that aren't
// yet materialised in the source MSQ (e.g. loading a tune whose veTable
// entry was absent from the base file).
//
// The caller is responsible for formatting `text` to match legacy's
// conventions (multi-line table layout, scalar representation, etc.).
// The helpers below mirror the Python `_format_value` / `_fmt_scalar`
// output byte-for-byte so callers can produce compatible text without
// re-implementing the formatter.
struct MsqInsertion {
    std::string name;
    std::string text;           // pre-formatted inner text
    std::string units;          // optional — empty = omit attribute
    int rows = 0;               // 0 = omit attribute
    int cols = 0;               // 0 = omit attribute
    int digits = -1;            // -1 = omit attribute
};

// Format a scalar the same way legacy/Python MsqWriteService does:
// integers (including floats like 6.0) render without a decimal point,
// non-integer floats use std::to_string default.
std::string format_msq_scalar(double value);

// Format a flat row-major table value as the multi-line inner text the
// Python `_format_value` produces: a leading newline, each row on its
// own line prefixed with nine spaces and separated by single spaces,
// followed by a closing "      " indent line. Mirrors the Python
// implementation byte-for-byte.
std::string format_msq_table(
    const std::vector<double>& values, int rows, int cols);

// Extended write variant: applies `updates` to existing constants, then
// injects any entry in `insertions` whose `name` doesn't already appear
// in the document into the first `<page>` element. Returns the rewritten
// XML.
//
// Insertions whose name is already present are silently skipped —
// callers don't need to pre-filter. This matches the Python
// `_insert_missing_constants` loop.
std::string write_msq_text_with_insertions(
    std::string_view source_xml,
    const std::map<std::string, std::string>& updates,
    const std::vector<MsqInsertion>& insertions);

}  // namespace tuner_core
