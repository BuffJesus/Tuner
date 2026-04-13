// SPDX-License-Identifier: MIT
//
// tuner_core::IniPreprocessor implementation. Direct port of
// `tuner.parsers.common.preprocess_ini_lines()`.

#include "tuner_core/ini_preprocessor.hpp"

#include <algorithm>
#include <utility>

namespace tuner_core {

namespace {

// Strip leading + trailing whitespace, matching Python's str.strip().
std::string_view strip_view(std::string_view text) {
    auto begin = text.begin();
    auto end = text.end();
    while (begin != end && std::isspace(static_cast<unsigned char>(*begin))) ++begin;
    while (end != begin && std::isspace(static_cast<unsigned char>(*(end - 1)))) --end;
    return std::string_view(&*begin, static_cast<std::size_t>(end - begin));
}

// Split a stripped line into (first_token, rest_with_leading_ws_stripped).
// Mirrors Python `stripped.split(None, 1)` which splits on any whitespace
// run and returns at most two parts.
std::pair<std::string, std::string> split_first_token(std::string_view stripped) {
    std::size_t i = 0;
    while (i < stripped.size() && !std::isspace(static_cast<unsigned char>(stripped[i]))) {
        ++i;
    }
    std::string first(stripped.substr(0, i));
    while (i < stripped.size() && std::isspace(static_cast<unsigned char>(stripped[i]))) {
        ++i;
    }
    std::string rest(stripped.substr(i));
    return {std::move(first), std::move(rest)};
}

// Whether every entry on the conditional stack is "active". Mirrors
// the Python `_in_active_branch()` closure.
bool in_active_branch(const std::vector<std::pair<bool, bool>>& stack) {
    for (const auto& [active, _] : stack) {
        if (!active) return false;
    }
    return true;
}

}  // namespace

std::vector<std::string> preprocess_ini_lines(
    const std::vector<std::string>& raw_lines,
    const std::set<std::string>& active_settings) {

    // ---- Phase 1: collect file-scope #set / #unset defaults ----
    std::set<std::string> file_settings;
    int nesting = 0;
    for (const auto& line : raw_lines) {
        std::string_view stripped = strip_view(line);
        if (stripped.empty()) continue;

        auto [directive, rest] = split_first_token(stripped);
        if (directive == "#if") {
            ++nesting;
        } else if (directive == "#endif") {
            nesting = std::max(0, nesting - 1);
        } else if ((directive == "#set" || directive == "#unset") && nesting == 0) {
            std::string symbol(strip_view(rest));
            if (directive == "#set") {
                file_settings.insert(symbol);
            } else {
                file_settings.erase(symbol);
            }
        }
    }

    // ---- Effective settings: user (active_settings) wins ----
    std::set<std::string> settings = file_settings;
    settings.insert(active_settings.begin(), active_settings.end());

    // ---- Phase 2: evaluate conditionals ----
    std::vector<std::string> result;
    result.reserve(raw_lines.size());

    // Stack entries are (branch_active, has_seen_else). branch_active
    // already folds in parent-branch activity.
    std::vector<std::pair<bool, bool>> stack;

    for (const auto& line : raw_lines) {
        std::string_view stripped = strip_view(line);

        if (stripped.empty()) {
            if (in_active_branch(stack)) result.push_back(line);
            continue;
        }

        auto [directive, rest] = split_first_token(stripped);

        if (directive == "#if") {
            std::string symbol(strip_view(rest));
            bool branch_active =
                in_active_branch(stack) && settings.count(symbol) > 0;
            stack.emplace_back(branch_active, false);
            continue;
        }

        if (directive == "#else") {
            if (!stack.empty()) {
                auto [was_active, seen_else] = stack.back();
                if (!seen_else) {
                    bool parent_active = true;
                    for (std::size_t i = 0; i + 1 < stack.size(); ++i) {
                        if (!stack[i].first) { parent_active = false; break; }
                    }
                    stack.back() = {parent_active && !was_active, true};
                }
            }
            continue;
        }

        if (directive == "#endif") {
            if (!stack.empty()) stack.pop_back();
            continue;
        }

        if (directive == "#set" || directive == "#unset") {
            // Consumed in phase 1; drop silently here.
            continue;
        }

        // All other `#`-lines (comments, #define, unrecognised) — keep
        // only when inside an active branch.
        if (!stripped.empty() && stripped[0] == '#') {
            if (!in_active_branch(stack)) continue;
            result.push_back(line);
            continue;
        }

        if (in_active_branch(stack)) {
            result.push_back(line);
        }
    }

    return result;
}

std::vector<std::string> preprocess_ini_text(
    std::string_view text,
    const std::set<std::string>& active_settings) {
    // Match Python text.splitlines(): split on \r\n / \r / \n, drop the
    // trailing empty after a final newline (Python does the same).
    std::vector<std::string> raw_lines;
    std::string current;
    for (std::size_t i = 0; i < text.size(); ++i) {
        char c = text[i];
        if (c == '\r') {
            raw_lines.push_back(std::move(current));
            current.clear();
            if (i + 1 < text.size() && text[i + 1] == '\n') ++i;
        } else if (c == '\n') {
            raw_lines.push_back(std::move(current));
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    if (!current.empty()) raw_lines.push_back(std::move(current));
    return preprocess_ini_lines(raw_lines, active_settings);
}

}  // namespace tuner_core
