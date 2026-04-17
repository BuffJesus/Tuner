// SPDX-License-Identifier: MIT
#include "tuner_core/airbear_api.hpp"

#include "nlohmann/json.hpp"

#include <algorithm>
#include <cctype>
#include <cstring>
#include <stdexcept>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#endif

namespace tuner_core::airbear_api {

namespace {

std::string to_lower(std::string_view s) {
    std::string out(s);
    for (auto& c : out) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return out;
}

}  // namespace

std::optional<std::string> parse_http_body(std::string_view response_text) {
    auto sep = response_text.find("\r\n\r\n");
    if (sep == std::string_view::npos) return std::nullopt;

    // Status line: HTTP/1.1 200 OK
    auto end_of_status = response_text.find("\r\n");
    if (end_of_status == std::string_view::npos || end_of_status > sep) {
        return std::nullopt;
    }
    auto status_line = response_text.substr(0, end_of_status);
    // Pull out the 3-digit status code between the first two spaces.
    auto sp1 = status_line.find(' ');
    if (sp1 == std::string_view::npos) return std::nullopt;
    auto sp2 = status_line.find(' ', sp1 + 1);
    if (sp2 == std::string_view::npos) return std::nullopt;
    auto code_text = status_line.substr(sp1 + 1, sp2 - sp1 - 1);
    if (code_text.size() != 3) return std::nullopt;
    if (code_text[0] != '2') return std::nullopt;

    return std::string(response_text.substr(sep + 4));
}

RealtimeResponse parse_realtime_json(std::string_view body) {
    RealtimeResponse out;
    auto doc = nlohmann::json::parse(body);
    if (doc.contains("ts") && doc["ts"].is_number_integer()) {
        out.ts_ms = doc["ts"].get<long long>();
    }
    if (doc.contains("fw_version") && doc["fw_version"].is_string()) {
        out.fw_version = doc["fw_version"].get<std::string>();
    }
    if (doc.contains("fw_variant") && doc["fw_variant"].is_string()) {
        out.fw_variant = doc["fw_variant"].get<std::string>();
    }
    if (doc.contains("data")) {
        out.data_json = doc["data"].dump();
    }
    return out;
}

StatusResponse parse_status_json(std::string_view body) {
    StatusResponse out;
    auto doc = nlohmann::json::parse(body);
    auto read_str = [&](const char* key, std::optional<std::string>& dst) {
        if (doc.contains(key) && doc[key].is_string()) dst = doc[key].get<std::string>();
    };
    auto read_int = [&](const char* key, std::optional<long long>& dst) {
        if (doc.contains(key) && doc[key].is_number_integer()) dst = doc[key].get<long long>();
    };
    read_str("product",     out.product);
    read_str("fw_version",  out.fw_version);
    read_str("fw_variant",  out.fw_variant);
    read_int("uptime_ms",     out.uptime_ms);
    read_int("free_heap",     out.free_heap);
    read_int("min_free_heap", out.min_free_heap);
    read_str("wifi_ssid",     out.wifi_ssid);
    if (doc.contains("wifi_rssi") && doc["wifi_rssi"].is_number_integer())
        out.wifi_rssi = doc["wifi_rssi"].get<int>();
    read_str("ip",            out.ip);
    read_str("ap_ip",         out.ap_ip);
    read_str("mac",           out.mac);
    // Phase 16 item 4 — Airbear health counters. Missing keys leave
    // each optional as nullopt so older Airbear builds before these
    // landed still pass through cleanly.
    read_int("tcp_requests",     out.tcp_requests);
    read_int("ecu_timeouts",     out.ecu_timeouts);
    read_int("ecu_busy",         out.ecu_busy);
    read_int("wifi_disconnects", out.wifi_disconnects);
    return out;
}

MatchResult signatures_match(std::string_view ecu_signature,
                             std::string_view fw_variant) {
    MatchResult r;
    auto trimmed_variant = fw_variant;
    while (!trimmed_variant.empty() && std::isspace(static_cast<unsigned char>(trimmed_variant.front())))
        trimmed_variant.remove_prefix(1);
    while (!trimmed_variant.empty() && std::isspace(static_cast<unsigned char>(trimmed_variant.back())))
        trimmed_variant.remove_suffix(1);

    if (trimmed_variant.empty() || to_lower(trimmed_variant) == "unknown") {
        r.state = SignatureMatch::Unknown;
        r.detail = "Airbear reports fw_variant=unknown — cannot cross-check.";
        return r;
    }
    if (ecu_signature.empty()) {
        r.state = SignatureMatch::Unknown;
        r.detail = "ECU signature not available — cannot cross-check.";
        return r;
    }

    if (to_lower(ecu_signature).find(to_lower(trimmed_variant)) != std::string::npos) {
        r.state = SignatureMatch::Match;
        r.detail = "ECU signature matches Airbear fw_variant.";
        return r;
    }

    r.state = SignatureMatch::Mismatch;
    r.detail = std::string("Firmware mismatch — ECU reports \"")
             + std::string(ecu_signature)
             + "\", Airbear reports fw_variant=\""
             + std::string(trimmed_variant)
             + "\". The Teensy may have been swapped between sessions. "
               "Re-validate your tune before writing.";
    return r;
}

#ifdef _WIN32

std::optional<std::string> http_get(std::string_view host,
                                    int port,
                                    std::string_view path,
                                    std::chrono::milliseconds timeout) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return std::nullopt;

