"""Tests for LiveWueAnalyzeSessionService.

Covers:
- Session starts inactive; feed_runtime is a no-op
- start() activates session and sets default WUE gating
- feed_runtime() converts OutputChannelSnapshot and routes to accumulator
- get_summary() returns WueAnalysisSummary
- reset() deactivates session and clears data
- status_snapshot() reflects live state
- Cold-CLT samples are accepted (minCltFilter excluded by default)
"""

from __future__ import annotations

from datetime import UTC, datetime

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.live_wue_analyze_session_service import LiveWueAnalyzeSessionService
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset({"_disabled_"}))


def _wue_snap() -> TablePageSnapshot:
    return TablePageSnapshot(
        page_id="wue", group_id="fuel", title="Warmup Enrichment",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="", validation_summary="", diff_summary="", diff_text="",
        diff_entries=(), axis_summary="", details_text="", help_topic=None,
        x_parameter_name=None, y_parameter_name="wueBins",
        x_labels=("1",), y_labels=("-40", "-26", "10", "28", "46", "64"),
        table_model=TableViewModel(rows=6, columns=1, cells=[
            ["180"], ["175"], ["168"], ["154"], ["134"], ["100"]
        ]),
        auxiliary_sections=(), can_undo=False, can_redo=False,
    )


def _runtime(clt: float, lambda_: float) -> OutputChannelSnapshot:
    return OutputChannelSnapshot(
        timestamp=_NOW,
        values=[
            OutputChannelValue(name="coolant", value=clt),
            OutputChannelValue(name="lambda", value=lambda_),
        ],
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_session_starts_inactive() -> None:
    svc = LiveWueAnalyzeSessionService()
    assert not svc.is_active
    assert svc.get_summary() is None


def test_feed_noop_when_inactive() -> None:
    svc = LiveWueAnalyzeSessionService()
    accepted = svc.feed_runtime(_runtime(clt=20.0, lambda_=1.0))
    assert not accepted


def test_start_activates_session() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap())
    assert svc.is_active


def test_feed_runtime_accepted() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap(), gating_config=_NO_GATE)
    accepted = svc.feed_runtime(_runtime(clt=10.0, lambda_=1.0))
    assert accepted


def test_feed_runtime_rejected_no_lambda() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap(), gating_config=_NO_GATE)
    snap = OutputChannelSnapshot(
        timestamp=_NOW,
        values=[OutputChannelValue(name="coolant", value=20.0)],
    )
    accepted = svc.feed_runtime(snap)
    assert not accepted


def test_get_summary_after_feed() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap(), gating_config=_NO_GATE)
    for _ in range(3):
        svc.feed_runtime(_runtime(clt=10.0, lambda_=1.1))
    summary = svc.get_summary()
    assert summary is not None
    assert summary.accepted_records == 3


def test_reset_clears_session() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap(), gating_config=_NO_GATE)
    svc.feed_runtime(_runtime(clt=10.0, lambda_=1.0))
    svc.reset()
    assert not svc.is_active
    assert svc.get_summary() is None


def test_status_snapshot_inactive() -> None:
    svc = LiveWueAnalyzeSessionService()
    status = svc.status_snapshot()
    assert not status.is_active
    assert "inactive" in status.status_text.lower()


def test_status_snapshot_active() -> None:
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap(), gating_config=_NO_GATE)
    svc.feed_runtime(_runtime(clt=10.0, lambda_=1.0))
    status = svc.status_snapshot()
    assert status.is_active
    assert status.accepted_count == 1
    assert status.total_count == 1


def test_default_gating_accepts_cold_clt() -> None:
    """Default WUE gating must accept cold-CLT samples (no minCltFilter)."""
    svc = LiveWueAnalyzeSessionService()
    svc.start(wue_table_snapshot=_wue_snap())  # no explicit gating_config → defaults
    # CLT = 10°C — would be rejected by minCltFilter if it were active
    accepted = svc.feed_runtime(_runtime(clt=10.0, lambda_=1.0))
    assert accepted


def test_restart_clears_previous_data() -> None:
    svc = LiveWueAnalyzeSessionService()
    snap = _wue_snap()
    svc.start(wue_table_snapshot=snap, gating_config=_NO_GATE)
    for _ in range(5):
        svc.feed_runtime(_runtime(clt=10.0, lambda_=1.0))
    # Restart
    svc.start(wue_table_snapshot=snap, gating_config=_NO_GATE)
    status = svc.status_snapshot()
    assert status.accepted_count == 0
    assert status.total_count == 0
