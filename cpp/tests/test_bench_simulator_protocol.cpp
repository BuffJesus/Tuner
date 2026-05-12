// SPDX-License-Identifier: MIT
//
// doctest unit tests for the Phase 17 Slice C bench-simulator
// host protocol layer.

#include "doctest.h"

#include "tuner_core/bench_simulator_protocol.hpp"

#include <string>
#include <vector>

using namespace tuner_core::bench_simulator;

TEST_CASE("baud rate is 115200 per firmware comms.cpp:51") {
    CHECK(kBaudRate == 115200);
}

TEST_CASE("single-byte command builders emit one byte each") {
    CHECK(build_noop()                  == std::vector<std::uint8_t>{'a'});
    CHECK(build_request_config()        == std::vector<std::uint8_t>{'C'});
    CHECK(build_request_wheel_list()    == std::vector<std::uint8_t>{'L'});
    CHECK(build_request_wheel_count()   == std::vector<std::uint8_t>{'n'});
    CHECK(build_request_current_wheel() == std::vector<std::uint8_t>{'N'});
    CHECK(build_request_wheel_size()    == std::vector<std::uint8_t>{'p'});
    CHECK(build_request_wheel_pattern() == std::vector<std::uint8_t>{'P'});
    CHECK(build_request_current_rpm()   == std::vector<std::uint8_t>{'R'});
    CHECK(build_save_config()           == std::vector<std::uint8_t>{'s'});
    CHECK(build_next_wheel()            == std::vector<std::uint8_t>{'X'});
}

TEST_CASE("Command constants match firmware case labels") {
    CHECK(Command::NOOP                  == 'a');
    CHECK(Command::SEND_CONFIG           == 'c');
    CHECK(Command::REQUEST_CONFIG        == 'C');
    CHECK(Command::REQUEST_WHEEL_LIST    == 'L');
    CHECK(Command::REQUEST_WHEEL_COUNT   == 'n');
    CHECK(Command::REQUEST_CURRENT_WHEEL == 'N');
    CHECK(Command::REQUEST_WHEEL_SIZE    == 'p');
    CHECK(Command::REQUEST_WHEEL_PATTERN == 'P');
    CHECK(Command::REQUEST_CURRENT_RPM   == 'R');
    CHECK(Command::SET_SWEEP_RPM         == 'r');
    CHECK(Command::SAVE_CONFIG           == 's');
    CHECK(Command::SET_WHEEL             == 'S');
    CHECK(Command::NEXT_WHEEL            == 'X');
}

TEST_CASE("build_set_wheel emits 'S' + 1-byte index") {
    auto out = build_set_wheel(24);  // GM_LS1_CRANK_AND_CAM
    CHECK(out == std::vector<std::uint8_t>{'S', 24});
    auto edge = build_set_wheel(0);
    CHECK(edge == std::vector<std::uint8_t>{'S', 0});
    auto max = build_set_wheel(0xFF);
    CHECK(max == std::vector<std::uint8_t>{'S', 0xFF});
}

TEST_CASE("build_set_sweep_rpm emits 'r' + 6 bytes (3 × u16 LE)") {
    auto out = build_set_sweep_rpm(250, 4000, 1000);
    REQUIRE(out.size() == 7);
    CHECK(out[0] == 'r');
    // low_rpm = 250 = 0x00FA  → LE: FA 00
    CHECK(out[1] == 0xFA);
    CHECK(out[2] == 0x00);
    // high_rpm = 4000 = 0x0FA0 → LE: A0 0F
    CHECK(out[3] == 0xA0);
    CHECK(out[4] == 0x0F);
    // interval = 1000 = 0x03E8 → LE: E8 03
    CHECK(out[5] == 0xE8);
    CHECK(out[6] == 0x03);
}

