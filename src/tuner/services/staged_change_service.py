from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.tune import TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService


@dataclass(slots=True)
class StagedChangeEntry:
    name: str
    preview: str
    before_preview: str = "n/a"
    page_title: str = "Other"
    is_written: bool = False


class StagedChangeService:
    def summarize(
        self,
        edit_service: LocalTuneEditService,
        page_titles: dict[str, str] | None = None,
        written_names: set[str] | None = None,
    ) -> list[StagedChangeEntry]:
        entries: list[StagedChangeEntry] = []
        page_titles = page_titles or {}
        written_names = written_names or set()
        for name, tune_value in sorted(edit_service.staged_values.items()):
            entries.append(
                StagedChangeEntry(
                    name=name,
                    preview=self._preview(tune_value),
                    before_preview=self._preview(edit_service.get_base_value(name)),
                    page_title=page_titles.get(name, "Other"),
                    is_written=name in written_names,
                )
            )
        return entries

    @staticmethod
    def _preview(tune_value: TuneValue | None) -> str:
        if tune_value is None:
            return "n/a"
        value = tune_value.value
        if isinstance(value, list):
            preview = ", ".join(str(item) for item in value[:4])
            suffix = f" ... ({len(value)} values)" if len(value) > 4 else ""
            return preview + suffix
        return str(value)
