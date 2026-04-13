// SPDX-License-Identifier: MIT
//
// tuner_core::transport::SerialTransport — Win32 COM port implementation.
// Port of `tuner.transports.serial_transport.SerialTransport`.
//
// Uses CreateFile/ReadFile/WriteFile for synchronous serial I/O with
// configurable timeouts. DTR and RTS are forced low on open (matches
// the Python `serial.Serial(dsrdtr=True, rtscts=False)` behavior).

#include "tuner_core/transport.hpp"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
// POSIX serial (Linux/macOS) — placeholder for future cross-platform.
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <cerrno>
#endif

#include <stdexcept>
#include <cstring>

namespace tuner_core::transport {

// ---------------------------------------------------------------
// SerialTransport
// ---------------------------------------------------------------

SerialTransport::SerialTransport(const std::string& port, int baud_rate)
    : port_(port), baud_rate_(baud_rate) {}

SerialTransport::~SerialTransport() {
    if (is_open()) close();
}

#ifdef _WIN32

void SerialTransport::open() {
    if (is_open()) close();

    // Win32 COM port path — must use \\.\COM3 form for ports > COM9.
    std::string path = port_;
    if (path.find("\\\\.\\") != 0 && path.find("COM") == 0)
        path = "\\\\.\\" + path;

    HANDLE h = CreateFileA(
        path.c_str(),
        GENERIC_READ | GENERIC_WRITE,
        0,             // no sharing
        nullptr,       // default security
        OPEN_EXISTING,
        0,             // synchronous I/O
        nullptr);
    if (h == INVALID_HANDLE_VALUE) {
        throw std::runtime_error("Cannot open serial port: " + port_
            + " (error " + std::to_string(GetLastError()) + ")");
    }
    handle_ = static_cast<void*>(h);

    // Configure baud rate, 8N1.
    DCB dcb;
    std::memset(&dcb, 0, sizeof(dcb));
    dcb.DCBlength = sizeof(dcb);
    if (!GetCommState(h, &dcb)) {
        CloseHandle(h); handle_ = nullptr;
        throw std::runtime_error("GetCommState failed for " + port_);
    }
    dcb.BaudRate = static_cast<DWORD>(baud_rate_);
    dcb.ByteSize = 8;
    dcb.Parity = NOPARITY;
    dcb.StopBits = ONESTOPBIT;
    dcb.fDtrControl = DTR_CONTROL_DISABLE;  // DTR low
    dcb.fRtsControl = RTS_CONTROL_DISABLE;  // RTS low
    dcb.fOutxCtsFlow = FALSE;
    dcb.fOutxDsrFlow = FALSE;
    dcb.fBinary = TRUE;
    if (!SetCommState(h, &dcb)) {
        CloseHandle(h); handle_ = nullptr;
        throw std::runtime_error("SetCommState failed for " + port_);
    }

    // Timeouts: 100ms read timeout, 500ms write timeout.
    COMMTIMEOUTS timeouts;
    std::memset(&timeouts, 0, sizeof(timeouts));
    timeouts.ReadIntervalTimeout = 100;
    timeouts.ReadTotalTimeoutMultiplier = 0;
    timeouts.ReadTotalTimeoutConstant = 100;
    timeouts.WriteTotalTimeoutMultiplier = 0;
    timeouts.WriteTotalTimeoutConstant = 500;
    SetCommTimeouts(h, &timeouts);

    // Clear buffers.
    PurgeComm(h, PURGE_RXCLEAR | PURGE_TXCLEAR);
}

void SerialTransport::close() {
    if (handle_ != nullptr) {
        CloseHandle(static_cast<HANDLE>(handle_));
        handle_ = nullptr;
    }
}

std::vector<std::uint8_t> SerialTransport::read(std::size_t size, double timeout_s) {
    if (!is_open()) throw std::runtime_error("Serial port not open");
    auto h = static_cast<HANDLE>(handle_);

    // Update read timeout to match requested value.
    COMMTIMEOUTS timeouts;
    std::memset(&timeouts, 0, sizeof(timeouts));
    auto ms = static_cast<DWORD>(timeout_s * 1000);
    if (ms == 0) ms = 1;
    timeouts.ReadIntervalTimeout = ms;
    timeouts.ReadTotalTimeoutConstant = ms;
    timeouts.WriteTotalTimeoutConstant = 500;
    SetCommTimeouts(h, &timeouts);

    std::vector<std::uint8_t> buf(size);
    DWORD bytes_read = 0;
    ReadFile(h, buf.data(), static_cast<DWORD>(size), &bytes_read, nullptr);
    buf.resize(bytes_read);
    return buf;
}

std::size_t SerialTransport::write(const std::uint8_t* data, std::size_t size) {
    if (!is_open()) throw std::runtime_error("Serial port not open");
    auto h = static_cast<HANDLE>(handle_);
    DWORD bytes_written = 0;
    if (!WriteFile(h, data, static_cast<DWORD>(size), &bytes_written, nullptr)) {
        throw std::runtime_error("Serial write failed (error "
            + std::to_string(GetLastError()) + ")");
    }
    FlushFileBuffers(h);
    return bytes_written;
}

bool SerialTransport::is_open() const {
    return handle_ != nullptr;
}

void SerialTransport::clear_buffers() {
    if (!is_open()) return;
    PurgeComm(static_cast<HANDLE>(handle_), PURGE_RXCLEAR | PURGE_TXCLEAR);
}

void SerialTransport::set_baud_rate(int baud) {
    baud_rate_ = baud;
    if (is_open()) {
        close();
        open();
    }
}

#else
// POSIX stub — not yet implemented.
void SerialTransport::open() { throw std::runtime_error("Serial not implemented on this platform"); }
void SerialTransport::close() {}
std::vector<std::uint8_t> SerialTransport::read(std::size_t, double) { return {}; }
std::size_t SerialTransport::write(const std::uint8_t*, std::size_t) { return 0; }
bool SerialTransport::is_open() const { return false; }
void SerialTransport::clear_buffers() {}
void SerialTransport::set_baud_rate(int) {}
#endif

}  // namespace tuner_core::transport
