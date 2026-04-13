// SPDX-License-Identifier: MIT
#include "tuner_core/firmware_catalog.hpp"

#include <algorithm>
#include <cctype>
#include <regex>
#include <string>

namespace tuner_core::firmware_catalog {

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

}  // namespace

BoardFamily board_from_filename(const std::string& name) {
    std::string n = to_lower(name);
    if (n.find("teensy41") != std::string::npos || n.find("t41") != std::string::npos)
        return BoardFamily::TEENSY41;
    if (n.find("teensy36") != std::string::npos || n.find("t36") != std::string::npos)
        return BoardFamily::TEENSY36;
    if (n.find("teensy35") != std::string::npos || n.find("t35") != std::string::npos)
        return BoardFamily::TEENSY35;
    if (n.find("stm32") != std::string::npos || n.find("f407") != std::string::npos)
        return BoardFamily::STM32F407_DFU;
    if (n.find("atmega2560") != std::string::npos || n.find("mega") != std::string::npos)
        return BoardFamily::ATMEGA2560;
    return BoardFamily::UNKNOWN;
}

std::optional<std::string> version_from_filename(const std::string& name) {
    std::string n = to_lower(name);
    std::regex re(R"(v\d+(?:\.\d+)+)");
    std::smatch m;
    if (std::regex_search(n, m, re)) return m[0].str();
    return std::nullopt;
}

int score_entry(const CatalogEntry& entry, const ScoringContext& ctx) {
    if (entry.artifact_kind == ArtifactKind::DIAGNOSTIC && !ctx.include_diagnostic)
        return 0;

    int score = 1;

    if (ctx.preferred_board != BoardFamily::UNKNOWN) {
        if (entry.board_family == ctx.preferred_board)
            score += 100;
        else if (entry.board_family != BoardFamily::UNKNOWN)
            return 0;
    }

    // Build metadata text for experimental detection.
    std::string meta;
    if (!ctx.definition_signature.empty()) meta += to_lower(ctx.definition_signature) + " ";
    if (!ctx.definition_name.empty()) meta += to_lower(ctx.definition_name) + " ";
    if (!ctx.tune_signature.empty()) meta += to_lower(ctx.tune_signature) + " ";
    if (!ctx.tune_firmware_info.empty()) meta += to_lower(ctx.tune_firmware_info) + " ";
    bool experimental_requested = meta.find("experimental") != std::string::npos
                                || meta.find("u16p2") != std::string::npos;

    // Signature matching.
    if (!entry.firmware_signature.empty() && !ctx.definition_signature.empty()) {
        if (to_lower(entry.firmware_signature) == to_lower(ctx.definition_signature))
            score += 40;
    }
    if (!entry.firmware_signature.empty() && !ctx.tune_signature.empty()) {
        if (to_lower(entry.firmware_signature) == to_lower(ctx.tune_signature))
            score += 30;
    }
    if (!ctx.tune_filename.empty()) {
        std::string entry_name = to_lower(entry.filename);
        std::string tune_name = to_lower(ctx.tune_filename);
        // Compare just the last path component.
        auto last_sep = tune_name.find_last_of("/\\");
        if (last_sep != std::string::npos) tune_name = tune_name.substr(last_sep + 1);
        auto entry_sep = entry_name.find_last_of("/\\");
        if (entry_sep != std::string::npos) entry_name = entry_name.substr(entry_sep + 1);
        if (entry_name == tune_name) score += 35;
    }

    if (entry.preferred)
        score += (entry.is_experimental == experimental_requested) ? 20 : 8;

    if (!entry.version_label.empty() && meta.find(to_lower(entry.version_label)) != std::string::npos)
        score += 20;

    if (entry.is_experimental) {
        score += experimental_requested ? 10 : -5;
    } else {
        score += 3;
    }

    return score;
}

}  // namespace tuner_core::firmware_catalog
