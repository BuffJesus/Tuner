from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FieldOptionDefinition:
    value: str
    label: str


@dataclass(slots=True)
class ScalarParameterDefinition:
    name: str
    data_type: str
    label: str | None = None
    units: str | None = None
    page: int | None = None
    offset: int | None = None
    scale: float | None = None
    translate: float | None = None
    digits: int | None = None
    scale_expression: str | None = None
    translate_expression: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    options: tuple[FieldOptionDefinition, ...] = ()
    help_text: str | None = None
    visibility_expression: str | None = None
    requires_power_cycle: bool = False
    bit_offset: int | None = None
    bit_length: int | None = None


@dataclass(slots=True)
class TableDefinition:
    name: str
    rows: int
    columns: int
    label: str | None = None
    units: str | None = None
    page: int | None = None
    offset: int | None = None
    data_type: str = "U08"
    scale: float | None = None
    translate: float | None = None
    digits: int | None = None
    scale_expression: str | None = None
    translate_expression: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    help_text: str | None = None


@dataclass(slots=True)
class TableEditorDefinition:
    table_id: str
    map_id: str
    title: str
    page: int | None = None
    x_bins: str | None = None
    x_channel: str | None = None
    y_bins: str | None = None
    y_channel: str | None = None
    z_bins: str | None = None
    x_label: str | None = None
    y_label: str | None = None
    topic_help: str | None = None
    grid_height: float | None = None
    grid_orient: tuple[float, float, float] | None = None
    up_label: str | None = None
    down_label: str | None = None


@dataclass(slots=True)
class DialogFieldDefinition:
    label: str
    parameter_name: str | None = None
    visibility_expression: str | None = None
    is_static_text: bool = False


@dataclass(slots=True)
class DialogPanelReference:
    target: str
    position: str | None = None
    visibility_expression: str | None = None


@dataclass(slots=True)
class DialogDefinition:
    dialog_id: str
    title: str
    axis_hint: str | None = None
    fields: list[DialogFieldDefinition] = field(default_factory=list)
    panels: list[DialogPanelReference] = field(default_factory=list)


@dataclass(slots=True)
class MenuItemDefinition:
    target: str
    label: str | None = None
    page: int | None = None
    visibility_expression: str | None = None


@dataclass(slots=True)
class MenuDefinition:
    title: str
    items: list[MenuItemDefinition] = field(default_factory=list)


@dataclass(slots=True)
class XcpMemoryMapping:
    name: str
    address: int
    size: int
    data_type: str = "u32"
    units: str | None = None


@dataclass(slots=True)
class AutotuneFilterGate:
    """A single filter gate declaration from [VeAnalyze] or [WueAnalyze].

    Standard named gates (std_xAxisMin, std_DeadLambda, etc.) have no channel/operator/threshold.
    Parameterised gates carry all four fields.
    """

    name: str
    label: str | None = None
    channel: str | None = None
    operator: str | None = None      # "<", ">", "<=", ">=", "==", "!=", "&"
    threshold: float | None = None
    default_enabled: bool = True     # True = filter is active by default


@dataclass(slots=True)
class AutotuneMapDefinition:
    """Compiled autotune analysis section from [VeAnalyze] or [WueAnalyze].

    map_parts stores the raw comma-separated fields from the *AnalyzeMap line so
    consumers can interpret them without another parsing step.  For VeAnalyze the
    typical order is: map_table, lambda_target, lambda_channel, correction_channel.
    For WueAnalyze the order is longer and ECU-specific.
    """

    section_name: str                            # "VeAnalyze" or "WueAnalyze"
    map_parts: tuple[str, ...] = ()              # fields from *AnalyzeMap line
    lambda_target_tables: tuple[str, ...] = ()   # explicit lambdaTargetTables, if present
    filter_gates: tuple[AutotuneFilterGate, ...] = ()


@dataclass(slots=True)
class ToolDeclaration:
    """A tool entry declared via addTool in the [Tools] section."""

    tool_id: str
    label: str
    target_table_id: str | None = None


@dataclass(slots=True)
class CurveAxisRange:
    """Display range hint for one axis of a curve editor."""

    min: float
    max: float
    steps: int


@dataclass(slots=True)
class CurveYBins:
    """One y-axis (editable) bin reference in a curve definition.

    Multi-line curves (e.g. WUE analyze showing current vs recommended) have
    multiple CurveYBins entries.
    """

    param: str               # parameter name in [Constants] — the editable array
    label: str | None = None  # optional line label for multi-line curves


