// SPDX-License-Identifier: MIT
//
// doctest unit tests for tuner_core::speeduino_live_data_decoder.

#include "doctest.h"

#include "tuner_core/speeduino_live_data_decoder.hpp"

#include <vector>

using namespace tuner_core::speeduino_live_data_decoder;
using DT = tuner_core::speeduino_value_codec::DataType;
using ScalarLayout = tuner_core::speeduino_param_codec::ScalarLayout;

namespace {

OutputChannelLayout make_channel(
    std::string name,
    std::size_t offset,
    DT type,
    double scale = 1.0,
    double translate = 0.0,
    std::string units = "") {
    OutputChannelLayout ch;
    ch.name = std::move(name);
    ch.units = std::move(units);
    ch.layout.offset = offset;
    ch.layout.data_type = type;
    ch.layout.scale = scale;
    ch.layout.translate = translate;
    return ch;
}

}  // namespace

TEST_CASE("runtime_packet_size returns the maximum offset+size") {
    std::vector<OutputChannelLayout> channels{
        make_channel("rpm", 14, DT::U16),
        make_channel("clt", 7,  DT::U08),
        make_channel("map", 4,  DT::U16),
    };
    // rpm covers bytes 14-15 → packet must be at least 16 bytes
    CHECK(runtime_packet_size(channels) == 16);
}

TEST_CASE("runtime_packet_size of an empty channel set is 0") {
    std::vector<OutputChannelLayout> channels;
    CHECK(runtime_packet_size(channels) == 0);
}

TEST_CASE("decode_runtime_packet preserves name + units in the result") {
    std::vector<OutputChannelLayout> channels{
        make_channel("rpm", 14, DT::U16, 1.0, 0.0, "rpm"),
        make_channel("clt", 7,  DT::U08, 1.0, -40.0, "C"),
    };
    std::vector<std::uint8_t> payload(16, 0);
    payload[14] = 0x88;  // rpm low
    payload[15] = 0x13;  // rpm high → 0x1388 = 5000
    payload[7]  = 90;    // clt → 90 - 40 = 50

    auto values = decode_runtime_packet(channels, payload);
    REQUIRE(values.size() == 2);
    CHECK(values[0].name == "rpm");
    CHECK(values[0].units == "rpm");
    CHECK(values[0].value == doctest::Approx(5000.0));
    CHECK(values[1].name == "clt");
    CHECK(values[1].units == "C");
    CHECK(values[1].value == doctest::Approx(50.0));
}

TEST_CASE("decode_runtime_packet honors scale and translate") {
    std::vector<OutputChannelLayout> channels{
        make_channel("iat", 0, DT::U08, 1.8, -22.23, "F"),
    };
    std::vector<std::uint8_t> payload{125};
    auto values = decode_runtime_packet(channels, payload);
    REQUIRE(values.size() == 1);
    CHECK(values[0].value == doctest::Approx(125 * 1.8 - 22.23));
}

TEST_CASE("decode_runtime_packet preserves channel input order") {
    std::vector<OutputChannelLayout> channels{
        make_channel("c", 2, DT::U08),
        make_channel("a", 0, DT::U08),
        make_channel("b", 1, DT::U08),
    };
    std::vector<std::uint8_t> payload{10, 20, 30};
    auto values = decode_runtime_packet(channels, payload);
    REQUIRE(values.size() == 3);
    CHECK(values[0].name == "c");
    CHECK(values[0].value == doctest::Approx(30.0));
    CHECK(values[1].name == "a");
    CHECK(values[1].value == doctest::Approx(10.0));
    CHECK(values[2].name == "b");
    CHECK(values[2].value == doctest::Approx(20.0));
}

TEST_CASE("decode_runtime_packet throws on undersized payload") {
    std::vector<OutputChannelLayout> channels{
        make_channel("rpm", 14, DT::U16),
    };
    std::vector<std::uint8_t> tiny(4, 0);
    CHECK_THROWS(decode_runtime_packet(channels, tiny));
}
