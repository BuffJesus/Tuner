// SPDX-License-Identifier: MIT
//
// tuner_core::udp_discovery — EcuHub / TSDash UDP discovery protocol
// on port 21846. The desktop sends a broadcast probe; any Airbear-class
// device on the subnet replies unicast with a `key:value\n` announcement.
// Parse is pure-logic; the actual UDP I/O is Winsock-only (ifdef-guarded).
//
// Airbear reference: Airbear-main/src/discovery.cpp — builds the
// announcement with slave / id / serial (MAC) / port / protocol /
// connectionState / projectName / name fields.

#pragma once

#include <chrono>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::udp_discovery {

constexpr int kDiscoveryPort = 21846;
constexpr const char* kDiscoveryProbe = "DISCOVER_SLAVE_SERVER";

struct DiscoveredDevice {
    std::string slave;            // e.g. "Dropbear"
    std::string id;               // e.g. "0.2.0" (bridge firmware version)
    std::string serial;           // MAC "AA:BB:CC:DD:EE:FF"
    std::string project_name;     // e.g. "Dropbear"
    std::string name;             // e.g. "Dropbear v2.0.1"
    std::string protocol;         // "TCP" / "UDP"
    int port = 0;                 // e.g. 2000
    int connection_state = 0;     // 0 = idle, 1 = available
    std::string source_ip;        // populated by discover() from sender addr
    std::string raw;              // full announcement text, for future fields

    // Operator-facing label: "Dropbear v2.0.1 @ 192.168.1.50:2000"
    std::string display_label() const;
};

// Parse one announcement text (`key:value\n` lines). Returns a
// DiscoveredDevice when at least `slave` is present; otherwise nullopt.
// Unknown keys are preserved only in `raw`; known keys populate their
// fields. Whitespace around keys and values is trimmed.
std::optional<DiscoveredDevice> parse_announcement(std::string_view text);

// Merge a new device into an existing list, deduplicating by `serial`
// when present (else by `source_ip`). Mirrors the TSDash picker
// semantics where multiple replies from the same box collapse into one
// entry.
void merge_device(std::vector<DiscoveredDevice>& out, DiscoveredDevice d);

#ifdef _WIN32
// Broadcast the discovery probe and collect responses for up to
// `timeout`. Caller runs this on a worker thread (blocks for the full
// timeout). Returns the deduplicated list of discovered devices.
std::vector<DiscoveredDevice> discover(std::chrono::milliseconds timeout);
#endif

}  // namespace tuner_core::udp_discovery
