from __future__ import annotations

from tuner.services.operation_evidence_service import OperationEvidenceService
from tuner.services.operation_log_service import OperationLogService


def test_operation_evidence_service_reports_pending_unwritten_stage() -> None:
    log = OperationLogService()
    log.record_staged("reqFuel", "8.5", "9.2", "Engine")

    snapshot = OperationEvidenceService().build(
        entries=log.entries(),
        has_unwritten=True,
    )

    assert snapshot.session_count == 1
    assert snapshot.latest_write_entry is None
    assert snapshot.latest_burn_entry is None
    assert "unwritten staged changes" in snapshot.summary_text
    assert "Recent operations:" in snapshot.summary_text


def test_operation_evidence_service_reports_last_write_and_burn() -> None:
    log = OperationLogService()
    log.record_staged("reqFuel", "8.5", "9.2", "Engine")
    log.record_written("reqFuel", "9.2", "Engine")
    log.record_burned("reqFuel", "9.2", "Engine")

    snapshot = OperationEvidenceService().build(
        entries=log.entries(),
        has_unwritten=False,
    )

    assert snapshot.session_count == 1
    assert snapshot.latest_write_entry is not None
    assert snapshot.latest_burn_entry is not None
    assert "Last write:" in snapshot.summary_text
    assert "Last burn:" in snapshot.summary_text
    assert "burned; verify persisted values" in snapshot.summary_text


def test_operation_evidence_service_starts_new_session_after_burn() -> None:
    log = OperationLogService()
    log.record_staged("reqFuel", "8.5", "9.2", "Engine")
    log.record_written("reqFuel", "9.2", "Engine")
    log.record_burned("reqFuel", "9.2", "Engine")
    log.record_staged("sparkDur", "1.0", "1.2", "Ignition")

    snapshot = OperationEvidenceService().build(
        entries=log.entries(),
        has_unwritten=True,
    )

    assert snapshot.session_count == 2
    assert snapshot.active_session is not None
    assert snapshot.active_session.sequence == 2
    assert snapshot.active_session.entry_count == 1
    assert snapshot.active_session.has_burn is False
    assert "Active review session: #2" in snapshot.summary_text
