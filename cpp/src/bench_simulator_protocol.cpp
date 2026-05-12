// SPDX-License-Identifier: MIT
//
// Implementation of the bench-simulator host protocol layer.

#include "tuner_core/bench_simulator_protocol.hpp"

#include <algorithm>
#include <charconv>
#include <cstring>

namespace tuner_core::bench_simulator {

namespace {

void put_u16_le(std::vector<std::uint8_t>& out, std::uint16_t v) {
    out.push_back(static_cast<std::uint8_t>(v & 0xFF));
    out.push_back(static_cast<std::uint8_t>((v >> 8) & 0xFF));
}

// Trim leading + trailing ASCII whitespace (incl. \r, \n, space, tab).
std::string_view trim(std::string_view sv) noexcept {
    while (!sv.empty() && (sv.front() == ' ' || sv.front() == '\t' ||
                           sv.front() == '\r' || sv.front() == '\n')) {
        sv.remove_prefix(1);
    }
    while (!sv.empty() && (sv.back() == ' ' || sv.back() == '\t' ||
                           sv.back() == '\r' || sv.back() == '\n')) {
        sv.remove_suffix(1);
    }
    return sv;
}

// Parse decimal u32. Returns nullopt for empty / non-numeric /
// out-of-range input. Uses from_chars to match the firmware's
// `Serial.println(unsigned)` decimal formatting.
std::optional<std::uint32_t> parse_u32(std::string_view sv) noexcept {
    if (sv.empty()) return std::nullopt;
    std::uint32_t value = 0;
    const auto* first = sv.data();
    const auto* last  = sv.data() + sv.size();
    auto [ptr, ec] = std::from_chars(first, last, value);
    if (ec != std::errc{} || ptr != last) return std::nullopt;
    return value;
}

// Split on '\n'; trailing '\r' on each line is stripped. Trailing
// empty line after a final '\n' is dropped.
std::vector<std::string_view> split_lines(std::string_view text) {
    std::vector<std::string_view> out;
    std::size_t start = 0;
    for (std::size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\n') {
            std::size_t end = i;
            if (end > start && text[end - 1] == '\r') --end;
            out.emplace_back(text.data() + start, end - start);
            start = i + 1;
        }
    }
    if (start < text.size()) {
        std::size_t end = text.size();
        if (end > start && text[end - 1] == '\r') --end;
        out.emplace_back(text.data() + start, end - start);
    }
    return out;
}

}  // namespace

std::vector<std::uint8_t> build_set_wheel(std::uint8_t wheel_index) {
    return {Command::SET_WHEEL, wheel_index};
}

std::vector<std::uint8_t> build_set_sweep_rpm(std::uint16_t low_rpm,
                                              std::uint16_t high_rpm,
                                              std::uint16_t interval_ms) {
    std::vector<std::uint8_t> out;
    out.reserve(7);
    out.push_back(Command::SET_SWEEP_RPM);
    put_u16_le(out, low_rpm);
    put_u16_le(out, high_rpm);
    put_u16_le(out, interval_ms);
    return out;
}

std::vector<std::uint8_t> build_send_config(const BenchSimulatorConfig& config,
                                            std::uint8_t wire_version) {
    std::vector<std::uint8_t> payload;
    if (wire_version == kSchemaVersionV2) {
        payload = encode_v2(config);
    } else if (wire_version == kSchemaVersionV1) {
        payload = encode_v1(config);
    } else {
        return {};
    }
    // Firmware reads sizeof(configTable)-1 bytes starting at byte
    // index 1 — version byte is NOT transmitted. Drop payload[0].
    std::vector<std::uint8_t> out;
    out.reserve(payload.size());  // 'c' + (size-1) bytes
    out.push_back(Command::SEND_CONFIG);
    out.insert(out.end(), payload.begin() + 1, payload.end());
    return out;
}

std::optional<BenchSimulatorConfig> parse_config_response(std::span<const std::uint8_t> payload) {
    return decode_auto(payload);
}

std::vector<std::string> parse_wheel_list_response(std::string_view text) {
    auto lines = split_lines(text);
    std::vector<std::string> out;
    out.reserve(lines.size());
    for (auto sv : lines) {
        // Per-line trim handles stray whitespace; empty lines are dropped.
        auto trimmed = trim(sv);
        if (trimmed.empty()) continue;
        out.emplace_back(trimmed);
    }
    return out;
}

std::optional<std::uint32_t> parse_decimal_line(std::string_view text) {
    auto trimmed = trim(text);
    if (trimmed.empty()) return std::nullopt;
    // If multiple lines arrived, parse only the first non-empty one.
    auto lines = split_lines(trimmed);
    for (auto sv : lines) {
        auto t = trim(sv);
        if (!t.empty()) return parse_u32(t);
    }
    return std::nullopt;
}

std::optional<WheelPatternResponse> parse_wheel_pattern_response(std::string_view text) {
    auto lines = split_lines(text);
    // Drop empty lines but keep order.
    std::vector<std::string_view> non_empty;
    non_empty.reserve(lines.size());
    for (auto sv : lines) {
        auto t = trim(sv);
        if (!t.empty()) non_empty.push_back(t);
    }
    if (non_empty.size() < 2) return std::nullopt;

    WheelPatternResponse out;

    // Line 1: CSV of decimal edge states.
    std::string_view csv = non_empty[0];
    std::size_t start = 0;
    while (start <= csv.size()) {
        std::size_t end = csv.find(',', start);
        if (end == std::string_view::npos) end = csv.size();
        auto tok = trim(csv.substr(start, end - start));
        if (tok.empty()) {
            // Trailing comma is tolerated (firmware emits trailing
            // println after the last value, not a trailing comma);
            // but a genuine empty token inside the list is rejected.
            if (end == csv.size()) break;
            return std::nullopt;
        }
        auto v = parse_u32(tok);
        if (!v.has_value() || *v > 0xFF) return std::nullopt;
        out.edge_states.push_back(static_cast<std::uint8_t>(*v));
        if (end == csv.size()) break;
        start = end + 1;
    }
    if (out.edge_states.empty()) return std::nullopt;

    // Line 2: wheel_degrees as decimal.
    auto deg = parse_u32(non_empty[1]);
    if (!deg.has_value() || *deg > 0xFFFF) return std::nullopt;
    out.wheel_degrees = static_cast<std::uint16_t>(*deg);
    return out;
}

std::string parse_next_wheel_response(std::string_view text) {
    auto lines = split_lines(text);
    for (auto sv : lines) {
        auto t = trim(sv);
        if (!t.empty()) return std::string(t);
    }
    return {};
}

}  // namespace tuner_core::bench_simulator
