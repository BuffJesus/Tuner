from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.dashboard import DashboardLayout, DashboardWidget, GaugeColorZone
from tuner.domain.ecu_definition import GaugeConfiguration

# Default Speeduino gauge cluster — channels match the Speeduino OutputChannels section.
_DEFAULT_SPEEDUINO_WIDGETS: list[dict] = [
    # Row 0–1 col 0–1: RPM dial (2×2 — needs square space to render properly)
    {
        "widget_id": "rpm",
        "kind": "dial",
        "title": "RPM",
        "source": "rpm",
        "units": "rpm",
        "x": 0, "y": 0, "width": 2, "height": 2,
        "min_value": 0, "max_value": 8000,
        "color_zones": [
            {"lo": 0,    "hi": 3000, "color": "ok"},
            {"lo": 3000, "hi": 6500, "color": "warning"},
            {"lo": 6500, "hi": 8000, "color": "danger"},
        ],
    },
    # Row 0–1 col 2–3: MAP dial (2×2)
    {
        "widget_id": "map",
        "kind": "dial",
        "title": "MAP",
        "source": "map",
        "units": "kPa",
        "x": 2, "y": 0, "width": 2, "height": 2,
        "min_value": 10, "max_value": 260,
        "color_zones": [],
    },
    # Row 2 — numeric readouts
    {
        "widget_id": "tps",
        "kind": "bar",
        "title": "TPS",
        "source": "tps",
        "units": "%",
        "x": 0, "y": 2, "width": 2, "height": 1,
        "min_value": 0, "max_value": 100,
        "color_zones": [],
    },
    {
        "widget_id": "afr",
        "kind": "number",
        "title": "AFR",
        "source": "afr",
        "units": "λ",
        "x": 2, "y": 2, "width": 1, "height": 1,
        "min_value": 0, "max_value": 20,
        "color_zones": [],
    },
    {
        "widget_id": "advance",
        "kind": "number",
        "title": "Advance",
        "source": "advance",
        "units": "°",
        "x": 3, "y": 2, "width": 1, "height": 1,
        "min_value": -20, "max_value": 60,
        "color_zones": [],
    },
    # Row 3 — temperatures + battery
    {
        "widget_id": "coolant",
        "kind": "number",
        "title": "Coolant",
        "source": "coolantRaw",
        "units": "°C",
        "x": 0, "y": 3, "width": 1, "height": 1,
        "min_value": -40, "max_value": 130,
        "color_zones": [
            {"lo": 90,  "hi": 110, "color": "warning"},
            {"lo": 110, "hi": 130, "color": "danger"},
        ],
    },
    {
        "widget_id": "iat",
        "kind": "number",
        "title": "IAT",
        "source": "iatRaw",
        "units": "°C",
        "x": 1, "y": 3, "width": 1, "height": 1,
        "min_value": -40, "max_value": 80,
        "color_zones": [],
    },
    {
        "widget_id": "battery",
        "kind": "number",
        "title": "Battery",
        "source": "batteryVoltage",
        "units": "V",
        "x": 2, "y": 3, "width": 1, "height": 1,
        "min_value": 8, "max_value": 16,
        "color_zones": [
            {"lo": 8,  "hi": 11, "color": "danger"},
            {"lo": 11, "hi": 12, "color": "warning"},
        ],
    },
    {
        "widget_id": "ve",
        "kind": "number",
        "title": "VE",
        "source": "VE1",
        "units": "%",
        "x": 3, "y": 3, "width": 1, "height": 1,
        "min_value": 0, "max_value": 150,
        "color_zones": [],
    },
    {
        "widget_id": "dwell",
        "kind": "number",
        "title": "Dwell",
        "source": "dwell",
        "units": "ms",
        "x": 0, "y": 4, "width": 1, "height": 1,
        "min_value": 0, "max_value": 10,
        "color_zones": [],
    },
    {
        "widget_id": "pw1",
        "kind": "number",
        "title": "PW1",
        "source": "pulseWidth",
        "units": "ms",
        "x": 1, "y": 4, "width": 1, "height": 1,
        "min_value": 0, "max_value": 30,
        "color_zones": [],
    },
]


