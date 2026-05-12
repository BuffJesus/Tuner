// SPDX-License-Identifier: MIT
//
// tuner_core::transport::TcpTransport — Winsock2 TCP implementation.
// Port of `tuner.transports.tcp_transport.TcpTransport`.
//
// Includes framed write/read for the Speeduino new-protocol over
// Airbear ESP32 bridge (port 2000).

#include "tuner_core/transport.hpp"
#include "tuner_core/speeduino_framing.hpp"

#include <chrono>
#include <thread>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")

namespace {
// RAII Winsock initializer — ensures WSAStartup/WSACleanup.
struct WsaInit {
    WsaInit() {
        WSADATA data;
        WSAStartup(MAKEWORD(2, 2), &data);
    }
    ~WsaInit() { WSACleanup(); }
};
static WsaInit wsa_init_;
}  // namespace

#else
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#endif

#include <stdexcept>
#include <cstring>
#include <algorithm>

namespace tuner_core::transport {

TcpTransport::TcpTransport(const std::string& host, int port, double connect_timeout_s)
    : host_(host), port_(port), connect_timeout_(connect_timeout_s) {}

TcpTransport::~TcpTransport() {
    if (is_open()) close();
}

#ifdef _WIN32

void TcpTransport::open() {
    if (is_open()) close();

    // Resolve host.
    struct addrinfo hints{}, *result = nullptr;
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    std::string port_str = std::to_string(port_);
    int rc = getaddrinfo(host_.c_str(), port_str.c_str(), &hints, &result);
    if (rc != 0 || result == nullptr) {
        throw std::runtime_error("Cannot resolve host: " + host_
            + " (error " + std::to_string(rc) + ")");
    }

    SOCKET s = socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (s == INVALID_SOCKET) {
        freeaddrinfo(result);
        throw std::runtime_error("Cannot create socket");
    }

    // Set connect timeout via non-blocking + select.
    u_long nonblock = 1;
    ioctlsocket(s, FIONBIO, &nonblock);
    ::connect(s, result->ai_addr, static_cast<int>(result->ai_addrlen));
    freeaddrinfo(result);

    fd_set writefds;
    FD_ZERO(&writefds);
    FD_SET(s, &writefds);
    timeval tv;
    tv.tv_sec = static_cast<long>(connect_timeout_);
    tv.tv_usec = static_cast<long>((connect_timeout_ - tv.tv_sec) * 1e6);
    int sel = select(0, nullptr, &writefds, nullptr, &tv);
    if (sel <= 0) {
        closesocket(s);
        throw std::runtime_error("TCP connect timeout to " + host_ + ":" + std::to_string(port_));
    }

    // Back to blocking mode.
    nonblock = 0;
    ioctlsocket(s, FIONBIO, &nonblock);

    // Set socket timeouts.
    DWORD recv_timeout = 1000;  // 1s
    DWORD send_timeout = 500;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&recv_timeout), sizeof(recv_timeout));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&send_timeout), sizeof(send_timeout));

    // Disable Nagle for low-latency command/response.
    int nodelay = 1;
    setsockopt(s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&nodelay), sizeof(nodelay));

    socket_ = static_cast<std::uintptr_t>(s);
    open_ = true;
}

void TcpTransport::close() {
    if (open_) {
        closesocket(static_cast<SOCKET>(socket_));
        socket_ = ~std::uintptr_t(0);
        open_ = false;
    }
}

std::vector<std::uint8_t> TcpTransport::read(std::size_t size, double timeout_s) {
    if (!is_open()) throw std::runtime_error("TCP socket not open");
    auto s = static_cast<SOCKET>(socket_);

    // Update recv timeout.
    DWORD ms = static_cast<DWORD>(timeout_s * 1000);
    if (ms == 0) ms = 1;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));

    std::vector<std::uint8_t> buf(size);
    int received = recv(s, reinterpret_cast<char*>(buf.data()), static_cast<int>(size), 0);
    if (received <= 0) {
        buf.clear();
        return buf;
    }
    buf.resize(static_cast<std::size_t>(received));
    return buf;
}

