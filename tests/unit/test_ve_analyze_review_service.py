"""Tests for VeAnalyzeReviewService.

Covers:
- Summary text for zero records
- Summary text with accepted/rejected/proposals
- Confidence distribution counts
- Largest lean corrections sorted descending by correction factor
- Largest rich corrections sorted ascending by correction factor
- cells_insufficient count (cells with data but below min_samples)
- Empty proposals produce "No corrections proposed" text
- Detail text contains rejection breakdown
- Preview truncated at 5 entries with ellipsis
"""

from __future__ import annotations

from datetime import UTC, datetime

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisCellCorrection,
    VeAnalysisProposal,
    VeAnalysisSummary,
)
from tuner.services.ve_analyze_review_service import VeAnalyzeReviewService


def _summary(
    total: int = 0,
    accepted: int = 0,
    rejected: int = 0,
    cells_with_data: int = 0,
    cells_with_proposals: int = 0,
    proposals: tuple[VeAnalysisProposal, ...] = (),
    cell_corrections: tuple[VeAnalysisCellCorrection, ...] = (),
    rejection_counts: tuple[tuple[str, int], ...] = (),
) -> VeAnalysisSummary:
    return VeAnalysisSummary(
        total_records=total,
        accepted_records=accepted,
        rejected_records=rejected,
        cells_with_data=cells_with_data,
        cells_with_proposals=cells_with_proposals,
        cell_corrections=cell_corrections,
        proposals=proposals,
        rejection_counts_by_gate=rejection_counts,
        summary_text="",
        detail_lines=(),
    )


def _proposal(row: int, col: int, current: float, proposed: float, cf: float, n: int = 5) -> VeAnalysisProposal:
    return VeAnalysisProposal(
        row_index=row, col_index=col,
        current_ve=current, proposed_ve=proposed,
        correction_factor=cf, sample_count=n,
    )


def _correction(row: int, col: int, n: int, cf: float, confidence: str,
                current: float | None = 50.0, proposed: float | None = None) -> VeAnalysisCellCorrection:
    return VeAnalysisCellCorrection(
        row_index=row, col_index=col,
        sample_count=n,
        mean_correction_factor=cf,
        current_ve=current,
        proposed_ve=proposed,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Summary text
# ---------------------------------------------------------------------------

def test_summary_text_zero_records() -> None:
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(total=0))
    assert "no records" in result.summary_text.lower()


def test_summary_text_with_data() -> None:
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(total=100, accepted=80, rejected=20,
                                cells_with_data=6, cells_with_proposals=4))
    assert "100" in result.summary_text
    assert "80" in result.summary_text
    assert "20" in result.summary_text
    assert "4" in result.summary_text


# ---------------------------------------------------------------------------
# Confidence distribution
# ---------------------------------------------------------------------------

def test_confidence_distribution_counts() -> None:
    corrections = (
        _correction(0, 0, 1, 1.0, "insufficient"),
        _correction(0, 1, 3, 1.0, "low"),
        _correction(0, 2, 10, 1.0, "medium"),
        _correction(1, 0, 30, 1.0, "high"),
        _correction(1, 1, 1, 1.0, "insufficient"),
    )
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(total=5, cells_with_data=5, cell_corrections=corrections))
    dist = dict(result.confidence_distribution)
    assert dist["insufficient"] == 2
    assert dist["low"] == 1
    assert dist["medium"] == 1
    assert dist["high"] == 1


def test_confidence_distribution_always_has_all_levels() -> None:
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary())
    levels = {lvl for lvl, _ in result.confidence_distribution}
    assert levels == {"insufficient", "low", "medium", "high"}


# ---------------------------------------------------------------------------
# Lean corrections
# ---------------------------------------------------------------------------

