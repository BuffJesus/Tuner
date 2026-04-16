// SPDX-License-Identifier: MIT
//
// Tests for tuner_core::runtime_telemetry — forty-fifth sub-slice.

#include <doctest.h>

#include "tuner_core/runtime_telemetry.hpp"

#include <string>
#include <vector>

namespace rt = tuner_core::runtime_telemetry;

static rt::ValueMap make_values(
    std::initializer_list<std::pair<std::string, double>> pairs) {
    return rt::ValueMap(pairs);
}

// -----------------------------------------------------------------------
// 1. Empty values → info severity, no capabilities
// -----------------------------------------------------------------------
TEST_CASE("rt: empty values produce info summary") {
    auto summary = rt::decode({});
    CHECK(summary.severity == "info");
    CHECK(summary.runtime_summary_text.find("not reported") != std::string::npos);
    CHECK(summary.capability_summary_text.find("not reported") != std::string::npos);
}

// -----------------------------------------------------------------------
// 2. Board capabilities decoded from packed byte
// -----------------------------------------------------------------------
TEST_CASE("rt: board capabilities from packed byte") {
    // 0xFF = all bits set.
    auto summary = rt::decode(make_values({{"boardCapabilities", 255.0}}));
    CHECK(summary.board_capabilities.rtc);
    CHECK(summary.board_capabilities.sd);
    CHECK(summary.board_capabilities.native_can);
    CHECK(summary.board_capabilities.spi_flash);
    CHECK(summary.board_capabilities.adc_12bit);
    CHECK(summary.board_capabilities.high_res_tables);
    CHECK(summary.board_capabilities.unrestricted_interrupts);
    CHECK(summary.board_capabilities.wifi_transport);
}

// -----------------------------------------------------------------------
// 3. Board capabilities from individual channels
// -----------------------------------------------------------------------
TEST_CASE("rt: board capabilities from individual channels") {
    auto summary = rt::decode(make_values({
        {"boardCap_rtc", 1.0},
        {"boardCap_sd", 0.0},
        {"boardCap_wifiTransport", 1.0},
    }));
    CHECK(summary.board_capabilities.rtc);
    CHECK(!summary.board_capabilities.sd);
    CHECK(summary.board_capabilities.wifi_transport);
}

// -----------------------------------------------------------------------
// 4. Runtime status decoded from packed byte
// -----------------------------------------------------------------------
TEST_CASE("rt: runtime status from packed byte") {
    // Bit 4 = fullSync, bit 7 = tuneLearnValid → 0x90 = 144.
    auto summary = rt::decode(make_values({{"runtimeStatusA", 144.0}}));
    CHECK(summary.runtime_status.full_sync);
    CHECK(summary.runtime_status.tune_learn_valid);
    CHECK(!summary.runtime_status.transient_active);
}

// -----------------------------------------------------------------------
// 4b. active_tune_slot from status5 bits 6..7 (Slice 14G first step)
// -----------------------------------------------------------------------
TEST_CASE("rt: active_tune_slot extracts from status5 bits 6..7") {
    // status5 = 0x00 → slot 0 (default today, pre-multi-tune).
    auto s0 = rt::decode(make_values({{"status5", 0.0}}));
    REQUIRE(s0.runtime_status.active_tune_slot.has_value());
    CHECK(*s0.runtime_status.active_tune_slot == 0);

    // status5 = 0x40 (bit 6 set) → slot 1.
    auto s1 = rt::decode(make_values({{"status5", 64.0}}));
    REQUIRE(s1.runtime_status.active_tune_slot.has_value());
    CHECK(*s1.runtime_status.active_tune_slot == 1);

    // status5 = 0x80 (bit 7 set) → slot 2.
    auto s2 = rt::decode(make_values({{"status5", 128.0}}));
    REQUIRE(s2.runtime_status.active_tune_slot.has_value());
    CHECK(*s2.runtime_status.active_tune_slot == 2);

    // status5 = 0xC0 (both set) → slot 3.
    auto s3 = rt::decode(make_values({{"status5", 192.0}}));
    REQUIRE(s3.runtime_status.active_tune_slot.has_value());
    CHECK(*s3.runtime_status.active_tune_slot == 3);

    // status5 bits 0..5 don't affect slot decode.
    // 0x3F | 0x40 = 0x7F → slot 1 regardless of low bits.
    auto s_mixed = rt::decode(make_values({{"status5", 0x7F}}));
    REQUIRE(s_mixed.runtime_status.active_tune_slot.has_value());
    CHECK(*s_mixed.runtime_status.active_tune_slot == 1);
}

