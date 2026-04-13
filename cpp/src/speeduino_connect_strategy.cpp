// SPDX-License-Identifier: MIT
//
// Implementation of `speeduino_connect_strategy.hpp`. Direct port of
// the connect-time helpers in `SpeeduinoControllerClient`.

#include "tuner_core/speeduino_connect_strategy.hpp"

#include "tuner_core/speeduino_value_codec.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <stdexcept>
#include <string>

namespace tuner_core::speeduino_connect_strategy {

namespace {

std::string strip(std::string_view s) {
    std::size_t start = 0;
    while (start < s.size() && std::isspace(static_cast<unsigned char>(s[start]))) ++start;
    std::size_t end = s.size();
    while (end > start && std::isspace(static_cast<unsigned char>(s[end - 1]))) --end;
    return std::string(s.substr(start, end - start));
}

// Try to parse a leading float from `s`. Mirrors Python `float(str)`
// applied to a stripped string: any trailing junk causes ValueError,
// so we require the entire string to consume cleanly.
std::optional<double> parse_float_strict(const std::string& s) {
    if (s.empty()) return std::nullopt;
    try {
        std::size_t consumed = 0;
        double v = std::stod(s, &consumed);
        if (consumed != s.size()) return std::nullopt;
        return v;
    } catch (...) {
        return std::nullopt;
    }
}

}  // namespace

char command_char(std::string_view raw, char fallback) noexcept {
    if (raw.empty()) return fallback;
    return raw[0];
}

int effective_blocking_factor(bool is_table,
                              std::optional<int> fw_blocking,
                              std::optional<int> fw_table_blocking,
                              std::optional<int> def_blocking,
                              std::optional<int> def_table_blocking) noexcept {
    // Match the Python `or` shortcut: a value of 0 is treated as
    // missing because `None or 0` is falsy. The optional inputs
    // already encode missing-ness; the explicit `> 0` check below
    // closes the "value present but zero" case.
    auto take = [](std::optional<int> v) -> std::optional<int> {
        if (v.has_value() && *v > 0) return v;
        return std::nullopt;
    };

    if (is_table) {
        if (auto v = take(fw_table_blocking))  return *v;
        if (auto v = take(def_table_blocking)) return *v;
    }
    if (auto v = take(fw_blocking))  return *v;
    if (auto v = take(def_blocking)) return *v;
    return 128;  // conservative default for AVR boards
}

std::vector<char> signature_probe_candidates(std::string_view query_command,
                                             std::string_view version_info_command) {
    std::vector<char> result;
    auto seen = std::vector<char>();  // small set, linear scan is fine
    auto try_add = [&](std::string_view raw) {
        const char c = command_char(raw, '\0');
        if (c == '\0') return;
        for (char s : seen) if (s == c) return;
        seen.push_back(c);
        result.push_back(c);
    };
    try_add(query_command);
    try_add(version_info_command);
    try_add("F");
    try_add("Q");
    try_add("S");
    return result;
}

std::vector<std::optional<int>> baud_probe_candidates(std::optional<int> current_baud) {
    std::vector<std::optional<int>> result;
    std::vector<int> seen;
    auto try_add = [&](std::optional<int> v) {
        if (!v.has_value()) return;
        for (int s : seen) if (s == *v) return;
        seen.push_back(*v);
        result.push_back(v);
    };
    try_add(current_baud);
    try_add(115200);
    try_add(230400);
    try_add(57600);
    try_add(9600);
    if (result.empty()) {
        result.push_back(std::nullopt);
    }
    return result;
}

double connect_delay_seconds(const std::map<std::string, std::string>& metadata) {
    static const std::array<const char*, 3> keys = {
        "controllerConnectDelay",
        "connectDelay",
        "interWriteDelay",
    };
    for (const char* key : keys) {
        auto it = metadata.find(key);
        if (it == metadata.end()) continue;
        const std::string& raw = it->second;
        // Python: `if raw_value` — non-empty truthy check.
        if (raw.empty()) continue;
        // `str(raw_value).strip().split(",", 1)[0]` — split on first
        // comma, take the head, strip again.
        std::string stripped = strip(raw);
        std::size_t comma = stripped.find(',');
        if (comma != std::string::npos) {
            stripped = stripped.substr(0, comma);
        }
        stripped = strip(stripped);
        auto parsed = parse_float_strict(stripped);
        if (!parsed.has_value()) continue;
        if (*parsed > 0.0) {
            return *parsed / 1000.0;
        }
        // Python: `if delay_ms > 0:` — falls through to default if
        // the parsed value is <= 0. Continue scanning the next key.
        continue;
    }
    return 1.5;
}

// ---------------------------------------------------------------------
// Capability header parse / derived flags
// ---------------------------------------------------------------------

CapabilityHeader parse_capability_header(
    std::optional<std::span<const std::uint8_t>> payload) {
    CapabilityHeader header;
    if (!payload.has_value()) return header;
    const auto& p = *payload;
    if (p.size() < 6) return header;
    if (p[0] != 0x00) return header;
    // Python: `payload[2] << 8 | payload[3]`. That's big-endian u16
    // — note this is the capability query, not the XCP spec.
    header.parsed = true;
    header.serial_protocol_version = p[1];
    header.blocking_factor =
        (static_cast<int>(p[2]) << 8) | static_cast<int>(p[3]);
    header.table_blocking_factor =
        (static_cast<int>(p[4]) << 8) | static_cast<int>(p[5]);
    return header;
}

std::string capability_source(const CapabilityHeader& header) {
    return header.parsed ? "serial+definition" : "definition";
}

std::optional<int> compute_live_data_size(
    const std::vector<OutputChannelField>& channels) {
    if (channels.empty()) return std::nullopt;
    int max_end = 0;
    bool seen = false;
    for (const auto& ch : channels) {
        const int offset = ch.offset.value_or(0);
        // `speeduino_value_codec::parse_data_type` throws on unknown
        // types — mirror the Python `KeyError` bubble-up.
        const auto type = tuner_core::speeduino_value_codec::parse_data_type(ch.data_type);
        const int size = tuner_core::speeduino_value_codec::data_size_bytes(type);
        const int end = offset + size;
        if (!seen || end > max_end) {
            max_end = end;
            seen = true;
        }
    }
    return max_end;
}

bool has_any_output_channel(const std::vector<std::string>& channel_names,
                            const std::vector<std::string>& targets) {
    // Linear scan — channel lists are small enough (< 200 in
    // production) that building a hash set would not pay off.
    for (const auto& target : targets) {
        for (const auto& name : channel_names) {
            if (name == target) return true;
        }
    }
    return false;
}

bool is_experimental_u16p2_signature(std::string_view signature) noexcept {
    // Uppercase comparison. Iterate byte-by-byte and check for the
    // 5-char "U16P2" substring.
    std::string upper;
    upper.reserve(signature.size());
    for (char c : signature) {
        upper.push_back(static_cast<char>(
            std::toupper(static_cast<unsigned char>(c))));
    }
    return upper.find("U16P2") != std::string::npos;
}

bool should_accept_probe_response(char command, std::string_view response) noexcept {
    if (response.empty()) return false;
    // `response == command`: Python compares string equality. The
    // echoed single-char is rejected because Speeduino sometimes
    // echoes the command without a real response.
    if (response.size() == 1 && response[0] == command) return false;
    // `F` never returns the real signature on Speeduino — it returns
    // the firmware identifier string (same role as a version banner).
    if (command == 'F') return false;
    return true;
}

}  // namespace tuner_core::speeduino_connect_strategy
