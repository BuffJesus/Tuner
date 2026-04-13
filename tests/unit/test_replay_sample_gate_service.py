"""Tests for ReplaySampleGateService and SampleGatingConfig.

Each test targets a specific named gate so gate boundaries and summary text
can be verified in isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)

_NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)


def _record(**values: float) -> DataLogRecord:
    return DataLogRecord(timestamp=_NOW, values=dict(values))


# ---------------------------------------------------------------------------
# std_DeadLambda
# ---------------------------------------------------------------------------

class TestDeadLambdaGate:
    _CFG = SampleGatingConfig(enabled_gates=frozenset({"std_DeadLambda"}))

    def test_accepts_plausible_afr(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=1000.0, afr=14.7), self._CFG)

    def test_rejects_afr_too_high(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(afr=40.0), self._CFG)
        assert r is not None
        assert r.gate_name == "std_DeadLambda"
        assert "40.00" in r.reason

    def test_rejects_afr_too_low(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(afr=4.9), self._CFG)
        assert r is not None
        assert r.gate_name == "std_DeadLambda"

    def test_rejects_missing_lambda(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(rpm=1000.0, map=50.0), self._CFG)
        assert r is not None
        assert r.gate_name == "std_DeadLambda"
        assert "no lambda" in r.reason

    def test_accepts_lambda_channel_directly(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(lambda_=0.98), self._CFG)

    def test_accepts_boundary_afr_min(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(afr=7.0), self._CFG)

    def test_accepts_boundary_afr_max(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(afr=25.0), self._CFG)

    def test_custom_afr_range(self) -> None:
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_DeadLambda"}),
            afr_min=10.0,
            afr_max=18.0,
        )
        svc = ReplaySampleGateService()
        assert not svc.is_accepted(_record(afr=9.9), cfg)
        assert not svc.is_accepted(_record(afr=18.1), cfg)
        assert svc.is_accepted(_record(afr=14.7), cfg)


# ---------------------------------------------------------------------------
# minCltFilter
# ---------------------------------------------------------------------------

class TestMinCltFilter:
    _CFG = SampleGatingConfig(enabled_gates=frozenset({"minCltFilter"}))

    def test_rejects_cold_coolant(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(coolant=40.0), self._CFG)
        assert r is not None
        assert r.gate_name == "minCltFilter"
        assert "40.0" in r.reason

    def test_accepts_warm_coolant(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(coolant=85.0), self._CFG)

    def test_accepts_exact_threshold(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(coolant=70.0), self._CFG)

    def test_passes_through_when_no_clt_channel(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=1000.0), self._CFG)

    def test_clt_alias(self) -> None:
        # "clt" should resolve via alias
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(clt=50.0), self._CFG)
        assert r is not None
        assert r.gate_name == "minCltFilter"


# ---------------------------------------------------------------------------
# accelFilter
# ---------------------------------------------------------------------------

class TestAccelFilter:
    _CFG = SampleGatingConfig(enabled_gates=frozenset({"accelFilter"}))

    def test_rejects_accel_flag_set(self) -> None:
        svc = ReplaySampleGateService()
        # engine & 0x10 (16) = accel enrichment
        r = svc.primary_rejection(_record(engine=16.0), self._CFG)
        assert r is not None
        assert r.gate_name == "accelFilter"
        assert "accel enrichment" in r.reason

    def test_rejects_engine_with_accel_flag_combined(self) -> None:
        svc = ReplaySampleGateService()
        # 0x13 = fuel pump (0x01) + accel (0x10) + unknown (0x02)
        r = svc.primary_rejection(_record(engine=0x13), self._CFG)
        assert r is not None
        assert r.gate_name == "accelFilter"

    def test_accepts_when_accel_flag_clear(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(engine=0x01), self._CFG)  # only fuel pump bit

    def test_passes_through_no_engine_channel(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=1000.0), self._CFG)


# ---------------------------------------------------------------------------
# aseFilter
# ---------------------------------------------------------------------------

class TestAseFilter:
    _CFG = SampleGatingConfig(enabled_gates=frozenset({"aseFilter"}))

    def test_rejects_ase_flag(self) -> None:
        svc = ReplaySampleGateService()
        # engine & 0x04 (4) = ASE active
        r = svc.primary_rejection(_record(engine=4.0), self._CFG)
        assert r is not None
        assert r.gate_name == "aseFilter"
        assert "after-start" in r.reason

    def test_accepts_without_ase_bit(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(engine=0x11), self._CFG)  # accel + fuel pump, no ASE

    def test_passes_through_no_engine_channel(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=2000.0), self._CFG)


# ---------------------------------------------------------------------------
# overrunFilter
# ---------------------------------------------------------------------------

class TestOverrunFilter:
    _CFG = SampleGatingConfig(enabled_gates=frozenset({"overrunFilter"}))

    def test_rejects_zero_pulsewidth(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(pulseWidth=0.0), self._CFG)
        assert r is not None
        assert r.gate_name == "overrunFilter"
        assert "overrun" in r.reason

    def test_accepts_nonzero_pulsewidth(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(pulseWidth=3.5), self._CFG)

    def test_passes_through_no_pw_channel(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=1500.0), self._CFG)

    def test_pw_alias(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(pw=0.0), self._CFG)
        assert r is not None
        assert r.gate_name == "overrunFilter"


# ---------------------------------------------------------------------------
# maxTPS gate
# ---------------------------------------------------------------------------

class TestMaxTpsFilter:
    _CFG = SampleGatingConfig(
        enabled_gates=frozenset({"maxTPS"}),
        tps_max_percent=80.0,
    )

    def test_rejects_high_tps(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(tps=85.0), self._CFG)
        assert r is not None
        assert r.gate_name == "maxTPS"

    def test_accepts_low_tps(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(tps=60.0), self._CFG)

    def test_passes_through_no_tps(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=2000.0), self._CFG)


# ---------------------------------------------------------------------------
# minRPM gate
# ---------------------------------------------------------------------------

class TestMinRpmFilter:
    _CFG = SampleGatingConfig(
        enabled_gates=frozenset({"minRPM"}),
        rpm_min=300.0,
    )

    def test_rejects_low_rpm(self) -> None:
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(rpm=200.0), self._CFG)
        assert r is not None
        assert r.gate_name == "minRPM"

    def test_accepts_adequate_rpm(self) -> None:
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=800.0), self._CFG)


# ---------------------------------------------------------------------------
# Axis bound gates
# ---------------------------------------------------------------------------

class TestAxisBoundGates:
    def test_x_axis_min_rejects(self) -> None:
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_xAxisMin"}),
            axis_x_min=500.0,
            axis_x_value=400.0,
        )
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(rpm=400.0), cfg)
        assert r is not None
        assert r.gate_name == "std_xAxisMin"

    def test_x_axis_min_accepts(self) -> None:
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_xAxisMin"}),
            axis_x_min=500.0,
            axis_x_value=600.0,
        )
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(rpm=600.0), cfg)

    def test_x_axis_max_rejects(self) -> None:
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_xAxisMax"}),
            axis_x_max=6000.0,
            axis_x_value=7000.0,
        )
        svc = ReplaySampleGateService()
        r = svc.primary_rejection(_record(rpm=7000.0), cfg)
        assert r is not None
        assert r.gate_name == "std_xAxisMax"

    def test_y_axis_gates_pass_through_without_context(self) -> None:
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_yAxisMin", "std_yAxisMax"}),
        )
        svc = ReplaySampleGateService()
        assert svc.is_accepted(_record(map=50.0), cfg)


# ---------------------------------------------------------------------------
# gate_log summary
# ---------------------------------------------------------------------------

class TestGateLog:
    def test_gate_log_summary_text(self) -> None:
        log = DataLog(
            name="test",
            records=[
                _record(rpm=1000.0, afr=14.7),       # accepted
                _record(rpm=1200.0, afr=14.5),       # accepted
                _record(rpm=800.0, afr=40.0),        # rejected: std_DeadLambda
                _record(rpm=600.0, engine=4.0, afr=14.7),   # rejected: aseFilter
            ],
        )
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_DeadLambda", "aseFilter"}),
        )
        svc = ReplaySampleGateService()
        summary = svc.gate_log(log, cfg)

        assert summary.total_count == 4
        assert summary.accepted_count == 2
        assert summary.rejected_count == 2
        assert dict(summary.rejection_counts_by_gate) == {
            "std_DeadLambda": 1,
            "aseFilter": 1,
        }
        assert "2 accepted" in summary.summary_text
        assert "2 rejected" in summary.summary_text
        assert "std_DeadLambda=1" in summary.detail_lines[1]
        assert "aseFilter=1" in summary.detail_lines[1]

    def test_gate_log_all_accepted(self) -> None:
        log = DataLog(
            name="test",
            records=[_record(rpm=1000.0, afr=14.7), _record(rpm=1200.0, afr=13.8)],
        )
        cfg = SampleGatingConfig(enabled_gates=frozenset({"std_DeadLambda"}))
        svc = ReplaySampleGateService()
        summary = svc.gate_log(log, cfg)

        assert summary.accepted_count == 2
        assert summary.rejected_count == 0
        assert summary.rejection_counts_by_gate == ()
        assert "No rejections." in summary.detail_lines

    def test_gate_log_uses_default_gates_when_none_specified(self) -> None:
        # Default gates include std_DeadLambda which rejects missing AFR
        log = DataLog(
            name="test",
            records=[_record(rpm=1000.0)],  # no AFR → std_DeadLambda rejects
        )
        svc = ReplaySampleGateService()
        summary = svc.gate_log(log)
        assert summary.rejected_count == 1
        assert summary.rejection_counts_by_gate[0][0] == "std_DeadLambda"

    def test_gate_log_empty_log(self) -> None:
        log = DataLog(name="empty", records=[])
        svc = ReplaySampleGateService()
        summary = svc.gate_log(log)
        assert summary.total_count == 0
        assert summary.accepted_count == 0
        assert summary.rejected_count == 0

    def test_fail_fast_stops_at_first_rejection(self) -> None:
        # Record fails both std_DeadLambda and aseFilter; only std_DeadLambda
        # should be reported because it sorts first alphabetically and fail-fast
        # stops on first rejection.
        cfg = SampleGatingConfig(
            enabled_gates=frozenset({"std_DeadLambda", "aseFilter"}),
        )
        record = _record(engine=4.0, afr=40.0)  # both gates would fire
        svc = ReplaySampleGateService()
        evals = svc.evaluate_record(record, cfg)
        rejections = [e for e in evals if not e.accepted]
        assert len(rejections) == 1  # fail-fast: only one rejection reported


# ---------------------------------------------------------------------------
# known_gate_names
# ---------------------------------------------------------------------------

def test_known_gate_names_covers_all_speeduino_gates() -> None:
    svc = ReplaySampleGateService()
    names = svc.known_gate_names()
    expected = {
        "std_DeadLambda", "std_xAxisMin", "std_xAxisMax",
        "std_yAxisMin", "std_yAxisMax",
        "minCltFilter", "accelFilter", "aseFilter",
        "overrunFilter", "maxTPS", "minRPM",
    }
    assert expected.issubset(set(names))
