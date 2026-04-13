"""Production artifact round-trip tests.

Covers fragile area #6 for the production (non-U16P2) release pair:
  - speeduino-dropbear-v2.0.1.ini      (signature: speeduino 202501-T41)
  - speeduino-dropbear-v2.0.1-base-tune.msq

And cross-validates the Ford300_TwinGT28_BaseStartup.msq non-U16P2 tune,
which shares the same signature family.

Contrast with test_release_round_trip.py which covers the U16P2 experimental pair.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"
_MSQ = _FIXTURES / "speeduino-dropbear-v2.0.1-base-tune.msq"
_FORD_MSQ = _FIXTURES / "Ford300_TwinGT28_BaseStartup.msq"

_PRODUCTION_SIGNATURE = "speeduino 202501-T41"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_tune(path: Path = _MSQ):
    return MsqParser().parse(path)


def _edit_service(tune=None):
    svc = LocalTuneEditService()
    svc.set_tune_file(tune or _load_tune())
    return svc


def _round_trip(
    edit_service: LocalTuneEditService,
    tmp_path: Path,
    source: Path = _MSQ,
    name: str = "out.msq",
):
    dest = tmp_path / name
    MsqWriteService().save(source, dest, edit_service)
    return MsqParser().parse(dest)


def _scalar(tune, name: str):
    return next(
        (c for c in tune.constants if c.name == name and not isinstance(c.value, list)),
        None,
    )


def _table(tune, name: str):
    return next(
        (c for c in tune.constants if c.name == name and isinstance(c.value, list)),
        None,
    )


# ---------------------------------------------------------------------------
# INI fixture sanity
# ---------------------------------------------------------------------------

def test_production_ini_loads_with_expected_signature() -> None:
    defn = IniParser().parse(_INI)
    assert defn.name == _PRODUCTION_SIGNATURE


def test_production_ini_has_15_pages() -> None:
    defn = IniParser().parse(_INI)
    assert len(defn.page_sizes) == 15


def test_production_ini_has_34_curve_definitions() -> None:
    defn = IniParser().parse(_INI)
    assert len(defn.curve_definitions) == 34


def test_production_ini_page_sizes_match_msq() -> None:
    defn = IniParser().parse(_INI)
    tune = _load_tune()
    assert len(defn.page_sizes) == tune.page_count


# ---------------------------------------------------------------------------
# Production MSQ fixture sanity
# ---------------------------------------------------------------------------

def test_production_msq_loads_with_expected_signature() -> None:
    tune = _load_tune()
    assert tune.signature == _PRODUCTION_SIGNATURE


def test_production_msq_has_15_pages() -> None:
    tune = _load_tune()
    assert tune.page_count == 15


def test_production_msq_has_req_fuel() -> None:
    tune = _load_tune()
    req = _scalar(tune, "reqFuel")
    assert req is not None
    assert isinstance(req.value, float)
    assert 0.0 < req.value < 30.0


def test_production_msq_has_n_cylinders() -> None:
    tune = _load_tune()
    nc = _scalar(tune, "nCylinders")
    assert nc is not None
    assert float(nc.value) == pytest.approx(6.0)


def test_production_msq_ve_table_has_real_data() -> None:
    tune = _load_tune()
    ve = _table(tune, "veTable")
    assert ve is not None
    assert ve.rows == 16
    assert ve.cols == 16
    assert any(v != 0.0 for v in ve.value)


def test_production_msq_lambda_table_has_stoich_values() -> None:
    """lambdaTable stores values in lambda units (1.0 = stoich)."""
    tune = _load_tune()
    lam = _table(tune, "lambdaTable")
    assert lam is not None
    assert lam.rows == 16
    assert lam.cols == 16
    # Ford 300 tune targets near stoich; expect values clustered around 1.0
    assert any(0.8 < v < 1.2 for v in lam.value)


def test_production_msq_afr_table_has_real_data() -> None:
    """afrTable is at lastOffset after lambdaTable; verifies lastOffset resolution."""
    tune = _load_tune()
    afr = _table(tune, "afrTable")
    assert afr is not None
    assert afr.rows == 16
    assert afr.cols == 16
    # AFR units; stoich ~14.7; expect real values > 10
    assert any(v > 10.0 for v in afr.value)


def test_production_msq_afr_not_same_as_lambda() -> None:
    """afrTable and lambdaTable occupy different offsets — their values must differ."""
    tune = _load_tune()
    afr = _table(tune, "afrTable")
    lam = _table(tune, "lambdaTable")
    assert afr is not None and lam is not None
    # afrTable values are ~14-15 (AFR); lambda values are ~0.9-1.1 — never equal
    assert afr.value[0] != pytest.approx(lam.value[0], abs=0.5)


# ---------------------------------------------------------------------------
# Scalar edit round-trips
# ---------------------------------------------------------------------------

def test_scalar_edit_round_trip_req_fuel(tmp_path: Path) -> None:
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "7.3")
    reloaded = _round_trip(svc, tmp_path)
    req = _scalar(reloaded, "reqFuel")
    assert req is not None
    assert req.value == pytest.approx(7.3, abs=0.05)


def test_scalar_edit_round_trip_n_cylinders(tmp_path: Path) -> None:
    svc = _edit_service()
    svc.stage_scalar_value("nCylinders", "8")
    reloaded = _round_trip(svc, tmp_path)
    nc = _scalar(reloaded, "nCylinders")
    assert nc is not None
    assert nc.value == pytest.approx(8.0)


def test_scalar_edit_does_not_corrupt_adjacent_scalars(tmp_path: Path) -> None:
    tune = _load_tune()
    original_ncyl = float(_scalar(tune, "nCylinders").value)
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "9.0")
    reloaded = _round_trip(svc, tmp_path)
    assert float(_scalar(reloaded, "nCylinders").value) == pytest.approx(original_ncyl)


# ---------------------------------------------------------------------------
# Table edit round-trips
# ---------------------------------------------------------------------------

def test_table_cell_edit_round_trip_ve_table(tmp_path: Path) -> None:
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


def test_table_cell_edit_preserves_rest_of_ve_table(tmp_path: Path) -> None:
    tune = _load_tune()
    ve_original = _table(tune, "veTable")
    svc = _edit_service(tune)
    svc.stage_list_cell("veTable", 0, "99.0")
    reloaded = _round_trip(svc, tmp_path)
    ve_reloaded = _table(reloaded, "veTable")
    for i in range(1, len(ve_original.value)):
        assert ve_reloaded.value[i] == pytest.approx(ve_original.value[i], abs=0.5), (
            f"veTable[{i}] changed: {ve_original.value[i]} → {ve_reloaded.value[i]}"
        )


# ---------------------------------------------------------------------------
# lastOffset-derived table preservation
# ---------------------------------------------------------------------------

def test_lambda_table_preserved_after_scalar_edit(tmp_path: Path) -> None:
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
    """afrTable is at lastOffset after lambdaTable — must survive a scalar edit."""
    tune = _load_tune()
    original_afr = _table(tune, "afrTable").value[:]
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "8.5")
    reloaded = _round_trip(svc, tmp_path)
    reloaded_afr = _table(reloaded, "afrTable")
    assert reloaded_afr is not None
    for i, (orig, new) in enumerate(zip(original_afr, reloaded_afr.value)):
        assert new == pytest.approx(orig, abs=0.1), f"afrTable[{i}] changed: {orig} → {new}"


def test_afr_table_preserved_after_ve_edit(tmp_path: Path) -> None:
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
# Multi-edit in one pass
# ---------------------------------------------------------------------------

def test_multiple_scalar_and_table_edits_round_trip(tmp_path: Path) -> None:
    tune = _load_tune()
    svc = _edit_service(tune)
    svc.stage_scalar_value("reqFuel", "11.1")
    svc.stage_list_cell("veTable", 5, "42.0")
    reloaded = _round_trip(svc, tmp_path)
    assert _scalar(reloaded, "reqFuel").value == pytest.approx(11.1, abs=0.05)
    assert _table(reloaded, "veTable").value[5] == pytest.approx(42.0, abs=0.5)


def test_unedited_save_is_functionally_identical(tmp_path: Path) -> None:
    tune = _load_tune()
    svc = _edit_service(tune)
    reloaded = _round_trip(svc, tmp_path)
    original_req = _scalar(tune, "reqFuel").value
    assert _scalar(reloaded, "reqFuel").value == pytest.approx(original_req, abs=0.01)
    original_ve0 = _table(tune, "veTable").value[0]
    assert _table(reloaded, "veTable").value[0] == pytest.approx(original_ve0, abs=0.5)


# ---------------------------------------------------------------------------
# Output format sanity
# ---------------------------------------------------------------------------

def test_saved_msq_is_valid_xml(tmp_path: Path) -> None:
    from xml.etree import ElementTree as ET
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    dest = tmp_path / "out.msq"
    MsqWriteService().save(_MSQ, dest, svc)
    root = ET.parse(dest).getroot()
    assert root is not None


def test_saved_msq_preserves_xml_declaration(tmp_path: Path) -> None:
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    dest = tmp_path / "out.msq"
    MsqWriteService().save(_MSQ, dest, svc)
    assert dest.read_bytes().startswith(b"<?xml")


def test_saved_msq_preserves_production_signature(tmp_path: Path) -> None:
    svc = _edit_service()
    svc.stage_scalar_value("reqFuel", "9.0")
    reloaded = _round_trip(svc, tmp_path)
    assert reloaded.signature == _PRODUCTION_SIGNATURE
    assert reloaded.page_count == 15


# ---------------------------------------------------------------------------
# Ford300_TwinGT28_BaseStartup.msq — non-U16P2 production tune
# ---------------------------------------------------------------------------

def test_ford300_msq_loads_with_production_signature() -> None:
    tune = _load_tune(_FORD_MSQ)
    assert tune.signature == _PRODUCTION_SIGNATURE


def test_ford300_msq_page_count_matches_production_ini() -> None:
    defn = IniParser().parse(_INI)
    tune = _load_tune(_FORD_MSQ)
    assert tune.page_count == len(defn.page_sizes)


def test_ford300_msq_has_req_fuel() -> None:
    tune = _load_tune(_FORD_MSQ)
    req = _scalar(tune, "reqFuel")
    assert req is not None
    assert 0.0 < req.value < 30.0


def test_ford300_msq_ve_table_differs_from_base_tune() -> None:
    """Ford300 is a different engine tune — veTable should not match base-tune."""
    base = _load_tune(_MSQ)
    ford = _load_tune(_FORD_MSQ)
    base_ve = _table(base, "veTable").value
    ford_ve = _table(ford, "veTable").value
    diffs = sum(1 for a, b in zip(base_ve, ford_ve) if abs(a - b) > 0.5)
    # Ford 300 I6 vs generic base tune — expect substantial differences
    assert diffs > 50


def test_ford300_round_trip_preserves_ve_table(tmp_path: Path) -> None:
    """Ford300 MSQ must survive a no-op save/reload against the production INI."""
    tune = _load_tune(_FORD_MSQ)
    original_ve = _table(tune, "veTable").value[:]
    svc = LocalTuneEditService()
    svc.set_tune_file(tune)
    reloaded = _round_trip(svc, tmp_path, source=_FORD_MSQ, name="ford_out.msq")
    reloaded_ve = _table(reloaded, "veTable")
    assert reloaded_ve is not None
    for i, (orig, new) in enumerate(zip(original_ve, reloaded_ve.value)):
        assert new == pytest.approx(orig, abs=0.5), f"veTable[{i}]: {orig} → {new}"


def test_ford300_afr_table_preserved_on_round_trip(tmp_path: Path) -> None:
    """Ford300 afrTable (lastOffset-derived) must survive a scalar edit."""
    tune = _load_tune(_FORD_MSQ)
    original_afr = _table(tune, "afrTable").value[:]
    svc = LocalTuneEditService()
    svc.set_tune_file(tune)
    svc.stage_scalar_value("reqFuel", "8.5")
    reloaded = _round_trip(svc, tmp_path, source=_FORD_MSQ, name="ford_afr.msq")
    reloaded_afr = _table(reloaded, "afrTable")
    assert reloaded_afr is not None
    for i, (orig, new) in enumerate(zip(original_afr, reloaded_afr.value)):
        assert new == pytest.approx(orig, abs=0.1), f"afrTable[{i}]: {orig} → {new}"
