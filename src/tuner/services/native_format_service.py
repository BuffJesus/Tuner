"""Future Phase 12 — Owned tune/definition contracts (v1) service.

Provides the in/out paths between the legacy `EcuDefinition` + `TuneFile`
models (parsed from INI/MSQ) and the project's own `NativeDefinition` /
`NativeTune` models. The service is intentionally a thin compatibility
layer in v1 — its job is to capture the *shape* of the contract and
make it round-trippable through JSON, not to invent richer semantics
than the underlying INI/MSQ artifacts already express.

Roundtrip guarantees:

- ``from_ecu_definition(definition).round_trip_through_json()`` produces
  the same ``NativeDefinition`` (verified by tests).
- ``from_tune_file(tune, native)`` walks the tune's constants and
  pc_variables, looks up each one's semantic id from the
  ``NativeDefinition`` (which v1 derives directly from the legacy name),
  and stores the value flat in ``NativeTune.values``.
- ``load_definition`` and ``load_tune`` reject schema versions whose
  major number is higher than the bundled ``NATIVE_SCHEMA_VERSION``;
  matching major + higher minor is accepted (forward compatible).

Future phases will introduce explicit semantic ids decoupled from
legacy names, edit history, capability assertions, and a JSON5 reader
for hand-authored definition files.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from tuner.domain.ecu_definition import (
    EcuDefinition,
    ScalarParameterDefinition,
    TableDefinition,
)
from tuner.domain.native_format import (
    NATIVE_SCHEMA_VERSION,
    NativeAxis,
    NativeCurve,
    NativeDefinition,
    NativeParameter,
    NativeTable,
    NativeTune,
)
from tuner.domain.tune import TuneFile, TuneValue


class NativeFormatVersionError(ValueError):
    """Raised when a native file's schema_version is incompatible."""


