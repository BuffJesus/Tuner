from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from tuner.domain.dashboard import DashboardLayout, DashboardWidget, GaugeColorZone
from tuner.domain.ecu_definition import FrontPageIndicator, GaugeConfiguration, ScalarParameterDefinition
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.services.dashboard_layout_service import DashboardLayoutService
from tuner.services.visibility_expression_service import VisibilityExpressionService

_GAUGE_MIME = "application/x-gauge-widget-id"

_ZONE_ACCENT: dict[str | None, str] = {
    "ok":      "#43a047",
    "warning": "#fb8c00",
    "danger":  "#e53935",
    None:      "#d0d0d0",
}

# Dimmer version used for the accent bar background (avoids competing with the value text)
_ZONE_ACCENT_DIM: dict[str | None, str] = {
    "ok":      "#1b5e20",
    "warning": "#bf360c",
    "danger":  "#7f0000",
    None:      "#252525",
}


# ---------------------------------------------------------------------------
# Gauge configuration dialog
# ---------------------------------------------------------------------------

class _ColorZoneRow:
    def __init__(self, zone: GaugeColorZone, list_widget: QListWidget) -> None:
        self.zone = zone
        self._list_widget = list_widget


class GaugeConfigDialog(QDialog):
    """Edit all properties of a single gauge widget."""

    def __init__(
        self,
        widget_def: DashboardWidget,
        available_channels: list[ScalarParameterDefinition],
        available_pages: list[tuple[str, str]],
        gauge_configurations: list[GaugeConfiguration] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Configure Gauge — {widget_def.title}")
        self.setMinimumWidth(460)
        self._def = widget_def
        self._color_zones: list[GaugeColorZone] = list(widget_def.color_zones)
        self._available_channels = available_channels
        self._available_pages = available_pages
        # Index gauge configs by channel name for O(1) lookup in _on_source_changed.
        self._gauge_by_channel: dict[str, GaugeConfiguration] = {}
        for gc in (gauge_configurations or []):
            self._gauge_by_channel.setdefault(gc.channel, gc)
        # Track the last auto-suggested title so we know whether to overwrite it
        # on source change (we won't overwrite if the user has typed something custom).
        self._auto_title: str = self._suggested_title_for(widget_def.source or "")
        self._build()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ch_for(self, name: str) -> ScalarParameterDefinition | None:
        for ch in self._available_channels:
            if ch.name == name:
                return ch
        return None

    def _suggested_title_for(self, source_name: str) -> str:
        ch = self._ch_for(source_name)
        if ch is None:
            return source_name
        return ch.label or ch.name

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)

        # Title
        self._title_edit = QLineEdit(self._def.title)
        form.addRow("Title", self._title_edit)

        # Source channel
        self._source_combo = QComboBox()
        self._source_combo.setEditable(True)
        self._source_combo.addItem("(none)", "")
        for ch in self._available_channels:
            display = ch.label or ch.name
            if ch.units:
                display = f"{display}  ({ch.units})"
            self._source_combo.addItem(display, ch.name)
        current_source = self._def.source or ""
        idx = self._source_combo.findData(current_source)
        if idx >= 0:
            self._source_combo.setCurrentIndex(idx)
        else:
            self._source_combo.setCurrentText(current_source)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        form.addRow("Source Channel", self._source_combo)

        # Units
        self._units_edit = QLineEdit(self._def.units or "")
        form.addRow("Units", self._units_edit)

        # Kind
        self._kind_combo = QComboBox()
        self._kind_combo.addItem("Number", "number")
        self._kind_combo.addItem("Bar", "bar")
        self._kind_combo.addItem("Dial", "dial")
        self._kind_combo.addItem("LED Indicator", "led")
        kind_idx = self._kind_combo.findData(self._def.kind)
        if kind_idx >= 0:
            self._kind_combo.setCurrentIndex(kind_idx)
        form.addRow("Display Kind", self._kind_combo)

        # Min / Max
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(-99999, 99999)
        self._min_spin.setDecimals(1)
        self._min_spin.setValue(self._def.min_value)
        form.addRow("Min Value", self._min_spin)

        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(-99999, 99999)
        self._max_spin.setDecimals(1)
        self._max_spin.setValue(self._def.max_value)
        form.addRow("Max Value", self._max_spin)

        # Grid span (col_span = width, row_span = height)
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 6)
        self._width_spin.setValue(max(1, int(self._def.width)))
        self._width_spin.setToolTip("Number of grid columns this gauge occupies")
        form.addRow("Column Span", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(1, 4)
        self._height_spin.setValue(max(1, int(self._def.height)))
        self._height_spin.setToolTip("Number of grid rows this gauge occupies")
        form.addRow("Row Span", self._height_spin)

        # Tuning page
        self._page_combo = QComboBox()
        self._page_combo.addItem("(none)", "")
        for page_id, title in self._available_pages:
            self._page_combo.addItem(f"{title}  [{page_id}]", page_id)
        if self._def.tune_page:
            pidx = self._page_combo.findData(self._def.tune_page)
            if pidx >= 0:
                self._page_combo.setCurrentIndex(pidx)
        form.addRow("Tuning Page", self._page_combo)

        root.addLayout(form)

        # Color zones
        zones_label = QLabel("Color Zones")
        zones_label.setStyleSheet("font-weight: bold;")
        root.addWidget(zones_label)

        self._zones_list = QListWidget()
        self._zones_list.setFixedHeight(90)
        self._zones_list.setToolTip("Zones are applied in order; last matching zone wins")
        self._refresh_zones_list()
        root.addWidget(self._zones_list)

        zone_btns = QHBoxLayout()
        zone_btns.setSpacing(6)
        add_zone_btn = QPushButton("Add Zone")
        add_zone_btn.clicked.connect(self._on_add_zone)
        zone_btns.addWidget(add_zone_btn)
        remove_zone_btn = QPushButton("Remove Selected")
        remove_zone_btn.clicked.connect(self._on_remove_zone)
        zone_btns.addWidget(remove_zone_btn)
        zone_btns.addStretch(1)
        root.addLayout(zone_btns)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_source_changed(self) -> None:
        """Auto-fill title, units, min, max, and color zones from gauge configuration."""
        ch_name = self._source_combo.currentData()
        if not ch_name:
            return

        gc = self._gauge_by_channel.get(ch_name)
        ch = self._ch_for(ch_name)

        # Title: prefer gauge config title; fall back to channel label/name.
        if gc is not None:
            new_auto = gc.title
        elif ch is not None:
            new_auto = ch.label or ch.name
        else:
            new_auto = ch_name
        current = self._title_edit.text().strip()
        if not current or current.lower() == self._auto_title.lower():
            self._title_edit.setText(new_auto)
        self._auto_title = new_auto

        # Units: gauge config wins over output channel definition
        if gc is not None and gc.units:
            self._units_edit.setText(gc.units)
        elif ch is not None and ch.units:
            self._units_edit.setText(ch.units)

        # Min / Max: gauge config lo/hi are the display range; scalar min/max is fallback
        if gc is not None:
            if gc.lo is not None:
                self._min_spin.setValue(gc.lo)
            if gc.hi is not None:
                self._max_spin.setValue(gc.hi)
        else:
            if ch is not None and ch.min_value is not None:
                self._min_spin.setValue(ch.min_value)
            if ch is not None and ch.max_value is not None:
                self._max_spin.setValue(ch.max_value)

        # Color zones: auto-populate from gauge warn/danger thresholds when the
        # current zone list is empty (don't clobber zones the user already set).
        if gc is not None and not self._color_zones:
            lo = gc.lo or 0.0
            hi = gc.hi or 100.0
            zones: list[GaugeColorZone] = []
            if gc.lo_danger is not None and gc.lo_danger > lo:
                zones.append(GaugeColorZone(lo=lo, hi=gc.lo_danger, color="danger"))
            if gc.lo_warn is not None and gc.lo_warn > lo:
                warn_lo = gc.lo_danger if gc.lo_danger is not None and gc.lo_danger > lo else lo
                zones.append(GaugeColorZone(lo=warn_lo, hi=gc.lo_warn, color="warning"))
            if gc.hi_warn is not None and gc.hi_warn < hi:
                warn_hi = gc.hi_danger if gc.hi_danger is not None and gc.hi_danger < hi else hi
                zones.append(GaugeColorZone(lo=gc.hi_warn, hi=warn_hi, color="warning"))
            if gc.hi_danger is not None and gc.hi_danger < hi:
                zones.append(GaugeColorZone(lo=gc.hi_danger, hi=hi, color="danger"))
            if zones:
                self._color_zones = zones
                self._refresh_zones_list()

    def _refresh_zones_list(self) -> None:
        self._zones_list.clear()
        for z in self._color_zones:
            self._zones_list.addItem(f"{z.lo} – {z.hi}  [{z.color}]")

    def _on_add_zone(self) -> None:
        dlg = _AddColorZoneDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._color_zones.append(dlg.zone())
            self._refresh_zones_list()

    def _on_remove_zone(self) -> None:
        row = self._zones_list.currentRow()
        if 0 <= row < len(self._color_zones):
            self._color_zones.pop(row)
            self._refresh_zones_list()

    def result_widget_def(self) -> DashboardWidget:
        source_data = self._source_combo.currentData()
        source = source_data if source_data else (self._source_combo.currentText().strip() or None)
        page_data = self._page_combo.currentData()
        return DashboardWidget(
            widget_id=self._def.widget_id,
            kind=self._kind_combo.currentData() or "number",
            title=self._title_edit.text().strip() or self._def.title,
            source=source or None,
            units=self._units_edit.text().strip() or None,
            x=self._def.x,
            y=self._def.y,
            width=float(self._width_spin.value()),
            height=float(self._height_spin.value()),
            min_value=self._min_spin.value(),
            max_value=self._max_spin.value(),
            color_zones=list(self._color_zones),
            tune_page=page_data if page_data else None,
        )


class _AddColorZoneDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Color Zone")
        self.setFixedWidth(280)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self._lo = QDoubleSpinBox()
        self._lo.setRange(-99999, 99999)
        self._lo.setDecimals(1)
        form.addRow("Lo", self._lo)
        self._hi = QDoubleSpinBox()
        self._hi.setRange(-99999, 99999)
        self._hi.setDecimals(1)
        self._hi.setValue(100)
        form.addRow("Hi", self._hi)
        self._color = QComboBox()
        for label, value in [("OK (green)", "ok"), ("Warning (orange)", "warning"), ("Danger (red)", "danger")]:
            self._color.addItem(label, value)
        form.addRow("Color", self._color)
        root.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def zone(self) -> GaugeColorZone:
        return GaugeColorZone(lo=self._lo.value(), hi=self._hi.value(), color=self._color.currentData())


# ---------------------------------------------------------------------------
# Dial face (QPainter-rendered circular gauge)
# ---------------------------------------------------------------------------

class _DialFace(QWidget):
    """Custom-painted circular gauge dial.

    Draws a 270° arc track with colour-zone segments, major tick marks, a
    needle, and a value readout — all sized relative to the widget dimensions
    so it scales cleanly on any screen resolution.
    """

    _SWEEP = 270.0          # degrees swept by the full arc
    _START = 225.0          # Qt CCW degrees from 3-o'clock where gauge begins (≈7-o'clock)

    _ZONE_RGB: dict[str, tuple[int, int, int]] = {
        "ok":      (76,  175,  80),
        "warning": (255, 152,   0),
        "danger":  (244,  67,  54),
    }

    def __init__(self, widget_def: "DashboardWidget", parent: "QWidget | None" = None) -> None:
        super().__init__(parent)
        self._def = widget_def
        self._value: float | None = None
        self.setMinimumSize(100, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_def(self, widget_def: "DashboardWidget") -> None:
        self._def = widget_def
        self.update()

    def update_value(self, value: float | None) -> None:
        self._value = value
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        side = min(w, h)
        cx, cy = w / 2.0, h / 2.0
        r = side / 2.0 * 0.86          # outer radius of the arc track
        track_w = r * 0.16              # arc stroke width

        span = self._def.max_value - self._def.min_value

        # --- background arc track ---
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        bg_pen = QPen(QColor(45, 45, 45))
        bg_pen.setWidthF(track_w)
        bg_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(bg_pen)
        p.drawArc(arc_rect, int(self._START * 16), int(-self._SWEEP * 16))

        # --- colour-zone arc segments ---
        if span > 0:
            for zone in self._def.color_zones:
                lo_f = max(0.0, (zone.lo - self._def.min_value) / span)
                hi_f = min(1.0, (zone.hi - self._def.min_value) / span)
                if hi_f <= lo_f:
                    continue
                rgb = self._ZONE_RGB.get(zone.color, (160, 160, 160))
                zone_pen = QPen(QColor(*rgb, 200))
                zone_pen.setWidthF(track_w)
                zone_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(zone_pen)
                start_deg = self._START - lo_f * self._SWEEP
                span_deg = -(hi_f - lo_f) * self._SWEEP
                p.drawArc(arc_rect, int(start_deg * 16), int(span_deg * 16))

        # --- major tick marks ---
        for i in range(9):
            frac = i / 8.0
            angle_rad = math.radians(self._START - frac * self._SWEEP)
            outer = r - track_w * 0.5
            inner = outer - r * 0.09
            p.setPen(QPen(QColor(110, 110, 110), max(1.0, side * 0.012)))
            p.drawLine(
                QPointF(cx + outer * math.cos(angle_rad), cy - outer * math.sin(angle_rad)),
                QPointF(cx + inner * math.cos(angle_rad), cy - inner * math.sin(angle_rad)),
            )

        # --- needle + hub ---
        if self._value is not None and span > 0:
            frac = max(0.0, min(1.0, (self._value - self._def.min_value) / span))
            angle_rad = math.radians(self._START - frac * self._SWEEP)
            tip = r * 0.70

            # Choose needle colour from active zone (last matching zone wins)
            needle_rgb = (210, 210, 210)
            for zone in reversed(self._def.color_zones):
                if zone.lo <= self._value <= zone.hi:
                    needle_rgb = self._ZONE_RGB.get(zone.color, needle_rgb)
                    break
            needle_color = QColor(*needle_rgb)

            needle_pen = QPen(needle_color)
            needle_pen.setWidthF(max(1.5, side * 0.028))
            needle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(needle_pen)
            p.drawLine(QPointF(cx, cy), QPointF(cx + tip * math.cos(angle_rad), cy - tip * math.sin(angle_rad)))

            # Outer hub ring
            hub_r = r * 0.09
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(55, 55, 55)))
            p.drawEllipse(QRectF(cx - hub_r, cy - hub_r, hub_r * 2, hub_r * 2))
            # Inner hub dot (matches needle colour)
            inner_r = r * 0.045
            p.setBrush(QBrush(needle_color))
            p.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        # --- value readout ---
        font = QFont()
        font.setPixelSize(max(8, int(side * 0.15)))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QPen(QColor(225, 225, 225)))
        value_text = (
            "—" if self._value is None
            else (str(int(self._value)) if self._value == int(self._value) else f"{self._value:.1f}")
        )
        p.drawText(
            QRectF(cx - r * 0.55, cy + r * 0.18, r * 1.1, r * 0.38),
            Qt.AlignmentFlag.AlignCenter,
            value_text,
        )

        # --- units ---
        if self._def.units:
            uf = QFont()
            uf.setPixelSize(max(7, int(side * 0.08)))
            p.setFont(uf)
            p.setPen(QPen(QColor(110, 110, 110)))
            p.drawText(
                QRectF(cx - r * 0.45, cy + r * 0.50, r * 0.9, r * 0.24),
                Qt.AlignmentFlag.AlignCenter,
                self._def.units,
            )

        # --- title ---
        tf = QFont()
        tf.setPixelSize(max(7, int(side * 0.09)))
        p.setFont(tf)
        p.setPen(QPen(QColor(130, 130, 130)))
        p.drawText(
            QRectF(cx - r * 0.55, cy + r * 0.72, r * 1.1, r * 0.25),
            Qt.AlignmentFlag.AlignCenter,
            self._def.title,
        )

        p.end()


