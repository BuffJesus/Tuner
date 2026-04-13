// SPDX-License-Identifier: MIT
//
// tuner_core::replay_sample_gate implementation. Pure logic.

#include "tuner_core/replay_sample_gate.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <map>

namespace tuner_core::replay_sample_gate {

namespace sgh = sample_gate_helpers;

namespace {

// runtimeStatusA bit layout (mirrors Python class constants).
constexpr std::uint32_t RSA_FULL_SYNC_BIT        = 1u << 4;  // 0x10
constexpr std::uint32_t RSA_TRANSIENT_ACTIVE_BIT = 1u << 5;  // 0x20
constexpr std::uint32_t RSA_WARMUP_ASE_BIT       = 1u << 6;  // 0x40
constexpr std::uint32_t RSA_TUNE_LEARN_VALID_BIT = 1u << 7;  // 0x80

std::string fmt(const char* spec, double v) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), spec, v);
    return buf;
}

std::string lower_collapse(const std::string& s) {
    std::string out;
    out.reserve(s.size());
    for (char c : s) {
        if (c == '_' || c == ' ') continue;
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

std::optional<std::uint32_t> resolve_runtime_status_a(const ValueMap& values) {
    for (const auto& [key, value] : values) {
        auto k = lower_collapse(key);
        if (k == "runtimestatusa" || k == "statusa" || k == "runtimestatus") {
            return static_cast<std::uint32_t>(static_cast<std::int64_t>(value)) & 0xFFu;
        }
    }
    return std::nullopt;
}

Eval ok(std::string name) {
    return Eval{std::move(name), true, ""};
}

Eval reject(std::string name, std::string reason) {
    return Eval{std::move(name), false, std::move(reason)};
}

// ---------------------------------------------------------------------------
// Individual gates
// ---------------------------------------------------------------------------

Eval gate_dead_lambda(const ValueMap& values, const Config& cfg) {
    auto afr = sgh::afr_value(values);
    if (!afr) {
        return reject("std_DeadLambda", "no lambda/AFR channel in record");
    }
    if (!(cfg.afr_min <= *afr && *afr <= cfg.afr_max)) {
        std::string reason = "AFR " + fmt("%.2f", *afr) + " outside plausible range ["
                           + fmt("%.1f", cfg.afr_min) + ", "
                           + fmt("%.1f", cfg.afr_max) + "]";
        return reject("std_DeadLambda", std::move(reason));
    }
    return ok("std_DeadLambda");
}

Eval gate_x_axis_min(const Config& cfg) {
    if (!cfg.axis_x_min || !cfg.axis_x_value) return ok("std_xAxisMin");
    if (*cfg.axis_x_value < *cfg.axis_x_min) {
        std::string reason = "X value " + fmt("%g", *cfg.axis_x_value)
                           + " below axis minimum " + fmt("%g", *cfg.axis_x_min);
        return reject("std_xAxisMin", std::move(reason));
    }
    return ok("std_xAxisMin");
}

Eval gate_x_axis_max(const Config& cfg) {
    if (!cfg.axis_x_max || !cfg.axis_x_value) return ok("std_xAxisMax");
    if (*cfg.axis_x_value > *cfg.axis_x_max) {
        std::string reason = "X value " + fmt("%g", *cfg.axis_x_value)
                           + " above axis maximum " + fmt("%g", *cfg.axis_x_max);
        return reject("std_xAxisMax", std::move(reason));
    }
    return ok("std_xAxisMax");
}

Eval gate_y_axis_min(const Config& cfg) {
    if (!cfg.axis_y_min || !cfg.axis_y_value) return ok("std_yAxisMin");
    if (*cfg.axis_y_value < *cfg.axis_y_min) {
        std::string reason = "Y value " + fmt("%g", *cfg.axis_y_value)
                           + " below axis minimum " + fmt("%g", *cfg.axis_y_min);
        return reject("std_yAxisMin", std::move(reason));
    }
    return ok("std_yAxisMin");
}

Eval gate_y_axis_max(const Config& cfg) {
    if (!cfg.axis_y_max || !cfg.axis_y_value) return ok("std_yAxisMax");
    if (*cfg.axis_y_value > *cfg.axis_y_max) {
        std::string reason = "Y value " + fmt("%g", *cfg.axis_y_value)
                           + " above axis maximum " + fmt("%g", *cfg.axis_y_max);
        return reject("std_yAxisMax", std::move(reason));
    }
    return ok("std_yAxisMax");
}

Eval gate_min_clt(const ValueMap& values, const Config& cfg) {
    auto clt = sgh::resolve_channel("coolant", values);
    if (!clt) return ok("minCltFilter");
    if (*clt < cfg.clt_min_celsius) {
        std::string reason = "coolant " + fmt("%.1f", *clt) + " \xc2\xb0""C below minimum "
                           + fmt("%.0f", cfg.clt_min_celsius) + " \xc2\xb0""C";
        return reject("minCltFilter", std::move(reason));
    }
    return ok("minCltFilter");
}

Eval gate_accel(const ValueMap& values) {
    auto engine = sgh::resolve_channel("engine", values);
    if (!engine) return ok("accelFilter");
    if (static_cast<std::int64_t>(*engine) & 0x10) {
        return reject("accelFilter", "accel enrichment active (engine & 16)");
    }
    return ok("accelFilter");
}

Eval gate_ase(const ValueMap& values) {
    auto engine = sgh::resolve_channel("engine", values);
    if (!engine) return ok("aseFilter");
    if (static_cast<std::int64_t>(*engine) & 0x04) {
        return reject("aseFilter", "after-start enrichment active (engine & 4)");
    }
    return ok("aseFilter");
}

Eval gate_overrun(const ValueMap& values) {
    auto pw = sgh::resolve_channel("pulsewidth", values);
    if (!pw) return ok("overrunFilter");
    if (*pw == 0.0) {
        return reject("overrunFilter", "overrun fuel cut (pulseWidth == 0)");
    }
    return ok("overrunFilter");
}

Eval gate_max_tps(const ValueMap& values, const Config& cfg) {
    auto tps = sgh::resolve_channel("throttle", values);
    if (!tps) return ok("maxTPS");
    if (*tps > cfg.tps_max_percent) {
        std::string reason = "TPS " + fmt("%.1f", *tps) + "% above maximum "
                           + fmt("%.0f", cfg.tps_max_percent) + "%";
        return reject("maxTPS", std::move(reason));
    }
    return ok("maxTPS");
}

Eval gate_min_rpm(const ValueMap& values, const Config& cfg) {
    auto rpm = sgh::resolve_channel("rpm", values);
    if (!rpm) return ok("minRPM");
    if (*rpm < cfg.rpm_min) {
        std::string reason = "RPM " + fmt("%.0f", *rpm) + " below minimum "
                           + fmt("%.0f", cfg.rpm_min);
        return reject("minRPM", std::move(reason));
    }
    return ok("minRPM");
}

Eval gate_firmware_learn(const ValueMap& values) {
    auto rsa = resolve_runtime_status_a(values);
    if (!rsa) return ok("firmwareLearnGate");
    if (!(*rsa & RSA_FULL_SYNC_BIT)) {
        return reject("firmwareLearnGate",
            "firmware reports !fullSync (runtimeStatusA bit 4 clear)");
    }
    if (*rsa & RSA_TRANSIENT_ACTIVE_BIT) {
        return reject("firmwareLearnGate",
            "firmware reports transientActive (runtimeStatusA bit 5 set)");
    }
    if (*rsa & RSA_WARMUP_ASE_BIT) {
        return reject("firmwareLearnGate",
            "firmware reports warmupOrASEActive (runtimeStatusA bit 6 set)");
    }
    if (!(*rsa & RSA_TUNE_LEARN_VALID_BIT)) {
        return reject("firmwareLearnGate",
            "firmware reports !tuneLearnValid (runtimeStatusA bit 7 clear)");
    }
    return ok("firmwareLearnGate");
}

Eval dispatch(std::string_view name, const ValueMap& values, const Config& cfg) {
    if (name == "std_DeadLambda")    return gate_dead_lambda(values, cfg);
    if (name == "std_xAxisMin")      return gate_x_axis_min(cfg);
    if (name == "std_xAxisMax")      return gate_x_axis_max(cfg);
    if (name == "std_yAxisMin")      return gate_y_axis_min(cfg);
    if (name == "std_yAxisMax")      return gate_y_axis_max(cfg);
    if (name == "minCltFilter")      return gate_min_clt(values, cfg);
    if (name == "accelFilter")       return gate_accel(values);
    if (name == "aseFilter")         return gate_ase(values);
    if (name == "overrunFilter")     return gate_overrun(values);
    if (name == "maxTPS")            return gate_max_tps(values, cfg);
    if (name == "minRPM")            return gate_min_rpm(values, cfg);
    if (name == "firmwareLearnGate") return gate_firmware_learn(values);
    return ok(std::string(name));  // unknown gate name → fail-open (skip)
}

}  // namespace

const std::vector<std::string>& default_gate_order() {
    static const std::vector<std::string> order = {
        "std_DeadLambda",
        "accelFilter",
        "aseFilter",
        "minCltFilter",
        "overrunFilter",
    };
    return order;
}

std::vector<Eval> evaluate_record(const ValueMap& record_values, const Config& config) {
    std::vector<std::string> gate_order;
    if (config.enabled_gates.empty()) {
        gate_order = default_gate_order();
    } else {
        // std::set already iterates in sorted order — same as Python
        // sorted(cfg.enabled_gates).
        gate_order.assign(config.enabled_gates.begin(), config.enabled_gates.end());
    }

    if (config.firmware_learn_gate_enabled) {
        bool present = false;
        for (const auto& g : gate_order) {
            if (g == "firmwareLearnGate") { present = true; break; }
        }
        if (!present) {
            gate_order.insert(gate_order.begin(), "firmwareLearnGate");
        }
    }

    std::vector<Eval> results;
    results.reserve(gate_order.size());
    for (const auto& name : gate_order) {
        Eval e = dispatch(name, record_values, config);
        bool rejected = !e.accepted;
        results.push_back(std::move(e));
        if (rejected) break;  // fail-fast
    }
    return results;
}

bool is_accepted(const ValueMap& record_values, const Config& config) {
    for (const auto& e : evaluate_record(record_values, config)) {
        if (!e.accepted) return false;
    }
    return true;
}

std::optional<Eval> primary_rejection(const ValueMap& record_values, const Config& config) {
    for (auto& e : evaluate_record(record_values, config)) {
        if (!e.accepted) return e;
    }
    return std::nullopt;
}

Summary gate_records(const std::vector<ValueMap>& records, const Config& config) {
    Summary out;
    out.total_count = records.size();
    std::map<std::string, std::size_t> rejection_counts;

    for (const auto& rec : records) {
        auto evals = evaluate_record(rec, config);
        const Eval* rejection = nullptr;
        for (const auto& e : evals) {
            if (!e.accepted) { rejection = &e; break; }
        }
        if (rejection == nullptr) {
            ++out.accepted_count;
        } else {
            ++out.rejected_count;
            rejection_counts[rejection->gate_name] += 1;
        }
    }

    out.rejection_counts_by_gate.assign(rejection_counts.begin(), rejection_counts.end());

    out.summary_text = "Sample gating: " + std::to_string(out.accepted_count)
                     + " accepted, " + std::to_string(out.rejected_count)
                     + " rejected of " + std::to_string(out.total_count) + " total.";
    out.detail_lines.push_back(out.summary_text);
    if (!out.rejection_counts_by_gate.empty()) {
        std::string line = "Rejections by gate: ";
        bool first = true;
        for (const auto& [gate, count] : out.rejection_counts_by_gate) {
            if (!first) line += ", ";
            first = false;
            line += gate + "=" + std::to_string(count);
        }
        line += ".";
        out.detail_lines.push_back(std::move(line));
    } else {
        out.detail_lines.emplace_back("No rejections.");
    }
    return out;
}

}  // namespace tuner_core::replay_sample_gate
