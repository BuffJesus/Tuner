"""Phase 7 Slice 7.5 — VE proposal smoothing as a reviewable transform.

Takes a ``VeAnalysisSummary`` produced by ``VeAnalyzeCellHitService`` and
returns a *separate* ``SmoothedProposalLayer`` containing post-acceptance
smoothed proposals. The original raw proposals on the summary are never
mutated; the operator chooses whether to stage the raw layer, the smoothed
layer, or neither.

Hard rules from Phase 7 Scope (see docs/tuning-roadmap.md):

- Smoothing is **never implicit** in the accept path. ``VeAnalyzeCellHitService``
  produces raw proposals; ``VeProposalSmoothingService`` produces smoothed
  proposals as a strictly additive review layer.
- The operator can disable, preview, and revert independently.
- Smoothing only operates on cells that already received a raw proposal —
  it never invents VE values for unvisited cells.
- Edge cells use only the neighbors that exist; the kernel shrinks
  gracefully at the grid boundary instead of fabricating values.
"""
from __future__ import annotations

from dataclasses import dataclass

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisProposal,
    VeAnalysisSummary,
)


@dataclass(slots=True, frozen=True)
class SmoothingConfig:
    """Operator-tunable smoothing kernel.

    ``kernel_radius`` is the half-width of the smoothing window: a value of
    1 produces a 3×3 kernel; 2 produces a 5×5 kernel. ``min_neighbors``
    requires at least N other proposals inside the kernel before a cell is
    smoothed; cells with fewer neighbors pass through unchanged so isolated
    spikes from a single high-confidence cell are not erased.

    ``preserve_edge_magnitude`` keeps the strongest correction in the
    kernel intact when set — useful when smoothing the table edge near a
    boost transition where the steep gradient is the *signal* and should
    not be averaged away.
    """

    kernel_radius: int = 1
    min_neighbors: int = 1
    preserve_edge_magnitude: bool = False


@dataclass(slots=True, frozen=True)
class SmoothedProposalLayer:
    """Result of running ``VeProposalSmoothingService.smooth()``.

    ``smoothed_proposals`` is a separate proposal list — the original
    summary is not modified. ``unchanged_count`` is the number of raw
    proposals that passed through unchanged (e.g. isolated cells with
    no neighbors); ``smoothed_count`` is the number that were modified.
    """

    smoothed_proposals: tuple[VeAnalysisProposal, ...]
    unchanged_count: int
    smoothed_count: int
    summary_text: str


class VeProposalSmoothingService:
    """Stateless smoothing service.

    Call ``smooth(summary, config)`` to obtain a ``SmoothedProposalLayer``.
    The summary is read-only; smoothing builds new ``VeAnalysisProposal``
    instances rather than mutating the existing ones.
    """

    def smooth(
        self,
        summary: VeAnalysisSummary,
        config: SmoothingConfig | None = None,
    ) -> SmoothedProposalLayer:
        cfg = config or SmoothingConfig()
        if not summary.proposals:
            return SmoothedProposalLayer(
                smoothed_proposals=(),
                unchanged_count=0,
                smoothed_count=0,
                summary_text="No proposals to smooth.",
            )
        if cfg.kernel_radius < 1:
            # A radius of zero is the identity transform — return the raw
            # proposals untouched so the caller can treat the layer as
            # "smoothing disabled" without a special-case branch.
            return SmoothedProposalLayer(
                smoothed_proposals=tuple(summary.proposals),
                unchanged_count=len(summary.proposals),
                smoothed_count=0,
                summary_text=(
                    f"Kernel radius {cfg.kernel_radius} → identity transform."
                ),
            )

        index: dict[tuple[int, int], VeAnalysisProposal] = {
            (p.row_index, p.col_index): p for p in summary.proposals
        }

        smoothed: list[VeAnalysisProposal] = []
        unchanged = 0
        modified = 0
        radius = cfg.kernel_radius

        for proposal in summary.proposals:
            neighbors: list[VeAnalysisProposal] = []
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if dr == 0 and dc == 0:
                        continue
                    neighbor = index.get(
                        (proposal.row_index + dr, proposal.col_index + dc)
                    )
                    if neighbor is not None:
                        neighbors.append(neighbor)

            if len(neighbors) < cfg.min_neighbors:
                # Insufficient neighbours — preserve the raw proposal.
                smoothed.append(proposal)
                unchanged += 1
                continue

            window = [proposal, *neighbors]
            if cfg.preserve_edge_magnitude:
                # Identify the strongest deviation in the window. If the
                # current cell is that strongest deviation, leave it
                # untouched so a real edge (e.g. boost spool transition)
                # is not averaged away by its softer neighbors.
                strongest = max(window, key=lambda p: abs(p.correction_factor - 1.0))
                if strongest is proposal:
                    smoothed.append(proposal)
                    unchanged += 1
                    continue

            # Sample-count-weighted average of the correction factors so a
            # high-confidence cell is not pulled by a low-confidence
            # neighbor. Falls back to a uniform mean when all weights are
            # zero (defensive — sample_count is always >= 1 for proposals).
            total_weight = sum(p.sample_count for p in window)
            if total_weight <= 0:
                avg_cf = sum(p.correction_factor for p in window) / len(window)
            else:
                avg_cf = (
                    sum(p.correction_factor * p.sample_count for p in window)
                    / total_weight
                )

            new_proposed = round(proposal.current_ve * avg_cf, 2)
            if abs(new_proposed - proposal.proposed_ve) < 0.01:
                # The smoothing pass would not move this cell — preserve
                # the raw proposal so the diff stays minimal and obvious.
                smoothed.append(proposal)
                unchanged += 1
                continue

            smoothed.append(
                VeAnalysisProposal(
                    row_index=proposal.row_index,
                    col_index=proposal.col_index,
                    current_ve=proposal.current_ve,
                    proposed_ve=new_proposed,
                    correction_factor=round(avg_cf, 4),
                    sample_count=proposal.sample_count,
                    raw_correction_factor=proposal.correction_factor,
                    clamp_applied=proposal.clamp_applied,
                )
            )
            modified += 1

        summary_text = (
            f"Smoothed {modified} proposal(s); {unchanged} preserved unchanged "
            f"(kernel radius {cfg.kernel_radius}, min_neighbors {cfg.min_neighbors})."
        )
        return SmoothedProposalLayer(
            smoothed_proposals=tuple(smoothed),
            unchanged_count=unchanged,
            smoothed_count=modified,
            summary_text=summary_text,
        )
