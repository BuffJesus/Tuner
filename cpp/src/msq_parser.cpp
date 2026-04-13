// SPDX-License-Identifier: MIT
//
// tuner_core::MsqParser implementation.
//
// The MSQ format is a small subset of XML:
//   <?xml ... ?>
//   <msq xmlns="...">
//     <versionInfo signature="..." fileFormat="..." nPages="..."/>
//     <page number="N">
//       <constant name="..." units="..." rows="2" cols="2" digits="1">
//         text
//       </constant>
//       ...
//     </page>
//   </msq>
//
// We only need to:
//   1. Find versionInfo and pull a few attributes
//   2. Walk every <constant> element, capturing name + attributes + inner text
//   3. For write_msq, replace inner text for any name in `updates` and emit
//      the rest of the document byte-for-byte
//
// A regex-based scanner is sufficient for this subset because the MSQ
// fixture set never uses XML features we don't model (no CDATA, no
// processing instructions inside elements, no entities beyond the
// standard five). The Python implementation makes the same assumption.

#include "tuner_core/msq_parser.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>

namespace tuner_core {

namespace {

// Read entire file into a string. Used by both parse_msq and write_msq.
std::string read_file(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error("MSQ file not found: " + path.string());
    }
    std::ostringstream out;
    out << stream.rdbuf();
    return out.str();
}

// Pull one attribute value out of an opening-tag attribute string.
// Tolerates single or double quotes; returns empty when missing.
std::string extract_attribute(std::string_view attr_blob, std::string_view name) {
    std::string pattern;
    pattern.reserve(name.size() + 16);
    pattern.append(name);
    pattern.append("\\s*=\\s*([\"'])([^\"']*)\\1");
    std::regex re(pattern);
    std::cmatch match;
    if (std::regex_search(attr_blob.data(), attr_blob.data() + attr_blob.size(), match, re)) {
        return match[2].str();
    }
    return {};
}

int parse_int_or(const std::string& text, int fallback) {
    if (text.empty()) {
        return fallback;
    }
    try {
        return std::stoi(text);
    } catch (...) {
        return fallback;
    }
}

// Locate every <constant ...> ... </constant> in the document and
// invoke `visit(name, attr_blob, inner_text_start, inner_text_end)`
// for each one. The visitor receives indices into the original text
// so write_msq can splice the document without re-serializing.
template <typename Visit>
void scan_constants(std::string_view xml, Visit&& visit) {
    static const std::regex open_re(R"(<constant\b([^>]*?)(/?)>)",
                                    std::regex::optimize);
    auto cursor = xml.begin();
    const auto end = xml.end();
    std::cmatch match;
    while (std::regex_search(&*cursor, &*end, match, open_re)) {
        std::size_t open_offset = static_cast<std::size_t>(
            (cursor - xml.begin()) + match.position(0));
        std::size_t open_length = static_cast<std::size_t>(match.length(0));
        std::string attr_blob = match[1].str();
        bool self_closing = match[2].length() > 0;

        std::string name = extract_attribute(attr_blob, "name");
        if (name.empty()) {
            cursor += match.position(0) + match.length(0);
            continue;
        }

        std::size_t inner_start = open_offset + open_length;
        std::size_t inner_end;
        if (self_closing) {
            inner_end = inner_start;
        } else {
            // Find the matching </constant>. The MSQ format never
            // nests <constant> elements, so a flat search is safe.
            std::size_t close_pos = xml.find("</constant>", inner_start);
            if (close_pos == std::string_view::npos) {
                throw std::runtime_error(
                    "Unterminated <constant name=\"" + name + "\"> in MSQ XML");
            }
            inner_end = close_pos;
        }

        visit(name, attr_blob, inner_start, inner_end);

        cursor = xml.begin() + (self_closing ? inner_end : inner_end + std::string_view("</constant>").size());
    }
}

}  // namespace

MsqDocument parse_msq(const std::filesystem::path& path) {
    return parse_msq_text(read_file(path));
}

