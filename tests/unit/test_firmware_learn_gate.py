"""Tests for Phase 7 Slice 7.1 — firmware-gated sample acceptance.

Covers the ``firmwareLearnGate`` opt-in hard gate in
``ReplaySampleGateService``: each rejection reason, the channel-missing
fall-back, the default-off no-regression guarantee, and the additive
behaviour when combined with the existing software-side gates.
"""
from __future__ import annotations

from datetime import UTC, datetime

from tuner.domain.datalog import DataLogRecord
from tuner.services.replay_sample_gate_service import (
    ReplaySampleGateService,
    SampleGatingConfig,
)

_NOW = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)

# Bit constants mirror the gate implementation; if the firmware bit layout
# ever changes these tests are the canary.
_FULL_SYNC = 0x10
_TRANSIENT = 0x20
_WARMUP    = 0x40
_LEARN_OK  = 0x80


def _record(**values: float) -> DataLogRecord:
    return DataLogRecord(timestamp=_NOW, values=dict(values))


def _ok_rsa() -> int:
    return _FULL_SYNC | _LEARN_OK


# ---------------------------------------------------------------------------
# Default-off behaviour: no regression vs Phase 6 baseline
# ---------------------------------------------------------------------------

class TestDefaultOff:
    def test_default_config_does_not_enable_firmware_learn_gate(self) -> None:
        cfg = SampleGatingConfig()
        assert cfg.firmware_learn_gate_enabled is False

    def test_default_off_ignores_runtimeStatusA_even_when_present(self) -> None:
        svc = ReplaySampleGateService()
        # All four rejection reasons asserted at once; gate is off so
        # acceptance must follow the software-side gate alone.
        rec = _record(
            rpm=2000.0, afr=14.7, coolant=85.0,
            runtimeStatusA=float(_TRANSIENT),  # bit set, but gate is off
        )
        assert svc.is_accepted(rec) is True


# ---------------------------------------------------------------------------
# Channel-missing fall-back: never causes a regression
# ---------------------------------------------------------------------------

class TestFallback:
    _CFG = SampleGatingConfig(
        enabled_gates=frozenset({"firmwareLearnGate"}),
        firmware_learn_gate_enabled=True,
    )

    def test_accepts_when_runtimeStatusA_channel_absent(self) -> None:
        svc = ReplaySampleGateService()
        # No runtimeStatusA in values — Phase 6 logs and offline replay
        # must continue to be accepted.
        assert svc.is_accepted(_record(rpm=2000.0, afr=14.7), self._CFG) is True

    def test_accepts_alternate_channel_name_statusA(self) -> None:
        svc = ReplaySampleGateService()
        rec = _record(rpm=2000.0, statusA=float(_ok_rsa()))
        assert svc.is_accepted(rec, self._CFG) is True


# ---------------------------------------------------------------------------
# Each rejection reason
# ---------------------------------------------------------------------------

class TestRejectionReasons:
    _CFG = SampleGatingConfig(
        enabled_gates=frozenset({"firmwareLearnGate"}),
        firmware_learn_gate_enabled=True,
    )

    def _reject(self, rsa: int) -> str:
        svc = ReplaySampleGateService()
        rec = _record(runtimeStatusA=float(rsa))
        rejection = svc.primary_rejection(rec, self._CFG)
        assert rejection is not None
        assert rejection.gate_name == "firmwareLearnGate"
        return rejection.reason

    def test_rejects_when_full_sync_clear(self) -> None:
        # tuneLearnValid set, fullSync clear → still rejected
        reason = self._reject(_LEARN_OK)
        assert "!fullSync" in reason

    def test_rejects_when_transient_active(self) -> None:
        reason = self._reject(_FULL_SYNC | _LEARN_OK | _TRANSIENT)
        assert "transientActive" in reason

    def test_rejects_when_warmup_or_ase_active(self) -> None:
        reason = self._reject(_FULL_SYNC | _LEARN_OK | _WARMUP)
        assert "warmupOrASEActive" in reason

    def test_rejects_when_tune_learn_valid_clear(self) -> None:
        reason = self._reject(_FULL_SYNC)
        assert "!tuneLearnValid" in reason

    def test_accepts_when_all_bits_compose_valid_learn(self) -> None:
        svc = ReplaySampleGateService()
        rec = _record(runtimeStatusA=float(_FULL_SYNC | _LEARN_OK))
        assert svc.is_accepted(rec, self._CFG) is True


# ---------------------------------------------------------------------------
# Additive interaction with software-side gates
# ---------------------------------------------------------------------------

class TestAdditiveBehaviour:
    def test_firmware_gate_runs_first_when_enabled(self) -> None:
        """Operator should see the firmware reason rather than a downstream
        software reason when both would reject the same record. This makes
        the operator's primary message reflect the strongest signal."""
        cfg = SampleGatingConfig(firmware_learn_gate_enabled=True)
        svc = ReplaySampleGateService()
        # Both: firmware says transient AND lambda is dead.
        rec = _record(runtimeStatusA=float(_FULL_SYNC | _LEARN_OK | _TRANSIENT))
        rejection = svc.primary_rejection(rec, cfg)
        assert rejection is not None
        assert rejection.gate_name == "firmwareLearnGate"

    def test_firmware_gate_does_not_replace_software_gates(self) -> None:
        """When the firmware gate accepts (or falls back), software gates
        still run and can reject — proving the firmware gate is *additional*."""
        cfg = SampleGatingConfig(firmware_learn_gate_enabled=True)
        svc = ReplaySampleGateService()
        # No runtimeStatusA → firmware gate falls back to accept;
        # std_DeadLambda still rejects on missing AFR.
        rec = _record(rpm=2000.0)
        rejection = svc.primary_rejection(rec, cfg)
        assert rejection is not None
        assert rejection.gate_name == "std_DeadLambda"

    def test_phase6_baseline_log_unchanged_with_gate_disabled(self) -> None:
        """Same record set, gate off vs. gate on with no runtimeStatusA →
        identical accept/reject decisions. This is the Phase 6 no-regression
        guarantee from the Phase 7 hard rules."""
        svc = ReplaySampleGateService()
        records = [
            _record(rpm=2000.0, afr=14.7, coolant=85.0),     # accepted
            _record(rpm=2000.0, afr=99.0, coolant=85.0),     # std_DeadLambda
            _record(rpm=2000.0, afr=14.7, coolant=20.0),     # minCltFilter
        ]
        off = SampleGatingConfig()
        on  = SampleGatingConfig(firmware_learn_gate_enabled=True)
        for rec in records:
            assert svc.is_accepted(rec, off) == svc.is_accepted(rec, on)
