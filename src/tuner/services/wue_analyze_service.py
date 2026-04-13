"""WUE Analyze cell-hit accumulation and correction proposal.

WueAnalyzeAccumulator and WueAnalyzeService implement warmup-enrichment
autotune on the same accumulator / gating architecture as VE Analyze:

  1. Filter datalog records through named sample gates (ReplaySampleGateService).
  2. Map each accepted record to a WUE table row via CLT axis nearest-bin lookup.
  3. Extract measured lambda/AFR from the record.
  4. Resolve the target lambda for that row.
  5. Compute per-sample correction factor:
       correction = measured_lambda / target_lambda
  6. Accumulate correction factors per row; compute arithmetic mean.
  7. Gate rows by minimum sample count before proposing a correction.
  8. Proposed new WUE = clamp(current_WUE × mean_correction, wue_min, wue_max).
  9. Surface proposed edits as WueAnalysisProposal objects — never auto-stage.

Key differences from VE Analyze:
  - 1-D lookup: only the CLT axis is used; the other table dimension is ignored.
  - Axis orientation: detects whether CLT bins are along x_labels or y_labels by
    inspecting x_parameter_name / y_parameter_name for CLT-related keywords.
  - Default gates: excludes minCltFilter (WUE *wants* samples at cold CLT),
    keeps std_DeadLambda, accelFilter, aseFilter, and overrunFilter.

Correction semantics (same as VE):
  - correction > 1 → running lean → WUE too low → increase enrichment
  - correction < 1 → running rich → WUE too high → decrease enrichment
"""

from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)
from tuner.services.tuning_workspace_presenter import TablePageSnapshot

# Stoichiometric AFR for gasoline.
_STOICH_AFR = 14.7

# Confidence thresholds (sample count per row).
_CONFIDENCE_LOW = 3
_CONFIDENCE_MEDIUM = 10
_CONFIDENCE_HIGH = 30

# Lambda unit auto-detection boundary.
_AFR_UNIT_MIN = 2.0

# Keywords that indicate a CLT-based axis (checked against x/y parameter names).
_CLT_KEYWORDS = ("clt", "coolant", "warmup", "wue", "cold", "temp")

# Default gates for WUE Analyze: same as VE except minCltFilter is excluded
# because WUE analysis deliberately targets cold-running conditions.
_WUE_DEFAULT_GATES: frozenset[str] = frozenset({
    "std_DeadLambda",
    "accelFilter",
    "aseFilter",
    "overrunFilter",
})


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class WueAnalysisRowCorrection:
    """Correction data for one WUE table row (CLT bin)."""

    row_index: int
    sample_count: int
    mean_correction_factor: float
    current_enrichment: float | None   # None if cell text couldn't be parsed
    proposed_enrichment: float | None  # None if below min_samples or no current value
    confidence: str                    # "insufficient", "low", "medium", "high"


@dataclass(slots=True, frozen=True)
class WueAnalysisProposal:
    """One proposed WUE table row edit.

    Only generated for rows that pass the minimum sample threshold and whose
    current enrichment value is known.  Caller stages them after operator review.
    """

    row_index: int
    current_enrichment: float
    proposed_enrichment: float    # clamped to [wue_min, wue_max]
    correction_factor: float      # mean correction applied
    sample_count: int


@dataclass(slots=True, frozen=True)
class WueAnalysisSummary:
    """Aggregate result of a full WUE Analyze pass."""

    total_records: int
    accepted_records: int
    rejected_records: int
    rows_with_data: int
    rows_with_proposals: int
    row_corrections: tuple[WueAnalysisRowCorrection, ...]
    proposals: tuple[WueAnalysisProposal, ...]
    rejection_counts_by_gate: tuple[tuple[str, int], ...]
    summary_text: str
    detail_lines: tuple[str, ...]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_lambda(values: dict[str, float]) -> float | None:
    for key, value in values.items():
        if "lambda" in key.lower():
            return value
    for key, value in values.items():
        k = key.lower()
        if "afr" in k or "ego" in k:
            if value > 0:
                return value / _STOICH_AFR
    return None