TEST_CASE("rt: active_tune_slot direct channel overrides status5") {
    // When firmware eventually exposes `activeTuneSlot` as a direct
    // named channel, the direct value takes precedence over bit decode.
    auto summary = rt::decode(make_values({
        {"status5", 0xC0},        // bits 6..7 → slot 3
        {"activeTuneSlot", 2.0},  // direct → slot 2
    }));
    REQUIRE(summary.runtime_status.active_tune_slot.has_value());
    CHECK(*summary.runtime_status.active_tune_slot == 2);
}

TEST_CASE("rt: active_tune_slot nullopt when neither channel present") {
    auto summary = rt::decode(make_values({{"rpm", 1000.0}}));
    CHECK_FALSE(summary.runtime_status.active_tune_slot.has_value());
}

// -----------------------------------------------------------------------
// 4c. Status3/Status4 bit channels surfaced (14C)
// -----------------------------------------------------------------------
TEST_CASE("rt: half_sync / burn_pending / staging / fan / wmi / vvt bits") {
    // All bits off → all fields false.
    auto off = rt::decode(make_values({
        {"halfSync", 0.0}, {"burnPending", 0.0}, {"stagingActive", 0.0},
        {"fanStatus", 0.0}, {"vvt1Error", 0.0}, {"vvt2Error", 0.0},
        {"wmiEmptyBit", 0.0},
    }));
    CHECK_FALSE(off.runtime_status.half_sync);
    CHECK_FALSE(off.runtime_status.burn_pending);
    CHECK_FALSE(off.runtime_status.staging_active);
    CHECK_FALSE(off.runtime_status.fan_on);
    CHECK_FALSE(off.runtime_status.vvt1_error);
    CHECK_FALSE(off.runtime_status.vvt2_error);
    CHECK_FALSE(off.runtime_status.wmi_empty);

    // All bits on → all fields true.
    auto on = rt::decode(make_values({
        {"halfSync", 1.0}, {"burnPending", 1.0}, {"stagingActive", 1.0},
        {"fanStatus", 1.0}, {"vvt1Error", 1.0}, {"vvt2Error", 1.0},
        {"wmiEmptyBit", 1.0},
    }));
    CHECK(on.runtime_status.half_sync);
    CHECK(on.runtime_status.burn_pending);
    CHECK(on.runtime_status.staging_active);
    CHECK(on.runtime_status.fan_on);
    CHECK(on.runtime_status.vvt1_error);
    CHECK(on.runtime_status.vvt2_error);
    CHECK(on.runtime_status.wmi_empty);
}

TEST_CASE("rt: status3/4 bits default to false when channels absent") {
    auto summary = rt::decode(make_values({{"rpm", 1000.0}}));
    CHECK_FALSE(summary.runtime_status.half_sync);
    CHECK_FALSE(summary.runtime_status.vvt1_error);
    CHECK_FALSE(summary.runtime_status.wmi_empty);
}

// -----------------------------------------------------------------------
// 5. Tune learn valid → "ok" severity
// -----------------------------------------------------------------------
TEST_CASE("rt: tune learn valid gives ok severity") {
    auto summary = rt::decode(make_values({{"runtimeStatusA", 0x90}}));
    CHECK(summary.severity == "ok");
    CHECK(summary.runtime_summary_text.find("Tune Learn Valid") != std::string::npos);
}

