from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.dashboard import DashboardLayout, DashboardWidget, GaugeColorZone
from tuner.domain.ecu_definition import GaugeConfiguration
from tuner.services.dashboard_layout_service import DashboardLayoutService


def test_default_layout_has_expected_channels() -> None:
    service = DashboardLayoutService()
    layout = service.default_layout()

    sources = {w.source for w in layout.widgets}
    assert "rpm" in sources
    assert "map" in sources
    assert "tps" in sources
    assert "afr" in sources
    assert "coolantRaw" in sources
    assert "iatRaw" in sources
    assert "batteryVoltage" in sources
    assert "advance" in sources


def test_default_layout_name() -> None:
    service = DashboardLayoutService()
    assert service.default_layout().name == "Speeduino"
    assert service.default_layout("MyLayout").name == "MyLayout"


def test_default_layout_rpm_is_dial() -> None:
    service = DashboardLayoutService()
    layout = service.default_layout()
    rpm = next(w for w in layout.widgets if w.source == "rpm")
    assert rpm.kind == "dial"
    assert rpm.max_value == 8000


def test_default_layout_rpm_has_color_zones() -> None:
    service = DashboardLayoutService()
    layout = service.default_layout()
    rpm = next(w for w in layout.widgets if w.source == "rpm")
    assert len(rpm.color_zones) > 0
    danger = [z for z in rpm.color_zones if z.color == "danger"]
    assert danger


