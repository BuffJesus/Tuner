from __future__ import annotations

from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.staged_change_service import StagedChangeService


def test_summarize_lists_staged_values() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[1.0, 2.0, 3.0, 4.0])])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    edit_service.stage_list_cell("veTable", 0, "9.5")

    entries = StagedChangeService().summarize(edit_service)

    assert len(entries) == 1
    assert entries[0].name == "veTable"
    assert "9.5" in entries[0].preview


def test_summarize_includes_before_page_and_written_state() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    edit_service.stage_scalar_value("reqFuel", "9.2")

    entries = StagedChangeService().summarize(
        edit_service,
        page_titles={"reqFuel": "Engine Constants"},
        written_names={"reqFuel"},
    )

    assert len(entries) == 1
    assert entries[0].before_preview == "8.5"
    assert entries[0].page_title == "Engine Constants"
    assert entries[0].is_written is True