MsqDocument parse_msq_text(std::string_view xml) {
    MsqDocument doc;

    // versionInfo — single self-closing element near the top of the file.
    static const std::regex version_re(R"(<versionInfo\b([^>]*)/>)",
                                       std::regex::optimize);
    std::cmatch version_match;
    if (std::regex_search(xml.data(), xml.data() + xml.size(), version_match, version_re)) {
        std::string attrs = version_match[1].str();
        doc.signature = extract_attribute(attrs, "signature");
        doc.file_format = extract_attribute(attrs, "fileFormat");
        doc.page_count = parse_int_or(extract_attribute(attrs, "nPages"), 0);
    }

    scan_constants(xml, [&](const std::string& name,
                            const std::string& attr_blob,
                            std::size_t inner_start,
                            std::size_t inner_end) {
        MsqConstant c;
        c.name = name;
        c.text.assign(xml.data() + inner_start, inner_end - inner_start);
        c.units = extract_attribute(attr_blob, "units");
        c.rows = parse_int_or(extract_attribute(attr_blob, "rows"), 0);
        c.cols = parse_int_or(extract_attribute(attr_blob, "cols"), 0);
        c.digits = parse_int_or(extract_attribute(attr_blob, "digits"), -1);
        doc.constants.push_back(std::move(c));
    });

    return doc;
}

std::string write_msq_text(
    std::string_view source_xml,
    const std::map<std::string, std::string>& updates) {

    // Splice strategy: walk all <constant> elements, accumulate the
    // unchanged ranges and update inner text where required. Builds
    // the output in a single pass with one allocation.
    std::string out;
    out.reserve(source_xml.size() + 64);
    std::size_t cursor = 0;

    scan_constants(source_xml, [&](const std::string& name,
                                   const std::string& /*attr_blob*/,
                                   std::size_t inner_start,
                                   std::size_t inner_end) {
        // Copy through everything before this constant's inner text.
        out.append(source_xml.substr(cursor, inner_start - cursor));
        auto it = updates.find(name);
        if (it != updates.end()) {
            out.append(it->second);
        } else {
            out.append(source_xml.substr(inner_start, inner_end - inner_start));
        }
        cursor = inner_end;
    });

    // Tail of the document after the final constant.
    out.append(source_xml.substr(cursor));
    return out;
}

// ---------------------------------------------------------------------------
// Formatters — mirror the Python _format_value / _fmt_scalar byte-for-byte.
// ---------------------------------------------------------------------------

std::string format_msq_scalar(double value) {
    // Integers (including values like 6.0) render without a decimal:
    //     6.0  → "6"
    //     6.5  → "6.5"
    // Non-integers use std::to_string's default formatting, which
    // matches Python's `str(float)` for the values MsqWriteService
    // cares about (legacy scalars are simple decimals, never
    // scientific notation in the fixture set).
    if (std::isfinite(value) && value == std::floor(value)) {
        long long as_int = static_cast<long long>(value);
        return std::to_string(as_int);
    }
    // Python's str(float) strips trailing zeros where possible; our
    // std::to_string emits 6 decimals. Trim to match.
    std::string s = std::to_string(value);
    // Strip trailing zeros after a decimal point, but leave at least
    // one digit after the point.
    auto dot = s.find('.');
    if (dot != std::string::npos) {
        std::size_t last_nonzero = s.find_last_not_of('0');
        if (last_nonzero > dot) {
            s.erase(last_nonzero + 1);
        } else {
            s.erase(dot);
        }
    }
    return s;
}

std::string format_msq_table(
    const std::vector<double>& values, int rows, int cols) {
    int effective_rows = rows > 0 ? rows : static_cast<int>(values.size());
    int effective_cols = cols > 0 ? cols : 1;

    std::string out;
    out.reserve(values.size() * 6 + 32);
    out += '\n';
    for (int r = 0; r < effective_rows; ++r) {
        int start = r * effective_cols;
        int end = start + effective_cols;
        if (start >= static_cast<int>(values.size())) break;
        out += "         ";
        bool first = true;
        for (int i = start; i < end && i < static_cast<int>(values.size()); ++i) {
            if (!first) out += ' ';
            out += format_msq_scalar(values[i]);
            first = false;
        }
        out += " \n";
    }
    out += "      ";
    return out;
}

// ---------------------------------------------------------------------------
// Insertion helpers
// ---------------------------------------------------------------------------