def test_round_trip_save_load(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    original = service.default_layout("TestLayout")
    path = tmp_path / "test.dashboard.json"

    service.save(path, original)
    loaded = service.load(path)

    assert loaded.name == "TestLayout"
    assert len(loaded.widgets) == len(original.widgets)
    original_sources = {w.source for w in original.widgets}
    loaded_sources = {w.source for w in loaded.widgets}
    assert original_sources == loaded_sources


def test_save_produces_valid_json(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    layout = service.default_layout()
    path = tmp_path / "layout.json"
    service.save(path, layout)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "name" in data
    assert "widgets" in data
    assert isinstance(data["widgets"], list)
    assert len(data["widgets"]) == len(layout.widgets)


def test_load_preserves_min_max_values(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    layout = DashboardLayout(
        name="Custom",
        widgets=[
            DashboardWidget(
                widget_id="rpm",
                kind="bar",
                title="RPM",
                source="rpm",
                units="rpm",
                min_value=500,
                max_value=9500,
            )
        ],
    )
    path = tmp_path / "custom.json"
    service.save(path, layout)
    loaded = service.load(path)

    assert loaded.widgets[0].min_value == 500
    assert loaded.widgets[0].max_value == 9500


def test_load_preserves_color_zones(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    layout = DashboardLayout(
        name="Zones",
        widgets=[
            DashboardWidget(
                widget_id="coolant",
                kind="number",
                title="Coolant",
                source="coolantRaw",
                units="°C",
                color_zones=[
                    GaugeColorZone(lo=90, hi=110, color="warning"),
                    GaugeColorZone(lo=110, hi=130, color="danger"),
                ],
            )
        ],
    )
    path = tmp_path / "zones.json"
    service.save(path, layout)
    loaded = service.load(path)

    assert len(loaded.widgets[0].color_zones) == 2
    assert loaded.widgets[0].color_zones[0].color == "warning"
    assert loaded.widgets[0].color_zones[1].color == "danger"


def test_load_uses_path_stem_as_name_when_missing(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    path = tmp_path / "my_dash.json"
    path.write_text(json.dumps({"widgets": []}), encoding="utf-8")
    loaded = service.load(path)
    assert loaded.name == "my_dash"


def test_round_trip_preserves_tune_page(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    layout = DashboardLayout(
        name="WithTunePage",
        widgets=[
            DashboardWidget(
                widget_id="ve",
                kind="number",
                title="VE",
                source="VE1",
                tune_page="table-editor:veTable1Tbl",
            )
        ],
    )
    path = tmp_path / "tune_page.json"
    service.save(path, layout)
    loaded = service.load(path)
    assert loaded.widgets[0].tune_page == "table-editor:veTable1Tbl"


def test_tune_page_omitted_from_json_when_none(tmp_path: Path) -> None:
    service = DashboardLayoutService()
    layout = DashboardLayout(
        name="NoTunePage",
        widgets=[
            DashboardWidget(
                widget_id="rpm",
                kind="bar",
                title="RPM",
                source="rpm",
            )
        ],
    )
    path = tmp_path / "no_tune.json"
    service.save(path, layout)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "tune_page" not in data["widgets"][0]


def test_default_layout_has_no_tune_pages_set() -> None:
    service = DashboardLayoutService()
    layout = service.default_layout()
    assert all(w.tune_page is None for w in layout.widgets)


# ---------------------------------------------------------------------------
# INI-seeded default layout
# ---------------------------------------------------------------------------

def _make_gc(name: str, channel: str, title: str, units: str = "",
             lo: float = 0.0, hi: float = 100.0,
             hi_warn: float | None = None, hi_danger: float | None = None) -> GaugeConfiguration:
    return GaugeConfiguration(
        name=name, channel=channel, title=title, units=units,
        lo=lo, hi=hi, hi_warn=hi_warn, hi_danger=hi_danger,
    )


def test_ini_seeded_layout_uses_front_page_order() -> None:
    service = DashboardLayoutService()
    configs = [
        _make_gc("tachometer", "rpm", "RPM", "rpm", lo=0, hi=8000),
        _make_gc("mapGauge",   "map", "MAP", "kPa", lo=10, hi=260),
        _make_gc("throttle",   "tps", "TPS", "%",   lo=0,  hi=100),
    ]
    layout = service.default_layout(gauge_configurations=configs, front_page_gauges=["tachometer", "mapGauge", "throttle"])
    sources = [w.source for w in layout.widgets]
    assert sources == ["rpm", "map", "tps"]


def test_ini_seeded_layout_first_two_are_dials() -> None:
    service = DashboardLayoutService()
    configs = [
        _make_gc("tachometer", "rpm", "RPM", lo=0, hi=8000),
        _make_gc("mapGauge",   "map", "MAP", lo=10, hi=260),
        _make_gc("throttle",   "tps", "TPS", lo=0, hi=100),
    ]
    layout = service.default_layout(gauge_configurations=configs, front_page_gauges=["tachometer", "mapGauge", "throttle"])
    dials = [w for w in layout.widgets if w.kind == "dial"]
    nums  = [w for w in layout.widgets if w.kind == "number"]
    assert len(dials) == 2
    assert len(nums)  == 1
    assert dials[0].source == "rpm"
    assert dials[1].source == "map"


def test_ini_seeded_layout_dials_are_2x2() -> None:
    service = DashboardLayoutService()
    configs = [
        _make_gc("tachometer", "rpm", "RPM", lo=0, hi=8000),
        _make_gc("mapGauge",   "map", "MAP", lo=10, hi=260),
    ]
    layout = service.default_layout(gauge_configurations=configs, front_page_gauges=["tachometer", "mapGauge"])
    for w in layout.widgets:
        assert w.width == 2.0
        assert w.height == 2.0


def test_ini_seeded_layout_numbers_start_at_row2() -> None:
    service = DashboardLayoutService()
    configs = [
        _make_gc("tachometer", "rpm",  "RPM", lo=0, hi=8000),
        _make_gc("mapGauge",   "map",  "MAP", lo=10, hi=260),
        _make_gc("throttle",   "tps",  "TPS", lo=0, hi=100),
        _make_gc("afrGauge",   "afr",  "AFR", lo=10, hi=20),
    ]
    layout = service.default_layout(
        gauge_configurations=configs,
        front_page_gauges=["tachometer", "mapGauge", "throttle", "afrGauge"],
    )
    numbers = [w for w in layout.widgets if w.kind == "number"]
    assert all(w.y >= 2.0 for w in numbers)
    assert numbers[0].x == 0.0
    assert numbers[1].x == 1.0


def test_ini_seeded_layout_zones_from_hi_warn_danger() -> None:
    service = DashboardLayoutService()
    configs = [
        _make_gc("clt", "coolantRaw", "Coolant", "°C", lo=-40, hi=130, hi_warn=95, hi_danger=110),
    ]
    layout = service.default_layout(gauge_configurations=configs, front_page_gauges=["clt"])
    # Only one widget (dial) — zones should include warning and danger
    w = layout.widgets[0]
    colors = {z.color for z in w.color_zones}
    assert "warning" in colors
    assert "danger" in colors


def test_ini_seeded_layout_falls_back_when_empty() -> None:
    """Passing empty lists should give the hardcoded fallback."""
    service = DashboardLayoutService()
    fallback = service.default_layout()
    ini_seeded = service.default_layout(gauge_configurations=[], front_page_gauges=[])
    assert {w.source for w in ini_seeded.widgets} == {w.source for w in fallback.widgets}


def test_ini_seeded_layout_skips_unknown_gauge_names() -> None:
    service = DashboardLayoutService()
    configs = [_make_gc("tachometer", "rpm", "RPM", lo=0, hi=8000)]
    # "unknownGauge" is in front_page_gauges but not in configs — should be silently skipped.
    layout = service.default_layout(
        gauge_configurations=configs,
        front_page_gauges=["tachometer", "unknownGauge"],
    )
    assert len(layout.widgets) == 1
    assert layout.widgets[0].source == "rpm"
