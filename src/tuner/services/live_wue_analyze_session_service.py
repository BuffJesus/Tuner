"""Live WUE Analyze session service for runtime polling.

Wraps WueAnalyzeAccumulator to accept OutputChannelSnapshot objects from live
ECU runtime polling.  Routes them through the same gate evaluation and CLT-axis
cell-mapping seam as batch datalog replay.

Typical usage (live polling loop):

    session = LiveWueAnalyzeSessionService()
    session.start(wue_table_snapshot=current_wue_snap)

    # Called for each incoming runtime frame:
    session.feed_runtime(runtime_snapshot)

    # Called whenever the operator wants a live preview:
    summary = session.get_summary()

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
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.wue_analyze_service import (
    WueAnalyzeAccumulator,
    WueAnalysisSummary,
    wue_default_gating_config,
)


@dataclass(slots=True, frozen=True)
class LiveWueAnalyzeSessionSnapshot:
    """Lightweight status snapshot for the live WUE session."""

    is_active: bool
    accepted_count: int
    rejected_count: int
    total_count: int
    status_text: str


class LiveWueAnalyzeSessionService:
    """Stateful session that routes live runtime snapshots into the WUE accumulator.

    A session is *active* after ``start()`` and before ``reset()``.
    ``feed_runtime()`` is a no-op when inactive.
    """

    def __init__(
        self,
        gate_service: ReplaySampleGateService | None = None,
    ) -> None:
        self._gate_service = gate_service or ReplaySampleGateService()
        self._accumulator: WueAnalyzeAccumulator | None = None
        self._wue_table_snapshot: TablePageSnapshot | None = None
        self._lambda_target: float = 1.0
        self._lambda_target_snapshot: TablePageSnapshot | None = None
        self._gating_config: SampleGatingConfig | None = None
        self._min_samples: int = 3
        self._wue_min: float = 100.0
        self._wue_max: float = 250.0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        *,
        wue_table_snapshot: TablePageSnapshot,
        gating_config: SampleGatingConfig | None = None,
        lambda_target: float = 1.0,
        lambda_target_snapshot: TablePageSnapshot | None = None,
        min_samples_for_correction: int = 3,
        wue_min: float = 100.0,
        wue_max: float = 250.0,
    ) -> None:
        """Start (or restart) the live session.

        Uses ``wue_default_gating_config()`` when *gating_config* is None,
        which disables minCltFilter so cold-start samples are accepted.
        """
        self._accumulator = WueAnalyzeAccumulator(gate_service=self._gate_service)
        self._wue_table_snapshot = wue_table_snapshot
        self._gating_config = gating_config if gating_config is not None else wue_default_gating_config()
        self._lambda_target = lambda_target
        self._lambda_target_snapshot = lambda_target_snapshot
        self._min_samples = min_samples_for_correction
        self._wue_min = wue_min
        self._wue_max = wue_max

    def reset(self) -> None:
        """Stop the session and clear all accumulated data."""
        if self._accumulator is not None:
            self._accumulator.reset()
        self._accumulator = None
        self._wue_table_snapshot = None

    @property
    def is_active(self) -> bool:
        return self._accumulator is not None and self._wue_table_snapshot is not None

    # ------------------------------------------------------------------
    # Feed interface
    # ------------------------------------------------------------------

    def feed_runtime(self, runtime_snapshot: OutputChannelSnapshot) -> bool:
        """Feed one live runtime snapshot into the accumulator.

        Returns True if the sample was accepted into a CLT row.
        """
        if not self.is_active:
            return False
        assert self._accumulator is not None
        assert self._wue_table_snapshot is not None

        record = _runtime_to_record(runtime_snapshot)
        return self._accumulator.add_record(
            record,
            self._wue_table_snapshot,
            gating_config=self._gating_config,
            lambda_target=self._lambda_target,
            lambda_target_snapshot=self._lambda_target_snapshot,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_summary(self) -> WueAnalysisSummary | None:
        """Return the current accumulated analysis, or None if not active."""
        if not self.is_active:
            return None
        assert self._accumulator is not None
        assert self._wue_table_snapshot is not None
        return self._accumulator.snapshot(
            self._wue_table_snapshot,
            min_samples_for_correction=self._min_samples,
            wue_min=self._wue_min,
            wue_max=self._wue_max,
        )

    def status_snapshot(self) -> LiveWueAnalyzeSessionSnapshot:
        """Return a lightweight status snapshot for UI display."""
        if not self.is_active or self._accumulator is None:
            return LiveWueAnalyzeSessionSnapshot(
                is_active=False,
                accepted_count=0,
                rejected_count=0,
                total_count=0,
                status_text="WUE Analyze: inactive.",
            )
        accepted = self._accumulator.accepted_count
        rejected = self._accumulator.rejected_count
        total = accepted + rejected
        return LiveWueAnalyzeSessionSnapshot(
            is_active=True,
            accepted_count=accepted,
            rejected_count=rejected,
            total_count=total,
            status_text=(
                f"WUE Analyze live: {accepted} accepted / {rejected} rejected "
                f"of {total} frame(s)."
            ),
        )


# ---------------------------------------------------------------------------
# Conversion helper
# ---------------------------------------------------------------------------


def _runtime_to_record(snapshot: OutputChannelSnapshot) -> DataLogRecord:
    return DataLogRecord(
        timestamp=snapshot.timestamp,
        values=snapshot.as_dict(),
    )
