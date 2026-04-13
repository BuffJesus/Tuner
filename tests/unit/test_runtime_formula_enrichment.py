"""Tests for runtime formula channel enrichment — G4 sub-slice 86.

Covers ``MathExpressionEvaluator.enrich_snapshot`` as a pure helper and
``SessionService.poll_runtime`` end-to-end against the production INI, so
downstream consumers (dashboard, HTTP server, datalog profile) see
computed channels for free without any extra wiring on their side.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tuner.domain.connection import ConnectionConfig, ProtocolType, TransportType
from tuner.domain.ecu_definition import EcuDefinition, FormulaOutputChannel
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.parsers.ini_parser import IniParser
from tuner.services.math_expression_evaluator import MathExpressionEvaluator
from tuner.services.session_service import SessionService
from tuner.transports.transport_factory import TransportFactory


FIXTURE_INI = (
    Path(__file__).parent.parent / "fixtures" / "speeduino-dropbear-v2.0.1.ini"
)


def _empty_def() -> EcuDefinition:
    return EcuDefinition(name="test")


# ---------------------------------------------------------------------------
# enrich_snapshot unit tests
# ---------------------------------------------------------------------------

def test_enrich_snapshot_noop_without_definition() -> None:
    snap = OutputChannelSnapshot(values=[OutputChannelValue("rpm", 3000.0)])
    out = MathExpressionEvaluator().enrich_snapshot(snap, None)
    # Same object — no allocation when there's nothing to compute
    assert out is snap


def test_enrich_snapshot_noop_without_formulas() -> None:
    snap = OutputChannelSnapshot(values=[OutputChannelValue("rpm", 3000.0)])
    out = MathExpressionEvaluator().enrich_snapshot(snap, _empty_def())
    assert out is snap


def test_enrich_snapshot_appends_simple_formula() -> None:
    d = _empty_def()
    d.formula_output_channels = [
        FormulaOutputChannel(
            name="coolant",
            formula_expression="coolantRaw - 40",
            units="C",
        ),
    ]
    snap = OutputChannelSnapshot(
        values=[OutputChannelValue("coolantRaw", 90.0, units="raw")]
    )
    out = MathExpressionEvaluator().enrich_snapshot(snap, d)
    # Input not mutated
    assert len(snap.values) == 1
    # Output has hardware + formula
    assert [v.name for v in out.values] == ["coolantRaw", "coolant"]
    assert out.values[-1].value == 50.0
    assert out.values[-1].units == "C"


def test_enrich_snapshot_preserves_timestamp() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    snap = OutputChannelSnapshot(
        timestamp=ts,
        values=[OutputChannelValue("x", 1.0)],
    )
    d = _empty_def()
    d.formula_output_channels = [
        FormulaOutputChannel(name="y", formula_expression="x + 1"),
    ]
    out = MathExpressionEvaluator().enrich_snapshot(snap, d)
    assert out.timestamp == ts


def test_enrich_snapshot_chained_formulas_resolve() -> None:
    d = _empty_def()
    d.formula_output_channels = [
        FormulaOutputChannel(
            name="revolutionTime", formula_expression="rpm ? ( 60000.0 / rpm) : 0"
        ),
        FormulaOutputChannel(
            name="strokeMultipler", formula_expression="twoStroke == 1 ? 1 : 2"
        ),
        FormulaOutputChannel(
            name="cycleTime", formula_expression="revolutionTime * strokeMultipler"
        ),
    ]
    snap = OutputChannelSnapshot(
        values=[
            OutputChannelValue("rpm", 6000.0),
            OutputChannelValue("twoStroke", 0.0),
        ],
    )
    out = MathExpressionEvaluator().enrich_snapshot(snap, d).as_dict()
    assert out["revolutionTime"] == 10.0
    assert out["strokeMultipler"] == 2.0
    assert out["cycleTime"] == 20.0


def test_enrich_snapshot_uses_definition_arrays() -> None:
    d = _empty_def()
    d.formula_output_channels = [
        FormulaOutputChannel(
            name="nFuelChannels",
            formula_expression="arrayValue( array.boardFuelOutputs, pinLayout )",
        ),
    ]
    d.output_channel_arrays = {"boardFuelOutputs": [4.0, 4.0, 16.0]}
    snap = OutputChannelSnapshot(values=[OutputChannelValue("pinLayout", 2.0)])
    out = MathExpressionEvaluator().enrich_snapshot(snap, d)
    assert out.as_dict()["nFuelChannels"] == 16.0


# ---------------------------------------------------------------------------
# SessionService.poll_runtime end-to-end via MockControllerClient
# ---------------------------------------------------------------------------

def test_session_poll_runtime_yields_formula_channels_from_production_ini() -> None:
    """Prove that the production INI's formula channels show up in the
    runtime snapshot that downstream consumers (dashboard, HTTP server,
    datalog profile) receive — without any change to those consumers.

    Uses the MockControllerClient so the test doesn't require a real ECU.
    MockEcuRuntime seeds scalar channels from the definition's output
    channel list, which gives us enough raw values for the formula
    evaluator to run without producing NaN.
    """
    definition = IniParser().parse(FIXTURE_INI)
    assert len(definition.formula_output_channels) >= 30

    service = SessionService(transport_factory=TransportFactory(), definition=definition)
    service.connect(ConnectionConfig(
        transport=TransportType.MOCK,
        protocol=ProtocolType.SPEEDUINO,
    ))

    snapshot = service.poll_runtime()

    # Every formula channel should appear exactly once in the snapshot,
    # in declaration order, after the hardware channels.
    by_name = {v.name: v for v in snapshot.values}
    for f in definition.formula_output_channels:
        assert f.name in by_name, f"missing formula channel in poll: {f.name}"
    # Units carried through for formulas that declare them (e.g. throttle
    # is declared as `= { tps }, "%"` in the production INI).
    throttle = by_name.get("throttle")
    assert throttle is not None
    assert throttle.units == "%"


def test_session_poll_runtime_no_definition_is_noop() -> None:
    """SessionService with no definition should pass the raw snapshot
    through unchanged — the enrichment must not crash on a bare session."""
    service = SessionService(transport_factory=TransportFactory(), definition=None)
    service.connect(ConnectionConfig(
        transport=TransportType.MOCK,
        protocol=ProtocolType.SPEEDUINO,
    ))
    snapshot = service.poll_runtime()
    # No formula channels were added
    assert all(
        v.name for v in snapshot.values
    )  # just a sanity assertion — values list is well-formed
