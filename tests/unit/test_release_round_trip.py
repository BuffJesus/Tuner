"""Real-release round-trip tests for Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq.

These tests cover fragile area #6: the MSQ was validated by inspection but lacked
an automated load → edit → save → reload test.

The fixtures are the actual release artifacts:
  - Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq
  - speeduino-dropbear-v2.0.1-u16p2-experimental.ini
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_MSQ = _FIXTURES / "Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1-u16p2-experimental.ini"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tune():
    return MsqParser().parse(_MSQ)


def _edit_service(tune=None):
    svc = LocalTuneEditService()
    svc.set_tune_file(tune or _load_tune())
    return svc


def _round_trip(edit_service: LocalTuneEditService, tmp_path: Path, name: str = "out.msq") -> object:
    """Save to tmp and reload. Returns the reloaded TuneFile."""
    dest = tmp_path / name
    MsqWriteService().save(_MSQ, dest, edit_service)
    return MsqParser().parse(dest)


def _scalar(tune, name: str):
    return next((c for c in tune.constants if c.name == name and not isinstance(c.value, list)), None)


def _table(tune, name: str):
    return next((c for c in tune.constants if c.name == name and isinstance(c.value, list)), None)


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------

def test_fixture_msq_loads_with_expected_signature() -> None:
    tune = _load_tune()
    assert tune.signature == "speeduino 202501-T41-U16P2"
    assert tune.page_count == 15


def test_fixture_msq_has_req_fuel() -> None:
    tune = _load_tune()
    req = _scalar(tune, "reqFuel")
    assert req is not None
    assert isinstance(req.value, float)
    assert 0.0 < req.value < 30.0


def test_fixture_msq_lambda_table_has_real_data() -> None:
    tune = _load_tune()
    lam = _table(tune, "lambdaTable")
    assert lam is not None
    assert lam.rows == 16
    assert lam.cols == 16
    # Real data — should not be all zeros
    assert any(v != 0.0 for v in lam.value)


def test_fixture_msq_afr_table_has_real_data() -> None:
    """afrTable is at lastOffset after lambdaTable — verifies lastOffset resolution."""
    tune = _load_tune()
    afr = _table(tune, "afrTable")
    assert afr is not None
    assert afr.rows == 16
    assert afr.cols == 16
    # afrTable stores AFR units; Ford300 tune idles near stoich (14.7)
    assert any(v > 10.0 for v in afr.value)


def test_fixture_ini_loads_with_matching_signature() -> None:
    defn = IniParser().parse(_INI)
    assert defn.name == "speeduino 202501-T41-U16P2"


def test_fixture_ini_page_count_matches_msq() -> None:
    defn = IniParser().parse(_INI)
    tune = _load_tune()
    assert len(defn.page_sizes) == tune.page_count


# ---------------------------------------------------------------------------
# Scalar edit round-trips
# ---------------------------------------------------------------------------

def test_scalar_edit_round_trip_req_fuel(tmp_path: Path) -> None:
    """Edit reqFuel, save, reload — new value must survive."""
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "7.3")
    reloaded = _round_trip(svc, tmp_path)
    req = _scalar(reloaded, "reqFuel")
    assert req is not None
    assert req.value == pytest.approx(7.3, abs=0.05)


def test_scalar_edit_round_trip_n_cylinders(tmp_path: Path) -> None:
    """Edit nCylinders (currently 6) to 8."""
    svc = _edit_service()
    svc.stage_scalar_value("nCylinders", "8")
    reloaded = _round_trip(svc, tmp_path)
    nc = _scalar(reloaded, "nCylinders")
    assert nc is not None
    assert nc.value == pytest.approx(8.0)


def test_scalar_edit_does_not_corrupt_other_scalars(tmp_path: Path) -> None:
    """Editing one scalar must not corrupt adjacent constants."""
    tune = _load_tune()
    original_ncyl = _scalar(tune, "nCylinders").value
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "9.0")
    reloaded = _round_trip(svc, tmp_path)
    assert _scalar(reloaded, "nCylinders").value == pytest.approx(original_ncyl)


# ---------------------------------------------------------------------------
# Table edit round-trips
# ---------------------------------------------------------------------------

def test_table_cell_edit_round_trip_ve_table(tmp_path: Path) -> None:
    """Edit a single veTable cell, save, reload — cell must survive."""
    tune = _load_tune()
    ve_original = _table(tune, "veTable")
    original_cell_0 = ve_original.value[0]
    svc = _edit_service(tune)
    new_val = original_cell_0 + 5.0
    svc.stage_list_cell("veTable", 0, str(new_val))
    reloaded = _round_trip(svc, tmp_path)
    ve_reloaded = _table(reloaded, "veTable")
    assert ve_reloaded is not None
    assert ve_reloaded.value[0] == pytest.approx(new_val, abs=0.5)


def test_table_cell_edit_preserves_rest_of_table(tmp_path: Path) -> None:
    """Editing one veTable cell must not corrupt the remaining 255 cells."""
    tune = _load_tune()
    ve_original = _table(tune, "veTable")
    svc = _edit_service(tune)
    svc.stage_list_cell("veTable", 0, "99.0")
    reloaded = _round_trip(svc, tmp_path)
    ve_reloaded = _table(reloaded, "veTable")
    # All cells beyond index 0 must match the originals
    for i in range(1, len(ve_original.value)):
        assert ve_reloaded.value[i] == pytest.approx(ve_original.value[i], abs=0.5), (
            f"veTable[{i}] changed unexpectedly: "
            f"{ve_original.value[i]} → {ve_reloaded.value[i]}"
        )


# ---------------------------------------------------------------------------
# Preservation of lastOffset-derived tables
# ---------------------------------------------------------------------------

def test_lambda_table_preserved_after_scalar_edit(tmp_path: Path) -> None:
    """lambdaTable must survive a reqFuel scalar edit unchanged."""
    tune = _load_tune()
    original_lam = _table(tune, "lambdaTable").value[:]
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "8.5")
    reloaded = _round_trip(svc, tmp_path)
    reloaded_lam = _table(reloaded, "lambdaTable")
    assert reloaded_lam is not None
    for i, (orig, new) in enumerate(zip(original_lam, reloaded_lam.value)):
        assert new == pytest.approx(orig, abs=0.001), f"lambdaTable[{i}] changed: {orig} → {new}"


def test_afr_table_preserved_after_scalar_edit(tmp_path: Path) -> None:
    """afrTable (lastOffset-derived) must survive a reqFuel scalar edit unchanged."""
    tune = _load_tune()
    original_afr = _table(tune, "afrTable").value[:]
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "8.5")
    reloaded = _round_trip(svc, tmp_path)
    reloaded_afr = _table(reloaded, "afrTable")
    assert reloaded_afr is not None
    for i, (orig, new) in enumerate(zip(original_afr, reloaded_afr.value)):
        assert new == pytest.approx(orig, abs=0.1), f"afrTable[{i}] changed: {orig} → {new}"


def test_afr_table_preserved_after_ve_table_edit(tmp_path: Path) -> None:
    """afrTable must survive a veTable cell edit unchanged."""
    tune = _load_tune()
    original_afr = _table(tune, "afrTable").value[:]
    svc = _edit_service(tune)
    svc.stage_list_cell("veTable", 10, "88.0")
    reloaded = _round_trip(svc, tmp_path)
    reloaded_afr = _table(reloaded, "afrTable")
    assert reloaded_afr is not None
    for i, (orig, new) in enumerate(zip(original_afr, reloaded_afr.value)):
        assert new == pytest.approx(orig, abs=0.1), f"afrTable[{i}] changed: {orig} → {new}"


# ---------------------------------------------------------------------------
# Multiple edits in one pass
# ---------------------------------------------------------------------------

def test_multiple_scalar_and_table_edits_round_trip(tmp_path: Path) -> None:
    """Edit both a scalar and a table cell in one pass; both must survive reload."""
    tune = _load_tune()
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "11.1")
    svc.stage_list_cell("veTable", 5, "42.0")
    reloaded = _round_trip(svc, tmp_path)
    assert _scalar(reloaded, "reqFuel").value == pytest.approx(11.1, abs=0.05)
    assert _table(reloaded, "veTable").value[5] == pytest.approx(42.0, abs=0.5)


# ---------------------------------------------------------------------------
# Output format sanity
# ---------------------------------------------------------------------------

def test_saved_msq_is_valid_xml(tmp_path: Path) -> None:
    """The saved file must be parseable as XML."""
    from xml.etree import ElementTree as ET
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    dest = tmp_path / "out.msq"
    MsqWriteService().save(_MSQ, dest, svc)
    tree = ET.parse(dest)
    root = tree.getroot()
    assert root is not None


def test_saved_msq_preserves_xml_declaration(tmp_path: Path) -> None:
    """The saved file must start with an XML declaration (ISO-8859-1)."""
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    dest = tmp_path / "out.msq"
    MsqWriteService().save(_MSQ, dest, svc)
    raw = dest.read_bytes()
    assert raw.startswith(b"<?xml")


def test_saved_msq_preserves_signature(tmp_path: Path) -> None:
    """The saved file must carry the original versionInfo signature."""
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    reloaded = _round_trip(svc, tmp_path)
    assert reloaded.signature == "speeduino 202501-T41-U16P2"
    assert reloaded.page_count == 15


def test_unedited_save_is_functionally_identical(tmp_path: Path) -> None:
    """Saving with no staged edits must produce a reload-identical tune."""
    tune = _load_tune()
    svc = _edit_service(tune)
    # No staged edits — round-trip should be a no-op
    reloaded = _round_trip(svc, tmp_path)
    original_req = _scalar(tune, "reqFuel").value
    assert _scalar(reloaded, "reqFuel").value == pytest.approx(original_req, abs=0.01)
    original_ve0 = _table(tune, "veTable").value[0]
    assert _table(reloaded, "veTable").value[0] == pytest.approx(original_ve0, abs=0.5)
