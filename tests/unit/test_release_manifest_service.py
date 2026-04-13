from __future__ import annotations

import json
from pathlib import Path

import pytest

from tuner.domain.firmware import BoardFamily, FirmwareArtifactKind
from tuner.services.release_manifest_service import ReleaseManifestService


def test_load_manifest_reads_firmware_entries(tmp_path: Path) -> None:
    (tmp_path / "release_manifest.json").write_text(
        json.dumps(
            {
                "firmware": [
                    {
                        "file": "speeduino.hex",
                        "board_family": "TEENSY41",
                        "version": "v2.0.1",
                        "is_experimental": False,
                        "artifact_kind": "standard",
                        "preferred": True,
                        "definition_file": "speeduino.ini",
                        "tune_file": "base.msq",
                        "firmware_signature": "speeduino 202501-T41",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest = ReleaseManifestService().load(tmp_path)

    assert manifest is not None
    assert len(manifest.firmware) == 1
    entry = manifest.firmware[0]
    assert entry.file_name == "speeduino.hex"
    assert entry.board_family == BoardFamily.TEENSY41
    assert entry.version_label == "v2.0.1"
    assert entry.artifact_kind == FirmwareArtifactKind.STANDARD
    assert entry.preferred is True


def test_load_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert ReleaseManifestService().load(tmp_path) is None


def test_load_manifest_rejects_unknown_board_family(tmp_path: Path) -> None:
    (tmp_path / "release_manifest.json").write_text(
        json.dumps({"firmware": [{"file": "speeduino.hex", "board_family": "NOT_A_BOARD"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown board_family"):
        ReleaseManifestService().load(tmp_path)