@dataclass(slots=True)
class CurveDefinition:
    """A 1D correction curve declared in [CurveEditor].

    x-axis: firmware-constant bin values (the x_bins_param array); may carry a
    live output channel (x_channel) for a runtime cursor.

    y-axis: one or more editable parameter arrays (y_bins_list); multi-line curves
    appear as separate CurveYBins entries with individual labels.
    """

    name: str
    title: str
    x_bins_param: str              # parameter name for x-axis bin values
    x_channel: str | None = None   # output channel for live cursor on x axis
    y_bins_list: list[CurveYBins] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    x_axis: CurveAxisRange | None = None
    y_axis: CurveAxisRange | None = None
    topic_help: str | None = None
    gauge: str | None = None       # named gauge config for live cursor display
    size: tuple[int, int] | None = None


@dataclass(slots=True)
class GaugeConfiguration:
    """A named gauge configuration declared in [GaugeConfigurations].

    Thresholds that use inline TunerStudio expressions (e.g. ``{rpmhigh}``) are
    stored as ``None`` — they cannot be evaluated without a live runtime context.
    """

    name: str
    channel: str
    title: str
    units: str
    lo: float | None = None
    hi: float | None = None
    lo_danger: float | None = None
    lo_warn: float | None = None
    hi_warn: float | None = None
    hi_danger: float | None = None
    value_digits: int = 0
    label_digits: int = 0
    category: str | None = None


@dataclass(slots=True)
class FrontPageIndicator:
    """A status indicator declared in [FrontPage].

    The expression is stored raw (braces stripped) for later evaluation against
    live output channel values.
    """

    expression: str   # e.g. ``running``, ``(tps > tpsflood) && (rpm < crankRPM)``
    off_label: str
    on_label: str
    off_bg: str       # color name: "white", "red", "green", "yellow"
    off_fg: str
    on_bg: str
    on_fg: str


@dataclass(slots=True, frozen=True)
class ControllerCommand:
    """One entry from ``[ControllerCommands]`` — a named raw-byte ECU command.

    These commands bypass normal page sync and are intended for bench testing
    (injector/spark activation, STM32 reboot, SD format, VSS calibration).
    The ``payload`` bytes are sent verbatim; no framing beyond the transport layer.
    """
    name: str     # INI key, e.g. ``cmdtestinj1on``
    payload: bytes  # decoded command bytes, e.g. b"E\\x02\\x01"


@dataclass(slots=True, frozen=True)
class LoggerRecordField:
    """One raw binary field declared in a ``recordField`` line of ``[LoggerDefinition]``."""
    name: str
    header: str
    start_bit: int    # bit offset within the record (0-based)
    bit_count: int    # number of bits
    scale: float      # multiply raw value by this to get display value
    units: str


@dataclass(slots=True, frozen=True)
class LoggerDefinition:
    """One logger declared in ``[LoggerDefinition]`` (tooth, composite, …).

    ``data_read_command`` is the fully-resolved byte string to send when reading
    the log buffer — ``$tsCanId`` has been substituted with ``\\x00\\x00`` (direct
    connection default) and all ``\\xNN`` escapes have been decoded.
    """
    name: str               # INI key, e.g. ``tooth``
    display_name: str       # e.g. ``"Tooth Logger"``
    kind: str               # ``tooth`` or ``composite``
    start_command: str      # single-char firmware command, e.g. ``"H"``
    stop_command: str       # e.g. ``"h"``
    data_read_command: bytes
    data_read_timeout_ms: int   # default 5000
    continuous_read: bool
    record_header_len: int  # from ``recordDef`` first field
    record_footer_len: int  # from ``recordDef`` second field
    record_len: int         # bytes per record, from ``recordDef`` third field
    record_count: int       # total records (tooth=127, composite=127)
    record_fields: tuple[LoggerRecordField, ...]


@dataclass(slots=True)
class FormulaOutputChannel:
    """Virtual / computed output channel defined in [OutputChannels] as
    ``name = { expression }`` — a derived value computed from other output
    channels at runtime (e.g. ``coolant = { coolantRaw - 40 }``).

    The ``formula_expression`` field stores the verbatim expression text
    with surrounding braces stripped. Evaluation is deferred to a later
    ``MathExpressionEvaluator`` slice — this model captures catalog state
    only.
    """

    name: str
    formula_expression: str
    units: str | None = None
    digits: int | None = None


