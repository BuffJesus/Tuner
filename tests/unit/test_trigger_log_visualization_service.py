from __future__ import annotations

from tuner.services.trigger_log_visualization_service import TriggerLogVisualizationService


def test_build_from_rows_creates_offset_numeric_traces() -> None:
    snapshot = TriggerLogVisualizationService().build_from_rows(
        [
            {"timeMs": "0.0", "crank": "0", "cam": "1"},
            {"timeMs": "1.0", "crank": "1", "cam": "0"},
            {"timeMs": "2.0", "crank": "0", "cam": "1"},
        ],
        columns=("timeMs", "crank", "cam"),
    )

    assert snapshot.trace_count == 2
    assert snapshot.point_count == 3
    assert snapshot.summary_text.startswith("Visualization:")
    assert snapshot.traces[0].name == "crank"
    assert snapshot.traces[0].x_values == (0.0, 1.0, 2.0)
    assert snapshot.traces[0].is_digital is True
    assert snapshot.traces[1].offset > snapshot.traces[0].offset
    assert any("rising" in annotation.label or "falling" in annotation.label for annotation in snapshot.annotations)


def test_build_from_rows_requires_time_column() -> None:
    snapshot = TriggerLogVisualizationService().build_from_rows(
        [{"crank": "0"}, {"crank": "1"}],
        columns=("crank",),
    )

    assert snapshot.trace_count == 0
    assert "time column" in snapshot.summary_text.lower()


def test_build_from_rows_ignores_non_numeric_signal_columns() -> None:
    snapshot = TriggerLogVisualizationService().build_from_rows(
        [
            {"timeMs": "0.0", "state": "sync", "crank": "0"},
            {"timeMs": "1.0", "state": "sync", "crank": "1"},
        ],
        columns=("timeMs", "state", "crank"),
    )

    assert snapshot.trace_count == 1
    assert snapshot.traces[0].name == "crank"


def test_build_from_rows_marks_possible_missing_tooth_gap() -> None:
    snapshot = TriggerLogVisualizationService().build_from_rows(
        [
            {"timeMs": "0.0", "tooth": "1"},
            {"timeMs": "1.0", "tooth": "1"},
            {"timeMs": "2.0", "tooth": "1"},
            {"timeMs": "4.0", "tooth": "1"},
            {"timeMs": "5.0", "tooth": "1"},
            {"timeMs": "6.0", "tooth": "1"},
        ],
        columns=("timeMs", "tooth"),
    )

    assert any(annotation.label == "Possible missing-tooth gap" for annotation in snapshot.annotations)
    assert "annotation" in snapshot.summary_text.lower()
