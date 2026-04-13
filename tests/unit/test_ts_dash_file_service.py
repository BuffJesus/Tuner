"""Tests for the TSDash ``.dash`` import / export service.

Schema reverse-engineered from the decompiled TSDash JAR
(``com/efiAnalytics/apps/ts/dashboard/T/c.java`` + ``T/e.java``):

  - Root element ``<dsh>`` with namespace ``http://www.EFIAnalytics.com/:dsh``
  - ``<bibliography>`` and ``<versionInfo fileFormat="3.0" firmwareSignature=...>``
  - ``<gaugeCluster>`` carrying global cluster attributes plus N child
    ``<dashComp type="com.efiAnalytics.apps.ts.dashboard.{Gauge,Indicator,...}">``
  - Each ``dashComp`` has reflection-emitted children whose tag names match
    the JVM getter names (``RelativeX``, ``RelativeY``, ``RelativeWidth``,
    ``RelativeHeight``, ``Title``, ``Units``, ``Min``, ``Max``,
    ``OutputChannel``, ``LowWarning``, ``HighWarning``, ``LowCritical``,
    ``HighCritical``)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tuner.domain.dashboard import DashboardLayout, DashboardWidget, GaugeColorZone
from tuner.services.ts_dash_file_service import TsDashFileService

# Real-format synthetic fixture matching the TSDash <dsh> schema.
_REAL_DASH = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <dsh xmlns="http://www.EFIAnalytics.com/:dsh">
      <bibliography author="TunerStudio 3.1.x" company="EFI Analytics" writeDate="Mon Jan 1 12:00:00 EST 2024"/>
      <versionInfo fileFormat="3.0" firmwareSignature="speeduino 202501-T41"/>
      <gaugeCluster
          clusterBackgroundColor="-16777216"
          backgroundDitherColor=""
          clusterBackgroundImageFileName=""
          clusterBackgroundImageStyle="Stretch"
          antiAliasing="true"
          forceAspect="false"
          forceAspectWidth="0.0"
          forceAspectHeight="0.0">
        <dashComp type="com.efiAnalytics.apps.ts.dashboard.Gauge">
          <RelativeX type="double">0.02</RelativeX>
          <RelativeY type="double">0.02</RelativeY>
          <RelativeWidth type="double">0.30</RelativeWidth>
          <RelativeHeight type="double">0.40</RelativeHeight>
          <Title type="String">RPM</Title>
          <Units type="String">rpm</Units>
          <Min type="double">0.0</Min>
          <Max type="double">8000.0</Max>
          <LowWarning type="double">0.0</LowWarning>
          <HighWarning type="double">6500.0</HighWarning>
          <LowCritical type="double">0.0</LowCritical>
          <HighCritical type="double">7500.0</HighCritical>
          <OutputChannel type="String">rpm</OutputChannel>
          <BackColor type="Color" red="0" green="0" blue="0" alpha="255">-16777216</BackColor>
          <GaugePainter type="GaugePainter">AnalogGaugePainter</GaugePainter>
        </dashComp>
        <dashComp type="com.efiAnalytics.apps.ts.dashboard.Indicator">
          <RelativeX type="double">0.50</RelativeX>
          <RelativeY type="double">0.10</RelativeY>
          <RelativeWidth type="double">0.20</RelativeWidth>
          <RelativeHeight type="double">0.10</RelativeHeight>
          <Title type="String">CEL</Title>
          <OutputChannel type="String">checkEngine</OutputChannel>
        </dashComp>
      </gaugeCluster>
    </dsh>
    """)


# ---------------------------------------------------------------------------
# Parse — real TSDash schema
# ---------------------------------------------------------------------------

