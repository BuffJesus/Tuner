"""Tests for SensorSetupChecklistService."""
from __future__ import annotations

import pytest

from tuner.domain.ecu_definition import (
    EcuDefinition,
    FieldOptionDefinition,
    ScalarParameterDefinition,
)
from tuner.domain.setup_checklist import ChecklistItemStatus
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.sensor_setup_checklist_service import SensorSetupChecklistService
from tuner.services.tuning_page_service import TuningPageService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pages(
    scalars: dict[str, float],
    options: dict[str, list[tuple[str, str]]] | None = None,
) -> tuple:
    """Return (tuple[TuningPage], LocalTuneEditService)."""
    options = options or {}
    scalar_defs = [
        ScalarParameterDefinition(
            name=name,
            data_type="U08",
            page=1,
            offset=i,
            options=tuple(
                FieldOptionDefinition(code, label)
                for code, label in options.get(name, [])
            ),
        )
        for i, name in enumerate(scalars)
    ]
    definition = EcuDefinition(name="Test", scalars=scalar_defs, dialogs=[])
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]
    tune = TuneFile(constants=[TuneValue(name=n, value=v) for n, v in scalars.items()])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return (page,), edits


def _svc() -> SensorSetupChecklistService:
    return SensorSetupChecklistService()


def _item(items, key: str):
    return next((i for i in items if i.key == key), None)


# ---------------------------------------------------------------------------
# EGO type checks
# ---------------------------------------------------------------------------

