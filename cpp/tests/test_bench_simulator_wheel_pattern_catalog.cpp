// SPDX-License-Identifier: MIT
//
// doctest unit tests for the Phase 17 Slice A bench-simulator
// wheel pattern catalog.

#include "doctest.h"

#include "tuner_core/bench_simulator_wheel_pattern_catalog.hpp"

#include <set>
#include <stdexcept>
#include <string_view>

using namespace tuner_core::bench_simulator;

TEST_CASE("catalog has 64 entries matching upstream WheelType enum") {
    CHECK(pattern_count() == 64);
    CHECK(patterns().size() == 64);
    CHECK(kPatternCount == 64);
}

TEST_CASE("first entry is DIZZY_FOUR_CYLINDER (firmware index 0)") {
    const auto& p = patterns()[0];
    CHECK(p.index == WheelPatternIndex::DIZZY_FOUR_CYLINDER);
    CHECK(p.enum_name == "DIZZY_FOUR_CYLINDER");
    CHECK(p.friendly_name == "4 cylinder dizzy");
    CHECK(p.cylinder_count == 4);
    CHECK_FALSE(p.has_cam);
}

TEST_CASE("last entry is GM_40_OSS (firmware index 63)") {
    const auto& p = patterns()[63];
    CHECK(p.index == WheelPatternIndex::GM_40_OSS);
    CHECK(p.enum_name == "GM_40_OSS");
    CHECK(p.cylinder_count == 0);  // transmission, not crank
}

TEST_CASE("catalog index field matches array position for every entry") {
    for (std::size_t i = 0; i < patterns().size(); ++i) {
        CAPTURE(i);
        CHECK(static_cast<std::size_t>(patterns()[i].index) == i);
    }
}

TEST_CASE("pattern_at returns entry by index and throws on out-of-range") {
    CHECK(pattern_at(0).enum_name == "DIZZY_FOUR_CYLINDER");
    CHECK(pattern_at(63).enum_name == "GM_40_OSS");
    CHECK_THROWS_AS(pattern_at(64), std::out_of_range);
    CHECK_THROWS_AS(pattern_at(999), std::out_of_range);
}

TEST_CASE("find_by_enum_name finds canonical entries") {
    CHECK(find_by_enum_name("DIZZY_FOUR_CYLINDER").value() == 0);
    CHECK(find_by_enum_name("EIGHT_MINUS_ONE").value() == 9);
    CHECK(find_by_enum_name("OPTISPARK_LT1").value() == 15);
    CHECK(find_by_enum_name("GM_LS1_CRANK_AND_CAM").value() == 24);
    CHECK(find_by_enum_name("GM_40_OSS").value() == 63);
}

TEST_CASE("find_by_enum_name is case-sensitive and returns nullopt on miss") {
    CHECK_FALSE(find_by_enum_name("").has_value());
    CHECK_FALSE(find_by_enum_name("dizzy_four_cylinder").has_value());  // wrong case
    CHECK_FALSE(find_by_enum_name("UNKNOWN_PATTERN").has_value());
    CHECK_FALSE(find_by_enum_name("EIGHT_MINUS").has_value());  // partial match
}

TEST_CASE("every entry has a non-empty enum_name and friendly_name") {
    for (const auto& p : patterns()) {
        CAPTURE(p.enum_name);
        CHECK_FALSE(p.enum_name.empty());
        CHECK_FALSE(p.friendly_name.empty());
    }
}

TEST_CASE("enum_names are unique across the catalog") {
    std::set<std::string_view> names;
    for (const auto& p : patterns()) {
        const auto [_, inserted] = names.insert(p.enum_name);
        CAPTURE(p.enum_name);
        CHECK(inserted);
    }
    CHECK(names.size() == kPatternCount);
}

TEST_CASE("friendly_names are unique across the catalog") {
    std::set<std::string_view> labels;
    for (const auto& p : patterns()) {
        const auto [_, inserted] = labels.insert(p.friendly_name);
        CAPTURE(p.friendly_name);
        CHECK(inserted);
    }
}

