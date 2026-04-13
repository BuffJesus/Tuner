"""Tests for Phase 7 Slice 7.3 — confidence and coverage reporting.

Covers:
- Continuous confidence_score in [0, 1] for each VeAnalysisCellCorrection
- Confidence math saturates near 1.0 for large samples and lines up with
  the existing categorical thresholds (n=10 → ~0.63, n=30 → ~0.95)
- Full-grid VeAnalysisCoverage map: every table cell is present, visited
  cells flagged, coverage_ratio computed correctly
- VeAnalyzeReviewService surfaces a coverage line in the detail text
"""
from __future__ import annotations

from datetime import UTC, datetime

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.tuning_pages import TuningPageState, TuningPageStateKind
from tuner.services.replay_sample_gate_service import SampleGatingConfig
from tuner.services.table_view_service import TableViewModel
from tuner.services.tuning_workspace_presenter import TablePageSnapshot
from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalyzeCellHitService,
    _confidence_score,
)
from tuner.services.ve_analyze_review_service import VeAnalyzeReviewService

_NOW = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
_NO_GATE = SampleGatingConfig(enabled_gates=frozenset())


def _snapshot() -> TablePageSnapshot:
    return TablePageSnapshot(
        page_id="ve",
        group_id="fuel",
        title="VE Table",
        state=TuningPageState(kind=TuningPageStateKind.CLEAN),
        summary="",
        validation_summary="",
        diff_summary="",
        diff_text="",
        diff_entries=(),
        axis_summary="",
        details_text="",
        help_topic=None,
        x_parameter_name="rpmBins",
        y_parameter_name="loadBins",
        x_labels=("500", "1000", "1500"),
        y_labels=("30", "60"),
        table_model=TableViewModel(
            rows=2, columns=3,
            cells=[["50", "55", "60"], ["65", "70", "75"]],
        ),
        auxiliary_sections=(),
        can_undo=False,
        can_redo=False,
    )


def _rec(rpm: float, map_: float, lambda_: float) -> DataLogRecord:
    return DataLogRecord(timestamp=_NOW, values={"rpm": rpm, "map": map_, "lambda": lambda_})


# ---------------------------------------------------------------------------
# Continuous confidence score
# ---------------------------------------------------------------------------

class TestConfidenceScore:
    def test_zero_samples_score_zero(self) -> None:
        assert _confidence_score(0) == 0.0

    def test_score_is_monotonic_in_sample_count(self) -> None:
        scores = [_confidence_score(n) for n in range(0, 50)]
        assert scores == sorted(scores)

    def test_score_aligns_with_categorical_thresholds(self) -> None:
        # n=10 corresponds to "medium" cutoff in the categorical scheme
        # and should map to ~0.63 (1 - 1/e). n=30 ≈ 0.95 ("high").
        assert 0.62 < _confidence_score(10) < 0.64
        assert 0.94 < _confidence_score(30) < 0.96

    def test_score_saturates_at_one(self) -> None:
        assert _confidence_score(1000) == 1.0
        assert _confidence_score(100) > 0.999


# ---------------------------------------------------------------------------
# Per-cell correction carries the confidence score
# ---------------------------------------------------------------------------

class TestCellCorrectionConfidenceScore:
    def test_correction_includes_confidence_score(self) -> None:
        records = [_rec(500.0, 30.0, 1.05), _rec(500.0, 30.0, 1.05)]
        log = DataLog(name="t", records=records)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        assert len(result.cell_corrections) == 1
        cell = result.cell_corrections[0]
        assert cell.confidence_score == _confidence_score(2)
        assert 0.0 < cell.confidence_score < 1.0


# ---------------------------------------------------------------------------
# Full-grid coverage map
# ---------------------------------------------------------------------------

class TestCoverageMap:
    def test_coverage_map_covers_full_table(self) -> None:
        records = [_rec(500.0, 30.0, 1.05)]  # one sample → cell (0,0)
        log = DataLog(name="t", records=records)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        cov = result.coverage
        assert cov is not None
        assert cov.rows == 2
        assert cov.columns == 3
        assert cov.total_count == 6
        assert cov.visited_count == 1
        assert cov.coverage_ratio == 1 / 6
        # Spot check: every grid cell is present
        flat_cells = [c for row in cov.cells for c in row]
        assert len(flat_cells) == 6
        visited = [c for c in flat_cells if c.status == "visited"]
        assert len(visited) == 1
        assert visited[0].sample_count == 1

    def test_coverage_map_zero_visited_when_no_records(self) -> None:
        log = DataLog(name="t", records=[])
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        cov = result.coverage
        assert cov is not None
        assert cov.visited_count == 0
        assert cov.coverage_ratio == 0.0
        for row in cov.cells:
            for cell in row:
                assert cell.status == "unvisited"
                assert cell.sample_count == 0
                assert cell.confidence_score == 0.0

    def test_unvisited_cells_have_zero_confidence(self) -> None:
        records = [_rec(500.0, 30.0, 1.05)]
        log = DataLog(name="t", records=records)
        result = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        cov = result.coverage
        assert cov is not None
        unvisited = [c for row in cov.cells for c in row if c.status == "unvisited"]
        assert len(unvisited) == 5
        assert all(c.confidence_score == 0.0 for c in unvisited)


# ---------------------------------------------------------------------------
# Review service surfaces coverage
# ---------------------------------------------------------------------------

class TestReviewServiceCoverage:
    def test_review_includes_coverage_line(self) -> None:
        records = [_rec(500.0, 30.0, 1.05)]  # 1 of 6 cells
        log = DataLog(name="t", records=records)
        summary = VeAnalyzeCellHitService().analyze(
            log=log, ve_table_snapshot=_snapshot(),
            gating_config=_NO_GATE, min_samples_for_correction=1,
        )
        review = VeAnalyzeReviewService().build(summary)
        assert "Coverage:" in review.detail_text
        assert "1/6 cells" in review.detail_text
        assert "17%" in review.detail_text  # 1/6 ≈ 16.67% → "17%"

    def test_review_omits_coverage_when_summary_has_no_coverage(self) -> None:
        """Hand-built VeAnalysisSummary instances (used by some legacy
        fixtures) pass coverage=None and must not produce a coverage line."""
        from tuner.services.ve_analyze_cell_hit_service import VeAnalysisSummary
        summary = VeAnalysisSummary(
            total_records=0, accepted_records=0, rejected_records=0,
            cells_with_data=0, cells_with_proposals=0,
            cell_corrections=(), proposals=(),
            rejection_counts_by_gate=(),
            summary_text="", detail_lines=(),
        )
        review = VeAnalyzeReviewService().build(summary)
        assert "Coverage:" not in review.detail_text