TEST_CASE("build_set_sweep_rpm handles boundary u16 values") {
    auto zero = build_set_sweep_rpm(0, 0, 0);
    CHECK(zero == std::vector<std::uint8_t>{'r', 0, 0, 0, 0, 0, 0});

    auto max = build_set_sweep_rpm(0xFFFF, 0xFFFF, 0xFFFF);
    CHECK(max == std::vector<std::uint8_t>{'r', 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF});
}

TEST_CASE("build_send_config v2 emits 'c' + 17 bytes (version byte dropped)") {
    BenchSimulatorConfig c;
    c.wheel = 9;
    auto out = build_send_config(c, kSchemaVersionV2);
    REQUIRE(out.size() == 18);  // 'c' + 17
    CHECK(out[0] == 'c');
    // The 17 payload bytes are encode_v2(c) bytes [1..18]: skipping
    // version byte 2 at index 0 of the encoded payload.
    auto v2_full = encode_v2(c);
    REQUIRE(v2_full.size() == 18);
    for (std::size_t i = 0; i < 17; ++i) {
        CAPTURE(i);
        CHECK(out[i + 1] == v2_full[i + 1]);
    }
    // First payload byte should be the wheel index (configTable[1]).
    CHECK(out[1] == 9);
}

TEST_CASE("build_send_config v1 emits 'c' + 10 bytes") {
    BenchSimulatorConfig c;
    c.wheel = 42;
    auto out = build_send_config(c, kSchemaVersionV1);
    REQUIRE(out.size() == 11);  // 'c' + 10
    CHECK(out[0] == 'c');
    CHECK(out[1] == 42);  // wheel byte first after 'c'
}

TEST_CASE("build_send_config returns empty vector for unknown wire version") {
    BenchSimulatorConfig c;
    CHECK(build_send_config(c, 0).empty());
    CHECK(build_send_config(c, 3).empty());
    CHECK(build_send_config(c, 99).empty());
}

TEST_CASE("parse_config_response round-trips v2 encoded payload") {
    BenchSimulatorConfig c;
    c.wheel              = 24;
    c.mode               = RpmMode::FIXED_RPM;
    c.fixed_rpm          = 3500;
    c.use_compression    = true;
    c.compression_type   = CompressionType::CYL8_4STROKE;

    auto payload = encode_v2(c);
    auto back = parse_config_response(payload);
    REQUIRE(back.has_value());
    CHECK(back->wheel == 24);
    CHECK(back->mode == RpmMode::FIXED_RPM);
    CHECK(back->fixed_rpm == 3500);
    CHECK(back->use_compression);
    CHECK(back->compression_type == CompressionType::CYL8_4STROKE);
}

TEST_CASE("parse_config_response handles v1 payloads") {
    BenchSimulatorConfig c;
    c.wheel = 17;
    auto payload = encode_v1(c);
    auto back = parse_config_response(payload);
    REQUIRE(back.has_value());
    CHECK(back->version == 1);
    CHECK(back->wheel == 17);
}

TEST_CASE("parse_config_response rejects wrong-size buffers") {
    std::vector<std::uint8_t> garbage(7, 0xAA);
    CHECK_FALSE(parse_config_response(garbage).has_value());

    std::vector<std::uint8_t> empty;
    CHECK_FALSE(parse_config_response(empty).has_value());
}

TEST_CASE("parse_wheel_list_response handles \\r\\n line endings") {
    std::string text = "60-2 crank only\r\n36-1 crank only\r\nGM LS1 crank and cam\r\n";
    auto lines = parse_wheel_list_response(text);
    REQUIRE(lines.size() == 3);
    CHECK(lines[0] == "60-2 crank only");
    CHECK(lines[1] == "36-1 crank only");
    CHECK(lines[2] == "GM LS1 crank and cam");
}

TEST_CASE("parse_wheel_list_response handles bare \\n line endings") {
    std::string text = "alpha\nbeta\ngamma";  // no trailing newline
    auto lines = parse_wheel_list_response(text);
    REQUIRE(lines.size() == 3);
    CHECK(lines[0] == "alpha");
    CHECK(lines[1] == "beta");
    CHECK(lines[2] == "gamma");
}