TEST_CASE("filter_by_cylinder_count(8) returns engine-V8 patterns plus generics") {
    const auto v8 = filter_by_cylinder_count(8);
    CHECK_FALSE(v8.empty());

    std::set<std::string_view> names;
    for (auto i : v8) names.insert(pattern_at(i).enum_name);

    // V8-specific entries the catalog must surface for 8-cyl operators:
    CHECK(names.count("DIZZY_EIGHT_CYLINDER") == 1);
    CHECK(names.count("OPTISPARK_LT1") == 1);
    CHECK(names.count("GM_LS1_CRANK_AND_CAM") == 1);
    CHECK(names.count("GM_58X_LS_CRANK_4X_CAM") == 1);
    CHECK(names.count("GM_EIGHT_TOOTH_WITH_CAM") == 1);
    CHECK(names.count("CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC8_CAM") == 1);

    // Generics that work on any cyl count must also surface:
    CHECK(names.count("SIXTY_MINUS_TWO") == 1);
    CHECK(names.count("THIRTY_SIX_MINUS_ONE") == 1);
    CHECK(names.count("TWENTY_FOUR_MINUS_ONE") == 1);

    // V4/V6/V10-only entries must NOT surface:
    CHECK(names.count("DIZZY_FOUR_CYLINDER") == 0);
    CHECK(names.count("DIZZY_SIX_CYLINDER") == 0);
    CHECK(names.count("FOURTY_MINUS_ONE") == 0);  // Ford V10
    CHECK(names.count("VIPER_96_02") == 0);       // V10
}

TEST_CASE("filter_by_cylinder_count(4) returns V4 patterns plus generics") {
    const auto v4 = filter_by_cylinder_count(4);
    CHECK_FALSE(v4.empty());

    std::set<std::string_view> names;
    for (auto i : v4) names.insert(pattern_at(i).enum_name);

    CHECK(names.count("DIZZY_FOUR_CYLINDER") == 1);
    CHECK(names.count("MIATA_9905") == 1);
    CHECK(names.count("FOUR_TWENTY_A") == 1);
    CHECK(names.count("BMW_N20") == 1);
    CHECK(names.count("EIGHT_MINUS_ONE") == 1);     // R6 motorcycle = 4-cyl
    CHECK(names.count("SIXTY_MINUS_TWO") == 1);     // generic
    CHECK(names.count("DIZZY_EIGHT_CYLINDER") == 0);
    CHECK(names.count("GM_LS1_CRANK_AND_CAM") == 0);
}

TEST_CASE("filter_by_cylinder_count(10) finds Ford and Viper V10 entries") {
    const auto v10 = filter_by_cylinder_count(10);
    std::set<std::string_view> names;
    for (auto i : v10) names.insert(pattern_at(i).enum_name);
    CHECK(names.count("FOURTY_MINUS_ONE") == 1);
    CHECK(names.count("VIPER_96_02") == 1);
}

TEST_CASE("filter_by_cylinder_count(0) returns only cylinder-agnostic generics") {
    const auto generics = filter_by_cylinder_count(0);
    for (auto i : generics) {
        CAPTURE(pattern_at(i).enum_name);
        CHECK(pattern_at(i).cylinder_count == 0);
    }
    CHECK_FALSE(generics.empty());
}

TEST_CASE("filter_by_cylinder_count(99) only returns generics, no engine-specifics") {
    // An out-of-distribution cylinder count should still find the
    // generics (cylinder_count == 0) but no engine-specific entries.
    const auto out = filter_by_cylinder_count(99);
    for (auto i : out) {
        CHECK(pattern_at(i).cylinder_count == 0);
    }
}

TEST_CASE("has_cam flag is consistent for known dual-signal patterns") {
    // OPTISPARK is 360 outer + 8 inner — both signals.
    CHECK(pattern_at(static_cast<std::size_t>(WheelPatternIndex::OPTISPARK_LT1)).has_cam);
    // 60-2 alone has no cam; +CAM variant does.
    CHECK_FALSE(pattern_at(static_cast<std::size_t>(WheelPatternIndex::SIXTY_MINUS_TWO)).has_cam);
    CHECK(pattern_at(static_cast<std::size_t>(WheelPatternIndex::SIXTY_MINUS_TWO_WITH_CAM)).has_cam);
    CHECK(pattern_at(static_cast<std::size_t>(WheelPatternIndex::GM_LS1_CRANK_AND_CAM)).has_cam);
    CHECK(pattern_at(static_cast<std::size_t>(WheelPatternIndex::GM_58X_LS_CRANK_4X_CAM)).has_cam);
}

TEST_CASE("V8 patterns are tagged as decoder-supported by Speeduino and RusEFI") {
    // The Speeduino + RusEFI decoder libraries both ship support
    // for these popular V8 patterns; the bench simulator should
    // surface them as compatible.
    for (auto name : {"DIZZY_EIGHT_CYLINDER",
                      "OPTISPARK_LT1",
                      "GM_LS1_CRANK_AND_CAM",
                      "GM_58X_LS_CRANK_4X_CAM",
                      "GM_EIGHT_TOOTH_WITH_CAM",
                      "CHRYSLER_NGC_THIRTY_SIX_MINUS_TWO_PLUS_TWO_WITH_NGC8_CAM"}) {
        CAPTURE(name);
        auto idx = find_by_enum_name(name);
        REQUIRE(idx.has_value());
        const auto& p = pattern_at(*idx);
        CHECK(p.decoder_speeduino);
        CHECK(p.decoder_rusefi);
    }
}

