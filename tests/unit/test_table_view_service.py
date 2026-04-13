from __future__ import annotations

from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.table_view_service import TableViewService


def test_build_table_model_uses_tune_shape() -> None:
    service = TableViewService()
    tune_value = TuneValue(name="veTable", value=[1.0, 2.0, 3.0, 4.0], rows=2, cols=2)

    model = service.build_table_model(tune_value)

    assert model is not None
    assert model.rows == 2
    assert model.columns == 2
    assert model.cells == [["1.0", "2.0"], ["3.0", "4.0"]]


def test_build_table_model_can_use_catalog_shape() -> None:
    service = TableViewService()
    tune_value = TuneValue(name="veTable", value=[1.0, 2.0, 3.0, 4.0])

    model = service.build_table_model(tune_value, "2x2")

    assert model is not None
    assert model.cells == [["1.0", "2.0"], ["3.0", "4.0"]]


def test_find_tune_value_searches_constants_and_pc_variables() -> None:
    service = TableViewService()
    tune_file = TuneFile(
        constants=[TuneValue(name="veTable", value=[1.0])],
        pc_variables=[TuneValue(name="status1", value="ok")],
    )

    assert service.find_tune_value(tune_file, "veTable") is not None
    assert service.find_tune_value(tune_file, "status1") is not None
