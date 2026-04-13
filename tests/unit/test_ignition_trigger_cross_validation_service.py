"""Tests for IgnitionTriggerCrossValidationService."""
from __future__ import annotations

import pytest

from tuner.domain.ecu_definition import (
    DialogDefinition,
    DialogFieldDefinition,
    EcuDefinition,
    FieldOptionDefinition,
    MenuDefinition,
    MenuItemDefinition,
    ScalarParameterDefinition,
)
from tuner.domain.setup_checklist import ChecklistItemStatus
from tuner.domain.tune import TuneFile, TuneValue
from tuner.services.ignition_trigger_cross_validation_service import IgnitionTriggerCrossValidationService
from tuner.services.local_tune_edit_service import LocalTuneEditService
from tuner.services.tuning_page_service import TuningPageService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(scalars: dict[str, float], page_title: str = "Test Page") -> tuple:
    """Return (TuningPage, LocalTuneEditService) for a set of scalar parameters."""
    scalar_defs = [
        ScalarParameterDefinition(name=name, data_type="U08", page=1, offset=i)
        for i, name in enumerate(scalars)
    ]
    definition = EcuDefinition(name="Test", scalars=scalar_defs, dialogs=[])
    pages = TuningPageService().build_pages(definition)
    page = pages[0].pages[0]
    tune = TuneFile(constants=[TuneValue(name=n, value=v) for n, v in scalars.items()])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return page, edits


def _svc() -> IgnitionTriggerCrossValidationService:
    return IgnitionTriggerCrossValidationService()


# ---------------------------------------------------------------------------
# Dwell checks
# ---------------------------------------------------------------------------

def test_dwell_ok_when_in_normal_range() -> None:
    ign, edits = _make_page({"dwellRun": 3.0})
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.OK


def test_dwell_error_when_zero() -> None:
    ign, edits = _make_page({"dwellRun": 0.0})
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.ERROR


def test_dwell_error_when_excessive() -> None:
    ign, edits = _make_page({"dwellRun": 15.0})
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.ERROR


def test_dwell_warning_when_implausibly_low() -> None:
    ign, edits = _make_page({"dwellRun": 0.5})
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.WARNING


def test_dwell_needed_when_no_page() -> None:
    items = _svc().validate(ignition_page=None, trigger_page=None, edits=LocalTuneEditService())
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.NEEDED


def test_dwell_found_on_trigger_page_when_not_on_ignition_page() -> None:
    """Dwell on a trigger page should still be found and checked."""
    trig, edits = _make_page({"dwellRun": 3.5})
    # ignition page has no dwell
    ign_def = EcuDefinition(name="T", scalars=[
        ScalarParameterDefinition(name="sparkMode", data_type="U08", page=1, offset=0),
    ], dialogs=[])
    ign_page = TuningPageService().build_pages(ign_def)[0].pages[0]
    edits.set_tune_file(TuneFile(constants=[
        TuneValue(name="dwellRun", value=3.5),
        TuneValue(name="sparkMode", value=0.0),
    ]))
    items = _svc().validate(ignition_page=ign_page, trigger_page=trig, edits=edits)
    dwell = next(i for i in items if i.key == "dwell_configured")
    assert dwell.status == ChecklistItemStatus.OK
    assert dwell.cross_page is True


# ---------------------------------------------------------------------------
# Reference angle checks
# ---------------------------------------------------------------------------

