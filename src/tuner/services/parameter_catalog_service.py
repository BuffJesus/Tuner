from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition, TableDefinition
from tuner.domain.tune import TuneFile, TuneValue


@dataclass(slots=True)
class ParameterCatalogEntry:
    name: str
    kind: str
    page: int | None
    offset: int | None
    units: str | None
    data_type: str
    shape: str
    tune_present: bool
    tune_preview: str


class ParameterCatalogService:
    def build_catalog(
        self,
        definition: EcuDefinition | None,
        tune_file: TuneFile | None,
        staged_values: dict[str, TuneValue] | None = None,
    ) -> list[ParameterCatalogEntry]:
        tune_index = self._tune_index(tune_file)
        if staged_values:
            tune_index.update(staged_values)
        entries: list[ParameterCatalogEntry] = []
        if definition is not None:
            for scalar in definition.scalars:
                tune_value = tune_index.get(scalar.name)
                entries.append(self._scalar_entry(scalar, tune_value))
            for table in definition.tables:
                tune_value = tune_index.get(table.name)
                entries.append(self._table_entry(table, tune_value))
        for tune_value in tune_index.values():
            if any(entry.name == tune_value.name for entry in entries):
                continue
            entries.append(self._tune_only_entry(tune_value))
        entries.sort(key=lambda entry: (entry.page if entry.page is not None else 9999, entry.offset if entry.offset is not None else 999999, entry.name.lower()))
        return entries

    @staticmethod
    def filter_catalog(entries: list[ParameterCatalogEntry], query: str) -> list[ParameterCatalogEntry]:
        normalized = query.strip().lower()
        if not normalized:
            return entries
        return [
            entry
            for entry in entries
            if normalized in entry.name.lower()
            or normalized in entry.kind.lower()
            or normalized in (entry.units or "").lower()
            or normalized in entry.data_type.lower()
        ]

    @staticmethod
    def _tune_index(tune_file: TuneFile | None) -> dict[str, TuneValue]:
        if tune_file is None:
            return {}
        values = {item.name: item for item in tune_file.constants}
        values.update({item.name: item for item in tune_file.pc_variables})
        return values

    def _scalar_entry(self, scalar: ScalarParameterDefinition, tune_value: TuneValue | None) -> ParameterCatalogEntry:
        return ParameterCatalogEntry(
            name=scalar.name,
            kind="scalar",
            page=scalar.page,
            offset=scalar.offset,
            units=scalar.units,
            data_type=scalar.data_type,
            shape="1x1",
            tune_present=tune_value is not None,
            tune_preview=self._preview_value(tune_value.value if tune_value else None),
        )

    def _table_entry(self, table: TableDefinition, tune_value: TuneValue | None) -> ParameterCatalogEntry:
        return ParameterCatalogEntry(
            name=table.name,
            kind="table",
            page=table.page,
            offset=table.offset,
            units=table.units,
            data_type="array",
            shape=f"{table.rows}x{table.columns}",
            tune_present=tune_value is not None,
            tune_preview=self._preview_value(tune_value.value if tune_value else None),
        )

    def _tune_only_entry(self, tune_value: TuneValue) -> ParameterCatalogEntry:
        is_table = bool(tune_value.rows or tune_value.cols or isinstance(tune_value.value, list))
        shape = (
            f"{tune_value.rows or len(tune_value.value)}x{tune_value.cols or 1}"
            if isinstance(tune_value.value, list)
            else "1x1"
        )
        return ParameterCatalogEntry(
            name=tune_value.name,
            kind="table" if is_table else "scalar",
            page=None,
            offset=None,
            units=tune_value.units,
            data_type="tune-only",
            shape=shape,
            tune_present=True,
            tune_preview=self._preview_value(tune_value.value),
        )

    @staticmethod
    def _preview_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            preview = ", ".join(str(item) for item in value[:4])
            suffix = f" ... ({len(value)} values)" if len(value) > 4 else ""
            return preview + suffix
        return str(value)
