// SPDX-License-Identifier: MIT
//
// Implementation of the 64-entry wheel pattern catalog. The data
// table mirrors the upstream `WheelType` enum + `*_friendly_name`
// strings from
//   resources/Ardu-Stim-master/ardustim/ardustim/wheel_defs.h.
//
// Decoder support tags are a starting heuristic and should be
// refined via direct firmware decoder survey before any
// operator-facing "guaranteed to work" claim.

#include "tuner_core/bench_simulator_wheel_pattern_catalog.hpp"

#include <algorithm>
#include <array>
#include <stdexcept>

namespace tuner_core::bench_simulator {

namespace {

// Catalog data. One entry per upstream `WheelType` enum value, in
// firmware enum order (index 0 = DIZZY_FOUR_CYLINDER, index 63 =
// GM_40_OSS). The compile-time array layout means the index field
// MUST stay in sync with WheelPatternIndex; the static_asserts at
// the bottom of this file pin the count.
constexpr std::array<WheelPattern, kPatternCount> kCatalog{{
    // cyl=0 means cylinder-agnostic generic wheel (works on any
    // 4/6/8/10/12-cyl engine when the ECU decoder is configured for
    // the wheel shape rather than the engine).

    {WheelPatternIndex::DIZZY_FOUR_CYLINDER,
     "DIZZY_FOUR_CYLINDER", "4 cylinder dizzy",
     4, false, true, true},
    {WheelPatternIndex::DIZZY_SIX_CYLINDER,
     "DIZZY_SIX_CYLINDER", "6 cylinder dizzy",
     6, false, true, true},
    {WheelPatternIndex::DIZZY_EIGHT_CYLINDER,
     "DIZZY_EIGHT_CYLINDER", "8 cylinder dizzy",
     8, false, true, true},
    {WheelPatternIndex::SIXTY_MINUS_TWO,
     "SIXTY_MINUS_TWO", "60-2 crank only",
     0, false, true, true},
    {WheelPatternIndex::SIXTY_MINUS_TWO_WITH_CAM,
     "SIXTY_MINUS_TWO_WITH_CAM", "60-2 crank and cam",
     0, true, true, true},
    {WheelPatternIndex::SIXTY_MINUS_TWO_WITH_HALFMOON_CAM,
     "SIXTY_MINUS_TWO_WITH_HALFMOON_CAM", "60-2 crank and 'half moon' cam",
     0, true, true, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_ONE,
     "THIRTY_SIX_MINUS_ONE", "36-1 crank only",
     0, false, true, true},
    {WheelPatternIndex::TWENTY_FOUR_MINUS_ONE,
     "TWENTY_FOUR_MINUS_ONE", "24-1 crank only",
     0, false, true, true},
    {WheelPatternIndex::FOUR_MINUS_ONE_WITH_CAM,
     "FOUR_MINUS_ONE_WITH_CAM", "4-1 crank wheel with cam",
     0, true, true, true},
    {WheelPatternIndex::EIGHT_MINUS_ONE,
     "EIGHT_MINUS_ONE", "8-1 crank only (R6)",
     4, false, true, true},  // Yamaha R6 is a 4-cyl motorcycle
    {WheelPatternIndex::SIX_MINUS_ONE_WITH_CAM,
     "SIX_MINUS_ONE_WITH_CAM", "6-1 crank with cam",
     0, true, true, true},
    {WheelPatternIndex::TWELVE_MINUS_ONE_WITH_CAM,
     "TWELVE_MINUS_ONE_WITH_CAM", "12-1 crank with cam",
     0, true, true, true},
    {WheelPatternIndex::FOURTY_MINUS_ONE,
     "FOURTY_MINUS_ONE", "40-1 crank only (Ford V10)",
     10, false, true, true},
    {WheelPatternIndex::DIZZY_FOUR_TRIGGER_RETURN,
     "DIZZY_FOUR_TRIGGER_RETURN", "Distributor style 4 cyl 50deg off, 40 deg on",
     4, false, false, true},
    {WheelPatternIndex::ODDFIRE_VR,
     "ODDFIRE_VR", "odd fire 90 deg pattern 0 and 135 pulses",
     2, false, false, true},
    {WheelPatternIndex::OPTISPARK_LT1,
     "OPTISPARK_LT1", "GM OptiSpark LT1 360 and 8",
     8, true, true, true},
    {WheelPatternIndex::TWELVE_MINUS_THREE,
     "TWELVE_MINUS_THREE", "12-3 oddball",
     0, false, true, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_TWO_TWO_TWO,
     "THIRTY_SIX_MINUS_TWO_TWO_TWO", "36-2-2-2 H4 Crank only",
     4, false, true, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_TWO_TWO_TWO_H6,
     "THIRTY_SIX_MINUS_TWO_TWO_TWO_H6", "36-2-2-2 H6 Crank only",
     6, false, true, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_CAM,
     "THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_CAM", "36-2-2-2 Crank and cam",
     0, true, true, true},
    {WheelPatternIndex::FOURTY_TWO_HUNDRED_WHEEL,
     "FOURTY_TWO_HUNDRED_WHEEL", "GM 4200 crank wheel",
     6, false, true, true},  // GM Atlas inline-6
    {WheelPatternIndex::THIRTY_SIX_MINUS_ONE_WITH_CAM_FE3,
     "THIRTY_SIX_MINUS_ONE_WITH_CAM_FE3", "Mazda FE3 36-1 with cam",
     4, true, true, true},
    {WheelPatternIndex::SIX_G_SEVENTY_TWO_WITH_CAM,
     "SIX_G_SEVENTY_TWO_WITH_CAM", "Mitsubishi 6g72 with cam",
     6, true, true, true},
    {WheelPatternIndex::BUELL_ODDFIRE_CAM,
     "BUELL_ODDFIRE_CAM", "Buell Oddfire CAM wheel",
     2, true, false, true},
    {WheelPatternIndex::GM_LS1_CRANK_AND_CAM,
     "GM_LS1_CRANK_AND_CAM", "GM LS1 crank and cam",
     8, true, true, true},  // 24x crank
    {WheelPatternIndex::GM_58X_LS_CRANK_4X_CAM,
     "GM_58X_LS_CRANK_4X_CAM", "GM 58x crank and 4x cam",
     8, true, true, true},
    {WheelPatternIndex::LOTUS_THIRTY_SIX_MINUS_ONE_ONE_ONE_ONE,
     "LOTUS_THIRTY_SIX_MINUS_ONE_ONE_ONE_ONE", "Odd Lotus 36-1-1-1-1 flywheel",
     4, false, true, true},
    {WheelPatternIndex::HONDA_RC51_WITH_CAM,
     "HONDA_RC51_WITH_CAM", "Honda RC51 with cam",
     2, true, false, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_ONE_WITH_SECOND_TRIGGER,
     "THIRTY_SIX_MINUS_ONE_WITH_SECOND_TRIGGER", "36-1 crank with 2nd trigger on teeth 33-34",
     0, true, true, true},
    {WheelPatternIndex::CHRYSLER_NGC_THIRTY_SIX_PLUS_TWO_MINUS_TWO_WITH_NGC4_CAM,
     "CHRYSLER_NGC_THIRTY_SIX_PLUS_TWO_MINUS_TWO_WITH_NGC4_CAM",
     "Chrysler NGC 36+2-2 crank, NGC 4-cyl cam",
     4, true, true, true},
    {WheelPatternIndex::CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC6_CAM,
     "CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC6_CAM",
     "Chrysler NGC 36-2+2 crank, NGC 6-cyl cam",
     6, true, true, true},
    {WheelPatternIndex::CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC8_CAM,
     "CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC8_CAM",
     "Chrysler NGC 36-2+2 crank, NGC 8-cyl cam",
     8, true, true, true},
    {WheelPatternIndex::WEBER_IAW_WITH_CAM,
     "WEBER_IAW_WITH_CAM", "Weber-Marelli 8 crank+2 cam pattern",
     0, true, false, true},
    {WheelPatternIndex::FIAT_ONE_POINT_EIGHT_SIXTEEN_VALVE_WITH_CAM,
     "FIAT_ONE_POINT_EIGHT_SIXTEEN_VALVE_WITH_CAM", "Fiat 1.8 16V crank and cam",
     4, true, false, true},
    {WheelPatternIndex::THREE_SIXTY_NISSAN_CAS,
     "THREE_SIXTY_NISSAN_CAS", "Nissan 360 CAS with 6 slots",
     6, true, true, true},  // VG30/VQ-family CAS
    {WheelPatternIndex::TWENTY_FOUR_MINUS_TWO_WITH_SECOND_TRIGGER,
     "TWENTY_FOUR_MINUS_TWO_WITH_SECOND_TRIGGER",
     "Mazda CAS 24-2 with single pulse outer ring",
     4, true, true, true},
    {WheelPatternIndex::YAMAHA_EIGHT_TOOTH_WITH_CAM,
     "YAMAHA_EIGHT_TOOTH_WITH_CAM", "Yamaha 2002-03 R1 8 even-tooth crank with 1 tooth cam",
     4, true, true, true},
    {WheelPatternIndex::GM_FOUR_TOOTH_WITH_CAM,
     "GM_FOUR_TOOTH_WITH_CAM", "GM 4 even-tooth crank with 1 tooth cam",
     4, true, true, true},
    {WheelPatternIndex::GM_SIX_TOOTH_WITH_CAM,
     "GM_SIX_TOOTH_WITH_CAM", "GM 6 even-tooth crank with 1 tooth cam",
     6, true, true, true},
    {WheelPatternIndex::GM_EIGHT_TOOTH_WITH_CAM,
     "GM_EIGHT_TOOTH_WITH_CAM", "GM 8 even-tooth crank with 1 tooth cam",
     8, true, true, true},
    {WheelPatternIndex::VOLVO_D12ACD_WITH_CAM,
     "VOLVO_D12ACD_WITH_CAM", "Volvo d12[acd] crank with 7 tooth cam",
     6, true, false, true},  // Volvo D12 inline-6 diesel
    {WheelPatternIndex::MAZDA_THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_SIX_TOOTH_CAM,
     "MAZDA_THIRTY_SIX_MINUS_TWO_TWO_TWO_WITH_SIX_TOOTH_CAM",
     "Mazda 36-2-2-2 with 6 tooth cam",
     4, true, true, true},
    {WheelPatternIndex::MITSUBISHI_4G63_4_2,
     "MITSUBISHI_4G63_4_2", "Mitsubishi 4g63 aka 4/2 crank and cam",
     4, true, true, true},
    {WheelPatternIndex::AUDI_135_WITH_CAM,
     "AUDI_135_WITH_CAM", "Audi 135 tooth crank and cam",
     0, true, false, true},
    {WheelPatternIndex::HONDA_D17_NO_CAM,
     "HONDA_D17_NO_CAM", "Honda D17 Crank (12+1)",
     4, false, false, true},  // D17 SOHC inline-4
    {WheelPatternIndex::MAZDA_323_AU,
     "MAZDA_323_AU", "Mazda 323 AU version",
     4, false, false, true},
    {WheelPatternIndex::DAIHATSU_3CYL,
     "DAIHATSU_3CYL", "Daihatsu 3+1 distributor (3 cylinders)",
     3, false, false, true},
    {WheelPatternIndex::MIATA_9905,
     "MIATA_9905", "Miata 99-05",
     4, true, true, true},
    {WheelPatternIndex::TWELVE_WITH_CAM,
     "TWELVE_WITH_CAM", "12/1 (12 crank with cam)",
     0, true, true, true},
    {WheelPatternIndex::TWENTY_FOUR_WITH_CAM,
     "TWENTY_FOUR_WITH_CAM", "24/1 (24 crank with cam)",
     0, true, true, true},
    {WheelPatternIndex::SUBARU_SIX_SEVEN,
     "SUBARU_SIX_SEVEN", "Subaru 6/7 crank and cam",
     4, true, true, true},  // pre-EJ Subaru H4
    {WheelPatternIndex::GM_7X,
     "GM_7X", "GM 7X",
     6, false, true, true},  // GM 3.8L V6 & others
    {WheelPatternIndex::FOUR_TWENTY_A,
     "FOUR_TWENTY_A", "DSM 420a",
     4, true, true, true},
    {WheelPatternIndex::FORD_ST170,
     "FORD_ST170", "Ford ST170",
     4, true, true, true},
    {WheelPatternIndex::MITSUBISHI_3A92,
     "MITSUBISHI_3A92", "Mitsubishi 3A92",
     3, true, false, true},
    {WheelPatternIndex::TOYOTA_4AGE_CAS,
     "TOYOTA_4AGE_CAS", "Toyota 4AGE",
     4, true, true, true},
    {WheelPatternIndex::TOYOTA_4AGZE,
     "TOYOTA_4AGZE", "Toyota 4AGZE",
     4, true, true, true},
    {WheelPatternIndex::SUZUKI_DRZ400,
     "SUZUKI_DRZ400", "Suzuki DRZ400",
     1, false, false, true},
    {WheelPatternIndex::JEEP2000_4CYL,
     "JEEP2000_4CYL", "Jeep 2000 4cyl",
     4, true, true, true},
    {WheelPatternIndex::JEEP2000_6CYL,
     "JEEP2000_6CYL", "Jeep 2000 6 cyl",
     6, true, true, true},
    {WheelPatternIndex::BMW_N20,
     "BMW_N20", "BMW N20",
     4, true, true, true},  // N20 inline-4 turbo
    {WheelPatternIndex::VIPER_96_02,
     "VIPER_96_02", "Dodge Viper V10 1996-2002",
     10, true, false, true},
    {WheelPatternIndex::THIRTY_SIX_MINUS_TWO_WITH_ONE_CAM,
     "THIRTY_SIX_MINUS_TWO_WITH_ONE_CAM", "36-2 with 1 tooth cam",
     6, true, true, true},  // 2JZ-GTE VVTI hybrid → I6
    {WheelPatternIndex::GM_40_OSS,
     "GM_40_OSS", "GM 40 tooth OSS wheel for Transmissions",
     0, false, false, false},  // Transmission output shaft, not a crank
}};

}  // namespace

std::span<const WheelPattern> patterns() noexcept {
    return std::span<const WheelPattern>(kCatalog.data(), kCatalog.size());
}

const WheelPattern& pattern_at(std::size_t index) {
    if (index >= kCatalog.size()) {
        throw std::out_of_range("wheel_pattern_catalog: index out of range");
    }
    return kCatalog[index];
}

std::optional<std::size_t> find_by_enum_name(std::string_view enum_name) noexcept {
    for (std::size_t i = 0; i < kCatalog.size(); ++i) {
        if (kCatalog[i].enum_name == enum_name) return i;
    }
    return std::nullopt;
}

std::vector<std::size_t> filter_by_cylinder_count(std::uint8_t cyl) {
    std::vector<std::size_t> out;
    out.reserve(kCatalog.size());
    for (std::size_t i = 0; i < kCatalog.size(); ++i) {
        const auto& p = kCatalog[i];
        if (p.cylinder_count == cyl || p.cylinder_count == 0) {
            out.push_back(i);
        }
    }
    return out;
}

std::vector<std::size_t> filter_by_speeduino_decoder() {
    std::vector<std::size_t> out;
    out.reserve(kCatalog.size());
    for (std::size_t i = 0; i < kCatalog.size(); ++i) {
        if (kCatalog[i].decoder_speeduino) out.push_back(i);
    }
    return out;
}

std::vector<std::size_t> filter_by_rusefi_decoder() {
    std::vector<std::size_t> out;
    out.reserve(kCatalog.size());
    for (std::size_t i = 0; i < kCatalog.size(); ++i) {
        if (kCatalog[i].decoder_rusefi) out.push_back(i);
    }
    return out;
}

static_assert(kCatalog.size() == kPatternCount,
              "catalog size must match kPatternCount");
static_assert(static_cast<std::size_t>(WheelPatternIndex::GM_40_OSS) ==
              kPatternCount - 1,
              "GM_40_OSS must be the last entry to match upstream MAX_WHEELS - 1");

}  // namespace tuner_core::bench_simulator
