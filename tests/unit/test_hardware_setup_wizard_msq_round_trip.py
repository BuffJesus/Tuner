"""End-to-end integration test for Phase 4 wizard → staged → MSQ write.

Covers the gap called out in the subsystem matrix:
  "Hardware setup wizard table generation: Implemented, unvalidated —
   Generator services well-tested; wizard wired. No end-to-end test:
   wizard input → staged → real MSQ write."

This test wires the real production INI/MSQ pair through the
HardwareSetupWizard, drives the VE-table generator from the wizard's
own button handler, then round-trips the staged result through
MsqWriteService and re-parses the saved file to confirm the staged
values land in the on-disk MSQ.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tuner.domain.generator_context import ForcedInductionTopology
from tuner.parsers.ini_parser import IniParser
from tuner.parsers.msq_parser import MsqParser
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.msq_write_service import MsqWriteService
from tuner.services.tuning_workspace_presenter import TuningWorkspacePresenter
from tuner.ui.hardware_setup_wizard import HardwareSetupWizard


_FIXTURES = Path(__file__).parent.parent / "fixtures"
_INI = _FIXTURES / "speeduino-dropbear-v2.0.1.ini"
_MSQ = _FIXTURES / "speeduino-dropbear-v2.0.1-base-tune.msq"


def _table(tune, name: str):
    return next(
        (c for c in tune.constants if c.name == name and isinstance(c.value, list)),
        None,
    )


def test_wizard_generate_ve_table_round_trips_through_msq_write(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])

    definition = IniParser().parse(_INI)
    tune_file = MsqParser().parse(_MSQ)

    edit_service = LocalTuneEditService()
    edit_service.set_tune_file(tune_file)
    presenter = TuningWorkspacePresenter(local_tune_edit_service=edit_service)
    presenter.load(definition, tune_file)

    wizard = HardwareSetupWizard(presenter)
    wizard.show()
    app.processEvents()

    # Push some operator context so the generator has non-default inputs
    presenter.update_operator_engine_context(
        forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO,
        boost_target_kpa=180.0,
    )

    ve_table_name = wizard._resolve_ve_table_name()
    base_table = _table(tune_file, ve_table_name)
    assert base_table is not None, f"production base tune missing {ve_table_name}"
    base_values = list(base_table.value)

    # Drive the actual wizard button handler.
    wizard._on_generate_ve_table()
    app.processEvents()

    staged = edit_service.get_value(ve_table_name)
    assert staged is not None, "wizard did not stage VE table"
    assert isinstance(staged.value, list)
    staged_values = list(staged.value)
    assert len(staged_values) == len(base_values)
    assert staged_values != base_values, (
        "generator produced an identity table — input context not flowing through"
    )

    # Round-trip through MsqWriteService and re-parse.
    dest = tmp_path / "wizard_round_trip.msq"
    MsqWriteService().save(_MSQ, dest, edit_service)
    reparsed = MsqParser().parse(dest)

    saved_table = _table(reparsed, ve_table_name)
    assert saved_table is not None, f"saved MSQ lost {ve_table_name}"
    assert list(saved_table.value) == staged_values, (
        "MSQ round-trip did not preserve wizard-staged VE values"
    )

    wizard.deleteLater()
