from __future__ import annotations

import re

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.firmware import BoardFamily
from tuner.domain.firmware_capabilities import FirmwareCapabilities
from tuner.domain.session import SessionInfo
from tuner.domain.tune import TuneFile


class BoardDetectionService:
    def detect(
        self,
        *,
        definition: EcuDefinition | None = None,
        tune_file: TuneFile | None = None,
        session_info: SessionInfo | None = None,
    ) -> BoardFamily | None:
        # Prefer authoritative firmware-advertised facts when a live session exists.
        if session_info is not None and session_info.firmware_capabilities is not None:
            result = self.detect_from_capabilities(
                session_info.firmware_capabilities,
                signature=session_info.firmware_signature,
            )
            if result is not None:
                return result

        candidates = [
            definition.firmware_signature if definition else None,
            definition.name if definition else None,
            tune_file.signature if tune_file else None,
            tune_file.firmware_info if tune_file else None,
            session_info.controller_name if session_info else None,
        ]
        for candidate in candidates:
            board_family = self._detect_from_text(candidate)
            if board_family is not None:
                return board_family
        return None

    def detect_from_capabilities(
        self,
        capabilities: FirmwareCapabilities,
        signature: str | None = None,
    ) -> BoardFamily | None:
        """Use authoritative firmware-advertised facts to determine board family.

        Checks the firmware signature first (most authoritative), then falls back
        to capability flags that encode board-specific features. Returns None when
        the available evidence is insufficient to identify the board.

        Prefer this over text-heuristic detection whenever a live session provides
        FirmwareCapabilities; fall back to detect() for offline/pre-connect use.
        """
        # Firmware signature from the handshake is the highest-fidelity text source.
        if signature:
            result = self._detect_from_text(signature)
            if result is not None:
                return result

        # Capability flags encode board-specific feature support.
        if capabilities.experimental_u16p2:
            # U16P2 is a Teensy 4.1-only experimental feature in the Speeduino ecosystem.
            return BoardFamily.TEENSY41

        return None

    def _detect_from_text(self, text: str | None) -> BoardFamily | None:
        if not text:
            return None
        normalized = text.upper()
        rules: list[tuple[re.Pattern[str], BoardFamily]] = [
            (re.compile(r"\b(T41|TEENSY[\s_-]*4\.?1|TEENSY41)\b"), BoardFamily.TEENSY41),
            (re.compile(r"\b(T36|TEENSY[\s_-]*3\.?6|TEENSY36)\b"), BoardFamily.TEENSY36),
            (re.compile(r"\b(T35|TEENSY[\s_-]*3\.?5|TEENSY35)\b"), BoardFamily.TEENSY35),
            (re.compile(r"\b(STM32F407|F407|DFU)\b"), BoardFamily.STM32F407_DFU),
            (re.compile(r"\b(ATMEGA2560|MEGA2560|ARDUINO\s+MEGA)\b"), BoardFamily.ATMEGA2560),
        ]
        for pattern, board_family in rules:
            if pattern.search(normalized):
                return board_family
        return None