# ---------------------------------------------------------------------------
# LED indicator face
# ---------------------------------------------------------------------------

class _LedFace(QWidget):
    """Custom-painted circular LED indicator.

    Shows a large glowing circle whose colour is driven by the active colour
    zone.  Dark-neutral when offline or when the value falls outside all zones.
    Title (top) and numeric value + units (bottom) are painted inside the cell
    so the cell needs no external label widgets.
    """

    _ZONE_RGB: dict[str, tuple[int, int, int]] = {
        "ok":      ( 76, 175,  80),
        "warning": (255, 152,   0),
        "danger":  (244,  67,  54),
    }

    def __init__(self, widget_def: "DashboardWidget", parent: "QWidget | None" = None) -> None:
        super().__init__(parent)
        self._def = widget_def
        self._value: float | None = None
        self._zone_color: str | None = None
        self.setMinimumSize(60, 60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_def(self, widget_def: "DashboardWidget") -> None:
        self._def = widget_def
        self.update()

    def update_value(self, value: float | None) -> None:
        self._value = value
        if value is None:
            self._zone_color = None
        else:
            self._zone_color = None
            for zone in reversed(self._def.color_zones):
                if zone.lo <= value <= zone.hi:
                    self._zone_color = zone.color
                    break
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self.width()), float(self.height())
        side = min(w, h)

        TITLE_H = max(14.0, side * 0.14)
        VALUE_H = max(12.0, side * 0.12)
        PAD = side * 0.06

        # Title
        title_font = QFont()
        title_font.setPixelSize(max(7, int(side * 0.09)))
        p.setFont(title_font)
        p.setPen(QColor("#606060"))
        p.drawText(
            QRectF(0.0, 0.0, w, TITLE_H),
            Qt.AlignmentFlag.AlignCenter,
            self._def.title.upper(),
        )

        # LED circle
        body_top = TITLE_H + PAD
        body_h = h - TITLE_H - VALUE_H - PAD * 2
        diameter = min(w - PAD * 4, body_h)
        if diameter < 6.0:
            p.end()
            return
        r = diameter / 2.0
        cx = w / 2.0
        cy = body_top + body_h / 2.0

        rgb = self._ZONE_RGB.get(self._zone_color, (42, 42, 42)) if self._zone_color else (42, 42, 42)
        fill = QColor(*rgb)
        border = QColor(min(rgb[0] + 40, 255), min(rgb[1] + 40, 255), min(rgb[2] + 40, 255))
        p.setPen(QPen(border, max(1.0, side * 0.025)))
        p.setBrush(QBrush(fill))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Gleam highlight (only when active zone)
        if self._zone_color:
            gleam = QColor(255, 255, 255, 55)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(gleam))
            p.drawEllipse(QPointF(cx - r * 0.18, cy - r * 0.28), r * 0.44, r * 0.28)

        # Value + units
        val_rgb = self._ZONE_RGB.get(self._zone_color) if self._zone_color else None
        val_color = QColor(*(val_rgb if val_rgb else (100, 100, 100)))
        p.setPen(val_color)
        val_font = QFont()
        val_font.setPixelSize(max(8, int(side * 0.10)))
        p.setFont(val_font)
        if self._value is not None:
            val_text = (
                str(int(self._value))
                if self._value == int(self._value)
                else f"{self._value:.1f}"
            )
            if self._def.units:
                val_text += f" {self._def.units}"
        else:
            val_text = "—"
        p.drawText(
            QRectF(0.0, h - VALUE_H, w, VALUE_H),
            Qt.AlignmentFlag.AlignCenter,
            val_text,
        )

        p.end()