std::size_t TcpTransport::write(const std::uint8_t* data, std::size_t size) {
    if (!is_open()) throw std::runtime_error("TCP socket not open");
    auto s = static_cast<SOCKET>(socket_);
    int sent = send(s, reinterpret_cast<const char*>(data), static_cast<int>(size), 0);
    if (sent < 0) {
        throw std::runtime_error("TCP write failed (error " + std::to_string(WSAGetLastError()) + ")");
    }
    return static_cast<std::size_t>(sent);
}

bool TcpTransport::is_open() const {
    return open_;
}

void TcpTransport::clear_buffers() {
    if (!is_open()) return;
    auto s = static_cast<SOCKET>(socket_);
    // Drain any pending data.
    u_long nonblock = 1;
    ioctlsocket(s, FIONBIO, &nonblock);
    char drain[256];
    while (recv(s, drain, sizeof(drain), 0) > 0) {}
    nonblock = 0;
    ioctlsocket(s, FIONBIO, &nonblock);
}

std::vector<std::uint8_t> TcpTransport::recv_exactly(std::size_t size, double timeout_s) {
    auto s = static_cast<SOCKET>(socket_);
    DWORD ms = static_cast<DWORD>(timeout_s * 1000);
    if (ms == 0) ms = 1;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, reinterpret_cast<const char*>(&ms), sizeof(ms));

    std::vector<std::uint8_t> buf(size);
    std::size_t total = 0;
    while (total < size) {
        int n = recv(s, reinterpret_cast<char*>(buf.data() + total),
                     static_cast<int>(size - total), 0);
        if (n <= 0) {
            throw std::runtime_error("TCP recv_exactly: connection lost or timeout");
        }
        total += static_cast<std::size_t>(n);
    }
    return buf;
}

// Framed write: [u16 LE len][payload][u32 LE CRC32].
void TcpTransport::write_framed(const std::uint8_t* data, std::size_t size) {
    auto frame = speeduino_framing::encode_frame(
        std::span<const std::uint8_t>(data, size));
    write(frame.data(), frame.size());
}

// Airbear error response codes — single-byte framed payloads.
// RC_BUSY_ERR (0x85): the Airbear dashboard holds the UART mutex.
//   → short backoff + retry (up to 3 attempts, 20ms between).
// RC_TIMEOUT (0x80): the ECU didn't respond within Airbear's timeout.
//   → surface as a descriptive error, no silent retry.
static constexpr std::uint8_t RC_TIMEOUT   = 0x80;
static constexpr std::uint8_t RC_BUSY_ERR  = 0x85;
static constexpr int           kMaxBusyRetries = 3;
static constexpr int           kBusyBackoffMs  = 20;

// Framed read: decode [u16 LE len][payload][u32 LE CRC32].
// Recognises Airbear error codes in single-byte responses and
// handles RC_BUSY_ERR with automatic backoff+retry.
std::vector<std::uint8_t> TcpTransport::read_framed(double timeout_s) {
    for (int attempt = 0; attempt <= kMaxBusyRetries; ++attempt) {
        // Read 2-byte length header.
        auto hdr = recv_exactly(2, timeout_s);
        std::uint16_t payload_len = static_cast<std::uint16_t>(hdr[0])
                                  | (static_cast<std::uint16_t>(hdr[1]) << 8);
        // Read payload + 4-byte CRC.
        auto body = recv_exactly(payload_len + 4, timeout_s);
        // Validate CRC.
        std::uint32_t expected_crc = speeduino_framing::crc32(
            std::span<const std::uint8_t>(body.data(), payload_len));
        std::uint32_t actual_crc =
            static_cast<std::uint32_t>(body[payload_len])
          | (static_cast<std::uint32_t>(body[payload_len + 1]) << 8)
          | (static_cast<std::uint32_t>(body[payload_len + 2]) << 16)
          | (static_cast<std::uint32_t>(body[payload_len + 3]) << 24);
        if (expected_crc != actual_crc) {
            throw std::runtime_error("TCP framed read: CRC mismatch");
        }

        // Check for Airbear error codes in single-byte responses.
        if (payload_len == 1) {
            std::uint8_t code = body[0];
            if (code == RC_BUSY_ERR) {
                if (attempt < kMaxBusyRetries) {
                    // Dashboard holds UART mutex — backoff and retry.
                    std::this_thread::sleep_for(
                        std::chrono::milliseconds(kBusyBackoffMs));
                    continue;
                }
                throw std::runtime_error(
                    "Airbear RC_BUSY_ERR: dashboard holds UART mutex "
                    "(retries exhausted)");
            }
            if (code == RC_TIMEOUT) {
                throw std::runtime_error(
                    "Airbear RC_TIMEOUT: ECU not responding");
            }
        }

        body.resize(payload_len);
        return body;
    }
    // Should not reach here, but satisfy compiler.
    throw std::runtime_error("TCP framed read: unexpected retry exhaustion");
}

