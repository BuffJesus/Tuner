"""Future Phase 12 — Owned tune and definition contracts (v1).

These dataclasses are the project's *own* definition and tune model,
independent of the legacy INI/MSQ page-and-offset shape we currently
parse from TunerStudio artifacts. They are deliberately minimal — the
v1 contract captures the **structure** of an ECU definition (parameters,
axes, tables, curves) and a flat semantic-id-keyed tune file. Later
schema versions will add capability assertions, edit history, and
richer semantic taxonomies.

Design rules:

- ``schema_version`` is a string in ``MAJOR.MINOR`` form. Loaders refuse
  to read future major versions; minor bumps are forward-compatible.
- Every entity carries a ``semantic_id`` and a ``legacy_name``. v1 uses
  the legacy INI/MSQ name as the semantic id (no rename pass yet); v2+
  will introduce stable semantic ids decoupled from legacy names.
- The model is page/offset-free. Firmware export is a separate
  compatibility layer, not the primary contract.
- All fields are JSON-friendly so the format round-trips through
  ``json.dumps`` / ``json.loads`` without custom encoders.

JSON5 is the eventual authored format for hand-edited definitions
(comments, trailing commas, unquoted keys), but the v1 service uses
plain JSON to avoid a third-party dependency. JSON5 input would be a
strict superset that the parser can adopt later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NATIVE_SCHEMA_VERSION = "1.0"


@dataclass(slots=True)
class NativeParameter:
    """A scalar tune parameter."""

    semantic_id: str
    legacy_name: str
    label: str | None = None
    units: str | None = None
    kind: str = "scalar"   # "scalar" | "enum" | "bits"
    min_value: float | None = None
    max_value: float | None = None
    default: float | int | str | None = None


@dataclass(slots=True)
class NativeAxis:
    """An axis (rpm bins, load bins, time bins, etc.) used by tables and curves."""

    semantic_id: str
    legacy_name: str
    length: int
    units: str | None = None


@dataclass(slots=True)
class NativeTable:
    """A 2D tune table with optional X and Y axes."""

    semantic_id: str
    legacy_name: str
    rows: int
    columns: int
    label: str | None = None
    units: str | None = None
    x_axis_id: str | None = None
    y_axis_id: str | None = None


@dataclass(slots=True)
class NativeCurve:
    """A 1D curve referencing an axis for the X bins."""

    semantic_id: str
    legacy_name: str
    point_count: int
    label: str | None = None
    units: str | None = None
    x_axis_id: str | None = None


@dataclass(slots=True)
class NativeDefinition:
    """Project-owned definition. Replaces the legacy ``EcuDefinition``
    page-layout shape with a flat semantic-id-indexed structure."""

    schema_version: str = NATIVE_SCHEMA_VERSION
    name: str = ""
    firmware_signature: str | None = None
    parameters: list[NativeParameter] = field(default_factory=list)
    axes: list[NativeAxis] = field(default_factory=list)
    tables: list[NativeTable] = field(default_factory=list)
    curves: list[NativeCurve] = field(default_factory=list)


@dataclass(slots=True)
class NativeTune:
    """Project-owned tune file. Flat key→value store keyed by semantic id.

    Matches against a ``NativeDefinition`` via ``definition_signature``
    (typically the firmware signature). Each entry is one of:
        - scalar: ``int | float | str``
        - axis or 1D curve y-values: ``list[float]``
        - 2D table: ``list[float]`` flattened row-major (length =
          ``rows × columns``)
    """

    schema_version: str = NATIVE_SCHEMA_VERSION
    definition_signature: str | None = None
    values: dict[str, float | int | str | list[float]] = field(default_factory=dict)
