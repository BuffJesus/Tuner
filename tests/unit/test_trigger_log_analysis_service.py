from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition, ScalarParameterDefinition
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.trigger_log_analysis_service import TriggerLogAnalysisService


def _edit_service(tune_file: TuneFile) -> LocalTuneEditService:
    service = LocalTuneEditService()
    service.set_tune_file(tune_file)
    return service


def test_analyze_rows_warns_when_missing_tooth_gap_is_not_visible() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="nTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="nTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=1.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "tooth": "1"},
            {"timeMs": "1.0", "tooth": "1"},
            {"timeMs": "2.0", "tooth": "1"},
            {"timeMs": "3.0", "tooth": "1"},
            {"timeMs": "4.0", "tooth": "1"},
            {"timeMs": "5.0", "tooth": "1"},
        ],
        columns=("timeMs", "tooth"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=None,
    )

    assert summary.log_kind == "tooth"
    assert summary.severity == "warning"
    assert any("missing-tooth gap" in finding.lower() for finding in summary.findings)


def test_analyze_rows_warns_when_sequential_context_is_crank_only() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="sparkMode", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=16.0),
                TuneValue(name="sparkMode", value=3.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[{"timeMs": "0.0", "triggerA": "0"}, {"timeMs": "4.0", "triggerA": "1"}] * 16,
        columns=("timeMs", "triggerA"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=OutputChannelSnapshot(values=[OutputChannelValue(name="rSA_fullSync", value=0.0)]),
    )

    assert summary.severity == "warning"
    assert "crank-only" in summary.decoder_summary_text.lower()
    assert any("sequential fuel or ignition is requested" in finding.lower() for finding in summary.findings)
    assert any("full sync is not present" in finding.lower() for finding in summary.findings)


def test_analyze_rows_summarizes_cam_optional_context_for_tooth_logs() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="sparkMode", data_type="U08"),
            ScalarParameterDefinition(name="nTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=3.0),
                TuneValue(name="nTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=1.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "tooth": "1"},
            {"timeMs": "1.0", "tooth": "1"},
            {"timeMs": "2.0", "tooth": "1"},
            {"timeMs": "3.8", "tooth": "1"},
            {"timeMs": "4.8", "tooth": "1"},
            {"timeMs": "5.8", "tooth": "1"},
            {"timeMs": "6.8", "tooth": "1"},
            {"timeMs": "7.8", "tooth": "1"},
            {"timeMs": "8.8", "tooth": "1"},
            {"timeMs": "9.8", "tooth": "1"},
            {"timeMs": "10.8", "tooth": "1"},
            {"timeMs": "11.8", "tooth": "1"},
            {"timeMs": "12.8", "tooth": "1"},
            {"timeMs": "13.8", "tooth": "1"},
            {"timeMs": "14.8", "tooth": "1"},
            {"timeMs": "15.8", "tooth": "1"},
            {"timeMs": "16.8", "tooth": "1"},
            {"timeMs": "17.8", "tooth": "1"},
            {"timeMs": "18.8", "tooth": "1"},
            {"timeMs": "19.8", "tooth": "1"},
        ],
        columns=("timeMs", "tooth"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=OutputChannelSnapshot(values=[OutputChannelValue(name="rSA_fullSync", value=1.0)]),
    )

    assert summary.severity in {"info", "warning"}
    assert "cam sync is configurable" in summary.decoder_summary_text.lower()
    assert any("tooth log may miss phase errors" in finding.lower() for finding in summary.findings)


def test_analyze_rows_reports_plausible_missing_tooth_gap_for_loaded_wheel() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="nTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="nTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=1.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "tooth": "1"},
            {"timeMs": "1.0", "tooth": "1"},
            {"timeMs": "2.0", "tooth": "1"},
            {"timeMs": "4.0", "tooth": "1"},
            {"timeMs": "5.0", "tooth": "1"},
            {"timeMs": "6.0", "tooth": "1"},
            {"timeMs": "7.0", "tooth": "1"},
            {"timeMs": "8.0", "tooth": "1"},
            {"timeMs": "9.0", "tooth": "1"},
            {"timeMs": "10.0", "tooth": "1"},
            {"timeMs": "11.0", "tooth": "1"},
            {"timeMs": "12.0", "tooth": "1"},
            {"timeMs": "13.0", "tooth": "1"},
            {"timeMs": "14.0", "tooth": "1"},
            {"timeMs": "15.0", "tooth": "1"},
            {"timeMs": "16.0", "tooth": "1"},
            {"timeMs": "17.0", "tooth": "1"},
            {"timeMs": "18.0", "tooth": "1"},
            {"timeMs": "19.0", "tooth": "1"},
            {"timeMs": "20.0", "tooth": "1"},
        ],
        columns=("timeMs", "tooth"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=None,
    )

    assert any("looks plausible for the loaded wheel" in finding.lower() for finding in summary.findings)
    assert summary.severity in {"info", "warning"}