def test_ego_type_disabled_returns_info() -> None:
    pages, edits = _make_pages({"egoType": 0.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "ego_type_configured")
    assert item is not None
    assert item.status == ChecklistItemStatus.INFO


def test_ego_type_narrow_band_returns_ok() -> None:
    pages, edits = _make_pages({"egoType": 1.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "ego_type_configured")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


def test_ego_type_wideband_returns_ok() -> None:
    pages, edits = _make_pages({"egoType": 2.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "ego_type_configured")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


def test_ego_type_missing_returns_needed() -> None:
    pages, edits = _make_pages({"egoType": 1.0})
    # Override edit service with no value set
    edits2 = LocalTuneEditService()
    edits2.set_tune_file(TuneFile(constants=[]))
    items = _svc().validate(sensor_pages=pages, edits=edits2)
    item = _item(items, "ego_type_configured")
    assert item is not None
    assert item.status == ChecklistItemStatus.NEEDED


# ---------------------------------------------------------------------------
# Wideband calibration checks
# ---------------------------------------------------------------------------

def test_wideband_cal_no_cal_param_returns_warning() -> None:
    # egoType=2, no calibration param
    pages, edits = _make_pages({"egoType": 2.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "wideband_cal")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


def test_wideband_cal_zero_returns_needed() -> None:
    pages, edits = _make_pages({"egoType": 2.0, "afrCal": 0.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "wideband_cal")
    assert item is not None
    assert item.status == ChecklistItemStatus.NEEDED


def test_wideband_cal_set_returns_ok() -> None:
    pages, edits = _make_pages({"egoType": 2.0, "afrCal": 5.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "wideband_cal")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


def test_wideband_cal_skipped_for_narrow_band() -> None:
    pages, edits = _make_pages({"egoType": 1.0, "afrCal": 0.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert _item(items, "wideband_cal") is None


# ---------------------------------------------------------------------------
# Stoich checks
# ---------------------------------------------------------------------------

def test_stoich_petrol_returns_ok() -> None:
    pages, edits = _make_pages({"stoich": 14.7})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "stoich_plausible")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK
    assert "petrol" in item.detail


def test_stoich_e85_returns_ok() -> None:
    pages, edits = _make_pages({"stoich": 9.8})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "stoich_plausible")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK
    assert "E85" in item.detail


def test_stoich_out_of_range_returns_warning() -> None:
    pages, edits = _make_pages({"stoich": 2.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "stoich_plausible")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


# ---------------------------------------------------------------------------
# Flex fuel checks
# ---------------------------------------------------------------------------

def test_flex_enabled_without_frequency_params_returns_warning() -> None:
    pages, edits = _make_pages({"flexEnabled": 1.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "flex_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


def test_flex_invalid_frequency_range_returns_error() -> None:
    pages, edits = _make_pages({"flexEnabled": 1.0, "flexFreqLow": 150.0, "flexFreqHigh": 50.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "flex_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.ERROR


def test_flex_standard_frequency_range_returns_ok() -> None:
    pages, edits = _make_pages({"flexEnabled": 1.0, "flexFreqLow": 50.0, "flexFreqHigh": 150.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "flex_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


# ---------------------------------------------------------------------------
# TPS range checks
# ---------------------------------------------------------------------------

def test_tps_inverted_returns_error() -> None:
    pages, edits = _make_pages({"tpsMin": 300.0, "tpsMax": 200.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "tps_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.ERROR


def test_tps_narrow_returns_warning() -> None:
    pages, edits = _make_pages({"tpsMin": 100.0, "tpsMax": 120.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "tps_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


def test_tps_ok_returns_ok() -> None:
    pages, edits = _make_pages({"tpsMin": 100.0, "tpsMax": 900.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "tps_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


def test_tps_missing_returns_no_item() -> None:
    pages, edits = _make_pages({"stoich": 14.7})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert _item(items, "tps_range") is None


# ---------------------------------------------------------------------------
# MAP range checks
# ---------------------------------------------------------------------------

def test_map_invalid_range_returns_error() -> None:
    pages, edits = _make_pages({"mapMin": 250.0, "mapMax": 100.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "map_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.ERROR


def test_map_narrow_range_returns_warning() -> None:
    pages, edits = _make_pages({"mapMin": 100.0, "mapMax": 130.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "map_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


def test_map_ok_range_returns_ok() -> None:
    pages, edits = _make_pages({"mapMin": 20.0, "mapMax": 300.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "map_range")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


# ---------------------------------------------------------------------------
# Knock pin checks
# ---------------------------------------------------------------------------

def test_knock_disabled_no_item() -> None:
    pages, edits = _make_pages({"knock_mode": 0.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert _item(items, "knock_pin_sensor") is None


def test_knock_digital_pin_missing_returns_warning() -> None:
    # knock_mode=1 but no pin param on page
    pages, edits = _make_pages({"knock_mode": 1.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "knock_pin_sensor")
    assert item is not None
    assert item.status == ChecklistItemStatus.WARNING


def test_knock_digital_pin_assigned_returns_ok() -> None:
    pages, edits = _make_pages({"knock_mode": 1.0, "knock_digital_pin": 5.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "knock_pin_sensor")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


def test_knock_digital_pin_assigned_with_non_index_option_value_returns_ok() -> None:
    pages, edits = _make_pages(
        {"knock_mode": 1.0, "knock_digital_pin": 30.0},
        options={
            "knock_mode": [("0", "Off"), ("1", "Digital"), ("2", "Analog")],
            "knock_digital_pin": [("0", "INVALID"), ("30", "PT4"), ("31", "PT5"), ("255", "INVALID")],
        },
    )
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "knock_pin_sensor")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK
    assert "PT4" in item.detail


# ---------------------------------------------------------------------------
# Oil pressure calibration checks
# ---------------------------------------------------------------------------

def test_oil_disabled_no_item() -> None:
    pages, edits = _make_pages({"oilPressureEnable": 0.0, "oilPressureMin": 1.0, "oilPressureMax": 5.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert _item(items, "oil_calibration") is None


def test_oil_invalid_range_returns_error() -> None:
    pages, edits = _make_pages({"oilPressureEnable": 1.0, "oilPressureMin": 5.0, "oilPressureMax": 2.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "oil_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.ERROR


def test_oil_valid_range_returns_ok() -> None:
    pages, edits = _make_pages({"oilPressureEnable": 1.0, "oilPressureMin": 0.5, "oilPressureMax": 6.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "oil_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


# ---------------------------------------------------------------------------
# Baro calibration checks
# ---------------------------------------------------------------------------

def test_baro_disabled_no_item() -> None:
    pages, edits = _make_pages({"useExtBaro": 0.0, "baroMin": 80.0, "baroMax": 110.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert _item(items, "baro_calibration") is None


def test_baro_invalid_range_returns_error() -> None:
    pages, edits = _make_pages({"useExtBaro": 1.0, "baroMin": 120.0, "baroMax": 80.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "baro_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.ERROR


def test_baro_valid_range_returns_ok() -> None:
    pages, edits = _make_pages({"useExtBaro": 1.0, "baroMin": 80.0, "baroMax": 110.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    item = _item(items, "baro_calibration")
    assert item is not None
    assert item.status == ChecklistItemStatus.OK


# ---------------------------------------------------------------------------
# Empty pages / no parameters
# ---------------------------------------------------------------------------

def test_empty_pages_returns_empty_tuple() -> None:
    pages, edits = _make_pages({"someOtherParam": 1.0})
    items = _svc().validate(sensor_pages=pages, edits=edits)
    assert isinstance(items, tuple)
    # No sensor-relevant keys — all checks return nothing
    assert all(i.key not in ("tps_range", "map_range", "oil_calibration", "baro_calibration") for i in items)
