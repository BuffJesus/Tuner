"""Tests for the v1 owned tune/definition contract (Future Phase 12)."""
from __future__ import annotations

import json

import pytest

from tuner.domain.ecu_definition import (
    EcuDefinition,
    FieldOptionDefinition,
    ScalarParameterDefinition,
    TableDefinition,
)
from tuner.domain.native_format import (
    NATIVE_SCHEMA_VERSION,
    NativeAxis,
    NativeDefinition,
    NativeParameter,
    NativeTable,
    NativeTune,
)
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.native_format_service import (
    NativeFormatService,
    NativeFormatVersionError,
)


# ---------------------------------------------------------------------------
# from_ecu_definition — legacy → native projection
# ---------------------------------------------------------------------------

class TestFromEcuDefinition:
    def _legacy(self) -> EcuDefinition:
        return EcuDefinition(
            name="speeduino 202501-T41",
            firmware_signature="speeduino 202501-T41",
            scalars=[
                ScalarParameterDefinition(
                    name="reqFuel", data_type="U16",
                    label="Required fuel", units="ms",
                    min_value=0.0, max_value=20.0,
                ),
                ScalarParameterDefinition(
                    name="injLayout", data_type="U08",
                    options=(
                        FieldOptionDefinition("0", "Paired"),
                        FieldOptionDefinition("1", "Sequential"),
                    ),
                ),
            ],
            tables=[
                TableDefinition(
                    name="veTable", rows=16, columns=16,
                    label="VE Table", units="%",
                ),
                TableDefinition(
                    name="rpmBins", rows=1, columns=16, units="rpm",
                ),
                TableDefinition(
                    name="loadBins", rows=16, columns=1, units="kPa",
                ),
            ],
        )

    def test_definition_metadata_carried_over(self) -> None:
        native = NativeFormatService().from_ecu_definition(self._legacy())
        assert native.name == "speeduino 202501-T41"
        assert native.firmware_signature == "speeduino 202501-T41"
        assert native.schema_version == NATIVE_SCHEMA_VERSION

    def test_scalar_parameters_projected(self) -> None:
        native = NativeFormatService().from_ecu_definition(self._legacy())
        names = {p.semantic_id: p for p in native.parameters}
        assert "reqFuel" in names
        assert names["reqFuel"].units == "ms"
        assert names["reqFuel"].min_value == 0.0
        assert names["reqFuel"].max_value == 20.0
        assert names["reqFuel"].kind == "scalar"
        assert names["injLayout"].kind == "enum"

    def test_axis_shaped_tables_become_axes(self) -> None:
        native = NativeFormatService().from_ecu_definition(self._legacy())
        axis_ids = {a.semantic_id for a in native.axes}
        assert "rpmBins" in axis_ids
        assert "loadBins" in axis_ids
        # The actual VE table is NOT an axis
        assert "veTable" not in axis_ids
        rpm_axis = next(a for a in native.axes if a.semantic_id == "rpmBins")
        assert rpm_axis.length == 16
        assert rpm_axis.units == "rpm"

    def test_data_tables_kept_separate_from_axes(self) -> None:
        native = NativeFormatService().from_ecu_definition(self._legacy())
        table_ids = {t.semantic_id for t in native.tables}
        assert table_ids == {"veTable"}
        ve = native.tables[0]
        assert ve.rows == 16
        assert ve.columns == 16
        assert ve.units == "%"

    def test_v1_uses_legacy_name_as_semantic_id(self) -> None:
        native = NativeFormatService().from_ecu_definition(self._legacy())
        for parameter in native.parameters:
            assert parameter.semantic_id == parameter.legacy_name


# ---------------------------------------------------------------------------
# from_tune_file — legacy → native tune
# ---------------------------------------------------------------------------

class TestFromTuneFile:
    def _native(self) -> NativeDefinition:
        return NativeDefinition(
            schema_version=NATIVE_SCHEMA_VERSION,
            name="x", firmware_signature="speeduino 202501-T41",
            parameters=[
                NativeParameter(
                    semantic_id="reqFuel", legacy_name="reqFuel", units="ms",
                ),
            ],
            tables=[
                NativeTable(
                    semantic_id="veTable", legacy_name="veTable",
                    rows=2, columns=2, units="%",
                ),
            ],
            axes=[
                NativeAxis(semantic_id="rpmBins", legacy_name="rpmBins", length=2),
            ],
        )

    def test_scalars_and_lists_carried_over(self) -> None:
        tune = TuneFile(
            constants=[
                TuneValue(name="reqFuel", value=8.5, units="ms"),
                TuneValue(name="veTable", value=[50.0, 55.0, 60.0, 65.0],
                          rows=2, cols=2, units="%"),
            ],
        )
        native_tune = NativeFormatService().from_tune_file(tune, self._native())
        assert native_tune.values["reqFuel"] == 8.5
        assert native_tune.values["veTable"] == [50.0, 55.0, 60.0, 65.0]

    def test_legacy_only_values_pass_through_under_legacy_name(self) -> None:
        tune = TuneFile(
            constants=[
                TuneValue(name="reqFuel", value=8.5, units="ms"),
                # Not in the native definition — should still survive
                TuneValue(name="customScalar", value=42.0),
            ],
        )
        native_tune = NativeFormatService().from_tune_file(tune, self._native())
        assert native_tune.values["customScalar"] == 42.0

    def test_definition_signature_inherited(self) -> None:
        tune = TuneFile(constants=[], signature="speeduino 202501-T41")
        native_tune = NativeFormatService().from_tune_file(tune, self._native())
        assert native_tune.definition_signature == "speeduino 202501-T41"


