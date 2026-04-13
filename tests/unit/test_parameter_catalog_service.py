from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition, TableDefinition
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.parameter_catalog_service import ParameterCatalogService


def test_build_catalog_merges_definition_and_tune_values() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="reqFuel", data_type="U08", page=1, offset=24, units="ms")],
        tables=[TableDefinition(name="veTable", rows=16, columns=16, page=1, offset=0, units="%")],
    )
    tune_file = TuneFile(
        constants=[
            TuneValue(name="reqFuel", value=9.1, units="ms"),
            TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0, 50.0], units="%", rows=5, cols=1),
        ]
    )

    entries = ParameterCatalogService().build_catalog(definition, tune_file)

    assert len(entries) == 2
    assert entries[0].name == "veTable"
    assert entries[0].tune_present is True
    assert "5 values" in entries[0].tune_preview
    assert entries[1].name == "reqFuel"
    assert entries[1].tune_preview == "9.1"


def test_filter_catalog_matches_name_and_units() -> None:
    entries = [
        ParameterCatalogService()._scalar_entry(
            ScalarParameterDefinition(name="reqFuel", data_type="U08", units="ms"),
            None,
        ),
        ParameterCatalogService()._table_entry(
            TableDefinition(name="veTable", rows=16, columns=16, units="%"),
            None,
        ),
    ]

    filtered = ParameterCatalogService.filter_catalog(entries, "ms")

    assert [entry.name for entry in filtered] == ["reqFuel"]


def test_build_catalog_works_with_tune_only() -> None:
    tune_file = TuneFile(
        constants=[TuneValue(name="reqFuel", value=9.1, units="ms")],
        pc_variables=[TuneValue(name="status1", value="ok")],
    )

    entries = ParameterCatalogService().build_catalog(None, tune_file)

    assert [entry.name for entry in entries] == ["reqFuel", "status1"]
    assert all(entry.tune_present for entry in entries)


def test_build_catalog_prefers_staged_values_for_preview() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        tables=[TableDefinition(name="veTable", rows=2, columns=2, page=1, offset=0, units="%")],
    )
    tune_file = TuneFile(constants=[TuneValue(name="veTable", value=[10.0, 20.0, 30.0, 40.0], rows=2, cols=2)])

    entries = ParameterCatalogService().build_catalog(
        definition,
        tune_file,
        staged_values={"veTable": TuneValue(name="veTable", value=[10.0, 55.0, 30.0, 40.0], rows=2, cols=2)},
    )

    assert entries[0].tune_preview.startswith("10.0, 55.0")


def test_build_catalog_keeps_unpaged_definition_artifacts_visible_for_debug() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[ScalarParameterDefinition(name="idleUnits", data_type="U08")],
        tables=[TableDefinition(name="boardHasSD", rows=1, columns=1, data_type="U16")],
    )

    entries = ParameterCatalogService().build_catalog(definition, None)

    assert [entry.name for entry in entries] == ["boardHasSD", "idleUnits"]
    assert all(entry.page is None for entry in entries)
    assert all(entry.tune_present is False for entry in entries)
