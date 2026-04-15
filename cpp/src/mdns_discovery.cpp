// SPDX-License-Identifier: MIT
#include "tuner_core/mdns_discovery.hpp"

#include <algorithm>
#include <cctype>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#endif

namespace tuner_core::mdns_discovery {

namespace {

std::string trim_copy(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return std::string(s);
}

std::string ascii_lower(std::string_view s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

}  // namespace

std::string ResolvedHost::display_label() const {
    std::string base = hostname.empty() ? "mDNS host" : hostname;
    if (!ip_address.empty()) {
        base += " @ ";
        base += ip_address;
    }
    if (port > 0) {
        base += ":";
        base += std::to_string(port);
    }
    base += " (mDNS)";
    return base;
}

std::optional<std::string> normalize_hostname(std::string_view hostname) {
    auto trimmed = trim_copy(hostname);
    if (trimmed.empty()) return std::nullopt;

    auto lowered = ascii_lower(trimmed);
    if (lowered.size() < 7 || lowered.substr(lowered.size() - 6) != ".local") {
        return std::nullopt;
    }
    return lowered;
}

void merge_result(std::vector<ResolvedHost>& out, ResolvedHost result) {
    auto normalized = normalize_hostname(result.hostname);
    if (normalized) result.hostname = *normalized;

    auto same = [&](const ResolvedHost& existing) {
        if (!result.ip_address.empty() && !existing.ip_address.empty()) {
            return existing.ip_address == result.ip_address && existing.port == result.port;
        }
        auto existing_name = normalize_hostname(existing.hostname);
        return normalized && existing_name && *normalized == *existing_name
            && existing.port == result.port;
    };

    for (auto& entry : out) {
        if (same(entry)) {
            entry = std::move(result);
            return;
        }
    }
    out.push_back(std::move(result));
}

#ifdef _WIN32

std::optional<ResolvedHost> resolve(std::string_view hostname, int port) {
    auto normalized = normalize_hostname(hostname);
    if (!normalized) return std::nullopt;

    addrinfo hints{};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    addrinfo* result = nullptr;
    auto port_str = std::to_string(port);
    int rc = getaddrinfo(normalized->c_str(), port_str.c_str(), &hints, &result);
    if (rc != 0 || result == nullptr) return std::nullopt;

    ResolvedHost out;
    out.hostname = *normalized;
    out.port = port;

    for (addrinfo* it = result; it != nullptr; it = it->ai_next) {
        if (it->ai_family != AF_INET || it->ai_addrlen < sizeof(sockaddr_in)) continue;
        char ip_buf[INET_ADDRSTRLEN]{};
        auto* addr = reinterpret_cast<sockaddr_in*>(it->ai_addr);
        if (inet_ntop(AF_INET, &addr->sin_addr, ip_buf, sizeof(ip_buf))) {
            out.ip_address = ip_buf;
            break;
        }
    }
    freeaddrinfo(result);

    if (out.ip_address.empty()) return std::nullopt;
    return out;
}

#endif  // _WIN32

}  // namespace tuner_core::mdns_discovery
