"""Phase 7 Slice 7.7 — root-cause diagnostics surface (read-only).

Inspects a ``VeAnalysisSummary`` for systematic patterns in the proposed
corrections that suggest the *real* problem is something other than VE
table cells. Read-only: no proposals are modified, no edits are staged.
The operator interprets the diagnostic and decides what to do.

Detected patterns:

- ``injector_flow_error`` — every cell biased the same direction by a
  similar magnitude. The VE table is the wrong place to fix this; the
  operator should re-check injector flow or deadtime characterization.

- ``deadtime_error`` — low-load / low-rpm cells (where pulsewidth is
  smallest, so deadtime error has the largest relative impact) share a
  common correction direction not seen in the rest of the table.

- ``target_table_error`` — high-load cells are biased in the *opposite*
  direction from low-load cells. This is the signature of an incorrect
  AFR/lambda target rather than a VE problem.

- ``sensor_calibration_error`` — corrections correlate strongly with the
  load axis (row index). MAP, IAT, or baro miscalibration distorts the
  apparent VE in a load-correlated way.

Each rule is closed-form, conservative, and triggered only by clear
patterns; the goal is to be useful when the diagnostic fires and silent
otherwise. Diagnostics are advisory — the operator stages whatever they
choose.
"""
from __future__ import annotations

from dataclasses import dataclass

from tuner.services.ve_analyze_cell_hit_service import (
    VeAnalysisProposal,
    VeAnalysisSummary,
)


@dataclass(slots=True, frozen=True)
class RootCauseDiagnostic:
    """One advisory diagnostic produced by the root-cause inspector."""

    rule: str               # stable identifier, e.g. "injector_flow_error"
    severity: str           # "info" | "warning"
    message: str            # operator-facing summary
    evidence_cells: tuple[tuple[int, int], ...]  # cells that triggered the rule


@dataclass(slots=True, frozen=True)
class RootCauseDiagnosticReport:
    diagnostics: tuple[RootCauseDiagnostic, ...]
    summary_text: str

    @property
    def has_findings(self) -> bool:
        return bool(self.diagnostics)


