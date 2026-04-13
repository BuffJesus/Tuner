// SPDX-License-Identifier: MIT
#include "tuner_core/ignition_trigger_cross_validation.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <map>
#include <set>
#include <string>

namespace tuner_core::ignition_trigger_cross_validation {

// -----------------------------------------------------------------------
// Pattern tables (from Speeduino INI TrigPattern bits definition)
// -----------------------------------------------------------------------

namespace {

const std::map<int, std::string> PATTERN_NAMES = {
    {0, "Missing Tooth"}, {1, "Basic Distributor"}, {2, "Dual Wheel"},
    {3, "GM 7X"}, {4, "4G63"}, {5, "GM 24X"}, {6, "Jeep 2000"},
    {7, "Audi 135"}, {8, "Honda D17"}, {9, "Miata 99-05"},
    {16, "36-2-2-2"}, {17, "36-2-1"}, {25, "Rover MEMS"},
};

const std::map<int, std::string> SEC_NAMES = {
    {0, "Single tooth cam"}, {1, "4-1 cam"}, {2, "Poll level"},
    {3, "Rover 5-3-2 cam"}, {4, "Toyota 3 Tooth"},
};

const std::set<int> CAM_CONFIGURABLE = {0, 25};
const std::set<int> CAM_INHERENT = {2,4,8,9,11,12,13,14,18,19,20,21,22,24,26,27};
const std::set<int> CRANK_ONLY = {3,5,6,7,10,15,16,17,23};

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

using KW = std::vector<std::string>;

const Parameter* find_in(const Page* page, const KW& kw) {
    if (!page) return nullptr;
    for (const auto& p : page->parameters) {
        std::string h = to_lower(p.name + " " + p.label);
        for (const auto& k : kw) if (h.find(k) != std::string::npos) return &p;
    }
    return nullptr;
}

const Parameter* find_cross(const Page* primary, const Page* secondary, const KW& kw) {
    auto* r = find_in(primary, kw);
    return r ? r : find_in(secondary, kw);
}

std::optional<double> num(const Parameter* p, ValueGetter& gv) {
    return p ? gv(p->name) : std::nullopt;
}

// -----------------------------------------------------------------------
// Individual checks
// -----------------------------------------------------------------------

void check_dwell(const Page* ign, const Page* trig, ValueGetter& gv, std::vector<ChecklistItem>& out) {
    auto* p = find_cross(ign, trig, {"dwell", "sparkdur"});
    if (!p) { out.push_back({"dwell_configured", "Set dwell time", Status::NEEDED,
        "No dwell parameter found on the ignition or trigger page.", ""}); return; }
    auto v = num(p, gv);
    if (!v) { char d[128]; std::snprintf(d, sizeof(d), "Dwell parameter '%s' has no value.", p->name.c_str());
        out.push_back({"dwell_configured", "Set dwell time", Status::NEEDED, d, p->name}); return; }
    if (*v == 0) { out.push_back({"dwell_configured", "Set dwell time", Status::ERROR,
        "Dwell is zero \xe2\x80\x94 coils will not charge and the engine will not fire.", p->name}); return; }
    if (*v > 10) { char d[128]; std::snprintf(d, sizeof(d), "Dwell is %.1f ms \xe2\x80\x94 above safe maximum (10 ms).", *v);
        out.push_back({"dwell_configured", "Check dwell time", Status::ERROR, d, p->name}); return; }
    if (*v < 1 || *v > 6) { char d[128]; std::snprintf(d, sizeof(d), "Dwell is %.1f ms \xe2\x80\x94 outside typical 1\xe2\x80\x93""6 ms range.", *v);
        out.push_back({"dwell_configured", "Check dwell time", Status::WARNING, d, p->name}); return; }
    char d[64]; std::snprintf(d, sizeof(d), "Dwell is %.1f ms.", *v);
    out.push_back({"dwell_configured", "Dwell configured", Status::OK, d, p->name});
}

void check_ref_angle(const Page* ign, const Page* trig, ValueGetter& gv, std::vector<ChecklistItem>& out) {
    KW kw = {"triggerangle", "fixang", "crankangle", "tdcangle"};
    auto* p = find_cross(trig, ign, kw);
    if (!p) { out.push_back({"reference_angle", "Set reference (TDC) angle", Status::NEEDED,
        "No trigger reference angle found.", ""}); return; }
    auto v = num(p, gv);
    if (!v) { out.push_back({"reference_angle", "Set reference (TDC) angle", Status::NEEDED,
        "Reference angle has no value.", p->name}); return; }
    if (*v == 0) { out.push_back({"reference_angle", "Verify reference angle", Status::WARNING,
        "Reference angle is 0\xc2\xb0. Confirm with a timing light.", p->name}); return; }
    if (*v > 50) { char d[128]; std::snprintf(d, sizeof(d), "Reference angle is %.0f\xc2\xb0 \xe2\x80\x94 unusually large.", *v);
        out.push_back({"reference_angle", "Check reference angle", Status::WARNING, d, p->name}); return; }
    char d[128]; std::snprintf(d, sizeof(d), "Reference angle is %.0f\xc2\xb0.", *v);
    out.push_back({"reference_angle", "Reference angle configured", Status::OK, d, p->name});
}

void check_geometry(const Page* trig, ValueGetter& gv, std::vector<ChecklistItem>& out) {
    if (!trig) return;
    auto* tp = find_in(trig, {"nteeth", "toothcount", "triggerteeth", "crankteeth", "numteeth"});
    auto* mp = find_in(trig, {"missingteeth", "missingtooth"});
    if (!tp || !mp) return;
    auto teeth = num(tp, gv), missing = num(mp, gv);
    if (!teeth || !missing) { out.push_back({"trigger_geometry", "Set trigger wheel tooth count", Status::NEEDED,
        "Tooth count or missing-tooth count has no value.", tp->name}); return; }
    if (*missing >= *teeth) { char d[128]; std::snprintf(d, sizeof(d),
        "Missing teeth (%.0f) must be less than total (%.0f).", *missing, *teeth);
        out.push_back({"trigger_geometry", "Fix trigger geometry", Status::ERROR, d, mp->name}); return; }
    if (*teeth > 0 && *missing >= *teeth / 2) { char d[128]; std::snprintf(d, sizeof(d),
        "Missing teeth (%.0f) is more than half of total (%.0f).", *missing, *teeth);
        out.push_back({"trigger_geometry", "Verify trigger geometry", Status::WARNING, d, mp->name}); return; }
    char d[64]; std::snprintf(d, sizeof(d), "Wheel: %d-%d.", static_cast<int>(*teeth), static_cast<int>(*missing));
    out.push_back({"trigger_geometry", "Trigger geometry set", Status::OK, d, tp->name});
}

void check_sequential(const Page* ign, const Page* trig, ValueGetter& gv, std::vector<ChecklistItem>& out) {
    auto* pat_p = find_cross(trig, ign, {"trigpattern", "trig_pattern"});
    auto pat = num(pat_p, gv);
    if (!pat) return;
    int pidx = static_cast<int>(*pat);

    auto spark_mode = num(find_cross(ign, trig, {"sparkmode", "spark_mode"}), gv);
    auto inj_layout = num(find_cross(ign, trig, {"injlayout", "inj_layout"}), gv);
    bool seq_ign = spark_mode && static_cast<int>(*spark_mode) == 3;
    bool seq_inj = inj_layout && static_cast<int>(*inj_layout) == 3;
    if (!seq_ign && !seq_inj) return;

    std::string mode;
    if (seq_ign && seq_inj) mode = "Sequential ignition and injection";
    else if (seq_ign) mode = "Sequential ignition";
    else mode = "Sequential injection";

    if (CRANK_ONLY.count(pidx)) {
        auto it = PATTERN_NAMES.find(pidx);
        std::string name = it != PATTERN_NAMES.end() ? it->second : "pattern " + std::to_string(pidx);
        char d[256]; std::snprintf(d, sizeof(d),
            "%s is selected but the %s decoder is crank-only. "
            "Sequential requires cam sync.", mode.c_str(), name.c_str());
        out.push_back({"sequential_cam_sync", "Cam sync required", Status::WARNING, d, pat_p ? pat_p->name : ""});
        return;
    }
    if (CAM_CONFIGURABLE.count(pidx)) {
        auto trig_speed = num(find_cross(trig, ign, {"trigspeed", "trig_speed"}), gv);
        if (trig_speed && static_cast<int>(*trig_speed) == 1) return; // cam speed
        auto* sec_p = find_in(trig, {"trigpatternsec", "trig_pattern_sec"});
        auto sec = num(sec_p, gv);
        if (!sec) {
            char d[256]; std::snprintf(d, sizeof(d),
                "%s with crank-speed Missing Tooth. Verify cam trigger (trigPatternSec) is configured.", mode.c_str());
            out.push_back({"sequential_cam_sync", "Verify cam sync", Status::WARNING, d, pat_p ? pat_p->name : ""});
            return;
        }
        auto sit = SEC_NAMES.find(static_cast<int>(*sec));
        std::string sn = sit != SEC_NAMES.end() ? sit->second : "type " + std::to_string(static_cast<int>(*sec));
        char d[256]; std::snprintf(d, sizeof(d),
            "%s with Missing Tooth crank. Secondary: %s.", mode.c_str(), sn.c_str());
        out.push_back({"sequential_cam_sync", "Cam sync configured", Status::OK, d, sec_p ? sec_p->name : ""});
    }
}

void trigger_topology(const Page* ign, const Page* trig, ValueGetter& gv, std::vector<ChecklistItem>& out) {
    auto* pat_p = find_cross(trig, ign, {"trigpattern", "trig_pattern"});
    auto pat = num(pat_p, gv);
    if (!pat) return;
    int pidx = static_cast<int>(*pat);
    auto it = PATTERN_NAMES.find(pidx);
    std::string name = it != PATTERN_NAMES.end() ? it->second : "Pattern " + std::to_string(pidx);

    auto teeth = num(find_in(trig, {"nteeth", "numteeth", "triggerteeth", "crankteeth"}), gv);
    auto missing = num(find_in(trig, {"missingteeth", "missingtooth"}), gv);
    if (pidx == 0 && teeth && missing) {
        char buf[64]; std::snprintf(buf, sizeof(buf), "Missing Tooth (%d-%d)",
            static_cast<int>(*teeth), static_cast<int>(*missing));
        name = buf;
    }
    std::string suffix;
    if (CAM_INHERENT.count(pidx)) suffix = " (cam sync inherent)";
    else if (CAM_CONFIGURABLE.count(pidx)) {
        auto sec = num(find_in(trig, {"trigpatternsec", "trig_pattern_sec"}), gv);
        if (sec) {
            auto sit = SEC_NAMES.find(static_cast<int>(*sec));
            suffix = " with " + (sit != SEC_NAMES.end() ? sit->second : "secondary " + std::to_string(static_cast<int>(*sec)));
        }
    }
    out.push_back({"trigger_topology", "Trigger topology", Status::INFO,
        name + suffix, pat_p ? pat_p->name : ""});
}

}  // namespace

// -----------------------------------------------------------------------
// validate()
// -----------------------------------------------------------------------

std::vector<ChecklistItem> validate(
    const Page* ignition_page,
    const Page* trigger_page,
    ValueGetter get_value,
    OptionLabelGetter get_option_label)
{
    (void)get_option_label;  // used by knock pin in full Python version; simplified here
    std::vector<ChecklistItem> items;
    check_dwell(ignition_page, trigger_page, get_value, items);
    check_ref_angle(ignition_page, trigger_page, get_value, items);
    check_geometry(trigger_page, get_value, items);
    check_sequential(ignition_page, trigger_page, get_value, items);
    trigger_topology(ignition_page, trigger_page, get_value, items);
    return items;
}

}  // namespace tuner_core::ignition_trigger_cross_validation
