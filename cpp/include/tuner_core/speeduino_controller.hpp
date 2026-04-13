// SPDX-License-Identifier: MIT
//
// tuner_core::speeduino_controller — high-level Speeduino ECU controller.
// Port of `tuner.comms.speeduino_controller_client.SpeeduinoControllerClient`.
//
// Owns a Transport (serial or TCP) and provides the typed command/response
// API the workspace uses: connect, read page, write parameter, burn,
// poll runtime, read signature. Handles auto-baud probing, framing
// detection (raw serial vs TCP framed), and settle delays.

#pragma once

#include "tuner_core/transport.hpp"
#include "tuner_core/speeduino_protocol.hpp"
#include "tuner_core/speeduino_framing.hpp"

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::speeduino_controller {

struct ConnectionInfo {
    std::string signature;
    std::string version;
    int blocking_factor = 128;
    int table_blocking_factor = 128;
    bool framed = false;  // true for TCP (Airbear) connections
};

// Status callback — called during connect to report progress.
using StatusCallback = std::function<void(const std::string& message)>;

class SpeeduinoController {
public:
    explicit SpeeduinoController(std::unique_ptr<transport::Transport> transport);
    ~SpeeduinoController();

    // Connect to the ECU: probe signature, negotiate capabilities.
    // Returns connection info on success, throws on failure.
    // The optional status callback is invoked with progress messages
    // ("Probing COM3 @ 115200...", "Signature: speeduino 202501-T41", etc.)
    ConnectionInfo connect(
        const std::vector<int>& baud_candidates = {115200, 230400, 57600, 9600},
        char query_command = 'Q',
        double settle_delay_s = 1.5,
        StatusCallback on_status = nullptr);

    // Disconnect — closes the transport.
    void disconnect();
    bool is_connected() const { return connected_; }

    // Read the firmware signature.
    std::string read_signature(char cmd = 'Q', double timeout_s = 1.5);

    // Read a page region from the ECU.
    std::vector<std::uint8_t> read_page(
        std::uint8_t page, std::uint16_t offset, std::uint16_t length,
        char cmd = 'r');

    // Write a parameter value to ECU RAM.
    void write_parameter(
        std::uint8_t page, std::uint16_t offset,
        const std::uint8_t* data, std::size_t size,
        char cmd = 'M');

    // Burn current RAM contents to flash.
    void burn(std::uint8_t page, char cmd = 'b');

    // Poll runtime data (output channels).
    std::vector<std::uint8_t> read_runtime(
        std::uint16_t offset, std::uint16_t length);

    // Send an arbitrary command and read the response. Used for logger
    // data fetch (tooth/composite capture) and other raw command paths
    // that don't fit the page read/write/burn API. Handles framing
    // transparently (raw serial vs TCP framed).
    std::vector<std::uint8_t> fetch_raw(
        const std::vector<std::uint8_t>& command,
        std::size_t response_length,
        double timeout_s = 2.0);

    // Access the underlying transport.
    transport::Transport& transport() { return *transport_; }
    const ConnectionInfo& connection_info() const { return info_; }

private:
    std::unique_ptr<transport::Transport> transport_;
    ConnectionInfo info_;
    bool connected_ = false;
    bool framed_ = false;  // TCP framing active

    // Send a command and read the response.
    void send_command(const std::vector<std::uint8_t>& payload);
    std::vector<std::uint8_t> recv_response(std::size_t size, double timeout_s = 1.0);

    // Probe signature at current baud/connection.
    std::string probe_signature(char cmd, double timeout_s);
};

}  // namespace tuner_core::speeduino_controller
