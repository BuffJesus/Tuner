from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily, FirmwareArtifactKind
from tuner.domain.tune import TuneFile
from tuner.services.release_manifest_service import ReleaseManifestService


@dataclass(slots=True)
class FirmwareCatalogEntry:
    path: Path
    board_family: BoardFamily | None
    version_label: str | None = None
    is_experimental: bool = False
    artifact_kind: FirmwareArtifactKind = FirmwareArtifactKind.STANDARD
    preferred: bool = False
    definition_path: Path | None = None
    tune_path: Path | None = None
    firmware_signature: str | None = None


class FirmwareCatalogService:
    def __init__(self, release_manifest_service: ReleaseManifestService | None = None) -> None:
        self.release_manifest_service = release_manifest_service or ReleaseManifestService()

    def scan_release(self, release_root: Path) -> list[FirmwareCatalogEntry]:
        root = release_root.expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Release folder not found: {root}")
        manifest = self.release_manifest_service.load(root)
        if manifest is not None:
            return [self._entry_from_manifest(root, item) for item in manifest.firmware]
        entries: list[FirmwareCatalogEntry] = []
        for path in sorted(root.glob("*.hex")):
            entries.append(self._entry_for_firmware(path))
        return entries

    def suggest_firmware(
        self,
        release_root: Path,
        *,
        preferred_board: BoardFamily | None = None,
        definition: EcuDefinition | None = None,
        tune_file: TuneFile | None = None,
        include_diagnostic: bool = False,
    ) -> FirmwareCatalogEntry | None:
        entries = self.scan_release(release_root)
        scored: list[tuple[int, FirmwareCatalogEntry]] = []
        for entry in entries:
            score = self._score_entry(
                entry,
                preferred_board=preferred_board,
                definition=definition,
                tune_file=tune_file,
                include_diagnostic=include_diagnostic,
            )
            scored.append((score, entry))
        scored = [item for item in scored if item[0] > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1].path.name.lower()), reverse=True)
        return scored[0][1]

    def entry_for_firmware(self, firmware_path: Path) -> FirmwareCatalogEntry:
        resolved_path = firmware_path.expanduser().resolve()
        manifest = self.release_manifest_service.load(resolved_path.parent)
        if manifest is not None:
            for item in manifest.firmware:
                if Path(item.file_name).name.lower() == resolved_path.name.lower():
                    return self._entry_from_manifest(resolved_path.parent, item)
        return self._entry_for_firmware(resolved_path)

    def _entry_for_firmware(self, path: Path) -> FirmwareCatalogEntry:
        name = path.stem.lower()
        board_family = self._board_from_filename(name)
        version_match = re.search(r"(v\d+(?:\.\d+)+)", name)
        return FirmwareCatalogEntry(
            path=path,
            board_family=board_family,
            version_label=version_match.group(1) if version_match else None,
            is_experimental="experimental" in name,
        )

    def _entry_from_manifest(self, release_root: Path, manifest_entry) -> FirmwareCatalogEntry:
        return FirmwareCatalogEntry(
            path=(release_root / manifest_entry.file_name).resolve(),
            board_family=manifest_entry.board_family,
            version_label=manifest_entry.version_label,
            is_experimental=manifest_entry.is_experimental,
            artifact_kind=manifest_entry.artifact_kind,
            preferred=manifest_entry.preferred,
            definition_path=((release_root / manifest_entry.definition_file_name).resolve() if manifest_entry.definition_file_name else None),
            tune_path=((release_root / manifest_entry.tune_file_name).resolve() if manifest_entry.tune_file_name else None),
            firmware_signature=manifest_entry.firmware_signature,
        )

    def _score_entry(
        self,
        entry: FirmwareCatalogEntry,
        *,
        preferred_board: BoardFamily | None,
        definition: EcuDefinition | None,
        tune_file: TuneFile | None,
        include_diagnostic: bool,
    ) -> int:
        if entry.artifact_kind == FirmwareArtifactKind.DIAGNOSTIC and not include_diagnostic:
            return 0

        score = 1
        if preferred_board is not None:
            if entry.board_family == preferred_board:
                score += 100
            elif entry.board_family is not None:
                return 0

        metadata_text = " ".join(
            value
            for value in [
                definition.firmware_signature if definition else None,
                definition.name if definition else None,
                tune_file.signature if tune_file else None,
                tune_file.firmware_info if tune_file else None,
            ]
            if value
        ).lower()
        experimental_requested = "experimental" in metadata_text or "u16p2" in metadata_text

        if entry.firmware_signature and definition and definition.firmware_signature:
            if entry.firmware_signature.lower() == definition.firmware_signature.lower():
                score += 40
        if entry.firmware_signature and tune_file and tune_file.signature:
            if entry.firmware_signature.lower() == tune_file.signature.lower():
                score += 30
        if entry.tune_path is not None and tune_file and tune_file.source_path is not None:
            if entry.tune_path.name.lower() == tune_file.source_path.name.lower():
                score += 35
        if entry.preferred:
            score += 20 if entry.is_experimental == experimental_requested else 8

        if entry.version_label and entry.version_label.lower() in metadata_text:
            score += 20
        if entry.is_experimental:
            if experimental_requested:
                score += 10
            else:
                score -= 5
        else:
            score += 3
        return score

    @staticmethod
    def _board_from_filename(name: str) -> BoardFamily | None:
        if "teensy41" in name or "t41" in name:
            return BoardFamily.TEENSY41
        if "teensy36" in name or "t36" in name:
            return BoardFamily.TEENSY36
        if "teensy35" in name or "t35" in name:
            return BoardFamily.TEENSY35
        if "stm32" in name or "f407" in name:
            return BoardFamily.STM32F407_DFU
        if "atmega2560" in name or "mega" in name:
            return BoardFamily.ATMEGA2560
        return None
