// SPDX-License-Identifier: MIT
//
// doctest unit tests for the Phase 17 Slice B bench-simulator
// config codec.

#include "doctest.h"

#include "tuner_core/bench_simulator_config_codec.hpp"

#include <vector>

using namespace tuner_core::bench_simulator;

TEST_CASE("v2 schema size is 18 bytes, v1 is 11 bytes") {
    CHECK(kV2ByteSize == 18);
    CHECK(kV1ByteSize == 11);
}

TEST_CASE("encode_v2 produces exactly 18 bytes with version 2 leading") {
    BenchSimulatorConfig c;
    auto bytes = encode_v2(c);
    CHECK(bytes.size() == 18);
    CHECK(bytes[0] == 2);
}

TEST_CASE("encode_v1 produces exactly 11 bytes with version 1 leading") {
    BenchSimulatorConfig c;
    auto bytes = encode_v1(c);
    CHECK(bytes.size() == 11);
    CHECK(bytes[0] == 1);
}

TEST_CASE("encode_v2 round-trips through decode_v2 byte-for-byte") {
    BenchSimulatorConfig original{
        /*version*/ 2,
        /*wheel*/ 9,
        /*mode*/ RpmMode::FIXED_RPM,
        /*fixed_rpm*/ 3500,
        /*sweep_low_rpm*/ 750,
        /*sweep_high_rpm*/ 6500,
        /*sweep_interval*/ 2000,
        /*use_compression*/ true,
        /*compression_type*/ CompressionType::CYL8_4STROKE,
        /*compression_rpm*/ 600,
        /*compression_offset*/ 100,
        /*compression_dynamic*/ true,
    };

    auto bytes = encode_v2(original);
    auto round = decode_v2(bytes);
    REQUIRE(round.has_value());
    CHECK(round->version == 2);
    CHECK(round->wheel == 9);
    CHECK(round->mode == RpmMode::FIXED_RPM);
    CHECK(round->fixed_rpm == 3500);
    CHECK(round->sweep_low_rpm == 750);
    CHECK(round->sweep_high_rpm == 6500);
    CHECK(round->sweep_interval == 2000);
    CHECK(round->use_compression);
    CHECK(round->compression_type == CompressionType::CYL8_4STROKE);
    CHECK(round->compression_rpm == 600);
    CHECK(round->compression_offset == 100);
    CHECK(round->compression_dynamic);
}

TEST_CASE("encode_v1 round-trips through decode_v1 preserving non-compression fields") {
    BenchSimulatorConfig original;
    original.wheel           = 24;  // GM_LS1_CRANK_AND_CAM
    original.mode            = RpmMode::POT_RPM;
    original.fixed_rpm       = 1500;
    original.sweep_low_rpm   = 100;
    original.sweep_high_rpm  = 9000;
    original.sweep_interval  = 500;

    auto bytes = encode_v1(original);
    auto round = decode_v1(bytes);
    REQUIRE(round.has_value());
    CHECK(round->version == 1);
    CHECK(round->wheel == 24);
    CHECK(round->mode == RpmMode::POT_RPM);
    CHECK(round->fixed_rpm == 1500);
    CHECK(round->sweep_low_rpm == 100);
    CHECK(round->sweep_high_rpm == 9000);
    CHECK(round->sweep_interval == 500);
    // Compression fields come back as struct defaults — not from
    // the v1 wire, which doesn't carry them.
    CHECK_FALSE(round->use_compression);
    CHECK(round->compression_type == CompressionType::CYL1_4STROKE);
    CHECK(round->compression_rpm == 400);
    CHECK(round->compression_offset == 0);
    CHECK_FALSE(round->compression_dynamic);
}

TEST_CASE("encode_v2 packs u16 fields as little-endian") {
    BenchSimulatorConfig c;
    c.fixed_rpm = 0x1234;
    c.sweep_low_rpm = 0xABCD;
    auto bytes = encode_v2(c);
    // fixed_rpm at offset 3..5 — LE means low byte first.
    CHECK(bytes[3] == 0x34);
    CHECK(bytes[4] == 0x12);
    CHECK(bytes[5] == 0xCD);
    CHECK(bytes[6] == 0xAB);
}