// -----------------------------------------------------------------------
// 6. Tune learn blocked → "warning" severity with blockers
// -----------------------------------------------------------------------
TEST_CASE("rt: tune learn blocked gives warning") {
    // Bit 5 = transient, bit 6 = warmup → 0x60 = 96. No fullSync, no tuneLearn.
    auto summary = rt::decode(make_values({{"runtimeStatusA", 96.0}}));
    CHECK(summary.severity == "warning");
    CHECK(summary.operator_summary_text.find("blocked") != std::string::npos);
    CHECK(summary.operator_summary_text.find("no full sync") != std::string::npos);
    CHECK(summary.operator_summary_text.find("transient active") != std::string::npos);
}

// -----------------------------------------------------------------------
// 7. SPI flash health decoded
// -----------------------------------------------------------------------
TEST_CASE("rt: SPI flash health decoded") {
    auto healthy = rt::decode(make_values({{"spiFlashHealth", 1.0}}));
    REQUIRE(healthy.spi_flash_health.has_value());
    CHECK(*healthy.spi_flash_health == true);

    auto unhealthy = rt::decode(make_values({{"spiFlashHealth", 0.0}}));
    REQUIRE(unhealthy.spi_flash_health.has_value());
    CHECK(*unhealthy.spi_flash_health == false);
}

// -----------------------------------------------------------------------
// 8. Available labels populated
// -----------------------------------------------------------------------
TEST_CASE("rt: available labels populated") {
    auto summary = rt::decode(make_values({{"boardCapabilities", 0x07}}));  // RTC + SD + CAN
    auto labels = summary.board_capabilities.available_labels();
    CHECK(labels.size() == 3);
    CHECK(labels[0] == "RTC");
    CHECK(labels[1] == "SD");
    CHECK(labels[2] == "Native CAN");
}

// -----------------------------------------------------------------------
// 9. Capability summary contains labels
// -----------------------------------------------------------------------
TEST_CASE("rt: capability summary text contains labels") {
    auto summary = rt::decode(make_values({
        {"boardCapabilities", 0x80},  // wifi only
        {"spiFlashHealth", 1.0},
    }));
    CHECK(summary.capability_summary_text.find("Wi-Fi transport") != std::string::npos);
    CHECK(summary.capability_summary_text.find("SPI flash healthy") != std::string::npos);
}

// -----------------------------------------------------------------------
// 10. Setup guidance for DropBear-class board
// -----------------------------------------------------------------------
TEST_CASE("rt: setup guidance for DropBear board") {
    auto summary = rt::decode(make_values({
        {"boardCapabilities", 0xFF},
        {"spiFlashHealth", 1.0},
    }));
    CHECK(summary.setup_guidance_text.find("unrestricted interrupts") != std::string::npos);
    CHECK(summary.setup_guidance_text.find("SPI flash-backed storage is present") != std::string::npos);
}

// -----------------------------------------------------------------------
// 11. Persistence summary for healthy flash
// -----------------------------------------------------------------------
TEST_CASE("rt: persistence summary for healthy flash") {
    auto summary = rt::decode(make_values({
        {"boardCapabilities", 0x08},  // spi_flash bit
        {"spiFlashHealth", 1.0},
    }));
    CHECK(summary.persistence_summary_text.find("flash-backed") != std::string::npos);
}

// -----------------------------------------------------------------------
// 12. Persistence summary for bad flash
// -----------------------------------------------------------------------
TEST_CASE("rt: persistence summary for bad flash") {
    auto summary = rt::decode(make_values({
        {"boardCapabilities", 0x08},
        {"spiFlashHealth", 0.0},
    }));
    CHECK(summary.persistence_summary_text.find("runtime health is bad") != std::string::npos);
}
