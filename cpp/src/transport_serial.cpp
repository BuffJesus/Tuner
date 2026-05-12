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
// POSIX serial (Linux/macOS) — Phase 20 slice 1.
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <time.h>
#include <cerrno>
#ifdef __APPLE__
// macOS-specific high-baud-rate ioctl. The standard Bxxx speed_t
// constants only go up to B230400 on macOS; rates above that go
// through IOSSIOSPEED with the raw integer value.
#include <IOKit/serial/ioss.h>
#endif
#endif

#include <algorithm>
#include <stdexcept>
#include <string>
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

    // ReadIntervalTimeout: max gap between consecutive bytes before
    // ReadFile returns. Short value (50ms) detects end-of-packet fast
    // without waiting for the full total timeout.
    // ReadTotalTimeoutConstant: overall deadline for the entire read.
    COMMTIMEOUTS timeouts;
    std::memset(&timeouts, 0, sizeof(timeouts));
    auto ms = static_cast<DWORD>(timeout_s * 1000);
    if (ms == 0) ms = 1;
    timeouts.ReadIntervalTimeout = 50;
    timeouts.ReadTotalTimeoutConstant = ms;
    timeouts.ReadTotalTimeoutMultiplier = 0;
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
    // WriteFile with synchronous I/O already blocks until the data is
    // in the driver buffer. FlushFileBuffers forces a physical drain of
    // the UART transmit shift register which adds 10-50ms per call on
    // Windows — removing it cuts page-read round-trip time dramatically.
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

#else  // POSIX (Linux/macOS) — Phase 20 slice 1

namespace {

// Translate an integer baud rate to a POSIX `speed_t`. POSIX defines
// only a discrete enumerated set; unsupported rates fall back to
// B115200, the Speeduino + Ardu-stim default.
//
// On Linux, B460800 / B921600 exist as macros. On macOS, those macros
// don't exist — `set_termios_speed` below handles macOS rates above
// B230400 via the IOSSIOSPEED ioctl after tcsetattr.
speed_t baud_to_speed(int baud) {
    switch (baud) {
        case 1200:    return B1200;
        case 2400:    return B2400;
        case 4800:    return B4800;
        case 9600:    return B9600;
        case 19200:   return B19200;
        case 38400:   return B38400;
        case 57600:   return B57600;
        case 115200:  return B115200;
        case 230400:  return B230400;
#ifdef B460800
        case 460800:  return B460800;
#endif
#ifdef B921600
        case 921600:  return B921600;
#endif
        default:      return B115200;
    }
}

// Returns true when the requested baud is above what `baud_to_speed`
// could express as a portable Bxxx constant — i.e. the caller needs
// the platform-specific IOSSIOSPEED ioctl (macOS) to actually clock
// the port at the requested rate.
bool baud_needs_macos_ioctl(int baud) {
#ifdef __APPLE__
    return baud > 230400 &&
           baud != 230400 &&
           baud_to_speed(baud) == B115200;  // i.e. fell into the default arm
#else
    (void)baud;
    return false;
#endif
}

double monotonic_now_s() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<double>(ts.tv_sec) + static_cast<double>(ts.tv_nsec) * 1e-9;
}

}  // namespace

void SerialTransport::open() {
    if (is_open()) close();

    // O_NOCTTY: prevent the port from becoming the controlling terminal
    // for the process. O_NONBLOCK on open() avoids hanging if the
    // device-driver open() path tries to wait for DCD on a port that
    // never asserts it; we clear it immediately afterwards because the
    // rest of the I/O path uses select()-driven timeouts on a blocking
    // fd (write in particular must block, not return EAGAIN).
    int fd = ::open(port_.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        throw std::runtime_error(
            "Cannot open serial port: " + port_
            + " (errno " + std::to_string(errno) + ": "
            + std::strerror(errno) + ")");
    }

    int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) {
        ::close(fd);
        throw std::runtime_error("fcntl(F_GETFL) failed on " + port_);
    }
    if (fcntl(fd, F_SETFL, flags & ~O_NONBLOCK) < 0) {
        ::close(fd);
        throw std::runtime_error("fcntl(F_SETFL) failed on " + port_
            + " — fd would remain non-blocking, write() would return EAGAIN");
    }

    struct termios tio{};
    if (tcgetattr(fd, &tio) != 0) {
        ::close(fd);
        throw std::runtime_error("tcgetattr failed on " + port_);
    }

    // Raw mode: no line discipline, no echo, no signals on control chars.
    // cfmakeraw is BSD/Linux/macOS — not strict POSIX, but available on
    // every platform we ship. The explicit 8N1 / flow-control / CREAD
    // overrides below are defensive belt-and-braces in case a future
    // platform's cfmakeraw doesn't normalise every field we depend on.
    cfmakeraw(&tio);

    speed_t speed = baud_to_speed(baud_rate_);
    cfsetispeed(&tio, speed);
    cfsetospeed(&tio, speed);

    // 8N1, no flow control.
    tio.c_cflag &= ~PARENB;   // no parity
    tio.c_cflag &= ~CSTOPB;   // 1 stop bit
    tio.c_cflag &= ~CSIZE;
    tio.c_cflag |=  CS8;      // 8 data bits