def test_analyze_rows_warns_when_missing_tooth_gap_ratio_disagrees_with_loaded_wheel() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="nTeeth", data_type="U08"),
            ScalarParameterDefinition(name="missingTeeth", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="nTeeth", value=36.0),
                TuneValue(name="missingTeeth", value=2.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "tooth": "1"},
            {"timeMs": "1.0", "tooth": "1"},
            {"timeMs": "2.0", "tooth": "1"},
            {"timeMs": "4.0", "tooth": "1"},
            {"timeMs": "5.0", "tooth": "1"},
            {"timeMs": "6.0", "tooth": "1"},
            {"timeMs": "7.0", "tooth": "1"},
            {"timeMs": "8.0", "tooth": "1"},
            {"timeMs": "9.0", "tooth": "1"},
            {"timeMs": "10.0", "tooth": "1"},
            {"timeMs": "11.0", "tooth": "1"},
            {"timeMs": "12.0", "tooth": "1"},
            {"timeMs": "13.0", "tooth": "1"},
            {"timeMs": "14.0", "tooth": "1"},
            {"timeMs": "15.0", "tooth": "1"},
            {"timeMs": "16.0", "tooth": "1"},
            {"timeMs": "17.0", "tooth": "1"},
            {"timeMs": "18.0", "tooth": "1"},
            {"timeMs": "19.0", "tooth": "1"},
            {"timeMs": "20.0", "tooth": "1"},
        ],
        columns=("timeMs", "tooth"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=None,
    )

    assert summary.severity == "warning"
    assert any("does not match the loaded wheel well" in finding.lower() for finding in summary.findings)


def test_analyze_rows_reports_plausible_crank_cam_edge_density_for_trigger_log() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="sparkMode", data_type="U08"),
            ScalarParameterDefinition(name="trigPatternSec", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=3.0),
                TuneValue(name="trigPatternSec", value=0.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "crank": "0", "cam": "0"},
            {"timeMs": "1.0", "crank": "1", "cam": "0"},
            {"timeMs": "2.0", "crank": "0", "cam": "0"},
            {"timeMs": "3.0", "crank": "1", "cam": "0"},
            {"timeMs": "4.0", "crank": "0", "cam": "1"},
            {"timeMs": "5.0", "crank": "1", "cam": "1"},
            {"timeMs": "6.0", "crank": "0", "cam": "1"},
            {"timeMs": "7.0", "crank": "1", "cam": "1"},
            {"timeMs": "8.0", "crank": "0", "cam": "0"},
            {"timeMs": "9.0", "crank": "1", "cam": "0"},
            {"timeMs": "10.0", "crank": "0", "cam": "0"},
            {"timeMs": "11.0", "crank": "1", "cam": "0"},
            {"timeMs": "12.0", "crank": "0", "cam": "1"},
            {"timeMs": "13.0", "crank": "1", "cam": "1"},
            {"timeMs": "14.0", "crank": "0", "cam": "1"},
            {"timeMs": "15.0", "crank": "1", "cam": "1"},
            {"timeMs": "16.0", "crank": "0", "cam": "0"},
            {"timeMs": "17.0", "crank": "1", "cam": "0"},
            {"timeMs": "18.0", "crank": "0", "cam": "0"},
            {"timeMs": "19.0", "crank": "1", "cam": "0"},
        ],
        columns=("timeMs", "crank", "cam"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=OutputChannelSnapshot(values=[OutputChannelValue(name="rSA_fullSync", value=1.0)]),
    )

    assert any("edge density looks plausible" in finding.lower() for finding in summary.findings)


def test_analyze_rows_warns_when_trigger_log_lacks_cam_channel_for_sequential_context() -> None:
    definition = EcuDefinition(
        name="Speeduino",
        scalars=[
            ScalarParameterDefinition(name="TrigPattern", data_type="U08"),
            ScalarParameterDefinition(name="sparkMode", data_type="U08"),
            ScalarParameterDefinition(name="trigPatternSec", data_type="U08"),
        ],
    )
    edits = _edit_service(
        TuneFile(
            constants=[
                TuneValue(name="TrigPattern", value=0.0),
                TuneValue(name="sparkMode", value=3.0),
                TuneValue(name="trigPatternSec", value=0.0),
            ]
        )
    )

    summary = TriggerLogAnalysisService().analyze_rows(
        rows=[
            {"timeMs": "0.0", "crank": "0"},
            {"timeMs": "1.0", "crank": "1"},
            {"timeMs": "2.0", "crank": "0"},
            {"timeMs": "3.0", "crank": "1"},
            {"timeMs": "4.0", "crank": "0"},
            {"timeMs": "5.0", "crank": "1"},
            {"timeMs": "6.0", "crank": "0"},
            {"timeMs": "7.0", "crank": "1"},
            {"timeMs": "8.0", "crank": "0"},
            {"timeMs": "9.0", "crank": "1"},
            {"timeMs": "10.0", "crank": "0"},
            {"timeMs": "11.0", "crank": "1"},
            {"timeMs": "12.0", "crank": "0"},
            {"timeMs": "13.0", "crank": "1"},
            {"timeMs": "14.0", "crank": "0"},
            {"timeMs": "15.0", "crank": "1"},
            {"timeMs": "16.0", "crank": "0"},
            {"timeMs": "17.0", "crank": "1"},
            {"timeMs": "18.0", "crank": "0"},
            {"timeMs": "19.0", "crank": "1"},
        ],
        columns=("timeMs", "crank"),
        source_path=None,
        edits=edits,
        definition=definition,
        runtime_snapshot=None,
    )

    assert summary.severity == "warning"
    assert any("does not expose a cam/secondary channel" in finding.lower() for finding in summary.findings)
