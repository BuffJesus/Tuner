from __future__ import annotations

from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService


def test_stage_list_cell_updates_staged_copy_without_touching_base() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2)])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    service.stage_list_cell("veTable", 1, "9.5")

    assert tune_file.constants[0].value == [1.0, 2.0, 3.0, 4.0]
    staged = service.get_value("veTable")
    assert staged is not None
    assert staged.value == [1.0, 9.5, 3.0, 4.0]
    assert service.is_dirty("veTable") is True


def test_revert_clears_staged_value() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="rpmBins", value=[500.0, 1000.0])])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)
    service.stage_list_cell("rpmBins", 0, "750")

    service.revert("rpmBins")

    restored = service.get_value("rpmBins")
    assert restored is not None
    assert restored.value == [500.0, 1000.0]
    assert service.is_dirty("rpmBins") is False


def test_stage_scalar_value_updates_staged_copy_without_touching_base() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5, units="ms")])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    service.stage_scalar_value("reqFuel", "9.1")

    assert tune_file.constants[0].value == 8.5
    staged = service.get_value("reqFuel")
    assert staged is not None
    assert staged.value == 9.1
    assert service.is_dirty("reqFuel") is True


def test_replace_list_supports_undo_and_redo() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2)])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    service.replace_list("veTable", [1.0, 9.0, 3.0, 4.0])
    service.undo("veTable")

    assert service.get_value("veTable") is not None
    assert service.get_value("veTable").value == [1.0, 2.0, 3.0, 4.0]

    service.redo("veTable")

    assert service.get_value("veTable").value == [1.0, 9.0, 3.0, 4.0]


def test_stage_scalar_value_autocreates_missing_entry() -> None:
    """Parameters in the definition but absent from the tune should be auto-created."""
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.0)])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    # "knockThreshold" is not in the tune — should not raise
    service.stage_scalar_value("knockThreshold", "42.0")

    result = service.get_value("knockThreshold")
    assert result is not None
    assert result.value == 42.0
    assert service.is_dirty("knockThreshold") is True


def test_stage_scalar_value_autocreates_string_value() -> None:
    """Auto-create also works when the raw value is non-numeric (stored as string)."""
    tune_file = TuneFile(constants=[])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    service.stage_scalar_value("sensorMode", "2")

    result = service.get_value("sensorMode")
    assert result is not None
    assert result.value == 2.0


def test_stage_scalar_value_still_raises_for_list_backed_name() -> None:
    """A parameter backed by a list value (table) must still reject scalar staging."""
    import pytest
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[1.0, 2.0], rows=1, cols=2)])
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)

    with pytest.raises(KeyError, match="not a scalar-backed parameter"):
        service.stage_scalar_value("veTable", "5.0")
