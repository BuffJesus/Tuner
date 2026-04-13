from __future__ import annotations

from dataclasses import dataclass

from tuner.domain.output_channels import OutputChannelSnapshot


@dataclass(slots=True, frozen=True)
class SpeeduinoBoardCapabilitySnapshot:
    raw_value: int | None = None
    rtc: bool = False
    sd: bool = False
    native_can: bool = False
    spi_flash: bool = False
    adc_12bit: bool = False
    high_res_tables: bool = False
    unrestricted_interrupts: bool = False
    wifi_transport: bool = False

    @property
    def available_labels(self) -> tuple[str, ...]:
        labels: list[str] = []
        if self.rtc:
            labels.append("RTC")
        if self.sd:
            labels.append("SD")
        if self.native_can:
            labels.append("Native CAN")
        if self.spi_flash:
            labels.append("SPI flash")
        if self.adc_12bit:
            labels.append("12-bit ADC")
        if self.high_res_tables:
            labels.append("16-bit tables")
        if self.unrestricted_interrupts:
            labels.append("Unrestricted IRQ")
        if self.wifi_transport:
            labels.append("Wi-Fi transport")
        return tuple(labels)


@dataclass(slots=True, frozen=True)
class SpeeduinoRuntimeStatusSnapshot:
    raw_value: int | None = None
    fuel_pump_on: bool = False
    launch_hard_active: bool = False
    flat_shift_hard_active: bool = False
    idle_up_active: bool = False
    full_sync: bool = False
    transient_active: bool = False
    warmup_or_ase_active: bool = False
    tune_learn_valid: bool = False


@dataclass(slots=True, frozen=True)
class SpeeduinoRuntimeTelemetrySummary:
    board_capabilities: SpeeduinoBoardCapabilitySnapshot
    runtime_status: SpeeduinoRuntimeStatusSnapshot
    spi_flash_health: bool | None
    capability_summary_text: str
    runtime_summary_text: str
    operator_summary_text: str
    setup_guidance_text: str
    persistence_summary_text: str
    severity: str