class TestParseRealSchema:
    def test_layout_name_uses_firmware_signature(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        assert layout.name == "speeduino 202501-T41"

    def test_parses_two_components(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        assert len(layout.widgets) == 2

    def test_gauge_component_mapped_to_dial_kind(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        rpm = next(w for w in layout.widgets if w.title == "RPM")
        assert rpm.kind == "dial"

    def test_indicator_component_mapped_to_indicator_kind(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        cel = next(w for w in layout.widgets if w.title == "CEL")
        assert cel.kind == "indicator"

    def test_relative_position_and_size_loaded(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        rpm = next(w for w in layout.widgets if w.title == "RPM")
        assert rpm.x == 0.02
        assert rpm.y == 0.02
        assert rpm.width == 0.30
        assert rpm.height == 0.40

    def test_units_min_max_and_channel(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        rpm = next(w for w in layout.widgets if w.title == "RPM")
        assert rpm.units == "rpm"
        assert rpm.min_value == 0.0
        assert rpm.max_value == 8000.0
        assert rpm.source == "rpm"

    def test_warning_and_critical_thresholds_become_color_zones(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        rpm = next(w for w in layout.widgets if w.title == "RPM")
        assert len(rpm.color_zones) == 2
        warning = next(z for z in rpm.color_zones if z.color == "warning")
        danger = next(z for z in rpm.color_zones if z.color == "danger")
        assert warning.lo == 6500.0
        assert danger.lo == 7500.0
        assert danger.hi == 8000.0

    def test_widget_id_is_slugified_title(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        rpm = next(w for w in layout.widgets if w.title == "RPM")
        assert rpm.widget_id == "rpm"

    def test_indicator_without_units_loads(self) -> None:
        layout = TsDashFileService().parse_text(_REAL_DASH)
        cel = next(w for w in layout.widgets if w.title == "CEL")
        assert cel.units is None
        assert cel.source == "checkEngine"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrors:
    def test_wrong_root_raises(self) -> None:
        with pytest.raises(ValueError, match="<dsh>"):
            TsDashFileService().parse_text("<NotDsh/>")

    def test_missing_gauge_cluster_raises(self) -> None:
        xml = '<dsh xmlns="http://www.EFIAnalytics.com/:dsh"/>'
        with pytest.raises(ValueError, match="gaugeCluster"):
            TsDashFileService().parse_text(xml)

    def test_invalid_xml_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid .dash XML"):
            TsDashFileService().parse_text("<dsh><unclosed>")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            TsDashFileService().parse(tmp_path / "missing.dash")


# ---------------------------------------------------------------------------
# Export — emits TSDash-compatible XML
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_root_uses_dsh_namespace(self) -> None:
        text = TsDashFileService().export_text(DashboardLayout(name="x", widgets=[]))
        assert "<dsh" in text
        assert 'xmlns="http://www.EFIAnalytics.com/:dsh"' in text

    def test_export_emits_versionInfo_and_gaugeCluster(self) -> None:
        text = TsDashFileService().export_text(
            DashboardLayout(name="speeduino 202501-T41", widgets=[])
        )
        assert 'fileFormat="3.0"' in text
        assert 'firmwareSignature="speeduino 202501-T41"' in text
        assert "<gaugeCluster" in text

    def test_export_emits_dashcomp_with_jvm_type_attribute(self) -> None:
        layout = DashboardLayout(
            name="L",
            widgets=[
                DashboardWidget(
                    widget_id="rpm", kind="dial", title="RPM",
                    source="rpm", units="rpm",
                    x=0.0, y=0.0, width=0.3, height=0.4,
                    min_value=0.0, max_value=8000.0,
                    color_zones=[
                        GaugeColorZone(6500.0, 7500.0, "warning"),
                        GaugeColorZone(7500.0, 8000.0, "danger"),
                    ],
                ),
            ],
        )
        text = TsDashFileService().export_text(layout)
        assert 'type="com.efiAnalytics.apps.ts.dashboard.Gauge"' in text
        assert "<RelativeX" in text
        assert "<Title" in text
        assert "<HighWarning" in text
        assert "<HighCritical" in text
        assert "<OutputChannel" in text


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_parse_export_parse_preserves_widgets(self) -> None:
        svc = TsDashFileService()
        original = svc.parse_text(_REAL_DASH)
        exported = svc.export_text(original)
        reparsed = svc.parse_text(exported)
        assert reparsed.name == original.name
        assert len(reparsed.widgets) == len(original.widgets)
        for a, b in zip(original.widgets, reparsed.widgets):
            assert a.title == b.title
            assert a.kind == b.kind
            assert a.source == b.source
            assert a.units == b.units
            assert a.x == b.x and a.y == b.y
            assert a.width == b.width and a.height == b.height
            assert a.min_value == b.min_value
            assert a.max_value == b.max_value
            assert a.color_zones == b.color_zones

    def test_export_to_file_round_trips(self, tmp_path: Path) -> None:
        svc = TsDashFileService()
        layout = svc.parse_text(_REAL_DASH)
        out = tmp_path / "out.dash"
        svc.export(out, layout)
        assert out.exists()
        reparsed = svc.parse(out)
        assert reparsed.name == layout.name
        assert len(reparsed.widgets) == len(layout.widgets)
