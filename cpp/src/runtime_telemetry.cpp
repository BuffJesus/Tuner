// SPDX-License-Identifier: MIT
#include "tuner_core/runtime_telemetry.hpp"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

namespace tuner_core::runtime_telemetry {

namespace {

std::optional<int> channel_int(const ValueMap& values, const std::string& name) {
    for (const auto& [k, v] : values) {
        if (k == name) return static_cast<int>(std::round(v));
    }
    return std::nullopt;
}

bool channel_bool(const ValueMap& values, const std::string& name) {
    for (const auto& [k, v] : values) {
        if (k == name) return v >= 0.5;
    }
    return false;
}

BoardCapabilities decode_board_capabilities(const ValueMap& values) {
    auto raw = channel_int(values, "boardCapabilities");
    if (raw.has_value()) {
        int r = *raw;
        return {raw, bool(r & (1 << 0)), bool(r & (1 << 1)), bool(r & (1 << 2)),
                bool(r & (1 << 3)), bool(r & (1 << 4)), bool(r & (1 << 5)),
                bool(r & (1 << 6)), bool(r & (1 << 7))};
    }
    return {std::nullopt,
            channel_bool(values, "boardCap_rtc"),
            channel_bool(values, "boardCap_sd"),
            channel_bool(values, "boardCap_nativeCAN"),
            channel_bool(values, "boardCap_spiFlash"),
            channel_bool(values, "boardCap_12bitADC"),
            channel_bool(values, "boardCap_highResTables"),
            channel_bool(values, "boardCap_unrestrictedIRQ"),
            channel_bool(values, "boardCap_wifiTransport")};
}

RuntimeStatus decode_runtime_status(const ValueMap& values) {
    RuntimeStatus out;
    auto raw = channel_int(values, "runtimeStatusA");
    if (raw.has_value()) {
        int r = *raw;
        out.raw_value               = raw;
        out.fuel_pump_on            = bool(r & (1 << 0));
        out.launch_hard_active      = bool(r & (1 << 1));
        out.flat_shift_hard_active  = bool(r & (1 << 2));
        out.idle_up_active          = bool(r & (1 << 3));
        out.full_sync               = bool(r & (1 << 4));
        out.transient_active        = bool(r & (1 << 5));
        out.warmup_or_ase_active    = bool(r & (1 << 6));
        out.tune_learn_valid        = bool(r & (1 << 7));
    } else {
        out.fuel_pump_on            = channel_bool(values, "rSA_fuelPump");
        out.launch_hard_active      = channel_bool(values, "rSA_launchHard");
        out.flat_shift_hard_active  = channel_bool(values, "rSA_flatShift");
        out.idle_up_active          = channel_bool(values, "rSA_idleUp");
        out.full_sync               = channel_bool(values, "rSA_fullSync");
        out.transient_active        = channel_bool(values, "rSA_transient");
        out.warmup_or_ase_active    = channel_bool(values, "rSA_warmupASE");
        out.tune_learn_valid        = channel_bool(values, "rSA_tuneValid");
    }
    // Active tune slot — firmware 14G adds an `activeTuneSlot` byte
    // to the runtime packet. 0-3 are valid slots; pre-14G firmware
    // doesn't emit the channel so channel_int returns nullopt and
    // we leave `active_tune_slot` unset. 0xFF is the "unknown/none"
    // sentinel firmware uses when the field isn't meaningful.
    auto slot = channel_int(values, "activeTuneSlot");
    if (slot.has_value() && *slot >= 0 && *slot <= 3) {
        out.active_tune_slot = *slot;
    }
    return out;
}

std::optional<bool> decode_spi_flash_health(const ValueMap& values) {
    auto raw = channel_int(values, "spiFlashHealth");
    if (!raw.has_value()) return std::nullopt;
    return *raw != 0;
}

std::string capability_summary_text(const BoardCapabilities& bc,
                                     std::optional<bool> spi_health) {
    auto labels = bc.available_labels();
    std::string cap;
    if (!labels.empty()) {
        for (std::size_t i = 0; i < labels.size(); ++i) {
            if (i > 0) cap += ", ";
            cap += labels[i];
        }
    } else if (bc.raw_value.has_value()) {
        cap = "none advertised";
    } else {
        cap = "not reported";
    }
    const char* flash;
    if (spi_health.has_value() && *spi_health) flash = "SPI flash healthy";
    else if (spi_health.has_value()) flash = "SPI flash unavailable";
    else flash = "SPI flash health unknown";

    char buf[512];
    std::snprintf(buf, sizeof(buf), "Capabilities: %s. %s.", cap.c_str(), flash);
    return buf;
}

struct RuntimeTexts { std::string runtime; std::string op; std::string sev; };

RuntimeTexts runtime_summary_texts(const RuntimeStatus& rs) {
    if (!rs.raw_value.has_value() &&
        !rs.fuel_pump_on && !rs.launch_hard_active && !rs.flat_shift_hard_active &&
        !rs.idle_up_active && !rs.full_sync && !rs.transient_active &&
        !rs.warmup_or_ase_active && !rs.tune_learn_valid) {
        return {
            "Runtime status: runtimeStatusA not reported.",
            "No Speeduino tune-learning status bits are available in the current runtime stream.",
            "info"
        };
    }
    if (rs.tune_learn_valid) {
        return {
            "Runtime status: Tune Learn Valid.",
            "Tune learning is currently allowed: full sync is present and the firmware reports no transient or warmup blockers.",
            "ok"
        };
    }
    std::vector<std::string> blockers;
    if (!rs.full_sync) blockers.push_back("no full sync");
    if (rs.transient_active) blockers.push_back("transient active");
    if (rs.warmup_or_ase_active) blockers.push_back("warmup/ASE active");
    if (blockers.empty()) blockers.push_back("firmware still marks learning blocked");
    std::string joined;
    for (std::size_t i = 0; i < blockers.size(); ++i) {
        if (i > 0) joined += ", ";
        joined += blockers[i];
    }
    return {
        "Runtime status: Tune Learn Blocked.",
        "Tune learning is blocked: " + joined + ".",
        "warning"
    };
}

std::string setup_guidance_text(const BoardCapabilities& bc,
                                 std::optional<bool> spi_health) {
    std::vector<std::string> guidance;
    if (bc.unrestricted_interrupts) {
        guidance.push_back("This board advertises unrestricted interrupts, so trigger input placement is less constrained than on AVR-class hardware.");
    } else if (bc.raw_value.has_value()) {
        guidance.push_back("This board does not advertise unrestricted interrupts; verify trigger inputs against interrupt-capable pins before first start.");
    }
    if (bc.spi_flash && spi_health.has_value() && *spi_health) {
        guidance.push_back("SPI flash-backed storage is present and healthy.");
    } else if (bc.spi_flash && spi_health.has_value() && !*spi_health) {
        guidance.push_back("SPI flash capability is advertised but the runtime health bit is bad; avoid assuming flash-backed persistence is currently available.");
    } else if (spi_health.has_value() && !*spi_health) {
        guidance.push_back("Runtime reports SPI flash unavailable.");
    }
    if (bc.native_can) guidance.push_back("Native CAN hardware is available on this board.");
    if (bc.wifi_transport) guidance.push_back("An onboard Wi-Fi transport coprocessor is advertised by the firmware.");
    if (guidance.empty()) return "No board-specific setup guidance is available from the current runtime telemetry.";
    std::string out;
    for (std::size_t i = 0; i < guidance.size(); ++i) {
        if (i > 0) out += " ";
        out += guidance[i];
    }
    return out;
}

std::string persistence_summary_text(const BoardCapabilities& bc,
                                      std::optional<bool> spi_health) {
    if (bc.spi_flash && spi_health.has_value() && *spi_health)
        return "Persistence: the connected board advertises SPI flash and runtime health is good. Burned changes should be treated as flash-backed, but still verify after reconnect.";
    if (bc.spi_flash && spi_health.has_value() && !*spi_health)
        return "Persistence: SPI flash is advertised but runtime health is bad. Do not trust burn persistence until the storage path is checked on the bench.";
    if (spi_health.has_value() && !*spi_health)
        return "Persistence: runtime reports SPI flash unavailable. Treat burn persistence as unverified until the board reconnects cleanly and storage health is understood.";
    if (bc.raw_value.has_value())
        return "Persistence: no SPI flash-backed storage is advertised by runtime telemetry. Verify burn results after reconnect instead of assuming flash-backed persistence from board family alone.";
    return "Persistence: runtime telemetry does not report storage capability data yet.";
}

}  // namespace

std::vector<std::string> BoardCapabilities::available_labels() const {
    std::vector<std::string> labels;
    if (rtc) labels.push_back("RTC");
    if (sd) labels.push_back("SD");
    if (native_can) labels.push_back("Native CAN");
    if (spi_flash) labels.push_back("SPI flash");
    if (adc_12bit) labels.push_back("12-bit ADC");
    if (high_res_tables) labels.push_back("16-bit tables");
    if (unrestricted_interrupts) labels.push_back("Unrestricted IRQ");
    if (wifi_transport) labels.push_back("Wi-Fi transport");
    return labels;
}

TelemetrySummary decode(const ValueMap& values) {
    auto bc = decode_board_capabilities(values);
    auto rs = decode_runtime_status(values);
    auto spi = decode_spi_flash_health(values);
    auto [runtime_text, op_text, sev] = runtime_summary_texts(rs);

    return {
        bc, rs, spi,
        capability_summary_text(bc, spi),
        runtime_text, op_text,
        setup_guidance_text(bc, spi),
        persistence_summary_text(bc, spi),
        sev
    };
}

}  // namespace tuner_core::runtime_telemetry
