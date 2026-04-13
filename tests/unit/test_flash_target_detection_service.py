from __future__ import annotations

from types import SimpleNamespace

from tuner.domain.firmware import BoardFamily
from tuner.services.flash_target_detection_service import FlashTargetDetectionService


def test_detects_mega_from_serial_vid_pid() -> None:
    service = FlashTargetDetectionService()
    ports = [SimpleNamespace(device="COM7", description="Arduino Mega", vid=0x2341, pid=0x0010)]

    targets = service._detect_serial_targets(ports)

    assert len(targets) == 1
    assert targets[0].board_family == BoardFamily.ATMEGA2560
    assert targets[0].serial_port == "COM7"


def test_detects_teensy41_from_serial_vid_pid() -> None:
    service = FlashTargetDetectionService()
    ports = [SimpleNamespace(device="COM9", description="Teensy", vid=0x16C0, pid=0x0483)]

    targets = service._detect_serial_targets(ports)

    assert len(targets) == 1
    assert targets[0].board_family == BoardFamily.TEENSY41
    assert targets[0].serial_port == "COM9"


def test_prefers_matching_board_family() -> None:
    service = FlashTargetDetectionService()
    service.detect_targets = lambda: [  # type: ignore[method-assign]
        SimpleNamespace(board_family=BoardFamily.ATMEGA2560, serial_port="COM1"),
        SimpleNamespace(board_family=BoardFamily.TEENSY41, serial_port="COM9"),
    ]

    target = service.detect_preferred_target(BoardFamily.TEENSY41)

    assert target is not None
    assert target.board_family == BoardFamily.TEENSY41
