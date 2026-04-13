// SPDX-License-Identifier: MIT
//
// tuner_core::live_data_map_parser — port of `LiveDataMapParser`.
// Twenty-first sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Parses the Speeduino firmware `live_data_map.h` header into a
// `ChannelContract` POD. Reads three things from the header:
//
//   1. Doxygen comment rows like `* 4-5  4  MAP  U16 LE  map (kPa)`
//   2. `#define LIVE_DATA_MAP_SIZE  148U`
//   3. `static constexpr uint16_t OCH_OFFSET_*` constants for the
//      well-known special offsets

#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::live_data_map_parser {

enum class ChannelEncoding {
    U08,
    U08_BITS,
    U16_LE,
    S16_LE,
    U32_LE,
    UNKNOWN,
};

// Stringify to the same identifier the Python `ChannelEncoding`
// StrEnum produces.
std::string_view to_string(ChannelEncoding e) noexcept;

// Parse a text token (`"U08"`, `"U08 bits"`, `"U16 LE"`, etc.) into
// the enum. Mirrors `ChannelEncoding.from_header_text`.
ChannelEncoding parse_encoding(std::string_view text);

// Byte width of one value with the given encoding. Mirrors the
// `byte_width` property.
int byte_width(ChannelEncoding e) noexcept;

struct ChannelEntry {
    std::string name;
    int byte_start = 0;
    int byte_end = 0;             // inclusive
    std::optional<int> readable_index;  // nullopt when '-' in the header
    ChannelEncoding encoding = ChannelEncoding::UNKNOWN;
    std::string field;            // raw `currentStatus` member or expression
    std::string notes;            // free-text trailing notes (often the INI channel name)
    bool locked = false;          // true when the row carries a [LOCKED] tag

    int width() const noexcept { return byte_end - byte_start + 1; }
};

struct ChannelContract {
    int log_entry_size = 0;
    std::optional<std::string> firmware_signature;
    std::vector<ChannelEntry> entries;
    std::optional<int> runtime_status_a_offset;
    std::optional<int> board_capability_flags_offset;
    std::optional<int> flash_health_status_offset;
};

// Parse the header text. `firmware_signature` is forwarded as-is to
// the resulting contract — the parser doesn't pull it from the
// header.
ChannelContract parse_text(
    std::string_view text,
    const std::optional<std::string>& firmware_signature = std::nullopt);

// File loader convenience. Throws `std::runtime_error` if the file
// can't be opened (mirrors Python's `FileNotFoundError`).
ChannelContract parse_file(
    const std::filesystem::path& path,
    const std::optional<std::string>& firmware_signature = std::nullopt);

}  // namespace tuner_core::live_data_map_parser