# ---------------------------------------------------------------------------
# JSON round trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_definition_round_trip_preserves_fields(self) -> None:
        svc = NativeFormatService()
        original = NativeDefinition(
            schema_version=NATIVE_SCHEMA_VERSION,
            name="speeduino", firmware_signature="speeduino 202501-T41",
            parameters=[
                NativeParameter(
                    semantic_id="reqFuel", legacy_name="reqFuel",
                    label="Required fuel", units="ms",
                    min_value=0.0, max_value=20.0,
                ),
            ],
            axes=[
                NativeAxis(
                    semantic_id="rpmBins", legacy_name="rpmBins",
                    length=16, units="rpm",
                ),
            ],
            tables=[
                NativeTable(
                    semantic_id="veTable", legacy_name="veTable",
                    rows=16, columns=16, units="%",
                ),
            ],
        )
        text = svc.dump_definition(original)
        # Round-trip is structural — load + re-dump must equal first dump
        reloaded = svc.load_definition(text)
        assert svc.dump_definition(reloaded) == text

    def test_tune_round_trip_preserves_values(self) -> None:
        svc = NativeFormatService()
        original = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={
                "reqFuel": 8.5,
                "veTable": [50.0, 55.0, 60.0, 65.0],
                "label": "shop tune",
            },
        )
        text = svc.dump_tune(original)
        reloaded = svc.load_tune(text)
        assert reloaded.definition_signature == original.definition_signature
        assert reloaded.values == original.values

    def test_dump_emits_schema_version(self) -> None:
        svc = NativeFormatService()
        text = svc.dump_definition(NativeDefinition())
        data = json.loads(text)
        assert data["schema_version"] == NATIVE_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Schema version gating
# ---------------------------------------------------------------------------

class TestSchemaVersionGating:
    def test_missing_version_raises(self) -> None:
        with pytest.raises(NativeFormatVersionError, match="missing"):
            NativeFormatService().load_definition('{"name": "x"}')

    def test_future_major_version_raises(self) -> None:
        future = '{"schema_version": "9.0", "name": "x"}'
        with pytest.raises(NativeFormatVersionError, match="newer"):
            NativeFormatService().load_definition(future)

    def test_minor_bump_is_forward_compatible(self) -> None:
        text = '{"schema_version": "1.5", "name": "x"}'
        defn = NativeFormatService().load_definition(text)
        assert defn.name == "x"
        assert defn.schema_version == "1.5"

    def test_unparsable_version_raises(self) -> None:
        text = '{"schema_version": "abc", "name": "x"}'
        with pytest.raises(NativeFormatVersionError, match="unparsable"):
            NativeFormatService().load_definition(text)

    def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid native JSON"):
            NativeFormatService().load_definition("{not json")

    def test_root_must_be_object(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            NativeFormatService().load_definition("[]")


# ---------------------------------------------------------------------------
# End-to-end legacy → native → JSON
# ---------------------------------------------------------------------------

class TestToTuneFile:
    """Future Phase 12 deliverable 3 reverse path: NativeTune → TuneFile."""

    def _native(self) -> NativeDefinition:
        return NativeDefinition(
            schema_version=NATIVE_SCHEMA_VERSION,
            name="x", firmware_signature="speeduino 202501-T41",
            parameters=[
                NativeParameter(
                    semantic_id="reqFuel", legacy_name="reqFuel",
                    units="ms",
                ),
            ],
            tables=[
                NativeTable(
                    semantic_id="veTable", legacy_name="veTable",
                    rows=2, columns=2, units="%",
                ),
            ],
            axes=[
                NativeAxis(
                    semantic_id="rpmBins", legacy_name="rpmBins",
                    length=2, units="rpm",
                ),
            ],
        )

    def test_scalar_projects_to_tune_value_with_units(self) -> None:
        svc = NativeFormatService()
        tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={"reqFuel": 8.5},
        )
        result = svc.to_tune_file(tune, self._native())
        req = next(c for c in result.constants if c.name == "reqFuel")
        assert req.value == 8.5
        assert req.units == "ms"
        assert result.signature == "speeduino 202501-T41"

    def test_table_projects_with_rows_cols_units(self) -> None:
        svc = NativeFormatService()
        tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="x",
            values={"veTable": [50.0, 55.0, 60.0, 65.0]},
        )
        result = svc.to_tune_file(tune, self._native())
        ve = next(c for c in result.constants if c.name == "veTable")
        assert ve.value == [50.0, 55.0, 60.0, 65.0]
        assert ve.rows == 2
        assert ve.cols == 2
        assert ve.units == "%"

    def test_axis_projects_with_length_as_cols(self) -> None:
        svc = NativeFormatService()
        tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="x",
            values={"rpmBins": [500.0, 1500.0]},
        )
        result = svc.to_tune_file(tune, self._native())
        rpm = next(c for c in result.constants if c.name == "rpmBins")
        assert rpm.value == [500.0, 1500.0]
        assert rpm.rows == 1
        assert rpm.cols == 2
        assert rpm.units == "rpm"

    def test_legacy_only_value_passes_through(self) -> None:
        svc = NativeFormatService()
        tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="x",
            values={"customScalar": 42.0, "customList": [1.0, 2.0, 3.0]},
        )
        result = svc.to_tune_file(tune, self._native())
        scalar = next(c for c in result.constants if c.name == "customScalar")
        assert scalar.value == 42.0
        assert scalar.units is None
        # Lists with no native shape default to 1×N
        lst = next(c for c in result.constants if c.name == "customList")
        assert lst.rows == 1
        assert lst.cols == 3

    def test_round_trip_native_to_legacy_to_native(self) -> None:
        svc = NativeFormatService()
        original = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={
                "reqFuel": 8.5,
                "veTable": [50.0, 55.0, 60.0, 65.0],
                "rpmBins": [500.0, 1500.0],
            },
        )
        native = self._native()
        legacy = svc.to_tune_file(original, native)
        reprojected = svc.from_tune_file(legacy, native)
        assert reprojected.values == original.values
        assert reprojected.definition_signature == original.definition_signature


