# Architecture

## Overview

Native C++ Qt 6 desktop application built on the `tuner_core` static library.

## Layers

- `tuner_core` (static library, 173 source files)
  INI/MSQ/native parsers, protocol codecs, table generators, analysis services,
  dashboard layout, gauge zones, telemetry decoders. Pure logic, no Qt dependency.
- `transports` (within tuner_core)
  Serial (Win32 COM), TCP (Winsock2 with Speeduino framing), mock.
- `app` (Qt 6 application)
  Single-file Qt shell (`main.cpp`) assembling tuner_core services into a tabbed UI.
  Theme tokens in `theme.hpp`.

## Dependency Rules

- UI depends inward on services and domain/view models only.
- Services may depend on domain, parsers, comms, transports, and other services.
- Comms does not depend on Qt.
- Parsers return typed models, not widget-ready objects.
- Raw INI dialogs/panels are compiled into stable layout/page models before the UI consumes them.

Long-term architectural direction:

- treat legacy INI/MSQ parsing as a compatibility boundary, not the permanent internal authoring model
- keep semantic tune/definition/project models separate from firmware page/offset storage details
- preserve the option for future native definition files (`JSON5`-style authored schema) and tune/project files (`JSON`-style semantic data) without forcing UI or service layers to understand legacy storage quirks directly

## Current Application Shape

The app shell in `TunerMainWindow` (cpp/app/main.cpp) currently exposes eight first-class sidebar surfaces (Alt+1..8 shortcuts, keyword-matched):

- `TUNE` — page tree + scalar/table/curve editors + review dialog
- `LIVE` — animated dashboard gauges + status strip + formula-channel readout + hardware test panel
- `FLASH` — preflight checklist + firmware picker + flash execution with progress bar
- `SETUP` — 6-step Engine Setup Wizard + table generators + compressor map modeling
- `ASSIST` — VE Analyze (accumulator + smoothing + diagnostics), WUE Analyze, Virtual Dyno with before/after overlay
- `TRIGGERS` — log capture, CSV import, oscilloscope waveform view, analysis findings
- `LOGGING` — profile editor, capture to CSV, import + scrubbable timeline + Airbear SD log browser
- `HISTORY` — 81-service manifest for the ported C++ core

Each surface is assembled by a `build_<name>_tab` free function that wires `tuner_core` services into Qt widgets. There is no presenter class in the C++ app — the presenter-driven architecture that existed in the Python reference lives as a shared-state closure in main.cpp (Workspace + EditService + EcuConnection shared_ptrs passed through the build functions).

## Tuning Workspace Architecture

Current stack (Python→C++ port complete):

```text
INI / MSQ / native file parsing  (tuner_core)
    ->
definition_layout  +  visibility_expression  +  setting_context_help
    ->
tuning_page_grouping  (tables/scalars/curves folded into keyword groups)
    ->
workspace_state  +  local_tune_edit
    ->
build_tune_tab()  (cpp/app/main.cpp)
```

### Key services (C++)

- `tuner_core::definition_layout`
  Compiles INI dialogs, menus, help, visibility expressions, and metadata into editor-facing layout structures.

- `tuner_core::tuning_page_grouping`
  Builds grouped scalar/table/curve pages folded by keyword family (Fuel / Ignition / Idle / Boost / Sensors / Enrich / Protection / Comms / General).

- `tuner_core::curve_editor` parser
  Parses `[CurveEditor]` definitions (34 curves in the production INI); the TUNE tab's curve page builds a bar chart + editable Y table from each.

- `tuner_core::workspace_state`
  Tracks per-page state (clean / staged / written) and aggregate state transitions for the review dialog.

- `tuner_core::local_tune_edit::EditService`
  Holds staged scalar and list edits; the review dialog reads `staged_names()` and writes through `replace_list` / `stage_scalar_value`.

- `tuner_core::visibility_expression`
  Evaluates INI visibility expressions against the live tune state + output-channel arrays; pages whose expressions resolve false are hidden from the tree.

