from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.operation_log_service import OperationKind, OperationLogService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


def _simple_presenter() -> TuningWorkspacePresenter:
    definition = EcuDefinition(
        name="Test",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0, units="ms")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    return presenter


def test_operation_log_service_records_staged() -> None:
    svc = OperationLogService()
    svc.record_staged("reqFuel", "8.5", "9.2", "Engine")
    entries = svc.entries()
    assert len(entries) == 1
    assert entries[0].kind == OperationKind.STAGED
    assert entries[0].parameter_name == "reqFuel"
    assert entries[0].old_value == "8.5"
    assert entries[0].new_value == "9.2"


def test_operation_log_service_clear_resets_log() -> None:
    svc = OperationLogService()
    svc.record_staged("x", "1", "2")
    svc.clear()
    assert svc.entries() == ()


def test_operation_log_service_summary_text_empty() -> None:
    svc = OperationLogService()
    assert "No operations" in svc.summary_text()


def test_operation_log_service_summary_text_shows_entries() -> None:
    svc = OperationLogService()
    svc.record_staged("reqFuel", "8.5", "9.2")
    svc.record_written("reqFuel", "9.2")
    text = svc.summary_text()
    assert "staged" in text
    assert "written" in text
    assert "reqFuel" in text


def test_presenter_logs_staged_change() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    log = presenter.operation_log_service
    entries = log.entries()
    assert len(entries) == 1
    assert entries[0].kind == OperationKind.STAGED
    assert entries[0].parameter_name == "reqFuel"


def test_presenter_logs_revert() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    presenter.revert_active_page()
    entries = presenter.operation_log_service.entries()
    assert any(e.kind == OperationKind.REVERTED for e in entries)


def test_presenter_write_active_page_logs_written() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    snapshot = presenter.write_active_page()
    entries = presenter.operation_log_service.entries()
    assert any(e.kind == OperationKind.WRITTEN for e in entries)
    assert snapshot.operation_log.entry_count >= 2
    assert snapshot.operation_log.session_count == 1
    assert snapshot.operation_log.latest_write_text is not None
    assert "written" in snapshot.operation_log.latest_write_text


def test_presenter_burn_active_page_logs_burned() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    presenter.write_active_page()
    snapshot = presenter.burn_active_page()
    entries = presenter.operation_log_service.entries()
    assert any(e.kind == OperationKind.BURNED for e in entries)
    assert not snapshot.operation_log.has_unwritten
    assert snapshot.operation_log.latest_burn_text is not None
    assert "burned" in snapshot.operation_log.latest_burn_text


def test_presenter_has_unwritten_after_stage() -> None:
    presenter = _simple_presenter()
    snapshot = presenter.stage_active_page_parameter("9.2")
    assert snapshot.operation_log.has_unwritten is True
    assert "Evidence summary:" in snapshot.operation_log.summary_text


def test_presenter_has_unwritten_cleared_after_write() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    snapshot = presenter.write_active_page()
    assert snapshot.operation_log.has_unwritten is False


def test_presenter_log_cleared_on_load() -> None:
    presenter = _simple_presenter()
    presenter.stage_active_page_parameter("9.2")
    assert len(presenter.operation_log_service.entries()) == 1
    definition = EcuDefinition(
        name="Test",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=0)],
    )
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    presenter.load(definition, tune_file)
    assert len(presenter.operation_log_service.entries()) == 0