def test_largest_lean_sorted_descending() -> None:
    proposals = (
        _proposal(0, 0, 50.0, 55.0, 1.1),
        _proposal(0, 1, 50.0, 57.5, 1.15),
        _proposal(1, 0, 50.0, 56.0, 1.12),
    )
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=3, accepted=3, cells_with_data=3, cells_with_proposals=3,
        proposals=proposals,
    ))
    lean = result.largest_lean_corrections
    assert len(lean) == 3
    assert lean[0].correction_factor == 1.15
    assert lean[1].correction_factor == 1.12
    assert lean[2].correction_factor == 1.1


def test_lean_text_in_detail() -> None:
    proposals = (_proposal(0, 0, 50.0, 55.0, 1.1, n=10),)
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=10, accepted=10, cells_with_data=1, cells_with_proposals=1,
        proposals=proposals,
    ))
    assert "lean" in result.detail_text.lower()
    assert "50.0→55.0" in result.detail_text


# ---------------------------------------------------------------------------
# Rich corrections
# ---------------------------------------------------------------------------

def test_largest_rich_sorted_ascending_by_factor() -> None:
    proposals = (
        _proposal(0, 0, 50.0, 45.0, 0.9),
        _proposal(0, 1, 50.0, 42.5, 0.85),
        _proposal(1, 0, 50.0, 44.0, 0.88),
    )
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=3, accepted=3, cells_with_data=3, cells_with_proposals=3,
        proposals=proposals,
    ))
    rich = result.largest_rich_corrections
    assert len(rich) == 3
    assert rich[0].correction_factor == 0.85
    assert rich[1].correction_factor == 0.88
    assert rich[2].correction_factor == 0.9


def test_rich_text_in_detail() -> None:
    proposals = (_proposal(0, 0, 50.0, 45.0, 0.9, n=10),)
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=10, accepted=10, cells_with_data=1, cells_with_proposals=1,
        proposals=proposals,
    ))
    assert "rich" in result.detail_text.lower()
    assert "50.0→45.0" in result.detail_text


# ---------------------------------------------------------------------------
# cells_insufficient
# ---------------------------------------------------------------------------

def test_cells_insufficient_counts_cells_below_min() -> None:
    # A correction with proposed_ve=None and current_ve known → insufficient
    corrections = (
        _correction(0, 0, 2, 1.1, "insufficient", current=50.0, proposed=None),
        _correction(0, 1, 10, 1.0, "medium", current=50.0, proposed=50.0),
    )
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(cells_with_data=2, cell_corrections=corrections))
    assert result.cells_insufficient == 1


def test_cells_insufficient_text_in_detail() -> None:
    corrections = (_correction(0, 0, 1, 1.1, "insufficient", current=50.0, proposed=None),)
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(cells_with_data=1, cell_corrections=corrections))
    assert "insufficient" in result.detail_text.lower()


# ---------------------------------------------------------------------------
# Empty proposals
# ---------------------------------------------------------------------------

def test_no_proposals_text() -> None:
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(total=10, accepted=10, cells_with_data=0))
    assert "no corrections" in result.detail_text.lower()


# ---------------------------------------------------------------------------
# Rejection breakdown in detail text
# ---------------------------------------------------------------------------

def test_rejection_breakdown_in_detail() -> None:
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=10, accepted=7, rejected=3,
        rejection_counts=(("std_DeadLambda", 2), ("minCltFilter", 1)),
    ))
    assert "std_DeadLambda=2" in result.detail_text
    assert "minCltFilter=1" in result.detail_text


# ---------------------------------------------------------------------------
# Preview truncation
# ---------------------------------------------------------------------------

def test_lean_preview_truncates_at_five() -> None:
    proposals = tuple(
        _proposal(0, i, 50.0, 50.0 + i, 1.0 + i * 0.01)
        for i in range(8)
    )
    svc = VeAnalyzeReviewService()
    result = svc.build(_summary(
        total=8, accepted=8, cells_with_data=8, cells_with_proposals=8,
        proposals=proposals,
    ))
    assert len(result.largest_lean_corrections) == 5
