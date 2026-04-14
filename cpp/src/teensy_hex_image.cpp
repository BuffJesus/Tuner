// SPDX-License-Identifier: MIT
#include "tuner_core/teensy_hex_image.hpp"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <cstring>
#include <stdexcept>
#include <string>

namespace tuner_core::teensy_hex_image {

namespace {

constexpr int kMaxTeensyMemorySize = 0x1000000;

int parse_hex_byte(std::string_view s, int lineno) {
    if (s.size() != 2) {
        throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
    }
    int out = 0;
    const auto* begin = s.data();
    const auto* end = s.data() + s.size();
    auto [ptr, ec] = std::from_chars(begin, end, out, 16);
    if (ec != std::errc{} || ptr != end) {
        throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
    }
    return out;
}

int parse_hex_word(std::string_view s, int lineno) {
    if (s.size() != 4) {
        throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
    }
    int out = 0;
    const auto* begin = s.data();
    const auto* end = s.data() + s.size();
    auto [ptr, ec] = std::from_chars(begin, end, out, 16);
    if (ec != std::errc{} || ptr != end) {
        throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
    }
    return out;
}

std::string_view trim(std::string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t' ||
                          s.front() == '\r' || s.front() == '\n')) {
        s.remove_prefix(1);
    }
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' ||
                          s.back() == '\r' || s.back() == '\n')) {
        s.remove_suffix(1);
    }
    return s;
}

}  // namespace

HexImage read_hex(std::string_view hex_text, const McuSpec& spec) {
    HexImage image;
    int extended_addr = 0;
    int lineno = 0;

    std::size_t pos = 0;
    while (pos <= hex_text.size()) {
        std::size_t nl = hex_text.find('\n', pos);
        std::string_view raw = (nl == std::string_view::npos)
            ? hex_text.substr(pos)
            : hex_text.substr(pos, nl - pos);
        pos = (nl == std::string_view::npos) ? hex_text.size() + 1 : nl + 1;
        ++lineno;

        auto line = trim(raw);
        if (line.empty()) continue;
        if (line.front() != ':' || line.size() < 11) {
            throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
        }

        int length = parse_hex_byte(line.substr(1, 2), lineno);
        int addr = parse_hex_word(line.substr(3, 4), lineno);
        int record_type = parse_hex_byte(line.substr(7, 2), lineno);

        const std::size_t data_text_len = static_cast<std::size_t>(length) * 2;
        if (line.size() < 9 + data_text_len + 2) {
            throw std::runtime_error("Invalid Intel HEX line " + std::to_string(lineno));
        }
        auto data_text = line.substr(9, data_text_len);
        int checksum = parse_hex_byte(line.substr(9 + data_text_len, 2), lineno);

        std::vector<int> data_bytes;
        data_bytes.reserve(static_cast<std::size_t>(length));
        for (int i = 0; i < length; ++i) {
            data_bytes.push_back(parse_hex_byte(data_text.substr(i * 2, 2), lineno));
        }

        int sum = length + ((addr >> 8) & 0xFF) + (addr & 0xFF) + record_type;
        for (int b : data_bytes) sum += b;
        if (((sum + checksum) & 0xFF) != 0) {
            throw std::runtime_error("Invalid Intel HEX checksum on line " + std::to_string(lineno));
        }

        if (record_type == 0x01) break;
        if (record_type == 0x02) {
            if (length != 2) {
                throw std::runtime_error("Invalid Intel HEX segment address on line " + std::to_string(lineno));
            }
            extended_addr = parse_hex_word(data_text, lineno) << 4;
            continue;
        }
        if (record_type == 0x04) {
            if (length != 2) {
                throw std::runtime_error("Invalid Intel HEX linear address on line " + std::to_string(lineno));
            }
            extended_addr = parse_hex_word(data_text, lineno) << 16;
            if (spec.code_size > 1048576 && spec.block_size >= 1024 &&
                extended_addr >= 0x60000000 &&
                extended_addr < 0x60000000 + spec.code_size) {
                extended_addr -= 0x60000000;
            }
            continue;
        }
        if (record_type != 0x00) continue;

        int base = addr + extended_addr;
        int limit = std::min(kMaxTeensyMemorySize, spec.code_size);
        if (base < 0 || base + length > limit) {
            throw std::runtime_error("HEX data on line " + std::to_string(lineno) +
                                     " is outside supported memory range");
        }
        for (int i = 0; i < length; ++i) {
            image.bytes_by_address[base + i] = static_cast<std::uint8_t>(data_bytes[i]);
        }
        image.byte_count += length;
    }

    return image;
}

bool block_is_blank(const HexImage& image, int addr, int block_size) noexcept {
    for (int i = 0; i < block_size; ++i) {
        auto it = image.bytes_by_address.find(addr + i);
        if (it != image.bytes_by_address.end() && it->second != 0xFF) {
            return false;
        }
    }
    return true;
}

std::vector<int> block_addresses(const HexImage& image, const McuSpec& spec) {
    std::vector<int> out;
    for (int addr = 0; addr < spec.code_size; addr += spec.block_size) {
        if (!out.empty()) {
            bool any_present = false;
            for (int i = 0; i < spec.block_size; ++i) {
                if (image.bytes_by_address.count(addr + i)) {
                    any_present = true;
                    break;
                }
            }
            if (!any_present) continue;
            if (block_is_blank(image, addr, spec.block_size)) continue;
        }
        out.push_back(addr);
    }
    return out;
}

std::vector<std::uint8_t> build_write_payload(const HexImage& image,
                                              const McuSpec& spec,
                                              int addr) {
    if (spec.block_size == 512 || spec.block_size == 1024) {
        std::vector<std::uint8_t> payload(spec.block_size + 64, 0);
        payload[0] = static_cast<std::uint8_t>(addr & 0xFF);
        payload[1] = static_cast<std::uint8_t>((addr >> 8) & 0xFF);
        payload[2] = static_cast<std::uint8_t>((addr >> 16) & 0xFF);
        for (int i = 0; i < spec.block_size; ++i) {
            auto it = image.bytes_by_address.find(addr + i);
            payload[64 + i] = (it != image.bytes_by_address.end()) ? it->second : 0xFF;
        }
        return payload;
    }

    std::vector<std::uint8_t> payload(spec.block_size + 2, 0);
    if (spec.code_size < 0x10000) {
        payload[0] = static_cast<std::uint8_t>(addr & 0xFF);
        payload[1] = static_cast<std::uint8_t>((addr >> 8) & 0xFF);
    } else {
        payload[0] = static_cast<std::uint8_t>((addr >> 8) & 0xFF);
        payload[1] = static_cast<std::uint8_t>((addr >> 16) & 0xFF);
    }
    for (int i = 0; i < spec.block_size; ++i) {
        auto it = image.bytes_by_address.find(addr + i);
        payload[2 + i] = (it != image.bytes_by_address.end()) ? it->second : 0xFF;
    }
    return payload;
}

std::vector<std::uint8_t> build_boot_payload(const McuSpec& spec) {
    const int write_size = spec.block_size +
        ((spec.block_size == 512 || spec.block_size == 1024) ? 64 : 2);
    std::vector<std::uint8_t> payload(write_size, 0);
    payload[0] = 0xFF;
    payload[1] = 0xFF;
    payload[2] = 0xFF;
    return payload;
}

}  // namespace tuner_core::teensy_hex_image
