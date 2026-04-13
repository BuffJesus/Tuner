from __future__ import annotations

from dataclasses import dataclass
import re

from tuner.domain.tuning_pages import TuningPage, TuningPageGroup


@dataclass(slots=True, frozen=True)
class PageFamilyTab:
    page_id: str
    title: str


@dataclass(slots=True, frozen=True)
class PageFamily:
    family_id: str
    title: str
    tabs: tuple[PageFamilyTab, ...]


class PageFamilyService:
    def build_index(self, page_groups: list[TuningPageGroup]) -> dict[str, PageFamily]:
        pages = [page for group in page_groups for page in group.pages]
        family_map: dict[str, list[TuningPage]] = {}
        for page in pages:
            family_id = self._family_id(page)
            if family_id is None:
                continue
            family_map.setdefault(family_id, []).append(page)

        result: dict[str, PageFamily] = {}
        for family_id, family_pages in family_map.items():
            if len(family_pages) < 2:
                continue
            ordered = tuple(sorted(
                family_pages,
                key=lambda page: (
                    page.page_number if page.page_number is not None else 9999,
                    self._tab_sort_key(page),
                    page.title.lower(),
                ),
            ))
            family = PageFamily(
                family_id=family_id,
                title=self._family_title(family_id),
                tabs=tuple(PageFamilyTab(page_id=page.page_id, title=self._tab_title(family_id, page)) for page in ordered),
            )
            for page in ordered:
                result[page.page_id] = family
        return result

    @staticmethod
    def _family_title(family_id: str) -> str:
        return {
            "fuel-trims": "Fuel Trims",
            "fuel-tables": "Fuel Tables",
            "spark-tables": "Spark Tables",
            "target-tables": "Target Tables",
            "vvt": "VVT",
        }[family_id]

    def _family_id(self, page: TuningPage) -> str | None:
        title = page.title.lower()
        if "fuel trim" in title or "sequential fuel trim" in title:
            return "fuel-trims"
        if title == "ve table" or title == "second fuel table":
            return "fuel-tables"
        if title == "spark table" or title == "second spark table":
            return "spark-tables"
        if title in {"afr target table", "lambda target table"}:
            return "target-tables"
        if title == "vvt target/duty" or title == "vvt2 target/duty" or title == "vvt control":
            return "vvt"
        return None

    @staticmethod
    def _tab_sort_key(page: TuningPage) -> tuple[int, str]:
        title = page.title.lower()
        if "sequential fuel trim (1-4)" in title:
            return (10, title)
        if "fuel trim table 2" in title:
            return (20, title)
        if "fuel trim table 3" in title:
            return (30, title)
        if "fuel trim table 4" in title:
            return (40, title)
        if "fuel trim table 6" in title:
            return (60, title)
        if "fuel trim table 7" in title:
            return (70, title)
        if "fuel trim table 8" in title:
            return (80, title)
        if "sequential fuel trim (5-8)" in title:
            return (90, title)
        if "sequential fuel trim settings" in title:
            return (100, title)
        if title == "ve table":
            return (10, title)
        if title == "second fuel table":
            return (20, title)
        if title == "spark table":
            return (10, title)
        if title == "second spark table":
            return (20, title)
        if title == "afr target table":
            return (10, title)
        if title == "lambda target table":
            return (20, title)
        if title == "vvt target/duty":
            return (10, title)
        if title == "vvt2 target/duty":
            return (20, title)
        if title == "vvt control":
            return (30, title)
        return (999, title)

    def _tab_title(self, family_id: str, page: TuningPage) -> str:
        title = page.title
        lower = title.lower()
        if family_id == "fuel-trims":
            if "sequential fuel trim (1-4)" in lower:
                return "Seq 1-4"
            if "sequential fuel trim (5-8)" in lower:
                return "Seq 5-8"
            if "sequential fuel trim settings" in lower:
                return "Settings"
            match = re.search(r"fuel trim table (\d+)", lower)
            if match:
                return f"Trim {match.group(1)}"
        if family_id == "fuel-tables":
            return "Primary" if lower == "ve table" else "Secondary"
        if family_id == "spark-tables":
            return "Primary" if lower == "spark table" else "Secondary"
        if family_id == "target-tables":
            return "AFR" if lower == "afr target table" else "Lambda"
        if family_id == "vvt":
            if lower == "vvt target/duty":
                return "VVT1"
            if lower == "vvt2 target/duty":
                return "VVT2"
            if lower == "vvt control":
                return "Control"
        return title