def test_reference_angle_ok_in_typical_range() -> None:
    trig, edits = _make_page({"triggerAngle": 20.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    angle = next(i for i in items if i.key == "reference_angle")
    assert angle.status == ChecklistItemStatus.OK


def test_reference_angle_warning_when_zero() -> None:
    trig, edits = _make_page({"triggerAngle": 0.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    angle = next(i for i in items if i.key == "reference_angle")
    assert angle.status == ChecklistItemStatus.WARNING


def test_reference_angle_warning_when_large() -> None:
    trig, edits = _make_page({"triggerAngle": 80.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    angle = next(i for i in items if i.key == "reference_angle")
    assert angle.status == ChecklistItemStatus.WARNING


def test_reference_angle_needed_when_no_page() -> None:
    items = _svc().validate(ignition_page=None, trigger_page=None, edits=LocalTuneEditService())
    angle = next(i for i in items if i.key == "reference_angle")
    assert angle.status == ChecklistItemStatus.NEEDED


# ---------------------------------------------------------------------------
# Trigger geometry checks
# ---------------------------------------------------------------------------

def test_trigger_geometry_ok_for_valid_36_1_wheel() -> None:
    trig, edits = _make_page({"numTeeth": 36.0, "missingTeeth": 1.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    geo = next((i for i in items if i.key == "trigger_geometry"), None)
    assert geo is not None
    assert geo.status == ChecklistItemStatus.OK


def test_trigger_geometry_error_when_missing_gte_total() -> None:
    trig, edits = _make_page({"numTeeth": 12.0, "missingTeeth": 12.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    geo = next(i for i in items if i.key == "trigger_geometry")
    assert geo.status == ChecklistItemStatus.ERROR


def test_trigger_geometry_warning_when_missing_gt_half() -> None:
    trig, edits = _make_page({"numTeeth": 12.0, "missingTeeth": 7.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    geo = next(i for i in items if i.key == "trigger_geometry")
    assert geo.status == ChecklistItemStatus.WARNING


def test_no_trigger_geometry_item_when_no_trigger_page() -> None:
    items = _svc().validate(ignition_page=None, trigger_page=None, edits=LocalTuneEditService())
    assert not any(i.key == "trigger_geometry" for i in items)


# ---------------------------------------------------------------------------
# Knock pin checks
# ---------------------------------------------------------------------------

def _knock_page(knock_mode: float, pin_val: float = 30.0) -> tuple:
    """Build a minimal ignition page with knock_mode and knock_digital_pin."""
    scalars: list[ScalarParameterDefinition] = [
        ScalarParameterDefinition(
            name="knock_mode",
            data_type="U08",
            page=1,
            offset=0,
            options=tuple(FieldOptionDefinition(value=str(i), label=lbl) for i, lbl in enumerate(["Off", "Digital", "Analog"])),
        ),
        ScalarParameterDefinition(name="knock_digital_pin", data_type="U08", page=1, offset=1),
        ScalarParameterDefinition(name="knock_analog_pin", data_type="U08", page=1, offset=2),
    ]
    definition = EcuDefinition(name="Test", scalars=scalars, dialogs=[])
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune = TuneFile(constants=[
        TuneValue(name="knock_mode", value=knock_mode),
        TuneValue(name="knock_digital_pin", value=pin_val),
        TuneValue(name="knock_analog_pin", value=0.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return page, edits


def test_no_knock_item_when_knock_mode_off() -> None:
    ign, edits = _knock_page(knock_mode=0.0)
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    assert not any(i.key == "knock_pin_configured" for i in items)


def test_knock_pin_ok_when_digital_mode_and_pin_assigned() -> None:
    ign, edits = _knock_page(knock_mode=1.0, pin_val=30.0)
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    knock = next((i for i in items if i.key == "knock_pin_configured"), None)
    assert knock is not None
    assert knock.status == ChecklistItemStatus.OK


def test_knock_pin_warning_when_digital_mode_and_pin_zero() -> None:
    ign, edits = _knock_page(knock_mode=1.0, pin_val=0.0)
    items = _svc().validate(ignition_page=ign, trigger_page=None, edits=edits)
    knock = next(i for i in items if i.key == "knock_pin_configured")
    assert knock.status == ChecklistItemStatus.WARNING


# ---------------------------------------------------------------------------
# All pages None — no crash
# ---------------------------------------------------------------------------

def test_validate_with_no_pages_returns_needed_items() -> None:
    items = _svc().validate(
        ignition_page=None,
        trigger_page=None,
        edits=LocalTuneEditService(),
    )
    assert len(items) > 0
    statuses = {i.status for i in items}
    assert ChecklistItemStatus.NEEDED in statuses


# ---------------------------------------------------------------------------
# Sequential cam sync checks
# ---------------------------------------------------------------------------

def _sequential_page(
    trig_pattern: float,
    spark_mode: float = 0.0,
    inj_layout: float = 0.0,
    trig_speed: float = 0.0,
    trig_pattern_sec: float = 0.0,
) -> tuple:
    """Build a trigger page with sequential-relevant fields."""
    scalars = [
        ScalarParameterDefinition(name="TrigPattern", data_type="U08", page=1, offset=0),
        ScalarParameterDefinition(name="sparkMode", data_type="U08", page=1, offset=1),
        ScalarParameterDefinition(name="injLayout", data_type="U08", page=1, offset=2),
        ScalarParameterDefinition(name="TrigSpeed", data_type="U08", page=1, offset=3),
        ScalarParameterDefinition(name="trigPatternSec", data_type="U08", page=1, offset=4),
    ]
    definition = EcuDefinition(name="Test", scalars=scalars, dialogs=[])
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune = TuneFile(constants=[
        TuneValue(name="TrigPattern", value=trig_pattern),
        TuneValue(name="sparkMode", value=spark_mode),
        TuneValue(name="injLayout", value=inj_layout),
        TuneValue(name="TrigSpeed", value=trig_speed),
        TuneValue(name="trigPatternSec", value=trig_pattern_sec),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    return page, edits


def test_no_cam_sync_check_when_not_sequential() -> None:
    """If neither sequential ignition nor sequential injection is set, no cam sync check."""
    trig, edits = _sequential_page(trig_pattern=0.0, spark_mode=0.0, inj_layout=0.0)
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    assert not any(i.key == "sequential_cam_sync" for i in items)


def test_sequential_ignition_with_crank_only_decoder_warns() -> None:
    """Sequential ignition with a crank-only decoder (GM 7X = 3) should warn."""
    trig, edits = _sequential_page(trig_pattern=3.0, spark_mode=3.0)  # GM 7X, sequential spark
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    cam = next((i for i in items if i.key == "sequential_cam_sync"), None)
    assert cam is not None
    assert cam.status == ChecklistItemStatus.WARNING


def test_sequential_injection_with_crank_only_decoder_warns() -> None:
    """Sequential injection with a crank-only decoder (36-2-2-2 = 16) should warn."""
    trig, edits = _sequential_page(trig_pattern=16.0, inj_layout=3.0)
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    cam = next((i for i in items if i.key == "sequential_cam_sync"), None)
    assert cam is not None
    assert cam.status == ChecklistItemStatus.WARNING


def test_sequential_with_inherent_cam_decoder_no_warning() -> None:
    """Sequential with Dual Wheel (2) — inherent cam — should not produce a warning."""
    trig, edits = _sequential_page(trig_pattern=2.0, spark_mode=3.0, inj_layout=3.0)
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    cam = next((i for i in items if i.key == "sequential_cam_sync"), None)
    # No item, or OK status if present
    assert cam is None or cam.status == ChecklistItemStatus.OK


def test_sequential_missing_tooth_crank_with_configured_cam_ok() -> None:
    """Missing Tooth at crank speed with trigPatternSec = 0 (Single tooth cam) is OK."""
    trig, edits = _sequential_page(
        trig_pattern=0.0,  # Missing Tooth
        trig_speed=0.0,    # crank speed
        trig_pattern_sec=0.0,  # Single tooth cam
        spark_mode=3.0,
    )
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    cam = next((i for i in items if i.key == "sequential_cam_sync"), None)
    assert cam is not None
    assert cam.status == ChecklistItemStatus.OK


def test_sequential_missing_tooth_cam_speed_no_sync_check() -> None:
    """Missing Tooth at cam speed is inherently phase-aware; no secondary trigger needed."""
    trig, edits = _sequential_page(
        trig_pattern=0.0,  # Missing Tooth
        trig_speed=1.0,    # cam speed
        spark_mode=3.0,
    )
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    # No cam sync warning expected
    cam = next((i for i in items if i.key == "sequential_cam_sync"), None)
    assert cam is None or cam.status == ChecklistItemStatus.OK


# ---------------------------------------------------------------------------
# Trigger topology summary
# ---------------------------------------------------------------------------

def test_trigger_topology_summary_produced_when_pattern_known() -> None:
    """A trigger topology INFO item should be produced when TrigPattern is visible."""
    trig, edits = _sequential_page(trig_pattern=0.0, trig_speed=0.0, trig_pattern_sec=0.0)
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    topology = next((i for i in items if i.key == "trigger_topology"), None)
    assert topology is not None
    assert topology.status == ChecklistItemStatus.INFO


def test_trigger_topology_mentions_secondary_cam_for_missing_tooth() -> None:
    trig, edits = _sequential_page(
        trig_pattern=0.0,       # Missing Tooth
        trig_speed=0.0,         # crank speed
        trig_pattern_sec=0.0,   # Single tooth cam
    )
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    topology = next(i for i in items if i.key == "trigger_topology")
    assert "cam" in topology.detail.lower() or "single tooth" in topology.detail.lower()


def test_trigger_topology_mentions_cam_inherent_for_dual_wheel() -> None:
    trig, edits = _sequential_page(trig_pattern=2.0)  # Dual Wheel
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    topology = next((i for i in items if i.key == "trigger_topology"), None)
    assert topology is not None
    assert "inherent" in topology.detail.lower() or "dual" in topology.detail.lower()


def test_trigger_topology_not_produced_when_pattern_not_visible() -> None:
    """If TrigPattern is not on either page, no topology summary is produced."""
    trig, edits = _make_page({"dwellRun": 3.0})
    items = _svc().validate(ignition_page=None, trigger_page=trig, edits=edits)
    assert not any(i.key == "trigger_topology" for i in items)


def test_trigger_topology_includes_tooth_count_for_missing_tooth() -> None:
    """For Missing Tooth, the summary should include tooth count where available."""
    scalars = [
        ScalarParameterDefinition(name="TrigPattern", data_type="U08", page=1, offset=0),
        ScalarParameterDefinition(name="TrigSpeed", data_type="U08", page=1, offset=1),
        ScalarParameterDefinition(name="trigPatternSec", data_type="U08", page=1, offset=2),
        ScalarParameterDefinition(name="numTeeth", data_type="U08", page=1, offset=3),
        ScalarParameterDefinition(name="missingTeeth", data_type="U08", page=1, offset=4),
    ]
    definition = EcuDefinition(name="Test", scalars=scalars, dialogs=[])
    page = TuningPageService().build_pages(definition)[0].pages[0]
    tune = TuneFile(constants=[
        TuneValue(name="TrigPattern", value=0.0),
        TuneValue(name="TrigSpeed", value=0.0),
        TuneValue(name="trigPatternSec", value=0.0),
        TuneValue(name="numTeeth", value=36.0),
        TuneValue(name="missingTeeth", value=1.0),
    ])
    edits = LocalTuneEditService()
    edits.set_tune_file(tune)
    items = _svc().validate(ignition_page=None, trigger_page=page, edits=edits)
    topology = next(i for i in items if i.key == "trigger_topology")
    assert "36" in topology.detail and "1" in topology.detail