TEST_CASE("encode_v2 packs bool fields as 0/1 bytes") {
    BenchSimulatorConfig c;
    c.use_compression    = true;
    c.compression_dynamic = false;
    auto bytes = encode_v2(c);
    CHECK(bytes[11] == 1);
    CHECK(bytes[17] == 0);

    c.use_compression    = false;
    c.compression_dynamic = true;
    bytes = encode_v2(c);
    CHECK(bytes[11] == 0);
    CHECK(bytes[17] == 1);
}

TEST_CASE("encode_v2 layout matches firmware configTable byte positions") {
    BenchSimulatorConfig c;
    c.wheel              = 42;
    c.mode               = RpmMode::FIXED_RPM;
    c.fixed_rpm          = 2500;
    c.sweep_low_rpm      = 250;
    c.sweep_high_rpm     = 4000;
    c.sweep_interval     = 1000;
    c.use_compression    = true;
    c.compression_type   = CompressionType::CYL6_4STROKE;
    c.compression_rpm    = 400;
    c.compression_offset = 0;
    c.compression_dynamic = false;
    auto bytes = encode_v2(c);

    CHECK(bytes[0] == 2);                // version
    CHECK(bytes[1] == 42);               // wheel
    CHECK(bytes[2] == 1);                // mode = FIXED_RPM
    CHECK(bytes[3] == (2500 & 0xFF));    // fixed_rpm LE lo
    CHECK(bytes[4] == ((2500 >> 8) & 0xFF));  // fixed_rpm LE hi
    CHECK(bytes[5] == (250 & 0xFF));     // sweep_low_rpm LE lo
    CHECK(bytes[6] == ((250 >> 8) & 0xFF));
    CHECK(bytes[7] == (4000 & 0xFF));    // sweep_high_rpm LE lo
    CHECK(bytes[8] == ((4000 >> 8) & 0xFF));
    CHECK(bytes[9] == (1000 & 0xFF));    // sweep_interval LE lo
    CHECK(bytes[10] == ((1000 >> 8) & 0xFF));
    CHECK(bytes[11] == 1);               // use_compression
    CHECK(bytes[12] == 4);               // compression_type CYL6_4STROKE
    CHECK(bytes[13] == (400 & 0xFF));    // compression_rpm LE lo
    CHECK(bytes[14] == ((400 >> 8) & 0xFF));
    CHECK(bytes[15] == 0);               // compression_offset LE lo
    CHECK(bytes[16] == 0);               // compression_offset LE hi
    CHECK(bytes[17] == 0);               // compression_dynamic
}

TEST_CASE("decode_v2 rejects wrong-size buffers") {
    std::vector<std::uint8_t> too_short(17, 2);
    too_short[0] = 2;
    CHECK_FALSE(decode_v2(too_short).has_value());

    std::vector<std::uint8_t> too_long(19, 0);
    too_long[0] = 2;
    CHECK_FALSE(decode_v2(too_long).has_value());

    std::vector<std::uint8_t> empty;
    CHECK_FALSE(decode_v2(empty).has_value());
}

TEST_CASE("decode_v2 rejects wrong leading version byte") {
    std::vector<std::uint8_t> v1_in_v2_slot(18, 0);
    v1_in_v2_slot[0] = 1;  // claims v1 but sized v2
    CHECK_FALSE(decode_v2(v1_in_v2_slot).has_value());

    std::vector<std::uint8_t> bogus_version(18, 0);
    bogus_version[0] = 99;
    CHECK_FALSE(decode_v2(bogus_version).has_value());
}

TEST_CASE("decode_v1 rejects wrong-size buffers and wrong version byte") {
    std::vector<std::uint8_t> too_short(10, 1);
    too_short[0] = 1;
    CHECK_FALSE(decode_v1(too_short).has_value());

    std::vector<std::uint8_t> too_long(12, 0);
    too_long[0] = 1;
    CHECK_FALSE(decode_v1(too_long).has_value());

    std::vector<std::uint8_t> v2_in_v1_slot(11, 0);
    v2_in_v1_slot[0] = 2;
    CHECK_FALSE(decode_v1(v2_in_v1_slot).has_value());
}

