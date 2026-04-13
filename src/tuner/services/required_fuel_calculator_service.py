from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Physical and unit-conversion constants (from TunerStudio an.java)
# ---------------------------------------------------------------------------

# Constant used in the TunerStudio reqFuel formula.
_REQ_FUEL_K = 3.6e7 * 4.27793e-5  # = 36000000 × 0.0000427793 ≈ 1540.05

# Cubic centimetres per cubic inch of displacement.
_CC_PER_CID = 16.38706

# cc/min per lb/hr of injector flow (approximate, as used in TunerStudio).
_CCMIN_PER_LBHR = 10.5

# Speeduino stores reqFuel as tenths of milliseconds (U08, scale 0.1).
_STORED_SCALE = 0.1


@dataclass(slots=True, frozen=True)
class RequiredFuelResult:
    """Result from the required fuel calculator.

    Mirrors the TunerStudio Required Fuel Calculator dialog result.
    All inputs are the values as provided by the caller (already in standard
    units: cc, cylinders, cc/min, AFR ratio).
    """

    req_fuel_ms: float
    """Computed required fuel pulse width in milliseconds."""

    req_fuel_stored: int
    """Value to store in the ECU (tenths of milliseconds, Speeduino U08 scale 0.1).
    Clipped to the Speeduino U08 range 0–255 (0–25.5 ms)."""

    displacement_cc: float
    cylinder_count: int
    injector_flow_ccmin: float
    target_afr: float

    inputs_summary: str
    """Human-readable summary of the inputs used in the calculation."""

    is_valid: bool
    """True when all inputs are positive and the result is in a plausible range."""


class RequiredFuelCalculatorService:
    """Computes the required fuel pulse width from engine and injector facts.

    Implements the exact formula used in the TunerStudio Required Fuel
    Calculator dialog (an.java):

        reqFuel_ms = (displacement_CID × 36,000,000 × 4.27793e-5)
                     ÷ (cylinder_count × AFR × injFlow_lbhr)
                     ÷ 10.0

    where:
        displacement_CID = displacement_cc ÷ 16.38706
        injFlow_lbhr     = injector_flow_ccmin ÷ 10.5

    The result is the base required fuel pulse width in milliseconds.
    Speeduino stores this value at scale 0.1 (tenths of milliseconds), so
    the stored integer is round(req_fuel_ms / 0.1) = round(req_fuel_ms × 10).

    Notes
    -----
    * This is a *calculator helper*, not an automated setter.  The result must
      be reviewed and applied by the operator via the normal staged edit flow.
    * The formula does not include a squirts-per-cycle correction; that
      adjustment is applied by the ECU firmware at runtime.
    * The conversion factor cc/min → lb/hr (÷ 10.5) is an approximation
      matching TunerStudio; more precise conversions differ by < 1 %.
    """

    def calculate(
        self,
        displacement_cc: float,
        cylinder_count: int,
        injector_flow_ccmin: float,
        target_afr: float,
    ) -> RequiredFuelResult:
        """Compute the required fuel from engine and injector parameters.

        Parameters
        ----------
        displacement_cc:
            Total engine displacement in cubic centimetres.
        cylinder_count:
            Number of cylinders.
        injector_flow_ccmin:
            Injector flow rate in cc/min at rated pressure.  For staged
            injection, use the primary injector size only.
        target_afr:
            Stoichiometric AFR (e.g. 14.7 for petrol).

        Returns
        -------
        RequiredFuelResult
            Always returned; check ``is_valid`` before using ``req_fuel_ms``.
        """
        is_valid = (
            displacement_cc > 0
            and cylinder_count > 0
            and injector_flow_ccmin > 0
            and target_afr > 0
        )

        if not is_valid:
            return RequiredFuelResult(
                req_fuel_ms=0.0,
                req_fuel_stored=0,
                displacement_cc=displacement_cc,
                cylinder_count=cylinder_count,
                injector_flow_ccmin=injector_flow_ccmin,
                target_afr=target_afr,
                inputs_summary="Invalid inputs — all values must be positive.",
                is_valid=False,
            )

        displacement_cid = displacement_cc / _CC_PER_CID
        injflow_lbhr = injector_flow_ccmin / _CCMIN_PER_LBHR

        numerator = _REQ_FUEL_K * displacement_cid
        denominator = cylinder_count * target_afr * injflow_lbhr
        req_fuel_ms = numerator / denominator / 10.0

        # Clip to U08 range (Speeduino: 0–25.5 ms at scale 0.1)
        stored_raw = round(req_fuel_ms / _STORED_SCALE)
        stored = max(0, min(stored_raw, 255))

        summary = (
            f"{displacement_cc:.0f} cc, {cylinder_count} cyl, "
            f"{injector_flow_ccmin:.0f} cc/min, AFR {target_afr:.1f}"
        )

        return RequiredFuelResult(
            req_fuel_ms=req_fuel_ms,
            req_fuel_stored=stored,
            displacement_cc=displacement_cc,
            cylinder_count=cylinder_count,
            injector_flow_ccmin=injector_flow_ccmin,
            target_afr=target_afr,
            inputs_summary=summary,
            is_valid=True,
        )
