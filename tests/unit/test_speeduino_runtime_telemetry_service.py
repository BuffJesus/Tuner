from __future__ import annotations

from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.services.speeduino_runtime_telemetry_service import SpeeduinoRuntimeTelemetryService


def test_decode_uses_raw_speeduino_bytes_when_present() -> None:
    summary = SpeeduinoRuntimeTelemetryService().decode(
        OutputChannelSnapshot(
            values=[
                OutputChannelValue(name="boardCapabilities", value=float(0b11011000)),
                OutputChannelValue(name="spiFlashHealth", value=1.0),
                OutputChannelValue(name="runtimeStatusA", value=float(0b10010000)),
            ]
        )
    )

    assert summary.board_capabilities.spi_flash is True
    assert summary.board_capabilities.unrestricted_interrupts is True
    assert summary.board_capabilities.wifi_transport is True
    assert summary.spi_flash_health is True
    assert summary.runtime_status.full_sync is True
    assert summary.runtime_status.tune_learn_valid is True
    assert summary.severity == "ok"
    assert "SPI flash healthy" in summary.capability_summary_text
    assert "Tune Learn Valid" in summary.runtime_summary_text
    assert "unrestricted interrupts" in summary.setup_guidance_text.lower()
    assert "burned changes should be treated as flash-backed" in summary.persistence_summary_text.lower()


def test_decode_falls_back_to_named_bit_channels() -> None:
    summary = SpeeduinoRuntimeTelemetryService().decode(
        OutputChannelSnapshot(
            values=[
                OutputChannelValue(name="boardCap_nativeCAN", value=1.0),
                OutputChannelValue(name="boardCap_unrestrictedIRQ", value=1.0),
                OutputChannelValue(name="spiFlashHealth", value=0.0),
                OutputChannelValue(name="rSA_fullSync", value=0.0),
                OutputChannelValue(name="rSA_transient", value=1.0),
                OutputChannelValue(name="rSA_tuneValid", value=0.0),
            ]
        )
    )

    assert summary.board_capabilities.native_can is True
    assert summary.board_capabilities.unrestricted_interrupts is True
    assert summary.spi_flash_health is False
    assert summary.runtime_status.transient_active is True
    assert summary.runtime_status.tune_learn_valid is False
    assert summary.severity == "warning"
    assert "SPI flash unavailable" in summary.capability_summary_text
    assert "transient active" in summary.operator_summary_text
    assert "native can" in summary.setup_guidance_text.lower()
    assert "treat burn persistence as unverified" in summary.persistence_summary_text.lower()


def test_decode_reports_unavailable_when_speeduino_channels_absent() -> None:
    summary = SpeeduinoRuntimeTelemetryService().decode(
        OutputChannelSnapshot(values=[OutputChannelValue(name="rpm", value=950.0)])
    )

    assert summary.spi_flash_health is None
    assert summary.board_capabilities.available_labels == ()
    assert summary.runtime_status.raw_value is None
    assert summary.severity == "info"
    assert "not reported" in summary.capability_summary_text
    assert "not reported" in summary.runtime_summary_text.lower()
    assert "no board-specific setup guidance" in summary.setup_guidance_text.lower()
    assert "does not report storage capability data yet" in summary.persistence_summary_text.lower()