def _parse_cell_float(cell_text: str | None) -> float | None:
    if cell_text is None:
        return None
    try:
        return float(cell_text)
    except (ValueError, TypeError):
        return None


def _confidence(sample_count: int) -> str:
    if sample_count < _CONFIDENCE_LOW:
        return "insufficient"
    if sample_count < _CONFIDENCE_MEDIUM:
        return "low"
    if sample_count < _CONFIDENCE_HIGH:
        return "medium"
    return "high"


def _is_clt_axis(param_name: str | None) -> bool:
    """Return True if *param_name* looks like a CLT / warmup axis."""
    if not param_name:
        return False
    lower = param_name.lower()
    return any(kw in lower for kw in _CLT_KEYWORDS)


def _clt_from_record(values: dict[str, float]) -> float | None:
    """Extract CLT value from record, trying common channel name variants."""
    for key, value in values.items():
        k = key.lower()
        if "coolant" in k or "clt" in k:
            return value
    return None


def _nearest_index(axis: tuple[float, ...], value: float) -> int:
    best_index = 0
    best_error = abs(axis[0] - value)
    for i, av in enumerate(axis[1:], start=1):
        err = abs(av - value)
        if err < best_error:
            best_index = i
            best_error = err
    return best_index


def _numeric_axis(labels: tuple[str, ...]) -> tuple[float, ...]:
    values: list[float] = []
    for label in labels:
        try:
            values.append(float(label))
        except ValueError:
            return ()
    return tuple(values)


class _TableOrientation:
    """Describes how CLT maps into a WUE TablePageSnapshot.

    For a N×1 table (N rows, 1 column):
      clt_along_y=True  → row_index = CLT bin, column_index = 0
    For a 1×N table (1 row, N columns):
      clt_along_y=False → row_index = 0, column_index = CLT bin
    """

    __slots__ = ("clt_along_y", "clt_axis")

    def __init__(self, clt_along_y: bool, clt_axis: tuple[float, ...]) -> None:
        self.clt_along_y = clt_along_y
        self.clt_axis = clt_axis

    @classmethod
    def detect(cls, snapshot: TablePageSnapshot) -> "_TableOrientation | None":
        """Detect CLT axis orientation from the table snapshot.

        Checks y_parameter_name first (typical N×1 WUE table layout).
        Falls back to x_parameter_name.  If neither looks like CLT, returns
        None (table is not recognised as a WUE-style table).
        """
        if snapshot.table_model is None:
            return None
        y_axis = _numeric_axis(snapshot.y_labels)
        x_axis = _numeric_axis(snapshot.x_labels)
        # Prefer the axis whose parameter name suggests CLT.
        if _is_clt_axis(snapshot.y_parameter_name) and y_axis:
            return cls(clt_along_y=True, clt_axis=y_axis)
        if _is_clt_axis(snapshot.x_parameter_name) and x_axis:
            return cls(clt_along_y=False, clt_axis=x_axis)
        # Fall back to whichever axis has more than one bin.
        if len(y_axis) > 1:
            return cls(clt_along_y=True, clt_axis=y_axis)
        if len(x_axis) > 1:
            return cls(clt_along_y=False, clt_axis=x_axis)
        return None

    def cell_indices(self, clt_value: float) -> tuple[int, int]:
        """Return (row_index, col_index) for the given CLT value."""
        idx = _nearest_index(self.clt_axis, clt_value)
        if self.clt_along_y:
            return (idx, 0)
        return (0, idx)

    def row_index_from_clt(self, clt_value: float) -> int:
        """Return the logical *row* index for this CLT value.

        For accumulators and proposals, we always key by `row_index` regardless
        of physical orientation, letting the apply step use `cell_indices()` to
        resolve the actual flat table index.
        """
        return _nearest_index(self.clt_axis, clt_value)

    def flat_index(self, logical_row: int, columns: int) -> int:
        """Convert logical row → flat list index in the tune value list."""
        if self.clt_along_y:
            return logical_row * columns
        return logical_row  # 1×N table: each logical row is a single column

    def current_value(self, snapshot: TablePageSnapshot, logical_row: int) -> float | None:
        """Read the current enrichment value for the given logical CLT bin row."""
        if snapshot.table_model is None:
            return None
        cells = snapshot.table_model.cells
        if self.clt_along_y:
            # N×1: row=logical_row, col=0
            if 0 <= logical_row < len(cells):
                row = cells[logical_row]
                if row:
                    return _parse_cell_float(row[0])
        else:
            # 1×N: row=0, col=logical_row
            if cells and 0 <= logical_row < len(cells[0]):
                return _parse_cell_float(cells[0][logical_row])
        return None


