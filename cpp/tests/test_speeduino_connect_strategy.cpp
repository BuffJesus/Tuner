// SPDX-License-Identifier: MIT
//
// doctest cases for `speeduino_connect_strategy.hpp`.

#include "doctest.h"

#include "tuner_core/speeduino_connect_strategy.hpp"

#include <map>
#include <optional>
#include <string>
#include <vector>

using namespace tuner_core::speeduino_connect_strategy;

// ---------------------------------------------------------------------
// command_char
// ---------------------------------------------------------------------

TEST_CASE("command_char: empty raw returns fallback") {
    CHECK(command_char("", 'p') == 'p');
}

TEST_CASE("command_char: non-empty raw returns first char") {
    CHECK(command_char("F", 'p') == 'F');
    CHECK(command_char("FOO", 'p') == 'F');
    CHECK(command_char("p", 'b') == 'p');
}

// ---------------------------------------------------------------------
// effective_blocking_factor
// ---------------------------------------------------------------------

TEST_CASE("effective_blocking_factor: scalar firmware wins over scalar definition") {
    CHECK(effective_blocking_factor(false, 256, std::nullopt, 64, std::nullopt) == 256);
}

TEST_CASE("effective_blocking_factor: scalar definition used when firmware missing") {
    CHECK(effective_blocking_factor(false, std::nullopt, std::nullopt, 64, std::nullopt) == 64);
}

TEST_CASE("effective_blocking_factor: 128 default when nothing supplied") {
    CHECK(effective_blocking_factor(false, std::nullopt, std::nullopt, std::nullopt, std::nullopt) == 128);
}

TEST_CASE("effective_blocking_factor: zero firmware value treated as missing") {
    CHECK(effective_blocking_factor(false, 0, std::nullopt, 64, std::nullopt) == 64);
}

TEST_CASE("effective_blocking_factor: zero definition value treated as missing") {
    CHECK(effective_blocking_factor(false, std::nullopt, std::nullopt, 0, std::nullopt) == 128);
}

TEST_CASE("effective_blocking_factor: table firmware wins for is_table=true") {
    CHECK(effective_blocking_factor(true, 256, 512, 64, 128) == 512);
}

TEST_CASE("effective_blocking_factor: table definition used when firmware missing") {
    CHECK(effective_blocking_factor(true, 256, std::nullopt, 64, 128) == 128);
}

TEST_CASE("effective_blocking_factor: table falls back to scalar firmware when no table value") {
    CHECK(effective_blocking_factor(true, 256, std::nullopt, 64, std::nullopt) == 256);
}

TEST_CASE("effective_blocking_factor: is_table=false ignores table values") {
    // Even with table values present, scalar branch should take scalar.
    CHECK(effective_blocking_factor(false, 256, 512, 64, 128) == 256);
}

// ---------------------------------------------------------------------
// signature_probe_candidates
// ---------------------------------------------------------------------

TEST_CASE("signature_probe_candidates: empty defs use F/Q/S only") {
    auto cands = signature_probe_candidates("", "");
    CHECK(cands == std::vector<char>{'F', 'Q', 'S'});
}

TEST_CASE("signature_probe_candidates: query_command leads") {
    auto cands = signature_probe_candidates("S", "");
    CHECK(cands == std::vector<char>{'S', 'F', 'Q'});  // S dedupes from the trailing default
}

TEST_CASE("signature_probe_candidates: dedupes against tail") {
    auto cands = signature_probe_candidates("F", "Q");
    CHECK(cands == std::vector<char>{'F', 'Q', 'S'});
}

TEST_CASE("signature_probe_candidates: takes first char only") {
    auto cands = signature_probe_candidates("Foo", "Bar");
    CHECK(cands == std::vector<char>{'F', 'B', 'Q', 'S'});
}

TEST_CASE("signature_probe_candidates: dedupes between query and version") {
    auto cands = signature_probe_candidates("X", "X");
    CHECK(cands == std::vector<char>{'X', 'F', 'Q', 'S'});
}

// ---------------------------------------------------------------------
// baud_probe_candidates
// ---------------------------------------------------------------------

TEST_CASE("baud_probe_candidates: current baud leads") {
    auto cands = baud_probe_candidates(57600);
    REQUIRE(cands.size() == 4);
    CHECK(cands[0] == std::optional<int>{57600});
    CHECK(cands[1] == std::optional<int>{115200});
    CHECK(cands[2] == std::optional<int>{230400});
    CHECK(cands[3] == std::optional<int>{9600});
}

