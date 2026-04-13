// SPDX-License-Identifier: MIT
#include "tuner_core/ini_dialog_parser.hpp"

#include <algorithm>
#include <cctype>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core {

namespace {

// Trim whitespace from both ends.
std::string_view trim(std::string_view sv) {
    while (!sv.empty() && std::isspace(static_cast<unsigned char>(sv.front()))) sv.remove_prefix(1);
    while (!sv.empty() && std::isspace(static_cast<unsigned char>(sv.back()))) sv.remove_suffix(1);
    return sv;
}

// Split a comma-separated value string, trimming each part.
// Respects quoted strings (double quotes).
std::vector<std::string> parse_csv(std::string_view value) {
    std::vector<std::string> parts;
    bool in_quote = false;
    std::string current;
    for (char c : value) {
        if (c == '"') {
            in_quote = !in_quote;
            continue;
        }
        if (c == ',' && !in_quote) {
            auto t = trim(std::string_view(current));
            parts.push_back(std::string(t));
            current.clear();
            continue;
        }
        current.push_back(c);
    }
    auto t = trim(std::string_view(current));
    if (!t.empty()) parts.push_back(std::string(t));
    return parts;
}

// Check if a string looks like a visibility expression: starts with { and ends with }.
bool is_visibility(const std::string& s) {
    return s.size() >= 2 && s.front() == '{' && s.back() == '}';
}

// Find the first visibility expression in parts[start..].
std::string find_visibility(const std::vector<std::string>& parts, std::size_t start) {
    for (std::size_t i = start; i < parts.size(); ++i) {
        if (is_visibility(parts[i])) return parts[i];
    }
    return {};
}

// Find the first non-empty, non-visibility, non-"{}" parameter name in parts[start..].
std::string find_parameter(const std::vector<std::string>& parts, std::size_t start) {
    for (std::size_t i = start; i < parts.size(); ++i) {
        if (parts[i].empty() || parts[i] == "{}") continue;
        if (is_visibility(parts[i])) continue;
        return parts[i];
    }
    return {};
}

// Case-insensitive compare for section headers.
std::string to_lower(std::string_view sv) {
    std::string out;
    out.reserve(sv.size());
    for (char c : sv) out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    return out;
}

}  // namespace

IniDialogSection parse_dialogs(const std::vector<std::string>& lines) {
    IniDialogSection result;
    IniDialog* current = nullptr;
    bool in_user_defined = false;

    for (const auto& raw_line : lines) {
        auto sv = trim(raw_line);
        if (sv.empty() || sv.front() == ';' || sv.front() == '#') continue;

        // Section header.
        if (sv.front() == '[') {
            in_user_defined = (to_lower(sv) == "[userdefined]");
            continue;
        }
        if (!in_user_defined) continue;

        // key = value.
        auto eq = sv.find('=');
        if (eq == std::string_view::npos) continue;
        auto key = trim(sv.substr(0, eq));
        auto value = trim(sv.substr(eq + 1));

        if (key == "dialog") {
            auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniDialog d;
            d.dialog_id = parts[0];
            d.title = (parts.size() > 1) ? parts[1] : parts[0];
            d.axis_hint = (parts.size() > 2) ? parts[2] : "";
            result.dialogs.push_back(std::move(d));
            current = &result.dialogs.back();
            continue;
        }

        if (current == nullptr) continue;

        if (key == "field") {
            auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniDialogField f;
            f.label = parts[0];
            f.visibility_expression = find_visibility(parts, 1);
            f.parameter_name = find_parameter(parts, 1);
            f.is_static_text = f.parameter_name.empty();
            current->fields.push_back(std::move(f));
        } else if (key == "panel") {
            auto parts = parse_csv(value);
            if (parts.empty()) continue;
            IniDialogPanelRef p;
            p.target = parts[0];
            p.position = find_parameter(parts, 1);
            p.visibility_expression = find_visibility(parts, 1);
            current->panels.push_back(std::move(p));
        }
    }

    return result;
}

}  // namespace tuner_core
