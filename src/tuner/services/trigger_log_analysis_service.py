from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from tuner.domain.ecu_definition import EcuDefinition
from tuner.domain.output_channels import OutputChannelSnapshot
from tuner.services.local_tune_edit_service import LocalTuneEditService


_TRIGGER_PATTERN_NAMES: dict[int, str] = {
    0: "Missing Tooth",
    1: "Basic Distributor",
    2: "Dual Wheel",
    3: "GM 7X",
    16: "36-2-2-2",
    17: "36-2-1",
    25: "Rover MEMS",
}

_SECONDARY_TRIGGER_NAMES: dict[int, str] = {
    0: "Single tooth cam",
    1: "4-1 cam",
    2: "Poll level cam",
    3: "Rover 5-3-2 cam",
    4: "Toyota 3 Tooth",
}

_CAM_CONFIGURABLE_PATTERNS: frozenset[int] = frozenset({0, 25})
_CAM_INHERENT_PATTERNS: frozenset[int] = frozenset({2, 4, 8, 9, 11, 12, 13, 14, 18, 19, 20, 21, 22, 24, 26, 27})
_CRANK_ONLY_PATTERNS: frozenset[int] = frozenset({3, 5, 6, 7, 10, 15, 16, 17, 23})


@dataclass(slots=True, frozen=True)
class TriggerDecoderContext:
    decoder_name: str
    wheel_summary: str
    sequential_requested: bool
    cam_mode: str
    full_sync: bool | None
    tooth_count: float | None
    missing_teeth: float | None


@dataclass(slots=True, frozen=True)
class TriggerLogAnalysisSummary:
    source_path: Path | None
    log_kind: str
    severity: str
    sample_count: int
    channel_count: int
    time_span_ms: float | None
    columns: tuple[str, ...]
    capture_summary_text: str
    decoder_summary_text: str
    operator_summary_text: str
    findings: tuple[str, ...]
    preview_text: str