class NativeFormatService:
    """Stateless conversion + serialization for the v1 native format."""

    SCHEMA_VERSION = NATIVE_SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Legacy → native (compatibility layer in)
    # ------------------------------------------------------------------

    def from_ecu_definition(self, definition: EcuDefinition) -> NativeDefinition:
        """Project a legacy ``EcuDefinition`` into the native v1 model.

        v1 uses the legacy name as the semantic id verbatim. The native
        model still drops the page/offset shape — the only contract that
        survives the projection is parameter/table identity, axes,
        units, and shape. Anything firmware-specific (encoding, byte
        offsets, scale/translate) lives in the compatibility layer
        rather than the native model.
        """
        parameters = [
            self._parameter_from_legacy(scalar)
            for scalar in definition.scalars
        ]

        axis_ids: dict[str, NativeAxis] = {}
        tables: list[NativeTable] = []
        for table in definition.tables:
            if self._looks_like_axis(table):
                axis = NativeAxis(
                    semantic_id=table.name,
                    legacy_name=table.name,
                    length=max(table.rows, table.columns),
                    units=table.units,
                )
                axis_ids[axis.semantic_id] = axis
                continue
            tables.append(self._table_from_legacy(table))

        curves = [
            NativeCurve(
                semantic_id=curve.name,
                legacy_name=curve.name,
                point_count=getattr(curve, "size", 0) or 0,
                label=getattr(curve, "title", None),
                units=getattr(curve, "z_units", None) or getattr(curve, "y_units", None),
                x_axis_id=getattr(curve, "x_bins", None),
            )
            for curve in definition.curve_definitions
        ]

        return NativeDefinition(
            schema_version=NATIVE_SCHEMA_VERSION,
            name=definition.name,
            firmware_signature=definition.firmware_signature,
            parameters=parameters,
            axes=list(axis_ids.values()),
            tables=tables,
            curves=curves,
        )

    def from_tune_file(self, tune: TuneFile, native: NativeDefinition) -> NativeTune:
        """Project a legacy ``TuneFile`` into a flat ``NativeTune``.

        The native definition is consulted only to look up semantic ids
        — v1 sets ``semantic_id == legacy_name``, so this collapses to a
        rename pass. Parameters, axes, and tables not present in the
        definition are still copied through under their legacy name so
        the projection is information-preserving for legacy artifacts
        the schema doesn't yet model.
        """
        values: dict[str, float | int | str | list[float]] = {}
        for entry in (*tune.constants, *tune.pc_variables):
            semantic_id = self._semantic_id_for_legacy(entry.name, native)
            value = entry.value
            if isinstance(value, list):
                values[semantic_id] = list(value)
            else:
                values[semantic_id] = value
        return NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature=native.firmware_signature or tune.signature,
            values=values,
        )

    # ------------------------------------------------------------------
    # Native → legacy (compatibility layer out)
    # ------------------------------------------------------------------

    def to_tune_file(
        self,
        native_tune: NativeTune,
        native: NativeDefinition,
    ) -> TuneFile:
        """Project a ``NativeTune`` back into a legacy ``TuneFile``.

        The result is suitable for handing to ``MsqWriteService.save()``
        — every value lands in ``TuneFile.constants`` with the legacy
        name and the right ``rows``/``cols``/``units`` inherited from
        the native definition. Values whose semantic id has no matching
        entry in the native definition still pass through under the
        same name so the projection is information-preserving.

        Important: the round trip ``EcuDefinition → NativeDefinition →
        … → TuneFile`` only works for parameters/tables/axes/curves the
        v1 native model represents. The reverse path is *additive* —
        it never invents byte offsets or page assignments and never
        touches firmware-specific fields like ``digits`` or
        ``data_type`` (the existing MSQ XML retains those).
        """
        legacy_lookup: dict[str, tuple[str, str | None, int | None, int | None]] = {}
        # (semantic_id) → (legacy_name, units, rows, cols)
        for parameter in native.parameters:
            legacy_lookup[parameter.semantic_id] = (
                parameter.legacy_name, parameter.units, None, None,
            )
        for axis in native.axes:
            # Axes are 1×N; v1 records the long dimension as `length`
            # and treats them as a single row.
            legacy_lookup[axis.semantic_id] = (
                axis.legacy_name, axis.units, 1, axis.length,
            )
        for table in native.tables:
            legacy_lookup[table.semantic_id] = (
                table.legacy_name, table.units, table.rows, table.columns,
            )
        for curve in native.curves:
            legacy_lookup[curve.semantic_id] = (
                curve.legacy_name, curve.units, 1, curve.point_count,
            )

        constants: list[TuneValue] = []
        for semantic_id, value in native_tune.values.items():
            legacy_name, units, rows, cols = legacy_lookup.get(
                semantic_id,
                (semantic_id, None, None, None),
            )
            if isinstance(value, list):
                # Default a 1-d list shape if the native definition
                # didn't carry rows/cols (e.g. legacy-only pass-through).
                if rows is None or cols is None:
                    rows = 1
                    cols = len(value)
                constants.append(TuneValue(
                    name=legacy_name,
                    value=list(value),
                    units=units,
                    rows=rows,
                    cols=cols,
                ))
            else:
                constants.append(TuneValue(
                    name=legacy_name,
                    value=value,  # int | float | str
                    units=units,
                ))

        return TuneFile(
            signature=native_tune.definition_signature,
            constants=constants,
        )

    # ------------------------------------------------------------------
    # JSON serialization
    # ------------------------------------------------------------------

    def dump_definition(self, definition: NativeDefinition, *, indent: int = 2) -> str:
        return json.dumps(asdict(definition), indent=indent, sort_keys=False)

    def dump_tune(self, tune: NativeTune, *, indent: int = 2) -> str:
        return json.dumps(asdict(tune), indent=indent, sort_keys=False)

    def load_definition(self, text: str) -> NativeDefinition:
        data = self._loads(text)
        self._check_version(data.get("schema_version"))
        return NativeDefinition(
            schema_version=data["schema_version"],
            name=data.get("name", ""),
            firmware_signature=data.get("firmware_signature"),
            parameters=[
                NativeParameter(**p) for p in data.get("parameters", [])
            ],
            axes=[NativeAxis(**a) for a in data.get("axes", [])],
            tables=[NativeTable(**t) for t in data.get("tables", [])],
            curves=[NativeCurve(**c) for c in data.get("curves", [])],
        )

    def load_tune(self, text: str) -> NativeTune:
        data = self._loads(text)
        self._check_version(data.get("schema_version"))
        return NativeTune(
            schema_version=data["schema_version"],
            definition_signature=data.get("definition_signature"),
            values=dict(data.get("values", {})),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _loads(text: str) -> dict[str, Any]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid native JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Native file root must be a JSON object.")
        return data

    @classmethod
    def _check_version(cls, raw: str | None) -> None:
        if not raw:
            raise NativeFormatVersionError(
                "Native file is missing the required `schema_version` field."
            )
        try:
            major_str, _, _ = raw.partition(".")
            major = int(major_str)
        except ValueError as exc:
            raise NativeFormatVersionError(
                f"Native file has unparsable schema_version {raw!r}."
            ) from exc
        bundled_major = int(NATIVE_SCHEMA_VERSION.split(".", 1)[0])
        if major > bundled_major:
            raise NativeFormatVersionError(
                f"Native file schema {raw} is newer than supported "
                f"({NATIVE_SCHEMA_VERSION}). Upgrade the application."
            )

    @staticmethod
    def _parameter_from_legacy(scalar: ScalarParameterDefinition) -> NativeParameter:
        kind = "scalar"
        if scalar.options:
            kind = "enum"
        elif scalar.bit_length:
            kind = "bits"
        return NativeParameter(
            semantic_id=scalar.name,
            legacy_name=scalar.name,
            label=scalar.label,
            units=scalar.units,
            kind=kind,
            min_value=scalar.min_value,
            max_value=scalar.max_value,
        )

    @staticmethod
    def _table_from_legacy(table: TableDefinition) -> NativeTable:
        return NativeTable(
            semantic_id=table.name,
            legacy_name=table.name,
            rows=table.rows,
            columns=table.columns,
            label=table.label,
            units=table.units,
        )

    @staticmethod
    def _looks_like_axis(table: TableDefinition) -> bool:
        """Heuristic: 1×N or N×1 tables that look like rpm/load bins.

        v1 collapses axis-shaped tables into ``NativeAxis`` so the native
        model has a clean axis concept rather than continuing to model
        bins as one-dimensional tables.
        """
        if table.rows == 1 or table.columns == 1:
            name = table.name.lower()
            if "bin" in name or name.endswith("axis"):
                return True
        return False

    @staticmethod
    def _semantic_id_for_legacy(legacy_name: str, native: NativeDefinition) -> str:
        for parameter in native.parameters:
            if parameter.legacy_name == legacy_name:
                return parameter.semantic_id
        for axis in native.axes:
            if axis.legacy_name == legacy_name:
                return axis.semantic_id
        for table in native.tables:
            if table.legacy_name == legacy_name:
                return table.semantic_id
        for curve in native.curves:
            if curve.legacy_name == legacy_name:
                return curve.semantic_id
        return legacy_name
