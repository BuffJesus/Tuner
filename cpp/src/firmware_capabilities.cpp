// SPDX-License-Identifier: MIT
#include "tuner_core/firmware_capabilities.hpp"
#include <cstdio>

namespace tuner_core::firmware_capabilities {

std::string Capabilities::runtime_trust_summary() const {
    std::string parts;
    auto append = [&](const char* s) {
        if (!parts.empty()) parts += "; ";
        parts += s;
    };
    if (supports_runtime_status_a)
        append("runtimeStatusA: trusted");
    else
        append("runtimeStatusA: uncertain (not advertised)");
    if (supports_board_capabilities_channel)
        append("boardCapabilities: available");
    if (supports_spi_flash_health_channel)
        append("spiFlashHealth: available");
    if (experimental_u16p2)
        append("U16P2: experimental");
    if (live_data_size.has_value()) {
        char buf[64];
        std::snprintf(buf, sizeof(buf), "live_data_size: %d", *live_data_size);
        parts += "; ";
        parts += buf;
    }
    return parts.empty() ? "no capability detail" : parts;
}

std::set<std::string> Capabilities::uncertain_channel_groups() const {
    std::set<std::string> uncertain;
    if (!supports_runtime_status_a) uncertain.insert("runtimeStatusA");
    if (!supports_board_capabilities_channel) uncertain.insert("boardCapabilities");
    if (!supports_spi_flash_health_channel) uncertain.insert("spiFlashHealth");
    return uncertain;
}

}  // namespace tuner_core::firmware_capabilities
