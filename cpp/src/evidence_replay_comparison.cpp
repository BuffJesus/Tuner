// SPDX-License-Identifier: MIT
//
// tuner_core::evidence_replay_comparison implementation. Pure logic.

#include "tuner_core/evidence_replay_comparison.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <map>
#include <set>
#include <string>

namespace tuner_core::evidence_replay_comparison {

namespace {

std::string lowercase(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (char c : text) {
        out.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    }
    return out;
}

std::map<std::string, const Channel*> index_by_lower_name(
    const std::vector<Channel>& channels) {
    std::map<std::string, const Channel*> out;
    for (const auto& ch : channels) {
        out.emplace(lowercase(ch.name), &ch);
    }
    return out;
}

// Mirror Python f"{value:+.1f}" — sign-prefixed fixed-point with
// 1 decimal. snprintf's `%+.1f` produces the same output for every
// value the parity test exercises.
std::string fmt_signed_1f(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%+.1f", v);
    return std::string(buf);
}

}  // namespace

std::optional<Comparison> compare_runtime_channels(
    const std::vector<Channel>& baseline_channels,
    const std::vector<Channel>& current_channels,
    const std::vector<std::string>& relevant_channel_names) {
    auto baseline_index = index_by_lower_name(baseline_channels);
    auto current_index = index_by_lower_name(current_channels);

    // Mirror Python: deduplicate the requested names while preserving
    // order, lowercasing each. Empty input → use every current channel
    // in *current_channels* iteration order (matches `current_channels.keys()`
    // — but Python dicts preserve insertion order, so the iteration
    // order is the order each channel was added to the dict).
    std::vector<std::string> requested;
    {
        std::set<std::string> seen;
        for (const auto& raw : relevant_channel_names) {
            if (raw.empty()) continue;
            auto lower = lowercase(raw);
            if (seen.insert(lower).second) {
                requested.push_back(std::move(lower));
            }
        }
        if (requested.empty()) {
            // Mirror Python `tuple(current_channels.keys())` — iterates
            // the dict in insertion order (which is `current_channels`
            // input order in our case).
            std::set<std::string> seen2;
            for (const auto& ch : current_channels) {
                auto lower = lowercase(ch.name);
                if (seen2.insert(lower).second) {
                    requested.push_back(std::move(lower));
                }
            }
        }
    }

    std::vector<Delta> deltas;
    for (const auto& key : requested) {
        auto base_it = baseline_index.find(key);
        auto curr_it = current_index.find(key);
        if (base_it == baseline_index.end() || curr_it == current_index.end()) {
            continue;
        }
        const Channel& baseline = *base_it->second;
        const Channel& current = *curr_it->second;
        double delta = current.value - baseline.value;
        if (std::abs(delta) < 1e-9) continue;
        Delta d;
        d.name = current.name;
        d.previous_value = baseline.value;
        d.current_value = current.value;
        d.delta_value = delta;
        // `current.units or baseline.units` — Python's `or` short-circuits
        // on falsy. None / empty string both fall through.
        if (current.units.has_value() && !current.units->empty()) {
            d.units = current.units;
        } else if (baseline.units.has_value() && !baseline.units->empty()) {
            d.units = baseline.units;
        }
        deltas.push_back(std::move(d));
    }

    if (deltas.empty()) return std::nullopt;

    // Top 4 by absolute delta, descending. Python uses `sorted(...)`
    // which is stable; we use `std::stable_sort` for the same.
    std::stable_sort(deltas.begin(), deltas.end(),
                     [](const Delta& a, const Delta& b) {
                         return std::abs(a.delta_value) > std::abs(b.delta_value);
                     });
    if (deltas.size() > 4) deltas.resize(4);

    // Build the delta_text per Python:
    //   " | ".join(f"{name} {delta:+.1f}{f' {units}' if units else ''}")
    std::string delta_text;
    for (std::size_t i = 0; i < deltas.size(); ++i) {
        if (i > 0) delta_text += " | ";
        delta_text += deltas[i].name;
        delta_text += " ";
        delta_text += fmt_signed_1f(deltas[i].delta_value);
        if (deltas[i].units.has_value() && !deltas[i].units->empty()) {
            delta_text += " ";
            delta_text += *deltas[i].units;
        }
    }

    Comparison result;
    result.summary_text =
        "Comparison vs latest capture highlights runtime drift on this page.";
    result.detail_text = result.summary_text + "\nChannel deltas: " + delta_text;
    result.changed_channels = std::move(deltas);
    return result;
}

}  // namespace tuner_core::evidence_replay_comparison
