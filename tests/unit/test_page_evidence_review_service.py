from __future__ import annotations

from datetime import UTC, datetime

from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot
from tuner.services.page_evidence_review_service import PageEvidenceReviewService


def _snapshot() -> EvidenceReplaySnapshot:
    return EvidenceReplaySnapshot(
        captured_at=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        session_state="connected",
        connection_text="Connection  connected",
        source_text="Source  ECU RAM",
        sync_summary_text="Sync  clean",
        sync_mismatch_details=(),
        staged_summary_text="1 staged change across the workspace.",
        operation_summary_text="Evidence summary: latest staged work has been written to RAM but not burned.",
        operation_session_count=1,
        latest_write_text="11:59:58  written  reqFuel = 9.2",
        latest_burn_text=None,
        runtime_summary_text="Runtime  4 channel(s)",
        runtime_channel_count=4,
        runtime_age_seconds=4.0,
        runtime_channels=(
            EvidenceReplayChannel(name="rpm", value=950.0, units="rpm"),
            EvidenceReplayChannel(name="map", value=42.0, units="kPa"),
            EvidenceReplayChannel(name="advance", value=14.0, units="deg"),
            EvidenceReplayChannel(name="rSA_fullSync", value=1.0),
        ),
        evidence_summary_text="Captured replay bundle.",
    )


def test_page_evidence_review_service_matches_fuel_channels() -> None:
    review = PageEvidenceReviewService().build(
        page_title="VE Table",
        page_id="table-editor:ve",
        group_id="fuel",
        page_family_id="fuel-tables",
        parameter_names=("veTable", "veRpm", "veLoad"),
        evidence_hints=("veTable", "veRpm", "veLoad"),
        evidence_snapshot=_snapshot(),
    )

    assert review is not None
    assert [item.name for item in review.relevant_channels] == ["rpm", "map"]
    assert "VE Table" in review.summary_text


def test_page_evidence_review_service_matches_ignition_channels() -> None:
    review = PageEvidenceReviewService().build(
        page_title="Ignition Settings",
        page_id="dialog:ignitionOptions",
        group_id="hardware_setup",
        page_family_id=None,
        parameter_names=("sparkDur", "knock_mode"),
        evidence_hints=("sparkDur", "knock_mode"),
        evidence_snapshot=_snapshot(),
    )

    assert review is not None
    assert [item.name for item in review.relevant_channels] == ["rpm", "map", "advance", "rSA_fullSync"]
    assert "Latest write:" in review.detail_text


def test_page_evidence_review_service_uses_group_context_for_sensor_pages() -> None:
    review = PageEvidenceReviewService().build(
        page_title="Sensor Calibration",
        page_id="dialog:sensors",
        group_id="hardware_setup",
        page_family_id=None,
        parameter_names=("baroPin", "mapMax"),
        evidence_hints=("baroPin", "mapMax"),
        evidence_snapshot=_snapshot(),
    )

    assert review is not None
    assert [item.name for item in review.relevant_channels] == ["rpm", "map"]


def test_page_evidence_review_service_uses_page_family_for_generic_spark_tab() -> None:
    review = PageEvidenceReviewService().build(
        page_title="Primary",
        page_id="table-editor:sparkTable2",
        group_id="settings",
        page_family_id="spark-tables",
        parameter_names=(),
        evidence_hints=(),
        evidence_snapshot=_snapshot(),
    )

    assert review is not None
    assert [item.name for item in review.relevant_channels] == ["rpm", "map", "advance", "rSA_fullSync"]
