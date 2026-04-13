// SPDX-License-Identifier: MIT
//
// tuner_core::runtime_telemetry — port of SpeeduinoRuntimeTelemetryService.
// Forty-fifth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Decodes Speeduino runtime telemetry from a flat channel-value map into
// board capability flags, runtime status bits, and operator-facing
// summaries. Pure logic, no transport or Qt.

#pragma once

#include "sample_gate_helpers.hpp"  // ValueMap

#include <optional>
#include <string>
#include <vector>

namespace tuner_core::runtime_telemetry {

using ValueMap = sample_gate_helpers::ValueMap;

struct BoardCapabilities {
    std::optional<int> raw_value;
    bool rtc = false;
    bool sd = false;
    bool native_can = false;
    bool spi_flash = false;
    bool adc_12bit = false;
    bool high_res_tables = false;
    bool unrestricted_interrupts = false;
    bool wifi_transport = false;

    std::vector<std::string> available_labels() const;
};

struct RuntimeStatus {
    std::optional<int> raw_value;
    bool fuel_pump_on = false;
    bool launch_hard_active = false;
    bool flat_shift_hard_active = false;
    bool idle_up_active = false;
    bool full_sync = false;
    bool transient_active = false;
    bool warmup_or_ase_active = false;
    bool tune_learn_valid = false;
};

struct TelemetrySummary {
    BoardCapabilities board_capabilities;
    RuntimeStatus runtime_status;
    std::optional<bool> spi_flash_health;
    std::string capability_summary_text;
    std::string runtime_summary_text;
    std::string operator_summary_text;
    std::string setup_guidance_text;
    std::string persistence_summary_text;
    std::string severity;  // "info" | "ok" | "warning"
};

// Decode runtime telemetry from a flat channel-value map.
TelemetrySummary decode(const ValueMap& values);

}  // namespace tuner_core::runtime_telemetry
