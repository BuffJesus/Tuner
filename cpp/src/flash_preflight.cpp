// SPDX-License-Identifier: MIT
//
// tuner_core::flash_preflight implementation. Pure logic — direct
// port of `FlashPreflightService.validate` warning rules.

#include "tuner_core/flash_preflight.hpp"

#include <cctype>
#include <string>

namespace tuner_core::flash_preflight {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

std::string uppercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

// Mirror `BoardFamily.value` — the lowercased Python enum value
// (e.g. `BoardFamily.TEENSY41` → `"TEENSY41"` since the enum's `value`
// IS the identifier on the Python side via `class BoardFamily(str, Enum)`).
std::string_view board_family_value(BoardFamily f) noexcept {
    return board_detection::to_string(f);
}

}  // namespace

std::optional<std::string> signature_family(std::string_view value) {
    if (value.empty()) return std::nullopt;
    auto upper = uppercase(value);
    if (contains(upper, "U16P2")) return std::string("U16P2");
    if (contains(upper, "T41")) return std::string("T41");
    if (contains(upper, "T36")) return std::string("T36");
    if (contains(upper, "T35")) return std::string("T35");
    if (contains(upper, "STM32") || contains(upper, "F407")) return std::string("STM32F407");
    if (contains(upper, "MEGA") || contains(upper, "2560")) return std::string("ATMEGA2560");
    return std::nullopt;
}

Report validate(const PreflightInputs& inputs) {
    Report report;

    // Selected vs firmware-detected board mismatch → ERROR
    if (inputs.selected_board.has_value() &&
        inputs.firmware_entry.board_family.has_value() &&
        *inputs.selected_board != *inputs.firmware_entry.board_family) {
        report.errors.push_back(
            std::string("Selected board is ") +
            std::string(board_family_value(*inputs.selected_board)) +
            ", but firmware file looks like " +
            std::string(board_family_value(*inputs.firmware_entry.board_family)) +
            ".");
    }

    // Detected (live) vs firmware-detected board → WARNING
    if (inputs.detected_board.has_value() &&
        inputs.firmware_entry.board_family.has_value() &&
        *inputs.detected_board != *inputs.firmware_entry.board_family) {
        report.warnings.push_back(
            std::string("Detected board is ") +
            std::string(board_family_value(*inputs.detected_board)) +
            ", but firmware file looks like " +
            std::string(board_family_value(*inputs.firmware_entry.board_family)) +
            ".");
    }

    // Definition signature substring vs detected board → WARNING
    if (inputs.definition_signature.has_value() &&
        !inputs.definition_signature->empty() &&
        inputs.detected_board.has_value()) {
        auto sig_lower = lowercase(*inputs.definition_signature);
        if (contains(sig_lower, "t41") &&
            *inputs.detected_board != BoardFamily::TEENSY41) {
            report.warnings.push_back(
                "Loaded ECU definition signature indicates T41, but the detected board is different.");
        }
        if (contains(sig_lower, "t36") &&
            *inputs.detected_board != BoardFamily::TEENSY36) {
            report.warnings.push_back(
                "Loaded ECU definition signature indicates T36, but the detected board is different.");
        }
        if (contains(sig_lower, "t35") &&
            *inputs.detected_board != BoardFamily::TEENSY35) {
            report.warnings.push_back(
                "Loaded ECU definition signature indicates T35, but the detected board is different.");
        }
    }

    // Build the metadata text blob (lowercased) for substring checks.
    std::string metadata_text;
    auto append_meta = [&](const std::optional<std::string>& v) {
        if (v.has_value() && !v->empty()) {
            if (!metadata_text.empty()) metadata_text += " ";
            metadata_text += *v;
        }
    };
    append_meta(inputs.definition_signature);
    append_meta(inputs.tune_signature);
    append_meta(inputs.tune_firmware_info);
    metadata_text = lowercase(metadata_text);

    auto firmware_signature_family = signature_family(
        inputs.firmware_entry.firmware_signature.value_or(""));
    auto definition_signature_family = signature_family(
        inputs.definition_signature.value_or(""));
    auto tune_signature_family = signature_family(
        inputs.tune_signature.value_or(""));
    auto connected_signature_family = signature_family(
        inputs.connected_firmware_signature.value_or(""));

    // Experimental vs production check — capability fact takes
    // precedence over text heuristics.
    if (inputs.experimental_u16p2.has_value()) {
        bool connected_is_experimental = *inputs.experimental_u16p2;
        if (inputs.firmware_entry.is_experimental && !connected_is_experimental) {
            report.warnings.push_back(
                "Selected firmware is experimental (U16P2), but the connected "
                "controller is running production firmware.");
        } else if (!inputs.firmware_entry.is_experimental && connected_is_experimental) {
            report.warnings.push_back(
                "Selected firmware is production, but the connected "
                "controller is running experimental (U16P2) firmware.");
        }
    } else {
        bool metadata_is_experimental =
            contains(metadata_text, "experimental") || contains(metadata_text, "u16p2");
        if (inputs.firmware_entry.is_experimental) {
            if (!metadata_is_experimental) {
                report.warnings.push_back(
                    "Selected firmware is experimental, but the loaded INI/tune "
                    "metadata looks production.");
            }
        } else if (metadata_is_experimental) {
            report.warnings.push_back(
                "Selected firmware looks production, but the loaded INI/tune "
                "metadata looks experimental.");
        }
    }

    // Connected controller signature family vs selected firmware
    if (connected_signature_family.has_value() &&
        firmware_signature_family.has_value() &&
        *connected_signature_family != *firmware_signature_family) {
        report.warnings.push_back(
            "Selected firmware signature family (" + *firmware_signature_family +
            ") does not match the connected controller's firmware (" +
            *connected_signature_family + ").");
    }

    // Definition signature family vs firmware signature family
    if (firmware_signature_family.has_value() &&
        definition_signature_family.has_value() &&
        *firmware_signature_family != *definition_signature_family) {
        report.warnings.push_back(
            "Loaded ECU definition signature family does not match the "
            "selected firmware's paired signature family.");
    }

    // Tune signature family vs firmware signature family
    if (firmware_signature_family.has_value() &&
        tune_signature_family.has_value() &&
        *firmware_signature_family != *tune_signature_family) {
        report.warnings.push_back(
            "Loaded tune signature family does not match the "
            "selected firmware's paired signature family.");
    }

    // Paired tune basename mismatch
    if (inputs.firmware_entry.tune_path_basename.has_value() &&
        inputs.tune_source_basename.has_value()) {
        if (lowercase(*inputs.firmware_entry.tune_path_basename) !=
            lowercase(*inputs.tune_source_basename)) {
            report.warnings.push_back(
                "Selected firmware is paired with tune '" +
                *inputs.firmware_entry.tune_path_basename +
                "', but the loaded tune is '" +
                *inputs.tune_source_basename + "'.");
        }
    }

    // Version label not present in metadata text
    if (inputs.firmware_entry.version_label.has_value() &&
        !inputs.firmware_entry.version_label->empty() &&
        !metadata_text.empty()) {
        auto version_lower = lowercase(*inputs.firmware_entry.version_label);
        if (!contains(metadata_text, version_lower)) {
            report.warnings.push_back(
                "Firmware version " + *inputs.firmware_entry.version_label +
                " does not appear in the loaded INI/tune metadata.");
        }
    }

    report.ok = report.errors.empty();
    return report;
}

}  // namespace tuner_core::flash_preflight