TEST_CASE("parse_wheel_list_response drops empty trailing lines") {
    std::string text = "one\r\ntwo\r\n\r\n";
    auto lines = parse_wheel_list_response(text);
    REQUIRE(lines.size() == 2);
    CHECK(lines[0] == "one");
    CHECK(lines[1] == "two");
}

TEST_CASE("parse_wheel_list_response on empty input is empty") {
    CHECK(parse_wheel_list_response("").empty());
    CHECK(parse_wheel_list_response("\r\n").empty());
    CHECK(parse_wheel_list_response("\n\n").empty());
}

TEST_CASE("parse_decimal_line parses single decimal value") {
    CHECK(parse_decimal_line("64\r\n").value() == 64);
    CHECK(parse_decimal_line("0\r\n").value() == 0);
    CHECK(parse_decimal_line("65535\r\n").value() == 65535);
    CHECK(parse_decimal_line("4294967295\n").value() == 4294967295u);  // max u32
}

TEST_CASE("parse_decimal_line tolerates whitespace and missing newline") {
    CHECK(parse_decimal_line("  42  ").value() == 42);
    CHECK(parse_decimal_line("\t9000\t\r\n").value() == 9000);
    CHECK(parse_decimal_line("3500").value() == 3500);
}

TEST_CASE("parse_decimal_line rejects empty / non-numeric / out-of-range") {
    CHECK_FALSE(parse_decimal_line("").has_value());
    CHECK_FALSE(parse_decimal_line("\r\n").has_value());
    CHECK_FALSE(parse_decimal_line("abc\r\n").has_value());
    CHECK_FALSE(parse_decimal_line("12 34\r\n").has_value());      // trailing garbage
    CHECK_FALSE(parse_decimal_line("99999999999999999\r\n").has_value());  // overflow u32
}

TEST_CASE("parse_wheel_pattern_response parses CSV edges + degrees") {
    std::string text = "0,1,0,1,0,1,0,3\r\n360\r\n";
    auto out = parse_wheel_pattern_response(text);
    REQUIRE(out.has_value());
    CHECK(out->edge_states == std::vector<std::uint8_t>{0, 1, 0, 1, 0, 1, 0, 3});
    CHECK(out->wheel_degrees == 360);
}

TEST_CASE("parse_wheel_pattern_response handles 720-degree wheels") {
    std::string text = "1,2,4,7,0,3,5,6\r\n720\r\n";
    auto out = parse_wheel_pattern_response(text);
    REQUIRE(out.has_value());
    CHECK(out->wheel_degrees == 720);
    REQUIRE(out->edge_states.size() == 8);
    CHECK(out->edge_states[3] == 7);
}

TEST_CASE("parse_wheel_pattern_response rejects malformed input") {
    // Only one line — no degrees.
    CHECK_FALSE(parse_wheel_pattern_response("0,1,0\r\n").has_value());
    // Non-decimal degrees.
    CHECK_FALSE(parse_wheel_pattern_response("0,1\r\nabc\r\n").has_value());
    // Non-decimal in edge CSV.
    CHECK_FALSE(parse_wheel_pattern_response("0,foo,1\r\n360\r\n").has_value());
    // Empty input.
    CHECK_FALSE(parse_wheel_pattern_response("").has_value());
    // Empty edges line.
    CHECK_FALSE(parse_wheel_pattern_response("\r\n360\r\n").has_value());
    // Edge value > 0xFF.
    CHECK_FALSE(parse_wheel_pattern_response("256,0\r\n360\r\n").has_value());
}

TEST_CASE("parse_wheel_pattern_response handles 1-edge minimum wheel") {
    auto out = parse_wheel_pattern_response("0\r\n360\r\n");
    REQUIRE(out.has_value());
    CHECK(out->edge_states.size() == 1);
    CHECK(out->wheel_degrees == 360);
}