### Editing model

- offline editing is first-class
- edits are staged before write/burn
- page state is explicit: clean / staged / invalid / written
- sync state is explicit: offline / RAM-different / flash-aligned / mismatch context

## Table Editor Design

The table editor is intentionally split into:

- full render/rebuild path for real page/table changes
- partial single-cell/axis refresh for table edits
- evidence-only refresh for runtime/datalog evidence churn

This separation is deliberate. Runtime evidence must not trigger full table-model rebuilds.

High-level structure:

```text
table page snapshot
    ->
render header / diff / help / evidence
    ->
optional grid rebuild
    ->
highlight / fit / auxiliary sections
```

Important current rule:

- evidence and replay updates should refresh only evidence widgets unless the table content itself changed

## Engine Setup / Hardware Setup

The SETUP tab hosts the single Engine Setup Wizard — a 6-step QDialog covering:

1. Board / MCU — 5 board options (DropBear default)
2. Engine / Induction — displacement, cylinders, compression ratio, turbo envelope
3. Injectors / Fueling — 18 injector presets, pressure compensation, AE mode
4. Trigger / Ignition — trigger pattern, coil preset, dwell
5. Sensors / Baro — MAP/baro/TPS/CLT/IAT presets + wideband calibration
6. Review — summary card with all staged values before Finish

The wizard stages values via `EditService::stage_scalar_value`; on Finish the workspace is dirty and the standard review → write → burn flow takes over. The SETUP tab also surfaces the six table generators (VE / AFR / Spark / WUE / Cranking / Idle) + thermistor calibration + reqFuel calculator + compressor map modeling card.

Supporting C++ service cluster (all under `tuner_core::`):

- `hardware_setup_validation`
- `hardware_setup_generator_context`
- `hardware_presets`
- `required_fuel_calculator`
- `operator_engine_context`
- `ve_table_generator`, `spark_table_generator`, `boost_table_generator`, `idle_rpm_generator`, `startup_enrichment_generator`
- `compressor_map_modeling`
- `thermistor_calibration`
- `wideband_calibration`

## Runtime Evidence / Replay Architecture

Current evidence flow:

```text
live runtime snapshot or replay row
    ->
SurfaceEvidenceService / EvidenceReplayService
    ->
history, comparison, export, active-page evidence
    ->
Runtime / Flash / Tuning workspace surfaces
```

Implemented service seams (all under `tuner_core::`):

- `datalog_import`, `datalog_profile`, `datalog_replay`
- `live_capture_session`, `live_trigger_logger`
- `table_replay_context`
- `trigger_log_analysis`, `trigger_log_visualization`

UI integration:

- LIVE tab: `EcuConnection::poll_runtime()` at 200 ms tick populates the snapshot; gauge bindings read by widget_id/source.
- LOGGING tab: `live_capture_session::append_record` on each tick; `format_csv` writes real-time to the capture file. The imported-log replay uses `LogTimelineWidget` for scrubbable timeline with play/pause + channel picker + shift-drag zoom + export.
- TRIGGERS tab: `TriggerScopeWidget` renders decoded traces as stacked oscilloscope tracks.
- ASSIST tab: `ve_cell_hit_accumulator` + `ve_proposal_smoothing` + `ve_root_cause_diagnostics` feed the VE Analyze results panel; coverage and CF grids carry per-cell hover tooltips.

Current product behavior:

- evidence snapshots can be captured, reviewed, exported, and pinned
- datalog rows can be replayed into workspace evidence review
- table pages can show evidence and replay context without rebuilding the grid on every poll
- live capture sessions record filtered snapshots according to a named `DatalogProfile`

Live logging architecture:

```text
definition output_channel_definitions
    ->
DatalogProfileService.default_profile()  (or operator-edited profile)
    ->
LiveCaptureSessionService  (start / append on each poll tick / stop)
    ->
to_csv() / save_csv()  →  standard CSV with Time_ms + channel columns
    ->
DatalogImportService  (load saved CSV back for replay/review)
```

