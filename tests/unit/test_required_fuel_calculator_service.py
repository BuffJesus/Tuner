from __future__ import annotations

import math

from tuner.services.required_fuel_calculator_service import RequiredFuelCalculatorService


def _svc() -> RequiredFuelCalculatorService:
    return RequiredFuelCalculatorService()


# ---------------------------------------------------------------------------
# Formula correctness
# ---------------------------------------------------------------------------

def test_known_values_produce_expected_result() -> None:
    # Reference: TunerStudio formula with:
    #   displacement=4916cc (Ford 300 CID), 6cyl, 540cc/min, 14.7 AFR
    # Computed reference: ≈10.2 ms (displacement = 300 CID)
    result = _svc().calculate(
        displacement_cc=4916.0,
        cylinder_count=6,
        injector_flow_ccmin=540.0,
        target_afr=14.7,
    )
    assert result.is_valid
    # Should be roughly in the 9–12 ms range for this setup
    assert 8.0 < result.req_fuel_ms < 13.0


def test_formula_constants_match_tunerstudio() -> None:
    # Verify formula constants by working from first principles.
    # reqFuel = (disp_CID * 36e6 * 4.27793e-5) / (cylinders * AFR * flow_lbhr) / 10
    # disp_CID = 1000 / 16.38706 ≈ 61.024
    # flow_lbhr = 500 / 10.5 ≈ 47.619
    # numerator = 61.024 * 36e6 * 4.27793e-5 = 61.024 * 1540.055 ≈ 93979
    # denominator = 4 * 14.7 * 47.619 = 2799.9
    # result = 93979 / 2799.9 / 10 ≈ 3.356 ms
    result = _svc().calculate(
        displacement_cc=1000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert result.is_valid
    expected = (1000.0 / 16.38706 * 36e6 * 4.27793e-5) / (4 * 14.7 * (500.0 / 10.5)) / 10.0
    assert math.isclose(result.req_fuel_ms, expected, rel_tol=1e-6)


def test_4cyl_2000cc_typical_values() -> None:
    # 2000cc, 4cyl, 380cc/min injectors, 14.7 AFR → should be ~5–7ms
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=380.0,
        target_afr=14.7,
    )
    assert result.is_valid
    assert 4.0 < result.req_fuel_ms < 10.0


def test_larger_injectors_produce_smaller_reqfuel() -> None:
    small_inj = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=300.0,
        target_afr=14.7,
    )
    large_inj = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=600.0,
        target_afr=14.7,
    )
    assert small_inj.req_fuel_ms > large_inj.req_fuel_ms


def test_more_cylinders_produce_smaller_reqfuel() -> None:
    four_cyl = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    eight_cyl = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=8,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert four_cyl.req_fuel_ms > eight_cyl.req_fuel_ms


def test_larger_displacement_produces_larger_reqfuel() -> None:
    small = _svc().calculate(
        displacement_cc=1000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    large = _svc().calculate(
        displacement_cc=4000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert large.req_fuel_ms > small.req_fuel_ms


# ---------------------------------------------------------------------------
# Stored value (Speeduino U08, scale 0.1)
# ---------------------------------------------------------------------------

def test_stored_value_is_tenths_of_ms() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert result.req_fuel_stored == round(result.req_fuel_ms / 0.1)


def test_stored_value_clipped_at_255() -> None:
    # Very large displacement + tiny injectors = very large reqFuel → clip to 255
    result = _svc().calculate(
        displacement_cc=99000.0,
        cylinder_count=1,
        injector_flow_ccmin=10.0,
        target_afr=14.7,
    )
    assert result.req_fuel_stored <= 255


def test_stored_value_not_negative() -> None:
    # Pathological inputs should still return a non-negative stored value
    result = _svc().calculate(
        displacement_cc=1.0,
        cylinder_count=1,
        injector_flow_ccmin=1.0,
        target_afr=14.7,
    )
    assert result.req_fuel_stored >= 0


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------

def test_zero_displacement_is_invalid() -> None:
    result = _svc().calculate(
        displacement_cc=0.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert not result.is_valid
    assert result.req_fuel_ms == 0.0


def test_zero_cylinder_count_is_invalid() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=0,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert not result.is_valid


def test_zero_injector_flow_is_invalid() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=0.0,
        target_afr=14.7,
    )
    assert not result.is_valid


def test_zero_afr_is_invalid() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=0.0,
    )
    assert not result.is_valid


def test_negative_displacement_is_invalid() -> None:
    result = _svc().calculate(
        displacement_cc=-100.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert not result.is_valid


# ---------------------------------------------------------------------------
# Inputs summary
# ---------------------------------------------------------------------------

def test_inputs_summary_contains_displacement() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert "2000" in result.inputs_summary


def test_inputs_summary_contains_cylinder_count() -> None:
    result = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=6,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert "6" in result.inputs_summary


def test_invalid_result_has_descriptive_summary() -> None:
    result = _svc().calculate(
        displacement_cc=0.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert not result.is_valid
    assert result.inputs_summary  # should not be empty


# ---------------------------------------------------------------------------
# Unit conversion round-trip
# ---------------------------------------------------------------------------

def test_halving_injector_flow_doubles_reqfuel() -> None:
    base = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=600.0,
        target_afr=14.7,
    )
    half = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=300.0,
        target_afr=14.7,
    )
    assert math.isclose(half.req_fuel_ms, base.req_fuel_ms * 2.0, rel_tol=1e-6)


def test_doubling_displacement_doubles_reqfuel() -> None:
    base = _svc().calculate(
        displacement_cc=1000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    doubled = _svc().calculate(
        displacement_cc=2000.0,
        cylinder_count=4,
        injector_flow_ccmin=500.0,
        target_afr=14.7,
    )
    assert math.isclose(doubled.req_fuel_ms, base.req_fuel_ms * 2.0, rel_tol=1e-6)