namespace {

// Build the attribute-list string for a new <constant> tag. Order
// matches MsqWriteService._constant_attribs on the Python side: name
// first, then units, then rows/cols (for tables), then digits.
std::string build_insertion_attribs(const MsqInsertion& ins) {
    std::string a;
    a.reserve(64);
    a += " name=\"";
    a += ins.name;
    a += '"';
    if (!ins.units.empty()) {
        a += " units=\"";
        a += ins.units;
        a += '"';
    }
    if (ins.rows > 0 || ins.cols > 0) {
        a += " rows=\"";
        a += std::to_string(ins.rows > 0 ? ins.rows : 1);
        a += "\" cols=\"";
        a += std::to_string(ins.cols > 0 ? ins.cols : 1);
        a += '"';
    }
    if (ins.digits >= 0) {
        a += " digits=\"";
        a += std::to_string(ins.digits);
        a += '"';
    }
    return a;
}

// Locate the position just before the first `</page>` closing tag in
// `xml`. Returns std::string_view::npos when the document has no
// <page> element (in which case insert_missing is a no-op).
std::size_t find_first_page_close(std::string_view xml) {
    return xml.find("</page>");
}

}  // namespace

std::string write_msq_text_with_insertions(
    std::string_view source_xml,
    const std::map<std::string, std::string>& updates,
    const std::vector<MsqInsertion>& insertions) {

    // First pass: apply inner-text updates using the existing seam.
    std::string updated = write_msq_text(source_xml, updates);

    if (insertions.empty()) {
        return updated;
    }

    // Build the set of constant names that already exist — these
    // insertions are silently skipped, matching the Python loop.
    std::set<std::string> existing_names;
    scan_constants(updated, [&](const std::string& name,
                                const std::string& /*attr_blob*/,
                                std::size_t /*inner_start*/,
                                std::size_t /*inner_end*/) {
        existing_names.insert(name);
    });

    // Also skip pcVariable collisions (the Python implementation treats
    // both <constant> and <pcVariable> as occupying the same namespace
    // when deciding what "already exists" means).
    {
        static const std::regex pcvar_re(R"(<pcVariable\b[^>]*\bname\s*=\s*[\"']([^\"']+)[\"'])",
                                          std::regex::optimize);
        auto it = updated.cbegin();
        auto end = updated.cend();
        std::cmatch match;
        while (std::regex_search(&*it, &*end, match, pcvar_re)) {
            existing_names.insert(match[1].str());
            auto advance = match.position(0) + match.length(0);
            if (advance <= 0) break;
            it += advance;
        }
    }

    // Compose the injected block. Each insertion becomes a
    // <constant ...>text</constant> node indented to match the
    // Python ElementTree SubElement output (8 spaces under <page>).
    std::string injected;
    injected.reserve(insertions.size() * 96);
    for (const auto& ins : insertions) {
        if (existing_names.count(ins.name)) continue;
        injected += "<constant";
        injected += build_insertion_attribs(ins);
        injected += '>';
        injected += ins.text;
        injected += "</constant>";
        existing_names.insert(ins.name);
    }

    if (injected.empty()) {
        return updated;
    }

    std::size_t page_close = find_first_page_close(updated);
    if (page_close == std::string::npos) {
        // No <page> element to inject into — nothing to do.
        return updated;
    }

    std::string out;
    out.reserve(updated.size() + injected.size());
    out.append(updated, 0, page_close);
    out.append(injected);
    out.append(updated, page_close, std::string::npos);
    return out;
}

std::size_t write_msq(
    const std::filesystem::path& source,
    const std::filesystem::path& destination,
    const std::map<std::string, std::string>& updates) {

    std::string source_xml = read_file(source);

    // Count how many of the requested updates actually correspond to
    // a <constant> in the source. The Python implementation silently
    // drops unknown names; we report the count for parity tests.
    std::size_t applied = 0;
    scan_constants(source_xml, [&](const std::string& name,
                                   const std::string& /*attr_blob*/,
                                   std::size_t /*inner_start*/,
                                   std::size_t /*inner_end*/) {
        if (updates.count(name)) {
            ++applied;
        }
    });

    std::string rewritten = write_msq_text(source_xml, updates);

    // Ensure the destination directory exists, mirroring the Python
    // MsqWriteService.save() behaviour.
    if (destination.has_parent_path()) {
        std::filesystem::create_directories(destination.parent_path());
    }
    std::ofstream stream(destination, std::ios::binary);
    if (!stream) {
        throw std::runtime_error(
            "Unable to open destination MSQ for write: " + destination.string());
    }
    stream.write(rewritten.data(), static_cast<std::streamsize>(rewritten.size()));
    return applied;
}

}  // namespace tuner_core
