// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_connect_strategy — pure-logic port of the
// connect-time helpers in `SpeeduinoControllerClient`. These pick
// the right blocking factor, the right signature probe order, the
// right baud rate fallbacks, and the right connect delay before any
// I/O happens. They sit one layer above the framing / command / value
// codecs (sub-slices 70–73) and one layer below the orchestration
// loop in `SpeeduinoControllerClient` itself (which stays Python).
//
// All helpers take primitive arguments and return primitive results
// — no domain types — so the parity test can marshal the Python
// `EcuDefinition` / `FirmwareCapabilities` field-by-field without
// having to round-trip through nanobind class bindings.

#pragma once

#include <array>
#include <cstdint>
#include <map>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::speeduino_connect_strategy {

// `_command_char(raw, fallback)` parity. Returns the first character
// of `raw` if it's non-empty, otherwise `fallback`. Pure single-char
// picker.
char command_char(std::string_view raw, char fallback) noexcept;

// `_effective_blocking_factor(is_table)` parity. Picks the write-
// chunk size with the priority order:
//   firmware-advertised (table or scalar) > INI definition > 128
// `is_table=true` lets table_blocking_factor win for the firmware /
// definition lookups before falling through to the scalar variants.
//
// Each `std::optional<int>` is `nullopt` when the source had no
// value or when the value was zero (the Python `or` test treats
// both as missing — `None or 0` is falsy). Mirror that here by
// passing `nullopt` for both the missing and the zero case.
int effective_blocking_factor(bool is_table,
                              std::optional<int> firmware_blocking_factor,
                              std::optional<int> firmware_table_blocking_factor,
                              std::optional<int> definition_blocking_factor,
                              std::optional<int> definition_table_blocking_factor) noexcept;

// `_signature_probe_candidates` parity. Walks the candidate list
//   [definition.query_command, definition.version_info_command, "F", "Q", "S"]
// taking the first character of each via `command_char`, then
// dedupes while preserving order. Returns the resulting probe
// character sequence.
//
// Pass `query_command` / `version_info_command` as the raw INI
// strings (empty string when the field is missing on the Python
// side, mirroring the `definition.foo if definition else None`
// fall-through).
std::vector<char> signature_probe_candidates(std::string_view query_command,
                                             std::string_view version_info_command);

// `_baud_probe_candidates` parity. Walks
//   [current_baud, 115200, 230400, 57600, 9600]
// dedupes while preserving order, drops nullopt entries. If the
// resulting list is empty, returns a single-element list containing
// `nullopt` (matches Python's `candidates or [None]`).
std::vector<std::optional<int>> baud_probe_candidates(std::optional<int> current_baud);

// `_connect_delay_seconds` parity. Looks up
//   metadata["controllerConnectDelay"] or
//   metadata["connectDelay"] or
//   metadata["interWriteDelay"]
// (in that order — first non-empty wins), trims whitespace, splits
// on the first comma if present (so "1500,1000" becomes "1500"),
// parses as a float treated as milliseconds. Returns delay_ms / 1000
// when the parsed value is positive; otherwise falls back to 1.5.
//
// Pass metadata as a `map<string, string>` mirroring
// `EcuDefinition.metadata`. Missing keys are treated as missing.
double connect_delay_seconds(const std::map<std::string, std::string>& metadata);

// ---------------------------------------------------------------------
// Capability header + derived flags. Pure-logic half of
// `_read_capabilities`; the actual `'f'` command + 6-byte read is
// I/O and stays Python.
// ---------------------------------------------------------------------