TEST_CASE("decode_auto picks v1 vs v2 by size and validates version byte") {
    BenchSimulatorConfig c;
    c.wheel = 17;

    auto v1_bytes = encode_v1(c);
    auto via_auto_v1 = decode_auto(v1_bytes);
    REQUIRE(via_auto_v1.has_value());
    CHECK(via_auto_v1->version == 1);
    CHECK(via_auto_v1->wheel == 17);

    auto v2_bytes = encode_v2(c);
    auto via_auto_v2 = decode_auto(v2_bytes);
    REQUIRE(via_auto_v2.has_value());
    CHECK(via_auto_v2->version == 2);
    CHECK(via_auto_v2->wheel == 17);

    // size 0 / 5 / 12 / 17 / 100 — none of these match a schema.
    for (std::size_t sz : {std::size_t{0}, std::size_t{5}, std::size_t{12},
                           std::size_t{17}, std::size_t{100}}) {
        std::vector<std::uint8_t> buf(sz, 0);
        if (sz > 0) buf[0] = 2;
        CHECK_FALSE(decode_auto(buf).has_value());
    }

    // size 18 with wrong version byte still fails decode_auto.
    std::vector<std::uint8_t> mismatched(18, 0);
    mismatched[0] = 1;
    CHECK_FALSE(decode_auto(mismatched).has_value());

    // size 11 with wrong version byte still fails decode_auto.
    std::vector<std::uint8_t> mismatched_v1(11, 0);
    mismatched_v1[0] = 2;
    CHECK_FALSE(decode_auto(mismatched_v1).has_value());
}

TEST_CASE("is_compression_type_firmware_supported gates the reserved entries") {
    CHECK(is_compression_type_firmware_supported(CompressionType::CYL2_4STROKE));
    CHECK(is_compression_type_firmware_supported(CompressionType::CYL4_4STROKE));
    CHECK(is_compression_type_firmware_supported(CompressionType::CYL6_4STROKE));
    CHECK(is_compression_type_firmware_supported(CompressionType::CYL8_4STROKE));
    // Firmware comments declare these "not initially supported".
    CHECK_FALSE(is_compression_type_firmware_supported(CompressionType::CYL1_4STROKE));
    CHECK_FALSE(is_compression_type_firmware_supported(CompressionType::CYL3_4STROKE));
}

TEST_CASE("compression_type_from_cylinders covers the four firmware-supported counts") {
    CHECK(compression_type_from_cylinders(2).value() == CompressionType::CYL2_4STROKE);
    CHECK(compression_type_from_cylinders(4).value() == CompressionType::CYL4_4STROKE);
    CHECK(compression_type_from_cylinders(6).value() == CompressionType::CYL6_4STROKE);
    CHECK(compression_type_from_cylinders(8).value() == CompressionType::CYL8_4STROKE);
}

TEST_CASE("compression_type_from_cylinders returns nullopt for unsupported counts") {
    // Firmware-reserved-but-unsupported and out-of-distribution
    // counts return nullopt so the UI can disable the option.
    CHECK_FALSE(compression_type_from_cylinders(1).has_value());
    CHECK_FALSE(compression_type_from_cylinders(3).has_value());
    CHECK_FALSE(compression_type_from_cylinders(5).has_value());
    CHECK_FALSE(compression_type_from_cylinders(7).has_value());
    CHECK_FALSE(compression_type_from_cylinders(10).has_value());
    CHECK_FALSE(compression_type_from_cylinders(12).has_value());
    CHECK_FALSE(compression_type_from_cylinders(0).has_value());
}

TEST_CASE("default-constructed config matches firmware default values") {
    BenchSimulatorConfig c;
    // Firmware globals.h defaults:
    //   wheel = FOUR_TWENTY_A (our catalog index 52), fixed_rpm = 2500,
    //   sweep_low_rpm = 250, sweep_high_rpm = 4000, sweep_interval = 1000,
    //   useCompression = false, compressionType = 0, compressionRPM = 400,
    //   compressionOffset = 0, compressionDynamic = false.
    // We track the firmware wheel default via the wheel-pattern
    // catalog directly rather than baking the index into the
    // codec, so we only assert the remaining fields here.
    CHECK(c.version == 2);
    CHECK(c.mode == RpmMode::LINEAR_SWEPT_RPM);
    CHECK(c.fixed_rpm == 2500);
    CHECK(c.sweep_low_rpm == 250);
    CHECK(c.sweep_high_rpm == 4000);
    CHECK(c.sweep_interval == 1000);
    CHECK_FALSE(c.use_compression);
    CHECK(c.compression_rpm == 400);
    CHECK(c.compression_offset == 0);
    CHECK_FALSE(c.compression_dynamic);
}

