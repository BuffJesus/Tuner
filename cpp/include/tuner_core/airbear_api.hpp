// SPDX-License-Identifier: MIT
//
// tuner_core::airbear_api — HTTP client for the Airbear REST API on
// port 80: `GET /api/realtime` and `GET /api/status`. Used by the
// desktop to cross-check the Teensy firmware variant Airbear probed
// against the signature the desktop got over its own `'Q'` exchange.
//
// Reference: `Airbear-main/src/rest_api.cpp` (v0.2.0). Responses are
// small flat JSON documents — no chunked encoding in practice.
//
// Pure-logic helpers:
//   - parse_http_body(response_text) -> optional<body_text>
//   - parse_realtime_json(body)      -> RealtimeResponse
//   - parse_status_json(body)        -> StatusResponse
//   - signatures_match(ecu_sig, fw_variant) -> MatchResult
//
// I/O (Winsock socket + recv loop) is Windows-only, ifdef-guarded.

#pragma once

#include <chrono>
#include <optional>
#include <string>
#include <string_view>

namespace tuner_core::airbear_api {

struct RealtimeResponse {
    std::optional<long long> ts_ms;          // Airbear millis()
    std::optional<std::string> fw_version;   // Airbear's own version, e.g. "0.2.0"
    std::optional<std::string> fw_variant;   // Teensy variant e.g. "202501-T41"
    std::string data_json;                   // raw OCH snapshot sub-doc (unused here)
};

struct StatusResponse {
    std::optional<std::string> product;       // "AirBear"
    std::optional<std::string> fw_version;    // "0.2.0"
    std::optional<std::string> fw_variant;    // Teensy variant
    std::optional<long long> uptime_ms;
    std::optional<long long> free_heap;
    std::optional<std::string> wifi_ssid;
    std::optional<int> wifi_rssi;
    std::optional<std::string> ip;
    std::optional<std::string> mac;
};

enum class SignatureMatch {
    Match,           // ECU sig contains (or ends with) fw_variant
    Mismatch,        // both known, they disagree
    Unknown,         // fw_variant is "unknown" or empty — no cross-check
};

struct MatchResult {
    SignatureMatch state = SignatureMatch::Unknown;
    std::string detail;  // operator-facing explanation
};

// Strip HTTP status line + headers, return just the body. Returns
// nullopt on malformed responses (no `\r\n\r\n`) or non-2xx status.
std::optional<std::string> parse_http_body(std::string_view response_text);

// Parse a `/api/realtime` JSON body into the struct. Throws on
// malformed JSON; missing fields become nullopt.
RealtimeResponse parse_realtime_json(std::string_view body);

// Parse a `/api/status` JSON body into the struct.
StatusResponse parse_status_json(std::string_view body);

// Cross-check rule:
//   - fw_variant missing / "unknown" / empty  -> Unknown
//   - ECU signature contains fw_variant (case-insensitive substring) -> Match
//   - otherwise -> Mismatch
MatchResult signatures_match(std::string_view ecu_signature,
                             std::string_view fw_variant);

#ifdef _WIN32
// Synchronous HTTP GET. Blocks up to `timeout`. Returns the full
// response text (status line + headers + body) on success, nullopt on
// network failure. Use `parse_http_body()` to strip headers.
std::optional<std::string> http_get(std::string_view host,
                                    int port,
                                    std::string_view path,
                                    std::chrono::milliseconds timeout);

// Convenience: GET /api/realtime and parse.
std::optional<RealtimeResponse> fetch_realtime(std::string_view host,
                                               int port,
                                               std::chrono::milliseconds timeout);
#endif

// Build a multipart/form-data request body for a single file upload.
// Pure-logic. The caller picks the `boundary` string; a simple random
// value like `----TunerBoundary42` works. Content-Type for the whole
// POST is `multipart/form-data; boundary=<boundary>`.
std::string build_multipart_body(std::string_view boundary,
                                 std::string_view field_name,
                                 std::string_view filename,
                                 std::string_view content_type,
                                 std::string_view file_bytes);

#ifdef _WIN32
// POST Airbear firmware (.bin) to the OTA endpoint. Blocks until the
// upload completes or the timeout expires. Returns the response text
// on success, nullopt on network failure. Uses multipart/form-data
// with a fixed boundary — Airbear v0.2.0 accepts any single-file part.
std::optional<std::string> post_firmware(std::string_view host,
                                         int port,
                                         std::string_view path,
                                         std::string_view filename,
                                         std::string_view file_bytes,
                                         std::chrono::milliseconds timeout);
#endif

}  // namespace tuner_core::airbear_api
