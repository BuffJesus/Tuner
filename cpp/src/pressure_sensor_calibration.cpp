// SPDX-License-Identifier: MIT
//
// tuner_core::pressure_sensor_calibration implementation. Pure logic.

#include "tuner_core/pressure_sensor_calibration.hpp"

#include <array>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <string>

namespace tuner_core::pressure_sensor_calibration {

namespace {

constexpr double kMatchToleranceKpa = 0.5;

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

// Mirror `urlparse(url).netloc`: extract the host (and port, if any)
// from a `scheme://host[:port]/path...` URL. The Python service only
// looks at `.netloc.lower()`, so we don't need full URL parsing —
// just the section between the `//` and the next `/` or end-of-string.
// Returns lowercased.
std::string url_netloc_lower(std::string_view url) {
    auto schema_end = url.find("://");
    std::size_t start = (schema_end == std::string_view::npos) ? 0 : (schema_end + 3);
    std::size_t end = start;
    while (end < url.size() && url[end] != '/' && url[end] != '?' && url[end] != '#') {
        ++end;
    }
    return lowercase(url.substr(start, end - start));
}

std::string fmt_0f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.0f", v);
    return std::string(buf);
}

std::string sensor_kind_upper(SensorKind kind) {
    return kind == SensorKind::MAP ? "MAP" : "BARO";
}

}  // namespace

std::optional<Preset> find_matching_preset(
    double minimum_value,
    double maximum_value,
    const std::vector<Preset>& presets) {
    for (const auto& p : presets) {
        if (std::abs(p.minimum_value - minimum_value) <= kMatchToleranceKpa &&
            std::abs(p.maximum_value - maximum_value) <= kMatchToleranceKpa) {
            return p;
        }
    }
    return std::nullopt;
}

std::string source_confidence_label(
    std::string_view source_note,
    const std::optional<std::string>& source_url) {
    auto note = lowercase(source_note);
    if (contains(note, "inferred") || !source_url.has_value()) {
        return "Starter";
    }
    auto domain = url_netloc_lower(*source_url);

    static constexpr std::array<std::string_view, 5> kOfficial = {
        "injectordynamics.com",
        "chevrolet.com",
        "documents.holley.com",
        "dtec.net.au",
        "nxp.com",
    };
    for (auto official : kOfficial) {
        if (contains(domain, official)) return "Official";
    }

    static constexpr std::array<std::string_view, 4> kSecondary = {
        "ms4x.net",
        "injector-rehab.com",
        "mpsracing.com",
        "msextra.com",
    };
    for (auto secondary : kSecondary) {
        if (contains(domain, secondary)) return "Trusted Secondary";
    }

    return "Sourced";
}

Assessment assess(
    std::optional<double> minimum_value,
    std::optional<double> maximum_value,
    const std::vector<Preset>& presets,
    SensorKind sensor_kind) {
    Assessment a;
    a.minimum_value = minimum_value;
    a.maximum_value = maximum_value;

    if (!minimum_value.has_value() || !maximum_value.has_value()) {
        a.guidance = "No " + sensor_kind_upper(sensor_kind) +
                     " calibration range is available yet.";
        return a;
    }

    auto preset = find_matching_preset(*minimum_value, *maximum_value, presets);

    std::optional<std::string> warning;
    if (sensor_kind == SensorKind::BARO && *maximum_value > 150.0) {
        warning =
            "External baro calibration spans well beyond normal atmospheric pressure. "
            "Verify that a dedicated MAP/TMAP-style sensor is intentionally being used for baro.";
    }

    if (preset.has_value()) {
        std::string confidence = source_confidence_label(
            preset->source_note, preset->source_url);
        std::string guidance =
            "Current " + sensor_kind_upper(sensor_kind) +
            " calibration matches " + preset->label + " (" +
            fmt_0f(preset->minimum_value) + "-" + fmt_0f(preset->maximum_value) +
            " " + preset->units + "). [" + confidence + "] " + preset->source_note;
        a.matching_preset = std::move(preset);
        a.guidance = std::move(guidance);
        a.warning = std::move(warning);
        return a;
    }

    a.guidance = "Current " + sensor_kind_upper(sensor_kind) +
                 " calibration is " + fmt_0f(*minimum_value) + "-" +
                 fmt_0f(*maximum_value) +
                 " kPa and does not match a curated preset.";
    a.warning = std::move(warning);
    return a;
}

}  // namespace tuner_core::pressure_sensor_calibration
