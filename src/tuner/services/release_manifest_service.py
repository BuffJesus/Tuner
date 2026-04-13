from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tuner.domain.firmware import BoardFamily, FirmwareArtifactKind


@dataclass(slots=True)
class ReleaseManifestFirmwareEntry:
    file_name: str
    board_family: BoardFamily | None
    version_label: str | None = None
    is_experimental: bool = False
    artifact_kind: FirmwareArtifactKind = FirmwareArtifactKind.STANDARD
    preferred: bool = False
    definition_file_name: str | None = None
    tune_file_name: str | None = None
    firmware_signature: str | None = None


@dataclass(slots=True)
class ReleaseManifest:
    firmware: tuple[ReleaseManifestFirmwareEntry, ...]


class ReleaseManifestService:
    MANIFEST_FILE_NAME = "release_manifest.json"

    def load(self, release_root: Path) -> ReleaseManifest | None:
        manifest_path = release_root.expanduser().resolve() / self.MANIFEST_FILE_NAME
        if not manifest_path.is_file():
            return None
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        firmware_payload = payload.get("firmware", [])
        if not isinstance(firmware_payload, list):
            raise ValueError("release_manifest.json field 'firmware' must be a list.")
        return ReleaseManifest(
            firmware=tuple(self._parse_firmware_entry(item) for item in firmware_payload)
        )

    def _parse_firmware_entry(self, payload: object) -> ReleaseManifestFirmwareEntry:
        if not isinstance(payload, dict):
            raise ValueError("release_manifest.json firmware entries must be objects.")
        file_name = payload.get("file")
        if not isinstance(file_name, str) or not file_name.strip():
            raise ValueError("release_manifest.json firmware entries require a non-empty 'file' value.")
        board_family = self._parse_board_family(payload.get("board_family"))
        artifact_kind = self._parse_artifact_kind(payload.get("artifact_kind"))
        return ReleaseManifestFirmwareEntry(
            file_name=file_name.strip(),
            board_family=board_family,
            version_label=self._optional_string(payload.get("version")),
            is_experimental=bool(payload.get("is_experimental", False)),
            artifact_kind=artifact_kind,
            preferred=bool(payload.get("preferred", False)),
            definition_file_name=self._optional_string(payload.get("definition_file")),
            tune_file_name=self._optional_string(payload.get("tune_file")),
            firmware_signature=self._optional_string(payload.get("firmware_signature")),
        )

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("release_manifest.json string fields must contain strings.")
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _parse_board_family(value: object) -> BoardFamily | None:
        board_name = ReleaseManifestService._optional_string(value)
        if board_name is None:
            return None
        try:
            return BoardFamily(board_name)
        except ValueError as exc:
            raise ValueError(f"Unknown board_family in release_manifest.json: {board_name}") from exc

    @staticmethod
    def _parse_artifact_kind(value: object) -> FirmwareArtifactKind:
        kind_name = ReleaseManifestService._optional_string(value)
        if kind_name is None:
            return FirmwareArtifactKind.STANDARD
        try:
            return FirmwareArtifactKind(kind_name)
        except ValueError as exc:
            raise ValueError(f"Unknown artifact_kind in release_manifest.json: {kind_name}") from exc
