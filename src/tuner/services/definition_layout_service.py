from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.ecu_definition import DialogDefinition, EcuDefinition, MenuDefinition, TableEditorDefinition


@dataclass(slots=True, frozen=True)
class CompiledLayoutField:
    label: str
    parameter_name: str | None
    visibility_expression: str | None = None
    is_static_text: bool = False


@dataclass(slots=True, frozen=True)
class CompiledLayoutSection:
    title: str
    fields: tuple[CompiledLayoutField, ...]
    notes: tuple[str, ...] = ()
    visibility_expression: str | None = None


@dataclass(slots=True, frozen=True)
class CompiledLayoutPage:
    target: str
    title: str
    group_id: str
    group_title: str
    page_number: int | None
    visibility_expression: str | None
    table_editor_id: str | None
    sections: tuple[CompiledLayoutSection, ...]


class DefinitionLayoutService:
    def compile_pages(self, definition: EcuDefinition | None) -> list[CompiledLayoutPage]:
        if definition is None:
            return []
        dialogs_by_id = {dialog.dialog_id: dialog for dialog in definition.dialogs}
        table_editors_by_id = {editor.table_id: editor for editor in definition.table_editors}
        pages: list[CompiledLayoutPage] = []
        seen_targets: set[str] = set()
        for menu in definition.menus:
            group_title = menu.title.replace("&", "").strip() or "Other"
            group_id = self._normalize_group_id(group_title)
            for item in menu.items:
                if item.target in seen_targets:
                    continue
                layout = self._compile_menu_item(
                    item.target,
                    item.label or item.target,
                    item.page,
                    item.visibility_expression,
                    group_id,
                    group_title,
                    dialogs_by_id,
                    table_editors_by_id,
                )
                if layout is None:
                    continue
                pages.append(layout)
                seen_targets.add(item.target)
        return pages

    def _compile_menu_item(
        self,
        target: str,
        title: str,
        page_number: int | None,
        visibility_expression: str | None,
        group_id: str,
        group_title: str,
        dialogs_by_id: dict[str, DialogDefinition],
        table_editors_by_id: dict[str, TableEditorDefinition],
    ) -> CompiledLayoutPage | None:
        if target in table_editors_by_id:
            return CompiledLayoutPage(
                target=target,
                title=title,
                group_id=group_id,
                group_title=group_title,
                page_number=page_number,
                visibility_expression=visibility_expression,
                table_editor_id=target,
                sections=(),
            )
        dialog = dialogs_by_id.get(target)
        if dialog is None:
            return None
        table_editor_id, sections = self._compile_dialog(dialog, dialogs_by_id, table_editors_by_id, set())
        if not sections and table_editor_id is None:
            return None
        return CompiledLayoutPage(
            target=target,
            title=title or dialog.title or dialog.dialog_id,
            group_id=group_id,
            group_title=group_title,
            page_number=page_number,
            visibility_expression=visibility_expression,
            table_editor_id=table_editor_id,
            sections=tuple(sections),
        )

    def _compile_dialog(
        self,
        dialog: DialogDefinition,
        dialogs_by_id: dict[str, DialogDefinition],
        table_editors_by_id: dict[str, TableEditorDefinition],
        active_stack: set[str],
    ) -> tuple[str | None, list[CompiledLayoutSection]]:
        if dialog.dialog_id in active_stack:
            return None, []
        active_stack = set(active_stack)
        active_stack.add(dialog.dialog_id)

        notes = tuple(field.label for field in dialog.fields if field.is_static_text and field.label)
        fields = tuple(
            CompiledLayoutField(
                label=field.label,
                parameter_name=field.parameter_name,
                visibility_expression=field.visibility_expression,
                is_static_text=field.is_static_text,
            )
            for field in dialog.fields
            if field.parameter_name
        )
        sections: list[CompiledLayoutSection] = []
        if fields or notes:
            sections.append(
                CompiledLayoutSection(
                    title=dialog.title or dialog.dialog_id,
                    fields=fields,
                    notes=notes,
                )
            )

        table_editor_id: str | None = None
        for panel in dialog.panels:
            if panel.target in table_editors_by_id and table_editor_id is None:
                table_editor_id = panel.target
                continue
            nested = dialogs_by_id.get(panel.target)
            if nested is None:
                continue
            nested_table_editor_id, nested_sections = self._compile_dialog(
                nested,
                dialogs_by_id,
                table_editors_by_id,
                active_stack,
            )
            if table_editor_id is None and nested_table_editor_id is not None:
                table_editor_id = nested_table_editor_id
            for section in nested_sections:
                sections.append(
                    CompiledLayoutSection(
                        title=section.title,
                        fields=section.fields,
                        notes=section.notes,
                        visibility_expression=panel.visibility_expression or section.visibility_expression,
                    )
                )
        return table_editor_id, sections

    @staticmethod
    def _normalize_group_id(title: str) -> str:
        return "".join(character.lower() if character.isalnum() else "-" for character in title).strip("-") or "other"