TEST_CASE("transmission OSS pattern is decoder-incompatible with both firmwares") {
    // GM_40_OSS is a transmission output-shaft sensor, not a crank
    // wheel. It can be emitted by the simulator hardware but no
    // engine-management ECU decoder consumes it.
    const auto& p = pattern_at(static_cast<std::size_t>(WheelPatternIndex::GM_40_OSS));
    CHECK_FALSE(p.decoder_speeduino);
    CHECK_FALSE(p.decoder_rusefi);
}

TEST_CASE("decoder filter helpers return non-empty subsets") {
    const auto sp = filter_by_speeduino_decoder();
    const auto ru = filter_by_rusefi_decoder();
    CHECK_FALSE(sp.empty());
    CHECK_FALSE(ru.empty());
    // Both subsets must be smaller than or equal to the full catalog.
    CHECK(sp.size() <= kPatternCount);
    CHECK(ru.size() <= kPatternCount);
    // RusEFI's decoder library is broader; its tagged-supported
    // subset should be at least as large as Speeduino's.
    CHECK(ru.size() >= sp.size());
}

TEST_CASE("filter_by_speeduino_decoder excludes the transmission OSS entry") {
    const auto sp = filter_by_speeduino_decoder();
    const auto gm_oss_index = static_cast<std::size_t>(WheelPatternIndex::GM_40_OSS);
    for (auto i : sp) CHECK(i != gm_oss_index);
}

TEST_CASE("filter_by_cylinder_count results preserve firmware enum order") {
    const auto v8 = filter_by_cylinder_count(8);
    for (std::size_t i = 1; i < v8.size(); ++i) {
        CAPTURE(i);
        CHECK(v8[i - 1] < v8[i]);
    }
}

TEST_CASE("V10-specific decoder claims: FOURTY_MINUS_ONE on Speeduino, VIPER_96_02 not") {
    // Ford V10 modular uses a standard 40-1 wheel that Speeduino's
    // missing-tooth decoder handles. The Viper V10 wheel is an
    // OEM-specific pattern not in Speeduino's decoder library.
    auto ford = find_by_enum_name("FOURTY_MINUS_ONE");
    auto viper = find_by_enum_name("VIPER_96_02");
    REQUIRE(ford.has_value());
    REQUIRE(viper.has_value());
    CHECK(pattern_at(*ford).decoder_speeduino);
    CHECK_FALSE(pattern_at(*viper).decoder_speeduino);
    CHECK(pattern_at(*viper).decoder_rusefi);  // RusEFI's library is broader
}

TEST_CASE("wizard-cross-link wheel indices stay pinned to firmware enum order") {
    // Phase 17 Slice F: the SETUP wizard's `wheel_index_for` lambda
    // returns plain size_t literals (windows.h macro contamination
    // blocks enum-qualified access in main.cpp). These literals MUST
    // match the WheelPatternIndex enum's integer values; if upstream
    // firmware reshuffles wheel_defs.h::WheelType, this test flags the
    // drift before the wizard ships silently wrong patterns.
    CHECK(static_cast<std::size_t>(WheelPatternIndex::THIRTY_SIX_MINUS_ONE)         == 6);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::SIXTY_MINUS_TWO)              == 3);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::TWENTY_FOUR_MINUS_ONE)        == 7);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::EIGHT_MINUS_ONE)              == 9);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::FOURTY_MINUS_ONE)             == 12);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::FOUR_MINUS_ONE_WITH_CAM)      == 8);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::SIX_MINUS_ONE_WITH_CAM)       == 10);
    CHECK(static_cast<std::size_t>(WheelPatternIndex::TWELVE_MINUS_ONE_WITH_CAM)    == 11);
}

TEST_CASE("catalog covers a reasonable engine cylinder count distribution") {
    int count_v4 = 0, count_v6 = 0, count_v8 = 0, count_v10 = 0, generic = 0;
    for (const auto& p : patterns()) {
        switch (p.cylinder_count) {
            case 4:  ++count_v4;  break;
            case 6:  ++count_v6;  break;
            case 8:  ++count_v8;  break;
            case 10: ++count_v10; break;
            case 0:  ++generic;   break;
            default: break;
        }
    }
    // Minimum expected coverage given upstream firmware as of
    // VERSION 2. These numbers act as a regression fence: if a
    // future firmware update changes the catalog, this test will
    // flag the count shift so we can re-audit the decoder tags.
    CHECK(count_v4 >= 10);
    CHECK(count_v6 >= 5);
    CHECK(count_v8 >= 6);
    CHECK(count_v10 >= 2);
    CHECK(generic >= 10);
}