class TriggerLogAnalysisService:
    def analyze_csv(
        self,
        path: Path,
        *,
        edits: LocalTuneEditService,
        definition: EcuDefinition | None,
        runtime_snapshot: OutputChannelSnapshot | None,
    ) -> TriggerLogAnalysisSummary:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = tuple(reader.fieldnames or ())
            rows = [row for row in reader]
        return self.analyze_rows(
            rows,
            columns=headers,
            source_path=path,
            edits=edits,
            definition=definition,
            runtime_snapshot=runtime_snapshot,
        )

    def analyze_rows(
        self,
        rows: list[dict[str, str]],
        *,
        columns: tuple[str, ...],
        source_path: Path | None,
        edits: LocalTuneEditService,
        definition: EcuDefinition | None,
        runtime_snapshot: OutputChannelSnapshot | None,
    ) -> TriggerLogAnalysisSummary:
        normalized_columns = tuple(column.strip() for column in columns if column and column.strip())
        log_kind = self._detect_log_kind(normalized_columns)
        decoder_context = self._decoder_context(edits, definition, runtime_snapshot)
        time_series = self._extract_time_series(rows, normalized_columns)
        channel_count = max(0, len(normalized_columns) - (1 if time_series is not None else 0))
        findings: list[str] = []
        severity = "info"

        if not rows:
            findings.append("The log is empty. Capture a fresh tooth, composite, or trigger log before diagnosing sync issues.")
            severity = "warning"

        if len(rows) < 20:
            findings.append("The capture is very short. Record a longer log so sync loss and missing-tooth gaps are visible.")
            severity = "warning"

        if time_series is None:
            findings.append("No usable time column was found. Import a CSV that includes timestamp, timeMs, or similar timing data.")
            severity = "warning"
            time_span_ms = None
        else:
            time_span_ms = max(0.0, time_series[-1] - time_series[0]) if len(time_series) >= 2 else 0.0
            if any(right <= left for left, right in zip(time_series, time_series[1:])):
                findings.append("Timestamps are not strictly increasing. The capture may be truncated or exported incorrectly.")
                severity = "warning"
            if decoder_context.decoder_name == "Missing Tooth":
                gap_ratio = self._missing_tooth_gap_ratio(time_series)
                if gap_ratio is None:
                    findings.append("The current log does not show a clear missing-tooth gap. Recheck the wheel pattern, sensor polarity, and logger capture window.")
                    severity = "warning"
                else:
                    expected_ratio = self._expected_missing_tooth_gap_ratio(decoder_context)
                    if expected_ratio is not None and abs(gap_ratio - expected_ratio) <= 0.4:
                        findings.append(
                            f"Detected missing-tooth gap looks plausible for the loaded wheel: observed {gap_ratio:.2f}x normal tooth spacing versus expected {expected_ratio:.2f}x."
                        )
                    elif expected_ratio is not None:
                        findings.append(
                            f"Detected missing-tooth gap does not match the loaded wheel well: observed {gap_ratio:.2f}x normal tooth spacing versus expected {expected_ratio:.2f}x. Recheck wheel geometry and capture scaling."
                        )
                        severity = "warning"
                    else:
                        findings.append(f"Detected missing-tooth gap is about {gap_ratio:.2f}x the normal tooth spacing.")

        if decoder_context.sequential_requested and decoder_context.cam_mode == "crank_only":
            findings.append("Sequential fuel or ignition is requested, but the loaded decoder context is crank-only. Full sync will not be stable without a decoder/cam change.")
            severity = "warning"
        elif decoder_context.sequential_requested and decoder_context.cam_mode == "cam_optional" and log_kind == "tooth":
            findings.append("Sequential operation depends on cam sync here. A tooth log may miss phase errors; import a composite or trigger log if sync remains unstable.")
        elif decoder_context.sequential_requested and decoder_context.cam_mode == "cam_present" and log_kind == "tooth":
            findings.append("A tooth log is useful for gap sanity checks, but a composite or trigger log will be better for verifying crank/cam phase alignment.")
        elif log_kind in {"composite", "trigger"} and decoder_context.cam_mode in {"cam_present", "cam_optional"}:
            phase_finding, phase_warning = self._phase_plausibility_finding(rows, normalized_columns, decoder_context)
            if phase_finding is not None:
                findings.append(phase_finding)
            if phase_warning:
                severity = "warning"

        if decoder_context.full_sync is False:
            findings.append("Live runtime telemetry currently says full sync is not present. Compare this capture against the selected decoder before trusting timing or tune-learn data.")
            severity = "warning"

        if not findings:
            findings.append("The capture looks structurally usable. Compare tooth spacing and phase transitions against the expected decoder pattern.")

        capture_summary = self._capture_summary_text(
            log_kind=log_kind,
            sample_count=len(rows),
            channel_count=channel_count,
            time_span_ms=time_span_ms,
        )
        decoder_summary = self._decoder_summary_text(decoder_context)
        operator_summary = findings[0]
        preview_text = self._preview_text(rows, normalized_columns)
        return TriggerLogAnalysisSummary(
            source_path=source_path,
            log_kind=log_kind,
            severity=severity,
            sample_count=len(rows),
            channel_count=channel_count,
            time_span_ms=time_span_ms,
            columns=normalized_columns,
            capture_summary_text=capture_summary,
            decoder_summary_text=decoder_summary,
            operator_summary_text=operator_summary,
            findings=tuple(findings),
            preview_text=preview_text,
        )

    @staticmethod
    def _detect_log_kind(columns: tuple[str, ...]) -> str:
        haystack = " ".join(column.lower() for column in columns)
        if "composite" in haystack:
            return "composite"
        if "tooth" in haystack:
            return "tooth"
        if "trigger" in haystack or "cam" in haystack or "crank" in haystack:
            return "trigger"
        return "unknown"

    def _decoder_context(
        self,
        edits: LocalTuneEditService,
        definition: EcuDefinition | None,
        runtime_snapshot: OutputChannelSnapshot | None,
    ) -> TriggerDecoderContext:
        trig_pattern = int(self._numeric_value(edits, definition, ("TrigPattern", "triggertype", "decoder", "pattern")) or 0)
        tooth_count = self._numeric_value(edits, definition, ("nTeeth", "numTeeth", "toothCount", "triggerTeeth", "crankTeeth"))
        missing_teeth = self._numeric_value(edits, definition, ("missingTeeth", "missingTooth"))
        spark_mode = self._numeric_value(edits, definition, ("sparkMode",))
        inj_layout = self._numeric_value(edits, definition, ("injLayout",))
        trig_pattern_sec = self._numeric_value(edits, definition, ("trigPatternSec",))
        cam_input = self._numeric_value(edits, definition, ("camInput",))

        sequential_requested = spark_mode == 3.0 or inj_layout == 3.0
        if trig_pattern in _CAM_INHERENT_PATTERNS:
            cam_mode = "cam_present"
        elif trig_pattern in _CAM_CONFIGURABLE_PATTERNS:
            cam_mode = "cam_present" if ((trig_pattern_sec is not None and trig_pattern_sec >= 0.0) or (cam_input is not None and cam_input > 0.0)) else "cam_optional"
        elif trig_pattern in _CRANK_ONLY_PATTERNS:
            cam_mode = "crank_only"
        else:
            cam_mode = "unknown"

        wheel_bits: list[str] = []
        if tooth_count is not None:
            if missing_teeth is not None and missing_teeth > 0.0:
                wheel_bits.append(f"{int(round(tooth_count))}-{int(round(missing_teeth))}")
            else:
                wheel_bits.append(f"{int(round(tooth_count))}-tooth")
        if trig_pattern_sec is not None and trig_pattern_sec >= 0.0:
            wheel_bits.append(_SECONDARY_TRIGGER_NAMES.get(int(round(trig_pattern_sec)), "secondary trigger configured"))

        runtime_values = runtime_snapshot.as_dict() if runtime_snapshot is not None else {}
        full_sync_value = runtime_values.get("runtimeStatusA")
        if full_sync_value is not None:
            full_sync = bool(int(round(full_sync_value)) & (1 << 4))
        elif "rSA_fullSync" in runtime_values:
            full_sync = runtime_values.get("rSA_fullSync", 0.0) >= 0.5
        else:
            full_sync = None

        return TriggerDecoderContext(
            decoder_name=_TRIGGER_PATTERN_NAMES.get(trig_pattern, f"pattern {trig_pattern}"),
            wheel_summary=", ".join(wheel_bits) if wheel_bits else "wheel geometry not loaded",
            sequential_requested=sequential_requested,
            cam_mode=cam_mode,
            full_sync=full_sync,
            tooth_count=tooth_count,
            missing_teeth=missing_teeth,
        )

    @staticmethod
    def _numeric_value(
        edits: LocalTuneEditService,
        definition: EcuDefinition | None,
        candidate_names: tuple[str, ...],
    ) -> float | None:
        lower_candidates = tuple(candidate.lower() for candidate in candidate_names)
        definition_names = {scalar.name.lower(): scalar.name for scalar in definition.scalars} if definition is not None else {}
        for candidate in candidate_names:
            tune_value = edits.get_value(candidate)
            if tune_value is not None and isinstance(tune_value.value, (int, float)):
                return float(tune_value.value)
        for lower_candidate in lower_candidates:
            canonical = definition_names.get(lower_candidate)
            if canonical is None:
                continue
            tune_value = edits.get_value(canonical)
            if tune_value is not None and isinstance(tune_value.value, (int, float)):
                return float(tune_value.value)
        base_tune = edits.base_tune_file
        if base_tune is None:
            return None
        for value in (*base_tune.constants, *base_tune.pc_variables):
            if value.name.lower() in lower_candidates and isinstance(value.value, (int, float)):
                return float(value.value)
        return None

    @staticmethod
    def _extract_time_series(rows: list[dict[str, str]], columns: tuple[str, ...]) -> list[float] | None:
        time_column = None
        for candidate in columns:
            lowered = candidate.lower()
            if lowered in {"time", "timems", "timestamp", "time_ms", "time (ms)"} or "time" in lowered:
                time_column = candidate
                break
        if time_column is None:
            return None
        series: list[float] = []
        for row in rows:
            raw = row.get(time_column, "").strip()
            if not raw:
                continue
            try:
                series.append(float(raw))
            except ValueError:
                continue
        return series if series else None

    @staticmethod
    def _missing_tooth_gap_ratio(time_series: list[float]) -> float | None:
        if len(time_series) < 6:
            return None
        deltas = [right - left for left, right in zip(time_series, time_series[1:]) if right > left]
        if len(deltas) < 4:
            return None
        sorted_deltas = sorted(deltas)
        median = sorted_deltas[len(sorted_deltas) // 2]
        if median <= 0.0:
            return None
        ratio = max(deltas) / median
        if ratio < 1.6:
            return None
        return ratio

    @staticmethod
    def _expected_missing_tooth_gap_ratio(context: TriggerDecoderContext) -> float | None:
        if context.missing_teeth is None or context.missing_teeth <= 0.0:
            return None
        return context.missing_teeth + 1.0

    def _phase_plausibility_finding(
        self,
        rows: list[dict[str, str]],
        columns: tuple[str, ...],
        context: TriggerDecoderContext,
    ) -> tuple[str | None, bool]:
        crank_column = self._find_signal_column(columns, ("crank", "trigger1", "primary", "composite1"))
        cam_column = self._find_signal_column(columns, ("cam", "trigger2", "secondary", "composite2", "sync"))
        if crank_column is None:
            return ("The composite/trigger log does not expose a clear crank signal column. Capture crank and cam channels together for phase troubleshooting.", True)
        if cam_column is None:
            if context.sequential_requested or context.cam_mode == "cam_present":
                return ("The loaded decoder context expects crank and cam evidence, but this log does not expose a cam/secondary channel.", True)
            return ("This composite/trigger log does not expose a cam/secondary channel. That may be acceptable if you are only verifying crank sync.", False)

        crank_values = self._numeric_signal(rows, crank_column)
        cam_values = self._numeric_signal(rows, cam_column)
        if crank_values is None or cam_values is None:
            return ("Crank or cam columns could not be parsed as numeric signals. Re-export the composite/trigger log with raw signal values.", True)

        crank_edges = self._edge_count(crank_values)
        cam_edges = self._edge_count(cam_values)
        if crank_edges <= 0:
            return ("The crank channel does not show any visible transitions. Verify trigger capture settings and sensor polarity.", True)
        if cam_edges <= 0:
            return ("The cam/secondary channel does not show any visible transitions. Verify the secondary trigger input and capture wiring.", True)
        edge_ratio = crank_edges / cam_edges if cam_edges else None
        if edge_ratio is not None and edge_ratio >= 4.0:
            return (
                f"Crank/cam edge density looks plausible for phase troubleshooting: {crank_edges} crank edges versus {cam_edges} cam edges in this capture.",
                False,
            )
        return (
            f"Crank/cam edge density looks unusual: {crank_edges} crank edges versus {cam_edges} cam edges. Recheck the selected decoder, cam pattern, and logger scaling.",
            True,
        )

    @staticmethod
    def _find_signal_column(columns: tuple[str, ...], tokens: tuple[str, ...]) -> str | None:
        for column in columns:
            lowered = column.lower()
            if any(token in lowered for token in tokens):
                return column
        return None

    @staticmethod
    def _numeric_signal(rows: list[dict[str, str]], column: str) -> list[float] | None:
        values: list[float] = []
        for row in rows:
            raw = row.get(column, "").strip()
            if not raw:
                return None
            try:
                values.append(float(raw))
            except ValueError:
                return None
        return values

    @staticmethod
    def _edge_count(values: list[float]) -> int:
        return sum(1 for left, right in zip(values, values[1:]) if left != right)

    @staticmethod
    def _capture_summary_text(
        *,
        log_kind: str,
        sample_count: int,
        channel_count: int,
        time_span_ms: float | None,
    ) -> str:
        span_text = f"{time_span_ms:.1f} ms" if time_span_ms is not None else "unknown span"
        return f"Capture: {log_kind} log, {sample_count} row(s), {channel_count} signal column(s), {span_text}."

    @staticmethod
    def _decoder_summary_text(context: TriggerDecoderContext) -> str:
        cam_text = {
            "cam_present": "cam sync is available in the loaded decoder context",
            "cam_optional": "cam sync is configurable and may still need a composite/trigger log to verify phase",
            "crank_only": "the loaded decoder context is crank-only",
            "unknown": "cam sync expectations are not clear from the loaded tune",
        }[context.cam_mode]
        sync_text = (
            "full sync is currently reported"
            if context.full_sync is True
            else "full sync is currently not reported"
            if context.full_sync is False
            else "runtime sync status is not available"
        )
        return (
            f"Decoder: {context.decoder_name}. Wheel: {context.wheel_summary}. "
            f"Sequential requested: {'yes' if context.sequential_requested else 'no'}. "
            f"Context: {cam_text}; {sync_text}."
        )

    @staticmethod
    def _preview_text(rows: list[dict[str, str]], columns: tuple[str, ...]) -> str:
        if not rows or not columns:
            return "No preview available."
        preview_lines = [", ".join(columns)]
        for row in rows[:8]:
            preview_lines.append(", ".join(row.get(column, "").strip() for column in columns))
        if len(rows) > 8:
            preview_lines.append("...")
        return "\n".join(preview_lines)
