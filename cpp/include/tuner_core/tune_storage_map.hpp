// SPDX-License-Identifier: MIT
//
// tuner_core::tune_storage_map — parser for the firmware's
// `tune_storage_map.h` declarative table of tunable storage locations.
//
// POSITIONING
// ===========
//
// The desktop's primary authoring surface for definitions is the
// native `.tunerdef` format (see `native_format.hpp`). `.tunerdef` is
// semantic — it carries tunable identities, axes, units, grouping —
// and is what operators and the generator services read and write.
//
// `tune_storage_map.h` is **firmware-side wire-format metadata**: it
// tells the desktop how the firmware lays tunables out in its storage
// pages so the desktop can do a byte-accurate read/write over the
// serial / TCP transport. It is NOT the definition format; it does
// not carry groupings, operator labels in the `.tunerdef` sense, or
// the layout/visibility metadata operators interact with.
//
// Reading order of authority (highest to lowest):
//   1. `.tunerdef`          — desktop-authored semantic definition
//   2. `tune_storage_map.h` — firmware storage layout (wire protocol)
//   3. legacy `.ini`        — one-way import/export compat adapter
//
// Sibling to `live_data_map_parser`. Both parsers read firmware-owned
// headers for wire-protocol purposes only; they don't override the
// operator-facing native format when both are present.
//
// Grammar (mirrors the firmware header comment). Every static entry
// carries (scale, offset_v) so operator-visible value = raw * scale +
// offset_v. Dynamic-scale axes carry a controller_id instead.
//
//   TUNE_SCALAR       (semantic_id, page, offset, type, scale, offset_v, units, label)
//   TUNE_AXIS         (semantic_id, page, offset, length, type, scale, offset_v, units, label)
//   TUNE_AXIS_DYNAMIC (semantic_id, page, offset, length, type, controller_id, units_hint, label)
//   TUNE_TABLE        (semantic_id, page, offset, rows, cols, type, scale, offset_v, x_axis_id, y_axis_id, units, label)
//   TUNE_CURVE        (semantic_id, page, offset, length, type, scale, offset_v, x_axis_id, units, label)
//
// Pure-logic. No I/O — callers slurp the file themselves.

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace tuner_core::tune_storage_map {

enum class Kind { Scalar, Axis, AxisDynamic, Table, Curve };

struct Entry {
    Kind kind = Kind::Scalar;
    std::string semantic_id;
    int page = 0;
    int offset = 0;

    // Shared across kinds.
    std::string data_type;                    // "U08" / "S08" / "U16" / ...
    std::string units;
    std::string label;

    // Scalar + axis + curve.
    std::optional<double> scale;
    std::optional<double> offset_v;           // scalar only; additive after scale

    // Axis + curve.
    std::optional<int> length;

    // Table.
    std::optional<int> rows;
    std::optional<int> cols;
    std::optional<std::string> x_axis_id;
    std::optional<std::string> y_axis_id;     // table only; nullopt on curves

    // AxisDynamic only: the semantic_id of the scalar whose runtime
    // value picks the axis's scale/units. The desktop resolves via an
    // opt-in registry keyed by (this.semantic_id, controller_value).
    std::optional<std::string> controller_id;
};

struct Map {
    std::vector<Entry> entries;

    const Entry* find(std::string_view semantic_id) const;
    std::vector<const Entry*> of_kind(Kind k) const;
};

// Parse the firmware-header source text. Skips lines outside the
// recognised macros; treats `#ifdef` / `#endif` / comments as no-ops.
// Throws `std::invalid_argument` with a line-number message on
// malformed macro arguments.
Map parse(std::string_view text);

}  // namespace tuner_core::tune_storage_map
