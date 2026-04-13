from __future__ import annotations

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.parameters import ParameterValue
from tuner.domain.sync_state import SyncMismatch, SyncMismatchKind, SyncState
from tuner.domain.tune import TuneFile


class SyncStateService:
    def build(
        self,
        definition: EcuDefinition | None,
        tune_file: TuneFile | None,
        ecu_ram: dict[str, ParameterValue] | None,
        has_staged: bool,
        connection_state: str,
    ) -> SyncState:
        mismatches = self._detect(definition, tune_file, ecu_ram, has_staged)
        return SyncState(
            mismatches=tuple(mismatches),
            has_ecu_ram=ecu_ram is not None,
            connection_state=connection_state,
        )

    def _detect(
        self,
        definition: EcuDefinition | None,
        tune_file: TuneFile | None,
        ecu_ram: dict[str, ParameterValue] | None,
        has_staged: bool,
    ) -> list[SyncMismatch]:
        mismatches: list[SyncMismatch] = []

        # Signature mismatch: tune was saved against a different firmware
        if definition and tune_file:
            def_sig = definition.firmware_signature
            tune_sig = tune_file.signature
            if def_sig and tune_sig and def_sig != tune_sig:
                mismatches.append(
                    SyncMismatch(
                        kind=SyncMismatchKind.SIGNATURE_MISMATCH,
                        detail=(
                            f"Definition expects '{def_sig}', "
                            f"tune was saved for '{tune_sig}'."
                        ),
                    )
                )

        # Page-size mismatch: tune was saved with a different page count than the definition expects
        if definition and tune_file:
            def_pages = len(definition.page_sizes)
            tune_pages = tune_file.page_count
            if def_pages and tune_pages is not None and def_pages != tune_pages:
                mismatches.append(
                    SyncMismatch(
                        kind=SyncMismatchKind.PAGE_SIZE_MISMATCH,
                        detail=(
                            f"Definition declares {def_pages} page(s), "
                            f"tune was saved with {tune_pages} page(s)."
                        ),
                    )
                )

        # ECU RAM vs loaded tune: parameters that differ after a read-from-ecu
        if ecu_ram is not None and tune_file is not None:
            base: dict[str, ParameterValue] = {}
            for tv in tune_file.constants:
                base[tv.name] = tv.value
            for tv in tune_file.pc_variables:
                base[tv.name] = tv.value
            diffs = [
                name
                for name, ecu_val in ecu_ram.items()
                if name in base and ecu_val != base[name]
            ]
            if diffs:
                preview = ", ".join(diffs[:5])
                suffix = "..." if len(diffs) > 5 else ""
                mismatches.append(
                    SyncMismatch(
                        kind=SyncMismatchKind.ECU_VS_TUNE,
                        detail=(
                            f"{len(diffs)} parameter(s) differ between ECU RAM "
                            f"and loaded tune: {preview}{suffix}"
                        ),
                    )
                )

        # Stale staged: local edits exist but no ECU RAM has been captured yet
        if has_staged and ecu_ram is None:
            mismatches.append(
                SyncMismatch(
                    kind=SyncMismatchKind.STALE_STAGED,
                    detail="Staged changes have not been written to ECU RAM.",
                )
            )

        return mismatches
