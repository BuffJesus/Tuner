// SPDX-License-Identifier: MIT
#include "tuner_core/page_evidence_review.hpp"
#include "tuner_core/surface_evidence.hpp"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <set>
#include <string>
#include <vector>

namespace tuner_core::page_evidence_review {

// -----------------------------------------------------------------------
// Channel key tables — mirrors Python class attributes
// -----------------------------------------------------------------------

namespace {

using KL = std::vector<std::string>;

const KL BASE_KEYS = {"rpm", "map", "tps", "batt"};

struct FamilyEntry { std::string family; KL keys; };
const std::vector<FamilyEntry> FAMILY_KEYS = {
    {"fuel-trims",   {"afr", "lambda", "ego", "pw"}},
    {"fuel-tables",  {"afr", "lambda", "ego", "pw"}},
    {"spark-tables", {"advance", "dwell", "knock", "sync", "rsa_fullsync"}},
    {"target-tables",{"afr", "lambda", "ego"}},
    {"vvt",          {"advance", "sync", "rpm", "map"}},
};

struct GroupEntry { std::string group; KL keys; };
const std::vector<GroupEntry> GROUP_KEYS = {
    {"fuel",           {"afr", "lambda", "ego", "pw"}},
    {"ignition",       {"advance", "dwell", "knock", "sync", "rsa_fullsync"}},
    {"idle",           {"clt", "iat", "idle"}},
    {"hardware_setup", {"clt", "iat", "afr", "lambda", "baro", "oil"}},
};

struct ParamEntry { std::string hint; KL keys; };
const std::vector<ParamEntry> PARAM_KEYS = {
    {"reqfuel",  {"rpm", "map", "pw"}},
    {"ve",       {"rpm", "map", "afr", "lambda", "ego"}},
    {"fuel",     {"rpm", "map", "afr", "lambda", "ego", "pw"}},
    {"afr",      {"rpm", "map", "afr", "lambda", "ego"}},
    {"lambda",   {"rpm", "map", "afr", "lambda", "ego"}},
    {"ego",      {"rpm", "map", "afr", "lambda", "ego"}},
    {"injector", {"rpm", "map", "pw", "afr", "lambda"}},
    {"inj",      {"rpm", "map", "pw", "afr", "lambda"}},
    {"spark",    {"rpm", "map", "advance", "dwell", "knock", "sync", "rsa_fullsync"}},
    {"ign",      {"rpm", "map", "advance", "dwell", "knock", "sync", "rsa_fullsync"}},
    {"dwell",    {"rpm", "batt", "dwell"}},
    {"knock",    {"rpm", "map", "advance", "knock", "sync", "rsa_fullsync"}},
    {"trigger",  {"rpm", "sync", "rsa_fullsync", "advance"}},
    {"idle",     {"rpm", "map", "tps", "clt", "iat", "idle"}},
    {"clt",      {"clt", "rpm", "batt"}},
    {"iat",      {"iat", "rpm", "batt"}},
    {"map",      {"map", "rpm", "baro"}},
    {"baro",     {"baro", "map", "rpm"}},
    {"oil",      {"oil", "rpm", "batt"}},
};

std::string to_lower(const std::string& s) {
    std::string r = s;
    for (auto& c : r) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return r;
}

void add_unique(std::vector<std::string>& ordered, const KL& keys) {
    std::set<std::string> seen(ordered.begin(), ordered.end());
    for (const auto& k : keys) {
        if (seen.insert(k).second) ordered.push_back(k);
    }
}

std::vector<std::string> tokenize(const std::string& raw) {
    std::vector<std::string> tokens;
    std::string tok;
    for (char ch : raw) {
        if (std::isalnum(static_cast<unsigned char>(ch))) {
            tok += static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
        } else {
            if (!tok.empty()) { tokens.push_back(tok); tok.clear(); }
        }
    }
    if (!tok.empty()) tokens.push_back(tok);
    return tokens;
}

std::vector<std::string> channel_keys(const PageContext& ctx) {
    std::vector<std::string> ordered = BASE_KEYS;
    // Family.
    for (const auto& fe : FAMILY_KEYS) {
        if (ctx.page_family_id == fe.family) add_unique(ordered, fe.keys);
    }
    // Group.
    for (const auto& ge : GROUP_KEYS) {
        if (ctx.group_id == ge.group) add_unique(ordered, ge.keys);
    }
    // Parameter-level hints.
    std::string raw = ctx.page_title;
    if (!ctx.page_id.empty()) raw += " " + ctx.page_id;
    for (const auto& pn : ctx.parameter_names) raw += " " + pn;
    for (const auto& eh : ctx.evidence_hints) raw += " " + eh;
    auto tokens = tokenize(to_lower(raw));
    for (const auto& token : tokens) {
        for (const auto& pe : PARAM_KEYS) {
            if (token.find(pe.hint) != std::string::npos) {
                add_unique(ordered, pe.keys);
            }
        }
    }
    return ordered;
}

std::string format_age(double age_seconds) {
    int rounded = static_cast<int>(age_seconds + 0.5);
    if (rounded < 60) {
        char buf[16]; std::snprintf(buf, sizeof(buf), "%ds", rounded);
        return buf;
    }
    int m = rounded / 60, s = rounded % 60;
    char buf[32]; std::snprintf(buf, sizeof(buf), "%dm %ds", m, s);
    return buf;
}

}  // namespace

// -----------------------------------------------------------------------
// build()
// -----------------------------------------------------------------------

std::optional<ReviewSnapshot> build(
    const PageContext& ctx,
    const evidence_replay::Snapshot* evidence)
{
    if (!evidence) return std::nullopt;

    auto keys = channel_keys(ctx);

    // Select matching channels (up to 6, deduplicated).
    std::vector<evidence_replay::Channel> selected;
    std::set<std::string> seen;
    for (const auto& ch : evidence->runtime_channels) {
        std::string norm = to_lower(ch.name);
        if (seen.count(norm)) continue;
        for (const auto& key : keys) {
            if (norm.find(key) != std::string::npos) {
                selected.push_back(ch);
                seen.insert(norm);
                break;
            }
        }
        if (selected.size() >= 6) break;
    }

    if (selected.empty()) {
        return ReviewSnapshot{
            "Evidence review: latest captured bundle has no page-relevant runtime channels.",
            evidence->evidence_summary_text,
            {},
        };
    }

    // Build channel text.
    std::string channel_text;
    for (size_t i = 0; i < selected.size(); ++i) {
        if (i > 0) channel_text += " | ";
        char buf[128];
        if (selected[i].units.empty())
            std::snprintf(buf, sizeof(buf), "%s=%g", selected[i].name.c_str(), selected[i].value);
        else
            std::snprintf(buf, sizeof(buf), "%s=%g %s", selected[i].name.c_str(), selected[i].value, selected[i].units.c_str());
        channel_text += buf;
    }

    std::string age_text = evidence->runtime_age_seconds
        ? format_age(*evidence->runtime_age_seconds)
        : "age unknown";

    char summary_buf[512];
    std::snprintf(summary_buf, sizeof(summary_buf),
        "Evidence review: latest capture for '%s' exposes %d relevant channel(s) from %s ago.",
        ctx.page_title.c_str(), static_cast<int>(selected.size()), age_text.c_str());
    std::string summary = summary_buf;

    std::string detail = summary + "\nRelevant channels: " + channel_text;
    if (!evidence->latest_write_text.empty())
        detail += "\nLatest write: " + evidence->latest_write_text;
    if (!evidence->latest_burn_text.empty())
        detail += "\nLatest burn: " + evidence->latest_burn_text;
    for (const auto& m : evidence->sync_mismatch_details)
        detail += "\nSync mismatch: " + m;

    return ReviewSnapshot{summary, detail, selected};
}

}  // namespace tuner_core::page_evidence_review
