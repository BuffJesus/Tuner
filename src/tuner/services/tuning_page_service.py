from __future__ import annotations

from collections import defaultdict
import re

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition, TableDefinition, TableEditorDefinition
from tuner.domain.tuning_pages import (
    TuningPage,
    TuningPageGroup,
    TuningPageKind,
    TuningPageParameter,
    TuningPageParameterRole,
    TuningPageSection,
)
from tuner.services.definition_layout_service import CompiledLayoutPage, CompiledLayoutSection, DefinitionLayoutService


class TuningPageService:
    _GROUP_RULES: tuple[tuple[int, str, str, tuple[str, ...]], ...] = (
        (5,  "hardware_setup", "Hardware Setup", ("injector", "coil", "trigger", "decoder", "thermistor")),
        (10, "fuel", "Fuel", ("ve", "fuel", "inject", "reqfuel")),
        (20, "ignition", "Ignition", ("spark", "ignition", "advance", "timing", "dwell", "knock")),
        (30, "afr", "AFR / Lambda", ("afr", "lambda", "ego", "o2")),
        (40, "idle", "Idle", ("idle", "iac")),
        (50, "enrich", "Startup / Enrich", ("enrich", "warmup", "crank", "afterstart", "prime", "accel", "ase", "wue")),
        (60, "boost", "Boost / Airflow", ("boost", "map", "baro", "vvt", "turbo")),
        (70, "settings", "Settings", ("setting", "config", "option", "sensor", "calibration", "general", "engine", "limit")),
        (99, "other", "Other", ()),
    )

    def __init__(self, definition_layout_service: DefinitionLayoutService | None = None) -> None:
        self.definition_layout_service = definition_layout_service or DefinitionLayoutService()

    def build_pages(self, definition: EcuDefinition | None) -> list[TuningPageGroup]:
        if definition is None:
            return []

        scalars_by_name = {scalar.name: scalar for scalar in definition.scalars}
        tables_by_name = {table.name: table for table in definition.tables}
        table_editors_by_id = {editor.table_id: editor for editor in definition.table_editors}
        covered_names: set[str] = set()
        covered_page_ids: set[str] = set()
        grouped_pages: dict[tuple[int, str, str], list[TuningPage]] = defaultdict(list)

        for layout in self.definition_layout_service.compile_pages(definition):
            page = self._build_layout_page(layout, scalars_by_name, tables_by_name, table_editors_by_id)
            if page is None:
                continue
            group_order = self._group_order(page.group_id)
            if group_order == 99:
                # INI menu title not in known rules — classify by page title keywords
                kw_order, kw_group_id, kw_group_title = self._group_for_text(page.title, page.group_title)
                group_order, group_id, group_title = kw_order, kw_group_id, kw_group_title
            else:
                group_id, group_title = page.group_id, page.group_title
            grouped_pages[(group_order, group_id, group_title)].append(page)
            covered_names.update(page.parameter_names)
            covered_page_ids.add(page.page_id)

        for editor in definition.table_editors:
            page_id = f"table-editor:{editor.table_id}"
            if page_id in covered_page_ids:
                continue
            group_order, group_id, group_title = self._group_for_text(editor.title, editor.z_bins, editor.map_id)
            page = self._build_table_editor_page(editor, scalars_by_name, tables_by_name, group_id, group_title)
            grouped_pages[(group_order, group_id, group_title)].append(page)
            covered_names.update(page.parameter_names)

        fallback_groups = self._build_fallback_pages(definition, covered_names)
        for group_order, group in fallback_groups:
            grouped_pages[(group_order, group.group_id, group.title)].extend(group.pages)

        result: list[TuningPageGroup] = []
        for (_, group_id, group_title), pages in sorted(grouped_pages.items(), key=lambda item: item[0]):
            ordered_pages = sorted(
                pages,
                key=lambda page: (
                    page.page_number if page.page_number is not None else 9999,
                    page.title.lower(),
                    page.page_id,
                ),
            )
            result.append(TuningPageGroup(group_id=group_id, title=group_title, pages=tuple(ordered_pages)))
        return result

    def _build_layout_page(
        self,
        layout: CompiledLayoutPage,
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
        table_editors_by_id: dict[str, TableEditorDefinition],
    ) -> TuningPage | None:
        editor = table_editors_by_id.get(layout.table_editor_id) if layout.table_editor_id else None
        if editor is not None:
            return self._build_dialog_backed_table_page(layout, editor, scalars_by_name, tables_by_name)

        parameters: list[TuningPageParameter] = []
        sections = self._sections_from_layout(layout.sections, scalars_by_name, tables_by_name, parameters)
        if not parameters:
            return None
        return TuningPage(
            page_id=f"dialog:{layout.target}",
            title=layout.title,
            group_id=layout.group_id,
            group_title=layout.group_title,
            page_number=layout.page_number,
            kind=TuningPageKind.PARAMETER_LIST,
            source="definition-layout",
            parameter_names=tuple(parameter.name for parameter in parameters),
            parameters=tuple(parameters),
            sections=sections,
            summary=self._parameter_page_summary(layout.title, parameters, sections),
            visibility_expression=layout.visibility_expression,
        )

    def _build_dialog_backed_table_page(
        self,
        layout: CompiledLayoutPage,
        editor: TableEditorDefinition,
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
    ) -> TuningPage:
        parameters: list[TuningPageParameter] = []
        z_parameter = self._parameter_for_name(editor.z_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.TABLE)
        x_parameter = self._parameter_for_name(editor.x_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.X_AXIS)
        y_parameter = self._parameter_for_name(editor.y_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.Y_AXIS)
        for parameter in [z_parameter, x_parameter, y_parameter]:
            if parameter is not None and parameter.name not in {item.name for item in parameters}:
                parameters.append(parameter)

        sections = list(
            self._sections_from_layout(
                layout.sections,
                scalars_by_name,
                tables_by_name,
                parameters,
                scalar_role=TuningPageParameterRole.AUXILIARY_SCALAR,
            )
        )
        sections.insert(
            0,
            TuningPageSection(
                title=layout.title,
                parameter_names=tuple(
                    parameter.name
                    for parameter in parameters
                    if parameter.role in {TuningPageParameterRole.TABLE, TuningPageParameterRole.X_AXIS, TuningPageParameterRole.Y_AXIS}
                ),
            ),
        )

        return TuningPage(
            page_id=f"table-editor:{editor.table_id}",
            title=layout.title or editor.title,
            group_id=layout.group_id,
            group_title=layout.group_title,
            page_number=layout.page_number or editor.page,
            kind=TuningPageKind.TABLE if z_parameter is not None and z_parameter.kind == "table" else TuningPageKind.PARAMETER_LIST,
            source="definition-layout",
            parameter_names=tuple(parameter.name for parameter in parameters),
            parameters=tuple(parameters),
            sections=tuple(sections),
            summary=self._table_page_summary(layout.title or editor.title, editor, sections),
            help_topic=editor.topic_help,
            table_id=editor.table_id,
            map_id=editor.map_id,
            table_name=editor.z_bins,
            x_axis_name=editor.x_bins,
            y_axis_name=editor.y_bins,
            x_axis_label=editor.x_label,
            y_axis_label=editor.y_label,
            visibility_expression=layout.visibility_expression,
        )

    def _build_table_editor_page(
        self,
        editor: TableEditorDefinition,
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
        group_id: str,
        group_title: str,
    ) -> TuningPage:
        parameters: list[TuningPageParameter] = []
        z_parameter = self._parameter_for_name(editor.z_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.TABLE)
        x_parameter = self._parameter_for_name(editor.x_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.X_AXIS)
        y_parameter = self._parameter_for_name(editor.y_bins, scalars_by_name, tables_by_name, TuningPageParameterRole.Y_AXIS)

        for parameter in [z_parameter, x_parameter, y_parameter]:
            if parameter is not None and parameter.name not in {item.name for item in parameters}:
                parameters.append(parameter)

        summary_parts = [editor.title]
        if editor.x_label or editor.x_bins:
            summary_parts.append(f"X axis: {editor.x_label or editor.x_bins}")
        if editor.y_label or editor.y_bins:
            summary_parts.append(f"Y axis: {editor.y_label or editor.y_bins}")
        if z_parameter is None:
            summary_parts.append("raw fallback")

        parameter_names = tuple(name for name in [editor.z_bins, editor.x_bins, editor.y_bins] if name)
        return TuningPage(
            page_id=f"table-editor:{editor.table_id}",
            title=editor.title,
            group_id=group_id,
            group_title=group_title,
            page_number=editor.page,
            kind=TuningPageKind.TABLE if z_parameter is not None and z_parameter.kind == "table" else TuningPageKind.PARAMETER_LIST,
            source="table-editor",
            parameter_names=parameter_names,
            parameters=tuple(parameters),
            sections=(
                TuningPageSection(
                    title="Table",
                    parameter_names=parameter_names,
                ),
            ),
            summary=" | ".join(summary_parts),
            help_topic=editor.topic_help,
            table_id=editor.table_id,
            map_id=editor.map_id,
            table_name=editor.z_bins,
            x_axis_name=editor.x_bins,
            y_axis_name=editor.y_bins,
            x_axis_label=editor.x_label,
            y_axis_label=editor.y_label,
            visibility_expression=None,
        )

    def _build_fallback_pages(
        self,
        definition: EcuDefinition,
        covered_names: set[str],
    ) -> list[tuple[int, TuningPageGroup]]:
        parameters_by_page: dict[int | None, list[TuningPageParameter]] = defaultdict(list)

        for scalar in definition.scalars:
            if scalar.name in covered_names:
                continue
            parameters_by_page[scalar.page].append(self._scalar_parameter(scalar))

        for table in definition.tables:
            if table.name in covered_names:
                continue
            parameters_by_page[table.page].append(self._table_parameter(table, TuningPageParameterRole.AUXILIARY_TABLE))

        fallback_pages: list[tuple[int, TuningPageGroup]] = []
        for page_number, parameters in sorted(parameters_by_page.items(), key=lambda item: item[0] if item[0] is not None else 9999):
            if page_number is None:
                # Unpaged definition artifacts stay available in the parameter catalog,
                # but they should not appear as first-class tuning pages.
                continue
            ordered_parameters = sorted(
                parameters,
                key=lambda parameter: (
                    parameter.offset if parameter.offset is not None else 999999,
                    parameter.name.lower(),
                ),
            )
            title = self._fallback_page_title(definition, page_number, ordered_parameters)
            group_order, group_id, group_title = 70, "settings", "Settings"
            page = TuningPage(
                page_id=f"fallback:{page_number if page_number is not None else 'unpaged'}",
                title=title,
                group_id=group_id,
                group_title=group_title,
                page_number=page_number,
                kind=TuningPageKind.PARAMETER_LIST,
                source="definition-fallback",
                parameter_names=tuple(parameter.name for parameter in ordered_parameters),
                parameters=tuple(ordered_parameters),
                sections=(TuningPageSection(title=title, parameter_names=tuple(parameter.name for parameter in ordered_parameters)),),
                summary=self._fallback_summary(page_number, ordered_parameters),
                visibility_expression=None,
            )
            fallback_pages.append((group_order, TuningPageGroup(group_id=group_id, title=group_title, pages=(page,))))
        return fallback_pages

    def _sections_from_layout(
        self,
        compiled_sections: tuple[CompiledLayoutSection, ...],
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
        parameters: list[TuningPageParameter],
        scalar_role: TuningPageParameterRole = TuningPageParameterRole.SCALAR,
    ) -> tuple[TuningPageSection, ...]:
        sections: list[TuningPageSection] = []
        for section in compiled_sections:
            names: list[str] = []
            for field in section.fields:
                parameter = self._parameter_for_name(field.parameter_name, scalars_by_name, tables_by_name, scalar_role)
                if parameter is None:
                    continue
                parameter = self._with_field_label(parameter, field.label, field.visibility_expression)
                existing_index = next((index for index, item in enumerate(parameters) if item.name == parameter.name), None)
                if existing_index is None:
                    parameters.append(parameter)
                else:
                    parameters[existing_index] = parameter
                names.append(parameter.name)
            if names or section.notes:
                sections.append(
                    TuningPageSection(
                        title=section.title,
                        parameter_names=tuple(names),
                        notes=section.notes,
                        visibility_expression=section.visibility_expression,
                    )
                )
        return tuple(sections)

    def _fallback_page_title(
        self,
        definition: EcuDefinition,
        page_number: int | None,
        parameters: list[TuningPageParameter],
    ) -> str:
        if page_number is None:
            return "Loose Parameters"

        explicit_menu_titles = self._explicit_page_menu_titles(definition, page_number)
        if explicit_menu_titles:
            return self._merge_fallback_titles(explicit_menu_titles)

        inferred_titles = self._inferred_page_titles(definition, page_number, parameters)
        if inferred_titles:
            return self._merge_fallback_titles(inferred_titles)

        if page_number in definition.page_titles:
            return definition.page_titles[page_number]

        return f"Page {page_number} Settings"

    def _explicit_page_menu_titles(self, definition: EcuDefinition, page_number: int) -> list[str]:
        titles: list[str] = []
        seen: set[str] = set()
        for menu in definition.menus:
            for item in menu.items:
                if item.page != page_number or not item.label:
                    continue
                label = item.label.strip()
                if not label or label in seen:
                    continue
                seen.add(label)
                titles.append(label)
        return titles

    def _inferred_page_titles(
        self,
        definition: EcuDefinition,
        page_number: int,
        parameters: list[TuningPageParameter],
    ) -> list[str]:
        parameter_names = {parameter.name for parameter in parameters}
        if not parameter_names:
            return []

        target_parameters = self._menu_target_parameters(definition)
        scored_titles: list[tuple[int, float, str]] = []
        for menu in definition.menus:
            for item in menu.items:
                if not item.label:
                    continue
                target_names = target_parameters.get(item.target, frozenset())
                if not target_names:
                    continue
                overlap = len(parameter_names & target_names)
                if overlap == 0:
                    continue
                overlap_ratio = overlap / max(1, len(target_names))
                scored_titles.append((overlap, overlap_ratio, item.label.strip()))

        if not scored_titles:
            return []

        scored_titles.sort(key=lambda item: (-item[0], -item[1], item[2]))
        best_overlap = scored_titles[0][0]
        threshold = max(1, min(3, best_overlap))
        titles: list[str] = []
        seen: set[str] = set()
        for overlap, _, title in scored_titles:
            if overlap < threshold:
                break
            if title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) == 2:
                break
        return titles

    def _menu_target_parameters(self, definition: EcuDefinition) -> dict[str, frozenset[str]]:
        dialogs_by_id = {dialog.dialog_id: dialog for dialog in definition.dialogs}
        table_editors_by_id = {editor.table_id: editor for editor in definition.table_editors}
        cache: dict[str, frozenset[str]] = {}

        def resolve(target: str, active_stack: frozenset[str] = frozenset()) -> frozenset[str]:
            cached = cache.get(target)
            if cached is not None:
                return cached
            if target in active_stack:
                return frozenset()

            editor = table_editors_by_id.get(target)
            if editor is not None:
                names = frozenset(name for name in (editor.z_bins, editor.x_bins, editor.y_bins) if name)
                cache[target] = names
                return names

            dialog = dialogs_by_id.get(target)
            if dialog is None:
                cache[target] = frozenset()
                return cache[target]

            names = {
                field.parameter_name
                for field in dialog.fields
                if field.parameter_name
            }
            next_stack = set(active_stack)
            next_stack.add(target)
            for panel in dialog.panels:
                names.update(resolve(panel.target, frozenset(next_stack)))
            cache[target] = frozenset(names)
            return cache[target]

        for menu in definition.menus:
            for item in menu.items:
                resolve(item.target)
        return cache

    @classmethod
    def _merge_fallback_titles(cls, titles: list[str]) -> str:
        normalized = [title.strip() for title in titles if title and title.strip()]
        deduped: list[str] = []
        seen: set[str] = set()
        for title in normalized:
            lower = title.lower()
            if lower in seen:
                continue
            seen.add(lower)
            deduped.append(title)
        if not deduped:
            return "Settings"
        if len(deduped) == 1:
            return deduped[0]

        tokenized = [cls._title_tokens(title) for title in deduped]
        common_prefix = cls._common_prefix(tokenized)
        if common_prefix:
            prefix = " ".join(common_prefix)
            if prefix.lower() not in {"table", "settings"}:
                return f"{prefix} Settings"

        common_suffix = cls._common_suffix(tokenized)
        if common_suffix and len(common_suffix) < len(tokenized[0]):
            suffix_text = " ".join(common_suffix)
            prefixes = []
            for tokens in tokenized:
                prefix_tokens = tokens[: len(tokens) - len(common_suffix)]
                if prefix_tokens:
                    prefixes.append(" ".join(prefix_tokens))
            if prefixes:
                suffix_text = cls._pluralize_suffix(suffix_text, len(prefixes))
                return f"{' / '.join(prefixes[:2])} {suffix_text}"

        return f"{deduped[0]} / {deduped[1]} Settings"

    @staticmethod
    def _title_tokens(title: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9/]+", title)

    @staticmethod
    def _common_prefix(token_lists: list[list[str]]) -> list[str]:
        if not token_lists:
            return []
        prefix: list[str] = []
        for parts in zip(*token_lists):
            if len(set(parts)) != 1:
                break
            prefix.append(parts[0])
        return prefix

    @staticmethod
    def _common_suffix(token_lists: list[list[str]]) -> list[str]:
        if not token_lists:
            return []
        reversed_lists = [list(reversed(tokens)) for tokens in token_lists]
        suffix_reversed: list[str] = []
        for parts in zip(*reversed_lists):
            if len(set(parts)) != 1:
                break
            suffix_reversed.append(parts[0])
        return list(reversed(suffix_reversed))

    @staticmethod
    def _pluralize_suffix(suffix: str, count: int) -> str:
        if count <= 1:
            return suffix
        if suffix.endswith(" Table"):
            return f"{suffix}s"
        return suffix

    @classmethod
    def _group_for_text(cls, *parts: str | None) -> tuple[int, str, str]:
        haystack = " ".join(part.lower() for part in parts if part).strip()
        for order, group_id, group_title, keywords in cls._GROUP_RULES:
            if not keywords:
                continue
            if any(keyword in haystack for keyword in keywords):
                return order, group_id, group_title
        return 99, "other", "Other"

    @classmethod
    def _group_order(cls, group_id: str) -> int:
        for order, existing_group_id, _, _ in cls._GROUP_RULES:
            if existing_group_id == group_id:
                return order
        return 99

    @staticmethod
    def _fallback_summary(page_number: int | None, parameters: list[TuningPageParameter]) -> str:
        scalar_count = sum(1 for parameter in parameters if parameter.kind == "scalar")
        table_count = sum(1 for parameter in parameters if parameter.kind == "table")
        location = f"page {page_number}" if page_number is not None else "unpaged definition data"
        return f"{len(parameters)} definition parameters from {location} ({scalar_count} scalars, {table_count} raw tables)."

    @staticmethod
    def _parameter_page_summary(
        title: str,
        parameters: list[TuningPageParameter],
        sections: tuple[TuningPageSection, ...],
    ) -> str:
        return f"{title} | {len(parameters)} parameters across {len(sections) or 1} sections."

    @staticmethod
    def _table_page_summary(
        title: str,
        editor: TableEditorDefinition,
        sections: list[TuningPageSection],
    ) -> str:
        summary_parts = [title]
        if editor.x_label or editor.x_bins:
            summary_parts.append(f"X axis: {editor.x_label or editor.x_bins}")
        if editor.y_label or editor.y_bins:
            summary_parts.append(f"Y axis: {editor.y_label or editor.y_bins}")
        auxiliary_sections = max(0, len(sections) - 1)
        if auxiliary_sections:
            summary_parts.append(f"{auxiliary_sections} supporting section{'s' if auxiliary_sections != 1 else ''}")
        return " | ".join(summary_parts)

    def _parameter_for_name(
        self,
        name: str | None,
        scalars_by_name: dict[str, ScalarParameterDefinition],
        tables_by_name: dict[str, TableDefinition],
        role: TuningPageParameterRole,
    ) -> TuningPageParameter | None:
        if not name:
            return None
        scalar = scalars_by_name.get(name)
        if scalar is not None:
            scalar_role = role if role != TuningPageParameterRole.TABLE else TuningPageParameterRole.SCALAR
            return self._scalar_parameter(scalar, role=scalar_role)
        table = tables_by_name.get(name)
        if table is not None:
            return self._table_parameter(table, role=role)
        return None

    @staticmethod
    def _with_field_label(
        parameter: TuningPageParameter,
        label: str,
        visibility_expression: str | None,
    ) -> TuningPageParameter:
        return TuningPageParameter(
            name=parameter.name,
            label=label or parameter.label,
            kind=parameter.kind,
            role=parameter.role,
            page=parameter.page,
            offset=parameter.offset,
            units=parameter.units,
            data_type=parameter.data_type,
            shape=parameter.shape,
            help_text=parameter.help_text,
            min_value=parameter.min_value,
            max_value=parameter.max_value,
            digits=parameter.digits,
            options=parameter.options,
            option_values=parameter.option_values,
            visibility_expression=visibility_expression or parameter.visibility_expression,
            requires_power_cycle=parameter.requires_power_cycle,
        )

    @staticmethod
    def _scalar_parameter(
        scalar: ScalarParameterDefinition,
        role: TuningPageParameterRole = TuningPageParameterRole.SCALAR,
    ) -> TuningPageParameter:
        return TuningPageParameter(
            name=scalar.name,
            label=scalar.label or scalar.name,
            kind="scalar",
            role=role,
            page=scalar.page,
            offset=scalar.offset,
            units=scalar.units,
            data_type=scalar.data_type,
            shape="1x1",
            help_text=scalar.help_text,
            min_value=scalar.min_value,
            max_value=scalar.max_value,
            digits=scalar.digits,
            options=tuple(option.label for option in scalar.options),
            option_values=tuple(option.value for option in scalar.options),
            visibility_expression=scalar.visibility_expression,
            requires_power_cycle=scalar.requires_power_cycle,
        )

    @staticmethod
    def _table_parameter(table: TableDefinition, role: TuningPageParameterRole) -> TuningPageParameter:
        return TuningPageParameter(
            name=table.name,
            label=table.label or table.name,
            kind="table",
            role=role,
            page=table.page,
            offset=table.offset,
            units=table.units,
            data_type=table.data_type,
            shape=f"{table.rows}x{table.columns}",
            help_text=table.help_text,
            min_value=table.min_value,
            max_value=table.max_value,
            digits=table.digits,
        )
