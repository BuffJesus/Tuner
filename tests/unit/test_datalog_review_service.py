from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tuner.domain.datalog import DataLog, DataLogRecord
from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.services.datalog_review_service import DatalogReviewService


def _log(*channel_sets: dict) -> DataLog:
    """Build a DataLog with one record per *channel_sets* dict."""
    start = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    records = [
        DataLogRecord(timestamp=start + timedelta(seconds=i * 0.5), values=ch)
        for i, ch in enumerate(channel_sets)
    ]
    return DataLog(name="session", records=records)


def _profile(*names: str) -> DatalogProfile:
    return DatalogProfile(
        name="Test",
        channels=[DatalogChannelEntry(name=n, enabled=True) for n in names],
    )


def test_datalog_review_service_prioritizes_runtime_relevant_channels() -> None:
    log = _log(
        {"rpm": 900.0, "map": 40.0, "clt": 80.0},
        {"rpm": 1100.0, "map": 48.0, "clt": 81.0},
    )

    review = DatalogReviewService().build(log=log, selected_index=1)

    assert [trace.name for trace in review.traces] == ["rpm", "map", "clt"]
    assert review.marker_x == 0.5
    assert "Selected replay row 2" in review.summary_text


def test_build_with_profile_uses_profile_channel_order() -> None:
    log = _log({"rpm": 900.0, "map": 40.0, "clt": 80.0})
    # Profile specifies clt first — overrides heuristic priority
    profile = _profile("clt", "map", "rpm")

    review = DatalogReviewService().build(log=log, selected_index=0, profile=profile)

    assert [trace.name for trace in review.traces] == ["clt", "map", "rpm"]


def test_build_with_profile_caps_at_three_traces() -> None:
    log = _log({"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0})
    profile = _profile("d", "c", "b", "a")

    review = DatalogReviewService().build(log=log, selected_index=0, profile=profile)

    assert len(review.traces) == 3
    assert review.traces[0].name == "d"


def test_build_with_profile_skips_channels_absent_from_log() -> None:
    log = _log({"rpm": 900.0, "map": 40.0})
    # Profile includes "ghost" which isn't in the log
    profile = _profile("ghost", "rpm", "map")

    review = DatalogReviewService().build(log=log, selected_index=0, profile=profile)

    assert "ghost" not in [t.name for t in review.traces]
    assert "rpm" in [t.name for t in review.traces]


def test_build_with_profile_falls_back_to_heuristic_when_no_match() -> None:
    log = _log({"rpm": 900.0, "map": 40.0})
    # Profile channels are all absent from the log
    profile = _profile("nonexistent1", "nonexistent2")

    review = DatalogReviewService().build(log=log, selected_index=0, profile=profile)

    # Should fall back to heuristic: rpm and map are top priority
    names = [t.name for t in review.traces]
    assert "rpm" in names
    assert "map" in names


def test_build_with_profile_excludes_disabled_channels() -> None:
    log = _log({"rpm": 900.0, "map": 40.0, "clt": 80.0})
    profile = DatalogProfile(name="P", channels=[
        DatalogChannelEntry(name="clt", enabled=True),
        DatalogChannelEntry(name="rpm", enabled=False),  # disabled — should be skipped
        DatalogChannelEntry(name="map", enabled=True),
    ])

    review = DatalogReviewService().build(log=log, selected_index=0, profile=profile)

    names = [t.name for t in review.traces]
    assert "rpm" not in names
    assert "clt" in names
    assert "map" in names


def test_build_without_profile_keeps_heuristic_ordering() -> None:
    """Passing no profile must not change existing heuristic behavior."""
    log = _log({"clt": 80.0, "rpm": 900.0, "map": 40.0})

    review = DatalogReviewService().build(log=log, selected_index=0)

    # rpm and map should come before clt under the heuristic
    names = [t.name for t in review.traces]
    assert names.index("rpm") < names.index("clt")
    assert names.index("map") < names.index("clt")
