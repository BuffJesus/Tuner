"""Tests for LiveVeAnalyzeSessionService.

Covers:
- Session starts inactive; feed_runtime is a no-op
- start() activates the session
- feed_runtime() converts OutputChannelSnapshot → DataLogRecord and routes through accumulator
- Accepted / rejected counts tracked correctly
- get_summary() returns VeAnalysisSummary matching batch results
- reset() deactivates session and clears data
- start() on an active session restarts cleanly
- status_snapshot() text reflects live state
- Per-cell lambda target snapshot wired through correctly
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.live_ve_analyze_session_service import LiveVeAnalyzeSessionService
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import VeAnalyzeCellHitService
from tuner.domain.datalog import DataLog, DataLogRecord

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())


def _snap(
    cells: list[list[str]] | None = None,
    x_labels: tuple[str, ...] = ("500", "1000", "1500"),
    y_labels: tuple[str, ...] = ("30", "60"),
) -> TablePageSnapshot:
    if cells is None:
        cells = [["50", "55", "60"], ["65", "70", "75"]]
    return TablePageSnapshot(
        page_id="table-editor:ve", group_id="fuel", title="VE Table",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name="rpmBins", y_parameter_name="loadBins",
        x_labels=x_labels, y_labels=y_labels,
        table_model=TableViewModel(rows=2, columns=3, cells=cells),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )


def _runtime(rpm: float, map_: float, lambda_: float | None = None, afr: float | None = None) -> OutputChannelSnapshot:
    values = [
        OutputChannelValue(name="rpm", value=rpm),
        OutputChannelValue(name="map", value=map_),
    ]
    if lambda_ is not None:
        values.append(OutputChannelValue(name="lambda", value=lambda_))
    if afr is not None:
        values.append(OutputChannelValue(name="afr", value=afr))
    return OutputChannelSnapshot(timestamp=_NOW, values=values)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def test_session_starts_inactive() -> None:
    svc = LiveVeAnalyzeSessionService()
    assert not svc.is_active
    assert svc.get_summary() is None


def test_feed_noop_when_inactive() -> None:
    svc = LiveVeAnalyzeSessionService()
    accepted = svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.0))
    assert not accepted
    assert svc.get_summary() is None


def test_start_activates_session() -> None:
    svc = LiveVeAnalyzeSessionService()
    svc.start(ve_table_snapshot=_snap())
    assert svc.is_active


def test_reset_deactivates() -> None:
    svc = LiveVeAnalyzeSessionService()
    svc.start(ve_table_snapshot=_snap())
    svc.reset()
    assert not svc.is_active
    assert svc.get_summary() is None


def test_start_restarts_clears_data() -> None:
    svc = LiveVeAnalyzeSessionService()
    snap = _snap()
    svc.start(ve_table_snapshot=snap, gating_config=_NO_GATE)
    svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.1))
    svc.start(ve_table_snapshot=snap, gating_config=_NO_GATE)  # restart
    summary = svc.get_summary()
    assert summary is not None
    assert summary.accepted_records == 0


# ---------------------------------------------------------------------------
# Feeding records
# ---------------------------------------------------------------------------

def test_accepted_record_increments_count() -> None:
    svc = LiveVeAnalyzeSessionService()
    svc.start(ve_table_snapshot=_snap(), gating_config=_NO_GATE)
    accepted = svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.0))
    assert accepted
    summary = svc.get_summary()
    assert summary is not None
    assert summary.accepted_records == 1
    assert summary.rejected_records == 0


def test_rejected_record_tracked() -> None:
    svc = LiveVeAnalyzeSessionService()
    svc.start(ve_table_snapshot=_snap(), gating_config=_NO_GATE)
    # No lambda → rejected by no_lambda_channel gate path
    rejected = svc.feed_runtime(
        OutputChannelSnapshot(
            timestamp=_NOW,
            values=[OutputChannelValue(name="rpm", value=900.0)],
        )
    )
    assert not rejected
    summary = svc.get_summary()
    assert summary is not None
    assert summary.rejected_records == 1


def test_multiple_frames_accumulate() -> None:
    svc = LiveVeAnalyzeSessionService()
    snap = _snap()
    svc.start(ve_table_snapshot=snap, gating_config=_NO_GATE, min_samples_for_correction=1)
    for _ in range(5):
        svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.0))
    summary = svc.get_summary()
    assert summary is not None
    assert summary.accepted_records == 5
    assert len(summary.cell_corrections) == 1
    assert summary.cell_corrections[0].sample_count == 5


# ---------------------------------------------------------------------------
# Correction factor accuracy
# ---------------------------------------------------------------------------

def test_live_correction_matches_batch_analysis() -> None:
    """Feeding records one at a time via live session should match batch service."""
    snap = _snap()
    records = [
        _runtime(900.0, 45.0, lambda_=1.1),
        _runtime(920.0, 45.0, lambda_=0.9),
        _runtime(1100.0, 55.0, lambda_=1.05),
    ]

    # Live session
    session = LiveVeAnalyzeSessionService()
    session.start(ve_table_snapshot=snap, gating_config=_NO_GATE, min_samples_for_correction=1)
    for r in records:
        session.feed_runtime(r)
    live_summary = session.get_summary()
    assert live_summary is not None

    # Batch service
    log = DataLog(name="t", records=[
        DataLogRecord(timestamp=r.timestamp, values=r.as_dict()) for r in records
    ])
    batch_summary = VeAnalyzeCellHitService().analyze(
        log=log, ve_table_snapshot=snap,
        gating_config=_NO_GATE, min_samples_for_correction=1,
    )

    assert live_summary.accepted_records == batch_summary.accepted_records
    assert live_summary.cells_with_data == batch_summary.cells_with_data
    live_cfs = {(c.row_index, c.col_index): c.mean_correction_factor for c in live_summary.cell_corrections}
    batch_cfs = {(c.row_index, c.col_index): c.mean_correction_factor for c in batch_summary.cell_corrections}
    assert live_cfs == batch_cfs


# ---------------------------------------------------------------------------
# status_snapshot
# ---------------------------------------------------------------------------

def test_status_inactive() -> None:
    svc = LiveVeAnalyzeSessionService()
    snap = svc.status_snapshot()
    assert not snap.is_active
    assert "inactive" in snap.status_text.lower()


def test_status_active_reflects_counts() -> None:
    svc = LiveVeAnalyzeSessionService()
    svc.start(ve_table_snapshot=_snap(), gating_config=_NO_GATE)
    svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.0))
    snap = svc.status_snapshot()
    assert snap.is_active
    assert snap.accepted_count == 1
    assert "1" in snap.status_text


# ---------------------------------------------------------------------------
# Lambda target snapshot wiring
# ---------------------------------------------------------------------------

def test_per_cell_target_used_in_live_session() -> None:
    """Lambda target from the target snapshot should affect the correction factor."""
    ve_snap = _snap()
    # Target lambda = 0.9 (rich target) for all cells
    target_snap = _snap(cells=[["0.9", "0.9", "0.9"], ["0.9", "0.9", "0.9"]])

    svc = LiveVeAnalyzeSessionService()
    svc.start(
        ve_table_snapshot=ve_snap,
        gating_config=_NO_GATE,
        lambda_target=1.0,             # scalar fallback (should be overridden)
        lambda_target_snapshot=target_snap,
        min_samples_for_correction=1,
    )
    svc.feed_runtime(_runtime(900.0, 45.0, lambda_=1.0))
    summary = svc.get_summary()
    assert summary is not None
    # correction = measured(1.0) / target(0.9) ≈ 1.111
    import pytest
    cf = summary.cell_corrections[0].mean_correction_factor
    assert pytest.approx(cf, abs=0.01) == 1.0 / 0.9
