"""Tests for the live_data_map.h parser and the resulting ChannelContract.

Future Phase 12 deliverable 4. Exercises the parser against:
  - synthetic header rows that lock the row format
  - the **real** firmware header at
    ``C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/live_data_map.h``
    so any future schema bump that breaks our parser fails loudly
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tuner.domain.channel_contract import (
    ChannelContract,
    ChannelEncoding,
    ChannelEntry,
)
from tuner.services.live_data_map_parser import LiveDataMapParser


_REAL_HEADER = Path(
    "C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/live_data_map.h"
)


# ---------------------------------------------------------------------------
# Synthetic-row parser tests (no firmware tree dependency)
# ---------------------------------------------------------------------------

_SYNTHETIC = textwrap.dedent("""\
    /**
     * Byte(s)  RIdx  Field                          Encoding       Notes
     * -------- ----- ------------------------------ -------------- ---------------------------
     * 0        0     secl                           U08            secl
     * 4-5      4     MAP                            U16 LE         map (kPa)
     * 14-15    13    RPM                            U16 LE         RPM
     * 22-23    19    tpsDOT                         S16 LE         tpsDOT
     * 84       57    status3                        U08 bits       status3 [LOCKED]
     * 143-146  102   startRevolutions [31:0] LE     U32 LE         startRevolutions (Phase 10) [LOCKED]
     * 147      104   runtimeStatusA packed          U08 bits       runtimeStatusA (Phase 10) [LOCKED]
     */

    #define LIVE_DATA_MAP_SIZE  148U

    static constexpr uint16_t OCH_OFFSET_BOARD_CAPABILITY_FLAGS = 130U;
    static constexpr uint16_t OCH_OFFSET_FLASH_HEALTH_STATUS    = 131U;
    static constexpr uint16_t OCH_OFFSET_RUNTIME_STATUS_A       = 147U;
""")


class TestSyntheticParser:
    def _parse(self) -> ChannelContract:
        return LiveDataMapParser().parse_text(_SYNTHETIC)

    def test_log_entry_size_extracted(self) -> None:
        contract = self._parse()
        assert contract.log_entry_size == 148

    def test_special_offsets_extracted(self) -> None:
        contract = self._parse()
        assert contract.runtime_status_a_offset == 147
        assert contract.board_capability_flags_offset == 130
        assert contract.flash_health_status_offset == 131

    def test_single_byte_row(self) -> None:
        contract = self._parse()
        secl = contract.find("secl")
        assert secl is not None
        assert secl.byte_start == 0
        assert secl.byte_end == 0
        assert secl.encoding == ChannelEncoding.U08
        assert secl.locked is False

    def test_two_byte_le_row(self) -> None:
        contract = self._parse()
        rpm = contract.find("RPM")
        assert rpm is not None
        assert rpm.byte_start == 14
        assert rpm.byte_end == 15
        assert rpm.encoding == ChannelEncoding.U16_LE
        assert rpm.width == 2

    def test_four_byte_u32_row(self) -> None:
        contract = self._parse()
        sr = contract.find("startRevolutions")
        assert sr is not None
        assert sr.byte_start == 143
        assert sr.byte_end == 146
        assert sr.encoding == ChannelEncoding.U32_LE
        assert sr.width == 4
        assert sr.locked is True

    def test_signed_row(self) -> None:
        contract = self._parse()
        tps = contract.find("tpsDOT")
        assert tps is not None
        assert tps.encoding == ChannelEncoding.S16_LE

    def test_bits_row_and_locked_flag(self) -> None:
        contract = self._parse()
        s3 = contract.find("status3")
        assert s3 is not None
        assert s3.encoding == ChannelEncoding.U08_BITS
        assert s3.locked is True
        # The [LOCKED] tag is stripped from the notes column.
        assert "[LOCKED]" not in s3.notes

    def test_find_by_byte(self) -> None:
        contract = self._parse()
        # Bytes 4 and 5 both belong to MAP
        for byte in (4, 5):
            entry = contract.find_by_byte(byte)
            assert entry is not None
            assert entry.name == "map"
        assert contract.find_by_byte(99999) is None

    def test_unknown_row_skipped(self) -> None:
        text = textwrap.dedent("""\
            /**
             * Byte(s)  RIdx  Field                          Encoding       Notes
             * -------- ----- ------------------------------ -------------- ---------------------------
             * not a real row at all
             *          103   startRevolutions [31:16]       -              (readable hi-half of above)
             */
            #define LIVE_DATA_MAP_SIZE 148U
            """)
        contract = LiveDataMapParser().parse_text(text)
        assert contract.entries == ()
        assert contract.log_entry_size == 148


# ---------------------------------------------------------------------------
# Real firmware header — locks the parser to the actual file on disk
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _REAL_HEADER.exists(),
    reason="Speeduino firmware tree not on this machine",
)
class TestRealHeader:
    def _parse(self) -> ChannelContract:
        return LiveDataMapParser().parse(
            _REAL_HEADER, firmware_signature="speeduino 202501-T41",
        )

    def test_log_entry_size_is_148(self) -> None:
        contract = self._parse()
        assert contract.log_entry_size == 148

    def test_firmware_signature_attached(self) -> None:
        contract = self._parse()
        assert contract.firmware_signature == "speeduino 202501-T41"

    def test_runtime_status_a_at_offset_147(self) -> None:
        contract = self._parse()
        assert contract.runtime_status_a_offset == 147
        assert contract.board_capability_flags_offset == 130
        assert contract.flash_health_status_offset == 131

    def test_known_channels_present(self) -> None:
        """Spot-check that the parser caught the high-leverage rows.
        These names match the firmware notes column verbatim."""
        contract = self._parse()
        for name in ("secl", "map", "RPM", "tpsDOT", "status3", "knockCount"):
            assert contract.find(name) is not None, f"missing: {name}"

    def test_runtime_status_a_byte_is_a_locked_bits_field(self) -> None:
        contract = self._parse()
        entry = contract.find_by_byte(147)
        assert entry is not None
        assert entry.encoding == ChannelEncoding.U08_BITS
        assert entry.locked is True

    def test_start_revolutions_spans_4_bytes_and_is_locked(self) -> None:
        contract = self._parse()
        entry = contract.find_by_byte(143)
        assert entry is not None
        assert entry.byte_start == 143
        assert entry.byte_end == 146
        assert entry.encoding == ChannelEncoding.U32_LE
        assert entry.locked is True

    def test_total_byte_coverage_matches_log_entry_size(self) -> None:
        """Sum of all parsed entry widths should equal LIVE_DATA_MAP_SIZE.
        This is the structural canary that catches a parser regression
        the moment a real firmware row stops matching."""
        contract = self._parse()
        covered = sum(e.width for e in contract.entries)
        assert covered == contract.log_entry_size, (
            f"covered {covered} bytes, expected {contract.log_entry_size}"
        )
