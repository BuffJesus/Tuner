// SPDX-License-Identifier: MIT
//
// tuner_core::bench_simulator::wheel_pattern_catalog — port of the
// 64-entry `WheelType` enum + per-entry friendly-name string table
// from `resources/Ardu-Stim-master/ardustim/ardustim/wheel_defs.h`.
//
// Phase 17 Slice A. Pure-logic catalog with no I/O. The protocol +
// controller layers (Slices B–D) read this catalog to populate the
// pattern picker, dispatch `S` (set wheel index) commands, and
// cross-validate that the firmware's `L` (list names) response
// matches what we expect.
//
// Each entry carries:
//   - the upstream enum identifier (e.g. "EIGHT_MINUS_ONE") — stable
//     across firmware versions, useful for headless wiring
//   - the operator-facing friendly name (e.g. "8-1 crank only (R6)")
//     pulled verbatim from `*_friendly_name PROGMEM` strings
//   - the **engine** cylinder count (0 = cylinder-agnostic generic
//     crank wheel); contrast with tooth count which is implicit in
//     the friendly name
//   - a `has_cam` flag for dual-signal patterns
//   - first-pass decoder compatibility tags for Speeduino and RusEFI
//
// Decoder tags are a starting heuristic — they reflect community
// knowledge of which patterns each firmware's decoder library
// supports. Refine via direct firmware decoder survey before
// shipping any operator-facing "this WILL work with your firmware"
// claim.

#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string_view>
#include <vector>

namespace tuner_core::bench_simulator {

// Upstream `WheelType` enum (wheel_defs.h:75-142). 64 patterns +
// MAX_WHEELS terminator. Indices match the firmware so `S` commands
// and `L`/`P` responses can index into this catalog directly.
enum class WheelPatternIndex : std::uint8_t {
    DIZZY_FOUR_CYLINDER = 0,
    DIZZY_SIX_CYLINDER,
    DIZZY_EIGHT_CYLINDER,
    SIXTY_MINUS_TWO,
    SIXTY_MINUS_TWO_WITH_CAM,
    SIXTY_MINUS_TWO_WITH_HALFMOON_CAM,
    THIRTY_SIX_MINUS_ONE,
    TWENTY_FOUR_MINUS_ONE,
    FOUR_MINUS_ONE_WITH_CAM,
    EIGHT_MINUS_ONE,
    SIX_MINUS_ONE_WITH_CAM,
    TWELVE_MINUS_ONE_WITH_CAM,
    FOURTY_MINUS_ONE,
    DIZZY_FOUR_TRIGGER_RETURN,
    ODDFIRE_VR,
    OPTISPARK_LT1,
    TWELVE_MINUS_THREE,
    THIRTY_SIX_MINUS_TWO_TWO_TWO,
    THIRTY_SIX_MINUS_TWO_TWO_TWO_H6,
    THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_CAM,
    FOURTY_TWO_HUNDRED_WHEEL,
    THIRTY_SIX_MINUS_ONE_WITH_CAM_FE3,
    SIX_G_SEVENTY_TWO_WITH_CAM,
    BUELL_ODDFIRE_CAM,
    GM_LS1_CRANK_AND_CAM,
    GM_58X_LS_CRANK_4X_CAM,
    LOTUS_THIRTY_SIX_MINUS_ONE_ONE_ONE_ONE,
    HONDA_RC51_WITH_CAM,
    THIRTY_SIX_MINUS_ONE_WITH_SECOND_TRIGGER,
    CHRYSLER_NGC_THIRTY_SIX_PLUS_TWO_MINUS_TWO_WITH_NGC4_CAM,
    CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC6_CAM,
    CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC8_CAM,
    WEBER_IAW_WITH_CAM,
    FIAT_ONE_POINT_EIGHT_SIXTEEN_VALVE_WITH_CAM,
    THREE_SIXTY_NISSAN_CAS,
    TWENTY_FOUR_MINUS_TWO_WITH_SECOND_TRIGGER,
    YAMAHA_EIGHT_TOOTH_WITH_CAM,
    GM_FOUR_TOOTH_WITH_CAM,
    GM_SIX_TOOTH_WITH_CAM,
    GM_EIGHT_TOOTH_WITH_CAM,
    VOLVO_D12ACD_WITH_CAM,
    MAZDA_THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_SIX_TOOTH_CAM,
    MITSUBISHI_4G63_4_2,
    AUDI_135_WITH_CAM,
    HONDA_D17_NO_CAM,
    MAZDA_323_AU,
    DAIHATSU_3CYL,
    MIATA_9905,
    TWELVE_WITH_CAM,
    TWENTY_FOUR_WITH_CAM,
    SUBARU_SIX_SEVEN,
    GM_7X,
    FOUR_TWENTY_A,
    FORD_ST170,
    MITSUBISHI_3A92,
    TOYOTA_4AGE_CAS,
    TOYOTA_4AGZE,
    SUZUKI_DRZ400,
    JEEP2000_4CYL,
    JEEP2000_6CYL,
    BMW_N20,
    VIPER_96_02,
    THIRTY_SIX_MINUS_TWO_WITH_ONE_CAM,
    GM_40_OSS,
};

inline constexpr std::size_t kPatternCount = 64;

struct WheelPattern {
    WheelPatternIndex index;
    std::string_view  enum_name;        // upstream identifier, e.g. "EIGHT_MINUS_ONE"
    std::string_view  friendly_name;    // operator-facing label from firmware
    std::uint8_t      cylinder_count;   // 0 = cylinder-agnostic generic wheel
    bool              has_cam;          // dual-signal pattern (crank + cam)
    bool              decoder_speeduino;
    bool              decoder_rusefi;
};

// Returns the full 64-entry catalog in firmware enum order. The
// returned span is backed by a function-local static array — safe
// to hold across calls; no allocation per call.
std::span<const WheelPattern> patterns() noexcept;

inline std::size_t pattern_count() noexcept { return kPatternCount; }

// Bounded lookup. Throws std::out_of_range if `index >=
// kPatternCount`. Use `patterns()[i]` directly when you've already
// validated the bound.
const WheelPattern& pattern_at(std::size_t index);

// Find a pattern by its upstream enum identifier (case-sensitive,
// exact match). Returns the index, or nullopt when not found.
std::optional<std::size_t> find_by_enum_name(std::string_view enum_name) noexcept;

// Return all pattern indices that match the requested engine
// cylinder count, plus all cylinder-agnostic generic wheels
// (cylinder_count == 0). Order preserves firmware enum order.
//
// Operator UX intent: passing 8 returns "V8 patterns" plus the
// 36-1/60-2/24-1 generics that operators can wire to any engine.
std::vector<std::size_t> filter_by_cylinder_count(std::uint8_t cyl);

// Predicate helpers for decoder-tag filtering. Both walk the
// catalog in firmware enum order.
std::vector<std::size_t> filter_by_speeduino_decoder();
std::vector<std::size_t> filter_by_rusefi_decoder();

}  // namespace tuner_core::bench_simulator
