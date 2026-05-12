// SPDX-License-Identifier: MIT
//
// Implementation of the bench-simulator controller layer.

#include "tuner_core/bench_simulator_controller.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>

namespace tuner_core::bench_simulator::controller {

namespace {

// Wait until either `expected_bytes` are buffered or the timeout
// runs out. Reads in small chunks so we can poll for completion
// without burning the whole timeout on a single blocking call.
std::vector<std::uint8_t> read_until_size(transport::Transport& t,
                                          std::size_t expected_bytes,
                                          double timeout_s) {
    using clock = std::chrono::steady_clock;
    const auto deadline =
        clock::now() +
        std::chrono::milliseconds(static_cast<long long>(timeout_s * 1000.0));
    std::vector<std::uint8_t> buf;
    buf.reserve(expected_bytes);

    constexpr double kChunkTimeoutS = 0.05;
    while (buf.size() < expected_bytes && clock::now() < deadline) {
        auto remaining = expected_bytes - buf.size();
        auto chunk = t.read(remaining, kChunkTimeoutS);
        if (!chunk.empty()) buf.insert(buf.end(), chunk.begin(), chunk.end());
    }
    return buf;
}

// Read into a text accumulator until `expected_lines` newlines
// have been observed or the timeout exhausts. Reads in small
// chunks; defensive against partial-line arrivals.
std::string read_until_lines(transport::Transport& t,
                             std::size_t expected_lines,
                             double timeout_s) {
    using clock = std::chrono::steady_clock;
    const auto deadline =
        clock::now() +
        std::chrono::milliseconds(static_cast<long long>(timeout_s * 1000.0));
    std::string acc;

    constexpr double kChunkTimeoutS = 0.05;
    constexpr std::size_t kChunkSize = 256;
    while (clock::now() < deadline) {
        std::size_t newlines = static_cast<std::size_t>(
            std::count(acc.begin(), acc.end(), '\n'));
        if (expected_lines > 0 && newlines >= expected_lines) break;

        auto chunk = t.read(kChunkSize, kChunkTimeoutS);
        if (!chunk.empty()) {
            acc.append(reinterpret_cast<const char*>(chunk.data()),
                       chunk.size());
        } else if (expected_lines == 0 && !acc.empty()) {
            // No expected count, no new data, but we already have
            // something — stop early to avoid burning the timeout.
            break;
        }
    }
    return acc;
}

}  // namespace

void set_wheel(transport::Transport& t, std::uint8_t wheel_index) {
    t.write(build_set_wheel(wheel_index));
}

void send_config(transport::Transport& t,
                 const BenchSimulatorConfig& config,
                 std::uint8_t wire_version) {
    auto bytes = build_send_config(config, wire_version);
    if (!bytes.empty()) t.write(bytes);
}

void set_sweep(transport::Transport& t,
               std::uint16_t low_rpm,
               std::uint16_t high_rpm,
               std::uint16_t interval_ms) {
    t.write(build_set_sweep_rpm(low_rpm, high_rpm, interval_ms));
}

void save_to_eeprom(transport::Transport& t) {
    t.write(build_save_config());
}

std::optional<BenchSimulatorConfig> read_config(transport::Transport& t,
                                                double timeout_s) {
    t.write(build_request_config());
    // Read up to the v2 size; if the firmware only sends 11 bytes
    // it'll arrive within the chunk timeout and decode_auto routes
    // it to v1 via the size check.
    auto bytes = read_until_size(t, kV2ByteSize, timeout_s);
    if (bytes.size() == kV1ByteSize || bytes.size() == kV2ByteSize) {
        return parse_config_response(bytes);
    }
    return std::nullopt;
}

std::vector<std::string> list_wheel_names(transport::Transport& t,
                                          std::size_t expected_count,
                                          double timeout_s) {
    t.write(build_request_wheel_list());
    auto text = read_until_lines(t, expected_count, timeout_s);
    return parse_wheel_list_response(text);
}

std::optional<std::uint32_t> read_wheel_count(transport::Transport& t,
                                              double timeout_s) {
    t.write(build_request_wheel_count());
    auto text = read_until_lines(t, 1, timeout_s);
    return parse_decimal_line(text);
}

std::optional<std::uint32_t> read_current_wheel_index(transport::Transport& t,
                                                      double timeout_s) {
    t.write(build_request_current_wheel());
    auto text = read_until_lines(t, 1, timeout_s);
    return parse_decimal_line(text);
}

std::optional<std::uint32_t> read_current_wheel_size(transport::Transport& t,
                                                     double timeout_s) {
    t.write(build_request_wheel_size());
    auto text = read_until_lines(t, 1, timeout_s);
    return parse_decimal_line(text);
}

std::optional<WheelPatternResponse> read_current_wheel_pattern(
    transport::Transport& t, double timeout_s) {
    t.write(build_request_wheel_pattern());
    auto text = read_until_lines(t, 2, timeout_s);
    return parse_wheel_pattern_response(text);
}

std::optional<std::uint32_t> read_current_rpm(transport::Transport& t,
                                              double timeout_s) {
    t.write(build_request_current_rpm());
    auto text = read_until_lines(t, 1, timeout_s);
    return parse_decimal_line(text);
}

std::string select_next_wheel(transport::Transport& t, double timeout_s) {
    t.write(build_next_wheel());
    auto text = read_until_lines(t, 1, timeout_s);
    return parse_next_wheel_response(text);
}

BenchSimulatorConfig make_fixed_rpm_config(std::uint16_t rpm,
                                           std::uint8_t wheel) {
    BenchSimulatorConfig c;
    c.wheel     = wheel;
    c.mode      = RpmMode::FIXED_RPM;
    c.fixed_rpm = rpm;
    return c;
}

BenchSimulatorConfig make_sweep_config(std::uint16_t low_rpm,
                                       std::uint16_t high_rpm,
                                       std::uint16_t interval_ms,
                                       std::uint8_t wheel) {
    BenchSimulatorConfig c;
    c.wheel          = wheel;
    c.mode           = RpmMode::LINEAR_SWEPT_RPM;
    c.sweep_low_rpm  = low_rpm;
    c.sweep_high_rpm = high_rpm;
    c.sweep_interval = interval_ms;
    return c;
}

BenchSimulatorConfig make_compression_enabled_config(CompressionType type,
                                                     std::uint16_t target_rpm,
                                                     std::uint16_t offset,
                                                     bool dynamic,
                                                     std::uint8_t wheel) {
    BenchSimulatorConfig c;
    c.wheel              = wheel;
    c.use_compression    = true;
    c.compression_type   = type;
    c.compression_rpm    = target_rpm;
    c.compression_offset = offset;
    c.compression_dynamic = dynamic;
    return c;
}

}  // namespace tuner_core::bench_simulator::controller
