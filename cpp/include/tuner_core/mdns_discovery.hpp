// SPDX-License-Identifier: MIT
//
// tuner_core::mdns_discovery -- lightweight resolution of well-known
// mDNS hostnames like `speeduino.local` for the connection picker.
// The desktop already supports direct TCP connections when the operator
// types the host manually; this service lets the "Scan Network" path
// surface that same target as a discovered device.

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::mdns_discovery {

struct ResolvedHost {
    std::string hostname;   // e.g. "speeduino.local"
    std::string ip_address; // first resolved IPv4 address
    int port = 0;           // usually 2000 for Airbear's framed TCP bridge

    std::string display_label() const;
};

// Normalize an operator-entered host candidate. Current scope is narrow:
// trim whitespace, lowercase ASCII, and accept only `.local` names so the
// UI does not confuse ordinary DNS names with explicit mDNS discovery.
std::optional<std::string> normalize_hostname(std::string_view hostname);

// Merge a new result into an existing list, deduplicating by IPv4 address
// first, then by normalized hostname when the IP is absent.
void merge_result(std::vector<ResolvedHost>& out, ResolvedHost result);

#ifdef _WIN32
// Resolve a `.local` hostname using the OS resolver. Returns the first IPv4
// answer because the transport layer currently uses AF_INET only.
std::optional<ResolvedHost> resolve(std::string_view hostname, int port);
#endif

}  // namespace tuner_core::mdns_discovery