`DatalogProfile` is a named ordered list of `DatalogChannelEntry` records:
- `name` / `label` / `units` — metadata from definition; operator-editable
- `enabled` — whether the channel is recorded in the current capture
- `format_digits` — decimal places for CSV export

Profile collection sidecar (`.logging-profile.json`) auto-loaded on project open, auto-saved on profile change.

## Trigger Logger Protocol

Live trigger log capture is wired end-to-end from the INI definition to decoded records.

Architecture:

```text
[LoggerDefinition] INI section
    ->
_parse_logger_definitions()  →  list[LoggerDefinition]  (on EcuDefinition)
    ->
SpeeduinoControllerClient.fetch_logger_data(logger_def)
    start command → poll toothLog1Ready bit → dataReadCommand → raw bytes → stop command
    ->
LiveTriggerLoggerService.decode(logger_def, raw)
    bit-level field extraction (1-bit flags, u32 LE refTime) → TriggerLogCapture
    ->
TriggerLogCapture.to_csv_path()
    →  temp CSV  →  TriggerLogAnalysisService (existing CSV analysis pipeline)
```

Four loggers are defined in the production INI:
- `tooth` (H/h) — 127 × 4-byte records; `toothTime` u32 LE in µs
- `compositeLogger` (J/j) — 127 × 5-byte records; 6 flag bits + `refTime` u32 LE × 0.001 = ms
- `compositeLogger2` (O/o) — second cam composite
- `compositeLogger3` (X/x) — both cams composite

`toothLog1Ready` is polled from runtime byte 1, bit 6 while waiting for the buffer to fill.

UI: Trigger Logs tab has a live-capture section (logger selector combo + "Capture Live Log" button) alongside the existing CSV import path. Capture runs in a `TriggerCaptureWorker` QThread.

## VE Analyze and WUE Analyze Service Layer

VE Analyze and WUE Analyze are both wired end-to-end:

**VE Analyze services:**
- `ReplaySampleGateService`
- `AutotuneFilterGateEvaluator`
- `VeAnalyzeCellHitService`
- `VeAnalyzeCellHitAccumulator`
- `VeAnalyzeReviewService`
- `LiveVeAnalyzeSessionService`

**WUE Analyze services:**
- `WueAnalyzeAccumulator`
- `WueAnalyzeService`
- `LiveWueAnalyzeSessionService`
- `WueAnalyzeReviewService`

Current architectural status:

- batch and live accumulation for both VE and WUE Analyze
- per-cell lambda target lookup for both
- proposal staging via `apply_ve_analyze_proposals()` (stages all proposals as table cell edits)
- `VeAnalyzeReviewService` and `WueAnalyzeReviewService` drive detail panels
- workspace UI: start/stop/reset/apply buttons and VE Analyze/WUE Analyze tabs on table pages
- WUE Analyze uses 1D CLT-axis orientation detection and WUE-specific default gating (no minCltFilter)

## TCP/WiFi Transport and Protocol Framing

`TcpTransport` implements the Speeduino new-protocol framing over TCP:

```text
write_framed(payload):
    [u16 LE len] + payload + [u32 LE CRC32(payload)]
read_framed_response(timeout):
    read 2-byte header → payload_len
    read payload_len + 4 bytes → payload + CRC
    return payload
```

`SpeeduinoControllerClient._send_data_command()` and `_recv_data_response()` detect framing capability via `getattr` so the controller is transport-agnostic:

- over TCP: framed (required by Airbear bridge)
- over serial: raw (unchanged legacy path)

Q/S identification commands remain unframed — Airbear special-cases these.

"Connect via WiFi" in the Runtime panel prefills `speeduino.local:2000`/TCP/SPEEDUINO and is enabled/disabled based on the `boardCap_wifiTransport` telemetry bit (byte 130, bit 7).

## HTTP Live-Data API

`LiveDataHttpServer` runs an opt-in background HTTP server (default port 8080):

