// SPDX-License-Identifier: MIT
#include "tuner_core/tune_storage_map.hpp"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <sstream>
#include <stdexcept>

namespace tuner_core::tune_storage_map {

namespace {

std::string strip(std::string_view s) {
    std::size_t start = 0;
    while (start < s.size()
        && std::isspace(static_cast<unsigned char>(s[start]))) ++start;
    std::size_t end = s.size();
    while (end > start
        && std::isspace(static_cast<unsigned char>(s[end - 1]))) --end;
    return std::string(s.substr(start, end - start));
}

std::string strip_quotes(std::string_view s) {
    auto t = strip(s);
    if (t.size() >= 2 && t.front() == '"' && t.back() == '"') {
        return t.substr(1, t.size() - 2);
    }
    return t;
}

// Split a macro-argument list on commas, respecting "quoted strings".
// "foo, bar, \"hello, world\", 1.0" → {"foo","bar","\"hello, world\"","1.0"}.
std::vector<std::string> split_args(std::string_view args) {
    std::vector<std::string> out;
    std::string cur;
    bool in_quotes = false;
    for (char c : args) {
        if (c == '"') {
            in_quotes = !in_quotes;
            cur += c;
        } else if (c == ',' && !in_quotes) {
            out.push_back(strip(cur));
            cur.clear();
        } else {
            cur += c;
        }
    }
    if (!cur.empty() || !args.empty()) {
        std::string trimmed = strip(cur);
        if (!trimmed.empty()) out.push_back(trimmed);
    }
    return out;
}

int parse_int(const std::string& s, int line_no) {
    try {
        std::size_t consumed = 0;
        int v = std::stoi(s, &consumed);
        if (consumed != s.size()) {
            throw std::invalid_argument(
                "tune_storage_map.h line " + std::to_string(line_no)
                + ": expected integer, got '" + s + "'");
        }
        return v;
    } catch (const std::out_of_range&) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": integer out of range: '" + s + "'");
    } catch (const std::invalid_argument&) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": expected integer, got '" + s + "'");
    }
}

double parse_double(const std::string& s, int line_no) {
    try {
        std::size_t consumed = 0;
        double v = std::stod(s, &consumed);
        if (consumed != s.size()) {
            throw std::invalid_argument(
                "tune_storage_map.h line " + std::to_string(line_no)
                + ": expected number, got '" + s + "'");
        }
        return v;
    } catch (...) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": expected number, got '" + s + "'");
    }
}

// Extract the (...) arguments from a macro invocation on a single
// line. Returns the substring between the outermost parens, or
// empty-optional if the line doesn't match `MACRO_NAME(...)` shape.
std::optional<std::string> extract_parens(std::string_view line) {
    auto lparen = line.find('(');
    if (lparen == std::string_view::npos) return std::nullopt;
    auto rparen = line.rfind(')');
    if (rparen == std::string_view::npos || rparen <= lparen) {
        return std::nullopt;
    }
    return std::string(line.substr(lparen + 1, rparen - lparen - 1));
}

void parse_scalar(const std::vector<std::string>& args,
                  int line_no, Entry& e) {
    if (args.size() != 8) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": TUNE_SCALAR expects 8 args, got "
            + std::to_string(args.size()));
    }
    e.kind = Kind::Scalar;
    e.semantic_id = args[0];
    e.page        = parse_int(args[1], line_no);
    e.offset      = parse_int(args[2], line_no);
    e.data_type   = args[3];
    e.scale       = parse_double(args[4], line_no);
    e.offset_v    = parse_double(args[5], line_no);
    e.units       = strip_quotes(args[6]);
    e.label       = strip_quotes(args[7]);
}

void parse_axis_dynamic(const std::vector<std::string>& args,
                        int line_no, Entry& e) {
    if (args.size() != 8) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": TUNE_AXIS_DYNAMIC expects 8 args, got "
            + std::to_string(args.size()));
    }
    e.kind = Kind::AxisDynamic;
    e.semantic_id  = args[0];
    e.page         = parse_int(args[1], line_no);
    e.offset       = parse_int(args[2], line_no);
    e.length       = parse_int(args[3], line_no);
    e.data_type    = args[4];
    e.controller_id = args[5];
    e.units        = strip_quotes(args[6]);
    e.label        = strip_quotes(args[7]);
}

