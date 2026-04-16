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
#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::airbear_api {

struct RealtimeResponse {
    std::optional<long long> ts_ms;          // Airbear millis()
    std::optional<std::string> fw_version;   // Airbear's own version, e.g. "0.2.0"
    std::optional<std::string> fw_variant;   // Teensy variant e.g. "202501-T41"
    std::string data_json;                   // raw OCH snapshot sub-doc (unused here)
};

struct StatusResponse {
    // All fields below are emitted by Airbear v0.2.0
    // (`Airbear-main/src/rest_api.cpp::handleStatus`).
    std::optional<std::string> product;       // "AirBear"
    std::optional<std::string> fw_version;    // "0.2.0"
    std::optional<std::string> fw_variant;    // Teensy variant
    std::optional<long long> uptime_ms;
    std::optional<long long> free_heap;
    std::optional<long long> min_free_heap;   // lowest heap seen since boot
    std::optional<std::string> wifi_ssid;
    std::optional<int> wifi_rssi;
    std::optional<std::string> ip;
    std::optional<std::string> ap_ip;         // AP-mode IP
    std::optional<std::string> mac;

    // Phase 16 item 4 — operator-facing health counters. These are
    // real Airbear keys (wired on the bridge side in tcp-uart.cpp,
    // wifi_mgt.cpp, and rest_api.cpp). Monotonic since boot.
    std::optional<long long> tcp_requests;      // total TS-to-ECU requests proxied
    std::optional<long long> ecu_timeouts;      // ECU failed to respond in ECU_SERIAL_TIMEOUT
    std::optional<long long> ecu_busy;          // DASH_ECHO mutex-busy refusals
    std::optional<long long> wifi_disconnects;  // Wi-Fi STA disconnect events
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

// Convenience: GET /api/status and parse. Used by the Airbear Health
// dialog to surface error counters (Phase 16 item 4).
std::optional<StatusResponse> fetch_status(std::string_view host,
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

// --- Airbear v0.2 datalog endpoints (actually exists today) ---------
//
// Source: `Airbear-main/src/rest_api.cpp` v0.2.0:
//   GET /api/log/status   -> { active, rows, file_bytes, ... }
//   GET /api/log/download -> streams the single on-device log.csv

struct LogStatusResponse {
    bool active = false;               // capture currently running
    std::optional<long long> rows;     // row count in the captured log
    std::optional<long long> file_bytes;
    std::optional<long long> max_bytes;
    std::optional<long long> elapsed_ms;
    bool trigger_enabled = false;
    std::optional<std::string> trigger_field;
};

LogStatusResponse parse_log_status_json(std::string_view body);

#ifdef _WIN32
// GET /api/log/status from the Airbear bridge. Returns nullopt on
// network or parse failure.
std::optional<LogStatusResponse> fetch_log_status(
    std::string_view host, int port,
    std::chrono::milliseconds timeout);

// GET /api/log/download — streams the single on-device log.csv. Caps
// at `max_bytes` (default 16 MB) to bound memory on a runaway server.
std::optional<std::string> fetch_log_csv(
    std::string_view host, int port,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes = 16 * 1024 * 1024);
#endif

// --- SD card log listing + download (Phase 15 item 4) -----------------
//
// DESIGN NOTE — pending firmware-side G5 command spec.
// The endpoints below are the desktop-side contract that will drive
// the firmware work. They follow the existing Airbear REST grammar
// (`/api/realtime`, `/api/status`, `/updateFWUpload`) so the Airbear
// side can add them as a minimal extension:
//
//   GET  /api/sd/logs              -> JSON array of {name, size, mtime_unix}
//   GET  /api/sd/logs/<filename>   -> raw CSV (or MSL) bytes
//
// If the firmware settles on a different path or schema, only the
// two convenience helpers below need to move — the parser + builder
// helpers are pure logic and can stay.

struct SdLogEntry {
    std::string name;
    long long size = 0;              // bytes
    long long mtime_unix = 0;        // seconds since epoch (0 if unknown)
};

// Parse the `/api/sd/logs` JSON body — an array of log-file entries.
// Throws on malformed JSON. Missing / wrong-type fields on an individual
// entry leave the corresponding field at its default (empty / 0).
std::vector<SdLogEntry> parse_sd_log_list_json(std::string_view body);

// Build the GET path for a single SD log file. URL-encodes the few
// characters that can realistically appear in a sensible filename
// (space, plus, percent, slash, hash, question-mark, ampersand) and
// passes everything else through unchanged. Keeps ASCII identifiers
// readable in Airbear logs instead of percent-encoding everything.
std::string build_sd_log_path(std::string_view prefix,
                              std::string_view filename);

#ifdef _WIN32
// GET /api/sd/logs and parse the JSON response. Returns nullopt on
// network failure OR parse failure so the caller can show one
// "could not reach device" message either way.
std::optional<std::vector<SdLogEntry>> fetch_sd_log_list(
    std::string_view host, int port,
    std::chrono::milliseconds timeout);

// GET the raw bytes of a single SD log file. `max_bytes` caps the
// buffer so a malformed server can't make us allocate unbounded
// memory (default: 16 MB). Returns nullopt on network failure or
// oversize response.
std::optional<std::string> fetch_sd_log_bytes(
    std::string_view host, int port,
    std::string_view filename,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes = 16 * 1024 * 1024);

// Parallel pair for the /api/sd/tunes endpoint (Phase 15 item 9 step
// 7 — SD-card tune ingest). Response schema is identical to the logs
// listing so `parse_sd_log_list_json` and `SdLogEntry` get reused.
// Tunes are small so the default max_bytes is 1 MB.
std::optional<std::vector<SdLogEntry>> fetch_sd_tune_list(
    std::string_view host, int port,
    std::chrono::milliseconds timeout);

std::optional<std::string> fetch_sd_tune_bytes(
    std::string_view host, int port,
    std::string_view filename,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes = 1 * 1024 * 1024);
#endif

}  // namespace tuner_core::airbear_api
