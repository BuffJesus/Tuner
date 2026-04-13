// SPDX-License-Identifier: MIT
#include "tuner_core/sensor_setup_checklist.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <string>

namespace tuner_core::sensor_setup_checklist {

// -----------------------------------------------------------------------
// Internal helpers
// -----------------------------------------------------------------------

namespace {

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

using KW = std::vector<std::string>;

const Parameter* find_any(const std::vector<Page>& pages, const KW& keywords) {
    for (const auto& page : pages) {
        for (const auto& param : page.parameters) {
            std::string haystack = to_lower(param.name + " " + param.label);
            for (const auto& kw : keywords) {
                if (haystack.find(kw) != std::string::npos) return &param;
            }
        }
    }
    return nullptr;
}

std::optional<double> numeric(const Parameter* param, ValueGetter& gv) {
    if (!param) return std::nullopt;
    return gv(param->name);
}

// -----------------------------------------------------------------------
// Individual checks — mirror Python _check_* methods
// -----------------------------------------------------------------------

void check_ego_type(const std::vector<Page>& pages, ValueGetter& gv,
                    std::vector<ChecklistItem>& out) {
    auto* param = find_any(pages, {"egotype", "afrsensortype", "o2sensortype", "lambdatype"});
    if (!param) return;
    auto val = numeric(param, gv);
    if (!val) {
        out.push_back({"ego_type_configured", "Set O2/EGO sensor type", Status::NEEDED,
            "Select the O2 sensor type (Narrow Band, Wide Band, or Disabled).", param->name});
        return;
    }
    int ego = static_cast<int>(*val);
    if (ego == 0) {
        out.push_back({"ego_type_configured", "O2 sensor disabled", Status::INFO,
            "EGO/O2 sensor is disabled. Enable it for closed-loop fueling or wideband logging.",
            param->name});
        return;
    }
    std::string label;
    if (!param->options.empty() && ego >= 0 && ego < static_cast<int>(param->options.size()))
        label = param->options[ego];
    else if (ego == 1) label = "Narrow Band";
    else if (ego == 2) label = "Wide Band";
    else { char b[16]; std::snprintf(b, sizeof(b), "type %d", ego); label = b; }
    char detail[128];
    std::snprintf(detail, sizeof(detail), "O2 sensor configured as %s.", label.c_str());
    out.push_back({"ego_type_configured", "O2/EGO type set", Status::OK, detail, param->name});
}

void check_wideband_cal(const std::vector<Page>& pages, ValueGetter& gv,
                        std::vector<ChecklistItem>& out) {
    auto* ego_param = find_any(pages, {"egotype", "afrsensortype", "o2sensortype", "lambdatype"});
    auto ego_val = numeric(ego_param, gv);
    if (!ego_val || static_cast<int>(*ego_val) != 2) return;

    auto* cal = find_any(pages, {"afrcal", "wbcal", "widebandcal", "lambdacal"});
    if (!cal) {
        out.push_back({"wideband_cal", "Wideband calibration parameter not found", Status::WARNING,
            "Wide band EGO is selected but no calibration parameter was found on these pages. "
            "Verify the calibration table is set on the sensor page.", ""});
        return;
    }
    auto cv = numeric(cal, gv);
    if (!cv || *cv == 0) {
        out.push_back({"wideband_cal", "Set wideband calibration", Status::NEEDED,
            "Wide band EGO is selected but the calibration value is zero or missing. "
            "Match the calibration to your wideband sensor model.", cal->name});
        return;
    }
    char detail[128];
    std::snprintf(detail, sizeof(detail), "Wideband calibration is set (value: %.0f).", *cv);
    out.push_back({"wideband_cal", "Wideband calibration set", Status::OK, detail, cal->name});
}

void check_stoich(const std::vector<Page>& pages, ValueGetter& gv,
                  std::vector<ChecklistItem>& out) {
    auto* param = find_any(pages, {"stoich"});
    if (!param) return;
    auto val = numeric(param, gv);
    if (!val) return;
    double v = *val;
    if (v < 6.0 || v > 22.0) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Stoich AFR is %.1f:1. Expected range: ~6.5 (methanol) to 22 (hydrogen). "
            "Petrol \xe2\x89\x88 14.7, E85 \xe2\x89\x88 9.8.", v);
        out.push_back({"stoich_plausible", "Stoich AFR looks incorrect", Status::WARNING, d, param->name});
        return;
    }
    const char* fuel;
    if (v >= 14.0 && v <= 15.2) fuel = "petrol";
    else if (v >= 9.0 && v <= 10.5) fuel = "E85";
    else if (v <= 7.0) fuel = "methanol";
    else fuel = "fuel";
    char d[128];
    std::snprintf(d, sizeof(d), "Stoich AFR is %.1f:1 (%s).", v, fuel);
    out.push_back({"stoich_plausible", "Stoich AFR plausible", Status::OK, d, param->name});
}