TEST_CASE("RpmMode enum values match firmware enums.h order") {
    CHECK(static_cast<std::uint8_t>(RpmMode::LINEAR_SWEPT_RPM) == 0);
    CHECK(static_cast<std::uint8_t>(RpmMode::FIXED_RPM)        == 1);
    CHECK(static_cast<std::uint8_t>(RpmMode::POT_RPM)          == 2);
}

TEST_CASE("CompressionType enum values match firmware globals.h order") {
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL1_4STROKE) == 0);
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL2_4STROKE) == 1);
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL3_4STROKE) == 2);
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL4_4STROKE) == 3);
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL6_4STROKE) == 4);
    CHECK(static_cast<std::uint8_t>(CompressionType::CYL8_4STROKE) == 5);
}

TEST_CASE("v1 wire bytes match the v2 prefix bytes for the shared 11-byte header") {
    BenchSimulatorConfig c;
    c.wheel          = 13;
    c.mode           = RpmMode::FIXED_RPM;
    c.fixed_rpm      = 3000;
    c.sweep_low_rpm  = 800;
    c.sweep_high_rpm = 5500;
    c.sweep_interval = 1500;

    auto v1_bytes = encode_v1(c);
    auto v2_bytes = encode_v2(c);
    REQUIRE(v1_bytes.size() == 11);
    REQUIRE(v2_bytes.size() == 18);
    // v1 schema byte 0 = 1, v2 schema byte 0 = 2; otherwise the
    // first 11 bytes carry the same payload fields in the same order.
    CHECK(v1_bytes[0] == 1);
    CHECK(v2_bytes[0] == 2);
    for (std::size_t i = 1; i < 11; ++i) {
        CAPTURE(i);
        CHECK(v1_bytes[i] == v2_bytes[i]);
    }
}

TEST_CASE("compression_rpm and compression_offset round-trip across u16 range") {
    for (std::uint16_t v : std::initializer_list<std::uint16_t>{
             0, 1, 0xFF, 0x100, 0x1234, 0xFFFE, 0xFFFF}) {
        BenchSimulatorConfig c;
        c.compression_rpm    = v;
        c.compression_offset = static_cast<std::uint16_t>(0xFFFF - v);
        auto bytes = encode_v2(c);
        auto back = decode_v2(bytes);
        REQUIRE(back.has_value());
        CAPTURE(v);
        CHECK(back->compression_rpm == v);
        CHECK(back->compression_offset == static_cast<std::uint16_t>(0xFFFF - v));
    }
}

TEST_CASE("mode field round-trips for every defined RpmMode") {
    for (auto m : {RpmMode::LINEAR_SWEPT_RPM, RpmMode::FIXED_RPM, RpmMode::POT_RPM}) {
        BenchSimulatorConfig c;
        c.mode = m;
        auto bytes = encode_v2(c);
        auto back = decode_v2(bytes);
        REQUIRE(back.has_value());
        CHECK(back->mode == m);
    }
}

TEST_CASE("compression_type field round-trips for every defined CompressionType") {
    for (auto t : {CompressionType::CYL1_4STROKE,
                   CompressionType::CYL2_4STROKE,
                   CompressionType::CYL3_4STROKE,
                   CompressionType::CYL4_4STROKE,
                   CompressionType::CYL6_4STROKE,
                   CompressionType::CYL8_4STROKE}) {
        BenchSimulatorConfig c;
        c.compression_type = t;
        auto bytes = encode_v2(c);
        auto back = decode_v2(bytes);
        REQUIRE(back.has_value());
        CHECK(back->compression_type == t);
    }
}
