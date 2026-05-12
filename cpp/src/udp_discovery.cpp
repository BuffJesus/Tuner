// SPDX-License-Identifier: MIT
#include "tuner_core/udp_discovery.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <string>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#else
// POSIX (Linux + macOS) — Phase 20 slice 6.
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <thread>
#endif

namespace tuner_core::udp_discovery {

namespace {

std::string_view trim(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) s.remove_prefix(1);
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) s.remove_suffix(1);
    return s;
}

int parse_int(std::string_view s, int fallback) {
    auto t = trim(s);
    if (t.empty()) return fallback;
    int sign = 1;
    std::size_t i = 0;
    if (t[0] == '-') { sign = -1; ++i; }
    else if (t[0] == '+') { ++i; }
    if (i >= t.size()) return fallback;
    int v = 0;
    for (; i < t.size(); ++i) {
        char c = t[i];
        if (c < '0' || c > '9') return fallback;
        v = v * 10 + (c - '0');
    }
    return sign * v;
}

}  // namespace

std::string DiscoveredDevice::display_label() const {
    std::string base = name.empty() ? slave : name;
    if (base.empty()) base = "Unknown device";
    if (!source_ip.empty()) {
        base += " @ ";
        base += source_ip;
        if (port > 0) {
            base += ":";
            base += std::to_string(port);
        }
    }
    return base;
}

std::optional<DiscoveredDevice> parse_announcement(std::string_view text) {
    DiscoveredDevice d;
    d.raw = std::string(text);

    std::size_t pos = 0;
    while (pos <= text.size()) {
        std::size_t nl = text.find('\n', pos);
        std::string_view line = (nl == std::string_view::npos)
            ? text.substr(pos)
            : text.substr(pos, nl - pos);
        pos = (nl == std::string_view::npos) ? text.size() + 1 : nl + 1;

        auto colon = line.find(':');
        if (colon == std::string_view::npos) continue;
        auto key = trim(line.substr(0, colon));
        auto val = trim(line.substr(colon + 1));
        if (key.empty()) continue;

        if (key == "slave")               d.slave = std::string(val);
        else if (key == "id")             d.id = std::string(val);
        else if (key == "serial")         d.serial = std::string(val);
        else if (key == "projectName")    d.project_name = std::string(val);
        else if (key == "name")           d.name = std::string(val);
        else if (key == "protocol")       d.protocol = std::string(val);
        else if (key == "port")           d.port = parse_int(val, 0);
        else if (key == "connectionState") d.connection_state = parse_int(val, 0);
    }

    if (d.slave.empty()) return std::nullopt;
    return d;
}

void merge_device(std::vector<DiscoveredDevice>& out, DiscoveredDevice d) {
    auto same = [&](const DiscoveredDevice& existing) {
        if (!d.serial.empty() && !existing.serial.empty()) return existing.serial == d.serial;
        return existing.source_ip == d.source_ip && existing.port == d.port;
    };
    for (auto& e : out) {
        if (same(e)) {
            e = std::move(d);
            return;
        }
    }
    out.push_back(std::move(d));
}

#ifdef _WIN32

std::vector<DiscoveredDevice> discover(std::chrono::milliseconds timeout) {
    std::vector<DiscoveredDevice> out;

    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock == INVALID_SOCKET) return out;

    BOOL broadcast = TRUE;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST,
               reinterpret_cast<const char*>(&broadcast), sizeof(broadcast));

    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = INADDR_ANY;
    local.sin_port = 0;  // ephemeral
    if (bind(sock, reinterpret_cast<sockaddr*>(&local), sizeof(local)) != 0) {
        closesocket(sock);
        return out;
    }

    sockaddr_in dest{};
    dest.sin_family = AF_INET;
    dest.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    dest.sin_port = htons(kDiscoveryPort);

    const char* probe = kDiscoveryProbe;
    sendto(sock, probe, static_cast<int>(std::strlen(probe)), 0,
           reinterpret_cast<sockaddr*>(&dest), sizeof(dest));

    // Non-blocking recv loop until deadline.
    u_long nonblock = 1;
    ioctlsocket(sock, FIONBIO, &nonblock);

    auto deadline = std::chrono::steady_clock::now() + timeout;
    char buf[2048];
    while (std::chrono::steady_clock::now() < deadline) {
        sockaddr_in from{};
        int from_len = sizeof(from);
        int n = recvfrom(sock, buf, sizeof(buf) - 1, 0,
                         reinterpret_cast<sockaddr*>(&from), &from_len);
        if (n > 0) {
            buf[n] = '\0';
            auto dev_opt = parse_announcement(std::string_view(buf, n));
            if (dev_opt) {
                char ip_str[INET_ADDRSTRLEN]{};
                inet_ntop(AF_INET, &from.sin_addr, ip_str, sizeof(ip_str));
                dev_opt->source_ip = ip_str;
                merge_device(out, std::move(*dev_opt));
            }
        } else {
            int err = WSAGetLastError();
            if (err != WSAEWOULDBLOCK) break;
            Sleep(20);
        }
    }

    closesocket(sock);
    return out;
}

#else  // POSIX (Linux + macOS) — Phase 20 slice 6

std::vector<DiscoveredDevice> discover(std::chrono::milliseconds timeout) {
    std::vector<DiscoveredDevice> out;

    int sock = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) return out;

    int broadcast = 1;
    ::setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));

    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = INADDR_ANY;
    local.sin_port = 0;  // ephemeral
    if (::bind(sock, reinterpret_cast<sockaddr*>(&local), sizeof(local)) != 0) {
        ::close(sock);
        return out;
    }

    sockaddr_in dest{};
    dest.sin_family = AF_INET;
    dest.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    dest.sin_port = htons(kDiscoveryPort);

    const char* probe = kDiscoveryProbe;
    ::sendto(sock, probe, std::strlen(probe), 0,
             reinterpret_cast<sockaddr*>(&dest), sizeof(dest));

    // Non-blocking recv loop until deadline.
    int flags = ::fcntl(sock, F_GETFL, 0);
    if (flags >= 0) ::fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    auto deadline = std::chrono::steady_clock::now() + timeout;
    char buf[2048];
    while (std::chrono::steady_clock::now() < deadline) {
        sockaddr_in from{};
        socklen_t from_len = sizeof(from);
        ssize_t n = ::recvfrom(sock, buf, sizeof(buf) - 1, 0,
                               reinterpret_cast<sockaddr*>(&from), &from_len);
        if (n > 0) {
            buf[n] = '\0';
            auto dev_opt = parse_announcement(
                std::string_view(buf, static_cast<std::size_t>(n)));
            if (dev_opt) {
                char ip_str[INET_ADDRSTRLEN]{};
                ::inet_ntop(AF_INET, &from.sin_addr, ip_str, sizeof(ip_str));
                dev_opt->source_ip = ip_str;
                merge_device(out, std::move(*dev_opt));
            }
        } else if (n < 0) {
            if (errno == EINTR) continue;
            if (errno != EAGAIN && errno != EWOULDBLOCK) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
    }

    ::close(sock);
    return out;
}

#endif  // _WIN32 / POSIX

}  // namespace tuner_core::udp_discovery
