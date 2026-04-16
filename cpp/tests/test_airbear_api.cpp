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

TEST_CASE("parse_status_json parses the post-health-counter shape") {
    const char* body =
        R"({"product":"AirBear","fw_version":"0.2.1",)"
        R"("uptime_ms":300000,"free_heap":123456,"min_free_heap":98765,)"
        R"("wifi_rssi":-62,"ip":"192.168.1.50","ap_ip":"192.168.4.1",)"
        R"("tcp_requests":4211,"ecu_timeouts":3,"ecu_busy":0,)"
        R"("wifi_disconnects":2})";
    auto s = parse_status_json(body);
    CHECK(s.min_free_heap.value_or(-1) == 98765);
    CHECK(s.ap_ip.value_or("") == "192.168.4.1");
    CHECK(s.tcp_requests.value_or(-1) == 4211);
    CHECK(s.ecu_timeouts.value_or(-1) == 3);
    CHECK(s.ecu_busy.value_or(-1) == 0);
    CHECK(s.wifi_disconnects.value_or(-1) == 2);
}

TEST_CASE("parse_status_json absent counters stay nullopt") {
    // Pre-counter Airbear build — counters missing from the JSON.
    const char* body = R"({"product":"AirBear","fw_version":"0.2.0"})";
    auto s = parse_status_json(body);
    CHECK_FALSE(s.tcp_requests.has_value());
    CHECK_FALSE(s.ecu_timeouts.has_value());
    CHECK_FALSE(s.ecu_busy.has_value());
    CHECK_FALSE(s.wifi_disconnects.has_value());
    CHECK_FALSE(s.min_free_heap.has_value());
    CHECK_FALSE(s.ap_ip.has_value());
}

TEST_CASE("parse_log_status_json parses an active-capture status") {
    const char* body =
        R"({"active":true,"rows":1200,"file_bytes":48000,)"
        R"("max_bytes":1048576,"elapsed_ms":12000,)"
        R"("trig_enabled":true,"trig_field":"rpm"})";
    auto s = parse_log_status_json(body);
    CHECK(s.active);
    CHECK(s.rows.value_or(-1) == 1200);
    CHECK(s.file_bytes.value_or(-1) == 48000);
    CHECK(s.max_bytes.value_or(-1) == 1048576);
    CHECK(s.elapsed_ms.value_or(-1) == 12000);
    CHECK(s.trigger_enabled);
    CHECK(s.trigger_field.value_or("") == "rpm");
}

TEST_CASE("parse_log_status_json idle with no log") {
    const char* body =
        R"({"active":false,"rows":0,"file_bytes":0,)"
        R"("max_bytes":1048576,"elapsed_ms":0,"trig_enabled":false})";
    auto s = parse_log_status_json(body);
    CHECK_FALSE(s.active);
    CHECK(s.rows.value_or(-1) == 0);
    CHECK(s.file_bytes.value_or(-1) == 0);
    CHECK_FALSE(s.trigger_enabled);
    CHECK_FALSE(s.trigger_field.has_value());
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
