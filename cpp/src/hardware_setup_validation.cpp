// SPDX-License-Identifier: MIT
//
// tuner_core::hardware_setup_validation implementation. Pure logic,
// direct port of `HardwareSetupValidationService`.

#include "tuner_core/hardware_setup_validation.hpp"

#include <array>
#include <cctype>
#include <cstdio>
#include <string>

namespace tuner_core::hardware_setup_validation {

namespace {

// Mirror Python module-level constants.
constexpr double kDwellMaxMs = 10.0;
constexpr double kDwellMinPlausibleMs = 1.5;
constexpr double kDwellMaxPlausibleMs = 6.0;
constexpr double kInjopenMaxPlausibleMs = 5.0;

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

bool contains(std::string_view haystack, std::string_view needle) noexcept {
    return haystack.find(needle) != std::string_view::npos;
}

// Format a double the way Python's f"{x:.1f}" does — fixed-point,
// 1 decimal, half-to-even rounding via printf's standard %.1f. The
// IEEE 754 default rounding matches Python's `format(x, '.1f')` for
// every case the parity test exercises.
std::string fmt_1f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.1f", v);
    return std::string(buf);
}

std::string fmt_0f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.0f", v);
    return std::string(buf);
}

Issue make_issue(
    Severity severity,
    std::string message,
    std::string parameter_name,
    std::optional<std::string> detail = std::nullopt) {
    Issue i;
    i.severity = severity;
    i.message = std::move(message);
    i.parameter_name = std::move(parameter_name);
    i.detail = std::move(detail);
    return i;
}

// ---------------------------------------------------------------------------
// Rule helpers
// ---------------------------------------------------------------------------

bool is_dwell_named(const std::string& lower) {
    return contains(lower, "dwell") ||
           lower == "sparkdur" || lower == "coildwell" || lower == "dwelltime";
}

bool is_dead_time_named(const std::string& lower) {
    return contains(lower, "deadtime") || contains(lower, "injopen") ||
           lower == "injectoropen" || lower == "opentime";
}

bool is_injector_flow_named(const std::string& lower) {
    return contains(lower, "injectorflow") ||
           contains(lower, "injflow") ||
           contains(lower, "injsize");
}

void check_dwell_excessive(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (!is_dwell_named(lower)) continue;
        auto v = get_value(name);
        if (!v.has_value() || *v <= kDwellMaxMs) continue;
        std::string msg =
            "Dwell time " + fmt_1f(*v) +
            " ms is excessive and may damage ignition coils.";
        std::string detail =
            "Safe maximum is " + fmt_0f(kDwellMaxMs) +
            " ms. Check coil specifications before proceeding.";
        out.push_back(make_issue(Severity::ERROR, std::move(msg), name, std::move(detail)));
    }
}

void check_dwell_zero(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        bool match =
            contains(lower, "dwell") ||
            lower == "sparkdur" || lower == "coildwell" ||
            lower == "dwelltime" || lower == "dwellrun";
        if (!match) continue;
        auto v = get_value(name);
        if (!v.has_value() || *v != 0.0) continue;
        std::string msg =
            "Dwell time '" + name + "' is zero. "
            "Coils will not charge and the engine will not fire. "
            "Set dwell from the coil datasheet before enabling ignition.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), name));
    }
}

void check_dwell_implausible_range(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        if (lowercase(name) != "dwellrun") continue;
        auto v = get_value(name);
        if (!v.has_value() || *v == 0.0) continue;
        if (*v > kDwellMaxMs) continue;
        if (*v >= kDwellMinPlausibleMs && *v <= kDwellMaxPlausibleMs) continue;
        std::string msg =
            "Running dwell '" + name + "' is " + fmt_1f(*v) +
            " ms — outside the typical 1.5–6.0 ms range. "
            "Verify against your coil's datasheet.";
        std::string detail =
            "Very low dwell (<1.5 ms) may produce a weak spark. "
            "Dwell above 6.0 ms may cause coil overheating at idle.";
        out.push_back(
            make_issue(Severity::WARNING, std::move(msg), name, std::move(detail)));
    }
}

void check_trigger_geometry(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    std::optional<std::string> tooth_name;
    std::optional<std::string> missing_name;
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (!tooth_name.has_value() &&
            (contains(lower, "nteeth") || lower == "toothcount" ||
             lower == "triggerteeth" || lower == "crankteeth")) {
            tooth_name = name;
        }
        if (!missing_name.has_value() &&
            (contains(lower, "missingteeth") || contains(lower, "missingtooth"))) {
            missing_name = name;
        }
    }
    if (!tooth_name.has_value() || !missing_name.has_value()) return;
    auto teeth = get_value(*tooth_name);
    auto missing = get_value(*missing_name);
    if (!teeth.has_value() || !missing.has_value()) return;

    if (*missing >= *teeth) {
        std::string msg =
            "Missing tooth count (" + fmt_0f(*missing) +
            ") must be less than total tooth count (" + fmt_0f(*teeth) + ").";
        out.push_back(make_issue(
            Severity::ERROR, std::move(msg), *missing_name,
            std::string("The ECU will fail to sync if missing teeth >= total teeth.")));
        return;
    }
    if (*teeth > 0 && *missing >= *teeth / 2.0) {
        std::string msg =
            "Missing tooth count (" + fmt_0f(*missing) +
            ") is more than half of total teeth (" + fmt_0f(*teeth) +
            "). Verify this matches your physical wheel.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), *missing_name));
    }
}

