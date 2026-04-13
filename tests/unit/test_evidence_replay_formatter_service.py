from __future__ import annotations

import json
from datetime import UTC, datetime

from tuner.services.evidence_replay_formatter_service import EvidenceReplayFormatterService
from tuner.services.evidence_replay_service import EvidenceReplayChannel, EvidenceReplaySnapshot


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
        runtime_summary_text="Runtime  2 channel(s)",
        runtime_channel_count=2,
        runtime_age_seconds=4.0,
        runtime_channels=(
            EvidenceReplayChannel(name="rpm", value=950.0, units="rpm"),
            EvidenceReplayChannel(name="map", value=42.0, units="kPa"),
        ),
        evidence_summary_text="Captured: 2026-04-03T12:00:00+00:00\nRuntime channels captured: 2 (4s old)",
    )


def test_evidence_replay_formatter_service_formats_text() -> None:
    text = EvidenceReplayFormatterService().to_text(_snapshot())

    assert "Captured: 2026-04-03T12:00:00+00:00" in text
    assert "Runtime values:" in text
    assert "rpm = 950.0 rpm" in text
    assert "Latest write: 11:59:58  written  reqFuel = 9.2" in text


def test_evidence_replay_formatter_service_formats_json() -> None:
    payload = EvidenceReplayFormatterService().to_json(_snapshot())
    data = json.loads(payload)

    assert data["session_state"] == "connected"
    assert data["runtime_channel_count"] == 2
    assert data["runtime_channels"][0]["name"] == "rpm"
    assert data["captured_at"] == "2026-04-03T12:00:00+00:00"
