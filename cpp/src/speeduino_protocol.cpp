// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_protocol implementation. Pure-logic command
// shapes — no I/O.

#include "tuner_core/speeduino_protocol.hpp"

namespace tuner_core::speeduino_protocol {

std::vector<std::uint8_t> page_request(
    char command,
    std::uint8_t page,
    std::uint16_t offset,
    std::uint16_t length) {
    return {
        static_cast<std::uint8_t>(command),
        0x00u,
        page,
        static_cast<std::uint8_t>(offset & 0xFFu),
        static_cast<std::uint8_t>((offset >> 8) & 0xFFu),
        static_cast<std::uint8_t>(length & 0xFFu),
        static_cast<std::uint8_t>((length >> 8) & 0xFFu),
    };
}

std::vector<std::uint8_t> page_write_request(
    std::uint8_t page,
    std::uint16_t offset,
    std::span<const std::uint8_t> payload,
    char command) {
    auto header = page_request(
        command, page, offset, static_cast<std::uint16_t>(payload.size()));
    header.insert(header.end(), payload.begin(), payload.end());
    return header;
}

std::vector<std::uint8_t> runtime_request(std::uint16_t offset, std::uint16_t length) {
    return {
        static_cast<std::uint8_t>(kRuntimePollChar),
        0x00u,
        kSendOutputChannelsSelector,
        static_cast<std::uint8_t>(offset & 0xFFu),
        static_cast<std::uint8_t>((offset >> 8) & 0xFFu),
        static_cast<std::uint8_t>(length & 0xFFu),
        static_cast<std::uint8_t>((length >> 8) & 0xFFu),
    };
}

std::vector<std::uint8_t> burn_request(std::uint8_t page, char command) {
    return {
        static_cast<std::uint8_t>(command),
        0x00u,
        page,
    };
}

char select_command_char(const char* raw, char fallback) noexcept {
    if (raw == nullptr || raw[0] == '\0') return fallback;
    return raw[0];
}

}  // namespace tuner_core::speeduino_protocol
