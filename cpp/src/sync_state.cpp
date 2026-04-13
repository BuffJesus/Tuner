// SPDX-License-Identifier: MIT
//
// tuner_core::sync_state implementation. Pure logic — direct port of
// `SyncStateService.build`.

#include "tuner_core/sync_state.hpp"

#include <map>
#include <utility>
#include <variant>

namespace tuner_core::sync_state {

namespace {

std::string fmt_size_t(std::size_t v) {
    return std::to_string(v);
}

bool values_equal(const ScalarOrList& a, const ScalarOrList& b) noexcept {
    if (a.index() != b.index()) return false;
    if (std::holds_alternative<double>(a)) {
        return std::get<double>(a) == std::get<double>(b);
    }
    return std::get<std::vector<double>>(a) == std::get<std::vector<double>>(b);
}

}  // namespace

std::string_view to_string(MismatchKind kind) noexcept {
    switch (kind) {
        case MismatchKind::SIGNATURE_MISMATCH: return "signature_mismatch";
        case MismatchKind::PAGE_SIZE_MISMATCH: return "page_size_mismatch";
        case MismatchKind::ECU_VS_TUNE:        return "ecu_vs_tune";
        case MismatchKind::STALE_STAGED:       return "stale_staged";
    }
    return "";
}

State build(
    std::optional<DefinitionInputs> definition,
    std::optional<TuneFileInputs> tune_file,
    std::optional<std::vector<std::pair<std::string, ScalarOrList>>> ecu_ram,
    bool has_staged,
    std::string connection_state) {
    State state;
    state.has_ecu_ram = ecu_ram.has_value();
    state.connection_state = std::move(connection_state);

    // 1. Signature mismatch
    if (definition.has_value() && tune_file.has_value() &&
        definition->firmware_signature.has_value() &&
        tune_file->signature.has_value() &&
        !definition->firmware_signature->empty() &&
        !tune_file->signature->empty() &&
        *definition->firmware_signature != *tune_file->signature) {
        Mismatch m;
        m.kind = MismatchKind::SIGNATURE_MISMATCH;
        m.detail =
            "Definition expects '" + *definition->firmware_signature +
            "', tune was saved for '" + *tune_file->signature + "'.";
        state.mismatches.push_back(std::move(m));
    }

    // 2. Page-size mismatch
    if (definition.has_value() && tune_file.has_value()) {
        const std::size_t def_pages = definition->page_sizes.size();
        if (def_pages > 0 && tune_file->page_count.has_value() &&
            def_pages != *tune_file->page_count) {
            Mismatch m;
            m.kind = MismatchKind::PAGE_SIZE_MISMATCH;
            m.detail =
                "Definition declares " + fmt_size_t(def_pages) +
                " page(s), tune was saved with " +
                fmt_size_t(*tune_file->page_count) + " page(s).";
            state.mismatches.push_back(std::move(m));
        }
    }

    // 3. ECU RAM vs loaded tune
    if (ecu_ram.has_value() && tune_file.has_value()) {
        // Build the base map from the merged constants + pc_variables
        // list, mirroring the Python iteration order (pc_variables
        // shadow constants when names collide).
        std::map<std::string, ScalarOrList> base;
        for (const auto& [name, value] : tune_file->base_values) {
            base[name] = value;
        }
        std::vector<std::string> diffs;
        for (const auto& [name, ecu_val] : *ecu_ram) {
            auto it = base.find(name);
            if (it == base.end()) continue;
            if (!values_equal(ecu_val, it->second)) {
                diffs.push_back(name);
            }
        }
        if (!diffs.empty()) {
            std::string preview;
            const std::size_t shown = std::min<std::size_t>(diffs.size(), 5);
            for (std::size_t i = 0; i < shown; ++i) {
                if (i > 0) preview += ", ";
                preview += diffs[i];
            }
            std::string suffix = diffs.size() > 5 ? "..." : "";
            Mismatch m;
            m.kind = MismatchKind::ECU_VS_TUNE;
            m.detail =
                std::to_string(diffs.size()) +
                " parameter(s) differ between ECU RAM and loaded tune: " +
                preview + suffix;
            state.mismatches.push_back(std::move(m));
        }
    }

    // 4. Stale staged: edits exist but no ECU RAM read yet
    if (has_staged && !ecu_ram.has_value()) {
        Mismatch m;
        m.kind = MismatchKind::STALE_STAGED;
        m.detail = "Staged changes have not been written to ECU RAM.";
        state.mismatches.push_back(std::move(m));
    }

    return state;
}

}  // namespace tuner_core::sync_state
