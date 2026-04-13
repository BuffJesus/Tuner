from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChecklistItemStatus(StrEnum):
    OK = "ok"
    INFO = "info"       # informational; no action required
    WARNING = "warning"
    ERROR = "error"
    NEEDED = "needed"   # required input not yet configured


@dataclass(slots=True, frozen=True)
class SetupChecklistItem:
    """A single actionable item in a hardware setup checklist.

    Attributes
    ----------
    key:
        Stable identifier (e.g. ``"dwell_configured"``) used for deduplication
        and UI anchoring.
    title:
        Short imperative label shown in the checklist (e.g. ``"Set dwell time"``).
    status:
        Current status derived from the tune values.
    detail:
        One-sentence explanation of why this item has its current status,
        or what the operator should do to resolve it.
    parameter_name:
        Primary parameter name associated with this item, if any.
        Used to navigate directly to the field.
    cross_page:
        True when the item involves a parameter that is not on the primary page
        (i.e. the operator may need to navigate to another page to resolve it).
    """

    key: str
    title: str
    status: ChecklistItemStatus
    detail: str
    parameter_name: str | None = None
    cross_page: bool = False
