// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_controller implementation.

#include "tuner_core/speeduino_controller.hpp"

#include <cctype>
#include <chrono>
#include <cstring>
#include <stdexcept>
#include <thread>

namespace tuner_core::speeduino_controller {

SpeeduinoController::SpeeduinoController(
    std::unique_ptr<transport::Transport> transport)
    : transport_(std::move(transport)) {}

SpeeduinoController::~SpeeduinoController() {
    if (connected_) disconnect();
}

// ---------------------------------------------------------------
// Connect
// ---------------------------------------------------------------

ConnectionInfo SpeeduinoController::connect(
    const std::vector<int>& baud_candidates,
    char query_command,
    double settle_delay_s,
    StatusCallback on_status) {

    auto status = [&](const std::string& msg) {
        if (on_status) on_status(msg);
    };

    // Detect framing: TCP transports have write_framed.
    auto* tcp = dynamic_cast<transport::TcpTransport*>(transport_.get());
    framed_ = (tcp != nullptr);

    // For serial: probe each baud rate.
    auto* serial = dynamic_cast<transport::SerialTransport*>(transport_.get());
    if (serial) {
        for (int baud : baud_candidates) {
            status("Probing " + serial->port() + " @ " + std::to_string(baud) + "...");
            serial->set_baud_rate(baud);
            try {
                serial->open();
            } catch (...) {
                continue;
            }
            // Settle delay — let the ECU boot/reset after DTR toggle.
            serial->clear_buffers();
            std::this_thread::sleep_for(
                std::chrono::milliseconds(static_cast<int>(settle_delay_s * 1000)));
            serial->clear_buffers();

            // Try to read signature.
            std::string sig = probe_signature(query_command, 1.5);
            if (!sig.empty()) {
                info_.signature = sig;
                info_.framed = false;
                connected_ = true;
                status("Connected: " + sig + " @ " + std::to_string(baud));

                // Read capabilities (6-byte 'f' query).
                info_.capabilities.source = "definition";
                try {
                    std::vector<std::uint8_t> f_cmd = {static_cast<std::uint8_t>('f')};
                    send_command(f_cmd);
                    auto resp = recv_response(6, 1.5);
                    if (resp.size() >= 6 && resp[0] == 'f') {
                        info_.blocking_factor =
                            (static_cast<int>(resp[2]) << 8) | resp[3];
                        info_.table_blocking_factor =
                            (static_cast<int>(resp[4]) << 8) | resp[5];
                        if (info_.blocking_factor == 0) info_.blocking_factor = 128;
                        if (info_.table_blocking_factor == 0) info_.table_blocking_factor = 128;
                        info_.capabilities.source = "serial+definition";
                        info_.capabilities.serial_protocol_version =
                            (static_cast<int>(resp[1]) << 0);
                        info_.capabilities.blocking_factor = info_.blocking_factor;
                        info_.capabilities.table_blocking_factor = info_.table_blocking_factor;
                    }
                } catch (...) {
                    // Capabilities query is optional — default blocking factors are fine.
                }

                // TN-006: signature-suffix U16P2 detection so U16-aware
                // generator paths can be gated without re-parsing the
                // signature downstream.
                {
                    const std::string needle = "U16P2";
                    std::string upper;
                    upper.reserve(info_.signature.size());
                    for (char c : info_.signature) upper.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
                    info_.capabilities.experimental_u16p2 =
                        (upper.find(needle) != std::string::npos);
                }

                return info_;
            }
            serial->close();
        }
        throw std::runtime_error("No Speeduino ECU found on " + serial->port());
    }

    // For TCP: just open and probe once.
    if (tcp) {
        status("Connecting to " + tcp->host() + ":" + std::to_string(tcp->port()) + "...");
        tcp->open();
        tcp->clear_buffers();
        std::this_thread::sleep_for(
            std::chrono::milliseconds(static_cast<int>(settle_delay_s * 1000)));
        tcp->clear_buffers();

        std::string sig = probe_signature(query_command, 2.0);
        if (sig.empty()) {
            tcp->close();
            throw std::runtime_error("No Speeduino response from "
                + tcp->host() + ":" + std::to_string(tcp->port()));
        }
        info_.signature = sig;
        info_.framed = true;
        connected_ = true;
        status("Connected: " + sig + " via TCP");
        return info_;
    }

    // Generic transport — just open and probe.
    transport_->open();
    std::string sig = probe_signature(query_command, 2.0);
    if (sig.empty()) {
        transport_->close();
        throw std::runtime_error("No Speeduino ECU found");
    }
    info_.signature = sig;
    connected_ = true;
    return info_;
}

void SpeeduinoController::disconnect() {
    if (transport_->is_open()) transport_->close();
    connected_ = false;
}

// ---------------------------------------------------------------
// Signature probe
// ---------------------------------------------------------------

std::string SpeeduinoController::probe_signature(char cmd, double timeout_s) {
    // Send single-byte command and read response.
    std::vector<std::uint8_t> payload = {static_cast<std::uint8_t>(cmd)};
    try {
        send_command(payload);
        auto resp = recv_response(128, timeout_s);
        if (resp.empty()) return {};
        // Skip echo of the sent command (serial path may echo).
        std::size_t start = 0;
        if (resp.size() > 1 && resp[0] == static_cast<std::uint8_t>(cmd))
            start = 1;
        // Find the null terminator or use the whole response.
        std::size_t end = start;
        while (end < resp.size() && resp[end] != 0) ++end;
        if (end <= start) return {};
        return std::string(resp.begin() + start, resp.begin() + end);
    } catch (...) {
        return {};
    }
}

std::string SpeeduinoController::read_signature(char cmd, double timeout_s) {
    return probe_signature(cmd, timeout_s);
}

// ---------------------------------------------------------------
// Page read/write
// ---------------------------------------------------------------

std::vector<std::uint8_t> SpeeduinoController::read_page(
    std::uint8_t page, std::uint16_t offset, std::uint16_t length, char cmd) {
    auto payload = speeduino_protocol::page_request(cmd, page, offset, length);
    send_command(payload);
    return recv_response(length, 2.0);
}

void SpeeduinoController::write_parameter(
    std::uint8_t page, std::uint16_t offset,
    const std::uint8_t* data, std::size_t size, char cmd) {
    auto payload = speeduino_protocol::page_write_request(
        page, offset, std::span<const std::uint8_t>(data, size), cmd);
    send_command(payload);
    // Some firmwares send a single-byte ack.
    try { recv_response(1, 0.5); } catch (...) {}
}

void SpeeduinoController::burn(std::uint8_t page, char cmd) {
    auto payload = speeduino_protocol::burn_request(page, cmd);
    send_command(payload);
    // Burn is slow — wait up to 5 seconds for ack.
    try { recv_response(1, 5.0); } catch (...) {}
}

std::uint32_t SpeeduinoController::fetch_page_crc(std::uint8_t page, char cmd) {
    auto payload = speeduino_protocol::page_crc_request(page, cmd);
    send_command(payload);
    auto resp = recv_response(4, 2.0);
    return speeduino_protocol::parse_page_crc_response(resp);
}

SpeeduinoController::PageVerifyResult SpeeduinoController::verify_page(
    std::uint8_t page, std::span<const std::uint8_t> local_bytes, char cmd) {
    PageVerifyResult r;
    r.expected = speeduino_framing::crc32(local_bytes);
    r.actual = fetch_page_crc(page, cmd);
    r.matched = (r.expected == r.actual);
    return r;
}

void SpeeduinoController::write_calibration_table(
    std::uint8_t page, const std::uint8_t* data, std::size_t size, char cmd) {
    // Framed 't' command shape (comms.cpp line 933):
    //   [cmd][0x00][page][offset_hi][offset_lo][len_hi][len_lo][data...]
    // Offset is always 0 for a single-chunk write; callers that need to
    // upload a multi-chunk O2 table (page 2, 1024 bytes) would invoke
    // this once per chunk with the running offset.
    std::vector<std::uint8_t> payload;
    payload.reserve(7 + size);
    payload.push_back(static_cast<std::uint8_t>(cmd));
    payload.push_back(0x00);
    payload.push_back(page);
    payload.push_back(0x00);  // offset hi
    payload.push_back(0x00);  // offset lo
    payload.push_back(static_cast<std::uint8_t>((size >> 8) & 0xFF));
    payload.push_back(static_cast<std::uint8_t>(size & 0xFF));
    payload.insert(payload.end(), data, data + size);
    send_command(payload);
    // Firmware may or may not send an ack; wait briefly but don't fail
    // if nothing arrives (legacy path is silent).
    try { recv_response(1, 1.0); } catch (...) {}
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
}

std::vector<std::uint8_t> SpeeduinoController::read_runtime(
    std::uint16_t offset, std::uint16_t length) {
    auto payload = speeduino_protocol::runtime_request(offset, length);
    send_command(payload);
    return recv_response(length, 1.0);
}

std::vector<std::uint8_t> SpeeduinoController::fetch_raw(
    const std::vector<std::uint8_t>& command,
    std::size_t response_length,
    double timeout_s) {
    send_command(command);
    return recv_response(response_length, timeout_s);
}

// ---------------------------------------------------------------
// Transport-aware send/receive
// ---------------------------------------------------------------

void SpeeduinoController::send_command(const std::vector<std::uint8_t>& payload) {
    if (framed_) {
        auto* tcp = dynamic_cast<transport::TcpTransport*>(transport_.get());
        if (tcp) { tcp->write_framed(payload); return; }
    }
    transport_->write(payload);
}

std::vector<std::uint8_t> SpeeduinoController::recv_response(
    std::size_t size, double timeout_s) {
    if (framed_) {
        auto* tcp = dynamic_cast<transport::TcpTransport*>(transport_.get());
        if (tcp) {
            auto frame = tcp->read_framed(timeout_s);
            if (frame.size() > size) frame.resize(size);
            return frame;
        }
    }
    // Raw serial: read up to `size` bytes.
    return transport_->read(size, timeout_s);
}

}  // namespace tuner_core::speeduino_controller
