from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.tuning_pages import TuningPage
from tuner.domain.tune import TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService


@dataclass(slots=True, frozen=True)
class TuningPageDiffEntry:
    name: str
    before_preview: str
    after_preview: str


@dataclass(slots=True, frozen=True)
class TuningPageDiffResult:
    entries: tuple[TuningPageDiffEntry, ...]

    @property
    def summary(self) -> str:
        count = len(self.entries)
        if count == 0:
            return "No staged changes on this page."
        return f"{count} staged change{'s' if count != 1 else ''} on this page."

    @property
    def detail_text(self) -> str:
        if not self.entries:
            return "No staged changes on this page."
        return "\n".join(
            f"{entry.name}: {entry.before_preview} -> {entry.after_preview}"
            for entry in self.entries
        )


class TuningPageDiffService:
    def build_page_diff(
        self,
        page: TuningPage,
        local_tune_edit_service: LocalTuneEditService,
    ) -> TuningPageDiffResult:
        entries: list[TuningPageDiffEntry] = []
        for name in page.parameter_names:
            if not local_tune_edit_service.is_dirty(name):
                continue
            staged_value = local_tune_edit_service.get_value(name)
            base_value = local_tune_edit_service.get_base_value(name)
            if staged_value is None:
                continue
            entries.append(
                TuningPageDiffEntry(
                    name=name,
                    before_preview=self._preview(base_value),
                    after_preview=self._preview(staged_value),
                )
            )
        return TuningPageDiffResult(entries=tuple(entries))

    def _preview(self, tune_value: TuneValue | None) -> str:
        if tune_value is None:
            return "n/a"
        value = tune_value.value
        if isinstance(value, list):
            return self._list_preview(value)
        return str(value)

    @staticmethod
    def _list_preview(values: list[float]) -> str:
        preview = ", ".join(str(item) for item in values[:4])
        suffix = f" ... ({len(values)} values)" if len(values) > 4 else ""
        return preview + suffix
