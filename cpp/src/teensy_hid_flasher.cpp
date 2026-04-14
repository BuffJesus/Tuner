// SPDX-License-Identifier: MIT
#include "tuner_core/teensy_hid_flasher.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <setupapi.h>
#include <cfgmgr32.h>
extern "C" {
// Inline HidD prototypes rather than pulling <hidsdi.h> + hid.lib
// because MinGW ships hidsdi.h in the DDK/WDK kit which isn't always
// present. The two symbols we need are documented stable ABI.
typedef struct _HIDD_ATTRIBUTES {
    ULONG Size;
    USHORT VendorID;
    USHORT ProductID;
    USHORT VersionNumber;
} HIDD_ATTRIBUTES, *PHIDD_ATTRIBUTES;

typedef struct _SP_DEVICE_INTERFACE_DETAIL_DATA_W_PACKED {
    DWORD cbSize;
    WCHAR DevicePath[1];
} SP_DEVICE_INTERFACE_DETAIL_DATA_W_PACKED;

__declspec(dllimport) void __stdcall HidD_GetHidGuid(GUID*);
__declspec(dllimport) BOOLEAN __stdcall HidD_GetAttributes(HANDLE, PHIDD_ATTRIBUTES);
}
#endif

namespace tuner_core::teensy_hid_flasher {

bool supported() noexcept {
#ifdef _WIN32
    return true;
#else
    return false;
#endif
}

#ifdef _WIN32

namespace {

constexpr USHORT kTeensyVid = 0x16C0;
constexpr USHORT kTeensyBootloaderPid = 0x0478;

void sleep_ms(int ms) {
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}

void report(const ProgressCallback& cb, const std::string& msg, int percent = -1) {
    if (cb) cb(FlashProgress{msg, percent});
}

HANDLE open_teensy_hid_device() {
    GUID hid_guid;
    HidD_GetHidGuid(&hid_guid);

    HDEVINFO dev_info = SetupDiGetClassDevsW(
        &hid_guid, nullptr, nullptr,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (dev_info == INVALID_HANDLE_VALUE) return INVALID_HANDLE_VALUE;

    HANDLE result = INVALID_HANDLE_VALUE;
    SP_DEVICE_INTERFACE_DATA iface{};
    iface.cbSize = sizeof(iface);

    for (DWORD index = 0;
         SetupDiEnumDeviceInterfaces(dev_info, nullptr, &hid_guid, index, &iface);
         ++index) {

        DWORD required = 0;
        SetupDiGetDeviceInterfaceDetailW(
            dev_info, &iface, nullptr, 0, &required, nullptr);
        if (required == 0) continue;

        std::vector<std::uint8_t> buf(required, 0);
        auto* detail = reinterpret_cast<PSP_DEVICE_INTERFACE_DETAIL_DATA_W>(buf.data());
        detail->cbSize = sizeof(SP_DEVICE_INTERFACE_DETAIL_DATA_W);

        if (!SetupDiGetDeviceInterfaceDetailW(
                dev_info, &iface, detail, required, nullptr, nullptr)) {
            continue;
        }

        HANDLE handle = CreateFileW(
            detail->DevicePath,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            nullptr,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            nullptr);
        if (handle == INVALID_HANDLE_VALUE) continue;

        HIDD_ATTRIBUTES attrs{};
        attrs.Size = sizeof(attrs);
        if (HidD_GetAttributes(handle, &attrs) &&
            attrs.VendorID == kTeensyVid &&
            attrs.ProductID == kTeensyBootloaderPid) {
            result = handle;
            break;
        }
        CloseHandle(handle);
    }

    SetupDiDestroyDeviceInfoList(dev_info);
    return result;
}

struct WriteResult {
    bool ok = false;
    std::string detail;
};

WriteResult write_usb_once(HANDLE handle,
                           const std::uint8_t* payload,
                           std::size_t payload_len,
                           double timeout_seconds) {
    std::vector<std::uint8_t> buf(payload_len + 1, 0);
    std::memcpy(buf.data() + 1, payload, payload_len);

    HANDLE event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    if (!event) {
        return WriteResult{false, "CreateEventW failed"};
    }

    OVERLAPPED overlapped{};
    overlapped.hEvent = event;
    DWORD bytes_written = 0;

    BOOL write_ok = WriteFile(
        handle, buf.data(), static_cast<DWORD>(buf.size()),
        nullptr, &overlapped);

    if (!write_ok) {
        DWORD err = GetLastError();
        if (err != ERROR_IO_PENDING) {
            CloseHandle(event);
            return WriteResult{false, "WriteFile failed with error " + std::to_string(err)};
        }
        DWORD wait_ms = static_cast<DWORD>(timeout_seconds * 1000.0);
        if (wait_ms < 1) wait_ms = 1;
        DWORD wait = WaitForSingleObject(event, wait_ms);
        if (wait == WAIT_TIMEOUT) {
            CancelIo(handle);
            CloseHandle(event);
            return WriteResult{false, "WaitForSingleObject timed out"};
        }
        if (wait != WAIT_OBJECT_0) {
            CloseHandle(event);
            return WriteResult{false, "WaitForSingleObject returned " + std::to_string(wait)};
        }
    }

    BOOL ok = GetOverlappedResult(handle, &overlapped, &bytes_written, FALSE);
    CloseHandle(event);
    if (!ok) {
        return WriteResult{false, "GetOverlappedResult failed with error " +
                                   std::to_string(GetLastError())};
    }
    if (bytes_written == 0) {
        return WriteResult{false, "zero bytes written"};
    }
    return WriteResult{true, ""};
}

WriteResult write_usb(HANDLE handle,
                      const std::vector<std::uint8_t>& payload,
                      double timeout_seconds) {
    auto deadline = std::chrono::steady_clock::now() +
                    std::chrono::milliseconds(static_cast<int>(timeout_seconds * 1000));
    WriteResult last{false, "unknown USB write error"};
    while (std::chrono::steady_clock::now() < deadline) {
        auto now = std::chrono::steady_clock::now();
        double remaining = std::chrono::duration<double>(deadline - now).count();
        if (remaining < 0.01) remaining = 0.01;
        auto attempt = write_usb_once(handle, payload.data(), payload.size(), remaining);
        if (attempt.ok) return attempt;
        last = attempt;
        sleep_ms(10);
    }
    return last;
}

}  // namespace

bool request_reboot(std::string_view serial_port) noexcept {
    if (serial_port.empty()) return false;
    // Win32 CreateFile on "COMn" needs `\\.\COMn` for COM10+.
    std::wstring path = L"\\\\.\\";
    for (char c : serial_port) path.push_back(static_cast<wchar_t>(c));

    HANDLE com = CreateFileW(path.c_str(),
                             GENERIC_READ | GENERIC_WRITE,
                             0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (com == INVALID_HANDLE_VALUE) return false;

    DCB dcb{};
    dcb.DCBlength = sizeof(dcb);
    if (GetCommState(com, &dcb)) {
        dcb.BaudRate = 134;
        dcb.ByteSize = 8;
        dcb.Parity = NOPARITY;
        dcb.StopBits = ONESTOPBIT;
        SetCommState(com, &dcb);
    }
    sleep_ms(50);
    CloseHandle(com);
    sleep_ms(250);
    return true;
}

FlashResult flash(std::string_view hex_text,
                  const teensy_hex_image::McuSpec& spec,
                  std::string_view serial_port,
                  const ProgressCallback& progress) {
    try {
        report(progress, "Parsing firmware...", 0);
        auto image = teensy_hex_image::read_hex(hex_text, spec);
        auto block_addrs = teensy_hex_image::block_addresses(image, spec);
        if (block_addrs.empty()) block_addrs.push_back(0);

        bool reboot_asked = false;
        bool reboot_ok = false;
        if (!serial_port.empty()) {
            reboot_asked = true;
            report(progress, std::string("Requesting Teensy reboot on ") +
                             std::string(serial_port), 0);
            reboot_ok = request_reboot(serial_port);
        }

        if (reboot_ok) {
            report(progress, "Waiting for Teensy bootloader after auto reboot.", 0);
        } else if (reboot_asked) {
            report(progress,
                   "Waiting for Teensy bootloader. Press the reset button if auto reboot does not trigger.",
                   0);
        } else {
            report(progress, "Waiting for Teensy bootloader. Press the reset button.", 0);
        }

        HANDLE handle = INVALID_HANDLE_VALUE;
        auto wait_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(60);
        while (std::chrono::steady_clock::now() < wait_deadline) {
            handle = open_teensy_hid_device();
            if (handle != INVALID_HANDLE_VALUE) break;
            sleep_ms(250);
        }
        if (handle == INVALID_HANDLE_VALUE) {
            return FlashResult{false,
                "Teensy bootloader not found within 60s. Press the reset button on the Teensy."};
        }

        report(progress, "Found HalfKay Bootloader", 0);

        int total = static_cast<int>(block_addrs.size());
        for (int i = 0; i < total; ++i) {
            int addr = block_addrs[i];
            auto payload = teensy_hex_image::build_write_payload(image, spec, addr);
            double timeout = (i < 5) ? 45.0 : 0.5;
            auto result = write_usb(handle, payload, timeout);
            if (!result.ok) {
                CloseHandle(handle);
                char buf[256];
                std::snprintf(buf, sizeof(buf),
                    "Failed to write firmware block %d/%d at 0x%06X: %s",
                    i + 1, total, addr, result.detail.c_str());
                return FlashResult{false, buf};
            }
            int percent = std::min(99, std::max(1, (i + 1) * 100 / total));
            report(progress, "Flashing Teensy firmware", percent);
        }

        auto boot_payload = teensy_hex_image::build_boot_payload(spec);
        auto boot_result = write_usb(handle, boot_payload, 0.5);
        CloseHandle(handle);
        if (!boot_result.ok) {
            return FlashResult{false,
                "Failed to reboot Teensy after programming: " + boot_result.detail};
        }

        report(progress, "Flash completed", 100);
        return FlashResult{true, ""};
    } catch (const std::exception& e) {
        return FlashResult{false, e.what()};
    }
}

#else  // non-Windows

bool request_reboot(std::string_view) noexcept { return false; }

FlashResult flash(std::string_view,
                  const teensy_hex_image::McuSpec&,
                  std::string_view,
                  const ProgressCallback&) {
    return FlashResult{false,
        "Embedded Teensy flashing is only implemented for Windows."};
}

#endif

}  // namespace tuner_core::teensy_hid_flasher