def _make_evidence_snapshot(record: DataLogRecord) -> EvidenceReplaySnapshot:
    return EvidenceReplaySnapshot(
        captured_at=record.timestamp,
        session_state="replay",
        connection_text="Connection  replay",
        source_text="Source  WUE Analyze",
        sync_summary_text="Sync  unavailable",
        sync_mismatch_details=(),
        staged_summary_text="No staged changes.",
        operation_summary_text="",
        operation_session_count=0,
        latest_write_text=None,
        latest_burn_text=None,
        runtime_summary_text=f"Runtime  {len(record.values)} channel(s)",
        runtime_channel_count=len(record.values),
        runtime_age_seconds=0.0,
        runtime_channels=tuple(
            EvidenceReplayChannel(name=name, value=value)
            for name, value in record.values.items()
        ),
        evidence_summary_text="WUE Analyze record.",
    )


def _target_lambda_from_table(
    row: int,
    col: int,
    target_snapshot: TablePageSnapshot,
    scalar_fallback: float,
) -> float:
    if target_snapshot.table_model is None:
        return scalar_fallback
    cells = target_snapshot.table_model.cells
    if 0 <= row < len(cells) and 0 <= col < len(cells[row]):
        raw = _parse_cell_float(cells[row][col])
        if raw is not None and raw > 0:
            if raw > _AFR_UNIT_MIN:
                return raw / _STOICH_AFR
            return raw
    return scalar_fallback


# ---------------------------------------------------------------------------
# Stateful accumulator
# ---------------------------------------------------------------------------