TEST_CASE("parse_wheel_pattern_response accepts bare \\n line endings") {
    auto out = parse_wheel_pattern_response("0,1,2\n360\n");
    REQUIRE(out.has_value());
    CHECK(out->edge_states == std::vector<std::uint8_t>{0, 1, 2});
    CHECK(out->wheel_degrees == 360);
}

TEST_CASE("parse_next_wheel_response trims and returns the wheel name") {
    CHECK(parse_next_wheel_response("8-1 crank only (R6)\r\n") == "8-1 crank only (R6)");
    CHECK(parse_next_wheel_response("GM 7X\n") == "GM 7X");
    CHECK(parse_next_wheel_response("  60-2 crank only  ") == "60-2 crank only");
    CHECK(parse_next_wheel_response("") == "");
    CHECK(parse_next_wheel_response("\r\n\r\n") == "");
}

TEST_CASE("set_sweep round trip — host emits 'r' + 6 LE bytes the firmware would read") {
    // Replicates the firmware-side decoding from comms.cpp:128-130.
    auto bytes = build_set_sweep_rpm(750, 6500, 2000);
    REQUIRE(bytes.size() == 7);
    REQUIRE(bytes[0] == 'r');
    auto decode_u16_le = [&](std::size_t offset) -> std::uint16_t {
        return static_cast<std::uint16_t>(bytes[offset]) |
               (static_cast<std::uint16_t>(bytes[offset + 1]) << 8);
    };
    CHECK(decode_u16_le(1) == 750);
    CHECK(decode_u16_le(3) == 6500);
    CHECK(decode_u16_le(5) == 2000);
}

TEST_CASE("build_send_config v2 firmware can reconstruct the full configTable from the 17 transmitted bytes") {
    // Simulates the firmware-side flow at comms.cpp:67-73: the
    // firmware leaves config[0] (version) at its current value
    // and writes transmitted bytes into config[1..sizeof-1].
    BenchSimulatorConfig original;
    original.wheel              = 42;
    original.fixed_rpm          = 3500;
    original.use_compression    = true;
    original.compression_type   = CompressionType::CYL8_4STROKE;
    original.compression_rpm    = 555;

    auto wire = build_send_config(original, kSchemaVersionV2);
    REQUIRE(wire.size() == 18);

    // Build the byte buffer the firmware would have in memory: a
    // pre-existing version byte (whatever the firmware already had)
    // followed by the 17 transmitted bytes at offsets 1..17.
    std::vector<std::uint8_t> firmware_memory(18, 0);
    firmware_memory[0] = kSchemaVersionV2;  // firmware persists its own version
    for (std::size_t i = 1; i < 18; ++i) {
        firmware_memory[i] = wire[i];  // wire[1..17] go to memory[1..17]
    }
    auto reconstructed = decode_v2(firmware_memory);
    REQUIRE(reconstructed.has_value());
    CHECK(reconstructed->wheel == 42);
    CHECK(reconstructed->fixed_rpm == 3500);
    CHECK(reconstructed->use_compression);
    CHECK(reconstructed->compression_type == CompressionType::CYL8_4STROKE);
    CHECK(reconstructed->compression_rpm == 555);
}

TEST_CASE("parse_wheel_list_response on a 64-line list returns all entries in order") {
    // Synthesize the kind of payload the firmware emits for `L` on
    // the modified fork — one decoder name per line, 64 names total.
    std::string text;
    for (int i = 0; i < 64; ++i) {
        text += "wheel_" + std::to_string(i) + "\r\n";
    }
    auto lines = parse_wheel_list_response(text);
    REQUIRE(lines.size() == 64);
    CHECK(lines[0] == "wheel_0");
    CHECK(lines[63] == "wheel_63");
    for (std::size_t i = 0; i < 64; ++i) {
        CAPTURE(i);
        CHECK(lines[i] == ("wheel_" + std::to_string(i)));
    }
}