class DashboardLayoutService:
    def default_layout(
        self,
        name: str = "Speeduino",
        gauge_configurations: list[GaugeConfiguration] | None = None,
        front_page_gauges: list[str] | None = None,
    ) -> DashboardLayout:
        """Build the default dashboard layout.

        When *gauge_configurations* and *front_page_gauges* are both supplied
        (i.e. an INI has been loaded) the layout is seeded from the INI-defined
        front-page gauge order and each gauge's min/max/warn/danger thresholds.
        Falls back to the hardcoded Speeduino defaults when INI data is absent.
        """
        if gauge_configurations and front_page_gauges:
            widgets = self._widgets_from_ini(gauge_configurations, front_page_gauges)
            if widgets:
                return DashboardLayout(name=name, widgets=widgets)
        widgets = [self._widget_from_dict(d) for d in _DEFAULT_SPEEDUINO_WIDGETS]
        return DashboardLayout(name=name, widgets=widgets)

    # ------------------------------------------------------------------
    # INI-seeded layout helpers
    # ------------------------------------------------------------------

    def _widgets_from_ini(
        self,
        gauge_configurations: list[GaugeConfiguration],
        front_page_gauges: list[str],
    ) -> list[DashboardWidget]:
        """Convert front-page gauge slots to DashboardWidget instances.

        The first two populated slots become 2×2 dials; the remaining slots
        become 1×1 numeric readouts arranged in a 4-column grid starting at row 2.
        """
        gc_by_name = {gc.name: gc for gc in gauge_configurations}
        widgets: list[DashboardWidget] = []
        dial_idx = 0
        num_col = 0
        num_row = 2  # below the two 2×2 dials

        for gauge_name in front_page_gauges[:8]:
            if not gauge_name:
                continue
            gc = gc_by_name.get(gauge_name)
            if gc is None:
                continue
            lo = gc.lo if gc.lo is not None else 0.0
            hi = gc.hi if gc.hi is not None else 100.0
            zones = self._zones_from_gauge_config(gc, lo, hi)

            if dial_idx < 2:
                widget = DashboardWidget(
                    widget_id=gc.name,
                    kind="dial",
                    title=gc.title,
                    source=gc.channel,
                    units=gc.units,
                    x=float(dial_idx * 2), y=0.0,
                    width=2.0, height=2.0,
                    min_value=lo, max_value=hi,
                    color_zones=zones,
                )
                dial_idx += 1
            else:
                widget = DashboardWidget(
                    widget_id=gc.name,
                    kind="number",
                    title=gc.title,
                    source=gc.channel,
                    units=gc.units,
                    x=float(num_col), y=float(num_row),
                    width=1.0, height=1.0,
                    min_value=lo, max_value=hi,
                    color_zones=zones,
                )
                num_col += 1
                if num_col >= 4:
                    num_col = 0
                    num_row += 1

            widgets.append(widget)

        return widgets

    @staticmethod
    def _zones_from_gauge_config(
        gc: GaugeConfiguration, lo: float, hi: float
    ) -> list[GaugeColorZone]:
        """Derive color zones from INI warn/danger thresholds.

        Zone priority (matches TunerStudio convention):
        - danger below lo_danger or above hi_danger
        - warning between lo_danger/lo_warn or hi_warn/hi_danger
        - ok between lo_warn and hi_warn (only emitted when at least one warn threshold exists)
        """
        zones: list[GaugeColorZone] = []
        # Low danger
        if gc.lo_danger is not None and gc.lo_danger > lo:
            zones.append(GaugeColorZone(lo=lo, hi=gc.lo_danger, color="danger"))
        # Low warning
        if gc.lo_warn is not None:
            warn_start = gc.lo_danger if gc.lo_danger is not None else lo
            if warn_start < gc.lo_warn:
                zones.append(GaugeColorZone(lo=warn_start, hi=gc.lo_warn, color="warning"))
        # OK (only when at least one warn threshold is defined)
        if gc.lo_warn is not None or gc.hi_warn is not None:
            ok_lo = gc.lo_warn if gc.lo_warn is not None else lo
            ok_hi = gc.hi_warn if gc.hi_warn is not None else hi
            if ok_lo < ok_hi:
                zones.append(GaugeColorZone(lo=ok_lo, hi=ok_hi, color="ok"))
        # High warning
        if gc.hi_warn is not None:
            warn_end = gc.hi_danger if gc.hi_danger is not None else hi
            if gc.hi_warn < warn_end:
                zones.append(GaugeColorZone(lo=gc.hi_warn, hi=warn_end, color="warning"))
        # High danger
        if gc.hi_danger is not None and gc.hi_danger < hi:
            zones.append(GaugeColorZone(lo=gc.hi_danger, hi=hi, color="danger"))
        return zones

    def load(self, path: Path) -> DashboardLayout:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("name", path.stem)
        widgets = [self._widget_from_dict(w) for w in data.get("widgets", [])]
        return DashboardLayout(name=name, widgets=widgets)

    def save(self, path: Path, layout: DashboardLayout) -> None:
        data = {
            "name": layout.name,
            "widgets": [self._widget_to_dict(w) for w in layout.widgets],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _widget_from_dict(d: dict) -> DashboardWidget:
        zones = [
            GaugeColorZone(lo=z["lo"], hi=z["hi"], color=z["color"])
            for z in d.get("color_zones", [])
        ]
        return DashboardWidget(
            widget_id=d["widget_id"],
            kind=d.get("kind", "number"),
            title=d.get("title", d["widget_id"]),
            source=d.get("source"),
            units=d.get("units"),
            x=float(d.get("x", 0)),
            y=float(d.get("y", 0)),
            width=float(d.get("width", 1)),
            height=float(d.get("height", 1)),
            min_value=float(d.get("min_value", 0)),
            max_value=float(d.get("max_value", 100)),
            color_zones=zones,
            tune_page=d.get("tune_page"),
            text=d.get("text"),
        )

    @staticmethod
    def _widget_to_dict(w: DashboardWidget) -> dict:
        d: dict = {
            "widget_id": w.widget_id,
            "kind": w.kind,
            "title": w.title,
            "source": w.source,
            "units": w.units,
            "x": w.x,
            "y": w.y,
            "width": w.width,
            "height": w.height,
            "min_value": w.min_value,
            "max_value": w.max_value,
            "color_zones": [
                {"lo": z.lo, "hi": z.hi, "color": z.color}
                for z in w.color_zones
            ],
        }
        if w.tune_page is not None:
            d["tune_page"] = w.tune_page
        if w.text is not None:
            d["text"] = w.text
        return d