#else  // POSIX TCP — Phase 20 slice 3

#include <netinet/tcp.h>  // TCP_NODELAY
#include <cerrno>
#include <sys/time.h>

namespace {

// Translate a fractional-seconds timeout into a `struct timeval` for
// SO_RCVTIMEO / SO_SNDTIMEO. The kernel rounds usec to its tick rate.
struct timeval seconds_to_tv(double seconds) {
    struct timeval tv;
    if (seconds <= 0) {
        tv.tv_sec = 0;
        tv.tv_usec = 1000;  // 1ms floor — matches Win32 "ms == 0 ⇒ 1"
        return tv;
    }
    tv.tv_sec  = static_cast<time_t>(seconds);
    tv.tv_usec = static_cast<suseconds_t>(
        (seconds - static_cast<double>(tv.tv_sec)) * 1e6);
    return tv;
}

}  // namespace

void TcpTransport::open() {
    if (is_open()) close();

    // Resolve host (IPv4-only to mirror the Win32 path).
    struct addrinfo hints{}, *result = nullptr;
    hints.ai_family   = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    std::string port_str = std::to_string(port_);
    int rc = ::getaddrinfo(host_.c_str(), port_str.c_str(), &hints, &result);
    if (rc != 0 || result == nullptr) {
        throw std::runtime_error("Cannot resolve host: " + host_
            + " (gai error " + std::to_string(rc) + ": "
            + std::string(gai_strerror(rc)) + ")");
    }

    int s = ::socket(result->ai_family, result->ai_socktype, result->ai_protocol);
    if (s < 0) {
        ::freeaddrinfo(result);
        throw std::runtime_error("Cannot create socket (errno "
            + std::to_string(errno) + ": " + std::strerror(errno) + ")");
    }

    // Non-blocking connect with select() for the configured timeout —
    // same shape as the Win32 path.
    int flags = ::fcntl(s, F_GETFL, 0);
    if (flags < 0 || ::fcntl(s, F_SETFL, flags | O_NONBLOCK) < 0) {
        ::close(s);
        ::freeaddrinfo(result);
        throw std::runtime_error("fcntl(O_NONBLOCK) failed on socket");
    }

    int connect_rc = ::connect(s, result->ai_addr, result->ai_addrlen);
    ::freeaddrinfo(result);
    if (connect_rc < 0 && errno != EINPROGRESS) {
        ::close(s);
        throw std::runtime_error("TCP connect failed: errno "
            + std::to_string(errno) + " (" + std::strerror(errno) + ")");
    }

    fd_set writefds;
    FD_ZERO(&writefds);
    FD_SET(s, &writefds);
    struct timeval tv = seconds_to_tv(connect_timeout_);
    int sel = ::select(s + 1, nullptr, &writefds, nullptr, &tv);
    if (sel <= 0) {
        ::close(s);
        throw std::runtime_error("TCP connect timeout to " + host_
            + ":" + std::to_string(port_));
    }

    // Check SO_ERROR for the actual connect result — select() reports
    // writable even on connect failure (e.g. ECONNREFUSED).
    int sockerr = 0;
    socklen_t soerr_len = sizeof(sockerr);
    if (::getsockopt(s, SOL_SOCKET, SO_ERROR, &sockerr, &soerr_len) < 0
        || sockerr != 0) {
        ::close(s);
        throw std::runtime_error("TCP connect to " + host_ + ":"
            + std::to_string(port_)
            + " failed: errno " + std::to_string(sockerr)
            + " (" + std::strerror(sockerr) + ")");
    }

    // Back to blocking mode for the rest of the I/O path.
    // Explicit ~O_NONBLOCK in case the kernel ever defaults to
    // non-blocking on open (defensive — current Linux/macOS don't).
    ::fcntl(s, F_SETFL, flags & ~O_NONBLOCK);

#ifdef __APPLE__
    // macOS lacks MSG_NOSIGNAL on send(). Without SO_NOSIGPIPE, a
    // write() to a closed-peer connection raises SIGPIPE → process
    // exits with signal 13. Set the socket-level flag once at open
    // so every future send() is protected.
    {
        int nosigpipe = 1;
        ::setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &nosigpipe, sizeof(nosigpipe));
    }
