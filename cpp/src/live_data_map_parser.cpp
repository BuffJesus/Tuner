// SPDX-License-Identifier: MIT
//
// tuner_core::live_data_map_parser implementation. Pure logic — uses
// `<regex>` to mirror the Python regex patterns one-for-one.

#include "tuner_core/live_data_map_parser.hpp"

#include <cctype>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace tuner_core::live_data_map_parser {

namespace {

std::string strip(std::string_view s) {
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.front()))) {
        s.remove_prefix(1);
    }
    while (!s.empty() && std::isspace(static_cast<unsigned char>(s.back()))) {
        s.remove_suffix(1);
    }
    return std::string(s);
}

std::string uppercase(std::string_view s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        out.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
    }
    return out;
}

// Replace every `"[LOCKED]"` substring with empty. Used to clean
// up the notes column.
std::string remove_substring(std::string s, std::string_view needle) {
    std::size_t pos = 0;
    while ((pos = s.find(needle, pos)) != std::string::npos) {
        s.erase(pos, needle.size());
    }
    return s;
}

// Mirror Python `clean_notes.split()[0]` — first whitespace-separated
// token, or empty if the string is empty/whitespace.
std::string first_word(std::string_view s) {
    auto first = s.find_first_not_of(" \t\r\n");
    if (first == std::string_view::npos) return "";
    auto last = s.find_first_of(" \t\r\n", first);
    if (last == std::string_view::npos) return std::string(s.substr(first));
    return std::string(s.substr(first, last - first));
}

// Same regex as the Python module — verbose mode collapsed.
const std::regex& row_regex() {
    static const std::regex re(
        R"(^\s*\*\s+)"
        R"((\d+(?:-\d+)?)\s+)"                                  // byte
        R"((-|\d+)\s+)"                                          // ridx
        R"((.+?)\s{2,})"                                         // field
        R"((U08(?:\s+bits)?|U16\s+LE|S16\s+LE|U32\s+LE)\s+)"    // encoding
        R"((.*?)\s*$)"                                           // notes
    );
    return re;
}

const std::regex& live_data_map_size_regex() {
    static const std::regex re(
        R"(#define\s+LIVE_DATA_MAP_SIZE\s+(\d+)U?)",
        std::regex::icase);
    return re;
}

const std::regex& och_offset_regex() {
    static const std::regex re(
        R"(OCH_OFFSET_([A-Z_]+)\s*=\s*(\d+)U?)",
        std::regex::icase);
    return re;
}

std::optional<ChannelEntry> parse_row(const std::string& line) {
    std::smatch m;
    if (!std::regex_match(line, m, row_regex())) return std::nullopt;

    ChannelEntry e;
    std::string byte_text = m[1].str();
    auto dash = byte_text.find('-');
    if (dash != std::string::npos) {
        e.byte_start = std::stoi(byte_text.substr(0, dash));
        e.byte_end = std::stoi(byte_text.substr(dash + 1));
    } else {
        e.byte_start = e.byte_end = std::stoi(byte_text);
    }

    std::string ridx_text = m[2].str();
    if (ridx_text != "-") {
        e.readable_index = std::stoi(ridx_text);
    }

    e.encoding = parse_encoding(m[4].str());
    std::string notes = m[5].str();
    e.locked = notes.find("[LOCKED]") != std::string::npos;
    std::string clean_notes = strip(remove_substring(notes, "[LOCKED]"));

    // Choose name: first whitespace token of clean_notes, falling
    // back to the field name. The Python service skips
    // `"DEPRECATED:"` notes too — preserve that.
    std::string field = strip(m[3].str());
    std::string name = clean_notes.empty() ? field : first_word(clean_notes);
    if (uppercase(name) == "DEPRECATED:") {
        name = field;
    }

    e.name = std::move(name);
    e.field = std::move(field);
    e.notes = std::move(clean_notes);
    return e;
}

}  // namespace

std::string_view to_string(ChannelEncoding e) noexcept {
    switch (e) {
        case ChannelEncoding::U08:      return "U08";
        case ChannelEncoding::U08_BITS: return "U08_BITS";
        case ChannelEncoding::U16_LE:   return "U16_LE";
        case ChannelEncoding::S16_LE:   return "S16_LE";
        case ChannelEncoding::U32_LE:   return "U32_LE";
        case ChannelEncoding::UNKNOWN:  return "UNKNOWN";
    }
    return "UNKNOWN";
}

ChannelEncoding parse_encoding(std::string_view text) {
    auto upper = uppercase(strip(text));
    // Replace whitespace with underscores: "U08 bits" → "U08_BITS"
    for (char& c : upper) {
        if (c == ' ') c = '_';
    }
    if (upper == "U08")      return ChannelEncoding::U08;
    if (upper == "U08_BITS") return ChannelEncoding::U08_BITS;
    if (upper == "U16_LE")   return ChannelEncoding::U16_LE;
    if (upper == "S16_LE")   return ChannelEncoding::S16_LE;
    if (upper == "U32_LE")   return ChannelEncoding::U32_LE;
    return ChannelEncoding::UNKNOWN;
}

int byte_width(ChannelEncoding e) noexcept {
    switch (e) {
        case ChannelEncoding::U08:      return 1;
        case ChannelEncoding::U08_BITS: return 1;
        case ChannelEncoding::U16_LE:   return 2;
        case ChannelEncoding::S16_LE:   return 2;
        case ChannelEncoding::U32_LE:   return 4;
        case ChannelEncoding::UNKNOWN:  return 0;
    }
    return 0;
}

ChannelContract parse_text(
    std::string_view text,
    const std::optional<std::string>& firmware_signature) {
    ChannelContract contract;
    contract.firmware_signature = firmware_signature;

    // Walk lines for row matches.
    std::string buffer(text);
    std::size_t pos = 0;
    while (pos < buffer.size()) {
        std::size_t line_end = buffer.find('\n', pos);
        std::string line = buffer.substr(
            pos, line_end == std::string::npos ? std::string::npos : line_end - pos);
        // Strip trailing CR if present
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto entry = parse_row(line);
        if (entry.has_value()) contract.entries.push_back(std::move(*entry));
        if (line_end == std::string::npos) break;
        pos = line_end + 1;
    }

    // LIVE_DATA_MAP_SIZE
    {
        std::smatch m;
        if (std::regex_search(buffer, m, live_data_map_size_regex())) {
            contract.log_entry_size = std::stoi(m[1].str());
        }
    }

    // OCH_OFFSET_* constants
    {
        auto begin = std::sregex_iterator(buffer.begin(), buffer.end(), och_offset_regex());
        auto end = std::sregex_iterator();
        for (auto it = begin; it != end; ++it) {
            std::string key = uppercase((*it)[1].str());
            int value = std::stoi((*it)[2].str());
            if (key == "RUNTIME_STATUS_A") {
                contract.runtime_status_a_offset = value;
            } else if (key == "BOARD_CAPABILITY_FLAGS") {
                contract.board_capability_flags_offset = value;
            } else if (key == "FLASH_HEALTH_STATUS") {
                contract.flash_health_status_offset = value;
            }
        }
    }

    return contract;
}

ChannelContract parse_file(
    const std::filesystem::path& path,
    const std::optional<std::string>& firmware_signature) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw std::runtime_error(
            std::string("live_data_map.h not found: ") + path.string());
    }
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    return parse_text(buffer.str(), firmware_signature);
}

}  // namespace tuner_core::live_data_map_parser