```text
MainWindow Runtime poll tick
    ->
live_data_server.update_snapshot(snapshot)     [Qt thread]
    ->
_lock  →  _channels / _channel_units dict
    ->
HTTP handler thread:
    GET /api/channels        →  {name: value, ...}
    GET /api/channels/{name} →  {name, value, units}
    GET /api/status          →  {connected, sync_state, port}
```

All responses include CORS headers for cross-origin browser/dashboard access. Start/stop toggled via "Start Live Data API" button in the Runtime panel. `update_status()` is called on connect and disconnect.

## Dashboard Architecture

Dashboard is a first-class top-level surface.

- `DashboardPanel` — gauge cluster panel with toolbar (Load/Save/Default Layout, Fullscreen)
- `DashboardLayoutService` — load/save `DashboardLayout` as JSON; `default_layout()` returns 11 Speeduino gauges
- `DashboardWidget` domain model — `kind`, `source`, `units`, `min_value`/`max_value`, `color_zones`, `tune_page`, grid position
- `GaugeConfigDialog` — per-gauge editor auto-filled from the INI gauge catalog (`GaugeConfiguration` from `[GaugeConfigurations]`): title, units, lo/hi display range, warn/danger thresholds → color zones
- Drag-and-drop rearrangement via `swap_requested Signal(str, str)`
- `DashboardFullscreenWindow` — borderless fullscreen QDialog, exits on Escape or double-click
- INI gauge catalog: `_parse_gauge_configurations()` produces 70+ `GaugeConfiguration` objects; `_parse_front_page()` produces 8 gauge slot assignments and 40+ `FrontPageIndicator` expressions

## Board, Firmware, and Bench Workflow Integration

Phase 9 is complete:

- `FirmwareCapabilities.runtime_trust_summary()` and `uncertain_channel_groups()` — evidence quality signals
- `BoardDetectionService.detect_from_capabilities()` — capability-first board detection with text-heuristic fallback
- `SessionService.reconnect_signature_changed()` and `prior_firmware_signature` — reconnect mismatch detection
- Reconnect signature warning dialog + status bar message wired in `MainWindow`
- Uncertain channel groups dimmed with tooltip in Runtime channel table
- `TcpTransport` + WiFi connect button
- `LiveTriggerLoggerService` + live capture UI

## Runtime / Flash / Bench Workflow

Supporting services:

- `SessionService`
- `SpeeduinoRuntimeTelemetryService`
- `FirmwareCatalogService`
- `FlashPreflightService`
- `FlashTargetDetectionService`
- `FirmwareFlashService`
- `BoardDetectionService`

## Design Priorities

Current priorities remain:

1. preserve legacy tuning software operating model for Speeduino-first workflows
2. keep offline editing equal to live editing
3. make sync/write/burn/revert states explicit
4. keep hardware/setup guidance reviewable and staged
5. keep evidence, replay, and future autotune behavior explainable
6. avoid UI-driven business logic and re-entrant widget coupling

## INI Preprocessor

The INI parser supports `#if`/`#else`/`#endif`/`#set`/`#unset` directives:

- two-phase evaluation: file-scope `#set`/`#unset` defaults collected first, then `active_settings` merged on top
- `active_settings` always wins over file-level defaults
- validated against production Speeduino INI
- `#define` lines preserved for downstream macro expansion
- nested conditionals supported

`active_settings` persisted to the project file (`activeSettings=LAMBDA,mcu_teensy`). "Definition Settings" toolbar button opens `DefinitionSettingsDialog` — shows `[SettingGroups]` as checkboxes or comboboxes; updates project and reloads definition on accept.

## Near-Term Direction

Most realistic next architecture slices:

- `[ControllerCommands]` dispatch — parse the 70+ named commands (injector test, spark test, STM32 reboot, SD format, VSS cal) and wire a hardware test surface
- hardening and release prep (Phase 10) — port-busy recovery for HTTP server, operator-facing diagnostics, integration test coverage
- final workspace/table polish (density/fit, interaction parity edge cases)