# ---------------------------------------------------------------------------
# Gauge widget
# ---------------------------------------------------------------------------

class GaugeWidget(QFrame):
    """Single gauge cell. Supports drag-and-drop rearrangement and full config editing."""

    swap_requested = Signal(str, str)  # (source_widget_id, target_widget_id)
    configure_requested = Signal(str)  # widget_id

    def __init__(
        self,
        widget_def: DashboardWidget,
        parent: QWidget | None = None,
        on_open_tuning: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._def = widget_def
        self._on_open_tuning = on_open_tuning
        self._drag_start_pos = None
        self.setAcceptDrops(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._build()

    # ------------------------------------------------------------------
    # Build / refresh
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._refresh_internal()

    def _refresh_internal(self) -> None:
        """Rebuild all child widgets from the current _def.

        Reuses the existing QVBoxLayout (Qt silently ignores a second setLayout()
        call, so we must never try to replace the layout — only clear and repopulate it).
        """
        layout = self.layout()
        if layout is None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(10, 8, 10, 0)
            layout.setSpacing(2)
        else:
            # Remove and schedule deletion of all current child widgets.
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.hide()
                    w.deleteLater()

        self._dial: _DialFace | None = None
        self._led: _LedFace | None = None
        self._title_label: QLabel | None = None
        self._value_label: QLabel | None = None
        self._units_label: QLabel | None = None
        self._bar: QProgressBar | None = None
        self._accent: QFrame | None = None

        self._label_widget: QLabel | None = None

        if self._def.kind == "dial":
            dial = _DialFace(self._def)
            layout.addWidget(dial, 1)
            self._dial = dial
        elif self._def.kind == "led":
            led = _LedFace(self._def)
            layout.addWidget(led, 1)
            self._led = led
        elif self._def.kind == "label":
            # Phase 8 final — static text widget. Renders the operator-supplied
            # text (or title as a fallback) and ignores live value updates.
            text = self._def.text if self._def.text is not None else self._def.title
            label = QLabel(text)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            label.setProperty("dashLabel", True)
            layout.addWidget(label, 1)
            self._label_widget = label
        else:
            title = QLabel(self._def.title.upper())
            title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            title.setProperty("gaugeTitle", True)
            layout.addWidget(title)
            self._title_label = title

            value = QLabel("—")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setProperty("gaugeValue", True)
            layout.addWidget(value, 1)
            self._value_label = value

            if self._def.units:
                units = QLabel(self._def.units)
                units.setAlignment(Qt.AlignmentFlag.AlignCenter)
                units.setProperty("gaugeUnits", True)
                layout.addWidget(units)
                self._units_label = units

            if self._def.kind == "bar":
                bar = QProgressBar()
                bar.setRange(0, 1000)
                bar.setValue(0)
                bar.setTextVisible(False)
                bar.setFixedHeight(6)
                layout.addWidget(bar)
                self._bar = bar

            # Coloured accent line at the bottom — updates with zone colour
            accent = QFrame()
            accent.setFixedHeight(4)
            accent.setObjectName("accentBar")
            layout.addWidget(accent)
            self._accent = accent

        self._apply_default_style()

    def update_def(self, widget_def: DashboardWidget) -> None:
        """Replace the definition and refresh all visuals."""
        self._def = widget_def
        self._refresh_internal()

    # ------------------------------------------------------------------
    # Live value
    # ------------------------------------------------------------------

    def update_value(self, value: float | None) -> None:
        if self._dial is not None:
            self._dial.update_value(value)
            return
        if self._led is not None:
            self._led.update_value(value)
            return
        if self._label_widget is not None:
            # Static text widgets ignore live data — they render once and stay put.
            return
        assert self._value_label is not None
        if value is None:
            self._value_label.setText("—")
            if self._bar is not None:
                self._bar.setValue(0)
            self._clear_zone_style()
            return
        text = str(int(value)) if value == int(value) else f"{value:.1f}"
        self._value_label.setText(text)
        if self._bar is not None:
            span = self._def.max_value - self._def.min_value
            if span > 0:
                fraction = (value - self._def.min_value) / span
                self._bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self._apply_zone_style(value)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_default_style(self) -> None:
        self.setStyleSheet(
            "GaugeWidget { border: 1px solid #383838; border-radius: 6px; background: #1a1a1a; }"
            "QLabel[gaugeTitle='true'] { color: #606060; font-size: 9px; letter-spacing: 1px; }"
            "QLabel[gaugeValue='true'] { color: #e0e0e0; font-size: 24px; font-weight: bold; }"
            "QLabel[gaugeUnits='true'] { color: #505050; font-size: 10px; }"
            "QLabel[dashLabel='true'] { color: #d0d0d0; font-size: 16px; font-weight: 600; padding: 6px; }"
            "QProgressBar { background: #252525; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #404040; border-radius: 3px; }"
            "QFrame#accentBar { background: #2e2e2e; border: none; }"
        )

    def _apply_hover_drop_style(self) -> None:
        self.setStyleSheet(
            "GaugeWidget { border: 2px solid #4fc3f7; border-radius: 6px; background: #1a2a35; }"
            "QLabel[gaugeTitle='true'] { color: #888; font-size: 9px; letter-spacing: 1px; }"
            "QLabel[gaugeValue='true'] { color: #ddd; font-size: 24px; font-weight: bold; }"
            "QLabel[gaugeUnits='true'] { color: #666; font-size: 10px; }"
            "QProgressBar { background: #252525; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background: #404040; border-radius: 3px; }"
            "QFrame#accentBar { background: #2e2e2e; border: none; }"
        )

    def _apply_zone_style(self, value: float) -> None:
        color = None
        for zone in reversed(self._def.color_zones):
            if zone.lo <= value <= zone.hi:
                color = zone.color
                break
        # Value label uses the zone color, or neutral white when no zone matches.
        label_color = _ZONE_ACCENT[color] if color is not None else "#e0e0e0"
        self._value_label.setStyleSheet(
            f"QLabel {{ color: {label_color}; font-size: 24px; font-weight: bold; }}"
        )
        # Accent bar and progress bar only light up when a zone is actually active.
        if color is not None:
            accent = _ZONE_ACCENT[color]
            dim = _ZONE_ACCENT_DIM[color]
            if self._accent is not None:
                self._accent.setStyleSheet(f"background: {accent}; border: none;")
            if self._bar is not None:
                self._bar.setStyleSheet(
                    f"QProgressBar {{ background: {dim}; border: none; border-radius: 3px; }}"
                    f"QProgressBar::chunk {{ background: {accent}; border-radius: 3px; }}"
                )
        else:
            if self._accent is not None:
                self._accent.setStyleSheet("background: #2e2e2e; border: none;")
            if self._bar is not None:
                self._bar.setStyleSheet(
                    "QProgressBar { background: #252525; border: none; border-radius: 3px; }"
                    "QProgressBar::chunk { background: #404040; border-radius: 3px; }"
                )

    def _clear_zone_style(self) -> None:
        self._value_label.setStyleSheet(
            "QLabel { color: #e0e0e0; font-size: 24px; font-weight: bold; }"
        )
        if self._accent is not None:
            self._accent.setStyleSheet("background: #2e2e2e; border: none;")
        if self._bar is not None:
            self._bar.setStyleSheet(
                "QProgressBar { background: #252525; border: none; border-radius: 3px; }"
                "QProgressBar::chunk { background: #404040; border-radius: 3px; }"
            )

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        if self._def.tune_page and self._on_open_tuning:
            open_action = menu.addAction(f"Open '{self._def.title}' in Tuning")
            _page = self._def.tune_page  # capture value, not reference
            open_action.triggered.connect(lambda checked=False, p=_page: self._on_open_tuning(p))
            menu.addSeparator()
        cfg_action = menu.addAction("Configure Gauge...")
        cfg_action.triggered.connect(lambda: self.configure_requested.emit(self._def.widget_id))
        menu.exec(self.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Drag source
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if delta >= 8:
                self._drag_start_pos = None
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(_GAUGE_MIME, self._def.widget_id.encode())
                drag.setMimeData(mime)
                drag.exec(Qt.DropAction.MoveAction)
        super().mouseMoveEvent(event)

    # ------------------------------------------------------------------
    # Drop target
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(_GAUGE_MIME):
            source_id = event.mimeData().data(_GAUGE_MIME).toStdString()
            if source_id != self._def.widget_id:
                event.acceptProposedAction()
                self._apply_hover_drop_style()
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self._apply_default_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self._apply_default_style()
        if event.mimeData().hasFormat(_GAUGE_MIME):
            source_id = event.mimeData().data(_GAUGE_MIME).toStdString()
            if source_id != self._def.widget_id:
                self.swap_requested.emit(source_id, self._def.widget_id)
                event.acceptProposedAction()
                return
        event.ignore()


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _apply_grid_stretch(grid: QGridLayout, widgets: list[DashboardWidget]) -> None:
    """Set equal stretch on every occupied column and row so cells fill available space.

    Without explicit stretch factors Qt keeps cells at minimum size, making gauges
    appear tiny regardless of how much space the parent widget has.
    """
    if not widgets:
        return
    max_col = max(int(w.x) + max(1, int(w.width))  for w in widgets)
    max_row = max(int(w.y) + max(1, int(w.height)) for w in widgets)
    for c in range(max_col):
        grid.setColumnStretch(c, 1)
    for r in range(max_row):
        grid.setRowStretch(r, 1)


# ---------------------------------------------------------------------------
# Fullscreen window
# ---------------------------------------------------------------------------

class DashboardFullscreenWindow(QDialog):
    """Fullscreen/operator gauge cluster. Escape or double-click to close."""

    def __init__(self, layout: DashboardLayout, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet("background: #111;")
        self._gauges: dict[str, GaugeWidget] = {}
        self._layout = layout
        self._build()
        self.showFullScreen()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        hint = QLabel("Press Escape or double-click to exit fullscreen")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #555; font-size: 10px;")
        root.addWidget(hint)

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        for widget_def in self._layout.widgets:
            gauge = GaugeWidget(widget_def)
            gauge.setStyleSheet(
                "GaugeWidget { border: 1px solid #3a3a3a; border-radius: 6px; background: #1a1a1a; }"
                "QLabel[gaugeTitle='true'] { color: #606060; font-size: 11px; letter-spacing: 1px; }"
                "QLabel[gaugeValue='true'] { color: #e8e8e8; font-size: 38px; font-weight: bold; }"
                "QLabel[gaugeUnits='true'] { color: #505050; font-size: 12px; }"
                "QProgressBar { background: #252525; border: none; border-radius: 3px; }"
                "QProgressBar::chunk { background: #404040; border-radius: 3px; }"
                "QFrame#accentBar { background: #2e2e2e; border: none; }"
            )
            row = int(widget_def.y)
            col = int(widget_def.x)
            row_span = max(1, int(widget_def.height))
            col_span = max(1, int(widget_def.width))
            grid.addWidget(gauge, row, col, row_span, col_span)
            self._gauges[widget_def.widget_id] = gauge

        _apply_grid_stretch(grid, self._layout.widgets)
        root.addWidget(grid_container, 1)

    def set_runtime_snapshot(self, snapshot: OutputChannelSnapshot | None) -> None:
        values = snapshot.as_dict() if snapshot is not None else {}
        for widget_id, gauge in self._gauges.items():
            gauge_def = next((w for w in self._layout.widgets if w.widget_id == widget_id), None)
            if gauge_def is None or gauge_def.source is None:
                gauge.update_value(None)
            else:
                gauge.update_value(values.get(gauge_def.source))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        self.close()


# ---------------------------------------------------------------------------
# FrontPage indicator strip
# ---------------------------------------------------------------------------

# Map TunerStudio color names to hex values that fit the dark theme.
_TS_COLORS: dict[str, str] = {
    "white":     "#e8e8e8",
    "black":     "#111111",
    "red":       "#e53935",
    "green":     "#43a047",
    "yellow":    "#fb8c00",
    "blue":      "#1976d2",
    "orange":    "#ef6c00",
    "gray":      "#888888",
    "grey":      "#888888",
    "darkgray":  "#444444",
    "darkgrey":  "#444444",
    "lightgray": "#aaaaaa",
    "lightgrey": "#aaaaaa",
}
_CHIP_OFF_BG = "#252525"
_CHIP_OFF_FG = "#555555"


class _IndicatorStrip(QWidget):
    """Compact grid of FrontPage status indicator chips.

    Each chip evaluates one ``[FrontPage]`` indicator expression against the
    live output-channel snapshot and shows the appropriate on/off label with
    its configured background and foreground colours.
    """

    _COLS = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._indicators: list[FrontPageIndicator] = []
        self._chips: list[QLabel] = []
        self._svc = VisibilityExpressionService()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 4, 0, 2)
        self._grid.setSpacing(3)
        self.setVisible(False)

    def set_indicators(self, indicators: list[FrontPageIndicator]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chips.clear()
        self._indicators = indicators

        for i, ind in enumerate(indicators):
            chip = QLabel(ind.off_label or "•")
            chip.setFixedHeight(18)
            chip.setMinimumWidth(30)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(self._chip_style(ind.off_bg, ind.off_fg))
            self._chips.append(chip)
            self._grid.addWidget(chip, i // self._COLS, i % self._COLS)

        self.setVisible(bool(indicators))

    def update_snapshot(self, values: dict[str, float]) -> None:
        for chip, ind in zip(self._chips, self._indicators):
            try:
                active = self._svc.evaluate(ind.expression, values)
            except Exception:
                active = False
            if active:
                chip.setText(ind.on_label or "•")
                chip.setStyleSheet(self._chip_style(ind.on_bg, ind.on_fg))
            else:
                chip.setText(ind.off_label or "•")
                chip.setStyleSheet(self._chip_style(ind.off_bg, ind.off_fg))

    @staticmethod
    def _chip_style(bg: str, fg: str) -> str:
        bg_color = _TS_COLORS.get(bg.lower(), _CHIP_OFF_BG) if bg else _CHIP_OFF_BG
        fg_color = _TS_COLORS.get(fg.lower(), _CHIP_OFF_FG) if fg else _CHIP_OFF_FG
        return (
            f"QLabel {{ background: {bg_color}; color: {fg_color}; "
            f"border-radius: 3px; font-size: 8px; padding: 0 4px; }}"
        )


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class DashboardPanel(QWidget):
    """Gauge cluster panel with live channel updates, layout persistence,
    drag-to-rearrange, and full per-gauge configuration."""

    navigate_to_page_requested = Signal(str)  # page_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout_service = DashboardLayoutService()
        self._layout: DashboardLayout = self._layout_service.default_layout()
        self._layout_path: Path | None = None
        self._gauges: dict[str, GaugeWidget] = {}
        self._fullscreen_window: DashboardFullscreenWindow | None = None
        self._available_pages: list[tuple[str, str]] = []
        self._available_channels: list[ScalarParameterDefinition] = []
        self._gauge_configurations: list[GaugeConfiguration] = []
        self._front_page_gauges: list[str] = []
        self._front_page_indicators: list[FrontPageIndicator] = []
        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_runtime_snapshot(self, snapshot: OutputChannelSnapshot | None) -> None:
        values = snapshot.as_dict() if snapshot is not None else {}
        for widget_id, gauge in self._gauges.items():
            gauge_def = next((w for w in self._layout.widgets if w.widget_id == widget_id), None)
            if gauge_def is None or gauge_def.source is None:
                gauge.update_value(None)
            else:
                gauge.update_value(values.get(gauge_def.source))
        self._indicator_strip.update_snapshot(values)
        if self._fullscreen_window is not None and self._fullscreen_window.isVisible():
            self._fullscreen_window.set_runtime_snapshot(snapshot)

    def set_layout_path(self, path: Path) -> None:
        self._layout_path = path
        if path.exists():
            self._load_from(path)

    def apply_layout(self, layout: DashboardLayout) -> None:
        self._layout = layout
        self._rebuild_gauges()

    def set_available_pages(self, pages: list[tuple[str, str]]) -> None:
        """Supply (page_id, title) pairs for the tuning page picker."""
        self._available_pages = pages

    def set_available_channels(self, channels: list[ScalarParameterDefinition]) -> None:
        """Supply output channel definitions for the source channel picker and auto-fill."""
        self._available_channels = channels

    def set_gauge_configurations(self, configs: list[GaugeConfiguration]) -> None:
        """Supply the INI gauge catalog so the config dialog can populate min/max/zones."""
        self._gauge_configurations = configs

    def set_front_page_data(
        self,
        gauge_configurations: list[GaugeConfiguration],
        front_page_gauges: list[str],
        front_page_indicators: list[FrontPageIndicator],
    ) -> None:
        """Supply INI front-page data.

        Updates the gauge catalog (used by the config dialog), seeds the
        default layout from INI data if no saved layout is already loaded,
        and populates the indicator strip.
        """
        self._gauge_configurations = gauge_configurations
        self._front_page_gauges = front_page_gauges
        self._front_page_indicators = front_page_indicators

        # Seed default layout from INI when no project-specific layout file exists yet.
        if self._layout_path is None or not self._layout_path.exists():
            self._layout = self._layout_service.default_layout(
                gauge_configurations=gauge_configurations,
                front_page_gauges=front_page_gauges,
            )
            self._rebuild_gauges()

        self._indicator_strip.set_indicators(front_page_indicators)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        title_label = QLabel("Dashboard")
        title_label.setProperty("surfacePanelTitle", True)
        toolbar.addWidget(title_label)

        hint = QLabel("Drag gauges to rearrange · Right-click to configure")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        toolbar.addWidget(hint)
        toolbar.addStretch(1)

        for label, slot, role in [
            ("Load Layout", self._on_load, "secondary"),
            ("Save Layout", self._on_save, "secondary"),
            ("Default Layout", self._on_reset, "secondary"),
            ("Fullscreen", self._on_fullscreen, "primary"),
        ]:
            btn = QPushButton(label)
            btn.setProperty("surfaceActionRole", role)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        root.addLayout(toolbar)

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(8)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._grid_container, 1)

        self._indicator_strip = _IndicatorStrip()
        root.addWidget(self._indicator_strip)

        self._rebuild_gauges()

    # ------------------------------------------------------------------
    # Grid management
    # ------------------------------------------------------------------

    def _rebuild_gauges(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._gauges.clear()

        for widget_def in self._layout.widgets:
            gauge = GaugeWidget(
                widget_def,
                self,
                on_open_tuning=self._on_open_tuning,
            )
            gauge.swap_requested.connect(self._on_swap)
            gauge.configure_requested.connect(self._on_configure_gauge)
            row = int(widget_def.y)
            col = int(widget_def.x)
            row_span = max(1, int(widget_def.height))
            col_span = max(1, int(widget_def.width))
            self._grid_layout.addWidget(gauge, row, col, row_span, col_span)
            self._gauges[widget_def.widget_id] = gauge

        _apply_grid_stretch(self._grid_layout, self._layout.widgets)

    def _on_swap(self, source_id: str, target_id: str) -> None:
        """Swap grid positions of two gauges."""
        src = next((w for w in self._layout.widgets if w.widget_id == source_id), None)
        tgt = next((w for w in self._layout.widgets if w.widget_id == target_id), None)
        if src is None or tgt is None:
            return
        # Exchange x, y, width, height
        src.x, tgt.x = tgt.x, src.x
        src.y, tgt.y = tgt.y, src.y
        src.width, tgt.width = tgt.width, src.width
        src.height, tgt.height = tgt.height, src.height
        self._rebuild_gauges()

    # ------------------------------------------------------------------
    # Gauge configuration
    # ------------------------------------------------------------------

    def _on_open_tuning(self, page_id: str) -> None:
        self.navigate_to_page_requested.emit(page_id)

    def _on_configure_gauge(self, widget_id: str) -> None:
        gauge_def = next((w for w in self._layout.widgets if w.widget_id == widget_id), None)
        if gauge_def is None:
            return
        dialog = GaugeConfigDialog(
            widget_def=gauge_def,
            available_channels=self._available_channels,
            available_pages=self._available_pages,
            gauge_configurations=self._gauge_configurations,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_def = dialog.result_widget_def()

        # Replace in layout and rebuild the grid.  Always do a full rebuild rather
        # than attempting in-place update_def(): Qt's deleteLater/layout-invalidation
        # interaction is unreliable for in-place widget swaps and was the root cause
        # of gauges not visually updating after a source change.
        for i, w in enumerate(self._layout.widgets):
            if w.widget_id == widget_id:
                self._layout.widgets[i] = new_def
                break
        self._rebuild_gauges()

    # ------------------------------------------------------------------
    # Layout I/O
    # ------------------------------------------------------------------

    def _on_load(self) -> None:
        start_dir = str(self._layout_path.parent) if self._layout_path else ""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Load Dashboard Layout", start_dir, "Dashboard JSON (*.dashboard.json *.json)"
        )
        if path_str:
            self._load_from(Path(path_str))

    def _load_from(self, path: Path) -> None:
        try:
            layout = self._layout_service.load(path)
        except Exception:
            return
        self._layout = layout
        self._layout_path = path
        self._rebuild_gauges()

    def _on_save(self) -> None:
        start_path = str(self._layout_path) if self._layout_path else ""
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Dashboard Layout", start_path, "Dashboard JSON (*.dashboard.json)"
        )
        if path_str:
            path = Path(path_str)
            if not path.suffix:
                path = path.with_suffix(".dashboard.json")
            self._layout_service.save(path, self._layout)
            self._layout_path = path

    def _on_reset(self) -> None:
        self._layout = self._layout_service.default_layout(
            gauge_configurations=self._gauge_configurations or None,
            front_page_gauges=self._front_page_gauges or None,
        )
        self._rebuild_gauges()

    def _on_fullscreen(self) -> None:
        if self._fullscreen_window is not None and self._fullscreen_window.isVisible():
            self._fullscreen_window.close()
            self._fullscreen_window = None
            return
        win = DashboardFullscreenWindow(self._layout, self)
        win.finished.connect(lambda: setattr(self, "_fullscreen_window", None))
        self._fullscreen_window = win
