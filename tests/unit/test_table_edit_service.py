from __future__ import annotations

from tuner.services.table_edit_service import TableEditService, TableSelection


def test_table_edit_service_copy_paste_fill_interpolate_and_smooth() -> None:
    service = TableEditService()
    values = [10.0, 20.0, 30.0, 40.0]
    selection = TableSelection(top=0, left=0, bottom=1, right=1)

    copied = service.copy_region(values, 2, selection)
    assert copied == "10.0\t20.0\n30.0\t40.0"

    filled = service.fill_region(values, 2, selection, 50.0)
    assert filled == [50.0, 50.0, 50.0, 50.0]

    interpolated = service.interpolate_region([10.0, 40.0, 50.0, 80.0], 2, TableSelection(top=0, left=0, bottom=1, right=1))
    assert interpolated == [10.0, 40.0, 50.0, 80.0]

    smoothed = service.smooth_region([10.0, 20.0, 30.0, 40.0], 2, selection)
    assert smoothed[0] > 10.0

    pasted = service.paste_region([1.0, 2.0, 3.0, 4.0], 2, TableSelection(top=0, left=0, bottom=0, right=0), "9\t8")
    assert pasted == [9.0, 8.0, 3.0, 4.0]


def test_table_edit_service_fill_down_repeats_first_selected_row() -> None:
    service = TableEditService()

    filled = service.fill_down_region(
        [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        3,
        TableSelection(top=0, left=0, bottom=1, right=2),
    )

    assert filled == [10.0, 20.0, 30.0, 10.0, 20.0, 30.0]


def test_table_edit_service_fill_right_repeats_first_selected_column() -> None:
    service = TableEditService()

    filled = service.fill_right_region(
        [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
        3,
        TableSelection(top=0, left=0, bottom=1, right=2),
    )

    assert filled == [10.0, 10.0, 10.0, 40.0, 40.0, 40.0]


def test_table_edit_service_paste_tiles_clipboard_across_selection() -> None:
    service = TableEditService()

    pasted = service.paste_region(
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        3,
        TableSelection(top=0, left=0, bottom=1, right=2),
        "9\t8",
    )

    assert pasted == [9.0, 8.0, 9.0, 9.0, 8.0, 9.0]


def test_table_edit_service_interpolates_vertical_single_column_selection() -> None:
    service = TableEditService()

    interpolated = service.interpolate_region(
        [10.0, 20.0, 30.0, 40.0, 50.0, 90.0],
        2,
        TableSelection(top=0, left=1, bottom=2, right=1),
    )

    assert interpolated == [10.0, 20.0, 30.0, 55.0, 50.0, 90.0]