void check_flex(const std::vector<Page>& pages, ValueGetter& gv,
                std::vector<ChecklistItem>& out) {
    auto* en = find_any(pages, {"flexenabled", "flexsensor", "ethanolsensor"});
    if (!en) return;
    auto ev = numeric(en, gv);
    if (!ev || *ev <= 0) return;

    auto* lo = find_any(pages, {"flexfreqlow", "ethanolfreqlow"});
    auto* hi = find_any(pages, {"flexfreqhigh", "ethanolfreqhigh"});
    if (!lo || !hi) {
        out.push_back({"flex_calibration", "Verify flex sensor calibration", Status::WARNING,
            "Flex fuel is enabled but the low/high ethanol frequency calibration is not exposed on these pages.",
            en->name});
        return;
    }
    auto lv = numeric(lo, gv), hv = numeric(hi, gv);
    if (!lv || !hv) {
        out.push_back({"flex_calibration", "Set flex sensor frequency calibration", Status::NEEDED,
            "Flex fuel is enabled but the low or high frequency value is missing.", lo->name});
        return;
    }
    if (*hv <= *lv) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Flex sensor high frequency (%.0f Hz) must be greater than low frequency (%.0f Hz).", *hv, *lv);
        out.push_back({"flex_calibration", "Flex sensor calibration invalid", Status::ERROR, d, lo->name});
        return;
    }
    if (*lv < 10.0 || *hv > 250.0) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Flex sensor frequency span is %.0f\xe2\x80\x93%.0f Hz. Standard GM/Continental sensors are typically 50\xe2\x80\x93" "150 Hz.", *lv, *hv);
        out.push_back({"flex_calibration", "Review flex sensor calibration", Status::WARNING, d, lo->name});
        return;
    }
    char d[128];
    std::snprintf(d, sizeof(d), "Flex sensor frequency span is %.0f\xe2\x80\x93%.0f Hz.", *lv, *hv);
    out.push_back({"flex_calibration", "Flex sensor calibration OK", Status::OK, d, lo->name});
}

void check_tps(const std::vector<Page>& pages, ValueGetter& gv,
               std::vector<ChecklistItem>& out) {
    auto* mn = find_any(pages, {"tpsmin", "tps_min", "throttlemin"});
    auto* mx = find_any(pages, {"tpsmax", "tps_max", "throttlemax"});
    if (!mn || !mx) return;
    auto a = numeric(mn, gv), b = numeric(mx, gv);
    if (!a || !b) return;
    double spread = *b - *a;
    if (spread < 0) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "TPS max (%.0f) is less than TPS min (%.0f). "
            "Closed throttle should be the lower ADC count \xe2\x80\x94 swap the values.", *b, *a);
        out.push_back({"tps_range", "TPS calibration inverted", Status::ERROR, d, mn->name});
    } else if (spread < 50) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "TPS span is only %.0f ADC counts (min=%.0f, max=%.0f). "
            "Most sensors span 500+ counts; a narrow range reduces pedal resolution.", spread, *a, *b);
        out.push_back({"tps_range", "TPS calibration range too narrow", Status::WARNING, d, mn->name});
    } else {
        char d[128];
        std::snprintf(d, sizeof(d), "TPS span is %.0f ADC counts (min=%.0f, max=%.0f).", spread, *a, *b);
        out.push_back({"tps_range", "TPS calibration range OK", Status::OK, d, mn->name});
    }
}

void check_map(const std::vector<Page>& pages, ValueGetter& gv,
               std::vector<ChecklistItem>& out) {
    auto* mn = find_any(pages, {"mapmin", "map_min"});
    auto* mx = find_any(pages, {"mapmax", "map_max"});
    if (!mn || !mx) return;
    auto a = numeric(mn, gv), b = numeric(mx, gv);
    if (!a || !b) return;
    double spread = *b - *a;
    if (spread <= 0) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "MAP max (%.0f kPa) must be greater than MAP min (%.0f kPa). "
            "Correct the values to match your sensor's output voltage range.", *b, *a);
        out.push_back({"map_range", "MAP calibration range invalid", Status::ERROR, d, mn->name});
    } else if (spread < 50) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "MAP range is only %.0f kPa (%.0f\xe2\x80\x93%.0f). "
            "A 100\xe2\x80\x93""300 kPa range is typical for NA; boost applications need higher max kPa.", spread, *a, *b);
        out.push_back({"map_range", "MAP calibration range looks narrow", Status::WARNING, d, mn->name});
    } else {
        char d[128];
        std::snprintf(d, sizeof(d), "MAP sensor calibrated %.0f\xe2\x80\x93%.0f kPa (%.0f kPa span).", *a, *b, spread);
        out.push_back({"map_range", "MAP calibration range OK", Status::OK, d, mn->name});
    }
}

