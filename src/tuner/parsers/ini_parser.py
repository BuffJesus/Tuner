from __future__ import annotations

import re
from pathlib import Path

from tuner.domain.ecu_definition import (
    AutotuneFilterGate,
    AutotuneMapDefinition,
    ControllerCommand,
    CurveAxisRange,
    CurveDefinition,
    CurveYBins,
    DialogDefinition,
    DialogFieldDefinition,
    DialogPanelReference,
    EcuDefinition,
    FieldOptionDefinition,
    FormulaOutputChannel,
    FrontPageIndicator,
    GaugeConfiguration,
    LoggerDefinition,
    LoggerRecordField,
    MenuDefinition,
    MenuItemDefinition,
    ReferenceTableDefinition,
    ReferenceTableSolution,
    ScalarParameterDefinition,
    SettingGroupDefinition,
    SettingGroupOption,
    TableDefinition,
    TableEditorDefinition,
    ToolDeclaration,
    XcpMemoryMapping,
)
from tuner.parsers.common import parse_key_value_lines, preprocess_ini_lines


class IniParser:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def parse(
        self,
        path: Path,
        active_settings: frozenset[str] = frozenset(),
    ) -> EcuDefinition:
        if path.exists():
            raw_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            self._lines = preprocess_ini_lines(raw_lines, active_settings)
        else:
            self._lines = []
        metadata = parse_key_value_lines(self._lines)
        signature = self._strip_quotes(metadata.get("signature"))
        definition = EcuDefinition(
            name=signature or self._strip_quotes(metadata.get("name")) or path.stem,
            firmware_signature=signature,
            transport_hint=self._strip_quotes(metadata.get("transport", metadata.get("protocol"))),
            query_command=self._strip_quotes(metadata.get("queryCommand")),
            version_info_command=self._strip_quotes(metadata.get("versionInfo")),
            page_read_command=self._first_command(metadata.get("pageReadCommand")),
            page_value_write_command=self._first_command(metadata.get("pageValueWrite")),
            page_chunk_write_command=self._first_command(metadata.get("pageChunkWrite")),
            burn_command=self._first_command(metadata.get("burnCommand")),
            endianness=self._strip_quotes(metadata.get("endianness")),
            metadata=metadata,
        )
        definition.output_channels = self._parse_list(metadata.get("outputChannels"))
        definition.page_sizes = self._parse_int_list(metadata.get("pageSize"))
        definition.blocking_factor = self._parse_first_int(metadata.get("blockingFactor"))
        definition.table_blocking_factor = self._parse_first_int(metadata.get("tableBlockingFactor"))
        defines = self._collect_defines(path)
        self._parse_constant_definitions(path, definition, defines)
        self._parse_pc_variables(path, definition, defines)
        self._parse_output_channels(path, definition, defines)
        self._parse_table_editors(path, definition)
        self._parse_dialogs(path, definition)
        self._parse_menus(path, definition)
        self._parse_setting_context_help(path, definition)
        self._parse_constants_extensions(path, definition)
        self._parse_autotune_sections(path, definition)
        self._parse_tools(path, definition)
        self._parse_reference_tables(path, definition)
        self._parse_curve_editors(path, definition)
        self._parse_gauge_configurations(path, definition)
        self._parse_front_page(path, definition)
        self._parse_logger_definitions(path, definition)
        self._parse_controller_commands(path, definition)
        self._apply_definition_metadata(definition)
        if not definition.scalars:
            scalar_names = self._parse_list(metadata.get("constants")) or self._parse_list(metadata.get("scalars"))
            definition.scalars = [
                ScalarParameterDefinition(name=name, data_type="float")
                for name in scalar_names
            ]
        if not definition.output_channels and definition.output_channel_definitions:
            definition.output_channels = [field.name for field in definition.output_channel_definitions]
        definition.xcp_mappings = self._parse_xcp_mappings(metadata)
        self._parse_setting_groups(path, definition)
        return definition

    @staticmethod
    def _parse_list(raw_value: str | None) -> list[str]:
        if not raw_value:
            return []
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    @staticmethod
    def _parse_xcp_mappings(metadata: dict[str, str]) -> list[XcpMemoryMapping]:
        mappings: list[XcpMemoryMapping] = []
        prefix = "xcpMap."
        for key, value in metadata.items():
            if not key.startswith(prefix):
                continue
            name = key[len(prefix) :]
            parts = [part.strip() for part in value.split(",")]
            if len(parts) < 2:
                continue
            address = int(parts[0], 0)
            size = int(parts[1], 0)
            data_type = parts[2] if len(parts) > 2 and parts[2] else "u32"
            units = parts[3] if len(parts) > 3 and parts[3] else None
            mappings.append(
                XcpMemoryMapping(
                    name=name,
                    address=address,
                    size=size,
                    data_type=data_type.lower(),
                    units=units,
                )
            )
        return mappings

    @staticmethod
    def _parse_int_list(raw_value: str | None) -> list[int]:
        if not raw_value:
            return []
        values: list[int] = []
        for part in raw_value.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(int(part, 0))
            except ValueError:
                continue
        return values

    @staticmethod
    def _parse_first_int(raw_value: str | None) -> int | None:
        """Parse the first integer from a comma-separated INI value, e.g. blockingFactor."""
        if not raw_value:
            return None
        first = raw_value.split(",", 1)[0].split(";", 1)[0].strip()
        try:
            return int(first, 0)
        except ValueError:
            return None

    @staticmethod
    def _strip_quotes(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.split(";", 1)[0].strip()
        return stripped.strip('"')

    def _parse_constant_definitions(self, path: Path, definition: EcuDefinition, defines: dict[str, list[str]] | None = None) -> None:
        if not path.exists():
            return
        current_page: int | None = None
        current_page_next_offset = 0
        in_constants = False
        comment_block: list[str] = []
        pattern = re.compile(
            r"^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|string|bits)\s*,\s*([A-Za-z0-9]+)\s*,\s*([A-Za-z0-9_]+)"
            r"(?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$"
        )
        for raw_line in self._lines:
            line = raw_line.strip()
            if not line:
                comment_block = []
                continue
            if line.startswith(";"):
                comment_block.append(line)
                continue
            if line.startswith("#"):
                comment_block = []
                continue
            if line.startswith("["):
                in_constants = line.lower() == "[constants]"
                comment_block = []
                continue
            if not in_constants:
                comment_block = []
                continue
            if line.startswith("page"):
                _, _, value = line.partition("=")
                try:
                    current_page = int(value.strip(), 0)
                except ValueError:
                    current_page = None
                current_page_next_offset = 0
                if current_page is not None:
                    title = self._infer_constant_page_title(comment_block, current_page)
                    if title:
                        definition.page_titles[current_page] = title
                comment_block = []
                continue
            match = pattern.match(raw_line)
            if not match:
                comment_block = []
                continue
            name, entry_kind, data_type, offset, shape, remainder = match.groups()
            parts = self._parse_csv(remainder)
            units = self._parse_value_token(parts[0]) if parts else None
            scale = self._parse_float_token(parts[1]) if len(parts) > 1 else None
            translate = self._parse_float_token(parts[2]) if len(parts) > 2 else None
            min_value = self._parse_float_token(parts[3]) if len(parts) > 3 else None
            max_value = self._parse_float_token(parts[4]) if len(parts) > 4 else None
            digits = self._parse_int_token(parts[5]) if len(parts) > 5 else None
            offset_int = self._resolve_constant_offset(offset, current_page_next_offset)
            if offset_int is None:
                comment_block = []
                continue
            if entry_kind == "scalar" or entry_kind == "string":
                definition.scalars.append(
                    ScalarParameterDefinition(
                        name=name,
                        label=name,
                        data_type=data_type,
                        units=units,
                        page=current_page,
                        offset=offset_int,
                        scale=scale,
                        translate=translate,
                        digits=digits,
                        scale_expression=parts[1] if len(parts) > 1 and scale is None else None,
                        translate_expression=parts[2] if len(parts) > 2 and translate is None else None,
                        min_value=min_value,
                        max_value=max_value,
                    )
                )
                current_page_next_offset = max(
                    current_page_next_offset,
                    offset_int + self._constant_storage_size(data_type, None, entry_kind=entry_kind),
                )
            elif entry_kind == "bits":
                bit_offset, bit_length = self._parse_bit_shape(shape)
                expanded = self._expand_options(parts, defines or {})
                options = tuple(
                    FieldOptionDefinition(value=str(index), label=option)
                    for index, option in enumerate(expanded)
                    if option
                )
                definition.scalars.append(
                    ScalarParameterDefinition(
                        name=name,
                        label=name,
                        data_type=data_type,
                        page=current_page,
                        offset=offset_int,
                        options=options,
                        bit_offset=bit_offset,
                        bit_length=bit_length,
                    )
                )
                current_page_next_offset = max(
                    current_page_next_offset,
                    offset_int + self._constant_storage_size(data_type, None, entry_kind=entry_kind),
                )
            elif entry_kind == "array" and shape:
                rows, cols = self._parse_shape(shape)
                definition.tables.append(
                    TableDefinition(
                        name=name,
                        label=name,
                        rows=rows,
                        columns=cols,
                        units=units,
                        page=current_page,
                        offset=offset_int,
                        data_type=data_type,
                        scale=scale,
                        translate=translate,
                        digits=digits,
                        scale_expression=parts[1] if len(parts) > 1 and scale is None else None,
                        translate_expression=parts[2] if len(parts) > 2 and translate is None else None,
                        min_value=min_value,
                        max_value=max_value,
                    )
                )
                current_page_next_offset = max(
                    current_page_next_offset,
                    offset_int + self._constant_storage_size(data_type, shape, entry_kind=entry_kind),
                )
            comment_block = []

    @staticmethod
    def _resolve_constant_offset(token: str, current_page_next_offset: int) -> int | None:
        token = token.strip()
        if token.lower() == "lastoffset":
            return current_page_next_offset
        try:
            return int(token, 0)
        except ValueError:
            return None

    @staticmethod
    def _constant_storage_size(data_type: str, shape: str | None, *, entry_kind: str) -> int:
        widths = {
            "U08": 1,
            "S08": 1,
            "U16": 2,
            "S16": 2,
            "U32": 4,
            "S32": 4,
            "F32": 4,
        }
        width = widths.get(data_type.upper(), 1)
        if entry_kind == "array" and shape:
            rows, cols = IniParser._parse_shape(shape)
            return width * rows * cols
        return width

    @classmethod
    def _infer_constant_page_title(cls, comments: list[str], page_number: int) -> str | None:
        candidates: list[str] = []
        for raw_comment in comments:
            comment = raw_comment.lstrip(";").strip()
            if not comment or set(comment) == {"-"}:
                continue
            if re.fullmatch(r"(?i)start\s+page\s+\d+", comment):
                continue
            normalized = cls._normalize_page_comment(comment, page_number)
            if normalized:
                candidates.append(normalized)
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-len(item), item))
        return candidates[0]

    @staticmethod
    def _normalize_page_comment(comment: str, page_number: int) -> str | None:
        text = comment.strip().rstrip(".")
        if not text:
            return None

        text = re.sub(rf"(?i)\(page\s*{page_number}\)", "", text).strip()
        text = re.sub(rf"(?i)^page\s*{page_number}\s+is\s+", "", text).strip()
        text = re.sub(r"(?i)^these are\s+", "", text).strip()
        text = re.sub(r"(?i)^this is\s+", "", text).strip()
        text = re.sub(r"(?i)\(previously.*?\)", "", text).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            return None

        lowered = text.lower()
        replacements = {
            "all general settings": "General Settings",
            "all settings associated with o2/afr": "O2/AFR Settings",
            "primarily ignition related settings": "Ignition Settings",
            "the programmable outputs": "Programmable Outputs",
            "boost duty lookup map": "Boost Duty Lookup",
        }
        if lowered in replacements:
            return replacements[lowered]

        if lowered.endswith(" settings"):
            return text.title()
        if lowered.endswith(" outputs"):
            return text.title()
        if lowered.endswith(" map"):
            return text.title()
        return text.title()

    def _parse_pc_variables(self, path: Path, definition: EcuDefinition, defines: dict[str, list[str]] | None = None) -> None:
        """Parse [PcVariables] section — same format as [Constants] but without an offset field."""
        if not path.exists():
            return
        in_pc_vars = False
        # scalar:  name = scalar, TYPE, "units", scale, translate, lo, hi, digits
        # bits:    name = bits,   TYPE, [shape], "opt1", ...
        # array:   name = array,  TYPE, [shape], "units", scale, translate, lo, hi, digits
        pattern = re.compile(
            r"^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,\s*([A-Za-z0-9]+)"
            r"(?:\s*,\s*(\[[^\]]+\]))?\s*,\s*(.+)$"
        )
        for raw_line in self._lines:
            line = raw_line.strip()
            if not line or line.startswith((";", "#")):
                continue
            if line.startswith("["):
                in_pc_vars = line.lower() == "[pcvariables]"
                continue
            if not in_pc_vars:
                continue
            match = pattern.match(raw_line)
            if not match:
                continue
            name, entry_kind, data_type, shape, remainder = match.groups()
            parts = self._parse_csv(remainder)
            units = self._parse_value_token(parts[0]) if parts else None
            scale = self._parse_float_token(parts[1]) if len(parts) > 1 else None
            translate = self._parse_float_token(parts[2]) if len(parts) > 2 else None
            min_value = self._parse_float_token(parts[3]) if len(parts) > 3 else None
            max_value = self._parse_float_token(parts[4]) if len(parts) > 4 else None
            digits = self._parse_int_token(parts[5]) if len(parts) > 5 else None
            if entry_kind == "scalar":
                definition.scalars.append(
                    ScalarParameterDefinition(
                        name=name,
                        label=name,
                        data_type=data_type,
                        units=units,
                        page=None,
                        offset=None,
                        scale=scale,
                        translate=translate,
                        digits=digits,
                        scale_expression=parts[1] if len(parts) > 1 and scale is None else None,
                        translate_expression=parts[2] if len(parts) > 2 and translate is None else None,
                        min_value=min_value,
                        max_value=max_value,
                    )
                )
            elif entry_kind == "bits":
                bit_offset, bit_length = self._parse_bit_shape(shape)
                expanded = self._expand_options(parts, defines or {})
                options = tuple(
                    FieldOptionDefinition(value=str(index), label=option)
                    for index, option in enumerate(expanded)
                    if option
                )
                definition.scalars.append(
                    ScalarParameterDefinition(
                        name=name,
                        label=name,
                        data_type=data_type,
                        page=None,
                        offset=None,
                        options=options,
                        bit_offset=bit_offset,
                        bit_length=bit_length,
                    )
                )
            elif entry_kind == "array" and shape:
                rows, cols = self._parse_shape(shape)
                definition.tables.append(
                    TableDefinition(
                        name=name,
                        label=name,
                        rows=rows,
                        columns=cols,
                        units=units,
                        page=None,
                        offset=None,
                        data_type=data_type,
                        scale=scale,
                        translate=translate,
                        digits=digits,
                        scale_expression=parts[1] if len(parts) > 1 and scale is None else None,
                        translate_expression=parts[2] if len(parts) > 2 and translate is None else None,
                        min_value=min_value,
                        max_value=max_value,
                    )
                )

    def _parse_output_channels(self, path: Path, definition: EcuDefinition, defines: dict[str, list[str]] | None = None) -> None:
        if not path.exists():
            return
        in_output_channels = False
        pattern = re.compile(
            r"^\s*([A-Za-z0-9_]+)\s*=\s*(scalar|array|bits)\s*,\s*([A-Za-z0-9]+)\s*,\s*([0-9]+)"
            r"(?:\s*,\s*(\[[^\]]+\]))?(?:\s*,\s*(.+))?$"
        )
        array_pattern = re.compile(
            r"^\s*([A-Za-z0-9_]+)\s*=\s*array\s*,\s*[A-Za-z0-9]+\s*,\s*\[([0-9]+)\]"
        )
        default_value_pattern = re.compile(
            r"^\s*defaultValue\s*=\s*([A-Za-z0-9_]+)\s*,\s*(.+)$"
        )
        # Virtual / formula output channel:  name = { expression } [, "units"] [, digits]
        # Expression body stored verbatim (braces stripped, whitespace trimmed).
        formula_pattern = re.compile(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.+?)\}\s*(?:,\s*(.+?))?\s*$"
        )
        array_names: set[str] = set()
        for raw_line in self._lines:
            line = raw_line.strip()
            if not line or line.startswith((";", "#")):
                continue
            if line.startswith("["):
                in_output_channels = line.lower() == "[outputchannels]"
                continue
            if not in_output_channels:
                continue
            # Array type output channels (e.g. boardHasRTC = array, U08, [128], ...)
            arr_match = array_pattern.match(raw_line)
            if arr_match:
                array_names.add(arr_match.group(1))
                continue
            # defaultValue = arrayName, val0 val1 val2 ...
            dv_match = default_value_pattern.match(raw_line)
            if dv_match:
                arr_name = dv_match.group(1)
                if arr_name in array_names:
                    values_str = dv_match.group(2).strip()
                    values = []
                    for token in values_str.split():
                        try:
                            values.append(float(token))
                        except ValueError:
                            break
                    if values:
                        definition.output_channel_arrays[arr_name] = values
                continue
            # Virtual / formula output channel branch. Checked before the
            # scalar/array/bits pattern: the formula regex only matches lines
            # whose RHS begins with ``{``, so real ``scalar, U08, …`` lines
            # (which may carry ``{ expression }`` tokens *after* the keyword)
            # still fall through to the scalar branch below.
            formula_candidate = raw_line
            semi_pos = formula_candidate.find(";")
            if semi_pos >= 0:
                formula_candidate = formula_candidate[:semi_pos]
            formula_match = formula_pattern.match(formula_candidate)
            if formula_match:
                f_name = formula_match.group(1)
                f_expr = formula_match.group(2).strip()
                f_trailing = formula_match.group(3)
                f_units: str | None = None
                f_digits: int | None = None
                if f_trailing:
                    trail_parts = self._parse_csv(f_trailing)
                    if trail_parts:
                        f_units = self._parse_value_token(trail_parts[0])
                    if len(trail_parts) > 1:
                        f_digits = self._parse_int_token(trail_parts[1])
                definition.formula_output_channels.append(
                    FormulaOutputChannel(
                        name=f_name,
                        formula_expression=f_expr,
                        units=f_units,
                        digits=f_digits,
                    )
                )
                continue
            match = pattern.match(raw_line)
            if not match:
                continue
            name, entry_kind, data_type, offset, shape, remainder = match.groups()
            parts = self._parse_csv(remainder) if remainder else []
            units = self._parse_value_token(parts[0]) if parts else None
            scale = self._parse_float_token(parts[1]) if len(parts) > 1 else None
            translate = self._parse_float_token(parts[2]) if len(parts) > 2 else None
            offset_int = int(offset, 0)
            if entry_kind == "bits":
                bit_offset, bit_length = self._parse_bit_shape(shape)
                expanded = self._expand_options(parts, defines or {})
                options = tuple(
                    FieldOptionDefinition(value=str(index), label=option)
                    for index, option in enumerate(expanded)
                    if option
                )
                definition.output_channel_definitions.append(
                    ScalarParameterDefinition(
                        name=name,
                        label=name,
                        data_type=data_type,
                        units=units,
                        page=None,
                        offset=offset_int,
                        scale=scale,
                        translate=translate,
                        options=options,
                        bit_offset=bit_offset,
                        bit_length=bit_length,
                    )
                )
                continue
            if entry_kind != "scalar":
                continue
            definition.output_channel_definitions.append(
                ScalarParameterDefinition(
                    name=name,
                    label=name,
                    data_type=data_type,
                    units=units,
                    page=None,
                    offset=offset_int,
                    scale=scale,
                    translate=translate,
                    digits=self._parse_int_token(parts[5]) if len(parts) > 5 else None,
                    scale_expression=parts[1] if len(parts) > 1 and scale is None else None,
                    translate_expression=parts[2] if len(parts) > 2 and translate is None else None,
                    min_value=self._parse_float_token(parts[3]) if len(parts) > 3 else None,
                    max_value=self._parse_float_token(parts[4]) if len(parts) > 4 else None,
                )
            )

    def _parse_table_editors(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        current_editor: TableEditorDefinition | None = None
        in_table_editor = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_table_editor = stripped.lower() == "[tableeditor]"
                continue
            if not in_table_editor:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key == "table":
                parts = self._parse_csv(value)
                if len(parts) < 3:
                    continue
                page = None
                if len(parts) > 3:
                    try:
                        page = int(parts[3], 0)
                    except ValueError:
                        page = None
                current_editor = TableEditorDefinition(
                    table_id=parts[0],
                    map_id=parts[1],
                    title=parts[2],
                    page=page,
                )
                definition.table_editors.append(current_editor)
                continue
            if current_editor is None:
                continue
            parts = self._parse_csv(value)
            if key == "topicHelp":
                current_editor.topic_help = self._strip_quotes(value)
            elif key == "xBins" and parts:
                current_editor.x_bins = parts[0]
                current_editor.x_channel = parts[1] if len(parts) > 1 else None
            elif key == "yBins" and parts:
                current_editor.y_bins = parts[0]
                current_editor.y_channel = parts[1] if len(parts) > 1 else None
            elif key == "zBins" and parts:
                current_editor.z_bins = parts[0]
            elif key == "xyLabels" and parts:
                current_editor.x_label = parts[0]
                current_editor.y_label = parts[1] if len(parts) > 1 else None
            elif key == "gridHeight" and parts:
                try:
                    current_editor.grid_height = float(parts[0])
                except ValueError:
                    pass
            elif key == "gridOrient" and len(parts) >= 3:
                try:
                    current_editor.grid_orient = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    pass
            elif key == "upDownLabel" and parts:
                current_editor.up_label = parts[0]
                current_editor.down_label = parts[1] if len(parts) > 1 else None

    def _parse_dialogs(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        current_dialog: DialogDefinition | None = None
        in_user_defined = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_user_defined = stripped.lower() == "[userdefined]"
                continue
            if not in_user_defined:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key == "dialog":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                current_dialog = DialogDefinition(
                    dialog_id=parts[0],
                    title=parts[1] if len(parts) > 1 else parts[0],
                    axis_hint=parts[2] if len(parts) > 2 else None,
                )
                definition.dialogs.append(current_dialog)
                continue
            if current_dialog is None:
                continue
            if key == "field":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                visibility = next((part for part in parts[1:] if part.startswith("{") and part.endswith("}")), None)
                parameter_name = next(
                    (
                        part
                        for part in parts[1:]
                        if part
                        and part not in {"{}"}
                        and not (part.startswith("{") and part.endswith("}"))
                    ),
                    None,
                )
                current_dialog.fields.append(
                    DialogFieldDefinition(
                        label=parts[0],
                        parameter_name=parameter_name,
                        visibility_expression=visibility,
                        is_static_text=parameter_name is None,
                    )
                )
            elif key == "panel":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                position = next(
                    (
                        part
                        for part in parts[1:]
                        if part
                        and part not in {"{}"}
                        and not (part.startswith("{") and part.endswith("}"))
                    ),
                    None,
                )
                visibility = next((part for part in parts[1:] if part.startswith("{") and part.endswith("}")), None)
                current_dialog.panels.append(
                    DialogPanelReference(
                        target=parts[0],
                        position=position,
                        visibility_expression=visibility,
                    )
                )

    def _parse_menus(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        current_menu: MenuDefinition | None = None
        in_menu_section = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_menu_section = stripped.lower() == "[menu]"
                continue
            if not in_menu_section:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key == "menu":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                current_menu = MenuDefinition(title=parts[0])
                definition.menus.append(current_menu)
                continue
            if current_menu is None or key not in {"subMenu", "groupChildMenu"}:
                continue
            parts = self._parse_csv(value)
            if not parts or parts[0] == "std_separator":
                continue
            label = parts[1] if len(parts) > 1 else parts[0]
            page = None
            visibility = None
            for part in parts[2:]:
                if part.startswith("{") and part.endswith("}"):
                    visibility = part
                    continue
                if page is None:
                    try:
                        page = int(part, 0)
                    except ValueError:
                        pass
            current_menu.items.append(
                MenuItemDefinition(
                    target=parts[0],
                    label=label,
                    page=page,
                    visibility_expression=visibility,
                )
            )

    def _parse_setting_context_help(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        in_help = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_help = stripped.lower() == "[settingcontexthelp]"
                continue
            if not in_help or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            definition.setting_help[key.strip()] = self._strip_quotes(value)

    def _parse_constants_extensions(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        in_extensions = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_extensions = stripped.lower() == "[constantsextensions]"
                continue
            if not in_extensions or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "requiresPowerCycle":
                for name in value.split(";", 1)[0].split(","):
                    name = name.strip()
                    if name:
                        definition.requires_power_cycle.add(name)

    def _parse_autotune_sections(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [VeAnalyze] and [WueAnalyze] sections into AutotuneMapDefinition objects."""
        if not path.exists():
            return
        autotune_section_names = {"[veanalyze]", "[wueanalyze]"}
        current_section_name: str | None = None
        map_parts: list[str] = []
        lambda_target_tables: list[str] = []
        filter_gates: list[AutotuneFilterGate] = []
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                if current_section_name is not None:
                    definition.autotune_maps.append(
                        AutotuneMapDefinition(
                            section_name=current_section_name,
                            map_parts=tuple(map_parts),
                            lambda_target_tables=tuple(lambda_target_tables),
                            filter_gates=tuple(filter_gates),
                        )
                    )
                lower = stripped.lower()
                if lower in autotune_section_names:
                    current_section_name = stripped[1:-1]  # strip brackets, preserve case
                    map_parts = []
                    lambda_target_tables = []
                    filter_gates = []
                else:
                    current_section_name = None
                continue
            if current_section_name is None:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key in {"veAnalyzeMap", "wueAnalyzeMap"}:
                map_parts = [p.strip() for p in value.split(",") if p.strip()]
            elif key == "lambdaTargetTables":
                lambda_target_tables = [p.strip() for p in value.split(",") if p.strip()]
            elif key == "filter":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                name = parts[0]
                if len(parts) == 1:
                    # Standard named filter with no additional params
                    filter_gates.append(AutotuneFilterGate(name=name))
                elif len(parts) >= 6:
                    # Parameterised: name, "label", channel, operator, threshold, default_enabled
                    label = parts[1] if len(parts) > 1 else None
                    channel = parts[2] if len(parts) > 2 else None
                    operator = parts[3] if len(parts) > 3 else None
                    threshold = self._parse_float_token(parts[4]) if len(parts) > 4 else None
                    default_enabled = parts[5].strip().lower() != "false" if len(parts) > 5 else True
                    filter_gates.append(
                        AutotuneFilterGate(
                            name=name,
                            label=label or None,
                            channel=channel or None,
                            operator=operator or None,
                            threshold=threshold,
                            default_enabled=default_enabled,
                        )
                    )
                else:
                    # Partial declaration — store name only
                    filter_gates.append(AutotuneFilterGate(name=name))
        # Flush last section
        if current_section_name is not None:
            definition.autotune_maps.append(
                AutotuneMapDefinition(
                    section_name=current_section_name,
                    map_parts=tuple(map_parts),
                    lambda_target_tables=tuple(lambda_target_tables),
                    filter_gates=tuple(filter_gates),
                )
            )

    def _parse_tools(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [Tools] section addTool declarations into ToolDeclaration objects."""
        if not path.exists():
            return
        in_tools = False
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_tools = stripped.lower() == "[tools]"
                continue
            if not in_tools:
                continue
            key, sep, value = stripped.partition("=")
            if not sep or key.strip() != "addTool":
                continue
            parts = self._parse_csv(value)
            if not parts:
                continue
            tool_id = parts[0]
            label = parts[1] if len(parts) > 1 else tool_id
            target_table_id = parts[2] if len(parts) > 2 else None
            definition.tool_declarations.append(
                ToolDeclaration(tool_id=tool_id, label=label, target_table_id=target_table_id)
            )

    def _parse_setting_groups(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [SettingGroups] section into SettingGroupDefinition objects."""
        if not path.exists():
            return
        in_section = False
        current: SettingGroupDefinition | None = None
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_section = stripped.lower() == "[settinggroups]"
                if not in_section and current is not None:
                    definition.setting_groups.append(current)
                    current = None
                continue
            if not in_section:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value_parts = self._parse_csv(value)
            if key == "settingGroup":
                if current is not None:
                    definition.setting_groups.append(current)
                symbol = value_parts[0] if value_parts else ""
                label = value_parts[1] if len(value_parts) > 1 else symbol
                current = SettingGroupDefinition(
                    symbol=symbol,
                    label=self._strip_quotes(label),
                )
            elif key == "settingOption" and current is not None:
                symbol = value_parts[0] if value_parts else ""
                label = value_parts[1] if len(value_parts) > 1 else symbol
                current.options.append(
                    SettingGroupOption(symbol=symbol, label=self._strip_quotes(label))
                )
        if current is not None:
            definition.setting_groups.append(current)

    def _parse_reference_tables(self, path: Path, definition: EcuDefinition) -> None:
        if not path.exists():
            return
        in_user_defined = False
        current_table: ReferenceTableDefinition | None = None
        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith((";", "#")):
                continue
            if stripped.startswith("["):
                in_user_defined = stripped.lower() == "[userdefined]"
                if not in_user_defined:
                    current_table = None
                continue
            if not in_user_defined:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key == "referenceTable":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                current_table = ReferenceTableDefinition(
                    table_id=parts[0],
                    label=parts[1] if len(parts) > 1 else parts[0],
                )
                definition.reference_tables.append(current_table)
                continue
            if current_table is None:
                continue
            if key == "topicHelp":
                current_table.topic_help = self._strip_quotes(value)
            elif key == "tableIdentifier":
                parts = self._parse_csv(value)
                current_table.table_identifier = parts[1] if len(parts) > 1 else (parts[0] if parts else None)
            elif key == "solutionsLabel":
                current_table.solutions_label = self._strip_quotes(value)
            elif key == "solution":
                parts = self._parse_csv(value)
                if not parts:
                    continue
                current_table.solutions.append(
                    ReferenceTableSolution(
                        label=parts[0],
                        expression=parts[1] if len(parts) > 1 else None,
                    )
                )

    def _parse_curve_editors(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [CurveEditor] section into CurveDefinition domain objects."""
        if not path.exists():
            return
        in_section = False
        current: CurveDefinition | None = None
        # lineLabels may appear after all yBins — collect them, assign at flush.
        pending_line_labels: list[str] = []

        def _flush(curve: CurveDefinition) -> None:
            # Assign accumulated line labels to y_bins_list in order.
            for i, label in enumerate(pending_line_labels):
                if i < len(curve.y_bins_list):
                    curve.y_bins_list[i].label = label
            pending_line_labels.clear()
            definition.curve_definitions.append(curve)

        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                in_section = stripped.lower() == "[curveeditor]"
                if not in_section and current is not None:
                    _flush(current)
                    current = None
                continue
            if not in_section:
                continue
            # Strip inline comments
            stripped = stripped.split(";")[0].strip()
            if not stripped:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if key == "curve":
                if current is not None:
                    _flush(current)
                parts = self._parse_csv(value)
                if not parts:
                    continue
                current = CurveDefinition(
                    name=parts[0].strip(),
                    title=self._strip_quotes(parts[1]) if len(parts) > 1 else parts[0].strip(),
                    x_bins_param="",
                )
                continue
            if current is None:
                continue
            if key == "columnLabel":
                parts = self._parse_csv(value)
                if parts:
                    current.x_label = self._strip_quotes(parts[0])
                if len(parts) > 1:
                    current.y_label = self._strip_quotes(parts[1])
            elif key == "xAxis":
                parts = self._parse_csv(value)
                if len(parts) >= 3:
                    try:
                        current.x_axis = CurveAxisRange(
                            min=float(parts[0]),
                            max=float(parts[1]),
                            steps=int(float(parts[2])),
                        )
                    except (ValueError, IndexError):
                        pass
            elif key == "yAxis":
                parts = self._parse_csv(value)
                if len(parts) >= 3:
                    try:
                        current.y_axis = CurveAxisRange(
                            min=float(parts[0]),
                            max=float(parts[1]),
                            steps=int(float(parts[2])),
                        )
                    except (ValueError, IndexError):
                        pass
            elif key == "xBins":
                parts = self._parse_csv(value)
                if parts:
                    current.x_bins_param = parts[0].strip()
                    current.x_channel = parts[1].strip() if len(parts) > 1 else None
            elif key == "yBins":
                parts = self._parse_csv(value)
                if parts:
                    current.y_bins_list.append(CurveYBins(param=parts[0].strip()))
            elif key == "lineLabel":
                # Line labels may appear after all yBins; collect for flush-time assignment.
                pending_line_labels.append(self._strip_quotes(value))
            elif key == "topicHelp":
                current.topic_help = self._strip_quotes(value)
            elif key == "gauge":
                current.gauge = value.strip()
            elif key == "size":
                parts = self._parse_csv(value)
                if len(parts) >= 2:
                    try:
                        current.size = (int(float(parts[0])), int(float(parts[1])))
                    except (ValueError, IndexError):
                        pass
        # Flush last curve
        if current is not None:
            _flush(current)

    def _parse_gauge_configurations(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [GaugeConfigurations] section into GaugeConfiguration domain objects.

        Format::

            name = channel, "title", "units", lo, hi, loD, loW, hiW, hiD, vd, ld

        Threshold values that contain inline TunerStudio expressions (e.g. ``{rpmhigh}``)
        cannot be evaluated at parse time and are stored as ``None``.
        """
        if not path.exists():
            return
        in_section = False
        current_category: str | None = None

        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                in_section = stripped.lower() == "[gaugeconfigurations]"
                continue
            if not in_section:
                continue
            stripped = stripped.split(";")[0].strip()
            if not stripped:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()

            if key == "gaugeCategory":
                current_category = self._strip_quotes(value)
                continue

            parts = self._parse_csv(value)
            if len(parts) < 3:
                continue

            def _try_float(s: str) -> float | None:
                try:
                    return float(s)
                except (ValueError, TypeError):
                    return None

            channel = parts[0].strip()
            title = self._strip_quotes(parts[1]) if len(parts) > 1 else ""
            units = self._strip_quotes(parts[2]) if len(parts) > 2 else ""
            lo = _try_float(parts[3]) if len(parts) > 3 else None
            hi = _try_float(parts[4]) if len(parts) > 4 else None
            lo_danger = _try_float(parts[5]) if len(parts) > 5 else None
            lo_warn = _try_float(parts[6]) if len(parts) > 6 else None
            hi_warn = _try_float(parts[7]) if len(parts) > 7 else None
            hi_danger = _try_float(parts[8]) if len(parts) > 8 else None
            value_digits = int(_try_float(parts[9]) or 0) if len(parts) > 9 else 0
            label_digits = int(_try_float(parts[10]) or 0) if len(parts) > 10 else 0

            definition.gauge_configurations.append(GaugeConfiguration(
                name=key,
                channel=channel,
                title=title,
                units=units,
                lo=lo,
                hi=hi,
                lo_danger=lo_danger,
                lo_warn=lo_warn,
                hi_warn=hi_warn,
                hi_danger=hi_danger,
                value_digits=value_digits,
                label_digits=label_digits,
                category=current_category,
            ))

    def _parse_front_page(self, path: Path, definition: EcuDefinition) -> None:
        """Parse [FrontPage] gauge list and indicator expressions.

        Gauge slots (``gauge1``-``gauge8``) are stored as a list in order.
        Indicator lines are parsed into ``FrontPageIndicator`` objects.

        Indicator format::

            indicator = { expr }, "off-label", "on-label", off-bg, off-fg, on-bg, on-fg
        """
        if not path.exists():
            return
        in_section = False
        gauges: dict[int, str] = {}

        for raw_line in self._lines:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                in_section = stripped.lower() == "[frontpage]"
                continue
            if not in_section:
                continue
            stripped = stripped.split(";")[0].strip()
            if not stripped:
                continue
            key, sep, value = stripped.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()

            # gauge1 ... gauge8
            if re.match(r"^gauge\d+$", key, re.IGNORECASE):
                try:
                    idx = int(key[5:])
                    gauges[idx] = value.strip()
                except ValueError:
                    pass
                continue

            if key == "indicator":
                parts = self._parse_csv(value)
                if len(parts) < 7:
                    continue
                # First token is the expression, still wrapped in { }
                expr_raw = parts[0].strip()
                if expr_raw.startswith("{") and expr_raw.endswith("}"):
                    expr = expr_raw[1:-1].strip()
                else:
                    expr = expr_raw
                off_label = self._strip_quotes(parts[1])
                on_label = self._strip_quotes(parts[2])
                off_bg = parts[3].strip()
                off_fg = parts[4].strip()
                on_bg = parts[5].strip()
                on_fg = parts[6].strip()
                definition.front_page_indicators.append(FrontPageIndicator(
                    expression=expr,
                    off_label=off_label,
                    on_label=on_label,
                    off_bg=off_bg,
                    off_fg=off_fg,
                    on_bg=on_bg,
                    on_fg=on_fg,
                ))

        # Build ordered gauge list from gauge1..gaugeN
        if gauges:
            max_slot = max(gauges.keys())
            definition.front_page_gauges = [gauges.get(i, "") for i in range(1, max_slot + 1)]

    def _parse_logger_definitions(self, path: Path, definition: EcuDefinition) -> None:
        """Parse ``[LoggerDefinition]`` section into ``LoggerDefinition`` domain objects.

        Handles ``loggerDef = name, "Display", type`` headers followed by per-logger
        key=value lines (``startCommand``, ``stopCommand``, ``dataReadCommand``,
        ``dataReadTimeout``, ``continuousRead``, ``dataLength``, ``recordDef``) and
        ``recordField`` lines.  ``calcField`` lines are skipped — they are derived
        expressions for display, not raw binary fields.

        ``$tsCanId`` in ``dataReadCommand`` is substituted with ``\\x00\\x00``
        (direct connection, CAN bus not used).  ``\\xNN`` escapes are decoded to
        their byte values.
        """
        if not path.exists():
            return
        in_section = False
        # State for the logger block currently being built
        current_name: str | None = None
        current_display: str = ""
        current_kind: str = "tooth"
        props: dict[str, str] = {}
        fields: list[LoggerRecordField] = []

        def _decode_command(raw: str) -> bytes:
            """Decode a TunerStudio command string to bytes.

            Handles ``\\xNN`` hex escapes and ``$tsCanId`` (→ ``\\x00\\x00``).
            Surrounding quotes are stripped first.
            """
            s = raw.strip().strip('"')
            # \$tsCanId (with or without leading backslash) → \x00\x00 (direct connection)
            s = s.replace("\\$tsCanId", "\\x00\\x00")
            s = s.replace("$tsCanId", "\\x00\\x00")
            result = bytearray()
            i = 0
            while i < len(s):
                if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "x":
                    hex_str = s[i + 2 : i + 4]
                    try:
                        result.append(int(hex_str, 16))
                    except ValueError:
                        result.append(ord("\\"))
                        i += 1
                        continue
                    i += 4
                else:
                    result.append(ord(s[i]))
                    i += 1
            return bytes(result)

        def _flush() -> None:
            if current_name is None:
                return
            start_cmd_raw = props.get("startCommand", "")
            stop_cmd_raw = props.get("stopCommand", "")
            start_cmd = start_cmd_raw.strip().strip('"')
            stop_cmd = stop_cmd_raw.strip().strip('"')
            data_cmd_raw = props.get("dataReadCommand", "")
            data_cmd = _decode_command(data_cmd_raw)
            timeout_ms = 5000
            raw_timeout = props.get("dataReadTimeout", "")
            try:
                timeout_ms = int(float(raw_timeout.split(";")[0].strip()))
            except (ValueError, IndexError):
                pass
            continuous = props.get("continuousRead", "").strip().lower() == "true"
            # recordDef = headerLen, footerLen, recordLen
            rec_header = rec_footer = rec_len = 0
            raw_rec = props.get("recordDef", "")
            rec_parts = [p.split(";")[0].strip() for p in raw_rec.split(",")]
            if len(rec_parts) >= 3:
                try:
                    rec_header = int(rec_parts[0])
                    rec_footer = int(rec_parts[1])
                    rec_len = int(rec_parts[2])
                except ValueError:
                    pass
            # record_count: dataLength may be bytes (tooth) or record count (composite)
            raw_dl = props.get("dataLength", "")
            data_length_val = 0
            try:
                data_length_val = int(float(raw_dl.split(";")[0].strip()))
            except (ValueError, IndexError):
                pass
            if rec_len > 0 and data_length_val > 0:
                if current_kind == "tooth":
                    # dataLength is in bytes
                    record_count = data_length_val // rec_len
                else:
                    # dataLength is number of records
                    record_count = data_length_val
            else:
                record_count = 0
            definition.logger_definitions.append(LoggerDefinition(
                name=current_name,
                display_name=current_display,
                kind=current_kind,
                start_command=start_cmd,
                stop_command=stop_cmd,
                data_read_command=data_cmd,
                data_read_timeout_ms=timeout_ms,
                continuous_read=continuous,
                record_header_len=rec_header,
                record_footer_len=rec_footer,
                record_len=rec_len,
                record_count=record_count,
                record_fields=tuple(fields),
            ))

        with open(path, encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.readlines()
        lines = preprocess_ini_lines(raw_lines, active_settings=frozenset())

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                if in_section:
                    _flush()
                    current_name = None
                    props = {}
                    fields = []
                in_section = stripped.lower().startswith("[loggerdefinition]")
                continue
            if not in_section:
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.split(";")[0].strip()  # drop inline comments

            if key == "loggerDef":
                # flush the previous logger block
                _flush()
                current_name = None
                props = {}
                fields = []
                parts = self._parse_csv(value)
                if len(parts) < 3:
                    continue
                current_name = parts[0].strip()
                current_display = self._strip_quotes(parts[1])
                current_kind = parts[2].strip().lower()
            elif key == "recordField":
                # recordField = name, "Header", startBit, bitCount, scale, "units"
                parts = self._parse_csv(value)
                if len(parts) < 6:
                    continue
                try:
                    fields.append(LoggerRecordField(
                        name=parts[0].strip(),
                        header=self._strip_quotes(parts[1]),
                        start_bit=int(parts[2].strip()),
                        bit_count=int(parts[3].strip()),
                        scale=float(parts[4].strip()),
                        units=self._strip_quotes(parts[5]),
                    ))
                except (ValueError, IndexError):
                    pass
            elif key == "calcField":
                pass  # derived/display fields — skip
            else:
                props[key] = value

        _flush()  # flush final logger block

    def _parse_controller_commands(self, path: Path, definition: EcuDefinition) -> None:
        """Parse ``[ControllerCommands]`` into ``ControllerCommand`` domain objects.

        Each line has the form::

            cmdName = "E\\xSS\\xPP"

        The quoted string may contain ``\\xNN`` hex escapes.  The decoded bytes
        are stored verbatim — no additional framing is applied here.
        """
        if not path.exists():
            return

        def _decode_cmd(raw: str) -> bytes:
            s = raw.strip().strip('"')
            result = bytearray()
            i = 0
            while i < len(s):
                if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "x":
                    hex_str = s[i + 2 : i + 4]
                    try:
                        result.append(int(hex_str, 16))
                    except ValueError:
                        result.append(ord("\\"))
                        i += 1
                        continue
                    i += 4
                else:
                    result.append(ord(s[i]))
                    i += 1
            return bytes(result)

        in_section = False
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw_lines = fh.readlines()
        lines = preprocess_ini_lines(raw_lines, active_settings=frozenset())

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            if stripped.startswith("["):
                in_section = stripped.lower().startswith("[controllercommands]")
                continue
            if not in_section:
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.split(";")[0].strip()
            if not value:
                continue
            # Commands may be a comma-separated sequence; decode each part
            # and concatenate (in practice all production commands are single entries)
            parts = self._parse_csv(value)
            payload = b"".join(_decode_cmd(p) for p in parts if p.strip())
            if payload:
                definition.controller_commands.append(ControllerCommand(
                    name=key,
                    payload=payload,
                ))

    def _apply_definition_metadata(self, definition: EcuDefinition) -> None:
        for scalar in definition.scalars:
            scalar.help_text = definition.setting_help.get(scalar.name)
            scalar.requires_power_cycle = scalar.name in definition.requires_power_cycle
        for table in definition.tables:
            table.help_text = definition.setting_help.get(table.name)

    @staticmethod
    def _parse_units(remainder: str) -> str | None:
        unit_match = re.search(r'"([^"]*)"', remainder)
        return unit_match.group(1) if unit_match else None

    @classmethod
    def _first_command(cls, raw_value: str | None) -> str | None:
        if not raw_value:
            return None
        parts = cls._parse_csv(raw_value)
        return parts[0] if parts else None

    @staticmethod
    def _parse_value_token(token: str | None) -> str | None:
        if token is None:
            return None
        stripped = token.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        return stripped or None

    @staticmethod
    def _parse_float_token(token: str | None) -> float | None:
        if token is None:
            return None
        stripped = token.strip()
        if not stripped or stripped.startswith("{"):
            return None
        try:
            return float(stripped)
        except ValueError:
            return None

    @staticmethod
    def _parse_int_token(token: str | None) -> int | None:
        if token is None:
            return None
        stripped = token.strip()
        if not stripped or stripped.startswith("{"):
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None

    @staticmethod
    def _parse_shape(shape: str) -> tuple[int, int]:
        cleaned = shape.strip()[1:-1]
        if "x" in cleaned:
            rows, cols = cleaned.split("x", 1)
            return int(rows.strip(), 0), int(cols.strip(), 0)
        count = int(cleaned.strip(), 0)
        return count, 1

    @staticmethod
    def _parse_bit_shape(shape: str | None) -> tuple[int | None, int | None]:
        if not shape:
            return None, None
        cleaned = shape.strip()[1:-1]
        if ":" not in cleaned:
            try:
                bit = int(cleaned, 0)
            except ValueError:
                return None, None
            return bit, 1
        start_text, end_text = cleaned.split(":", 1)
        try:
            start = int(start_text.strip(), 0)
            end = int(end_text.strip(), 0)
        except ValueError:
            return None, None
        if end < start:
            start, end = end, start
        return start, (end - start) + 1

    def _collect_defines(self, path: Path) -> dict[str, list[str]]:
        """Collect all ``#define name = value`` macros from the INI file.

        Returns a mapping of macro name → list of un-quoted string tokens.
        Only list-style defines (comma-separated option strings) are kept;
        single-value defines that don't look like option lists are included
        as a one-element list so expansion is always consistent.

        Example::

            #define pinLayouts = "INVALID","Speeduino v0.2","Drop Bear"
            → {"pinLayouts": ["INVALID", "Speeduino v0.2", "Drop Bear"]}
        """
        defines: dict[str, list[str]] = {}
        if not path.exists():
            return defines
        lines = self._lines if self._lines else preprocess_ini_lines(
            path.read_text(encoding="utf-8", errors="ignore").splitlines()
        )
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped.startswith("#define"):
                continue
            rest = stripped[len("#define"):].strip()
            if "=" not in rest:
                continue
            name, _, value = rest.partition("=")
            name = name.strip()
            if not name:
                continue
            tokens = self._parse_csv(value.strip())
            if tokens:
                defines[name] = tokens
        return defines

    @staticmethod
    def _expand_options(
        parts: list[str],
        defines: dict[str, list[str]],
        depth: int = 0,
    ) -> list[str]:
        """Expand ``$macroName`` tokens in an options list.

        Resolves each ``$name`` reference by looking it up in ``defines`` and
        recursively expanding the result.  Tokens that start with ``{`` (inline
        visibility expressions that leaked into the options list) are dropped.
        Recursion is limited to 10 levels to guard against circular defines.

        Returns a flat list of plain option strings with no ``$`` or ``{``
        prefixes.
        """
        if depth > 10:
            return []
        result: list[str] = []
        for part in parts:
            if not part:
                continue
            if part.startswith("{"):
                # Inline condition expression — not an option label; skip.
                continue
            if part.startswith("$"):
                macro_name = part[1:]
                expanded = defines.get(macro_name)
                if expanded is not None:
                    result.extend(
                        IniParser._expand_options(expanded, defines, depth + 1)
                    )
                # If macro not found, drop the token silently rather than
                # surfacing a raw "$undefined" label to the user.
            else:
                result.append(part)
        return result

    @staticmethod
    def _parse_csv(value: str) -> list[str]:
        tokens: list[str] = []
        current: list[str] = []
        in_quotes = False
        brace_depth = 0
        paren_depth = 0
        for char in value:
            if char == '"':
                in_quotes = not in_quotes
                current.append(char)
                continue
            if not in_quotes:
                if char == "{":
                    brace_depth += 1
                elif char == "}":
                    brace_depth = max(0, brace_depth - 1)
                elif char == "(":
                    paren_depth += 1
                elif char == ")":
                    paren_depth = max(0, paren_depth - 1)
                elif char == "," and brace_depth == 0 and paren_depth == 0:
                    token = "".join(current).strip()
                    if token:
                        tokens.append(token.strip('"'))
                    current = []
                    continue
            current.append(char)
        token = "".join(current).strip()
        if token:
            tokens.append(token.strip('"'))
        return tokens
