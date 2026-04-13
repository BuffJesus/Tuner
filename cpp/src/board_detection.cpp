// SPDX-License-Identifier: MIT
//
// tuner_core::board_detection implementation. Pure logic — direct
// port of `BoardDetectionService`. Uses `<regex>` to mirror the Python
// regex patterns one-for-one (the alternatives are too varied to
// hand-roll cleanly — `TEENSY[\s_-]*4\.?1` already needs five distinct
// separator-and-dot combinations per family).

#include "tuner_core/board_detection.hpp"

#include <cctype>
#include <regex>
#include <string>
#include <utility>
#include <vector>

namespace tuner_core::board_detection {

namespace {

std::string uppercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return out;
}

const std::vector<std::pair<std::regex, BoardFamily>>& rules() {
    static const std::vector<std::pair<std::regex, BoardFamily>> table = []() {
        // Same patterns as the Python module — only difference is
        // `\b` is honoured by std::regex's ECMAScript dialect (default),
        // and `\.` matches a literal dot. Patterns target the
        // already-uppercased input so we don't need IGNORECASE.
        return std::vector<std::pair<std::regex, BoardFamily>>{
            {std::regex(R"(\b(T41|TEENSY[\s_-]*4\.?1|TEENSY41)\b)"),
             BoardFamily::TEENSY41},
            {std::regex(R"(\b(T36|TEENSY[\s_-]*3\.?6|TEENSY36)\b)"),
             BoardFamily::TEENSY36},
            {std::regex(R"(\b(T35|TEENSY[\s_-]*3\.?5|TEENSY35)\b)"),
             BoardFamily::TEENSY35},
            {std::regex(R"(\b(STM32F407|F407|DFU)\b)"),
             BoardFamily::STM32F407_DFU},
            {std::regex(R"(\b(ATMEGA2560|MEGA2560|ARDUINO\s+MEGA)\b)"),
             BoardFamily::ATMEGA2560},
        };
    }();
    return table;
}

}  // namespace

std::string_view to_string(BoardFamily family) noexcept {
    switch (family) {
        case BoardFamily::ATMEGA2560:    return "ATMEGA2560";
        case BoardFamily::TEENSY35:      return "TEENSY35";
        case BoardFamily::TEENSY36:      return "TEENSY36";
        case BoardFamily::TEENSY41:      return "TEENSY41";
        case BoardFamily::STM32F407_DFU: return "STM32F407_DFU";
    }
    return "";
}

std::optional<BoardFamily> detect_from_text(std::string_view text) {
    if (text.empty()) return std::nullopt;
    auto upper = uppercase(text);
    for (const auto& [pattern, family] : rules()) {
        if (std::regex_search(upper, pattern)) return family;
    }
    return std::nullopt;
}

std::optional<BoardFamily> detect_from_capabilities(
    bool experimental_u16p2,
    std::string_view signature) {
    if (!signature.empty()) {
        auto from_text = detect_from_text(signature);
        if (from_text.has_value()) return from_text;
    }
    if (experimental_u16p2) return BoardFamily::TEENSY41;
    return std::nullopt;
}

}  // namespace tuner_core::board_detection
