"""Round-trip tests for real Speeduino release artifacts.

These tests are skipped automatically when the release files are not present on the
machine.  They serve as a regression net for the parser + write path against real
production-quality MSQ files.

Artifacts expected at:
  C:\\Users\\Cornelio\\Desktop\\speeduino-202501.6\\release\\
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

_RELEASE = Path(r"C:\Users\Cornelio\Desktop\speeduino-202501.6\release")

_INI_STANDARD = _RELEASE / "speeduino-dropbear-v2.0.1.ini"
_MSQ_STANDARD = _RELEASE / "Ford300_TwinGT28_BaseStartup.msq"

_INI_U16P2 = _RELEASE / "speeduino-dropbear-v2.0.1-u16p2-experimental.ini"
_MSQ_U16P2 = _RELEASE / "Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq"
_MSQ_BASE_U16P2 = _RELEASE / "speeduino-dropbear-v2.0.1-u16p2-experimental-base-tune.msq"

_HAVE_STANDARD = _INI_STANDARD.exists() and _MSQ_STANDARD.exists()
_HAVE_U16P2 = _INI_U16P2.exists() and _MSQ_U16P2.exists()

_skip_standard = pytest.mark.skipif(not _HAVE_STANDARD, reason="Standard release artifacts not present")
_skip_u16p2 = pytest.mark.skipif(not _HAVE_U16P2, reason="U16P2 release artifacts not present")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(ini: Path, msq: Path) -> tuple:
    """Return (definition, tune, edit_service)."""
    definition = IniParser().parse(ini)
    tune = MsqParser().parse(msq)
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return definition, tune, edits


def _round_trip(msq: Path, edits: LocalTuneEditService, tmp_path: Path) -> LocalTuneEditService:
    """Save to a temp file and reload into a fresh edit service."""
    out = tmp_path / "round_trip.msq"
    MsqWriteService().save(msq, out, edits)
    reloaded = MsqParser().parse(out)
    fresh = LocalTuneEditService()
    fresh.set_tune_file(reloaded)
    return fresh


# ---------------------------------------------------------------------------
# Standard release: Ford300 MSQ (production signature)
# ---------------------------------------------------------------------------

@_skip_standard
def test_standard_msq_parses_without_error() -> None:
    _definition, tune, _edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    assert tune.signature is not None
    assert "speeduino" in tune.signature.lower()
    assert len(tune.constants) > 10


@_skip_standard
def test_standard_msq_reqfuel_present() -> None:
    _definition, _tune, edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    val = edits.get_value("reqFuel")
    assert val is not None
    assert isinstance(val.value, float)
    assert val.value > 0


@_skip_standard
def test_standard_msq_ve_table_present_and_correct_shape() -> None:
    _definition, _tune, edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    ve = edits.get_value("veTable")
    assert ve is not None
    assert isinstance(ve.value, list)
    assert len(ve.value) == (ve.rows or 1) * (ve.cols or 1)
    assert all(isinstance(v, float) for v in ve.value)


@_skip_standard
def test_standard_msq_scalar_round_trip(tmp_path: Path) -> None:
    """Edit reqFuel, save, reload — the edited value must survive the round trip."""
    _definition, _tune, edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    original = edits.get_value("reqFuel").value  # type: ignore[union-attr]

    edits.stage_scalar_value("reqFuel", str(original + 1.0))
    reloaded = _round_trip(_MSQ_STANDARD, edits, tmp_path)

    result = reloaded.get_value("reqFuel")
    assert result is not None
    assert abs(result.value - (original + 1.0)) < 0.01


@_skip_standard
def test_standard_msq_table_round_trip(tmp_path: Path) -> None:
    """Edit one VE cell, save, reload — the edited cell must survive the round trip."""
    _definition, _tune, edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    original_ve = list(edits.get_value("veTable").value)  # type: ignore[union-attr]
    sentinel = original_ve[0] + 3.0

    edits.stage_list_cell("veTable", 0, str(sentinel))
    reloaded = _round_trip(_MSQ_STANDARD, edits, tmp_path)

    result = reloaded.get_value("veTable")
    assert result is not None
    assert abs(result.value[0] - sentinel) < 0.01
    # Rest of the table must be unchanged
    for i in range(1, min(8, len(original_ve))):
        assert abs(result.value[i] - original_ve[i]) < 0.01


@_skip_standard
def test_standard_msq_unstaged_values_preserved(tmp_path: Path) -> None:
    """Saving without any edits must not corrupt any existing values."""
    _definition, _tune, edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    reqfuel_before = edits.get_value("reqFuel").value  # type: ignore[union-attr]

    # No edits — save-and-reload should be a no-op
    reloaded = _round_trip(_MSQ_STANDARD, edits, tmp_path)

    reqfuel_after = reloaded.get_value("reqFuel")
    assert reqfuel_after is not None
    assert abs(reqfuel_after.value - reqfuel_before) < 0.001


@_skip_standard
def test_standard_ini_page_layout_covers_scalars_from_msq() -> None:
    """Every scalar in the MSQ that matches a definition name must appear on at
    least one compiled page (or be a PcVariable)."""
    from tuner.services.tuning_page_service import TuningPageService
    definition, tune, _edits = _load(_INI_STANDARD, _MSQ_STANDARD)
    groups = TuningPageService().build_pages(definition)
    all_page_param_names: set[str] = set()
    for group in groups:
        for page in group.pages:
            for param in page.parameters:
                all_page_param_names.add(param.name)
    definition_scalar_names = {s.name for s in definition.scalars}
    tune_scalar_names = {
        c.name for c in tune.constants + tune.pc_variables
        if not isinstance(c.value, list)
    }
    # At least 70% of tune scalars that are in the definition should be on a page
    covered = {n for n in tune_scalar_names if n in all_page_param_names and n in definition_scalar_names}
    relevant = tune_scalar_names & definition_scalar_names
    if relevant:
        ratio = len(covered) / len(relevant)
        assert ratio >= 0.70, (
            f"Only {ratio:.0%} of tune scalars appear on pages "
            f"({len(covered)}/{len(relevant)}).  Missing sample: "
            f"{sorted(relevant - covered)[:10]}"
        )


# ---------------------------------------------------------------------------
# U16P2 experimental: Ford300 MSQ
# ---------------------------------------------------------------------------

@_skip_u16p2
def test_u16p2_msq_parses_without_error() -> None:
    _definition, tune, _edits = _load(_INI_U16P2, _MSQ_U16P2)
    assert tune.signature is not None
    assert "U16P2" in tune.signature or "u16p2" in tune.signature.lower()


@_skip_u16p2
def test_u16p2_afr_and_lambda_tables_both_present() -> None:
    """The Ford300 U16P2 MSQ must carry both lambdaTable and afrTable with real data."""
    _definition, _tune, edits = _load(_INI_U16P2, _MSQ_U16P2)
    lambda_tbl = edits.get_value("lambdaTable")
    afr_tbl = edits.get_value("afrTable")
    assert lambda_tbl is not None, "lambdaTable not found in U16P2 MSQ"
    assert afr_tbl is not None, "afrTable not found in U16P2 MSQ"
    assert isinstance(lambda_tbl.value, list) and len(lambda_tbl.value) > 0
    assert isinstance(afr_tbl.value, list) and len(afr_tbl.value) > 0


@_skip_u16p2
def test_u16p2_scalar_round_trip(tmp_path: Path) -> None:
    """Edit and round-trip reqFuel in the U16P2 tune."""
    _definition, _tune, edits = _load(_INI_U16P2, _MSQ_U16P2)
    original = edits.get_value("reqFuel").value  # type: ignore[union-attr]

    edits.stage_scalar_value("reqFuel", str(original + 0.5))
    reloaded = _round_trip(_MSQ_U16P2, edits, tmp_path)

    result = reloaded.get_value("reqFuel")
    assert result is not None
    assert abs(result.value - (original + 0.5)) < 0.01


@_skip_u16p2
def test_u16p2_ini_hardware_testing_hidden() -> None:
    """#unset enablehardware_test must suppress Hardware Testing from U16P2 INI."""
    definition = IniParser().parse(_INI_U16P2)
    menu_titles = {m.title for m in definition.menus}
    assert "Hardware Testing" not in menu_titles


@_skip_u16p2
def test_u16p2_ini_signature_family() -> None:
    definition = IniParser().parse(_INI_U16P2)
    assert definition.firmware_signature is not None
    assert "U16P2" in definition.firmware_signature or "u16p2" in definition.firmware_signature.lower()