class SpeeduinoRuntimeTelemetryService:
    def decode(self, snapshot: OutputChannelSnapshot | None) -> SpeeduinoRuntimeTelemetrySummary:
        values = snapshot.as_dict() if snapshot is not None else {}
        board_capabilities = self._decode_board_capabilities(values)
        runtime_status = self._decode_runtime_status(values)
        spi_flash_health = self._decode_spi_flash_health(values)

        capability_summary_text = self._capability_summary_text(board_capabilities, spi_flash_health)
        runtime_summary_text, operator_summary_text, severity = self._runtime_summary_text(runtime_status)
        setup_guidance_text = self._setup_guidance_text(board_capabilities, spi_flash_health)
        persistence_summary_text = self._persistence_summary_text(board_capabilities, spi_flash_health)
        return SpeeduinoRuntimeTelemetrySummary(
            board_capabilities=board_capabilities,
            runtime_status=runtime_status,
            spi_flash_health=spi_flash_health,
            capability_summary_text=capability_summary_text,
            runtime_summary_text=runtime_summary_text,
            operator_summary_text=operator_summary_text,
            setup_guidance_text=setup_guidance_text,
            persistence_summary_text=persistence_summary_text,
            severity=severity,
        )

    def _decode_board_capabilities(self, values: dict[str, float]) -> SpeeduinoBoardCapabilitySnapshot:
        raw_value = self._channel_int(values, "boardCapabilities")
        if raw_value is not None:
            return SpeeduinoBoardCapabilitySnapshot(
                raw_value=raw_value,
                rtc=bool(raw_value & (1 << 0)),
                sd=bool(raw_value & (1 << 1)),
                native_can=bool(raw_value & (1 << 2)),
                spi_flash=bool(raw_value & (1 << 3)),
                adc_12bit=bool(raw_value & (1 << 4)),
                high_res_tables=bool(raw_value & (1 << 5)),
                unrestricted_interrupts=bool(raw_value & (1 << 6)),
                wifi_transport=bool(raw_value & (1 << 7)),
            )
        return SpeeduinoBoardCapabilitySnapshot(
            rtc=self._channel_bool(values, "boardCap_rtc"),
            sd=self._channel_bool(values, "boardCap_sd"),
            native_can=self._channel_bool(values, "boardCap_nativeCAN"),
            spi_flash=self._channel_bool(values, "boardCap_spiFlash"),
            adc_12bit=self._channel_bool(values, "boardCap_12bitADC"),
            high_res_tables=self._channel_bool(values, "boardCap_highResTables"),
            unrestricted_interrupts=self._channel_bool(values, "boardCap_unrestrictedIRQ"),
            wifi_transport=self._channel_bool(values, "boardCap_wifiTransport"),
        )

    def _decode_runtime_status(self, values: dict[str, float]) -> SpeeduinoRuntimeStatusSnapshot:
        raw_value = self._channel_int(values, "runtimeStatusA")
        if raw_value is not None:
            return SpeeduinoRuntimeStatusSnapshot(
                raw_value=raw_value,
                fuel_pump_on=bool(raw_value & (1 << 0)),
                launch_hard_active=bool(raw_value & (1 << 1)),
                flat_shift_hard_active=bool(raw_value & (1 << 2)),
                idle_up_active=bool(raw_value & (1 << 3)),
                full_sync=bool(raw_value & (1 << 4)),
                transient_active=bool(raw_value & (1 << 5)),
                warmup_or_ase_active=bool(raw_value & (1 << 6)),
                tune_learn_valid=bool(raw_value & (1 << 7)),
            )
        return SpeeduinoRuntimeStatusSnapshot(
            fuel_pump_on=self._channel_bool(values, "rSA_fuelPump"),
            launch_hard_active=self._channel_bool(values, "rSA_launchHard"),
            flat_shift_hard_active=self._channel_bool(values, "rSA_flatShift"),
            idle_up_active=self._channel_bool(values, "rSA_idleUp"),
            full_sync=self._channel_bool(values, "rSA_fullSync"),
            transient_active=self._channel_bool(values, "rSA_transient"),
            warmup_or_ase_active=self._channel_bool(values, "rSA_warmupASE"),
            tune_learn_valid=self._channel_bool(values, "rSA_tuneValid"),
        )

    def _decode_spi_flash_health(self, values: dict[str, float]) -> bool | None:
        raw_value = self._channel_int(values, "spiFlashHealth")
        if raw_value is None:
            return None
        return raw_value != 0

    @staticmethod
    def _capability_summary_text(
        board_capabilities: SpeeduinoBoardCapabilitySnapshot,
        spi_flash_health: bool | None,
    ) -> str:
        labels = board_capabilities.available_labels
        if labels:
            capabilities_text = ", ".join(labels)
        elif board_capabilities.raw_value is not None:
            capabilities_text = "none advertised"
        else:
            capabilities_text = "not reported"
        if spi_flash_health is True:
            flash_text = "SPI flash healthy"
        elif spi_flash_health is False:
            flash_text = "SPI flash unavailable"
        else:
            flash_text = "SPI flash health unknown"
        return f"Capabilities: {capabilities_text}. {flash_text}."

    @staticmethod
    def _runtime_summary_text(
        runtime_status: SpeeduinoRuntimeStatusSnapshot,
    ) -> tuple[str, str, str]:
        if runtime_status.raw_value is None and not any(
            (
                runtime_status.fuel_pump_on,
                runtime_status.launch_hard_active,
                runtime_status.flat_shift_hard_active,
                runtime_status.idle_up_active,
                runtime_status.full_sync,
                runtime_status.transient_active,
                runtime_status.warmup_or_ase_active,
                runtime_status.tune_learn_valid,
            )
        ):
            return (
                "Runtime status: runtimeStatusA not reported.",
                "No Speeduino tune-learning status bits are available in the current runtime stream.",
                "info",
            )
        if runtime_status.tune_learn_valid:
            return (
                "Runtime status: Tune Learn Valid.",
                "Tune learning is currently allowed: full sync is present and the firmware reports no transient or warmup blockers.",
                "ok",
            )
        blockers: list[str] = []
        if not runtime_status.full_sync:
            blockers.append("no full sync")
        if runtime_status.transient_active:
            blockers.append("transient active")
        if runtime_status.warmup_or_ase_active:
            blockers.append("warmup/ASE active")
        if not blockers:
            blockers.append("firmware still marks learning blocked")
        return (
            "Runtime status: Tune Learn Blocked.",
            "Tune learning is blocked: " + ", ".join(blockers) + ".",
            "warning",
        )

    @staticmethod
    def _setup_guidance_text(
        board_capabilities: SpeeduinoBoardCapabilitySnapshot,
        spi_flash_health: bool | None,
    ) -> str:
        guidance: list[str] = []
        if board_capabilities.unrestricted_interrupts:
            guidance.append(
                "This board advertises unrestricted interrupts, so trigger input placement is less constrained than on AVR-class hardware."
            )
        elif board_capabilities.raw_value is not None:
            guidance.append(
                "This board does not advertise unrestricted interrupts; verify trigger inputs against interrupt-capable pins before first start."
            )

        if board_capabilities.spi_flash and spi_flash_health is True:
            guidance.append("SPI flash-backed storage is present and healthy.")
        elif board_capabilities.spi_flash and spi_flash_health is False:
            guidance.append(
                "SPI flash capability is advertised but the runtime health bit is bad; avoid assuming flash-backed persistence is currently available."
            )
        elif spi_flash_health is False:
            guidance.append("Runtime reports SPI flash unavailable.")

        if board_capabilities.native_can:
            guidance.append("Native CAN hardware is available on this board.")
        if board_capabilities.wifi_transport:
            guidance.append("An onboard Wi-Fi transport coprocessor is advertised by the firmware.")

        if not guidance:
            return "No board-specific setup guidance is available from the current runtime telemetry."
        return " ".join(guidance)

    @staticmethod
    def _persistence_summary_text(
        board_capabilities: SpeeduinoBoardCapabilitySnapshot,
        spi_flash_health: bool | None,
    ) -> str:
        if board_capabilities.spi_flash and spi_flash_health is True:
            return (
                "Persistence: the connected board advertises SPI flash and runtime health is good. "
                "Burned changes should be treated as flash-backed, but still verify after reconnect."
            )
        if board_capabilities.spi_flash and spi_flash_health is False:
            return (
                "Persistence: SPI flash is advertised but runtime health is bad. "
                "Do not trust burn persistence until the storage path is checked on the bench."
            )
        if spi_flash_health is False:
            return (
                "Persistence: runtime reports SPI flash unavailable. "
                "Treat burn persistence as unverified until the board reconnects cleanly and storage health is understood."
            )
        if board_capabilities.raw_value is not None:
            return (
                "Persistence: no SPI flash-backed storage is advertised by runtime telemetry. "
                "Verify burn results after reconnect instead of assuming flash-backed persistence from board family alone."
            )
        return "Persistence: runtime telemetry does not report storage capability data yet."

    @staticmethod
    def _channel_int(values: dict[str, float], name: str) -> int | None:
        value = values.get(name)
        if value is None:
            return None
        return int(round(value))

    @staticmethod
    def _channel_bool(values: dict[str, float], name: str) -> bool:
        value = values.get(name)
        if value is None:
            return False
        return value >= 0.5
