// SPDX-License-Identifier: MIT
//
// tuner_core::teensy_hex_image — pure-logic port of the Intel HEX
// parser + block-address planner + payload builder from the legacy
// Python `FirmwareFlashService._flash_internal_teensy` path.
//
// Owns:
//   - read_hex()                 parse Intel HEX text -> {addr -> byte} map
//   - block_addresses()          list of block-aligned write targets
//   - block_is_blank()           skip-blank-block helper
//   - build_write_payload()      per-block USB HID write payload
//   - build_boot_payload()       final reboot USB HID payload
//
// I/O (USB HID open/write, file read) stays in the non-pure
// `teensy_hid_flasher` module. Every helper here is byte-for-byte
// parity with the Python original.

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace tuner_core::teensy_hex_image {

// Matches the private `_TeensyMcuSpec` in the Python service. Kept
// independent of `firmware_flash_builder::TeensyMcuSpec` so this
// module has no cross-dep; the caller converts.
struct McuSpec {
    std::string name;
    int code_size = 0;
    int block_size = 0;
};

// Parsed Intel HEX image — sparse byte map + total byte count.
struct HexImage {
    std::unordered_map<int, std::uint8_t> bytes_by_address;
    int byte_count = 0;
};

// Parse an Intel HEX text buffer (the full file contents) into a
// HexImage. Throws `std::runtime_error` on malformed lines, bad
// checksums, or data outside the supported memory range. Stops at
// the first `01` (end-of-file) record.
//
// `spec.code_size` bounds the supported address range; the Teensy 4.x
// `0x60000000` flash origin is rebased to 0x00000000 when detected, to
// match the Python parser's "if code_size > 1 MiB and addr in flash
// aperture then subtract 0x60000000" branch.
HexImage read_hex(std::string_view hex_text, const McuSpec& spec);

// Is every byte in `[addr, addr + block_size)` either absent from the
// image or equal to 0xFF? Mirrors `_teensy_block_is_blank`.
bool block_is_blank(const HexImage& image, int addr, int block_size) noexcept;

// Compute the ordered list of block-aligned addresses that actually
// need to be written. The first block (address 0) is always present
// even if blank — matches the Python walker, which emits block 0
// unconditionally so the bootloader sees "at least one" payload.
std::vector<int> block_addresses(const HexImage& image, const McuSpec& spec);

// Build the USB HID write payload for a single block. Block sizes of
// 512 or 1024 use a 3-byte address header + 64-byte pad + block data
// (total = block_size + 64). Other block sizes use a 2-byte address
// header + block data (total = block_size + 2), with the low byte
// depending on whether the code section is <64 KiB or not.
std::vector<std::uint8_t> build_write_payload(const HexImage& image,
                                              const McuSpec& spec,
                                              int addr);

// Build the USB HID payload that requests the Teensy bootloader to
// jump to the freshly flashed application. Three 0xFF bytes followed
// by padding up to `block_size + 64` (for 512/1024 block sizes) or
// `block_size + 2` otherwise. Mirrors `_teensy_boot`.
std::vector<std::uint8_t> build_boot_payload(const McuSpec& spec);

}  // namespace tuner_core::teensy_hex_image
