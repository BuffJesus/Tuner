"""Tests for Phase 7 Slice 7.5 — VE proposal smoothing as a reviewable layer.

Covers:
- Empty input → empty output
- kernel_radius=0 → identity transform
- Isolated proposal (no neighbors) → unchanged
- Already-smooth row of proposals → unchanged
- Spike proposal pulled toward its neighbors after smoothing
- Sample-count weighting: a high-n cell is barely pulled by a low-n neighbor
- preserve_edge_magnitude keeps the strongest correction in the kernel
- min_neighbors=2 forces single-neighbor cells to pass through
- Original VeAnalysisSummary.proposals is *never* mutated by smoothing
"""
from __future__ import annotations

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisProposal,
    VeAnalysisSummary,
)
from tuner.services.ve_proposal_smoothing_service import (
    SmoothingConfig,
    VeProposalSmoothingService,
)


def _proposal(
    row: int, col: int, *, current: float = 50.0,
    proposed: float, cf: float, n: int = 5,
) -> VeAnalysisProposal:
    return VeAnalysisProposal(
        row_index=row, col_index=col,
        current_ve=current, proposed_ve=proposed,
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


# ---------------------------------------------------------------------------
# Trivial cases
# ---------------------------------------------------------------------------

class TestTrivialCases:
    def test_empty_summary_returns_empty_layer(self) -> None:
        result = VeProposalSmoothingService().smooth(_summary())
        assert result.smoothed_proposals == ()
        assert result.smoothed_count == 0
        assert result.unchanged_count == 0

    def test_kernel_radius_zero_is_identity(self) -> None:
        summary = _summary(_proposal(0, 0, proposed=55.0, cf=1.10))
        result = VeProposalSmoothingService().smooth(
            summary, SmoothingConfig(kernel_radius=0),
        )
        assert result.smoothed_proposals == summary.proposals
        assert result.smoothed_count == 0


# ---------------------------------------------------------------------------
# Pass-through cases (no modification expected)
# ---------------------------------------------------------------------------

class TestPassThrough:
    def test_isolated_proposal_with_no_neighbors_unchanged(self) -> None:
        summary = _summary(_proposal(0, 0, proposed=55.0, cf=1.10))
        result = VeProposalSmoothingService().smooth(summary)
        assert result.smoothed_proposals[0].proposed_ve == 55.0
        assert result.smoothed_count == 0
        assert result.unchanged_count == 1

    def test_already_smooth_row_unchanged(self) -> None:
        # Three contiguous cells with identical correction factor → already
        # smooth, no movement.
        summary = _summary(
            _proposal(0, 0, proposed=55.0, cf=1.10),
            _proposal(0, 1, proposed=55.0, cf=1.10),
            _proposal(0, 2, proposed=55.0, cf=1.10),
        )
        result = VeProposalSmoothingService().smooth(summary)
        assert result.smoothed_count == 0
        assert result.unchanged_count == 3
        for original, smoothed in zip(summary.proposals, result.smoothed_proposals):
            assert smoothed.proposed_ve == original.proposed_ve


# ---------------------------------------------------------------------------
# Smoothing actually moves a spike
# ---------------------------------------------------------------------------

class TestSpikeSmoothing:
    def test_middle_spike_pulled_toward_neighbors(self) -> None:
        # Two flat cells (cf=1.00) and a spike (cf=1.20) in the middle.
        summary = _summary(
            _proposal(0, 0, proposed=50.0, cf=1.00, n=10),
            _proposal(0, 1, proposed=60.0, cf=1.20, n=10),
            _proposal(0, 2, proposed=50.0, cf=1.00, n=10),
        )
        result = VeProposalSmoothingService().smooth(summary)
        spike = next(
            p for p in result.smoothed_proposals
            if (p.row_index, p.col_index) == (0, 1)
        )
        # Window mean: (1.20 + 1.00 + 1.00)/3 = 1.0667
        # New proposed = 50 * 1.0667 = 53.33
        assert spike.proposed_ve == 53.33
        assert spike.raw_correction_factor == 1.20  # original cf surfaced for review
        # Edge cells (0,0) and (0,2) each have one neighbor → also smoothed
        # toward the window mean (1.00 + 1.20)/2 = 1.10 → 55.0.
        assert result.smoothed_count == 3
        assert result.unchanged_count == 0
        edge = next(
            p for p in result.smoothed_proposals if (p.row_index, p.col_index) == (0, 0)
        )
        assert edge.proposed_ve == 55.0


# ---------------------------------------------------------------------------
# Sample-count weighting
# ---------------------------------------------------------------------------

class TestSampleCountWeighting:
    def test_high_confidence_cell_resists_low_confidence_neighbor(self) -> None:
        # cell (0,0) has 100 samples at cf=1.00; (0,1) has 1 sample at cf=2.00
        summary = _summary(
            _proposal(0, 0, proposed=50.0, cf=1.00, n=100),
            _proposal(0, 1, proposed=100.0, cf=2.00, n=1),
        )
        result = VeProposalSmoothingService().smooth(summary)
        anchor = next(
            p for p in result.smoothed_proposals if (p.row_index, p.col_index) == (0, 0)
        )
        # Weighted mean: (100*1.00 + 1*2.00) / 101 ≈ 1.0099
        # Anchor proposed = 50 * 1.0099 ≈ 50.50 — barely moved.
        assert 50.4 <= anchor.proposed_ve <= 50.6


# ---------------------------------------------------------------------------
# preserve_edge_magnitude
# ---------------------------------------------------------------------------

class TestPreserveEdgeMagnitude:
    def test_strongest_deviation_preserved_when_flag_set(self) -> None:
        # Spike at (0,1) is the strongest deviation in its window;
        # preserve_edge_magnitude should leave it alone.
        summary = _summary(
            _proposal(0, 0, proposed=50.0, cf=1.00),
            _proposal(0, 1, proposed=70.0, cf=1.40),  # strongest
            _proposal(0, 2, proposed=50.0, cf=1.00),
        )
        result = VeProposalSmoothingService().smooth(
            summary, SmoothingConfig(preserve_edge_magnitude=True),
        )
        spike = next(
            p for p in result.smoothed_proposals if (p.row_index, p.col_index) == (0, 1)
        )
        assert spike.proposed_ve == 70.0


# ---------------------------------------------------------------------------
# min_neighbors gate
# ---------------------------------------------------------------------------

class TestMinNeighbors:
    def test_min_neighbors_two_passes_through_single_neighbor_cells(self) -> None:
        # Two adjacent cells; each has exactly one neighbor → below
        # min_neighbors threshold of 2.
        summary = _summary(
            _proposal(0, 0, proposed=50.0, cf=1.00),
            _proposal(0, 1, proposed=60.0, cf=1.20),
        )
        result = VeProposalSmoothingService().smooth(
            summary, SmoothingConfig(min_neighbors=2),
        )
        assert result.smoothed_count == 0
        assert result.unchanged_count == 2


# ---------------------------------------------------------------------------
# Non-mutation guarantee
# ---------------------------------------------------------------------------

class TestNonMutation:
    def test_original_summary_proposals_not_modified(self) -> None:
        summary = _summary(
            _proposal(0, 0, proposed=50.0, cf=1.00),
            _proposal(0, 1, proposed=60.0, cf=1.20),
            _proposal(0, 2, proposed=50.0, cf=1.00),
        )
        original_repr = tuple(
            (p.proposed_ve, p.correction_factor) for p in summary.proposals
        )
        VeProposalSmoothingService().smooth(summary)
        after_repr = tuple(
            (p.proposed_ve, p.correction_factor) for p in summary.proposals
        )
        assert original_repr == after_repr
