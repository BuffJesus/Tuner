// SPDX-License-Identifier: MIT
#include "tuner_core/trigger_log_analysis.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <map>
#include <set>
#include <string>

namespace tuner_core::trigger_log_analysis {

// -----------------------------------------------------------------------
// Pattern tables
// -----------------------------------------------------------------------

namespace {

const std::map<int, std::string> PATTERN_NAMES = {
    {0, "Missing Tooth"}, {1, "Basic Distributor"}, {2, "Dual Wheel"},
    {3, "GM 7X"}, {4, "4G63 / Miata / 3000GT"}, {5, "GM 24X"},
    {6, "Jeep 2000"}, {7, "Audi 135"}, {8, "Honda D17"},
    {9, "Miata 99-05"}, {10, "Mazda AU"}, {11, "Non-360 Dual"},
    {12, "Nissan 360"}, {13, "Subaru 6/7"}, {14, "Daihatsu +1"},
    {15, "Harley EVO"}, {16, "36-2-2-2"}, {17, "36-2-1"},
    {18, "DSM 420a"}, {19, "Weber-Marelli"}, {20, "Ford ST170"},
    {21, "DRZ400"}, {22, "Chrysler NGC"}, {23, "Yamaha Vmax 1990+"},
    {24, "Renix"}, {25, "Rover MEMS"}, {26, "K6A"}, {27, "Honda J32"},
};

const std::map<int, std::string> SEC_TRIGGER_NAMES = {
    {0, "Single tooth cam"}, {1, "4-1 cam"}, {2, "Poll level (cam level sensor)"},
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

std::string strip(const std::string& s) {
    auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return {};
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}

std::string detect_log_kind(const std::vector<std::string>& cols) {
    std::string haystack;
    for (const auto& c : cols) haystack += to_lower(c) + " ";
    if (haystack.find("composite") != std::string::npos) return "composite";
    if (haystack.find("tooth") != std::string::npos) return "tooth";
    if (haystack.find("trigger") != std::string::npos || haystack.find("cam") != std::string::npos
        || haystack.find("crank") != std::string::npos) return "trigger";
    return "unknown";
}

std::string find_time_column(const std::vector<std::string>& cols) {
    for (const auto& c : cols) {
        std::string low = to_lower(strip(c));
        if (low == "time" || low == "timems" || low == "timestamp" ||
            low == "time_ms" || low == "time (ms)" || low.find("time") != std::string::npos)
            return strip(c);
    }
    return {};
}

std::vector<double> extract_time_series(const std::vector<Row>& rows, const std::string& col) {
    std::vector<double> s;
    for (const auto& row : rows) {
        std::string raw = strip(row.get(col));
        if (raw.empty()) continue;
        try { size_t p; double v = std::stod(raw, &p); if (p == raw.size()) s.push_back(v); else continue; }
        catch (...) { continue; }
    }
    return s;
}

std::optional<double> gap_ratio(const std::vector<double>& ts) {
    if (ts.size() < 6) return std::nullopt;
    std::vector<double> deltas;
    for (size_t i = 1; i < ts.size(); ++i)
        if (ts[i] > ts[i-1]) deltas.push_back(ts[i] - ts[i-1]);
    if (deltas.size() < 4) return std::nullopt;
    auto sorted = deltas;
    std::sort(sorted.begin(), sorted.end());
    double median = sorted[sorted.size() / 2];
    if (median <= 0) return std::nullopt;
    double mx = *std::max_element(deltas.begin(), deltas.end());
    double r = mx / median;
    return (r >= 1.6) ? std::optional(r) : std::nullopt;
}

std::vector<double> numeric_signal(const std::vector<Row>& rows, const std::string& col) {
    std::vector<double> v;
    for (const auto& row : rows) {
        std::string raw = strip(row.get(col));
        if (raw.empty()) return {};
        try { size_t p; double d = std::stod(raw, &p); if (p == raw.size()) v.push_back(d); else return {}; }
        catch (...) { return {}; }
    }
    return v;
}

int edge_count(const std::vector<double>& v) {
    int n = 0;
    for (size_t i = 1; i < v.size(); ++i) if (v[i] != v[i-1]) ++n;
    return n;
}

std::string find_signal_column(const std::vector<std::string>& cols,
                                std::initializer_list<const char*> tokens) {
    for (const auto& c : cols) {
        std::string low = to_lower(c);
        for (const char* t : tokens) if (low.find(t) != std::string::npos) return c;
    }
    return {};
}

std::string preview_text(const std::vector<Row>& rows, const std::vector<std::string>& cols) {
    if (rows.empty() || cols.empty()) return "No preview available.";
    std::string out;
    for (size_t i = 0; i < cols.size(); ++i) { if (i) out += ", "; out += cols[i]; }
    int lim = std::min(static_cast<int>(rows.size()), 8);
    for (int i = 0; i < lim; ++i) {
        out += "\n";
        for (size_t j = 0; j < cols.size(); ++j) {
            if (j) out += ", ";
            out += strip(rows[i].get(cols[j]));
        }
    }
    if (rows.size() > 8) out += "\n...";
    return out;
}

}  // namespace

// -----------------------------------------------------------------------
// build_decoder_context
// -----------------------------------------------------------------------

DecoderContext build_decoder_context(
    TuneValueGetter get_value,
    std::optional<double> runtime_status_a,
    std::optional<double> rsa_full_sync)
{
    auto gv = [&](const std::string& name) { return get_value(name); };
    auto first_of = [&](std::initializer_list<const char*> names) -> std::optional<double> {
        for (const char* n : names) { auto v = gv(n); if (v) return v; }
        return std::nullopt;
    };

    int pattern = static_cast<int>(first_of({"TrigPattern", "triggertype", "decoder", "pattern"}).value_or(0));
    auto tooth_count = first_of({"nTeeth", "numTeeth", "toothCount", "triggerTeeth", "crankTeeth"});
    auto missing_teeth = first_of({"missingTeeth", "missingTooth"});
    auto spark_mode = first_of({"sparkMode"});
    auto inj_layout = first_of({"injLayout"});
    auto trig_sec = first_of({"trigPatternSec"});
    auto cam_input = first_of({"camInput"});

    bool seq_req = (spark_mode && *spark_mode == 3.0) || (inj_layout && *inj_layout == 3.0);
    std::string cam_mode;
    if (CAM_INHERENT.count(pattern)) cam_mode = "cam_present";
    else if (CAM_CONFIGURABLE.count(pattern))
        cam_mode = ((trig_sec && *trig_sec >= 0) || (cam_input && *cam_input > 0)) ? "cam_present" : "cam_optional";
    else if (CRANK_ONLY.count(pattern)) cam_mode = "crank_only";
    else cam_mode = "unknown";

    std::string wheel;
    if (tooth_count) {
        if (missing_teeth && *missing_teeth > 0)
            wheel = std::to_string(static_cast<int>(std::round(*tooth_count))) + "-" +
                    std::to_string(static_cast<int>(std::round(*missing_teeth)));
        else
            wheel = std::to_string(static_cast<int>(std::round(*tooth_count))) + "-tooth";
    }
    if (trig_sec && *trig_sec >= 0) {
        int sec = static_cast<int>(std::round(*trig_sec));
        auto it = SEC_TRIGGER_NAMES.find(sec);
        if (!wheel.empty()) wheel += ", ";
        wheel += (it != SEC_TRIGGER_NAMES.end()) ? it->second : "secondary trigger configured";
    }
    if (wheel.empty()) wheel = "wheel geometry not loaded";

    std::optional<bool> full_sync;
    if (runtime_status_a) full_sync = (static_cast<int>(std::round(*runtime_status_a)) & (1 << 4)) != 0;
    else if (rsa_full_sync) full_sync = *rsa_full_sync >= 0.5;

    auto pit = PATTERN_NAMES.find(pattern);
    std::string pname = (pit != PATTERN_NAMES.end()) ? pit->second :
        "pattern " + std::to_string(pattern);

    return {pname, wheel, seq_req, cam_mode, full_sync, tooth_count, missing_teeth};
}

// -----------------------------------------------------------------------
// analyze_rows
// -----------------------------------------------------------------------

AnalysisSummary analyze_rows(
    const std::vector<Row>& rows,
    const std::vector<std::string>& columns,
    const DecoderContext& decoder)
{
    std::vector<std::string> norm_cols;
    for (const auto& c : columns) { auto s = strip(c); if (!s.empty()) norm_cols.push_back(s); }

    std::string log_kind = detect_log_kind(norm_cols);
    std::vector<std::string> findings;
    std::string severity = "info";

    std::string time_col = find_time_column(norm_cols);
    std::optional<double> time_span_ms;
    std::vector<double> time_series;

    if (rows.empty()) {
        findings.push_back("The log is empty. Capture a fresh tooth, composite, or trigger log before diagnosing sync issues.");
        severity = "warning";
    }
    if (rows.size() < 20 && !rows.empty()) {
        findings.push_back("The capture is very short. Record a longer log so sync loss and missing-tooth gaps are visible.");
        severity = "warning";
    }

    if (time_col.empty()) {
        findings.push_back("No usable time column was found. Import a CSV that includes timestamp, timeMs, or similar timing data.");
        severity = "warning";
    } else {
        time_series = extract_time_series(rows, time_col);
        if (time_series.size() >= 2)
            time_span_ms = std::max(0.0, time_series.back() - time_series.front());
        else
            time_span_ms = 0.0;

        // Check monotonicity.
        for (size_t i = 1; i < time_series.size(); ++i) {
            if (time_series[i] <= time_series[i-1]) {
                findings.push_back("Timestamps are not strictly increasing. The capture may be truncated or exported incorrectly.");
                severity = "warning";
                break;
            }
        }

        // Missing-tooth gap analysis.
        if (decoder.decoder_name == "Missing Tooth") {
            auto gr = gap_ratio(time_series);
            if (!gr) {
                findings.push_back("The current log does not show a clear missing-tooth gap. Recheck the wheel pattern, sensor polarity, and logger capture window.");
                severity = "warning";
            } else {
                std::optional<double> expected;
                if (decoder.missing_teeth && *decoder.missing_teeth > 0)
                    expected = *decoder.missing_teeth + 1.0;
                if (expected && std::abs(*gr - *expected) <= 0.4) {
                    char buf[256];
                    std::snprintf(buf, sizeof(buf),
                        "Detected missing-tooth gap looks plausible for the loaded wheel: observed %.2fx normal tooth spacing versus expected %.2fx.",
                        *gr, *expected);
                    findings.push_back(buf);
                } else if (expected) {
                    char buf[256];
                    std::snprintf(buf, sizeof(buf),
                        "Detected missing-tooth gap does not match the loaded wheel well: observed %.2fx normal tooth spacing versus expected %.2fx. Recheck wheel geometry and capture scaling.",
                        *gr, *expected);
                    findings.push_back(buf);
                    severity = "warning";
                } else {
                    char buf[128];
                    std::snprintf(buf, sizeof(buf),
                        "Detected missing-tooth gap is about %.2fx the normal tooth spacing.", *gr);
                    findings.push_back(buf);
                }
            }
        }
    }

    // Sequential + cam sync checks.
    if (decoder.sequential_requested && decoder.cam_mode == "crank_only") {
        findings.push_back("Sequential fuel or ignition is requested, but the loaded decoder context is crank-only. Full sync will not be stable without a decoder/cam change.");
        severity = "warning";
    } else if (decoder.sequential_requested && decoder.cam_mode == "cam_optional" && log_kind == "tooth") {
        findings.push_back("Sequential operation depends on cam sync here. A tooth log may miss phase errors; import a composite or trigger log if sync remains unstable.");
    } else if (decoder.sequential_requested && decoder.cam_mode == "cam_present" && log_kind == "tooth") {
        findings.push_back("A tooth log is useful for gap sanity checks, but a composite or trigger log will be better for verifying crank/cam phase alignment.");
    } else if ((log_kind == "composite" || log_kind == "trigger") &&
               (decoder.cam_mode == "cam_present" || decoder.cam_mode == "cam_optional")) {
        // Phase plausibility check.
        auto crank_col = find_signal_column(norm_cols, {"crank", "trigger1", "primary", "composite1"});
        auto cam_col = find_signal_column(norm_cols, {"cam", "trigger2", "secondary", "composite2", "sync"});
        if (crank_col.empty()) {
            findings.push_back("The composite/trigger log does not expose a clear crank signal column. Capture crank and cam channels together for phase troubleshooting.");
            severity = "warning";
        } else if (cam_col.empty()) {
            if (decoder.sequential_requested || decoder.cam_mode == "cam_present") {
                findings.push_back("The loaded decoder context expects crank and cam evidence, but this log does not expose a cam/secondary channel.");
                severity = "warning";
            } else {
                findings.push_back("This composite/trigger log does not expose a cam/secondary channel. That may be acceptable if you are only verifying crank sync.");
            }
        } else {
            auto cv = numeric_signal(rows, crank_col);
            auto mv = numeric_signal(rows, cam_col);
            if (cv.empty() || mv.empty()) {
                findings.push_back("Crank or cam columns could not be parsed as numeric signals. Re-export the composite/trigger log with raw signal values.");
                severity = "warning";
            } else {
                int ce = edge_count(cv), me = edge_count(mv);
                if (ce <= 0) {
                    findings.push_back("The crank channel does not show any visible transitions. Verify trigger capture settings and sensor polarity.");
                    severity = "warning";
                } else if (me <= 0) {
                    findings.push_back("The cam/secondary channel does not show any visible transitions. Verify the secondary trigger input and capture wiring.");
                    severity = "warning";
                } else {
                    double ratio = static_cast<double>(ce) / me;
                    char buf[256];
                    if (ratio >= 4.0)
                        std::snprintf(buf, sizeof(buf),
                            "Crank/cam edge density looks plausible for phase troubleshooting: %d crank edges versus %d cam edges in this capture.", ce, me);
                    else
                        std::snprintf(buf, sizeof(buf),
                            "Crank/cam edge density looks unusual: %d crank edges versus %d cam edges. Recheck the selected decoder, cam pattern, and logger scaling.", ce, me);
                    findings.push_back(buf);
                    if (ratio < 4.0) severity = "warning";
                }
            }
        }
    }

    if (decoder.full_sync.has_value() && !*decoder.full_sync) {
        findings.push_back("Live runtime telemetry currently says full sync is not present. Compare this capture against the selected decoder before trusting timing or tune-learn data.");
        severity = "warning";
    }

    if (findings.empty())
        findings.push_back("The capture looks structurally usable. Compare tooth spacing and phase transitions against the expected decoder pattern.");

    int chan_count = std::max(0, static_cast<int>(norm_cols.size()) - (!time_col.empty() ? 1 : 0));

    // Build summary texts.
    char capture_buf[256];
    if (time_span_ms)
        std::snprintf(capture_buf, sizeof(capture_buf),
            "Capture: %s log, %d row(s), %d signal column(s), %.1f ms.",
            log_kind.c_str(), static_cast<int>(rows.size()), chan_count, *time_span_ms);
    else
        std::snprintf(capture_buf, sizeof(capture_buf),
            "Capture: %s log, %d row(s), %d signal column(s), unknown span.",
            log_kind.c_str(), static_cast<int>(rows.size()), chan_count);

    const char* cam_text =
        (decoder.cam_mode == "cam_present") ? "cam sync is available in the loaded decoder context" :
        (decoder.cam_mode == "cam_optional") ? "cam sync is configurable and may still need a composite/trigger log to verify phase" :
        (decoder.cam_mode == "crank_only") ? "the loaded decoder context is crank-only" :
        "cam sync expectations are not clear from the loaded tune";
    const char* sync_text =
        (decoder.full_sync.has_value() && *decoder.full_sync) ? "full sync is currently reported" :
        (decoder.full_sync.has_value()) ? "full sync is currently not reported" :
        "runtime sync status is not available";
    char decoder_buf[512];
    std::snprintf(decoder_buf, sizeof(decoder_buf),
        "Decoder: %s. Wheel: %s. Sequential requested: %s. Context: %s; %s.",
        decoder.decoder_name.c_str(), decoder.wheel_summary.c_str(),
        decoder.sequential_requested ? "yes" : "no", cam_text, sync_text);

    AnalysisSummary result;
    result.log_kind = log_kind;
    result.severity = severity;
    result.sample_count = static_cast<int>(rows.size());
    result.channel_count = chan_count;
    result.time_span_ms = time_span_ms;
    result.columns = norm_cols;
    result.capture_summary_text = capture_buf;
    result.decoder_summary_text = decoder_buf;
    result.operator_summary_text = findings.empty() ? "" : findings[0];
    result.findings = std::move(findings);
    result.preview_text = preview_text(rows, norm_cols);
    return result;
}

}  // namespace tuner_core::trigger_log_analysis
