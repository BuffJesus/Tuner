// SPDX-License-Identifier: MIT
//
// doctest unit tests for the Phase 17 Slice D bench-simulator
// controller. Uses an in-test MockTransport to verify command
// byte sequences and response-parse wiring without touching real
// serial hardware.

#include "doctest.h"

#include "tuner_core/bench_simulator_controller.hpp"
#include "tuner_core/transport.hpp"

#include <algorithm>
#include <cstring>
#include <deque>
#include <stdexcept>
#include <string>
#include <vector>

using namespace tuner_core::bench_simulator;
namespace ctrl = tuner_core::bench_simulator::controller;

namespace {

// In-test mock that records writes and replays a programmed read
// buffer. Doesn't model timing — every `read(size, timeout)` call
// returns up to `size` bytes from the head of the queue.
class MockTransport : public tuner_core::transport::Transport {
public:
    void open() override { open_ = true; }
    void close() override { open_ = false; }
    bool is_open() const override { return open_; }
    void clear_buffers() override {
        writes.clear();
        read_queue.clear();
    }

    std::size_t write(const std::uint8_t* data, std::size_t size) override {
        writes.insert(writes.end(), data, data + size);
        return size;
    }
    using tuner_core::transport::Transport::write;

    std::vector<std::uint8_t> read(std::size_t size, double /*timeout_s*/) override {
        std::vector<std::uint8_t> out;
        std::size_t take = std::min(size, read_queue.size());
        out.reserve(take);
        for (std::size_t i = 0; i < take; ++i) {
            out.push_back(read_queue.front());
            read_queue.pop_front();
        }
        return out;
    }

    // Helper: queue raw bytes for the controller to read.
    void queue_bytes(const std::vector<std::uint8_t>& bytes) {
        for (auto b : bytes) read_queue.push_back(b);
    }
    void queue_text(const std::string& text) {
        for (auto c : text) read_queue.push_back(static_cast<std::uint8_t>(c));
    }

    std::vector<std::uint8_t> writes;
    std::deque<std::uint8_t>  read_queue;
    bool open_ = true;
};

}  // namespace

TEST_CASE("set_wheel writes 'S' + 1 byte index") {
    MockTransport t;
    ctrl::set_wheel(t, 24);
    REQUIRE(t.writes.size() == 2);
    CHECK(t.writes[0] == 'S');
    CHECK(t.writes[1] == 24);
}

TEST_CASE("set_sweep writes 'r' + 6 LE bytes") {
    MockTransport t;
    ctrl::set_sweep(t, 250, 4000, 1000);
    REQUIRE(t.writes.size() == 7);
    CHECK(t.writes[0] == 'r');
    CHECK(t.writes[1] == 0xFA);  // 250 LE lo
    CHECK(t.writes[2] == 0x00);
    CHECK(t.writes[3] == 0xA0);  // 4000 LE lo
    CHECK(t.writes[4] == 0x0F);
    CHECK(t.writes[5] == 0xE8);  // 1000 LE lo
    CHECK(t.writes[6] == 0x03);
}

TEST_CASE("save_to_eeprom writes single 's' byte") {
    MockTransport t;
    ctrl::save_to_eeprom(t);
    CHECK(t.writes == std::vector<std::uint8_t>{'s'});
}

TEST_CASE("send_config v2 writes 'c' + 17 bytes") {
    MockTransport t;
    BenchSimulatorConfig c;
    c.wheel = 9;
    c.fixed_rpm = 3500;
    ctrl::send_config(t, c, kSchemaVersionV2);
    REQUIRE(t.writes.size() == 18);
    CHECK(t.writes[0] == 'c');
    CHECK(t.writes[1] == 9);  // wheel byte first after 'c'
}

TEST_CASE("send_config v1 writes 'c' + 10 bytes") {
    MockTransport t;
    BenchSimulatorConfig c;
    c.wheel = 17;
    ctrl::send_config(t, c, kSchemaVersionV1);
    REQUIRE(t.writes.size() == 11);
    CHECK(t.writes[0] == 'c');
    CHECK(t.writes[1] == 17);
}

TEST_CASE("send_config with unknown wire version writes nothing") {
    MockTransport t;
    BenchSimulatorConfig c;
    ctrl::send_config(t, c, 99);
    CHECK(t.writes.empty());
}

TEST_CASE("read_config sends 'C' and parses an 18-byte v2 reply") {
    MockTransport t;
    BenchSimulatorConfig src;
    src.wheel              = 42;
    src.fixed_rpm          = 5500;
    src.use_compression    = true;
    src.compression_type   = CompressionType::CYL8_4STROKE;
    src.compression_rpm    = 700;
    t.queue_bytes(encode_v2(src));

    auto cfg = ctrl::read_config(t);
    REQUIRE(cfg.has_value());
    CHECK(cfg->version == 2);
    CHECK(cfg->wheel == 42);
    CHECK(cfg->fixed_rpm == 5500);
    CHECK(cfg->use_compression);
    CHECK(cfg->compression_type == CompressionType::CYL8_4STROKE);

    REQUIRE(t.writes.size() == 1);
    CHECK(t.writes[0] == 'C');
}