@dataclass(slots=True)
class ReferenceTableSolution:
    label: str
    expression: str | None = None


@dataclass(slots=True)
class ReferenceTableDefinition:
    table_id: str
    label: str
    topic_help: str | None = None
    table_identifier: str | None = None
    solutions_label: str | None = None
    solutions: list[ReferenceTableSolution] = field(default_factory=list)


@dataclass(slots=True)
class SettingGroupOption:
    symbol: str   # e.g. "DEFAULT", "mcu_teensy", "pressure_bar"
    label: str    # e.g. "Arduino Mega 2560", "Teensy"


@dataclass(slots=True)
class SettingGroupDefinition:
    symbol: str          # reference name / flag, e.g. "mcu", "enablehardware_test"
    label: str           # display name, e.g. "Controller in use"
    options: list[SettingGroupOption] = field(default_factory=list)
    # Groups with no options are boolean flags (present = enabled, absent = disabled)


@dataclass(slots=True)
class EcuDefinition:
    name: str
    firmware_signature: str | None = None
    transport_hint: str | None = None
    query_command: str | None = None
    version_info_command: str | None = None
    page_read_command: str | None = None
    page_value_write_command: str | None = None
    page_chunk_write_command: str | None = None
    burn_command: str | None = None
    endianness: str | None = None
    blocking_factor: int | None = None
    table_blocking_factor: int | None = None
    page_sizes: list[int] = field(default_factory=list)
    scalars: list[ScalarParameterDefinition] = field(default_factory=list)
    tables: list[TableDefinition] = field(default_factory=list)
    table_editors: list[TableEditorDefinition] = field(default_factory=list)
    dialogs: list[DialogDefinition] = field(default_factory=list)
    menus: list[MenuDefinition] = field(default_factory=list)
    output_channels: list[str] = field(default_factory=list)
    xcp_mappings: list[XcpMemoryMapping] = field(default_factory=list)
    output_channel_definitions: list[ScalarParameterDefinition] = field(default_factory=list)
    autotune_maps: list[AutotuneMapDefinition] = field(default_factory=list)
    tool_declarations: list[ToolDeclaration] = field(default_factory=list)
    reference_tables: list[ReferenceTableDefinition] = field(default_factory=list)
    setting_help: dict[str, str] = field(default_factory=dict)
    requires_power_cycle: set[str] = field(default_factory=set)
    metadata: dict[str, str] = field(default_factory=dict)
    page_titles: dict[int, str] = field(default_factory=dict)
    setting_groups: list[SettingGroupDefinition] = field(default_factory=list)
    output_channel_arrays: dict[str, list[float]] = field(default_factory=dict)
    curve_definitions: list[CurveDefinition] = field(default_factory=list)
    gauge_configurations: list[GaugeConfiguration] = field(default_factory=list)
    front_page_gauges: list[str] = field(default_factory=list)   # gauge1-8 in order
    front_page_indicators: list[FrontPageIndicator] = field(default_factory=list)
    logger_definitions: list[LoggerDefinition] = field(default_factory=list)
    controller_commands: list[ControllerCommand] = field(default_factory=list)
    formula_output_channels: list[FormulaOutputChannel] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Endianness consumer (Fragile area #3)
    # ------------------------------------------------------------------
    #
    # ``endianness`` is parsed from the INI ``endianness = big|little`` line
    # but no byte-order-aware read/write code path consumes it yet (current
    # Speeduino raw-protocol code assumes little-endian throughout). These
    # helpers are the canonical way for future consumers to query byte
    # order so the default behaviour stays in one place — flipping the
    # default would otherwise require auditing every call site.

    def is_little_endian(self) -> bool:
        """Return True when the definition advertises little-endian byte
        order or has no explicit endianness (the historical Speeduino
        assumption). Comparison is case-insensitive and tolerant of
        whitespace; unrecognized values fall back to little-endian so a
        typo never silently flips the byte order on existing fixtures.
        """
        if self.endianness is None:
            return True
        text = self.endianness.strip().lower()
        if text == "big":
            return False
        return True

    def byte_order(self) -> str:
        """Return ``"little"`` or ``"big"`` — the form Python's ``int``
        and ``struct`` modules expect. Pure derivation from
        ``is_little_endian()`` so the two helpers cannot diverge."""
        return "little" if self.is_little_endian() else "big"
