// SPDX-License-Identifier: MIT
//
// tuner_core::firmware_capabilities — port of FirmwareCapabilities domain.
// Fifty-third sub-slice of the Phase 14 workspace-services port (Slice 4).

#pragma once

#include <optional>
#include <set>
#include <string>

namespace tuner_core::firmware_capabilities {

struct Capabilities {
    std::string source;
    std::optional<int> serial_protocol_version;
    std::optional<int> blocking_factor;
    std::optional<int> table_blocking_factor;
    std::optional<int> live_data_size;
    bool supports_board_capabilities_channel = false;
    bool supports_spi_flash_health_channel = false;
    bool supports_runtime_status_a = false;
    bool experimental_u16p2 = false;

    std::string runtime_trust_summary() const;
    std::set<std::string> uncertain_channel_groups() const;
};

}  // namespace tuner_core::firmware_capabilities