void parse_axis(const std::vector<std::string>& args,
                int line_no, Entry& e) {
    if (args.size() != 9) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": TUNE_AXIS expects 9 args, got "
            + std::to_string(args.size()));
    }
    e.kind = Kind::Axis;
    e.semantic_id = args[0];
    e.page        = parse_int(args[1], line_no);
    e.offset      = parse_int(args[2], line_no);
    e.length      = parse_int(args[3], line_no);
    e.data_type   = args[4];
    e.scale       = parse_double(args[5], line_no);
    e.offset_v    = parse_double(args[6], line_no);
    e.units       = strip_quotes(args[7]);
    e.label       = strip_quotes(args[8]);
}

void parse_table(const std::vector<std::string>& args,
                 int line_no, Entry& e) {
    if (args.size() != 12) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": TUNE_TABLE expects 12 args, got "
            + std::to_string(args.size()));
    }
    e.kind = Kind::Table;
    e.semantic_id = args[0];
    e.page        = parse_int(args[1], line_no);
    e.offset      = parse_int(args[2], line_no);
    e.rows        = parse_int(args[3], line_no);
    e.cols        = parse_int(args[4], line_no);
    e.data_type   = args[5];
    e.scale       = parse_double(args[6], line_no);
    e.offset_v    = parse_double(args[7], line_no);
    e.x_axis_id   = args[8];
    e.y_axis_id   = args[9];
    e.units       = strip_quotes(args[10]);
    e.label       = strip_quotes(args[11]);
}

void parse_curve(const std::vector<std::string>& args,
                 int line_no, Entry& e) {
    if (args.size() != 10) {
        throw std::invalid_argument(
            "tune_storage_map.h line " + std::to_string(line_no)
            + ": TUNE_CURVE expects 10 args, got "
            + std::to_string(args.size()));
    }
    e.kind = Kind::Curve;
    e.semantic_id = args[0];
    e.page        = parse_int(args[1], line_no);
    e.offset      = parse_int(args[2], line_no);
    e.length      = parse_int(args[3], line_no);
    e.data_type   = args[4];
    e.scale       = parse_double(args[5], line_no);
    e.offset_v    = parse_double(args[6], line_no);
    e.x_axis_id   = args[7];
    e.units       = strip_quotes(args[8]);
    e.label       = strip_quotes(args[9]);
}

}  // namespace

const Entry* Map::find(std::string_view semantic_id) const {
    for (const auto& e : entries) {
        if (e.semantic_id == semantic_id) return &e;
    }
    return nullptr;
}

std::vector<const Entry*> Map::of_kind(Kind k) const {
    std::vector<const Entry*> out;
    for (const auto& e : entries) {
        if (e.kind == k) out.push_back(&e);
    }
    return out;
}

Map parse(std::string_view text) {
    Map out;
    std::string line;
    std::istringstream in(std::string{text});
    int line_no = 0;
    while (std::getline(in, line)) {
        ++line_no;
        auto stripped = strip(line);
        if (stripped.empty()) continue;
        if (stripped.rfind("//", 0) == 0) continue;
        if (stripped[0] == '*' || stripped[0] == '/'
            || stripped[0] == '#') continue;

        // Macro dispatch — first matching prefix wins.
        struct Dispatcher {
            const char* macro;
            void (*fn)(const std::vector<std::string>&, int, Entry&);
        };
        static const Dispatcher dispatchers[] = {
            {"TUNE_SCALAR", &parse_scalar},
            {"TUNE_AXIS",   &parse_axis},
            {"TUNE_TABLE",  &parse_table},
            {"TUNE_CURVE",  &parse_curve},
        };
        for (const auto& d : dispatchers) {
            std::size_t mlen = std::strlen(d.macro);
            if (stripped.size() <= mlen) continue;
            if (stripped.compare(0, mlen, d.macro) != 0) continue;
            // Next char must be '(' or whitespace then '('.
            std::size_t after = mlen;
            while (after < stripped.size()
                && std::isspace(static_cast<unsigned char>(stripped[after])))
                ++after;
            if (after >= stripped.size() || stripped[after] != '(') continue;

            auto args_str = extract_parens(stripped);
            if (!args_str) break;  // malformed — skip
            auto args = split_args(*args_str);
            Entry e;
            d.fn(args, line_no, e);
            out.entries.push_back(std::move(e));
            break;
        }
    }
    return out;
}

}  // namespace tuner_core::tune_storage_map
