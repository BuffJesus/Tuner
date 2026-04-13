"""Session-level operation log.

Tracks every mutation to the tune at the session level so the user can see
what changed, when, and in what direction — regardless of which page they are
currently viewing.

Operations are append-only within a session.  ``clear`` resets for a new
project/tune load.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OperationKind(str, Enum):
    STAGED = "staged"
    REVERTED = "reverted"
    WRITTEN = "written"
    BURNED = "burned"


@dataclass(slots=True, frozen=True)
class OperationEntry:
    kind: OperationKind
    parameter_name: str
    old_value: str
    new_value: str
    timestamp: datetime = field(default_factory=datetime.now)
    page_title: str = ""

    def summary_line(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S")
        if self.kind == OperationKind.STAGED:
            return f"{ts}  staged   {self.parameter_name}: {self.old_value} → {self.new_value}"
        if self.kind == OperationKind.REVERTED:
            return f"{ts}  reverted {self.parameter_name}: {self.new_value} ← {self.old_value}"
        if self.kind == OperationKind.WRITTEN:
            return f"{ts}  written  {self.parameter_name} = {self.new_value}"
        if self.kind == OperationKind.BURNED:
            return f"{ts}  burned   {self.parameter_name} = {self.new_value}"
        return f"{ts}  {self.kind.value} {self.parameter_name}"


class OperationLogService:
    def __init__(self) -> None:
        self._entries: list[OperationEntry] = []

    def record_staged(
        self,
        parameter_name: str,
        old_value: str,
        new_value: str,
        page_title: str = "",
    ) -> None:
        self._entries.append(
            OperationEntry(
                kind=OperationKind.STAGED,
                parameter_name=parameter_name,
                old_value=old_value,
                new_value=new_value,
                page_title=page_title,
            )
        )

    def record_reverted(
        self,
        parameter_name: str,
        old_value: str,
        new_value: str,
        page_title: str = "",
    ) -> None:
        self._entries.append(
            OperationEntry(
                kind=OperationKind.REVERTED,
                parameter_name=parameter_name,
                old_value=old_value,
                new_value=new_value,
                page_title=page_title,
            )
        )

    def record_written(
        self,
        parameter_name: str,
        value: str,
        page_title: str = "",
    ) -> None:
        self._entries.append(
            OperationEntry(
                kind=OperationKind.WRITTEN,
                parameter_name=parameter_name,
                old_value=value,
                new_value=value,
                page_title=page_title,
            )
        )

    def record_burned(
        self,
        parameter_name: str,
        value: str,
        page_title: str = "",
    ) -> None:
        self._entries.append(
            OperationEntry(
                kind=OperationKind.BURNED,
                parameter_name=parameter_name,
                old_value=value,
                new_value=value,
                page_title=page_title,
            )
        )

    def entries(self) -> tuple[OperationEntry, ...]:
        return tuple(self._entries)

    def recent(self, n: int = 50) -> tuple[OperationEntry, ...]:
        return tuple(self._entries[-n:])

    def clear(self) -> None:
        self._entries.clear()

    def summary_text(self, n: int = 50) -> str:
        recent = self.recent(n)
        if not recent:
            return "No operations recorded this session."
        return "\n".join(e.summary_line() for e in reversed(recent))
