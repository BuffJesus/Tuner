"""Tests for Phase 7 workspace UI surfacing through VeAnalyzeReviewService.

The Phase 7 service-layer slices added new signals on
``VeAnalysisCellCorrection`` (clamp_applied, boost_penalty_applied) and
two new optional inputs to the review service (smoothed layer, root-cause
diagnostics). This file proves those signals reach the operator-facing
review snapshot without disturbing Phase 6 behaviour.
"""
from __future__ import annotations

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisCellCorrection,
    VeAnalysisProposal,
    VeAnalysisSummary,
)
from tuner.services.ve_analyze_review_service import VeAnalyzeReviewService
from tuner.services.ve_proposal_smoothing_service import (
    SmoothedProposalLayer,
)
from tuner.services.ve_root_cause_diagnostics_service import (
    RootCauseDiagnostic,
    RootCauseDiagnosticReport,
)


def _correction(
    row: int = 0, col: int = 0, *,
    clamp_applied: bool = False, boost_penalty_applied: float = 0.0,
    cf: float = 1.10, current: float = 50.0, proposed: float | None = 55.0,
    n: int = 5, confidence: str = "low",
) -> VeAnalysisCellCorrection:
    return VeAnalysisCellCorrection(
        row_index=row, col_index=col, sample_count=n,
        mean_correction_factor=cf, current_ve=current,
        proposed_ve=proposed, confidence=confidence,
        clamp_applied=clamp_applied,
        boost_penalty_applied=boost_penalty_applied,
    )


def _summary(*corrections: VeAnalysisCellCorrection) -> VeAnalysisSummary:
    return VeAnalysisSummary(
        total_records=len(corrections),
        accepted_records=len(corrections),
        rejected_records=0,
        cells_with_data=len(corrections),
        cells_with_proposals=len(corrections),
        cell_corrections=corrections,
        proposals=(),
        rejection_counts_by_gate=(),
        summary_text="",
        detail_lines=(),
    )


# ---------------------------------------------------------------------------
# Default-off no-regression
# ---------------------------------------------------------------------------

class TestDefaultsAreEmpty:
    def test_summary_with_no_phase7_signals_emits_no_extra_lines(self) -> None:
        snap = VeAnalyzeReviewService().build(_summary(_correction()))
        assert snap.clamp_count == 0
        assert snap.boost_penalty_count == 0
        assert snap.smoothed_summary_text is None
        assert snap.diagnostic_lines == ()
        assert "Clamp transparency" not in snap.detail_text
        assert "Boost penalty" not in snap.detail_text
        assert "Smoothed layer" not in snap.detail_text
        assert "Root-cause diagnostics" not in snap.detail_text


# ---------------------------------------------------------------------------
# Slice 7.2 — clamp transparency line
# ---------------------------------------------------------------------------

class TestClampTransparency:
    def test_clamp_count_and_line_emitted(self) -> None:
        summary = _summary(
            _correction(0, 0, clamp_applied=True),
            _correction(0, 1, clamp_applied=True),
            _correction(0, 2),
        )
        snap = VeAnalyzeReviewService().build(summary)
        assert snap.clamp_count == 2
        assert "Clamp transparency: 2 proposal(s)" in snap.detail_text
        assert "raw_correction_factor" in snap.detail_text


# ---------------------------------------------------------------------------
# Slice 7.6 — boost penalty line
# ---------------------------------------------------------------------------

class TestBoostPenalty:
    def test_boost_penalty_count_and_line_emitted(self) -> None:
        summary = _summary(
            _correction(0, 0, boost_penalty_applied=0.7),
            _correction(0, 1, boost_penalty_applied=0.0),
            _correction(0, 2, boost_penalty_applied=0.3),
        )
        snap = VeAnalyzeReviewService().build(summary)
        assert snap.boost_penalty_count == 2
        assert "Boost penalty: 2 cell(s) downweighted" in snap.detail_text


# ---------------------------------------------------------------------------
# Slice 7.5 — smoothed layer summary
# ---------------------------------------------------------------------------

class TestSmoothedLayer:
    def test_smoothed_summary_surfaced_when_layer_provided(self) -> None:
        layer = SmoothedProposalLayer(
            smoothed_proposals=(),
            unchanged_count=2,
            smoothed_count=3,
            summary_text="Smoothed 3 proposal(s); 2 preserved unchanged.",
        )
        snap = VeAnalyzeReviewService().build(
            _summary(_correction()), smoothed_layer=layer,
        )
        assert snap.smoothed_summary_text == layer.summary_text
        assert "Smoothed layer: Smoothed 3 proposal(s)" in snap.detail_text


# ---------------------------------------------------------------------------
# Slice 7.7 — root-cause diagnostic lines
# ---------------------------------------------------------------------------

class TestDiagnosticLines:
    def test_diagnostic_lines_surfaced_with_rule_and_severity(self) -> None:
        report = RootCauseDiagnosticReport(
            diagnostics=(
                RootCauseDiagnostic(
                    rule="injector_flow_error", severity="warning",
                    message="All cells biased lean by ~10% with low variance.",
                    evidence_cells=((0, 0), (0, 1)),
                ),
            ),
            summary_text="1 finding",
        )
        snap = VeAnalyzeReviewService().build(
            _summary(_correction()), diagnostics=report,
        )
        assert len(snap.diagnostic_lines) == 1
        assert snap.diagnostic_lines[0].startswith("[warning] injector_flow_error")
        assert "Root-cause diagnostics:" in snap.detail_text
        assert "[warning] injector_flow_error" in snap.detail_text

    def test_empty_diagnostics_emit_no_section(self) -> None:
        report = RootCauseDiagnosticReport(diagnostics=(), summary_text="ok")
        snap = VeAnalyzeReviewService().build(
            _summary(_correction()), diagnostics=report,
        )
        assert snap.diagnostic_lines == ()
        assert "Root-cause diagnostics" not in snap.detail_text
