from __future__ import annotations

import json
from pathlib import Path

import pytest

from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.domain.ecu_definition import ScalarParameterDefinition
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.services.datalog_profile_service import DatalogProfileService


def _ch(name: str, label: str | None = None, units: str | None = None, **kw) -> ScalarParameterDefinition:
    return ScalarParameterDefinition(name=name, data_type="U08", label=label, units=units, **kw)


def _snap(*pairs: tuple[str, float]) -> OutputChannelSnapshot:
    return OutputChannelSnapshot(
        values=[OutputChannelValue(name=n, value=v) for n, v in pairs]
    )


def test_default_profile_empty_without_defs() -> None:
    svc = DatalogProfileService()
    profile = svc.default_profile()
    assert profile.name == "Default"
    assert profile.channels == []


def test_default_profile_uses_definition_channels() -> None:
    svc = DatalogProfileService()
    defs = [_ch("rpm", label="RPM", units="RPM"), _ch("map", label="MAP", units="kPa")]
    profile = svc.default_profile(defs)
    assert len(profile.channels) == 2
    names = [ch.name for ch in profile.channels]
    assert "rpm" in names
    assert "map" in names


def test_default_profile_priority_ordering() -> None:
    svc = DatalogProfileService()
    defs = [_ch("iat"), _ch("rpm"), _ch("map"), _ch("tps")]
    profile = svc.default_profile(defs)
    names = [ch.name for ch in profile.channels]
    # rpm, map, tps should come before iat
    assert names.index("rpm") < names.index("iat")
    assert names.index("map") < names.index("iat")


def test_default_profile_all_channels_enabled() -> None:
    svc = DatalogProfileService()
    profile = svc.default_profile([_ch("rpm"), _ch("map")])
    assert all(ch.enabled for ch in profile.channels)


def test_unavailable_channels_empty_when_all_present() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"), DatalogChannelEntry(name="map"),
    ])
    missing = svc.unavailable_channels(profile, {"rpm", "map", "tps"})
    assert missing == []


def test_unavailable_channels_reports_missing() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"), DatalogChannelEntry(name="ghost"),
    ])
    missing = svc.unavailable_channels(profile, {"rpm", "map"})
    assert missing == ["ghost"]


def test_unavailable_channels_ignores_disabled() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"),
        DatalogChannelEntry(name="ghost", enabled=False),
    ])
    missing = svc.unavailable_channels(profile, {"rpm"})
    assert missing == []


def test_filter_snapshot_keeps_enabled_channels() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"), DatalogChannelEntry(name="map"),
    ])
    snap = _snap(("rpm", 3000.0), ("map", 98.5), ("tps", 45.0))
    filtered = svc.filter_snapshot(profile, snap)
    names = {v.name for v in filtered.values}
    assert names == {"rpm", "map"}
    assert "tps" not in names


def test_filter_snapshot_excludes_disabled() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"),
        DatalogChannelEntry(name="map", enabled=False),
    ])
    snap = _snap(("rpm", 3000.0), ("map", 98.5))
    filtered = svc.filter_snapshot(profile, snap)
    assert {v.name for v in filtered.values} == {"rpm"}


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="MyLog", channels=[
        DatalogChannelEntry(name="rpm", label="RPM", units="RPM", enabled=True, format_digits=0),
        DatalogChannelEntry(name="map", label="MAP", units="kPa", enabled=False),
    ])
    path = tmp_path / "test.json"
    svc.save(path, profile)
    loaded = svc.load(path)
    assert loaded.name == "MyLog"
    assert len(loaded.channels) == 2
    rpm = next(ch for ch in loaded.channels if ch.name == "rpm")
    assert rpm.label == "RPM"
    assert rpm.enabled is True
    assert rpm.format_digits == 0
    map_ch = next(ch for ch in loaded.channels if ch.name == "map")
    assert map_ch.enabled is False


def test_apply_definition_metadata_fills_missing() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm"),
    ])
    svc.apply_definition_metadata(profile, [_ch("rpm", label="Engine RPM", units="RPM")])
    assert profile.channels[0].label == "Engine RPM"
    assert profile.channels[0].units == "RPM"


def test_apply_definition_metadata_preserves_existing() -> None:
    svc = DatalogProfileService()
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="rpm", label="My RPM", units="rev/min"),
    ])
    svc.apply_definition_metadata(profile, [_ch("rpm", label="Engine RPM", units="RPM")])
    # Existing label/units should not be overwritten
    assert profile.channels[0].label == "My RPM"
    assert profile.channels[0].units == "rev/min"


# ---------------------------------------------------------------------------
# Profile collection (load_collection / save_collection)
# ---------------------------------------------------------------------------

def test_save_and_load_collection_round_trip(tmp_path: Path) -> None:
    svc = DatalogProfileService()
    profiles = [
        DatalogProfile(name="Default", channels=[DatalogChannelEntry(name="rpm", enabled=True)]),
        DatalogProfile(name="Race", channels=[DatalogChannelEntry(name="map", enabled=True)]),
    ]
    path = tmp_path / "test.logging-profile.json"
    svc.save_collection(path, profiles, active_name="Race")
    loaded, active_name = svc.load_collection(path)

    assert active_name == "Race"
    assert len(loaded) == 2
    assert loaded[0].name == "Default"
    assert loaded[1].name == "Race"
    assert loaded[0].channels[0].name == "rpm"


def test_load_collection_falls_back_to_single_profile_format(tmp_path: Path) -> None:
    """Old single-profile JSON files are wrapped transparently into a one-item collection."""
    svc = DatalogProfileService()
    old_profile = DatalogProfile(name="Legacy", channels=[DatalogChannelEntry(name="rpm")])
    path = tmp_path / "legacy.json"
    svc.save(path, old_profile)  # writes old single-profile format

    loaded, active_name = svc.load_collection(path)

    assert len(loaded) == 1
    assert loaded[0].name == "Legacy"
    assert active_name == "Legacy"


def test_save_collection_version_field(tmp_path: Path) -> None:
    svc = DatalogProfileService()
    path = tmp_path / "coll.json"
    svc.save_collection(path, [DatalogProfile(name="P")], active_name="P")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["active"] == "P"
    assert isinstance(data["profiles"], list)


def test_load_collection_returns_default_when_profiles_list_empty(tmp_path: Path) -> None:
    svc = DatalogProfileService()
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"version": 1, "active": "X", "profiles": []}), encoding="utf-8")

    loaded, active_name = svc.load_collection(path)

    assert len(loaded) == 1
    assert loaded[0].name == "Default"


def test_load_collection_active_name_falls_back_to_first(tmp_path: Path) -> None:
    svc = DatalogProfileService()
    profiles = [DatalogProfile(name="Alpha"), DatalogProfile(name="Beta")]
    path = tmp_path / "coll.json"
    svc.save_collection(path, profiles, active_name="Alpha")

    # Tamper: change active to an unknown name
    data = json.loads(path.read_text(encoding="utf-8"))
    data["active"] = "Unknown"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded, active_name = svc.load_collection(path)
    # active_name keeps what was stored; caller decides whether to clamp
    assert active_name == "Unknown"
    assert loaded[0].name == "Alpha"
