from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.sync_state import SyncMismatchKind
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.sync_state_service import SyncStateService


def _service() -> SyncStateService:
    return SyncStateService()


def test_no_mismatches_when_signatures_match() -> None:
    definition = EcuDefinition(name="Speedy", firmware_signature="speeduino-202501")
    tune_file = TuneFile(signature="speeduino-202501")
    state = _service().build(definition, tune_file, None, False, "offline")
    assert state.is_clean


def test_signature_mismatch_detected() -> None:
    definition = EcuDefinition(name="Speedy", firmware_signature="speeduino-202501")
    tune_file = TuneFile(signature="speeduino-202412")
    state = _service().build(definition, tune_file, None, False, "offline")
    assert not state.is_clean
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.SIGNATURE_MISMATCH in kinds


def test_signature_mismatch_detail_contains_both_signatures() -> None:
    definition = EcuDefinition(name="Speedy", firmware_signature="sig-A")
    tune_file = TuneFile(signature="sig-B")
    state = _service().build(definition, tune_file, None, False, "offline")
    detail = next(m.detail for m in state.mismatches if m.kind == SyncMismatchKind.SIGNATURE_MISMATCH)
    assert "sig-A" in detail
    assert "sig-B" in detail


def test_no_signature_mismatch_when_either_is_none() -> None:
    definition = EcuDefinition(name="Speedy", firmware_signature=None)
    tune_file = TuneFile(signature="speeduino-202501")
    state = _service().build(definition, tune_file, None, False, "offline")
    assert state.is_clean


def test_ecu_vs_tune_mismatch_detected() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    ecu_ram = {"reqFuel": 9.0}
    state = _service().build(None, tune_file, ecu_ram, False, "connected")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.ECU_VS_TUNE in kinds


def test_no_ecu_vs_tune_mismatch_when_values_match() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    ecu_ram = {"reqFuel": 8.5}
    state = _service().build(None, tune_file, ecu_ram, False, "connected")
    assert state.is_clean


def test_ecu_vs_tune_detail_names_differing_parameter() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    ecu_ram = {"reqFuel": 9.0}
    state = _service().build(None, tune_file, ecu_ram, False, "connected")
    detail = next(m.detail for m in state.mismatches if m.kind == SyncMismatchKind.ECU_VS_TUNE)
    assert "reqFuel" in detail


def test_ecu_vs_tune_ignores_unknown_ecu_parameters() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    ecu_ram = {"unknownParam": 42.0}
    state = _service().build(None, tune_file, ecu_ram, False, "connected")
    assert state.is_clean


def test_stale_staged_detected_when_staged_and_no_ecu_ram() -> None:
    state = _service().build(None, None, None, True, "offline")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.STALE_STAGED in kinds


def test_no_stale_staged_when_ecu_ram_present() -> None:
    tune_file = TuneFile(constants=[TuneValue(name="reqFuel", value=8.5)])
    ecu_ram = {"reqFuel": 8.5}
    state = _service().build(None, tune_file, ecu_ram, True, "connected")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.STALE_STAGED not in kinds


def test_has_ecu_ram_flag() -> None:
    state_without = _service().build(None, None, None, False, "offline")
    state_with = _service().build(None, None, {}, False, "connected")
    assert not state_without.has_ecu_ram
    assert state_with.has_ecu_ram


def test_connection_state_preserved_in_snapshot() -> None:
    state = _service().build(None, None, None, False, "connected")
    assert state.connection_state == "connected"


def test_page_size_mismatch_detected() -> None:
    definition = EcuDefinition(name="Speedy", page_sizes=[128, 64])
    tune_file = TuneFile(page_count=3)
    state = _service().build(definition, tune_file, None, False, "offline")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.PAGE_SIZE_MISMATCH in kinds


def test_page_size_mismatch_detail_contains_counts() -> None:
    definition = EcuDefinition(name="Speedy", page_sizes=[128, 64])
    tune_file = TuneFile(page_count=3)
    state = _service().build(definition, tune_file, None, False, "offline")
    detail = next(m.detail for m in state.mismatches if m.kind == SyncMismatchKind.PAGE_SIZE_MISMATCH)
    assert "2" in detail
    assert "3" in detail


def test_no_page_size_mismatch_when_counts_match() -> None:
    definition = EcuDefinition(name="Speedy", page_sizes=[128, 64])
    tune_file = TuneFile(page_count=2)
    state = _service().build(definition, tune_file, None, False, "offline")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.PAGE_SIZE_MISMATCH not in kinds


def test_no_page_size_mismatch_when_definition_has_no_page_sizes() -> None:
    definition = EcuDefinition(name="Speedy", page_sizes=[])
    tune_file = TuneFile(page_count=3)
    state = _service().build(definition, tune_file, None, False, "offline")
    assert state.is_clean


def test_no_page_size_mismatch_when_tune_page_count_is_none() -> None:
    definition = EcuDefinition(name="Speedy", page_sizes=[128, 64])
    tune_file = TuneFile(page_count=None)
    state = _service().build(definition, tune_file, None, False, "offline")
    kinds = {m.kind for m in state.mismatches}
    assert SyncMismatchKind.PAGE_SIZE_MISMATCH not in kinds