TEST_CASE("baud_probe_candidates: nullopt current baud uses defaults") {
    auto cands = baud_probe_candidates(std::nullopt);
    REQUIRE(cands.size() == 4);
    CHECK(cands[0] == std::optional<int>{115200});
    CHECK(cands[1] == std::optional<int>{230400});
    CHECK(cands[2] == std::optional<int>{57600});
    CHECK(cands[3] == std::optional<int>{9600});
}

TEST_CASE("baud_probe_candidates: dedupes current against defaults") {
    auto cands = baud_probe_candidates(115200);
    REQUIRE(cands.size() == 4);
    CHECK(cands[0] == std::optional<int>{115200});
    CHECK(cands[1] == std::optional<int>{230400});
    CHECK(cands[2] == std::optional<int>{57600});
    CHECK(cands[3] == std::optional<int>{9600});
}

// ---------------------------------------------------------------------
// connect_delay_seconds
// ---------------------------------------------------------------------

TEST_CASE("connect_delay_seconds: empty metadata returns 1.5 default") {
    std::map<std::string, std::string> meta;
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.5));
}

TEST_CASE("connect_delay_seconds: controllerConnectDelay key wins") {
    std::map<std::string, std::string> meta = {
        {"controllerConnectDelay", "2500"},
        {"connectDelay", "1000"},
        {"interWriteDelay", "500"},
    };
    CHECK(connect_delay_seconds(meta) == doctest::Approx(2.5));
}

TEST_CASE("connect_delay_seconds: connectDelay used when controllerConnectDelay missing") {
    std::map<std::string, std::string> meta = {{"connectDelay", "1000"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.0));
}