class WueAnalyzeAccumulator:
    """Stateful accumulator for WUE Analyze row hits.

    Keyed by logical CLT-bin row index.  Accepts one record at a time to
    support both live polling and batch datalog replay.
    """

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()
        # row_index → list of per-sample correction factors
        self._row_corrections: dict[int, list[float]] = {}
        self._accepted: int = 0
        self._rejected: int = 0
        self._gate_rejections: dict[str, int] = {}

    @property
    def accepted_count(self) -> int:
        return self._accepted

    @property
    def rejected_count(self) -> int:
        return self._rejected

    def add_record(
        self,
        record: DataLogRecord,
        wue_table_snapshot: TablePageSnapshot,
        *,
        gating_config: SampleGatingConfig | None = None,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
    ) -> bool:
        """Add one record.  Returns True if accepted into a CLT bin row."""
        # 1. Gate evaluation — use WUE-specific defaults when no config is given
        effective_config = gating_config if gating_config is not None else wue_default_gating_config()
        rejection = self._gate_service.primary_rejection(record, effective_config)
        if rejection is not None:
            self._rejected += 1
            self._gate_rejections[rejection.gate_name] = (
                self._gate_rejections.get(rejection.gate_name, 0) + 1
            )
            return False

        # 2. Extract measured lambda
        measured_lambda = _to_lambda(record.values)
        if measured_lambda is None or measured_lambda <= 0:
            self._rejected += 1
            self._gate_rejections["no_lambda_channel"] = (
                self._gate_rejections.get("no_lambda_channel", 0) + 1
            )
            return False

        # 3. Extract CLT
        clt = _clt_from_record(record.values)
        if clt is None:
            self._rejected += 1
            self._gate_rejections["no_clt_channel"] = (
                self._gate_rejections.get("no_clt_channel", 0) + 1
            )
            return False

        # 4. Detect orientation and map CLT to row index
        orientation = _TableOrientation.detect(wue_table_snapshot)
        if orientation is None:
            self._rejected += 1
            self._gate_rejections["unmappable_axes"] = (
                self._gate_rejections.get("unmappable_axes", 0) + 1
            )
            return False

        row_index = orientation.row_index_from_clt(clt)
        # Also get the col_index for lambda target lookup
        row_i, col_i = orientation.cell_indices(clt)

        # 5. Resolve lambda target
        if lambda_target_snapshot is not None:
            effective_target = _target_lambda_from_table(
                row_i, col_i, lambda_target_snapshot,
                scalar_fallback=lambda_target if lambda_target > 0 else 1.0,
            )
        else:
            effective_target = lambda_target if lambda_target > 0 else 1.0

        # 6. Compute and accumulate correction
        correction = measured_lambda / effective_target
        self._row_corrections.setdefault(row_index, []).append(correction)
        self._accepted += 1
        return True

    def reset(self) -> None:
        self._row_corrections.clear()
        self._accepted = 0
        self._rejected = 0
        self._gate_rejections.clear()

    def snapshot(
        self,
        wue_table_snapshot: TablePageSnapshot,
        *,
        min_samples_for_correction: int = _CONFIDENCE_LOW,
        wue_min: float = 100.0,
        wue_max: float = 250.0,
    ) -> WueAnalysisSummary:
        """Build a WueAnalysisSummary without clearing state."""
        orientation = _TableOrientation.detect(wue_table_snapshot)
        row_corrections: list[WueAnalysisRowCorrection] = []
        proposals: list[WueAnalysisProposal] = []

        for row_index, factors in sorted(self._row_corrections.items()):
            count = len(factors)
            mean_cf = sum(factors) / count
            current_val = (
                orientation.current_value(wue_table_snapshot, row_index)
                if orientation is not None else None
            )
            proposed: float | None = None
            if count >= min_samples_for_correction and current_val is not None:
                raw_proposed = current_val * mean_cf
                proposed = round(max(wue_min, min(wue_max, raw_proposed)), 2)
                proposals.append(
                    WueAnalysisProposal(
                        row_index=row_index,
                        current_enrichment=current_val,
                        proposed_enrichment=proposed,
                        correction_factor=round(mean_cf, 4),
                        sample_count=count,
                    )
                )
            row_corrections.append(
                WueAnalysisRowCorrection(
                    row_index=row_index,
                    sample_count=count,
                    mean_correction_factor=round(mean_cf, 4),
                    current_enrichment=current_val,
                    proposed_enrichment=proposed,
                    confidence=_confidence(count),
                )
            )

        total = self._accepted + self._rejected
        sorted_gate_rejections = tuple(sorted(self._gate_rejections.items()))
        summary_text = _build_summary(total, self._accepted, self._rejected, len(proposals), len(row_corrections))
        detail_lines = _build_detail_lines(
            total=total,
            accepted=self._accepted,
            rejected=self._rejected,
            gate_rejections=sorted_gate_rejections,
            row_corrections=tuple(row_corrections),
            proposals=tuple(proposals),
        )
        return WueAnalysisSummary(
            total_records=total,
            accepted_records=self._accepted,
            rejected_records=self._rejected,
            rows_with_data=len(row_corrections),
            rows_with_proposals=len(proposals),
            row_corrections=tuple(row_corrections),
            proposals=tuple(proposals),
            rejection_counts_by_gate=sorted_gate_rejections,
            summary_text=summary_text,
            detail_lines=detail_lines,
        )


# ---------------------------------------------------------------------------
# Stateless batch service
# ---------------------------------------------------------------------------


