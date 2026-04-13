"""CurvePageService — compiles INI CurveDefinitions into TuningPage objects.

Curve pages sit alongside table pages in the tuning workspace navigator. Each
curve page represents one 1D correction curve (xBins → yBins mapping).

The service assigns each curve to an existing group category using the same
keyword-matching rules as TuningPageService, so curve pages land naturally
inside Fuel / Ignition / Idle / Startup-Enrich groups.
"""
from __future__ import annotations

import re

from tuner.domain.ecu_definition import CurveDefinition, EcuDefinition, ScalarParameterDefinition, TableDefinition
from tuner.domain.tuning_pages import (
    TuningPage,
    TuningPageGroup,
    TuningPageKind,
    TuningPageParameter,
    TuningPageParameterRole,
)


class CurvePageService:
    """Build TuningPage objects with kind=CURVE from the parsed CurveDefinitions."""

    _GROUP_RULES: tuple[tuple[int, str, str, tuple[str, ...]], ...] = (
        (10, "fuel",      "Fuel",             ("vetable", "fuel", "inject", "reqfuel", "baro", "density", "priming", "flex", "wmi")),
        (20, "ignition",  "Ignition",         ("spark", "ignition", "advance", "timing", "dwell", "knock", "rotary")),
        (30, "afr",       "AFR / Lambda",     ("afr", "lambda", "ego", "o2", "warmup_afr", "wue_afr")),
        (40, "idle",      "Idle",             ("idle", "iac")),
        (50, "enrich",    "Startup / Enrich", ("enrich", "warmup", "crank", "afterstart", "prime", "accel", "ase", "wue")),
        (60, "boost",     "Boost / Airflow",  ("boost", "map", "vvt", "turbo")),
        (70, "settings",  "Settings",         ("setting", "config", "option", "sensor", "calibration", "engine", "limit",
                                                "pwm", "fan", "protection", "oil", "coolant", "rolling")),
        (99, "other",     "Other",            ()),
    )

    def build_curve_pages(self, definition: EcuDefinition) -> list[TuningPageGroup]:
        """Return TuningPageGroup objects for all curves in the definition."""
        if not definition.curve_definitions:
            return []

        scalars_by_name: dict[str, ScalarParameterDefinition] = {
            s.name: s for s in definition.scalars
        }
        tables_by_name: dict[str, TableDefinition] = {
            t.name: t for t in definition.tables
        }

        from collections import defaultdict
        grouped: dict[tuple[int, str, str], list[TuningPage]] = defaultdict(list)

        for curve in definition.curve_definitions:
            page = self._build_curve_page(curve, scalars_by_name, tables_by_name)
            order, gid, gtitle = self._classify(curve)
            grouped[(order, gid, gtitle)].append(page)

        result: list[TuningPageGroup] = []
        for (_order, gid, gtitle), pages in sorted(grouped.items(), key=lambda x: x[0]):
            result.append(
                TuningPageGroup(
                    group_id=f"curve-{gid}",
                    title=gtitle,
                    pages=tuple(sorted(pages, key=lambda p: p.title.lower())),
                )
            )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_curve_page(
        self,
        curve: CurveDefinition,
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
    ) -> TuningPage:
        parameters: list[TuningPageParameter] = []
        param_names: list[str] = []

        # X-axis bins — read-only display (not directly editable via the curve UI)
        x_param = scalars_by_name.get(curve.x_bins_param) or tables_by_name.get(curve.x_bins_param)
        if x_param is not None:
            parameters.append(self._make_param(x_param, TuningPageParameterRole.X_AXIS, curve.x_label))
            param_names.append(x_param.name)

        # Y-axis bins — editable
        for yb in curve.y_bins_list:
            y_param = scalars_by_name.get(yb.param) or tables_by_name.get(yb.param)
            if y_param is not None:
                label = yb.label or curve.y_label or y_param.label or y_param.name
                parameters.append(self._make_param(y_param, TuningPageParameterRole.Y_AXIS, label))
                param_names.append(y_param.name)

        return TuningPage(
            page_id=f"curve:{curve.name}",
            title=curve.title,
            group_id="",  # filled at group level
            group_title="",
            page_number=None,
            kind=TuningPageKind.CURVE,
            source="curve-editor",
            parameter_names=tuple(param_names),
            parameters=tuple(parameters),
            sections=(),
            summary=self._summary(curve),
            help_topic=curve.topic_help,
            x_axis_label=curve.x_label,
            y_axis_label=curve.y_label,
            # Curve-specific
            curve_name=curve.name,
            curve_x_bins_param=curve.x_bins_param,
            curve_x_channel=curve.x_channel,
            curve_y_bins_params=tuple(yb.param for yb in curve.y_bins_list),
            curve_line_labels=tuple(yb.label for yb in curve.y_bins_list),
            curve_gauge=curve.gauge,
        )

    @staticmethod
    def _make_param(
        param: ScalarParameterDefinition | TableDefinition,
        role: TuningPageParameterRole,
        override_label: str | None,
    ) -> TuningPageParameter:
        return TuningPageParameter(
            name=param.name,
            label=override_label or param.label or param.name,
            kind=param.data_type,
            role=role,
            page=param.page,
            offset=param.offset,
            units=param.units,
            data_type=param.data_type,
            shape="array",
            help_text=param.help_text,
            min_value=param.min_value,
            max_value=param.max_value,
            digits=param.digits,
        )

    def _classify(self, curve: CurveDefinition) -> tuple[int, str, str]:
        text = (curve.name + " " + curve.title).lower()
        for order, gid, gtitle, keywords in self._GROUP_RULES:
            if any(re.search(r'\b' + re.escape(kw) + r'\b', text) for kw in keywords):
                return order, gid, gtitle
        return 99, "other", "Other"

    @staticmethod
    def _summary(curve: CurveDefinition) -> str:
        nbins = len(curve.y_bins_list)
        multi = f"{nbins} lines" if nbins > 1 else "1D"
        channel = f" · live: {curve.x_channel}" if curve.x_channel else ""
        return f"Curve · {multi}{channel}"
