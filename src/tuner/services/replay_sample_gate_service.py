"""Formal sample gating for datalog replay and VE Analyze-ready evidence evaluation.

Named gates align with TunerStudio VeAnalyze filter semantics so that later Phase 6
VE Analyze parity work can reference the same gate names used in [VeAnalyze] INI sections.

Standard named gates:
  std_DeadLambda  — reject implausible or missing lambda/AFR reading
  std_xAxisMin    — reject below X-axis minimum (requires axis bounds in config)
  std_xAxisMax    — reject above X-axis maximum
  std_yAxisMin    — reject below Y-axis minimum
  std_yAxisMax    — reject above Y-axis maximum

Speeduino parametric gates (also supported as named built-ins):
  minCltFilter    — reject cold coolant (coolant < threshold, default 70 °C)
  accelFilter     — reject accel enrichment active (engine & 16)
  aseFilter       — reject after-start enrichment active (engine & 4)
  overrunFilter   — reject overrun/decel fuel cut (pulseWidth == 0)
  maxTPS          — reject wide-open throttle (throttle > threshold)
  minRPM          — reject below minimum RPM (rpm < threshold)

Phase 7 Slice 7.1 — Firmware-gated sample acceptance:
  firmwareLearnGate — opt-in hard gate driven by the firmware ``runtimeStatusA``
                      byte. Rejects samples unless ``tuneLearnValid`` (bit 7),
                      ``fullSync`` (bit 4) are set AND ``transientActive``
                      (bit 5), ``warmupOrASEActive`` (bit 6) are clear. Falls
                      back to accept if the channel is missing from the
                      record (so legacy logs and offline replay don't break).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from tuner.domain.datalog import DataLog, DataLogRecord


@dataclass(slots=True, frozen=True)
class SampleGatingConfig:
    """Controls which gates are active and their thresholds.

    ``enabled_gates`` — set of gate names to apply.  An empty set means "use
    DEFAULT_GATES".  Pass an explicit frozenset (even a non-empty one) to
    override the defaults exactly.
    """

    enabled_gates: frozenset[str] = field(default_factory=frozenset)
    afr_min: float = 7.0
    afr_max: float = 25.0
    clt_min_celsius: float = 70.0
    tps_max_percent: float = 100.0  # disabled by default; set lower to exclude WOT
    rpm_min: float = 300.0
    pulsewidth_min_ms: float = 0.0  # disabled by default; set >0 to exclude low PW
    axis_x_min: float | None = None
    axis_x_max: float | None = None
    axis_y_min: float | None = None
    axis_y_max: float | None = None
    # Runtime axis values for std_xAxis/std_yAxis gates (populated per-record by caller)
    axis_x_value: float | None = None
    axis_y_value: float | None = None
    # Phase 7 Slice 7.1 — Firmware-gated sample acceptance.
    # When True, the firmwareLearnGate is added to the active gate set and
    # samples are hard-rejected unless the firmware ``runtimeStatusA`` byte
    # advertises a valid learn condition. Default off so existing fixtures
    # and Phase 6 baselines remain bit-identical.
    firmware_learn_gate_enabled: bool = False


@dataclass(slots=True, frozen=True)
class SampleGateEval:
    """Result of evaluating one gate against one record."""

    gate_name: str
    accepted: bool
    reason: str  # human-readable; non-empty when rejected


@dataclass(slots=True, frozen=True)
class GatedSampleSummary:
    """Aggregate result of gating an entire DataLog."""

    total_count: int
    accepted_count: int
    rejected_count: int
    rejection_counts_by_gate: tuple[tuple[str, int], ...]  # gate_name → count, sorted
    summary_text: str
    detail_lines: tuple[str, ...]


# ---------------------------------------------------------------------------
# Channel name resolution helpers
# ---------------------------------------------------------------------------

_CHANNEL_ALIASES: dict[str, tuple[str, ...]] = {
    # INI name   → candidate datalog channel tokens (lowercase, substring match)
    "lambda":    ("lambda",),
    "afr":       ("afr",),
    "ego":       ("ego", "afr", "lambda"),
    "coolant":   ("coolant", "clt"),
    "engine":    ("engine", "status"),
    "pulsewidth": ("pulsewidth", "pw"),
    "throttle":  ("throttle", "tps"),
    "rpm":       ("rpm",),
    "map":       ("map",),
    "load":      ("load", "map"),
}


def _resolve_channel(name: str, values: dict[str, float]) -> float | None:
    """Resolve a named channel to a float from record values using alias matching."""
    aliases = _CHANNEL_ALIASES.get(name.lower(), (name.lower(),))
    for candidate in aliases:
        for key, value in values.items():
            if candidate in key.lower():
                return value
    return None


def _lambda_value(values: dict[str, float]) -> float | None:
    """Return the first lambda or AFR-derived value found, or None."""
    for key, value in values.items():
        k = key.lower()
        if "lambda" in k:
            return value
    for key, value in values.items():
        k = key.lower()
        if "afr" in k or "ego" in k:
            # Convert AFR to lambda (stoich gasoline 14.7)
            return value / 14.7
    return None


def _afr_value(values: dict[str, float]) -> float | None:
    for key, value in values.items():
        k = key.lower()
        if "afr" in k:
            return value
        if "lambda" in k:
            return value * 14.7
    return None


# ---------------------------------------------------------------------------
# ReplaySampleGateService
# ---------------------------------------------------------------------------

# Gate function signature: (record, config) → SampleGateEval
_GateFn = Callable[[DataLogRecord, SampleGatingConfig], SampleGateEval]


class ReplaySampleGateService:
    """Evaluate named sample gates against DataLogRecord instances.

    Gate names match Speeduino's [VeAnalyze] filter= declarations so that
    Phase 6 VE Analyze parity work can reference the same names used in INI files.
    """

    # Gates enabled when SampleGatingConfig.enabled_gates is empty.
    DEFAULT_GATES: frozenset[str] = frozenset({
        "std_DeadLambda",
        "minCltFilter",
        "accelFilter",
        "aseFilter",
        "overrunFilter",
    })

    # Priority-ordered evaluation sequence for the default gate set.
    # std_DeadLambda is first because most real-world datalogs lack an explicit
    # lambda/AFR channel name that matches our aliases, making it the most
    # common fast-reject.  Keeping it first avoids four unnecessary dict scans
    # per record on large datalogs and prevents main-thread freezes.
    _DEFAULT_GATE_ORDER: tuple[str, ...] = (
        "std_DeadLambda",
        "accelFilter",
        "aseFilter",
        "minCltFilter",
        "overrunFilter",
    )

    # Singleton default config — avoids allocating a new dataclass on every
    # record when the caller passes config=None.
    _DEFAULT_CONFIG: SampleGatingConfig = SampleGatingConfig()

    def __init__(self) -> None:
        self._registry: dict[str, _GateFn] = {
            "std_DeadLambda":  self._gate_dead_lambda,
            "std_xAxisMin":    self._gate_x_axis_min,
            "std_xAxisMax":    self._gate_x_axis_max,
            "std_yAxisMin":    self._gate_y_axis_min,
            "std_yAxisMax":    self._gate_y_axis_max,
            "minCltFilter":    self._gate_min_clt,
            "accelFilter":     self._gate_accel,
            "aseFilter":       self._gate_ase,
            "overrunFilter":   self._gate_overrun,
            "maxTPS":          self._gate_max_tps,
            "minRPM":          self._gate_min_rpm,
            "firmwareLearnGate": self._gate_firmware_learn,
        }

    def known_gate_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._registry))

    def evaluate_record(
        self,
        record: DataLogRecord,
        config: SampleGatingConfig | None = None,
    ) -> list[SampleGateEval]:
        """Evaluate all active gates against *record*.

        Returns one SampleGateEval per active gate.  Iteration stops at the
        first rejection (fail-fast), so callers get the primary reason only.
        To get all rejections, iterate manually.
        """
        cfg = config if config is not None else self._DEFAULT_CONFIG
        if cfg.enabled_gates:
            # Custom gate set: sort once for determinism, caller bears the cost.
            gate_order: tuple[str, ...] = tuple(sorted(cfg.enabled_gates))
        else:
            # Default gate set: use the pre-ordered priority sequence.
            gate_order = self._DEFAULT_GATE_ORDER
        # Phase 7 Slice 7.1: firmwareLearnGate is opt-in and runs first when
        # enabled so its rejection reason is the primary one surfaced to the
        # operator. It is added regardless of whether the caller passed a
        # custom gate set, because it is a hard *additional* gate, not a
        # replacement for the software-side gating.
        if cfg.firmware_learn_gate_enabled and "firmwareLearnGate" not in gate_order:
            gate_order = ("firmwareLearnGate",) + gate_order
        results: list[SampleGateEval] = []
        for gate_name in gate_order:
            fn = self._registry.get(gate_name)
            if fn is None:
                continue
            result = fn(record, cfg)
            results.append(result)
            if not result.accepted:
                break  # fail-fast: first rejection is the primary reason
        return results

    def is_accepted(
        self,
        record: DataLogRecord,
        config: SampleGatingConfig | None = None,
    ) -> bool:
        """Return True only if all active gates accept this record."""
        for eval_ in self.evaluate_record(record, config):
            if not eval_.accepted:
                return False
        return True

    def primary_rejection(
        self,
        record: DataLogRecord,
        config: SampleGatingConfig | None = None,
    ) -> SampleGateEval | None:
        """Return the first rejection result, or None if accepted."""
        for eval_ in self.evaluate_record(record, config):
            if not eval_.accepted:
                return eval_
        return None

    def gate_log(
        self,
        log: DataLog,
        config: SampleGatingConfig | None = None,
    ) -> GatedSampleSummary:
        """Gate all records in *log* and return an aggregate summary."""
        cfg = config or SampleGatingConfig()
        total = len(log.records)
        accepted = 0
        rejected = 0
        rejection_counts: dict[str, int] = {}

        for record in log.records:
            evals = self.evaluate_record(record, cfg)
            rejection = next((e for e in evals if not e.accepted), None)
            if rejection is None:
                accepted += 1
            else:
                rejected += 1
                rejection_counts[rejection.gate_name] = (
                    rejection_counts.get(rejection.gate_name, 0) + 1
                )

        sorted_rejections = tuple(sorted(rejection_counts.items()))
        summary = (
            f"Sample gating: {accepted} accepted, {rejected} rejected of {total} total."
        )
        detail_lines: list[str] = [summary]
        if sorted_rejections:
            gate_detail = "Rejections by gate: " + ", ".join(
                f"{gate}={count}" for gate, count in sorted_rejections
            ) + "."
            detail_lines.append(gate_detail)
        else:
            detail_lines.append("No rejections.")

        return GatedSampleSummary(
            total_count=total,
            accepted_count=accepted,
            rejected_count=rejected,
            rejection_counts_by_gate=sorted_rejections,
            summary_text=summary,
            detail_lines=tuple(detail_lines),
        )

    # ------------------------------------------------------------------
    # Individual gate implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _gate_dead_lambda(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject if the lambda/AFR reading is implausible or absent."""
        afr = _afr_value(record.values)
        if afr is None:
            return SampleGateEval(
                gate_name="std_DeadLambda",
                accepted=False,
                reason="no lambda/AFR channel in record",
            )
        if not (config.afr_min <= afr <= config.afr_max):
            return SampleGateEval(
                gate_name="std_DeadLambda",
                accepted=False,
                reason=(
                    f"AFR {afr:.2f} outside plausible range "
                    f"[{config.afr_min:.1f}, {config.afr_max:.1f}]"
                ),
            )
        return SampleGateEval(gate_name="std_DeadLambda", accepted=True, reason="")

    @staticmethod
    def _gate_x_axis_min(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        if config.axis_x_min is None or config.axis_x_value is None:
            return SampleGateEval(gate_name="std_xAxisMin", accepted=True, reason="")
        if config.axis_x_value < config.axis_x_min:
            return SampleGateEval(
                gate_name="std_xAxisMin",
                accepted=False,
                reason=f"X value {config.axis_x_value} below axis minimum {config.axis_x_min}",
            )
        return SampleGateEval(gate_name="std_xAxisMin", accepted=True, reason="")

    @staticmethod
    def _gate_x_axis_max(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        if config.axis_x_max is None or config.axis_x_value is None:
            return SampleGateEval(gate_name="std_xAxisMax", accepted=True, reason="")
        if config.axis_x_value > config.axis_x_max:
            return SampleGateEval(
                gate_name="std_xAxisMax",
                accepted=False,
                reason=f"X value {config.axis_x_value} above axis maximum {config.axis_x_max}",
            )
        return SampleGateEval(gate_name="std_xAxisMax", accepted=True, reason="")

    @staticmethod
    def _gate_y_axis_min(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        if config.axis_y_min is None or config.axis_y_value is None:
            return SampleGateEval(gate_name="std_yAxisMin", accepted=True, reason="")
        if config.axis_y_value < config.axis_y_min:
            return SampleGateEval(
                gate_name="std_yAxisMin",
                accepted=False,
                reason=f"Y value {config.axis_y_value} below axis minimum {config.axis_y_min}",
            )
        return SampleGateEval(gate_name="std_yAxisMin", accepted=True, reason="")

    @staticmethod
    def _gate_y_axis_max(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        if config.axis_y_max is None or config.axis_y_value is None:
            return SampleGateEval(gate_name="std_yAxisMax", accepted=True, reason="")
        if config.axis_y_value > config.axis_y_max:
            return SampleGateEval(
                gate_name="std_yAxisMax",
                accepted=False,
                reason=f"Y value {config.axis_y_value} above axis maximum {config.axis_y_max}",
            )
        return SampleGateEval(gate_name="std_yAxisMax", accepted=True, reason="")

    @staticmethod
    def _gate_min_clt(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples with coolant temperature below threshold (cold engine)."""
        clt = _resolve_channel("coolant", record.values)
        if clt is None:
            # No CLT channel — pass-through; can't gate what we can't see
            return SampleGateEval(gate_name="minCltFilter", accepted=True, reason="")
        if clt < config.clt_min_celsius:
            return SampleGateEval(
                gate_name="minCltFilter",
                accepted=False,
                reason=f"coolant {clt:.1f} °C below minimum {config.clt_min_celsius:.0f} °C",
            )
        return SampleGateEval(gate_name="minCltFilter", accepted=True, reason="")

    @staticmethod
    def _gate_accel(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples with acceleration enrichment active (engine status & 0x10)."""
        engine = _resolve_channel("engine", record.values)
        if engine is None:
            return SampleGateEval(gate_name="accelFilter", accepted=True, reason="")
        if int(engine) & 0x10:
            return SampleGateEval(
                gate_name="accelFilter",
                accepted=False,
                reason="accel enrichment active (engine & 16)",
            )
        return SampleGateEval(gate_name="accelFilter", accepted=True, reason="")

    @staticmethod
    def _gate_ase(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples with after-start enrichment active (engine status & 0x04)."""
        engine = _resolve_channel("engine", record.values)
        if engine is None:
            return SampleGateEval(gate_name="aseFilter", accepted=True, reason="")
        if int(engine) & 0x04:
            return SampleGateEval(
                gate_name="aseFilter",
                accepted=False,
                reason="after-start enrichment active (engine & 4)",
            )
        return SampleGateEval(gate_name="aseFilter", accepted=True, reason="")

    @staticmethod
    def _gate_overrun(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples during overrun/decel fuel cut (pulseWidth == 0)."""
        pw = _resolve_channel("pulsewidth", record.values)
        if pw is None:
            return SampleGateEval(gate_name="overrunFilter", accepted=True, reason="")
        if pw == 0.0:
            return SampleGateEval(
                gate_name="overrunFilter",
                accepted=False,
                reason="overrun fuel cut (pulseWidth == 0)",
            )
        return SampleGateEval(gate_name="overrunFilter", accepted=True, reason="")

    @staticmethod
    def _gate_max_tps(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples above TPS threshold (wide-open throttle)."""
        tps = _resolve_channel("throttle", record.values)
        if tps is None:
            return SampleGateEval(gate_name="maxTPS", accepted=True, reason="")
        if tps > config.tps_max_percent:
            return SampleGateEval(
                gate_name="maxTPS",
                accepted=False,
                reason=f"TPS {tps:.1f}% above maximum {config.tps_max_percent:.0f}%",
            )
        return SampleGateEval(gate_name="maxTPS", accepted=True, reason="")

    @staticmethod
    def _gate_min_rpm(record: DataLogRecord, config: SampleGatingConfig) -> SampleGateEval:
        """Reject samples below minimum RPM."""
        rpm = _resolve_channel("rpm", record.values)
        if rpm is None:
            return SampleGateEval(gate_name="minRPM", accepted=True, reason="")
        if rpm < config.rpm_min:
            return SampleGateEval(
                gate_name="minRPM",
                accepted=False,
                reason=f"RPM {rpm:.0f} below minimum {config.rpm_min:.0f}",
            )
        return SampleGateEval(gate_name="minRPM", accepted=True, reason="")

    # ------------------------------------------------------------------
    # Phase 7 Slice 7.1 — Firmware-gated sample acceptance
    # ------------------------------------------------------------------

    # ``runtimeStatusA`` bit layout (per docs/tuning-roadmap.md). The
    # firmware exposes these as a single byte; the gate accepts a few
    # common channel-name variants.
    _RSA_FULL_SYNC_BIT          = 1 << 4   # 0x10
    _RSA_TRANSIENT_ACTIVE_BIT   = 1 << 5   # 0x20
    _RSA_WARMUP_ASE_BIT         = 1 << 6   # 0x40
    _RSA_TUNE_LEARN_VALID_BIT   = 1 << 7   # 0x80

    @classmethod
    def _gate_firmware_learn(
        cls, record: DataLogRecord, config: SampleGatingConfig
    ) -> SampleGateEval:
        """Hard-reject samples the firmware says are not safe to learn from.

        The firmware ``runtimeStatusA`` byte composes its own steady-state
        signal: ``tuneLearnValid && fullSync && !transientActive &&
        !warmupOrASEActive``. We re-check all four bits explicitly so that a
        firmware version that exports the bits but does not pre-compose
        ``tuneLearnValid`` still gates correctly.

        Fall-back: if the channel is missing from the record (legacy log,
        offline replay, or firmware that does not advertise the byte), the
        gate accepts. This keeps the gate strictly *additional* to the
        software-side gating — it never causes a regression on inputs that
        Phase 6 already accepted, only ever rejects more.
        """
        rsa = cls._resolve_runtime_status_a(record.values)
        if rsa is None:
            return SampleGateEval(
                gate_name="firmwareLearnGate",
                accepted=True,
                reason="",
            )
        if not (rsa & cls._RSA_FULL_SYNC_BIT):
            return SampleGateEval(
                gate_name="firmwareLearnGate",
                accepted=False,
                reason="firmware reports !fullSync (runtimeStatusA bit 4 clear)",
            )
        if rsa & cls._RSA_TRANSIENT_ACTIVE_BIT:
            return SampleGateEval(
                gate_name="firmwareLearnGate",
                accepted=False,
                reason="firmware reports transientActive (runtimeStatusA bit 5 set)",
            )
        if rsa & cls._RSA_WARMUP_ASE_BIT:
            return SampleGateEval(
                gate_name="firmwareLearnGate",
                accepted=False,
                reason="firmware reports warmupOrASEActive (runtimeStatusA bit 6 set)",
            )
        if not (rsa & cls._RSA_TUNE_LEARN_VALID_BIT):
            return SampleGateEval(
                gate_name="firmwareLearnGate",
                accepted=False,
                reason="firmware reports !tuneLearnValid (runtimeStatusA bit 7 clear)",
            )
        return SampleGateEval(gate_name="firmwareLearnGate", accepted=True, reason="")

    @staticmethod
    def _resolve_runtime_status_a(values: dict[str, float]) -> int | None:
        """Locate ``runtimeStatusA`` in record values, tolerant to naming.

        Returns the integer byte value or None when the channel is absent.
        """
        for key, value in values.items():
            k = key.lower().replace("_", "").replace(" ", "")
            if k in ("runtimestatusa", "statusa", "runtimestatus"):
                try:
                    return int(value) & 0xFF
                except (TypeError, ValueError):
                    return None
        return None
