"""Future Phase 12 deliverable 4 — ``live_data_map.h`` parser.

Reads the Speeduino firmware ``live_data_map.h`` header (located at
``speeduino/live_data_map.h`` in the firmware source tree) and produces
a ``ChannelContract``. The header is the firmware-side single source of
truth for byte positions in the live-data packet; this parser lets the
desktop app consume those positions directly instead of duplicating them
in INI ``[OutputChannels]`` strings.

Header structure consumed by this parser:

  1. A doxygen comment block above the table containing rows like::

         * 4-5      4     MAP                            U16 LE         map (kPa)
         * 14-15    13    RPM                            U16 LE         RPM
         * 84       57    status3                        U08 bits       status3 [LOCKED]

  2. ``#define LIVE_DATA_MAP_SIZE  148U`` — total packet size.
  3. ``static constexpr uint16_t OCH_OFFSET_*`` constants for the
     well-known special offsets (board capability flags, flash health,
     runtime status A).

The parser is line-based and tolerant of trailing whitespace and the
``[LOCKED]``, ``[low]``, and ``(Phase N)`` markers in the notes column.
Unknown rows (e.g. the readable-only ``startRevolutions [31:16]``
sub-row) are skipped rather than rejected.
"""
from __future__ import annotations

import re
from pathlib import Path

from tuner.domain.channel_contract import (
    ChannelContract,
    ChannelEncoding,
    ChannelEntry,
)


# Match a single byte-table row inside the doxygen comment.
#   group "byte"     : "4-5" or "147"
#   group "ridx"     : digit run or "-"
#   group "field"    : the currentStatus member / expression (allowed to
#                      contain whitespace because some rows are like
#                      "AEamount >> 1 [low]"; we capture greedily and
#                      then split off the encoding token by anchoring
#                      against the next column)
#   group "encoding" : "U08", "U08 bits", "U16 LE", "S16 LE", "U32 LE"
#   group "notes"    : free-text trailing notes
_ROW_RE = re.compile(
    r"""
    ^\s*\*\s+
    (?P<byte>\d+(?:-\d+)?)\s+
    (?P<ridx>-|\d+)\s+
    (?P<field>.+?)\s{2,}
    (?P<encoding>U08(?:\s+bits)?|U16\s+LE|S16\s+LE|U32\s+LE)\s+
    (?P<notes>.*?)\s*$
    """,
    re.VERBOSE,
)

_LIVE_DATA_MAP_SIZE_RE = re.compile(
    r"#define\s+LIVE_DATA_MAP_SIZE\s+(\d+)U?", re.IGNORECASE,
)
_OCH_OFFSET_RE = re.compile(
    r"OCH_OFFSET_(?P<key>[A-Z_]+)\s*=\s*(?P<value>\d+)U?", re.IGNORECASE,
)


class LiveDataMapParser:
    """Parses ``live_data_map.h`` into a :class:`ChannelContract`."""

    def parse(self, path: Path, *, firmware_signature: str | None = None) -> ChannelContract:
        if not path.exists():
            raise FileNotFoundError(f"live_data_map.h not found: {path}")
        return self.parse_text(
            path.read_text(encoding="utf-8"),
            firmware_signature=firmware_signature,
        )

    def parse_text(
        self, text: str, *, firmware_signature: str | None = None,
    ) -> ChannelContract:
        entries: list[ChannelEntry] = []
        for line in text.splitlines():
            entry = self._parse_row(line)
            if entry is not None:
                entries.append(entry)

        size_match = _LIVE_DATA_MAP_SIZE_RE.search(text)
        log_entry_size = int(size_match.group(1)) if size_match else 0

        offsets: dict[str, int] = {}
        for match in _OCH_OFFSET_RE.finditer(text):
            offsets[match.group("key").upper()] = int(match.group("value"))

        return ChannelContract(
            log_entry_size=log_entry_size,
            firmware_signature=firmware_signature,
            entries=tuple(entries),
            runtime_status_a_offset=offsets.get("RUNTIME_STATUS_A"),
            board_capability_flags_offset=offsets.get("BOARD_CAPABILITY_FLAGS"),
            flash_health_status_offset=offsets.get("FLASH_HEALTH_STATUS"),
        )

    @staticmethod
    def _parse_row(line: str) -> ChannelEntry | None:
        match = _ROW_RE.match(line)
        if match is None:
            return None
        byte_text = match.group("byte")
        if "-" in byte_text:
            byte_start_str, byte_end_str = byte_text.split("-", 1)
            byte_start, byte_end = int(byte_start_str), int(byte_end_str)
        else:
            byte_start = byte_end = int(byte_text)

        ridx_text = match.group("ridx")
        readable_index = None if ridx_text == "-" else int(ridx_text)

        encoding = ChannelEncoding.from_header_text(match.group("encoding"))
        notes = match.group("notes")
        locked = "[LOCKED]" in notes
        # Normalize the notes by stripping the trailing [LOCKED] tag so
        # consumers can match against the channel name without juggling
        # marker text.
        clean_notes = notes.replace("[LOCKED]", "").strip()

        # The first whitespace-separated token of the notes column is the
        # canonical INI channel name in the firmware header (e.g. "map"
        # for "map (kPa)"); fall back to the field name when notes are
        # missing or start with deprecation text.
        name = clean_notes.split()[0] if clean_notes else match.group("field").strip()
        if name.upper() == "DEPRECATED:":
            name = match.group("field").strip()

        return ChannelEntry(
            name=name,
            byte_start=byte_start,
            byte_end=byte_end,
            readable_index=readable_index,
            encoding=encoding,
            field=match.group("field").strip(),
            notes=clean_notes,
            locked=locked,
        )