TEST_CASE("read_config sends 'C' and parses an 11-byte v1 reply") {
    MockTransport t;
    BenchSimulatorConfig src;
    src.wheel = 13;
    t.queue_bytes(encode_v1(src));

    auto cfg = ctrl::read_config(t);
    REQUIRE(cfg.has_value());
    CHECK(cfg->version == 1);
    CHECK(cfg->wheel == 13);
}

TEST_CASE("read_config returns nullopt when transport delivers nothing") {
    MockTransport t;
    auto cfg = ctrl::read_config(t, 0.05);  // tight timeout, empty queue
    CHECK_FALSE(cfg.has_value());
}

TEST_CASE("read_config returns nullopt on wrong-size response") {
    MockTransport t;
    t.queue_bytes({0xAA, 0xBB, 0xCC, 0xDD});
    auto cfg = ctrl::read_config(t, 0.05);
    CHECK_FALSE(cfg.has_value());
}

TEST_CASE("read_wheel_count sends 'n' and parses single decimal line") {
    MockTransport t;
    t.queue_text("64\r\n");
    auto n = ctrl::read_wheel_count(t);
    REQUIRE(n.has_value());
    CHECK(*n == 64);
    REQUIRE(t.writes.size() == 1);
    CHECK(t.writes[0] == 'n');
}

TEST_CASE("read_current_wheel_index sends 'N' and parses decimal line") {
    MockTransport t;
    t.queue_text("9\r\n");
    auto idx = ctrl::read_current_wheel_index(t);
    REQUIRE(idx.has_value());
    CHECK(*idx == 9);
    CHECK(t.writes[0] == 'N');
}

TEST_CASE("read_current_wheel_size sends 'p' and parses decimal line") {
    MockTransport t;
    t.queue_text("360\r\n");
    auto size = ctrl::read_current_wheel_size(t);
    REQUIRE(size.has_value());
    CHECK(*size == 360);
    CHECK(t.writes[0] == 'p');
}

TEST_CASE("read_current_rpm sends 'R' and parses decimal line") {
    MockTransport t;
    t.queue_text("2500\r\n");
    auto rpm = ctrl::read_current_rpm(t);
    REQUIRE(rpm.has_value());
    CHECK(*rpm == 2500);
    CHECK(t.writes[0] == 'R');
}

TEST_CASE("list_wheel_names sends 'L' and parses line-delimited names") {
    MockTransport t;
    t.queue_text("60-2 crank only\r\n36-1 crank only\r\nGM LS1 crank and cam\r\n");
    auto names = ctrl::list_wheel_names(t, /*expected_count=*/3);
    REQUIRE(names.size() == 3);
    CHECK(names[0] == "60-2 crank only");
    CHECK(names[1] == "36-1 crank only");
    CHECK(names[2] == "GM LS1 crank and cam");
    CHECK(t.writes[0] == 'L');
}

TEST_CASE("list_wheel_names tolerates missing trailing newline") {
    MockTransport t;
    t.queue_text("alpha\r\nbeta\r\ngamma");
    auto names = ctrl::list_wheel_names(t, /*expected_count=*/3, /*timeout_s=*/0.2);
    REQUIRE(names.size() == 3);
    CHECK(names[2] == "gamma");
}

TEST_CASE("list_wheel_names returns empty when nothing arrives") {
    MockTransport t;
    auto names = ctrl::list_wheel_names(t, 0, 0.05);
    CHECK(names.empty());
}

TEST_CASE("read_current_wheel_pattern sends 'P' and parses CSV+degrees response") {
    MockTransport t;
    t.queue_text("0,1,0,1,0,1,0,3\r\n360\r\n");
    auto pat = ctrl::read_current_wheel_pattern(t);
    REQUIRE(pat.has_value());
    CHECK(pat->edge_states == std::vector<std::uint8_t>{0, 1, 0, 1, 0, 1, 0, 3});
    CHECK(pat->wheel_degrees == 360);
    CHECK(t.writes[0] == 'P');
}

TEST_CASE("read_current_wheel_pattern returns nullopt on incomplete response") {
    MockTransport t;
    t.queue_text("0,1,0\r\n");  // only one line — degrees missing
    auto pat = ctrl::read_current_wheel_pattern(t, 0.05);
    CHECK_FALSE(pat.has_value());
}

