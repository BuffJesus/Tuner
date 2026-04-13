from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from tuner.domain.datalog_profile import DatalogChannelEntry, DatalogProfile
from tuner.domain.output_channels import OutputChannelSnapshot, OutputChannelValue
from tuner.services.live_capture_session_service import LiveCaptureSessionService


def _profile(*names: str) -> DatalogProfile:
    return DatalogProfile(
        name="Test",
        channels=[DatalogChannelEntry(name=n, enabled=True) for n in names],
    )


def _snap(t: float, **values: float) -> OutputChannelSnapshot:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return OutputChannelSnapshot(
        timestamp=base + timedelta(seconds=t),
        values=[OutputChannelValue(name=k, value=v) for k, v in values.items()],
    )


def test_initial_state_not_recording() -> None:
    svc = LiveCaptureSessionService()
    assert not svc.is_recording
    assert svc.row_count == 0
    assert not svc.has_data


def test_start_sets_recording() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    assert svc.is_recording


def test_append_records_filtered_snapshot() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm", "map"))
    svc.append(_snap(0.0, rpm=3000.0, map=98.5, tps=45.0))
    assert svc.row_count == 1
    log = svc.to_log()
    assert len(log.records) == 1
    assert "rpm" in log.records[0].values
    assert "map" in log.records[0].values
    assert "tps" not in log.records[0].values


def test_append_noop_when_not_recording() -> None:
    svc = LiveCaptureSessionService()
    svc.append(_snap(0.0, rpm=3000.0))
    assert svc.row_count == 0


def test_stop_ends_recording() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    assert not svc.is_recording
    assert svc.has_data


def test_append_after_stop_is_ignored() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.stop()
    svc.append(_snap(1.0, rpm=2000.0))
    assert svc.row_count == 0


def test_reset_clears_data() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    svc.reset()
    assert not svc.is_recording
    assert svc.row_count == 0
    assert not svc.has_data


def test_start_discards_previous_session() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    svc.start(_profile("map"))
    assert svc.row_count == 0


def test_to_csv_produces_header_and_rows() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm", "map"))
    svc.append(_snap(0.0, rpm=3000.0, map=98.5))
    svc.append(_snap(1.0, rpm=3100.0, map=99.0))
    svc.stop()
    text = svc.to_csv()
    reader = list(csv.DictReader(io.StringIO(text)))
    assert len(reader) == 2
    assert "rpm" in reader[0]
    assert "map" in reader[0]
    assert "Time_ms" in reader[0]


def test_to_csv_empty_when_no_data() -> None:
    svc = LiveCaptureSessionService()
    assert svc.to_csv() == ""


def test_to_csv_column_order_follows_profile() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("map", "rpm", "tps"))
    svc.append(_snap(0.0, rpm=3000.0, map=98.5, tps=40.0))
    svc.stop()
    text = svc.to_csv()
    header = next(csv.reader(io.StringIO(text)))
    # Time_ms is first, then channels in profile order
    assert header[0] == "Time_ms"
    assert header[1] == "map"
    assert header[2] == "rpm"
    assert header[3] == "tps"


def test_to_csv_format_digits_applied() -> None:
    svc = LiveCaptureSessionService()
    profile = DatalogProfile(name="T", channels=[
        DatalogChannelEntry(name="rpm", format_digits=0),
        DatalogChannelEntry(name="advance", format_digits=1),
    ])
    svc.start(profile)
    svc.append(_snap(0.0, rpm=3000.123, advance=12.567))
    svc.stop()
    rows = list(csv.DictReader(io.StringIO(svc.to_csv())))
    assert rows[0]["rpm"] == "3000"
    assert rows[0]["advance"] == "12.6"


def test_status_text_while_recording() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    status = svc.status()
    assert status.recording
    assert "Recording" in status.status_text


def test_status_text_after_stop() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    status = svc.status()
    assert not status.recording
    assert "Stopped" in status.status_text


def test_status_text_initial_ready() -> None:
    svc = LiveCaptureSessionService()
    assert "Ready" in svc.status().status_text


def test_to_log_name_includes_profile_name() -> None:
    svc = LiveCaptureSessionService()
    svc.start(DatalogProfile(name="MySession", channels=[DatalogChannelEntry(name="rpm")]))
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    log = svc.to_log()
    assert "MySession" in log.name


def test_save_csv_writes_file(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=2500.0))
    svc.stop()
    out = tmp_path / "capture.csv"
    svc.save_csv(out)
    assert out.exists()
    rows = list(csv.DictReader(out.read_text().splitlines()))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Streaming (capture-to-file) tests
# ---------------------------------------------------------------------------

def test_streaming_creates_file_on_start(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm"), output_path=out)
    assert out.exists()
    svc.stop()


def test_streaming_writes_header_immediately(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm", "map"), output_path=out)
    header = next(csv.reader(io.StringIO(out.read_text())))
    assert header[0] == "Time_ms"
    assert "rpm" in header
    assert "map" in header
    svc.stop()


def test_streaming_appends_rows_in_real_time(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm"), output_path=out)
    svc.append(_snap(0.0, rpm=1000.0))
    # File should already have the row before stop()
    rows = list(csv.DictReader(io.StringIO(out.read_text())))
    assert len(rows) == 1
    assert rows[0]["rpm"] == "1000.0"
    svc.append(_snap(1.0, rpm=1500.0))
    rows = list(csv.DictReader(io.StringIO(out.read_text())))
    assert len(rows) == 2
    svc.stop()


def test_streaming_file_closed_after_stop(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm"), output_path=out)
    svc.append(_snap(0.0, rpm=1000.0))
    svc.stop()
    # After stop, the file handle should be closed; no further rows on re-read
    assert svc._output_file is None


def test_streaming_file_closed_after_reset(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm"), output_path=out)
    svc.append(_snap(0.0, rpm=1000.0))
    svc.reset()
    assert svc._output_file is None


def test_streaming_time_ms_column_relative_to_first_row(tmp_path) -> None:
    svc = LiveCaptureSessionService()
    out = tmp_path / "stream.csv"
    svc.start(_profile("rpm"), output_path=out)
    svc.append(_snap(0.0, rpm=1000.0))
    svc.append(_snap(1.0, rpm=1500.0))
    svc.stop()
    rows = list(csv.DictReader(io.StringIO(out.read_text())))
    assert rows[0]["Time_ms"] == "0"
    assert float(rows[1]["Time_ms"]) == pytest.approx(1000.0, abs=1.0)


def test_no_streaming_when_output_path_not_given() -> None:
    svc = LiveCaptureSessionService()
    svc.start(_profile("rpm"))
    svc.append(_snap(0.0, rpm=1000.0))
    assert svc._output_file is None
    svc.stop()
