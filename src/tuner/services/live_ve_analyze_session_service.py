"""Live VE Analyze session service for runtime polling.

Wraps VeAnalyzeCellHitAccumulator to accept OutputChannelSnapshot objects
from live ECU runtime polling.  Routes them through the same gate evaluation
and cell-mapping seam as batch datalog replay, so live and replay analysis
produce identical correction factors for identical data.

Typical usage (live polling loop):

    session = LiveVeAnalyzeSessionService()
    session.start(ve_table_snapshot=current_ve_snap, gating_config=cfg)

    # Called for each incoming runtime frame:
    session.feed_runtime(runtime_snapshot)

    # Called whenever the operator wants a live preview:
    summary = session.get_summary()
    review = VeAnalyzeReviewService().build(summary)

    # Operator clicks "Reset" or switches tune page:
    session.reset()

All proposed edits remain output-only.  Staging is an explicit operator action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tuner.domain.datalog import DataLogRecord
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)
from tuner.services.table_replay_context_service import TableReplayContextService
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalyzeCellHitAccumulator,
    VeAnalysisSummary,
)


@dataclass(slots=True, frozen=True)
class LiveVeAnalyzeSessionSnapshot:
    """Lightweight status snapshot for the live session."""

    is_active: bool
    accepted_count: int
    rejected_count: int
    total_count: int
    status_text: str


class LiveVeAnalyzeSessionService:
    """Stateful session that routes live runtime snapshots into the VE Analyze accumulator.

    A session is considered *active* after ``start()`` is called and before
    ``reset()`` is called.  ``feed_runtime()`` is a no-op when inactive.
    """

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
        context_service: TableReplayContextService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()
        self._context_service = context_service or TableReplayContextService()
        self._accumulator: VeAnalyzeCellHitAccumulator | None = None
        self._ve_table_snapshot: TablePageSnapshot | None = None
        self._lambda_target: float = 1.0
        self._lambda_target_snapshot: TablePageSnapshot | None = None
        self._gating_config: SampleGatingConfig | None = None
        self._min_samples: int = 3
        self._ve_min: float = 0.0
        self._ve_max: float = 100.0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        *,
        ve_table_snapshot: TablePageSnapshot,
        gating_config: SampleGatingConfig | None = None,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
        min_samples_for_correction: int = 3,
        ve_min: float = 0.0,
        ve_max: float = 100.0,
    ) -> None:
        """Start (or restart) the live session.

        Clears any previously accumulated data and records the configuration for
        subsequent ``feed_runtime()`` calls.
        """
        self._accumulator = VeAnalyzeCellHitAccumulator(
            gate_service=self._gate_service,
            context_service=self._context_service,
        )
        self._ve_table_snapshot = ve_table_snapshot
        self._gating_config = gating_config
        self._lambda_target = lambda_target
        self._lambda_target_snapshot = lambda_target_snapshot
        self._min_samples = min_samples_for_correction
        self._ve_min = ve_min
        self._ve_max = ve_max

    def reset(self) -> None:
        """Stop the session and clear all accumulated data."""
        if self._accumulator is not None:
            self._accumulator.reset()
        self._accumulator = None
        self._ve_table_snapshot = None

    @property
    def is_active(self) -> bool:
        return self._accumulator is not None and self._ve_table_snapshot is not None

    # ------------------------------------------------------------------
    # Feed interface
    # ------------------------------------------------------------------

    def feed_runtime(self, runtime_snapshot: OutputChannelSnapshot) -> bool:
        """Feed one live runtime snapshot into the accumulator.

        Returns True if the sample was accepted into a cell, False otherwise
        (either inactive session or gate/axis rejection).

        The ``OutputChannelSnapshot`` is converted to a ``DataLogRecord`` so it
        travels through the same gate evaluation and cell-mapping path as batch
        datalog replay.
        """
        if not self.is_active:
            return False
        assert self._accumulator is not None
        assert self._ve_table_snapshot is not None

        record = _runtime_to_record(runtime_snapshot)
        return self._accumulator.add_record(
            record,
            self._ve_table_snapshot,
            gating_config=self._gating_config,
            lambda_target=self._lambda_target,
            lambda_target_snapshot=self._lambda_target_snapshot,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_summary(self) -> VeAnalysisSummary | None:
        """Return the current accumulated analysis, or None if not active."""
        if not self.is_active:
            return None
        assert self._accumulator is not None
        assert self._ve_table_snapshot is not None
        return self._accumulator.snapshot(
            self._ve_table_snapshot,
            min_samples_for_correction=self._min_samples,
            ve_min=self._ve_min,
            ve_max=self._ve_max,
        )

    def status_snapshot(self) -> LiveVeAnalyzeSessionSnapshot:
        """Return a lightweight status snapshot for UI display."""
        if not self.is_active or self._accumulator is None:
            return LiveVeAnalyzeSessionSnapshot(
                is_active=False,
                accepted_count=0,
                rejected_count=0,
                total_count=0,
                status_text="VE Analyze: inactive.",
            )
        accepted = self._accumulator.accepted_count
        rejected = self._accumulator.rejected_count
        total = accepted + rejected
        return LiveVeAnalyzeSessionSnapshot(
            is_active=True,
            accepted_count=accepted,
            rejected_count=rejected,
            total_count=total,
            status_text=(
                f"VE Analyze live: {accepted} accepted / {rejected} rejected "
                f"of {total} frame(s)."
            ),
        )


# ---------------------------------------------------------------------------
# Conversion helper
# ---------------------------------------------------------------------------


def _runtime_to_record(snapshot: OutputChannelSnapshot) -> DataLogRecord:
    """Convert an OutputChannelSnapshot to a DataLogRecord for gate evaluation."""
    return DataLogRecord(
        timestamp=snapshot.timestamp,
        values=snapshot.as_dict(),
    )