TEST_CASE("select_next_wheel sends 'X' and reads back the new wheel name") {
    MockTransport t;
    t.queue_text("OPTISPARK_LT1\r\n");  // wheel name as the firmware would emit
    auto name = ctrl::select_next_wheel(t);
    CHECK(name == "OPTISPARK_LT1");
    CHECK(t.writes[0] == 'X');
}

TEST_CASE("select_next_wheel returns empty when no response arrives") {
    MockTransport t;
    auto name = ctrl::select_next_wheel(t, 0.05);
    CHECK(name.empty());
}

TEST_CASE("make_fixed_rpm_config builds a FIXED_RPM config with target value") {
    auto c = ctrl::make_fixed_rpm_config(3500, /*wheel=*/9);
    CHECK(c.mode == RpmMode::FIXED_RPM);
    CHECK(c.fixed_rpm == 3500);
    CHECK(c.wheel == 9);
}

TEST_CASE("make_sweep_config builds a LINEAR_SWEPT_RPM config with range") {
    auto c = ctrl::make_sweep_config(500, 7500, 1500, /*wheel=*/16);
    CHECK(c.mode == RpmMode::LINEAR_SWEPT_RPM);
    CHECK(c.sweep_low_rpm == 500);
    CHECK(c.sweep_high_rpm == 7500);
    CHECK(c.sweep_interval == 1500);
    CHECK(c.wheel == 16);
}

TEST_CASE("make_compression_enabled_config builds a v2-only compression config") {
    auto c = ctrl::make_compression_enabled_config(
        CompressionType::CYL8_4STROKE, 600, 0, false, /*wheel=*/24);
    CHECK(c.use_compression);
    CHECK(c.compression_type == CompressionType::CYL8_4STROKE);
    CHECK(c.compression_rpm == 600);
    CHECK(c.compression_offset == 0);
    CHECK_FALSE(c.compression_dynamic);
    CHECK(c.wheel == 24);
}

TEST_CASE("full connect-then-status sequence simulates real operator workflow") {
    MockTransport t;
    // Operator opens the port and the host queries C → n → L → R.
    // Firmware replies are queued in order.

    // C response: 18-byte v2 config.
    BenchSimulatorConfig fw_state;
    fw_state.wheel = 9;
    fw_state.mode = RpmMode::FIXED_RPM;
    fw_state.fixed_rpm = 2500;
    t.queue_bytes(encode_v2(fw_state));

    auto cfg = ctrl::read_config(t);
    REQUIRE(cfg.has_value());
    CHECK(cfg->wheel == 9);
    CHECK(cfg->fixed_rpm == 2500);

    // n response: wheel count
    t.queue_text("64\r\n");
    auto n = ctrl::read_wheel_count(t);
    REQUIRE(n.has_value());
    CHECK(*n == 64);

    // L response: name list (truncated for brevity)
    t.queue_text("DIZZY_FOUR_CYLINDER\r\nDIZZY_SIX_CYLINDER\r\nDIZZY_EIGHT_CYLINDER\r\n");
    auto names = ctrl::list_wheel_names(t, 3, 0.2);
    REQUIRE(names.size() == 3);
    CHECK(names[2] == "DIZZY_EIGHT_CYLINDER");

    // R response: live RPM
    t.queue_text("2487\r\n");
    auto rpm = ctrl::read_current_rpm(t);
    REQUIRE(rpm.has_value());
    CHECK(*rpm == 2487);

    // Verify the host emitted the expected command sequence.
    REQUIRE(t.writes.size() == 4);
    CHECK(t.writes[0] == 'C');
    CHECK(t.writes[1] == 'n');
    CHECK(t.writes[2] == 'L');
    CHECK(t.writes[3] == 'R');
}

TEST_CASE("set_compression flow via send_config + set_wheel sequences correctly") {
    MockTransport t;
    auto c = ctrl::make_compression_enabled_config(
        CompressionType::CYL8_4STROKE, 600, 0, false, /*wheel=*/24);
    ctrl::set_wheel(t, c.wheel);
    ctrl::send_config(t, c, kSchemaVersionV2);

    REQUIRE(t.writes.size() == 2 + 18);
    // First two bytes: S, 24
    CHECK(t.writes[0] == 'S');
    CHECK(t.writes[1] == 24);
    // Next 18: c + 17 config bytes
    CHECK(t.writes[2] == 'c');
    // The compression-enable byte is at configTable offset 7 (after
    // version, wheel, mode, 4 × u16 = 11 bytes), so on the wire
    // (with version dropped) it's at offset 10 — verify the byte
    // came across.
    CHECK(t.writes[2 + 11] == 1);                                 // use_compression
    CHECK(t.writes[2 + 12] == static_cast<std::uint8_t>(
                                    CompressionType::CYL8_4STROKE));
}
