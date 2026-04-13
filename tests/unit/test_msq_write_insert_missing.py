"""Tests for the Phase 7 follow-up MsqWriteService ``insert_missing`` flag.

Closes Fragile area #1: when a generator stages values for a table that
has no ``<constant>`` node in the source MSQ XML, ``insert_missing=True``
inserts the new node into the first ``<page>`` element instead of silently
dropping the staged values on save. The default ``insert_missing=False``
preserves the existing documented behaviour for byte-stable round trips.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService

_HEADER = textwrap.dedent("""\
    <?xml version="1.0" encoding="ISO-8859-1"?>
    <msq xmlns="http://www.msefi.com/:msq">
      <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
      <page number="1">
""")
_FOOTER = textwrap.dedent("""\
      </page>
    </msq>
    """)


def _msq_with_only_reqfuel(tmp_path: Path) -> Path:
    body = '    <constant name="reqFuel" units="ms" digits="1">8.5</constant>\n'
    msq_path = tmp_path / "missing_table.msq"
    msq_path.write_text(_HEADER + body + _FOOTER, encoding="ISO-8859-1")
    return msq_path


# ---------------------------------------------------------------------------
# Default behaviour (insert_missing=False) — unchanged
# ---------------------------------------------------------------------------

class TestDefaultUnchanged:
    def test_default_still_drops_absent_constants(self, tmp_path: Path) -> None:
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        edit_service.set_or_add_base_value(
            "veTable", [55.0, 56.0, 57.0, 58.0], rows=2, cols=2, units="%"
        )
        out = tmp_path / "default.msq"
        MsqWriteService().save(msq_path, out, edit_service)
        reloaded = MsqParser().parse(out)
        names = {c.name for c in reloaded.constants}
        assert "veTable" not in names


# ---------------------------------------------------------------------------
# insert_missing=True — Fragile area #1 fix
# ---------------------------------------------------------------------------

class TestInsertMissing:
    def test_inserts_missing_table_constant(self, tmp_path: Path) -> None:
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        edit_service.set_or_add_base_value(
            "veTable", [50.0, 55.0, 60.0, 65.0], rows=2, cols=2, units="%"
        )
        out = tmp_path / "insert.msq"
        MsqWriteService().save(msq_path, out, edit_service, insert_missing=True)
        reloaded = MsqParser().parse(out)
        ve = next((c for c in reloaded.constants if c.name == "veTable"), None)
        assert ve is not None
        assert ve.value == [50.0, 55.0, 60.0, 65.0]
        assert ve.rows == 2
        assert ve.cols == 2
        assert ve.units == "%"

    def test_preserves_existing_constants(self, tmp_path: Path) -> None:
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        edit_service.set_or_add_base_value(
            "veTable", [10.0, 20.0, 30.0, 40.0], rows=2, cols=2, units="%"
        )
        out = tmp_path / "preserve.msq"
        MsqWriteService().save(msq_path, out, edit_service, insert_missing=True)
        reloaded = MsqParser().parse(out)
        reqfuel = next(c for c in reloaded.constants if c.name == "reqFuel")
        assert reqfuel.value == 8.5

    def test_inserts_scalar_missing_from_source(self, tmp_path: Path) -> None:
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        edit_service.set_or_add_base_value("nCylinders", 6.0)
        out = tmp_path / "scalar.msq"
        MsqWriteService().save(msq_path, out, edit_service, insert_missing=True)
        reloaded = MsqParser().parse(out)
        cyl = next((c for c in reloaded.constants if c.name == "nCylinders"), None)
        assert cyl is not None
        assert cyl.value == 6.0

    def test_inserts_staged_only_value_with_no_base_entry(self, tmp_path: Path) -> None:
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        # Bypass set_or_add_base_value: stage directly into staged_values
        # to simulate a generator that only touched the staged layer.
        from tuner.domain.tune import TuneValue
        edit_service.staged_values["sparkTable"] = TuneValue(
            name="sparkTable", value=[20.0, 22.0, 24.0, 26.0],
            rows=2, cols=2, units="deg",
        )
        out = tmp_path / "staged_only.msq"
        MsqWriteService().save(msq_path, out, edit_service, insert_missing=True)
        reloaded = MsqParser().parse(out)
        spark = next((c for c in reloaded.constants if c.name == "sparkTable"), None)
        assert spark is not None
        assert spark.value == [20.0, 22.0, 24.0, 26.0]
        assert spark.units == "deg"

    def test_idempotent_second_save_does_not_duplicate_insertion(
        self, tmp_path: Path
    ) -> None:
        """Round-trip the saved file once more — the inserted node is now
        part of the source XML, so a second save should not duplicate it."""
        msq_path = _msq_with_only_reqfuel(tmp_path)
        tune = MsqParser().parse(msq_path)
        edit_service = LocalTuneEditService()
        edit_service.set_tune_file(tune)
        edit_service.set_or_add_base_value(
            "veTable", [50.0, 55.0, 60.0, 65.0], rows=2, cols=2, units="%"
        )
        first = tmp_path / "first.msq"
        MsqWriteService().save(msq_path, first, edit_service, insert_missing=True)

        # Re-load from the just-written file and save again.
        round_trip = MsqParser().parse(first)
        edit_service2 = LocalTuneEditService()
        edit_service2.set_tune_file(round_trip)
        second = tmp_path / "second.msq"
        MsqWriteService().save(first, second, edit_service2, insert_missing=True)

        reloaded = MsqParser().parse(second)
        ve_entries = [c for c in reloaded.constants if c.name == "veTable"]
        assert len(ve_entries) == 1
