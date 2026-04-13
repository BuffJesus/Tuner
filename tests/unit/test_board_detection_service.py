from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.session import SessionInfo
from tuner.domain.tune import TuneFile
from tuner.services.board_detection_service import BoardDetectionService


# ---------------------------------------------------------------------------
# Text-heuristic baseline (existing coverage)
# ---------------------------------------------------------------------------

def test_detects_teensy41_from_definition_signature() -> None:
    service = BoardDetectionService()

    result = service.detect(definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41"))

    assert result == BoardFamily.TEENSY41


def test_detects_teensy41_from_tune_firmware_info() -> None:
    service = BoardDetectionService()

    result = service.detect(tune_file=TuneFile(firmware_info="Speeduino DropBear / Teensy 4.1"))

    assert result == BoardFamily.TEENSY41


def test_detects_stm32_from_session_name_when_other_sources_missing() -> None:
    service = BoardDetectionService()

    result = service.detect(session_info=SessionInfo(controller_name="STM32F407 DFU Loader"))

    assert result == BoardFamily.STM32F407_DFU


# ---------------------------------------------------------------------------
# detect_from_capabilities — authoritative path
# ---------------------------------------------------------------------------

def _caps(**kwargs) -> FirmwareCapabilities:
    return FirmwareCapabilities(source="test", **kwargs)


def test_detect_from_capabilities_uses_signature_before_flags() -> None:
    """Firmware signature is the highest-priority source inside detect_from_capabilities."""
    service = BoardDetectionService()
    caps = _caps(experimental_u16p2=False)

    result = service.detect_from_capabilities(caps, signature="speeduino 202501-T41")

    assert result == BoardFamily.TEENSY41


def test_detect_from_capabilities_u16p2_flag_implies_teensy41() -> None:
    """experimental_u16p2=True must resolve to TEENSY41 even without a signature."""
    service = BoardDetectionService()
    caps = _caps(experimental_u16p2=True)

    result = service.detect_from_capabilities(caps, signature=None)

    assert result == BoardFamily.TEENSY41


def test_detect_from_capabilities_returns_none_when_evidence_insufficient() -> None:
    """A fully generic capabilities object with no board-distinguishing facts → None."""
    service = BoardDetectionService()
    caps = _caps()

    result = service.detect_from_capabilities(caps, signature=None)

    assert result is None


def test_detect_from_capabilities_signature_overrides_u16p2_flag() -> None:
    """If the signature identifies a T36, the signature wins over the u16p2 flag."""
    service = BoardDetectionService()
    caps = _caps(experimental_u16p2=True)

    # Hypothetical mismatch — signature says T36 even though u16p2 is set.
    result = service.detect_from_capabilities(caps, signature="speeduino 202501-T36")

    # Signature is checked first; u16p2 fallback is not reached.
    assert result == BoardFamily.TEENSY36


# ---------------------------------------------------------------------------
# detect() — capability-first precedence over text heuristics
# ---------------------------------------------------------------------------

def test_detect_prefers_capabilities_over_controller_name_heuristic() -> None:
    """When session_info has capabilities, they take priority over controller_name text."""
    service = BoardDetectionService()
    # Controller name text says STM32 but capabilities + signature say T41.
    caps = _caps(experimental_u16p2=False)
    session = SessionInfo(
        controller_name="STM32F407",
        firmware_capabilities=caps,
        firmware_signature="speeduino 202501-T41",
    )

    result = service.detect(session_info=session)

    assert result == BoardFamily.TEENSY41


def test_detect_falls_back_to_text_heuristic_when_capabilities_insufficient() -> None:
    """When capabilities yield None, detect() continues to text heuristics."""
    service = BoardDetectionService()
    caps = _caps()  # no board-specific flags, no signature on caps
    session = SessionInfo(
        controller_name="ATMEGA2560",
        firmware_capabilities=caps,
        firmware_signature=None,
    )

    result = service.detect(session_info=session)

    assert result == BoardFamily.ATMEGA2560


def test_detect_uses_u16p2_capability_flag_to_resolve_teensy41() -> None:
    """experimental_u16p2=True in a live session resolves to TEENSY41 without text cues."""
    service = BoardDetectionService()
    caps = _caps(experimental_u16p2=True)
    session = SessionInfo(
        controller_name="Speeduino",
        firmware_capabilities=caps,
        firmware_signature=None,
    )

    result = service.detect(session_info=session)

    assert result == BoardFamily.TEENSY41


def test_detect_without_session_capabilities_still_uses_definition() -> None:
    """With no session_info, the definition signature heuristic must still work."""
    service = BoardDetectionService()

    result = service.detect(definition=EcuDefinition(name="X", firmware_signature="speeduino 202501-T36"))

    assert result == BoardFamily.TEENSY36
