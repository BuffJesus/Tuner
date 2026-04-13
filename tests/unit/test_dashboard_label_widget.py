"""Phase 8 final closeout — dashboard ``label`` widget kind (TSDash DashLabel parity).

Adds focused offscreen Qt coverage for the new static-text dashboard
widget kind. The label widget renders the operator-supplied ``text``
(or falls back to ``title``), ignores live value updates, and survives
the standard layout JSON round trip.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.domain.dashboard import DashboardLayout, DashboardWidget
from tuner.services.dashboard_layout_service import DashboardLayoutService
from tuner.ui.dashboard_panel import GaugeWidget


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _label(text: str | None = "Static Note", title: str = "Note") -> DashboardWidget:
    return DashboardWidget(
        widget_id="note", kind="label", title=title, text=text,
        x=0, y=0, width=2, height=1,
    )


# ---------------------------------------------------------------------------
# Domain field
# ---------------------------------------------------------------------------

class TestDomainField:
    def test_text_field_default_is_none(self) -> None:
        w = DashboardWidget(widget_id="x", kind="dial", title="X")
        assert w.text is None

    def test_text_field_round_trips_via_constructor(self) -> None:
        w = DashboardWidget(widget_id="x", kind="label", title="X", text="hello")
        assert w.text == "hello"


# ---------------------------------------------------------------------------
# GaugeWidget render path
# ---------------------------------------------------------------------------

class TestLabelRendering:
    def test_renders_text_field_when_present(self) -> None:
        _app()
        widget = GaugeWidget(_label(text="Track Day"))
        assert widget._label_widget is not None
        assert widget._label_widget.text() == "Track Day"

    def test_falls_back_to_title_when_text_is_none(self) -> None:
        _app()
        widget = GaugeWidget(_label(text=None, title="Sponsor Name"))
        assert widget._label_widget is not None
        assert widget._label_widget.text() == "Sponsor Name"

    def test_label_widget_ignores_value_updates(self) -> None:
        """Static labels never react to runtime telemetry."""
        _app()
        widget = GaugeWidget(_label(text="Pit Wall"))
        # Should not raise even though there's no _value_label or _dial.
        widget.update_value(123.0)
        widget.update_value(None)
        assert widget._label_widget is not None
        assert widget._label_widget.text() == "Pit Wall"

    def test_other_kinds_have_no_label_widget(self) -> None:
        _app()
        dial = GaugeWidget(DashboardWidget(
            widget_id="rpm", kind="dial", title="RPM", x=0, y=0,
        ))
        assert dial._label_widget is None
        number = GaugeWidget(DashboardWidget(
            widget_id="afr", kind="number", title="AFR", x=0, y=0,
        ))
        assert number._label_widget is None

    def test_update_def_can_swap_to_label_kind(self) -> None:
        """Reassigning the def to a label kind must rebuild the
        children without crashing."""
        _app()
        widget = GaugeWidget(DashboardWidget(
            widget_id="cell", kind="number", title="Cell", x=0, y=0,
        ))
        assert widget._label_widget is None
        widget.update_def(_label(text="Promoted"))
        assert widget._label_widget is not None
        assert widget._label_widget.text() == "Promoted"


# ---------------------------------------------------------------------------
# Layout JSON persistence
# ---------------------------------------------------------------------------

class TestLayoutPersistence:
    def test_label_widget_round_trips_through_json(self, tmp_path: Path) -> None:
        layout = DashboardLayout(
            name="Track",
            widgets=[
                _label(text="Sponsor: Bench Racing Co."),
                DashboardWidget(
                    widget_id="rpm", kind="dial", title="RPM",
                    source="rpm", units="rpm", x=0, y=1, width=2, height=2,
                    min_value=0, max_value=8000,
                ),
            ],
        )
        path = tmp_path / "layout.json"
        svc = DashboardLayoutService()
        svc.save(path, layout)

        # Sanity: text field made it into the JSON
        raw = json.loads(path.read_text(encoding="utf-8"))
        widgets = raw.get("widgets") or raw
        note_entry = next(
            w for w in widgets if w.get("widget_id") == "note"
        )
        assert note_entry.get("text") == "Sponsor: Bench Racing Co."

        reloaded = svc.load(path)
        note = next(w for w in reloaded.widgets if w.widget_id == "note")
        assert note.kind == "label"
        assert note.text == "Sponsor: Bench Racing Co."