class TestNativeToMsqWrite:
    """Prove the native format can drive an actual MSQ write through the
    existing ``MsqWriteService`` — the whole point of the reverse path."""

    def test_native_tune_writes_to_msq_via_existing_service(self, tmp_path) -> None:
        from pathlib import Path
        import textwrap
        from tuner.parsers.msq_parser import MsqParser
        from tuner.services.local_tune_edit_service import LocalTuneEditService
        from tuner.services.msq_write_service import MsqWriteService

        # Minimal source MSQ with a zero-filled veTable so the write
        # service has a node to update — exercises the round trip
        # without needing the full insert_missing flag.
        zeros = " ".join(["0"] * 2)
        body = textwrap.dedent(f"""\
            <?xml version="1.0" encoding="ISO-8859-1"?>
            <msq xmlns="http://www.msefi.com/:msq">
              <versionInfo signature="speeduino 202501-T41" fileFormat="2" nPages="1"/>
              <page number="1">
                <constant name="reqFuel" units="ms" digits="1">8.5</constant>
                <constant name="veTable" units="%" rows="2" cols="2" digits="1">
                    {zeros}
                    {zeros}
                </constant>
              </page>
            </msq>
            """)
        msq_path = tmp_path / "source.msq"
        msq_path.write_text(body, encoding="ISO-8859-1")

        # Build the native model directly (no INI parse needed for the test)
        native = NativeDefinition(
            schema_version=NATIVE_SCHEMA_VERSION,
            firmware_signature="speeduino 202501-T41",
            parameters=[
                NativeParameter(
                    semantic_id="reqFuel", legacy_name="reqFuel", units="ms",
                ),
            ],
            tables=[
                NativeTable(
                    semantic_id="veTable", legacy_name="veTable",
                    rows=2, columns=2, units="%",
                ),
            ],
        )
        native_tune = NativeTune(
            schema_version=NATIVE_SCHEMA_VERSION,
            definition_signature="speeduino 202501-T41",
            values={
                "reqFuel": 9.5,
                "veTable": [60.0, 65.0, 70.0, 75.0],
            },
        )

        # Native → legacy → MSQ write → re-parse
        legacy_tune = NativeFormatService().to_tune_file(native_tune, native)
        edit = LocalTuneEditService()
        edit.set_tune_file(legacy_tune)
        out = tmp_path / "out.msq"
        MsqWriteService().save(msq_path, out, edit)
        reloaded = MsqParser().parse(out)

        ve = next(c for c in reloaded.constants if c.name == "veTable")
        assert ve.value == [60.0, 65.0, 70.0, 75.0]
        req = next(c for c in reloaded.constants if c.name == "reqFuel")
        assert req.value == 9.5


class TestEndToEnd:
    def test_legacy_to_native_to_json_to_native(self) -> None:
        legacy = EcuDefinition(
            name="speeduino 202501-T41",
            firmware_signature="speeduino 202501-T41",
            scalars=[
                ScalarParameterDefinition(
                    name="reqFuel", data_type="U16", units="ms",
                ),
            ],
            tables=[
                TableDefinition(name="veTable", rows=2, columns=2, units="%"),
                TableDefinition(name="rpmBins", rows=1, columns=2, units="rpm"),
            ],
        )
        svc = NativeFormatService()
        native = svc.from_ecu_definition(legacy)
        text = svc.dump_definition(native)
        reloaded = svc.load_definition(text)
        assert reloaded.name == "speeduino 202501-T41"
        assert {p.semantic_id for p in reloaded.parameters} == {"reqFuel"}
        assert {a.semantic_id for a in reloaded.axes} == {"rpmBins"}
        assert {t.semantic_id for t in reloaded.tables} == {"veTable"}
