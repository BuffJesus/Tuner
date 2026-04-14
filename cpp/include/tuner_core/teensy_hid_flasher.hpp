// SPDX-License-Identifier: MIT
//
// tuner_core::teensy_hid_flasher — Win32 HID bootloader flasher for
// Teensy 3.5 / 3.6 / 4.1, port of the Python `_flash_internal_teensy`
// path. On non-Windows builds every entry point returns
// FlashResult{ok=false, detail="unsupported platform"} so callers can
// probe `supported()` before wiring a button.
//
// This is the "no external exe" flash path the legacy app used. The
// embedded AVRDUDE + DFU branches never existed; keep those as
// subprocess calls.

#pragma once

#include "tuner_core/teensy_hex_image.hpp"

#include <functional>
#include <string>
#include <string_view>

namespace tuner_core::teensy_hid_flasher {

struct FlashProgress {
    std::string message;
    int percent = -1;  // -1 -> message-only update
};

using ProgressCallback = std::function<void(const FlashProgress&)>;

struct FlashResult {
    bool ok = false;
    std::string detail;
};

// True on Windows; false everywhere else. Matches
// `firmware_flash_builder::supports_internal_teensy`.
bool supported() noexcept;

// Try to nudge the running Teensy into bootloader mode by opening
// `serial_port` (e.g. `"COM5"`) at 134 baud, which Teensy's HID
// firmware recognises as a reboot-into-bootloader request. Returns
// true on success, false if the port couldn't be opened (the caller
// should then prompt the operator to press the physical reset button).
// Empty port -> returns false without side-effects.
bool request_reboot(std::string_view serial_port) noexcept;

// Drive a full flash cycle synchronously — parse the HEX text,
// walk blocks, open the HID bootloader, write every block, boot the
// freshly programmed firmware. `serial_port` is optional; when set,
// a 134-baud reboot request is sent first. The progress callback (if
// non-null) is invoked with status strings and 0..100 percentages.
// Returns FlashResult{ok=true} on success or {ok=false, detail=...}
// on any error.
FlashResult flash(std::string_view hex_text,
                  const teensy_hex_image::McuSpec& spec,
                  std::string_view serial_port,
                  const ProgressCallback& progress);

}  // namespace tuner_core::teensy_hid_flasher