TEST_CASE("connect_delay_seconds: interWriteDelay used when both leading keys missing") {
    std::map<std::string, std::string> meta = {{"interWriteDelay", "750"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(0.75));
}

TEST_CASE("connect_delay_seconds: comma-separated value takes the leading number") {
    std::map<std::string, std::string> meta = {{"controllerConnectDelay", "1500,1000"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.5));
}

TEST_CASE("connect_delay_seconds: leading whitespace stripped") {
    std::map<std::string, std::string> meta = {{"controllerConnectDelay", "  3000  "}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(3.0));
}

TEST_CASE("connect_delay_seconds: zero parsed value falls through to default") {
    std::map<std::string, std::string> meta = {{"controllerConnectDelay", "0"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.5));
}

TEST_CASE("connect_delay_seconds: negative parsed value falls through to default") {
    std::map<std::string, std::string> meta = {{"controllerConnectDelay", "-500"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.5));
}

TEST_CASE("connect_delay_seconds: malformed value falls through to default") {
    std::map<std::string, std::string> meta = {{"controllerConnectDelay", "not-a-number"}};
    CHECK(connect_delay_seconds(meta) == doctest::Approx(1.5));
}

TEST_CASE("connect_delay_seconds: empty string skips that key and uses fallback") {
    std::map<std::string, std::string> meta = {
        {"controllerConnectDelay", ""},
        {"connectDelay", "800"},
    };
    CHECK(connect_delay_seconds(meta) == doctest::Approx(0.8));
}

// ---------------------------------------------------------------------
// parse_capability_header / capability_source
// ---------------------------------------------------------------------

TEST_CASE("parse_capability_header: nullopt payload returns parsed=false") {
    auto h = parse_capability_header(std::nullopt);
    CHECK(h.parsed == false);
    CHECK(capability_source(h) == "definition");
}

TEST_CASE("parse_capability_header: short payload returns parsed=false") {
    std::vector<std::uint8_t> p = {0x00, 0x01, 0x02, 0x03};  // only 4 bytes
    auto h = parse_capability_header(std::span<const std::uint8_t>(p));
    CHECK(h.parsed == false);
}

TEST_CASE("parse_capability_header: first byte non-zero rejects") {
    std::vector<std::uint8_t> p = {0x01, 0x02, 0x00, 0x80, 0x01, 0x00};
    auto h = parse_capability_header(std::span<const std::uint8_t>(p));
    CHECK(h.parsed == false);
}

TEST_CASE("parse_capability_header: valid payload decodes big-endian u16 pair") {
    // serial_protocol_version=2, blocking_factor=0x0180=384,
    // table_blocking_factor=0x0200=512
    std::vector<std::uint8_t> p = {0x00, 0x02, 0x01, 0x80, 0x02, 0x00};
    auto h = parse_capability_header(std::span<const std::uint8_t>(p));
    CHECK(h.parsed == true);
    CHECK(h.serial_protocol_version == 2);
    CHECK(h.blocking_factor == 384);
    CHECK(h.table_blocking_factor == 512);
    CHECK(capability_source(h) == "serial+definition");
}

TEST_CASE("parse_capability_header: zero integers still count as parsed") {
    std::vector<std::uint8_t> p = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
    auto h = parse_capability_header(std::span<const std::uint8_t>(p));
    CHECK(h.parsed == true);
    CHECK(h.serial_protocol_version == 0);
    CHECK(h.blocking_factor == 0);
    CHECK(h.table_blocking_factor == 0);
}

TEST_CASE("parse_capability_header: extra trailing bytes are ignored") {
    std::vector<std::uint8_t> p = {0x00, 0x01, 0x00, 0x80, 0x01, 0x00, 0xFF, 0xFF};
    auto h = parse_capability_header(std::span<const std::uint8_t>(p));
    CHECK(h.parsed == true);
    CHECK(h.blocking_factor == 0x0080);
}

// ---------------------------------------------------------------------
// compute_live_data_size
// ---------------------------------------------------------------------

TEST_CASE("compute_live_data_size: empty channel list returns nullopt") {
    std::vector<OutputChannelField> channels;
    CHECK(compute_live_data_size(channels) == std::nullopt);
}

TEST_CASE("compute_live_data_size: single U08 at offset 0 gives 1") {
    std::vector<OutputChannelField> channels = {
        {"clt", 0, "U08"},
    };
    CHECK(compute_live_data_size(channels) == std::optional<int>{1});
}

TEST_CASE("compute_live_data_size: max over offsets + data_size") {
    // rpm U16 at 14 -> end 16; map U08 at 4 -> end 5; iat S08 at 6 -> end 7
    std::vector<OutputChannelField> channels = {
        {"rpm", 14, "U16"},
        {"map", 4,  "U08"},
        {"iat", 6,  "S08"},
    };
    CHECK(compute_live_data_size(channels) == std::optional<int>{16});
}

TEST_CASE("compute_live_data_size: nullopt offset treated as 0") {
    std::vector<OutputChannelField> channels = {
        {"noOffset", std::nullopt, "U32"},  // end = 0 + 4 = 4
    };
    CHECK(compute_live_data_size(channels) == std::optional<int>{4});
}

// ---------------------------------------------------------------------
// has_any_output_channel
// ---------------------------------------------------------------------

TEST_CASE("has_any_output_channel: match found returns true") {
    std::vector<std::string> defined = {"rpm", "map", "runtimeStatusA", "clt"};
    std::vector<std::string> targets = {"runtimeStatusA", "rSA_tuneValid"};
    CHECK(has_any_output_channel(defined, targets) == true);
}

TEST_CASE("has_any_output_channel: all alternatives absent returns false") {
    std::vector<std::string> defined = {"rpm", "map"};
    std::vector<std::string> targets = {"runtimeStatusA", "rSA_tuneValid"};
    CHECK(has_any_output_channel(defined, targets) == false);
}

TEST_CASE("has_any_output_channel: empty inputs return false") {
    CHECK(has_any_output_channel({}, {"x"}) == false);
    CHECK(has_any_output_channel({"x"}, {}) == false);
    CHECK(has_any_output_channel({}, {}) == false);
}

// ---------------------------------------------------------------------
// is_experimental_u16p2_signature
// ---------------------------------------------------------------------

TEST_CASE("is_experimental_u16p2_signature: substring match regardless of case") {
    CHECK(is_experimental_u16p2_signature("speeduino 202501-T41-U16P2") == true);
    CHECK(is_experimental_u16p2_signature("speeduino 202501-T41-u16p2") == true);
    CHECK(is_experimental_u16p2_signature("speeduino 202501-T41") == false);
    CHECK(is_experimental_u16p2_signature("") == false);
}

// ---------------------------------------------------------------------
// should_accept_probe_response
// ---------------------------------------------------------------------

TEST_CASE("should_accept_probe_response: empty response rejected") {
    CHECK(should_accept_probe_response('S', "") == false);
}

TEST_CASE("should_accept_probe_response: single-char echo rejected") {
    CHECK(should_accept_probe_response('S', "S") == false);
    CHECK(should_accept_probe_response('Q', "Q") == false);
}

TEST_CASE("should_accept_probe_response: F probe always rejected") {
    CHECK(should_accept_probe_response('F', "speeduino 202501-T41") == false);
}

TEST_CASE("should_accept_probe_response: real signature accepted") {
    CHECK(should_accept_probe_response('S', "speeduino 202501-T41") == true);
    CHECK(should_accept_probe_response('Q', "speeduino 202501-T41") == true);
}
