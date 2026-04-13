"""Tests for FirmwareCapabilities trust helpers."""
from __future__ import annotations

from tuner.domain.firmware_capabilities import FirmwareCapabilities


def _caps(**kwargs) -> FirmwareCapabilities:
    return FirmwareCapabilities(source="test", **kwargs)


# ---------------------------------------------------------------------------
# runtime_trust_summary
# ---------------------------------------------------------------------------

def test_trust_summary_flags_runtime_status_a_as_uncertain_when_absent() -> None:
    caps = _caps(supports_runtime_status_a=False)
    summary = caps.runtime_trust_summary()
    assert "runtimeStatusA: uncertain" in summary


def test_trust_summary_marks_runtime_status_a_trusted_when_present() -> None:
    caps = _caps(supports_runtime_status_a=True)
    summary = caps.runtime_trust_summary()
    assert "runtimeStatusA: trusted" in summary


def test_trust_summary_mentions_board_capabilities_when_available() -> None:
    caps = _caps(supports_board_capabilities_channel=True)
    summary = caps.runtime_trust_summary()
    assert "boardCapabilities: available" in summary


def test_trust_summary_omits_board_capabilities_when_not_available() -> None:
    caps = _caps(supports_board_capabilities_channel=False)
    summary = caps.runtime_trust_summary()
    assert "boardCapabilities" not in summary


def test_trust_summary_mentions_spi_flash_health_when_available() -> None:
    caps = _caps(supports_spi_flash_health_channel=True)
    summary = caps.runtime_trust_summary()
    assert "spiFlashHealth: available" in summary


def test_trust_summary_mentions_u16p2_flag() -> None:
    caps = _caps(experimental_u16p2=True)
    summary = caps.runtime_trust_summary()
    assert "U16P2: experimental" in summary


def test_trust_summary_includes_live_data_size_when_known() -> None:
    caps = _caps(live_data_size=125)
    summary = caps.runtime_trust_summary()
    assert "live_data_size: 125" in summary


def test_trust_summary_returns_fallback_for_minimal_caps() -> None:
    caps = _caps()
    summary = caps.runtime_trust_summary()
    # At minimum, runtimeStatusA uncertainty should be present.
    assert summary  # non-empty
    assert "runtimeStatusA" in summary


def test_trust_summary_full_caps_contains_all_known_groups() -> None:
    caps = _caps(
        supports_runtime_status_a=True,
        supports_board_capabilities_channel=True,
        supports_spi_flash_health_channel=True,
        experimental_u16p2=True,
        live_data_size=200,
    )
    summary = caps.runtime_trust_summary()
    assert "runtimeStatusA: trusted" in summary
    assert "boardCapabilities: available" in summary
    assert "spiFlashHealth: available" in summary
    assert "U16P2: experimental" in summary
    assert "live_data_size: 200" in summary


# ---------------------------------------------------------------------------
# uncertain_channel_groups
# ---------------------------------------------------------------------------

def test_uncertain_channel_groups_includes_runtime_status_a_when_not_advertised() -> None:
    caps = _caps(supports_runtime_status_a=False)
    uncertain = caps.uncertain_channel_groups()
    assert "runtimeStatusA" in uncertain


def test_uncertain_channel_groups_excludes_runtime_status_a_when_advertised() -> None:
    caps = _caps(supports_runtime_status_a=True)
    uncertain = caps.uncertain_channel_groups()
    assert "runtimeStatusA" not in uncertain


def test_uncertain_channel_groups_includes_board_capabilities_when_absent() -> None:
    caps = _caps(supports_board_capabilities_channel=False)
    uncertain = caps.uncertain_channel_groups()
    assert "boardCapabilities" in uncertain


def test_uncertain_channel_groups_excludes_board_capabilities_when_present() -> None:
    caps = _caps(supports_board_capabilities_channel=True)
    uncertain = caps.uncertain_channel_groups()
    assert "boardCapabilities" not in uncertain


def test_uncertain_channel_groups_includes_spi_flash_health_when_absent() -> None:
    caps = _caps(supports_spi_flash_health_channel=False)
    uncertain = caps.uncertain_channel_groups()
    assert "spiFlashHealth" in uncertain


def test_uncertain_channel_groups_empty_when_all_capabilities_present() -> None:
    caps = _caps(
        supports_runtime_status_a=True,
        supports_board_capabilities_channel=True,
        supports_spi_flash_health_channel=True,
    )
    uncertain = caps.uncertain_channel_groups()
    assert len(uncertain) == 0


def test_uncertain_channel_groups_is_frozenset() -> None:
    caps = _caps()
    uncertain = caps.uncertain_channel_groups()
    assert isinstance(uncertain, frozenset)
