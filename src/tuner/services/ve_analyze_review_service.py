"""Operator-facing review text for VE Analyze proposals.

Turns a VeAnalysisSummary into a human-readable review block suitable for the
workspace review panel.  Covers:

  - Total accepted / rejected sample counts
  - Confidence distribution across cells (insufficient / low / medium / high)
  - Largest lean corrections (proposed VE increase, sorted descending)
  - Largest rich corrections (proposed VE decrease, sorted ascending)
  - Cells skipped because minimum sample count was not met
  - Per-gate rejection breakdown
  - A condensed one-line summary plus a full multi-line detail block

No tune data is modified here.  The caller stages proposed edits explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

from tuner.services.ve_analyze_cell_hit_service import VeAnalysisProposal, VeAnalysisSummary
from tuner.services.ve_proposal_smoothing_service import SmoothedProposalLayer
from tuner.services.ve_root_cause_diagnostics_service import RootCauseDiagnosticReport


@dataclass(slots=True, frozen=True)
class VeAnalyzeReviewSnapshot:
    """Operator-facing review of a VeAnalysisSummary."""

    summary_text: str                           # one-line
    detail_text: str                            # multi-line, newline-separated
    confidence_distribution: tuple[tuple[str, int], ...]  # (level, count) sorted
    largest_lean_corrections: tuple[VeAnalysisProposal, ...]   # largest CF → sort desc
    largest_rich_corrections: tuple[VeAnalysisProposal, ...]   # smallest CF → sort asc
    cells_insufficient: int                     # cells with data but below min_samples
    max_preview_entries: int = 5
    # Phase 7 workspace UI surfacing — opt-in fields populated when the
    # corresponding signal is present. Defaults preserve existing review
    # snapshot equality and serialization.
    clamp_count: int = 0                        # Slice 7.2 — cells with clamp_applied
    boost_penalty_count: int = 0                # Slice 7.6 — cells with non-zero penalty
    smoothed_summary_text: str | None = None    # Slice 7.5 — when caller supplies layer
    diagnostic_lines: tuple[str, ...] = ()      # Slice 7.7 — root-cause findings


class VeAnalyzeReviewService:
    """Build an operator-facing review snapshot from a ``VeAnalysisSummary``."""

    _PREVIEW_COUNT = 5

    def build(
        self,
        summary: VeAnalysisSummary,
        *,
        smoothed_layer: SmoothedProposalLayer | None = None,
        diagnostics: RootCauseDiagnosticReport | None = None,
    ) -> VeAnalyzeReviewSnapshot:
        # -- Confidence distribution across all cells that received data ------
        dist: dict[str, int] = {"insufficient": 0, "low": 0, "medium": 0, "high": 0}
        cells_insufficient = 0
        # Phase 7 workspace UI surfacing — count clamp/boost-penalty cells
        # in the same loop so the review snapshot can flag the operator
        # without re-iterating.
        clamp_count = 0
        boost_penalty_count = 0
        for correction in summary.cell_corrections:
            level = correction.confidence
            dist[level] = dist.get(level, 0) + 1
            if correction.proposed_ve is None and correction.current_ve is not None:
                cells_insufficient += 1
            if correction.clamp_applied:
                clamp_count += 1
            if correction.boost_penalty_applied > 0:
                boost_penalty_count += 1

        confidence_distribution = tuple(
            (level, dist[level])
            for level in ("insufficient", "low", "medium", "high")
        )

        # -- Largest lean corrections (correction_factor > 1, sorted desc) ---
        lean = sorted(
            (p for p in summary.proposals if p.correction_factor > 1.0),
            key=lambda p: p.correction_factor,
            reverse=True,
        )
        largest_lean = tuple(lean[: self._PREVIEW_COUNT])

        # -- Largest rich corrections (correction_factor < 1, sorted asc) ----
        rich = sorted(
            (p for p in summary.proposals if p.correction_factor < 1.0),
            key=lambda p: p.correction_factor,
        )
        largest_rich = tuple(rich[: self._PREVIEW_COUNT])

        # -- Build text -------------------------------------------------------
        diagnostic_lines = (
            tuple(
                f"[{d.severity}] {d.rule}: {d.message}"
                for d in diagnostics.diagnostics
            )
            if diagnostics is not None and diagnostics.has_findings
            else ()
        )
        smoothed_summary_text = (
            smoothed_layer.summary_text if smoothed_layer is not None else None
        )

        summary_text = self._build_summary(summary)
        detail_text = self._build_detail(
            summary=summary,
            confidence_distribution=confidence_distribution,
            largest_lean=largest_lean,
            largest_rich=largest_rich,
            cells_insufficient=cells_insufficient,
            clamp_count=clamp_count,
            boost_penalty_count=boost_penalty_count,
            smoothed_summary_text=smoothed_summary_text,
            diagnostic_lines=diagnostic_lines,
        )

        return VeAnalyzeReviewSnapshot(
            summary_text=summary_text,
            detail_text=detail_text,
            confidence_distribution=confidence_distribution,
            largest_lean_corrections=largest_lean,
            largest_rich_corrections=largest_rich,
            cells_insufficient=cells_insufficient,
            max_preview_entries=self._PREVIEW_COUNT,
            clamp_count=clamp_count,
            boost_penalty_count=boost_penalty_count,
            smoothed_summary_text=smoothed_summary_text,
            diagnostic_lines=diagnostic_lines,
        )

    # ------------------------------------------------------------------
    # Text builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(summary: VeAnalysisSummary) -> str:
        if summary.total_records == 0:
            return "VE Analyze: no records to review."
        parts = [
            f"VE Analyze reviewed {summary.total_records} record(s):",
            f"{summary.accepted_records} accepted,",
            f"{summary.rejected_records} rejected,",
            f"{summary.cells_with_proposals} cell proposal(s) of {summary.cells_with_data} with data.",
        ]
        return " ".join(parts)

    @staticmethod
    def _build_detail(
        *,
        summary: VeAnalysisSummary,
        confidence_distribution: tuple[tuple[str, int], ...],
        largest_lean: tuple[VeAnalysisProposal, ...],
        largest_rich: tuple[VeAnalysisProposal, ...],
        cells_insufficient: int,
        clamp_count: int = 0,
        boost_penalty_count: int = 0,
        smoothed_summary_text: str | None = None,
        diagnostic_lines: tuple[str, ...] = (),
    ) -> str:
        lines: list[str] = []

        # Overview
        lines.append(
            f"Records: {summary.accepted_records} accepted / "
            f"{summary.rejected_records} rejected / "
            f"{summary.total_records} total."
        )

        # Rejection breakdown
        if summary.rejection_counts_by_gate:
            lines.append(
                "Rejections: "
                + ", ".join(f"{g}={c}" for g, c in summary.rejection_counts_by_gate)
                + "."
            )

        # Confidence distribution
        non_zero = [(lvl, cnt) for lvl, cnt in confidence_distribution if cnt > 0]
        if non_zero:
            dist_text = ", ".join(f"{lvl}={cnt}" for lvl, cnt in non_zero)
            lines.append(f"Cell confidence: {dist_text}.")

        if cells_insufficient > 0:
            lines.append(
                f"Cells skipped (insufficient samples): {cells_insufficient}."
            )

        # Phase 7 Slice 7.3 — coverage line. Only emitted when the
        # accumulator built a coverage map (i.e. the snapshot had a
        # table model); existing zero-data fixtures stay unchanged.
        if summary.coverage is not None and summary.coverage.total_count > 0:
            cov = summary.coverage
            lines.append(
                f"Coverage: {cov.visited_count}/{cov.total_count} cells "
                f"({cov.coverage_ratio * 100:.0f}%) visited."
            )

        # Lean corrections preview
        if largest_lean:
            lean_text = "; ".join(
                f"({p.row_index+1},{p.col_index+1}) "
                f"{p.current_ve:.1f}→{p.proposed_ve:.1f} ×{p.correction_factor:.4f} "
                f"n={p.sample_count}"
                for p in largest_lean
            )
            suffix = "…" if len(largest_lean) == 5 and summary.cells_with_proposals > 5 else ""
            lines.append(f"Largest lean corrections: {lean_text}{suffix}.")

        # Rich corrections preview
        if largest_rich:
            rich_text = "; ".join(
                f"({p.row_index+1},{p.col_index+1}) "
                f"{p.current_ve:.1f}→{p.proposed_ve:.1f} ×{p.correction_factor:.4f} "
                f"n={p.sample_count}"
                for p in largest_rich
            )
            suffix = "…" if len(largest_rich) == 5 and summary.cells_with_proposals > 5 else ""
            lines.append(f"Largest rich corrections: {rich_text}{suffix}.")

        if not largest_lean and not largest_rich and summary.cells_with_proposals == 0:
            lines.append("No corrections proposed yet.")

        # Phase 7 workspace UI surfacing — additive lines for clamp,
        # boost penalty, smoothed layer, and root-cause diagnostics.
        # Each line is emitted only when its signal fires so the
        # review block stays empty for Phase 6 baseline runs.
        if clamp_count > 0:
            lines.append(
                f"Clamp transparency: {clamp_count} proposal(s) hit the per-cell "
                "max-correction clamp — review raw_correction_factor before staging."
            )
        if boost_penalty_count > 0:
            lines.append(
                f"Boost penalty: {boost_penalty_count} cell(s) downweighted by the "
                "spool/MAT confidence model."
            )
        if smoothed_summary_text:
            lines.append(f"Smoothed layer: {smoothed_summary_text}")
        if diagnostic_lines:
            lines.append("Root-cause diagnostics:")
            lines.extend(f"  {line}" for line in diagnostic_lines)

        return "\n".join(lines)
