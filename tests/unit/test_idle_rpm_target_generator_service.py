"""Tests for IdleRpmTargetGeneratorService."""
from __future__ import annotations

import pytest

from tuner.domain.generator_context import ForcedInductionTopology, GeneratorInputContext
from tuner.domain.operator_engine_context import CalibrationIntent
from tuner.services.idle_rpm_target_generator_service import (
    IdleRpmTargetGeneratorService,
    _IAC_BINS,
    _IAC_BIN_COUNT,
    _RPM_MAX,
    _RPM_MIN,
)


def _svc() -> IdleRpmTargetGeneratorService:
    return IdleRpmTargetGeneratorService()


def _ctx(**kwargs) -> GeneratorInputContext:
    return GeneratorInputContext(**kwargs)


# ===========================================================================
# Shape and bin constraints
# ===========================================================================

class TestShape:

    def test_result_has_correct_bin_count(self) -> None:
        result = _svc().generate(_ctx())
        assert len(result.clt_bins) == _IAC_BIN_COUNT

    def test_result_has_correct_target_count(self) -> None:
        result = _svc().generate(_ctx())
        assert len(result.rpm_targets) == _IAC_BIN_COUNT

    def test_bins_match_reference(self) -> None:
        result = _svc().generate(_ctx())
        assert result.clt_bins == _IAC_BINS

    def test_bins_are_monotonically_increasing(self) -> None:
        result = _svc().generate(_ctx())
        bins = list(result.clt_bins)
        assert all(bins[i] < bins[i + 1] for i in range(len(bins) - 1))

    def test_targets_are_monotonically_decreasing(self) -> None:
        """Idle RPM should taper from cold to warm."""
        result = _svc().generate(_ctx())
        targets = list(result.rpm_targets)
        assert all(targets[i] >= targets[i + 1] for i in range(len(targets) - 1))

    def test_cold_idle_higher_than_warm_idle(self) -> None:
        result = _svc().generate(_ctx())
        assert result.rpm_targets[0] > result.rpm_targets[-1]

    def test_all_targets_within_rpm_range(self) -> None:
        result = _svc().generate(_ctx())
        for target in result.rpm_targets:
            assert _RPM_MIN <= target <= _RPM_MAX

    def test_targets_rounded_to_10_rpm(self) -> None:
        result = _svc().generate(_ctx())
        for target in result.rpm_targets:
            assert target % 10 == 0


# ===========================================================================
# Warm idle values
# ===========================================================================

class TestWarmIdle:

    def test_warm_idle_is_reasonable_for_na(self) -> None:
        """NA warm idle should be in a sensible range (700–950 RPM)."""
        result = _svc().generate(_ctx())
        warm = result.rpm_targets[-1]
        assert 700 <= warm <= 950

    def test_boosted_engine_has_higher_warm_idle(self) -> None:
        na = _svc().generate(_ctx())
        boosted = _svc().generate(
            _ctx(forced_induction_topology=ForcedInductionTopology.SINGLE_TURBO)
        )
        assert boosted.rpm_targets[-1] >= na.rpm_targets[-1]

    def test_high_cam_raises_warm_idle(self) -> None:
        stock = _svc().generate(_ctx(cam_duration_deg=230.0))
        hot_cam = _svc().generate(_ctx(cam_duration_deg=280.0))
        assert hot_cam.rpm_targets[-1] > stock.rpm_targets[-1]

    def test_itb_manifold_raises_warm_idle(self) -> None:
        plenum = _svc().generate(_ctx(intake_manifold_style="long_runner_plenum"))
        itb = _svc().generate(_ctx(intake_manifold_style="itb"))
        assert itb.rpm_targets[-1] > plenum.rpm_targets[-1]

    def test_race_ported_head_raises_warm_idle(self) -> None:
        stock = _svc().generate(_ctx())
        ported = _svc().generate(_ctx(head_flow_class="race_ported"))
        assert ported.rpm_targets[-1] > stock.rpm_targets[-1]


# ===========================================================================
# Cold idle values
# ===========================================================================

class TestColdIdle:

    def test_first_start_cold_idle_higher_than_drivable_base(self) -> None:
        first_start = _svc().generate(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert first_start.rpm_targets[0] >= drivable.rpm_targets[0]

    def test_cold_idle_is_reasonable(self) -> None:
        """Cold idle should not be absurdly high or match warm idle."""
        result = _svc().generate(_ctx())
        cold = result.rpm_targets[0]
        warm = result.rpm_targets[-1]
        assert cold >= warm + 200   # at least 200 RPM cold bump
        assert cold <= 2000         # not absurdly high

    def test_high_cam_raises_cold_idle(self) -> None:
        stock = _svc().generate(_ctx())
        hot_cam = _svc().generate(_ctx(cam_duration_deg=280.0))
        assert hot_cam.rpm_targets[0] > stock.rpm_targets[0]

    def test_itb_manifold_raises_cold_idle(self) -> None:
        base = _svc().generate(_ctx())
        itb = _svc().generate(_ctx(intake_manifold_style="itb"))
        assert itb.rpm_targets[0] > base.rpm_targets[0]


# ===========================================================================
# Warnings
# ===========================================================================

class TestWarnings:

    def test_no_cam_warning_without_cam(self) -> None:
        result = _svc().generate(_ctx())
        assert any("cam" in w.lower() for w in result.warnings)

    def test_no_warning_when_cam_provided(self) -> None:
        result = _svc().generate(_ctx(cam_duration_deg=240.0))
        cam_warnings = [w for w in result.warnings if "cam" in w.lower()]
        assert len(cam_warnings) == 0

    def test_high_cam_warning_issued(self) -> None:
        result = _svc().generate(_ctx(cam_duration_deg=290.0))
        assert any("cam" in w.lower() or "high" in w.lower() for w in result.warnings)

    def test_itb_warning_issued(self) -> None:
        result = _svc().generate(_ctx(intake_manifold_style="itb"))
        assert any("itb" in w.lower() for w in result.warnings)


# ===========================================================================
# Summary
# ===========================================================================

class TestSummary:

    def test_summary_is_non_empty(self) -> None:
        result = _svc().generate(_ctx())
        assert result.summary.strip()

    def test_summary_mentions_warm_rpm(self) -> None:
        result = _svc().generate(_ctx())
        assert "RPM" in result.summary

    def test_summary_distinguishes_intent(self) -> None:
        first_start = _svc().generate(_ctx(), CalibrationIntent.FIRST_START)
        drivable = _svc().generate(_ctx(), CalibrationIntent.DRIVABLE_BASE)
        assert "first-start" in first_start.summary
        assert "drivable" in drivable.summary


# ===========================================================================
# Result helpers
# ===========================================================================

class TestHelpers:

    def test_as_bins_list_returns_list(self) -> None:
        result = _svc().generate(_ctx())
        assert isinstance(result.as_bins_list(), list)
        assert len(result.as_bins_list()) == _IAC_BIN_COUNT

    def test_as_targets_list_returns_list(self) -> None:
        result = _svc().generate(_ctx())
        assert isinstance(result.as_targets_list(), list)
        assert len(result.as_targets_list()) == _IAC_BIN_COUNT