#endif

    // SO_RCVTIMEO / SO_SNDTIMEO — same default cadence as Win32.
    struct timeval recv_tv = seconds_to_tv(1.0);
    struct timeval send_tv = seconds_to_tv(0.5);
    ::setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &recv_tv, sizeof(recv_tv));
    ::setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &send_tv, sizeof(send_tv));

    // Disable Nagle for low-latency command/response.
    int nodelay = 1;
    ::setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &nodelay, sizeof(nodelay));

    socket_ = static_cast<std::uintptr_t>(s);
    open_   = true;
}

void TcpTransport::close() {
    if (open_) {
        ::close(static_cast<int>(socket_));
        socket_ = ~std::uintptr_t(0);
        open_ = false;
    }
}

bool TcpTransport::is_open() const { return open_; }

std::vector<std::uint8_t> TcpTransport::read(std::size_t size, double timeout_s) {
    if (!is_open()) throw std::runtime_error("TCP socket not open");
    int s = static_cast<int>(socket_);

    struct timeval tv = seconds_to_tv(timeout_s);
    ::setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    std::vector<std::uint8_t> buf(size);
    ssize_t received = ::recv(s, buf.data(), size, 0);
    if (received <= 0) {
        buf.clear();
        return buf;
    }
    buf.resize(static_cast<std::size_t>(received));
    return buf;
}

std::size_t TcpTransport::write(const std::uint8_t* data, std::size_t size) {
    if (!is_open()) throw std::runtime_error("TCP socket not open");
    int s = static_cast<int>(socket_);
    // MSG_NOSIGNAL: prevent SIGPIPE on a closed-peer connection; we'd
    // rather get EPIPE and throw than crash the process. macOS doesn't
    // define MSG_NOSIGNAL — set SO_NOSIGPIPE on the socket instead
    // (done at open() on macOS via #ifdef below would be cleaner, but
    // most callers wrap in a connection-state check anyway).
#ifdef MSG_NOSIGNAL
    ssize_t sent = ::send(s, data, size, MSG_NOSIGNAL);
#else
    ssize_t sent = ::send(s, data, size, 0);
#endif
    if (sent < 0) {
        throw std::runtime_error("TCP write failed (errno "
            + std::to_string(errno) + ": " + std::strerror(errno) + ")");
    }
    return static_cast<std::size_t>(sent);
}

