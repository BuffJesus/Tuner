// SPDX-License-Identifier: MIT
//
// doctest cases for `airbear_api.hpp` — pure-logic half.

#include "doctest.h"

#include "tuner_core/airbear_api.hpp"

#include <stdexcept>

using namespace tuner_core::airbear_api;

TEST_CASE("parse_http_body strips headers for a 200 response") {
    const char* resp =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: 5\r\n"
        "\r\n"
        "hello";
    auto body = parse_http_body(resp);
    REQUIRE(body.has_value());
    CHECK(*body == "hello");
}

TEST_CASE("parse_http_body rejects non-2xx responses") {
    const char* resp = "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n";
    CHECK_FALSE(parse_http_body(resp).has_value());
}

TEST_CASE("parse_http_body rejects malformed responses") {
    CHECK_FALSE(parse_http_body("garbage").has_value());
    CHECK_FALSE(parse_http_body("HTTP/1.1 200 OK\r\n").has_value());
}

TEST_CASE("parse_realtime_json parses the canonical v0.2.0 shape") {
    const char* body =
        R"({"ts":12345,"fw_version":"0.2.0","fw_variant":"202501-T41","data":{"rpm":1800}})";
    auto r = parse_realtime_json(body);
    REQUIRE(r.ts_ms.has_value());
    CHECK(*r.ts_ms == 12345);
    REQUIRE(r.fw_version.has_value());
    CHECK(*r.fw_version == "0.2.0");
    REQUIRE(r.fw_variant.has_value());
    CHECK(*r.fw_variant == "202501-T41");
    CHECK(r.data_json.find("1800") != std::string::npos);
}

TEST_CASE("parse_realtime_json tolerates missing optional fields") {
    auto r = parse_realtime_json(R"({"ts":1})");
    CHECK(r.ts_ms.value_or(-1) == 1);
    CHECK_FALSE(r.fw_variant.has_value());
}

TEST_CASE("parse_realtime_json throws on malformed JSON") {
    CHECK_THROWS(parse_realtime_json("{not valid json"));
}

TEST_CASE("parse_status_json parses the /api/status shape") {
    const char* body =
        R"({"product":"AirBear","fw_version":"0.2.0","fw_variant":"202501-T41-U16P2",)"
        R"("uptime_ms":60000,"wifi_ssid":"home","wifi_rssi":-55,"ip":"192.168.1.50"})";
    auto s = parse_status_json(body);
    CHECK(s.product.value_or("") == "AirBear");
    CHECK(s.fw_version.value_or("") == "0.2.0");
    CHECK(s.fw_variant.value_or("") == "202501-T41-U16P2");
    CHECK(s.uptime_ms.value_or(-1) == 60000);
    CHECK(s.wifi_ssid.value_or("") == "home");
    CHECK(s.wifi_rssi.value_or(0) == -55);
    CHECK(s.ip.value_or("") == "192.168.1.50");
}

TEST_CASE("signatures_match: ECU signature contains fw_variant -> Match") {
    auto r = signatures_match("speeduino 202501-T41", "202501-T41");
    CHECK(r.state == SignatureMatch::Match);
}

TEST_CASE("signatures_match: case-insensitive substring") {
    auto r = signatures_match("SPEEDUINO 202501-t41", "202501-T41");
    CHECK(r.state == SignatureMatch::Match);
}

TEST_CASE("signatures_match: U16P2 variant matches experimental signature") {
    auto r = signatures_match("speeduino 202501-T41-U16P2", "202501-T41-U16P2");
    CHECK(r.state == SignatureMatch::Match);
}

TEST_CASE("signatures_match: different variant -> Mismatch") {
    auto r = signatures_match("speeduino 202501-T41", "202501-T41-U16P2");
    CHECK(r.state == SignatureMatch::Mismatch);
    CHECK(r.detail.find("Firmware mismatch") != std::string::npos);
}

TEST_CASE("signatures_match: fw_variant=unknown -> Unknown") {
    auto r = signatures_match("speeduino 202501-T41", "unknown");
    CHECK(r.state == SignatureMatch::Unknown);
}

TEST_CASE("signatures_match: empty fw_variant -> Unknown") {
    auto r = signatures_match("speeduino 202501-T41", "");
    CHECK(r.state == SignatureMatch::Unknown);
}

TEST_CASE("signatures_match: empty ECU sig -> Unknown") {
    auto r = signatures_match("", "202501-T41");
    CHECK(r.state == SignatureMatch::Unknown);
}

TEST_CASE("signatures_match: whitespace-only fw_variant treated as empty") {
    auto r = signatures_match("speeduino 202501-T41", "   ");
    CHECK(r.state == SignatureMatch::Unknown);
}

TEST_CASE("build_multipart_body produces RFC7578-shape output") {
    auto body = build_multipart_body(
        "BOUNDARY", "file", "firmware.bin",
        "application/octet-stream", "\x01\x02\x03\x04");
    // Leading boundary + headers.
    CHECK(body.find("--BOUNDARY\r\n") == 0);
    CHECK(body.find("Content-Disposition: form-data; name=\"file\"; filename=\"firmware.bin\"\r\n")
          != std::string::npos);
    CHECK(body.find("Content-Type: application/octet-stream\r\n") != std::string::npos);
    // Payload bytes present.
    CHECK(body.find(std::string("\x01\x02\x03\x04", 4)) != std::string::npos);
    // Trailing boundary.
    CHECK(body.find("\r\n--BOUNDARY--\r\n") != std::string::npos);
}

TEST_CASE("build_multipart_body preserves binary content including NUL bytes") {
    std::string payload("\x00\x01\x00\x02", 4);
    auto body = build_multipart_body(
        "B", "f", "x.bin", "application/octet-stream", payload);
    // Find the payload inside the body and verify its length matches.
    auto start = body.find("\r\n\r\n");
    REQUIRE(start != std::string::npos);
    start += 4;
    auto end = body.find("\r\n--B--\r\n");
    REQUIRE(end != std::string::npos);
    CHECK((end - start) == payload.size());
    for (std::size_t i = 0; i < payload.size(); ++i) {
        CHECK(body[start + i] == payload[i]);
    }
}
