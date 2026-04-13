from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.tune import TuneFile
from tuner.services.flash_preflight_service import FlashPreflightService


def test_preflight_rejects_missing_firmware(tmp_path: Path) -> None:
    report = FlashPreflightService().validate(
        firmware_path=tmp_path / "missing.hex",
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
    )

    assert report.ok is False
    assert report.errors


def test_preflight_rejects_board_mismatch(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-dropbear-v2.0.1-teensy41.hex"
    firmware.write_text("", encoding="utf-8")

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.ATMEGA2560,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
    )

    assert report.ok is False
    assert any("Selected board" in error for error in report.errors)


def test_preflight_warns_for_experimental_mismatch(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-dropbear-v2.0.1-teensy41-u16p2-experimental.hex"
    firmware.write_text("", encoding="utf-8")

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41"),
        tune_file=TuneFile(firmware_info="Speeduino DropBear v2.0.1"),
    )

    assert report.ok is True
    assert any("experimental" in warning.lower() for warning in report.warnings)


def test_preflight_uses_manifest_signature_family_and_pairing_when_available(tmp_path: Path) -> None:
    firmware = tmp_path / "selected.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "paired.msq").write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "selected.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "is_experimental": True,
                        "tune_file": "paired.msq",
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41"),
        tune_file=TuneFile(
            source_path=tmp_path / "different.msq",
            signature="speeduino 202501-T41",
            firmware_info="Speeduino DropBear v2.0.1",
        ),
    )

    assert report.ok is True
    assert any("looks production" in warning for warning in report.warnings)
    assert any("definition signature family" in warning for warning in report.warnings)
    assert any("tune signature family" in warning for warning in report.warnings)
    assert any("paired with tune" in warning for warning in report.warnings)


def test_preflight_uses_capabilities_for_experimental_mismatch_production_to_experimental(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-t41-experimental.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino-t41-experimental.hex",
                        "board_family": "TEENSY41",
                        "is_experimental": True,
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    capabilities = FirmwareCapabilities(source="f_command", experimental_u16p2=False)

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
        firmware_capabilities=capabilities,
    )

    assert report.ok is True
    assert any("running production firmware" in w for w in report.warnings)


def test_preflight_uses_capabilities_for_experimental_mismatch_experimental_to_production(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-t41-production.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino-t41-production.hex",
                        "board_family": "TEENSY41",
                        "is_experimental": False,
                        "firmware_signature": "speeduino 202501-T41",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    capabilities = FirmwareCapabilities(source="f_command", experimental_u16p2=True)

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
        firmware_capabilities=capabilities,
    )

    assert report.ok is True
    assert any("running experimental" in w for w in report.warnings)


def test_preflight_no_warning_when_capabilities_and_firmware_both_experimental(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-t41-experimental.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino-t41-experimental.hex",
                        "board_family": "TEENSY41",
                        "is_experimental": True,
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    capabilities = FirmwareCapabilities(source="f_command", experimental_u16p2=True)

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
        firmware_capabilities=capabilities,
    )

    assert report.ok is True
    assert not any("experimental" in w.lower() for w in report.warnings)


def test_preflight_warns_on_connected_signature_family_mismatch(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-t41.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino-t41.hex",
                        "board_family": "TEENSY41",
                        "is_experimental": False,
                        "firmware_signature": "speeduino 202501-T41",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
        connected_firmware_signature="speeduino 202501-T36",
    )

    assert report.ok is True
    assert any("connected controller" in w for w in report.warnings)


def test_preflight_no_connected_signature_warning_when_families_match(tmp_path: Path) -> None:
    firmware = tmp_path / "speeduino-t41.hex"
    firmware.write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino-t41.hex",
                        "board_family": "TEENSY41",
                        "is_experimental": False,
                        "firmware_signature": "speeduino 202501-T41",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = FlashPreflightService().validate(
        firmware_path=firmware,
        selected_board=BoardFamily.TEENSY41,
        detected_board=BoardFamily.TEENSY41,
        definition=None,
        tune_file=None,
        connected_firmware_signature="speeduino 202501-T41",
    )

    assert report.ok is True
    assert not any("connected controller" in w for w in report.warnings)
