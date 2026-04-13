from __future__ import annotations

from tuner.services.table_rendering_service import TableRenderingService
from tuner.services.table_view_service import TableViewModel


def test_table_rendering_service_reverses_y_axis_and_applies_gradient() -> None:
    service = TableRenderingService()
    model = TableViewModel(
        rows=2,
        columns=2,
        cells=[["10.0", "20.0"], ["30.0", "40.0"]],
    )

    rendered = service.build_render_model(
        model,
        x_labels=("500", "1000"),
        y_labels=("30", "60"),
    )

    assert rendered.y_labels == ("60", "30")
    assert rendered.row_index_map == (1, 0)
    assert rendered.cells[0][0].text == "30.0"
    assert rendered.cells[0][0].background_hex != rendered.cells[1][0].background_hex
