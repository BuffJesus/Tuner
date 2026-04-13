from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GaugeColorZone:
    lo: float
    hi: float
    color: str  # "ok", "warning", "danger"


@dataclass(slots=True)
class DashboardWidget:
    widget_id: str
    kind: str  # "number" | "bar" | "dial" | "led" | "label"
    title: str
    source: str | None = None  # output channel name
    units: str | None = None
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    min_value: float = 0.0
    max_value: float = 100.0
    color_zones: list[GaugeColorZone] = field(default_factory=list)
    tune_page: str | None = None  # page_id to navigate to in the tuning workspace
    # Phase 8 final — static text payload for "label" kind widgets
    # (TSDash DashLabel parity). Ignored by every other kind. None means
    # the widget falls back to ``title`` for display.
    text: str | None = None


@dataclass(slots=True)
class DashboardLayout:
    name: str
    widgets: list[DashboardWidget] = field(default_factory=list)