#ifdef CRTSCTS
    tio.c_cflag &= ~CRTSCTS;  // no hardware flow control
#endif
    tio.c_cflag |=  (CREAD | CLOCAL);  // enable receiver, ignore modem ctrl

    tio.c_iflag &= ~(IXON | IXOFF | IXANY);  // no SW flow control

    // VMIN=0, VTIME=0: non-blocking read; we drive timeout via select().
    tio.c_cc[VMIN]  = 0;
    tio.c_cc[VTIME] = 0;

    if (tcsetattr(fd, TCSANOW, &tio) != 0) {
        ::close(fd);
        throw std::runtime_error("tcsetattr failed on " + port_);
    }

#ifdef __APPLE__
    // macOS only supports Bxxx constants up to B230400. Anything higher
    // needs IOSSIOSPEED with the raw integer baud — applied AFTER
    // tcsetattr so the standard fields are in place first.
    if (baud_needs_macos_ioctl(baud_rate_)) {
        speed_t raw = static_cast<speed_t>(baud_rate_);
        if (ioctl(fd, IOSSIOSPEED, &raw) < 0) {
            ::close(fd);
            throw std::runtime_error(
                "IOSSIOSPEED failed for baud " + std::to_string(baud_rate_)
                + " on " + port_);
        }
    }
#endif

    // Advisory exclusive access — second process that tries to open the
    // same port gets EBUSY instead of corrupt interleaved reads. Solaris
    // lacks TIOCEXCL; gate accordingly.
#ifdef TIOCEXCL
    ioctl(fd, TIOCEXCL);  // best-effort, error is non-fatal
#endif

    // Drop DTR + RTS so the bench/ECU doesn't auto-reset on connect.
    // Matches the Win32 path which clears both modem lines.
    int modem = 0;
    if (ioctl(fd, TIOCMGET, &modem) == 0) {
        modem &= ~(TIOCM_DTR | TIOCM_RTS);
        ioctl(fd, TIOCMSET, &modem);
    }

    fd_ = fd;
}

void SerialTransport::close() {
    if (fd_ >= 0) {
        ::close(fd_);
        fd_ = -1;
    }
}

bool SerialTransport::is_open() const { return fd_ >= 0; }

void SerialTransport::clear_buffers() {
    if (fd_ < 0) return;
    tcflush(fd_, TCIOFLUSH);
}

std::vector<std::uint8_t> SerialTransport::read(std::size_t size, double timeout_s) {
    std::vector<std::uint8_t> out;
    if (fd_ < 0 || size == 0) return out;
    out.reserve(size);

    const double deadline = monotonic_now_s() + timeout_s;
    std::uint8_t buf[256];

    while (out.size() < size) {
        const double remaining = deadline - monotonic_now_s();
        if (remaining <= 0) break;

        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(fd_, &rfds);

        struct timeval tv;
        tv.tv_sec  = static_cast<time_t>(remaining);
        tv.tv_usec = static_cast<suseconds_t>(
            (remaining - static_cast<double>(tv.tv_sec)) * 1e6);

        int rc = ::select(fd_ + 1, &rfds, nullptr, nullptr, &tv);
        if (rc < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (rc == 0) break;  // timeout

        std::size_t want = std::min(sizeof(buf), size - out.size());
        ssize_t n = ::read(fd_, buf, want);
        if (n < 0) {
            if (errno == EINTR || errno == EAGAIN) continue;
            break;
        }
        if (n == 0) break;  // EOF (port closed by peer)
        out.insert(out.end(), buf, buf + static_cast<std::size_t>(n));
    }
    return out;
}

std::size_t SerialTransport::write(const std::uint8_t* data, std::size_t size) {
    if (fd_ < 0 || size == 0) return 0;
    std::size_t written = 0;
    while (written < size) {
        ssize_t n = ::write(fd_, data + written, size - written);
        if (n < 0) {
            if (errno == EINTR) continue;
            break;
        }
        if (n == 0) break;
        written += static_cast<std::size_t>(n);
    }
    return written;
}

void SerialTransport::set_baud_rate(int baud) {
    baud_rate_ = baud;
    if (is_open()) {
        close();
        open();
    }
}

#endif  // _WIN32 / POSIX

}  // namespace tuner_core::transport
