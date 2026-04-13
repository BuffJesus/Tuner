"""Tests for Phase 7 Slice 7.7 — root-cause diagnostics surface (read-only).

Covers:
- Empty / under-threshold proposal sets produce no diagnostics
- Healthy data (no systemic patterns) produces no diagnostics
- Uniform global bias → injector_flow_error
- Low-load-only bias → deadtime_error
- Opposite high-vs-low load bias → target_table_error
- Correction strongly correlated with load axis → sensor_calibration_error
- Diagnostics never modify the input proposals
"""
from __future__ import annotations

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisProposal,
    VeAnalysisSummary,
)
from tuner.services.ve_root_cause_diagnostics_service import (
    VeRootCauseDiagnosticsService,
)


def _proposal(row: int, col: int, cf: float, n: int = 5) -> VeAnalysisProposal:
    return VeAnalysisProposal(
        row_index=row, col_index=col,
        current_ve=50.0, proposed_ve=round(50.0 * cf, 2),
        correction_factor=cf, sample_count=n,
    )


def _summary(*proposals: VeAnalysisProposal) -> VeAnalysisSummary:
    return VeAnalysisSummary(
        total_records=len(proposals),
        accepted_records=len(proposals),
        rejected_records=0,
        cells_with_data=len(proposals),
        cells_with_proposals=len(proposals),
        cell_corrections=(),
        proposals=proposals,
        rejection_counts_by_gate=(),
        summary_text="",
        detail_lines=(),
    )


def _rules(report) -> set[str]:
    return {d.rule for d in report.diagnostics}


# ---------------------------------------------------------------------------
# Threshold gating
# ---------------------------------------------------------------------------

class TestThresholdGating:
    def test_empty_summary_no_diagnostics(self) -> None:
        report = VeRootCauseDiagnosticsService().diagnose(_summary())
        assert report.diagnostics == ()
        assert report.has_findings is False

    def test_below_minimum_proposals_no_diagnostics(self) -> None:
        # 5 proposals — below the _MIN_PROPOSALS threshold of 6
        proposals = tuple(_proposal(0, c, 1.20) for c in range(5))
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert report.diagnostics == ()


# ---------------------------------------------------------------------------
# Healthy data — no diagnostics fire
# ---------------------------------------------------------------------------

class TestHealthyData:
    def test_random_small_corrections_no_diagnostics(self) -> None:
        # 9 cells with corrections within ±2% of 1.0 — under all thresholds
        cfs = [0.98, 1.01, 0.99, 1.02, 0.99, 1.01, 1.00, 0.98, 1.02]
        proposals = tuple(
            _proposal(i // 3, i % 3, cf) for i, cf in enumerate(cfs)
        )
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert report.diagnostics == ()


# ---------------------------------------------------------------------------
# injector_flow_error
# ---------------------------------------------------------------------------

class TestInjectorFlowError:
    def test_uniform_lean_bias_fires(self) -> None:
        # 9 cells all biased ~10% lean with low variance
        cfs = [1.10, 1.10, 1.10, 1.11, 1.10, 1.09, 1.10, 1.10, 1.10]
        proposals = tuple(
            _proposal(i // 3, i % 3, cf) for i, cf in enumerate(cfs)
        )
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert "injector_flow_error" in _rules(report)
        finding = next(
            d for d in report.diagnostics if d.rule == "injector_flow_error"
        )
        assert "lean" in finding.message
        assert finding.severity == "warning"

    def test_uniform_rich_bias_fires(self) -> None:
        cfs = [0.90] * 9
        proposals = tuple(
            _proposal(i // 3, i % 3, cf) for i, cf in enumerate(cfs)
        )
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        finding = next(
            d for d in report.diagnostics if d.rule == "injector_flow_error"
        )
        assert "rich" in finding.message

    def test_high_variance_does_not_fire(self) -> None:
        # Mean is biased lean but variance is too high
        cfs = [1.30, 0.90, 1.20, 0.95, 1.25, 0.88, 1.15, 0.92, 1.10]
        proposals = tuple(
            _proposal(i // 3, i % 3, cf) for i, cf in enumerate(cfs)
        )
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert "injector_flow_error" not in _rules(report)


# ---------------------------------------------------------------------------
# deadtime_error
# ---------------------------------------------------------------------------

class TestDeadtimeError:
    def test_low_load_low_rpm_bias_fires(self) -> None:
        # 4×4 grid; low-load/low-rpm corner (rows 0-1, cols 0-1) lean by 15%;
        # rest near 1.0
        proposals: list[VeAnalysisProposal] = []
        for r in range(4):
            for c in range(4):
                if r <= 1 and c <= 1:
                    proposals.append(_proposal(r, c, 1.15))
                else:
                    proposals.append(_proposal(r, c, 1.00))
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert "deadtime_error" in _rules(report)


# ---------------------------------------------------------------------------
# target_table_error
# ---------------------------------------------------------------------------

class TestTargetTableError:
    def test_opposite_high_low_load_bias_fires(self) -> None:
        # rows 0-1 lean (1.10), rows 2-3 rich (0.90), 4 cells per row
        proposals: list[VeAnalysisProposal] = []
        for r in range(4):
            cf = 1.10 if r <= 1 else 0.90
            for c in range(4):
                proposals.append(_proposal(r, c, cf))
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert "target_table_error" in _rules(report)


# ---------------------------------------------------------------------------
# sensor_calibration_error
# ---------------------------------------------------------------------------

class TestSensorCalibrationError:
    def test_load_correlated_bias_fires(self) -> None:
        # Linear ramp of correction with row (load) — perfect correlation.
        # Use opposite-sign ramp so target_table_error doesn't dominate
        # the assertion (we just want to verify sensor_calibration fires).
        proposals: list[VeAnalysisProposal] = []
        for r in range(4):
            cf = 0.90 + r * 0.07  # 0.90, 0.97, 1.04, 1.11
            for c in range(3):
                proposals.append(_proposal(r, c, cf))
        report = VeRootCauseDiagnosticsService().diagnose(_summary(*proposals))
        assert "sensor_calibration_error" in _rules(report)
        finding = next(
            d for d in report.diagnostics if d.rule == "sensor_calibration_error"
        )
        assert "Pearson" in finding.message


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_diagnostics_do_not_mutate_input(self) -> None:
        cfs = [1.10] * 9
        proposals = tuple(
            _proposal(i // 3, i % 3, cf) for i, cf in enumerate(cfs)
        )
        summary = _summary(*proposals)
        before = tuple(
            (p.proposed_ve, p.correction_factor) for p in summary.proposals
        )
        VeRootCauseDiagnosticsService().diagnose(summary)
        after = tuple(
            (p.proposed_ve, p.correction_factor) for p in summary.proposals
        )
        assert before == after