    DWORD to_ms = static_cast<DWORD>(timeout.count());
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    std::string host_s(host);
    std::string port_s = std::to_string(port);
    addrinfo* res = nullptr;
    if (getaddrinfo(host_s.c_str(), port_s.c_str(), &hints, &res) != 0 || !res) {
        closesocket(sock);
        return std::nullopt;
    }

    if (connect(sock, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
        freeaddrinfo(res);
        closesocket(sock);
        return std::nullopt;
    }
    freeaddrinfo(res);

    std::string req;
    req += "GET ";
    req += std::string(path);
    req += " HTTP/1.1\r\nHost: ";
    req += host_s;
    req += "\r\nConnection: close\r\nUser-Agent: tuner_app/0.1\r\n\r\n";
    if (send(sock, req.data(), static_cast<int>(req.size()), 0) < 0) {
        closesocket(sock);
        return std::nullopt;
    }

    std::string response;
    char buf[2048];
    while (true) {
        int n = recv(sock, buf, sizeof(buf), 0);
        if (n <= 0) break;
        response.append(buf, static_cast<std::size_t>(n));
        if (response.size() > 64 * 1024) break;  // safety cap
    }
    closesocket(sock);
    if (response.empty()) return std::nullopt;
    return response;
}

std::optional<RealtimeResponse> fetch_realtime(std::string_view host,
                                               int port,
                                               std::chrono::milliseconds timeout) {
    auto raw = http_get(host, port, "/api/realtime", timeout);
    if (!raw) return std::nullopt;
    auto body = parse_http_body(*raw);
    if (!body) return std::nullopt;
    try {
        return parse_realtime_json(*body);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<StatusResponse> fetch_status(std::string_view host,
                                           int port,
                                           std::chrono::milliseconds timeout) {
    auto raw = http_get(host, port, "/api/status", timeout);
    if (!raw) return std::nullopt;
    auto body = parse_http_body(*raw);
    if (!body) return std::nullopt;
    try {
        return parse_status_json(*body);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<std::string> http_post_form(std::string_view host,
                                          int port,
                                          std::string_view path,
                                          std::string_view form_body,
                                          std::chrono::milliseconds timeout) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return std::nullopt;

    DWORD to_ms = static_cast<DWORD>(timeout.count());
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    std::string host_s(host);
    std::string port_s = std::to_string(port);
    addrinfo* res = nullptr;
    if (getaddrinfo(host_s.c_str(), port_s.c_str(), &hints, &res) != 0 || !res) {
        closesocket(sock);
        return std::nullopt;
    }

    if (connect(sock, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
        freeaddrinfo(res);
        closesocket(sock);
        return std::nullopt;
    }
    freeaddrinfo(res);

    char cl[32];
    std::snprintf(cl, sizeof(cl), "%zu", form_body.size());
    std::string req;
    req += "POST ";
    req += std::string(path);
    req += " HTTP/1.1\r\nHost: ";
    req += host_s;
    req += "\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: ";
    req += cl;
    req += "\r\nConnection: close\r\nUser-Agent: tuner_app/0.1\r\n\r\n";
    req += std::string(form_body);
    if (send(sock, req.data(), static_cast<int>(req.size()), 0) < 0) {
        closesocket(sock);
        return std::nullopt;
    }

    std::string response;
    char buf[2048];
    while (true) {
        int n = recv(sock, buf, sizeof(buf), 0);
        if (n <= 0) break;
        response.append(buf, static_cast<std::size_t>(n));
        if (response.size() > 64 * 1024) break;
    }
    closesocket(sock);
    if (response.empty()) return std::nullopt;
    return response;
}

#endif  // _WIN32

std::string build_multipart_body(std::string_view boundary,
                                 std::string_view field_name,
                                 std::string_view filename,
                                 std::string_view content_type,
                                 std::string_view file_bytes) {
    std::string body;
    body.reserve(file_bytes.size() + 256);
    body += "--";
    body += boundary;
    body += "\r\n";
    body += "Content-Disposition: form-data; name=\"";
    body += field_name;
    body += "\"; filename=\"";
    body += filename;
    body += "\"\r\n";
    body += "Content-Type: ";
    body += content_type;
    body += "\r\n\r\n";
    body.append(file_bytes.data(), file_bytes.size());
    body += "\r\n--";
    body += boundary;
    body += "--\r\n";
    return body;
}

#ifdef _WIN32

std::optional<std::string> post_firmware(std::string_view host,
                                         int port,
                                         std::string_view path,
                                         std::string_view filename,
                                         std::string_view file_bytes,
                                         std::chrono::milliseconds timeout) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return std::nullopt;

    DWORD to_ms = static_cast<DWORD>(timeout.count());
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    std::string host_s(host);
    std::string port_s = std::to_string(port);
    addrinfo* res = nullptr;
    if (getaddrinfo(host_s.c_str(), port_s.c_str(), &hints, &res) != 0 || !res) {
        closesocket(sock);
        return std::nullopt;
    }
    if (connect(sock, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
        freeaddrinfo(res);
        closesocket(sock);
        return std::nullopt;
    }
    freeaddrinfo(res);

    const std::string boundary = "----TunerAppBoundary7f3d";
    std::string body = build_multipart_body(
        boundary, "file", filename, "application/octet-stream", file_bytes);

    std::string req;
    req += "POST ";
    req += std::string(path);
    req += " HTTP/1.1\r\nHost: ";
    req += host_s;
    req += "\r\nContent-Type: multipart/form-data; boundary=";
    req += boundary;
    req += "\r\nContent-Length: ";
    req += std::to_string(body.size());
    req += "\r\nConnection: close\r\nUser-Agent: tuner_app/0.1\r\n\r\n";

    // Send header + body in two chunks to avoid doubling the buffer.
    if (send(sock, req.data(), static_cast<int>(req.size()), 0) < 0) {
        closesocket(sock);
        return std::nullopt;
    }
    // Chunked body send — large firmware payloads (~1 MB) exceed
    // typical TCP window sizes in a single send() call.
    std::size_t total_sent = 0;
    while (total_sent < body.size()) {
        int chunk = static_cast<int>(std::min<std::size_t>(
            body.size() - total_sent, 32 * 1024));
        int n = send(sock, body.data() + total_sent, chunk, 0);
        if (n <= 0) { closesocket(sock); return std::nullopt; }
        total_sent += static_cast<std::size_t>(n);
    }

    std::string response;
    char buf[2048];
    while (true) {
        int n = recv(sock, buf, sizeof(buf), 0);
        if (n <= 0) break;
        response.append(buf, static_cast<std::size_t>(n));
        if (response.size() > 64 * 1024) break;
    }
    closesocket(sock);
    if (response.empty()) return std::nullopt;
    return response;
}

#endif  // _WIN32

// --- Airbear v0.2 datalog endpoints (actually exists today) ---------

#ifdef _WIN32
namespace {

// Shared helper used by all download-ish fetchers — bigger-buffer
// variant of http_get that lets the caller cap at an explicit size
// instead of the 64KB default of the original http_get.
std::optional<std::string> http_get_bounded(std::string_view host,
                                            int port,
                                            std::string_view path,
                                            std::chrono::milliseconds timeout,
                                            std::size_t max_bytes) {
    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return std::nullopt;

    DWORD to_ms = static_cast<DWORD>(timeout.count());
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));
    setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&to_ms), sizeof(to_ms));

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    std::string host_s(host);
    std::string port_s = std::to_string(port);
    addrinfo* res = nullptr;
    if (getaddrinfo(host_s.c_str(), port_s.c_str(), &hints, &res) != 0 || !res) {
        closesocket(sock);
        return std::nullopt;
    }
    if (connect(sock, res->ai_addr, static_cast<int>(res->ai_addrlen)) != 0) {
        freeaddrinfo(res);
        closesocket(sock);
        return std::nullopt;
    }
    freeaddrinfo(res);

    std::string req;
    req += "GET ";
    req += std::string(path);
    req += " HTTP/1.1\r\nHost: ";
    req += host_s;
    req += "\r\nConnection: close\r\nUser-Agent: tuner_app/0.1\r\n\r\n";
    if (send(sock, req.data(), static_cast<int>(req.size()), 0) < 0) {
        closesocket(sock);
        return std::nullopt;
    }

    std::string response;
    char buf[4096];
    while (true) {
        int n = recv(sock, buf, sizeof(buf), 0);
        if (n <= 0) break;
        response.append(buf, static_cast<std::size_t>(n));
        if (response.size() > max_bytes) {
            closesocket(sock);
            return std::nullopt;
        }
    }
    closesocket(sock);
    if (response.empty()) return std::nullopt;
    return response;
}

}  // namespace
#endif  // _WIN32

LogStatusResponse parse_log_status_json(std::string_view body) {
    LogStatusResponse out;
    auto doc = nlohmann::json::parse(body);
    if (doc.contains("active") && doc["active"].is_boolean())
        out.active = doc["active"].get<bool>();
    if (doc.contains("rows") && doc["rows"].is_number_integer())
        out.rows = doc["rows"].get<long long>();
    if (doc.contains("file_bytes") && doc["file_bytes"].is_number_integer())
        out.file_bytes = doc["file_bytes"].get<long long>();
    if (doc.contains("max_bytes") && doc["max_bytes"].is_number_integer())
        out.max_bytes = doc["max_bytes"].get<long long>();
    if (doc.contains("elapsed_ms") && doc["elapsed_ms"].is_number_integer())
        out.elapsed_ms = doc["elapsed_ms"].get<long long>();
    if (doc.contains("trig_enabled") && doc["trig_enabled"].is_boolean())
        out.trigger_enabled = doc["trig_enabled"].get<bool>();
    if (doc.contains("trig_field") && doc["trig_field"].is_string())
        out.trigger_field = doc["trig_field"].get<std::string>();
    return out;
}

#ifdef _WIN32
std::optional<LogStatusResponse> fetch_log_status(
    std::string_view host, int port,
    std::chrono::milliseconds timeout) {
    auto raw = http_get(host, port, "/api/log/status", timeout);
    if (!raw) return std::nullopt;
    auto body = parse_http_body(*raw);
    if (!body) return std::nullopt;
    try {
        return parse_log_status_json(*body);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<std::string> fetch_log_csv(
    std::string_view host, int port,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes) {
    auto raw = http_get_bounded(host, port, "/api/log/download", timeout,
                                max_bytes + 4096);
    if (!raw) return std::nullopt;
    return parse_http_body(*raw);
}
#endif

// --- SD card log list + download (Phase 15 item 4) ------------------

std::vector<SdLogEntry> parse_sd_log_list_json(std::string_view body) {
    std::vector<SdLogEntry> out;
    auto doc = nlohmann::json::parse(body);
    if (!doc.is_array()) return out;
    for (const auto& e : doc) {
        SdLogEntry entry;
        if (e.contains("name") && e["name"].is_string())
            entry.name = e["name"].get<std::string>();
        if (e.contains("size") && e["size"].is_number_integer())
            entry.size = e["size"].get<long long>();
        if (e.contains("mtime_unix") && e["mtime_unix"].is_number_integer())
            entry.mtime_unix = e["mtime_unix"].get<long long>();
        if (!entry.name.empty())
            out.push_back(std::move(entry));
    }
    return out;
}

std::string build_sd_log_path(std::string_view prefix,
                              std::string_view filename) {
    std::string out(prefix);
    if (!out.empty() && out.back() != '/') out += '/';
    for (char c : filename) {
        unsigned char uc = static_cast<unsigned char>(c);
        bool safe = std::isalnum(uc) || c == '.' || c == '-' || c == '_';
        if (safe) {
            out += c;
        } else {
            char buf[8];
            std::snprintf(buf, sizeof(buf), "%%%02X", uc);
            out += buf;
        }
    }
    return out;
}

#ifdef _WIN32

std::optional<std::vector<SdLogEntry>> fetch_sd_log_list(
    std::string_view host, int port,
    std::chrono::milliseconds timeout) {
    auto raw = http_get_bounded(host, port, "/api/sd/logs", timeout,
                                256 * 1024);
    if (!raw) return std::nullopt;
    auto body = parse_http_body(*raw);
    if (!body) return std::nullopt;
    try {
        return parse_sd_log_list_json(*body);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<std::string> fetch_sd_log_bytes(
    std::string_view host, int port,
    std::string_view filename,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes) {
    // max_bytes covers the raw response including headers; give the
    // caller some headroom for a couple of KB of HTTP header framing.
    std::string path = build_sd_log_path("/api/sd/logs", filename);
    auto raw = http_get_bounded(host, port, path, timeout,
                                max_bytes + 4096);
    if (!raw) return std::nullopt;
    return parse_http_body(*raw);
}

std::optional<std::vector<SdLogEntry>> fetch_sd_tune_list(
    std::string_view host, int port,
    std::chrono::milliseconds timeout) {
    auto raw = http_get_bounded(host, port, "/api/sd/tunes", timeout,
                                256 * 1024);
    if (!raw) return std::nullopt;
    auto body = parse_http_body(*raw);
    if (!body) return std::nullopt;
    try {
        return parse_sd_log_list_json(*body);
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

std::optional<std::string> fetch_sd_tune_bytes(
    std::string_view host, int port,
    std::string_view filename,
    std::chrono::milliseconds timeout,
    std::size_t max_bytes) {
    std::string path = build_sd_log_path("/api/sd/tunes", filename);
    auto raw = http_get_bounded(host, port, path, timeout,
                                max_bytes + 4096);
    if (!raw) return std::nullopt;
    return parse_http_body(*raw);
}

#endif  // _WIN32

}  // namespace tuner_core::airbear_api
