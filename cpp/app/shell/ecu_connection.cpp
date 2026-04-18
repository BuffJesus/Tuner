// SPDX-License-Identifier: MIT

#include "shell/ecu_connection.hpp"

#include "tuner_core/speeduino_value_codec.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>

bool EcuConnection::poll_runtime() {
    if (!connected || !controller) return false;
    if (runtime_packet_size == 0) return false;
    try {
        auto bytes = controller->read_runtime(
            0, static_cast<std::uint16_t>(runtime_packet_size));
        if (bytes.size() < runtime_packet_size) return false;
        auto values = tuner_core::speeduino_live_data_decoder::decode_runtime_packet(
            channel_layouts, bytes);
        for (const auto& v : values) {
            runtime[v.name] = v.value;
        }
        return true;
    } catch (...) {
        // Connection lost — mark disconnected and log for debug.
        connected = false;
        try { controller->disconnect(); } catch (...) {}
        // debug_log not in scope here; console log only.
        std::printf("[live] ECU connection lost\n");
        std::fflush(stdout);
        return false;
    }
}

std::vector<std::uint8_t> EcuConnection::read_page_slice(int page, int offset, int length) {
    if (!connected || !controller) return {};
    // Check cache first.
    auto it = page_cache.find(page);
    if (it != page_cache.end() &&
        static_cast<int>(it->second.size()) >= offset + length) {
        return std::vector<std::uint8_t>(
            it->second.begin() + offset,
            it->second.begin() + offset + length);
    }
    // Targeted read from ECU.
    return controller->read_page(
        static_cast<std::uint8_t>(page),
        static_cast<std::uint16_t>(offset),
        static_cast<std::uint16_t>(length));
}

void EcuConnection::write_chunked(int page, int offset,
                                  const std::uint8_t* data, std::size_t size,
                                  bool is_table) {
    if (!connected || !controller) return;
    int max_chunk = is_table
        ? info.table_blocking_factor
        : info.blocking_factor;
    if (max_chunk <= 0) max_chunk = 128;
    std::size_t sent = 0;
    while (sent < size) {
        std::size_t chunk_size = std::min(
            static_cast<std::size_t>(max_chunk), size - sent);
        controller->write_parameter(
            static_cast<std::uint8_t>(page),
            static_cast<std::uint16_t>(offset + static_cast<int>(sent)),
            data + sent, chunk_size);
        sent += chunk_size;
        if (sent < size) {
            // 10ms inter-chunk delay — matches Python.
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
    // Update page cache with the written bytes.
    auto& cached = page_cache[page];
    if (cached.size() < static_cast<std::size_t>(offset) + size) {
        cached.resize(static_cast<std::size_t>(offset) + size, 0);
    }
    std::memcpy(cached.data() + offset, data, size);
    dirty_pages.insert(page);
}

int EcuConnection::read_all_pages(const tuner_core::NativeEcuDefinition& def) {
    if (!connected || !controller) return 0;
    namespace svc = tuner_core::speeduino_value_codec;

    // Compute page sizes: max(offset + data_size) per page.
    std::map<int, int> page_sizes;
    for (const auto& sc : def.constants.scalars) {
        if (!sc.page.has_value() || !sc.offset.has_value()) continue;
        int page = *sc.page;
        int end = *sc.offset;
        try { end += static_cast<int>(svc::data_size_bytes(svc::parse_data_type(sc.data_type))); }
        catch (...) { end += 1; }
        if (end > page_sizes[page]) page_sizes[page] = end;
    }
    for (const auto& ar : def.constants.arrays) {
        if (!ar.page.has_value() || !ar.offset.has_value()) continue;
        int page = *ar.page;
        int elem_size = 1;
        try { elem_size = static_cast<int>(svc::data_size_bytes(svc::parse_data_type(ar.data_type))); }
        catch (...) {}
        int end = *ar.offset + ar.rows * ar.columns * elem_size;
        if (end > page_sizes[page]) page_sizes[page] = end;
    }

    int read_count = 0;
    auto t0 = std::chrono::steady_clock::now();
    for (const auto& [page, size] : page_sizes) {
        if (size <= 0) continue;
        auto pt0 = std::chrono::steady_clock::now();
        try {
            auto data = controller->read_page(
                static_cast<std::uint8_t>(page), 0,
                static_cast<std::uint16_t>(size));
            auto pt1 = std::chrono::steady_clock::now();
            double pms = std::chrono::duration<double, std::milli>(pt1 - pt0).count();
            std::printf("PERF   page %d: %d bytes in %.0f ms (%.0f KB/s)\n",
                page, size, pms,
                pms > 0 ? (size / 1024.0) / (pms / 1000.0) : 0.0);
            std::fflush(stdout);
            if (!data.empty()) {
                page_cache[page] = std::move(data);
                read_count++;
            }
        } catch (const std::exception& ex) {
            std::printf("PERF   page %d (%d bytes): FAILED [%s]\n",
                page, size, ex.what());
            std::fflush(stdout);
            continue;
        }
    }
    auto elapsed = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - t0).count();
    std::printf("PERF   read_all_pages %d pages in %.0f ms\n",
                read_count, elapsed);
    std::fflush(stdout);
    return read_count;
}

double EcuConnection::get(const std::string& name) const {
    auto it = runtime.find(name);
    return (it != runtime.end()) ? it->second : 0.0;
}

void EcuConnection::close() {
    if (controller) {
        try { controller->disconnect(); } catch (...) {}
        controller.reset();
    }
    connected = false;
    info = {};
    runtime.clear();
    page_cache.clear();
    dirty_pages.clear();
}
