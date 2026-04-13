from __future__ import annotations

from datetime import UTC, datetime

from tuner.services.evidence_replay_comparison_service import EvidenceReplayComparisonService
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot


def _snapshot(*, rpm: float, map_kpa: float, advance: float = 14.0) -> EvidenceReplaySnapshot:
    return EvidenceReplaySnapshot(
        captured_at=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        session_state="connected",
        connection_text="Connection  connected",
        source_text="Source  ECU RAM",
        sync_summary_text="Sync  clean",
        sync_mismatch_details=(),
        staged_summary_text="1 staged change across the workspace.",
        operation_summary_text="Evidence summary.",
        operation_session_count=1,
        latest_write_text=None,
        latest_burn_text=None,
        runtime_summary_text="Runtime  3 channel(s)",
        runtime_channel_count=3,
        runtime_age_seconds=2.0,
        runtime_channels=(
            EvidenceReplayChannel(name="rpm", value=rpm, units="rpm"),
            EvidenceReplayChannel(name="map", value=map_kpa, units="kPa"),
            EvidenceReplayChannel(name="advance", value=advance, units="deg"),
        ),
        evidence_summary_text="Captured replay bundle.",
    )


def test_evidence_replay_comparison_service_reports_relevant_channel_deltas() -> None:
    comparison = EvidenceReplayComparisonService().build(
        baseline_snapshot=_snapshot(rpm=900.0, map_kpa=40.0),
        current_snapshot=_snapshot(rpm=1100.0, map_kpa=48.0),
        relevant_channel_names=("rpm", "map"),
    )

    assert comparison is not None
    assert [item.name for item in comparison.changed_channels] == ["rpm", "map"]
    assert "rpm +200.0 rpm" in comparison.detail_text
    assert "map +8.0 kPa" in comparison.detail_text


def test_evidence_replay_comparison_service_returns_none_for_identical_snapshots() -> None:
    snapshot = _snapshot(rpm=900.0, map_kpa=40.0)

    comparison = EvidenceReplayComparisonService().build(
        baseline_snapshot=snapshot,
        current_snapshot=snapshot,
        relevant_channel_names=("rpm",),
    )

    assert comparison is None
