"""Tests for blank-table materialization when the tune file lacks a table constant.

These tests cover the known fragile area documented in CLAUDE.md:
  "Blank table when tune lacks data: if a generator stages values but the MSQ
  has no <constant> element for that table, the save will write the staged values
  but a fresh load may produce an empty table."

Tests here verify:
  1. _ensure_table_page_materialized creates a zero-filled base entry when absent
  2. Axes are also materialized when absent
  3. Generator-staged values via replace_list are readable after materialization
  4. MsqWriteService drops tables absent from the source XML (documents the limit)
  5. Round-trip works correctly when the source MSQ has a blank <constant> node
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tuner.domain.ecu_definition import (
    EcuDefinition,
    TableDefinition,
    TableEditorDefinition,
)
from tuner.domain.tune import TuneFile, TuneValue
from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter


# ---------------------------------------------------------------------------
# Minimal MSQ XML helpers
# ---------------------------------------------------------------------------

_MSQ_HEADER = textwrap.dedent("""\
    <?xml version="1.0" encoding="ISO-8859-1"?>
    <msq xmlns="http://www.msefi.com/:msq">
      <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
      <page number="1">
    """)
_MSQ_FOOTER = textwrap.dedent("""\
      </page>
    </msq>
    """)


def _msq_with_blank_table(tmp_path: Path, table_rows: int, table_cols: int) -> Path:
    """Write a minimal MSQ file containing a zero-filled veTable constant node."""
    zeros = " ".join(["0"] * table_cols)
    rows_text = "\n".join(f"        {zeros}" for _ in range(table_rows))
    body = textwrap.dedent(f"""\
        <constant name="veTable" units="%" rows="{table_rows}" cols="{table_cols}" digits="1">
    {rows_text}
        </constant>
        <constant name="rpmBins" units="rpm" rows="1" cols="{table_cols}" digits="0">
            {" ".join(["500"] * table_cols)}
        </constant>
        <constant name="loadBins" units="kPa" rows="{table_rows}" cols="1" digits="0">
    {chr(10).join(f"        {30 + i * 10}" for i in range(table_rows))}
        </constant>
        <constant name="reqFuel" units="ms" digits="1">8.5</constant>
    """)
    msq_path = tmp_path / "blank_table.msq"
    msq_path.write_text(_MSQ_HEADER + body + _MSQ_FOOTER, encoding="ISO-8859-1")
    return msq_path


def _msq_without_table(tmp_path: Path) -> Path:
    """Write a minimal MSQ file that has NO veTable, rpmBins, or loadBins nodes."""
    body = '    <constant name="reqFuel" units="ms" digits="1">8.5</constant>\n'
    msq_path = tmp_path / "no_table.msq"
    msq_path.write_text(_MSQ_HEADER + body + _MSQ_FOOTER, encoding="ISO-8859-1")
    return msq_path


def _ve_definition() -> EcuDefinition:
    return EcuDefinition(
        name="Speeduino",
        tables=[
            TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%"),
            TableDefinition(name="rpmBins", rows=1, columns=2, page=1, offset=16, units="rpm"),
            TableDefinition(name="loadBins", rows=2, columns=1, page=1, offset=20, units="kPa"),
        ],
        table_editors=[
            TableEditorDefinition(
                table_id="ve",
                map_id="veMap",
                title="VE Table",
                page=1,
                x_bins="rpmBins",
                y_bins="loadBins",
                z_bins="veTable",
            )
        ],
    )


# ---------------------------------------------------------------------------
# 1. Materialization: absent table creates zero-filled entry
# ---------------------------------------------------------------------------

def test_materialize_absent_table_creates_zero_filled_entry() -> None:
    """_ensure_table_page_materialized must create a 2×2 zero list when veTable is absent."""
    definition = _ve_definition()
    tune_file = TuneFile(constants=[
        TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
        TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    assert edit_service.get_value("veTable") is None, "Pre-condition: veTable absent from tune"

    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    result = edit_service.get_value("veTable")
    assert result is not None, "veTable must exist after materialization"
    assert isinstance(result.value, list)
    assert len(result.value) == 4, "2x2 table → 4 elements"
    assert all(v == 0.0 for v in result.value), "Materialized values must be zero-filled"


def test_materialize_preserves_existing_table() -> None:
    """_ensure_table_page_materialized must not overwrite a table already in the tune."""
    definition = _ve_definition()
    existing_values = [10.0, 20.0, 30.0, 40.0]
    tune_file = TuneFile(constants=[
        TuneValue(name="veTable", value=list(existing_values), rows=2, cols=2, units="%"),
        TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
        TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    result = edit_service.get_value("veTable")
    assert result is not None
    assert result.value == existing_values, "Existing table must not be overwritten"


# ---------------------------------------------------------------------------
# 2. Axes are materialized when absent
# ---------------------------------------------------------------------------

def test_materialize_absent_table_also_creates_absent_axes() -> None:
    """When both table and all axes are absent, all three must be materialized."""
    definition = _ve_definition()
    tune_file = TuneFile(constants=[])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    assert edit_service.get_value("veTable") is not None
    assert edit_service.get_value("rpmBins") is not None
    assert edit_service.get_value("loadBins") is not None


def test_materialize_table_absent_but_axes_present() -> None:
    """When axes are already in the tune, only the table must be created."""
    definition = _ve_definition()
    tune_file = TuneFile(constants=[
        TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
        TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    ve = edit_service.get_value("veTable")
    assert ve is not None
    assert all(v == 0.0 for v in ve.value)  # type: ignore[union-attr]

    # Axes must be unchanged (not zeroed out)
    rpm = edit_service.get_value("rpmBins")
    assert rpm is not None
    assert rpm.value == [500.0, 1000.0]


# ---------------------------------------------------------------------------
# 3. Generator staging onto a materialized table
# ---------------------------------------------------------------------------

def test_replace_list_staging_after_materialization() -> None:
    """Generator-staged values via replace_list must be readable after materialization."""
    definition = _ve_definition()
    tune_file = TuneFile(constants=[
        TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
        TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    generated = [42.0, 44.0, 46.0, 48.0]
    edit_service.replace_list("veTable", generated)

    result = edit_service.get_value("veTable")
    assert result is not None
    assert result.value == generated


def test_staged_cells_readable_after_materialization() -> None:
    """Individual stage_list_cell edits on a materialized table must be readable."""
    definition = _ve_definition()
    tune_file = TuneFile(constants=[
        TuneValue(name="rpmBins", value=[500.0, 1000.0], rows=1, cols=2, units="rpm"),
        TuneValue(name="loadBins", value=[30.0, 60.0], rows=2, cols=1, units="kPa"),
    ])
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)
    presenter._ensure_table_page_materialized("veTable")  # type: ignore[attr-defined]

    edit_service.stage_list_cell("veTable", 0, "75.0")

    result = edit_service.get_value("veTable")
    assert result is not None
    assert result.value[0] == pytest.approx(75.0)
    # Remaining cells still zero
    assert result.value[1] == pytest.approx(0.0)
    assert result.value[2] == pytest.approx(0.0)
    assert result.value[3] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 4. Known limitation: MsqWriteService drops tables absent from source XML
# ---------------------------------------------------------------------------

def test_msq_write_drops_table_absent_from_source_xml(tmp_path: Path) -> None:
    """KNOWN LIMITATION: If veTable has no <constant> node in the source MSQ,
    MsqWriteService cannot write it — the staged value is lost on reload.

    This test documents the limitation rather than asserting a fix.
    """
    msq_path = _msq_without_table(tmp_path)

    tune = MsqParser().parse(msq_path)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)

    # Simulate generator: add the table into the base tune via set_or_add_base_value
    edit_service.set_or_add_base_value(
        "veTable", [55.0, 55.0, 55.0, 55.0], rows=2, cols=2, units="%"
    )
    assert edit_service.get_value("veTable") is not None

    # Save and reload
    out = tmp_path / "round_trip_no_node.msq"
    MsqWriteService().save(msq_path, out, edit_service)
    reloaded = MsqParser().parse(out)

    # The reloaded tune must NOT contain veTable because the source XML had no node for it
    names = {c.name for c in reloaded.constants}
    assert "veTable" not in names, (
        "veTable must NOT appear in the reload — source XML had no <constant> node for it.  "
        "This is the documented limitation: new constants not in source XML are dropped."
    )


# ---------------------------------------------------------------------------
# 5. Round-trip: blank (zero-filled) <constant> node in source MSQ
# ---------------------------------------------------------------------------

def test_blank_constant_node_round_trip_preserves_staged_values(tmp_path: Path) -> None:
    """When source MSQ has a zero-filled <constant> node, generator-staged values
    must survive a MsqWriteService save → MsqParser reload cycle."""
    msq_path = _msq_with_blank_table(tmp_path, table_rows=2, table_cols=2)

    tune = MsqParser().parse(msq_path)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)

    # Verify zero-filled table was parsed from source
    baseline = edit_service.get_value("veTable")
    assert baseline is not None
    assert all(v == 0.0 for v in baseline.value)  # type: ignore[union-attr]

    # Stage generator values
    generated = [50.0, 55.0, 60.0, 65.0]
    edit_service.replace_list("veTable", generated)

    # Save → reload
    out = tmp_path / "round_trip_blank.msq"
    MsqWriteService().save(msq_path, out, edit_service)
    reloaded_tune = MsqParser().parse(out)
    reloaded = LocalTuneEditService()
    reloaded.set_tune_file(reloaded_tune)

    result = reloaded.get_value("veTable")
    assert result is not None
    assert isinstance(result.value, list)
    assert len(result.value) == 4
    for i, expected in enumerate(generated):
        assert result.value[i] == pytest.approx(expected, abs=0.01), (
            f"veTable[{i}]: expected {expected}, got {result.value[i]}"
        )


def test_blank_constant_node_round_trip_preserves_other_constants(tmp_path: Path) -> None:
    """Saving staged veTable values must not corrupt other constants (reqFuel)."""
    msq_path = _msq_with_blank_table(tmp_path, table_rows=2, table_cols=2)

    tune = MsqParser().parse(msq_path)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)

    original_reqfuel = edit_service.get_value("reqFuel")
    assert original_reqfuel is not None
    assert isinstance(original_reqfuel.value, float)

    edit_service.replace_list("veTable", [50.0, 55.0, 60.0, 65.0])

    out = tmp_path / "round_trip_reqfuel.msq"
    MsqWriteService().save(msq_path, out, edit_service)
    reloaded_tune = MsqParser().parse(out)
    reloaded = LocalTuneEditService()
    reloaded.set_tune_file(reloaded_tune)

    reqfuel_after = reloaded.get_value("reqFuel")
    assert reqfuel_after is not None
    assert abs(reqfuel_after.value - original_reqfuel.value) < 0.001  # type: ignore[arg-type]


def test_blank_constant_node_round_trip_no_edits_is_lossless(tmp_path: Path) -> None:
    """Saving without any edits must produce an identical reload for all constants."""
    msq_path = _msq_with_blank_table(tmp_path, table_rows=2, table_cols=2)

    tune = MsqParser().parse(msq_path)
    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune)

    out = tmp_path / "round_trip_noop.msq"
    MsqWriteService().save(msq_path, out, edit_service)
    reloaded_tune = MsqParser().parse(out)
    reloaded = LocalTuneEditService()
    reloaded.set_tune_file(reloaded_tune)

    # reqFuel unchanged
    reqfuel = reloaded.get_value("reqFuel")
    assert reqfuel is not None
    assert abs(reqfuel.value - 8.5) < 0.001  # type: ignore[arg-type]

    # veTable still all zeros
    ve = reloaded.get_value("veTable")
    assert ve is not None
    assert all(v == 0.0 for v in ve.value)  # type: ignore[union-attr]