class WueAnalyzeService:
    """Stateless batch WUE Analyze service.  Processes an entire DataLog in one call."""

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()

    def analyze(
        self,
        log: DataLog,
        wue_table_snapshot: TablePageSnapshot,
        *,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
        gating_config: SampleGatingConfig | None = None,
        min_samples_for_correction: int = _CONFIDENCE_LOW,
        wue_min: float = 100.0,
        wue_max: float = 250.0,
    ) -> WueAnalysisSummary:
        accumulator = WueAnalyzeAccumulator(gate_service=self._gate_service)
        for record in log.records:
            accumulator.add_record(
                record,
                wue_table_snapshot,
                gating_config=gating_config,
                lambda_target=lambda_target,
                lambda_target_snapshot=lambda_target_snapshot,
            )
        return accumulator.snapshot(
            wue_table_snapshot,
            min_samples_for_correction=min_samples_for_correction,
            wue_min=wue_min,
            wue_max=wue_max,
        )


# ---------------------------------------------------------------------------
# Default gating config for WUE
# ---------------------------------------------------------------------------


def wue_default_gating_config() -> SampleGatingConfig:
    """Return the default SampleGatingConfig for WUE Analyze sessions.

    Excludes minCltFilter (WUE wants cold samples), keeps the transient-
    rejection gates that matter during warmup.
    """
    return SampleGatingConfig(enabled_gates=_WUE_DEFAULT_GATES)


# ---------------------------------------------------------------------------
# Summary text builders
# ---------------------------------------------------------------------------


def _build_summary(
    total: int, accepted: int, rejected: int, proposals: int, rows_with_data: int
) -> str:
    if total == 0:
        return "WUE Analyze: no records to review."
    return (
        f"WUE Analyze reviewed {total} record(s): "
        f"{accepted} accepted, {rejected} rejected, "
        f"{proposals} row proposal(s) of {rows_with_data} with data."
    )


def _build_detail_lines(
    *,
    total: int,
    accepted: int,
    rejected: int,
    gate_rejections: tuple[tuple[str, int], ...],
    row_corrections: tuple[WueAnalysisRowCorrection, ...],
    proposals: tuple[WueAnalysisProposal, ...],
) -> tuple[str, ...]:
    lines: list[str] = [
        f"Records: {accepted} accepted / {rejected} rejected / {total} total."
    ]
    if gate_rejections:
        lines.append(
            "Rejections: "
            + ", ".join(f"{g}={c}" for g, c in gate_rejections)
            + "."
        )
    dist: dict[str, int] = {"insufficient": 0, "low": 0, "medium": 0, "high": 0}
    for rc in row_corrections:
        dist[rc.confidence] = dist.get(rc.confidence, 0) + 1
    non_zero = [(lvl, cnt) for lvl, cnt in dist.items() if cnt > 0]
    if non_zero:
        lines.append("Row confidence: " + ", ".join(f"{l}={c}" for l, c in non_zero) + ".")
    if proposals:
        _PREVIEW = 5
        lean = sorted((p for p in proposals if p.correction_factor > 1.0),
                      key=lambda p: p.correction_factor, reverse=True)
        rich = sorted((p for p in proposals if p.correction_factor < 1.0),
                      key=lambda p: p.correction_factor)
        if lean:
            text = "; ".join(
                f"row {p.row_index + 1} {p.current_enrichment:.1f}→{p.proposed_enrichment:.1f}"
                f" ×{p.correction_factor:.4f} n={p.sample_count}"
                for p in lean[:_PREVIEW]
            )
            suffix = "…" if len(lean) > _PREVIEW else ""
            lines.append(f"Largest lean corrections: {text}{suffix}.")
        if rich:
            text = "; ".join(
                f"row {p.row_index + 1} {p.current_enrichment:.1f}→{p.proposed_enrichment:.1f}"
                f" ×{p.correction_factor:.4f} n={p.sample_count}"
                for p in rich[:_PREVIEW]
            )
            suffix = "…" if len(rich) > _PREVIEW else ""
            lines.append(f"Largest rich corrections: {text}{suffix}.")
    if not proposals:
        lines.append("No corrections proposed yet.")
    return tuple(lines)
