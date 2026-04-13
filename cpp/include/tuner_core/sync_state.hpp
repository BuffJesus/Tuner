// SPDX-License-Identifier: MIT
//
// tuner_core::sync_state — port of `SyncStateService.build`.
// Eighteenth sub-slice of the Phase 14 workspace-services port (Slice 4).
//
// Detects four kinds of sync mismatches between an active definition,
// a loaded tune file, optional ECU RAM, and the staged-edits flag:
//   - SIGNATURE_MISMATCH — definition expects a different firmware
//   - PAGE_SIZE_MISMATCH — tune was saved with a different page count
//   - ECU_VS_TUNE        — parameters differ between RAM and the tune
//   - STALE_STAGED       — staged changes exist but no RAM has been read
//
// Pure logic over minimal POD inputs — no live `EcuDefinition` /
// `TuneFile` / `ParameterValue` types needed.

#pragma once

#include "tuner_core/tune_value_preview.hpp"

#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace tuner_core::sync_state {

using ScalarOrList = tune_value_preview::ScalarOrList;

enum class MismatchKind {
    SIGNATURE_MISMATCH,
    PAGE_SIZE_MISMATCH,
    ECU_VS_TUNE,
    STALE_STAGED,
};

// Stringify to the same identifier the Python `SyncMismatchKind`
// StrEnum produces (e.g. `"signature_mismatch"`).
std::string_view to_string(MismatchKind kind) noexcept;

struct Mismatch {
    MismatchKind kind = MismatchKind::SIGNATURE_MISMATCH;
    std::string detail;
};

struct State {
    std::vector<Mismatch> mismatches;
    bool has_ecu_ram = false;
    std::string connection_state;
    bool is_clean() const noexcept { return mismatches.empty(); }
};

// Minimal definition input — only the fields the detector reads.
struct DefinitionInputs {
    std::optional<std::string> firmware_signature;
    // Page sizes vector — empty means "no pages declared". The
    // detector only uses `len(page_sizes)`.
    std::vector<std::size_t> page_sizes;
};

// Minimal tune file input. `constants` and `pc_variables` are merged
// into a single name → value map for the ECU-vs-tune diff. The Python
// service iterates `tune_file.constants` then `pc_variables` and lets
// later entries shadow earlier ones — the C++ caller is responsible
// for that ordering by passing the merged list.
struct TuneFileInputs {
    std::optional<std::string> signature;
    std::optional<std::size_t> page_count;
    std::vector<std::pair<std::string, ScalarOrList>> base_values;
};

// `ecu_ram` is optional via the `has_value` flag — nullopt mirrors
// Python `ecu_ram is None`. Mirrors `SyncStateService.build`.
State build(
    std::optional<DefinitionInputs> definition,
    std::optional<TuneFileInputs> tune_file,
    std::optional<std::vector<std::pair<std::string, ScalarOrList>>> ecu_ram,
    bool has_staged,
    std::string connection_state);

}  // namespace tuner_core::sync_state
