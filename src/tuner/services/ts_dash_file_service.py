"""TSDash ``.dash`` file import / export.

Reverse-engineered from the decompiled TSDash JAR
(`com/efiAnalytics/apps/ts/dashboard/T/c.java` and `T/e.java`). The real
TSDash `.dash` format is XML using namespace
``http://www.EFIAnalytics.com/:dsh`` with the following structure:

    <dsh xmlns="http://www.EFIAnalytics.com/:dsh">
      <bibliography author="..." company="..." writeDate="..."/>
      <versionInfo fileFormat="3.0" firmwareSignature="..."/>
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
          <RelativeWidth type="double">0.20</RelativeWidth>
          <RelativeHeight type="double">0.15</RelativeHeight>
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
        ...
      </gaugeCluster>
    </dsh>

Each ``<dashComp>`` is reflection-serialized in the JVM — every public
zero-arg getter on the component class becomes a child element whose
name is the getter name with ``get``/``is`` stripped. We don't need to
round-trip *every* possible getter — only the fields the
``DashboardWidget`` domain model carries plus enough metadata for an
operator to recognize the widget.

Position and size fields are normalized fractions in ``[0.0, 1.0]``
relative to the cluster size. They map directly onto the ``DashboardWidget``
``x/y/width/height`` floats; consumers that prefer integer grid cells
can scale on display.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from tuner.domain.dashboard import DashboardLayout, DashboardWidget, GaugeColorZone


_NS = "http://www.EFIAnalytics.com/:dsh"
_FILE_FORMAT = "3.0"

# Map JVM dashComp class FQNs → our short ``DashboardWidget.kind`` value.
# Anything not in the table falls back to the lowercased simple class name.
_KIND_BY_TYPE: dict[str, str] = {
    "com.efiAnalytics.apps.ts.dashboard.Gauge": "dial",
    "com.efiAnalytics.apps.ts.dashboard.Indicator": "indicator",
    "com.efiAnalytics.apps.ts.dashboard.DashLabel": "label",
    "com.efiAnalytics.apps.ts.dashboard.HtmlDisplay": "html",
}
_TYPE_BY_KIND: dict[str, str] = {kind: fqn for fqn, kind in _KIND_BY_TYPE.items()}


def _local_tag(element: ET.Element) -> str:
    """Strip the XML namespace from an element tag.

    TSDash files declare ``xmlns="http://www.EFIAnalytics.com/:dsh"`` on
    the root, so every child tag comes back as ``{NS}tagname`` from
    ElementTree. Stripping keeps the rest of the parser readable.
    """
    tag = element.tag
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


class TsDashFileService:
    """TSDash ``.dash`` parser and exporter.

    Stateless. Both directions go through the namespaced ``<dsh>`` root
    so the output is loadable by stock TSDash and the parser accepts
    real fixtures pulled from a TunerStudio install. Reflection-serialized
    fields not represented on ``DashboardWidget`` are ignored on import
    and omitted on export.
    """

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def parse(self, source_path: Path) -> DashboardLayout:
        if not source_path.exists():
            raise FileNotFoundError(f"Dash file not found: {source_path}")
        return self.parse_text(source_path.read_text(encoding="utf-8"))

    def parse_text(self, xml_text: str) -> DashboardLayout:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise ValueError(f"Invalid .dash XML: {exc}") from exc
        if _local_tag(root) != "dsh":
            raise ValueError(
                f"Expected root element <dsh>, got <{_local_tag(root)}>."
            )

        cluster = self._find_child(root, "gaugeCluster")
        if cluster is None:
            raise ValueError("<dsh> root has no <gaugeCluster> child.")

        # Use the firmware signature as the layout name when present —
        # nothing else in the .dash file carries a human-friendly title.
        version = self._find_child(root, "versionInfo")
        layout_name = "Imported Dashboard"
        if version is not None:
            sig = version.attrib.get("firmwareSignature")
            if sig:
                layout_name = sig

        widgets: list[DashboardWidget] = []
        for index, comp in enumerate(self._iter_children(cluster, "dashComp")):
            widget = self._dashcomp_to_widget(comp, index)
            if widget is not None:
                widgets.append(widget)
        return DashboardLayout(name=layout_name, widgets=widgets)

    @classmethod
    def _dashcomp_to_widget(
        cls, comp: ET.Element, fallback_index: int
    ) -> DashboardWidget | None:
        type_fqn = comp.attrib.get("type", "")
        kind = _KIND_BY_TYPE.get(type_fqn) or type_fqn.rsplit(".", 1)[-1].lower()

        # Reflection-emitted children: tag = field name, text = value.
        fields: dict[str, str] = {}
        for child in comp:
            tag = _local_tag(child)
            text = child.text or ""
            fields[tag] = text.strip()

        title = fields.get("Title", "")
        widget_id = title.strip() or f"widget_{fallback_index}"
        # Slugify so the id is filesystem/JSON safe.
        widget_id = "".join(
            ch.lower() if ch.isalnum() else "_" for ch in widget_id
        ).strip("_") or f"widget_{fallback_index}"

        zones = cls._extract_color_zones(fields)

        return DashboardWidget(
            widget_id=widget_id,
            kind=kind,
            title=title or widget_id,
            source=fields.get("OutputChannel") or None,
            units=fields.get("Units") or None,
            x=_to_float(fields.get("RelativeX"), 0.0),
            y=_to_float(fields.get("RelativeY"), 0.0),
            width=_to_float(fields.get("RelativeWidth"), 0.1),
            height=_to_float(fields.get("RelativeHeight"), 0.1),
            min_value=_to_float(fields.get("Min"), 0.0),
            max_value=_to_float(fields.get("Max"), 100.0),
            color_zones=zones,
        )

    @staticmethod
    def _extract_color_zones(fields: dict[str, str]) -> list[GaugeColorZone]:
        """Build ``GaugeColorZone`` entries from the four threshold fields.

        TSDash stores warning/critical bands as four scalars
        (``LowWarning``, ``HighWarning``, ``LowCritical``, ``HighCritical``)
        rather than explicit zones. We synthesize at most two zones —
        one ``warning`` and one ``danger`` — using the high thresholds
        as the lower bound of each band. Low thresholds are ignored
        because the ``DashboardWidget`` model has no concept of a
        symmetrical warning band yet.
        """
        zones: list[GaugeColorZone] = []
        max_value = _to_float(fields.get("Max"), 100.0)
        warn = _to_float(fields.get("HighWarning"), 0.0)
        crit = _to_float(fields.get("HighCritical"), 0.0)
        if warn > 0 and warn < max_value:
            zones.append(GaugeColorZone(lo=warn, hi=max(warn, crit or max_value), color="warning"))
        if crit > 0 and crit < max_value:
            zones.append(GaugeColorZone(lo=crit, hi=max_value, color="danger"))
        return zones

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self, destination_path: Path, layout: DashboardLayout) -> None:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_text(self.export_text(layout), encoding="utf-8")

    def export_text(self, layout: DashboardLayout) -> str:
        # Register the namespace as the default so ElementTree emits
        # ``<dsh xmlns="...">`` rather than ``ns0:`` prefixes.
        ET.register_namespace("", _NS)
        root = ET.Element(f"{{{_NS}}}dsh")

        bibliography = ET.SubElement(root, f"{{{_NS}}}bibliography")
        bibliography.set("author", "Tuner — Speeduino-first TunerStudio rewrite")
        bibliography.set("company", "Tuner")
        bibliography.set("writeDate", datetime.now().isoformat(timespec="seconds"))

        version = ET.SubElement(root, f"{{{_NS}}}versionInfo")
        version.set("fileFormat", _FILE_FORMAT)
        version.set("firmwareSignature", layout.name)

        cluster = ET.SubElement(root, f"{{{_NS}}}gaugeCluster")
        cluster.set("clusterBackgroundColor", "-16777216")
        cluster.set("backgroundDitherColor", "")
        cluster.set("clusterBackgroundImageFileName", "")
        cluster.set("clusterBackgroundImageStyle", "Stretch")
        cluster.set("antiAliasing", "true")
        cluster.set("forceAspect", "false")
        cluster.set("forceAspectWidth", "0.0")
        cluster.set("forceAspectHeight", "0.0")

        for widget in layout.widgets:
            cluster.append(self._widget_to_dashcomp(widget))

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode")

    @staticmethod
    def _widget_to_dashcomp(widget: DashboardWidget) -> ET.Element:
        type_fqn = _TYPE_BY_KIND.get(widget.kind, "com.efiAnalytics.apps.ts.dashboard.Gauge")
        comp = ET.Element(f"{{{_NS}}}dashComp", attrib={"type": type_fqn})

        def _f(name: str, value: float) -> None:
            element = ET.SubElement(comp, f"{{{_NS}}}{name}", attrib={"type": "double"})
            element.text = _fmt_num(value)

        def _s(name: str, value: str | None) -> None:
            if value is None:
                return
            element = ET.SubElement(comp, f"{{{_NS}}}{name}", attrib={"type": "String"})
            element.text = value

        _f("RelativeX", widget.x)
        _f("RelativeY", widget.y)
        _f("RelativeWidth", widget.width)
        _f("RelativeHeight", widget.height)
        _s("Title", widget.title)
        _s("Units", widget.units)
        _f("Min", widget.min_value)
        _f("Max", widget.max_value)

        warn_lo = next((z.lo for z in widget.color_zones if z.color == "warning"), 0.0)
        crit_lo = next((z.lo for z in widget.color_zones if z.color == "danger"), 0.0)
        _f("LowWarning", 0.0)
        _f("HighWarning", warn_lo)
        _f("LowCritical", 0.0)
        _f("HighCritical", crit_lo)

        _s("OutputChannel", widget.source)
        return comp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_child(parent: ET.Element, local_name: str) -> ET.Element | None:
        for child in parent:
            if _local_tag(child) == local_name:
                return child
        return None

    @staticmethod
    def _iter_children(parent: ET.Element, local_name: str):
        for child in parent.iter():
            if _local_tag(child) == local_name and child is not parent:
                yield child


def _to_float(text: str | None, default: float) -> float:
    if text is None:
        return default
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _fmt_num(value: float) -> str:
    """TSDash uses Java ``Double.toString``-style output, which always
    includes a decimal point. Mimic that for diff stability."""
    if isinstance(value, int):
        return f"{value}.0"
    if isinstance(value, float) and value.is_integer():
        return f"{value:.1f}"
    return str(value)
