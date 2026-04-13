from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TuningPageKind(StrEnum):
    TABLE = "table"
    PARAMETER_LIST = "parameter-list"
    CURVE = "curve"


class TuningPageParameterRole(StrEnum):
    TABLE = "table"
    X_AXIS = "x-axis"
    Y_AXIS = "y-axis"
    SCALAR = "scalar"
    AUXILIARY_TABLE = "auxiliary-table"
    AUXILIARY_SCALAR = "auxiliary-scalar"


class TuningPageStateKind(StrEnum):
    CLEAN = "clean"
    WRITTEN = "written"
    STAGED = "staged"
    INVALID = "invalid"


@dataclass(slots=True, frozen=True)
class TuningPageParameter:
    name: str
    label: str
    kind: str
    role: TuningPageParameterRole
    page: int | None
    offset: int | None
    units: str | None
    data_type: str
    shape: str
    help_text: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    digits: int | None = None
    options: tuple[str, ...] = ()
    option_values: tuple[str, ...] = ()
    visibility_expression: str | None = None
    requires_power_cycle: bool = False


@dataclass(slots=True, frozen=True)
class TuningPageSection:
    title: str
    parameter_names: tuple[str, ...]
    notes: tuple[str, ...] = ()
    visibility_expression: str | None = None


@dataclass(slots=True, frozen=True)
class TuningPage:
    page_id: str
    title: str
    group_id: str
    group_title: str
    page_number: int | None
    kind: TuningPageKind
    source: str
    parameter_names: tuple[str, ...]
    parameters: tuple[TuningPageParameter, ...]
    sections: tuple[TuningPageSection, ...]
    summary: str
    help_topic: str | None = None
    table_id: str | None = None
    map_id: str | None = None
    table_name: str | None = None
    x_axis_name: str | None = None
    y_axis_name: str | None = None
    x_axis_label: str | None = None
    y_axis_label: str | None = None
    visibility_expression: str | None = None
    # Curve-specific fields (populated when kind == CURVE)
    curve_name: str | None = None
    curve_x_bins_param: str | None = None   # x-axis parameter name (bin values)
    curve_x_channel: str | None = None       # live output channel for cursor
    curve_y_bins_params: tuple[str, ...] = ()  # editable y-axis parameter names
    curve_line_labels: tuple[str | None, ...] = ()  # per-y-bins display labels
    curve_gauge: str | None = None           # named gauge config for live reference


@dataclass(slots=True, frozen=True)
class TuningPageGroup:
    group_id: str
    title: str
    pages: tuple[TuningPage, ...]


@dataclass(slots=True, frozen=True)
class TuningPageState:
    kind: TuningPageStateKind
    detail: str | None = None

    @property
    def label(self) -> str:
        if self.kind == TuningPageStateKind.CLEAN:
            return "Clean"
        if self.kind == TuningPageStateKind.WRITTEN:
            return "Written"
        if self.kind == TuningPageStateKind.STAGED:
            return "Staged"
        return "Invalid"