void check_dead_time_zero(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (!is_dead_time_named(lower)) continue;
        auto v = get_value(name);
        if (!v.has_value() || *v != 0.0) continue;
        std::string msg =
            "Injector dead time '" + name +
            "' is zero. "
            "Most injectors require a non-zero dead time for accurate fuelling.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), name));
    }
}

void check_injopen_range(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (!is_dead_time_named(lower)) continue;
        auto v = get_value(name);
        if (!v.has_value() || *v <= 0.0 || *v <= kInjopenMaxPlausibleMs) continue;
        std::string msg =
            "Injector dead time '" + name + "' is " + fmt_1f(*v) +
            " ms — this is implausibly high and may indicate a scale or units error. "
            "Typical values are 0.3–2.0 ms.";
        std::string detail =
            "Check whether the value was entered in microseconds rather than milliseconds.";
        out.push_back(
            make_issue(Severity::WARNING, std::move(msg), name, std::move(detail)));
    }
}

void check_injector_flow_zero(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (!is_injector_flow_named(lower)) continue;
        auto v = get_value(name);
        if (!v.has_value() || *v != 0.0) continue;
        std::string msg =
            "Injector flow rate '" + name +
            "' is zero. "
            "Enter the rated flow (cc/min) from the injector datasheet before first start.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), name));
    }
}

void check_required_fuel_zero(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        if (lowercase(name) != "reqfuel") continue;
        auto v = get_value(name);
        if (!v.has_value() || *v != 0.0) continue;
        std::string msg =
            "Required fuel is zero. "
            "Calculate and enter the required fuel value before writing or running the engine.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), name));
    }
}

void check_trigger_angle_zero(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (lower != "triggerangle" && lower != "crankangle" &&
            lower != "tdcangle" && lower != "fixang" && lower != "crankedge") continue;
        auto v = get_value(name);
        if (!v.has_value() || *v != 0.0) continue;
        std::string msg =
            "Trigger angle '" + name +
            "' is zero. "
            "Verify this is intentional — most engines require a non-zero TDC reference.";
        out.push_back(make_issue(Severity::WARNING, std::move(msg), name));
        return;  // Python `_check_trigger_angle_zero` returns the first match.
    }
}

void check_wideband_without_calibration(
    const std::vector<std::string>& names,
    const ValueLookup& get_value,
    std::vector<Issue>& out) {
    std::optional<std::string> ego_name;
    for (const auto& name : names) {
        auto lower = lowercase(name);
        if (lower == "egotype" || lower == "afrsensortype" ||
            lower == "o2sensortype" || lower == "lambdatype") {
            ego_name = name;
            break;
        }
    }
    if (!ego_name.has_value()) return;
    auto v = get_value(*ego_name);
    if (!v.has_value() || *v < 2.0) return;

    bool cal_present = false;
    for (const auto& n : names) {
        auto lower = lowercase(n);
        if (contains(lower, "afrcal") || contains(lower, "widebandcal") ||
            contains(lower, "lambdacal")) {
            cal_present = true;
            break;
        }
    }
    if (cal_present) return;

    std::string msg =
        "Wideband sensor selected but no calibration table found on this page. "
        "Verify AFR calibration is configured before relying on autotune.";
    out.push_back(make_issue(Severity::WARNING, std::move(msg), *ego_name));
}

}  // namespace

std::vector<Issue> validate(
    const std::vector<std::string>& parameter_names,
    const ValueLookup& get_value) {
    // Mirror Python `present = set(parameter_names)`: deduplicate
    // while preserving the input order so a parity test that pre-
    // sorts the input on both sides gets a deterministic ordering.
    std::vector<std::string> present;
    present.reserve(parameter_names.size());
    for (const auto& n : parameter_names) {
        bool seen = false;
        for (const auto& p : present) {
            if (p == n) {
                seen = true;
                break;
            }
        }
        if (!seen) present.push_back(n);
    }

    std::vector<Issue> issues;
    check_dwell_excessive(present, get_value, issues);
    check_dwell_zero(present, get_value, issues);
    check_dwell_implausible_range(present, get_value, issues);
    check_trigger_geometry(present, get_value, issues);
    check_dead_time_zero(present, get_value, issues);
    check_injopen_range(present, get_value, issues);
    check_injector_flow_zero(present, get_value, issues);
    check_required_fuel_zero(present, get_value, issues);
    check_trigger_angle_zero(present, get_value, issues);
    check_wideband_without_calibration(present, get_value, issues);
    return issues;
}

}  // namespace tuner_core::hardware_setup_validation
