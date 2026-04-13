from __future__ import annotations

import json
from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily, FirmwareArtifactKind
from tuner.domain.tune import TuneFile
from tuner.services.firmware_catalog_service import FirmwareCatalogService


def test_scan_release_reads_hex_files(tmp_path: Path) -> None:
    (tmp_path / "speeduino-dropbear-v2.0.1-teensy41.hex").write_text("", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("", encoding="utf-8")

    entries = FirmwareCatalogService().scan_release(tmp_path)

    assert len(entries) == 1
    assert entries[0].board_family == BoardFamily.TEENSY41


def test_scan_release_prefers_manifest_metadata_over_filename_heuristics(tmp_path: Path) -> None:
    (tmp_path / "main.hex").write_text("", encoding="utf-8")
    (tmp_path / "paired.ini").write_text("", encoding="utf-8")
    (tmp_path / "paired.msq").write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "main.hex",
                        "board_family": "TEENSY41",
                        "version": "v9.9.9",
                        "is_experimental": True,
                        "artifact_kind": "diagnostic",
                        "preferred": True,
                        "definition_file": "paired.ini",
                        "tune_file": "paired.msq",
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    entries = FirmwareCatalogService().scan_release(tmp_path)

    assert len(entries) == 1
    assert entries[0].path == (tmp_path / "main.hex").resolve()
    assert entries[0].board_family == BoardFamily.TEENSY41
    assert entries[0].version_label == "v9.9.9"
    assert entries[0].is_experimental is True
    assert entries[0].artifact_kind == FirmwareArtifactKind.DIAGNOSTIC
    assert entries[0].preferred is True
    assert entries[0].definition_path == (tmp_path / "paired.ini").resolve()
    assert entries[0].tune_path == (tmp_path / "paired.msq").resolve()
    assert entries[0].firmware_signature == "speeduino 202501-T41-U16P2"


def test_suggest_firmware_prefers_matching_board_and_non_experimental(tmp_path: Path) -> None:
    stable = tmp_path / "speeduino-dropbear-v2.0.1-teensy41.hex"
    experimental = tmp_path / "speeduino-dropbear-v2.0.1-teensy41-u16p2-experimental.hex"
    stable.write_text("", encoding="utf-8")
    experimental.write_text("", encoding="utf-8")

    suggestion = FirmwareCatalogService().suggest_firmware(
        tmp_path,
        preferred_board=BoardFamily.TEENSY41,
        definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41"),
        tune_file=TuneFile(firmware_info="Speeduino DropBear v2.0.1"),
    )

    assert suggestion is not None
    assert suggestion.path == stable


def test_suggest_firmware_prefers_experimental_when_metadata_matches(tmp_path: Path) -> None:
    stable = tmp_path / "speeduino-dropbear-v2.0.1-teensy41.hex"
    experimental = tmp_path / "speeduino-dropbear-v2.0.1-teensy41-u16p2-experimental.hex"
    stable.write_text("", encoding="utf-8")
    experimental.write_text("", encoding="utf-8")

    suggestion = FirmwareCatalogService().suggest_firmware(
        tmp_path,
        preferred_board=BoardFamily.TEENSY41,
        tune_file=TuneFile(firmware_info="Speeduino DropBear v2.0.1 u16p2 experimental"),
    )

    assert suggestion is not None
    assert suggestion.path == experimental


def test_suggest_firmware_hides_diagnostics_by_default_when_manifest_present(tmp_path: Path) -> None:
    (tmp_path / "normal.hex").write_text("", encoding="utf-8")
    (tmp_path / "diag.hex").write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "normal.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "artifact_kind": "standard",
                    },
                    {
                        "file": "diag.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "artifact_kind": "diagnostic",
                        "preferred": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    suggestion = FirmwareCatalogService().suggest_firmware(
        tmp_path,
        preferred_board=BoardFamily.TEENSY41,
        definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41"),
        tune_file=TuneFile(firmware_info="Speeduino DropBear v2.0.1"),
    )

    assert suggestion is not None
    assert suggestion.path == (tmp_path / "normal.hex").resolve()


def test_suggest_firmware_prefers_manifest_paired_preferred_experimental_artifact(tmp_path: Path) -> None:
    (tmp_path / "exp_a.hex").write_text("", encoding="utf-8")
    (tmp_path / "exp_b.hex").write_text("", encoding="utf-8")
    (tmp_path / "paired_a.msq").write_text("", encoding="utf-8")
    (tmp_path / "paired_b.msq").write_text("", encoding="utf-8")
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "exp_a.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "is_experimental": True,
                        "preferred": False,
                        "tune_file": "paired_a.msq",
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    },
                    {
                        "file": "exp_b.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "is_experimental": True,
                        "preferred": True,
                        "tune_file": "paired_b.msq",
                        "firmware_signature": "speeduino 202501-T41-U16P2",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    suggestion = FirmwareCatalogService().suggest_firmware(
        tmp_path,
        preferred_board=BoardFamily.TEENSY41,
        definition=EcuDefinition(name="Speeduino", firmware_signature="speeduino 202501-T41-U16P2"),
        tune_file=TuneFile(
            signature="speeduino 202501-T41-U16P2",
            firmware_info="Speeduino DropBear v2.0.1 u16p2 experimental",
            source_path=tmp_path / "paired_b.msq",
        ),
    )

    assert suggestion is not None
    assert suggestion.path == (tmp_path / "exp_b.hex").resolve()