class VeRootCauseDiagnosticsService:
    """Stateless inspector — call ``diagnose(summary)`` to get a report."""

    # Minimum number of proposals before any rule fires. Below this the
    # report is empty so noisy partial datalogs don't surface false leads.
    _MIN_PROPOSALS = 6

    # Magnitudes — kept conservative on purpose. A diagnostic should fire
    # only when the pattern is obvious to a human inspecting the table.
    _UNIFORM_BIAS_THRESHOLD = 0.05      # mean cf must be > 5% from 1.0
    _UNIFORM_BIAS_VARIANCE_MAX = 0.0025  # std-dev² across cells must be small
    _DEADTIME_REGION_BIAS = 0.08         # low-load region 8% biased
    _OPPOSITE_REGION_BIAS = 0.05         # both regions ≥5% from 1.0
    _LOAD_CORRELATION_THRESHOLD = 0.7    # |Pearson r| ≥ 0.7

    def diagnose(self, summary: VeAnalysisSummary) -> RootCauseDiagnosticReport:
        proposals = summary.proposals
        if len(proposals) < self._MIN_PROPOSALS:
            return RootCauseDiagnosticReport(
                diagnostics=(),
                summary_text=(
                    f"Root-cause diagnostics: only {len(proposals)} proposal(s) "
                    f"— need ≥{self._MIN_PROPOSALS} before patterns are reliable."
                ),
            )

        findings: list[RootCauseDiagnostic] = []

        # Each rule is independent and may fire alongside the others.
        for rule_fn in (
            self._check_uniform_global_bias,
            self._check_deadtime_low_load_bias,
            self._check_opposite_high_low_load_bias,
            self._check_load_axis_correlation,
        ):
            finding = rule_fn(proposals)
            if finding is not None:
                findings.append(finding)

        if findings:
            summary_text = (
                f"Root-cause diagnostics: {len(findings)} pattern(s) found "
                f"({', '.join(f.rule for f in findings)})."
            )
        else:
            summary_text = (
                f"Root-cause diagnostics: no systemic patterns found across "
                f"{len(proposals)} proposal(s)."
            )

        return RootCauseDiagnosticReport(
            diagnostics=tuple(findings),
            summary_text=summary_text,
        )

    # ------------------------------------------------------------------
    # Individual rules
    # ------------------------------------------------------------------

    def _check_uniform_global_bias(
        self, proposals: tuple[VeAnalysisProposal, ...]
    ) -> RootCauseDiagnostic | None:
        """Every cell biased the same direction by similar magnitude →
        looks like an injector flow / deadtime characterization error
        rather than a VE problem."""
        cfs = [p.correction_factor for p in proposals]
        mean_cf = sum(cfs) / len(cfs)
        bias = mean_cf - 1.0
        if abs(bias) < self._UNIFORM_BIAS_THRESHOLD:
            return None
        # Variance check: every cell should be close to the mean.
        variance = sum((cf - mean_cf) ** 2 for cf in cfs) / len(cfs)
        if variance > self._UNIFORM_BIAS_VARIANCE_MAX:
            return None
        direction = "lean" if bias > 0 else "rich"
        return RootCauseDiagnostic(
            rule="injector_flow_error",
            severity="warning",
            message=(
                f"All cells biased {direction} by ~{bias * 100:+.0f}% with low "
                "variance — re-check injector flow rating and deadtime curve "
                "before staging VE corrections."
            ),
            evidence_cells=tuple((p.row_index, p.col_index) for p in proposals),
        )

    def _check_deadtime_low_load_bias(
        self, proposals: tuple[VeAnalysisProposal, ...]
    ) -> RootCauseDiagnostic | None:
        """Cells in the bottom-left quadrant (low load, low rpm) share a
        common correction sign that doesn't match the rest of the table.
        Idle/cruise pulsewidths are smallest, so deadtime error shows up
        there first."""
        if not proposals:
            return None
        max_row = max(p.row_index for p in proposals)
        max_col = max(p.col_index for p in proposals)
        if max_row < 2 or max_col < 2:
            return None  # Table too small for region analysis
        row_split = max_row // 2
        col_split = max_col // 2
        low_region = [
            p for p in proposals
            if p.row_index <= row_split and p.col_index <= col_split
        ]
        rest = [
            p for p in proposals
            if not (p.row_index <= row_split and p.col_index <= col_split)
        ]
        if len(low_region) < 2 or len(rest) < 2:
            return None
        low_mean = sum(p.correction_factor for p in low_region) / len(low_region)
        rest_mean = sum(p.correction_factor for p in rest) / len(rest)
        low_bias = low_mean - 1.0
        rest_bias = rest_mean - 1.0
        if abs(low_bias) < self._DEADTIME_REGION_BIAS:
            return None
        # Same-sign would be caught by uniform-global; deadtime fires
        # when the low-load region is meaningfully MORE biased than the
        # rest, suggesting the low-pw side is the source.
        if abs(low_bias) - abs(rest_bias) < self._DEADTIME_REGION_BIAS:
            return None
        direction = "lean" if low_bias > 0 else "rich"
        return RootCauseDiagnostic(
            rule="deadtime_error",
            severity="warning",
            message=(
                f"Low-load / low-rpm cells biased {direction} by "
                f"~{low_bias * 100:+.0f}% (vs {rest_bias * 100:+.0f}% elsewhere) "
                "— deadtime characterization is the most likely cause; "
                "re-check the injector deadtime curve before VE edits."
            ),
            evidence_cells=tuple(
                (p.row_index, p.col_index) for p in low_region
            ),
        )

    def _check_opposite_high_low_load_bias(
        self, proposals: tuple[VeAnalysisProposal, ...]
    ) -> RootCauseDiagnostic | None:
        """High-load cells biased opposite from low-load cells →
        AFR/lambda target table is wrong, not VE."""
        if not proposals:
            return None
        max_row = max(p.row_index for p in proposals)
        if max_row < 2:
            return None
        row_split = max_row // 2
        low = [p for p in proposals if p.row_index <= row_split]
        high = [p for p in proposals if p.row_index > row_split]
        if len(low) < 2 or len(high) < 2:
            return None
        low_bias = sum(p.correction_factor for p in low) / len(low) - 1.0
        high_bias = sum(p.correction_factor for p in high) / len(high) - 1.0
        if (
            abs(low_bias) < self._OPPOSITE_REGION_BIAS
            or abs(high_bias) < self._OPPOSITE_REGION_BIAS
        ):
            return None
        if (low_bias > 0) == (high_bias > 0):
            return None  # same direction → not opposite
        return RootCauseDiagnostic(
            rule="target_table_error",
            severity="info",
            message=(
                f"Low-load region biased {low_bias * 100:+.0f}% while "
                f"high-load region biased {high_bias * 100:+.0f}% — opposite "
                "directions across the load axis suggest an AFR/lambda "
                "target table problem, not a VE problem."
            ),
            evidence_cells=tuple((p.row_index, p.col_index) for p in (*low, *high)),
        )

    def _check_load_axis_correlation(
        self, proposals: tuple[VeAnalysisProposal, ...]
    ) -> RootCauseDiagnostic | None:
        """Strong linear correlation between row index (load) and
        correction factor → MAP/IAT/baro calibration is the more likely
        culprit than VE."""
        if len(proposals) < self._MIN_PROPOSALS:
            return None
        xs = [float(p.row_index) for p in proposals]
        ys = [p.correction_factor for p in proposals]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x == 0 or var_y == 0:
            return None
        r = cov / (var_x ** 0.5 * var_y ** 0.5)
        if abs(r) < self._LOAD_CORRELATION_THRESHOLD:
            return None
        return RootCauseDiagnostic(
            rule="sensor_calibration_error",
            severity="info",
            message=(
                f"Correction factor correlates with load axis (Pearson r="
                f"{r:+.2f}) — MAP/IAT/baro calibration is a more likely "
                "explanation than VE table error; verify sensor scaling "
                "before staging VE edits."
            ),
            evidence_cells=tuple((p.row_index, p.col_index) for p in proposals),
        )
