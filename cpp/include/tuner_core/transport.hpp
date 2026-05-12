// SPDX-License-Identifier: MIT
//
// tuner_core::transport — abstract byte transport interface and
// concrete serial/TCP implementations. Port of the Python
// `tuner.transports` package.
//
// The interface is deliberately minimal: open, close, read, write,
// is_open. The serial implementation uses the Win32 API for COM
// port access; TCP uses winsock2 directly. Both are synchronous
// with configurable timeouts.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace tuner_core::transport {

// Abstract transport interface — matches the Python Transport protocol.
class Transport {
public:
    virtual ~Transport() = default;
    virtual void open() = 0;
    virtual void close() = 0;
    virtual std::vector<std::uint8_t> read(std::size_t size, double timeout_s = 0.1) = 0;
    virtual std::size_t write(const std::uint8_t* data, std::size_t size) = 0;
    virtual bool is_open() const = 0;
    virtual void clear_buffers() = 0;

    // Convenience: write a vector.
    std::size_t write(const std::vector<std::uint8_t>& data) {
        return write(data.data(), data.size());
    }
};

// Serial transport. Win32 COM port API on Windows; POSIX termios on
// Linux/macOS (Phase 20 slice 1).
class SerialTransport : public Transport {
public:
    SerialTransport(const std::string& port, int baud_rate);
    ~SerialTransport() override;

    void open() override;
    void close() override;
    std::vector<std::uint8_t> read(std::size_t size, double timeout_s = 0.1) override;
    std::size_t write(const std::uint8_t* data, std::size_t size) override;
    bool is_open() const override;
    void clear_buffers() override;

    // Change baud rate (closes and reopens if already open).
    void set_baud_rate(int baud);
    int baud_rate() const { return baud_rate_; }
    const std::string& port() const { return port_; }

private:
    std::string port_;
    int baud_rate_;
#ifdef _WIN32
    void* handle_ = nullptr;  // HANDLE, opaque to avoid windows.h in header
#else
    int   fd_     = -1;       // POSIX file descriptor (-1 = closed)
#endif
};

// TCP transport with optional Speeduino new-protocol framing.
class TcpTransport : public Transport {
public:
    TcpTransport(const std::string& host, int port, double connect_timeout_s = 5.0);
    ~TcpTransport() override;

    void open() override;
    void close() override;
    std::vector<std::uint8_t> read(std::size_t size, double timeout_s = 1.0) override;
    std::size_t write(const std::uint8_t* data, std::size_t size) override;
    bool is_open() const override;
    void clear_buffers() override;

    // Framed write/read for Airbear bridge (new protocol).
    // write_framed: sends [u16 LE len][payload][u32 LE CRC32].
    // read_framed: receives and validates framed response.
    void write_framed(const std::uint8_t* data, std::size_t size);
    void write_framed(const std::vector<std::uint8_t>& data) {
        write_framed(data.data(), data.size());
    }
    std::vector<std::uint8_t> read_framed(double timeout_s = 1.0);

    const std::string& host() const { return host_; }
    int port() const { return port_; }

private:
    std::string host_;
    int port_;
    double connect_timeout_;
    std::uintptr_t socket_ = ~std::uintptr_t(0);  // SOCKET, opaque
    bool open_ = false;

    // Read exactly N bytes or throw.
    std::vector<std::uint8_t> recv_exactly(std::size_t size, double timeout_s);
};

}  // namespace tuner_core::transport