void check_knock(const std::vector<Page>& pages, ValueGetter& gv,
                 OptionLabelGetter& olg, std::vector<ChecklistItem>& out) {
    auto* mode = find_any(pages, {"knock_mode", "knockmode", "knocksensormode"});
    if (!mode) return;
    auto mv = numeric(mode, gv);
    if (!mv || static_cast<int>(*mv) == 0) return;
    int m = static_cast<int>(*mv);
    const char* mode_label = (m == 1) ? "Digital" : "Analog";
    KW pin_kw = (m == 1)
        ? KW{"knock_digital_pin", "knockdigitalpin", "knockpindigital"}
        : KW{"knock_analog_pin", "knockanalogpin", "knockpinanalog"};

    auto* pin = find_any(pages, pin_kw);
    if (!pin) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Knock mode is %s but the pin parameter is not on these pages. "
            "Verify the pin assignment on the Hardware Setup ignition page.", mode_label);
        out.push_back({"knock_pin_sensor", "Knock pin parameter not visible", Status::WARNING, d, mode->name});
        return;
    }
    std::string label = olg(*pin);
    std::string upper_label = to_lower(label);  // reuse to_lower, then check
    // Python checks: INVALID, NONE, DISABLED, ""
    if (label.empty() || upper_label == "invalid" || upper_label == "none" || upper_label == "disabled") {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Knock mode is %s but no input pin is assigned. "
            "Select the pin the knock sensor is wired to.", mode_label);
        out.push_back({"knock_pin_sensor", "Assign knock sensor input pin", Status::NEEDED, d, pin->name});
        return;
    }
    auto pv = numeric(pin, gv);
    std::string display = !label.empty() ? label : (pv ? std::to_string(static_cast<int>(*pv)) : "?");
    char d[128];
    std::snprintf(d, sizeof(d), "Knock sensor (%s) assigned to pin %s.", mode_label, display.c_str());
    out.push_back({"knock_pin_sensor", "Knock sensor pin assigned", Status::OK, d, pin->name});
}

void check_oil(const std::vector<Page>& pages, ValueGetter& gv,
               std::vector<ChecklistItem>& out) {
    auto* en = find_any(pages, {"oilpressureenable", "oilpressureenabled", "useoilpressure"});
    if (!en) return;
    auto ev = numeric(en, gv);
    if (!ev || static_cast<int>(*ev) == 0) return;

    auto* mn = find_any(pages, {"oilpressuremin", "oilpressure_min"});
    auto* mx = find_any(pages, {"oilpressuremax", "oilpressure_max"});
    auto a = numeric(mn, gv), b = numeric(mx, gv);
    if (!a || !b) {
        out.push_back({"oil_calibration", "Oil pressure calibration incomplete", Status::NEEDED,
            "Oil pressure sensor is enabled but min/max calibration values are missing.", en->name});
        return;
    }
    if (*b <= *a) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Oil pressure max (%.1f bar) must be greater than min (%.1f bar). "
            "Check sensor voltage range against the physical pressure range.", *b, *a);
        out.push_back({"oil_calibration", "Oil pressure calibration range invalid", Status::ERROR, d,
            mn ? mn->name : ""});
        return;
    }
    char d[128];
    std::snprintf(d, sizeof(d), "Oil pressure sensor calibrated %.1f\xe2\x80\x93%.1f bar.", *a, *b);
    out.push_back({"oil_calibration", "Oil pressure calibration OK", Status::OK, d, en->name});
}

void check_baro(const std::vector<Page>& pages, ValueGetter& gv,
                std::vector<ChecklistItem>& out) {
    auto* en = find_any(pages, {"useextbaro", "extbaroenable", "useexternalbaro", "barosensorenable"});
    if (!en) return;
    auto ev = numeric(en, gv);
    if (!ev || static_cast<int>(*ev) == 0) return;

    auto* mn = find_any(pages, {"baromin", "baro_min", "extbaromin"});
    auto* mx = find_any(pages, {"baromax", "baro_max", "extbaromax"});
    auto a = numeric(mn, gv), b = numeric(mx, gv);
    if (!a || !b) {
        out.push_back({"baro_calibration", "Baro sensor calibration incomplete", Status::NEEDED,
            "External barometric sensor is enabled but min/max calibration values are missing.", en->name});
        return;
    }
    if (*b <= *a) {
        char d[200];
        std::snprintf(d, sizeof(d),
            "Baro max (%.0f kPa) must be greater than min (%.0f kPa).", *b, *a);
        out.push_back({"baro_calibration", "Baro sensor calibration range invalid", Status::ERROR, d,
            mn ? mn->name : ""});
        return;
    }
    char d[128];
    std::snprintf(d, sizeof(d), "External baro sensor calibrated %.0f\xe2\x80\x93%.0f kPa.", *a, *b);
    out.push_back({"baro_calibration", "Baro sensor calibration OK", Status::OK, d, en->name});
}

}  // namespace

// -----------------------------------------------------------------------
// validate()
// -----------------------------------------------------------------------

std::vector<ChecklistItem> validate(
    const std::vector<Page>& pages,
    ValueGetter get_value,
    OptionLabelGetter get_option_label)
{
    std::vector<ChecklistItem> items;
    check_ego_type(pages, get_value, items);
    check_wideband_cal(pages, get_value, items);
    check_stoich(pages, get_value, items);
    check_flex(pages, get_value, items);
    check_tps(pages, get_value, items);
    check_map(pages, get_value, items);
    check_knock(pages, get_value, get_option_label, items);
    check_oil(pages, get_value, items);
    check_baro(pages, get_value, items);
    return items;
}

}  // namespace tuner_core::sensor_setup_checklist
