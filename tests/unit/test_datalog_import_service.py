from __future__ import annotations

from tuner.services.datalog_import_service import DatalogImportService


def test_datalog_import_service_loads_numeric_channels_and_time_ms(tmp_path) -> None:
    path = tmp_path / "session.csv"
    path.write_text(
        "timeMs,rpm,map,comment\n"
        "0,900,40,start\n"
        "500,1100,48,steady\n",
        encoding="utf-8",
    )

    snapshot = DatalogImportService().load_csv(path)

    assert snapshot.row_count == 2
    assert snapshot.channel_names == ("rpm", "map")
    assert snapshot.log.records[1].values["rpm"] == 1100.0
    assert snapshot.log.records[1].values["map"] == 48.0
    assert "Imported 2 datalog row(s)" in snapshot.summary_text


def test_datalog_import_service_rejects_csv_without_numeric_rows(tmp_path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text(
        "timeMs,comment\n"
        "0,start\n",
        encoding="utf-8",
    )

    try:
        DatalogImportService().load_csv(path)
    except ValueError as exc:
        assert "numeric replay rows" in str(exc)
    else:
        raise AssertionError("Expected load_csv() to reject a CSV without numeric replay rows.")
