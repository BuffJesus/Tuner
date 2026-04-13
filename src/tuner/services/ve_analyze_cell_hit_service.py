"""Phase 6: VE Analyze cell-hit accumulation and correction proposal.

VeAnalyzeCellHitService and VeAnalyzeCellHitAccumulator implement the core of
TunerStudio's VeAnalyze algorithm:

  1. Filter datalog records through named sample gates (ReplaySampleGateService).
  2. Map each accepted record to a VE table cell (TableReplayContextService).
  3. Extract measured lambda/AFR from the record.
  4. Resolve the target lambda for that cell — either from a per-cell lambda
     target table (lambdaTable1/afrTable1) or from a scalar fallback.
  5. Compute per-sample correction factor:
       correction = measured_lambda / target_lambda
     - correction > 1 → running lean → VE too low → increase VE
     - correction < 1 → running rich → VE too high → decrease VE
  6. Accumulate correction factors per cell; compute arithmetic mean.
  7. Gate cells by minimum sample count before proposing a correction.
  8. Proposed new VE = clamp(current_VE × mean_correction, ve_min, ve_max).
  9. Surface proposed edits as VeAnalysisProposal objects — never auto-stage.

The accumulator is stateful so it can accept records one at a time for live
polling.  The service is stateless and processes an entire DataLog in one call
via the accumulator internally.

Lambda target table units (auto-detected by value range):
  - Lambda units: values in [0.5, 2.0] → used directly.
  - AFR units: values in (2.0, 30.0] → divided by _STOICH_AFR to convert.
  - Values outside both ranges fall back to the scalar lambda_target.

Correction factor semantics (lambda-based, gasoline stoich = 14.7):
  - target_lambda = target AFR / 14.7 (or set directly in lambda units)
  - If measured lambda = 1.1 and target = 1.0: correction = 1.1 → +10% VE
  - If measured lambda = 0.9 and target = 1.0: correction = 0.9 → -10% VE
  - The correction factor is agnostic to whether the log channel is in AFR or
    lambda units; both are normalised to lambda internally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)
from tuner.services.table_replay_context_service import TableReplayContextService
from tuner.services.tuning_workspace_presenter import TablePageSnapshot

# Gasoline stoichiometric AFR used for AFR ↔ lambda conversion.
_STOICH_AFR = 14.7

# Confidence thresholds (sample count per cell).
_CONFIDENCE_LOW = 3
_CONFIDENCE_MEDIUM = 10
_CONFIDENCE_HIGH = 30

# Phase 7 Slice 7.3 — continuous confidence score parameter.
# confidence(n) = 1 - exp(-n / _CONFIDENCE_SCORE_K) gives:
#   n=0  → 0.00 (no data)
#   n=3  → 0.26 (low)
#   n=10 → 0.63 (medium)
#   n=30 → 0.95 (high)
# This matches the existing categorical thresholds while being continuous.
_CONFIDENCE_SCORE_K = 10.0

# Lambda value range used to auto-detect units in the target table.
_LAMBDA_UNIT_MAX = 2.0   # values <= this are treated as lambda
_AFR_UNIT_MIN = 2.0      # values > this are treated as AFR


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BoostConfidenceConfig:
    """Phase 7 Slice 7.6 — closed-form sample weight penalties for boost
    transitions and unstable manifold-temperature regions.

    Defaults are off so the Phase 6 baseline path is bit-identical.

    Spool transition penalty:
        active only when MAP > ``atmospheric_kpa`` (positive boost). The
        severity is the larger of |drpm/dt|/``spool_drpm_threshold`` and
        |dmap/dt|/``spool_dmap_threshold``, clamped to [0, 1]. The applied
        penalty is ``severity * spool_penalty_max`` so a sample at exactly
        the threshold gets no penalty and a sample at twice the threshold
        gets the full ``spool_penalty_max``.

    MAT instability penalty:
        severity = |dmat/dt| / ``mat_dt_threshold``, clamped to [0, 1];
        penalty = ``severity * mat_penalty_max``. Applies regardless of
        whether the engine is in boost or vacuum.

    The two penalties combine as ``1 - max(spool_pen, mat_pen)`` so the
    sample weight always lands in [1 - max(penalty_max), 1.0]. Closed-form
    and operator-inspectable; no hidden state.
    """

    atmospheric_kpa: float = 100.0
    spool_drpm_threshold: float = 2000.0
    spool_dmap_threshold: float = 100.0
    spool_penalty_max: float = 0.7
    mat_dt_threshold: float = 5.0
    mat_penalty_max: float = 0.5


@dataclass(slots=True, frozen=True)
class SteadyStateConfig:
    """Phase 7 Slice 7.4 — EGO transport-delay compensation and explicit
    steady-state derivative gating.

    Defaults are off so the Phase 6 baseline path is bit-identical.

    ``ego_transport_delay_seconds`` — when > 0, the lambda reading from each
    incoming record is paired with the *engine state* (rpm/map/tps/...)
    from approximately ``delay`` seconds earlier in the accumulator's
    history buffer. Models the physical lag between the cylinder firing
    and the wideband sensor measurement at the manifold or downstream of
    the turbo. Records arriving before the history buffer has covered the
    delay window are rejected as ``delay_buffer_cold``.

    ``max_drpm_per_second`` / ``max_dmap_per_second`` — when set, samples
    are rejected if the absolute time-derivative of the named channel
    exceeds the threshold relative to the most recent prior record in
    history. Tightens the implicit Phase 6 ``accelFilter`` heuristic with
    explicit numerical bounds.

    ``history_window_seconds`` — rolling history depth maintained by the
    accumulator. Caps memory and bounds the delay-comp lookup window.
    """

    ego_transport_delay_seconds: float = 0.0
    max_drpm_per_second: float | None = None
    max_dmap_per_second: float | None = None
    history_window_seconds: float = 2.0


@dataclass(slots=True, frozen=True)
class WeightedCorrectionConfig:
    """Phase 7 Slice 7.2 — opt-in weighting and bounded-edit configuration.

    Default values reproduce the Phase 6 baseline exactly: arithmetic mean of
    per-sample correction factors with no clamp. Each field is independently
    opt-in.

    ``max_correction_per_cell`` is the maximum *signed* deviation from 1.0
    that a correction factor may apply. Example: ``0.10`` means proposed
    corrections are clamped to the range ``[0.90, 1.10]`` (±10 % VE shift)
    regardless of how lean or rich the cell ran. ``None`` disables clamping.

    ``dwell_weight_enabled`` weights samples by the time the engine spent in
    the cell — successive samples in the same cell accumulate dwell weight
    proportional to the time delta to the previous accepted sample in the
    same cell. Caps at ``dwell_weight_cap_seconds`` so a single long pause
    can't dominate.

    ``sample_age_decay_per_second`` applies an exponential decay to older
    samples at snapshot time: ``weight *= exp(-age_seconds * decay)`` where
    ``age_seconds`` is the time from the most recent accepted sample in any
    cell. ``None`` disables decay.
    """

    max_correction_per_cell: float | None = None
    dwell_weight_enabled: bool = False
    dwell_weight_cap_seconds: float = 2.0
    sample_age_decay_per_second: float | None = None


@dataclass(slots=True, frozen=True)
class VeAnalysisCellCorrection:
    """Correction data for one VE table cell."""

    row_index: int
    col_index: int
    sample_count: int
    mean_correction_factor: float   # multiply current VE by this (post-clamp)
    current_ve: float | None        # None if the table cell text couldn't be parsed
    proposed_ve: float | None       # None if below min_samples or no current value
    confidence: str                 # "insufficient", "low", "medium", "high"
    # Phase 7 Slice 7.2 — clamp transparency. raw_correction_factor is the
    # weighted mean before clamping; clamp_applied is True iff the proposed
    # correction was actually moved by the clamp. Both default to "no clamp"
    # so existing call-sites and fixtures stay green.
    raw_correction_factor: float | None = None
    clamp_applied: bool = False
    # Phase 7 Slice 7.3 — continuous confidence score in [0.0, 1.0]. Defaults
    # to 0.0 so existing call-sites that build VeAnalysisCellCorrection
    # directly stay valid.
    confidence_score: float = 0.0
    # Phase 7 Slice 7.6 — total boost-confidence penalty applied to this
    # cell's accumulated samples. 0.0 = no penalty applied (default).
    # Surfaced to operators so they can see *why* a cell was downweighted.
    boost_penalty_applied: float = 0.0


@dataclass(slots=True, frozen=True)
class CoverageCell:
    """Phase 7 Slice 7.3 — coverage status for one VE table cell."""

    row_index: int
    col_index: int
    sample_count: int
    confidence_score: float
    status: str  # "unvisited" | "visited"


@dataclass(slots=True, frozen=True)
class VeAnalysisCoverage:
    """Phase 7 Slice 7.3 — full-grid coverage map for the VE table.

    Always carries the *whole* table — visited and unvisited cells alike —
    so the workspace UI can render a heatmap without re-deriving the grid
    from the table snapshot.
    """

    rows: int
    columns: int
    cells: tuple[tuple[CoverageCell, ...], ...]
    visited_count: int
    total_count: int

    @property
    def coverage_ratio(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.visited_count / self.total_count


@dataclass(slots=True, frozen=True)
class VeAnalysisProposal:
    """One proposed VE table cell edit.

    Only generated for cells that pass the minimum sample threshold and whose
    current VE value is known.  These are strictly informational — the caller
    is responsible for staging them after operator review.
    """

    row_index: int
    col_index: int
    current_ve: float
    proposed_ve: float              # clamped to [ve_min, ve_max]
    correction_factor: float        # mean correction applied (post-clamp)
    sample_count: int
    # Phase 7 Slice 7.2 — clamp transparency. raw_correction_factor is the
    # pre-clamp weighted mean; clamp_applied flags whether the per-cell max
    # correction clamp moved the value. Defaults preserve backwards-compat.
    raw_correction_factor: float | None = None
    clamp_applied: bool = False


@dataclass(slots=True, frozen=True)
class VeAnalysisSummary:
    """Aggregate result of a full VE Analyze pass."""

    total_records: int
    accepted_records: int
    rejected_records: int
    cells_with_data: int
    cells_with_proposals: int
    cell_corrections: tuple[VeAnalysisCellCorrection, ...]   # all cells that received ≥1 sample
    proposals: tuple[VeAnalysisProposal, ...]                # cells that meet min_samples
    rejection_counts_by_gate: tuple[tuple[str, int], ...]
    summary_text: str
    detail_lines: tuple[str, ...]
    # Phase 7 Slice 7.3 — full-grid coverage map. Defaults to None so
    # existing fixtures and review-service tests that build VeAnalysisSummary
    # by hand stay green.
    coverage: VeAnalysisCoverage | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_lambda(values: dict[str, float]) -> float | None:
    """Extract a lambda value from datalog channel values.

    Tries lambda channels first, then AFR-derived channels.
    Returns None if no usable channel is found.
    """
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


def _boost_confidence_multiplier(
    record: DataLogRecord,
    prior: DataLogRecord,
    config: BoostConfidenceConfig,
) -> float:
    """Closed-form sample-weight multiplier in [1 - max_pen, 1.0].

    Phase 7 Slice 7.6. Combines a spool-transition penalty (active only
    in positive boost) and a manifold-air-temperature instability penalty.
    The multiplier is ``1 - max(spool, mat)`` so the worst single signal
    dominates rather than the two penalties stacking multiplicatively.
    """
    dt = (record.timestamp - prior.timestamp).total_seconds()
    if dt <= 0:
        return 1.0

    def _delta(name: str) -> float | None:
        cur = prior.values.get(name)
        new = record.values.get(name)
        if cur is None or new is None:
            return None
        return abs(new - cur) / dt

    # Spool transition penalty — only when MAP is above atmospheric.
    spool_pen = 0.0
    map_value = record.values.get("map")
    if map_value is not None and map_value > config.atmospheric_kpa:
        drpm = _delta("rpm") or 0.0
        dmap = _delta("map") or 0.0
        rpm_severity = (
            min(drpm / config.spool_drpm_threshold, 1.0)
            if config.spool_drpm_threshold > 0 else 0.0
        )
        map_severity = (
            min(dmap / config.spool_dmap_threshold, 1.0)
            if config.spool_dmap_threshold > 0 else 0.0
        )
        severity = max(rpm_severity, map_severity)
        spool_pen = severity * config.spool_penalty_max

    # MAT instability penalty — applies in vacuum or boost.
    mat_pen = 0.0
    dmat = _delta("mat")
    if dmat is None:
        # Tolerate alternate channel names commonly seen in datalogs.
        dmat = _delta("iat")
    if dmat is not None and config.mat_dt_threshold > 0:
        mat_severity = min(dmat / config.mat_dt_threshold, 1.0)
        mat_pen = mat_severity * config.mat_penalty_max

    combined = max(spool_pen, mat_pen)
    return max(0.0, 1.0 - combined)


def _confidence_score(sample_count: int) -> float:
    """Continuous confidence in [0.0, 1.0] from sample count.

    Phase 7 Slice 7.3. Uses ``1 - exp(-n / k)`` so the curve is monotonic,
    saturates near 1.0 for large samples, and lines up with the existing
    categorical thresholds (n=10 → 0.63, n=30 → 0.95).
    """
    if sample_count <= 0:
        return 0.0
    return round(1.0 - math.exp(-sample_count / _CONFIDENCE_SCORE_K), 4)


def _make_evidence_snapshot(record: DataLogRecord) -> EvidenceReplaySnapshot:
    """Wrap a DataLogRecord in an EvidenceReplaySnapshot for the context service."""
    return EvidenceReplaySnapshot(
        captured_at=record.timestamp,
        session_state="replay",
        connection_text="Connection  replay",
        source_text="Source  VE Analyze",
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
        evidence_summary_text="VE Analyze record.",
    )


def _target_lambda_from_table(
    row: int,
    col: int,
    target_snapshot: TablePageSnapshot,
    scalar_fallback: float,
) -> float:
    """Look up the per-cell lambda target from *target_snapshot*.

    Auto-detects units: values ≤ 2.0 are treated as lambda; values > 2.0 are
    treated as AFR and divided by _STOICH_AFR.  Falls back to *scalar_fallback*
    if the cell is absent or unparseable.
    """
    if target_snapshot.table_model is None:
        return scalar_fallback
    cells = target_snapshot.table_model.cells
    if 0 <= row < len(cells) and 0 <= col < len(cells[row]):
        raw = _parse_cell_float(cells[row][col])
        if raw is not None and raw > 0:
            if raw > _AFR_UNIT_MIN:
                return raw / _STOICH_AFR  # AFR → lambda
            return raw  # already lambda
    return scalar_fallback


# ---------------------------------------------------------------------------
# Stateful accumulator (live-polling or incremental feed)
# ---------------------------------------------------------------------------


class VeAnalyzeCellHitAccumulator:
    """Stateful accumulator for VE Analyze cell hits.

    Accepts records one at a time so it can be driven by live polling as well
    as batch datalog replay.  Call ``snapshot()`` to retrieve the current
    accumulated analysis without clearing state; call ``reset()`` to start over.
    """

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
        context_service: TableReplayContextService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()
        self._context_service = context_service or TableReplayContextService()
        # cell → list of (correction_factor, weight, timestamp) tuples.
        # When weighting is disabled, weight is 1.0 and timestamp is unused
        # at snapshot time, so the weighted mean reduces to an arithmetic mean
        # bit-identical to the Phase 6 baseline.
        self._cell_corrections: dict[
            tuple[int, int], list[tuple[float, float, datetime]]
        ] = {}
        # Per-cell timestamp of the most recently accepted sample, used for
        # dwell weighting. Separate from _cell_corrections so resetting one
        # cell does not require touching the other state.
        self._cell_last_timestamp: dict[tuple[int, int], datetime] = {}
        self._latest_accepted_timestamp: datetime | None = None
        self._accepted: int = 0
        self._rejected: int = 0
        self._gate_rejections: dict[str, int] = {}
        # Phase 7 Slice 7.4 — rolling history of recently observed records
        # for EGO transport-delay compensation and derivative-based
        # steady-state gating. Trimmed on each add_record call.
        self._history: list[DataLogRecord] = []
        # Phase 7 Slice 7.6 — accumulated boost-confidence penalty per cell.
        # Sum of `1 - penalty_multiplier` across all accepted samples in
        # the cell so the operator can see total downweighting.
        self._cell_boost_penalty: dict[tuple[int, int], float] = {}

    # ------------------------------------------------------------------
    # Feed interface
    # ------------------------------------------------------------------

    def add_record(
        self,
        record: DataLogRecord,
        ve_table_snapshot: TablePageSnapshot,
        *,
        gating_config: SampleGatingConfig | None = None,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
        weighting_config: WeightedCorrectionConfig | None = None,
        steady_state_config: SteadyStateConfig | None = None,
        boost_confidence_config: BoostConfidenceConfig | None = None,
    ) -> bool:
        """Add one record.  Returns True if the sample was accepted into a cell.

        Parameters
        ----------
        lambda_target:
            Scalar fallback target lambda (1.0 = stoich gasoline).  Used when
            *lambda_target_snapshot* is None or the cell value is unparseable.
        lambda_target_snapshot:
            Optional per-cell lambda target table (lambdaTable1 / afrTable1).
            Must share the same axes as *ve_table_snapshot*.  Values ≤ 2.0 are
            treated as lambda units; values > 2.0 as AFR units.
        """
        # 0. Phase 7 Slice 7.4 — derivative steady-state gate + EGO
        # transport-delay compensation. The history buffer is updated
        # *before* gating so the delay lookup window grows even when the
        # current sample is ultimately rejected, and so the next sample's
        # derivative comparison includes this record. The window is
        # capped by ``history_window_seconds``.
        history_window = (
            steady_state_config.history_window_seconds
            if steady_state_config is not None
            else 2.0
        )
        if self._history:
            cutoff = record.timestamp.timestamp() - history_window
            self._history = [
                r for r in self._history if r.timestamp.timestamp() >= cutoff
            ]
        prior_record = self._history[-1] if self._history else None
        self._history.append(record)

        if steady_state_config is not None:
            # Derivative gates
            if prior_record is not None and (
                steady_state_config.max_drpm_per_second is not None
                or steady_state_config.max_dmap_per_second is not None
            ):
                dt = (record.timestamp - prior_record.timestamp).total_seconds()
                if dt > 0:
                    deriv_reject = self._derivative_rejection(
                        record, prior_record, dt, steady_state_config
                    )
                    if deriv_reject is not None:
                        self._rejected += 1
                        self._gate_rejections[deriv_reject] = (
                            self._gate_rejections.get(deriv_reject, 0) + 1
                        )
                        return False

            # EGO transport-delay compensation
            if steady_state_config.ego_transport_delay_seconds > 0:
                paired = self._pair_with_delayed_engine_state(
                    record, steady_state_config.ego_transport_delay_seconds
                )
                if paired is None:
                    self._rejected += 1
                    self._gate_rejections["delay_buffer_cold"] = (
                        self._gate_rejections.get("delay_buffer_cold", 0) + 1
                    )
                    return False
                record = paired

        # 1. Gate evaluation
        rejection = self._gate_service.primary_rejection(record, gating_config)
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

        # 3. Map to VE table cell
        evidence = _make_evidence_snapshot(record)
        context = self._context_service.build(
            table_snapshot=ve_table_snapshot,
            evidence_snapshot=evidence,
        )
        if context is None:
            self._rejected += 1
            self._gate_rejections["unmappable_axes"] = (
                self._gate_rejections.get("unmappable_axes", 0) + 1
            )
            return False

        # 4. Resolve per-cell lambda target
        if lambda_target_snapshot is not None:
            effective_target = _target_lambda_from_table(
                context.row_index,
                context.column_index,
                lambda_target_snapshot,
                scalar_fallback=lambda_target if lambda_target > 0 else 1.0,
            )
        else:
            effective_target = lambda_target if lambda_target > 0 else 1.0

        # 5. Compute correction factor
        correction = measured_lambda / effective_target

        key = (context.row_index, context.column_index)
        # 6. Compute per-sample weight (Phase 7 Slice 7.2). When weighting is
        # disabled the weight is 1.0 and the weighted mean reduces to the
        # Phase 6 arithmetic mean exactly.
        weight = 1.0
        if weighting_config is not None and weighting_config.dwell_weight_enabled:
            previous_ts = self._cell_last_timestamp.get(key)
            if previous_ts is not None:
                delta = (record.timestamp - previous_ts).total_seconds()
                # Cap the contribution so a single long pause cannot dominate
                # the weighted mean. Floor at zero so out-of-order timestamps
                # do not produce negative weights.
                if delta > 0:
                    weight = 1.0 + min(delta, weighting_config.dwell_weight_cap_seconds)

        # Phase 7 Slice 7.6 — boost-confidence penalty multiplier. The
        # penalty needs the prior record (for derivatives) so it falls
        # back to "no penalty" when there is no history yet.
        if boost_confidence_config is not None and prior_record is not None:
            penalty_multiplier = _boost_confidence_multiplier(
                record, prior_record, boost_confidence_config
            )
            if penalty_multiplier < 1.0:
                weight *= penalty_multiplier
                self._cell_boost_penalty[key] = (
                    self._cell_boost_penalty.get(key, 0.0)
                    + (1.0 - penalty_multiplier)
                )

        self._cell_corrections.setdefault(key, []).append(
            (correction, weight, record.timestamp)
        )
        self._cell_last_timestamp[key] = record.timestamp
        if (
            self._latest_accepted_timestamp is None
            or record.timestamp > self._latest_accepted_timestamp
        ):
            self._latest_accepted_timestamp = record.timestamp
        self._accepted += 1
        return True

    def reset(self) -> None:
        """Clear all accumulated data."""
        self._cell_corrections.clear()
        self._cell_last_timestamp.clear()
        self._latest_accepted_timestamp = None
        self._accepted = 0
        self._rejected = 0
        self._gate_rejections.clear()
        self._history.clear()
        self._cell_boost_penalty.clear()

    # ------------------------------------------------------------------
    # Phase 7 Slice 7.4 — internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derivative_rejection(
        record: DataLogRecord,
        prior: DataLogRecord,
        dt_seconds: float,
        config: SteadyStateConfig,
    ) -> str | None:
        """Return a rejection-reason key if the |d/dt| of any gated channel
        exceeds its threshold, else None.
        """
        def _delta(name: str) -> float | None:
            cur = prior.values.get(name)
            new = record.values.get(name)
            if cur is None or new is None:
                return None
            return abs(new - cur) / dt_seconds

        if config.max_drpm_per_second is not None:
            drpm = _delta("rpm")
            if drpm is not None and drpm > config.max_drpm_per_second:
                return "transient_rpm_derivative"
        if config.max_dmap_per_second is not None:
            dmap = _delta("map")
            if dmap is not None and dmap > config.max_dmap_per_second:
                return "transient_map_derivative"
        return None

    def _pair_with_delayed_engine_state(
        self, record: DataLogRecord, delay_seconds: float
    ) -> DataLogRecord | None:
        """Return a synthesized record whose engine state comes from
        ``delay_seconds`` ago and whose lambda/AFR comes from *record*.

        Returns None if the history buffer does not yet cover the delay
        window — caller treats that as ``delay_buffer_cold`` rejection.
        """
        target_time = record.timestamp.timestamp() - delay_seconds
        # The current record is already at history[-1]; ignore it for the
        # lookup so we never pair the lambda with its own engine state.
        candidates = self._history[:-1]
        if not candidates:
            return None
        oldest_time = candidates[0].timestamp.timestamp()
        if oldest_time > target_time:
            # The buffer doesn't reach back far enough yet.
            return None
        # Pick the candidate whose timestamp is closest to target_time.
        delayed = min(
            candidates,
            key=lambda r: abs(r.timestamp.timestamp() - target_time),
        )
        # Synthesize: engine state from delayed, lambda/AFR/EGO from current.
        merged = dict(delayed.values)
        for key, value in record.values.items():
            kl = key.lower()
            if "lambda" in kl or "afr" in kl or "ego" in kl:
                merged[key] = value
        return DataLogRecord(timestamp=record.timestamp, values=merged)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(
        self,
        ve_table_snapshot: TablePageSnapshot,
        *,
        min_samples_for_correction: int = _CONFIDENCE_LOW,
        ve_min: float = 0.0,
        ve_max: float = 100.0,
        weighting_config: WeightedCorrectionConfig | None = None,
    ) -> VeAnalysisSummary:
        """Build a VeAnalysisSummary from accumulated data without clearing state.

        ``weighting_config`` enables Phase 7 Slice 7.2 behaviour: per-cell
        weighted mean (dwell + age decay) and bounded-edit clamping. When
        ``None`` the snapshot reproduces the Phase 6 arithmetic-mean baseline
        bit-identically.
        """
        cell_corrections: list[VeAnalysisCellCorrection] = []
        proposals: list[VeAnalysisProposal] = []

        clamp = (
            weighting_config.max_correction_per_cell
            if weighting_config is not None
            else None
        )
        decay = (
            weighting_config.sample_age_decay_per_second
            if weighting_config is not None
            else None
        )
        latest_ts = self._latest_accepted_timestamp

        for (row, col), entries in sorted(self._cell_corrections.items()):
            count = len(entries)
            # Compute weighted mean. With weighting disabled all weights are
            # 1.0 and decay is None, so this collapses to sum(cf)/count.
            total_weight = 0.0
            total_weighted = 0.0
            for cf, w, ts in entries:
                effective_w = w
                if decay is not None and latest_ts is not None:
                    age = (latest_ts - ts).total_seconds()
                    if age > 0:
                        effective_w *= math.exp(-age * decay)
                total_weight += effective_w
                total_weighted += cf * effective_w
            raw_mean_cf = (
                total_weighted / total_weight if total_weight > 0 else 1.0
            )

            # Apply per-cell clamp (Phase 7 Slice 7.2). When clamp is None
            # the effective correction factor is the raw mean unchanged.
            mean_cf = raw_mean_cf
            clamp_applied = False
            if clamp is not None and clamp >= 0:
                lower = 1.0 - clamp
                upper = 1.0 + clamp
                clamped = max(lower, min(upper, raw_mean_cf))
                if clamped != raw_mean_cf:
                    clamp_applied = True
                mean_cf = clamped

            # Look up current VE from the table snapshot
            current_ve: float | None = None
            if ve_table_snapshot.table_model is not None:
                cells = ve_table_snapshot.table_model.cells
                if 0 <= row < len(cells) and 0 <= col < len(cells[row]):
                    current_ve = _parse_cell_float(cells[row][col])

            # Proposed VE — only if min_samples met and current value known
            proposed_ve: float | None = None
            if count >= min_samples_for_correction and current_ve is not None:
                raw_proposed = current_ve * mean_cf
                proposed_ve = max(ve_min, min(ve_max, raw_proposed))
                proposals.append(
                    VeAnalysisProposal(
                        row_index=row,
                        col_index=col,
                        current_ve=current_ve,
                        proposed_ve=round(proposed_ve, 2),
                        correction_factor=round(mean_cf, 4),
                        sample_count=count,
                        raw_correction_factor=(
                            round(raw_mean_cf, 4) if clamp_applied else None
                        ),
                        clamp_applied=clamp_applied,
                    )
                )

            cell_corrections.append(
                VeAnalysisCellCorrection(
                    row_index=row,
                    col_index=col,
                    sample_count=count,
                    mean_correction_factor=round(mean_cf, 4),
                    current_ve=current_ve,
                    proposed_ve=(round(proposed_ve, 2) if proposed_ve is not None else None),
                    confidence=_confidence(count),
                    raw_correction_factor=(
                        round(raw_mean_cf, 4) if clamp_applied else None
                    ),
                    clamp_applied=clamp_applied,
                    confidence_score=_confidence_score(count),
                    boost_penalty_applied=round(
                        self._cell_boost_penalty.get((row, col), 0.0), 4
                    ),
                )
            )

        total = self._accepted + self._rejected
        cells_with_data = len(self._cell_corrections)
        cells_with_proposals = len(proposals)

        # Phase 7 Slice 7.3 — full-grid coverage map. Built from the table
        # snapshot dimensions so unvisited cells are explicit. Falls back to
        # None when the table model is unavailable so existing zero-data
        # tests still get None.
        coverage: VeAnalysisCoverage | None = None
        if ve_table_snapshot.table_model is not None:
            grid_rows = ve_table_snapshot.table_model.rows
            grid_cols = ve_table_snapshot.table_model.columns
            grid: list[tuple[CoverageCell, ...]] = []
            visited_count = 0
            for r in range(grid_rows):
                row_cells: list[CoverageCell] = []
                for c in range(grid_cols):
                    samples = len(self._cell_corrections.get((r, c), ()))
                    if samples > 0:
                        visited_count += 1
                    row_cells.append(
                        CoverageCell(
                            row_index=r,
                            col_index=c,
                            sample_count=samples,
                            confidence_score=_confidence_score(samples),
                            status="visited" if samples > 0 else "unvisited",
                        )
                    )
                grid.append(tuple(row_cells))
            coverage = VeAnalysisCoverage(
                rows=grid_rows,
                columns=grid_cols,
                cells=tuple(grid),
                visited_count=visited_count,
                total_count=grid_rows * grid_cols,
            )

        sorted_rejections = tuple(sorted(self._gate_rejections.items()))
        summary = (
            f"VE Analyze: {self._accepted} accepted samples across {cells_with_data} cell(s); "
            f"{self._rejected} rejected; {cells_with_proposals} cell(s) have correction proposals."
        )
        detail_lines: list[str] = [summary]
        if sorted_rejections:
            detail_lines.append(
                "Rejections: "
                + ", ".join(f"{g}={c}" for g, c in sorted_rejections)
                + "."
            )
        if proposals:
            detail_lines.append(
                "Proposals: "
                + "; ".join(
                    f"cell ({p.row_index+1},{p.col_index+1}) {p.current_ve:.1f}→{p.proposed_ve:.1f} "
                    f"(×{p.correction_factor:.4f}, n={p.sample_count})"
                    for p in proposals[:5]  # preview first 5
                )
                + ("…" if len(proposals) > 5 else ".")
            )

        return VeAnalysisSummary(
            total_records=total,
            accepted_records=self._accepted,
            rejected_records=self._rejected,
            cells_with_data=cells_with_data,
            cells_with_proposals=cells_with_proposals,
            cell_corrections=tuple(cell_corrections),
            proposals=tuple(proposals),
            rejection_counts_by_gate=sorted_rejections,
            summary_text=summary,
            detail_lines=tuple(detail_lines),
            coverage=coverage,
        )

    @property
    def accepted_count(self) -> int:
        return self._accepted

    @property
    def rejected_count(self) -> int:
        return self._rejected


# ---------------------------------------------------------------------------
# Stateless service — batch processing
# ---------------------------------------------------------------------------


class VeAnalyzeCellHitService:
    """Stateless batch VE Analyze service.

    Processes an entire DataLog in one call.  Internally creates and drives a
    VeAnalyzeCellHitAccumulator so the analysis logic is shared with the live
    polling path.
    """

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
        context_service: TableReplayContextService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()
        self._context_service = context_service or TableReplayContextService()

    def analyze(
        self,
        *,
        log: DataLog,
        ve_table_snapshot: TablePageSnapshot,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
        gating_config: SampleGatingConfig | None = None,
        min_samples_for_correction: int = _CONFIDENCE_LOW,
        ve_min: float = 0.0,
        ve_max: float = 100.0,
        weighting_config: WeightedCorrectionConfig | None = None,
        steady_state_config: SteadyStateConfig | None = None,
        boost_confidence_config: BoostConfidenceConfig | None = None,
    ) -> VeAnalysisSummary:
        """Analyze *log* against *ve_table_snapshot* and return a summary.

        Parameters
        ----------
        log:
            The datalog to analyze.
        ve_table_snapshot:
            Current VE table state (values + axis labels).  Provides both the
            axis bins for cell mapping and the current VE values for proposals.
        lambda_target:
            Scalar target lambda fallback (1.0 = stoich gasoline).  Used when
            *lambda_target_snapshot* is None or a cell value is unparseable.
        lambda_target_snapshot:
            Optional per-cell lambda target table (lambdaTable1 / afrTable1).
            Must share the same axes as *ve_table_snapshot*.  Values ≤ 2.0 are
            treated as lambda; values > 2.0 as AFR (divided by 14.7).
        gating_config:
            Sample gate configuration.  Defaults to ReplaySampleGateService
            defaults (std_DeadLambda, minCltFilter, accelFilter, aseFilter,
            overrunFilter).
        min_samples_for_correction:
            Minimum accepted samples per cell before a correction is proposed.
        ve_min / ve_max:
            Clamp bounds for proposed VE values.
        """
        accumulator = VeAnalyzeCellHitAccumulator(
            gate_service=self._gate_service,
            context_service=self._context_service,
        )
        for record in log.records:
            accumulator.add_record(
                record,
                ve_table_snapshot,
                gating_config=gating_config,
                lambda_target=lambda_target,
                lambda_target_snapshot=lambda_target_snapshot,
                weighting_config=weighting_config,
                steady_state_config=steady_state_config,
                boost_confidence_config=boost_confidence_config,
            )
        return accumulator.snapshot(
            ve_table_snapshot,
            min_samples_for_correction=min_samples_for_correction,
            ve_min=ve_min,
            ve_max=ve_max,
            weighting_config=weighting_config,
        )