void TcpTransport::clear_buffers() {
    if (!is_open()) return;
    int s = static_cast<int>(socket_);
    // Drain any buffered data — set nonblock, recv until EAGAIN, restore.
    int flags = ::fcntl(s, F_GETFL, 0);
    if (flags < 0) return;
    ::fcntl(s, F_SETFL, flags | O_NONBLOCK);
    char drain[256];
    while (::recv(s, drain, sizeof(drain), 0) > 0) {}
    ::fcntl(s, F_SETFL, flags);
}

std::vector<std::uint8_t> TcpTransport::recv_exactly(std::size_t size, double timeout_s) {
    int s = static_cast<int>(socket_);
    struct timeval tv = seconds_to_tv(timeout_s);
    ::setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    std::vector<std::uint8_t> buf(size);
    std::size_t total = 0;
    while (total < size) {
        ssize_t n = ::recv(s, buf.data() + total, size - total, 0);
        if (n < 0) {
            if (errno == EINTR) continue;  // signal interrupted — retry
            // EAGAIN / EWOULDBLOCK from SO_RCVTIMEO fall through to throw.
            throw std::runtime_error(
                "TCP recv_exactly: connection lost or timeout (errno "
                + std::to_string(errno) + ": " + std::strerror(errno) + ")");
        }
        if (n == 0) {
            throw std::runtime_error(
                "TCP recv_exactly: peer closed connection mid-read");
        }
        total += static_cast<std::size_t>(n);
    }
    return buf;
}

// Framed write — identical body to the Win32 version (the framing
// codec is pure logic in tuner_core::speeduino_framing).
void TcpTransport::write_framed(const std::uint8_t* data, std::size_t size) {
    auto frame = speeduino_framing::encode_frame(
        std::span<const std::uint8_t>(data, size));
    write(frame.data(), frame.size());
}

// Framed read with Airbear error-code handling — same logic as the
// Win32 path, repeated here so the POSIX build doesn't need a
// shared helper TU (the speeduino_framing module is pure-logic
// and is what gets shared).
namespace {
constexpr std::uint8_t kRcTimeout      = 0x80;
constexpr std::uint8_t kRcBusyErr      = 0x85;
constexpr int          kMaxBusyRetries = 3;
constexpr int          kBusyBackoffMs  = 20;
}  // namespace

std::vector<std::uint8_t> TcpTransport::read_framed(double timeout_s) {
    for (int attempt = 0; attempt <= kMaxBusyRetries; ++attempt) {
        auto hdr = recv_exactly(2, timeout_s);
        std::uint16_t payload_len = static_cast<std::uint16_t>(hdr[0])
                                  | (static_cast<std::uint16_t>(hdr[1]) << 8);
        auto body = recv_exactly(payload_len + 4, timeout_s);
        std::uint32_t expected_crc = speeduino_framing::crc32(
            std::span<const std::uint8_t>(body.data(), payload_len));
        std::uint32_t actual_crc =
            static_cast<std::uint32_t>(body[payload_len])
          | (static_cast<std::uint32_t>(body[payload_len + 1]) << 8)
          | (static_cast<std::uint32_t>(body[payload_len + 2]) << 16)
          | (static_cast<std::uint32_t>(body[payload_len + 3]) << 24);
        if (expected_crc != actual_crc) {
            throw std::runtime_error("TCP framed read: CRC mismatch");
        }

        if (payload_len == 1) {
            std::uint8_t code = body[0];
            if (code == kRcBusyErr) {
                if (attempt < kMaxBusyRetries) {
                    std::this_thread::sleep_for(
                        std::chrono::milliseconds(kBusyBackoffMs));
                    continue;
                }
                throw std::runtime_error(
                    "Airbear RC_BUSY_ERR: dashboard holds UART mutex "
                    "(retries exhausted)");
            }
            if (code == kRcTimeout) {
                throw std::runtime_error(
                    "Airbear RC_TIMEOUT: ECU not responding");
            }
        }

        body.resize(payload_len);
        return body;
    }
    throw std::runtime_error("TCP framed read: unexpected retry exhaustion");
}

#endif  // _WIN32 / POSIX

}  // namespace tuner_core::transport
