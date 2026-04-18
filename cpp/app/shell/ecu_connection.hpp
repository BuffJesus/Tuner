// SPDX-License-Identifier: MIT
//
// Shared ECU connection state.
//
// One instance lives in TunerMainWindow and is shared with the LIVE tab
// timer, TUNE crosshair timer, status bar timer, and sidebar indicator.
// All access happens on the Qt GUI thread (timer callbacks), so no mutex
// is needed.

#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

#include "tuner_core/ecu_definition_compiler.hpp"
#include "tuner_core/speeduino_connect_strategy.hpp"
#include "tuner_core/speeduino_controller.hpp"
#include "tuner_core/speeduino_live_data_decoder.hpp"

struct EcuConnection {
    std::unique_ptr<tuner_core::speeduino_controller::SpeeduinoController> controller;
    tuner_core::speeduino_controller::ConnectionInfo info;
    bool connected = false;

    // Last decoded runtime snapshot — channel name → value.
    std::unordered_map<std::string, double> runtime;

    // Output channel layouts from the parsed INI (needed to decode
    // the runtime packet). Built once after INI load.
    std::vector<tuner_core::speeduino_live_data_decoder::OutputChannelLayout> channel_layouts;
    std::size_t runtime_packet_size = 0;

    // Page cache — stores raw page bytes read from the ECU. Needed by
    // bit-field scalar encoding (read-modify-write) and for future
    // ECU-vs-local mismatch detection. Keyed by page number.
    std::unordered_map<int, std::vector<std::uint8_t>> page_cache;

    // Pages that have been written to RAM but not yet burned to flash.
    // Iterated in sorted order during burn.
    std::set<int> dirty_pages;

    // Last parsed capability header from the legacy `'f'` query
    // (blocking factors only).
    tuner_core::speeduino_connect_strategy::CapabilityHeader capabilities;

    // FW-003 `'K'` capability response — board ID, feature flags,
    // signature, and (schema v2+) schema_fingerprint. Zero-init on a
    // failed probe (parsed=false).
    tuner_core::speeduino_connect_strategy::KCapabilityResponse k_capabilities;

    // Poll the ECU for runtime data and update `runtime` map.
    // Returns true on success, false on error (disconnects on failure).
    bool poll_runtime();

    // Read a page slice from the ECU (or return cached bytes).
    // For bit-field scalar encoding we need the current byte(s) at
    // the target offset before we can do the read-modify-write.
    std::vector<std::uint8_t> read_page_slice(int page, int offset, int length);

    // Write parameter bytes to ECU RAM, respecting the blocking factor.
    // Mirrors Python's `_write_page_chunk` — splits large payloads into
    // chunks no bigger than the negotiated blocking factor.
    void write_chunked(int page, int offset,
                       const std::uint8_t* data, std::size_t size,
                       bool is_table = false);

    // Read all ECU pages into the page cache. Computes page sizes from
    // the definition by finding max(offset + data_size) per page number
    // across all scalars and arrays. Mirrors the Python read_from_ecu()
    // flow that invalidates the cache and reads every known page.
    // Returns the number of pages successfully read.
    int read_all_pages(const tuner_core::NativeEcuDefinition& def);

    // Get a runtime value by channel name (returns 0.0 if not found).
    double get(const std::string& name) const;

    // Disconnect and clean up — leaves the EcuConnection in a clean
    // disconnected state (controller destroyed, transport released,
    // info cleared). Safe to call multiple times; safe to call after a
    // failed connect attempt (TN-001).
    void close();
};