// Parsed shape of the capability query response:
//   byte 0: must be 0x00 (otherwise treated as unknown)
//   byte 1: serial protocol version
//   bytes 2..4: blocking_factor       (big-endian u16)
//   bytes 4..6: table_blocking_factor (big-endian u16)
//
// Optional Firmware Slice 14B extension (pending commit):
//   bytes 6..38:  4 slots × 8 bytes = 32 bytes of truncated SHA-256
//                 fingerprints identifying the tune currently burned
//                 in each flash slot.
//   bytes 38..54: 16-byte truncated SHA-256 of `live_data_map.h` +
//                 `tune_storage_map.h` + `BOARD_ID`, baked at firmware
//                 build time (Phase 16 item 1: Definition hash in
//                 firmware capability). Desktop compares this against
//                 the loaded tune's `definition_hash` (when set) and
//                 warns on mismatch — prevents burning a tune built
//                 against a different firmware schema.
//   bytes 54..62: 64-bit per-page format bitmap (Phase 16 item 2).
//                 Bit i set = page i uses U16 encoding; bit clear = U08.
//                 Pre-14B firmware omits these 8 bytes so the desktop
//                 keeps inferring the format from the INI.
//   bytes 62..:   reserved for future extensions.
//
// Missing trailing bytes mean pre-14B firmware; the desktop treats
// absent fingerprints / absent definition hash as "unknown" rather
// than "mismatch" so the UI doesn't scream at every connect while the
// firmware PR is in flight.
struct CapabilityHeader {
    bool parsed = false;            // true iff payload is valid
    int serial_protocol_version = 0;
    int blocking_factor = 0;
    int table_blocking_factor = 0;

    // Hex-encoded 8-byte fingerprints per slot (16 hex chars). Empty
    // string = slot fingerprint not reported (pre-14B firmware) or the
    // slot is unused (firmware reports all zeros → "0000000000000000").
    std::array<std::string, 4> slot_fingerprints;

    // Hex-encoded 16-byte firmware definition hash (32 hex chars).
    // Empty = not reported. Identifies the firmware-side data layout
    // (channel map + tune storage map + board id) so a desktop tune
    // built against a different firmware can be caught at connect.
    std::string definition_hash;

    // Phase 16 item 2 — 64-bit per-page format bitmap. nullopt when
    // firmware omits the trailing bytes. When populated, bit i set
    // means page i is U16; otherwise U08. Lets the desktop skip the
    // INI-based inference for high-resolution 3D tables.
    std::optional<std::uint64_t> page_format_bitmap;
};

// `_read_capabilities` parity (payload parse half). Returns
// `parsed=false` when the payload is nullopt, shorter than 6 bytes,
// or does not start with 0x00. Mirrors Python's
//   if payload is not None and len(payload) >= 6 and payload[0] == 0x00:
// Pure byte arithmetic — no I/O.
CapabilityHeader parse_capability_header(
    std::optional<std::span<const std::uint8_t>> payload);

// Convenience: pick the capability source string from the parsed
// header shape. Returns "serial+definition" when `parsed=true`,
// "definition" otherwise. Mirrors the Python source assignment.
std::string capability_source(const CapabilityHeader& header);

// One output channel field carrying the minimum info needed for
// `_live_data_size` + `_has_output_channel`. Mirrors
// `OutputChannelDefinition` from the Python side.
struct OutputChannelField {
    std::string name;
    std::optional<int> offset;  // `field.offset or 0` -> nullopt means 0
    std::string data_type;      // U08 / S08 / U16 / S16 / U32 / S32 / F32
};

// `_live_data_size` parity. Returns `nullopt` when `channels` is
// empty (matches the Python `if ... or not output_channel_definitions`
// early-return). Otherwise returns `max((field.offset or 0) + data_size(field.data_type))`
// over all channels. Invalid `data_type` strings throw
// `std::runtime_error` from `speeduino_value_codec::parse_data_type`.
std::optional<int> compute_live_data_size(
    const std::vector<OutputChannelField>& channels);

// `_has_output_channel(*names)` parity. Returns true iff any of
// `targets` is present in `channel_names`. Pure set membership.
bool has_any_output_channel(const std::vector<std::string>& channel_names,
                            const std::vector<std::string>& targets);

// `experimental_u16p2` parity. Returns true iff the uppercased
// signature contains the substring "U16P2". Mirrors
// `"U16P2" in (self.firmware_signature or "").upper()`.
bool is_experimental_u16p2_signature(std::string_view signature) noexcept;

// `_probe_signature` filter parity. Returns true iff the response
// should be accepted as a valid signature candidate: non-empty,
// not equal to the echoed command, and the command character is
// not 'F' (the 'F' probe always echoes the firmware identifier
// string on Speeduino but does not itself return the signature).
bool should_accept_probe_response(char command, std::string_view response) noexcept;

}  // namespace tuner_core::speeduino_connect_strategy
