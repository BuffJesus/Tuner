from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.domain.dashboard import DashboardWidget, GaugeColorZone
from tuner.ui.dashboard_panel import GaugeWidget, _DialFace


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _rpm_def(**overrides) -> DashboardWidget:
    defaults = dict(
        widget_id="rpm",
        kind="dial",
        title="RPM",
        source="rpm",
        units="rpm",
        min_value=0.0,
        max_value=8000.0,
        color_zones=[
            GaugeColorZone(lo=0,    hi=3000, color="ok"),
            GaugeColorZone(lo=3000, hi=6500, color="warning"),
            GaugeColorZone(lo=6500, hi=8000, color="danger"),
        ],
    )
    defaults.update(overrides)
    return DashboardWidget(**defaults)


# ---------------------------------------------------------------------------
# _DialFace unit tests
# ---------------------------------------------------------------------------

def test_dial_face_created_and_shown() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    assert dial.isVisible()


def test_dial_face_update_value_triggers_repaint() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    # Should not raise — value within range
    dial.update_value(3500.0)
    app.processEvents()


def test_dial_face_none_value_does_not_raise() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(None)
    app.processEvents()


def test_dial_face_clamped_over_max_does_not_raise() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(99999.0)
    app.processEvents()


def test_dial_face_clamped_under_min_does_not_raise() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(-500.0)
    app.processEvents()


def test_dial_face_zero_span_does_not_divide_by_zero() -> None:
    app = _app()
    # min == max → span = 0, must not raise ZeroDivisionError
    dial = _DialFace(_rpm_def(min_value=100.0, max_value=100.0))
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(100.0)
    app.processEvents()


def test_dial_face_update_def_changes_title() -> None:
    app = _app()
    dial = _DialFace(_rpm_def())
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_def(_rpm_def(title="Engine Speed"))
    assert dial._def.title == "Engine Speed"


def test_dial_face_no_color_zones_renders() -> None:
    app = _app()
    dial = _DialFace(_rpm_def(color_zones=[]))
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(4000.0)
    app.processEvents()


def test_dial_face_no_units_renders() -> None:
    app = _app()
    dial = _DialFace(_rpm_def(units=None))
    dial.resize(200, 200)
    dial.show()
    app.processEvents()
    dial.update_value(2000.0)
    app.processEvents()


# ---------------------------------------------------------------------------
# GaugeWidget integration — dial kind
# ---------------------------------------------------------------------------

def test_gauge_widget_dial_kind_creates_dial_face() -> None:
    app = _app()
    widget = GaugeWidget(_rpm_def())
    widget.resize(200, 200)
    widget.show()
    app.processEvents()
    assert widget._dial is not None
    assert widget._value_label is None
    assert widget._bar is None


def test_gauge_widget_dial_update_value_delegates_to_dial() -> None:
    app = _app()
    widget = GaugeWidget(_rpm_def())
    widget.resize(200, 200)
    widget.show()
    app.processEvents()
    widget.update_value(5500.0)
    app.processEvents()
    assert widget._dial is not None
    assert widget._dial._value == 5500.0


def test_gauge_widget_dial_update_none_delegates_to_dial() -> None:
    app = _app()
    widget = GaugeWidget(_rpm_def())
    widget.resize(200, 200)
    widget.show()
    app.processEvents()
    widget.update_value(None)
    app.processEvents()
    assert widget._dial is not None
    assert widget._dial._value is None


def test_gauge_widget_number_kind_still_works() -> None:
    app = _app()
    def_ = DashboardWidget(widget_id="afr", kind="number", title="AFR", source="afr",
                           units="λ", min_value=0.0, max_value=20.0)
    widget = GaugeWidget(def_)
    widget.resize(160, 80)
    widget.show()
    app.processEvents()
    assert widget._dial is None
    assert widget._value_label is not None
    widget.update_value(14.7)
    app.processEvents()
    assert widget._value_label.text() == "14.7"


def test_gauge_widget_bar_kind_still_works() -> None:
    app = _app()
    def_ = DashboardWidget(widget_id="tps", kind="bar", title="TPS", source="tps",
                           units="%", min_value=0.0, max_value=100.0)
    widget = GaugeWidget(def_)
    widget.resize(200, 80)
    widget.show()
    app.processEvents()
    assert widget._dial is None
    assert widget._bar is not None
    widget.update_value(75.0)
    app.processEvents()
    assert widget._bar.value() == 750
