from __future__ import annotations

from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily, FlashPreflightReport
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.tune import TuneFile
from tuner.services.firmware_catalog_service import FirmwareCatalogService


class FlashPreflightService:
    def __init__(self, firmware_catalog_service: FirmwareCatalogService | None = None) -> None:
        self.firmware_catalog_service = firmware_catalog_service or FirmwareCatalogService()

    def validate(
        self,
        *,
        firmware_path: Path,
        selected_board: BoardFamily | None,
        detected_board: BoardFamily | None,
        definition: EcuDefinition | None,
        tune_file: TuneFile | None,
        firmware_capabilities: FirmwareCapabilities | None = None,
        connected_firmware_signature: str | None = None,
    ) -> FlashPreflightReport:
        errors: list[str] = []
        warnings: list[str] = []

        if not str(firmware_path).strip():
            errors.append("No firmware file selected.")
            return FlashPreflightReport(ok=False, errors=errors, warnings=warnings)

        resolved_path = firmware_path.expanduser().resolve()
        if not resolved_path.is_file():
            errors.append(f"Firmware file not found: {resolved_path}")
            return FlashPreflightReport(ok=False, errors=errors, warnings=warnings)

        entry = self.firmware_catalog_service.entry_for_firmware(resolved_path)
        firmware_board = entry.board_family

        if selected_board is not None and firmware_board is not None and selected_board != firmware_board:
            errors.append(
                f"Selected board is {selected_board.value}, but firmware file looks like {firmware_board.value}."
            )

        if detected_board is not None and firmware_board is not None and detected_board != firmware_board:
            warnings.append(
                f"Detected board is {detected_board.value}, but firmware file looks like {firmware_board.value}."
            )

        if definition is not None and detected_board is not None and definition.firmware_signature:
            signature = definition.firmware_signature.lower()
            if "t41" in signature and detected_board != BoardFamily.TEENSY41:
                warnings.append("Loaded ECU definition signature indicates T41, but the detected board is different.")
            if "t36" in signature and detected_board != BoardFamily.TEENSY36:
                warnings.append("Loaded ECU definition signature indicates T36, but the detected board is different.")
            if "t35" in signature and detected_board != BoardFamily.TEENSY35:
                warnings.append("Loaded ECU definition signature indicates T35, but the detected board is different.")

        metadata_text = " ".join(
            value
            for value in [
                definition.firmware_signature if definition else None,
                tune_file.signature if tune_file else None,
                tune_file.firmware_info if tune_file else None,
            ]
            if value
        ).lower()
        firmware_signature_family = self._signature_family(entry.firmware_signature)
        definition_signature_family = self._signature_family(definition.firmware_signature if definition else None)
        tune_signature_family = self._signature_family(tune_file.signature if tune_file else None)
        connected_signature_family = self._signature_family(connected_firmware_signature)

        # Experimental/production mismatch: prefer live capability fact over text heuristics
        if firmware_capabilities is not None:
            connected_is_experimental = firmware_capabilities.experimental_u16p2
            if entry.is_experimental and not connected_is_experimental:
                warnings.append(
                    "Selected firmware is experimental (U16P2), but the connected controller is running production firmware."
                )
            elif not entry.is_experimental and connected_is_experimental:
                warnings.append(
                    "Selected firmware is production, but the connected controller is running experimental (U16P2) firmware."
                )
        else:
            metadata_is_experimental = "experimental" in metadata_text or "u16p2" in metadata_text
            if entry.is_experimental:
                if not metadata_is_experimental:
                    warnings.append("Selected firmware is experimental, but the loaded INI/tune metadata looks production.")
            elif metadata_is_experimental:
                warnings.append("Selected firmware looks production, but the loaded INI/tune metadata looks experimental.")

        # Connected firmware signature family vs selected firmware: authoritative when live
        if connected_signature_family is not None and firmware_signature_family is not None:
            if connected_signature_family != firmware_signature_family:
                warnings.append(
                    f"Selected firmware signature family ({firmware_signature_family}) does not match "
                    f"the connected controller's firmware ({connected_signature_family})."
                )

        if firmware_signature_family is not None and definition_signature_family is not None:
            if firmware_signature_family != definition_signature_family:
                warnings.append(
                    "Loaded ECU definition signature family does not match the selected firmware's paired signature family."
                )
        if firmware_signature_family is not None and tune_signature_family is not None:
            if firmware_signature_family != tune_signature_family:
                warnings.append(
                    "Loaded tune signature family does not match the selected firmware's paired signature family."
                )

        if entry.tune_path is not None and tune_file is not None and tune_file.source_path is not None:
            if entry.tune_path.name.lower() != tune_file.source_path.name.lower():
                warnings.append(
                    f"Selected firmware is paired with tune '{entry.tune_path.name}', but the loaded tune is '{tune_file.source_path.name}'."
                )

        if entry.version_label and metadata_text and entry.version_label.lower() not in metadata_text:
            warnings.append(f"Firmware version {entry.version_label} does not appear in the loaded INI/tune metadata.")

        return FlashPreflightReport(ok=not errors, errors=errors, warnings=warnings)

    @staticmethod
    def _signature_family(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.upper()
        if "U16P2" in normalized:
            return "U16P2"
        if "T41" in normalized:
            return "T41"
        if "T36" in normalized:
            return "T36"
        if "T35" in normalized:
            return "T35"
        if "STM32" in normalized or "F407" in normalized:
            return "STM32F407"
        if "MEGA" in normalized or "2560" in normalized:
            return "ATMEGA2560"
        return None
