"""Operator-facing review text for WUE Analyze proposals.

Mirrors VeAnalyzeReviewService but for the 1-D WUE table corrections.
"""

from __future__ import annotations

from dataclasses import dataclass

from tuner.services.wue_analyze_service import WueAnalysisProposal, WueAnalysisSummary


@dataclass(slots=True, frozen=True)
class WueAnalyzeReviewSnapshot:
    """Operator-facing review of a WueAnalysisSummary."""

    summary_text: str
    detail_text: str
    confidence_distribution: tuple[tuple[str, int], ...]
    largest_lean_corrections: tuple[WueAnalysisProposal, ...]
    largest_rich_corrections: tuple[WueAnalysisProposal, ...]
    rows_insufficient: int
    max_preview_entries: int = 5


class WueAnalyzeReviewService:
    """Build an operator-facing review snapshot from a ``WueAnalysisSummary``."""

    _PREVIEW_COUNT = 5

    def build(self, summary: WueAnalysisSummary) -> WueAnalyzeReviewSnapshot:
        dist: dict[str, int] = {"insufficient": 0, "low": 0, "medium": 0, "high": 0}
        rows_insufficient = 0
        for rc in summary.row_corrections:
            dist[rc.confidence] = dist.get(rc.confidence, 0) + 1
            if rc.proposed_enrichment is None and rc.current_enrichment is not None:
                rows_insufficient += 1

        confidence_distribution = tuple(
            (level, dist[level]) for level in ("insufficient", "low", "medium", "high")
        )

        lean = sorted(
            (p for p in summary.proposals if p.correction_factor > 1.0),
            key=lambda p: p.correction_factor,
            reverse=True,
        )
        rich = sorted(
            (p for p in summary.proposals if p.correction_factor < 1.0),
            key=lambda p: p.correction_factor,
        )
        largest_lean = tuple(lean[: self._PREVIEW_COUNT])
        largest_rich = tuple(rich[: self._PREVIEW_COUNT])

        summary_text = summary.summary_text
        detail_text = self._build_detail(
            summary=summary,
            confidence_distribution=confidence_distribution,
            largest_lean=largest_lean,
            largest_rich=largest_rich,
            rows_insufficient=rows_insufficient,
        )

        return WueAnalyzeReviewSnapshot(
            summary_text=summary_text,
            detail_text=detail_text,
            confidence_distribution=confidence_distribution,
            largest_lean_corrections=largest_lean,
            largest_rich_corrections=largest_rich,
            rows_insufficient=rows_insufficient,
            max_preview_entries=self._PREVIEW_COUNT,
        )

    @staticmethod
    def _build_detail(
        *,
        summary: WueAnalysisSummary,
        confidence_distribution: tuple[tuple[str, int], ...],
        largest_lean: tuple[WueAnalysisProposal, ...],
        largest_rich: tuple[WueAnalysisProposal, ...],
        rows_insufficient: int,
    ) -> str:
        lines: list[str] = [
            f"Records: {summary.accepted_records} accepted / "
            f"{summary.rejected_records} rejected / "
            f"{summary.total_records} total."
        ]
        if summary.rejection_counts_by_gate:
            lines.append(
                "Rejections: "
                + ", ".join(f"{g}={c}" for g, c in summary.rejection_counts_by_gate)
                + "."
            )
        non_zero = [(lvl, cnt) for lvl, cnt in confidence_distribution if cnt > 0]
        if non_zero:
            lines.append("Row confidence: " + ", ".join(f"{l}={c}" for l, c in non_zero) + ".")
        if rows_insufficient > 0:
            lines.append(f"Rows skipped (insufficient samples): {rows_insufficient}.")
        if largest_lean:
            text = "; ".join(
                f"row {p.row_index + 1} "
                f"{p.current_enrichment:.1f}→{p.proposed_enrichment:.1f} "
                f"×{p.correction_factor:.4f} n={p.sample_count}"
                for p in largest_lean
            )
            suffix = "…" if len(largest_lean) == 5 and summary.rows_with_proposals > 5 else ""
            lines.append(f"Largest lean corrections: {text}{suffix}.")
        if largest_rich:
            text = "; ".join(
                f"row {p.row_index + 1} "
                f"{p.current_enrichment:.1f}→{p.proposed_enrichment:.1f} "
                f"×{p.correction_factor:.4f} n={p.sample_count}"
                for p in largest_rich
            )
            suffix = "…" if len(largest_rich) == 5 and summary.rows_with_proposals > 5 else ""
            lines.append(f"Largest rich corrections: {text}{suffix}.")
        if not largest_lean and not largest_rich and summary.rows_with_proposals == 0:
            lines.append("No corrections proposed yet.")
        return "\n".join(lines)
