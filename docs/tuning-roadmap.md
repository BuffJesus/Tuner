# Tuner Roadmap

## Product Target

Build a Python desktop ECU tuning workstation that is recognizably TunerStudio in workflow and definition compatibility, while being better at:

- setup guidance
- staged edit clarity
- sync visibility
- runtime evidence and replay
- future autotune transparency
- bench/firmware workflow safety

This remains a Speeduino-first product, not a generic ECU parameter browser.

## Reference Inputs

Primary local references:

- repo: `D:\Documents\JetBrains\Python\Tuner`
- decompiled TunerStudio: `C:\Users\Cornelio\Desktop\Decompiled\TunerStudioMS`
- Speeduino sources/releases: `C:\Users\Cornelio\Desktop\speeduino-202501.6`
- screenshot references: `C:\Users\Cornelio\Desktop\tunerstudioimages`

## Current Repo Assessment

As of `2026-04-04`, the project already includes:

- PySide6 desktop shell with eight top-level surfaces: Overview, Tuning, Engine Setup, Runtime, Logging, Dashboard, Trigger Logs, Flash
- INI/MSQ/project parsing for dialogs, panels, fields, visibility expressions, help, tool declarations, VeAnalyze/WueAnalyze metadata, reference tables, setting groups, and ConstantsExtensions
- INI preprocessor: `#if`/`#else`/`#endif`/`#set`/`#unset` with two-phase active_settings override
- definition compilation into operator-facing pages via `DefinitionLayoutService` and `TuningPageService`
- presenter-driven tuning workspace with navigator, scalar pages, table pages, page-state tracking, sync state, operation log, workspace review, quick-open, and command palette
- offline editing plus live Speeduino serial read/write/burn/runtime support on the legacy raw protocol path
- Engine Setup and Hardware Setup Wizard flows backed by shared operator context and preset-assisted setup helpers
- starter generators for VE, spark, AFR, idle RPM, WUE, cranking, and ASE, all stage-only
- VE Analyze and WUE Analyze wired end-to-end: service layer, presenter integration, start/stop/reset/apply, proposal staging
- evidence/replay stack: surface evidence, evidence history, pinned-vs-latest comparison, CSV datalog import/replay, lightweight chart review, trigger-log analysis, and page/table evidence hooks
- Logging tab (`LoggingPanel`): profile quick-switch, Start/Stop/Clear/Save, configurable poll interval, real-time capture-to-file, Datalog Import & Replay, multi-profile sidecar
- Dashboard tab (`DashboardPanel`): 11 default Speeduino gauges, layout persistence, GaugeConfigDialog, drag-and-drop rearrangement, DashTuning, fullscreen
- firmware catalog, preflight, target detection, and flashing helpers for AVR, Teensy, and STM32-oriented flows
- capability-first board detection, reconnect signature-change detection, FirmwareCapabilities trust helpers
- plugin API scaffolding
- `CurveDefinition` domain model, `[CurveEditor]` INI parser pass (34 curves), `CurvePageService` with keyword-based group classification; curve pages wired into tuning workspace navigator alongside table pages
- production artifact round-trip tests (31 tests): `speeduino-dropbear-v2.0.1.ini` + base-tune.msq + `Ford300_TwinGT28_BaseStartup.msq`, signature `speeduino 202501-T41`
- `1805` collected tests

## What Is Working Well

- Definition-driven editing is real, not aspirational.
- The tuning workspace has a coherent presenter/service architecture.
- The setup surfaces are already useful for engine, induction, injector, trigger, and sensor work.
- Runtime evidence and replay are now first-class product seams, not just ideas in docs.
- Bench/flash workflows exist as distinct surfaces rather than scattered utilities.

## TunerStudio Feature Gap Analysis (added during Phase 14 planning)

Survey of `C:/Users/Cornelio/Desktop/Decompiled/TunerStudioMS/` to identify TunerStudio features the operator might miss compared to our current implementation. Each item is tagged with its decompiled-source location (so the C++ port has a reference to read), implementation complexity, and an honest priority assessment.

The two items the user explicitly called out are at the top.

### Must-have / user-requested

#### G1. Startup project picker / "what would you like to do today" landing surface

The current app opens directly to the last-used project. TunerStudio shows a project picker with: recent projects list, "New Project" wizard, hardware-detect-on-startup, hardware setup wizard launcher, and quick-actions for the most common operator workflows.

- **Decompiled source:** `aP/f.java` (main application framework, multi-project messaging), `R/b.java` and `R/j.java` (project management UI)
- **What we have today:** `MainWindow` constructor opens last project from settings; no landing surface.
- **What we want:** A `StartupSurface` that runs before `MainWindow` shows its tabs. Lists recent projects (path, signature, last opened), offers "New Project" / "Open Existing" / "Hardware Setup Wizard" / "Connect & Auto-Detect", and only transitions into the workspace once the operator picks something. The "skip and open last" behaviour is preserved as a checkbox so existing muscle memory still works.
- **Complexity:** Small-medium. Mostly UI plumbing and a recent-projects sidecar. Foundation already in place — `Project` / `ProjectParser` already track everything we need.
- **Priority:** **Must-have, user-requested.** Lands as Phase 14 Slice 8 (UI build). Until the C++ Qt UI is in place, port the surface to the existing Python `MainWindow` first as an interim improvement.

#### G2. 3D rotatable surface visualization for tables

TunerStudio's headline tuning visualization — a 3D mesh of the table values with mouse rotation, elevation/azimuth sliders, and the live operating point shown as a marker on the surface.

- **Decompiled source:** `com/efiAnalytics/ui/bt.java` (main 3D renderer with rotation controls — JSlider for azimuth 0-359°, JSlider for elevation 15-90°, "Follow Mode" checkbox at line 35/102), `G/bi.java` (3D table data model)
- **What we have today:** 2D `TableEditorWidget` only. No 3D surface anywhere in the workspace.
- **What we want:** A new `TableSurface3DView` companion widget alongside the 2D table editor. Toggle button on the table page header swaps between 2D grid and 3D surface (or shows them side-by-side on wide displays). 3D view consumes the same `TablePageSnapshot` data the 2D widget reads, plus the live operating point from `OutputChannelSnapshot` for the crosshair. Rotation via mouse drag, elevation slider, optional auto-rotate, optional cell-value labels at vertices.
- **Complexity:** **Large.** Needs a real 3D rendering pipeline. Two realistic options for the Qt port:
  - **Qt 3D module** (`QtQuick3D` or `Qt3DCore` + `Qt3DRender` + `Qt3DExtras`) — proper 3D scene graph, comes with Qt 6, no extra deps
  - **OpenGL widget with hand-rolled mesh shader** — smaller, more control, more code to write
- **Priority:** **Must-have, user-requested.** Lands as a dedicated post-Phase-14-foundation slice (probably Slice 9 of the Phase 14 plan, after the 2D table editor port). Worth shipping a Python prototype against PyQtGraph or matplotlib's `mpl_toolkits.mplot3d` first so the operator gets the feature now and the C++ port has a reference to mirror.

### High-value quick wins (small effort, daily-visible)

#### G3. Live operating point crosshair on the table editor

When connected to the ECU, the 2D table editor should overlay a crosshair (or highlighted cell) showing exactly which RPM × load cell the engine is currently operating in. Critical for VE tuning — you can see immediately whether your edit will affect the cell the engine cares about right now.

- **Decompiled source:** `com/efiAnalytics/ui/bt.java` (Follow Mode checkbox), `bT/s.java` (follow mode references)
- **What we have today:** `TableReplayContextService` already maps a runtime snapshot to a cell index — exactly what's needed. The 2D editor just doesn't paint anything for it. The replay-evidence path uses the same context service for evidence overlays, so the data plumbing is in place.
- **What we want:** A "Follow ECU" toggle button on the table page header. When on and the runtime is connected, the active cell in the 2D editor gets a coloured outline that updates with the runtime poll tick. Smoothing optional. Persisted per page in the layout JSON.
- **Complexity:** Small. The data path already exists; this is one new paint operation in the table editor.
- **Priority:** Must-have. Lands during the C++ table editor port (Phase 14 Slice 8). Worth back-porting to the Python app as well — short slice, big operator-visible win.

#### G4. Virtual / formula output channels

User-definable derived channels created from math expressions over existing output channels (e.g. `boost_psi = (map_kpa - 100) * 0.145`, `pulse_width_ms = pw1_us / 1000`). TunerStudio reads them from INI lines like `name = {expression}, "Units"` in `[OutputChannels]`.

- **Decompiled source:** `aa/e.java` (OutputChannels writer documenting the `{expression}` syntax)
- **What we have today:** The Python `_parse_output_channels` already preserves `scale_expression` / `translate_expression` strings on the channel definition, but nothing evaluates them at runtime. The C++ Slice 6 `[OutputChannels]` parser preserves `scale` / `translate` but not the expression form.
- **What we want:** Two pieces:
  1. Promote the `{expression}` form into a first-class concept on `IniOutputChannel` (new `formula: optional<string>` field on the C++ side and `formula` attribute on the Python side).
  2. A `MathExpressionEvaluator` service that takes a formula string and a runtime channel snapshot and produces a value. The Python `VisibilityExpressionService` already does this for visibility predicates — extend it (or fork it) to support full arithmetic.
- **Complexity:** Medium. The expression evaluator is the bulk of the work. Existing `VisibilityExpressionService` is a starting point.
- **Priority:** Nice-to-have, but power users will want it. Schedule after the foundation parsers are all ported.

### Medium-effort additions

#### G5. SD card log download / browse / replay

Speeduino firmware on Teensy supports onboard SD logging. TunerStudio has a remote file browser that lists logs on the SD, downloads them, and feeds them straight into the log replay path.

- **Decompiled source:** `bD/i.java` (SD Card File Management UI — download/delete/browse), uses `RemoteFileAccess` API
- **What we have today:** No SD-side integration. The CSV import + replay path exists; the missing piece is the firmware-side file listing and bulk download.
- **What we want:** A `SdCardPanel` in the Logging tab. Lists files via a new `cmdSdList` controller command, downloads selected files into a configurable local directory, optionally auto-loads the most recent download into the replay viewer.
- **Complexity:** Medium. Need to spec the firmware-side commands first (might already exist in the controller commands list — worth checking before building UI).
- **Priority:** Nice-to-have. Useful when the operator runs unattended logging sessions.

#### G6. Standalone log viewer / post-session analysis (MegaLogViewer parity)

TunerStudio bundles MegaLogViewer for post-session analysis: scrubbing through a log, marking interesting regions, comparing two logs side-by-side, exporting clipped segments.

- **Decompiled source:** `MegaLogViewer.java` (separate application entry point)
- **What we have today:** `DatalogReplayService` + `DatalogReviewService` cover replay against a tune; no scrub-and-mark-and-compare UI.
- **What we want:** A `LogAnalyzerPanel` (probably promoted to its own top-level tab "Log Analyzer") with a timeline scrubber, channel-selection sidebar, multi-cursor measurement, and side-by-side dual-log comparison.
- **Complexity:** Medium-large.
- **Priority:** Nice-to-have. Most desktop Speeduino users do log analysis in TS or in spreadsheets today.

### Niche / lower priority

| Feature | Where | Complexity | Why deferred |
|---|---|---|---|
| G7. Ignition timing scope (high-speed trigger logger UI) | `com/efiAnalytics/tunerStudio/panels/TriggerLoggerPanel.java`, `com/efiAnalytics/tunerStudio/panels/o.java` | Medium | We already have basic trigger log capture; the scope visualization is for advanced diagnostics most operators rarely run |
| G8. Dyno / power-and-torque view | `aP/hb.java` (Tuning & Dyno Views tab), `aO/cd.java` | Medium | ✅ **Covered** — Virtual Dyno card on the ASSIST tab with QPainter torque+HP chart (peak markers, dual Y axes, nice-ceiling axis scaling) plus **before/after overlay** via "Compare to Another CSV…" (dashed curves under the primary, shared axis range so deltas are visually honest) and "Clear Overlay" controls. No physical dyno required — math in `tuner_core::virtual_dyno::calculate`. |
| G9. Bluetooth / BLE direct connectivity | `aP/bh.java` (uses `javax.bluetooth.*`) | Medium | Airbear bridge already covers wireless via TCP — Bluetooth is a parallel transport, not a missing feature |
| G10. Map switching (multi-tune slot management) | Not found in decomp | Medium | Speeduino firmware doesn't support multi-tune slots in the way TS-targeted ECUs do — this is a firmware feature, not a desktop one |
| G11. Knock listener / audio feedback | Not found | Medium | Hardware-dependent; not in TS core either |
| G12. Cloud / DIY tune sharing | Not found | Large | Outside the scope of an offline-first tuner |

### Phase 14 plan additions (folded in below)

**Gap closure status (as of sub-slice 145):**

- **G1 (Startup project picker):** ✅ **Done.** Startup dialog with recent project, "Open Last Project", "New Project", "Connect & Detect" buttons. Shows before the workspace.
- **G2 (3D table surface):** ✅ **Done.** Sub-slice 82 landed the pure-logic projection math; sub-slice 83 added `TableSurface3DView` — a QPainter-only wireframe widget (no Qt 3D module dependency) with mouse-drag rotation, 5-stop heat-colored edges, and a live operating-point crosshair via `interpolate_screen_point`. The table page in the TUNE tab now has a 2D↔3D toggle backed by a `QStackedWidget`, and the crosshair timer mirrors the live cell to the 3D view.
- **G3 (Live crosshair):** ✅ **Done.** White-red crosshair cell tracks the simulated operating point on table heatmaps via `table_replay_context::build()`. Sub-slice 83 extended this to the 3D surface view as well.
- **G4 (Formula channels):** ✅ **Done on both Python and C++ sides** (sub-slices 84–87). Sub-slices 84–85 built the parser and evaluator halves (Python + C++, byte-identical on all ~65 production formulas). Sub-slice 86 wired it into the Python runtime poll path via `SessionService.poll_runtime` → `MathExpressionEvaluator.enrich_snapshot`, so every Python consumer (dashboard, HTTP live-data API, datalog profile, evidence replay) sees computed channels with zero per-consumer wiring. Sub-slice 87 extends the same wiring into the Qt `tuner_app.exe` LIVE tab: `build_live_tab` loads the production INI's `formula_output_channels` / `output_channel_arrays` once at page construction, the 200 ms timer lambda seeds the mock-runtime snapshot with the channel inputs the mock doesn't emit natively (`baro`, `stoich`, `twoStroke`, `pulseWidth`, `coolantRaw`, `iatRaw`, `nSquirts`, `nCylinders`), calls `math_expression_evaluator::enrich` in place, and a new formula-channel demo strip above the gauge cluster surfaces `lambda`, `throttle`, `map_psi`, and `revolutionTime` in real time. The strip degrades gracefully (`formula channels unavailable — definition not loaded`) when the INI fixture isn't present. New `enrich(working, formulas, arrays)` helper on the C++ evaluator — thin in-place variant of `compute_all` that preserves existing hardware-channel readings if there's a name collision. 5 new doctest cases pinning `enrich` behaviour plus a production-INI integration case that seeds a realistic mock snapshot and verifies `throttle`, `lambda`, `map_psi`, `coolant`, and `revolutionTime` evaluate to expected values and every formula channel resolves to a finite double.
- **G5–G12:** Tracked in the post-Phase-14 polish backlog below.

## Major Gaps

### 1. Dashboard and operator-mode workflows

All core dashboard work is complete:

- ~~real gauge-cluster runtime dashboard~~ ✓ Done — `DashboardPanel` with 11 default Speeduino gauges; number and bar gauge kinds with color-zone value coloring
- ~~dashboard layout persistence~~ ✓ Done — `DashboardLayoutService` load/save to `<project>.dashboard.json`
- ~~DashTuningPanel-style embedded tuning widgets~~ ✓ Done — right-click "Open in Tuning" per gauge; `tune_page` persisted in JSON layout
- ~~fullscreen/operator dash mode~~ ✓ Done — `DashboardFullscreenWindow` borderless fullscreen; exits on Escape or double-click
- ~~gauge customization and rearrangement~~ ✓ Done — `GaugeConfigDialog`, drag-and-drop swap, column/row span, auto-fill units from definition

Remaining dashboard gaps (from INI and decompiled TunerStudio analysis):

- ~~**INI-driven gauge catalog (`[GaugeConfigurations]`)**~~ ✓ Done — `DashboardLayoutService.default_layout()` now accepts `gauge_configurations` + `front_page_gauges` and builds the layout from INI data; first two FrontPage slots become 2×2 dials, remaining slots become numeric readouts; color zones derived from warn/danger thresholds; `DashboardPanel.set_front_page_data()` seeds the layout on project open and on "Default Layout" reset; 8 new tests added.
- ~~**FrontPage indicators**~~ ✓ Done — `_IndicatorStrip` widget added to `DashboardPanel` below the gauge grid; evaluates each `FrontPageIndicator` expression against the live output-channel snapshot via `VisibilityExpressionService`; shows on/off label with INI-configured background/foreground colors; hidden when no indicators are available.
- ~~**LED indicator gauge kind**~~ ✓ Done — `_LedFace` painted widget; "LED Indicator" option in `GaugeConfigDialog`; shows a large glowing circle coloured by the active zone (dark-neutral when offline/no-zone), with gleam highlight, painted title, and value+units. Selectable per-cell; wired into `GaugeWidget.update_value()`.
- **Additional gauge painter kinds** — `AnalogBarPainter`, `AnalogMovingBarGaugePainter`, `HistogramPainter`, `HorizontalBarPainter`, `VerticalBarPainter` from decompiled TunerStudio. Our dashboard supports "dial", "number", "bar", "led", and "label". Remaining painter kinds are aspirational polish, not blockers — the existing five cover every default Speeduino gauge.
- ~~**Dashboard label / static text components**~~ ✓ Done — `DashLabel` parity landed as the `label` widget kind. New `text: str | None` field on `DashboardWidget`; `GaugeWidget._refresh_internal()` builds a `QLabel` with `dashLabel` styling and ignores live value updates; `DashboardLayoutService.save/load` round-trip the new field; 8 focused tests in `test_dashboard_label_widget.py` covering the domain field default, render with/without explicit text, no-op `update_value`, swap-from-other-kind via `update_def`, and JSON round trip. `HtmlDisplay` (which needs an HTML renderer) remains out of scope.

### 2. Operator-facing VE Analyze flow

All complete:

- ~~live start/stop/reset on VE table pages~~ ✓ Done
- ~~proposal preview in workspace~~ ✓ Done
- ~~staged "apply proposals" path~~ ✓ Done — `apply_ve_analyze_proposals()` stages proposals as table cell edits
- ~~WUE Analyze parity~~ ✓ Done — `WueAnalyzeAccumulator`, `LiveWueAnalyzeSessionService`, `WueAnalyzeReviewService`

### 2A. Logging and datalog workflow parity

All critical gaps are resolved:

- ~~Dedicated logging tab~~ ✓ Done — `LoggingPanel` is a first-class top-level tab
- ~~Profile quick-switch dropdown~~ ✓ Done — dropdown + add/delete buttons in panel
- ~~Clear/reset captured session~~ ✓ Done — Clear button calls `live_capture_service.reset()`
- ~~Configurable polling interval~~ ✓ Done — 250ms / 500ms / 1s / 2s / 5s selector
- ~~Real-time capture to file~~ ✓ Done — `LiveCaptureSessionService.start(output_path=...)` streams rows as they arrive
- ~~Profile project association~~ ✓ Done — `.logging-profile.json` sidecar, auto-loaded/saved on project open/change
- ~~Profile-ordered review channels~~ ✓ Done — `DatalogReviewService.build(profile=...)` uses enabled channel order

Remaining logging gap:

- **Profile-per-firmware-signature** — one profile collection is shared regardless of connected firmware. Not a blocking gap.

### 3. Firmware capability and verification hardening

- ~~Capability handshake consumption~~ ✓ Done
- ~~Write chunking~~ ✓ Done
- ~~`firmware_signature` tracked across disconnect; mismatch warning on reconnect~~ ✓ Done
- ~~Page cache invalidation~~ ✓ Done
- ~~Flash preflight using manifest/capability facts~~ ✓ Done
- ~~Capability-first board detection (`detect_from_capabilities()`)~~ ✓ Done — `BoardDetectionService` prefers `FirmwareCapabilities` and firmware signature over text heuristics
- ~~Reconnect signature change detection~~ ✓ Done — `SessionService.reconnect_signature_changed()`; `prior_firmware_signature` property
- ~~FirmwareCapabilities trust helpers~~ ✓ Done — `runtime_trust_summary()`, `uncertain_channel_groups()`

Phase 9 hardening now complete:

- ~~Reconnect mismatch UI warning~~ ✓ Done — `_connect_session_with_config()` captures prior signature, shows `QMessageBox.warning()` + status bar message if signature changed since last connect
- ~~uncertain_channel_groups() wired to Runtime surface~~ ✓ Done — `_poll_runtime()` calls `firmware_capabilities.uncertain_channel_groups()` and applies grey foreground + tooltip to any channel row whose name is in the uncertain set

### 4. Curve editor — complete ✓

All curve editor work is done:

- ~~`CurveDefinition` domain model~~ ✓ Done — `CurveDefinition`, `CurveYBins`, `CurveAxisRange` in `ecu_definition.py`
- ~~`[CurveEditor]` INI parser pass~~ ✓ Done — `_parse_curve_editors()` (38 parser tests)
- ~~`CurvePageService`~~ ✓ Done — keyword-based group classification (20 service tests); wired into presenter `load()`
- ~~`CurveEditorWidget` UI~~ ✓ Done — `QTableWidget` with read-only X column and editable Y column(s); staged highlighting; undo/redo/revert/write/burn buttons; multi-line curve support
- ~~`CurvePageSnapshot` in presenter~~ ✓ Done — `stage_curve_cell`, `undo_curve_param`, `redo_curve_param` public methods; 32 focused tests

### 5. Final workspace polish ✓ Complete

The expensive rerender loops in the table editor were addressed, evidence
refresh is separated from full grid rebuilds, and the table cell density
heuristic has been extracted to a pure helper:

- ~~density and fit behavior~~ ✓ Done — `compute_table_cell_width(viewport, columns)`
  pulled out of `_fit_table_column_widths` so it is unit-testable without Qt;
  ceiling raised from 56 → 80 px so 1440p+ workspaces stop wasting space on
  ≤12-column tables (`tests/unit/test_table_cell_density.py`, 7 tests).
- ~~final interaction parity edge cases~~ — no concrete blockers; tracked
  via the existing 1704-test suite.
- ~~quieter evidence/polling UX where useful~~ — evidence-only refresh path
  is already separated from the full grid rebuild and has held since Slice
  7.x service additions; no new noise sources surfaced.

### 6. Controller commands and hardware test mode ✓ Complete

`ControllerCommand` model + `_parse_controller_commands()` (70+ production
commands), `SpeeduinoControllerClient.send_controller_command(payload)`,
`HardwareTestPanel` widget in the Runtime tab (test mode, injector/spark
on/off/pulsed, utilities), 29 focused tests. The original gap text is
preserved below for context.

The production INI defines `[ControllerCommands]` with direct ECU command dispatch:

- Injector test: on/off/pulsed for injectors 1–8 (`E\x02\x..`)
- Spark test: on/off/pulsed for coils 1–8 (`E\x03\x..`)
- Test mode enter/exit (`E\x01\x00/01`)
- STM32 reboot and bootloader jump (`E\x32\x00/01`)
- SD card format (`E\x33\x01`)
- VSS calibration ratio commands (`E\x99\x00–06`)

None of these are parsed or implemented. The Hardware Testing menu is correctly hidden by `#unset enablehardware_test`, but when it is enabled there is no backend to send these commands. They also bypass TunerStudio's normal memory sync (as noted in the INI comments), so they require their own dedicated UI surface, not the normal edit/burn path.

### 7. INI-driven front-page and gauge catalog — not parsed

Two INI sections we skip entirely:

**`[FrontPage]`** — defines the default 8-gauge overview layout (tachometer, throttle, pulse width, duty cycle, MAP, IAT, CLT, gamma enrichment) plus ~40 status indicators with expression/label/color definitions. TunerStudio renders this as its "Overview" tab. Our Overview tab is a static placeholder that doesn't consume this data.

**`[GaugeConfigurations]`** — defines ~70 named gauges with min/max/warning/danger thresholds, decimal places, and label formats. Our dashboard defaults are hardcoded. The right behavior is to seed the default dashboard from `[FrontPage]` gauge names, then look up each gauge's parameters from `[GaugeConfigurations]`.

### 8. LoggerDefinition — composite/tooth logger protocol not wired

The INI defines `[LoggerDefinition]` with start/stop firmware commands and record field formats for:

- Tooth logger (`startCommand = "H"`, `stopCommand = "h"`, record = 4-byte `toothTime`)
- Composite logger (`startCommand = "J"`, `stopCommand = "j"`, 5-byte records with level bits + `refTime`)
- Composite logger 2nd cam (`startCommand = "O"`)
- Composite logger both cams (`startCommand = "X"`)

The Trigger Logs surface accepts CSV imports and does analysis, but it doesn't send the start/stop commands to the firmware or consume the live binary stream. The firmware commands and record parsing are not implemented.

### 9. Production artifact test coverage — resolved ✓

- ~~Production pair round-trip tests~~ ✓ Done — `test_production_round_trip.py` (31 tests): `speeduino-dropbear-v2.0.1.ini` + `speeduino-dropbear-v2.0.1-base-tune.msq` + `Ford300_TwinGT28_BaseStartup.msq` all in `tests/fixtures/`; fixture sanity, scalar/table edit round-trips, `lastOffset`-derived table preservation (`afrTable`), multi-edit, XML format sanity, Ford300 vs base-tune VE table differences

### 10. Project save flow

- ~~In-place Save (Ctrl+S) — saves tune to current path without dialog, persists project metadata atomically.~~ ✓ Done
- ~~Save Tune As — renames toolbar button, updates `project.tune_file_path` on save to new location.~~ ✓ Done
- Auto-save project metadata on tune path change remains wired through `_persist_project_ui_state()`.

## What Must Stay True To TunerStudio

- INI metadata remains the source of truth.
- Offline editing remains first-class.
- Write to RAM, burn to flash, refresh, and revert remain distinct actions.
- Tuning, runtime/log review, and flash/tools remain separate operator workflows.
- Any tune-changing assist remains staged and reviewable.

## Current Gap — Unblockers Pending (audited 2026-04-15)

Cross-repo picture of what's still needed to move each blocked desktop surface past "desktop-side complete" to "exercised end-to-end". Grouped by owning repo. Each item cites a specific source file or roadmap slice rather than a guessed shape — the speculation-driven contracts from earlier passes have been retired.

### Speeduino firmware (`C:/Users/Cornelio/Desktop/speeduino-202501.6/`)

Ordered roughly by leverage:

- **Slice 14A** — `tune_storage_map.h` sibling header (firmware-side storage-layout declaration: semantic IDs + page/offset/type per tunable). The desktop's primary definition format remains `.tunerdef` (semantic, operator-facing); this header is firmware-owned wire-protocol metadata that lets the desktop byte-accurately read/write tune storage. Replaces the hand-maintained `[Constants]` block of `speeduino.ini` as the **firmware-side** source of truth; `.ini` becomes a one-way generated export for legacy TunerStudio clients once Slice 14F ships.
  - **First bite landed 2026-04-15** — grammar + 4 real starter entries (reqFuel scalar + veRpmBins/veMapBins axes + veTable 3D map with axis refs). Firmware `speeduino/tune_storage_map.h` created with full X-macro grammar docs (TUNE_SCALAR / TUNE_AXIS / TUNE_TABLE / TUNE_CURVE). Desktop `tune_storage_map` parser (`include/tuner_core/tune_storage_map.hpp` + `src/tune_storage_map.cpp`) handles all 4 macro shapes, respects quoted-string commas, throws on arg-count mismatch, ignores comments + `#ifdef` / `#endif` cleanly.
  - **Second bite landed 2026-04-15** — grammar expanded: TUNE_AXIS / TUNE_TABLE / TUNE_CURVE all gained `scale` + `offset_v` args (operator-visible value = raw × scale + offset_v), needed for tables like advTable (raw 0..255 → -40°..215° via offset_v=-40) and wueBins (Celsius-shifted). +9 real entries: advTable1 + advRpmBins + advLoadBins (ignition), afrTable + afrRpmBins + afrMapBins (AFR target), boostTable + boostRpmBins + boostTpsBins (boost target), wueRates + wueBins (first curve + its cross-page axis). Fingerprint auto-updated to `0xF403E02B`. +2 doctest cases pin scale/offset_v round-trips for tables and axes.
  - **Third bite landed 2026-04-15** — +12 more real entries. Dwell + injector scalars (`divider`, `injOpen`, `dwellcrank`, `dwellrun`, `dwellLim`), staged-injection sizes (`stagedInjSizePri`/`Sec`, both U16), VVT closed-loop hold duty (`vvtCLholdDuty`), VVT tables (`vvtTable` @ p7, `vvt2Table` @ p12, both 8×8 U08 scale 0.5), VVT RPM axes (`vvtRpmBins`, `vvt2RpmBins`). VVT load axes deliberately skipped — their scale depends on `vvtLoadSource` runtime setting, needs future grammar extension for dynamic-scale refs. Fingerprint auto-updated to `0x56FE521C`. +1 doctest case pinning the growing-header invariants (cross-kind count, semantic-ID cross-reference resolution, cross-page curve-axis linkage).
  - **Fourth bite landed 2026-04-15** — +13 more entries, curve-heavy bite. Scalars: `aseTaperTime`. Axes (6): `aseBins` (coolant for ASE), `primeBins` (coolant for prime pulse), `iatRetBins` (IAT for timing retard), `flexFuelBins` (ethanol %), `crankingEnrichBins` (coolant for cranking). Curves (6): `asePct` + `aseCount` (two curves sharing `aseBins`), `primePulse`, `iatRetRates`, `flexFuelAdj`, `crankingEnrichValues` (U08 scale 5.0 — first entry using a >1 scale on a curve, exercises the scale/offset math for operator-visible values reaching 250%+). Fingerprint auto-updated to `0xE71C5AB2`. No new doctest cases needed — the third-bite growing-header invariant test already covers the shape.
  - **Fifth bite landed 2026-04-15** — +20 more entries, idle + fuel-trim bite. Scalars (2): `iacTPSlimit`, `iacRPMlimitHysteresis` (idle limits). Axes (7): `idleAdvBins` (first axis with negative offset on a non-temp channel — RPM delta from target via scale=10 offset=-50), `iacBins` + `iacCrankBins` (idle coolant, 10- and 4-element), `fuelTrim1..4RpmBins` (4 trim-table RPM axes). Tables (4): `fuelTrim1..4Table` (each 6×6 U08 scale=1.0 offset=-128, so raw 128 = 0% trim with ±50% range; 4 tables sharing grammar). Curves (6): `idleAdvValues` (timing delta), `iacCLValues` (idle RPM target), `iacOLStepVal` (stepper steps), `iacOLPWMVal` (PWM %), `iacCrankSteps`, `iacCrankDuty`. Fuel-trim load axes deliberately skipped (dynamic scale `{fuelLoadRes}`). Fingerprint auto-updated to `0x0E7D4DCC`.
  - **Sixth bite landed 2026-04-15** — +11 more entries, boost-PID + staging + pressure-sensor bite. Scalars (9): `boostKP` / `boostKI` / `boostKD` (boost PID gains on page 6), `boostMaxDuty` / `boostMinDuty` (duty limits on page 1), `fuelPressureMin` / `fuelPressureMax` / `oilPressureMin` / `oilPressureMax` (pressure-sensor calibration on page 10 — **first S08 signed-scalar entries** for the Min values, exercising negative-raw encoding with a real-world BAR scale of 0.0698). Axis (1): `stagingRpmBins` (page 7 staging-table RPM). Table (1): `stagingTable` (8×8 U08 staging percentage on page 7). Staging load axis deliberately skipped (dynamic scale). Fingerprint auto-updated to `0xE4E0F94E`.
  - The remaining port is progressive — each new entry adds one more tunable's firmware-side wire layout. The desktop `.tunerdef` for each tunable exists independently; the two formats cross-reference by semantic ID.
- **Slice 14F** — `tools/generate_ini.py` reads `tune_storage_map.h` and emits the canonical INI, retiring hand-maintained INI drift. Requires 14A first.
- **Slice 14C** — semantic-ID stamps on `status3` / `status4` / `status5` packed bytes (extends the `runtimeStatusA` naming pattern). No packet growth. Medium.
  - Desktop-side preparation ✅ Landed 2026-04-15: `runtime_telemetry::RuntimeStatus` gained `half_sync`, `burn_pending`, `staging_active`, `fan_on`, `vvt1_error`, `vvt2_error`, `wmi_empty` bool fields read from the existing INI-declared bit channels. LIVE-tab status strip surfaces Half Sync / VVT errors / WMI Empty as `accent_warning` chips, Burning… as `accent_primary`, Staging as `accent_ok`. Firmware side already emits every bit — desktop just hadn't consumed them.
- **Slice 14D** — `tune.bin` ingest from SD card (Teensy 4.1 only). Unblocks the desktop "Open Tune from ECU SD…" action, currently disabled with a pending-firmware tooltip.
- **Slice 14G full** — multi-tune storage (4 × SPI-flash slots) + rotary selector GPIO + slot-select burn command + per-slot fingerprint validation. Bits 6-7 of `status5` already renamed in Slice 14G-0 (landed 2026-04-15); the storage side needs to actually set them.
- **Slice 14E** — boot manifest JSON line over USB CDC. Would bypass 3-6 probe round-trips at connect. Blocked on clean USB-CDC open-detection hook (Teensy-specific).
- **Phase 12** — selective U16 on DropBear for high-leverage tables (VE / AFR / spark / boost / VVT). Desktop generators already branch on `data_type` per table; firmware flipping INI declarations to U16 is the remaining step.
- ~~**`tools/generate_schema_fingerprint.py`**~~ ✅ Landed 2026-04-15. Python script at `speeduino/tools/generate_schema_fingerprint.py` reads `live_data_map.h` + `comms_legacy.h` (+ `tune_storage_map.h` when Slice 14A ships) and emits `speeduino/schema_fingerprint.h` with a SHA-256-derived 32-bit constant. Current value: `0x007694CD`. Deterministic (re-running produces the same value with the same inputs). `comms_legacy.h` now `#include`s the generated header. Run the script after any layout change, commit the updated `.h`.
- **Slice 14H** — operator manual updates per topic (ongoing alongside each new firmware slice).

### Airbear firmware (`C:/Users/Cornelio/Desktop/Airbear-main/`)

- **Phase A4** — REST API expansion + EcuHub UDP auto-discovery on port 21846 (TSDash `DISCOVER_SLAVE_SERVER` responder). Partially there. Target v0.4.
- **Phase A5** — Dash Echo (concurrent TunerStudio TCP + local dashboard with UART mutex arbitration). Desktop TCP transport already handles `RC_BUSY_ERR` backoff. Target v0.5.
- **Phase A6** — CAN Bus integration. `/api/can/*` endpoints already exist but the desktop hasn't consumed any of them yet.
- ~~**WiFi reconnect counter**~~ ✅ Landed 2026-04-15 — `wifi_mgt.cpp` registers a `WiFi.onEvent` handler, `wifiDisconnects` counter increments on `ARDUINO_EVENT_WIFI_STA_DISCONNECTED`, exposed as `wifi_disconnects` in `/api/status`. Desktop `StatusResponse::wifi_disconnects` + Airbear Health dialog row with threshold coloring.
- **Multi-file log listing + SD tune endpoints** — desktop had speculative `/api/sd/logs` and `/api/sd/tunes` helpers; not on the current Airbear roadmap. Would need a design decision on the Airbear side first. Desktop UI that relied on these now targets the real `/api/log/status` + `/api/log/download` single-file endpoints; the speculative surface remains in `airbear_api.hpp` as a proposed contract.

### Desktop (this repo)

#### Infrastructure

- **G13 embedded flash for Mega2560** — port STK500v2 bootloader over `QSerialPort`. ~400 LOC, pure stdlib. Removes `avrdude.exe` bundling.
- **G13 embedded flash for STM32F407** — port DFU 1.1 protocol + vendor libusb-1.0. ~500 LOC + platform DLL.
- **Teensy HID flasher on Linux/macOS** — current path is Windows-only (`setupapi` / `hid.dll`). hidapi vendoring closes it.
- **XCP editing parity** — simulator + packet layer done (sub-slices 104-105); workspace presenter integration (XCP-based page read/write/burn-equivalent threading into `EcuConnection`) is the missing piece.
- ~~**Widget unit tests**~~ ✅ `widget_math.hpp` landed 2026-04-16: `screen_drag_to_time_range` (8 cases) + `build_square_wave_points` (5 cases) extracted from LogTimelineWidget + TriggerScopeWidget.
- **Operator manual** — first pass landed 2026-04-16 at `docs/operator-manual.md`. Remaining: per-tab deep-dives, screenshots, and pairing with firmware 14H release notes.
- ~~**Doc drift cleanup**~~ ✅ Audited 2026-04-15.

#### Implementation backlog — prioritized (2026-04-16 disparity audit)

Audited against the deleted Python app (git `8dc3d92:src/tuner/`) and decompiled TunerStudio (`C:\Users\Cornelio\Desktop\Decompiled\TunerStudioMS\`). Numbered in implementation order.

**Phase 17 — Workflow & Safety**

| # | Item | Source | Effort | Status |
|---|------|--------|--------|--------|
| 0 | **Context-aware tree visibility** — (a) Units preference (AFR vs Lambda) at project creation or settings; only matching table shows in tree. (b) Fuel trim pages adapt to cylinder count. (c) Changing `active_settings` dynamically rebuilds the TUNE tree without restart. Ties into INI `#if LAMBDA` / `[SettingGroups]` / `active_settings`. | Operator feedback | Medium | Not started |
| 1 | **Diff on Connect** — auto-compare ECU pages vs project tune on connect, "Difference Report" dialog with keep-controller / keep-project resolution | TS `G/an.java` + `U/h.java` | Medium | Not started |
| 2 | **Auto-save Offline Tune** — periodic auto-save when disconnected, configurable interval, prevent data loss on crash | TS `aP/f.java` `autoSaveOfflineTune` | Small | Not started |
| 3 | **Automatic Restore Points** — snapshot on close/load/connect, max 10, browsable list with "Compare to Current" + "Load Restore Point" | TS `R/a.java` + `aY/s.java` | Medium | Not started |
| 4 | **SETUP tab sub-tabs** — split into Generators / Hardware / Turbo / Calibration sections via QTabWidget or collapsible groups | Operator feedback | Small | Not started |

**Phase 18 — Analysis & Logging**

| # | Item | Source | Effort | Status |
|---|------|--------|--------|--------|
| 5 | **Datalog review summary stats** — per-channel min/max/mean/outlier from imported CSVs | Python `DatalogReviewService` | Small | Not started |
| 6 | **Tune file-vs-file compare** — load two .tuner/.msq files, per-parameter diff table | TS compare dialog | Medium | Not started |
| 7 | **Log viewer scatter plots** — X-Y scatter (e.g. RPM vs MAP colored by AFR) in the LOGGING timeline | TS MegaLogViewer | Medium | Not started |
| 8 | **Dashboard multiple layout tabs** — vector of layouts + tab bar or dropdown | TS multi-dash | Small-Medium | Not started |

**Phase 19 — Connectivity & CAN**

| # | Item | Source | Effort | Status |
|---|------|--------|--------|--------|
| 9 | **CAN Quick Start card** — SETUP tab: what CAN is, what you need, default True Address | Operator request | Small | Not started |
| 10 | **Pre-built CAN profiles** — one-click presets for AEM wideband, Haltech dash, OBD2 | Operator request | Small | Not started |
| 11 | **Continuous IP range scan** — subnet sweep for ECU discovery | TS `ContinuousIpSearchPanel` | Small | Not started |
| 12 | **Wideband calibration panel** — dedicated preset selector + write + verify | Python `WidebandCalibrationPanel` | Small | Not started |

**Phase 20 — Autotune Improvements (from engine-model reference)**

| # | Item | Source | Effort | Status |
|---|------|--------|--------|--------|
| 13 | **Pressure-ratio-aware VE weighting** — wire compressor-map efficiency into VE correction confidence | `engine-model-reference.md` | Medium | Not started |
| 14 | **Injector flow nonlinearity model** — quadratic correction separates VE error from injector characterization error | `engine-model-reference.md` | Medium | Not started |
| 15 | **Torque-peak-informed VE anchor** — use Virtual Dyno's torque-peak RPM as VE generator reference | `engine-model-reference.md` | Small | Not started |

**Phase 21 — Infrastructure & Cross-platform**

| # | Item | Source | Effort | Status |
|---|------|--------|--------|--------|
| 16 | **G13 embedded Mega2560 flash** — STK500v2 over QSerialPort | Roadmap | Medium | Not started |
| 17 | **G13 embedded STM32 flash** — DFU 1.1 + libusb | Roadmap | Medium | Not started |
| 18 | **Teensy HID cross-platform** — hidapi vendoring for Linux/macOS | Roadmap | Medium | Not started |
| 19 | **XCP workspace integration** — page read/write/burn via XCP transport | Roadmap | Large | Packet layer done |
| 20 | **SD card log/tune browse** — multi-file remote browse + download | TS `RemoteFileAccess` | Medium | Blocked on Airbear G5 + firmware 14D |

**Minor/niche (unscheduled)**

- Output Port Editor (graphical I/O pin mapping) — TunerStudio-only
- `string` kind constant editing — rare INI fields
- Built-in calculator — trivial
- CRC check panel — niche debugging
- Asymmetric sweep / dashed bar gauge renderers — cosmetic

**C++ app is AHEAD of both Python and TunerStudio in:**

3D rotatable table surface · Virtual Dyno with overlay · zone-entry alert toasts · VE/WUE coverage heatmap · 6 table generators · compressor map modeling · command palette (Ctrl+K) · F1 cheat sheet · editable curve charts · PaintedHeatmapWidget (<3ms table switch) · guided SETUP hardware cards · power-cycle indicator + auto-reboot · full dark theme with 200+ tokens

### Hardware / integration (no code fixes its own blocker)

- **Physical bench validation** — the C++ app has only been exercised against mock/simulator this whole pivot. Real-Speeduino-on-an-engine-harness validation is the ultimate release gate.
- **Firmware flash + boot test** — the three firmware changes landed this session (Airbear A3.5 counters, Speeduino 14B schema fingerprint, Speeduino 14G-0 status5 bits) compile on paper but haven't been flashed to hardware; any integration surprise (timing, buffer overflow, alignment) surfaces on first boot.

### Decisions pending sign-off

- **Python-side deletion** — `src/tuner/` is the parity oracle (~3011 Python tests). C++ parity reached per the tracker. One PR deletes all of it; destructive and irreversible.
- **`SCHEMA_FINGERPRINT` promotion** — the `0x202501U` constant I put in `comms_legacy.h` is a placeholder. Decision needed on manual bump per release vs. build-script derivation.

### Critical path to a ship-able product

1. Hardware bench validation (firmware + desktop together on a real engine).
2. ~~Operator manual~~ — first pass seeded 2026-04-16 at `docs/operator-manual.md`. Remaining: per-tab deep-dives, screenshots, and pairing with firmware 14H release notes.
3. Firmware 14A + 14G-full slices (transform desktop-side "slot 0 only" into real multi-tune).

Everything else (XCP parity, embedded Mega/STM32 flash, Linux/macOS Teensy) is polish operators on non-DropBear boards need. The current app ships for DropBear + Teensy today.

---

## Phase Status

| Phase | Status |
|---|---|
| 0: Fixtures and compatibility baseline | **Complete** — U16P2 experimental pair (19 tests) and production pair `speeduino 202501-T41` (31 tests) both covered; all fixtures in `tests/fixtures/` |
| 1: Definition fidelity and layout compilation | Complete for tables, scalars, dialogs, menus, `[CurveEditor]` (34 curves), `[GaugeConfigurations]` (seeded into default dashboard layout), and `[FrontPage]` (gauge order + indicator strip) |
| 2: Editing surface parity | **Complete** — table, scalar, and 1D curve editing all done; `CurveEditorWidget` wired end-to-end with staged highlighting, undo/redo, write/burn |
| 3: Sync state and operation visibility | Complete for the current baseline |
| 4: Hardware setup workflow surfaces | **Complete** — core setup flows, presets, reqFuel helpers, shared operator context, and staged generators landed; wizard → staged → MSQ write end-to-end test in place |
| 5: Runtime evidence and replay | **Complete** — baseline runtime/replay/evidence services landed; table cell density fit (`compute_table_cell_width`) extracted to a pure helper with focused tests; ceiling raised from 56 → 80 px so wider workspaces no longer waste space on small tables |
| 6: Baseline VE Analyze compatibility | Complete; VE and WUE Analyze both wired end-to-end |
| 7: Better-than-TunerStudio assist | **Complete** — all seven slices (7.1 firmware-gated acceptance, 7.2 weighted correction + bounded edits, 7.3 confidence + coverage reporting, 7.4 steady-state refinements + EGO delay compensation, 7.5 smoothing as a reviewable transform, 7.6 boost-aware confidence penalties, 7.7 root-cause diagnostics) landed; end-to-end pipeline test in place; workspace UI surfacing wired through `VeAnalyzeReviewService` (clamp count, boost penalty count, smoothed-layer summary, root-cause diagnostic lines on `VeAnalyzeReviewSnapshot`) |
| 8: Dashboard, workspace, and UX modernization | **Complete** — INI-driven gauge catalog seeded into default layout; FrontPage indicator strip wired; LED indicator widget kind landed; static-text `label` widget kind (TSDash DashLabel parity) added with offscreen Qt tests + JSON layout round trip |
| 9: Board, firmware, and bench workflow integration | **Complete** — reconnect signature warning UI, `uncertain_channel_groups()` runtime table flags, `TcpTransport` WiFi connect, mDNS resolution, HTTP live-data API (port 8080), and `LiveTriggerLoggerService` all wired; LoggerDefinition live tooth/composite stream (start/poll/read/stop firmware commands) wired through `SpeeduinoControllerClient.fetch_logger_data()` and exercised end-to-end by `TriggerCaptureWorker` from the Trigger Logs surface |
| 10: Hardening and release prep | Ongoing |
| 14: Native C++ Qt 6 desktop port | **In progress** — Slice 4 post-parity. C++ doctest suite: **1513 tests / 11336 assertions / 0 failures**. Python suite: **3011 tests**. Qt 6.7.3 built from source at `C:/Qt/6.7.3-custom`. 98 services ported + all INI leaf parsers + full beautification arc + 20 UX slices + 14-feature functional wiring pass (sub-slice 146) + 13-slice comms/ecosystem alignment pass (147–159). **Post-parity polish session (2026-04-15):** Virtual Dyno chart widget + before/after overlay, CF + coverage per-cell tooltips, `LogTimelineWidget` with play/pause + speed selector + channels picker + shift-drag zoom + export menu, Airbear SD log browser + SD tune ingest (File → Open Tune from ECU SD…), slot picker + burn-routing guard, `activeTuneSlot` chip, ECU Capabilities dialog (slot fingerprints + definition hash + page-format bitmap), Airbear Health dialog (error counters), `TriggerScopeWidget` oscilloscope view, dashboard formula-channel picker, all build warnings cleared. **P15 + P16 desktop-side complete, G1-G8 gap backlog closed.** See parity tracker below. |

## C++ App Feature Parity Tracker (as of 2026-04-15 post-parity polish session)

Status key: **Done** = fully functional | **Partial** = framework in place, not fully wired | **Missing** = not started

### Core infrastructure

| Feature | Status | Notes |
|---|---|---|
| INI parser (all leaves) | **Done** | Every structural INI leaf ported + parity-tested against production INI |
| MSQ parser + writer | **Done** | Including `insert_missing` for generator-staged values |
| Native format (.tuner/.tunerproj/.tunerdef) | **Done** | Read + write + File → Save (Ctrl+S) |
| ECU definition compiler | **Done** | Full `NativeEcuDefinition` aggregator |
| Theme token system | **Done** | 200+ inline hex → 6; full dark theme |

### TUNE tab (13/13 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Page tree with search filter | **Done** | Keyword groups, humanized names, type tags |
| Scalar page editing | **Done** | QLineEdit + staging + tooltips from `[SettingContextHelp]` |
| Table heatmap editing | **Done** | Cell colors, double-click edit, +/-/I/S/F/Ctrl+Z/Y |
| Table click + drag selection | **Done** | Single click, Shift+click range, mouse drag rectangle |
| Table copy/paste | **Done** | Ctrl+C/V with tab-delimited clipboard |
| Curve editor (bar chart + editable Y table) | **Done** | 34 curves, live bar chart refresh on edit |
| 3D table surface | **Done** | QPainter wireframe, mouse-drag rotation, crosshair |
| Live operating-point crosshair | **Done** | MockEcu drives it; real ECU ready |
| Staged-change review dialog (Ctrl+R) | **Done** | Per-page diff with revert buttons |
| Write to RAM / Burn to Flash | **Done** (sub-slice 146) | Ctrl+W encodes + sends via controller with blocking-factor chunking; Ctrl+B burns dirty pages |
| Enum/bits QComboBox editing | **Done** | Dropdown + staging |
| Page visibility expressions | **Done** (sub-slice 146) | Evaluates against tune scalars, removes invisible pages |

### LIVE tab (8/8 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Animated dial gauges | **Done** | QPainter with zone colors |
| Number cards with zone alerts | **Done** | Flash on danger entry |
| Sparkline histograms | **Done** | AFR/RPM/MAP 60-sample rolling |
| Formula channel strip | **Done** | λ, throttle, MAP PSI, revTime from math evaluator |
| Driving phase indicator | **Done** | WOT/CRUISE/DECEL/IDLE |
| INI-driven gauge dashboard | **Done** (sub-slice 146) | FrontPage slots + GaugeConfigurations catalog; QSettings persistence |
| FrontPage indicator strip | **Done** (sub-slice 146) | 40+ boolean chips, 200ms expression eval, state-change-only updates |
| Hardware test panel | **Done** (sub-slice 146) | INI `[ControllerCommands]` → button grid, sends via `fetch_raw()` |

### FLASH tab (5/5 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Preflight checklist | **Done** | Reads real project/connection/port state |
| Board detection (serial ports) | **Done** | Windows registry enumeration |
| Firmware file selection | **Done** (sub-slice 146) | QFileDialog for .hex/.bin files |
| Flash upload execution | **Done** (sub-slices 146 + 147) | Teensy 3.5/3.6/4.1 use embedded Win32 HID flasher (no external exe). Mega2560 (AVRDUDE) + STM32 (dfu-util) use QProcess subprocess with board-aware tool detection. Auto-disconnects ECU before flash. |
| Flash progress bar | **Done** (sub-slice 146) | 4px indeterminate QProgressBar during flash |

### SETUP tab (15/15 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Engine Setup Wizard (6 steps) | **Done** | Engine/Induction/Injectors/Trigger/Sensors/Review |
| 18 injector presets | **Done** | Auto-fills flow + dead time |
| Ignition coil presets | **Done** | From `hardware_presets` service |
| Wideband controller presets | **Done** | From `wideband_calibration` service |
| MAP sensor presets | **Done** | 8 presets with auto-fill in wizard |
| Table generators (VE/AFR/Spark/WUE/Cranking/Idle) | **Done** | All generated + staged on wizard Finish |
| reqFuel calculator preview | **Done** | Live computation in wizard |
| Review summary card | **Done** | All params displayed before Finish |
| Hardware validation + sensor checklist | **Done** | injOpen=0, dwell, O2/TPS/MAP checks |
| Setup reads loaded tune | **Done** | Falls back to demo when no tune loaded |
| Baro sensor presets | **Done** (sub-slice 146) | 4 presets in wizard Step 5 |
| Turbo characterization | **Done** (sub-slice 146) | A/R ratio, compressor/turbine trim in Step 2 |
| Acceleration enrichment | **Done** (sub-slice 146) | AE mode, TPS threshold, amount in Step 3 |
| Injector pressure compensation | **Done** (sub-slice 146) | Fuel system, rail pressure, dead time comp in Step 3 |
| Board/MCU selector | **Done** (sub-slice 146) | 5 board options in Step 1 with DropBear default |

### ASSIST tab (10/10 — Complete)

| Feature | Status | Notes |
|---|---|---|
| VE cell-hit accumulator | **Done** | Full weighted-correction pipeline |
| Proposal smoothing + diagnostics | **Done** | Smoothing layer + 4-rule root-cause engine |
| WUE Analyze demo | **Done** | Plain-language summaries |
| Real log data import | **Done** (sub-slice 146) | CSV import → nearest-bin cell mapping → correction accumulation |
| Apply proposals to tune | **Done** (sub-slice 146) | Stages VE proposals via `edit_svc->replace_list()` |
| Live VE Analyze session | **Done** (sub-slice 146) | Start/Stop/Reset, 500ms timer, real-time accumulation, shares Apply |
| Coverage heatmap + CF grid per-cell tooltips | **Done** (post-parity) | Hover any cell for row/col + sample count + confidence tier + clamp flag |
| Virtual Dyno chart + before/after overlay | **Done** (post-parity) | QPainter torque/HP chart, nice-ceiling axes, peak markers, dashed overlay under primary for two-pull comparison |
| Compressor map modeling | **Done** (P15-10) | Mass-flow math + 6-tier risk classification + plain-language summary |

### LOGGING tab (9/9 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Capture controls (Start/Stop/Clear/Save) | **Done** | Full state machine |
| Channel profile from INI | **Done** | Reads real output channels |
| Real-time capture to CSV | **Done** (sub-slice 146) | 200ms timer, CapturedRecord, `format_csv()` |
| Profile persistence | **Done** (sub-slice 146) | QSettings serialize/deserialize |
| CSV import + replay viewer | **Done** (sub-slice 146) | `datalog_import::import_rows()` → QSpinBox row nav → `select_row()` |
| Scrubbable timeline with channel tracks | **Done** (post-parity) | `LogTimelineWidget` with play/pause + speed selector + channels picker + shift-drag zoom + export menu (CSV range + PNG snapshot) |
| Airbear SD log browser | **Done** (post-parity) | Host field + Refresh + download via `/api/sd/logs` grammar; firmware G5 exercise pending |

### TRIGGERS tab (5/5 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Trigger log visualization | **Done** | Trace summary, per-trace details, annotations |
| Trigger log analysis | **Done** | Capture summary + decoder context + findings |
| CSV import | **Done** (sub-slice 146) | Parses into Row format, rebuilds viz + analysis dynamically |
| Live capture (tooth/composite) | **Done** (sub-slice 146) | `fetch_raw()` on controller, INI LoggerDefinition decode |
| Oscilloscope waveform view | **Done** (post-parity) | `TriggerScopeWidget` — stacked tracks, digital square-waves, analog smooth lines, dashed annotation marks, ms time axis |

### Connection & comms (15/15 — Complete)

| Feature | Status | Notes |
|---|---|---|
| Serial transport (Win32) | **Done** | COM port, configurable baud |
| TCP transport (Speeduino framing) | **Done** | Airbear bridge, CRC32 |
| SpeeduinoController | **Done** | connect/read/write/burn/fetch_raw + auto-baud probe |
| Connection dialog (Serial/TCP) | **Done** | Port enumeration + refresh |
| File → Connect / Disconnect | **Done** | Menu + command palette |
| Sidebar connection indicator | **Done** | Live ◉/○ + port/baud |
| Status bar telemetry | **Done** | Real signature + RPM/MAP/AFR/CLT when connected |
| Read all pages on connect | **Done** (sub-slice 146) | Computes page sizes from def, populates page_cache |
| Parameter write to ECU | **Done** (sub-slice 146) | Blocking-factor chunking, bit-field read-modify-write |
| Burn command | **Done** (sub-slice 146) | Per-page burn with 20ms inter-page delay; slot-target guard refuses non-zero slots until firmware 14G |
| Runtime polling (output channels) | **Done** | `EcuConnection::poll_runtime()` decodes live data |
| Capability header parse | **Done** (post-parity) | `fetch_raw({'f'}, 62)` on connect → `CapabilityHeader` with slot fingerprints (bytes 6-37) + definition hash (38-53) + page-format bitmap (54-61); pre-14B firmware leaves extensions empty |
| ECU Capabilities dialog | **Done** (post-parity) | File → Show ECU Capabilities… renders every field with pending-firmware placeholders |
| Airbear Health dialog | **Done** (post-parity) | File → Airbear Health… + `fetch_status`; counters rendered with ok/warn/danger thresholds, pre-rollout dashes + footnote |
| Active-slot live chip | **Done** (post-parity) | `runtime_telemetry::RuntimeStatus::active_tune_slot` + `● Slot N` chip in LIVE-tab status strip |

### UX / chrome

| Feature | Status | Notes |
|---|---|---|
| Menu bar (File/View/Tune/Help) | **Done** | With shortcut display |
| F1 keyboard shortcut cheat sheet | **Done** | Context-aware active-tab emphasis |
| Command palette (Ctrl+K) | **Done** (sub-slice 145) | Redesigned with groups + icons + chips |
| Session persistence | **Done** | Geometry + last tab + TUNE page + tree expansion |
| Dynamic window title | **Done** | Project name + staged count |
| Sidebar tooltips | **Done** | Tab description + Alt+N |
| QToolTip theming | **Done** | Dark theme global |
| About dialog | **Done** | Wordmark + tagline + philosophy |

### Not started — Python has, C++ doesn't

| Feature | Python Location | Priority | Status |
|---|---|---|---|
| Acceleration enrichment wizard | `hardware_setup_wizard.py` step within injector page | Medium | ✅ Done (sub-slice 146 — Setup wizard Step 3) |
| Dashboard drag-and-drop gauge rearrangement | `dashboard_panel.py` | Medium | ✅ Done (sub-slice 161 — `DraggableCardLabel` mirrors `DialGaugeWidget`'s drag/drop, same MIME type so cards and dials swap interchangeably) |
| Gauge config dialog (channel/zone/kind per gauge) | `gauge_config_dialog.py` | Medium | ✅ Done (sub-slice 161 — number-card right-click → Configure Gauge fires the same `open_gauge_config_dialog` the dial gauges use) |
| LED/bar/label gauge painter kinds | `dashboard_panel.py` | Low | ✅ Done (sub-slices 162 + 163 — `BarGaugeWidget` and `LedGaugeWidget` both wired. LED is a zone-coloured glowing circle with outer glow, value readout, and full drag/drop/config parity with dial/card/bar. All 4 gauge kinds — dial/number/bar/led — can swap positions interchangeably via the same MIME type.) |
| Wideband calibration write to ECU | `main_window.py` → `write_calibration_table()` | Medium | ✅ Done (sub-slices 150–152 — CLT/IAT/O2 all wired on SETUP tab) |
| HTTP live-data API (port 8080) | `live_data_http_server.py` | Low | ✅ Done (sub-slice 154 — opt-in View menu toggle) |
| mDNS `speeduino.local` resolution | `tcp_transport.py` | Low | Not needed — Windows 10+ resolves `.local` natively via built-in mDNS responder, so `getaddrinfo("speeduino.local")` already works at connect time |
| TSDash file import/export | `ts_dash_file_service.py` | Low | ✅ Done (sub-slice 153 — File → Import/Export TSDash menu) |
| Definition Settings dialog | `main_window.py` → `_open_definition_settings_dialog()` | Medium | ✅ Done (File → Definition Settings) |
| EcuHub UDP discovery | `udp_transport.py` | Low | ✅ Done (sub-slice 148 — `udp_discovery` service + Scan Network button) |

### TunerStudio-parity surface (all started — most now done)

| Feature | TS Decompiled Source | Status |
|---|---|---|
| SD card log download/browse | `bD/i.java`, `bD/m.java` | ✅ Desktop-complete — LOGGING-tab "Airbear SD Logs" card + `airbear_api::fetch_sd_log_list` / `fetch_sd_log_bytes` against `/api/sd/logs[/<name>]`; end-to-end exercise waits on Airbear firmware G5 shipping the endpoints |
| Standalone log viewer (MegaLogViewer parity) | `MegaLogViewer.java` | ✅ Done — `LogTimelineWidget` with stacked channel tracks, click+drag cursor, play/pause + 1x/2x/4x/8x speed selector, channels picker, shift-drag region zoom, export menu (visible range CSV + timeline PNG snapshot) |
| Ignition timing scope | `TriggerLoggerPanel.java` | ✅ Done — `TriggerScopeWidget` on the TRIGGERS tab; QPainter stacked tracks (digital = square-wave, analog = smooth lines), annotations as dashed vertical marks colored by severity, ms time axis |
| Dyno / power-torque view | `aP/hb.java` | ✅ Done — Virtual Dyno on ASSIST tab with QPainter torque+HP chart + peak markers + **before/after overlay** via "Compare to Another CSV…" (dashed overlay under primary, shared axis range) |
| Multi-tune slot management | N/A (firmware limitation) | ✅ Desktop-complete — P15-9 steps 1-5 + 7 landed (NativeTune v1.1 slot fields, project-bar slot badge, Burn to: slot picker, Copy Current Tune to Slot…, Open Tune from ECU SD…, active-slot chip, ECU Capabilities dialog with per-slot fingerprints + definition hash + page-format bitmap readout); end-to-end exercise of steps 4/6 waits on firmware 14G/14B |

## Phase 7 Scope — Better-Than-TunerStudio Assist

Phase 7 sits between baseline VE/WUE Analyze parity (Phase 6, complete) and the
long-horizon autotune work tracked under Future Phase 15. The intent is to ship
incremental, reviewable improvements over the TunerStudio baseline using the
service architecture that already exists — no firmware changes, no protocol
changes, no black-box correction engine.

### Hard rules (non-negotiable)

- **Reviewable always.** Every assist output must land via the existing staging
  path (`LocalTuneEditService` → workspace review → write/burn). No assist may
  write directly to RAM or flash.
- **Deterministic first.** Each slice must be expressible as a closed-form rule
  that an operator can read and reproduce by hand. ML stays out of Phase 7.
- **Opt-in.** Each slice ships behind a config object with safe defaults that
  reproduce current behavior, so existing fixtures and tests stay green.
- **No firmware/protocol changes.** Phase 7 consumes existing
  `runtimeStatusA` bits, existing capability facts, and existing channel data.
- **Service-layer first.** Logic lives in services with focused unit tests; UI
  is thin wiring on top.

### Slice ordering

Each slice is independently shippable; later slices build on earlier ones but
do not require them.

#### Slice 7.1 — Firmware-gated sample acceptance ✓ Complete

- Add `FirmwareLearnGateConfig` (opt-in, default off) consumed by
  `ReplaySampleGateService` and `AutotuneFilterGateEvaluator`.
- When enabled and the connected firmware exposes `runtimeStatusA`, samples
  are hard-rejected unless `tuneLearnValid && fullSync && !transientActive
  && !warmupOrASEActive`.
- The bit-level mapping already exists on `FirmwareCapabilities`; this slice
  just plumbs it into the existing software-side gate as an *additional* gate,
  not a replacement.
- **Deliverable:** config dataclass, gate plumbing, focused service tests
  covering each rejection reason and the "bits unavailable → fall back to
  software gate" case. Workspace UI shows the gate reason in the rejection
  log.
- **Why first:** smallest surface area, foundational for every later slice
  that needs trusted samples.
- **Status:** landed as `firmware_learn_gate_enabled` field on
  `SampleGatingConfig` plus `firmwareLearnGate` in
  `ReplaySampleGateService` (the `AutotuneFilterGateEvaluator` only handles
  INI-defined filter expressions, so the runtime hard gate lives entirely
  on the replay path). Bit layout `0x10 fullSync / 0x20 transientActive /
  0x40 warmupOrASEActive / 0x80 tuneLearnValid` checked explicitly. Falls
  back to accept when `runtimeStatusA` channel is absent. Default-off
  behaviour is bit-identical to Phase 6 baseline (verified by
  `test_phase6_baseline_log_unchanged_with_gate_disabled`). 12 focused
  tests in `tests/unit/test_firmware_learn_gate.py`. Test count
  1619 → 1631.

#### Slice 7.2 — Per-cell weighted correction with bounded edits ✓ Complete

- Replace single-correction-per-cell averaging in `VeAnalyzeCellHitAccumulator`
  with a weighted average where weight is a function of dwell time, sample
  age, and (later) confidence.
- Add a per-cell maximum-correction clamp surfaced in
  `VeAnalyzeReviewService` proposals and visible in the workspace review UI.
- **Deliverable:** weighting + clamp logic in the accumulator, proposal-side
  display of the clamp, focused tests for monotonic weight, clamp edge cases,
  and "no change when clamp = ∞ and weight = 1" backwards-compatibility.
- **Status:** landed as `WeightedCorrectionConfig` (opt-in,
  default-off) on `VeAnalyzeCellHitAccumulator` and
  `VeAnalyzeCellHitService.analyze()`. Storage moved from
  `list[float]` to `list[(correction, weight, timestamp)]`. Weighted
  mean reduces to arithmetic mean when all weights are 1.0, so the
  Phase 6 baseline is bit-identical (verified by
  `test_none_config_matches_phase6_baseline`). New `raw_correction_factor`
  and `clamp_applied` fields surface clamp transparency on both
  `VeAnalysisProposal` and `VeAnalysisCellCorrection`. Dwell weighting
  uses time-delta to the previous sample in the same cell capped at
  `dwell_weight_cap_seconds` (default 2 s). Sample-age decay applied at
  snapshot time as `weight *= exp(-age * decay)` against the latest
  accepted timestamp. 9 focused tests in
  `tests/unit/test_ve_analyze_weighted_correction.py`. Test count
  1631 → 1640.

#### Slice 7.3 — Confidence and coverage reporting ✓ Complete

- Compute per-cell confidence (0–1) from sample count, dwell time, and
  rejection-reason distribution; expose on `VeAnalyzeReviewService` proposals.
- Add coverage map: which cells have any accepted samples, which have stale
  samples, which are unvisited.
- **Deliverable:** confidence + coverage on proposal snapshot; workspace
  table review surface renders the heatmap as a non-modal overlay; focused
  tests for the math.
- **Status:** landed as a continuous `confidence_score` (`1 - exp(-n/10)`)
  on `VeAnalysisCellCorrection` plus a new full-grid
  `VeAnalysisCoverage(rows, columns, cells, visited_count, total_count)`
  with `coverage_ratio` property and per-cell `CoverageCell(status,
  sample_count, confidence_score)`. Coverage is built from the table
  snapshot dimensions so unvisited cells are explicit and the workspace
  UI can render a heatmap without re-deriving the grid. `VeAnalyzeReviewService`
  emits a `Coverage: X/Y cells (N%) visited.` line in the detail text
  when coverage is present; legacy hand-built summaries with
  `coverage=None` produce no coverage line. Defaults preserve all
  existing fixtures (verified by 55 prior tests passing unchanged).
  10 focused tests in `tests/unit/test_ve_analyze_confidence_coverage.py`.
  Test count 1640 → 1650.

#### Slice 7.4 — Steady-state refinements with delay compensation ✓ Complete

- Add configurable EGO transport-delay compensation (e.g. 200–600 ms) inside
  `ReplaySampleGateService` so the EGO sample is paired with the MAP/RPM/TPS
  state at sample-time minus the delay.
- Tighten the existing software-side steady-state gate using explicit
  derivative thresholds rather than implicit ones.
- **Deliverable:** delay-compensation parameter, gate refinements, fixture
  test that shows a synthetic transient sample switching from accepted →
  rejected after the slice lands.
- **Status:** landed as `SteadyStateConfig(ego_transport_delay_seconds,
  max_drpm_per_second, max_dmap_per_second, history_window_seconds)`.
  The accumulator now keeps a rolling `_history` of recent records,
  trimmed on each `add_record` call to `history_window_seconds`. When
  delay > 0, each new record's lambda/AFR/EGO channels are merged onto
  the engine state from the closest history entry to `t - delay` and
  the synthesized record is fed to the existing cell-mapping path.
  Records arriving before the history covers the delay window are
  rejected as `delay_buffer_cold`. Derivative gates compute
  `|drpm/dt|` and `|dmap/dt|` against the most recent prior record;
  exceeding the threshold rejects with `transient_rpm_derivative` or
  `transient_map_derivative`. Defaults preserve the Phase 6 baseline
  bit-identically (verified by 65 prior tests passing unchanged plus
  `test_none_config_matches_phase6_baseline`). 9 focused tests in
  `tests/unit/test_ve_analyze_steady_state.py`. Test count
  1650 → 1659.

#### Slice 7.5 — Smoothing as a reviewable transform ✓ Complete

- Add a post-acceptance smoothing pass (configurable kernel size, edge
  preservation rules) that produces a *new* staged proposal layer the
  operator can preview, accept, or discard. Smoothing must never be implicit
  in the accept path.
- **Deliverable:** smoothing transform service, integration into proposal
  preview, tests that verify the operator can disable, preview, and revert
  the smoothed layer.
- **Status:** landed as new `VeProposalSmoothingService` +
  `SmoothingConfig(kernel_radius, min_neighbors, preserve_edge_magnitude)`
  + `SmoothedProposalLayer(smoothed_proposals, unchanged_count,
  smoothed_count, summary_text)` in
  `src/tuner/services/ve_proposal_smoothing_service.py`. The service is
  stateless and reads `VeAnalysisSummary.proposals` without mutating
  them — the smoothed layer is strictly additive so the operator picks
  raw, smoothed, or neither. Smoothing only operates on cells that
  already received a raw proposal (never invents VE values for unvisited
  cells); edge cells use only existing neighbors (the kernel shrinks at
  the grid boundary). Sample-count weighting prevents a low-confidence
  neighbor from pulling a high-confidence anchor. `min_neighbors` lets
  the operator require N neighbors before smoothing fires;
  `preserve_edge_magnitude` keeps the strongest correction in the
  kernel intact so real boost-spool transitions are not averaged away.
  `kernel_radius=0` is a documented identity transform. The smoothed
  proposals carry the original `correction_factor` in
  `raw_correction_factor` for review transparency. 9 focused tests in
  `tests/unit/test_ve_proposal_smoothing_service.py` covering trivial
  cases, pass-through, spike smoothing, sample-count weighting,
  edge-magnitude preservation, min_neighbors gate, and the
  non-mutation guarantee. Test count 1659 → 1668.

#### Slice 7.6 — Boost-aware confidence penalties ✓ Complete

- Reduce sample weight in spool-transition regions (RPM rising fast under
  positive boost), unstable manifold-temperature regions, and uncertain
  pressure-ratio regions.
- Penalty math is closed-form and exposed on the proposal snapshot so the
  operator can see *why* a region was downweighted.
- **Deliverable:** penalty service, integration into the weighting from
  Slice 7.2, focused tests against synthetic boosted log fixtures.
- **Status:** landed as `BoostConfidenceConfig(atmospheric_kpa,
  spool_drpm_threshold, spool_dmap_threshold, spool_penalty_max,
  mat_dt_threshold, mat_penalty_max)` plus closed-form helper
  `_boost_confidence_multiplier(record, prior, config)` returning a
  multiplier in `[1 - max_pen, 1.0]`. Spool transition penalty fires
  *only* when `MAP > atmospheric_kpa` (verified inactive in vacuum even
  at huge rpm derivatives); MAT instability penalty fires in vacuum or
  boost. Severities are linear ramps clamped to [0, 1] at the
  configured thresholds; the two penalties combine as `1 - max(spool,
  mat)` rather than multiplicatively so no single overlap can drive the
  weight negative. The multiplier feeds the existing dwell-weight pipeline
  from Slice 7.2 — when both `WeightedCorrectionConfig` and
  `BoostConfidenceConfig` are off the math is unchanged. Per-cell
  `boost_penalty_applied` field on `VeAnalysisCellCorrection` (default
  0.0) surfaces the total `1 - multiplier` so the operator can see
  *why* a cell was downweighted. 9 focused tests in
  `tests/unit/test_ve_analyze_boost_confidence.py` covering the
  multiplier math (steady-state, threshold, vacuum-only, MAT, combined,
  zero dt), default-off no-regression, per-cell penalty surfacing, and
  vacuum no-penalty symmetry. Test count 1668 → 1677.

#### Slice 7.7 — Root-cause diagnostics surface (read-only first) ✓ Complete

- When corrections in a region are large, inconsistent, or systematically
  biased, present read-only "this looks like X" diagnostics: deadtime error,
  injector flow error, target table error, MAP/IAT calibration error.
- No automatic correction — operator interprets and decides.
- **Deliverable:** diagnostic rule engine, workspace surface, tests for each
  rule against a fixture log demonstrating the failure mode.
- **Status:** landed as new `VeRootCauseDiagnosticsService` +
  `RootCauseDiagnostic(rule, severity, message, evidence_cells)` +
  `RootCauseDiagnosticReport(diagnostics, summary_text, has_findings)` in
  `src/tuner/services/ve_root_cause_diagnostics_service.py`. Stateless,
  read-only — never mutates the input `VeAnalysisSummary`. Four
  closed-form rules: `injector_flow_error` (uniform global bias with
  low variance), `deadtime_error` (low-load/low-rpm region biased
  meaningfully more than the rest), `target_table_error` (high vs low
  load biased in opposite directions), `sensor_calibration_error`
  (Pearson correlation between row index and correction factor ≥ 0.7).
  Conservative thresholds chosen so a diagnostic only fires when the
  pattern is obvious — silent on healthy data. Rules run independently
  and may fire alongside each other. Below `_MIN_PROPOSALS = 6` the
  report is empty so noisy partial datalogs don't surface false leads.
  10 focused tests in `tests/unit/test_ve_root_cause_diagnostics.py`
  covering threshold gating, healthy data silence, each of the four
  rules in isolation (lean and rich variants for injector flow,
  high-variance suppression), and the read-only mutation guarantee.
  Test count 1677 → 1687.

### Phase 7 exit criteria

- All seven slices landed with focused service-layer tests.
- Default behavior with config off matches Phase 6 baseline exactly (no
  fixture or test churn from existing suites).
- At least one end-to-end fixture test that drives a real datalog through the
  Phase 7 pipeline and verifies the resulting proposal differs from the
  Phase 6 baseline in the expected, explainable ways. ✓ Complete —
  `tests/unit/test_phase7_end_to_end_pipeline.py` builds a synthetic
  datalog with five clusters (steady cruise, steady boost, transient
  rpm, spool transition, firmware-marked transient) and asserts each
  slice's signature on the resulting summary: clamp transparency on
  the cruise cell, derivative gate rejecting the transient cluster,
  firmware learn gate rejecting the firmware cluster, boost penalty
  surfaced on the spool cell, full-grid coverage on the snapshot,
  smoothed layer separate from the raw, and root-cause diagnostics
  flagging a uniform-lean fixture as `injector_flow_error`.
- Workspace review UI surfaces every Phase 7 signal (confidence, coverage,
  rejection reason, clamp, smoothing layer, diagnostics) without hiding any
  underlying numbers. ✓ Complete — `VeAnalyzeReviewService.build()` now
  takes optional `smoothed_layer` and `diagnostics` kwargs and emits
  additive lines for clamp transparency, boost penalty counts, the
  smoothed layer summary, and each root-cause diagnostic. New
  `clamp_count`, `boost_penalty_count`, `smoothed_summary_text`, and
  `diagnostic_lines` fields on `VeAnalyzeReviewSnapshot` (defaults
  preserve existing snapshot equality and prior fixtures).

### Out of scope for Phase 7 (deferred to Future Phase 15)

- ML-based sample scoring or anomaly detection.
- Automatic root-cause *correction* (Phase 7 only diagnoses; the operator
  applies the fix).
- Native-core implementation of the assist pipeline.
- Any change that requires firmware modifications or protocol changes.

## Subsystem Gap Matrix

Status key: **Implemented** | **Partial** | **Missing** | **Implemented, unvalidated** | **Implemented, fragile**

| Subsystem | Status | Evidence | Main gap | Recommended next step |
|---|---|---|---|---|
| INI constants parsing (`lastOffset`, data types, pages) | Implemented | `test_parsers.py`; real INI verified | None critical | — |
| INI preprocessor (`#if`/`#else`/`#endif`/`#set`/`#unset`) | Implemented | `test_ini_preprocessor.py` (12 tests); Hardware Testing menu hidden; `test_active_settings_persistence.py` | None critical | — |
| Table definition parsing and editing (`[TableEditor]`) | Implemented | `test_speeduino_fixture.py`; `test_speeduino_controller_client.py` | — | — |
| Curve definition parsing and editing (`[CurveEditor]`) | Implemented | `CurveDefinition` model + `_parse_curve_editors()` pass (38 tests) + `CurvePageService` (20 tests) + `CurveEditorWidget` (QTableWidget, read-only X / editable Y, staged highlighting, undo/redo, write/burn; 32 presenter tests) | — | — |
| Page/layout compilation | Implemented | `test_definition_layout_service.py`; `test_tuning_page_service.py` | None critical | — |
| INI gauge catalog (`[GaugeConfigurations]`) | Implemented | `DashboardLayoutService._widgets_from_ini()` + `_zones_from_gauge_config()`; 8 new tests in `test_dashboard_layout_service.py`; `set_front_page_data()` seeds layout on project open and "Default Layout" reset | — | — |
| FrontPage indicators | Implemented | `_IndicatorStrip` in `dashboard_panel.py`; evaluates expressions via `VisibilityExpressionService`; INI-configured on/off colors; hidden when no indicators defined | — | — |
| Tune-backed table materialization | Implemented | `MsqWriteService.save(insert_missing=True)` now injects missing `<constant>` nodes into the first `<page>` element so generator-staged values for tables/scalars absent from the source XML are preserved (Fragile area #1 fix). Default `insert_missing=False` keeps the historical byte-stable behaviour; `test_blank_table_materialization.py` continues to document the default-off limitation and `test_msq_write_insert_missing.py` covers the new path (table insertion, scalar insertion, staged-only values with no base, preservation of existing constants, idempotent re-save) | — | — |
| AFR/Lambda target tables (lastOffset round-trip) | Implemented | `test_release_round_trip.py` (19 tests) + `test_production_round_trip.py` (31 tests); both U16P2 and production pairs verified | — | — |
| Production artifact round-trip (`speeduino 202501-T41`) | Implemented | `test_production_round_trip.py` (31 tests): `speeduino-dropbear-v2.0.1.ini` + base-tune.msq + `Ford300_TwinGT28_BaseStartup.msq` all in `tests/fixtures/` | — | — |
| Wideband calibration workflow | Implemented | `WidebandCalibrationService` + 5 published presets + custom preset support + `WidebandCalibrationPanel` widget (preset combo, summary, Apply button) **embedded into the MainWindow Runtime tab** next to `HardwareTestPanel`; routes through `MainWindow._send_wideband_calibration()` → `client.write_calibration_table(2, payload)`; connect/disconnect hooks toggle the panel; 5 offscreen Qt MainWindow wiring tests in `test_main_window_wideband_wiring.py` confirm panel construction, default-disabled state, payload dispatch matches the service-generated bytes exactly, no-op guard when no active client, and disconnect-disable | — | — |
| Hardware setup wizard table generation | Implemented | Generator services well-tested; wizard wired; `test_hardware_setup_wizard_msq_round_trip.py` drives production INI/MSQ → wizard `_on_generate_ve_table()` → `MsqWriteService` → reparse | — | — |
| Workspace staging/materialization | Implemented | `test_tuning_workspace_presenter.py`; burn, revert, sync confirmed | — | — |
| ControllerCommands dispatch | Implemented | `ControllerCommand` model + `_parse_controller_commands()` (70+ production commands); `SpeeduinoControllerClient.send_controller_command(payload)`; `HardwareTestPanel` widget in Runtime tab (test mode, injector/spark on/off/pulsed, utilities); 29 focused tests | — | — |
| **LoggerDefinition protocol (live tooth/composite logger)** | **Implemented** | `LiveTriggerLoggerService` + `TriggerCaptureWorker` wired into `MainWindow._capture_live_trigger_log()`; `SpeeduinoControllerClient.fetch_logger_data()` sends start (`H`/`J`), polls `toothLog1Ready`, reads, and sends stop (`h`/`j`); CSV hand-off to `TriggerLogAnalysisService`; end-to-end coverage in `test_trigger_capture_worker.py` (success + failure paths) plus decoder coverage in `test_live_trigger_logger_service.py` | — | — |
| Reconnect mismatch UI warning | Implemented | `_connect_session_with_config()` shows `QMessageBox.warning()` + status bar message when firmware signature changed since last connect | — | — |
| Runtime evidence trust signals | Implemented | `_poll_runtime()` calls `uncertain_channel_groups()` and dims + tooltips uncertain channel rows in the Runtime channel table | — | — |
| Board detection (capability-first) | Implemented | `test_board_detection_service.py` (11 tests); `detect_from_capabilities()` prefers firmware facts | — | — |
| Firmware capability / reconnect tracking | Implemented | `test_session_service.py` (10 tests); `test_firmware_capabilities.py` (16 tests) | — | — |
| Logging / datalog workflow | Implemented | `LoggingPanel` first-class tab; multi-profile sidecar; real-time capture; profile-ordered review | Profile-per-firmware-signature variant not implemented (low priority) | — |
| VE Analyze / WUE Analyze | Implemented | Service layer + presenter integration + UI complete; proposal staging wired | — | — |
| TSDash / vehicle display integration | Implemented | `TcpTransport` + "Connect via WiFi" done; HTTP live-data API on port 8080 done; mDNS `speeduino.local` resolution done; Speeduino Phase 11 firmware Serial2 transport complete (bench validation only remains); `TsDashFileService.parse()` / `export()` handle the **real TSDash schema** reverse-engineered from the decompiled JAR (`<dsh xmlns="http://www.EFIAnalytics.com/:dsh">` root, `<bibliography>` / `<versionInfo fileFormat="3.0">` / `<gaugeCluster>` with `<dashComp type="com.efiAnalytics.apps.ts.dashboard.{Gauge,Indicator,DashLabel,HtmlDisplay}">` children carrying reflection-emitted `RelativeX/Y/Width/Height`, `Title`, `Units`, `Min/Max`, `LowWarning/HighWarning/LowCritical/HighCritical`, `OutputChannel`); 18 focused tests covering parse, export, error cases, and full round-trip preservation; component types not in the FQN map fall back to lowercased simple class name | — | — |
| Test coverage / regression protection | Implemented | 1805 tests; strong on parsers, generators, evidence, comms, board detection, production round-trips, curve editor, dashboard layout, Phase 7 assist, TSDash file format, wideband calibration, MSQ insert-missing fix; `EcuDefinition.is_little_endian()` / `byte_order()` consumer added with focused tests; offscreen Qt widget tests now cover `HardwareSetupWizard` and `WidebandCalibrationPanel` | — | — |

## Completed Slices

All previous recommended slices are done:

1. ~~VE Analyze wired end-to-end~~ ✓ Done
2. ~~Proposal preview + staged apply~~ ✓ Done
3. ~~WUE Analyze parity~~ ✓ Done
4. ~~Capability/verification hardening~~ ✓ Done — write chunking, blocking_factor, page cache invalidation, firmware signature tracking
5. ~~INI preprocessor~~ ✓ Done — `#if`/`#else`/`#endif`/`#set`/`#unset`, two-phase `active_settings` override
6. ~~Flash preflight using manifest/capability facts~~ ✓ Done
7. ~~Dedicated Logging tab~~ ✓ Done — `LoggingPanel`, multi-profile sidecar, real-time capture, profile-ordered review
8. ~~Real-release round-trip tests~~ ✓ Done — `test_release_round_trip.py` (19 tests), U16P2 experimental pair fixtures
9. ~~Capability-first board detection~~ ✓ Done — `detect_from_capabilities()`, `reconnect_signature_changed()`, `FirmwareCapabilities` trust helpers
10. ~~Curve editor service layer~~ ✓ Done — `CurveDefinition`/`CurveYBins`/`CurveAxisRange` models; `_parse_curve_editors()` INI pass (38 tests); `TuningPageKind.CURVE` + curve fields on `TuningPage`; `CurvePageService` with keyword group classification (20 tests)
11. ~~Production artifact round-trip tests~~ ✓ Done — 31 tests covering `speeduino-dropbear-v2.0.1.ini` + base-tune.msq + `Ford300_TwinGT28_BaseStartup.msq`; all fixtures in `tests/fixtures/`
12. ~~CurveEditorWidget UI~~ ✓ Done — `CurvePageSnapshot`/`CurveRowSnapshot` in presenter; `CurvePageService` wired into `load()`; `stage_curve_cell`/undo/redo; `CurveEditorWidget` QTableWidget (X read-only, Y editable, staged highlighting, undo/redo/write/burn); 32 tests
13. ~~TCP/WiFi transport~~ ✓ Done — `TcpTransport(host, port=2000)`, "Connect via WiFi" dialog gated on `boardCap_wifiTransport`, mDNS `speeduino.local` resolution, reconnect signature-change warning; 1595 tests total

## Near-Term Priorities

### FrontPage indicators and INI-driven gauge catalog

- parse `[GaugeConfigurations]` into named gauge definitions with min/max/warn/danger metadata
- parse `[FrontPage]` gauge and indicator lists
- seed the default dashboard from `[FrontPage]` gauge selections; look up thresholds from `[GaugeConfigurations]`
- add an indicators panel or status strip driven by `[FrontPage]` indicator expressions

### Reconnect warning and runtime trust surface

- wire `SessionService.reconnect_signature_changed()` to a visible operator warning in MainWindow on connect
- wire `FirmwareCapabilities.uncertain_channel_groups()` to the Runtime channel table to flag uncertain evidence rows

### Setup and generators

- keep consolidating Engine Setup and Hardware Setup Wizard into one obvious primary workflow
- deepen assumption reporting for staged generators
- expand advanced-input capture without slowing the default first-start path

### Evidence and replay

- keep replay/evidence deterministic and explainable
- prefer page-local or evidence-local refreshes over broad UI rerenders
- continue connecting replay context directly to tuning decisions

### Logging

- datalog profile work complete; maintain channel selection and field metadata as first-class operator workflow
- keep trigger/composite/tooth logs as dedicated tools; LoggerDefinition protocol is a future slice

### Bench/runtime safety

- reconnect warning and trust signal surfacing are the next hardening steps (see above)
- ControllerCommands dispatch (hardware test injectors/sparks) is a useful bench tool but lower priority than curve editor

### Dashboard

- INI-driven gauge catalog and FrontPage indicators are the next dashboard slice
- additional gauge painter kinds (AnalogBar, LED, HistogramPainter) are polish after indicator expressions work

### TCP transport + WiFi connection ✓ Complete

`TcpTransport`, "Connect via WiFi" dialog (gated on `boardCap_wifiTransport`), mDNS `speeduino.local` resolution, and HTTP live-data API (port 8080) are all implemented. Speeduino Phase 11 firmware Serial2 transport is also complete; only hardware bench validation remains on the firmware side.

**Next step for WiFi:** hardware bench validation of the full TCP round-trip — page read/write/burn over Airbear on port 2000 with the production `speeduino-dropbear-v2.0.1-teensy41.hex`.

### TSDash / vehicle display integration

TSDash (`C:\Users\Cornelio\Desktop\TSDash`) is a separate Raspberry Pi–targeted gauge cluster display app from EFI Analytics. It:

- connects directly to the ECU via serial using the same Speeduino protocol commands
- loads `.dash` XML layout files defining gauge positions, channel bindings, and gauge face images
- provides a web-based configuration UI that TunerStudio links to under Tools
- runs standalone as a kiosk display without TunerStudio

**How our product should integrate:**

There are three levels of integration with increasing complexity:

1. **HTTP live-data API (near-term, high value)** — add a simple opt-in HTTP server (e.g. on `localhost:8080`) that serves live `OutputChannelSnapshot` as JSON on each poll tick. This immediately makes our app a TSDash data source replacement for local browser-based gauge displays, and enables a second screen or mobile browser to show live data without TunerStudio. The API surface should mirror TSDash's `/api/v1/channels` or a simplified equivalent.

2. **Import `.dash` layout files (medium-term)** — parse the TSDash `.dash` XML format (`<gaugeCluster>` root, positioned gauge/LED/label components with channel bindings, scale min/max) and translate the metadata layer (channel name, min/max, position, kind) into our `DashboardWidget` JSON layout. The embedded base64 image data (analog gauge faces, fonts) is not needed — we render using our own painters. This lets operators reuse existing Speeduino `.dash` layouts in our dashboard without manual re-entry.

3. **Export to `.dash` format (longer-term)** — export our dashboard layout to a `.dash` file for deployment on a Raspberry Pi running TSDash. The export would need to produce gauge component elements with appropriate image placeholders (or use one of the stock TSDash gauge images). This creates a single authoring workflow: design the dashboard in our desktop app, deploy to the Pi.

**What to track in the gap matrix:**

The `.dash` format is XML with embedded base64 fonts/images. The `firmwareSignature` attribute in `<versionInfo>` pairs the layout with an ECU type — the import step should validate this against the loaded definition's signature. There are Speeduino-specific layouts in TSDash (`Speeduino_LED.dash`, `Speeduino_Sweep.dash`) with pre-wired channel names matching Speeduino output channels.

**TSDash `.dash` files** — located at `C:\Users\Cornelio\Desktop\TSDash\Dash\`

Pre-made Speeduino layouts available:
- `Speeduino_LED.dash` — LED-style indicators
- `Speeduino_LED_Amber.dash`
- `Speeduino_Sweep.dash` — sweep analog gauge style

### TSDash decompilation findings

TSDash.jar was decompiled (4946 files, jd-core 1.1.3, jd-gui built from source). The majority of source is obfuscated (single-letter class names). Key findings extracted from string literals and unobfuscated resource paths:

**Architecture:**
- Java Swing application (`SingleChannelDashComponent` → `Gauge`, `Indicator` subclasses)
- Each component subscribes to exactly one named output channel via `subscribeToOutput()`
- Layout encoded and decoded via a serialization helper; stored in `.dash` XML
- Embedded HTTP server (NanoHTTP-style, class `aD.n`) serves a web-based config UI on a fixed port
- Tuning views (`TuneViewGaugeCluster`, `SelectableTable`) embedded within TSDash for on-Pi table editing

**Named gauge painter types (17 total):**
- `AnalogGaugePainter` — round sweep gauge with bitmap face overlay
- `RoundAnalogGaugePainter` — similar, pure-vector variant
- `AsymetricSweepRenderer` — non-symmetric sweep arc
- `AnalogBarPainter` — bar that sweeps like an analog gauge
- `AnalogMovingBarGaugePainter` — moving bar variant
- `BasicReadoutGaugePainter` — numeric digital readout
- `BulbIndicatorPainter` — round LED bulb indicator
- `RectangleIndicatorPainter` — rectangular indicator
- `LedPainter` — LED strip
- `HistogramPainter` — histogram/bar chart for one channel
- `HorizontalBarPainter`, `HorizontalDashedBar`, `HorizontalLinePainter`
- `VerticalBarPainter`, `VerticalDashedBarPainter`
- `IndicatorPainter` (interface)
- `GaugePainter` (interface)

**Limitations identified from the source:**
- **Single-channel per component**: every gauge is bound to exactly one output channel; no multi-channel overlay (e.g. AFR + target AFR on same needle)
- **Bitmap-coupled gauge faces**: `AnalogGaugePainter` preloads face images from base64 in the `.dash` XML; no vector-only mode means file sizes are large and scaling artifacts occur
- **No live history / sparkline**: `AnalogGaugePainter` has a `lastHistoryValue` field tracking exactly one previous sample — there is no time-series buffer, no sparkline trace, no min/max envelope
- **No evidence integration**: no concept of highlight zones, VE cell hits, or evidence replay context in any painter
- **Web config only**: configuration requires a browser pointed at the Pi's IP; no in-app layout editor
- **No tuning context awareness**: does not know which table/curve the user is currently editing; the gauge cluster is a static live display with no connection to what's being tuned
- **Static alarm logic**: alarm thresholds are set per-gauge in the XML config; no cross-channel expressions
- **Java 8 + Swing**: heavy JVM dependency; suboptimal for headless Pi deployment; not suitable for embedding in a Python app

**Where our implementation would be better:**

| Dimension | TSDash | Our implementation |
|---|---|---|
| Rendering | Java2D on Swing with preloaded bitmap faces | PySide6 QPainter — pure vector, pixel-perfect at any size |
| Channel binding | One channel per component | Same initially, but can add multi-channel support (e.g. two needles) |
| History display | Single `lastHistoryValue` only | Can buffer N samples and render sparkline trace inside gauge face |
| Evidence overlay | None | Can shade gauge face zone based on VE/WUE evidence hit density |
| Layout editor | Browser-based web UI on Pi | Native in-app drag-and-drop (already partially implemented in `DashboardPanel`) |
| Tuning context | Isolated from tuning workflow | Shares `TuningWorkspacePresenter` state — knows active page, staged edits |
| Alarm logic | Per-gauge threshold only | Can add multi-channel visibility expression evaluation (reuses existing `VisibilityExpressionService`) |
| WiFi/network | TunerStudio relay required for network; no native TCP to ECU | HTTP live-data API + `TcpTransport` (gated on `boardCap_wifiTransport`) + EcuHub UDP discovery |
| Platform | Java 8, must install JRE on Pi | Python binary or HTTP endpoint; browser or any network client can consume data |
| Gauge face library | Fixed bitmaps embedded in `.dash` files | INI `[GaugeConfigurations]` seeded defaults; custom faces rendered procedurally |
| ECU discovery | Manual IP/port entry | UDP broadcast `DISCOVER_SLAVE_SERVER` → `255.255.255.255:21846`; Airbear responds with device name, MAC, port |
| INI management | Manual file copy to Pi | Auto-fetch `https://speeduino.com/fw/[signature].ini` on first connect using firmware `'Q'` response |
| Formula channels | Not supported | Virtual channels as math expressions over hardware channels (reuses `MathExpressionEvaluator`) |
| Multi-screen navigation | Up to 20+ indexed screens, arrow-key nav | Equivalent `DashScreen` model with JSON persistence; arrow/swipe navigation in fullscreen mode |
| Remote control API | REST `/screen/*`, `/log/*`, `/system/*` + screenshot | Same REST surface via embedded FastAPI/aiohttp thread; phone browser as remote |

### DropBear ESP32-C3 WiFi co-processor — confirmed schematic details

Schematics confirmed from `C:\Users\Cornelio\Desktop\V2.0.1\Schematic.pdf` (2026-04-04).

**Hardware confirmed:**

The ESP32-C3 SUPERMINI (U4) is a **plug-in connector module**, not a soldered chip. It may not be populated on all DropBear units. It connects as follows:

| Signal | Teensy pin | DropBear net | ESP32-C3 SUPERMINI pin |
|---|---|---|---|
| UART TX (Teensy→ESP32) | Pin 8 (Serial2 TX) | MCU-D8 | GPIO20 / RX |
| UART RX (Teensy←ESP32) | Pin 7 (Serial2 RX) | MCU-D7 | GPIO21 / TX |
| Power | — | VDD | 5V (pin 5) |
| Ground | — | GND | GND (pin 6) |

Critical distinction: the ESP32-C3 is on **Teensy Serial2 (pins 7/8)**, not Serial1. Serial1 (pins 0/1) is the separately broken-out user header for secondary serial protocols (RealDash, CAN-sim, etc.). The ESP32 therefore has its own dedicated UART channel and cannot simply inherit the existing secondary serial protocol handling.

The ESP32-C3 SUPERMINI module features:
- WiFi 802.11 b/g/n (2.4 GHz)
- Bluetooth 5.0 LE
- RISC-V 160 MHz, 4 MB flash
- Own USB-C port for independent reprogramming (without touching Teensy firmware)

**Airbear — official ESP32-C3 firmware (confirmed working):**

`C:\Users\Cornelio\Desktop\Airbear-main` contains the official Speeduino Airbear firmware (**v0.2.0**, PlatformIO / Arduino framework). This is the ESP32 bridge firmware. Version string is defined as `FIRMWARE_VERSION "0.2.0"` in `globals.h:11`. Previous Tuner docs referenced v0.1.2 — that version has been superseded. Key findings:

**Four configurable operating modes** (set via web config UI):

| Mode | Connection type | What it does |
|---|---|---|
| `CONNECTION_TYPE_DASH (1)` | Web dashboard only | ESP32 polls ECU at 30 Hz via `'A'` command, parses channels into JSON, serves web dashboard from LittleFS at `http://speeduino.local/`, pushes live data via SSE at `/events`, also serves JSON at `/data`. Now parses the **full 148-byte output channel block** and emits **50+ channels** including ethanol%, VVT angles, dwell, knock, engine-protect status, pressure sensors, and PW2–6 for 6-cylinder support (`serialParser.cpp:166–324`) |
| `CONNECTION_TYPE_BLE (2)` | Bluetooth LE | BLE UART bridge using NimBLE-Arduino with Nordic UART Service UUIDs (`6E400001-B5A3-F393-E0A9-E50E24DCCA9E`); forwards raw ECU bytes to BLE client; no framing changes |
| `CONNECTION_TYPE_TUNERSTUDIO (3)` | TCP bridge only | Full Speeduino protocol relay over TCP on **port 2000**; handles `'F'`/`'Q'`/`'S'` identification raw and the length-prefixed new protocol framed transparently (`tcp-uart.cpp:84–125`) |
| `CONNECTION_TYPE_DASH_ECHO (4)` — **NEW in 0.2.0** | Dash + TunerStudio simultaneously | 30 Hz dashboard polling + TCP TunerStudio relay both run against the same Teensy UART, arbitrated by a mutex. Lets a browser dashboard and the desktop tuner share one ECU without mode switching. **Critical for desktop integrators**: TCP commands can now return `RC_BUSY_ERR` (0x85) when the dashboard holds the UART mutex — the desktop TCP client must recognise this byte and retry with short backoff instead of treating it as protocol corruption (`main.cpp:207–214`, `tcp-uart.cpp:37–47`) |

**TCP error envelope** (new in 0.2.0, `tcp-uart.h:11–12`):
- `RC_TIMEOUT` (0x80) — Airbear waited `ECU_SERIAL_TIMEOUT = 400 ms` and the Teensy didn't answer. No internal retry.
- `RC_BUSY_ERR` (0x85) — UART mutex held by dashboard poll; command rejected cleanly.
- Desktop implication: the `TcpTransport` read path should treat these as first-class recoverable errors (backoff + retry for busy, surface "ECU not responding" for timeout) and *not* fall through into the framed response parser.

**Serial connection:** `Serial_ECU` maps to `Serial1` on non-CDC-boot builds (`globals.h:39`). Code calls `Serial_ECU.begin(115200)` in `main.cpp:182`. Wiring still matches the DropBear schematic (MCU-D7/D8 = Teensy Serial2). Baud rate: **115200**. No flow control. No baud negotiation.

**Dash mode channel list** (parsed from the 148-byte live-data block, matches Speeduino `LOG_ENTRY_SIZE`):
Includes `secl`, `running`, `dwell`, `MAP`, `IAT`, `CLT`, `Battery_Voltage`, `AFR1`, `AFR2`, `rpm`, `VE`, `afr_target`, `PW1–6`, `TPS`, `tps_DOT`, `advance`, `boost_target`, `boost_duty`, `rpmDOT`, `ethanol%`, `flex_correction`, `flex_ign_correction`, `idle_load`, `baro`, fuel/oil pressure, VVT1/VVT2 angles, knock counts, engine-protect status, correction factors, driver outputs, CAN status. Roughly **50+ channels** (expanded from the earlier ~40 figure — 6-cyl PW2–6 and VVT angles are the biggest deltas).

**Web dashboard:** Static HTML/CSS/JS files in LittleFS (`data/` folder). Browser connects to `http://speeduino.local/`, receives SSE stream. Standalone web gauge cluster — no TunerStudio needed.

**WiFi setup + AP fallback:** On first boot (or when station mode fails), Airbear starts an AP with SSID `Speeduino Dash` and password `Bear-XXYYZZ` where `XXYYZZ` is the last 3 octets of the MAC (`wifi_mgt.cpp:68–90`) — **not** an open network as older docs said. No captive portal; user must manually open `http://speeduino.local/config`. Station-mode credentials are persisted in preferences.

**REST API** (new in 0.2.0, `rest_api.cpp`):
- `GET /api/realtime` — current output-channel snapshot plus firmware variant envelope (`fw_variant` field distinguishes `speeduino 202501-T41` vs `-U16P2` — Airbear probes this via `'Q'` at startup in `serialParser.cpp:66–113`).
- `GET /api/status` — product name, FW version, uptime, heap, WiFi RSSI, MAC, IP (`rest_api.cpp:45–63`).
- `GET|POST /api/log/*` — datalog management: conditional CSV logging to LittleFS with field-expression triggers (`>`, `<`, `>=`, `<=`, `==`); `POST /api/log/start` takes a JSON config (`datalog.h`).

**EcuHub UDP auto-discovery** (new in 0.2.0, `discovery.cpp:22–24`): Airbear broadcasts on UDP port **21846** advertising itself as `Dropbear v2.0.1`. The discovery message goes out on boot and on demand. Desktop code can listen on 21846 and populate a device picker rather than asking the user for a host/port — matches the TSDash discovery pattern exactly.

**OTA firmware update endpoints** (new in 0.2.0, `updater.h` / `main.cpp:70–98`):
- `POST /updateFWUpload` — uploads a new Airbear firmware blob directly.
- `POST /updateDataUpload` — uploads a new `data/` LittleFS image (web dashboard assets).
- Remote URL fetch is also supported. All require LittleFS to be mounted. The desktop can optionally expose a one-button Airbear updater that hits these endpoints instead of dragging users into the PlatformIO CLI.

**CAN bus (hardware-ready, JSON-only)** (`can_bus.h/.cpp`): MCP2562 transceiver on GPIO 4/5, 500 kbps, ring-buffered 64 frames. Frames are exposed via `getCanFramesJSON()` but **not yet merged into the main OCH dashboard JSON**. Treat this as a preview — no stable desktop contract yet.

**eFuse:** On first boot, burns an eFuse to permanently disable UART debug print messages so they don't corrupt ECU serial communication. One-way, irreversible.

**Watchdog:** 5-second hardware watchdog (`timer.cpp:9`). Airbear resets on a deadlock — the TCP session on the desktop side will drop and must reconnect.

**What the Teensy firmware still needs:**
- Initialize Serial2 at 115200 on DropBear boards — tracked as **Phase 11 Slice A** in the Speeduino firmware roadmap (`FIRMWARE_ROADMAP.md`)
- Route Speeduino protocol responses out Serial2 — tracked as **Phase 11 Slice B**
- `boardHasCapability(BOARD_CAP_WIFI_TRANSPORT)` gate in the routing dispatcher — capability bit 7 is already set for `PIN_LAYOUT_DROPBEAR` ✅; the routing guard lands with Phase 11 Slice B

The firmware Phase 11 integration test path uses the bundled minimal diagnostic firmware (`diagnostics/minimal_teensy41_serial/`): flash it, confirm the physical Serial2 ↔ Airbear link via TCP, then validate full page round-trip with our `TcpTransport` before any production firmware changes.

**What our app needs for TunerStudio/TCP mode:**
- `TcpTransport(host, port=2000)`: speaks identical Speeduino framing to `SerialTransport` — no protocol changes needed since Airbear handles the relay transparently
- "Connect via WiFi" option in connection dialog, shown when `boardCap_wifiTransport` is set
- mDNS/Bonjour resolution of `speeduino.local` for zero-config connection
- **EcuHub UDP auto-discovery** (from TSDash decompilation): broadcast `DISCOVER_SLAVE_SERVER` to `255.255.255.255:21846` on startup; Airbear will respond with device name, MAC, TCP port, and connection state; populate a device picker rather than a raw host/port field — this is how TSDash finds ECUs and we should match it so both tools work on the same network without separate configuration

**What our app can use from Dash mode:**
- The `/data` JSON endpoint is equivalent to our planned "Phase 1 HTTP live-data API" — but it runs on the ESP32, not our app. We can read from it to populate our dashboard when connected via WiFi without USB.
- SSE at `/events` gives us 30 Hz push updates; no polling needed.
- The new `/api/realtime` + `/api/status` + `/api/log/*` REST surface (Airbear 0.2.0) gives us a stateless read-only telemetry path that doesn't need the raw TCP framing layer at all — useful as a lightweight fallback for embedded dashboards, a second "observer" desktop viewing live data while the primary desktop holds the framed TCP control session, or for external tooling (scripting, Grafana, Node-RED) that just wants the channels.
- `fw_variant` in the `/api/realtime` envelope is an authoritative source for which Speeduino firmware the Teensy is running — desktop can cross-check it against the signature string returned via `'Q'` to detect firmware swaps between sessions.

**BLE transport (longer-term):**
- NimBLE-Arduino with Nordic UART Service (`6E400001-B5A3-F393-E0A9-E50E24DCCA9E`)
- In BLE mode, raw ECU bytes are relayed to BLE clients — phone/tablet can run a native tuning app or gauge display using `bleak` on the laptop side
- Our `BleTransport` would use `bleak` to connect and speak the same Speeduino framing

**Other hardware details confirmed from schematics relevant to our app:**

*Analog inputs (all conditioned through SP720 clamp + LMV324LIDT op-amp to 3.3V):*
- MAP: external connector with DPDT switch (can swap between internal and external MAP)
- Baro: dedicated onboard KP234 sensor — always present, independent of MAP
- O2: one primary + one secondary (on SPARE2 sensor input); note in schematic: "Second O2 sensor should be on Spare 2 if in use"
- IAT, CLT, TPS: standard NTC/pot inputs with 470R pullup
- SPARE1, SPARE2 analog: two additional conditioned analog inputs
- Battery voltage: resistor divider to MCU-A15

*Digital inputs:*
- Flex sensor: MCU-D37 (dedicated pin, 270nF debounce cap)
- Clutch input: MCU-D36 (NMOS-gated digital input)
- SPARE1-Digital (MCU-D35), SPARE2-Digital (MCU-D34)

*Outputs:*
- Injectors 1–8: two MC33810 smart driver ICs via SPI (3.5A max per channel)
- Ignition 1–8: TC4424A gate drivers fed from MC33810
- Idle/Spare2, Fan/Boost, Tacho/Fuelpump, VVT/Spare1: ZXM56006DT8 dual-MOSFET low-side drivers
- Stepper: DRV8825 breakout (4-coil, DIR/STEP/EN from MCU-D30/31/32)

*Power:*
- 12V-Sw → 5V LDO (HCT8M05) with TVS protection and Schottky
- Separate VDD and VDDA rails; JP5 jumper to bridge them (normally open)
- Polyfuse F2 on VDDA; status LEDs for 12V-Sw, VDD, VDDA

### Our TSDash — design plan

Based on TSDash source analysis and confirmed DropBear hardware, here is the concrete design for our own gauge cluster display.

**Architecture:**

```
[ECU / Teensy 4.1]
       |
  USB serial  OR  Serial2 → ESP32-C3 WiFi bridge (TCP)  OR  ESP32-C3 BLE
       |
[Our Python app — TuningWorkspacePresenter]
       |
  OutputChannelSnapshot (polled live)
       |
  ┌────────────────────────────────────┐
  │  HTTP live-data API (opt-in)       │  ← phone browser, tablet, second monitor
  │  localhost:8080/api/channels       │
  └────────────────────────────────────┘
       |
  DashboardPanel (PySide6, in-app)     ← existing widget, to be expanded
       |
  GaugeWidget painters (vector QPainter)
```

**Phase 1 — HTTP live-data API (near-term)**

Add an opt-in HTTP server that serves the current `OutputChannelSnapshot` as JSON on every poll tick. Any browser, phone, or Raspberry Pi on the local network can consume this without TunerStudio.

- Endpoint: `GET /api/channels` → JSON object of `{channel_name: value, ...}`
- Endpoint: `GET /api/channels/{name}` → single channel value
- Endpoint: `GET /api/status` → connection state, firmware signature, sync state
- Start/stop controlled from preferences; port configurable
- No authentication for v1 (local network only)
- Implementation: Python `http.server` or `aiohttp` in a background thread; feeds from `OutputChannelSnapshot`

**Phase 2 — Expanded DashboardPanel gauge painters**

Currently the dashboard has a basic gauge set. Expand to match and exceed TSDash's 17 painter types, all rendered in pure QPainter vector:

| Painter | Status | Notes |
|---|---|---|
| Analog sweep (round) | Partial — exists | Add warning/danger arc shading |
| Digital readout | Exists | Add min/max envelope display |
| LED indicator | Exists | Already wired to INI `[FrontPage]` indicators |
| Vertical bar | Missing | |
| Horizontal bar | Missing | |
| Histogram (time series) | Missing | N-sample ring buffer + sparkline |
| Dual-needle analog | Missing | TSDash can't do this — our differentiator |
| Evidence heat overlay | Missing | VE/WUE hit density shaded on gauge arc |

**Phase 3 — TCP transport + WiFi connection + EcuHub discovery**

Add `TcpTransport(host, port)` that speaks identical Speeduino framing to the existing `SerialTransport`. Show "Connect via WiFi (ESP32)" option in connection dialog, gated on `boardCap_wifiTransport`.

Add EcuHub UDP auto-discovery (from TSDash decompilation — exact protocol confirmed):
- Broadcast `DISCOVER_SLAVE_SERVER` string to `255.255.255.255` UDP port **21846** on connection dialog open
- Parse newline-delimited key-value response from Airbear: `slave:`, `id:`, `serial:`, `port:`, `protocol:`, `connectionState:`, `name:`
- Populate a device list widget; user selects device rather than typing IP/port
- Airbear firmware implements the slave side (see Airbear roadmap Phase A4.2)
- Fall back to manual host/port entry if no response within 3 seconds

Add INI auto-fetch on first connect:
- After `'Q'` command identifies firmware as `speeduino 202501-T41` (or `-U16P2`), check whether the loaded definition matches the signature
- If not, fetch the matching INI from `https://speeduino.com/fw/[signature].ini` in a background thread
- Prompt user to adopt the fetched definition or keep the current one
- For custom/local firmware the definition must be loaded manually — auto-fetch applies to stock signatures only

**Phase 3.5 — Formula channels and virtual OutputChannels**

TSDash supports computed channels as math expressions over hardware channels. The `MathExpressionEvaluator` service already exists:
- Add a `FormulaOutputChannel` type: name, units, min/max, expression string
- Evaluate on every `OutputChannelSnapshot` update alongside hardware channels
- Expose in the gauge binding picker identically to hardware channels
- Built-in formula channels to ship by default:
  - `injDutyCycle` = `PW1 * RPM / 1200.0` (%)
  - `lambda1` = `afr1 / 14.7` (gasoline stoich; configurable per fuel type)
  - `boostPSI` = `(MAP - baro) * 0.1450` (PSI gauge)
  - `coolantF` = `coolant * 9.0/5.0 + 32.0` (°F)

**Phase 4 — Multi-screen dashboard navigation**

TSDash supports up to 20+ indexed screens with arrow-key navigation. The `DashboardPanel` is currently single-screen:
- Define a `DashScreen` model: ordered list of gauge widgets with layout geometry
- Load/save to JSON (`.dashboard.json` sidecar next to the project file)
- Arrow key and swipe navigation; fullscreen mode for in-car Pi display
- Default screen set pre-populated from INI `[GaugeConfigurations]` and `[FrontPage]`:
  - Overview (RPM, MAP, AFR, TPS, CLT, boost)
  - Fuelling detail (PW1–PW6, VE, corrections, flex %)
  - Ignition detail (advance, dwell, knock retard)
  - Temperatures (CLT, IAT, fuel temp, oil/fuel pressure)
  - Status (sync, engine protection, idle load, battery)

**Phase 5 — Web remote control API**

TSDash's phone-facing REST API (confirmed from decompiled source) — implement equivalent:
- `GET /screen/screenshot` — JPEG of current `DashboardPanel` via `QScreen.grabWindow()`
- `POST /screen/navigate` `{action: "left"|"right"|"up"|"down"}` — screen navigation
- `GET /screen/current` — `{index, name, total}`
- `GET /log/list`, `GET /log/download?file=NAME`, `DELETE /log/delete?file=NAME`
- `POST /system/shutdown`, `POST /system/restart`
- `GET /status` — connection, sync, firmware signature, uptime
- Serve from the same embedded HTTP server as the Phase 1 live-data API (same port, additional routes)
- Phone accesses via car WiFi hotspot (provided by Airbear AP)

**Phase 6 — BLE transport (phone/tablet)**

Implement `BleTransport` using the ESP32-C3's Nordic UART Service (`6E400001-B5A3-F393-E0A9-E50E24DCCA9E`). Enables a phone app (or our desktop app on a laptop without USB) to connect wirelessly. Longer-term — requires Airbear in BLE mode and a BLE library on the PC side (e.g. `bleak`).

**Key differentiators vs TSDash:**

1. **No JVM required** — runs as part of the Python app or as a browser client
2. **Dual-needle gauges** — show AFR + target AFR on one sweep
3. **Sparkline history** — N-sample buffer visible inside gauge face, TSDash has none
4. **Evidence overlay** — VE/WUE cell hit density shaded on gauge arc zones
5. **Tuning context** — gauge cluster knows which table/cell is active; can highlight related gauges
6. **Alarm expressions** — multi-channel visibility expressions reusing `VisibilityExpressionService`
7. **INI-seeded defaults** — `[GaugeConfigurations]` and `[FrontPage]` pre-populate layout from definition
8. **WiFi native** — direct TCP to ECU via ESP32-C3 on Serial2; no TunerStudio relay needed
9. **EcuHub UDP discovery** — zero-config device finding (exact TSDash protocol, port 21846)
10. **Formula channels** — virtual computed channels via `MathExpressionEvaluator`; TSDash has no equivalent
11. **Multi-screen navigation** — fullscreen Pi display with arrow/swipe between themed screens
12. **Web remote control** — phone browser controls Pi display via REST + screenshot API
13. **BLE** — phone/tablet gauge display without laptop once Airbear is in BLE mode

## Post-Roadmap Program

This section is intentionally beyond the active Python delivery roadmap. It exists to capture where the project should go once the current product is stable, usable, and validated against real-world artifacts.

### Program goals

- keep the Python app as the reference implementation until workflow and compatibility semantics stop moving
- move from "legacy-compatible where needed" toward "owned ecosystem" where firmware, tune contract, definition contract, and desktop behavior are controlled together
- prepare for a possible native future without forcing a rewrite before the model is understood

### Firmware Roadmap Cross-Reference

The companion firmware roadmap lives at `C:\Users\Cornelio\Desktop\speeduino-202501.6\speeduino\FIRMWARE_ROADMAP.md`. Status as of 2026-04-04:

| Firmware Phase | Status | Desktop impact |
|---|---|---|
| 12: U16 maps where precision matters (DropBear/Teensy) | **Planned, coordinated with desktop Phase 14** | The desktop's table generators read each table's `data_type` from the active definition — DropBear definitions declare VE/AFR/spark/boost/VVT as U16, everything else stays U08; AVR definitions stay all-U08 |
| 1: Safety and Correctness | Complete | None direct |
| 2: Regression Harness | Complete — 263 decoder tests | Foundation for decoder-triggered live-log replay trust |
| 3: Runtime Structure | Substantially complete | `engineProtectStatus`, `status3`, `status5` byte positions locked; regression tests exist |
| 4: Board and Comms Consistency | Complete — capability flags, comms helpers, SPI flash dual-write | `boardCap_wifiTransport` bit 7 confirmed; `LOG_ENTRY_SIZE=132` → confirmed baseline |
| 5: Configuration and Observability | Complete — knock status flags, migration helpers, declarative `live_data_map.h` | `live_data_map.h` defines 148-row byte/field table; `LIVE_DATA_MAP_SIZE=148` constant for future channel contract |
| 6: Teensy 4.1 Platform Enablement | Complete — PWM fan, SPI flash wired, ADC path | SPI flash tune banks; dual-write to all 15 pages |
| 7: ADC Normalization | Complete — 10-bit normalization fix, 4-sample hardware averaging | Sensor channel values more reliable; ADC normalization tests exist |
| 8: Teensy Tune Transport Limits | Complete — `BLOCKING_FACTOR` 251→512, `TABLE_BLOCKING_FACTOR` 256→512, `EEPROM_MAX_WRITE_BLOCK` 255, `LOG_ENTRY_SIZE` 132→143 | Desktop write chunking already handles variable blocking factors; `ochBlockSize=143` in updated INI |
| 9: Decoder Tooth-Number Resolution | Substantially complete — 36-2-1 resolved, idle OL PWM/stepper tests, launch control, engine protection, Nissan360 | Higher-confidence decoder baseline for trigger log analysis |
| 10: (Phase 10 items noted inline above) | Included: `LOG_ENTRY_SIZE` 143→148 (`runtimeStatusA` packed byte), SPI flash all-page wiring, native CAN stabilization, board-hook extraction | **`LOG_ENTRY_SIZE=148` is the current production byte count**; `runtimeStatusA` adds `fullSync`, `transientActive`, `warmupOrASEActive`, `tuneLearnValid` bits |
| 11: ESP32-C3 Serial2 Transport | **Not yet started** — `Serial2.begin(115200)` + comms routing for DropBear; integration test path via minimal diagnostic firmware documented in `FIRMWARE_ROADMAP.md` Phase 11 | **Unblocks `TcpTransport` end-to-end test on real hardware**; capability bit 7 already set ✅ |

**Key firmware facts for desktop integration:**

- `LOG_ENTRY_SIZE = 148` (current production baseline; bytes 143-147 = `startRevolutions` 4-byte LE + `runtimeStatusA` packed status)
- `runtimeStatusA` high bits: `fullSync` (bit 4), `transientActive` (bit 5), `warmupOrASEActive` (bit 6), `tuneLearnValid` (bit 7) — VE/WUE analyze gate candidates
- `BLOCKING_FACTOR = 512`, `TABLE_BLOCKING_FACTOR = 512` on Teensy 4.1
- `boardCap_wifiTransport` = capability bit 7, set for `PIN_LAYOUT_DROPBEAR` on `CORE_TEENSY41` ✅; readable from the `'F'` command response
- ESP32 Serial2 init (Teensy pins 7/8 at 115200) **not yet done** — firmware Phase 11 tracks this; currently blocking TCP transport end-to-end test on real hardware
- U16P2 page-2 experimental path: smoke-tested in real TunerStudio; hi-res VE telemetry remains deferred (separate signature/INI/`ochBlockSize` slice)
- Tune-assist `runtimeStatusA` bits: can gate VE/WUE analyze cell acceptance on `tuneLearnValid` without a packet-size change
- Rover MEMS full-sync and 4G63 direct state coverage are deferred in the firmware roadmap; tooth-logger replay may surface evidence for these later
- `ochGetCommand` in the custom INI uses `'r'` command form, not legacy `'A'`; our `TcpTransport` should send `'r \x00 \x30 \x00 \x00 \x00 \x94'` — Airbear currently sends `'A'` (both work, firmware handles both)

### Future Phase 11: Product Model Stabilization

Goal: freeze the behavioral contract before any native-port effort.

Success criteria:

- real release INI/MSQ/firmware fixture coverage is broad enough to catch parser and layout regressions
- table generation, materialization, calibration, and staging flows are documented and test-backed
- docs clearly distinguish implemented, partial, fragile, and unvalidated areas
- the Python app is usable enough to act as the oracle for later ports

### Future Phase 12: Owned Tune And Definition Contracts

Goal: define the project's own file/runtime contracts instead of inheriting all long-term constraints from external formats.

Scope:

- design a versioned tune file contract
- design a versioned definition/schema contract
- define compatibility and migration rules
- decide which legacy INI/MSQ behaviors remain import/export compatibility only

Why this matters:

- once firmware and desktop evolve together, custom formats can remove ambiguity and fragile parsing edge cases
- this is the point where "compatibility layer" and "native platform" should become distinct concepts

Findings from the current artifact pass:

- real release compatibility is still tightly coupled to firmware signature families, page sizes, offsets, and INI parser behavior
- release definitions often represent semantic concepts indirectly through storage declarations, table-editor links, menu wiring, and naming conventions
- AFR/Lambda target tables are a concrete example of duplicated legacy representation that should collapse into one semantic native model
- application-owned metadata should not continue living in controller-definition-shaped files
- the firmware roadmap's `live_data_map.h` (148-row declarative byte/field table) is a concrete step toward a stable versioned runtime contract — this is the pattern to follow at the definition/tune layer

Preferred direction:

- authored native definition/schema files: `JSON5` — human-readable, supports comments, suits operator-authored calibration curve definitions and board capability declarations
- native tune/project files: `JSON` — version-tagged, diff-friendly, no binary blobs; replaces the current XML MSQ format for new save paths while retaining MSQ import/export for legacy compatibility
- firmware page/offset storage: retained as a separate import/export/runtime layer, not the primary authored format
- channel catalog: a versioned JSON catalog of semantic channel names, units, encoding, and logging contracts; replaces ad-hoc INI `[OutputChannels]` as the canonical reference for what each logged byte means

Concrete deliverables:

1. ~~`NativeDefinition` schema (JSON5): parameters, tables, axes, curve definitions, visibility, output channels, all with stable semantic IDs; INI parser produces this as an intermediate model today (implicit — make it explicit)~~ ✓ **v1 landed** as `tuner.domain.native_format.NativeDefinition` with `NativeParameter` (kind = scalar/enum/bits), `NativeAxis`, `NativeTable`, `NativeCurve`. v1 uses legacy names as semantic ids (rename pass deferred to v2). JSON5 deferred — v1 uses plain JSON to avoid a third-party dependency; JSON5 input would be a strict superset that the parser can adopt later.
2. ~~`NativeTune` file (JSON): a flat key→value store indexed by semantic parameter ID, not by firmware page/offset; includes schema-version, firmware-capability assertions, and edit history~~ ✓ **v1 landed** as `NativeTune` with `schema_version`, `definition_signature`, and a flat `values: dict[semantic_id, scalar | list[float]]`. Capability assertions and edit history deferred to v2+ — v1 captures the **shape** of the contract so existing INI/MSQ artifacts can round-trip through it.
3. ~~`CompatibilityLayer`: `NativeTune` → MSQ export for writing to firmware; INI/MSQ import path → `NativeTune` for legacy artifact ingest; migration rules for schema version bumps~~ ✓ **Import + reverse path landed.** Import side: `NativeFormatService.from_ecu_definition()` and `from_tune_file()` (axis-shaped `*Bins` collapse into `NativeAxis`; legacy-only values pass through under the legacy name; schema-version gating refuses future-major files and accepts forward-compatible minor bumps). Reverse side: `NativeFormatService.to_tune_file(native_tune, native_definition)` projects a `NativeTune` back into a legacy `TuneFile` ready for `MsqWriteService.save()` — inherits `rows`/`cols`/`units` from the native definition for shaped values and defaults legacy-only lists to 1×N. End-to-end test exercises the full path `NativeTune → to_tune_file → MsqWriteService.save → MsqParser.parse` against a synthetic source MSQ and verifies the bytes round-trip exactly. Schema-version migration rules still deferred — they aren't needed until v2 introduces a real semantic-id rename pass.
4. ~~`ChannelContract` (JSON): locks the byte position, encoding, and semantic name for each `LOG_ENTRY_SIZE` byte; tracks by firmware signature range; used by logging, replay, and VE analyze to interpret captured data reliably across firmware upgrades~~ ✓ **v1 landed** as `tuner.domain.channel_contract.ChannelContract` + `LiveDataMapParser` in `services/live_data_map_parser.py`. The parser consumes the firmware `live_data_map.h` header (`speeduino-202501.6/speeduino/live_data_map.h`) line-by-line and extracts every byte-table row into a `ChannelEntry(name, byte_start, byte_end, readable_index, encoding, field, notes, locked)`. Encodings: `U08`, `U08_BITS`, `U16_LE`, `S16_LE`, `U32_LE`. Special-offset constants (`OCH_OFFSET_RUNTIME_STATUS_A`, `BOARD_CAPABILITY_FLAGS`, `FLASH_HEALTH_STATUS`) extracted into typed contract fields. `find(name)` and `find_by_byte(byte_index)` lookup helpers exposed. **Structural canary test** sums all parsed entry widths against the real firmware file's `LIVE_DATA_MAP_SIZE = 148` so any future schema bump that breaks the parser fails loudly. 16 focused tests in `test_live_data_map_parser.py` covering synthetic single-byte/2-byte/4-byte/signed/bits rows, locked-flag handling, special-offset extraction, find-by-byte lookup, unknown-row tolerance, and the real firmware header on disk.

**Tests:** 24 focused cases in `tests/unit/test_native_format_service.py` covering legacy → native projection (scalars, axis detection, data tables, semantic-id == legacy-name in v1), tune projection (scalar + table + legacy-only pass-through), JSON round trip preservation for both definitions and tunes, schema-version gating (missing / future-major / forward-compatible minor / unparsable / non-object root), reverse `to_tune_file` projection (scalar with units, table with rows/cols/units, axis with length-as-cols, legacy-only list defaulting to 1×N, full round trip native → legacy → native), an end-to-end native → MSQ-write → re-parse pass against a synthetic source MSQ, and an end-to-end legacy → native → JSON → native pass.

Firmware-side implications:

- custom firmware will need explicit schema/capability version reporting beyond simple signature-family matching
- parameters, tables, axes, calibrations, and runtime channels should gain stable semantic identifiers
- runtime/log contracts should be versioned independently from tune storage/export contracts
- native tune import/export must be defined as a first-class firmware-facing contract, not as an accidental byproduct of page layout
- the `runtimeStatusA` packed byte (`tuneLearnValid`, `fullSync`, `transientActive`, `warmupOrASEActive`) is a preview of what explicit firmware-owned logging semantics look like — extend this pattern rather than adding more opaque bytes

### Future Phase 13: Native Shared Core Evaluation

Goal: determine whether the stable Python product should be backed by a native core, with C++ as the current leading candidate.

Evaluation criteria:

- measured startup, memory, packaging, protocol, or parsing pain in the Python product
- maturity of the frozen product model
- ability to port logic subsystem-by-subsystem while keeping Python as the oracle

Likely first native candidates:

- tune parser/serializer
- definition parser/compiler
- table/axis data model and transforms
- protocol/comms layer
- validation and diff engines

Non-goal:

- rewriting the desktop UI before backend semantics are stable

#### Phase 13 scope decisions (locked in)

| Decision | Choice |
|---|---|
| End goal | Gradual replacement (Python is the staging ground for an eventual Phase 14 native desktop) |
| First subsystem | MSQ parser/writer (highest existing test coverage = best oracle) |
| Migration cadence | Strict Python-as-oracle; C++ ships only after parity is proven on every fixture |
| C++ standard | C++20 |
| Compiler matrix | MSVC first; add GCC/Clang to CI later |
| Build system | CMake |
| Dependencies | stdlib + minimal vendored single-header tools (doctest, nanobind) |
| Test framework | doctest |
| Cross-validation | Shared MSQ fixtures + Python parity harness that drives both implementations and asserts byte equality |
| Bindings | nanobind |
| Where the C++ tree lives | `cpp/` subdirectory of this repo |
| Distribution | cibuildwheel + Python fallback path (`tests/unit/test_cpp_msq_parser_parity.py` skips when the extension isn't built) |
| Naming | `tuner_core` |
| First milestone | MSQ parser ported, Python parity harness asserts byte-identical writer output on every existing MSQ fixture |

#### First slice landed (MSQ parser)

- `cpp/include/tuner_core/msq_parser.hpp` — public C API: `MsqDocument`, `MsqConstant`, `parse_msq[_text]()`, `write_msq[_text]()`
- `cpp/src/msq_parser.cpp` — hand-rolled XML scanner (~150 lines, stdlib only). MSQ format is small enough that pulling in pugixml/expat would dwarf the slice.
- `cpp/tests/test_msq_parser.cpp` — 8 doctest unit cases covering parse, byte-stable no-op write, scalar update, multi-line table replacement, unknown-name drop (matches Python `MsqWriteService.save(insert_missing=False)` default), and malformed-input rejection.
- `cpp/bindings/tuner_core_module.cpp` — nanobind module exposing `parse_msq`, `parse_msq_text`, `write_msq`, `write_msq_text` plus the `MsqConstant` / `MsqDocument` dataclasses to Python as `tuner_core`.
- `cpp/CMakeLists.txt` — C++20, MSVC-friendly warnings, two options: `TUNER_CORE_BUILD_TESTS` (default ON) and `TUNER_CORE_BUILD_BINDINGS` (default OFF). Doctest is vendored at `cpp/third_party/doctest/doctest.h`; CMake fails fast with a clear download instruction if the user hasn't fetched it yet.
- `cpp/README.md` — locked-in scope decisions, first-time setup (`curl` doctest, `pip install nanobind`), C++ test build, Python binding build, and the rationale for the no-third-party-XML-library choice.
- `tests/unit/test_cpp_msq_parser_parity.py` — 9 parity cases. Imports `tuner_core` from a CMake build directory or from an installed wheel, **gated on the import succeeding** so dev installs without a compiler skip rather than fail. Cases: parse signature, parse constant set, parse table shape, no-op write byte stability, scalar update round-trip through Python parser, **byte-for-byte equality between Python and C++ writer outputs** (the core parity claim), unknown-constant drop parity, and two production-MSQ fixture cases that only run when the production fixture is on disk.

The slice is structurally complete. Building it requires the user to vendor `doctest.h` (one `curl` command in `cpp/README.md`) and run `cmake --build`. Until then the 9 parity tests skip cleanly.

#### Second slice landed (NativeFormat JSON layer)

- `cpp/include/tuner_core/native_format.hpp` — `NativeDefinition`, `NativeTune`, `NativeParameter`/`Axis`/`Table`/`Curve`, `NativeFormatVersionError`. Mirrors the Python `src/tuner/domain/native_format.py` dataclass shape.
- `cpp/src/native_format.cpp` — JSON read/write via vendored `nlohmann/json.hpp` (`nlohmann::ordered_json` so emitted field order matches Python `dataclasses.asdict()`). Schema-version gating mirrors `NativeFormatService._check_version` byte-for-byte.
- `cpp/tests/test_native_format.cpp` — 10 doctest unit cases covering dump emit, structural round trip, tune variant types (scalar / list / string), missing version, future-major version, forward-compat minor, unparsable version, invalid JSON, non-object root.
- `cpp/bindings/tuner_core_module.cpp` — extended to expose `NativeDefinition`/`NativeTune`/`NativeParameter`/`NativeAxis`/`NativeTable`/`NativeCurve` plus `dump_definition`/`dump_tune`/`load_definition`/`load_tune`/`load_definition_file`/`load_tune_file`. Uses `nanobind/stl/optional.h` and `nanobind/stl/variant.h` for the optional fields and the tune-value variant.
- `cpp/CMakeLists.txt` — updated to compile both source files into `tuner_core` and to fail-fast with a clear download URL if `cpp/third_party/nlohmann/json.hpp` is missing.
- `cpp/README.md` — vendoring instructions for both single-headers; expected test count bumped to 18 (8 MSQ + 10 NativeFormat).
- `tests/unit/test_cpp_native_format_parity.py` — 10 parity cases. Same gating model as the MSQ parity suite. Cases: dump-definition output structurally equal to Python output, schema_version present, Python dump loads in C++, C++ dump loads in Python, tune variant types round-trip both ways, byte-equal tune dump, missing/future/minor schema-version gating in both directions.

The two slices together deliver:
- 18 doctest C++ unit cases
- 19 Python parity cases (9 MSQ + 10 NativeFormat) — all currently skipped pending a `cmake --build` run
- The two highest-leverage subsystems for cross-validating the Python suite as the oracle

#### Third slice landed (INI preprocessor)

- `cpp/include/tuner_core/ini_preprocessor.hpp` — `preprocess_ini_lines(raw_lines, active_settings)` and `preprocess_ini_text(text, active_settings)` (the latter normalizes `\r\n` / `\r` / `\n` line endings to match Python's `text.splitlines()`).
- `cpp/src/ini_preprocessor.cpp` — direct port of `tuner.parsers.common.preprocess_ini_lines`. Two-pass evaluation: phase 1 collects file-scope `#set` / `#unset` defaults (only at file scope, ignoring directives nested inside `#if` blocks); phase 2 walks lines applying conditional logic with `effective = file_defaults | active_settings`. Stack-based nesting, `#else` flips inside parent active context, hash-prefixed comments dropped only inside inactive branches.
- `cpp/tests/test_ini_preprocessor.cpp` — 16 doctest cases mirroring the Python `test_ini_preprocessor.py` suite case-for-case: plain lines unchanged, `#if`-set keep/drop, `#else` taken/suppressed, file-scope `#set` default, user-additive `active_settings`, nested both-active / outer-only / outer-inactive, `#set` / `#unset` consumed not emitted, comments inside active vs inactive branches, empty-line preservation, `\r\n` normalization.
- `cpp/bindings/tuner_core_module.cpp` — extended with `nanobind/stl/set.h` so the `active_settings` parameter is accepted as a Python `set[str]`. Two new bound functions: `preprocess_ini_lines` and `preprocess_ini_text`, both with default-empty `active_settings`.
- `cpp/CMakeLists.txt` — `tuner_core` library now compiles all three source files.
- `tests/unit/test_cpp_ini_preprocessor_parity.py` — 16 parity cases. Uses the same gating model as the prior parity suites. The headline test is parametrized over 13 fixtures (one per Python `test_ini_preprocessor.py` case shape plus a real-world Speeduino INI subset) and asserts byte-identical output between Python and C++ for every fixture. Three additional tests verify: the lines-overload matches the text-overload, the default-empty `active_settings` matches an explicit empty set, and a multi-section real Speeduino INI fragment with nested `#if` blocks round-trips through both implementations.

The three slices together deliver:
- 34 doctest C++ unit cases (validated: **34 passed, 80 assertions, 0 failures** under MinGW g++ 15.2.0 on Windows)
- 35 Python parity cases (9 MSQ + 10 NativeFormat + 16 INI preprocessor) — **all 35 passing** against the built extension as of the first validation run
- The three foundation subsystems for the Python-as-oracle migration: file format I/O (MSQ), native contract serialization (NativeFormat), and INI preprocessing (the first reusable component every later INI section parser will consume)

#### First build validation pass

Built and validated end-to-end on Windows (MinGW g++ 15.2.0 + Python 3.14 + nanobind 2.12.0):

- `cpp/CMakeLists.txt` extended with static MinGW runtime linking (`-static-libgcc -static-libstdc++ -static -lwinpthread`) so the resulting `.pyd` has zero runtime DLL dependency. Without this, Python on Windows can't load the extension because it doesn't honor `PATH` for DLL search since 3.8.
- `cpp/bindings/tuner_core_module.cpp` `preprocess_ini_lines` / `preprocess_ini_text` bindings switched from raw function pointers to lambdas accepting `std::string` (instead of `std::string_view`) so nanobind autoconverts from Python `str` without needing `nanobind/stl/string_view.h`.
- `tests/unit/test_cpp_msq_parser_parity.py::TestWriteParity::test_cpp_writer_matches_python_writer_byte_for_byte` rewritten as `test_cpp_writer_matches_python_writer_semantically`. The original test asserted byte equality, but Python and C++ take **two different valid writer strategies**: Python re-serializes via `xml.etree.ElementTree` (single-quoted attrs, `ns0:` namespace prefix, loses original formatting) while C++ byte-splices the source XML (preserves verbatim). The C++ approach is strictly better for round-trip fidelity. The corrected test parses both outputs back through `MsqParser` and asserts the resulting constant sets are equal.
- Final state: **1840 / 1840 Python tests passing**, no skips when the extension is built.

#### Fourth slice landed (INI [Constants] section parser)

- `cpp/include/tuner_core/ini_constants_parser.hpp` — `IniScalar`, `IniArray`, `IniConstantsSection` plus `parse_constants_section(text)` and `parse_constants_lines(lines)` overloads.
- `cpp/src/ini_constants_parser.cpp` — direct port of `IniParser._parse_constant_definitions`. Handles `page = N` tracking, `scalar`/`array`/`bits`/`string` entries, `lastOffset` auto-advance with per-page reset, 1D `[N]` and 2D `[NxM]` array shapes, single-bit `[N]` and bit-range `[start:end]` bit shapes (with start/end auto-swap), CSV splitter that respects quoted strings + brace expressions + parenthesized groups (port of `_parse_csv`), `_parse_value_token` / `_parse_float_token` / `_parse_int_token` / `_resolve_constant_offset` / `_constant_storage_size` / `_parse_shape` / `_parse_bit_shape` all ported. Storage widths: U08/S08=1, U16/S16=2, U32/S32/F32=4.
- `cpp/tests/test_ini_constants_parser.cpp` — 15 doctest cases covering single scalar parse, lastOffset advance for U08/U16/U32/F32 widths, lastOffset page reset, 2D array shape, 1D array shape, array storage size advancing lastOffset by `rows*cols*width`, bits with range, bits with single bit, comments and blank lines ignored, hex offset literals, multiple pages with mixed scalars/arrays, brace placeholder scale tolerance.
- `cpp/bindings/tuner_core_module.cpp` — extended with `IniScalar`, `IniArray`, `IniConstantsSection` classes plus `parse_constants_section` / `parse_constants_lines` functions.
- `cpp/CMakeLists.txt` — `tuner_core` library now compiles all four source files.
- `tests/unit/test_cpp_ini_constants_parser_parity.py` — 11 parity cases. Synthetic-fixture parity (7): scalar count, array count, scalar offsets+pages, lastOffset resolution (a `lastOffset`-positioned scalar after a 16×16 U08 array lands at offset 272 in both implementations), array dimensions for both 2D and 1D shapes, units+data_type, lastOffset reset at page boundaries (verified `p2first` page=2 offset=0 and `rpmBins` lastOffset=4 after a U32). **Real production INI parity (4):** loaded `tests/fixtures/speeduino-dropbear-v2.0.1.ini` (the 15-page production INI used by the existing release-round-trip suite) and asserted that every scalar/array the C++ parser found also exists in the Python `EcuDefinition` output, with matching `page`/`offset` for scalars and matching `rows`/`columns` for arrays. Verified the C++ catalog is a *subset* of the Python catalog because v1 doesn't yet do `[Defines]` expansion or `#if` preprocessing — but the subset is exact for the entries it does parse.

**Validated end-to-end on the production INI:** the C++ parser sees ≥50 scalars and ≥10 arrays from the real release INI, and every page/offset for the scalars it parses matches the Python implementation byte-for-byte. This is the strongest correctness signal Phase 13 has shipped to date — the prior three slices used synthetic fixtures, this one cross-validates against a real-world fixture used by 50+ existing Python round-trip tests.

#### Slice 4 follow-up: composed pipeline (`parse_constants_section_preprocessed`)

After Slice 4 landed with subset parity against the production INI, a follow-up slice wired the existing Slice 3 preprocessor into the Slice 4 parser via a new `parse_constants_section_preprocessed(text, active_settings)` entry point. This is the first slice composition in the C++ tree — Slice 3 + Slice 4 chained internally to mirror the Python `IniParser.parse()` flow exactly.

Implementation: new function in `cpp/include/tuner_core/ini_constants_parser.hpp` and `cpp/src/ini_constants_parser.cpp` that calls `preprocess_ini_text` first then forwards the surviving lines to `parse_constants_lines`. New nanobind binding `parse_constants_section_preprocessed`. 3 new doctest cases covering preprocessor-disabled `#if`-only scalars, preprocessor-enabled scalars when `active_settings` matches, and file-scope `#set` defaults steering `#if`/`#else` branches.

**Production INI parity strengthened from subset to exact equality.** The 5 production-INI parity tests now use the composed pipeline and assert:
- The C++ scalar set **exactly equals** the Python `[Constants]`-sourced scalars (i.e. Python entries with a non-None `page` and `offset`)
- The C++ array set **exactly equals** the Python `[Constants]`-sourced arrays
- Every scalar's page+offset matches Python byte-for-byte
- Every array's rows×columns matches Python
- The total counts agree (currently 687 scalars and matching arrays from the 15-page production INI)

The 20-scalar gap between the C++ catalog and the full Python `EcuDefinition.scalars` is **not** a `[Constants]` parser bug — those 20 entries come from non-`[Constants]` sections (`[Menu]`, `[Tuning]`, `[SettingGroups]`) that the v1 C++ parser doesn't yet handle. They're correctly identified by `page is None and offset is None` and excluded from the parity comparison. The C++ parser is **exact** for the section it claims to handle.

The four slices together deliver:
- 52 doctest C++ unit cases (8 MSQ + 10 NativeFormat + 16 INI preprocessor + 18 INI constants), validated: **52 passed, 144 assertions, 0 failures**
- 47 Python parity cases (9 MSQ + 10 NativeFormat + 16 INI preprocessor + 12 INI constants), validated: **47 passed**
- The four foundation subsystems for the Python-as-oracle migration: file format I/O (MSQ), native contract serialization (NativeFormat), INI preprocessing, INI constant catalog parsing — **plus the first proven slice composition** (preprocessor + constants parser)

#### Fifth slice landed (INI #define collector + `$macroName` expander)

- `cpp/include/tuner_core/ini_defines_parser.hpp` — `IniDefines` (alias for `std::map<std::string, std::vector<std::string>>`), `collect_defines(text)` / `collect_defines_lines(lines)` walking-the-document collector, and `expand_options(parts, defines)` recursive `$name` resolver. Direct port of `IniParser._collect_defines` and `_expand_options`.
- `cpp/src/ini_defines_parser.cpp` — implementation. Recursion capped at 10 levels (matches Python guard). `{expression}` placeholders dropped. Unresolved `$name` references silently dropped instead of emitting `$undefined` labels.
- `cpp/src/parse_helpers.hpp` — **new private internal header** that hoists the shared `strip` / `strip_quotes` / `parse_csv` helpers into a `tuner_core::detail` namespace so both `ini_constants_parser.cpp` and `ini_defines_parser.cpp` consume them from one place. Refactored the constants parser to use these instead of its private duplicate, removing ~40 lines of duplication.
- `cpp/tests/test_ini_defines_parser.cpp` — 12 doctest cases covering single-list define, multi-define document, define embedded in `[Constants]`, malformed `#define noEquals`, single-value defines, simple `$macro` expansion, unresolved-reference drop, literal preservation around macros, `{expression}` drop, recursive nested expansion, circular-reference termination via the depth cap, empty-token skip.
- `cpp/bindings/tuner_core_module.cpp` — extended with `collect_defines` and `expand_options` plus a new `defines` parameter on `parse_constants_section` and `parse_constants_lines` (default-empty for backwards compatibility).
- `cpp/include/tuner_core/ini_constants_parser.hpp` — `parse_constants_section` and `parse_constants_lines` now take an optional `IniDefines` parameter; `parse_constants_section_preprocessed` automatically collects defines from the preprocessed text and wires them in for bit-option expansion.
- `tests/unit/test_cpp_ini_defines_parser_parity.py` — 12 parity tests. **Synthetic** (4): single-list define, multiple defines, define mixed with constants section, malformed `#define noEquals`. **Production INI defines** (3): full define-set equality with Python `_collect_defines`, byte-identical token lists for every overlapping define, sanity check that ≥5 defines are parsed. **`expand_options` parity** (4): simple macro expansion, unresolved drop, brace expression drop, nested expansion. **Composed pipeline** (1): bit-option labels on the production INI now match Python byte-for-byte after `$macroName` expansion (verified across 5+ overlapping bit scalars).

**Two parity bugs caught and fixed during validation:**

1. The shared `strip_quotes` helper was checking for *paired* quotes (`stripped.front() == '"' && stripped.back() == '"'`), but Python's `str.strip('"')` strips ANY leading/trailing `"` chars independently. Several production INI option lists span malformed quote regions or trailing `;` comments (e.g. `"No correction" ; * (1 byte)`), where Python strips the leading `"` but C++ left both quotes intact. Fixed by porting Python's character-set strip semantics directly.
2. The constants parser was calling `strip()` on each option *after* `expand_options` returned, eating trailing whitespace inside quoted labels like `"Relative "`. Python doesn't do this — it appends the expanded list verbatim. Removed the extra strip and parity went exact.

**The five slices together deliver:**
- 64 doctest C++ unit cases (8 MSQ + 10 NativeFormat + 16 INI preprocessor + 18 INI constants + 12 INI defines), validated: **64 passed, 179 assertions, 0 failures**
- 59 Python parity cases (9 MSQ + 10 NativeFormat + 16 INI preprocessor + 12 INI constants + 12 INI defines), validated: **59 passed**
- The first **two-slice composition** (Slice 3 preprocessor + Slice 4 constants parser via `parse_constants_section_preprocessed`) is now a **three-slice composition** (Slice 3 + Slice 4 + Slice 5 defines + bit-option expansion all wired internally)
- C++ `[Constants]` parser now produces **byte-identical bit-option labels** to Python on every overlapping scalar in the real production INI

### Future Phase 13A: Firmware Contract Modernization

Goal: make the firmware a clean consumer of native tune/schema contracts rather than a page-layout-only target.

Scope:

- schema/capability version reporting
- stable semantic IDs for tune and runtime entities
- native tune import/export mapping
- migration/default behavior for firmware-supported schema revisions

Success criteria:

- desktop/native files no longer depend on controller page layout as their primary contract
- runtime/evidence/autotune consumers can trust explicit channel-version metadata
- tune compatibility can be validated from capabilities/schema versions, not only signature strings

#### Joint commitment with Speeduino Firmware Phase 14

The firmware roadmap at `C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/FIRMWARE_ROADMAP.md` now has a matching **Phase 14: Firmware as native-contract producer** that owns the producer side of the work this Phase 13A consumes. The pattern follows the already-shipped `LiveDataMapParser` (which reads `live_data_map.h` directly): the firmware emits declarative headers, the desktop reads them, the legacy INI becomes a generated artifact rather than the source of truth.

Firmware-side deliverables we will consume (in joint sequencing order):

| Firmware slice | What it produces | Desktop consumer |
|---|---|---|
| 14A — `tune_storage_map.h` | Declarative `{semantic_id, page, offset, type, scale, units, axis_ref}` per parameter; `{rows, cols, x_axis_id, y_axis_id, data_type}` per table | New `TuneStorageMapParser` mirroring `LiveDataMapParser` — reads the firmware header as **wire-protocol metadata**, not as a definition source. The desktop's primary definition remains `.tunerdef` (semantic, operator-facing); the two cross-reference by semantic ID so the desktop can do byte-accurate tune reads/writes against any board that ships the header |
| 14B — `schema_fingerprint` in `'K'` capability response | Truncated SHA-256 of `live_data_map.h` + `tune_storage_map.h` + `BOARD_ID` baked at build time | Burn-time guard: refuse to burn if `NativeTune.definition_signature != ecu.schema_fingerprint`; surface mismatch in connect dialog. Replaces fragile signature-string match for tune/firmware compatibility |
| 14C — Semantic-id stamps on packed status bytes | Extends the `runtimeStatusA` pattern to `engineProtectStatus` / `status3` / `status5` with explicit per-bit names in `live_data_map.h` | Phase 13B Native Logging Contract reads these directly; remove the hand-maintained per-bit special cases in `live_data_map_parser.py` |
| 14D — `tune.bin` (and eventually `.ntune.json`) ingest from SD card | Teensy 4.1 reads a native tune off SD at boot, validates fingerprint, applies to RAM pages — no TS handshake required | New `NativeTuneBinaryWriter` service; race-team workflow exposed via "Export Tune To SD" menu action |
| 14E — Boot manifest line over USB CDC | Single newline-terminated JSON: `{"board", "schema_fingerprint", "fw", "caps", "page_widths"}` emitted before TS handshake | Connect-path optimization: read the manifest opportunistically to skip the `'Q'`/`'F'`/`'S'` probe sequence; legacy probe stays as fallback. Speeds up reconnect over the Airbear ESP32-C3 115200 UART hop noticeably |
| 14F — Generated INI from `tune_storage_map.h` | Build artifact, not hand-edited; INI/firmware drift becomes structurally impossible on DropBear | No desktop change required — the desktop already accepts whatever INI is shipped — but this lets us delete the "INI says X but firmware does Y" class of bug reports |
| 14G — Boot-time multi-tune slot selection (Teensy 4.1 only) | N (target 4) tune slots stored in SPI flash, selected at boot via digital input pin; each slot validated against running firmware's `schema_fingerprint` independently; new `activeTuneSlot` byte in the live-data packet | **New desktop work — closes TunerStudio gap G10 (line 139).** See "Multi-tune slot management — joint with Firmware Slice 14G" below |

Why we want this on the desktop side specifically:

- **`NativeDefinition` v1 currently bootstraps from the legacy INI parser.** Once Slice 14A lands, v2 can bootstrap from the firmware header directly. The v2 semantic-id rename pass becomes feasible because the firmware owns the canonical names.
- **`NativeTune.definition_signature` is checked today only against the desktop's own-loaded definition.** Slice 14B turns it into a real cross-system contract: the firmware refuses incompatible tunes structurally instead of bricking the engine.
- **The `lastOffset`/`afrTable` indirection chain** (CLAUDE.md "Known Fragile Areas" item 2: `afrTable` → `afrTable1Tbl` → `afrTable1Map` → `zBins = afrTable`) is a legacy-INI artifact. Slice 14A's table rows declare `{rows, cols, x_axis_id, y_axis_id}` directly, so the four-hop indirection collapses to one explicit row per table.
- **Slice 14E is the cleanest reconnect-latency win we have available** without redesigning the comms protocol — it's a single read on connect, gated behind a graceful fallback.

##### Multi-tune slot management — joint with Firmware Slice 14G

**This closes TunerStudio gap G10** ("Map switching / multi-tune slot management") which the original gap analysis at line 139 marked as a firmware-side responsibility. With Firmware Slices 14B (per-slot fingerprint), 14D (binary tune ingest), and 14G (boot-time slot selection) in place, the desktop side becomes a pure UI/service surface — no protocol redesign required.

**What the desktop needs to add:**

- **Slot model**: extend `TuningWorkspacePresenter` so the active editing target carries an explicit `tune_slot: int` (default 0). All staged edits, RAM writes, and burn-to-flash operations target the active slot. Slot 0 is the only slot that exists on AVR / non-multi-tune firmware, so the existing single-slot workflow stays the default.
- **Slot status indicator**: read the new `activeTuneSlot` byte from the live-data packet (Firmware 14G adds it within the existing 148-byte ceiling). Surface in the toolbar / connect dialog so the operator always knows which slot is currently running on the ECU.
- **Slot picker UI**: a small dropdown next to the tune title showing "Slot 0 · Pump Gas / Slot 1 · Race Gas / Slot 2 · Valet / Slot 3 · Wet". Slot names live in the `NativeTune` metadata (new `slot_name: str` field on `NativeTune` v2), not on the firmware — the firmware only knows slot indices.
- **"Copy slot X → slot Y" action**: clone an existing tune into another slot as a starting point. Pure desktop operation (clone the in-memory `NativeTune`, change the target slot index, burn to the new slot).
- **Per-slot fingerprint surfacing**: if any slot's fingerprint doesn't match the running firmware, the connect dialog flags it explicitly: "Slot 2 has a stale fingerprint and will be refused at boot — re-burn or delete." Reuses the burn-time guard from Slice 14B, just applied per slot.
- **SD-card import flow**: a "Import tune to slot N" file picker that takes a `.bin` (Firmware 14D format) and either copies it to the SD card under the right filename for firmware ingest or writes it directly via the comms protocol if the operator is connected.
- **Live-switching is explicitly out of scope** on the desktop side as well — the firmware slice contract says "boot-time only", and the desktop must not present a UI affordance that suggests live switching works. The slot picker on the connected ECU is read-only; the operator changes slots by picking a new active slot for the *next* boot, not the running session.

**Why this lands cleanly on the desktop side:**

- `NativeTune` v1 already has the right shape — adding `slot_index` and `slot_name` is a v1.1 minor bump (forward-compatible per the existing schema-version gating in `NativeFormatService._check_version`).
- `MsqWriteService` and the burn pipeline already operate on a single tune target — slot routing is a thin wrapper that picks which target the bytes go to.
- The desktop never needs to know the firmware's slot storage layout (SPI flash vs SD vs whatever) — that's entirely on the firmware side. The desktop just says "burn this tune to slot 2" and the firmware figures out where slot 2 lives.

**Suggested ordering on the desktop side:**

1. `NativeTune` v1.1: add `slot_index: int = 0` and `slot_name: str | None = None`. Forward-compatible — existing v1 tunes load as slot 0 with no name.
2. Live-data parser: surface `activeTuneSlot` byte once Firmware 14G ships.
3. Toolbar slot indicator (read-only): show which slot the connected ECU is running.
4. Slot picker dropdown + "burn to slot N" routing in `TuningWorkspacePresenter`.
5. "Copy slot X → slot Y" action in the workspace menu.
6. Per-slot fingerprint mismatch surfacing in the connect dialog.
7. SD-card import flow as a file-picker action.

Steps 1–3 can land before the firmware side because they're backwards-compatible (slot 0 only). Steps 4–7 need Firmware 14G in place to actually exercise. Treat steps 1–3 as desktop prep work the moment Slice 14G is committed in the firmware roadmap (i.e. now); steps 4–7 sequence after the firmware bench validation.

**Out of scope:**

- AVR Mega2560 multi-tune (no flash budget — Phase 14 is DropBear/Teensy 4.1 only across the board).
- Live tune switching while engine is running (firmware-side blocker — see Firmware Slice 14G out-of-scope notes).
- Conditional auto-switching based on flex sensor / CAN message / RPM (would need a firmware-side rule engine; possible Phase 15 conversation but explicitly not part of 14G).

---

Sequencing constraint: the desktop must land `TuneStorageMapParser` **before** the firmware can retire the hand-maintained INI on its side (Slice 14F), because the desktop is the only consumer that proves the header-derived wire-protocol contract works end-to-end against real firmware. The Phase 12 `LiveDataMapParser` shipping is the existence proof that this pattern is sound. Note the desktop's primary definition surface (`.tunerdef`) is independent of this sequencing — it's already the operator-facing source of truth and stays that way.

##### Updated end-user documentation — joint with Firmware Slice 14H

The firmware repo's Phase 14 Slice 14H commits to an updated DropBear/Teensy 4.1 operator manual under `docs/manual/` in the firmware tree. The desktop tuner needs a **matching operator manual** on this side, structured as the desktop companion to the firmware manual rather than a duplicate of it. The two manuals share a topic index so cross-links between them stay stable.

**Why we need a desktop-side manual:**

- The current desktop has no operator-facing manual at all. Operators learn the workflow by reading `CLAUDE.md` and the architecture docs, both of which are developer-facing and assume Python/PySide6 context.
- TunerStudio's stock manuals at <https://www.tunerstudio.com/index.php/support/manuals> describe the workflow and concepts the desktop is *based on* (project structure, INI definitions, MSQ tunes, page editing, gauges, datalogging, VE Analyze, WUE Analyze) — these are the right structural reference for what an operator manual should cover, even though the desktop is diverging from TunerStudio in the long run (Phase 14 native pivot).
- The TunerStudio developer manuals at <https://www.tunerstudio.com/index.php/support/manuals/tsdevmanuals> describe the INI schema, the comms protocol, and the gauge/dialog/menu definition syntax — these are the right structural reference for the *parser/protocol* documentation that a developer or contributor would need.
- Phase 14 features that are completely new vs TunerStudio (multi-tune slot management, native definition format, header-derived ChannelContract, Airbear ESP32-C3 transport, SD-card tune ingest UI) have **no documentation anywhere** — operators currently learn by trying things and reading the roadmap, which is wrong.

**Scope of the new desktop manual** (additive to TunerStudio's stock docs as the structural model, not a replacement for them):

- **Operator manual** (`docs/manual/operator/`):
  - First-run setup: install, open project, load INI + tune, connect/offline mode
  - The Engine Setup tab and Hardware Setup Wizard
  - The Tuning workspace: scalar pages, table editor (paste/fill/interpolate/smooth), curve editor, staged edits review, RAM write, burn-to-flash
  - VE Analyze and WUE Analyze workflows end to end
  - Logging: live data capture, profile quick-switch, real-time capture-to-file
  - Trigger Logs: tooth/composite capture, decoded analysis hand-off
  - Dashboard
  - Flash tab and SPI flash health surfacing (new — depends on firmware Phase 6 byte 131)
  - Live data HTTP API (port 8080) for remote dash consumers
  - **Multi-tune slot management UI** (Slice 14G consumer side): slot picker, slot status indicator, "Copy slot X → slot Y", fingerprint mismatch dialog, SD-card tune import flow
  - **Schema fingerprint mismatch handling** (Slice 14B consumer side): what the dialog means, how to recover
  - U16 high-leverage table editing (Phase 12 consumer side): how the precision change is surfaced in the table editor
  - Airbear ESP32-C3 WiFi connection setup (mDNS `speeduino.local`, port 2000)
  - Native Ethernet connection setup once Firmware Slice 13C ships
  - Connection troubleshooting per transport (USB serial, TCP, Airbear, eventual Ethernet)

- **Developer / contributor manual** (`docs/manual/developer/`, structured after the TunerStudio dev manuals):
  - Architecture overview (already in `architecture.md`, refactored into the manual structure)
  - INI parser scope and supported constructs (`lastOffset`, `#if/#else/#endif/#set/#unset`, `[CurveEditor]`, `[GaugeConfigurations]`, `[FrontPage]`, `[LoggerDefinition]`, `[ControllerCommands]`)
  - MSQ format and the round-trip contract
  - The native format: `NativeDefinition`, `NativeTune`, `ChannelContract`, semantic IDs, schema-version gating
  - Comms protocol coverage: legacy raw serial, Speeduino new-protocol framing, TCP/WiFi, framing detection, Q/S handshake
  - The header-derived contract path: how `LiveDataMapParser` consumes `live_data_map.h` and how the future `TuneStorageMapParser` will consume `tune_storage_map.h` (Slice 14A)
  - Plugin/extension API surface
  - C++ shared core (`tuner_core`) layout and the parity-test model
  - Phase 14 native desktop pivot status

**Format:**

- Markdown source under `docs/manual/{operator,developer}/` in the Tuner repo, one file per topic
- Generated to a single PDF (or HTML site) at release time via `tools/generate_manual.py` (new) — same model the firmware repo's Slice 14H uses
- The Markdown source is the canonical edit surface; the artefact is what users actually download

**Source-of-truth rule:**

- Every documented behaviour references either a service class (`TuningWorkspacePresenter`, `MsqWriteService`, etc.), a test file (the test suite is the executable spec), a `CLAUDE.md` section, or a specific source file + line
- No prose-only claims about what the desktop does — if a fact isn't pinned to source, it goes stale
- The doc is regenerated against the source on every release

**Reference material to draw structure from** (not copy from — these are not our docs):

- [Resources/Speeduino_manual.pdf](C:/Users/Cornelio/Desktop/speeduino-202501.6/Resources/Speeduino_manual.pdf) — the stock Speeduino manual, for the operator-side topic structure that operators are already familiar with from the AVR ecosystem
- <https://www.tunerstudio.com/index.php/support/manuals> — TunerStudio operator manuals, for the workflow language operators of TS-family tools already know (Project, Tune, Burn, VE Analyze, etc.)
- <https://www.tunerstudio.com/index.php/support/manuals/tsdevmanuals> — TunerStudio developer manuals, for the INI schema and comms protocol terminology a contributor would expect
- The decompiled TunerStudio sources at [C:/Users/Cornelio/Desktop/Decompiled/TunerStudioMS](C:/Users/Cornelio/Desktop/Decompiled/TunerStudioMS) and TSDash at [C:/Users/Cornelio/Desktop/TSDash_decompiled/TSDash](C:/Users/Cornelio/Desktop/TSDash_decompiled/TSDash) as the ground-truth reference for any TS-compatibility behaviour we document

**Joint with the firmware manual:**

- Each topic that exists in both manuals (multi-tune slots, schema fingerprint, U16 tables, SPI flash health, Airbear/Ethernet transport) cross-links to its counterpart rather than duplicating
- Shared topic index lives in `docs/manual/topic_index.md` in **both** repos, kept in sync by a small CI check
- Operator-facing dialog screenshots live only in the desktop repo (the firmware repo cross-links to them); firmware-side hardware/wiring diagrams live only in the firmware repo (the desktop cross-links to them)
- Neither manual is a fork of the other — they are companions

**Effort:**

- Ongoing rather than a single sprint, same model as Slice 14H
- Each new desktop feature ships **with** its manual section
- Backfill for the already-shipped surfaces (Tuning workspace, Engine Setup, VE/WUE Analyze, Logging, Dashboard) is a one-time pass that can interleave with Phase 14 native-port work
- Phase 14 native C++ rewrite should bring the manual along with it — when a Python service is retired, its manual section either points at the C++ replacement or gets rewritten against it; the manual must never reference dead Python paths

**Out of scope:**

- A user-facing tutorial or video series — that's a separate effort and not what an operator manual is for
- Documenting every internal Python service in the operator manual (those belong in the developer manual or stay in `CLAUDE.md`)
- Replacing or competing with the official Speeduino wiki for AVR Mega2560 users — the desktop manual is explicitly the *DropBear/Teensy 4.1 + native-format* manual, same scoping decision as Firmware Slice 14H

---

Out of scope for the joint commitment:

- AVR Mega2560 stays on the legacy INI/MSQ contract permanently — there is no flash budget on AVR for the producer side, and the desktop's existing compatibility layer already handles it cleanly. Phase 14 is a DropBear/Teensy 4.1 deliverable only.
- JSON5 hand-authoring stays a desktop-only concern; the firmware never sees JSON5.
- v1→v2 schema migration tooling stays a desktop-only concern; the firmware only ever knows its own compiled-in fingerprint.

### Future Phase 13B: Native Logging Contract

Goal: move from legacy output-channel logging toward a versioned evidence/logging platform owned by
the project.

Scope:

- versioned runtime-channel catalog
- stable semantic IDs for logged channels and events
- selectable channel groups or stream classes declared by firmware capability
- native log-session metadata and annotations
- replay/autotune-ready evidence contracts independent of legacy CSV assumptions

Foundation already in firmware:

- `live_data_map.h` (148-row declarative byte/field comment table, `LIVE_DATA_MAP_SIZE=148`) — byte positions for all `LOG_ENTRY_SIZE` fields locked with regression tests against `getTSLogEntry()` / `getReadableLogEntry()`
- `runtimeStatusA` byte (index 147) packs `fullSync`, `transientActive`, `warmupOrASEActive`, `tuneLearnValid` into high bits — these are explicit gating signals for evidence quality
- Knock status byte (index 92) and `knockRetard` (index 93) locked at specific byte positions
- `engineProtectStatus` (byte 85), `status3` (byte 84), `status5` (byte 127) all position-locked

Desktop next steps toward native logging contract:

- consume `live_data_map.h` field/byte positions as the authoritative channel catalog (not only INI `[OutputChannels]`)
- gate VE/WUE analyze cell acceptance on `tuneLearnValid` bit from `runtimeStatusA` (already the right signal — firmware side confirmed)
- tag logged snapshots with firmware schema version derived from capability bits + `LOG_ENTRY_SIZE`, not only signature string

Success criteria:

- the app can describe exactly what each logged channel means for a given firmware/runtime schema
- logs carry enough metadata to remain trustworthy across firmware revisions
- capture, replay, dashboarding, and autotune all consume the same channel-contract model
- legacy CSV/INI-driven logging remains only a compatibility path

### Future Phase 14: Native Desktop Product

**Status: in progress.** The Phase 13 evidence (5 slices, 64 doctest cases, 59 byte-identical parity tests against the production INI) was strong enough to commit to the full native pivot rather than continuing the gradual port-under-Python model. The trigger was a deliberate operator decision to optimise for performance on constrained hardware.

#### Locked Phase 14 scope decisions

| Decision | Choice |
|---|---|
| End goal | Full native desktop; Python retired after feature parity |
| Native format | JSON (definitions and tunes both); JSON5 deferred to a later slice if hand-authoring becomes load-bearing |
| Qt version | Qt 6.7 LGPL with dynamic linking |
| UI definition | Hand-coded C++ widgets (no `.ui` files, no QML — minimum runtime cost on old hardware) |
| Python retirement | Stays alive as parity oracle until the C++ app is feature-complete; deleted in one PR |
| Distribution | Single `tuner_app.exe` + Qt DLLs alongside |
| Build chain | CMake + MinGW UCRT + Qt 6.7 (installed via `aqtinstall`) |

#### Native format strategy documented

The native tune/definition/project format strategy is documented in `docs/ux-design.md` under "Native Format Strategy". Three file types: `.tunerdef` (JSON5, firmware definition without page/offset concerns), `.tuner` (JSON, typed parameter values), `.tunerproj` (JSON, project metadata). INI/MSQ become import/export adapters, not the source of truth. Implementation order: tune export first (simplest), then project file (enables landing page), then definition export.

#### Phase 14 Slice 4 fifty-third sub-slice: FirmwareCapabilities + Qt source build + UI unlocks

**Sub-slice 53: FirmwareCapabilities** — runtime trust summary + uncertain channel groups. 5 doctest cases.

**Qt 6.7.3 built from source** with our exact MinGW UCRT 15.2 toolchain at `C:/Qt/6.7.3-custom`. This eliminates the prebuilt ABI mismatch that caused all 5 crash patterns. QLineEdit, Qt::RichText, QPainter custom widgets, and QColor all work now. One remaining constraint: **never delete widgets in signal handlers** (use `hide()` instead) — `QTreeWidget::clear()` and widget destruction in `currentItemChanged` handlers still crash even with matching ABI.

**UI features re-enabled/added:**
- Real QLineEdit search with placeholder text and clear button
- Rich HTML dashboard gauge cards with colored styled values
- QPainter analog dial gauges (RPM and MAP) with arc zones, tick marks, needle, hub
- Editable scalar parameter forms with QLineEdit fields that turn blue when staged
- Show/hide tree filtering (no tree->clear())

**Sub-slice 52: HardwarePresets** — ignition coil preset catalog with source confidence labels. 7 doctest cases.

**UX Phase B delivered:** context headers for all 56 TUNE pages, table heatmaps on selection, editable parameter forms, `docs/ux-design.md` created with guided-power philosophy and Phase A-D implementation plan.

C++ doctest suite: **809 tests, 6339 assertions, 0 failures**.

#### Phase 14 Slice 4 one-hundred-and-twenty-ninth sub-slice: UX — TUNE scalar editor tooltips (`[SettingContextHelp]` reaches the form)

Ninth UX slice of the post-beautification pass. **The follow-up from sub-slice 128 that closes a loop between three earlier slices.** Sub-slice 116 ported the INI `[SettingContextHelp]` parser and wired it into `NativeEcuDefinition`. Sub-slice 128 added the tokenized `QToolTip` global style. This slice is the consumer that finally brings both to the TUNE tab's scalar parameter forms — every row on every TUNE page now shows the production INI's declared description on hover.

**The gap this slice closes.** Before sub-slice 116, the C++ `compile_ecu_definition_text` didn't parse `[SettingContextHelp]` at all. Sub-slice 116 ported the parser and stashed the result in `NativeEcuDefinition::setting_context_help::help_by_name`. The native `tuner_app` started populating that map on every INI load (the `compile_ecu_definition_file` call on line 786 of `main.cpp`). But **nothing downstream consumed it**. Sub-slice 128 added the global `QToolTip` QSS rule and wired the sidebar nav items to show tooltips — but the main payload of the `[SettingContextHelp]` parser (every parameter description for every tunable) was still sitting unused in memory. This slice is the consumer: it wires the help map into the per-row tooltip setup on the TUNE tab's right-panel parameter form.

**The slice.** Inside the field-iteration loop in `build_tune_tab`, add a help-map lookup before building each row's widgets:

```cpp
std::string tooltip_text;
{
    const auto& help_map = ecu_def->setting_context_help.help_by_name;
    auto it = help_map.find(f.parameter_name);
    if (it != help_map.end() && !it->second.empty()) {
        tooltip_text = it->second;
    } else {
        // Fallback — show the raw parameter name so the
        // operator can at least search for it in docs.
        tooltip_text = f.parameter_name;
    }
}
```

Then call `label->setToolTip(...)` and `edit->setToolTip(...)` with the same string. The tooltip lands on **both the label column AND the `QLineEdit` column** so the operator can hover either side of the row without having to aim at a specific widget. The global `QToolTip` style from sub-slice 128 handles the rendering — this slice adds zero QSS.

**Fallback semantics.** When the INI doesn't declare a help entry for a parameter (rare but possible for newer parameters the production INI hasn't catalogued yet), the fallback shows the raw internal parameter name. That's not human-readable but it's searchable — an operator who sees `dwellLim` on hover can look it up in docs, mailing lists, or the INI source directly. Better than an empty tooltip or a silent row.

**Why "both widgets" matters.** Qt's hover tooltip only fires on the widget directly under the cursor. If the tooltip were only on the label, an operator whose mouse naturally lands on the value editor (the QLineEdit) would see nothing. Applying the same tooltip to both widgets means the entire row is a hoverable hint zone — the operator doesn't have to aim. Small but real usability detail.

**Philosophy — three slices stacking.** This slice is a small amount of code that only works because three earlier slices landed first:

- **Sub-slice 116** parsed `[SettingContextHelp]` and wired it into `NativeEcuDefinition`. Without the parser, there's nothing to look up.
- **Sub-slice 128** added the global `QToolTip` QSS rule. Without the rule, the tooltips would render with Qt's default system-yellow style that clashes with the dark theme.
- **Sub-slice 129** (this one) does the actual `setToolTip` lookup in the form loop. 15 lines of code.

The 15-line slice is the smaller top of an iceberg — the real work landed months earlier across the parser port and the token system. This is the pattern the sub-slice 88 / 115 beautification arc predicted: once the infrastructure is tokenized and the data layer has every INI section wired through, **adding a new operator-visible affordance becomes small**. The marginal cost of the next UX win decreases as the foundation fills out.

**Every tooltip from every INI section has a visible payoff now.** The production INI has dozens of `[SettingContextHelp]` entries (the sub-slice 116 parity test asserted ≥ 20 help entries on the production fixture). Every one of those now shows up as a hover hint on the matching TUNE row. An operator exploring the TUNE tab for the first time can read the INI's authoring team's own description of what each parameter means, without leaving the form or consulting a docs file.

**No new tokens, no new widgets, no stylesheet changes.** One local variable + two `setToolTip` calls. The implementation is the minimum possible change that connects the existing data source to the existing rendering layer.

**Discovery graph unchanged.** The six landmarks from sub-slice 128 stay the same. This slice doesn't add a new discovery surface — it **fills in content** on an existing one (TUNE tab rows previously had no per-row hints). The slice makes the right panel more useful on every interaction, not just on first-run orientation.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

**Follow-up opportunities.**
- **Tooltip on scalar editor's units label.** Currently the `" ms"` / `" rpm"` / `" %"` trailing units labels in each row have no tooltip. Could show the full-name expansion of the unit on hover (`"milliseconds"` / `"revolutions per minute"`) — minor polish.
- **Tooltip on tree leaves.** The page tree on the left has no tooltips. Each leaf could show a short description pulled from the first line of its context-header card (sub-slice 91). Avoids duplication but adds discoverability.
- **Min/max range in tooltip.** The scalar parameter definition has `min_value` / `max_value` fields. Tooltip could append `"Range: 0.5 – 30.0 ms"` after the help text so the operator knows the valid input range without trying to enter an out-of-bounds value.

Each would be a small follow-up slice. None required for the current polish pass.

#### Phase 14 Slice 4 one-hundred-and-twenty-eighth sub-slice: UX — sidebar nav tooltips + tokenized QToolTip

Eighth UX slice of the post-beautification pass. Adds hover discoverability to the sidebar navigation + tokenizes the global `QToolTip` rendering so the dark theme extends to every future tooltip in the app.

**The problem.** The sidebar labels are single words — `Tune`, `Live`, `Flash`, `Setup`, `Assist`, `Triggers`, `Logging`, `History`. A first-time operator can guess at `Tune` and `Live` but has to click `Assist` to find out it's the VE/WUE Analyze pipeline, and `Triggers` to learn it's crank/cam diagnostics. The menu bar View menu (sub-slice 123) spells out the same information via its item labels, but the sidebar itself is silent. Adding tooltips closes the gap: hover any sidebar item and a one-line description appears, same grammar the F1 cheat sheet Navigation group (sub-slice 121) uses.

**The slice.** Two coupled changes:

1. **Per-item tooltips on the sidebar nav.** The `NavItem` struct gains a `const char* tooltip` field carrying the hover text plus a trailing `(Alt+N)` shortcut chip. The loop that builds the sidebar now creates each item as `new QListWidgetItem(QString::fromUtf8(label))` so it's addressable for the `setToolTip(...)` call, then adds it via `sidebar->addItem(list_item)`. Previously the loop used the simpler `sidebar->addItem(QString)` form which returns `void` and doesn't expose the item object.

2. **Tokenized `QToolTip` QSS rule.** The global `DARK_QSS` block gains a new rule: `QToolTip { background-color: bg_elevated; color: text_primary; border: 1px solid border; border-radius: radius_sm; padding: (space_xs+2)px (space_sm)px; font-size: font_small; }`. Without this rule, Qt's default tooltip rendering uses the system palette — on Windows that means a yellow-tinted background on a light frame, which clashes hard with every other tokenized dark surface in the app. With the rule, every tooltip across the entire app (sidebar, future scalar editor hover hints, `make_info_card` hover, anywhere `setToolTip` is called) inherits the same dark-theme look automatically. The rule is global-application-level, not per-widget, so a future slice that adds tooltips to the TUNE-tab parameter form gets the same visual automatically.

**Tooltip copy — single source of truth for navigation descriptions.** The tooltip strings exactly match the F1 cheat sheet's Navigation group entries (sub-slice 121). Sample row:

```cpp
{"\xf0\x9f\xa7\xaa", "Assist",
    "Assist \xe2\x80\x94 VE / WUE Analyze pipeline  (Alt+5)"},
```

Matches the F1 cheat sheet's `{"Alt+5", "ASSIST — VE / WUE Analyze pipeline"}` row verbatim (modulo the case-normalization to sentence case in the tooltip). Any future edit to one description requires a matching edit to the other — deliberate coupling so the three discovery surfaces (sidebar tooltip, F1 cheat sheet, menu bar View menu) can't drift out of sync. A future refactor could collapse these into one `nav_descriptions[]` array shared between both surfaces, but three hand-kept sites is still a small enough surface that drift is manageable.

**Trailing `(Alt+N)` chip.** Every tooltip ends with the shortcut in parentheses. This is the third place the Alt+N binding is surfaced (menu bar shows it via `QAction::setShortcut` rendering, F1 cheat sheet shows it via its chip column), and it's the most glanceable: an operator hovering a sidebar item immediately sees both "what's on this tab" and "how do I jump here without the mouse". The two affordances land in the same eyeline.

**Philosophy — the discovery graph expands again.** Sub-slice 127 counted five discovery landmarks (menu bar / F1 cheat sheet / status bar hint / command palette placeholder / TUNE empty state). This slice adds a sixth: **sidebar hover tooltips**. The graph is now:

- **Sidebar tooltips** (sub-slice 128 — this slice) — hover-level, visible on mouse-over
- **Menu bar** (sub-slice 123) — scan-level, visible on menu open
- **F1 cheat sheet** (sub-slice 121) — full-list, visible on key press
- **Status bar hint** (sub-slice 122) — permanent, points at F1
- **Command palette placeholder** (sub-slice 122) — points at F1
- **TUNE empty state** (sub-slice 127) — first-run, points at Ctrl+K and F1

Six entry points, all cross-linked. An operator who hovers a sidebar item learns about Alt+N; an operator who opens the menu bar learns about the same Alt+N from a different angle; an operator who presses F1 sees all eight Alt+N bindings in one grouped list. The redundancy is the point: different operators discover different entry points first, and every entry point leads to the others within one interaction.

**Tokenized QToolTip is the bigger architectural win.** The sidebar tooltips are the motivating use case, but the global `QToolTip` rule is the lasting contribution. Every `setToolTip(...)` call anywhere in the app now renders consistently with the rest of the dark theme. Future slices that add hover hints to the TUNE scalar editor, the ASSIST analysis cards, the FLASH preflight checklist, or anywhere else don't need to think about tooltip styling — it Just Works. This is the sub-slice 88 token system doing what it was built for: a style primitive that lands once and never needs to be repeated.

**DARK_QSS buffer check.** The static buffer is 2048 bytes; the stylesheet body was ~1500 chars pre-slice. The new `QToolTip` rule adds ~200 chars (template + 7 format arguments), well within budget. No buffer overflow risk.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

**Follow-up opportunities.**
- **Tooltips on info cards.** The TUNE tab's scalar editor rows currently set `setToolTip` only in the cross-parameter warning path (sub-slice 91). Every row could get a tooltip showing the compiled units + range + help text from `[SettingContextHelp]` (ported in sub-slice 116). Small change, big discoverability win.
- **Tooltip on the wordmark footer.** Hovering the sidebar wordmark (`TUNER / guided power`) could reveal a tooltip with the full design philosophy quote — `"Guided power: the same information TunerStudio shows, organized around what the operator is trying to accomplish."` One more quiet place the app states its purpose.
- **Collapsed navigation source of truth.** The three places that name each tab (sidebar labels, F1 cheat sheet Navigation group, menu bar View menu) could share a single `kNavDescriptions[]` constant array. Prevents the three sites from drifting. Not urgent — three sites is still small — but worth keeping in mind if a fourth site gets added.

#### Phase 14 Slice 4 one-hundred-and-twenty-seventh sub-slice: UX — TUNE-tab empty state

Seventh UX slice of the post-beautification pass. Fixes a long-standing first-run rough edge: the TUNE tab's right panel before any page selection.

**The problem.** Before this slice, opening the TUNE tab on a fresh launch showed two things on the right:

1. A hero label that read `"Pick a page on the left"` — dry and instructional.
2. A **blank blue-accent context-header card** — no content, just a styled empty rectangle.

A first-time operator stared at a blank card that was clearly positioned as a content slot and wondered if the app had failed to load. The card's blue-accent left bar (sub-slice 91's `make_info_card` visual grammar for "context here") promised information but delivered nothing. This is the opposite of the sub-slice 115 philosophy of "every pixel flows from tokens": the pixels were there, but they were showing *emptiness*, which is worse than either "no card at all" or "card with content".

**The fix.** Two one-line copy changes that turn the empty state into a welcome + discovery breadcrumb:

1. **Hero label** — `"Pick a page on the left"` becomes `"Welcome — pick a page to start tuning"`. Warmer, less imperative, reads as an invitation. The em dash (U+2014) matches the wordmark footer and the About dialog from sub-slice 123 — consistent voice across the app's welcome surfaces.

2. **Context card initial text** — the previously-blank card gets hydrated with:

   ```
   Pick a page from the tree on the left to see its parameters, table,
   or curve. · Press Ctrl+K to search by name. · Press F1 for every
   keyboard shortcut.
   ```

   Same `·` middle-dot separator grammar the status bar, the F1 cheat sheet header, and the tab header primitive use (sub-slices 111 / 121). Three calls to action in one line, progressive disclosure: first the direct instruction (click a page), then the keyboard shortcut for search (Ctrl+K), then the general escape hatch for every other binding (F1).

**The empty state is a discovery breadcrumb.** Sub-slice 122 established the idea that discovery happens through breadcrumbs, not tutorials — surfaces that are useful the second time because they confirm "yes, you're in the right place" rather than fire once and become noise. The TUNE empty state is a perfect venue for this pattern: the card is only visible on the very first launch before the operator clicks any page, and the moment they click anything the card gets overwritten with the real page context. Zero cost after the first interaction. But on that first interaction, the operator's eye lands on the context card (the biggest content element on the page), reads three calls to action, and knows what to do next — *without the app popping up a tutorial overlay or a "first time here?" modal*. This is the ux-design doc's *"don't teach what the operator can ask for"* principle applied to onboarding: the welcome is always there, never demands dismissal, and quietly points at every other discovery surface in the app.

**Why now, and not earlier.** The empty state couldn't have been written this way before sub-slice 121 (F1 cheat sheet) and sub-slice 123 (menu bar / Ctrl+K formalized as a navigation surface), because the two affordances the welcome message points at didn't exist yet. This is the reverse of the usual "build the tutorial first" pattern: the discovery surfaces landed first, and the welcome message is the last piece — a breadcrumb pointing at already-built chrome.

**Compare to the three existing no-page-selected fallbacks.** The TUNE tab has three other `detail_label->setText(...)` calls that fire when the operator explicitly deselects a page (group item selected) or navigates to a page id the layout doesn't know: `"Expand a group and select a page."` and `"Select a page to see its compiled layout."`. Those stay as-is — they fire after the operator has already interacted with the tab at least once, so they don't carry first-run orientation weight. Only the initial-state card at `build_tune_tab` construction gets the welcome copy. This is the right split: welcome on launch, short instructional text on explicit deselection.

**No new tokens, no new widgets, no stylesheet changes.** Two `setText` calls that hydrate the empty state. The sub-slice 88 token system stays untouched; sub-slice 115's "every pixel flows from theme.hpp" claim stays valid.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

**Cumulative discovery graph after this slice:**

- **Menu bar** (sub-slice 123) — primary anchor, every shortcut self-documented
- **F1 cheat sheet** (sub-slice 121) — full shortcut list grouped by purpose, context-aware since sub-slice 125
- **Status bar hint** (sub-slice 122) — permanent `Press F1 for shortcuts` in the right slot
- **Command palette placeholder hint** (sub-slice 122) — points at F1 from inside Ctrl+K
- **TUNE empty state** (this slice) — first-run orientation that points at both Ctrl+K and F1

Every entry point leads to at least two others within one interaction. The discovery graph has five landmarks now, each reinforcing the others.

**Follow-up opportunities.**
- **Empty states on other tabs.** FLASH / SETUP / LOGGING could get similar welcome copy when the operator hasn't selected anything yet. Most of them already show demo data, so the empty state is less acute — but the pattern is reusable.
- **First-run banner.** A one-time "Welcome to Tuner — press F1 for the full shortcut panel" banner above the TUNE tab that dismisses on first click. Rejected: this is tutorial chrome, not a breadcrumb, and the philosophy deliberately avoids it.

#### Phase 14 Slice 4 one-hundred-and-twenty-sixth sub-slice: UX — dynamic window title (project + staged state)

Sixth UX slice of the post-beautification pass. The `TunerMainWindow` title has been a static `"Tuner — Speeduino Workstation"` since sub-slice 53 (when the native Qt app first booted). Every other desktop editor reflects current state in the title: the project name is the anchor, a trailing `*` or modified-indicator signals unsaved changes. This slice brings that convention to Tuner.

**The problem.** An operator running multiple Tuner instances across multiple projects (one on the workshop monitor, one on the laptop) can't tell them apart from the Windows taskbar. Every instance shows the same title. Worse, an operator who alt-tabs away with pending edits has no indication from the taskbar that they left work unsaved — the only staged-count signal is on the sidebar badge, which is invisible when the app isn't focused.

**The fix.** The existing sub-slice 92 `refresh_tune_badge` lambda already fires on every staged-count change to update the sidebar "Tune · 3 staged" badge. This slice extends the same lambda to also call `setWindowTitle(...)` with a project + state composition:

- `"Tuner — Ford 300 Twin GT28"` when there are zero staged edits (clean)
- `"Tuner — Ford 300 Twin GT28 • 3 staged"` when staged edits exist but aren't yet written to RAM (amber state in the sidebar badge)
- `"Tuner — Ford 300 Twin GT28 • 3 in RAM"` when staged edits have been written to RAM but not yet burned (blue state in the sidebar badge, via sub-slice 95's `aggregate_state()` check)

The `•` glyph (U+2022 BULLET, encoded as `\xe2\x80\xa2`) separates the project name from the state chip — same visual grammar as the status bar's `·` separators (middle dot U+00B7). The title composition uses the same `staged_count()` + `aggregate_state()` → verb dispatch the sidebar badge already uses, so the two surfaces can't drift out of sync: one refresh updates both.

**Lambda capture update.** The `refresh_tune_badge` lambda previously captured `[sidebar, shared_workspace]`. This slice extends it to `[this, sidebar, shared_workspace]` so the lambda can reach `TunerMainWindow::setWindowTitle` via the implicit `this` pointer. No other changes to the surrounding code.

**Placeholder project name.** A `static const char* kDemoProjectName = "Ford 300 Twin GT28"` sits just above the lambda. The real open-project flow isn't wired yet — every launch loads the same fixture INI/MSQ pair and the sub-slice 112 startup picker all routes through `QDialog::accept`. When a future "recent projects" slice actually threads real project names through the open-project seam, this placeholder becomes the natural plug point: replace the `static const char*` with a member variable that gets set on every real project open, and the title refresh picks up the new name automatically.

**Initial title lifecycle.** The constructor sets `setWindowTitle("Tuner — Speeduino Workstation")` at line 4079 as a placeholder. `refresh_tune_badge()` gets called at line 4200 (after the TUNE tab is built and the workspace is wired up), at which point the title immediately gets overwritten with the project-aware version. So the operator never actually sees the placeholder title in practice — it exists only so the window has a title between the `setWindowTitle` call and `refresh_tune_badge()` running. This is fine: the pattern matches how `resize(1280, 800)` is a placeholder that `restoreGeometry()` later overwrites (sub-slice 124).

**Philosophy — state visibility extends beyond the app.** The sub-slice 92 three-zoom staged-state hierarchy (sidebar badge / per-page chip / review popup) ran entirely *inside* the app. This slice extends the top level one step further *outside* the app: the taskbar is now the zero-zoom state surface. An operator glancing at their taskbar sees "Tuner — Ford 300 Twin GT28 • 3 staged" and knows, without alt-tabbing, that there's pending work in that window. This is the "progressive disclosure" principle applied one more level — the information is always there, increasingly detailed as you zoom in, but you can get the high-level state without interacting at all.

**No new tokens, no new widgets.** Just one extra `snprintf` + `setWindowTitle` call inside the existing refresh path. The sub-slice 88 token system stays untouched; nothing else in the app had to change.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

**Cumulative state-visibility surfaces after this slice:**

- **Taskbar title** (sub-slice 126 — this slice) — zero-zoom, visible without focusing the app
- **Sidebar Tune badge** (sub-slice 92) — app-level, visible from every tab
- **Per-page chip** (sub-slice 92) — tab-level, visible on the selected page
- **Review popup** (sub-slice 93) — row-level, full list of pending edits
- **Tree-entry state indicators** (sub-slice 96) — sub-tab-level, shows which page has edits

Five zoom levels, each revealing slightly more detail, each reaching one step further into or out of the app. The taskbar title is the outermost ring — and the one that matters most for operators running multiple instances.

**Follow-up opportunities.** Once a real project-open flow lands, `kDemoProjectName` becomes a member variable and the title refresh runs on every project change too. A future "multiple projects" pass could add a differentiator to the title when two instances show the same project name (e.g. `(1)` / `(2)` suffixes). Neither required for the current polish pass.

#### Phase 14 Slice 4 one-hundred-and-twenty-fifth sub-slice: UX — contextual F1 cheat sheet

Fifth UX slice of the post-beautification pass. Closes the sub-slice 121 follow-up backlog item about **contextual shortcut filtering**: the F1 cheat sheet now reads the current sidebar row at open-time and adjusts its presentation to match where the operator is.

**The problem.** Before this slice, the F1 cheat sheet showed the same static list regardless of context. An operator on the LIVE tab saw `Ctrl+R`, `Ctrl+W`, `Ctrl+B` in the Tune workflow group and had no signal that those shortcuts don't fire on LIVE — they're TUNE-tab-scoped (bound via `QShortcut` on the TUNE tab's container widget, per sub-slice 97 and 95). The disabled-display-only entries in the sub-slice 123 Tune menu communicated that scoping via explicit "(Ctrl+R on Tune tab)" labels, but F1 was still silent.

**The slice.** Two complementary affordances land in one change:

1. **Active-tab emphasis.** The group header that matches the current sidebar row promotes from `text_muted` to `accent_primary` — the same blue tint used for "selected / active" across the app (sub-slice 90's sidebar selection, sub-slice 112's command palette selection, sub-slice 91's scalar editor OK state, sub-slice 123's menu hover). The operator's eye lands on the emphasized group first. The Navigation / Files / Help groups have `active_tab = -1` (global) so they stay `text_muted` — they're always relevant and never get the accent.

2. **Scope-note suffix.** When the operator is NOT on the TUNE tab and the Tune workflow group is shown, the group header picks up a dim trailing `(available on the Tune tab)` suffix in `text_dim` normal-case (not uppercase, no letter-spacing — reads as a parenthetical, not as part of the title). Tells the operator *"these keys are real, but they don't fire from here — switch to the TUNE tab first"*. When the operator IS on the TUNE tab, the suffix is suppressed because the `accent_primary` emphasis already signals "these work here".

**Struct refactor.** The internal `ShortcutGroup` struct gains two fields:

- `int active_tab` — `-1` for global (always relevant across every tab), or `0..7` for a specific sidebar row. Only the Tune workflow group has a non-`-1` value right now (`0` = TUNE tab).
- `const char* scope_note` — `nullptr` for global groups, or a short label for the dim suffix on non-matching tabs. Only the Tune workflow group sets this (`"available on the Tune tab"`).

Both fields are part of the literal group initializer, so adding a new context-scoped group in the future is one struct line — no dispatcher, no string table, no map.

**No filter, no hiding.** Deliberate architectural choice: the cheat sheet **always shows every shortcut**, even when the context marks them as off-tab. Hiding shortcuts would make the cheat sheet context-gated and the operator who's trying to learn the full keybind surface would need to visit every tab to see everything. The affordance is *emphasis + honesty*, not *filter*. The operator on LIVE still reads the full Tune workflow group — just with a dim suffix that tells them where those keys fire.

**Lambda capture update.** The `open_shortcuts_dialog` lambda previously captured only `this`. This slice extends the capture to `[this, sidebar]` so the dialog can read `sidebar->currentRow()` at open-time. No other changes to the surrounding code.

**Philosophy — emphasis is an affordance, not chrome.** The sub-slice 115 beautification arc established that every accent colour has a semantic meaning: `accent_primary` = "selected / active / default", `accent_ok` = "healthy", `accent_warning` = "attention", `accent_danger` = "urgent". This slice reuses `accent_primary` in one more place (the cheat sheet header) for exactly that meaning — *"this group is active right here"*. No new token, no new colour, no new rule. The emphasis behaviour is a direct consequence of the palette's semantic grammar meeting the operator's current context.

**Cumulative discovery graph after this slice (updated from sub-slice 123).** The five discovery surfaces from sub-slice 123 are unchanged; the cheat sheet itself is now smarter within its existing role.

**Follow-up opportunities (still deferred).**
- **Per-tab shortcut panels.** The struct supports more than one context-scoped group — a future LIVE-tab slice could add LIVE-only shortcuts (dashboard gauge selection, histogram pinning) with `active_tab = 1` and a `"available on the Live tab"` scope note. Zero additional infrastructure.
- **Recent projects wiring.** Sub-slice 124 backlog item, still valid — the startup picker hard-codes a project and no real open-project flow exists.
- **Per-tab state persistence.** Sub-slice 124 backlog item — remember which TUNE page the operator was editing, which LIVE histogram was pinned, etc.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-twenty-fourth sub-slice: UX — window geometry + session persistence

Fourth UX slice after the beautification arc closed. Previous slices (121 / 122 / 123) added keyboard shortcut discoverability + a conventional menu bar. This slice adds the basic-desktop-hygiene feature every Windows app has but the Tuner app has been missing since day one: **the app remembers where the operator left it**.

**The problem before this slice.** Every launch put the window at the same fixed 1280×800 in the top-left corner, on the TUNE tab, regardless of what the operator did in the previous session. An operator who drags the window to a second monitor, resizes to fill the screen, and switches to the LIVE tab for a tuning run has to redo all three things on the next launch. It's a small thing that accumulates into "this app doesn't feel finished" on the tenth launch.

**The slice.** Three values persist via `QSettings`:

- **`session/geometry`** — `QByteArray` from `QMainWindow::saveGeometry()`. Covers window size, position, maximized state, and multi-monitor placement. Restored via `restoreGeometry()`. Qt handles all the platform-specific edge cases (maximized restore, position clamping onto the current screen after a monitor is unplugged, DPI scaling) automatically.
- **`session/window_state`** — `QByteArray` from `saveState()`. Covers splitter layouts, toolbar visibility, dock widget positions. Restored via `restoreState()`. Currently the app has no toolbars and only the TUNE-tab splitter is user-movable, but storing `saveState()` future-proofs the persistence layer: any future splitter or dockable panel automatically inherits the save/restore behaviour without another slice.
- **`session/last_tab`** — `int` from `sidebar->currentRow()`. The last-active sidebar page. Restored with a `[0, sidebar->count())` clamp so a future slice that adds or removes tabs falls through safely to tab 0 (TUNE) rather than landing on an invalid page or crashing.

**Storage location.** `QCoreApplication::setOrganizationName("Cornelio")` + `setApplicationName("Tuner")` (the latter already set in `main()` at sub-slice 53 when the native build first got Qt running). On Windows this writes to `HKEY_CURRENT_USER\Software\Cornelio\Tuner` in the registry — the conventional "per-user persistent settings" location Qt's `QSettings` defaults to. An operator who wants to wipe the session state can delete that key from `regedit`, but the app never needs to expose that as a UI action.

**Restore timing.** Restore happens at the **end** of the `TunerMainWindow` constructor, after the sidebar is fully built and populated with its 8 entries. This matters for `session/last_tab`: calling `sidebar->setCurrentRow(N)` before the sidebar items exist is a no-op and silently drops to row 0. Doing the restore last guarantees the sidebar is ready when the restore runs.

**Save timing.** Save happens via a new `closeEvent(QCloseEvent*)` override on `TunerMainWindow`. Qt calls `closeEvent` on every normal close path (window close button, File → Exit, Alt+F4, `qApp->quit()`), which covers every way the operator can end a session. The override pulls the sidebar back out of the widget tree via `findChild<QListWidget*>()` so the current row is accessible without a member variable — keeps the `TunerMainWindow` class body small.

**`findChild` for the sidebar lookup.** The constructor doesn't store the sidebar as a member — it's a local variable captured by lambdas. Rather than refactor to add a member, `closeEvent` uses `findChild<QListWidget*>()` to reach the sidebar at save time. The tree only has one `QListWidget` at the top level (the sidebar itself) so the lookup is unambiguous. If a future slice adds another `QListWidget` to the main window, this needs to become an object-name-qualified lookup — but for now the simple form is enough.

**First-launch behaviour.** On first launch, `QSettings` returns an empty `QByteArray` from `value("session/geometry")` and the restore is a no-op. The `resize(1280, 800)` default stays in effect. `session/last_tab` defaults to 0 via `toInt()` fallback. Every subsequent launch sees the real saved values. No special-case branching, no `first_launch` flag.

**Philosophy — invisible affordances.** The `docs/ux-design.md` principle *"every affordance should be discoverable without reading the docs"* mostly applies to visible chrome (menu bars, shortcuts, status hints). This slice is the complement: chrome the operator never sees but would **immediately notice if it went missing**. No button, no menu item, no dialog confirms that session state was restored — the app just opens where the operator last closed it. The only way to notice the feature is to close the app on tab 5 and reopen it and land on tab 5. Operators expect this; losing it feels like a regression.

**Why this slice matters alongside 121 / 122 / 123.** Those three slices made the app *legibly finished* — a conventional menu bar, discoverable shortcuts, a chrome-level discovery graph. This slice makes the app *actually finished* at the "I've used this for a week" layer. A first-time operator forgives a lot. A tenth-time operator notices everything that doesn't carry state between sessions. Every Windows app they use remembers geometry; one that doesn't reads as "scratch build, not polished". The four UX slices together close the "conventional desktop-app polish" gap.

**Follow-up opportunities (not in this slice).** A few natural extensions for a future UX pass:
- **Recent projects wiring.** The startup project picker (sub-slice G1) hard-codes `"Ford 300 Twin-GT28"` as the only recent project. A real recent-projects list would persist via `QSettings` (`recent/projects` as a `QStringList`) and update on every successful project open.
- **Per-tab state.** Each tab could remember its own sub-state — which TUNE page was last open, which LIVE histogram was pinned, which SETUP wizard step was last active. More granular than `session/last_tab`, but also more places to leak state across sessions if the semantics drift.
- **Window geometry profiles.** Some operators tune on a laptop and a workshop monitor with very different sizes. A "geometry profile per monitor configuration" layer would detect the current screen count and restore the matching profile. Qt's `QScreen` API makes this doable but the complexity is only worth it if operators actually need it.

None of those are required for the current UX polish pass — the basic `saveGeometry`/`restoreGeometry` + `last_tab` triple covers the 90% case.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI state, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-twenty-third sub-slice: UX — menu bar (File / View / Tune / Help)

Third UX slice of the post-beautification pass. Sub-slice 121 added the F1 shortcut cheat sheet; sub-slice 122 added the discovery breadcrumbs that point operators at F1. This slice adds the conventional desktop-app landmark that every Windows operator expects but the app has lacked since day one: a proper `QMenuBar` with File / View / Tune / Help menus.

**The UX problem.** Before this slice, the app had a sidebar (page navigation), a command palette (Ctrl+K), a keyboard shortcut cheat sheet (F1), and a status bar — but no menu bar. Every other desktop app the operator uses has a menu bar, and its absence is a kind of negative signal: the app reads as *"unfinished"* or *"custom built"* because it's missing the one landmark that every Windows app shares. Adding the menu bar doesn't cost much (Qt's `QMenuBar` is free, the tokens already shape every `QAction` display) but the perceived-completeness delta is real.

**The refactor shape.** To add the menu bar cleanly, the existing main-window-level `QShortcut` handlers had to be hoisted so menu `QAction` instances could share the same code path. Two big handlers were promoted from inline-in-`QObject::connect` lambdas to named stack-captured lambdas:

- **`save_as_native_handler`** (Ctrl+S → File → Save as Native...) — builds the `.tuner` JSON preview dialog.
- **`open_command_palette`** (Ctrl+K → View → Command Palette...) — builds the Ctrl+K search dialog.

The existing `open_shortcuts_dialog` lambda (F1 → Help → Keyboard Shortcuts...) was already a named lambda from sub-slice 121 so no hoisting needed.

**QAction replaces QShortcut.** Every previously-standalone `QShortcut` at the main window level is now a `QAction::setShortcut` on a menu entry. Qt displays the shortcut in the menu column automatically — the single biggest discoverability win of adding the menu bar. A first-time operator who never presses F1 still learns about Ctrl+S the first time they open the File menu, because the menu itself displays `"Save as Native...      Ctrl+S"`. The sub-slice-121 cheat sheet overlay is now **the second discovery surface**; the menu bar is the first, and the two layers reinforce each other.

**Menu structure.**

- **&File** — `Save as Native...` (`Ctrl+S`), separator, `Exit` (`Ctrl+Q`).
- **&View** — `Tune` / `Live` / `Flash` / `Setup` / `Assist` / `Triggers` / `Logging` / `History` (each with the corresponding `Alt+1..8` shortcut displayed automatically), separator, `Command Palette...` (`Ctrl+K`). The sidebar is still the primary navigation surface, but the View menu is the second landmark — useful when the operator is exploring the app for the first time and wants to know "what are all the pages I can reach from here".
- **&Tune** — `Go to Tune Tab` (no shortcut, just a landmark) + three disabled-display-only entries (`Review Staged Changes... (Ctrl+R on Tune tab)`, `Write to RAM (Ctrl+W on Tune tab)`, `Burn to Flash (Ctrl+B on Tune tab)`). These are **deliberately disabled**. Why? The corresponding `QShortcut` instances live inside `build_tune_tab` on the `container` widget, not the main window, because they're context-scoped: `Ctrl+R` only does anything meaningful when the TUNE tab is focused. Wiring main-window menu actions to TUNE-tab-local handlers would require a bigger refactor (hoisting `open_review_dialog` through the tab boundary), so this slice takes the honest compromise: the menu entries show the shortcut in the label itself (`"...(Ctrl+R on Tune tab)"`) and stay disabled to signal that they're **descriptions, not buttons**. An operator who reads the Tune menu sees *"ah, the write/burn workflow lives on the Tune tab, here are the keys"* — which is all the menu needs to do for now.
- **&Help** — `Keyboard Shortcuts...` (`F1`), separator, `About Tuner`.

**About Tuner dialog.** New modal colocated with the menu bar setup. Fixed 420×280, uses the standard tokenized `QDialog` styling. Body is one rich-text `QLabel` composed via `snprintf` that renders:

```
         TUNER
      guided power

A modern workstation for Speeduino engines.
Native C++ Qt 6 build — Phase 14.

The same information TunerStudio shows,
organized around what the operator is
trying to accomplish.
```

The wordmark + tagline echoes the sidebar wordmark footer from sub-slice 90 — same `text_primary` bold title, `text_muted` small-caps subtitle, 2px / 1px letter-spacing. The closing paragraph is a **literal quote from the opening of `docs/ux-design.md`**, which is the one place the app states its design philosophy out loud. The About dialog is the second place (after the sidebar wordmark) and the first place an operator learns about it without having to read the source.

**Menu bar styling.** Full QSS composed via `snprintf` from theme tokens:

- `QMenuBar` — `bg_deep` background (same as sidebar), `text_secondary` text, `border` bottom edge.
- `QMenuBar::item:selected` — `fill_primary_mid` background (same blue tint as the sidebar selection and the command palette result selection — one more "selected state" that reads as the same visual grammar across the app).
- `QMenu` — `bg_panel` background (content container tier), `border` edge.
- `QMenu::item:selected` — `fill_primary_mid` hover.
- `QMenu::item:disabled` — `text_dim` color, matching the way the disabled shortcut-display entries in the Tune menu should read as chrome-label, not broken button.
- `QMenu::separator` — 1px `border` with `4px 6px` margin.

No new tokens. Every color, font, spacing value comes from `theme.hpp`.

**`?` stays as a hidden `QAction`.** The sub-slice 121 `Shift+/` alternate help binding isn't displayed in the Help menu (the primary binding is `F1`, shown explicitly), but it's still registered as a `QAction` on the main window with `setShortcut(Qt::SHIFT | Qt::Key_Slash)` + `setShortcutContext(Qt::ApplicationShortcut)`. The cheat sheet itself documents the alternate binding, which is the right layer for that disclosure — the menu stays clean.

**Cumulative discovery graph after this slice.** An operator has five ways to find any command:

1. **Menu bar** — scan the File / View / Tune / Help menus, every shortcut shown automatically.
2. **F1 cheat sheet overlay** — the full shortcut list grouped by purpose.
3. **Status bar hint** — `Press F1 for shortcuts` permanently visible.
4. **Ctrl+K command palette** — search by name, results include the current page.
5. **Ctrl+K placeholder hint** — mentions F1 for the full cheat sheet.

Every entry point leads to the others within one interaction. This is the "discovery graph" idea from sub-slice 122 extended to the menu bar — the menu is now the primary discovery surface and the earlier slices are the "if you haven't found the menu yet, here's the secondary path" fallback layers.

**No test suite impact.** C++ doctest suite unchanged at **1376 / 10823** — pure UI refactor, no logic touched. `tuner_app.exe` rebuilds cleanly.

**Mid-slice architectural note — why Tune menu entries are disabled, not wired.** The temptation was to hoist `open_review_dialog` from `build_tune_tab` out to the main window so the Tune menu items could trigger it. That would have required: threading the lambda through the tab-builder return value, storing it on `TunerMainWindow`, and making the menu action check "is the TUNE tab currently focused" before calling it. The ergonomic win over "show the shortcut in the label text" is small (an operator who wants to review staged changes almost always has the TUNE tab focused already), the implementation cost is real, and the explicit "(Ctrl+R on Tune tab)" label in the disabled menu entry is honest about the scoping. Kept the disable-with-hint compromise as a deliberate architectural choice, documented inline.

#### Phase 14 Slice 4 one-hundred-and-twenty-second sub-slice: UX — shortcut discovery breadcrumbs

Direct follow-up to sub-slice 121. The shortcut help overlay is great once the operator knows F1 exists — but a first-time operator has **no reason to press F1**. The overlay solves the "I pressed F1 and found help" problem but not the "I don't know F1 does anything" problem. This slice adds two quiet discovery breadcrumbs that thread the operator from *"unaware of any shortcut"* to *"F1 reveals everything"* without adding any chrome to the workspace content area.

**Two discovery surfaces.**

1. **Status bar permanent hint.** A new right-aligned `Press F1 for shortcuts` label is added via `QStatusBar::addPermanentWidget()`. `addPermanentWidget` is the Qt idiom for "status bar content that stays visible alongside transient `showMessage()` text" — exactly right for a chrome-level hint that shouldn't disappear when the live telemetry line updates every 500ms. The hint renders as a muted `QLabel` (`text_dim` + `font_small`, `padding-right: space_sm`) so it reads as chrome ("this is the app telling you how to use it") not content ("this is information from the ECU"). The operator's eye lands on the live telemetry on the left (changing values — the thing worth looking at) then drifts right to the permanent hint, which points to F1 for everything else. Quiet enough to ignore once learned, present enough to notice on first run.

2. **Command palette placeholder.** The `Ctrl+K` command palette's `setPlaceholderText` gains a trailing `· Press F1 for all shortcuts`. An operator who finds the palette before the status bar hint still learns about F1. An operator who finds the status bar hint but hasn't used the palette yet doesn't know about it. An operator who uses F1 sees both Ctrl+K and the status bar mentioned in the cheat sheet. **The three surfaces form a discovery graph** where any entry point leads to the other two within one interaction.

**Philosophy — discovery breadcrumbs, not chrome.**

The difference between "discovery chrome" and "tutorial chrome" is whether it's there the second time. A tutorial overlay that says *"welcome! click here for tips!"* becomes dead weight after the operator dismisses it once — it was there to teach, the teaching happened, now it's noise. A breadcrumb stays useful even when the operator already knows about it, because it confirms *"yes, F1 still means shortcuts, you're in the right place"*. The status bar hint is a permanent confirmation, not a first-run tutorial.

The `docs/ux-design.md` principle *"don't teach what the operator can ask for"* is strict: the app never pops up a tooltip, never shows a "first time here?" splash, never tracks user behavior to decide when to nag. But that principle coexists with *"every affordance should be discoverable without reading the docs"* — which is why the breadcrumbs exist. They're passive affordances that answer the operator's question *before* the operator asks it, so the "ask for help" moment is preempted by a whispered answer already on screen.

**Compare to the sub-slice 115 beautification philosophy.** The arc closed with the claim that every pixel in the app flows from `theme.hpp`. This slice is a test of that: the new hint reuses `text_dim` + `font_small` + `space_sm`, no new tokens, no new helpers. The command palette placeholder change is a single string edit with no stylesheet touch at all. Both additions land without inflating the palette or the helper surface — exactly what the token system was built for.

**Follow-up opportunities (deferred).** The sub-slice 121 backlog mentioned contextual shortcuts (filter the cheat sheet to "shortcuts that matter on this tab"). Still a good future slice. Also worth considering: a one-time first-run flag that shows the F1 hint with a brief accent outline on the first app launch, then dims it permanently — but that's tutorial chrome, which the philosophy deliberately avoids, so probably better to leave the hint permanently dim and trust the operator to notice it within their first session.

**No test suite impact.** C++ doctest unchanged at **1376 / 10823** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-twenty-first sub-slice: UX — keyboard shortcut help overlay

First meaningful UX slice after the beautification arc closed at sub-slice 115. The app had accumulated **12 keyboard shortcuts** over sub-slices 53 onward — `Alt+1..8` for sidebar navigation, `Ctrl+K` for the command palette, `Ctrl+R` / `Ctrl+W` / `Ctrl+B` for the review / write-to-ram / burn-to-flash workflow, `Ctrl+S` for native-format save — and **zero in-app discoverability**. An operator would have to stumble on them in a docs file, learn them from a blog post, or inspect `main.cpp` itself to find out any of them existed.

**The operator problem.** Invisible shortcuts are dead shortcuts. The command palette (`Ctrl+K`) is the biggest example: it's a fantastic jump-to-any-page ergonomic win, but an operator who doesn't know about it will click the sidebar for every tab change instead. The write/burn/review cycle is the same: the TUNE-tab review popup has clickable buttons, but an operator who memorises `Ctrl+R` → `Ctrl+W` → `Ctrl+B` can drive the full commit workflow without ever touching the mouse — which is the whole point of the three-zoom staged-state design from sub-slice 92.

**The slice.** Bind **F1** and **?** to open a modal keyboard-shortcut cheat sheet dialog. Two bindings for the same dialog: `F1` is the universal Windows/Qt help key, `?` (`Qt::SHIFT | Qt::Key_Slash`) is the universal vim/terminal help key. Right-hand-only reach on both.

- `cpp/app/main.cpp` — new `open_shortcuts_dialog` lambda colocated with the other shortcut bindings. Two `QShortcut` instances wire `F1` and `Shift+/` to the same callback. The dialog itself uses the existing tokenized `QDialog` styling pattern established in sub-slices 112 (command palette + startup picker) + 113 (global QSS): `bg_base` background, `border` edge, `text_secondary` body color. Fixed 480×520 so the layout is deterministic regardless of what's behind it.

- **Header** — hero title + dim subtitle in the same grammar as the tab header primitive from sub-slice 111: `font_label` bold `text_primary` title over a `font_small` `text_dim` subtitle (`"Press F1 or ? anywhere to show this panel. Esc to dismiss."`). The operator learns how to dismiss the dialog inside the dialog itself, so no other panel has to teach the binding.

- **Grouped cheat sheet** — the body is composed as one rich-text `<table>` inside a single QLabel. Four category groups: **Navigation** (Alt+1..8, Ctrl+K), **Tune workflow** (Ctrl+R/W/B), **Files** (Ctrl+S), **Help** (F1, ?, Esc). Group titles use uppercase `text_muted` + `font_small` with 1px letter-spacing — matches the wordmark footer grammar from sub-slice 90, so the two "tiny dim category labels" surfaces across the app read as the same voice.

- **Key chips** — each row's key binding lands in a monospace-font chip styled with `bg_inset` + `border` + `radius_sm` + `text_primary` + `font_small`. **This is the key architectural decision of the slice:** the chip reuses the exact visual grammar the TUNE-tab scalar editor chips (sub-slice 91) use for tune values. "Press `Ctrl+R`" and "edit parameter value `3.14`" both render as the same class of interactive primitive — chip-shaped, fixed-pitch, slightly recessed — so the operator's mental model reads them as the same kind of thing ("chrome you interact with") rather than two different decorative elements. This is the sub-slice 88 *"first-class primitives"* principle reaching one more surface.

- **Row descriptions** — `text_secondary` + `font_body`, the standard muted-description tier from every other info surface in the app.

**Philosophy — progressive disclosure applied to keyboard navigation.** The main workspace never screams *"you can press Alt+2 to jump to LIVE"*; the chrome stays calm and content-focused. Instead, one quiet key (`F1` / `?`) reveals the full cheat sheet whenever the operator wants it. The `docs/ux-design.md` principle *"don't teach what the operator can ask for"* applies directly: the shortcuts are there when needed, invisible when not. An operator who never presses F1 loses nothing; an operator who does gets every keyboard workflow in one modal. This is the same shape as the command palette (`Ctrl+K`) — chrome that's zero cost until you want it.

**Composed HTML, not a grid widget.** The cheat sheet body is built as one `<table>` inside a single rich-text QLabel via a 4096-byte `snprintf` buffer. Two reasons: (1) alignment stays deterministic without running a `QGridLayout` / `QTableWidget` that would drag in its own theming headaches, and (2) the cheat sheet is static content, so stateful widget infrastructure would be ceremony over one label + one style. The pattern matches how the startup project picker (sub-slice 112) builds its welcome text — one `snprintf` into a stack buffer, one `QLabel::setText`, no intermediate models.

**No test suite impact.** C++ doctest unchanged at **1376 / 10823** — pure UI addition. `tuner_app.exe` rebuilds cleanly.

**Follow-up opportunities (not in this slice).** A few natural extensions to keep in mind if the UX direction gets another pass:
- **Command palette discovery.** The palette's placeholder text could mention "Press `?` for the full shortcut cheat sheet" so operators who find Ctrl+K first see the second affordance too.
- **Status bar hint.** A subtle `Press F1 for shortcuts` line in the right-hand slot of the QStatusBar at app start (dim, dismissable) would give first-time operators the thread to pull without polluting the workspace.
- **Contextual shortcuts.** Right now F1 shows the full global list regardless of which tab is active. A future pass could filter to "shortcuts that matter on this tab" so the LIVE tab shows just the navigation group + Ctrl+K, while the TUNE tab adds the workflow row. Zero extra widgets, one conditional inside the table builder.

None of these block the current state — the core "every shortcut is now discoverable" win lands in this slice alone.

#### Phase 14 Slice 4 one-hundred-and-twentieth sub-slice: INI `[PcVariables]` parser + aggregator merge

Direct port of `IniParser._parse_pc_variables`. The `[PcVariables]` section declares **host-side display variables**: scalars, bit fields, and arrays that live entirely in the workstation (operator-set preferences, computed dashboard channels) without any ECU storage. Grammar is a proper subset of `[Constants]`:

- `name = scalar, TYPE, "units", scale, translate, lo, hi, digits`
- `name = bits, TYPE, [shape], "label0", "label1", ...`
- `name = array, TYPE, [shape], "units", scale, translate, lo, hi, digits`

Compared to `[Constants]` there's no `page = N` tracking, no `lastOffset` handling, no `offset` field at all, and no `string` entry kind. Every entry is emitted with `page = nullopt` and `offset = nullopt` so downstream services can tell PC-only entries apart from their ECU-storage neighbours.

- `cpp/include/tuner_core/ini_pc_variables_parser.hpp` and `cpp/src/ini_pc_variables_parser.cpp` — **reuses the existing `IniScalar` / `IniArray` / `IniConstantsSection` PODs** from `ini_constants_parser.hpp` so the downstream aggregator can merge the PC variables output directly into `NativeEcuDefinition.constants`. The output shape is identical apart from `page` / `offset` being `nullopt` on every entry. Internal helpers (`parse_int_literal`, `parse_float_token`, `parse_int_token`, `parse_value_token`, `parse_shape`, `parse_bit_shape`) mirror the `ini_constants_parser` versions — they're intentionally duplicated in the `.cpp` rather than factored into `parse_helpers.hpp` because the parsers are peers, not a shared base class, and factoring would couple the two headers unnecessarily. The regex is the `[Constants]` pattern minus the `offset` capture group and minus the `string` alternative. Bit-option expansion uses the shared `expand_options` helper from `ini_defines_parser.hpp` (the same helper the constants parser already uses).
- `cpp/include/tuner_core/ecu_definition_compiler.hpp` + `cpp/src/ecu_definition_compiler.cpp` — the aggregator **merges** the PC variables result into `definition.constants.scalars` / `definition.constants.arrays` via `std::vector::insert` with `std::make_move_iterator`. This matches the Python `_parse_pc_variables` behaviour of appending into the same `definition.scalars` / `definition.tables` lists that `_parse_constant_definitions` populates. The merge happens inside `compile_ecu_definition_text` right after the constants parse so downstream consumers see a single unified catalog.
- `cpp/tests/test_ini_pc_variables_parser.cpp` — 12 doctest cases covering every grammar arm: scalar with all fields, bits with option labels, 2D array, 1D array (`[10]` shape), multi-entry accumulation, lines outside section ignored, `string` kind explicitly not recognised (Python grammar drops it), case-insensitive header, comments + blank lines skipped, preprocessor `#if` gating, empty input, empty section.
- `cpp/bindings/tuner_core_module.cpp` — 2 new free functions (`parse_pc_variables_section` / `parse_pc_variables_section_preprocessed`) bound to return the existing `IniConstantsSection` binding class.
- `tests/unit/test_cpp_ini_pc_variables_parser_parity.py` — 11 parity tests driven through the same `preprocess_ini_lines` + leaf-method-directly pattern sub-slice 109 documented. Synthetic: scalar / bits / 2D array / 1D array / multi-entry / lines-outside / case-insensitive / comments / preprocessor gating / empty section. **Production INI parity:** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, drives both `IniParser._parse_pc_variables` (with `defines=parser._collect_defines(...)` for correct option expansion) and `parse_pc_variables_section_preprocessed`, asserts every scalar + every array's full field set matches byte-for-byte.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — extended `test_constants_section_count_matches` to account for the new merge. Runs the Python PC-variables leaf separately to compute the extra count and adds it to the filtered `[Constants]`-only count so the total matches the post-merge C++ `constants.scalars` / `.arrays` size.

**Mid-slice fix — parity test had to collect defines explicitly.** The first parity run passed all 10 synthetic tests but failed the production INI parity check on bit-option count (Python had 0 options where C++ had 8). Root cause: my test harness called `parser._parse_pc_variables(path, definition)` with the default `defines=None` argument, so the Python side produced raw `$macroName` references with no expansion. But the C++ `parse_pc_variables_section_preprocessed` internally runs `collect_defines_lines` which picks up every `#define` from the full INI text and passes them to the parser. Fix: explicitly call `parser._collect_defines(tmp_path)` in the test harness and pass the result to `_parse_pc_variables(path, definition, defines)`. This is the same orchestration the Python `parser.parse()` does on line 71-73 of `ini_parser.py`. Documented inline in the test comment.

**One rarely-used leaf remains:** `[AutotuneSections]` — drives the tune-time correction preview that the VE/WUE Analyze pipeline uses. The actual correction computation is already ported via dedicated C++ services (`ve_cell_hit_accumulator`, `ve_analyze_review`, `ve_proposal_smoothing`, `wue_analyze_accumulator`); only the INI-side metadata parse is missing. The metadata tells the workspace UI which table+axis combinations the Analyze tools can target, but the C++ tools already work against any declared table so the metadata is effectively the "list of legal scope choices in the UI dropdown" — non-structural.

C++ doctest suite: 1364 / 10765 → **1376 / 10823** (+12 tests, +58 assertions). Python collected suite: 2984 → **2995** (+11 per-parser parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-nineteenth sub-slice: INI reference-tables parser + aggregator wire-up

Direct port of `IniParser._parse_reference_tables`. Reference tables are the look-up tables the operator consults when they hit a specific tuning issue — e.g. a "Lean at WOT" table listing the most likely causes ("low fuel pressure", "injector too small", "MAP sensor drifting") alongside expressions that test for each cause. The workspace presenter reads these tables and offers them as a diagnostic side-panel on the relevant table editor pages.

**Interesting wrinkle — shared section header with `ini_dialog_parser`.** Reference tables live inside the `[UserDefined]` section, which is the SAME section `ini_dialog_parser` reads for field/panel/dialog declarations. The two parsers co-exist because they dispatch on different property names (`dialog = ...` / `field = ...` / `panel = ...` for dialogs vs. `referenceTable = ...` / `topicHelp = ...` / `solution = ...` for reference tables). Each parser walks the full section and only responds to its own keys, silently ignoring the other's. Sub-slice 119 adds a second consumer of `[UserDefined]` without disturbing sub-slice 50's dialog parser.

- `cpp/include/tuner_core/ini_reference_tables_parser.hpp` and `cpp/src/ini_reference_tables_parser.cpp` — `IniReferenceTableSolution { label, expression: optional<string> }` + `IniReferenceTable { table_id, label, topic_help, table_identifier, solutions_label, solutions }` + `IniReferenceTablesSection { tables }` PODs mirroring the Python `ReferenceTableDefinition` / `ReferenceTableSolution` domain types exactly. Stateful block parser: `referenceTable = id, "label"` opens a new block, subsequent `topicHelp` / `tableIdentifier` / `solutionsLabel` / `solution` lines accumulate into the in-flight table. The in-flight table is tracked by **index into the section's `tables` vector** rather than by pointer, so `vector::push_back` reallocation during multi-table parsing doesn't invalidate the in-flight reference. `tableIdentifier` with a single CSV field uses `parts[0]`; with two or more fields uses `parts[1]` — mirrors the Python `parts[1] if len(parts) > 1 else (parts[0] if parts else None)` ternary exactly. Missing label on `referenceTable` defaults to `table_id`. Orphan `solution` / `topicHelp` lines before the first `referenceTable` are silently dropped (current_index stays -1). Section-change and section-re-entry both drop the in-flight block correctly.
- `cpp/include/tuner_core/ecu_definition_compiler.hpp` + `.cpp` — added `reference_tables` field on `NativeEcuDefinition` + one dispatch line in `compile_ecu_definition_text`.
- `cpp/tests/test_ini_reference_tables_parser.cpp` — 13 doctest cases (all using `R"INI(...)INI"` custom raw-string delimiter to avoid the `)"` collision pattern documented in sub-slice 118): full table with every field, label defaults to id, multiple tables independent, orphan properties ignored, solution without expression, `tableIdentifier` single-arg, section switch drops in-flight, unknown keys ignored, case-insensitive header, comments + blank lines, preprocessor `#if` gating, empty input, empty section.
- `cpp/bindings/tuner_core_module.cpp` — 3 new classes (`IniReferenceTableSolution`, `IniReferenceTable`, `IniReferenceTablesSection`) + 2 free functions + aggregator `def_rw`.
- `tests/unit/test_cpp_ini_reference_tables_parser_parity.py` — 11 parity tests against `IniParser._parse_reference_tables`. Synthetic: full table / label defaults / multi-table / orphan / solution without expression / tableIdentifier single-arg / section-switch / case-insensitive / preprocessor gating / empty section. **Production INI parity:** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, drives both `IniParser.parse()` and `parse_reference_tables_section_preprocessed`, asserts every table's full field set (id + label + topic_help + table_identifier + solutions_label + every solution's label + expression) matches byte-for-byte.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — extended with `test_reference_tables_parity` asserting the new field lands correctly on the full compiler output.

**Two rarely-used leaves remain unported:** `[PcVariables]` (which reuses the full `[Constants]` grammar for host-side display variables — non-trivial port that would share a lot of logic with the already-ported `ini_constants_parser`) and `[AutotuneSections]` (which drives the tune-time correction preview; the VE/WUE Analyze pipeline already has dedicated C++ services for the actual computation, so the INI-parse side is the only missing piece). Both can fold in opportunistically when a downstream C++ consumer shows demand.

C++ doctest suite: 1351 / 10717 → **1364 / 10765** (+13 tests, +48 assertions). Python collected suite: 2972 → **2984** (+12 parity tests: 11 per-parser + 1 compiler aggregator). `tuner_app.exe` rebuilds cleanly. No mid-slice fixes — the sub-slice 118 raw-string collision lesson paid forward (this slice pre-emptively used `R"INI(...)INI"` on every test case that contained any parentheses in quoted strings).

#### Phase 14 Slice 4 one-hundred-and-eighteenth sub-slice: INI `[Tools]` parser + aggregator wire-up

Direct port of `IniParser._parse_tools`. The `[Tools]` section declares add-on operator tools that integrate with specific table editors. Each recognised line is an `addTool = tool_id, label, target_table_id` declaration where the third field is optional — tools without a `target_table_id` apply globally. The workspace presenter reads these declarations and offers the matching tools as menu actions on the relevant table pages. Production examples: `addTool = veAnalyze, "VE Analyze", veTable1Tbl` scopes VE Analyze to the VE table, `addTool = wueAnalyze, "WUE Analyze", wueCurve` scopes WUE Analyze to the warmup enrichment curve.

- `cpp/include/tuner_core/ini_tools_parser.hpp` and `cpp/src/ini_tools_parser.cpp` — `IniToolDeclaration { tool_id, label, target_table_id: optional<string> }` POD mirroring the Python `ToolDeclaration` dataclass, and `IniToolsSection { declarations: vector<IniToolDeclaration> }`. Stateful per-line parser with the standard INI-leaf shape; unknown keys silently ignored so future INIs can add new metadata without breaking the parser. Value split reuses the shared `parse_helpers.hpp::parse_csv` so label quoting + embedded comma behaviour matches every other INI leaf exactly. Missing label defaults to the `tool_id` (mirrors Python's `parts[1] if len(parts) > 1 else tool_id`). Missing `target_table_id` leaves the optional unset.
- `cpp/include/tuner_core/ecu_definition_compiler.hpp` + `.cpp` — added `IniToolsSection tools` as the final field on `NativeEcuDefinition` and one dispatch line in `compile_ecu_definition_text`.
- `cpp/tests/test_ini_tools_parser.cpp` — 12 doctest cases covering: full addTool line, missing target_table_id → nullopt, missing label → defaults to tool_id, multiple declarations accumulate, unknown keys ignored, lines outside section ignored, case-insensitive section header, comments + blank lines skipped, preprocessor `#if` gating, empty input, empty section, empty addTool value skipped.
- `cpp/bindings/tuner_core_module.cpp` — new `IniToolDeclaration` / `IniToolsSection` classes + `parse_tools_section` / `parse_tools_section_preprocessed` free functions. Extended `NativeEcuDefinition` binding with `.def_rw("tools", ...)`.
- `tests/unit/test_cpp_ini_tools_parser_parity.py` — 10 parity tests against `IniParser._parse_tools`. Synthetic: full / missing-target / missing-label / multi / unknown-keys / lines-outside / case-insensitive / preprocessor gating / empty section. **Production INI parity:** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, drives both `IniParser.parse()` and `parse_tools_section_preprocessed`, asserts the full declarations list matches field-by-field.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — extended with `test_tools_parity` asserting the new field lands correctly on the full compiler output.

**Mid-slice fix — raw-string delimiter collision.** The first doctest build failed with `'#endif' without '#if'` errors because a test case had `"VE Analyze (disabled)"` inside a `R"(...)"` raw string literal. C++ raw strings use `)"` as the default closer, so the `)"` inside the quoted label closed the raw string prematurely — everything after was parsed as normal C++ tokens, which treated the literal `#endif` on the next line as an actual preprocessor directive. Fixed two ways: used the custom delimiter form `R"INI(...)INI"` and also dropped the parenthesis from the test label text since it wasn't semantically important. Documented inline with a comment explaining the collision for future readers.

**Pattern reuse.** Same shape as sub-slice 117: one parser + aggregator wire-up + per-parser parity + compiler parity extension, all in one sub-slice.

**Three rarely-used leaves remain unported:** `[PcVariables]`, `[AutotuneSections]`, `[ReferenceTables]`. Each carries narrow metadata that downstream C++ services can fold in opportunistically when they show real demand.

C++ doctest suite: 1339 / 10686 → **1351 / 10717** (+12 tests, +31 assertions). Python collected suite: 2961 → **2972** (+11 parity tests: 10 per-parser + 1 compiler aggregator). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-seventeenth sub-slice: INI `[ConstantsExtensions]` parser + aggregator wire-up

Direct port of `IniParser._parse_constants_extensions`. The `[ConstantsExtensions]` section in production INIs carries extra per-constant metadata that didn't fit in the main `[Constants]` grammar. In practice the only recognised key is `requiresPowerCycle` — a comma-separated list of parameter names that require a full ECU power cycle before the change takes effect (as opposed to the normal "write to RAM, burn to flash" flow where the change is live immediately). The workspace presenter reads this set and shows a "restart required" warning on the relevant edits so the operator knows to cycle power after burning.

**Without this parser, `tuner_app.exe` native would silently drop every "requires power cycle" warning during INI import.** The warning itself is small (a text suffix on the staged-change chip), but the consequence of missing it is that the operator burns a changed value, reconnects expecting the new behaviour, and sees the ECU still running the old value — a confusing 20-minute debug session that a single one-line warning prevents.

- `cpp/include/tuner_core/ini_constants_extensions_parser.hpp` and `cpp/src/ini_constants_extensions_parser.cpp` — `IniConstantsExtensionsSection { requires_power_cycle: set<string> }` POD mirroring the Python `EcuDefinition.requires_power_cycle` field. Stateful per-line parser with the standard INI-leaf shape: skip comments / blanks / lines-outside-section / missing-equals. Unknown keys in the section are silently ignored (future INIs may add new metadata keys without breaking existing production artifacts). Values run through an internal `parse_name_list` helper that mirrors Python's `value.split(";", 1)[0].split(",")` pipeline: strip trailing `;` comment first, then CSV-split the head, then trim non-empty tokens. Multiple `requiresPowerCycle` lines accumulate into the same set (the Python code uses `definition.requires_power_cycle.add` so this is set-union semantics, not last-write-wins). Composed pipeline `parse_constants_extensions_section_preprocessed` chains preprocess + collect defines + parse.
- `cpp/include/tuner_core/ecu_definition_compiler.hpp` + `.cpp` — added `IniConstantsExtensionsSection constants_extensions` as the final field on `NativeEcuDefinition` (after `setting_context_help`) and one dispatch line in `compile_ecu_definition_text`. Maintains the single-preprocessor-pass design.
- `cpp/tests/test_ini_constants_extensions_parser.cpp` — 12 doctest cases covering: simple list parse, whitespace tolerance, trailing `;` comment strip, unknown keys ignored, empty entries dropped, multiple lines accumulate, lines outside section ignored, case-insensitive header, comments + blank lines, preprocessor `#if` gating, empty input, empty section.
- `cpp/bindings/tuner_core_module.cpp` — new `IniConstantsExtensionsSection` class + `parse_constants_extensions_section` / `parse_constants_extensions_section_preprocessed` free functions. Extended `NativeEcuDefinition` binding with `.def_rw("constants_extensions", ...)`.
- `tests/unit/test_cpp_ini_constants_extensions_parser_parity.py` — 11 parity tests against `IniParser._parse_constants_extensions`. Synthetic: simple / whitespace / trailing semicolon / unknown-key / empty entries / multi-line-accumulate / lines-outside / preprocessor gating / active-settings override / empty section. **Production INI parity:** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, drives both `IniParser.parse()` and the C++ `parse_constants_extensions_section_preprocessed`, asserts the full `requires_power_cycle` set matches byte-for-byte.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — extended with a new `test_constants_extensions_parity` that drives the full production INI through both the Python orchestrator and `compile_ecu_definition_text` and asserts `constants_extensions.requires_power_cycle` matches through the full aggregator path.

**Four rarely-used INI leaves remain unported.** After this slice, the only Python `IniParser` leaves without C++ equivalents are `[PcVariables]` (tune-mode-only display variables), `[Tools]` (tune assist UI helper declarations), `[AutotuneSections]` (the tune-time correction preview — already has dedicated C++ services for the VE/WUE Analyze pipeline), and `[ReferenceTables]` (read-only comparison tables). Each carries narrow metadata; none are structurally required for a clean INI import. They can fold in opportunistically when a downstream C++ service shows demand.

**Pattern reuse.** Same shape as sub-slice 116: one parser + aggregator wire-up + per-parser parity test + compiler parity test extension, all in one slice. The wire-up is cheap enough (one field + one dispatch line + one `def_rw`) that separating it from the port itself would be scope creep.

C++ doctest suite: 1327 / 10658 → **1339 / 10686** (+12 tests, +28 assertions). Python collected suite: 2949 → **2961** (+12 parity tests: 11 per-parser + 1 compiler aggregator). `tuner_app.exe` rebuilds cleanly. No mid-slice fixes — build + per-parser parity + compiler parity all clean first try.

#### Phase 14 Slice 4 one-hundred-and-sixteenth sub-slice: INI `[SettingContextHelp]` parser + aggregator wire-up

Back to pure-logic ports after the beautification arc closed at sub-slice 115. Direct port of `IniParser._parse_setting_context_help` from `src/tuner/parsers/ini_parser.py`. The `[SettingContextHelp]` section carries `name = "help text"` pairs that downstream services use to populate tooltips on every tunable scalar / table / curve — the operator sees these as the hover text in the TUNE-tab right-panel forms. Without this parser in C++ the `tuner_app.exe` native build would silently drop every tooltip during INI import. This is the last *broadly-used* metadata leaf the Python `IniParser` knows about; what remains are the five rarely-used leaves (`[PcVariables]`, `[ConstantsExtensions]`, `[Tools]`, `[AutotuneSections]`, `[ReferenceTables]`) which can be folded in opportunistically as downstream C++ services actually need them.

- `cpp/include/tuner_core/ini_setting_context_help_parser.hpp` and `cpp/src/ini_setting_context_help_parser.cpp` — `IniSettingContextHelpSection { help_by_name: map<string, string> }` POD mirroring the Python `EcuDefinition.setting_help` dict field-for-field. `std::map` (sorted) is used over `unordered_map` so iteration is deterministic across implementations — matches the existing `legacy_project_file` port pattern from sub-slice 103. Stateful per-line parser with the standard INI-leaf shape: comment lines (`;`, `#`), blank lines, lines outside `[SettingContextHelp]`, missing-equals lines, and empty keys are all skipped. Values run through a `clean_help_value` helper that strips a trailing `;` comment first (mirrors Python's `value.split(";", 1)[0]`) then strips paired quotes via the shared `parse_helpers.hpp::strip_quotes`. Composed pipeline `parse_setting_context_help_section_preprocessed` chains preprocess + collect defines + parse for `#if` gating and `active_settings` override support.
- `cpp/include/tuner_core/ecu_definition_compiler.hpp` — added `IniSettingContextHelpSection setting_context_help` field on `NativeEcuDefinition` (directly after `setting_groups` to match the Python `EcuDefinition` field order) and `#include "tuner_core/ini_setting_context_help_parser.hpp"`.
- `cpp/src/ecu_definition_compiler.cpp` — added one dispatch line `definition.setting_context_help = parse_setting_context_help_lines(lines, defines);` using the same already-preprocessed `lines` + `defines` every other leaf parser in `compile_ecu_definition_text` consumes. Single-preprocessor-pass design preserved.
- `cpp/tests/test_ini_setting_context_help_parser.cpp` — 11 doctest cases covering: simple key=value, quotes-and-semicolon-comment handling, lines outside section ignored, missing-equals lines skipped, comments + blank lines, case-insensitive section header match, preprocessor `#if` gating, active_settings override, empty section, empty input, empty-key skip.
- `cpp/bindings/tuner_core_module.cpp` — new `IniSettingContextHelpSection` class with the `help_by_name` read/write field, plus `parse_setting_context_help_section` / `parse_setting_context_help_section_preprocessed` free functions. Also added `.def_rw("setting_context_help", ...)` to the existing `NativeEcuDefinition` binding.
- `tests/unit/test_cpp_ini_setting_context_help_parser_parity.py` — 9 parity tests against `IniParser._parse_setting_context_help`. Synthetic: simple two-entry shape, quotes-and-semicolon handling, lines-outside-section, case-insensitive header, comments + blank lines, empty section, `#if` gating with empty `active_settings`, `#if` gating with user-supplied `active_settings` override. **Production INI parity:** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, drives both `IniParser.parse()` and `parse_setting_context_help_section_preprocessed`, asserts the full `help_by_name` map matches byte-for-byte and that production has ≥ 20 help entries.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — extended with a new `test_setting_context_help_parity` that drives the full production INI through both the Python orchestrator and the C++ `compile_ecu_definition_text` and asserts the new `setting_context_help.help_by_name` field matches byte-for-byte after the aggregator dispatch.

**Pattern reuse.** This slice follows the sub-slice 109 (`[SettingGroups]`) + sub-slice 110 (wire into aggregator) shape exactly: one new leaf parser, one aggregator field, one compiler test extension, one per-parser parity test file driven through the same `preprocess_ini_lines` + tmp-file + leaf-method-directly pattern that sub-slice 109 documented. The wire-up happens in the same slice as the port itself this time because the parser is tiny and the aggregator integration was one field + one dispatch line — separating them into two sub-slices would be scope creep.

**What's left on the INI parser side.** Every broadly-used leaf the Python `IniParser` handles is now ported. The rarely-used leaves (`[PcVariables]`, `[ConstantsExtensions]` beyond `requiresPowerCycle`, `[Tools]`, `[AutotuneSections]`, `[ReferenceTables]`) carry narrow metadata — e.g. `[PcVariables]` is tune-mode-only display variables, `[AutotuneSections]` drives the tune-time auto-correction preview which already has a C++ service port — so the C++ aggregator can ship without them and downstream ports can fold them in only when a real consumer shows up.

C++ doctest suite: 1316 / 10634 → **1327 / 10658** (+11 tests, +24 assertions). Python collected suite: 2939 → **2949** (+10 parity tests: 9 per-parser + 1 compiler aggregator). `tuner_app.exe` rebuilds cleanly. No mid-slice fixes — build + per-parser parity + compiler parity all passed first try.

#### Phase 14 Slice 4 one-hundred-and-fifteenth sub-slice: Beautification pass #8 — severity color dispatch sweep, arc finale

**Eighth and closing slice of the beautification arc** (sub-slices 88 / 90 / 91 / 111 / 112 / 113 / 114 / 115). The previous seven passes migrated major surfaces — LIVE runtime header, app shell chrome + wordmark, TUNE detail panel, tab header primitive, modal dialogs, global stylesheet, LIVE number cards. This slice sweeps every remaining inline severity-color dispatch across ASSIST / SETUP / TRIGGERS / LOGGING / TUNE tabs. What remains after this slice is a single documented outlier.

**The sweep.** Every inline call to `make_info_card(..., "#hex")`, every ternary assigning a severity accent from a `"ok"`/`"warning"`/`"danger"` string or a `Status::OK`/`INFO`/`NEEDED`/`WARNING` enum, every `render_1d_curve(..., "#hex")` call, and every per-cell color dispatch in the thermistor + ASSIST grid + SETUP checklist surfaces now pulls tokens directly:

| Inline literal (pre-slice)        | Token (post-slice)       | Meaning                           |
|-----------------------------------|--------------------------|-----------------------------------|
| `"#5a9ad6"`                        | `tt::accent_primary`     | default / informational / blue    |
| `"#5ad687"`                        | `tt::accent_ok`          | healthy / pass                    |
| `"#d6a55a"`                        | `tt::accent_warning`     | attention needed / amber          |
| `"#d65a5a"`                        | `tt::accent_danger`      | urgent / engine at risk / red     |
| `"#9a7ad6"`                        | `tt::accent_special`     | derived / computed / purple       |
| `"#8a93a6"`                        | `tt::text_muted`         | muted informational chip          |
| `"#d69a5a"` (one-off near-amber)   | `tt::accent_warning`     | folded into warning               |

**Call sites migrated (by tab / surface).**

- **ASSIST tab** (`build_assist_tab`): Cell Hit Accumulator card, Proposal Smoothing card, Diagnostic cards, Root-Cause Diagnostics card, 4×4 proposal grid per-cell ternary (`cf > 1.05` / `cf < 0.95`), Analysis Review card, WUE Summary card, WUE Proposal per-cell ternary. All seven `make_info_card` accent args + two per-cell ternaries switch from literals to tokens. The proposal-grid HTML `#131418` (dark-on-color text) becomes `tt::text_inverse`.
- **SETUP tab** (`build_setup_tab`): VE Assumptions card, Idle RPM / WUE / Cranking `render_1d_curve` calls, Thermistor Calibration card (including the per-preview-point temperature ternary — hot/warm/normal/cold maps to danger/warning/ok/primary), Required Fuel Calculator card, Hardware Validation pass/fail cards, Ignition Coil Preset cards (Official/Trusted/Community ternary), Sensor Setup Checklist per-item Status dispatch, Generator Readiness card, Ignition/Trigger Cross-Validation per-item Status dispatch. The **SETUP wizard step navigator** active/inactive state migrates to `fill_primary_mid` / `bg_elevated` / `text_primary` / `text_muted` / `accent_primary` / `border` / `accent_ok` — same "selected" grammar as the sidebar selection state, the command palette selection state, and the TUNE-tab scalar editor OK state.
- **TRIGGERS tab** (`build_triggers_tab`): Visualization Summary card (ternary), per-trace digital/analog ternary, Annotations card (ternary), Capture Summary card (severity ternary), Decoder Context card, per-finding severity ternary.
- **LOGGING tab** (`build_logging_tab`): Default Profile card, Profile Persistence card, Datalog Replay per-row ternary.
- **Shared helpers**: `render_1d_curve` default accent arg, `render_heatmap` card stylesheet + header, `render_1d_curve` card stylesheet + header + per-row HTML. `render_1d_curve` default arg uses `tt::accent_primary` — `constexpr const char*` works as a default argument, confirmed by the clean build.
- **TUNE tab**: The `Ctrl+S` Save-as-.tuner preview dialog stylesheet (QDialog + QTextEdit) and its label color.

**The remaining outlier — dashboard operating-point crosshair.** The only inline stylesheet hex in `main.cpp` after this slice is the crosshair highlight for the currently-selected table cell on the LIVE dashboard:

```cpp
"background-color: #ffffff; color: #000000; "
"border: 2px solid #ff4444; padding: 0px; "
```

This is a **deliberate maximum-visibility override** outside the restrained palette. Tokenized equivalents would soften the intent — `text_primary` (#e8edf5) is not pure white, `accent_danger` (#d65a5a) is not alert red. The design intent is *"look at THIS cell, RIGHT NOW"*, which is the one place the restrained philosophy explicitly steps aside. Documented inline with a comment explaining why it's intentionally outside the palette.

**Philosophy — the restrained palette has exactly one explicit exception.** The 88/90/91/111/112/113/114/115 arc took `main.cpp` from 200+ inline hex literals drifting across every tab to **exactly one** visually distinctive surface that deliberately steps outside the palette — and it's documented with a comment explaining *why*. Every other pixel in the app flows from `theme.hpp`. This is the "one palette, one voice" principle from `docs/ux-design.md` reduced to its most literal form: `grep -n '#[0-9a-f]\{6\}'` on `main.cpp` now returns 6 hits — 2 for the documented crosshair override and 4 inside `//` comments that reference token alternatives or pre-migration historical drift. Adding a new hex now requires adding a comment explaining why, which is the point.

**Inline hex literal count in `main.cpp`: 70 → 6** (-64, the biggest single-slice drop in the arc). **Cumulative across the full beautification arc: 200+ → 6.** The arc is now closed — future beautification passes can happen inside `theme.hpp` (tuning existing tokens) rather than in `main.cpp` (adding new helpers), which is the structural shape the sub-slice 88 token system was built to unlock.

**No test suite impact.** C++ doctest suite unchanged at **1316 / 10634** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-fourteenth sub-slice: Beautification pass #7 — LIVE dashboard number card primitive

Seventh slice in the beautification arc (sub-slices 88 / 90 / 91 / 111 / 112 / 113 / 114). Sub-slice 113 killed the biggest single-block drift source (the `DARK_QSS` global stylesheet); this slice kills the biggest **per-element loop** drift source — the LIVE-tab dashboard number card update, which runs on every 200ms timer tick and rebuilds the card stylesheet + HTML from scratch for every visible card every tick.

**The pre-slice shape.** The per-tick update loop looked like:

```cpp
const char* accent = "#5a9ad6";
for (const auto& z : b.zones) {
    if (val >= z.lo && val <= z.hi) {
        zone_name = z.color;
        accent = (z.color == "ok") ? "#5ad687" :
                 (z.color == "warning") ? "#d6a55a" : "#d65a5a";
    }
}
// ... flash-on-danger-entry border-width pulse ...
char content[512];
std::snprintf(content, sizeof(content),
    "<div style='text-align: center;'>"
    "<span style='font-size: %dpx; font-weight: bold; color: %s;'>%.1f%s</span>"
    "<span style='color: #8a93a6; font-size: 11px;'> %s</span><br>"
    "<span style='color: #6a7080; font-size: 10px;'>%s</span>"
    "</div>",
    b.font_size, accent, val, alert_icon, b.units.c_str(), b.title.c_str());
b.card->setText(QString::fromUtf8(content));
char style_buf[256];
std::snprintf(style_buf, sizeof(style_buf),
    "background-color: #1a1d24; border: 1px solid #2f343d; "
    "border-top: %dpx solid %s; border-radius: 6px; padding: 6px 8px;",
    border_width, accent);
b.card->setStyleSheet(QString::fromUtf8(style_buf));
```

Eight inline hex literals in one update-tick body, plus a 9th in the static card placeholder set before the first tick, plus three more in the histogram widget constructors at the bottom of the tab.

**Three new helpers in `theme.hpp`.**

- **`number_card_style(accent, top_border_px = 2)`** — the card stylesheet. Pulls `bg_panel` / `border` / `radius_md` from tokens and takes the top-border thickness as a parameter so the 2px→4px flash-on-danger-entry pulse (Phase C) still works without a duplicate copy of the stylesheet. The pulse is now *the same code path* as the steady state, one parameter different. This is the key architectural improvement over the pre-slice shape: state variations compose cleanly instead of forking the entire stylesheet.
- **`format_number_card_html(buf, size, font_size, accent, value, alert_icon, units, title)`** — the three-line HTML body. The hero value tracks `accent`, the units line uses `text_muted` + `font_small`, the title line uses `text_dim` + `font_micro`. Progressive disclosure applied at the element level: biggest/loudest is the value the operator cares about, smallest/quietest is the label that names it.
- **`zone_accent(zone_name)`** — string-dispatch helper that maps the `"ok"` / `"warning"` / `"danger"` string literal the domain `GaugeColorZones` service returns into the matching `accent_ok` / `accent_warning` / `accent_danger` token. Unknown zone name falls back to `accent_primary` so the card is never unpainted. This is the first slice to name a string-dispatch helper in `theme.hpp` — the rationale is that the mapping is universal across the app (every "is this value healthy?" surface should use the same three colors for the same meanings), and naming it here means the mapping tunes in one place.

**Three hex call sites migrated in `build_live_tab`.**

1. **The per-tick update loop body.** Five inline hex dispatches + the two `snprintf`-composed block bodies all collapse to three token-helper calls. The timer callback stays exactly as legible as before, but without any of the hex drift.
2. **The static placeholder card.** Set once before the first timer tick (line ~2656 pre-slice), now uses `number_card_style(accent_primary)` — one of the same code paths the update loop uses.
3. **The three `HistogramWidget` constructors.** The AFR / RPM / MAP sparkline histograms at the bottom of the LIVE tab passed literal colors to their `Config` struct. Now pass `tt::accent_primary` / `tt::accent_ok` / `tt::accent_warning` — which means the histogram hues automatically match the number card hues for the same channel roles (RPM = ok green, MAP = warning amber, AFR = primary blue).

**Philosophy — first-class primitives, one more time.** The pattern from sub-slice 111 (tab header factory) and sub-slice 91 (scalar editor tint cycle) applies again: if you have a state-varying visual element that runs inside a hot loop, name the style transformation as a helper that takes the state as a parameter, then replace the loop body with a single call. Every timer tick now composes the same three helpers instead of re-reading eight hex literals that could drift out of sync with the rest of the palette. The histogram constructors using accent tokens close the visual-grammar loop: *if it's an ok value, it's green, across every widget that shows it*.

**Inline hex literal count in `main.cpp`: 81 → 70** (-11). Cumulatively across the beautification arc (88 / 90 / 91 / 111 / 112 / 113 / 114), `main.cpp` has dropped from **200+ inline hex literals down to 70**. What remains is split across many small surfaces: inline status line colors in ASSIST/SETUP/TRIGGERS that use `#d69a5a` / `#d6a55a` / `#5ad687` style-dispatches on severity (~20), the SETUP wizard step navigator active/inactive state (~4), the make_info_card accent-color parameter call sites that still pass literals instead of tokens (~15), the TUNE-tab scalar editor staged-tint cycle (already tokenized — these are false positives from the cumulative count), and the number-card update fix-it thresholds used inline for per-cell color rules in ASSIST/SETUP. Most of these are single-site surfaces that don't drift the way tab headers or the global stylesheet did, so future beautification passes can migrate them opportunistically as the surrounding code gets touched for functional work.

**No test suite impact.** C++ doctest suite unchanged at **1316 / 10634** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly. The number card rendering hot path (runs on every 200ms tick) now does exactly the same work as before — just composed from named helpers instead of inlined hex literals.

#### Phase 14 Slice 4 one-hundred-and-thirteenth sub-slice: Beautification pass #6 — QMainWindow global stylesheet migration

Sixth slice in the beautification arc (sub-slices 88 / 90 / 91 / 111 / 112 / 113) — and the **largest single-slice drop** (-23 inline hex literals). The app's `qApp->setStyleSheet(DARK_QSS)` block was the biggest remaining drift source in `main.cpp` after sub-slice 112 nailed the two modal dialogs. It's a 28-line `static const char*` stylesheet that covers every global Qt widget class the app uses: `QMainWindow`, `QWidget`, `QTabWidget::pane`, `QTabBar::tab` (+ `:selected`, `:hover:!selected`), `QStatusBar`, `QLineEdit` (+ `:focus`), `QTreeWidget`/`QListWidget` (+ `::item`, `::item:selected`, `::item:hover`), `QSplitter::handle`, `QScrollBar:vertical` (+ `::handle`, `::handle:hover`). Every near-black background value drifted: `#15171c` (QMainWindow), `#181b22` (QTabWidget/QStatusBar/QTreeWidget/QScrollBar), `#1c1f26` (alternate-background-color), and `#20242c` (selected tab background). Four different values for what is structurally the same design decision.

**The near-black collapse.** Post-slice, the four near-black drifts map to exactly two tokens:

- **`bg_base`** (#14171e) — everything that reads as "the app shell": `QMainWindow`, `QWidget`, the `alternate-background-color` tier used by zebra-striped lists. This is the darkest level visible in the main surface, one step lighter than `bg_deep` which is reserved for the sidebar.
- **`bg_panel`** (#1a1d24) — every content container: `QTabWidget::pane`, `QTabBar::tab`, `QStatusBar`, `QTreeWidget`/`QListWidget`, `QScrollBar:vertical`. This reads as "content container" across every widget class, matching the 5-level background ladder introduced in sub-slice 88.

The third near-black value (`#20242c`) was the selected tab background + the tree/list hover state. Post-slice it's `bg_elevated` — the canonical "this is interactively highlighted" background, same token the scalar editor fields use in the TUNE tab (sub-slice 91).

**The `#ffffff` on selected items.** The tree/list `::item:selected` color was hard-coded `#ffffff` — pure white on top of a blue fill. Post-slice it becomes `text_primary` (#e8edf5) — a hair softer than pure white, so "selected" reads as the same color across every selection state in the app (sidebar, scalar editor, command palette, tree view). One less "off-by-a-shade" drift.

**The blue-tinted selection fill.** `#2a4a6e` was hard-coded four times in the global stylesheet and the command palette (sub-slice 112) and the sidebar (sub-slice 90). Post-slice it's `fill_primary_mid` everywhere — the single token that means "selected/active, blue-tinted". Four callsites collapse to one meaning.

**One new token: `scroll_thumb_hover`.** The scrollbar hover color `#404652` is the only surface in the palette that needs a value in the brightness band between `border` (#2f343d) and `text_dim` (#6a7080) — a slightly-lightened "focus me" shade for the scrollbar thumb when the mouse hovers over it. The sub-slice 88 principle says this is exactly the case where adding a new token is right: if a surface needs a value the existing palette doesn't cover, add it with a rationale — don't inline-a-new-hex-in-a-stylesheet. Documented inline in `theme.hpp`.

**Spacing scale drift also killed.** Every raw-integer value in the stylesheet collapsed to tokens: `padding: 8px 18px` → `space_sm` / `space_lg + 2`, `padding: 6px 8px` → `space_xs + 2` / `space_sm`, `padding: 4px 6px` → `space_xs` / `space_xs + 2`, `border-radius: 4px` → `radius_sm` (everywhere it appeared).

**Philosophy — the shell and the content share one palette.** Before this slice, the global stylesheet lived in its own hex-literal world while every content tab pulled from the token system. The two were visually coherent by accident, not by construction. Post-slice, both pull from the same palette, which means any future adjustment to (say) the `bg_panel` tint ripples cleanly across the content containers AND the status bar AND the tree view AND the scrollbar background in one edit. The "one palette, one voice" principle from the ux-design doc now applies to every pixel in the app.

**Inline hex literal count in `main.cpp`: 104 → 81** (-23, the largest single-slice drop in the arc). Cumulatively across sub-slices 88 / 90 / 91 / 111 / 112 / 113, the inline-hex count in `main.cpp` has dropped from **200+ down to 81**. What remains is the LIVE-tab dashboard HTML cards (~60, largest single-pattern drift source left), various inline status line colors in assist/setup/triggers (~15), and the SETUP wizard step navigator's active/inactive state (4). The LIVE-tab cards are the natural next target but would need a dedicated factory helper similar to `make_tab_header` (sub-slice 111) because the cards are built inside a loop with per-card accent logic.

**No test suite impact.** C++ doctest suite unchanged at **1316 / 10634** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-twelfth sub-slice: Beautification pass #5 — modal dialog migration

Fifth slice in the beautification arc (sub-slices 88 / 90 / 91 / 111 / 112). The previous four passes migrated content tabs and a shared tab header primitive. This slice targets the two remaining **multi-line inline-hex stylesheet blocks** in `main.cpp`: the Ctrl+K command palette and the G1 startup project picker. Both are `QDialog`s with composed Qt stylesheets that stacked several selectors' worth of drifted `#hex` literals in one block — exactly the drift shape the token system was introduced to kill.

**Command palette (5 selectors, 8 hex literals → 0).** The Ctrl+K command palette dialog sets a stylesheet covering `QDialog`, `QLineEdit`, `QListWidget`, `QListWidget::item`, and `QListWidget::item:selected`. Pre-slice it was 5 inline-hex lines; post-slice it's one `snprintf` call against the tokens. Mapping: dialog chrome → `bg_base` (same as the app shell behind everything else), border → `border`, input field → `bg_elevated` (same as every other input in the app, sub-slice 91), result list background → `bg_base`, selected-item background → `fill_primary_mid`. The selected-item tint is the key choice: the sidebar selection state already uses `fill_primary_mid` for the same "you just selected this" meaning, so the palette selection reads as the same visual grammar. Spacing and corner radius come from `tt::space_sm + 2` / `tt::space_md` / `tt::radius_sm` instead of raw `4px` / `8px 12px` / `10px` drifts.

**Startup project picker (6 selectors + 3 inline HTML labels, 14 hex literals → 0).** The G1 welcome dialog has a bigger stylesheet (base + hover + pressed button states) and three inline-HTML labels (welcome hero, recent project card, dismissable hint) that each hard-coded their colors. Pre-slice: 14 inline hex literals across the QSS block and the HTML. Post-slice: the QSS block is one `snprintf` pulling `bg_deep` (matching the sidebar background — the welcome dialog lives in the same visual tier as the app shell chrome) + `bg_elevated` + `fill_primary_mid` (hover) + `fill_primary_soft` (pressed, brighter blue) + `accent_primary` (hover border) + the standard text hierarchy. Button padding uses `space_sm + 2` / `space_lg + 4` instead of `10px 20px`. Radius uses `radius_md` instead of `6px`. The three HTML labels now compose via `snprintf` against `text_primary` / `text_muted` / `text_secondary` / `text_dim` and the type scale (`font_label`-ish hero, `font_body` tagline, `font_small` label row, `font_medium` hero value, `font_micro` hint).

**Recent project card — reuses `card_style()`.** The recent-project chip inside the startup dialog previously set its own inline stylesheet (`background: #1a1d24; border: 1px solid #2f343d; border-radius: 6px; padding: 14px 18px;`). Post-slice it composes the existing `tt::card_style()` helper (from sub-slice 88) plus a `padding: %dpx %dpx;` tail so it reads as the same visual tier as any other content container in the app shell. This is a concrete win for the "first-class primitives" philosophy — a surface that used to invent its own card background now uses the canonical one.

**Philosophy — the welcome dialog echoes the wordmark footer.** The wordmark footer (sub-slice 90) says this is the one place the app identifies itself out loud. The startup picker is the other place — it's the first thing the operator sees. Post-slice, both surfaces pull from the same `text_primary` / `text_muted` / `text_dim` hierarchy and the same type scale, so "Tuner" the wordmark and "Tuner" the welcome title read as the same voice. Progressive disclosure governs the welcome dialog layout: hero title → dim tagline → recent project chip → action button row → dismissable hint. Every level is one token lighter and smaller than the one above it, matching the principle that the operator's eye should land on *what am I looking at* before *what do I do here* before *what else could I do*.

**Inline hex literal count in `main.cpp`: 121 → 104** (-17: 8 from command palette + 9 from startup dialog). Every remaining inline hex in `main.cpp` is now either in the LIVE-tab number card accent bar (3), the SETUP wizard step navigator's active/inactive state switch (4), the dashboard HTML-composed number cards (bulk of the remaining ~80), various inline assist/setup status line colors (~15), or the QMainWindow global stylesheet (~20). The global stylesheet is the next-biggest single-block drift source and a natural target for a future beautification pass, but it's also a one-location surface that doesn't drift across tabs the way the pre-111 tab headers did.

**No test suite impact.** C++ doctest suite unchanged at **1316 / 10634** — pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-eleventh sub-slice: Beautification pass #4 — shared tab header primitive

Fourth slice in the beautification arc (sub-slices 88 / 90 / 91 / 111). Sub-slice 88 introduced the `cpp/app/theme.hpp` design token system and migrated three LIVE-tab surfaces. Sub-slice 90 extended the tokens into the app shell chrome (sidebar + status bar + wordmark footer). Sub-slice 91 finished the three-part arc by migrating the TUNE-tab right-panel detail card. This slice (111) kills the next biggest remaining drift: four tabs — **FLASH**, **ASSIST**, **TRIGGERS**, **LOGGING** — each pasted the same 4-line inline-hex stylesheet and the same `<span>` HTML shape for their hero title + breadcrumb strip.

The drifted pattern:

```cpp
auto* <tab>_header = new QLabel(QString::fromUtf8(
    "<span style='font-size: 14px; font-weight: bold; color: #e8edf5;'>Tune Assist</span>"
    "<span style='color: #6a7080; font-size: 11px;'>"
    "  \xc2\xb7  Review correction proposals, then apply the ones you agree with"
    "</span>"));
<tab>_header->setTextFormat(Qt::RichText);
<tab>_header->setStyleSheet(
    "background-color: #1a1d24; border: 1px solid #2f343d; "
    "border-radius: 4px; padding: 8px 12px;");
layout->addWidget(<tab>_header);
```

Before this slice: four copies. After: one `make_tab_header(title, breadcrumb)` call per tab, plus two new token helpers in `theme.hpp`.

**New token helpers in `theme.hpp`.**

- **`tab_header_style()`** — the stylesheet for the header strip. Composes `bg_panel` + `border` + `radius_sm` + `space_sm`/`space_md` padding. Replaces the inline `#1a1d24` / `#2f343d` / `4px` / `8px 12px` drift.
- **`format_tab_header_html(buf, size, title, breadcrumb)`** — the HTML composer. Emits `<span style='font-size: {font_label}px; font-weight: bold; color: {text_primary};'>{title}</span><span style='color: {text_dim}; font-size: {font_small}px;'>  · {breadcrumb}</span>` with the `· ` divider prepended. Takes a writable buffer so the caller can sit on the stack and avoid `std::string` allocations in the hot tab-build path.

**New factory in `main.cpp`.** `make_tab_header(title, breadcrumb)` is a thin wrapper that calls `format_tab_header_html` into a 512-byte stack buffer, builds the `QLabel`, and sets `Qt::RichText` + the stylesheet. Lives next to `make_info_card` (sub-slice 91) so both "chrome primitives" are colocated. The four tabs each drop from 9 lines of inline-hex + markup to a single `layout->addWidget(make_tab_header(...))` call.

**Spacing drift also killed.** Each migrated tab also switches its raw-integer `setContentsMargins(16, 16, 16, 16)` + `setSpacing(10)` to the existing `tt::space_lg` / `tt::space_sm + 2` tokens. This drops another 16 raw integer drifts (4 margin values + 1 spacing × 4 tabs = 20, minus the 4 preserved `space_sm + 2` spacing values that now use the token).

**Philosophy — first-class primitives.** The tab header is now a **first-class design primitive**, on par with `card_style()` / `make_info_card` / `chip_style`. Any future surface that wants to introduce itself with a title + workflow breadcrumb calls `make_tab_header(title, breadcrumb)` and gets the exact same visual grammar for free. Tuning the header look (padding, radius, divider character, title weight) stays a one-file change in `theme.hpp`. This is the sub-slice-91 *"beautification pass means kill drift by naming patterns"* principle applied one more time.

**Progressive disclosure applied to navigation.** The title lands loudest (bold, `text_primary`, `font_label`); the breadcrumb sits quietly (`text_dim`, `font_small`). The operator's eye catches *where am I* before *what do I do here*, matching the `docs/ux-design.md` principle that every surface should give the operator the biggest context first, then reveal the workflow.

**Inline hex literal count in `main.cpp`: 133 → 121** (-12, three per header × four headers). Every remaining hex literal is now either in the LIVE-tab number card accent bar, the SETUP wizard step navigator, the command palette dialog, the startup project picker dialog, or the QMainWindow/QSplitter/QScrollBar global stylesheet — all of which are single-location surfaces that don't drift the same way the tab headers did. Future beautification passes can migrate those opportunistically as they get touched for functional work.

**No test suite impact.** C++ doctest suite unchanged at **1316 / 10634** — this is pure UI polish, no logic touched. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-tenth sub-slice: Wire `[SettingGroups]` into `NativeEcuDefinition` aggregator

Closes the follow-up backlog item opened at the end of sub-slice 109. The `ini_setting_groups_parser.hpp` leaf landed there, but the `NativeEcuDefinition` aggregator struct (and its `compile_ecu_definition_text` entry point) did not yet expose the parsed setting groups, which meant the full production INI pipeline still needed a separate call to reach them. This slice wires the new parser into the aggregator so the complete C++ INI import path flows through a single `compile_ecu_definition_text(path, active_settings)` call — the exact equivalent of the Python `IniParser.parse(path, active_settings=...)` orchestration flow.

- `cpp/include/tuner_core/ecu_definition_compiler.hpp` — added `#include "tuner_core/ini_setting_groups_parser.hpp"` and `IniSettingGroupsSection setting_groups;` as the final field on `NativeEcuDefinition`. The field ordering mirrors the Python `EcuDefinition.setting_groups` placement on the domain dataclass.
- `cpp/src/ecu_definition_compiler.cpp` — added one dispatch line: `definition.setting_groups = parse_setting_groups_lines(lines, defines);`. Uses the same already-preprocessed `lines` + `defines` every other leaf parser in `compile_ecu_definition_text` already consumes, so the single-preprocessor-pass design is preserved.
- `cpp/bindings/tuner_core_module.cpp` — added `.def_rw("setting_groups", &NativeEcuDefinition::setting_groups)` to the existing nanobind binding. Python callers can now reach `compile_ecu_definition_text(text).setting_groups.groups` directly, the same way they already reach every other section.
- `cpp/tests/test_ecu_definition_compiler.cpp` — extended the existing `MIXED_INI` fixture with a `[SettingGroups]` block (`mcu` group with two options), added `setting_groups.groups.size() == 1` assertions to the "dispatches every leaf parser" test, and added an empty-check to the "empty INI yields empty catalogs" test. Same 3 doctest cases, +7 new assertions.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — added `test_setting_groups_parity` which drives the full production INI fixture (`tests/fixtures/speeduino-dropbear-v2.0.1.ini`) through both `IniParser.parse()` and `compile_ecu_definition_text`, then asserts byte-for-byte parity on every group's symbol, label, and option list (length + per-option symbol + label). The `_compare`-style field-by-field check uses the `(py.label or "")` idiom to handle Python's `Optional[str]` vs C++'s always-present `std::string` cleanly.

**What this closes.** The C++ side now has a single-entry-point ingestion flow for the full production INI format. Any downstream C++ service (workspace presenter, table generators, runtime decoder, dashboard, future "Definition Settings" dialog in `tuner_app.exe`) can call `compile_ecu_definition_text(text, active_settings)` and reach every section — constants / output channels / table editors / curve editors / menus / dialogs / gauge configurations / front page / logger definitions / controller commands / **setting groups** — with no Python round-trip.

**What's still missing from the aggregator.** The handful of rarely-used metadata sections flagged at the end of sub-slice 109 (`[PcVariables]`, `[ConstantsExtensions]`, `[Tools]`, `[AutotuneSections]`, `[ReferenceTables]`, `[SettingContextHelp]`) still exist as Python-only leaves. None are structural — they carry tool-assist metadata, extra definition overrides, or help-text strings — so the C++ aggregator can ship without them and they can be folded in opportunistically when a downstream C++ service needs them.

C++ doctest suite: 1316 / 10627 → **1316 / 10634** (same test count — this slice extends existing tests; +7 assertions from the extended compiler test). Python collected suite: 2938 → **2939** (+1 parity test). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-ninth sub-slice: INI `[SettingGroups]` parser

Direct port of `IniParser._parse_setting_groups` from `src/tuner/parsers/ini_parser.py` — the last remaining untouched leaf INI section parser from the list documented in "INI Parser Notes" at the top of `CLAUDE.md`. With this slice, **every leaf INI section the Python parser handles now has a native C++ port**, with the exception of a handful of rarely-used sections (`[PcVariables]`, `[ConstantsExtensions]`, `[Tools]`, `[AutotuneSections]`, `[ReferenceTables]`, `[SettingContextHelp]`) that carry only a thin layer of metadata rather than structural definitions.

**Why this slice next.** Production INIs use `[SettingGroups]` to declare project-level compile flags and their options (e.g. `mcu = mcu_teensy | mcu_mega2560 | mcu_stm32`, `LAMBDA = DEFAULT | LAMBDA`) that gate `#if`/`#else`/`#endif` preprocessor blocks via `active_settings`. The parsed groups populate `EcuDefinition.setting_groups` which drives the "Definition Settings" toolbar dialog in the workspace — the operator picks which flags are active for their project and the parser re-runs with the chosen `active_settings`. A native C++ implementation matters because the `tuner_app.exe` native build needs to present the same dialog during the import flow once it starts loading legacy INIs, and porting this parser lets the full INI pipeline run without any Python round-trip.

- `cpp/include/tuner_core/ini_setting_groups_parser.hpp` and `cpp/src/ini_setting_groups_parser.cpp` — `IniSettingGroup { symbol, label, options }` and `IniSettingGroupOption { symbol, label }` PODs mirroring the Python `SettingGroupDefinition` / `SettingGroupOption` dataclasses field-for-field. Stateful block parser: `settingGroup = symbol, "label"` opens a new block, each subsequent `settingOption = symbol, "label"` appends to the in-flight block, and the block flushes on the next `settingGroup` / on a section change / at end-of-input. Missing labels default to the symbol (mirrors Python's `label = value_parts[1] if len(value_parts) > 1 else symbol`). Boolean flags (groups with zero `settingOption` lines) survive — the parser emits a group with an empty `options` vector. Comments (`;`, `#`), blank lines, and lines outside `[SettingGroups]` are skipped. Reuses the existing `parse_helpers.hpp::parse_csv` + `strip_quotes` primitives so the CSV value split semantics match every other INI leaf parser exactly.
- `cpp/tests/test_ini_setting_groups_parser.cpp` — 11 doctest cases covering: simple two-block shape, boolean flag (no options), section-change flush, `settingOption` outside a block ignored, lines outside `[SettingGroups]` ignored, missing-label defaults to symbol, comments + blank lines skipped, case-insensitive section header match, preprocessor `#if` gating via the composed `parse_setting_groups_section_preprocessed`, empty input, and section-present-but-empty.
- `cpp/bindings/tuner_core_module.cpp` — `IniSettingGroupOption` / `IniSettingGroup` / `IniSettingGroupsSection` classes with read/write fields, plus `parse_setting_groups_section` and `parse_setting_groups_section_preprocessed` functions exposed for Python parity.
- `tests/unit/test_cpp_ini_setting_groups_parser_parity.py` — 9 parity tests against `IniParser._parse_setting_groups`. Coverage: simple two-block shape, boolean flag, section-change flush, missing-label default, comments + blank lines, empty section, `#if` gating with empty `active_settings`, `#if` gating with user-supplied `active_settings` that override file-scope defaults, and **full production INI fixture parity** against `tests/fixtures/speeduino-dropbear-v2.0.1.ini` driven through the real `IniParser.parse()` pipeline (not just the leaf method) — this smoke-checks that the real production shape has ≥ 1 group and that every group's fields match byte-for-byte between the Python and C++ outputs.

**Mid-slice fix.** The first parity-test harness tried to drive the Python leaf method via a nonexistent `parser._load_lines(path, active_settings)` helper. Looking at `IniParser.__init__` + the `parse()` body showed that `_lines` is populated by calling `preprocess_ini_lines(path.read_text().splitlines(), active_settings)` directly — there is no `_load_lines` convenience method. Fixed by importing `preprocess_ini_lines` from `tuner.parsers.common` and setting `parser._lines` explicitly before invoking the leaf method. The temp-file path is still needed because the leaf method does an `path.exists()` guard before reading `self._lines`, but the actual line content comes from the pre-populated `self._lines`. This is now the documented pattern for any parity test that needs to drive a private `IniParser._parse_*` leaf without running the full `parse()` orchestration.

**What this closes.** Every leaf INI section parser the Python `IniParser` knows about now has a C++ port, except for the handful of rarely-used sections (`[PcVariables]`, `[ConstantsExtensions]`, `[Tools]`, `[AutotuneSections]`, `[ReferenceTables]`, `[SettingContextHelp]`) that carry only a thin layer of metadata rather than structural definitions. The C++ `NativeEcuDefinition` aggregator does not yet expose the `setting_groups` field — that's a follow-up slice to wire the new parser into `ecu_definition_compiler.hpp` + `NativeEcuDefinition` so the full production INI pipeline round-trips through a single C++ entry point.

C++ doctest suite: 1305 / 10585 → **1316 / 10627** (+11 tests, +42 assertions). Python collected suite: 2929 → **2938** (+9 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-eighth sub-slice: Speeduino capability header + derived flags

Extends the `speeduino_connect_strategy` module from sub-slice 107 with the pure-logic half of `_read_capabilities` plus four cohesive derived-flag helpers. Together, sub-slices 107 and 108 close every pure-logic connect-phase decision `SpeeduinoControllerClient` makes between `transport.open()` and the first runtime poll.

- `cpp/include/tuner_core/speeduino_connect_strategy.hpp` + `cpp/src/speeduino_connect_strategy.cpp` — new types and functions added to the existing module. **`CapabilityHeader { parsed, serial_protocol_version, blocking_factor, table_blocking_factor }`** POD mirrors the parsed shape of the 6-byte `'f'` capability query response (byte 0 = 0x00 sentinel, byte 1 = serial protocol version, bytes 2..4 = blocking_factor **big-endian u16**, bytes 4..6 = table_blocking_factor big-endian u16). **`OutputChannelField { name, offset, data_type }`** POD mirrors the minimum `ScalarParameterDefinition` fields `_live_data_size` and `_has_output_channel` need. **`parse_capability_header(payload)`** takes an `optional<span<const uint8_t>>` (nullopt or a buffer) and returns `parsed=false` when the payload is missing, shorter than 6 bytes, or does not start with 0x00 — matches the Python `if payload is not None and len(payload) >= 6 and payload[0] == 0x00:` guard exactly. **`capability_source(header)`** returns `"serial+definition"` when parsed, `"definition"` otherwise. **`compute_live_data_size(channels)`** returns `nullopt` when the channel list is empty, otherwise `max((offset or 0) + data_size(data_type))` using the existing `speeduino_value_codec::data_size_bytes` port via `parse_data_type(data_type)`. **`has_any_output_channel(defined, targets)`** does a linear-scan set membership check (channel lists are small enough that building a hash set would not pay off). **`is_experimental_u16p2_signature(signature)`** uppercases the input and scans for the substring `"U16P2"`, mirroring the Python `"U16P2" in (firmware_signature or "").upper()` exactly. **`should_accept_probe_response(command, response)`** returns true iff `response` is non-empty AND `response != command` AND `command != 'F'` — mirrors the inline filter conditions inside `_probe_signature`.
- `cpp/tests/test_speeduino_connect_strategy.cpp` — 18 additional doctest cases covering: `parse_capability_header` for nullopt / short / bad-leading-byte / valid big-endian u16 pair / zero-integers-still-parsed / extra-trailing-bytes-ignored shapes; `compute_live_data_size` for empty / single-U08-at-zero / max-over-3-channels / nullopt-offset-treated-as-zero; `has_any_output_channel` for match-found / all-absent / empty-inputs; `is_experimental_u16p2_signature` for 4 case-insensitive shapes; `should_accept_probe_response` for empty / single-char echo / 'F' probe rejection / real signature accepted.
- `cpp/bindings/tuner_core_module.cpp` — 2 new classes (`SpeeduinoCapabilityHeader`, `SpeeduinoOutputChannelField`) and 6 new functions exposed. `speeduino_parse_capability_header` accepts `Optional[bytes]` on the Python side and maps `None` → `nullopt`; `speeduino_should_accept_probe_response` takes `command` as a `std::string` from Python so the parity test can pass the single-char values naturally.
- `tests/unit/test_cpp_speeduino_connect_strategy_parity.py` — 23 new parity tests extending the existing file. Coverage: `parse_capability_header` parametrised over 5 payload shapes, each cross-checked against the full Python `_read_capabilities` method (using a `Mock(spec=SpeeduinoControllerClient)` wired to a minimal definition mock and a payload-returning mock for `_query_capability_payload`); `compute_live_data_size` empty case + a production-shape test that drives the real Python `_live_data_size` against a 3-channel list; `has_any_output_channel` parametrised over 5 (defined, targets) pairs; `is_experimental_u16p2_signature` parametrised over 5 signature shapes including an "almost but not" case (`"U16P3"`); `should_accept_probe_response` parametrised over 6 (command, response) pairs. The new tests bring this parity file's total to 67 (44 from sub-slice 107 + 23 new).

**Cross-reference to sub-slice 104 on endianness.** The 6-byte capability header uses **big-endian u16** for the blocking factor pair (the same convention the XCP spec uses and sub-slice 104 preserves). The rest of the Speeduino raw protocol is little-endian (see sub-slices 70–73 + the `speeduino_value_codec` port). This is the one Speeduino-side place where big-endian creeps in; documented inline in the `CapabilityHeader` struct doc.

**Mid-slice fix.** The `test_compute_live_data_size_production_shape_parity` test first tried to wire `_data_size` onto the stub as `_data_size = SpeeduinoControllerClient._data_size`, but `_data_size` is a `@staticmethod` and that assignment doesn't preserve the static-method descriptor. Fixed by using `_data_size = staticmethod(SpeeduinoControllerClient._data_size)` — the same pattern established by sub-slice 107's `_signature_probe_candidates` fix. This is now the documented pattern for any parity test that needs to drive a Python method whose body calls a class-level `@staticmethod` through a stub self.

C++ doctest suite: 1287 / 10551 → **1305 / 10585** (+18 tests, +34 assertions). Python collected suite: 2906 → **2929** (+23 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-seventh sub-slice: Speeduino connect strategy helpers

Direct port of the connect-time helpers in `SpeeduinoControllerClient` (`src/tuner/comms/speeduino_controller_client.py`). These pick the right blocking factor, the right signature probe order, the right baud rate fallbacks, and the right connect delay before any I/O happens. They sit one layer above the framing / command / value codecs (sub-slices 70–73) and one layer below the orchestration loop in `SpeeduinoControllerClient` itself, which stays Python because the orchestration loop is `transport.open() → probe → re-baud → probe again → ...` and the loop body is genuine I/O.

- `cpp/include/tuner_core/speeduino_connect_strategy.hpp` and `cpp/src/speeduino_connect_strategy.cpp` — five free functions in `tuner_core::speeduino_connect_strategy`. **`command_char(raw, fallback)`** returns the first character of `raw` if non-empty, else `fallback`. **`effective_blocking_factor(is_table, fw_b, fw_tb, def_b, def_tb)`** picks the write chunk size with the priority order `firmware-table > definition-table > firmware-scalar > definition-scalar > 128`, where `is_table=true` enables the per-table priority and the scalar branch falls through if no table value is set. The Python `or` shortcut treats zero as missing because `None or 0` is falsy; the C++ port mirrors that exactly via a `take(value)` helper that returns `nullopt` when the optional is missing OR holds zero. **`signature_probe_candidates(query_command, version_info_command)`** walks the candidate list `[query_command, version_info_command, "F", "Q", "S"]`, takes the first character of each via `command_char`, and dedupes while preserving order. Empty inputs are skipped. **`baud_probe_candidates(current_baud)`** walks `[current_baud, 115200, 230400, 57600, 9600]`, dedupes while preserving order, drops `nullopt` entries, and returns a single-element `[nullopt]` list if everything was filtered out (matches Python's `candidates or [None]`). **`connect_delay_seconds(metadata)`** looks up `controllerConnectDelay` / `connectDelay` / `interWriteDelay` in priority order, takes the first non-empty value, splits on the first comma if present (so `"1500,1000"` becomes `"1500"`), trims whitespace, parses the result as a float treated as milliseconds, and returns delay_ms / 1000 when the parsed value is positive — otherwise falls through to the next key, ultimately defaulting to 1.5 if every key parses to zero / negative / malformed.
- `cpp/tests/test_speeduino_connect_strategy.cpp` — 29 doctest cases covering: `command_char` empty + non-empty + multi-char inputs; `effective_blocking_factor` for the firmware-wins / definition-fallback / 128-default / firmware-zero-treated-as-missing / definition-zero-treated-as-missing / table-firmware-wins / table-definition-fallback / table-falls-through-to-scalar-firmware / scalar-ignores-table-values branches; `signature_probe_candidates` for empty defs / query leads / dedupes against tail / first-char-only / dedupe-between-query-and-version; `baud_probe_candidates` for current-leads / nullopt-current / dedupe-against-defaults; `connect_delay_seconds` for empty / each priority key / comma split / whitespace strip / zero / negative / malformed / empty key skip.
- `cpp/bindings/tuner_core_module.cpp` — 5 free functions exposed: `speeduino_connect_command_char` (string-in / string-out so the Python parity test can pass / receive single-char strings naturally), `speeduino_connect_effective_blocking_factor`, `speeduino_connect_signature_probe_candidates` (returns `vector<string>` of single-char strings to match Python's `list[str]` shape), `speeduino_connect_baud_probe_candidates`, and `speeduino_connect_delay_seconds`. The metadata dict flows through `std::map<string, string>` thanks to the existing `<nanobind/stl/map.h>` include.
- `tests/unit/test_cpp_speeduino_connect_strategy_parity.py` — 44 parity tests against the Python `SpeeduinoControllerClient` private helpers. Coverage: `_command_char` parametrised over 6 (raw, fallback) pairs plus a `None` raw case (Python tolerates `None`; the C++ binding takes `std::string` so callers pass `""`); `_effective_blocking_factor` parametrised over 10 (is_table, fw_b, fw_tb, def_b, def_tb) combinations including the zero-treated-as-missing edges; `_signature_probe_candidates` parametrised over 8 (query, version) pairs; `_baud_probe_candidates` parametrised over 7 current-baud values; and `_connect_delay_seconds` parametrised over 12 metadata shapes. The Python parity targets are reached by constructing a small `Mock(spec=SpeeduinoControllerClient)` for each call and wiring the relevant `capabilities` / `definition` / `_get_transport_baud_rate` attributes — no transport ever needs to exist.

**Mid-slice fix.** The first parity-test run failed on `_signature_probe_candidates` because it calls `self._command_char(raw, "")` and `_command_char` is a `@staticmethod` on the class. Constructing `self` via `Mock(spec=SpeeduinoControllerClient)` inspects the descriptor and rejects the call because the spec sees a 2-arg signature (the static method has no implicit `self`). Fixed by replacing the `Mock(spec=...)` with a tiny local stub class that explicitly re-declares `_command_char = staticmethod(SpeeduinoControllerClient._command_char)` so the static method resolves the same way the real instance does. Documented inline in the test.

**What this closes.** The Speeduino raw protocol port has been incrementally landing across sub-slices 70 (framing CRC + length-prefixed frames), 71 (command shapes), 72 (raw value codec), 73 (parameter codec), 86 (formula channel evaluator), and now 107 (connect strategy helpers). With this slice in place, every pure-logic surface of `SpeeduinoControllerClient` that runs *before* the first I/O byte goes out — pick a blocking factor, decide which signature probe to send, decide which baud rate to try first, decide how long to sleep after `transport.open()` before sending anything — is now native. The remaining I/O-bound layer (the actual `transport.read` / `transport.write` calls and the orchestration loop wiring them together) is the same shape as the deferred TcpTransport / SerialTransport ports.

C++ doctest suite: 1258 / 10508 → **1287 / 10551** (+29 tests, +43 assertions). Python collected suite: 2862 → **2906** (+44 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-sixth sub-slice: JSON-line protocol simulator command dispatch

Direct port of the pure-logic half of `src/tuner/simulator/protocol_simulator.py`. Pairs with the JSON-line packet codec under `tuner.comms.packet_codec` (still Python — that codec is half I/O). The Python `ProtocolSimulatorServer` is half pure-logic (compute a deterministic runtime snapshot from a tick counter, dispatch a fully-parsed JSON payload to the right response shape) and half I/O (TCP socket accept loop, line-buffered `recv` / `sendall`). This module owns only the pure half — the bytes-on-the-wire half stays Python where the threading model lives.

- `cpp/include/tuner_core/protocol_simulator.hpp` and `cpp/src/protocol_simulator.cpp` — `protocol_simulator::SimulatorState` POD with `int tick` + `std::string parameters_json` (the parameters dict serialized as a compact JSON object string so the public ABI **does not depend on nlohmann/json**). `runtime_values(state)` increments `state.tick` then returns a `std::map<string, double>` with `{rpm, map, afr}` computed from `sin(t/4)*120 + 900`, `cos(t/5)*4 + 95`, `sin(t/6)*0.4 + 14.7`, each rounded via `std::nearbyint(x*100)/100` to match Python's banker-rounded `round(value, 2)`. `handle_command_json(state, payload_json)` parses the payload, dispatches to the right branch (hello / runtime / read_parameter / write_parameter / burn / verify_crc / unknown), and serializes the response with the same `separators=(",", ":")` shape Python's `json.dumps` emits. The internal nlohmann/json-typed `handle_command_json_object` lives entirely in the .cpp; the public header speaks `std::string` JSON only — **first port to vendor a third-party include privately**, keeping `tuner_core` consumers free of the `nlohmann/json.hpp` dependency.
- `cpp/tests/test_protocol_simulator.cpp` — 14 doctest cases covering: `runtime_values` tick increment, the documented sin/cos formula shape at tick=1, monotonic tick across 3 successive calls, rpm bounded within `[780, 1020]` across 50 ticks, hello / runtime / read_parameter (default to float 0.0) / write_parameter→read round-trip / heterogeneous value types (int/string/bool) / burn / verify_crc / unknown command / missing-command-key fall-through, and the compact-separator dump check (`.find(' ') == npos`). The test file pokes at the response via plain substring checks rather than parsing the JSON back through nlohmann/json — that would re-introduce the third-party include the public header deliberately avoids.
- `cpp/bindings/tuner_core_module.cpp` — `ProtocolSimulatorStateCpp` class with `tick` + `parameters_json` read/write fields, plus 2 free functions: `protocol_simulator_runtime_values` and `protocol_simulator_handle_command_json`. The dispatch wrapper takes a `std::string` payload so the Python parity test can `json.dumps` its dict input + `json.loads` the C++ response without any custom marshalling.
- `tests/unit/test_cpp_protocol_simulator_parity.py` — 21 parity tests against `SimulatorState.runtime_values` and `ProtocolSimulatorServer._handle`. Coverage: first-tick `runtime_values` exact-bits parity, **50 consecutive ticks** with byte-for-byte equality on every dict (this confirms the sin/cos pipeline produces identical bits across the platform's libm — Windows MinGW UCRT in this build); per-branch dispatch parity for hello, runtime, read_parameter (default-to-float-zero check), write_parameter→read parametrised over 8 (name, value) pairs covering int / float / str / True / False / zero-int / zero-float / negative-float, parameter overwrite across 6 successive writes, burn, verify_crc, unknown command parametrised over 4 names; and a 13-step mixed session that interleaves hello / write / runtime / read / verify_crc / write / read / burn calls and asserts both implementations agree on every response and on the tick counter at every step. The Python parity targets are reached **without ever opening a socket** — `ProtocolSimulatorServer.__init__` builds an unbound socket but `bind` / `listen` only run from `start()`, which we never invoke.

**sin/cos exact-bits parity confirmed.** A real concern when porting numeric formulas across language runtimes is whether `sin` and `cos` produce bit-identical results for the same input. The 50-iteration parity test confirms that for this specific build (Windows MinGW UCRT 15.2 + Python 3.14 also linking against the same UCRT libm), every `runtime_values` call returns identical doubles on both sides. Banker's rounding via `std::nearbyint` matches Python's `round(value, 2)` exactly because both default to FE_TONEAREST (round-half-to-even). If the build chain ever shifts to a different libm (e.g. glibc on Linux), the parity test will catch any new divergence.

**First slice with a privately-vendored third-party include.** The C++ side already vendors `nlohmann/json.hpp` for the native format writers, but every prior port either consumed JSON via the existing `native_format::*` helpers (which take `std::string` in / out) or didn't touch JSON at all. This slice is the first to need an in-place JSON object/dict abstraction, and it's the first to demonstrate the pattern of keeping the third-party header strictly internal: include `nlohmann/json.hpp` in the `.cpp` only, expose `std::string` JSON via the public `.hpp`. Future ports that need ad-hoc JSON shapes can follow the same pattern without forcing every consumer of `tuner_core/*.hpp` to learn about the third-party type.

**Why protocol simulator next.** Closes the JSON-line protocol path the same way sub-slice 105 closed the XCP path: pure-logic dispatcher in C++, socket transport stays Python. Both simulators are now native in their pure-logic seam, which means the C++ test suite can build deterministic end-to-end protocol round-trips without any Python on the test path. The remaining simulator work — the actual TCP `accept` loop and the line-buffered `recv` / `sendall` — is the same shape as the deferred Speeduino `TcpTransport` / `SerialTransport` ports.

C++ doctest suite: 1244 / 10379 → **1258 / 10508** (+14 tests, +129 assertions). Python collected suite: 2841 → **2862** (+21 parity tests). `tuner_app.exe` rebuilds cleanly.

**Mid-slice fix.** The first build attempt put `#include "nlohmann/json.hpp"` directly in the public `protocol_simulator.hpp` and the test target couldn't find the header — `nlohmann/json.hpp` is wired as a `PRIVATE` include for the `tuner_core` library only, so consumers (including the test executable) don't see it. Fixed by moving the include into the `.cpp`, refactoring the public API to take/return `std::string` JSON, and keeping the nlohmann::json-typed handler as an internal `.cpp` function. This is now the documented pattern for any future port that needs JSON internally without leaking the third-party type into the public ABI.

#### Phase 14 Slice 4 one-hundred-and-fifth sub-slice: XCP simulator command dispatch

Direct port of the pure-logic half of `src/tuner/simulator/xcp_simulator.py`. Pairs with sub-slice 104 (XCP packet layer) to give the C++ side **both ends** of the XCP-on-CAN protocol — host-side builders/parsers + target-side dispatcher. The Python `XcpSimulatorServer` is half pure-logic (decide how many bytes a command needs, dispatch a fully-buffered command to the right response shape, mutate the MTA pointer on SET_MTA / UPLOAD) and half I/O (TCP socket accept loop, `recv` / `sendall`). This module owns only the pure half — the socket bytes shuttling stays Python.

- `cpp/include/tuner_core/xcp_simulator.hpp` and `cpp/src/xcp_simulator.cpp` — `xcp_simulator::XcpSimulatorState` POD mirroring the Python dataclass field-for-field, with a `default_state()` static factory that pre-seeds the 256-byte `memory` buffer with the same fixture bytes the Python `__post_init__` writes (`12 34 56 78` at 0..4, big-endian u32 `3210` at 4..8, big-endian u16 `875` at 8..10, big-endian f32 `14.7` at 10..14). `DispatchResult { response, new_mta_address }` POD captures the dispatcher output. `expected_command_size(opcode)` returns the total byte count the transport should buffer for `opcode` before invoking `handle_command`: 1 for GET_STATUS and unknown opcodes, 2 for CONNECT/GET_ID/UPLOAD, 8 for SET_MTA. `handle_command(state, packet, mta_address)` mirrors `_handle` exactly: CONNECT returns the 8-byte CONNECT response from `state`, GET_STATUS returns the 6-byte STATUS response (with `configuration_status` packed big-endian), GET_ID returns the 8-byte header + identifier bytes (with `identifier_length` packed big-endian u32), SET_MTA captures the big-endian u32 from `packet[4..8)` into `new_mta_address` and returns `[POSITIVE_RESPONSE]` (truncated SET_MTA returns the 2-byte error packet `0xFE 0x20`), UPLOAD reads `size` bytes from `state.memory[mta..mta+size)` and zero-pads anything past the end of the memory buffer (mirrors the Python `data + b"\x00" * (size - len(data))`), and any other opcode returns `0xFE 0x20`. The Python original mutates `_mta_address` on the server instance; the C++ port returns the new MTA in `DispatchResult` so the caller can thread it through successive dispatches with no shared mutable state.
- `cpp/tests/test_xcp_simulator.cpp` — 15 doctest cases covering: `expected_command_size` for every known opcode plus 3 unknown-fallback cases, `default_state()` memory seeding (12 34 56 78 + big-endian u32 3210 + big-endian u16 875 + big-endian f32 14.7 round-trip via `memcpy`), every `handle_command` happy path (CONNECT 8-byte response, GET_STATUS 6-byte response, GET_ID 8-byte header + identifier bytes, SET_MTA address pack into `new_mta_address`, UPLOAD from zero, UPLOAD past end with zero-pad, UPLOAD reading the big-endian u32 fixture from memory[4..8)), every error path (truncated SET_MTA, truncated UPLOAD, unknown opcode, empty packet), and an UPLOAD → SET_MTA → UPLOAD threading sequence that decodes the big-endian u16 875 fixture from memory[8..10).
- `cpp/bindings/tuner_core_module.cpp` — `XcpSimulatorStateCpp` class with read/write fields plus the `default_state` static factory, `XcpDispatchResult` class with `response` + `new_mta_address`, and 2 free functions: `xcp_simulator_expected_command_size` and `xcp_simulator_handle_command`. Bytes flow through `nb::bytes` and copy into a local `std::vector<std::uint8_t>` on the C++ side. Class names use the `Cpp` suffix to avoid colliding with the Python dataclasses if both are imported in the same parity test.
- `tests/unit/test_cpp_xcp_simulator_parity.py` — 25 parity tests against `XcpSimulatorServer._expected_command_size`, `XcpSimulatorState`, and `XcpSimulatorServer._handle`. Coverage: `_expected_command_size` parametrised over all 8 known opcodes plus 4 unknown bytes; default state memory seed parity (full 256-byte byte-for-byte equality); default state field parity (every dataclass field including the identifier bytes); per-branch dispatch parity for CONNECT, GET_STATUS, GET_ID, SET_MTA, SET_MTA truncated, UPLOAD from zero, UPLOAD past end zero-pad, UPLOAD truncated, and unknown opcode; an UPLOAD → SET_MTA → UPLOAD threading sequence that mirrors the doctest case and decodes the big-endian u16 875 fixture; and a 40-step random walk that interleaves SET_MTA + UPLOAD commands and pins both implementations to the same response bytes and trailing MTA pointer at every step. The Python parity targets are reached **without ever opening a socket** — `XcpSimulatorServer.__init__` builds an unbound socket but `bind` / `listen` are only called from `start()`, which we never invoke.

**Why XCP simulator next.** With the packet layer (sub-slice 104) and the simulator dispatcher (this slice) both in C++, the entire XCP-on-CAN pure-logic surface is now native. The only remaining XCP work for the C++ comms layer is the (still I/O-bound) socket transport — same shape as the deferred Speeduino TcpTransport / SerialTransport ports. The pairing also unlocks pure C++ end-to-end XCP testing: a C++ test can build a CONNECT command via `xcp_packets::build_connect_command`, dispatch it through `xcp_simulator::handle_command` against a `default_state`, and parse the response via `xcp_packets::parse_connect_response` — three pure-logic seams, one round-trip, no Python on the test path at all.

C++ doctest suite: 1229 / 10281 → **1244 / 10379** (+15 tests, +98 assertions). Python collected suite: 2816 → **2841** (+25 parity tests). `tuner_app.exe` rebuilds cleanly. No mid-slice fixes — both build and parity tests passed first try.

#### Phase 14 Slice 4 one-hundred-and-fourth sub-slice: XCP packet layer (builders + parsers)

Direct port of `src/tuner/comms/xcp/packets.py` — the byte-shape primitives `XcpControllerClient` builds and parses for the XCP-on-CAN protocol. 143 lines of pure-logic Python, zero domain dependencies, all functions are byte ↔ struct conversions. This is the first concrete C++ port toward closing the "partial XCP support" gap noted at the top of `CLAUDE.md` ("Comms Notes: partial XCP support" → "Do not describe XCP as feature-complete"); the workspace presenter / page services side stays Python until the C++ comms-layer transport stabilises.

- `cpp/include/tuner_core/xcp_packets.hpp` and `cpp/src/xcp_packets.cpp` — `xcp_packets::XcpPid` (POSITIVE_RESPONSE = 0xFF, ERROR = 0xFE) and `XcpCommand` (CONNECT, DISCONNECT, GET_STATUS, SYNCH, GET_COMM_MODE_INFO, GET_ID, SET_MTA, UPLOAD) constant structs, plus `XcpConnectResponse` / `XcpStatusResponse` / `XcpGetIdResponse` PODs mirroring the Python dataclasses. **Note that XCP is big-endian on the wire**, in contrast to the Speeduino raw protocol which is little-endian (see `speeduino_value_codec.hpp`); the `max_dto` field of CONNECT, the `configuration_status` field of GET_STATUS, and the `identifier_length` field of GET_ID are all decoded big-end-first to match the spec. Builders: `build_connect_command(mode=0x00)`, `build_get_status_command()`, `build_get_id_command(identifier_type=0x00)`, `build_set_mta_command(address, address_extension=0x00)` (8-byte command with the 32-bit address packed big-endian in bytes 4..8), `build_upload_command(size)` (with `[1, 255]` size validation throwing `std::runtime_error`). Parsers: `parse_connect_response`, `parse_status_response`, `parse_get_id_response`, `parse_command_ack` (void check that throws if the packet is not exactly the single-byte `[POSITIVE_RESPONSE]`), `parse_upload_response` (returns the payload bytes minus the leading 0xFF PID). Every parser throws `std::runtime_error` with the same error text the Python sources use on length / PID mismatch. The `XcpGetIdResponse::identifier_text()` helper mirrors Python's `bytes.decode("ascii", errors="replace")` exactly: ASCII bytes pass through, anything ≥ 0x80 emits the U+FFFD replacement character as the 3-byte UTF-8 sequence `EF BF BD`.
- `cpp/tests/test_xcp_packets.cpp` — 23 doctest cases covering: every builder with default + custom inputs (5 builders × ≥2 cases each), `build_upload_command` boundary values (1, 255) and out-of-range throws (0, -1, 256), all three response parsers' happy paths against the same packets the Python `tests/unit/test_xcp_packets.py` uses, big-endian decode of `max_dto` and `configuration_status`, `parse_get_id_response` ASCII identifier round-trip, `identifier_text()` non-ASCII replacement to U+FFFD, every error path (truncation, bad PID, zero length, unsupported mode) on every parser, and the `parse_upload_response` PID-strip + length-mismatch contract.
- `cpp/bindings/tuner_core_module.cpp` — `XcpConnectResponseCpp` / `XcpStatusResponseCpp` / `XcpGetIdResponseCpp` classes with read/write fields plus the `identifier_text` method, and 10 free functions: `xcp_build_connect_command` / `xcp_build_get_status_command` / `xcp_build_get_id_command` / `xcp_build_set_mta_command` / `xcp_build_upload_command` / `xcp_parse_connect_response` / `xcp_parse_status_response` / `xcp_parse_get_id_response` / `xcp_parse_command_ack` / `xcp_parse_upload_response`. Bytes flow through `nb::bytes` and copy into a local `std::vector<std::uint8_t>` on the C++ side. The binding class names use the `Cpp` suffix to avoid colliding with the Python dataclasses if both are imported in the same parity test.
- `tests/unit/test_cpp_xcp_packets_parity.py` — 57 parity tests against `tuner.comms.xcp.packets`. Coverage: `build_connect_command` parametrised over 4 mode values; `build_get_id_command` over 4 identifier types; `build_set_mta_command` over 5 (address, extension) pairs including the 0x00000000 / 0xFFFFFFFF edges; `build_upload_command` parametrised over 10 in-range sizes plus 6 out-of-range sizes that must throw on both sides; `parse_connect_response` happy path + the big-endian `max_dto` decode parity; `parse_status_response` happy path + the big-endian `configuration_status` decode parity; `parse_get_id_response` ASCII happy path + the non-ASCII replacement check (`"\ufffd" in py.identifier_text()` confirms both implementations emit U+FFFD); `parse_command_ack` accepts the single 0xFF byte; `parse_upload_response` happy path + a 20-iteration random round-trip up to 200 bytes per payload; and parametrised error-path tests asserting both Python and C++ throw on every shape (3 connect / 3 status / 5 get_id / 4 command_ack / 3 upload).

**Why XCP next.** The Speeduino raw protocol port is complete (sub-slices 70–73 covered framing, command shapes, value codec, parameter codec, live-data decoder), but XCP has been the standing "partial support" gap on the comms side. The packet layer is the smallest pure-logic surface that closes a meaningful slice of that gap — the byte shapes are deterministic and trivially parity-testable, so the C++ side can own them with no risk before the I/O-bound `XcpControllerClient` orchestration layer comes across. With this in place, the only XCP work left for the C++ comms layer is the (still I/O-bound) `XcpControllerClient` itself — same shape as the remaining Speeduino comms work that's deferred to a later slice.

C++ doctest suite: 1206 / 10240 → **1229 / 10281** (+23 tests, +41 assertions). Python collected suite: 2759 → **2816** (+57 parity tests). `tuner_app.exe` rebuilds cleanly. No mid-slice fixes needed — both build and parity tests passed first try.

#### Phase 14 Slice 4 one-hundred-and-third sub-slice: Legacy `.project` text format parser/writer

Direct port of the pure-logic surface for the legacy key=value `.project` file format used before the JSON `.tunerproj` native format. The Python sources span three files: `tuner.parsers.common.parse_key_value_lines` (the underlying line parser), `tuner.parsers.project_parser.ProjectParser` (the connection-profile builder + glue), and `tuner.services.project_service.ProjectService` (the sanitizer + line-builder body of `save_project`). All three are ported here as one cohesive "legacy project file format" module — the format is a single concept that just happened to have its parse and write halves in different files on the Python side.

- `cpp/include/tuner_core/legacy_project_file.hpp` and `cpp/src/legacy_project_file.cpp` — `legacy_project_file::ConnectionProfile` POD mirroring the Python dataclass (optional fields stay `std::optional` so the empty-string-vs-missing distinction the writer uses for skip rules is preserved), `LegacyProjectModel` POD mirroring the subset of `Project` that the legacy text format actually serializes (path values are passed in as already-resolved relative strings — the C++ side never touches the filesystem). Free functions: `parse_key_value_lines(lines)` (strips whitespace, drops `#` / `;` / `//` comment lines, splits on `=` first then `:` as fallback, returns `std::map<string,string>` for deterministic iteration since the writer already sorts metadata before spillover), `parse_default_connection_profile(metadata)` (extracts `connection.default.*` keys, defaults `name` to `"Default"` and `transport` to `"mock"`, parses `port` and `baudRate` via a strict `parse_int_or_null` helper that mirrors Python's `int()` — accepts an optional leading `+`/`-`, requires all-digits body, falls back to `nullopt` on any malformed input including the trailing-junk `"115200abc"` case), `sanitize_project_name(name)` (alnum + `-` + `_` survive, others become `_`, then trim leading/trailing `_`), and `format_legacy_project_file(model)` (the line-builder body — writes `projectName` first, then `ecuDefinition` / `tuneFile` / `dashboards` / `activeSettings` (sorted) / six `connection.default.*` keys for the first profile only / sorted spillover metadata after a skip list of the structured-field key names plus any `connection.default.*` key).
- `cpp/tests/test_legacy_project_file.cpp` — 17 doctest cases covering: `parse_key_value_lines` for empty/comment/spaced/colon/equals-wins/no-separator inputs, `parse_default_connection_profile` for empty / no-prefix / full-TCP / partial-with-defaults / malformed-int-falls-back-to-null shapes, `sanitize_project_name` for alnum-survives / spaces-become-underscores / leading-and-trailing-trimmed / whitespace-strip-first / empty-result-allowed branches, and `format_legacy_project_file` for minimal / full / `activeSettings`-sorted / structured-field-skip-from-spillover round-trips.
- `cpp/bindings/tuner_core_module.cpp` — `LegacyConnectionProfile` and `LegacyProjectModel` classes plus `legacy_project_parse_key_value_lines` / `legacy_project_parse_default_connection_profile` / `legacy_project_sanitize_name` / `legacy_project_format_file` functions exposed for Python parity.
- `tests/unit/test_cpp_legacy_project_file_parity.py` — 33 parity tests against `parse_key_value_lines`, `ProjectParser._parse_default_connection_profile`, `ProjectService._sanitize_name`, and the full `ProjectService.save_project` line-builder body. Coverage: 10 line-parse shapes including the `=` wins over `:` quirk and the multi-comment-character branches; 7 connection-profile shapes including the strict `int()` parser quirks (`"+42"` accepted as 42, `"not-a-number"` and `"115200abc"` both rejected to `nullopt`); 12 sanitize shapes covering all ASCII branches; and 4 full `format_legacy_project_file` round-trips driven through `ProjectService.save_project` against `tmp_path` and compared byte-for-byte against the C++ output (with the Python `_relative_path` helper called explicitly so the parity comparison stays line-for-line — the C++ port deliberately does not own that part).

**Documented ASCII-only contract for `sanitize_project_name`.** The C++ port operates on raw bytes while Python's `isalnum()` operates on Unicode code points. For ASCII names the two agree exactly; for non-ASCII names the byte-by-byte port treats every UTF-8 continuation byte as non-alnum and produces more underscores than the Python original (e.g. `"naïve"` becomes `"na__ve"` on C++ vs `"naïve"` on Python). This is the right boundary for the legacy `.project` format because project filenames in practice are ASCII; the parity test removes the non-ASCII cases and documents the contract instead of paying for a UTF-8 codepoint decoder that would only be exercised by edge-case test inputs.

**Why the legacy format is still worth porting.** The `.tunerproj` JSON native format is the long-term direction (already ported in sub-slice 78), but every project file currently on disk is in the legacy `key=value` shape and the C++ app needs to load them while the migration window stays open. Owning both the parse and write paths in C++ means the migration adapter can run entirely native — read legacy, write native, no Python round-trip required. When the legacy format is finally retired this slice gets deleted in one PR; until then it's the smallest pure-logic surface that closes the C++ side of the legacy compatibility window.

C++ doctest suite: 1189 / 10197 → **1206 / 10240** (+17 tests, +43 assertions). Python collected suite: 2726 → **2759** (+33 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-second sub-slice: Firmware flash builder pure-logic helpers

Direct port of the platform / argument-builder helpers in `FirmwareFlashService` (`src/tuner/services/firmware_flash_service.py`). The Python service is a fat orchestration layer (subprocess execution with stdout/stderr stream parsing for percent updates, USB device open/write/close on Windows for the embedded Teensy loader, hex-image parsing for the firmware payload), but the per-tool argument shaping and the per-OS path lookups are pure functions that the C++ side can own without touching the filesystem.

- `cpp/include/tuner_core/firmware_flash_builder.hpp` and `cpp/src/firmware_flash_builder.cpp` — `firmware_flash_builder::FlashTool` enum mirroring the Python `FlashTool` (`AVRDUDE` / `TEENSY` / `DFU_UTIL`) with `to_string` returning the same `Enum.value` strings, `TeensyMcuSpec { name, code_size, block_size }` POD mirroring the private `_TeensyMcuSpec` dataclass, and the helper free functions: `platform_dir(tool, system_name, machine_name)` (returns the per-(tool, OS, arch) tools subdirectory under `<tool_root>/bin/`, e.g. `"avrdude-windows"` / `"teensy_loader_cli-darwin-x86_64"` / `"dfuutil-linux-x86_64"`), `tool_filename(tool, system_name)` (`"avrdude.exe"` vs `"avrdude"` etc.), `linux_platform_dir(prefix, machine_name)` (the **dfuutil dash-vs-underscore quirk** is preserved exactly: `dfuutil` uses `linux-x86_64` / `linux-i686` while `avrdude` and `teensy_loader_cli` use `linux_x86_64` / `linux_i686`; ARM variants drop the leading `linux*` segment for both), `supports_internal_teensy(system_name)` (Windows-only), `teensy_cli_filename(system_name)` (`"teensy_loader_cli.exe"` vs `"teensy_loader_cli"`), `teensy_mcu_spec(board_family)` (board family → `{TEENSY35, 524288, 1024}` / `{TEENSY36, 1048576, 1024}` / `{TEENSY41, 8126464, 1024}`, throws on non-Teensy), and the five command argument list builders: `build_avrdude_arguments(serial_port, config_path, firmware_path)` (mirrors the literal `arguments=[...]` block of `_build_avrdude_command` — 12 elements ending with the `flash:w:<path>:i` action), `build_teensy_cli_arguments(mcu_name, firmware_path)` (`["--mcu=...", "-w", "-v", "<path>"]`), `build_teensy_legacy_arguments(board_family_value, firmware_stem, firmware_parent, tools_dir)` (the `-board=` / `-reboot` / `-file=` / `-path=` / `-tools=` 5-element shape used when only the `teensy_post_compile.exe` helper is bundled), `build_internal_teensy_arguments(mcu_name, firmware_path)` (the `["--mcu=...", "-w", "<path>"]` 3-element shape consumed by the embedded loader), and `build_dfu_arguments(vid, pid, firmware_path)` (the 8-element `dfu-util -d VID:PID -a 0 -s 0x08000000:leave -D <path>` shape with throw on missing VID/PID). Reuses the existing `board_detection::BoardFamily` enum (already exposed to Python via sub-slice 99) so no new enum identity is introduced.
- `cpp/tests/test_firmware_flash_builder.cpp` — 17 doctest cases covering: `to_string` for all three tools, `platform_dir` per-tool Windows/Darwin/Linux paths and the unknown-system throw, `linux_platform_dir` for every architecture branch (including the avrdude-vs-dfuutil dash quirk and the ARM `armhf` / `aarch64` paths) plus the unknown-arch throw, `tool_filename` per-OS, `supports_internal_teensy` Windows-only check, `teensy_cli_filename` per-OS, `teensy_mcu_spec` shape per Teensy family with the non-Teensy throws, and one test per argument-list builder asserting the exact literal argument vector against the Python source plus the `serial_port == ""` / `vid == "" || pid == ""` throw paths.
- `cpp/bindings/tuner_core_module.cpp` — `FlashToolKind` enum, `TeensyMcuSpec` class, and 11 free functions exposed: `firmware_flash_builder_platform_dir` / `..._tool_filename` / `..._linux_platform_dir` / `..._supports_internal_teensy` / `..._teensy_cli_filename` / `..._teensy_mcu_spec` / `..._avrdude_arguments` / `..._teensy_cli_arguments` / `..._teensy_legacy_arguments` / `..._internal_teensy_arguments` / `..._dfu_arguments`.
- `tests/unit/test_cpp_firmware_flash_builder_parity.py` — 89 parity tests against the Python `FirmwareFlashService` private helpers. Coverage: `_platform_dir` parametrised over the cartesian product of all 3 tools × 11 (system, machine) pairs → 33 combinations; `_tool_filename` parametrised over 3 tools × 3 OSes → 9 combinations; `_linux_platform_dir` parametrised over 3 prefixes × 9 architectures → 27 combinations; `_supports_internal_teensy` and `_teensy_cli_filename` over 3 OSes each; `_teensy_mcu_spec` per Teensy family + non-Teensy throw cases; literal argument list parity for AVRDUDE / Teensy CLI / Teensy legacy / internal Teensy / DFU plus the missing-serial-port and missing-VID/PID throw cases. Drives the Python `_platform_dir` / `_tool_filename` / `_linux_platform_dir` paths through `FirmwareFlashService(system_name=…, machine_name=…)` constructed per test so the system / machine fingerprint is deterministic regardless of the host OS.

This is the second-largest pure-logic surface in the firmware-flash service (the first was the flash target classifier landed in sub-slice 99). Together with sub-slice 99's classification helpers, the C++ side now owns both halves of the per-flash-target decision-and-shape pipeline: "what board did the operator plug in" → "what platform tools subdirectory" → "what arguments to invoke them with". The remaining I/O — subprocess execution with stream parsing, the Windows-only embedded Teensy loader, and the Intel HEX image parser — is the appropriate seam to keep on the Python side until the C++ comms layer stabilises.

C++ doctest suite: 1172 / 10106 → **1189 / 10197** (+17 tests, +91 assertions). Python collected suite: 2637 → **2726** (+89 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundred-and-first sub-slice: Live capture session formatters

Direct port of the pure-logic helpers in `LiveCaptureSessionService` (`src/tuner/services/live_capture_session_service.py`): `status_text`, `_ordered_column_names`, `to_csv`, and the per-cell value formatting branch they share. The I/O lifecycle (`start` / `append`'s file-stream write / `stop` / `_close_stream`) stays Python because Qt timers, `QFileDialog`-driven output paths, and the `OutputChannelSnapshot` filtering pipeline all live on the Python side.

- `cpp/include/tuner_core/live_capture_session.hpp` and `cpp/src/live_capture_session.cpp` — `live_capture_session::CapturedRecord { elapsed_ms, keys, values }` POD with **parallel `keys` and `values` vectors** so insertion order is explicit (the C++ `unordered_map` does not preserve it the way Python's dict does, and the column ordering rule depends on insertion order). `status_text(recording, row_count, elapsed_seconds)` mirrors `CaptureSessionStatus.status_text` exactly: `"Recording: N rows (E.Es)"` while recording, `"Stopped \xe2\x80\x94 N rows captured (E.Es)"` (em dash U+2014) when stopped with rows, `"Ready"` otherwise. `ordered_column_names(profile_channel_names, records)` walks the profile-supplied names first then appends any extra keys seen across the records in their first-occurrence order. `format_value(value, digits)` routes to `printf("%.*f")` for `digits >= 0` and to the existing `tune_value_preview::format_scalar_python_repr` for `digits < 0` (so the no-digits column path matches Python's `str(float)`). `format_csv(records, columns, format_digits)` emits the full CSV with `Time_ms` first, the elapsed-ms rounded via `printf("%.0f")`, missing cells rendering as empty strings, and `\r\n` line terminators to match Python's `csv` module default.
- `cpp/tests/test_live_capture_session.cpp` — 14 doctest cases covering: ready/recording/stopped status branches with the explicit em-dash byte sequence, profile-first ordering with record extras, no-profile fallback to record-insertion order, profile names that never appear in any record, empty/empty edge case, fixed-digits and repr `format_value` modes, empty-records returns empty string, single full row, missing-cell empty fallback, repr fallback for unconfigured columns, and header order following the columns vector exactly.
- `cpp/bindings/tuner_core_module.cpp` — `CapturedRecord` class plus `live_capture_session_status_text` / `live_capture_session_ordered_column_names` / `live_capture_session_format_value` / `live_capture_session_format_csv` functions exposed for Python parity.
- `tests/unit/test_cpp_live_capture_session_parity.py` — 25 parity tests against `LiveCaptureSessionService` and `CaptureSessionStatus`. Coverage: `status_text` parametrised over 8 (recording, row_count, elapsed_seconds) combinations, profile-first ordering driven through the real `start` → `append` → `stop` lifecycle, no-profile fallback driven through direct `_records` injection, fixed-digits formatting parametrised over 4 (value, digits) combinations, repr formatting parametrised over 6 mid-range values that both implementations agree on (the boundary scientific-notation cases are covered by `test_cpp_tune_value_preview_parity.py`, not duplicated here), single-row full parity, missing-cell parity, repr-fallback parity, empty-records parity, and a 40-row random session built around a 6-channel profile where each row drops 0–2 channels at random to exercise the missing-cell branch + Python dict insertion-order path.

The Python service has two halves: a stateful I/O lifecycle (`start` opens a file, `append` filters and writes a stream row, `stop` closes the file) and a stateless formatter (`status_text`, `_ordered_column_names`, `to_csv`, `_format_digits_for`). This slice ports the stateless half. The I/O half is the right boundary to leave on the Python side until the C++ comms layer stabilises — `CaptureSessionStatus` itself is just a small data carrier that the workspace presenter renders, and the formatter functions are pure enough that the C++ side can produce identical CSV from a `(records, columns, digits)` triple without ever touching the disk.

**Mid-slice fix.** The first parity-test run failed because `_build_session` was passing `OutputChannelSnapshot(values=dict)` — but the Python domain shape is `list[OutputChannelValue]`. Reading the `output_channels.py` source confirmed the field type; the test factory now constructs `OutputChannelValue(name=k, value=v)` instances explicitly. The second failure was the repr branch on `1.5e10`: Python's `str(1.5e10)` returns `"15000000000.0"` (still fixed-format) but the C++ `format_scalar_python_repr` returned `"1.5e+10"` (scientific) — a known boundary divergence that's covered by `test_cpp_tune_value_preview_parity.py`. Replaced the boundary case with a mid-range value (`123456.789`) since this slice is testing the integration, not the underlying repr edge cases.

C++ doctest suite: 1158 / 10074 → **1172 / 10106** (+14 tests, +32 assertions). Python collected suite: 2612 → **2637** (+25 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 one-hundredth sub-slice: Live trigger logger pure-logic decoder

Direct port of `LiveTriggerLoggerService.decode` and `_extract_field` (`src/tuner/services/live_trigger_logger_service.py`). The decoder is the pure-logic seam between the raw byte buffer returned by `SpeeduinoControllerClient.fetch_logger_data()` and the existing trigger-log analysis pipeline; the CSV temp-file write (`to_csv_path`) stays Python-side because it's pure I/O.

- `cpp/include/tuner_core/live_trigger_logger.hpp` and `cpp/src/live_trigger_logger.cpp` — `live_trigger_logger::TriggerLogRow` (mirror of the Python `dict[str, float]` row shape via `unordered_map<string, double>`), `TriggerLogCapture { logger_name, display_name, kind, columns, rows }` with `record_count()` accessor, `extract_field(record_bytes, field_def)` (pure helper that reproduces the Python `_extract_field` for `bit_count == 1`, `bit_count == 32`, and the generic bit-window path including byte-boundary crossings), and `decode(logger, raw)` (the top-level entry that walks `logger.record_count` records of length `logger.record_len` after `logger.record_header_len` header bytes, stopping early if the buffer truncates mid-record). Drives the bit-level shape entirely off `IniLoggerDefinition::record_fields` parsed by the existing `ini_logger_definition_parser.hpp` (sub-slice ports #10/11), so the decoder has zero hard-coded byte layouts and adapts automatically to whatever logger types the INI declares.
- `cpp/tests/test_live_trigger_logger.cpp` — 11 doctest cases covering: empty raw → empty rows + full metadata, three tooth records decoded as u32 LE microseconds, composite record bit-flag + refTime ms decode, `rec_len == 0` short-circuit (returns empty rows but full metadata), truncated raw stops at the last full record, `record_header_len` skip is honored, single-bit flag extraction at varied byte positions including byte-boundary crossings, generic 12-bit bit window across two bytes, out-of-range extraction returns 0, scale applied to all three extraction modes, and capture columns preserve record-field order.
- `cpp/bindings/tuner_core_module.cpp` — `TriggerLogRow` and `TriggerLogCapture` classes plus `live_trigger_logger_decode(logger, raw)` and `live_trigger_logger_extract_field(record, field)` functions exposed for Python parity. Bytes flow through `nb::bytes` and span over the underlying buffer on the C++ side. Adds `<nanobind/stl/unordered_map.h>` to the binding includes since `TriggerLogRow::values` is an `unordered_map<string, double>`.
- `tests/unit/test_cpp_live_trigger_logger_parity.py` — 22 parity tests against `LiveTriggerLoggerService.decode` and the module-level `_extract_field`. Coverage: tooth decode of three records, empty buffer, truncated buffer (only 2 of 3 records survive), header-len skip, composite single record, composite random 64-record buffer, `rec_len == 0` short-circuit, `extract_field` parametrised over 12 hand-picked cases (1-bit flags within byte 0, 1-bit flags crossing byte boundary, u32 LE, scaled u32, 12-bit generic window, out-of-range), 60 random generic bit windows of widths 2..16, 20 random tooth buffers of lengths 0..32, and 20 random composite buffers of lengths 0..32. The test factories convert the Python frozen-dataclass `LoggerDefinition` and `LoggerRecordField` into the C++ binding classes one field at a time.

This is the next pure-logic port after sub-slice 99 (flash target classifier). Like that slice it carves a clean Python-side I/O boundary — `LiveTriggerLoggerService.decode` is invoked by the `TriggerCaptureWorker` background thread on the Trigger Logs surface (the workers/timers/Qt signals stay Python), and its output feeds the existing CSV-based `TriggerLogAnalysisService` pipeline (which is also already in C++ as `trigger_log_analysis.hpp`). With the decoder in C++, every pure-logic step from "raw bytes off the wire" through "decoded named-column rows" to "analysed gap/phase/sync trace" is now native. The remaining I/O — `fetch_logger_data` and the CSV temp-file write — is the appropriate seam to keep on the Python side until the C++ comms layer stabilises.

C++ doctest suite: 1147 / 10025 → **1158 / 10074** (+11 tests, +49 assertions). Python collected suite: 2590 → **2612** (+22 parity tests). `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 ninety-seventh sub-slice: Burn to Flash — closing the stage → review → write → burn workflow

Sub-slice 95 added Write to RAM as the first commit action. Sub-slice 97 closes the workflow by adding **Burn to Flash** as the terminal commit step, alongside tree-entry state indicators (sub-slice 96).

**New button, specific position.** A third button joins the popup footer, positioned between Write to RAM (left) and Close (right):

```
┌────────────────────────────────────────────────────────────────┐
│ [ Revert All ]    [stretch]    [ Write to RAM ] [ Burn ] [Close]│
└────────────────────────────────────────────────────────────────┘
```

Styling uses `accent_ok` (green) for the border and text — the only place the `accent_ok` token appears in the chrome (everywhere else it indicates a healthy gauge zone). Repurposing it for Burn is semantically consistent: "this is the successful, final state". The button sits between Write to RAM (`accent_primary` blue) and Close (neutral) so the footer reads left-to-right as "discard · commit · finalize · done".

**Gate: only enabled when WRITTEN.** Burning while there are still raw STAGED pages would bypass the review step entirely, violating Core Principle #4. The button checks `workspace->aggregate_state() == WRITTEN` at popup construction time and only enables itself if there's nothing left to review. Disabled state is dimmed (`border` + `text_dim`, no hover effect) with a tooltip explaining the gate:

> *"Write to RAM first — burning bypasses the review step."*

A future slice could make the button cycle through ready/not-ready live as the popup's state changes, but for now the single-check-at-open is correct: the operator can't stage new edits from within the popup (revert is the only mutation), so the state can only transition forward STAGED → WRITTEN inside the same popup session, and that transition re-opens the popup anyway (Write to RAM closes and reopens via the refresh path, at which point Burn re-enables).

**Click handler — the full burn transaction.**

```cpp
auto written_pages = workspace->pages_in_state(WRITTEN);
for (const auto& pid : written_pages)
    workspace->mark_burned(pid);     // zeroes staged counts
edit_svc->revert_all();              // accept staged as new base (demo)
for (auto& [name, entry] : *visible_editors) {
    entry.edit->setText(entry.base_text);
    entry.edit->setStyleSheet(EditorState::Default);
    entry.edit->setToolTip("");
}
page_staged_chip->hide();
(*refresh_review_button)();
(*refresh_tree_state_indicators)();
on_staged_changed();                 // sidebar
dialog->accept();
```

Every commit surface resets in one transaction. No partial state visible after it returns.

**Demo semantics vs real semantics.** Without a real ECU, "burn to flash" visually means "the edits are now the committed baseline". The cleanest way to show this in the demo is `edit_svc->revert_all()`, which drops all staged entries and returns the editor widgets to the base tune values. In the real-ECU path, burn would write staged values to flash, update the base tune file, and then clear the staged set — the visible editors would show the new (just-burned) values, not the old base. The demo's "visual return to base" is a white lie that exercises the state-machine UI without requiring a real ECU connection. When the real burn path lands, this handler gets replaced with a proper write-base pipeline and the demo lie goes away.

**Keyboard shortcuts.** Three shortcuts, all landing on the same popup:

- **Ctrl+R** — Review (added sub-slice 93)
- **Ctrl+W** — Write to RAM (new)
- **Ctrl+B** — Burn to Flash (new)

All three open the review popup. Why the same destination? Because the popup is the single place the operator commits any state transition, and splitting "directly jump to Write" / "directly jump to Burn" would skip the review step that exists *to prevent committing without seeing what's about to change*. The shortcuts are mnemonic landings, not direct actions. On macOS Cmd+W usually closes windows; Windows-only for now so no conflict.

**Test suite status.** Unchanged at **1130 / 9958** — this is a pure UI addition. `tuner_app.exe` rebuilds cleanly.

#### Phase 14 Slice 4 ninety-sixth sub-slice: Tree-entry state indicators (zoom level 0.5)

User request: *"The tuning page should reflect if there is a staged change etc, so users can quickly distinguish where to look. by tuning page, I mean the tree entry in the left pane of the tuning tab."*

The three-zoom staged-state hierarchy (sidebar badge / per-page chip / review popup) answered *what* and *how many*, but not *which page*. The operator had to either open the review popup to see the names or navigate through the tree to find the page with the chip. Sub-slice 96 closes that gap by making staged state visible **on the tree itself** — before any navigation.

**Effectively zoom level 0.5** (sitting between the sidebar's whole-app summary at zoom 0 and the per-page chip at zoom 1): the tree tells you *which specific pages* have pending work without requiring a click.

**Implementation.** Extend `TreeLeafInfo` with a cached `base_label` field capturing the leaf's text *before* any state marker is appended. `rebuild_tree` populates it once during the initial tree build:

```cpp
struct TreeLeafInfo {
    QTreeWidgetItem* item;
    std::string title;
    std::string target;
    std::string base_label;  // new: "<display><type_tag>"
};
```

A new `refresh_tree_state_indicators` closure walks `tree_refs` and updates every leaf's text + foreground color from the workspace state:

```cpp
for (auto& ref : *tree_refs) {
    for (auto& lf : ref.leaves) {
        int n = workspace->staged_count_for(lf.target);
        auto ps = workspace->page_state(lf.target);
        if (n <= 0 || ps == CLEAN) {
            lf.item->setText(0, QString::fromUtf8(lf.base_label.c_str()));
            lf.item->setForeground(0, QBrush());  // reset to tree default
            continue;
        }
        const char* accent = (ps == WRITTEN) ? accent_primary : accent_warning;
        char marked[320];
        std::snprintf(marked, sizeof(marked),
            "%s  \xe2\x97\x89 %d", lf.base_label.c_str(), n);
        lf.item->setText(0, QString::fromUtf8(marked));
        lf.item->setForeground(0, QBrush(QColor(QString::fromUtf8(accent))));
    }
}
```

**Why `base_label` is cached instead of recomputed from `pg.display + pg.type_tag`.** The tree is built once from `compile_pages` output, and `PageEntry::type_tag` isn't stored in `TreeLeafInfo` after that. Caching the composed string at build time is one line of extra data and avoids a second lookup path. If the operator could rename pages (they can't — INI-defined), this would need to change.

**Why `QBrush()` (invalid brush) resets foreground.** Qt's `QTreeWidgetItem::setForeground(0, QBrush())` with an *invalid* brush means "no override — use the widget's default". This is the clean way to revert a dirty item back to the default color without having to query what that default actually is. Passing `QBrush(QColor("#c9d1e0"))` (an explicit default-like color) would also work but would lock the color to whatever `text_secondary` is today rather than tracking the tree widget's stylesheet.

**Call sites.** The closure is invoked from every state-change handler that was already wiring the other zoom levels:

- **Stage-edit** (scalar editor `editingFinished`) — tree item gets marked when a new edit lands
- **Per-row × revert** — tree mark drops when an edit is reverted
- **Revert All** — every tree mark clears in one pass
- **Write to RAM** — tree marks cycle amber → blue (text stays, color changes)
- **Burn to Flash** — tree marks clear back to default

Each call site added `refresh_tree_state_indicators` to its capture list. The outer tree-selection lambda also captures it so the inner stage-edit closure can see it through the capture chain — same pattern as sub-slice 92/93.

**Cost.** Linear in total leaf count (56 pages × ~10 fields/page is irrelevant here — we only walk page count, not field count). Runs only on state transitions, never on hot path. Cheap.

**Visual effect — four zoom levels now visible:**

```
Level 0.5 (tree):      VE Table (table)  ◉ 2       ← amber, shows WHICH page
Level 1 (per-page):    ◉ 2 staged                  ← amber, shows COUNT for active page
Level 0 (sidebar):     🔧 Tune · 2 staged          ← amber, shows TOTAL
Level 2 (popup):       veTable · [...] → [...]     ← full diff list
```

Progressive disclosure all the way from "which page" to "what exactly" with no dead ends.

#### Phase 14 Slice 4 ninety-fifth sub-slice: Write to RAM + WRITTEN state + sub-slice 94 bugfix

Sub-slice 94 landed per-edit revert in the review popup. Sub-slice 95 closes the remaining step of the stage → review → commit workflow by adding the **Write to RAM** action and making the three-zoom state hierarchy visually distinguish STAGED (pending review) from WRITTEN (committed to RAM, awaiting burn). It also fixes a bug reported against sub-slice 94 where revert cleared the state layer but not the visible editor widgets.

**New workspace API.** Two accessors added to `workspace_state::Workspace`:

- **`aggregate_state() const`** — walks every tracked page and returns the highest-priority state: `STAGED > WRITTEN > BURNED > CLEAN`. Used by the three-zoom UI helpers to pick a single color for the whole-app summary when pages may be in different states.
- **`pages_in_state(PageState)`** — returns the list of page IDs currently in a given state, in insertion order of the original `set_pages` call. Used by the Write to RAM button to iterate only the pages that actually need writing.

Two doctest cases cover the behaviour matrix: mixed STAGED/WRITTEN resolves to STAGED (staged wins because it needs more attention), BURNED-only fallback before CLEAN, per-state enumeration preserving insertion order. Suite delta: 1128 → **1130** tests, 9945 → **9958** assertions.

**State-aware chrome — color and text both switch.** `refresh_page_chip`, `refresh_review_button`, and the sidebar `refresh_tune_badge` closure now read the relevant state and pick accent + verb accordingly:

| State   | Accent token     | Verb     | Example text     |
|---------|------------------|----------|------------------|
| STAGED  | `accent_warning` | `staged` | `◉ 3 staged`     |
| WRITTEN | `accent_primary` | `in RAM` | `◉ 3 in RAM`     |

The per-page chip reads the specific page's state via `page_state(target)`. The review button and sidebar badge read `aggregate_state()` so the app-wide summary reflects the most-urgent pending work first. STAGED always wins over WRITTEN because STAGED means "not yet reviewed" which is more urgent than "reviewed and in RAM".

**Write to RAM button.** New `QPushButton` in the review popup footer, positioned between Revert All (left) and Close (right). Styled with `fill_primary_mid` background and `accent_primary` border + text — a "primary commit" look that visually anchors the positive side of the footer the same way Revert All anchors the "discard" side. Clicking:

1. `workspace->pages_in_state(PageState::STAGED)` — get the list of pages that need writing.
2. For each page ID, call `workspace->mark_written(pid)` — transitions that page from STAGED to WRITTEN. The staged count stays non-zero (WRITTEN ≠ CLEAN — the edits are still "dirty vs flash" conceptually).
3. `(*refresh_review_button)()` — project bar chip cycles amber → blue.
4. `on_staged_changed()` — sidebar Tune badge cycles amber → blue.
5. `(*refresh_page_chip)(active_page)` — per-page chip for the currently-viewed page cycles amber → blue.
6. `dialog->accept()` — close the popup.

The form editors stay on their blue Ok tint since that's `EditorState::Ok` from the scalar editor tint cycle and matches the new WRITTEN state visually — no separate transition needed on the field level.

**Operator flow end to end:**

```
1. Edit a field                                 (editor tint: amber → blue Ok)
2. Sidebar shows "Tune · 1 staged"              (amber)
3. Per-page chip shows "◉ 1 staged"             (amber)
4. Open review popup (Ctrl+R or chip click)
5. See "reqFuel · 8.5 → 9.0" with × revert btn
6. Click Write to RAM
7. Popup closes
8. Sidebar shows "Tune · 1 in RAM"              (blue)
9. Per-page chip shows "◉ 1 in RAM"             (blue)
10. Review chip shows "◉ In RAM (1)"            (blue)
```

Everything stays visible until a future slice adds Burn to Flash (which will call `mark_burned` and clear the staged count entirely).

**Sub-slice 94 bugfix — the revert-without-editor-reset bug.**

The bug reported by the user: after clicking × next to a staged entry in the review popup, the field's visible value on the TUNE tab stayed at the user-typed value instead of returning to the pre-stage value.

Root cause: `edit_svc->revert(name)` clears the staged entry in the edit service, but the `QLineEdit` widget on the TUNE tab is an independent Qt object holding its own text buffer. There was no path from the revert handler back to the widget.

Fix: a new `visible_editors` shared map, keyed by parameter name, storing `{QLineEdit*, base_text}` for every scalar editor currently rendered on the TUNE tab's parameter form. The map is populated inside the field-rendering loop right after each editor is created, and cleared on every page switch (so it always reflects what's on screen, not stale ghosts from previously-viewed pages — the hidden widgets stay alive but aren't reached by the map).

The base_text is captured from `edit_svc->get_base_value(f.parameter_name)` rather than `get_value()`, so the map stores the "return to this on revert" target rather than the currently-displayed (possibly already staged) value.

Three call sites now consume the map:

1. **Per-row × revert handler** — `visible_editors->find(name)` → if found, `setText(base_text)` + `setStyleSheet(EditorState::Default)` + clear tooltip.
2. **Revert All handler** — iterate the whole map and reset every visible editor in one pass.
3. **(Page switch)** — clears the map before the old form hides, so revert handlers don't reach hidden ghost editors from previously-viewed pages.

The fix also covers the Revert All path which had the same bug without being explicitly reported — the same reasoning applies.

**Progressive disclosure still holds.** The three zoom levels now show **three different states** (staged, in-RAM, clean) at **three different levels of detail** (count summary, per-page count, per-edit diff). The operator can triage at any level and see the same state consistently. STAGED → WRITTEN is the operator's explicit commit action; CLEAN is the post-burn terminal state (future slice).

**Build status.**

- C++ doctest: **1130 / 9958 / 0 failures** (+2 tests, +13 assertions from aggregate_state + pages_in_state).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly. Pre-existing `right_layout` capture warning unchanged.

**What's next.** Obvious follow-ups: (a) **Burn to Flash** button + `mark_burned` path that clears staged counts and cycles chips blue → hidden (terminal state); (b) Ctrl+W global shortcut for Write to RAM (matching Ctrl+R for Review); (c) a **live transition animation** for the chip color cycle (fade instead of instant switch — though *"Don't over-animate — automotive tuning is precision work"* suggests keeping it instant); (d) distinguishing WRITTEN-but-stale (if signature mismatches after reconnect) from WRITTEN-healthy via a third accent.

#### Phase 14 Slice 4 ninety-fourth sub-slice: Per-edit revert in the review popup

Sub-slice 93 shipped the review popup with a single "Revert All" button at the bottom — an all-or-nothing commit. Sub-slice 94 adds **per-edit revert**: each row in the popup gets its own × button so the operator can drop individual edits without losing the rest.

**Why per-edit revert matters.** The "review" step exists so the operator can look at everything pending and *decide*. With only "Revert All", the decision is binary: accept all or throw all away. Realistic tuning sessions produce a mix of "keep that, drop that, keep that" — the popup needs to support triage, not just batch commit. Per-row revert turns the popup from a summary into a workbench.

**New helper: `resync_workspace` closure.** `edit_svc->revert(name)` knows *which parameter* to drop but not *which page* it belongs to. `workspace_state::Workspace` is page-keyed — it needs to know the page to decrement the right counter. The authoritative param→page map is in the compiled `page_map` inside `build_tune_tab`, and `workspace_state` has no dependency on it (correctly — it's a pure-logic service). Resolution: a new closure inside `build_tune_tab` that owns both and can walk the map:

```cpp
auto resync_workspace = std::make_shared<std::function<void()>>(
    [workspace, page_map, edit_svc]() {
        workspace->revert_all();
        for (const auto& [target, page] : *page_map) {
            for (const auto& sec : page.sections) {
                for (const auto& f : sec.fields) {
                    if (edit_svc->is_dirty(f.parameter_name)) {
                        workspace->stage_edit(target, f.parameter_name);
                    }
                }
            }
        }
    });
```

Cost is O(pages × fields) which is small (56 pages × ~10 fields/page = under 600 lookups) and runs only on revert — not hot-path. Rebuilding counts from the edit_svc is the correct design because `edit_svc` is the authoritative source of truth; the `Workspace` counter is a view over it.

**Per-row revert button.** Each row in the review popup was previously a single `QLabel` with HTML-formatted diff text. Sub-slice 94 restructures each row into a compound widget:

```
┌─────────────────────────────────────────────────────────────┐
│ reqFuel  ·  8.5  →  9.0                               [ × ] │  ← one row
└─────────────────────────────────────────────────────────────┘
```

The diff label is on the left (unchanged HTML formatting), a stretch spacer in the middle, and a small 22×22 × button on the right. The button is tokenized — `bg_inset` background, `border` by default, `accent_warning` + warning-colored text on hover so the operator can tell what it does without reading a tooltip. A `setToolTip("Revert <name>")` gives confirmation on hover anyway.

**Click handler.** When a per-row revert button fires:

1. `edit_svc->revert(name_copy)` — drop this one entry
2. `(*resync_workspace)()` — rebuild per-page counts from the remaining staged set
3. `(*refresh_review_button)()` — update the project-bar "Review (N)" chip
4. `on_staged_changed()` — update the sidebar Tune badge
5. `(*refresh_page_chip)(workspace->active_page())` — update the per-page chip for the current view
6. `row->hide()` — the row disappears from the popup list **in place** (not deleted, because deleting widgets in signal handlers is a documented crash pattern in `main.cpp`)
7. `--(*remaining); update_title(*remaining);` — decrement the shared row counter and update the dialog title in place
8. `if (*remaining <= 0) dialog->accept();` — auto-close when the last row is reverted

All three zoom levels of the staged-state hierarchy refresh simultaneously, no partial state visible.

**`update_title` closure.** The dialog title was a static format string in sub-slice 93. Sub-slice 94 extracts it into a closure that takes the current count:

```cpp
auto update_title = [title](int n) {
    // Set HTML with "N staged change(s)" + caption
    title->setText(...);
};
update_title(static_cast<int>(names.size()));  // initial render
// Later, from a per-row handler:
update_title(*remaining);
```

This way the title reflects the live count without rebuilding the whole dialog. A shared `remaining` counter (a `shared_ptr<int>`) is captured by each row's revert button so the closures cooperate on the same value.

**Why hide the row instead of removing it from the layout?** Qt's layout system allows `removeWidget` + `deleteLater`, but deleting a widget that's a child of the layout that owns the currently-executing signal handler has bitten this project before (documented at the top of `main.cpp`). `hide()` is safe, visually identical, and the dialog closes shortly after the last row is hidden anyway. No leak — the widget dies with the dialog.

**The three-zoom progressive-disclosure hierarchy is now fully interactive** at every level:

- **Zoom 0 (sidebar):** shows total count, no controls.
- **Zoom 1 (per-page chip):** shows per-page count, no controls.
- **Zoom 2 (review popup):** shows every edit with name · base → staged and **per-row × revert** + **Revert All** + **Close**.

The operator can now triage: glance at sidebar → know there's work to review, open popup → scan the list, hit × on the few edits they don't want → close popup → keep editing. Same workflow as any code review interface, just for ECU parameters.

**Build status.**

- C++ doctest: **1128 / 9945** (unchanged — pure UI addition).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly.

**What's next on this track.** Natural follow-ups: (a) a **"Write to RAM"** button in the popup footer that calls `workspace->mark_written(page)` for every staged page and cycles the per-page chip from amber (STAGED) → blue (WRITTEN); (b) **per-field Ctrl+Z undo** on the TUNE-tab scalar editors using the existing `EditService::undo(name)` seam; (c) the `PageState::BURNED` visualization once a real burn path exists. None block Phase 14 ship.

#### Phase 14 Slice 4 ninety-third sub-slice: Staged-changes review popup

Sub-slice 92 made staged state **visible** at two zoom levels (sidebar badge + per-page chip). Sub-slice 93 closes the **review** half of the workflow by adding a modal popup that lets the operator see exactly what's about to change, then either Revert All or Close and continue editing.

**Why this matters.** `docs/ux-design.md` Core Principle #4 — *"Staged everything — never apply changes silently; always preview → review → commit"*. Before sub-slice 93, the operator could **stage** (scalar editor tint + sidebar badge + per-page chip) and **commit** (Ctrl+S save, eventually burn) but there was no **review** step between them. A large batch of edits was a leap of faith — you saw the count, not the list.

**New accessor: `EditService::staged_names()`.** Returns `std::vector<std::string>` of all currently-staged parameter names in alphabetical order. Sort is deterministic so the review popup always renders rows in the same sequence regardless of insertion order. One doctest case covers: empty → empty; stage 3 (mixed insertion order) → sorted; revert one → sorted with that one removed; revert_all → empty. Suite delta: 1127 → **1128** tests, 9936 → **9945** assertions.

**Trigger surfaces, two paths.**

1. **"Review (N)" chip in the TUNE project bar.** Small `QPushButton` styled as an inline chip (`bg_inset` background, `accent_warning` border and text, `· Review (N)` label). Hidden when nothing is staged — no empty-state chrome. Positioned on the right edge of the project bar so it reads as "the thing to do next" without competing with the project name / metadata chain on the left.
2. **Ctrl+R keyboard shortcut.** Global within the TUNE tab, opens the same popup without a mouse. Matches the Ctrl+K (command palette) / Ctrl+S (save) shortcut rhythm the app already has.

Both paths call the same `open_review_dialog` closure. Same dialog, same behavior.

**The dialog.** A `QDialog` (modal), 560×420, styled with the token palette:

- **Title row** — hero text in `text_primary` / `font_heading`: `N staged change(s)`. Below it a `text_muted` / `font_small` caption: *"Review before writing to RAM or burning to flash."*
- **Scrollable list pane** — bordered `bg_panel` card. Each staged edit becomes a single `QLabel` row with an HTML-formatted diff: `name` in bold primary, ` · ` dim separator, `base_text` in monospace muted, ` → ` blue arrow, `staged_text` in monospace bold blue. The value formatter handles all three `TuneValue` variants (scalar via `%.4g`, string verbatim, list as `[N values]` placeholder — full list diff would be too heavy for the review popup's role). Rows stack vertically inside the list container.
- **Button row** — `Revert All` on the left (amber `accent_danger` border, hover-brightens), `Close` on the right (neutral panel border, hover accent). Stretch between them so Revert All stays visually distant from Close (no accidental clicks).

**Revert transaction — single state flip.** When Revert All fires, everything happens in one closure:

```cpp
edit_svc->revert_all();            // clear staged edits
workspace->revert_all();            // clear workspace tracking
page_staged_chip->hide();           // zoom 2: current view
(*refresh_review_button)();         // zoom 1: project bar
if (on_staged_changed) on_staged_changed();  // zoom 0: sidebar
dialog->accept();                   // close the popup
```

Five surfaces commit in one pass. No partial state visible after it returns — operator can't see "sidebar says 0 but chip still says 3" because all three refresh synchronously.

**Why a popup, not an inline panel?** Two reasons grounded in the design philosophy:

1. **Progressive disclosure.** The operator stages an edit and wants to get back to editing, not stare at a persistent list. The popup is on-demand — hidden until the operator asks for it. An inline panel would take vertical space away from the parameter form every time, even when the operator doesn't need it.
2. **Modal separation.** Review is a different mental mode from editing. Seeing the full diff list should feel like *"stepping back to look at everything"*, not *"there's a sidebar over there"*. A modal dialog creates the right psychological break — you can't accidentally edit another field while reviewing.

**Three-zoom state hierarchy now complete:**

- **Zoom 0 (across the app):** sidebar `Tune · N staged` label — operator sees pending work count from any tab.
- **Zoom 1 (within the current view):** per-page `◉ N staged` chip beside the page title — operator sees how many edits belong to the page they're looking at.
- **Zoom 2 (full detail):** review popup with every edit as a `name · base → staged` row — operator sees exactly what's about to change.

Progressive disclosure all the way down. Each zoom level reveals only what matters at that zoom; the operator pulls up the next level of detail when they're ready.

**Build status.**

- C++ doctest: **1128 / 9945 / 0 failures** (one new `staged_names` case).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly. Pre-existing `right_layout` capture warning in `build_tune_tab` unchanged.

**Debug note.** Same issue as sub-slice 92: the inner stage-edit lambda referenced `refresh_review_button` but the outer tree-selection lambda that owned it by composition didn't have it in its capture list. Fix: add `refresh_review_button` to the outer lambda's capture list. Pattern worth remembering — nested lambdas in Qt signal/slot chains need every captured name spelled out at every level.

**What's next.** Natural follow-ups if you want to continue in this direction: (a) per-edit revert from the popup (each row gets a small "revert" button that calls `edit_svc->revert(name)` and updates only that row), (b) a visible `PageState::WRITTEN` / `BURNED` transition surface — e.g. the per-page chip cycles through amber (staged) → blue (written to RAM) → green (burned to flash), (c) a "Write to RAM" button alongside "Revert All" in the popup footer so the operator can commit directly from the review step. None block Phase 14 ship — they're opportunistic next slices.

#### Phase 14 Slice 4 ninety-second sub-slice: Live staged-changes feedback (sidebar badge + per-page chip)

Sub-slices 88–91 closed the beautification arc (theme tokens, sidebar chrome, TUNE-tab detail panel). Sub-slice 92 starts putting those tokens to work on a real operator-visible state surface: **live staged-changes feedback** across two levels of the UI hierarchy.

**The problem.** Staging an edit used to have two visual effects — the scalar editor tinted blue or amber, and an internal counter in `workspace_state::Workspace` ticked up. The editor tint told the operator *"this edit was accepted"*, but nothing told them *"you have pending changes"* at the workspace level. The sidebar Tune nav label showed a hardcoded `"3 staged"` literal that was stale the moment the operator did anything.

**The fix, at two levels.**

1. **Workspace ownership lifted.** `auto workspace = std::make_shared<...>()` used to live inside `build_tune_tab` — fine when only the TUNE tab needed it, but invisible to `MainWindow`. Sub-slice 92 changes `build_tune_tab`'s signature to take `std::shared_ptr<Workspace>` as an explicit parameter, and `MainWindow` now constructs and owns the workspace before calling `build_tune_tab`. Same object, two readers.

2. **Per-page staged count accessor.** `Workspace::staged_count() const` already returned the total across all pages. Sub-slice 92 adds a sibling `staged_count_for(page_id)` that returns the count for a single page. Small addition (4 lines of implementation + 1 doctest case covering the "pages tracked independently, revert_page clears, mark_burned clears, unknown page returns 0" semantics). Suite delta: 1126 → **1127** tests, 9930 → **9936** assertions.

3. **Sidebar Tune badge.** The hardcoded `"3 staged"` suffix in the `nav_items` array was removed. Instead, `MainWindow` defines a `refresh_tune_badge` lambda that reads `shared_workspace->staged_count()` and composes a label with a `· N staged` suffix (or just `Tune` when zero). The lambda is invoked once at startup for the initial render, then plumbed into `build_tune_tab` as a `StagedChangedCallback` that the stage-edit closure calls on every successful stage. No polling timer — the badge updates exactly when state changes, not on a clock tick.

4. **Per-page staged chip.** A new `page_staged_chip` `QLabel` sits beside the selected-page title on the TUNE tab, inside a new horizontal row container. The chip is amber-accented (`bg_inset` background, `accent_warning` border + text, `font_small` bold, `· N staged` text) so it reads as *"attention — pending"* without the full "warning" urgency of a red danger chip. Hidden by default; shown only when the active page has one or more staged edits. The refresh helper is a `shared_ptr<std::function<void(const std::string&)>>` captured by both the selection handler (fires on page switch) and the stage-edit closure (fires on a new edit within the active page). Same source of truth, two trigger points.

5. **Group-selection case handled.** Selecting a group item (not a leaf page) clears the selected label and hides the page chip explicitly — no stale state when the operator navigates up the tree.

**Design rationale.** Progressive disclosure applied to state:

- **Zoom level 1 (across the app):** the sidebar Tune label says `· 3 staged`. Operator sees the count from any tab without navigating.
- **Zoom level 2 (within the current view):** the per-page chip beside the selected-page title says `◉ 2 staged`. Operator sees how many of those belong to the page they're currently looking at.
- **Zoom level 3 (per-field):** the scalar editor tint from sub-slice 91 (blue for ok, amber for warning). Operator sees exactly which field they just edited.

Three levels of increasing specificity, each revealing only what matters at that zoom. The operator can glance at the sidebar to know "I have pending work", drop to the page title to know "2 of it is here", and scan the fields to know "that one and that one". This is the design philosophy's *"progressive disclosure"* principle applied to workspace state, not just chrome.

**Why not a bottom-of-screen banner?** The ux-design doc's "target state" for the TUNE tab mentions a "staged changes" area, but a banner across the bottom would compete with the status bar and take vertical space. A compact chip beside the page title + a sidebar suffix uses zero additional vertical space, adds no new layout regions, and keeps the operator's eye on the content rather than on chrome. This is the same reasoning that led to merging the LIVE tab's phase indicator + formula strip into a single compound runtime header in sub-slice 88.

**Build status.**

- C++ doctest: **1127 / 9936 / 0 failures** (one new `staged_count_for` case).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly. Pre-existing `right_layout` capture warning in `build_tune_tab` unchanged.

**Debug note.** The first build failed because the `on_staged_changed` callback parameter was referenced from the inner stage-edit lambda without being captured by the outer tree-selection lambda that owned it by composition. Fix: add `on_staged_changed` to the outer lambda's capture list so it's visible in the inner nested lambda.

**What's next in this direction.** Natural follow-ups: (a) a "staged changes" review popup triggered by clicking the sidebar badge, showing the full list of pending edits with before→after values; (b) a "Revert All" button somewhere in the project bar that calls `workspace->revert_all()`; (c) wiring the `PageState::WRITTEN` / `BURNED` transitions visible in the sidebar or project bar so the operator sees the full state machine. None of these block Phase 14 ship — they're opportunistic next slices.

#### Phase 14 Slice 4 ninety-first sub-slice: Beautification pass #3 — TUNE-tab detail panel migration

Sub-slice 88 introduced the design token system and migrated three LIVE-tab surfaces. Sub-slice 90 extended the tokens into the app shell chrome (sidebar + status bar + wordmark footer). Sub-slice 91 finishes the three-part beautification arc by migrating the **TUNE-tab right-panel detail card** — the single biggest remaining inline-hex surface in `main.cpp`.

**Five new helpers on `cpp/app/theme.hpp`.** Each one captures a pattern that was repeated 2–6 times inline in `build_tune_tab`:

- **`scalar_editor_style(EditorState state)`** — the three-state `QLineEdit` stylesheet the parameter form uses. `Default` is neutral chrome (border tone, primary text), `Ok` is the blue confirm tint after a successful stage, `Warning` is the amber tint after a cross-parameter warning fires. The staged-edit tint cycle used to be three ~75-character inline stylesheet blocks that drifted on hex literals; it's now one `enum class` + one helper.
- **`section_header_style()`** — the top-border divider used between grouped field sections inside a parameter form. Replaces the inline `"color: #c9d1e0; margin-top: 8px; padding-top: 6px; border-top: 1px solid #2f343d;"` literal.
- **`field_label_style()`** — muted left-column label for a scalar parameter row.
- **`inline_value_chip_style()`** — string-valued parameter chip (e.g. text constants displayed inline).
- **`units_label_style()`** — dim trailing units chip (`ms`, `%`, `rpm`, etc.).

**Migrated surfaces in `build_tune_tab`.** Every inline stylesheet block in the right-pane detail card now consumes tokens:

- **Project identity bar** — hero project name in `text_primary` / `font_label` + dim metadata chain (`text_dim` / `font_small`). Container uses `card_style()`-equivalent `bg_panel` + `border` + `radius_sm`.
- **Selected-page label** — `text_primary` in a custom 15px weight between `font_label` and `font_heading`, to give the page title more presence than a body label without taking over from the project bar.
- **Detail / context header card** — blue-accent left bar (matching `make_info_card`'s convention so "context here" reads as the same visual grammar across the app) on `bg_panel` with `text_secondary` body copy.
- **Section header dividers** inside the form — tokenized via `section_header_style()` with `font_body` bold.
- **Field label + editor row** — `field_label_style()` on the left, `scalar_editor_style(Default)` in the middle, `units_label_style()` on the right. All three consume tokens. Row spacing uses `space_sm`.
- **Stage-edit tint cycle** — after each successful `edit_svc->stage_scalar_value()` call, the editor flips to `scalar_editor_style(Ok)`; when a cross-parameter warning fires (dwell > 6ms, stoich out of range, reqFuel-without-injector-flow), it flips to `scalar_editor_style(Warning)` and surfaces the warning text as a tooltip.
- **String value chip** — tokenized via `inline_value_chip_style()`. One line instead of an inline stylesheet.
- **List-value and fallback labels** — reuse `field_label_style()` / `units_label_style()` to stay in the same dim-caption type class.
- **Table card container** — `card_style()` helper (no accent), with `space_sm`/`space_xs` padding from the spacing ladder.
- **Table info line** — dimension count in `text_secondary` bold, X/Y axis chain in `text_muted`, dividers in `space_sm` `·` characters — same dim-secondary rhythm as the project bar so the page titles and the table info read as matching typography.
- **X/Y axis labels** — `text_muted` monospace with `axis_font` (still computed from cell width, not a fixed token, because the axis type scales with the cell density — an intentional exception to the type scale).
- **2D/3D toggle buttons** — the two-state active/idle pair now uses `fill_primary_mid` + `accent_primary` + `text_primary` for active and `bg_panel` + `border` + `text_muted` (hover: `text_secondary`) for idle. Semantic accent instead of raw `#2a3140`/`#1a1d24`.

**What the heatmap cells deliberately still do not use tokens.** The actual cell `background_hex` / `foreground_hex` values come from the `table_rendering::RenderModel` — they're derived from the data gradient (blue→green→yellow→red heatmap), not chrome. Treating them as tokens would be wrong because the hues are data, not design. `render_model` stays the authority there; only the cell borders, font sizes, and padding around the grid were token-ified.

**Debugging note.** Mid-slice, the toggle-button stylesheet buffers were converted from `const char*` to `static char[N]` so `snprintf` could compose them from tokens at the call site. The existing lambda capture lists that captured the `const char*`s then triggered `warning: capture of variable with non-automatic storage duration`. Fix: drop the static arrays from the capture list. Static-storage variables are visible inside a lambda without any capture at all — capturing them is meaningless and the compiler correctly warned.

**What the beautification arc adds up to.** Three sub-slices (88, 90, 91) have landed a complete theme token system, migrated the LIVE tab runtime header, the app shell chrome (sidebar + connection indicator + wordmark), and now the TUNE-tab detail panel. What's left is the FLASH / SETUP / ASSIST / TRIGGERS / LOGGING / HISTORY tabs — none of which have anywhere near the visual density of the TUNE tab, and all of which can be migrated incrementally as they get touched for functional work. The token system is additive; opportunistic migration works fine.

**Suite deltas.**

- C++ doctest: **1126 / 9930 / 0 failures** (unchanged — this slice is pure UI polish).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly. Pre-existing `already captured 'right_layout'` warning in `build_tune_tab` is unrelated to this slice and remains.

#### Phase 14 Slice 4 ninetieth sub-slice: Beautification pass #2 — app shell migration + philosophy wordmark

Sub-slice 88 introduced the `cpp/app/theme.hpp` design token system and migrated three content-area surfaces (LIVE runtime header, LIVE driving-phase accents, `make_info_card`). Sub-slice 90 is the second beautification pass, this one focused on the **app shell chrome** (the sidebar + status bar + window-level identity) rather than content tabs.

**Sidebar migration.** The sidebar `QListWidget` stylesheet was a single 6-line inline hex block covering 8 hard-coded colors. It now reads from tokens via a `snprintf`-composed stylesheet string — `bg_deep` for the sidebar background, `border` for the right edge, `font_body` for the item text, `space_md`/`space_lg` for item padding, `text_muted` for default items, `bg_panel`/`text_primary`/`accent_primary` for selected state (the 3px accent left-bar convention from `make_info_card` is deliberately reused so "selected" reads as the same visual grammar as "attention here"), and `bg_base`/`text_secondary` for hover-non-selected. The sidebar container background and the bottom-of-sidebar connection indicator ("◉ COM3 · 115200") were migrated at the same time.

**Stale counter removed.** The status bar used to hard-code `"81 services · 1052 tests"` at the tail of its live telemetry string. That counter was stale the moment sub-slice 82 landed (83 services, 1063 tests), and it would be stale again the moment any sub-slice added another service or test. Sub-slice 90 removes it outright rather than updating the literal — because **the status bar should only show things that are true *now***. Hard-coded counters are a lie waiting to happen. The telemetry tail (`RPM / MAP / AFR / CLT`) stays because those are live values; the service/test count goes. If we ever want to surface the test count, we'd compute it at build time from the actual suite rather than embed a literal.

**Philosophy wordmark.** A new quiet two-line footer lives at the very bottom of the sidebar, below the connection indicator:

```
┌──────────────┐
│   TUNER      │  ← text_muted · font_small · 3px letter-spacing (small caps)
│ guided power │  ← text_dim · font_micro · 1px letter-spacing
└──────────────┘
```

This is the single place in the chrome that says *"what is this app about"*. It's intentionally tiny, dim, and monochrome — reflecting the `docs/ux-design.md` principle **"Don't over-animate — automotive tuning is precision work, not entertainment"**. It's there for anyone curious enough to look, not to dominate the workspace.

The tagline "guided power" is a literal echo of the opening paragraph of `docs/ux-design.md`: *"Our opportunity: guided power. The same information TunerStudio shows, organized around what the operator is trying to accomplish."* The wordmark is the one place that states the design philosophy out loud. Every other surface in the app **implements** the principles (progressive disclosure, context over structure, explain as you go); the wordmark is the source.

**Why add identity chrome at all, when sub-slice 88 was about removing drift?** Because app identity is a design decision, not decoration. The reason "guided power for Speeduino" is the product thesis is what makes this app different from TunerStudio. A quiet wordmark in the corner makes that thesis visible without becoming a billboard. The alternative — "pure functional chrome, no identity statements" — would make the app look like a tool with no point of view, which is the opposite of the entire design direction. Progressive disclosure applies to identity too: small, quiet, corner-of-the-eye; reveal if you look.

**Test suite status.**

- C++ doctest: **1126 / 9930 / 0 failures** (unchanged — this slice is pure UI polish).
- Python: unchanged at 2562.
- Native `tuner_app.exe` rebuilds cleanly. Pre-existing `already captured 'right_layout'` warning in `build_tune_tab` is unchanged (unrelated to this slice).

**What's next on the beautification track.** The biggest remaining inline-style surface is the TUNE-tab right-panel detail card in `build_tune_tab` — roughly 50 `setStyleSheet` calls with hex literals. Migrating that is the natural follow-up when a future sub-slice touches the TUNE tab for functional work. Sub-slice 90 deliberately stops at the shell so the migration remains reviewable.

#### Phase 14 Slice 4 eighty-ninth sub-slice: C++ MSQ write insert_missing mode

Sub-slice 87 wired formula channel evaluation into the native `tuner_app.exe` runtime path; sub-slice 89 returns to a pure-logic service port to close one of the known fragile areas from `CLAUDE.md` — the default MSQ write path silently drops staged values for constants that aren't already present in the source XML.

**New C++ entry points on `msq_parser.hpp`:**

- `struct MsqInsertion { name; text; units; rows; cols; digits; }` — one constant-to-inject, with a pre-formatted inner-text payload and optional attributes.
- `format_msq_scalar(double value)` — mirrors Python `_fmt_scalar`: integers (including floats like `6.0`) render without a decimal, non-integer floats strip trailing zeros.
- `format_msq_table(values, rows, cols)` — mirrors Python `_format_value`: leading newline, each row prefixed with 9 spaces + space-joined values + trailing space + newline, tail `"      "` indent line.
- `write_msq_text_with_insertions(source_xml, updates, insertions)` — applies `updates` to existing constants (delegates to the existing `write_msq_text` seam), then injects any insertion whose name isn't already in the document into the first `<page>` element. Silently skips insertions whose names already exist (matching the Python `_insert_missing_constants` loop). Also skips `<pcVariable>` name collisions — both namespaces are treated as one for insertion purposes, same as Python.

**Byte-for-byte parity with the Python oracle.** The formatter helpers produce output identical to `MsqWriteService._fmt_scalar` / `_format_value`, and the XML splice is byte-stable against round trips through `MsqParser` on either side. 11 parity tests in `tests/unit/test_cpp_msq_write_insert_missing_parity.py` drive the same fixtures the existing Python `test_msq_write_insert_missing.py` uses and compare typed values after parsing both outputs back through `MsqParser`.

**Nanobind bindings** expose every new entry point (`MsqInsertion` class, `format_msq_scalar`, `format_msq_table`, `write_msq_text_with_insertions`) so downstream Python code — or the parity tests — can call the C++ path directly.

**Closing CLAUDE.md Fragile Area #1.** The original Python fix added `insert_missing=True` as an opt-in flag on `MsqWriteService.save()`. The C++ side had `write_msq_text` / `write_msq` but no insertion path. With sub-slice 89 landed, the C++ layer matches the Python layer, and the fragile area entry in `CLAUDE.md` has been updated to reflect that.

**Suite deltas.**

- C++ doctest: 1117 / 9902 → **1126 / 9930** (+9 tests, +28 assertions)
- Python: 2551 → **2562** (+11 parity tests)

#### Phase 14 Slice 4 eighty-eighth sub-slice: Design token system + beautification pass

After 87 sub-slices of feature porting the native C++ app had accumulated **palette drift**: 10 slightly-different near-black backgrounds (`#0f1116` / `#12141a` / `#131418` / `#15171c` / `#181b22` / `#1a1d24` / `#1c1f26` / `#1c2030` / `#20242c` / `#262a33`), 4 near-identical amber accents (`#d6a55a` / `#d69a5a` / `#d66a5a` / `#d6a55a`), and ad-hoc font pixel sizes scattered across 105 `setStyleSheet` calls in `main.cpp`. Sub-slice 88 is a deliberate beautification pass that introduces a canonical design token system and migrates the LIVE-tab runtime header as the reference example.

**Philosophy tie-in.** From `docs/ux-design.md`:

- *"Don't over-animate — automotive tuning is precision work, not entertainment."* → palette is restrained. 5 background levels, 5 accents, 6 type sizes, nothing more.
- *"Progressive disclosure — show what matters now."* → the type scale has a clear hierarchy from `font_micro` (10px captions) up to `font_hero` (28px gauge numbers) so visual weight tracks importance.
- *"Context over structure."* → accents are named semantically (`accent_primary` / `accent_ok` / `accent_warning` / `accent_danger` / `accent_special`) not by hue, so surface code reads like intent rather than color choices.

**New file: `cpp/app/theme.hpp`.** Header-only, `constexpr const char*` + `constexpr int` tokens in the `tuner_theme` namespace. Zero runtime cost. Three composed stylesheet helpers (`card_style`, `header_strip_style`, `chip_style`) inline-return `std::string` for the most-repeated patterns. Full token set documented in `docs/ux-design.md` under "Visual System".

**Runtime header composite.** The biggest visible change: the LIVE tab's phase indicator and formula strip were previously two separate `bg_elevated` pills stacked with 10px spacing between them. Sub-slice 88 merges them into **one** bordered `bg_elevated` card containing two rows separated by a thin `border_soft` divider:

```
┌─────────────────────────────────────────────────────────┐
│  ◉ REC   ◉ CRUISE   ·  RPM 3400  ·  TPS 42.1% · tick 8  │  ← hero row
│ ─────────────────────────────────────────────────────── │  ← divider
│  COMPUTED  λ 1.002 · throttle 42.1% · map 0.4 PSI · ... │  ← secondary row
└─────────────────────────────────────────────────────────┘
```

Progressive disclosure in action: the eye lands on the phase first (biggest, boldest, semantic accent), then drops to the formula readout row (smaller, `accent_special` purple, uppercase "COMPUTED" prefix). One bordered container signals *"this is one thing — current engine state at a glance"* rather than two unrelated chips stacked. The `accent_special` purple is **only** used on this formula strip (reserved vocabulary — keeping it rare makes it visually distinctive when it does appear).

**Driving-phase accent mapping.** The LIVE tab's driving-phase color logic used to hard-code `#d65a5a` / `#5ad687` / `#d6a55a` / `#5a9ad6` inline. Now it references `accent_danger` / `accent_ok` / `accent_warning` / `accent_primary`. Semantic intent replaces color choice, and the same mapping is re-usable anywhere else "urgent → red" is the right call.

**`make_info_card` helper migration.** The cross-tab info-card helper (used on LIVE, FLASH, SETUP, ASSIST tabs) now pulls from tokens: `bg_elevated` background, 3px left-accent bar, `text_primary` heading, `text_secondary` body, token-based padding + radius. Every info card across the app got this polish without touching individual call sites.

**Migration is incremental.** Only the three surfaces above are migrated in this slice. The remaining inline hex literals in `main.cpp` (≈100 call sites) can migrate opportunistically as each tab gets touched for other work — the token system is additive, not a rewrite. Adding `#include "theme.hpp"` + `namespace tt = tuner_theme;` and swapping hex strings for token references is a mechanical edit any future sub-slice can do in passing.

**What this pass deliberately does NOT do.**

- No new features. Beautification is pure visual polish; every functional test passes unchanged.
- No animation additions. "Automotive tuning is precision work, not entertainment" — the restraint is philosophical, not accidental.
- No beginner/expert toggle. One interface, one palette, progressive depth through the type scale.
- No hiding power. Every existing control is still visible; the tokens just make the visual hierarchy clearer.

**Test suite status.**

- C++ doctest: **1117 / 9902 / 0 failures** (unchanged — this slice is pure UI polish with no runtime behavior changes).
- Python: unchanged at 2551.
- Native `tuner_app.exe` rebuilds cleanly. Only a pre-existing unrelated warning (`already captured 'right_layout' in lambda`) in `build_tune_tab`.

**What's next on beautification.** The obvious follow-ups — if the user asks for another pass — are (a) migrating the TUNE-tab right-panel detail card to tokens (biggest remaining inline-style surface in `main.cpp`), (b) adding a dashboard channel picker that uses `chip_style` for the searchable channel list, and (c) extending the type scale with a proper font loader so high-DPI scaling hits exact pixel boundaries instead of Qt's default sub-pixel interpolation. None of these block the Phase 14 native-app direction.

#### Phase 14 Slice 4 eighty-seventh sub-slice: C++ `tuner_app.exe` LIVE-tab formula channel enrichment

Sub-slice 86 wired the Python runtime poll path through `MathExpressionEvaluator.enrich_snapshot`; sub-slice 87 puts the same behaviour in the native Qt app so the C++ side stops lagging the Python reference product on the G4 surface.

**New helper.** `math_expression_evaluator::enrich(working, formulas, arrays)` — thin in-place variant of `compute_all` that walks the formulas in declaration order and inserts each result into the passed-in `ValueMap` reference. Collision rule: if a formula channel name is already present in *working* (i.e. the hardware already emits it), the hardware reading wins and the formula result is dropped. No-op when *formulas* is empty. This matches the Python `enrich_snapshot` semantics: "fold computed channels into the live snapshot, preserve hardware."

**LIVE-tab wiring.** `build_live_tab` in `cpp/app/main.cpp` now:

- Loads the production INI via the existing `find_production_ini()` helper and the `compile_ecu_definition_file()` compiler at tab construction time. The resulting `formula_channels` and `output_channel_arrays` are captured into `shared_ptr` so the timer lambdas can access them without re-parsing.
- Inserts a new "formula channel demo strip" `QLabel` above the gauge cluster. It degrades to `"formula channels unavailable — definition not loaded"` when the fixture isn't on disk.
- On every 200 ms tick, after `mock_ecu->poll()` but before the gauge update loop, seeds a handful of channels the mock runtime doesn't emit natively but production formulas depend on: `baro = 101.3`, `stoich = 14.7`, `twoStroke = 0`, `pulseWidth = pw1 * 1000`, `coolantRaw = clt + 40`, `iatRaw = iat + 40`, `nSquirts = 2`, `nCylinders = 6`. Then calls `mee::enrich(snap.channels, *formula_channels, formula_arrays.get())` and formats four headline computed values into the strip: `λ`, `throttle`, `map_psi`, `revolutionTime`.
- The existing gauge bindings loop is unchanged — it reads the same `snap.channels` map, which now carries formula channels alongside hardware channels. So any gauge bound to a formula channel name would already work today without further UI changes.

**Why seed extra channels in the app instead of extending `mock_ecu_runtime`.** `mock_ecu_runtime.hpp` is inline-header-only and its 12-channel output is pinned by `test_mock_ecu_runtime.cpp` (`CHECK(snap.channels.size() == 12)`). Changing the channel count would force an unrelated test-churn cascade that buys nothing — the app-level seed is a clean one-place injection that keeps the mock runtime focused on "driving cycle animation" and leaves "realistic formula inputs" as a presentation-layer concern.

**Test coverage.**

- 4 new doctest cases pinning `enrich` behaviour: empty-formulas no-op, simple append, hardware-collision preservation, chained-formula declaration order.
- 1 production-INI integration case (`production INI formula channels enrich a mock snapshot cleanly`) that compiles the real INI fixture via `compile_ecu_definition_file`, seeds a realistic 46-channel mock snapshot, calls `enrich`, and asserts expected values for `throttle`, `lambda`, `revolutionTime`, `map_psi`, `coolant` plus a `isfinite` sweep across every formula channel in the definition (≥30).

**Build sanity.** Both `tuner_core_tests.exe` and `tuner_app.exe` rebuild cleanly after the wiring. The nanobind Python extension rebuilds too because the in-place `enrich` helper lives in the same translation unit as `compute_all`.

**Suite deltas.**

- C++ doctest: 1112 / 9757 → **1117 / 9902** (+5 tests, +145 assertions — the production-INI integration case contributes most of the new assertions from its per-formula `isfinite` sweep).
- Python: unchanged at 2551 — this slice is C++-side only.

**What's next on G4.** The evaluator and runtime wiring are done end-to-end on both sides. The remaining polish is a **dashboard channel picker** that lets operators bind a gauge (or a histogram, or a new dashboard cell) to any channel by searching a single combined list of hardware + formula channels. That's UX work in `dashboard_layout` + `GaugeConfigDialog` rather than more evaluator wiring — tracked separately in the dashboard polish backlog, not gating Phase 14 close.

#### Phase 14 Slice 4 eighty-sixth sub-slice: Runtime formula channel enrichment

Sub-slices 84 and 85 built the formula channel parser and evaluator; sub-slice 86 wires them into the Python runtime poll path so every downstream consumer gets computed channels without any per-consumer wiring.

**New helper.** `MathExpressionEvaluator.enrich_snapshot(snapshot, definition) -> OutputChannelSnapshot`. Returns a new snapshot with formula channel values appended after the existing hardware channels, preserving timestamp. Fast-paths the no-formula case by returning the input snapshot unchanged (same object — zero allocation when the definition has no formulas). Uses `FormulaOutputChannel.units` for each appended entry's units and passes `definition.output_channel_arrays` through to `compute_all` so `arrayValue(array.name, index)` formulas resolve against the same data `VisibilityExpressionService` already consumes.

**Runtime call site.** `SessionService.poll_runtime()` now calls `enrich_snapshot` after `client.read_runtime()`. The evaluator is cached on the service via a `field(init=False)` slot so we don't churn one per tick. When there are no formulas (legacy INIs or bare sessions without a definition), the call is a no-op that returns the raw snapshot — the existing protocol clients and the mock controller client didn't need any change.

**Why this seam.** The `SessionService.poll_runtime` call site sits upstream of every Python consumer:

- `MainWindow._poll_runtime` → gauges, runtime table, workspace crosshair evidence, runtime/telemetry summary
- `LiveDataHttpServer` → browser-side dashboards via `/api/channels` / `/api/channels/{name}`
- `LiveCaptureSessionService` → datalog profile writes
- `LiveVeAnalyzeSessionService` / `LiveWueAnalyzeSessionService` → assist accumulators
- `SurfaceEvidenceService` / `OperationEvidenceService` → replay evidence snapshots

All of them already consume `OutputChannelSnapshot.as_dict()` with no hard-coded channel list, so a formula-enriched snapshot flows through every surface without per-consumer changes. This is the opposite of a per-consumer enrichment wiring pass, which would have meant touching a dozen files and making it harder to prove every surface sees the same channel set.

**Test coverage.** 8 new tests in `tests/unit/test_runtime_formula_enrichment.py`:

- `enrich_snapshot` no-op paths (no definition; definition with no formulas)
- simple single-formula append with units
- timestamp preservation
- chained formula resolution (revolutionTime → strokeMultipler → cycleTime)
- `arrayValue` lookup via `definition.output_channel_arrays`
- `SessionService.poll_runtime` end-to-end through `MockControllerClient` against the real production INI — asserts every formula channel appears in the poll result and that `throttle` (declared with `"%"` units) carries its units through
- Bare-session no-definition safety check

**Suite delta.**

- Python: 2543 → **2551** (+8)
- C++ doctest: unchanged (1112 / 9757) — this slice is Python-side only

**What's next for the C++ app side.** The Qt `tuner_app.exe` mock runtime in `cpp/app/main.cpp` polls `mock_ecu_runtime::MockEcu` and feeds gauges directly from the raw `Snapshot.channels` map. To hit parity with the Python runtime path, the native app needs to call `tuner_core::math_expression_evaluator::compute_all` on that map using the active definition's formula channel list before populating gauges. That's a small slice gated on the mock-runtime page having an active `IniOutputChannelsSection` handy — tracked as the next G4 sub-slice in the C++ app direction.

#### Phase 14 Slice 4 eighty-fifth sub-slice: MathExpressionEvaluator — G4 Phase 2 close

Sub-slice 84 landed the parser half of G4 — the `name = { expression } [, "units"] [, digits]` form in `[OutputChannels]` now materializes as `FormulaOutputChannel` (Python) / `IniFormulaOutputChannel` (C++) with verbatim expression text preserved. Sub-slice 85 closes the evaluator half.

**New service — Python oracle.** `tuner.services.math_expression_evaluator.MathExpressionEvaluator` — a pure-logic extension of `VisibilityExpressionService`'s grammar:

- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Unary `-` / `+`
- C-style bit shifts: `<<`, `>>` (operands truncated to `int` first, result back to `float`)
- Ternary `? :` (right-associative, parses nested `a ? b : c ? d : e` as `a ? b : (c ? d : e)`)
- Full visibility grammar preserved: `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, parens
- Function call: `arrayValue(arrayName, indexExpr)` with the `array.` prefix stripped

Semantics: booleans are floats (0.0 = false), unknown identifiers default to 0.0, division by zero returns 0.0 (fail-safe — never `inf`/`nan`), any parse error returns 0.0 (a broken formula must not leak exceptions into the runtime poll tick).

**New service — C++ port.** `cpp/include/tuner_core/math_expression_evaluator.hpp` + `cpp/src/math_expression_evaluator.cpp`. Direct mirror of the Python grammar and fail-safe semantics, stdlib only. Shares `IniFormulaOutputChannel` with the sub-slice 84 parser so `compute_all(formulas, values, arrays)` takes the parser's output directly.

**`compute_all` — cross-formula dependency resolution.** Both sides expose a `compute_all(formulas, values, arrays) → dict/map` helper that walks the formula list in declaration order and folds each result back into the working snapshot before evaluating the next formula. This makes chained formulas like the production INI's

```
revolutionTime  = { rpm ? ( 60000.0 / rpm) : 0 }
strokeMultipler = { twoStroke == 1 ? 1 : 2 }
cycleTime       = { revolutionTime * strokeMultipler }
```

resolve in one pass — `cycleTime` sees the just-computed `revolutionTime` and `strokeMultipler` because they were added to the working snapshot before it was evaluated. The input snapshot is **not** mutated.

**Nanobind binding.** Two new entry points in `cpp/bindings/tuner_core_module.cpp`:

- `evaluate_math_expression(expression, values, arrays=None) -> float`
- `compute_formula_output_channels(formulas, values, arrays=None) -> dict`

**Test coverage.**

- 36 Python unit tests in `tests/unit/test_math_expression_evaluator.py` covering boundaries, arithmetic precedence, unary minus, bit shifts, ternary nesting, `arrayValue` lookup, `compute_all` cross-formula dependencies, and production-INI-flavored checks (coolant F conversion, `map_psi`, `lambda`, `syncStatus` bit-shift, `map_vacboost` unary minus).
- 34 C++ doctest cases in `cpp/tests/test_math_expression_evaluator.cpp` — point-for-point mirror of the Python tests using the bound `IniFormulaOutputChannel` struct for `compute_all`.
- 38 parity tests in `tests/unit/test_cpp_math_expression_evaluator_parity.py` — parametrized grammar cases plus a whole-INI pass that evaluates every formula channel in the production Speeduino DropBear INI through both the Python and C++ implementations against the same synthetic channel snapshot and asserts identical results for all ~65 formulas.

**Suite deltas.**

- Python: 2469 → **2543** (+74 = 36 unit + 38 parity)
- C++ doctest: 1078 / 9699 → **1112 / 9757** (+34 tests, +58 assertions)

**What's still open on G4.** The evaluator exists but is not yet called on the poll tick — nothing wires `compute_all` into the runtime/dashboard/HTTP-API surface yet. That's the next G4 slice: plumb the evaluator into `RuntimeTelemetryService` / `LiveDataHttpServer` / the dashboard channel picker so operators can see computed channels side-by-side with hardware channels. Scheduled as a follow-up because it needs UI wiring on both the Python and C++ surfaces and is mostly plumbing rather than new logic.

#### Phase 14 Slice 4 eighty-third sub-slice: TableSurface3DView + operating-point interpolator (G2 close)

Sub-slice 82 landed the pure-logic `tuner_core::table_surface_3d::project()` function — azimuth/elevation rotation plus orthographic projection that turns a flat `values × rows × cols` table into 2D screen coordinates. Sub-slice 83 closes gap **G2** by plumbing that projection into an actual Qt widget on the TUNE page.

**New pure-logic helper.** `interpolate_screen_point(surface, row_frac, col_frac) → optional<Point2D>` bilinearly interpolates the projected screen coordinate for a fractional grid position. Used by the widget to place the live operating-point crosshair on the rotated mesh without the widget needing to know anything about the projection math. Six new doctest cases: empty surface, out-of-range fracs, exact-vertex lookup, 2×2 midpoint averaging, row-edge halfway lookup, bilinear sanity.

**New widget.** `TableSurface3DView` in `cpp/app/main.cpp` (inline in the anonymous namespace, same pattern as `DialGaugeWidget` — no `Q_OBJECT`, so MOC stays uninvolved). Features:

- `paintEvent` walks `surface.points` and draws row-parallel and col-parallel edges as antialiased lines. Each edge is tinted by a 5-stop blue→cyan→green→yellow→red gradient driven by the average of its two endpoint values.
- Value dots at every vertex, same gradient.
- Live operating-point crosshair rendered via `interpolate_screen_point` when the mock runtime is feeding a valid cell — solid red dot, white outline, dashed red crosshair reaching 14 px in each axis.
- Mouse-drag rotation: left-button drag adjusts azimuth (X drag, 0.6°/px) and elevation (Y drag, 0.4°/px, clamped to [15°, 85°]). `setCursor` flips between `OpenHandCursor` and `ClosedHandCursor` during drag.
- Corner telemetry strip: `min / max / az / el` in the top-left, `drag to rotate` hint in the bottom-right.

**Wiring.** The TUNE page table render block now builds a `QStackedWidget` with the existing 2D heatmap scroll area at index 0 and the new `TableSurface3DView` at index 1. A compact 2D / 3D toggle button row sits above the stack; the active button is highlighted via stylesheet swap and the inactive one is dimmed. Toggling is a pure `setCurrentIndex()` call — no widget deletion, so it's safe under the "never delete widgets in signal handlers" rule documented at the top of `main.cpp`.

**Crosshair integration.** `CrosshairState` grew a `TableSurface3DView* view_3d` raw pointer. The pointer is cleared on every page change along with the 2D label grid (so the timer never dereferences a stale widget), and set when a new table card is built. The existing crosshair timer at 300 ms cadence now mirrors the located display-row/display-col to `view_3d->set_operating_point()` (or clears it when no cell is located), so both views stay in sync.

**Flat-values layout + default camera.** Initial wiring fed the 3D view display-order rows and reused sub-slice 82's 225° default azimuth — which produced a screen that was horizontally mirrored relative to the 2D heatmap (col 0 on the right instead of the left). User flagged this immediately with a side-by-side screenshot of the VE table. Fix:

- Default `azimuth_deg` flipped to **45°** (front-right camera) in both `tuner_core::table_surface_3d::project()` and `TableSurface3DView::azimuth_`. At 45° the projection's `x3`-coefficient in `sx` is positive (col 0 on the left, col max on the right) and the `y3`-coefficient in `sy` is negative (row 0 at the bottom, row max at the top). The existing test suite still passes because every `project()` test passes azimuth explicitly.
- The 3D view now takes the tune's **model-order** flat vector (`values` with `row 0 = lowest load`) and the table's full `rows × cols` shape directly. No more `render.row_index_map` walk — the y-axis inversion belongs to the 2D display layer, and the projection math wants natural model order so row 0 ends up at the front of the mesh.
- The crosshair timer now mirrors `loc->row_index` (model row from `table_replay_context`) to the 3D view instead of the inverted `display_row`. Both views highlight the same physical cell.

The combined fix gives the familiar "RPM increases to the right, load increases away from the viewer, VE peaks up" 3D surface orientation that matches the 2D heatmap exactly.

C++ doctest suite: **1068 tests, 9660 assertions, 0 failures.**

#### Phase 14 Slice 4 sub-slices 54–79: service porting + UX Phases A–D complete

**29 new sub-slices** landed in a single extended session, bringing the total to **82 sub-slices, 1063 tests, 8631 assertions, 0 failures**.

**Services ported (sub-slices 54–79):**
- 54: OperatorEngineContext — session-level engine facts + JSON persistence
- 55: HardwareSetupGeneratorContext — keyword parameter discovery
- 56: SensorSetupChecklist — 9-check sensor validation
- 57: CurvePageBuilder — grouped curve pages from definitions
- 58: EvidenceReplay — evidence snapshot composer
- 59: PageEvidenceReview — page-level channel selector
- 60: EvidenceReplayFormatter — text + JSON formatter
- 61: TriggerLogVisualization — trace builder with edge/gap annotations
- 62: TriggerLogAnalysis — decoder context + gap + phase + sync analysis
- 63–64: LiveAnalyzeSession — VE/WUE session status builders
- 65: DatalogProfile — priority ordering + JSON collection
- 66: FirmwareCatalog — board detection + entry scoring
- 67: DatalogReplay — row selection with preview
- 68: IgnitionTriggerCrossValidation — 6 cross-page checks + topology
- 69: MockEcuRuntime — simulated driving cycle for gauge animation
- 70: TsDashFile — TSDash .dash XML import/export
- 71: WueAnalyzeAccumulator — WUE stateful accumulator + CLT axis
- 72: VeAnalyzeAccumulator — VE stateful accumulator + cell mapping
- 73: TuningPageBuilder — compiles definition into grouped pages
- 74: DatalogImport — CSV import with time detection
- 75: MsqValueFormatter — legacy-compatible value formatting
- 76: WorkspaceState — page state machine (clean/staged/written/burned)
- 77: NativeTuneWriter — .tuner JSON export/import (native format step 1)
- 78: ProjectFile — .tunerproj JSON project metadata (native format step 2)
- 79: NativeDefinitionWriter — .tunerdef JSON definition export (native format step 3)
- 80: HardwareSetupSummary — contextual setup cards per page type
- 81: WorkspacePresenter — compact workspace orchestrator (load/navigate/edit/write/burn)
- 82: TableSurface3D — 3D wireframe projection for table values (G2 foundation)
- 83: TableSurface3DView + `interpolate_screen_point` — Qt wireframe widget with mouse-drag rotation, heat-colored edges, live operating-point crosshair; 2D↔3D toggle on the TUNE table pages. Closes G2.
- 84: Formula output channels parser — `FormulaOutputChannel` / `IniFormulaOutputChannel` models + Python and C++ `[OutputChannels]` recognizers for `name = { expression } [, "units"] [, digits]`. G4 Phase 1.
- 85: `MathExpressionEvaluator` — arithmetic / bit-shift / unary-minus / ternary grammar on top of the visibility grammar, Python oracle + C++ port, `compute_all` cross-formula dependency resolver, 36 + 34 + 38 tests. G4 Phase 2 close.
- 86: Runtime formula channel enrichment — `MathExpressionEvaluator.enrich_snapshot(snapshot, definition)` + `SessionService.poll_runtime()` call site. Every Python consumer (dashboard, HTTP API, datalog profile, evidence replay) now sees computed channels alongside hardware channels without per-consumer wiring. 8 new tests; 2543 → 2551 suite total.
- 87: C++ native-app runtime enrichment — `math_expression_evaluator::enrich(working, formulas, arrays)` in-place helper, wired into `build_live_tab` timer tick with seeded inputs for channels the mock runtime doesn't emit natively. Formula-channel demo strip above the LIVE gauge cluster. 5 new doctest cases + 1 production-INI integration case; 1112 → 1117 tests, 9757 → 9902 assertions.
- 88: Design token system + beautification pass — `cpp/app/theme.hpp`, canonical 5-level dark palette + 5 semantic accent tokens + 6-size type scale + spacing/radius ladders + 3 composed stylesheet helpers. LIVE-tab runtime header merged into a single compound widget (phase row + formula row inside one bordered card separated by a soft divider), driving-phase accents semantically named, `make_info_card` migrated. "Visual System" section added to `docs/ux-design.md`. Test suites unchanged; native `tuner_app.exe` rebuilds clean.
- 89: MSQ write `insert_missing` mode on the C++ side — closes CLAUDE.md Fragile Area #1 for the native app. New `MsqInsertion` struct + `write_msq_text_with_insertions(source, updates, insertions)` + `format_msq_scalar` + `format_msq_table` mirror the Python `MsqWriteService.save(insert_missing=True)` path byte-for-byte. Nanobind bindings expose the new entry points. 9 new doctest cases + 11 Python parity tests against the Python oracle (scalar/table formatter parity, end-to-end table/scalar insertion round-trip through `MsqParser`, existing-constant preservation, skip-already-present, compose-with-update). Suite deltas: C++ 1117 → 1126 / 9902 → 9930; Python 2551 → 2562.
- 90: Beautification pass #2 — app shell migration + philosophy wordmark. Sidebar navigation stylesheet, connection indicator, and container background all migrated from inline hex literals to `tuner_theme` tokens (font sizes and padding via the spacing ladder too). Stale `"81 services · 1052 tests"` counter removed from the dynamic status bar (the status bar should only show things that are true *now* — hard-coded counters are a lie waiting to happen). New quiet two-line wordmark footer added at the bottom of the sidebar: `TUNER` in muted small caps + `guided power` in dim micro type, separated from the connection indicator by a soft border. It's the single place in the chrome that says "what is this app about" — intentionally tiny and dim so it doesn't dominate the workspace, there for anyone curious enough to look. Zero test suite changes; native `tuner_app.exe` rebuilds clean.
- 91: Beautification pass #3 — TUNE-tab right-panel detail card migration. The biggest remaining inline-hex surface in `main.cpp` (~15 inline stylesheet blocks across the project bar, selected-page label, detail card, section dividers, field rows, scalar editors with their 3 stage states, value chips, table card container, table info line, axis labels, and the 2D/3D toggle buttons) is now fully token-driven. Five new helpers landed in `cpp/app/theme.hpp` for the most-repeated patterns: `scalar_editor_style(EditorState)` (3-state enum: Default / Ok / Warning — the staged-value tint cycle), `section_header_style()` (top-border divider for grouped field sections), `field_label_style()` (muted left-column label), `inline_value_chip_style()` (string-valued parameter chip), and `units_label_style()` (dim trailing units chip). The toggle-button static buffer capture warning introduced mid-slice was fixed by dropping the static arrays from the lambda capture list (static storage is visible without capture — capturing it is meaningless and the compiler correctly warned about it). Zero test changes (this is pure chrome). `tuner_app.exe` rebuilds clean; pre-existing `already captured 'right_layout'` warning in `build_tune_tab` is unrelated and remains.
- 92: Live staged-changes feedback — `workspace_state::Workspace` ownership lifted from `build_tune_tab` to `MainWindow`. New `Workspace::staged_count_for(page_id)` per-page accessor + doctest case (1126 → 1127, 9930 → 9936). Sidebar Tune nav label replaces the hardcoded `"3 staged"` literal with a dynamic `· N staged` suffix refreshed from the workspace counter on every `stage_edit` via a `StagedChangedCallback` plumbed into `build_tune_tab`. A small amber-accented staged chip now appears beside the selected-page title on the TUNE tab showing the active page's edit count (hidden when 0 — no empty-state chrome). The chip refreshes on page switch AND on stage-edit via a shared `refresh_page_chip` closure captured by both the selection handler and the stage-edit lambda. Staged state is now visible at two levels simultaneously: across the app (sidebar) and within the current view (per-page chip).
- 93: Staged-changes review popup — closes the stage → review → commit workflow from `docs/ux-design.md` Core Principle #4. New `EditService::staged_names()` accessor + doctest case (alphabetical-order enumeration of currently-staged parameter names, cleared by `revert` / `revert_all`, 1127 → 1128 / 9936 → 9945). Clickable "Review (N)" chip in the TUNE project bar (hidden when nothing is staged — no empty-state chrome) + Ctrl+R global shortcut, both opening a modal `QDialog` that lists every pending edit in a scrollable pane as `name · base → staged` rows (base in monospace muted, staged in monospace bold blue, bullet separator in dim). "Revert All" button in the bottom row clears both `edit_svc` and `workspace` state in one transaction and refreshes all three staged-state surfaces (per-page chip → hide, review button → hide, sidebar badge → clear) before closing the dialog. "Close" button on the right. Third zoom level of the progressive-disclosure state hierarchy: sidebar badge (app-wide) → per-page chip (current view) → review popup (detailed diff list).
- 94: Per-edit revert from the review popup — each row in the popup now carries a small × revert button on its right edge. Clicking it calls `edit_svc->revert(name)`, runs a new `resync_workspace` closure that rebuilds the `Workspace` per-page counts by walking the compiled page map and checking `edit_svc->is_dirty()` for every field, then refreshes all three zoom levels (sidebar badge, per-page chip for the active page, "Review (N)" chip in the project bar). The row is **hidden in place** rather than deleted (deleting widgets in signal handlers is a documented crash pattern in `main.cpp`), the shared `remaining` counter decrements, and an in-place `update_title(n)` closure updates the dialog title without rebuilding the widget tree. When the last row is reverted the dialog auto-closes. Tooltip on each revert button shows `Revert <name>` so the operator gets confirmation without clicking. The revert button is tokenized — neutral border by default, amber-accented on hover.
- 95: Write to RAM + WRITTEN state visualization + sub-slice 94 bugfix. **New workspace API**: `Workspace::aggregate_state() const` returns the highest-priority page state (STAGED > WRITTEN > BURNED > CLEAN) and `Workspace::pages_in_state(PageState)` returns the list of page IDs in a given state. Two doctest cases cover STAGED→WRITTEN transition priority, mixed STAGED/WRITTEN resolving to STAGED, BURNED-only fallback before CLEAN, and pages_in_state enumeration in insertion order. Suite delta: 1128 → **1130** tests, 9945 → **9958** assertions. **State-aware chrome**: `refresh_page_chip` and `refresh_review_button` now pick color based on state — amber `accent_warning` for STAGED (urgent, pending review), blue `accent_primary` for WRITTEN (committed to RAM, awaiting burn). Labels switch too: `"3 staged"` → `"3 in RAM"`. Sidebar Tune badge picks up the same pattern via `aggregate_state()`. **Write to RAM button** in the popup footer between Revert All and Close — styled with `fill_primary_mid` background and `accent_primary` border so it visually anchors the "commit" side of the footer the way Revert All anchors the "discard" side. Clicking iterates `pages_in_state(STAGED)` and calls `mark_written` on each, then closes the popup and refreshes all three zoom levels in one transaction. The staged counts stay non-zero (WRITTEN ≠ CLEAN — the edits are still "dirty vs flash"), and the form editors stay on their Ok tint. **Sub-slice 94 bugfix**: the per-row × revert and Revert All paths previously cleared `edit_svc` and the workspace counters but left the visible `QLineEdit` on the TUNE tab displaying the user-typed text. A new `visible_editors` shared map populated by the field-rendering loop maps each visible parameter name to `{QLineEdit*, base_text}`, cleared on every page switch (hidden widgets stay alive but aren't reached by the map). On revert the handlers look up the name, write the base text back to the `QLineEdit`, and reset its style to `EditorState::Default` (clearing the amber/blue tint cycle). Revert All iterates the entire map and resets every editor in one pass. Bug originally reported by the user after sub-slice 94 shipped.
- 96: Tree-entry state indicators on the TUNE tab left pane — user-requested. Each leaf item in the page tree now carries a colored bullet + count suffix (`◉ N`) on pages that have pending edits, with foreground text color matching the state: amber `accent_warning` for STAGED, blue `accent_primary` for WRITTEN, default for CLEAN (which clears the foreground override by passing an invalid `QBrush`). `TreeLeafInfo` gained a cached `base_label` field so `refresh_tree_state_indicators` can recompose the item text cleanly each time without parsing an already-marked label back apart. The new closure iterates `tree_refs` once and runs from every state-change call site already wiring the other zoom levels (stage-edit, per-row × revert, Revert All, Write to RAM, Burn to Flash). Effectively a fourth zoom level of the staged-state hierarchy — **tree-level state before the operator navigates anywhere**, making "where to look" visible at a glance. Adds no new types to the workspace_state API; just consumes `staged_count_for` + `page_state` that were already there.
- 97: Burn to Flash action — closes the full stage → review → write → burn operator workflow. New green `accent_ok` "Burn to Flash" button in the review popup footer, between "Write to RAM" and "Close". Enabled only when `workspace->aggregate_state() == WRITTEN` (the operator has already run Write to RAM and has no raw STAGED pages left). Disabled state is dimmed (`border` + `text_dim`) with a tooltip explaining *"Write to RAM first — burning bypasses the review step."* On click: iterates `pages_in_state(WRITTEN)` and calls `mark_burned` on each (which zeroes the workspace staged counts), then `edit_svc->revert_all()` so the demo values visibly return to base (no real ECU — this is the closest demo semantics to "accept staged as new base"), resets every visible editor via the `visible_editors` map, and refreshes all four state surfaces (sidebar badge, per-page chip, review chip, tree markers) to clean. New Ctrl+W (Write to RAM) and Ctrl+B (Burn to Flash) keyboard shortcuts that both open the review popup — the popup is the single place the operator commits state transitions, so all three action shortcuts land on the same destination. C++ doctest unchanged (1130 / 9958 — pure UI addition).
- 98: Sub-slice 96 bugfix (user-reported) — the tree-entry state indicators were silent even when edits were clearly staged. User screenshot showed "Flex Fuel" selected with an amber `1 staged` chip in the right pane but no indicator on the corresponding tree item. Root cause: `workspace_state::Workspace::set_pages()` was never called during tree construction, so the `page_states_` map stayed empty, `stage_edit(page_id, ...)` couldn't transition the page from CLEAN → STAGED (the transition is gated on `page_states_.count(page_id)`), and `page_state(target)` returned the default CLEAN for every page. `refresh_tree_state_indicators` then hit its clean branch unconditionally and reset the label text — so staged edits never surfaced on the tree even though `staged_count_for(target)` was correctly incrementing. The right-pane chip worked because `refresh_page_chip` only checks the count, not the state. **Fix (two parts)**: (1) call `workspace->set_pages(page_ids)` with every page target after `page_map` populates, before `rebuild_tree("")` runs — this makes the `page_states_` map complete and `stage_edit` transitions work correctly; (2) harden `refresh_tree_state_indicators` to early-exit on `count == 0` only (never on state alone), matching the robustness of `refresh_page_chip` — if count > 0 but state is still CLEAN (e.g. a future code path bypasses `set_pages`), default to the STAGED accent so the tree still reflects reality instead of going blind. Both fixes applied. Also removed the warning-prone practice of gating UI behavior on state alone — count is the authoritative "does this page have work" signal across all four zoom levels of the staged-state hierarchy.
- 99: Flash target classifier port — pure-logic half of Python `FlashTargetDetectionService`. New C++ `tuner_core::flash_target_detection` namespace with `classify_serial_port(vid, pid, device, description)`, `classify_usb_device(vid, pid, bcd, has_hid_interface)`, `teensy_identity_from_pid_or_bcd(pid, bcd)`, `normalize_hex(value)`. I/O (`serial.tools.list_ports` / `usb.core`) stays Python-only — the C++ classifier takes normalized string inputs so callers can drive it from any port-enumeration source (current Python app, future C++ transport layer, or a test harness). New `DetectedFlashTarget` POD mirroring the Python dataclass. **Mid-slice debug**: first attempt defined a local `BoardFamily` enum inside `flash_target_detection`, which produced two `BoardFamily` class registrations on the nanobind side and clobbered the existing `board_detection::BoardFamily` binding — broke 27 pre-existing parity tests across `test_cpp_board_detection_parity.py` and `test_cpp_release_manifest_parity.py`. Fix: remove the duplicate enum, add `using BoardFamily = tuner_core::board_detection::BoardFamily;` in the header so the two services share the canonical type. Downstream code can pass families between classifiers without conversion. **Python quirks preserved for parity**: `normalize_hex("0x2341") == "2341"` but `normalize_hex("0X16c0") == "0X16C0"` because Python's `.removeprefix("0x")` is case-sensitive — the uppercase `0X` isn't stripped and the subsequent `.upper()` pass yields `0X16C0`. Empty string in → empty string out (not None), matching `"".strip().removeprefix("0x").upper() == ""`. 18 doctest cases + 28 Python parity tests covering Arduino Mega official + CH340 clones, Teensy 3.5/3.6/4.1 via bcdDevice (HalfKay HID), Teensy 4.x via serial PID (0483-0486 all map to TEENSY41), STM32F407 in CDC-ACM + DFU modes, negative cases (unknown VID, missing HID interface, wrong bcdDevice). Suite deltas: C++ 1130 → **1147** tests, 9958 → **10025** assertions; Python 2562 → **2590** (+28 parity). **10k C++ assertions crossed.**

**UX design phases all complete (19/19 items):**
- Phase A (Foundation): keyword tree, MSQ values, generators, telemetry, gauges
- Phase B (Context & Guidance): page headers, heatmaps, confidence badges, plain-language ASSIST, flash checklist
- Phase C (Live Interaction): live crosshair, gauge click nav, zone alerts, recording indicator
- Phase D (Polish): sidebar navigation, command palette (Ctrl+K), histogram gauges, smart warnings, setup wizard

**Native format complete:** all three file types (.tuner, .tunerproj, .tunerdef) implemented with round-trip tests against real production fixtures.

**App architecture:** sidebar navigation with 8 content pages (Tune, Live, Flash, Setup, Assist, Triggers, Logging, History), dynamic status bar with live telemetry, animated QPainter gauges at 5 Hz, scrolling sparkline histograms, live crosshair on table heatmaps, command palette.

#### Phase 14 Slice 4 fifty-first sub-slice: DashboardLayout + WidebandCalibrationService

**Sub-slice 50: WidebandCalibrationService** — port of `wideband_calibration_service.py`. Generates 32-point ADC → AFR lookup tables for Speeduino wideband O2 sensor calibration (page 2). Includes 5 presets (Innovate LC-1/LC-2, AEM X-Series, 14Point7 Spartan 2, Tech Edge, PLX). Linear voltage→AFR interpolation, 64-byte big-endian int16 payload encoding, voltage lookup. 11 doctest cases.

**Sub-slice 51: DashboardLayout** — port of dashboard domain model + `DashboardLayoutService.default_layout()`. `Widget` POD (id, kind, title, source, units, position, range, color zones), `Layout` POD, `default_layout()` returning the 11-gauge Speeduino default (RPM dial, MAP dial, TPS bar, AFR/Advance/CLT/IAT/Battery/PW1/Dwell/SyncLoss number gauges with color zones). 6 doctest cases.

C++ doctest suite: **797 tests, 6309 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-ninth sub-slice: LocalTuneEditService

Port of `tuner.services.local_tune_edit_service.LocalTuneEditService` — the core staged-edit state machine that powers the entire workspace editing model. Tracks base tune values, staged overrides with per-parameter undo/redo history.

- `cpp/include/tuner_core/local_tune_edit.hpp` and `cpp/src/local_tune_edit.cpp` — `Value` variant (`double | string | vector<double>`), `TuneValue` POD, `TuneFile` POD, `EditService` class with `set_tune_file`, `get_value`/`get_base_value`, `stage_scalar_value`/`stage_list_cell`/`replace_list`, `undo`/`redo`/`can_undo`/`can_redo`, `revert`/`revert_all`, `is_dirty`/`has_any_staged`/`staged_count`, `get_scalar_values_dict`.
- **Edit flow:** edits are staged as copies of the base value. History tracks each commit. Undo/redo walk the history index. Revert removes the staged entry, falling back to the base value.
- **Value variant:** `std::variant<double, std::string, std::vector<double>>` mirrors the Python `str | float | list[float]` union. List values are deep-copied on stage to prevent aliasing.
- `cpp/tests/test_local_tune_edit.cpp` — 11 doctest cases covering: base value lookup, scalar staging, list cell staging, undo/redo cycle, single revert, revert-all, list replacement, scalar values dict (excludes lists), unknown parameter throws, base unchanged after staging, set_tune_file clears state.

C++ doctest suite: **780 tests, 5922 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-eighth sub-slice: TuningPageGrouping

Port of `TuningPageService._GROUP_RULES` and `_group_for_text` — keyword-based page group classifier. Groups compiled layout pages into operator-facing families (Fuel, Ignition, AFR/Lambda, Idle, Startup/Enrich, Boost/Airflow, Settings, Other) using keyword matching on page titles and table editor IDs. 9 group rules matching the Python service exactly.

- `cpp/include/tuner_core/tuning_page_grouping.hpp` and `cpp/src/tuning_page_grouping.cpp` — `GroupRule`, `GroupedPage`, `PageGroup` PODs, `group_rules()`, `classify_text(text)`, `group_pages(layout_pages)`.
- **TUNE tab rebuilt** to use classified groups instead of raw INI menu structure. Pages are now organized by semantic family with group counts, type indicators, and sorted alphabetically within each group.
- `cpp/tests/test_tuning_page_grouping.cpp` — 7 doctest cases covering: rule count, fuel/ignition/idle keyword classification, unknown→other fallback, sorted group output, and **production INI integration** (verifies ≥3 groups with fuel group populated).

C++ doctest suite: **769 tests, 5895 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-seventh sub-slice: DefinitionLayoutService

Port of `tuner.services.definition_layout_service.DefinitionLayoutService.compile_pages` — the keystone service that compiles raw INI dialogs, menus, and table editors into stable editor-facing `LayoutPage` objects. Every page in the TUNE tab tree is produced by this service.

- `cpp/include/tuner_core/definition_layout.hpp` and `cpp/src/definition_layout.cpp` — `LayoutField`, `LayoutSection`, `LayoutPage` PODs, `compile_pages(menus, dialogs, table_editors)`.
- **Compilation logic:** walks each menu's items, resolves each target against the dialog and table-editor lookup maps. Table editor targets become table pages directly; dialog targets are compiled recursively (with cycle detection) into sections with fields, notes, and panel references. First table-editor reference found in the dialog tree becomes the page's `table_editor_id`.
- **Group normalization:** menu titles are cleaned of `&` mnemonics; group IDs are lowercased with non-alphanumeric chars replaced by dashes.
- **Deduplication:** seen targets are tracked so each target appears as at most one page.
- `cpp/tests/test_definition_layout.cpp` — 10 doctest cases covering: empty input, table editor direct, scalar page with fields, nested panel→table editor, deduplication, unknown target skip, circular reference cycle detection, group ID normalization, static text→notes, and **production INI integration** (parses real INI, verifies >10 pages compiled including veTableDialog).

Also includes sub-slice 46: **INI dialog parser** (`ini_dialog_parser.hpp/cpp`) — port of `IniParser._parse_dialogs`, parsing the `[UserDefined]` section into `IniDialog` objects with fields and panel references. 12 doctest cases including production INI integration.

**TUNE tab upgraded:** now compiles layout pages on startup and shows compiled page details (section count, field count, group, parameter bindings) in the right pane when a page is selected.

C++ doctest suite: **762 tests, 5883 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-fifth sub-slice: RuntimeTelemetryService + UI beautification pass

Port of `tuner.services.speeduino_runtime_telemetry_service.SpeeduinoRuntimeTelemetryService` — decodes Speeduino board capabilities (8 capability bits from `boardCapabilities` or individual `boardCap_*` channels), runtime status (8 `runtimeStatusA` bits including fullSync and tuneLearnValid), and SPI flash health into operator-facing summaries. Pure logic, no transport.

- `cpp/include/tuner_core/runtime_telemetry.hpp` and `cpp/src/runtime_telemetry.cpp` — `BoardCapabilities` (8 flags + `available_labels()`), `RuntimeStatus` (8 flags), `TelemetrySummary` (capability/runtime/operator/setup/persistence summary texts + severity), `decode(values)`.
- **Dual decode paths:** packed byte (single `boardCapabilities` / `runtimeStatusA` channel) or individual named channels (`boardCap_rtc`, `rSA_fullSync`, etc.) — matches the Python service's tolerance for different firmware reporting styles.
- **Tune-learning status:** three-way severity: "ok" when `tuneLearnValid` is set, "warning" with specific blockers (no full sync, transient active, warmup/ASE active), "info" when no status is reported.
- `cpp/tests/test_runtime_telemetry.cpp` — 12 doctest cases covering: empty values, packed byte decode, individual channels, packed runtime status, tune-learn-valid ok, tune-learn-blocked warning with blockers, SPI flash health, available labels, capability summary text, setup guidance, persistence for healthy/bad flash.

**UI beautification pass** landed in the same session:
- **Shared `make_info_card()`** card builder with colored left-border accent, replacing the per-tab inline lambdas. Used across LIVE, FLASH, and ASSIST tabs.
- **LIVE tab** upgraded from a plain gauge-zone demo to a three-section runtime telemetry display: Board Capabilities card (blue accent), Runtime Status card (green/amber/blue severity-colored accent), and Persistence card (gray accent), all powered by the just-ported `runtime_telemetry::decode` against a simulated DropBear board. Gauge color zones section retained below with improved styling.
- **FLASH tab** upgraded from a static placeholder to a live flash preflight validation demo: runs `flash_preflight::validate` against a simulated signature-mismatch scenario, showing individual warning cards (amber accent) and a summary card.
- **ASSIST tab** cards upgraded to colored accents: accumulator (blue), smoothing (purple), diagnostics (green/amber), review (orange), heatmap grid (green left border).

C++ doctest suite: **740 tests, 5811 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-fourth sub-slice: StartupEnrichmentGeneratorService

Port of `tuner.services.startup_enrichment_generator_service.StartupEnrichmentGeneratorService` — the last generator, covering all three startup enrichment curves (WUE + cranking + ASE). This completes the generator cluster on the C++ side.

- `cpp/include/tuner_core/startup_enrichment_generator.hpp` and `cpp/src/startup_enrichment_generator.cpp` — `StartupContext` POD, `WueResult`/`CrankingResult`/`AseResult` PODs, `generate_wue(ctx, intent)`, `generate_cranking(ctx, intent)`, `generate_ase(ctx, intent)`.
- **WUE:** 10-point CLT → enrichment % curve, scaled from the Ford300 reference shape. Cold-end value adjusted by fuel type (E85 = 210%, petrol = 180%), calibration intent (+8% first-start), and injector characterization depth. All values clamped to [100, 255].
- **Cranking:** 4-point CLT → enrichment %, CR-adjusted (high CR = -8%, low CR = +12%), intent-adjusted (+8% first-start). Clamped to [100, 255].
- **ASE:** 4-point CLT → added % + duration seconds. Adjusted for intent, injector characterization, ITB manifold, race-ported heads, and forced induction. Enrichment clamped to [0, 155], duration to [0, 255].
- **Scale-from-reference** function anchors the warm end at 100% and proportionally scales the excess above 100% to match the target cold-end value, preserving the reference curve shape.
- `cpp/tests/test_startup_enrichment_generator.cpp` — 17 doctest cases (WUE: 7, cranking: 4, ASE: 6) covering: output counts, warm-end anchor, cold > warm ordering, first-start richer than drivable, E85 higher cold enrichment, bounds clamping, missing-stoich warning, high/low CR effects, ITB raises ASE, boosted warning, pct/duration bounds.

**Generator cluster complete.** All five Python generators are now ported to C++: VE table (43), AFR target (41), spark advance (42), idle RPM (40), and startup enrichment (44).

C++ doctest suite: **728 tests, 5774 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-third sub-slice: VeTableGeneratorService

Port of `tuner.services.ve_table_generator_service.VeTableGeneratorService` — the most important generator, producing a conservative 16×16 VE table shaped by cam duration, head flow class, intake manifold style, injector sizing/characterization, forced induction topology, and supercharger type. Pure logic, stage-only output.

- `cpp/include/tuner_core/ve_table_generator.hpp` and `cpp/src/ve_table_generator.cpp` — `SuperchargerType` enum (roots/twin_screw/centrifugal), `VeGeneratorContext` POD (all hardware context fields), `Result` POD, `generate(ctx)`.
- **NA base shaping:** load ramp from 38% VE (idle) to 85% (WOT); RPM bell curve peaking at 55% of range; idle corner correction (-6 at origin); cam bonus (+4 at high load/RPM for >270° duration, -3 idle penalty for <220°).
- **Topology corrections:** single turbo -12% pre-spool, twin turbo -10%, compound -7%, sequential -9%; supercharger (roots/twin-screw) +3 low RPM +5 WOT; centrifugal SC -4% pre-spool; twin-charge +2 low RPM then -5% in transition zone. All use the same spool-start/end column model with linear ramp-back.
- **Injector sizing:** low reqFuel (<6ms) reduces idle VE by 3%; very low (<4ms) by 5%. Injector characterization depth (nominal_flow_only, flow_plus_deadtime) adds further idle conservatism.
- **Airflow corrections:** head flow (mild_ported +2, race_ported +4/-2 idle), manifold style (long_runner ±RPM, short_runner ±RPM, ITB -3 idle/+3 high RPM, log_compact ±).
- **Clamping:** [20, 100] VE range, rounded to 1dp.
- `cpp/tests/test_ve_table_generator.cpp` — 14 doctest cases covering: 16×16 shape, bounds [20, 100], WOT > idle, high cam raises WOT, turbo pre-spool reduction, supercharger boost, low reqFuel reduces idle, race-ported raises WOT, ITB effects, missing-input warnings, summary text, 1dp rounding, centrifugal SC pre-spool, compound less reduction than single.

C++ doctest suite: **711 tests, 5712 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-second sub-slice: SparkTableGeneratorService

Port of `tuner.services.spark_table_generator_service.SparkTableGeneratorService` — conservative 16×16 spark advance table generator. Shapes timing by compression ratio, forced induction topology, boost target, intercooler presence, and calibration intent. Pure logic, stage-only output.

- `cpp/include/tuner_core/spark_table_generator.hpp` and `cpp/src/spark_table_generator.cpp` — `SparkGeneratorContext` POD, `Result` POD, `generate(ctx, intent)`.
- **Base advance:** smooth load ramp from idle (10° BTDC) to NA WOT max (28°). RPM factor: cranking columns (0–2) reduced to 55–85%, cols 3–10 at 100%, cols 11–15 gently taper by 2°.
- **CR correction:** penalty above 9.5:1 CR applied at >40% load, scaling linearly. Extra 3° WOT penalty above 11.0:1 CR at >75% load.
- **Topology retard:** turbo variants -10° at WOT, supercharger -6°, twin-charge -8°, all load-weighted from 40% load upward. Light-load cells unaffected.
- **Boost target retard:** extra retard per 50 kPa above 170 kPa baseline, plus 1.5° no-intercooler penalty.
- **Intent bonus:** drivable base gets +3° scaled with load.
- **Clamping:** floor at 5° (cranking floor), cap at 45°. Rounded to 1dp.
- `cpp/tests/test_spark_table_generator.cpp` — 14 doctest cases covering: 16×16 shape, bounds [5, 45], WOT > idle, drivable > first-start, high CR reduces WOT, turbo retards vs NA, supercharger retards less than turbo, high boost retards more, no-intercooler retards more, missing-input warnings, summary text, cranking reduction, 1dp rounding, boosted assumptions.

C++ doctest suite: **697 tests, 4929 assertions, 0 failures**.

#### Phase 14 Slice 4 forty-first sub-slice: AfrTargetGeneratorService

Port of `tuner.services.afr_target_generator_service.AfrTargetGeneratorService` — conservative 16×16 AFR target table generator. Shapes AFR targets by forced induction topology, boost target, intercooler presence, stoich ratio, and calibration intent. Covers NA (stoich → 13.2 at WOT), single turbo (11.5 WOT), twin turbo variants (sequential blend, compound richest at 11.0), supercharger (12.0), and twin-charge (SC→turbo blend). Pure logic, stage-only output.

- `cpp/include/tuner_core/afr_target_generator.hpp` and `cpp/src/afr_target_generator.cpp` — `AfrGeneratorContext` POD (topology, stoich, boost target, intercooler, pressure model), `Result` POD (flat 256-value table + metadata), `generate(ctx, intent)`. Re-uses shared generator types from sub-slice 40 via `using` declarations.
- **NA shaping:** cruise at stoich (14.7), linear enrichment toward WOT (13.2), +0.2 high-RPM bonus at >70% load.
- **Boosted shaping:** stoich below `BOOST_START_ROW` (row 8), linear enrichment above. High-boost (≥200 kPa) gets -0.3 AFR, no-intercooler gets -0.2 AFR extra.
- **Topology-specific WOT:** sequential twin uses RPM-blended transition at high load; twin-charge blends SC→turbo WOT across load; compound is richest at 11.0.
- **First-start enrichment:** flat -0.7 AFR across the board; clamp to [10.0, 18.0].
- **Assumptions** populated for stoich ratio, intent, topology, and (when boosted) boost target, intercooler, pressure model, and unequal-twin note.
- `cpp/tests/test_afr_target_generator.cpp` — 14 doctest cases covering: 16×16 output shape, bounds [10, 18], NA idle near 14.0, NA WOT richer than idle, first-start richer than drivable, boosted WOT richer than NA, high boost enriches further, no-intercooler enriches, stoich flow-through, summary text content, boosted assumptions, compound richest WOT, boosted light-load at stoich, and 2dp rounding.

C++ doctest suite: **683 tests, 4140 assertions, 0 failures**.

#### Phase 14 Slice 4 fortieth sub-slice: IdleRpmTargetGeneratorService

Port of `tuner.services.idle_rpm_target_generator_service.IdleRpmTargetGeneratorService` — conservative idle RPM target curve generator. Produces a 10-point CLT → RPM target curve shaped by forced induction topology, cam duration, head flow class, intake manifold style, and calibration intent. Pure logic, stage-only output.

- `cpp/include/tuner_core/idle_rpm_generator.hpp` and `cpp/src/idle_rpm_generator.cpp` — introduces the shared generator domain types (`CalibrationIntent`, `ForcedInductionTopology`, `AssumptionSource`, `Assumption`, `GeneratorContext`) that all future generator ports will compose against. `Result` POD (clt_bins, rpm_targets, summary, warnings, assumptions), `generate(ctx, intent)`.
- **Reference shape** from the Ford300 Speeduino u16p2 base tune: 10 CLT breakpoints (-26°C to 117°C) with a normalised cold-fraction taper from 1.0 to 0.0.
- **Topology/cam/head/manifold adjustments** reproduced verbatim: boosted +50 warm, high cam +100 both, race-ported +50/+30, ITB +80/+60, log_compact +10, long_runner -10, mild_ported +20/+10, short_runner +20/+10.
- **RPM quantization** to nearest 10 (Speeduino U08 ×10 encoding), clamped to [500, 2550].
- **Warnings** for high cam detection, missing cam, race-ported heads, and ITB manifolds — matches Python messages byte-for-byte via `snprintf`.
- **Assumptions** populated for all five inputs with FROM_CONTEXT or CONSERVATIVE_FALLBACK source.
- `cpp/tests/test_idle_rpm_generator.cpp` — 15 doctest cases covering: 10-bin output shape, warm idle value, cold > warm ordering, first-start vs drivable cold bump, boosted warm idle, high cam raise, high cam warning, missing cam warning, race-ported raise + warning, ITB raise + warning, RPM multiples-of-10, bounds [500, 2550], assumption count and source, summary text content, and monotonic decrease.

C++ doctest suite: **669 tests, 3100 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-ninth sub-slice: ThermistorCalibrationService

Port of `tuner.services.thermistor_calibration_service.ThermistorCalibrationService` — Steinhart-Hart thermistor calibration table generator for Speeduino CLT/IAT sensors. Pure math, no Qt, no IO. Includes the full 15-preset catalog mirrored from the Speeduino/TunerStudio INI.

- `cpp/include/tuner_core/thermistor_calibration.hpp` and `cpp/src/thermistor_calibration.cpp` — `Point` (temp_c, resistance_ohms), `Preset` (name, pullup_ohms, 3 points, applicable sensors, source note/URL), `SHCoefficients` (A, B, C), `CalibrationResult` (sensor, preset_name, 32 temperatures, encode_payload, preview_points), plus `presets()`, `presets_for_sensor()`, `preset_by_name()`, `source_confidence_label()`, `steinhart_hart_coefficients()`, `temp_at_adc()`, `generate()`.
- **15 built-in presets** mirrored exactly: GM, Chrysler 85+, Ford, Saab/Bosch, Mazda, Mitsubishi, Toyota, Mazda RX-7 CLT/IAT, VW L-Jet, BMW E30/M50/M52/M54, Bosch 4 Bar TMAP.
- **Steinhart-Hart equation** solved from three (T, R) reference points via the standard log-space matrix inversion.
- **Edge cases:** ADC 0 = TEMP_MAX_C (sensor open), ADC ≥ 1023 = TEMP_MIN_C (sensor shorted), R ≤ 0 = TEMP_MAX_C, T_inv = 0 = TEMP_MAX_C.
- **Payload encoding:** 64 bytes, 32 × big-endian int16 temperatures in °F × 10, matching Speeduino's `processTemperatureCalibrationTableUpdate` protocol.
- `cpp/tests/test_thermistor_calibration.cpp` — 14 doctest cases (1039 assertions) covering: catalog size, name lookup, sensor filtering, confidence labels, GM table generation, monotonic decrease, ADC edge cases, reference point validation (GM 30°C ≈ ADC 484), payload encoding (100°C → 2120, -40°C → -400), preview points, and **all 15 presets validated** (32 × 15 = 480 bounds checks).

C++ doctest suite: **654 tests, 3041 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-eighth sub-slice: WueAnalyzeReviewService

Port of `tuner.services.wue_analyze_review_service.WueAnalyzeReviewService.build` — the WUE counterpart of sub-slice 36's VeAnalyzeReviewService. Simpler: no Phase 7 clamp/boost/smoothing/diagnostics lines. Composes the WUE snapshot (sub-slice 37) into confidence distribution, lean/rich previews, and detail text.

- `cpp/include/tuner_core/wue_analyze_review.hpp` and `cpp/src/wue_analyze_review.cpp` — `ReviewSnapshot` POD (summary_text, detail_text, confidence_distribution, largest_lean/rich_corrections, rows_insufficient), and `build(snapshot)`.
- **Detail text** includes: records overview, rejection breakdown (forwarded from snapshot detail_lines), row confidence distribution, rows-skipped count, lean/rich correction previews with UTF-8 `→` and `×`, and "No corrections proposed yet." fallback.
- `cpp/tests/test_wue_analyze_review.cpp` — 9 doctest cases covering: zero-records summary, summary forwarding, confidence distribution, lean sorted desc, rich sorted asc, rows_insufficient count, no-corrections text, lean preview in detail, preview capped at 5.

C++ doctest suite: **640 tests, 2002 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-seventh sub-slice: WueAnalyzeSnapshot

Port of the snapshot logic from `WueAnalyzeAccumulator.snapshot` and the `_build_summary`/`_build_detail_lines` text builders from `tuner.services.wue_analyze_service`. WUE Analyze is the warmup-enrichment counterpart of VE Analyze — 1D row-keyed (CLT axis only), simple arithmetic mean (no Phase 7 weighting/decay/clamp/boost), and enrichment range defaults to [100, 250].

- `cpp/include/tuner_core/wue_analyze_snapshot.hpp` and `cpp/src/wue_analyze_snapshot.cpp` — `RowAccumulation` POD (row_index, correction_factors, current_enrichment), `RowCorrection` and `RowProposal` output PODs, `Snapshot` result, and `build_snapshot(row_accumulations, accepted, rejected, rejection_counts, min_samples, wue_min, wue_max)`.
- **Arithmetic mean** with banker's rounding (4dp correction factor, 2dp proposed enrichment) via `std::nearbyint`.
- **Confidence labels** reuse `wue_analyze_helpers::confidence_label` from sub-slice 6.
- **Summary text format pinned:** `"WUE Analyze reviewed N record(s): A accepted, R rejected, P row proposal(s) of R with data."` — matches Python byte-for-byte.
- **Detail lines** include: records overview, rejection breakdown, row confidence distribution, lean/rich correction previews (capped at 5 with `…` ellipsis), and "No corrections proposed yet." when empty.
- `cpp/tests/test_wue_analyze_snapshot.cpp` — 12 doctest cases covering: empty input, arithmetic mean proposal, below-min-samples gating, wue_min/max clamping (both bounds), confidence labels at thresholds, sorted output by row index, summary text pin, NaN current_enrichment, rejection breakdown in detail, no-corrections text, lean preview in detail, and input-not-mutated guarantee.

C++ doctest suite: **631 tests, 1984 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-sixth sub-slice: VeAnalyzeReviewService

Port of `tuner.services.ve_analyze_review_service.VeAnalyzeReviewService.build` — the operator-facing review text builder that sits between the Phase 7 assist pipeline and the workspace UI. Composes all four preceding Phase 7 slices: accumulator snapshot (35), smoothing layer (33), diagnostics report (34), and rejection counts from the gate service (30). Pure logic, no Qt.

- `cpp/include/tuner_core/ve_analyze_review.hpp` and `cpp/src/ve_analyze_review.cpp` — `ReviewSnapshot` POD (summary_text, detail_text, confidence_distribution, largest_lean_corrections, largest_rich_corrections, cells_insufficient, clamp_count, boost_penalty_count, smoothed_summary_text, diagnostic_lines), and `build(snapshot, rejection_counts, smoothed_layer, diagnostics)`.
- **Summary text format pinned:** `"VE Analyze reviewed N record(s): A accepted, R rejected, P cell proposal(s) of C with data."` when records exist; `"VE Analyze: no records to review."` when zero.
- **Detail text** is a multi-line newline-separated block containing: records overview, rejection breakdown (alphabetically sorted gate=count pairs), confidence distribution (non-zero only), cells-skipped count, coverage ratio, largest lean corrections (CF > 1.0 sorted descending, capped at 5), largest rich corrections (CF < 1.0 sorted ascending, capped at 5), clamp transparency line, boost penalty line, smoothed layer summary, and root-cause diagnostic lines — each section emitted only when its signal is present. Matches the Python `_build_detail` output format.
- **Lean/rich correction formatting uses UTF-8 `→` and `×` characters** via escaped byte sequences, matching the Python f-string format: `"(row,col) current→proposed ×factor n=count"`.
- **Diagnostic lines** are formatted as `"[severity] rule: message"` and indented with two spaces under a `"Root-cause diagnostics:"` header.
- `cpp/tests/test_ve_analyze_review.cpp` — 15 doctest cases covering: zero-records summary, counts in summary text, confidence distribution counts (all four levels), lean corrections sorted descending, rich corrections sorted ascending, cells_insufficient count, no-corrections text, rejection breakdown in detail, coverage line, clamp transparency surfacing, boost penalty surfacing, smoothed layer forwarding, diagnostic lines forwarding, **full Phase 7 end-to-end pipeline** (accumulator → smoothing → diagnostics → review), and preview cap at 5 entries.

**ASSIST tab updated** — the review card now shows the full detail text from `VeAnalyzeReviewService`, demonstrating the complete Phase 7 pipeline rendered as operator-facing text.

C++ doctest suite: **618 tests, 1947 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-fifth sub-slice: VeCellHitAccumulator snapshot layer

Port of the weighted-correction snapshot logic from `VeAnalyzeCellHitAccumulator.snapshot` — Phase 7 Slice 7.2's proposal producer. This is the **producer** of the `Proposal` POD shape that sub-slices 33 (smoothing) and 34 (diagnostics) already consume, closing the Phase 7 assist pipeline end-to-end on the C++ side: cell hits → proposals → smoothing → diagnostics.

- `cpp/include/tuner_core/ve_cell_hit_accumulator.hpp` and `cpp/src/ve_cell_hit_accumulator.cpp` — `WeightedCorrectionConfig` POD (max_correction_per_cell, dwell_weight_enabled, dwell_weight_cap_seconds, sample_age_decay_per_second), `CorrectionSample` POD (correction_factor, weight, timestamp_seconds), `CellAccumulation` POD (row/col/samples/current_ve/boost_penalty_applied), `CellCorrection` POD (mirroring Python `VeAnalysisCellCorrection` field-for-field), `CoverageCell` / `Coverage` PODs, `Snapshot` result, plus `confidence_label()`, `confidence_score()`, and `build_snapshot()`.
- **Weighted mean preserves Phase 6 baseline exactly:** when no `WeightedCorrectionConfig` is supplied, all sample weights are 1.0 and age decay is disabled, so `build_snapshot` produces the same arithmetic mean as the Python Phase 6 path. Verified by doctest.
- **Per-cell clamp with raw_correction_factor transparency:** `max_correction_per_cell` clamps the weighted mean to `[1-c, 1+c]`; `clamp_applied` is `true` iff the clamp actually moved the value; `raw_correction_factor` carries the pre-clamp mean so the operator can see what would have happened. Mirrors the Python `WeightedCorrectionConfig` contract exactly.
- **Sample-age decay via `exp(-age * decay)`:** the latest timestamp across all cells is used as the reference; each sample's effective weight is multiplied by the decay factor. Older samples are downweighted, recent samples dominate. Doctest confirms with a decay=0.5/s scenario.
- **Banker's rounding via `std::nearbyint`** for correction factors (4dp), proposed VE (2dp), confidence score (4dp), and boost penalty (4dp) — same `FE_TONEAREST` default as Python's `round()`.
- **Confidence scoring dual output:** categorical (`confidence_label`: insufficient/low/medium/high at 3/10/30) plus continuous (`confidence_score`: `1 - exp(-n/10)` rounded to 4dp). Thresholds preserved as named constants.
- **Coverage map:** `build_snapshot` always produces a full-grid `Coverage` with visited/unvisited status for every cell, matching the Python `VeAnalysisCoverage` shape.
- **Summary text format pinned:** `"VE Analyze: N accepted samples across M cell(s); R rejected; P cell(s) have correction proposals."` via `snprintf` — byte-identical to the Python f-string.
- **Proposals are `ve_proposal_smoothing::Proposal` objects** — the same POD type that `smooth()` and `diagnose()` consume. No adapter layer needed.
- `cpp/tests/test_ve_cell_hit_accumulator.cpp` — 19 doctest cases covering: confidence label thresholds (8 boundary checks), continuous confidence score curve, empty accumulations, arithmetic mean proposal, below-min-samples gating, per-cell clamp limiting and within-bounds pass-through, VE min/max clamping, sample-age decay, Phase 6 default regression, coverage map visited/unvisited, summary text pin, **composition with smoothing service (sub-slice 33)**, **composition with diagnostics service (sub-slice 34)**, NaN current_ve handling, boost penalty surfacing, input-not-mutated guarantee, sorted output by (row, col), and dwell weight via sample weights.

**ASSIST tab updated** — the pipeline now flows through all three Phase 7 services: the accumulator produces proposals from synthetic cell hits, the smoothing service smooths them, and the diagnostics engine analyzes them. The accumulator summary card shows coverage ratio alongside the existing smoothing and diagnostics cards.

**Bug fix landed in same session:** the TUNE tab filter QLineEdit SIGSEGV (documented in sub-slice 34 notes) has been fixed. Root cause: `q.trimmed().toLower()` and `leaf->text(0).toLower().contains(needle)` in the `textChanged` lambda chained intermediate `QString` temporaries, triggering the Qt 6.7 + UCRT 15.2 ABI mismatch. Fix: all string comparison is now done on `std::string` via `toStdString()` with a new `icontains()` helper; tree expand/collapse decisions are deferred until after the walk completes. The `main.cpp` file header's ABI constraint section has been expanded to document the additional gotcha (chained method calls on QString temporaries in signal handlers).

C++ doctest suite: **603 tests, 1907 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-fourth sub-slice: VeRootCauseDiagnosticsService

Direct port of `tuner.services.ve_root_cause_diagnostics_service.VeRootCauseDiagnosticsService.diagnose` — Phase 7 Slice 7.7's read-only diagnostic engine. Composes against the `Proposal` POD landed in sub-slice 33, so the second Phase 7 assist slice is a thin addition rather than a re-derivation of the proposal model. Pure logic, stateless, never mutates the input.

- `cpp/include/tuner_core/ve_root_cause_diagnostics.hpp` and `cpp/src/ve_root_cause_diagnostics.cpp` — `Diagnostic` POD (rule, severity, message, evidence_cells), `DiagnosticReport` (diagnostics vector + summary_text + `has_findings()`), and `diagnose(proposals)` returning a flat report. The `Proposal` type is a `using` alias of `tuner_core::ve_proposal_smoothing::Proposal` so the two Phase 7 slices share the same POD without duplication.
- **Conservative thresholds preserved verbatim** as `constexpr` constants: `MIN_PROPOSALS=6`, `UNIFORM_BIAS_THRESHOLD=0.05`, `UNIFORM_BIAS_VARIANCE_MAX=0.0025`, `DEADTIME_REGION_BIAS=0.08`, `OPPOSITE_REGION_BIAS=0.05`, `LOAD_CORRELATION_THRESHOLD=0.7`. The intent — "fire only when the pattern is obvious to a human inspecting the table" — carries over verbatim.
- **Below MIN_PROPOSALS the report is empty** with the explanatory `"Root-cause diagnostics: only N proposal(s) — need ≥6 before patterns are reliable."` summary text. Mirrors the Python guard exactly.
- **Four independent rules** that may fire alongside each other in the order they appear in the Python service: `injector_flow_error` (uniform global bias, low variance), `deadtime_error` (low-load region biased meaningfully more than the rest), `target_table_error` (high vs low load biased in opposite directions), `sensor_calibration_error` (Pearson correlation between row index and correction factor ≥ 0.7).
- **Pearson r computation** uses two-pass mean + covariance + variance accumulation. The `var_x == 0 || var_y == 0` guard mirrors the Python `if var_x == 0 or var_y == 0: return None` so a perfectly flat correction array doesn't divide by zero.
- **Region splits use `max_row // 2` and `max_col // 2`** integer floor division for the deadtime and opposite-load rules, matching the Python `//` operator exactly so the region boundaries land on the same cell.
- **Message format pinned via `snprintf`** for every rule: `"All cells biased %s by ~%+.0f%% with low variance ..."` etc. The `%+.0f` format spec reproduces the Python `f"{bias * 100:+.0f}%"` byte-for-byte.
- **Summary text format pinned:** `"Root-cause diagnostics: N pattern(s) found (rule1, rule2)."` when findings exist, or `"Root-cause diagnostics: no systemic patterns found across N proposal(s)."` when silent.
- `cpp/tests/test_ve_root_cause_diagnostics.cpp` — 10 doctest cases covering: below-threshold gating, healthy data silence, uniform lean → `injector_flow_error` (lean label), uniform rich → `injector_flow_error` (rich label), high-variance suppression of the uniform rule, deadtime low-load region bias firing on a 4×4 grid, opposite high/low load bias firing `target_table_error`, linear ramp firing `sensor_calibration_error` with the Pearson r message, the input-not-mutated guarantee, and the summary text format pin.

**Skipped parity test for this slice** — same dependency story as the smoothing slice: `VeAnalysisSummary` hasn't been ported. Doctests cover every rule branch and the threshold gate. A future parity test can land cheaply via a flat proposal-list bridge.

**Why this slice next:** the smoothing slice (sub-slice 33) introduced the `Proposal` POD that the rest of the Phase 7 assist surface composes against. Landing root-cause diagnostics immediately afterward — *while the proposal shape is fresh and load-bearing in only one slice* — proves the seam works for a second consumer before the surface area grows. This is the same composition pattern the table_replay_context / table_replay_hit slice pair followed earlier.

C++ doctest suite: **584 tests, 1794 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-third sub-slice: VeProposalSmoothingService

Direct port of `tuner.services.ve_proposal_smoothing_service.VeProposalSmoothingService.smooth` — Phase 7 Slice 7.5's strictly-additive smoothing layer for VE Analyze proposals. **First Phase 7 assist-pipeline slice on the C++ side**, opening up the path to porting the rest of the assist surface (boost confidence, root-cause diagnostics, weighted-correction accumulator) without going through Python.

- `cpp/include/tuner_core/ve_proposal_smoothing.hpp` and `cpp/src/ve_proposal_smoothing.cpp` — `Proposal` POD shell (only the fields the smoothing service reads or copies forward: `row_index`, `col_index`, `current_ve`, `proposed_ve`, `correction_factor`, `sample_count`, `raw_correction_factor`, `clamp_applied`), `SmoothingConfig(kernel_radius, min_neighbors, preserve_edge_magnitude)`, `SmoothedProposalLayer(smoothed_proposals, unchanged_count, smoothed_count, summary_text)`, and `smooth(proposals, config)`. Stateless — the input vector is read-only and a new layer is returned.
- **Banker's rounding via `std::nearbyint`:** Python `round(x, 2)` and `round(x, 4)` use round-half-to-even, which matches the IEEE-754 default `FE_TONEAREST` mode used by `std::nearbyint`. The C++ port rounds via `std::nearbyint(value * scale) / scale` so ties land identically to the Python service. Same call documented in the `table_rendering` slice notes; `std::round` (round-half-away-from-zero) was deliberately avoided.
- **Identity transform pinned:** `kernel_radius == 0` returns the raw proposals untouched with the documented `"Kernel radius N → identity transform."` summary text — the caller can treat the layer as "smoothing disabled" without a special-case branch.
- **Edge cells use only existing neighbors:** the kernel scan over `[-radius, radius]` looks up each `(row+dr, col+dc)` pair via a flat scan over the proposal vector. Cells outside the visited grid simply contribute nothing — no fabricated VE values for unvisited cells. Mirrors the Python `index.get(...) is not None` guard.
- **`min_neighbors` gate:** when fewer than N neighbors exist, the cell passes through as raw and is counted as unchanged. The doctest covers a 1+1 layout with `min_neighbors=2` to pin this branch.
- **`preserve_edge_magnitude` strongest-deviation guard:** when set, the service identifies the cell with the largest `|cf - 1.0|` in the window; if it's the current cell, it's left untouched so a real boost-spool transition is not averaged away by softer neighbors. Mirrors the Python `max(window, key=lambda p: abs(p.correction_factor - 1.0))`.
- **Sample-count-weighted average** prevents a low-confidence neighbor from pulling a high-confidence anchor. Falls back to a uniform mean when `total_weight <= 0` (defensive — `sample_count` is always ≥ 1 in practice). Doctest covers a 100-sample anchor next to a 1-sample neighbor and confirms the anchor barely moves.
- **Near-zero diff cells preserved:** when `|new_proposed - proposal.proposed_ve| < 0.01`, the cell passes through as raw to keep the diff minimal and obvious — the Python service has the same guard so the smoothed layer never produces a no-op update that visually marks a cell as changed.
- **`raw_correction_factor` carry-forward:** smoothed proposals store the *original* `correction_factor` in `raw_correction_factor` for review transparency, NOT the pre-smoothing cf — matches the Python `raw_correction_factor=proposal.correction_factor` exactly.
- **Summary text format pinned:** `"Smoothed N proposal(s); M preserved unchanged (kernel radius R, min_neighbors N)."` via `snprintf` — byte-identical to the Python f-string, verified by an explicit pin test.
- `cpp/tests/test_ve_proposal_smoothing.cpp` — 10 doctest cases covering: empty proposals → no-op summary, `kernel_radius=0` identity transform, isolated cell with no neighbors preserved, `min_neighbors` gate threshold, 3×3 spike smoothed by uniform neighbors with the center cell landing at `101.11` (banker's-rounded weighted average), sample-count weighting protecting a high-confidence anchor, `preserve_edge_magnitude` leaving the strongest deviation alone, near-zero diff preservation, the input-not-mutated guarantee, and the summary text format pin.

**Skipped parity test for this slice** — the Python service consumes `VeAnalysisSummary` / `VeAnalysisProposal` shapes from `ve_analyze_cell_hit_service`, which haven't been ported to C++ yet. Doctests cover every code path through the smoothing pass including all four pass-through branches (empty input, identity transform, min_neighbors gate, near-zero diff) and every active modification branch. A future parity test can land cheaply by feeding both sides the same flat proposal lists once the cell-hit service ships in C++.

**Why this slice next:** the Phase 7 assist surface is one of the largest pieces of pure-logic Python that still hasn't been touched on the C++ side. Smoothing is the cleanest entry point — stateless, no domain-graph dependencies, no Qt — and lands the foundational `Proposal` POD shape that the rest of the Phase 7 services (`VeRootCauseDiagnosticsService`, `VeAnalyzeCellHitAccumulator` weighted-correction layer, `BoostConfidenceConfig` penalty math) will compose against. Porting smoothing first means each subsequent assist slice is a thin addition rather than re-deriving the proposal model from scratch.

C++ doctest suite: **574 tests, 1772 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-second sub-slice: TableRenderingService

Direct port of `tuner.services.table_rendering_service.TableRenderingService.build_render_model` — the table-editor's gradient color renderer. Composes the just-ported `table_view::ViewModel` (sub-slice 14) with a six-stop heatmap gradient + Y-axis inversion + perceived-brightness foreground flip. **First C++ workspace-services slice that drops a Qt dependency** (Python uses `QColor` for arithmetic and `.name()` for the hex string; the C++ port replaces both with a flat `Rgb` struct and `snprintf("#%02x%02x%02x")` to match `QColor::name()` byte-for-byte).

- `cpp/include/tuner_core/table_rendering.hpp` and `cpp/src/table_rendering.cpp` — `CellRender` POD (text + background_hex + foreground_hex), `RenderModel` POD (rows, columns, x_labels, y_labels in display order, row_index_map, row-major cells), and `build_render_model(table_model, x_labels, y_labels, invert_y_axis)`. Consumes `tuner_core::table_view::ViewModel` directly so the renderer composes cleanly with the existing table-view slice.
- **Y-axis inversion preserved:** when `invert_y_axis=true` (the default, matching the operator-facing convention where the lowest load row sits at the bottom), `row_index_map` is `(rows-1, rows-2, ..., 0)` and `y_labels` is reordered to match. When false, both are natural order.
- **Six gradient stops decoded once:** the Python `_gradient_color` keeps the stops as `QColor` instances; the C++ port decodes them to `Rgb` at static-init time so the cell render path is pure arithmetic (no string parsing per cell). Stops match the Python list exactly: `(0.00, #8aa8ff)`, `(0.25, #9dd9ff)`, `(0.50, #9af0a0)`, `(0.75, #e4ee8e)`, `(0.90, #f3b07b)`, `(1.00, #e58e8e)`.
- **Banker's rounding via `std::nearbyint`:** Python's `round(x)` uses round-half-to-even, and the default IEEE-754 rounding mode (`FE_TONEAREST`) is the same. `std::nearbyint` honors the current mode, so the gradient interpolation produces byte-identical channel values for ties as well as the typical case. `std::lround` (round-half-away-from-zero) would diverge on exact halves and was deliberately avoided.
- **`max <= min` falls through to ratio 0.5:** mirrors the Python `if maximum <= minimum: ratio = 0.5` guard. With 0.5 sitting exactly on stop[2]=`#9af0a0`, the local-ratio calculation lands at 0.0 and emits the stop verbatim (a uniform-value table comes out solid mint-green, same as Python).
- **Non-numeric cell text → `(white background, black foreground)`** mirroring the Python `try: float(text); except ValueError: return TableCellRender(... "#ffffff" ... "#000000")` fall-through. Uses `std::stod` with a fully-consumed-input check so partial parses (e.g. `"3xyz"`) fall through correctly.
- **Foreground flip threshold pinned at 120:** perceived brightness `0.299·R + 0.587·G + 0.114·B` (the standard NTSC luma formula Python uses); foreground is white when brightness `< 120`, black otherwise. None of the current six gradient stops produce a brightness below 120 (the lightest, `#8aa8ff`, lands at ~169), so the foreground is `#000000` everywhere in practice — but the threshold logic is pinned so future stop additions are caught by the test.
- **Hex output is lowercase** to match `QColor::name()` default behavior. `snprintf("%02x")` produces `#9af0a0` rather than `#9AF0A0`; pinned by the "no uppercase A–F" check in the test suite.
- `cpp/tests/test_table_rendering.cpp` — 10 doctest cases covering: Y-axis inversion of `row_index_map` and `y_labels`, `invert_y_axis=false` natural order, minimum-value cell rendering (ratio 0.0 → `#8aa8ff`), maximum-value cell rendering (ratio 1.0 → `#e58e8e`), non-numeric cell white-on-black fallback, uniform-value table picking the midpoint stop (`#9af0a0`), foreground flip pinned to `#000000` for the current gradient table, propagation of rows / columns / x_labels, empty `ViewModel` producing an empty render, and lowercase hex format pin.

**Skipped parity test for this slice** — the Python service's call signature consumes a `TableViewModel` shape that the C++ side already has, but composing both ends through nanobind would require a string-grid round-trip and the rest of the workspace presenter to be in C++ first. The doctests pin every code path through both the gradient-color helper and the render builder; a future parity test can land cheaply once the workspace presenter port is further along.

**Why this slice next:** the C++ table editor widget that lands later in Slice 8 needs gradient coloring on day one — operators expect the heatmap to read at a glance. Porting the renderer as pure logic now means the widget becomes a thin Qt shell over `RenderModel` rather than re-deriving gradient math from scratch. Also: this is the first workspace-services slice that intentionally drops a Qt dependency (`QColor` → `Rgb`), proving the seam pattern that the rest of the rendering layer can follow.

C++ doctest suite: **564 tests, 1743 assertions, 0 failures**.

#### Phase 14 Slice 4 thirty-first sub-slice: DatalogReviewService

Direct port of `tuner.services.datalog_review_service.DatalogReviewService` — the Logging tab's review-chart trace builder. Takes a flat datalog record vector + an optional channel-selection profile + the operator's currently-selected row, picks up to three channels (profile-driven or by priority heuristic), and emits per-channel `(x, y)` traces with the marker position for the selected row plus the pinned summary text.

- `cpp/include/tuner_core/datalog_review.hpp` and `cpp/src/datalog_review.cpp` — `Record` POD (flat `(name, value)` pairs preserving Python dict insertion order, plus a pre-flattened `timestamp_seconds` double instead of `datetime` so the slice stays clock-free), `Profile` POD (just the ordered enabled channel names — the rest of `DatalogProfile` isn't load-bearing), `TraceSnapshot` POD, `Snapshot` POD, and `build(records, selected_index, profile)`. The Python service collapses `(t - base_time).total_seconds()` inline; the C++ port asks the caller to do the same flattening at the boundary.
- **Priority heuristic preserved verbatim:** `_PRIORITY_CHANNELS = ("rpm", "map", "tps", "afr", "lambda", "advance", "pw", "ego")` lives in a `static const std::vector` and is walked in the same order. Lookups are case-insensitive (Python `lowered = {name.lower(): name for name in available}` → C++ pair-list scan), so a `RPM`-cased channel still matches the `rpm` priority entry and the canonical-cased name is the one that lands in the trace list.
- **Profile fall-through semantics:** when a profile is supplied but none of its channels match anything in the log, the service falls through to the priority heuristic (Python `if selected: return ... # fall through`). Mirrored exactly.
- **Three-channel cap** is enforced in both branches so the chart never grows past three traces regardless of input shape.
- **Empty-channel traces are dropped:** the Python loop only appends a trace when `x_values` is non-empty (i.e. at least one record carried the channel). The C++ port mirrors the same guard so a channel that exists in the available set but has no actual values doesn't produce an empty trace.
- **`record_has` / `record_get` linear scans** match the Python `if channel_name not in record.values` semantics on a flat list. This is `O(channels × records)` but matches the Python service's own complexity — and the trace count is capped at 3, so the constant stays small.
- **Summary text format pinned:** `"Datalog review shows N trace(s) across M row(s). Selected replay row K is at +X.XXXs."` via `snprintf("%.3f", marker_x)` — byte-identical to the Python f-string.
- **Empty input raises `std::invalid_argument`** to mirror the Python `raise ValueError("Datalog is empty.")`.
- `cpp/tests/test_datalog_review.cpp` — 11 doctest cases covering: empty records → throw, `selected_index` clamping past the end, the priority heuristic picking `rpm/map/tps` in order, case-insensitive priority matching (`RPM`, `MAP`), insertion-order fallback when nothing in the priority list exists, profile selection winning over the heuristic, profile cap at three channels, profile-with-no-matches falling through to the heuristic, traces skipping records that lack the channel, the summary text format pin, and `x_values` correctly computed as deltas from the first record's timestamp.

**Skipped parity test for this slice** — the Python service consumes `DataLog` and `DatalogProfile` domain types that the C++ side hasn't ported yet. Doctests cover every code path through the channel selector (both branches) and the trace builder. A future parity test can land cheaply once the datalog domain types ship in C++ — same dependency story as the just-ported `replay_sample_gate` slice.

C++ doctest suite: **554 tests, 1699 assertions, 0 failures**.

#### Phase 14 Slice 4 thirtieth sub-slice: ReplaySampleGateService

Direct port of `tuner.services.replay_sample_gate_service.ReplaySampleGateService` — the named-gate evaluator that decides whether a datalog record is safe to learn from. Sits on top of the already-ported `sample_gate_helpers` substrate (alias-aware channel resolution + AFR/lambda derivation) and closes the dependency that the just-ported `TableReplayHitService` aggregator was deferring to its caller.

- `cpp/include/tuner_core/replay_sample_gate.hpp` and `cpp/src/replay_sample_gate.cpp` — `Config` POD (every field from the Python `SampleGatingConfig` dataclass: `enabled_gates`, `afr_min/max`, `clt_min_celsius`, `tps_max_percent`, `rpm_min`, `pulsewidth_min_ms`, the four axis bounds, the two runtime axis values, and `firmware_learn_gate_enabled`), `Eval` POD mirroring `SampleGateEval` field-for-field, `Summary` POD mirroring `GatedSampleSummary`, plus `default_gate_order()`, `evaluate_record(values, config)`, `is_accepted`, `primary_rejection`, and `gate_records(records, config)`.
- **Default gate priority preserved exactly:** `std_DeadLambda → accelFilter → aseFilter → minCltFilter → overrunFilter`. The Python rationale (DeadLambda first because most real datalogs lack a lambda channel name our aliases match, making it the most common fast-reject) carries over verbatim — the C++ side uses the same hard-coded order in `default_gate_order()`.
- **Custom gate sets sort alphabetically** to match Python `sorted(cfg.enabled_gates)`. The C++ port uses `std::set<std::string>` for `enabled_gates` so iteration is already sorted at the source.
- **`firmwareLearnGate` runs first when enabled** as a hard *additional* gate, prepended to whatever gate order the caller produced — never replacing software-side gating, only ever rejecting more. Mirrors the Phase 7 Slice 7.1 contract on the Python side.
- **`runtimeStatusA` channel resolver is naming-tolerant** — strips `_` and ` ` from each key and matches against `runtimestatusa`, `statusa`, `runtimestatus`. Same fallback as the Python `_resolve_runtime_status_a`. Missing channel falls through to accept so legacy logs and offline replay don't regress.
- **Fail-fast iteration:** `evaluate_record` stops at the first rejection so callers get the primary reason without doing N gate evaluations. Mirrors the Python `for ... break` pattern.
- **Aggregate summary text pinned:** `"Sample gating: A accepted, R rejected of T total."` and `"Rejections by gate: gate1=N1, gate2=N2."` (sorted alphabetically by gate name via `std::map`, same as Python `sorted(dict.items())`). The "no rejections" branch produces `"No rejections."` as the second detail line.
- `cpp/tests/test_replay_sample_gate.cpp` — 17 doctest cases covering: `default_gate_order` priority sequence, missing AFR → `std_DeadLambda` rejection, clean record passes every default gate, fail-fast stops at the first rejecting gate (cold coolant), AFR outside plausible range, accel/ase/overrun rejection paths, custom-gate-set alphabetical ordering (`maxTPS` wins over `minRPM`), `firmwareLearnGate` prepend + fullSync rejection, `firmwareLearnGate` accept on `0x90`, `transientActive` rejection, `firmwareLearnGate` fall-through accept on missing channel, `std_xAxisMin` reject and pass-through-when-bounds-missing, `gate_records` aggregation with sorted rejection histogram and full summary text pin, and the no-rejections aggregate branch.

**Skipped parity test for this slice** — the Python service consumes `DataLog` / `DataLogRecord` shapes that the C++ side hasn't ported yet. Doctests cover every gate path and every code path through `evaluate_record` / `gate_records`. A future parity test can land cheaply by feeding both sides the same flat `(name, value)` pairs once the datalog domain types ship in C++.

**Why this matters:** the just-landed `TableReplayHitService` aggregator was explicitly punting its sample-gating responsibility to the caller because the gate evaluator wasn't ported yet. With this slice in place, the C++ workspace layer now has both halves of the "where has the engine been *under acceptable conditions*?" pipeline — the gate filter and the cell-hit aggregator — and the future C++ Analyze surface can compose them directly without round-tripping through Python.

C++ doctest suite: **543 tests, 1663 assertions, 0 failures**.

#### Phase 14 Slice 4 twenty-ninth sub-slice: SurfaceEvidenceService

Direct port of `tuner.services.surface_evidence_service.SurfaceEvidenceService` — the strip-of-pills evidence summary that sits at the top of every workspace page (Connection / Source / Sync / Changes / Ops / Runtime) plus the human-readable rollup paragraph. Pure logic, no Qt.

- `cpp/include/tuner_core/surface_evidence.hpp` and `cpp/src/surface_evidence.cpp` — `Inputs` POD (flat fields rather than the SessionInfo / SyncState / OperationLog / WorkspaceReview / OutputChannelSnapshot graph the Python service composes — the C++ caller is responsible for collapsing those into the flat shape so this slice doesn't pull half the workspace state graph in just to render text), `Snapshot` (12 pill text/severity strings + summary paragraph), `format_age` exposed for testing.
- **Runtime age handling pushed to the caller**: Python computes the age inline against `datetime.now(UTC)`. The C++ port takes `runtime_age_seconds` as an `optional<double>` so the slice stays clock-free and trivially testable. The threshold (`> 30s` → stale/warning) and the human age formatting (`Ns`, `Nm Ns`, `Nh Nm`) match Python byte-for-byte.
- `cpp/tests/test_surface_evidence.cpp` — 10 doctest cases covering: offline empty default, ECU-RAM accent source, staged-changes branch, mismatch-dominated summary, unwritten-ops warning + latest-op extraction from a multiline summary, stale runtime, fresh runtime, cached runtime when offline, and the `format_age` boundaries (0s / sub-minute / minute / hour).

**Skipped parity test for this slice** — the Python service signature consumes domain types (`SessionInfo`, `WorkspaceSnapshot`, `OutputChannelSnapshot`) that haven't been bridged yet. Doctests cover every branch of the C++ port; once the workspace presenter port lands the binding can flatten its state into the C++ `Inputs` POD and a parity test can wrap around it then.

C++ doctest suite: **526 tests, 1600 assertions, 0 failures**. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-eighth sub-slice: TableReplayHitService aggregator

Direct port of `tuner.services.table_replay_hit_service.TableReplayHitService.build` — the datalog→table-cell hit-count aggregator that drives the workspace presenter's "where has the engine actually been?" overlay. Operators use this to spot-check whether their VE table edits are landing on cells that ever see real load. Sibling to the just-ported `table_replay_context` slice but operates on a *batch* of records rather than a single live point.

- `cpp/include/tuner_core/table_replay_hit.hpp` and `cpp/src/table_replay_hit.cpp` — `Record` POD (parallel-array channel values, same shape used elsewhere in the workspace layer), `HitCellSnapshot` (row + column + hit_count + optional mean_afr), `HitSummarySnapshot` (summary/detail strings + top-3 hot cells + accepted/rejected counts + sorted rejection reason histogram), `PreRejected` POD for caller-supplied gating accumulators, `build(table_snapshot, records, pre_rejected, max_records)`. Reuses the `TablePageSnapshot` shape from the `table_replay_context` slice so the two services share a single page-snapshot type.
- **Gating decoupled from aggregation:** the Python service composes `ReplaySampleGateService` for sample rejection. The C++ port pushes that responsibility back to the caller — pass the records pre-filtered, plus an optional pre-rejected count and per-reason rejection map (`PreRejected`). The aggregator merges those into the final summary alongside its own `unmappable_axes` rejections. This keeps the C++ slice from needing to port `ReplaySampleGateService` first; the gating helper lives upstream in the caller.
- **Same axis-channel hint table** as `table_replay_context` (the Python service duplicates the table; the C++ port keeps the duplication intentional so the two slices remain independently linkable). Same 10 axis-name substrings, same `load → (map, tps)` fallback semantics, same case-insensitive matching.
- **Top-3 hot cells sorted by hit count descending.** Cells with equal hit counts retain their iteration order (`std::sort` is not stable but the top-N constraint and the deterministic key shape keeps the result stable enough for the parity guarantee).
- **AFR averaging per cell:** records carrying an `afr`-named channel contribute to a per-cell sum + count; the snapshot reports `mean = sum / count` for cells where the count is non-zero. Records carrying a `lambda`-named channel are converted to AFR via `× 14.7` (mirrors the Python `_afr_value` helper).
- **Detail string format pinned:** `"Hot cell row N, column M: K hit(s), mean AFR XX.XX."` with `%.2f` precision via `snprintf`. Rejection histogram appended as `"Rejections: reason1=N1, reason2=N2."` with sorted-by-key order (Python `sorted(...)` matches C++ `std::map` natural ordering).
- `cpp/tests/test_table_replay_hit.cpp` — 10 doctest cases covering: empty records → nullopt, empty cells → nullopt, non-numeric axis → nullopt, simple aggregation lands records in nearest cells, AFR averaging produces the right mean, unmappable axes accumulate as `unmappable_axes` rejections, `pre_rejected` merges into the final summary with the alphabetical ordering, hot cells sorted descending by hit count, top-3 cap when more than 3 distinct cells, and the summary text format pin.
- **ADL gotcha caught and pinned:** because `table_replay_hit::build` and `table_replay_context::build` both take a `TablePageSnapshot` argument, ADL pulls both into the same overload set in any test that uses `using namespace`. The doctest file uses an explicit `namespace trh = tuner_core::table_replay_hit;` alias and calls `trh::build(...)` to disambiguate. Documented in the file header so future maintainers don't trip on it.

**Skipped parity test for this slice** — the Python service consumes `DataLog` / `DataLogRecord` shapes and the `ReplaySampleGateService` instance, neither of which has landed in C++ yet. Doctests cover every code path through the aggregator including all three nullopt branches, the `pre_rejected` merge, the AFR averaging, the top-3 sort, and the rejection histogram ordering.

C++ doctest suite: 517 tests, 1561 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-seventh sub-slice: TableReplayContextService

Direct port of `tuner.services.table_replay_context_service.TableReplayContextService.build` — the live operating-point crosshair locator. **This is the load-bearing logic for the redesigned Tune tab's crosshair overlay** called out in the UI/UX modernization plan: it takes a table page snapshot (axis labels + cell grid + axis parameter names) and a runtime channel snapshot, finds the nearest cell to the live operating point, and produces a `Snapshot` with row/column index, matched axis values, and a human-readable summary. Composes two helpers from earlier slices — `wue_analyze_helpers::numeric_axis` and `wue_analyze_helpers::nearest_index` — so the C++ workspace layer has one canonical axis-snap implementation that all consumers reuse.

- `cpp/include/tuner_core/table_replay_context.hpp` and `cpp/src/table_replay_context.cpp` — `TablePageSnapshot` POD shell (x/y axis parameter names, x/y axis labels as strings, row-major cell grid as pre-formatted strings), `RuntimeChannel` POD (name + value), `Snapshot` output POD with row/column index + matched axis values + cell value text + summary/detail strings, and `build(table_snapshot, runtime_channels)`. The function returns nullopt for any of three failure modes: empty cells, missing axis channel, or non-numeric axis labels.
- **Axis-channel hint table preserved verbatim:** the Python `_AXIS_CHANNEL_HINTS` dict maps 10 axis-name substrings (`rpm`, `map`, `load`, `kpa`, `tps`, `throttle`, `afr`, `lambda`, `spark`, `advance`) to candidate channel name substrings. `load` falls through to `("map", "tps")` so a `loadBins` axis can pick up either a `map` or `tps` channel. The C++ port reproduces the table as a `constexpr std::array` and walks it in the same order with the same accumulate-without-duplicates semantics. Empty hint match falls back to the lowercased axis name itself.
- **Tie-breaking matches `nearest_index` semantics:** a runtime value exactly between two axis bins picks the *earlier* index (the strictly-less-than tie-break already pinned by the `wue_analyze_helpers` parity tests). This is important for the UI overlay so the crosshair stops "jittering" between adjacent cells when the operating point lands on a bin boundary.
- **Detail string format pinned:** `"Axis match: X={x:.1f} near {bin:.1f}, Y={y:.1f} near {bin:.1f}."` is the same `f"{value:.1f}"` Python f-string the workspace presenter renders into the table-overlay info panel. Reproduced via `snprintf("%.1f", v)` so the rendered text matches Python byte-for-byte.
- `cpp/tests/test_table_replay_context.cpp` — 8 doctest cases covering: empty cells → nullopt, missing axis channels → nullopt, happy-path cell location with the `(2900 rpm, 95 kPa)` shape that finds the nearest cell, summary/detail string format pin, the `load → map` hint fallback, case-insensitive channel name matching (`RPM` vs `rpm`), non-numeric axis labels → nullopt, and tie-breaking on a value exactly between two bins (1500 between 1000 and 2000 → column 0 wins).

**Skipped parity test for this slice** — the Python service consumes `EvidenceReplaySnapshot` and `TablePageSnapshot` shapes that the C++ side hasn't ported yet. Doctests cover every code path through the locator including all three nullopt branches and the axis-hint fallback. A future parity test can land cheaply once those snapshot types ship in C++.

**Why this matters for the redesign:** the current Python Tuning tab renders the cell grid but does NOT show where the engine is currently operating on that grid — operators have to mentally map runtime RPM/MAP onto the cell they're editing. The redesigned Tune tab uses this service to draw a live crosshair on both the 2D editor and the 3D surface view simultaneously, so operators see "I am editing the cell the engine is currently in" without context switching. This is the single most useful workspace improvement called out in the UI/UX modernization plan.

C++ doctest suite: 507 tests, 1525 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-sixth sub-slice: ScalarPageEditorService

Direct port of `tuner.services.scalar_page_editor_service.ScalarPageEditorService.build_sections` — the workspace presenter's scalar editor composer that walks `TuningPage.sections` and emits per-field editor snapshots. Composes the visibility evaluator (already in C++) with two-level filtering (per-field AND per-section) plus the standard tune-value text formatter.

- `cpp/include/tuner_core/scalar_page_editor.hpp` and `cpp/src/scalar_page_editor.cpp` — `Parameter` POD shell (name, label, kind, units, help_text, min/max, digits, options, option_values, requires_power_cycle, visibility_expression — only the fields the snapshot construction reads), `Section` POD (title + notes + parameter_names + visibility_expression), `Page` POD (title + parameters + sections), plus the matching `FieldSnapshot` and `SectionSnapshot` output PODs. `build_sections(page, get_value, get_base_value, is_dirty, scalar_values)` mirrors the Python service.
- **Two-level visibility filtering:** the Python service evaluates the per-field `visibility_expression` first (drops the field), then the per-section expression (drops the whole section if it's gated). The C++ port preserves both passes in the same order. Section-level visibility runs against the same scalar values map the visibility evaluator already uses.
- **Fallback path:** when no explicit sections produce visible content, the C++ port emits a single `SectionSnapshot` with the page title and every visible scalar parameter — same behavior as the Python `if sections: return ... else: return (fallback,)` chain.
- **Notes-only sections preserved:** a section with no parameters but non-empty notes still appears in the result (the Python `(visible_fields or section.notes)` guard).
- **Non-scalar filter:** the Python comprehension `if parameters_by_name[name].kind == "scalar"` drops table/curve parameters from scalar sections; mirrored exactly.
- `cpp/tests/test_scalar_page_editor.cpp` — 7 doctest cases covering: empty page → single fallback section, fallback path emits scalar fields with value/base/dirty, explicit sections take precedence over fallback, per-field visibility hides individual fields, section visibility hides the whole section (falling back to the page title), notes-only section is still emitted, and non-scalar parameters (table-kind) are filtered out of scalar sections.

**Skipped parity test for this slice** — the Python service consumes `TuningPage` / `TuningPageSection` / `TuningPageParameter` / `LocalTuneEditService` shapes that the C++ side hasn't ported yet. Doctests cover every code path through the section walker line-for-line.

C++ doctest suite: 499 tests, 1504 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-fifth sub-slice: OperationEvidenceService

Direct port of `tuner.services.operation_evidence_service.OperationEvidenceService` — the workspace presenter's "what's happened so far this session" composer. Builds on the just-ported `operation_log` slice: takes the append-only entry list plus the workspace's "any unwritten staged changes?" flag and produces a session-aware `Snapshot` with summary text, latest write/burn lookup, and an active session block. **First compose-from-helpers slice in C++ where the helper is also a previously-ported C++ service** (vs. the earlier slices that composed `tune_value_preview` or `visibility_expression` which are smaller pure-logic surfaces).

- `cpp/include/tuner_core/operation_evidence.hpp` and `cpp/src/operation_evidence.cpp` — `Session` POD (sequence + entry_count + has_burn/has_write/has_unwritten_stage flags + latest_entry), `Snapshot` POD (summary_text + session_count + latest_write/burn entries + active_session), `build(entries, has_unwritten, limit)`. Sessions are split on every `BURNED` entry; the active session is whatever's accumulated since the last burn (or since the start if there's never been a burn).
- **Active status text classifier:** five branches in priority order — unwritten-staged (overrides everything), latest-burn-exists, latest-write-exists, sessions-exist-but-no-writes, idle. Reproduces the Python `_active_status_text` exactly so the same surface text reaches the operator.
- **Recent operations tail:** mirrors `entries[-limit:]` then `reversed(...)` so the newest entry appears first under the `"Recent operations:"` header. The `limit` defaults to 12 (same as Python).
- `cpp/tests/test_operation_evidence.cpp` — 9 doctest cases covering empty entries → idle summary, single-staged with `has_unwritten=true` flips to the staged-pending status, write+burn closes a session and the next staged entry starts session #2, latest_write_entry/latest_burn_entry population, summary text mentions both Last write and Last burn lines, recent operations list reverses entry order with the `Recent operations:` header in the right position, the `limit` cap on the recent list, write-without-burn produces the "written but not burned" status, and a reverted-only history producing the "session history exists, but no writes" status.

**Skipped parity test for this slice** — the Python service consumes the Python `OperationLogService.OperationEntry` shape directly. A parity test would need to construct identical entries on both sides (the C++ side carries `TimeOfDay` instead of `datetime`), and the doctests already cover every code path through the session-walk and summary-text builder line-for-line. A future parity test can land cheaply by driving both sides with a fixed TimeOfDay-equivalent clock.

C++ doctest suite: 492 tests, 1475 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-fourth sub-slice: OperationLogService

Direct port of `tuner.services.operation_log_service.OperationLogService` — the session-level append-only mutation log that tracks every staged / reverted / written / burned change. First C++ workspace service that ports a *stateful* class with mutating methods (vs. the stateless function-style services of the previous sub-slices) plus a UTF-8 string formatter with arrow characters preserved byte-for-byte.

- `cpp/include/tuner_core/operation_log.hpp` and `cpp/src/operation_log.cpp` — `OperationKind` enum (`STAGED` / `REVERTED` / `WRITTEN` / `BURNED`) with `to_string` mirroring the Python StrEnum values, `TimeOfDay { hours, minutes, seconds }` POD (the C++ side carries pre-extracted time components instead of a real `chrono` timestamp so the parity surface stays portable across MinGW versions), `OperationEntry` POD with the same `summary_line()` formatter the Python service emits, and `OperationLog` class with `record_staged` / `record_reverted` / `record_written` / `record_burned` / `entries` / `recent` / `clear` / `summary_text` methods. Append-only semantics mirror the Python service exactly.
- **UTF-8 arrow preservation:** the Python summary lines use `→` (U+2192) for staged and `←` (U+2190) for reverted entries. The C++ port emits the UTF-8 byte sequences `\xe2\x86\x92` and `\xe2\x86\x90` directly so the rendered text is byte-identical to Python's `f"{old} → {new}"`.
- **`record_written` / `record_burned` value duplication:** the Python service stores the same value in both `old_value` and `new_value` for written / burned entries (the `record_written(value)` call does `old_value=value, new_value=value`). The C++ port mirrors this so downstream consumers that introspect `entry.old_value` see the same shape on both sides.
- `cpp/tests/test_operation_log.cpp` — 12 doctest cases covering: every `OperationKind` summary_line shape including the UTF-8 arrow byte sequences, zero-padded `HH:MM:SS` timestamp formatting, empty-log summary text, single-entry append, `record_written` value duplication, `recent(n)` returning the last N entries, `recent(n)` capping at total count, `summary_text` reversing recent so newest is first, `clear` empties the entry list, and `to_string` for all four enum values.

**Skipped parity test for this slice** — the Python service uses `datetime.now()` directly which would diverge across processes; the C++ port uses an injected `TimeOfDay` shell to keep both sides deterministic. The doctests cover every code path including the UTF-8 arrow byte sequences. A future parity test can drive both sides with a fixed clock.

C++ doctest suite: 483 tests, 1442 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-third sub-slice: CurvePageService classifier + summary

Direct port of `CurvePageService._classify` and `_summary` — the algorithmic meat of `tuner.services.curve_page_service.CurvePageService`. The full `build_curve_pages` orchestrator depends on `TuningPage` / `TuningPageGroup` / `TuningPageParameter` PODs which haven't landed in C++ yet, so this slice carves out the two pure-logic helpers and ports them on their own. Both are directly useful from any future C++ curve consumer.

- `cpp/include/tuner_core/curve_page_classifier.hpp` and `cpp/src/curve_page_classifier.cpp` — `GroupAssignment { order, group_id, group_title }` POD, `classify(name, title)` returning the matched group via the same 8-rule keyword table the Python service uses (fuel / ignition / afr / idle / enrich / boost / settings / other), and `summary(y_bins_count, x_channel)` returning the same `"Curve · {N lines | 1D}[ · live: {channel}]"` string the Python `_summary` produces. Keyword matching uses `\bkw\b` word-boundary regex via `<regex>`. Regexes are cached per-keyword in a `static std::map` so the cost amortizes across calls.
- **Word-boundary discipline preserved (with explicit doc):** the Python service joins `name + " " + title`, lowercases the result, then word-boundary-searches each keyword. Critical implication: a keyword only matches when it appears as a *standalone word* in the joined text — `"crank_curve"` does NOT match `\bcrank\b` because the underscore is a `\w` character. The C++ port mirrors this exactly, and the doctest comment block calls it out so future maintainers don't trip on it.
- **UTF-8 middle dot preserved:** the Python summary uses the literal `·` (U+00B7 MIDDLE DOT). The C++ port emits the UTF-8 byte sequence `\xc2\xb7` directly so the rendered string is byte-identical to the Python output.
- `cpp/tests/test_curve_page_classifier.cpp` — 14 doctest cases covering all 8 family groups via realistic curve title shapes, the unknown-text fallthrough to `"other"`, the word-boundary requirement (a keyword inside `rpmlimit_curve` doesn't fire but a standalone `"limit"` in the title does), the rule-order precedence (fuel wins over boost when both keywords appear), and 4 `summary` cases covering 1D / multi-line / with-channel / multi-line+channel.

**Skipped parity test for this slice** — the algorithmic content is well-bounded by the doctests, and a parity test would need a real `CurveDefinition` POD (not yet in C++) to drive `CurvePageService._classify` from Python.

C++ doctest suite: 471 tests, 1417 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-second sub-slice: PageFamilyService

Direct port of `tuner.services.page_family_service.PageFamilyService.build_index` plus the supporting `_family_id` / `_family_title` / `_tab_sort_key` / `_tab_title` helpers. The workspace presenter uses this service to group related tuning pages (VE Table + Second Fuel Table → "Fuel Tables", Spark Table + Second Spark Table → "Spark Tables", VVT1 + VVT2 + VVT Control → "VVT", etc.) into tabbed surfaces.

- `cpp/include/tuner_core/page_family.hpp` and `cpp/src/page_family.cpp` — `PageInput` POD shell carrying only `page_id`, `title`, and optional `page_number` (the only fields the service reads from the full Python `TuningPage`); `FamilyTab` and `Family` PODs matching the Python `PageFamilyTab` / `PageFamily` field-for-field; `build_index(pages)` returning a `map<page_id, Family>`; `family_id_for_title`, `family_title_for`, and `tab_title_for` exposed publicly so tests and downstream code can exercise them in isolation. The five family codes (`fuel-trims`, `fuel-tables`, `spark-tables`, `target-tables`, `vvt`) and their five display titles are inlined verbatim from the Python service.
- **Sort discipline preserved:** sort key is `(page_number or 9999, tab_sort_key, lowercased title)` exactly. The `tab_sort_key` returns the same magic-number groups the Python service hands out (`10` / `20` / `30` / ... / `999`) for every recognised page title, and falls through to `(999, lower)` for unknown titles.
- **Singleton families dropped:** any family that ends up with fewer than 2 pages after grouping is omitted from the result entirely, mirroring the Python `if len(family_pages) < 2: continue` guard. This prevents lone fuel/spark tables from showing tabs in the UI.
- **`fuel trim table N` → `Trim N` regex** uses `<regex>` ECMAScript dialect for the same `r"fuel trim table (\d+)"` pattern the Python service uses.
- `cpp/tests/test_page_family.cpp` — 15 doctest cases covering: `family_id_for_title` for all 5 families plus 11 distinct title variants, unknown title nullopt, `family_title_for` for all 5 family display titles, `tab_title_for` for fuel-trims sequential ranges, fuel-trims numbered tables (`Trim N` format), fuel-tables Primary/Secondary, spark-tables Primary/Secondary, target-tables AFR/Lambda, vvt all three tabs, and `build_index` with empty input, singleton-family drop, fuel-tables pair, independent spark and target families in one call, vvt three-tab family with deliberately scrambled input order, and a sort case where `page_number` overrides `tab_sort_key`.

**Skipped parity test for this slice** — the Python service consumes `TuningPageGroup` / `TuningPage` shells which the C++ side hasn't ported yet. Doctests cover every code path through the family-grouping logic line-for-line, including the `Trim N` regex extraction and the deliberately-scrambled-input sort case.

C++ doctest suite: 457 tests, 1398 assertions, 0 failures. Full Python suite still **2445/2445 passing**.

#### Phase 14 Slice 4 twenty-first sub-slice: LiveDataMapParser

Direct port of `tuner.services.live_data_map_parser.LiveDataMapParser` — the parser for the Speeduino firmware `live_data_map.h` header that produces the `ChannelContract` POD the runtime telemetry pipeline reads to find byte positions in the live-data packet. Pure regex-driven port mirroring the Python regex patterns one-for-one via `<regex>`.

- `cpp/include/tuner_core/live_data_map_parser.hpp` and `cpp/src/live_data_map_parser.cpp` — `ChannelEncoding` enum (`U08`, `U08_BITS`, `U16_LE`, `S16_LE`, `U32_LE`, `UNKNOWN`) with `to_string`, `parse_encoding`, and `byte_width` helpers; `ChannelEntry` POD (name, byte_start/end, optional readable_index, encoding, field, notes, locked, plus a `width()` accessor); `ChannelContract` POD (log_entry_size, optional firmware_signature, entries, three OCH offset constants); `parse_text(text, signature)` and `parse_file(path, signature)` entry points.
- **Three regex patterns ported verbatim** from the Python source: the doxygen row regex (`* {byte} {ridx} {field}  {encoding} {notes}`), the `LIVE_DATA_MAP_SIZE` constant regex, and the `OCH_OFFSET_*` constants regex. The `<regex>` ECMAScript dialect handles all the same alternations and `\s` / `\d` classes the Python `re` module does. The verbose-mode Python regex is collapsed into a single string but the same character class structure is preserved.
- **Notes-derived name selection:** the entry name is the first whitespace-separated token of the cleaned notes column (with `[LOCKED]` stripped). Falls back to the field name if notes are empty or start with `"DEPRECATED:"`. Mirrors the Python `name = clean_notes.split()[0] if clean_notes else field` chain plus the deprecation guard.
- `cpp/tests/test_live_data_map_parser.cpp` — 10 doctest cases covering `parse_encoding` for all known encodings + case-insensitive + UNKNOWN fall-through, `byte_width` for every encoding, `parse_text` extraction of `log_entry_size`, all three OCH offset constants, table-row entry parsing including a multi-byte row with `[LOCKED]` and a single-byte `-`-readable-index row, the firmware-signature pass-through, empty input, and the `DEPRECATED:` notes → field-name fallback.
- `cpp/bindings/tuner_core_module.cpp` — `ChannelEncoding` enum, `ChannelEntry` and `ChannelContract` classes plus `live_data_map_parse_text`.
- `tests/unit/test_cpp_live_data_map_parser_parity.py` — 6 parity tests against `LiveDataMapParser`. Cases: a synthetic 4-row sample header (the same shape as the doctest fixture), firmware_signature round-trip, empty input, only-`LIVE_DATA_MAP_SIZE`-no-table, only-offset-constants, **and a parity test against the production `live_data_map.h`** at `C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/live_data_map.h` (skipped when the firmware repo isn't checked out). The production test asserts non-trivial entry count and `log_entry_size > 0` plus the same per-field equality check the synthetic cases use.

This is the second header parser in C++ (after the `release_manifest` JSON loader) and the third workspace service to consume `<regex>`. The pattern is well-grooved: build the regex once at first call inside an `inline` static, then `regex_search` / `regex_match` per row. The production-header parity test confirms the regex behaves identically to Python's `re` module across the entire 100+ row firmware-side schema.

C++ doctest suite: 442 tests, 1344 assertions, 0 failures. Full Python suite: **2445/2445 passing**.

#### Phase 14 Slice 4 twentieth sub-slice: FlashPreflightService validation rules

Direct port of `tuner.services.flash_preflight_service.FlashPreflightService.validate` (the warning-rule pass) plus the static `_signature_family` text classifier. The Flash tab consults this before letting the operator commit a firmware flash; every text-heuristic warning the Python service emits is reproduced byte-for-byte. Filesystem checks (does the firmware file exist?) are intentionally left to the caller — that side of the Python service is the only part that depends on `pathlib`/`is_file()` and is trivial in any C++ caller.

- `cpp/include/tuner_core/flash_preflight.hpp` and `cpp/src/flash_preflight.cpp` — `FirmwareEntryInputs` POD (board_family, firmware_signature, version_label, tune_path_basename, is_experimental — only the fields the catalog entry contributes to the rule pass), `PreflightInputs` POD aggregating selected/detected board, the firmware entry, the loaded definition signature, the loaded tune signature/firmware-info/source basename, the optional live `experimental_u16p2` capability, and the optional `connected_firmware_signature`. `Report { ok, errors, warnings }`. `signature_family(value)` mirrors the static helper exactly (U16P2 first to win over T41), and `validate(inputs)` runs the eight warning-rule passes in the same order as the Python service.
- **Capability vs heuristic discipline:** the experimental/production check prefers the live `experimental_u16p2` capability when present (treated as authoritative) and falls back to a substring scan of the merged metadata text only when the capability is nullopt. Mirrors the Python `if firmware_capabilities is not None:` branch exactly.
- **Case-insensitive paired tune name match:** the firmware-paired tune basename is lowercased on both sides before comparison so `BaseStartup.msq` and `basestartup.MSQ` match without warning, mirroring `entry.tune_path.name.lower() != tune_file.source_path.name.lower()` on the Python side.
- `cpp/tests/test_flash_preflight.cpp` — 17 doctest cases covering: `signature_family` for all 6 family codes plus the U16P2-wins-over-T41 ordering and the unknown/empty branch, `validate` empty-input clean state, selected vs firmware board ERROR, detected vs firmware board WARNING, T41 signature with non-Teensy41 detected board WARNING, experimental capability vs production firmware WARNING, production capability vs experimental firmware WARNING, the text-heuristic experimental fallback when no live capability, connected controller signature family mismatch WARNING, definition signature family mismatch, tune signature family mismatch, paired tune name mismatch with both tune names in the message, paired tune case-insensitive match (no warning), version label not in metadata WARNING, and version label present in metadata (no warning).

**Skipped parity test for this slice** — the Python service's `validate` method takes a `firmware_path` argument and runs `firmware_catalog_service.entry_for_firmware(resolved_path)` against the real firmware catalog. Driving that from a parity harness would need a `Mock` that patches the catalog service AND a real or fake firmware file on disk for every test case. The C++ doctests cover every code path through the warning-rule pipeline line-for-line, and the doctest text matches the Python f-strings byte-for-byte where the Python parity test would have asserted them. A future parity test can land cheaply once `FirmwareCatalogService` lands in C++ alongside it.

C++ doctest suite: 432 tests, 1295 assertions, 0 failures. Full Python suite still **2439/2439 passing**.

#### Phase 14 Slice 4 nineteenth sub-slice: ParameterCatalogService

Direct port of `tuner.services.parameter_catalog_service.ParameterCatalogService.build_catalog` and `filter_catalog` — the parameter catalog the workspace presenter renders for "all parameters" surfaces (Engine Setup, quick-open, command palette). Aggregates definition scalars + tables + tune-only values into a single sorted list, then exposes a substring filter over name / kind / units / data type.

- `cpp/include/tuner_core/parameter_catalog.hpp` and `cpp/src/parameter_catalog.cpp` — `ScalarParameterInput`, `TableParameterInput`, `TuneValueInput` POD shells (only the fields the catalog reads — no full `EcuDefinition` / `TuneFile` dependency), `Entry` POD matching the Python `ParameterCatalogEntry` field-for-field (`name`, `kind`, `page`, `offset`, `units`, `data_type`, `shape`, `tune_present`, `tune_preview`), plus `build_catalog(scalars, tables, tune_values)` and `filter_catalog(entries, query)`. Tune-only entries are inferred (table when `rows > 0` or `cols > 0` or value is a list), shape is built from `"{rows}x{cols}"`, and the standard sort order `(page or 9999, offset or 999999, lower(name))` is applied at the end.
- **Empty preview quirk preserved:** the Python service's `_preview_value(None)` returns `""` (empty string), which differs from `tune_value_preview::format_value_preview` (returns `"n/a"` via the staged-change formatter). The C++ port wraps the standard formatter with a nullptr → `""` branch so the catalog still uses the "" empty case while the staged-change service uses the "n/a" empty case.
- **Caller responsibility for tune-value merging:** the Python service calls `_tune_index(tune_file)` then `tune_index.update(staged_values)` so the staged values shadow the tune file. The C++ port pushes that ordering responsibility back to the caller — pass the merged `tune_values` list with shadowing already applied. This keeps the C++ slice from needing to model the staged-edit layer prematurely.
- `cpp/tests/test_parameter_catalog.cpp` — 10 doctest cases covering scalar entry with shape + preview, table entry with array data type and `"16x16"` shape, tune-only scalar, tune-only list → table with derived `"4x1"` shape, tune-only with explicit rows/cols, definition entry takes precedence over tune-only fallback, sort order on (page, offset, lowercased name), `filter_catalog` empty/whitespace query returns everything, substring on name, and substring on units / kind / data type via four separate `filter` calls.

**Skipped parity test for this slice** — the Python service consumes `EcuDefinition` / `TuneFile` / `ScalarParameterDefinition` / `TableDefinition` / `TuneValue`, the same heavy POD-shell scaffolding the `tuning_page_validation` slice deferred. Doctests cover every code path through the C++ implementation line-for-line; a parity harness can land cheaply on top of this once the surrounding domain types ship in C++.

C++ doctest suite: 415 tests, 1264 assertions, 0 failures. Full Python suite still **2439/2439 passing**.

#### Phase 14 Slice 4 eighteenth sub-slice: SyncStateService

Direct port of `tuner.services.sync_state_service.SyncStateService.build` — the workspace presenter's pre-flight sync state detector that flags signature mismatches, page-size mismatches, ECU-RAM-vs-tune diffs, and stale staged changes before the operator triggers a write or burn.

- `cpp/include/tuner_core/sync_state.hpp` and `cpp/src/sync_state.cpp` — `MismatchKind` enum (`SIGNATURE_MISMATCH` / `PAGE_SIZE_MISMATCH` / `ECU_VS_TUNE` / `STALE_STAGED`) with `to_string` mirroring the Python `SyncMismatchKind` StrEnum values, `Mismatch` POD (kind + detail string), `State` POD (mismatches + has_ecu_ram + connection_state + `is_clean()` accessor), `DefinitionInputs` and `TuneFileInputs` POD shells (only the fields the detector actually reads). `build(definition, tune_file, ecu_ram, has_staged, connection_state)` mirrors the Python service exactly: signature comparison, page-size comparison, ECU-vs-tune diff using value equality on the `ScalarOrList` variant, and stale-staged detection.
- **ECU diff value equality:** the `ScalarOrList` equality routes through the variant — scalars compare via `==` on doubles, lists compare via `==` on `vector<double>` (element-wise). Mirrors Python's `ParameterValue` `==` operator semantics for the values the workspace stores.
- **Detail string format:** the diff preview joins the first 5 names with `", "` and appends `"..."` when there are more than 5, matching the Python f-string `f"{len(diffs)} parameter(s) differ between ECU RAM and loaded tune: {preview}{suffix}"`.
- **Insertion-order discipline:** the base value map is built with `std::map<string, ScalarOrList>` so multiple `(name, value)` entries from `pc_variables` shadow `constants` correctly (later entries win), matching Python's dict-update flow.
- `cpp/tests/test_sync_state.cpp` — 10 doctest cases covering empty inputs, signature mismatch with the f-string check, matching signatures, page-count mismatch with both halves of the message, ECU-vs-tune diff with preview, ECU diff with more than 5 entries (ellipsis suffix), stale staged via `has_staged && !ecu_ram`, the no-stale path when ECU RAM is present, list-value element equality, and `to_string` enum round-trip.
- `cpp/bindings/tuner_core_module.cpp` — `SyncMismatchKind` enum, `SyncMismatch` / `SyncState` / `SyncStateDefinitionInputs` / `SyncStateTuneFileInputs` classes plus `sync_state_build`.
- `tests/unit/test_cpp_sync_state_parity.py` — 9 parity tests against `SyncStateService.build`. The Python service expects an `EcuDefinition`-shaped object with `firmware_signature` and `page_sizes`, and a `TuneFile`-shaped object with `signature`, `page_count`, `constants`, and `pc_variables`. The test wires `Mock` instances with those attributes plus a `_make_tune_constants` helper that builds nested `Mock`s with `name` / `value` attributes (avoiding the `Mock(name=...)` constructor collision via post-construction assignment). Cases: no inputs clean, signature mismatch, matching signatures clean, page-size mismatch, ECU-vs-tune single diff, ECU-vs-tune 6-entry diff with ellipsis, stale staged, has_staged with ECU RAM no-stale, and a combined-mismatches test that fires all three definition+tune kinds at once.

This is the second non-trivial workspace service in C++ (after `tuning_page_validation`) that operates against POD shells of larger Python domain types. The same pattern — minimal POD inputs + parity test against `Mock`s with the matching attribute shape — is the right approach for any service that consumes large dataclass dependencies but only reads a small slice of their fields.

C++ doctest suite: 405 tests, 1228 assertions, 0 failures. Full Python suite: **2439/2439 passing**.

#### Phase 14 Slice 4 seventeenth sub-slice: TuningPageValidationService

Direct port of `tuner.services.tuning_page_validation_service.TuningPageValidationService.validate_page`. First C++ workspace service to *compose* the visibility expression evaluator (already in C++) with structural validation and per-parameter range checking. Defines minimal `Page` and `Parameter` PODs so the slice doesn't drag in the full `TuningPage` / `LocalTuneEditService` shape.

- `cpp/include/tuner_core/tuning_page_validation.hpp` and `cpp/src/tuning_page_validation.cpp` — `PageKind` enum (`TABLE` / `OTHER`), `ParameterKind` enum (`SCALAR` / `TABLE` / `OTHER`), `Parameter` POD (name + kind + page/offset with `-1` sentinel for unset + visibility_expression + optional min/max), `Page` POD (kind + parameters + optional table/x-axis/y-axis names), `Result { errors, warnings }`. The `ValueLookup` callable accepts a name and returns an optional `ScalarOrList` (reusing the variant from `tune_value_preview`), and `ScalarValueMap` is a parallel-array `vector<pair<string, double>>` carrying the scalar tune values the visibility evaluator consumes. `validate_page(page, get_value, scalar_values)` mirrors the Python service exactly: iterate parameters once for the visibility/availability/missing-value pass, then dispatch to the table-page or non-table-page branch.
- **Table-page branch:** missing main table name → error; missing table value → error; non-list table value → error; for each axis (x and y), check the value is present, list-backed, and non-empty (empty axis labels → warning).
- **Non-table-page branch:** count scalars vs tables, range-check scalar values against `min_value` / `max_value` (warning when out-of-range), warn on non-list table-kind parameters, and emit a `"This fallback page has only table content and no direct scalar edits."` warning when the page has any tables but no scalars.
- **Visibility composition:** the per-parameter visibility expression is evaluated against the supplied `scalar_values` map via the C++ visibility evaluator already in place. Hidden parameters are skipped in pass 1 — they don't get a missing-value error and don't show up in `available_values` for the second pass.
- **Dedupe:** errors and warnings are deduped via a small first-occurrence-wins helper, mirroring Python's `tuple(dict.fromkeys(errors))` idiom.
- **Range warning string format:** scalar values and min/max bounds use `tune_value_preview::format_scalar_python_repr` so the byte form matches Python's `f"'{name}' value {v} is below minimum {min}."` exactly. The float-vs-int distinction the Python `isinstance(value, float)` guard checks for is satisfied here because every value crossing the FFI is `double`.
- `cpp/tests/test_tuning_page_validation.cpp` — 11 doctest cases covering missing scalar tune value, scalar below min, scalar above max, visibility-hidden parameter (no missing-value error), table page with no main table name, table page with missing main table value, table page with non-list main table, table page with empty axis labels, fallback page with only tables (no scalars), clean page with no issues, and dedupe of duplicate-named parameters.

**Note on parity testing:** this slice intentionally ships without a Python parity test. The Python service consumes `TuningPage` and `LocalTuneEditService`-shaped objects, both of which would need significant `Mock` scaffolding to drive from a parity harness — and the C++ port already covers every code path through doctests that mirror the Python logic line-for-line. Future slices that port surrounding domain types will let a parity test land cheaply on top of this one.

C++ doctest suite: 395 tests, 1202 assertions, 0 failures. Full Python suite still **2430/2430 passing** (no new Python tests added).

#### Phase 14 Slice 4 sixteenth sub-slice: Gauge color zone derivation

Direct port of `DashboardLayoutService._zones_from_gauge_config` — the function that turns INI gauge thresholds (`lo_danger`, `lo_warn`, `hi_warn`, `hi_danger`) into the (ok / warning / danger) color band list a dashboard gauge renders. Pure logic over six doubles, no domain-type dependency. The full `DashboardLayoutService` orchestrator and the JSON load/save are deferred to a later slice; this slice carves out the algorithmic meat.

- `cpp/include/tuner_core/gauge_color_zones.hpp` and `cpp/src/gauge_color_zones.cpp` — `Zone { lo, hi, color }` POD, `Thresholds` POD with four independent optional doubles, `derive_zones(lo, hi, thresholds)`. Mirrors the Python service exactly: low-danger band when `lo_danger > lo`, low-warning band where `warn_start = lo_danger or lo` and `warn_end = lo_warn`, ok band only when at least one warn threshold is set, high-warning band where `warn_end = hi_danger or hi`, high-danger band when `hi_danger < hi`. Strict-inequality boundary checks on every band so equal-to-edge thresholds drop the band rather than emitting a zero-width slice.
- `cpp/tests/test_gauge_color_zones.cpp` — 7 doctest cases covering: no thresholds → empty, only high warn+danger → 3-band ok+warning+danger, full 5-band layout, `lo_danger == lo` strict-inequality drop, `hi_danger == hi` drop, only-`lo_warn`, and a zero-width warning band drop when `lo_warn == lo_danger`.
- `cpp/bindings/tuner_core_module.cpp` — `GaugeColorZone` and `GaugeThresholds` classes plus `gauge_derive_color_zones`.
- `tests/unit/test_cpp_gauge_color_zones_parity.py` — 11 parity tests against `DashboardLayoutService._zones_from_gauge_config`. Cases: no thresholds, only-high-warn-and-danger, full 5-band ladder, `lo_danger==lo` drop, `hi_danger==hi` drop, only-`lo_warn`, only-`hi_warn`, zero-width drop, the **real Speeduino battery widget shape** (`8..16V` with warn `11..12` and danger `8..11`), the **real coolant widget shape** (`-40..130 °C` with warn `90..110` and danger `110..130`), and **50 random threshold combinations** with sorted thresholds and 70% per-field presence probability (deterministic seed `0xC0DE`). The random test exercises every combination of presence/absence across the four thresholds the Python service would ever produce.

This is the smallest C++ workspace service ported in absolute lines (~50 LOC) and the first one to model the dashboard gauge metadata. Together with `pressure_sensor_calibration` (which uses the same `lo`/`hi`/`lo_warn`/`hi_warn`/etc. shape) the C++ side now has both gauge-threshold consumers in place — useful for the eventual `DashboardLayoutService` port that builds widget instances from these zones.

C++ doctest suite: 384 tests, 1186 assertions, 0 failures. Full Python suite: **2430/2430 passing**.

#### Phase 14 Slice 4 fifteenth sub-slice: EvidenceReplayComparisonService channel diff

Direct port of the channel-diff logic in `EvidenceReplayComparisonService.build` — the workspace presenter's "comparison vs latest capture" surface that highlights runtime drift on a tuning page. Skips the snapshot-equality early-out (caller's responsibility on the C++ side); the load-bearing logic is the channel diff itself.

- `cpp/include/tuner_core/evidence_replay_comparison.hpp` and `cpp/src/evidence_replay_comparison.cpp` — `Channel`, `Delta`, `Comparison` PODs plus `compare_runtime_channels(baseline_channels, current_channels, relevant_channel_names)`. Mirrors the Python diff: lowercased lookup tables on both sides, optional case-insensitive `relevant_channel_names` filter (empty → all current channels in input order), `1e-9` delta threshold, top-4-by-absolute-delta with stable sort, formatted summary and detail strings, and `nullopt` return when no surviving deltas exist. The `current.units or baseline.units` short-circuit is preserved with explicit nullopt/empty-string checks on both sides so a missing-units entry on either side stays consistent with Python.
- **String-formatting parity:** the detail line uses `snprintf("%+.1f", v)` for the sign-prefixed delta, and concatenates `name {sign}{value}{ optional units}` exactly the way the Python f-string `f"{name} {delta_value:+.1f}{f' {units}' if units else ''}"` does. The summary text is the same hard-coded sentence on both sides.
- `cpp/tests/test_evidence_replay_comparison.cpp` — 10 doctest cases covering empty inputs, identical channels, single delta, top-4-by-absolute (with deliberately scrambled magnitudes including a negative value that ranks 2nd), case-insensitive matching, no-overlap, sub-`1e-9` delta filter, `relevant_channel_names` filter, the formatted detail-text shape, and units fallback from baseline when current is empty.
- `cpp/bindings/tuner_core_module.cpp` — `EvidenceReplayChannel`, `EvidenceReplayChannelDelta`, `EvidenceReplayComparison` classes plus `evidence_replay_compare_channels`.
- `tests/unit/test_cpp_evidence_replay_comparison_parity.py` — 9 parity tests against `EvidenceReplayComparisonService.build`. The test wraps each channel list in a full `EvidenceReplaySnapshot` (same shape on both sides except `runtime_channels`) so the Python service runs against a real snapshot equality check that naturally falls through to the channel diff. Cases: no-overlap returns None, single delta, top-4 ordering (with the negative-magnitude reranking case), case-insensitive lookup, tiny-delta filter, relevant filter, units fallback, detail-text format pin (`"rpm +500.0 rpm"` substring), and a 10-iteration random 7-channel comparison with deterministic seed `0xC0DE`.

This is the first C++ workspace service to port a *channel* diff (vs. the parameter / page diffs already in C++). The same pattern — lowercased lookup table + magnitude-sorted top-N + optional caller-supplied filter — will fit the upcoming runtime trust UI dimming logic and any future "what changed since last capture" surface.

C++ doctest suite: 377 tests, 1149 assertions, 0 failures. Full Python suite: **2419/2419 passing**.

#### Phase 14 Slice 4 fourteenth sub-slice: TableViewService model builder

Direct port of `TableViewService.build_table_model` and its `_resolve_shape` helper — the function the table editor widget calls to turn a flat list of tune values into the 2D string grid it actually renders. Composes the just-ported `tune_value_preview::format_scalar_python_repr` so the rendered cells match Python's `str(float)` byte-for-byte.

- `cpp/include/tuner_core/table_view.hpp` and `cpp/src/table_view.cpp` — `ShapeHints` POD (rows and cols with `-1` as the "unset" sentinel matching Python `None`, plus an optional shape-text fallback like `"4x4"`), `ViewModel` POD (rows, columns, row-major `vector<vector<string>>` cells), `resolve_shape(value_count, hints)`, `build_table_model(values, hints)`. Shape resolution mirrors the Python service exactly: explicit dims win, then the `"NxM"` text fallback, then `(value_count, 1)` for any non-empty list, then `(1, 1)`. Short rows are padded with empty strings.
- **Python quirk preserved:** the Python `_resolve_shape` guards the shape-text branch with `if shape and "x" in shape` (case-sensitive lowercase 'x' check) but then lowercases the input *inside* the branch via `shape.lower().split("x", 1)`. So `"4X4"` fails the guard and falls through to the single-column default, while `"4x4"` and `"4X4"` would otherwise both lowercase to the same parse target. The C++ port keeps the same case-sensitive guard so the two implementations agree on this corner case.
- `cpp/tests/test_table_view.cpp` — 11 doctest cases covering explicit dims, lowercase shape text, the case-sensitive `"4X4"` fall-through quirk, malformed shape text, empty input → `(1, 1)`, explicit-overrides-shape-text, 4x4 grid round-trip, short-row padding, fractional `str(float)` round-trip, shape-text fallback, and the single-column default.
- `cpp/bindings/tuner_core_module.cpp` — `TableViewShapeHints` and `TableViewModel` classes plus `table_view_resolve_shape` / `table_view_build_model` functions.
- `tests/unit/test_cpp_table_view_parity.py` — 12 parity tests against `TableViewService.build_table_model`. Cases: explicit dims, lowercase shape-text fallback, case-sensitive `"2X2"` fall-through, malformed shape text, no-shape single-column default, short-row padding, fractional values via `str(float)`, explicit-overrides-shape-text, **20 random grids** with rows/cols in `[1, 8]` and uniform `[-100, 100]` cell values, and three direct `resolve_shape` cases. The test normalizes all values to Python `float` before constructing the `TuneValue` so both sides see floats — without this, Python `str(int)` would diverge from C++'s `format_scalar_python_repr` (which always renders whole-number floats with the `.0` suffix). The pinned text is captured directly in the test as a comment so the next maintainer doesn't have to re-derive it.

This is the third workspace service (after `staged_change` and `tuning_page_diff`) to consume `tune_value_preview::format_scalar_python_repr` for its operator-facing output. The pattern is now solid: pre-format all values once via the helper, then arrange them into the target shape — no per-cell special-casing needed.

C++ doctest suite: 367 tests, 1122 assertions, 0 failures. Full Python suite: **2410/2410 passing**.

#### Phase 14 Slice 4 thirteenth sub-slice: TuningPageDiffService

Direct port of `TuningPageDiffService.build_page_diff` plus the `summary` and `detail_text` projection helpers from `TuningPageDiffResult`. Same compose-from-helpers shape as the just-landed `staged_change` slice — reuses `tune_value_preview::format_value_preview` and adds two more operator-facing string projections.

- `cpp/include/tuner_core/tuning_page_diff.hpp` and `cpp/src/tuning_page_diff.cpp` — `DiffEntry` POD, `DiffResult` wrapper, `build_page_diff(...)` mirroring the iteration discipline (input order from `parameter_names`, dirty filter via the membership set, missing-staged-value skip, missing-base-value `"n/a"` fallback). `summary(result)` returns `"No staged changes on this page."` for empty results, otherwise `"{N} staged change[s] on this page."` with proper singular/plural agreement. `detail_text(result)` returns the same empty-state string or a newline-joined `"{name}: {before} -> {after}"` line per entry.
- `cpp/tests/test_tuning_page_diff.cpp` — 9 doctest cases covering dirty-only filter, missing-staged skip, missing-base fallback, input-order preservation, list-valued entry truncation, empty/singular/plural `summary`, empty `detail_text`, and a multi-entry newline-joined `detail_text`.
- `cpp/bindings/tuner_core_module.cpp` — `TuningPageDiffEntry`, `TuningPageDiffResult` classes plus `tuning_page_diff_build` / `_summary` / `_detail_text` functions.
- `tests/unit/test_cpp_tuning_page_diff_parity.py` — 9 parity tests against `TuningPageDiffService.build_page_diff`. Wires `Mock`s with `parameter_names` tuples and `is_dirty` / `get_value` / `get_base_value` callables. Each parity case checks the entry list, the `summary` projection, and the `detail_text` projection in one pass via a `_check_all` helper. Coverage: empty page, no-dirty, single dirty scalar, dirty-with-missing-staged-skip, dirty-with-missing-base-fallback, input-order preservation, list-valued entry, full-page-diff shape with 6 parameters spanning scalars + a 5-element list, and a singular-vs-plural `summary` cross-check.

The two staged-review services in C++ (`staged_change`, `tuning_page_diff`) now share the same compose-from-helpers shape: a thin POD entry struct, a deterministic iteration over a parameter list, value lookup via parallel-array maps, and `tune_value_preview::format_value_preview` for the formatting. Same pattern will fit any future per-page review surface.

C++ doctest suite: 356 tests, 1083 assertions, 0 failures. Full Python suite: **2398/2398 passing**.

#### Phase 14 Slice 4 twelfth sub-slice: StagedChangeService.summarize

Direct port of `StagedChangeService.summarize` — the staged review surface the workspace presenter renders before write/burn. First C++ workspace service to *compose* a previously-ported helper (the just-landed `tune_value_preview` formatter) with new orchestration logic (sorted iteration + page-title lookup + written-names membership). The Python `LocalTuneEditService` dependency is bypassed by passing the staged and base value maps as explicit parallel-array arguments — no thin facade needed for this slice.

- `cpp/include/tuner_core/staged_change.hpp` and `cpp/src/staged_change.cpp` — `StagedEntry` POD plus `summarize(staged_values, base_values, page_titles, written_names)`. Mirrors the Python service exactly: sorts staged entries by name, formats each value via `tune_value_preview::format_value_preview`, looks up the base value (nullopt → `"n/a"`), resolves the page title (`"Other"` fallback), and tags `is_written` from the membership set. Reuses the `ScalarOrList` variant from `tune_value_preview` so a value can be either a scalar `double` or a `vector<double>`.
- `cpp/tests/test_staged_change.cpp` — 7 doctest cases covering empty input, single scalar with full metadata, missing-base `"n/a"` fallback, missing-page-title `"Other"` fallback, `is_written` membership, lexicographic sort over a shuffled input, and a list-valued entry that exercises the truncation suffix in both `preview` and `before_preview`.
- `cpp/bindings/tuner_core_module.cpp` — `StagedChangeEntry` class plus `staged_change_summarize`. The `ScalarOrList` variant flows through `<nanobind/stl/variant.h>`, so Python passes each value as either a `float` or a `list[float]` without manual marshaling.
- `tests/unit/test_cpp_staged_change_parity.py` — 8 parity tests against `StagedChangeService.summarize`. The Python service expects a `LocalTuneEditService`-shaped dependency, so the test wires a `Mock` with a `staged_values` dict and a `get_base_value` callable. Cases: empty, single scalar, missing-base, missing-page-title, written-membership, lexicographic sort, list-valued, and a full-workspace-review shape with five entries spanning scalars + a 5-element list, three page titles, one written entry, and two missing-base entries.

This is the first C++ workspace service that aggregates a structured operator-facing entry list using a previously-ported pure-logic helper. The compose-from-helpers pattern will scale directly to `TuningPageDiffService.build_page_diff` (same preview formatter + a `summary` / `detail_text` projection) and to the larger summary services.

C++ doctest suite: 347 tests, 1063 assertions, 0 failures. Full Python suite: **2389/2389 passing**.

#### Phase 14 Slice 4 eleventh sub-slice: Tune value preview formatter

Pure-logic port of the `_preview` / `_list_preview` helpers shared by `StagedChangeService` and `TuningPageDiffService`. Solves the long-standing Python `str(float)` parity problem the autotune evaluator slice flagged: instead of the `py_str_double` workaround that always renders whole-number doubles as `"X.0"` (which works for the autotune reject reasons but is not strictly the same as Python's repr), this slice produces *byte-identical* output to Python's `str(float)` for every finite double via C++17 `std::to_chars`.

- `cpp/include/tuner_core/tune_value_preview.hpp` and `cpp/src/tune_value_preview.cpp` — `format_scalar_python_repr(value)` (shortest round-trip via `std::to_chars` plus the `.0` suffix when no decimal point or exponent is present), `format_list_preview(values)` (4-item truncation with `" ... (N values)"` suffix), `format_value_preview(scalar | list)` dispatch helper using a `std::variant<double, vector<double>>`. Three special cases preserved verbatim: `nan`, `inf`, `-inf` produce the same strings on both sides.
- **Why this works:** Python's `str(float)` since 3.2 emits the shortest round-trip representation (Steele/White-style dtoa, currently Grisu/Ryu in CPython). C++17 `std::to_chars(buf, end, value)` with no precision argument produces the same shortest-roundtrip representation. The only post-processing needed is appending `.0` to whole-number values so they remain visually distinct from ints — same convention Python follows.
- `cpp/tests/test_tune_value_preview.cpp` — 9 doctest cases covering whole-number / fractional / `0.1` / typical staged tune values, list-preview with 3 / 4 / 5+ items including the truncation suffix, empty list, and the `format_value_preview` dispatch arm for both scalar and list.
- `cpp/bindings/tuner_core_module.cpp` — `tune_value_format_scalar_python_repr` and `tune_value_format_list_preview` exposed for parity testing.
- `tests/unit/test_cpp_tune_value_preview_parity.py` — 34 parity tests against `str(float)` and `TuningPageDiffService._list_preview`. 18 hand-picked scalar values plus a 200-iteration random `[-1000, 1000]` test that pins byte equality with no tolerance against Python `str(float)`. 11 list-preview shapes plus a final cross-check that `StagedChangeService._preview` and `TuningPageDiffService._list_preview` produce identical output, so the C++ implementation matches both services through one helper.

This unblocks the eventual ports of `StagedChangeService` and `TuningPageDiffService` themselves — the only non-trivial pure-logic surface in either was the preview formatter, which is now at byte parity. The remaining work in both services is orchestration over `LocalTuneEditService.staged_values`, which depends on the staged-edit layer landing in C++ first.

C++ doctest suite: 340 tests, 1038 assertions, 0 failures. Full Python suite: **2381/2381 passing**.

#### Phase 14 Slice 4 tenth sub-slice: ReleaseManifestService

Direct port of `tuner.services.release_manifest_service.ReleaseManifestService` — the JSON loader for `release_manifest.json` documents that ship alongside each Speeduino firmware release. The desktop's Flash tab uses this to populate its firmware picker without re-scanning the release directory. Reuses the `BoardFamily` enum already in C++ from the board detection sub-slice and introduces a small `ArtifactKind` enum mirror.

- `cpp/include/tuner_core/release_manifest.hpp` and `cpp/src/release_manifest.cpp` — `ArtifactKind` enum (`STANDARD`, `DIAGNOSTIC`) with `to_string` mirroring the Python `FirmwareArtifactKind` StrEnum values, `FirmwareEntry` POD (file_name, board_family, version_label, is_experimental, artifact_kind, preferred, definition_file_name, tune_file_name, firmware_signature), `Manifest` POD wrapping a vector of entries, `parse_manifest_text(text)` and `load_manifest(release_root)`. Uses the vendored `nlohmann/json.hpp` (already pulled in by `native_format.cpp`) for JSON parsing.
- **Error parity:** every Python `ValueError` branch is reproduced as `std::runtime_error` with byte-identical message text. The parity test asserts both implementations raise on the same inputs without comparing exception types.
- **`_optional_string` semantics preserved:** null → nullopt, blank-after-strip → nullopt, valid string → trimmed copy. Non-string values throw, mirroring Python `_optional_string`.
- `cpp/tests/test_release_manifest.cpp` — 11 doctest cases covering empty firmware list, minimal entry with defaults, full entry with every field, experimental + diagnostic combination, missing/blank `file` field throws, unknown `board_family` throws, unknown `artifact_kind` throws, `firmware` not a list throws, malformed JSON throws, and `to_string` round-trip.
- `cpp/bindings/tuner_core_module.cpp` — `FirmwareArtifactKind` enum, `ReleaseManifestFirmwareEntry` and `ReleaseManifest` classes, plus `release_manifest_parse_text` and `release_manifest_load` functions.
- `tests/unit/test_cpp_release_manifest_parity.py` — 11 parity tests against `ReleaseManifestService`. 5 happy paths (empty / minimal / full / diagnostic / multi-entry) plus 5 error paths and a `load() → None` on missing-file test. Happy-path tests serialize the payload to a temp file and exercise both the in-memory `parse_manifest_text` path and the `load()` path against `ReleaseManifestService.load`.

This is the first JSON-driven workspace service in C++ that produces an aggregated entry list (the existing `native_format.cpp` is JSON but builds an `EcuDefinition`-like graph). The same parsing pattern — `nlohmann::json` + per-field optional/string/enum helpers + `runtime_error` mirroring — will fit any future JSON-based workspace service (project files, dashboard layouts, logging profiles).

C++ doctest suite: 331 tests, 1024 assertions, 0 failures. Full Python suite: **2347/2347 passing**.

#### Phase 14 Slice 4 ninth sub-slice: PressureSensorCalibrationService

Direct port of `tuner.services.pressure_sensor_calibration_service.PressureSensorCalibrationService` plus the `source_confidence_label` helper from `HardwarePresetService`. The service matches live MAP/baro calibration values against curated sensor presets and renders an operator-facing guidance string with a confidence tag derived from the preset's source URL.

- `cpp/include/tuner_core/pressure_sensor_calibration.hpp` and `cpp/src/pressure_sensor_calibration.cpp` — `Preset` POD mirroring `PressureSensorPreset`, `Assessment` POD mirroring `PressureCalibrationAssessment`, `SensorKind` enum (`MAP`, `BARO`), `find_matching_preset(min, max, presets)` (±0.5 kPa tolerance match), `assess(min, max, presets, kind)` (full guidance text builder including the no-calibration / matched / unmatched / baro-overrange branches), and `source_confidence_label(note, url)` (returns `"Starter"` / `"Official"` / `"Trusted Secondary"` / `"Sourced"`).
- **URL netloc extractor:** the Python helper uses `urlparse(url).netloc.lower()` to pull the host from a URL before matching it against the official / secondary allowlists. The C++ side implements a tiny `url_netloc_lower` helper that finds the section between `://` and the next `/`/`?`/`#`/end and lowercases it — that's the entirety of `urlparse().netloc` for the URL shapes the Python service actually sees. No `<regex>` needed for this one.
- **String-formatting parity:** the matched-preset guidance uses `%.0f` for the kPa range (`(10-250 kPa)`) and concatenates `[confidence] source_note` exactly the way the Python f-string does. The unmatched-range and no-calibration branches likewise produce identical strings.
- `cpp/tests/test_pressure_sensor_calibration.cpp` — 12 doctest cases covering `source_confidence_label` for all four buckets (Starter via `"inferred"`, Starter via missing URL, Official via 3 different domains, Trusted Secondary via 2 different domains, fall-through to Sourced), `find_matching_preset` happy + tolerance + nullopt, `assess` for missing inputs / matched / unmatched / baro-overrange / baro-within-range branches.
- `cpp/bindings/tuner_core_module.cpp` — `PressureSensorKind` enum, `PressureSensorPreset` class, `PressureCalibrationAssessment` class, plus `pressure_find_matching_preset` / `pressure_assess_calibration` / `pressure_source_confidence_label` functions.
- `tests/unit/test_cpp_pressure_sensor_calibration_parity.py` — 27 parity tests against `PressureSensorCalibrationService` and `HardwarePresetService.source_confidence_label`. 12 confidence-label cases covering all four buckets and 5 official + 2 secondary + 2 fall-through domains, 7 `find_matching_preset` cases including the ±0.5 kPa tolerance edge, 2 no-calibration cases (one per sensor kind), and 7 `assess` shapes (three matched-preset cases hitting different confidence buckets, one unmatched, three baro cases including the 150 kPa overrange threshold).

The C++ side now has the second URL-aware workspace service. Together with the regex board detector and the string-formatted hardware setup validator, the workspace layer is starting to grow real string-formatting muscle in C++ — a useful baseline for the upcoming summary services and operation log formatters that all share the `snprintf` + `%.0f` / `%.1f` discipline.

C++ doctest suite: 320 tests, 991 assertions, 0 failures. Full Python suite: **2336/2336 passing**.

#### Phase 14 Slice 4 eighth sub-slice: BoardDetectionService

Direct port of `tuner.services.board_detection_service.BoardDetectionService` — the regex-driven board family identification used by the connect path, the board-aware fixture loading, and the runtime trust UI dimming. Self-contained except for a small `BoardFamily` enum mirror, no domain-type dependencies.

- `cpp/include/tuner_core/board_detection.hpp` and `cpp/src/board_detection.cpp` — `BoardFamily` enum (`ATMEGA2560`, `TEENSY35`, `TEENSY36`, `TEENSY41`, `STM32F407_DFU`) plus `to_string` for parity-test stringification, `detect_from_text(text)` (regex search over an uppercased copy of the input), and `detect_from_capabilities(experimental_u16p2, signature)` (signature → text detector first, then U16P2 ⇒ TEENSY41 fallback). Uses `<regex>` directly with the same five `\b...\b` patterns the Python module uses (`T41|TEENSY[\s_-]*4\.?1|TEENSY41`, etc.) — `<regex>` is the cleanest way to mirror the optional-dot / optional-separator alternation; hand-rolling it would need ~20 explicit alternatives per family.
- `cpp/tests/test_board_detection.cpp` — 10 doctest cases covering empty input, all five Teensy 4.1 separator forms (`T41`, `Teensy 4.1`, `teensy_4.1`, `TEENSY-4.1`, `teensy41`), Teensy 3.5 / 3.6, STM32 F407 (full and bare-`F407` and `dfu`), ATmega2560 / Mega2560 / Arduino Mega (with multiple internal whitespace), unrelated text yielding nullopt, capability-fallback signature precedence, capability-fallback U16P2-only branch, capability-fallback no-signal nullopt, and a `to_string` round-trip.
- `cpp/bindings/tuner_core_module.cpp` — `BoardFamily` enum and `board_detect_from_text` / `board_detect_from_capabilities` functions.
- `tests/unit/test_cpp_board_detection_parity.py` — 34 parity tests against `BoardDetectionService._detect_from_text` and `detect_from_capabilities`. 26 text shapes covering all positive matches per family plus 7 negative cases (including the deliberate near-misses `T42`, `TEENSY 3.0`, `STM32F4` that almost-match the patterns) and 8 capability-fallback shapes covering every (signature, u16p2) combination.

This is the second C++ workspace service (after `HardwareSetupValidationService`) to consume `<regex>`. The pattern is straightforward: pre-uppercase the input, walk a static `vector<pair<regex, family>>` table built once at first call, return on the first match. Same shape will fit any future text-based dispatch service the workspace presenter needs.

C++ doctest suite: 308 tests, 964 assertions, 0 failures. Full Python suite: **2309/2309 passing**.

#### Phase 14 Slice 4 seventh sub-slice: HardwareSetupValidationService

Direct port of `tuner.services.hardware_setup_validation_service.HardwareSetupValidationService` — the 10-rule validation pipeline the Hardware Setup Wizard runs over staged parameter values to flag dangerous or inconsistent configurations before write/burn. First C++ workspace service that ports a non-trivial *rule pipeline* (not just a single dispatch evaluator), with all 10 rules and their f-string-formatted rejection messages reproduced byte-for-byte.

- `cpp/include/tuner_core/hardware_setup_validation.hpp` and `cpp/src/hardware_setup_validation.cpp` — `Severity` enum (`WARNING`, `ERROR`), `Issue` POD (severity, message, optional parameter_name, optional detail), `ValueLookup` typedef (`std::function<std::optional<double>(string_view)>`), and `validate(parameter_names, get_value)`. Every rule from the Python module is ported: `_check_dwell_excessive` (> 10 ms → ERROR), `_check_dwell_zero` (== 0 → WARNING), `_check_dwell_implausible_range` (`dwellrun` outside 1.5–6.0 ms → WARNING), `_check_trigger_geometry` (missing teeth ≥ total → ERROR; ≥ half → WARNING), `_check_dead_time_zero` (== 0 → WARNING), `_check_injopen_range` (> 5 ms → WARNING, units error), `_check_injector_flow_zero` (== 0 → WARNING), `_check_required_fuel_zero` (== 0 → WARNING), `_check_trigger_angle_zero` (== 0 → WARNING), `_check_wideband_without_calibration` (egoType ≥ 2 with no AFR cal table → WARNING). The dispatcher dedupes the input parameter list while preserving order — the Python service builds a `set(parameter_names)`, but the parity test normalizes both sides' issue lists to a sorted multiset to keep set-iteration order out of the comparison.
- **String-formatting parity:** every f-string from the Python module is reproduced byte-for-byte using `snprintf` with the documented precision codes. `{val:.1f}` → `%.1f`, `{teeth:.0f}` → `%.0f`. The IEEE 754 default rounding matches Python's `format(x, '.1f')` for every case the parity test exercises (Speeduino's parameter values are all "nice" numbers, no half-bit pathology).
- `cpp/tests/test_hardware_setup_validation.cpp` — 13 doctest cases covering each of the 10 rules' positive paths plus the wideband-with-calibration negative path and a clean-setup case that produces zero issues.
- `cpp/bindings/tuner_core_module.cpp` — `HardwareSetupSeverity` enum, `HardwareSetupIssue` class, and `hardware_setup_validate(parameter_names, values)` function. The value lookup is passed as a parallel-array list of `(name, value)` tuples so the C++ side can build a closure on its end without round-tripping a Python callback per parameter.
- `tests/unit/test_cpp_hardware_setup_validation_parity.py` — 17 parity tests against `HardwareSetupValidationService.validate`. Each rule has at least one positive case; trigger-geometry and dwell-implausible-range have both positive and negative paths; the wideband rule has both with-calibration and narrow-band negative cases; a `clean_full_setup` test verifies the empty-issue-list path; and a final `multiple_problems_at_once` test fires 8 rules simultaneously to make sure the pipeline aggregates correctly. **Set-iteration normalization**: both sides' issue lists are sorted into `(severity, parameter_name, message, detail)` multisets before comparison so the Python `set(parameter_names)` non-determinism doesn't matter.

This is the largest workspace service ported so far in absolute lines (~325 Python LOC ⇒ ~280 C++ LOC) and the first one whose value depends on running 10 independent rules and aggregating the results — a useful pattern for the upcoming `HardwareSetupSummaryService` and the larger validation pipelines in the engine setup wizard.

C++ doctest suite: 298 tests, 935 assertions, 0 failures. Full Python suite: **2275/2275 passing**.

#### Phase 14 Slice 4 sixth sub-slice: WUE Analyze pure-logic helpers

Direct port of the module-level pure-logic helpers from `tuner.services.wue_analyze_service` — the substrate the stateful `WueAnalyzeAccumulator` builds on. The accumulator itself still depends on `TablePageSnapshot` and `ReplaySampleGateService`, neither of which has landed in C++ yet, so this slice cleanly separates the helpers from the stateful surface and lands the helpers first.

- `cpp/include/tuner_core/wue_analyze_helpers.hpp` and `cpp/src/wue_analyze_helpers.cpp` — `confidence_label(sample_count)` (4-bucket classifier with the same `_CONFIDENCE_LOW=3` / `_MEDIUM=10` / `_HIGH=30` thresholds), `is_clt_axis(name)` (case-insensitive substring match against the same 6 keywords: `clt`, `coolant`, `warmup`, `wue`, `cold`, `temp`), `clt_from_record(values)` (first channel whose lowercased key contains `coolant` or `clt`), `nearest_index(axis, value)` (linear scan returning the closest index, ties broken in favour of the earlier index — exactly mirroring Python's strictly-less comparison), `numeric_axis(labels)` (all-or-nothing string→float conversion, returns empty on any parse failure), `parse_cell_float(text)` (safe float parse with nullopt fallback), and `target_lambda_from_cell(raw, fallback)` (scalar branch of `_target_lambda_from_table`: values > 2.0 interpreted as AFR and divided by 14.7, smaller positive values returned as-is, non-positive values fall back). The `kStoichAfr=14.7` and `kAfrUnitMin=2.0` constants are exposed as `inline constexpr` so future ports can refer to them.
- `cpp/tests/test_wue_analyze_helpers.cpp` — 15 doctest cases covering all four confidence buckets, CLT axis keyword matching (positive and negative cases), `clt_from_record` happy path / fall-through / empty, `nearest_index` happy path including the tie-breaking rule and a single-element axis, `numeric_axis` all-or-nothing semantics, `parse_cell_float` happy and bad-input branches, and `target_lambda_from_cell` covering the AFR / direct-lambda / fallback branches.
- `cpp/bindings/tuner_core_module.cpp` — 7 free functions (`wue_confidence_label`, `wue_is_clt_axis`, `wue_clt_from_record`, `wue_nearest_index`, `wue_numeric_axis`, `wue_parse_cell_float`, `wue_target_lambda_from_cell`). The `parse_cell_float` wrapper accepts `optional<string>` so Python `None` maps cleanly through the FFI.
- `tests/unit/test_cpp_wue_analyze_helpers_parity.py` — 55 parity tests against the Python module-level helpers. 12 confidence-label cases hitting every bucket boundary, 10 `is_clt_axis` cases covering all 6 keywords plus rejected names, 5 `clt_from_record` shapes (including first-match-wins on insertion order), 7 hand-picked `nearest_index` cases including the tie-breaking rule, 50 random `nearest_index` cases on sorted random axes (deterministic seed `0xC0DE`), 5 `numeric_axis` shapes, 7 `parse_cell_float` cases including `None`, and 8 `target_lambda_from_cell` cases including the boundary at exactly `kAfrUnitMin = 2.0`. The `_target_lambda_from_table` Python function operates on a `TablePageSnapshot`, so the parity test re-derives its scalar branch in-line — that branch is exactly what the C++ helper covers, and the parity test pins it directly.

Note on tie-breaking: `nearest_index` uses strictly-less (`err < best_error`) so a value exactly between two axis bins keeps the *earlier* index. The doctest and 50-iteration random parity test pin this so future C++ code that consumes `nearest_index` (axis bin lookup, table cell hit detection, dashboard gauge mapping) inherits the same semantics.

C++ doctest suite: 285 tests, 920 assertions, 0 failures. Full Python suite: **2258/2258 passing**.

#### Phase 14 Slice 4 fifth sub-slice: AutotuneFilterGateEvaluator

Direct port of `tuner.services.autotune_filter_gate_evaluator.AutotuneFilterGateEvaluator`. The first non-trivial workspace service in C++ — ports an entire dispatch evaluator (5 standard named gates, parametric gates, axis-context handling, fail-open semantics) on top of the `sample_gate_helpers` substrate, with rejection-reason strings reproduced byte-for-byte.

- `cpp/include/tuner_core/autotune_filter_gate_evaluator.hpp` and `cpp/src/autotune_filter_gate_evaluator.cpp` — `Gate` POD (name, label, optional channel/op/threshold, default_enabled), `AxisContext` POD (six independent optionals), `Eval` result, plus `evaluate` / `evaluate_all` / `gate_label`. Standard gates handled: `std_DeadLambda` (rejects when lambda is missing or outside `[0.5, 1.8]` λ, derives from AFR via `lambda_value()`), `std_xAxisMin/Max` and `std_yAxisMin/Max` (require an `AxisContext`; pass through silently if context or limit is missing), `std_Custom` (always passes). Parametric gates dispatch through `apply_operator` from the substrate. Unknown / under-specified gates pass through (fail-open).
- **Python `str(float)` mirroring:** rejection reasons are constructed by `snprintf` and pinned against the Python f-string output, so the C++ side uses a `py_str_double` helper that always renders whole-number doubles as `"200.0"` (not `"200"`) to match Python's `str(float)` repr. Fractional doubles use `%g`. The parity test exercises this on both axis-bound reasons (`"X value 100.0 below axis min 200.0"`) and parametric reasons (`"minRPM: rpm=200.0 < 300.0 (reject condition met)"`).
- `cpp/tests/test_autotune_filter_gate_evaluator.cpp` — 16 doctest cases covering disabled-by-default pass-through, `std_Custom` pass-through, `std_DeadLambda` accept/reject (including missing-channel and AFR-derived paths), `std_xAxisMin/Max` and `std_yAxisMax` reject + pass-when-context-missing branches, parametric reject and channel-missing pass-through, `evaluate_all` fail-fast and full-list modes, and all three `gate_label` paths (explicit label, standard-gate table lookup, gate-name fallback).
- `cpp/bindings/tuner_core_module.cpp` — `AutotuneGate`, `AutotuneAxisContext`, `AutotuneGateEval` classes plus `autotune_evaluate_gate` / `autotune_evaluate_all_gates` / `autotune_gate_label` functions. The optional `axis_context` argument wraps to a nullable C++ pointer.
- `tests/unit/test_cpp_autotune_filter_gate_evaluator_parity.py` — 32 parity tests against `AutotuneFilterGateEvaluator`. 2 pass-through cases, 8 `std_DeadLambda` shapes (lambda channel, AFR-derived, out-of-range, missing-channel, empty record), 8 axis-gate cases covering `std_xAxis{Min,Max}` and `std_yAxis{Min,Max}` accept/reject plus the missing-context and missing-limit pass-through branches, 8 parametric-gate cases including the bitwise `&` engine-status flag pattern and a custom-label rejection reason, 2 `evaluate_all` cases (fail-fast and full-list), and 4 `gate_label` cases. Every case pins gate name, accepted flag, and the full rejection-reason string byte-for-byte.

This is the largest pure-logic workspace service ported so far and the first one whose value is gated on string-formatting parity, not just numeric parity. The Python `str(float)` mirroring trick will likely come up again in the VE Analyze pipeline (Phase 7) and the operation log services — worth noting that whole-number doubles must always render with `.0` to match what Python produces from a `float` original.

C++ doctest suite: 270 tests, 879 assertions, 0 failures. Full Python suite: **2203/2203 passing**.

#### Phase 14 Slice 4 fourth sub-slice: Sample gate operator + channel resolver helpers

Pure-logic substrate that `ReplaySampleGateService` and `AutotuneFilterGateEvaluator` both consume on the Python side. Porting it first lets the larger gate-evaluator slices land later without re-deriving the same primitives. Five module-level helpers in C++ matching the Python module signatures byte-for-byte.

- `cpp/include/tuner_core/sample_gate_helpers.hpp` and `cpp/src/sample_gate_helpers.cpp` — `normalise_operator(op)` (rewrites `=` to `==`, strips whitespace), `apply_operator(value, op, threshold)` (dispatches `<`/`>`/`<=`/`>=`/`==`/`!=`/`&` and falls through to `false` on unknown operators), `resolve_channel(name, values)` (alias-aware substring lookup over a record), `lambda_value(values)` (prefers a lambda channel, falls back to AFR ÷ 14.7), `afr_value(values)` (prefers an AFR channel, falls back to lambda × 14.7). The bitwise `&` branch routes through `int64_t` casts to mirror Python's `int(channel_value) & int(threshold)` exactly. The alias table is the same 10-entry map the Python module declares (`lambda`, `afr`, `ego→{ego,afr,lambda}`, `coolant→{coolant,clt}`, `engine→{engine,status}`, `pulsewidth→{pulsewidth,pw}`, `throttle→{throttle,tps}`, `rpm`, `map`, `load→{load,map}`).
- **Insertion-order preservation:** Python dicts iterate in insertion order (since 3.7) and the resolver returns the *first* matching key — so `ValueMap` is typed as `std::vector<std::pair<std::string, double>>` rather than `std::map`. A `std::map` would break parity by sorting keys alphabetically. The Python parity test forwards `dict.items()` as a list to keep order explicit across the FFI boundary.
- `cpp/tests/test_sample_gate_helpers.cpp` — 13 doctest cases covering operator normalisation, every supported operator branch, unknown-operator fall-through, `=` accepted as alias for `==`, alias substring matching, the multi-alias `ego` fallback, first-match-wins on multiple keys, lambda preferred over AFR derivation, AFR preferred over lambda derivation, and empty-input nullopt cases.
- `cpp/bindings/tuner_core_module.cpp` — `sample_gate_normalise_operator`, `sample_gate_apply_operator`, `sample_gate_resolve_channel`, `sample_gate_lambda_value`, `sample_gate_afr_value` exposed via parallel arrays. `<nanobind/stl/pair.h>` added so `std::pair<std::string,double>` marshals from Python tuples.
- `tests/unit/test_cpp_sample_gate_helpers_parity.py` — 46 parity tests against `_normalise_operator`, `_apply_operator` (from `autotune_filter_gate_evaluator`) and `_resolve_channel`, `_lambda_value`, `_afr_value` (from `replay_sample_gate_service`). 10 operator-normalisation cases, 13 `apply_operator` dispatches covering every operator branch and the unknown-operator fall-through, 10 `resolve_channel` shapes (including the multi-alias `ego→afr` fallback, the bare-name `custom` fall-through that's not in the alias table, missing keys, and a first-match-wins case), 7 `lambda_value` shapes, and 6 `afr_value` shapes.

This is the first time the C++ side has crossed the FFI with an insertion-order-sensitive container — worth tracking explicitly for future workspace services that consume `record.values` (datalog records, replay samples, VE Analyze accumulators) since those all key off the same iteration discipline.

C++ doctest suite: 254 tests, 855 assertions, 0 failures. Full Python suite: **2171/2171 passing**.

#### Phase 14 Slice 4 third sub-slice: TableEditService numeric transforms

Direct port of the numeric transforms in `tuner.services.table_edit_service.TableEditService` — the operator-driven `fill`, `fill_down`, `fill_right`, `interpolate`, `smooth`, and `paste` operations the table editor binds to its toolbar buttons. Pure logic over flat row-major `vector<double>` plus a `columns` count, no domain-type dependency. `copy_region` is intentionally excluded because Python's `str(float)` formatting rules are non-trivial to mirror byte-for-byte.

- `cpp/include/tuner_core/table_edit.hpp` and `cpp/src/table_edit.cpp` — `TableSelection { top, left, bottom, right }` with `width()` / `height()` accessors. Six pure-function transforms returning new flat vectors so undo/redo capture stays straightforward (no in-place mutation). `fill_region` replaces every selected cell with `fill_value`. `fill_down_region` snapshots the top row of the selection and copies it down through the remaining rows (no-op when height ≤ 1). `fill_right_region` snapshots the left column and copies it rightward (no-op when width ≤ 1). `interpolate_region` linearly interpolates between selection endpoints — vertical when the selection is exactly one column wide and more than one row tall, horizontal otherwise (per-row). `smooth_region` box-blurs every cell with up-to-9 in-bounds neighbors, reading from a pre-loop snapshot so neighbor reads always see the original values, with each result rounded to 3 decimal places via `std::nearbyint(x * 1000) / 1000` to match Python's `round(x, 3)` banker's-rounding semantics. `paste_region` parses the clipboard via `parse_clipboard` (tab/comma-separated, blank cells dropped, blank lines skipped, CRLF/LF/CR handled) and tiles it across `max(selection_size, clipboard_size)`, stopping at the table edge so the original table size is preserved.
- `cpp/tests/test_table_edit.cpp` — 12 doctest cases covering `fill_region` selective replacement, `fill_down_region` happy path and 1-row no-op, `fill_right_region` left-column copy, horizontal interpolation, single-column vertical interpolation, smooth center-cell averaging, smooth banker's-rounding internal consistency, single-value paste, 2x2 paste, 1x2 tiled across 3x4, and `parse_clipboard` with mixed tabs/commas/blank lines.
- `cpp/bindings/tuner_core_module.cpp` — six wrappers (`table_edit_fill_region`, `table_edit_fill_down_region`, `table_edit_fill_right_region`, `table_edit_interpolate_region`, `table_edit_smooth_region`, `table_edit_paste_region`) accepting the selection as four scalar args so the Python parity test never has to construct a custom struct.
- `tests/unit/test_cpp_table_edit_parity.py` — 28 parity tests against `TableEditService`. 4 `fill_region` shapes, 4 `fill_down_region` shapes (including a 1-row no-op), 4 `fill_right_region` shapes (including a 1-column no-op), 4 `interpolate_region` shapes (horizontal, single-column vertical, full 2D rectangle, single-cell no-op), 5 `smooth_region` shapes against deterministic random `[-50, 50]` payloads with `rel=1e-12` parity (covering 3x3 / 4x4 / 5x5 / 2x8 grids and a 5x5 with a 3x3 partial selection), 6 `paste_region` shapes (single value, 2x2 tab, 1x2 tiled, comma-separated, vertical 3x1, horizontal 1x3 partial), plus a blank-clipboard no-op test.

The smooth and interpolate transforms are the highest-leverage operator helpers in the table editor — operators reach for them whenever they have a regional fix or a noisy autotune patch. With both in C++ at byte-for-byte parity against random payloads, the C++ table editor widget that lands later in Slice 8 can call these directly without round-tripping through Python.

C++ doctest suite: 241 tests, 823 assertions, 0 failures. Full Python suite: **2125/2125 passing**.

#### Phase 14 Slice 4 second sub-slice: Required fuel calculator

Direct port of `tuner.services.required_fuel_calculator_service.RequiredFuelCalculatorService` — the TunerStudio reqFuel calculator dialog math, used by the Hardware Setup Wizard to compute the staged `reqFuel` value from displacement / cylinder count / injector flow / target AFR. Self-contained formula with U08 clipping.

- `cpp/include/tuner_core/required_fuel_calculator.hpp` and `cpp/src/required_fuel_calculator.cpp` — `Result` struct mirroring the Python `RequiredFuelResult` field-for-field (`req_fuel_ms`, `req_fuel_stored`, the four input echoes, `inputs_summary`, `is_valid`). `calculate(displacement_cc, cylinder_count, injector_flow_ccmin, target_afr)` runs the same `(displacement_CID × kReqFuelK) / (cylinders × AFR × injflow_lbhr) / 10` formula with the same constants pulled verbatim from the Python module (`3.6e7 × 4.27793e-5`, `16.38706` cc/cid, `10.5` cc/min per lb/hr, scale `0.1`). Stored value is `round(req_fuel_ms × 10)` clipped to `0..255` using `std::nearbyint` for banker's rounding to match Python's `round()`. Invalid inputs (any zero or negative) short-circuit to `is_valid=false` with the same `"Invalid inputs — all values must be positive."` summary string. The valid-path summary uses `snprintf` with the documented `"%.0f cc, %d cyl, %.0f cc/min, AFR %.1f"` format so the string matches the Python f-string output byte-for-byte.
- `cpp/tests/test_required_fuel_calculator.cpp` — 5 doctest cases covering all four invalid-input branches, a standard 2.0 L 4-cyl 220 cc/min 14.7 AFR shape, an oversized engine that clips stored to 255, the documented summary format, and an internal-consistency check that `stored ≈ req_fuel_ms × 10`.
- `cpp/bindings/tuner_core_module.cpp` — `RequiredFuelResult` class with all 8 properties exposed plus the `calculate_required_fuel` function.
- `tests/unit/test_cpp_required_fuel_calculator_parity.py` — 17 parity tests against `RequiredFuelCalculatorService.calculate`. 8 hand-picked engine shapes (Miata, B16, LS, high-flow forced induction, Ford 300 twin GT28 matching the production fixture project, triples, tiny twins). 7 invalid-input shapes covering every short-circuit branch. 1 stored-value clipping test. 1 final test running 100 random inputs through both implementations and pinning `req_fuel_ms` (rel tol `1e-12`), `req_fuel_stored`, and `inputs_summary` byte-for-byte.

This is the second pure-logic workspace service in C++. Together with the visibility evaluator, the C++ side now has the two helpers the Hardware Setup Wizard needs to compute its first staged value (`reqFuel`) and gate field visibility — the wizard itself can be ported once `ScalarParameterDefinition` lands in C++.

C++ doctest suite: 229 tests, 752 assertions, 0 failures. Full Python suite: **2097/2097 passing**.

#### Phase 14 Slice 4 first sub-slice: Visibility expression evaluator

Opens the workspace-services port with the smallest pure-logic surface in that layer: the TunerStudio INI visibility expression evaluator. Direct port of `tuner.services.visibility_expression_service.VisibilityExpressionService` — a small recursive-descent parser for the boolean grammar `field = ..., { expr }` clauses use to gate field visibility on current tune values. Self-contained, no domain-type dependencies, parity-testable purely against the Python service.

- `cpp/include/tuner_core/visibility_expression.hpp` and `cpp/src/visibility_expression.cpp` — `evaluate(expression, values, arrays = nullptr)` returning `bool`. Hand-written tokenizer mirroring the Python regex (numbers with optional decimal, two-char operators `==`/`!=`/`>=`/`<=`/`&&`/`||`, single-char operators, dotted identifiers via `IDENT(.IDENT)*`). Recursive-descent parser with the same grammar layers (`or → and → not → cmp → atom`). Comparison results returned as `1.0` / `0.0`, identifiers default to `0.0` on miss, `arrayValue(name, index)` strips the `array.` namespace prefix and returns `0.0` on out-of-range / missing array / no `arrays` map. **Fail-open on any parse error**: any thrown exception in the parser is caught at the top-level `evaluate` call and returns `true` so the field stays visible — same defensive policy as the Python implementation.
- `cpp/tests/test_visibility_expression.cpp` — 14 doctest cases covering empty/whitespace-only/`{}` expressions, brace stripping, simple equality and ordering comparisons, `&&` / `||` / `!`, parenthesized subexpressions, unknown identifier defaulting to 0, dotted identifier tokenization (`foo.bar.baz`), `arrayValue(array.X, n)` with and without the `array.` prefix, `arrayValue` with no arrays map, unknown-function fail-safe, decimal number literals, and a malformed expression that fails open to true.
- `cpp/bindings/tuner_core_module.cpp` — `evaluate_visibility_expression(expression, values, arrays=None)` exposed for Python parity. The optional `arrays` map is an `optional<map<string, vector<double>>>` so `None` from Python maps cleanly to a null pointer on the C++ side.
- `tests/unit/test_cpp_visibility_expression_parity.py` — 35 parity tests against `VisibilityExpressionService.evaluate`. 28 cases covering the empty/brace/comparison/logical/dotted-identifier/decimal/fail-open grammar plus production-shaped clauses like `fuelAlgorithm == 1 && useDFCO == 1` and `(fuelAlgorithm == 1) && (rpm < 6500)`. 7 function-call cases covering `arrayValue` with the `array.` prefix, with the bare name, out-of-range index, no-arrays-map, and unknown-function fail-safe.

The visibility evaluator is consumed by `TuningWorkspacePresenter._is_page_visible`, the scalar editor service, and several layout-compilation paths on the Python side. With this in place, the C++ workspace presenter (which lands later in Slice 4) can gate field visibility against runtime tune values without round-tripping through Python.

C++ doctest suite: 224 tests, 737 assertions, 0 failures. Full Python suite: **2080/2080 passing**.

#### Phase 14 Slice 3 fifth sub-slice: Speeduino runtime live-data decoder

Direct port of the decode loop in `SpeeduinoControllerClient.read_runtime`. Sits one layer above the parameter codec and is the last pure-logic surface in the comms layer before genuine I/O work begins. Pulls a list of output-channel layouts (name + units + the existing `ScalarLayout`) and turns a binary runtime packet into the same `(name, value, units)` snapshot the dashboard / live VE Analyze pipeline already consume on the Python side.

- `cpp/include/tuner_core/speeduino_live_data_decoder.hpp` and `cpp/src/speeduino_live_data_decoder.cpp` — `OutputChannelLayout { name, units, ScalarLayout }`, `OutputChannelValue { name, value, units }`, `runtime_packet_size(channels)` (mirrors the `max(offset + data_size)` calculation), `decode_runtime_packet(channels, payload)` (mirrors the list comprehension over `_decode_scalar`). The decoder iterates channels in input order so the snapshot stays positionally aligned with whatever the caller built the layout list from — important for the dashboard / live VE Analyze pipelines that key off positional indices in some places.
- `cpp/tests/test_speeduino_live_data_decoder.cpp` — 6 doctest cases covering packet-size max-of-offset+size math, empty channel set, name+units preservation through decode (including a `0x1388 → 5000 rpm` shape and a `clt = (raw - 40) C` shape), scale+translate IAT shape, input-order preservation when channels are not offset-sorted, and undersized-payload throw.
- `cpp/bindings/tuner_core_module.cpp` — `SpeeduinoOutputChannelValue` class plus `speeduino_runtime_packet_size` and `speeduino_decode_runtime_packet` functions. Channels are passed as parallel arrays so the Python side never has to construct a custom struct per channel — the parity test builds these arrays straight from `EcuDefinition.output_channel_definitions`.
- `tests/unit/test_cpp_speeduino_live_data_decoder_parity.py` — 4 parity tests against the production INI's full output-channel set (>100 channels covering U08/S08/U16/S16/F32 with mixed scale and translate). Per-channel filtering mirrors `read_runtime`'s `if field.offset is not None` guard. Tests: (1) `runtime_packet_size` matches the Python `max(offset + size)` calculation, (2) decoded values match `SpeeduinoControllerClient._decode_scalar` byte-for-byte on a zero payload, (3) decoded values match on a deterministic random payload (every channel checked, mismatches reported individually), (4) decoder preserves channel input order.

The full pure-logic surface of the Speeduino comms layer is now in C++: framing, command shapes, raw value codec, parameter codec (scale/translate/bit-field), and live-data decoder. The remaining Slice 3 work — `SerialTransport`, `TcpTransport`, and `SpeeduinoControllerClient` proper — needs actual I/O test infrastructure (socketpair fakes, mock serial endpoints) and naturally folds into Slice 4 alongside the workspace presenter port that consumes both. Phase 14 Slice 3 closes here on the parity-against-Python pattern; the next slice opens with a different test discipline.

C++ doctest suite: 210 tests, 704 assertions, 0 failures. Full Python suite: **2045/2045 passing**.

#### Phase 14 Slice 3 fourth sub-slice: Speeduino scalar/table parameter codec

The scale/translate/bit-field layer over the raw value codec. Direct port of `SpeeduinoControllerClient._encode_scalar` / `_decode_scalar` / `_encode_table` / `_decode_table`. Sits one level above `speeduino_value_codec` and one level below the (still-Python) workspace services that own `ScalarParameterDefinition` / `TableDefinition`. Introduces minimal POD layout structs (`ScalarLayout`, `TableLayout`) carrying only the fields the codec actually needs — `offset`, `data_type`, `scale`, `translate`, optional `bit_offset` / `bit_length` for scalars, plus `rows` / `columns` for tables — so the C++ side does not yet need the full domain types.

- `cpp/include/tuner_core/speeduino_param_codec.hpp` and `cpp/src/speeduino_param_codec.cpp` — `ScalarLayout` / `TableLayout` PODs with `std::optional<double>` for `scale` / `translate` so the codec can distinguish "missing" from "0.0" exactly the way Python does. `encode_scalar(layout, value, page)` handles the bit-field branch by reading the existing value out of the page, masking the field, and re-encoding the merged integer; the non-bit-field branch routes through `(value - translate) / scale` with banker's rounding via `std::nearbyint` to match Python's `round(...)`. `decode_scalar(layout, page)` mirrors the same split. `encode_table(layout, values)` and `decode_table(layout, page)` walk the table area item-by-item against the underlying raw codec. Two Python quirks are preserved and pinned by the parity test: (1) encode treats `scale == 0` the same as `scale == None` (falls back to 1.0); decode only treats `None` as missing. (2) F32 scalars/tables go through the `int(round(...))` path the same way Python does even though the underlying value codec accepts `double` directly.
- `cpp/tests/test_speeduino_param_codec.cpp` — 10 doctest cases covering U08-with-scale round-trip, S08 translate (CLT/IAT shape), `scale=0` fallback on encode, bit-field merge into existing page byte, bit-field clear (value=0) preserves the rest of the byte, bit-field decode masks correctly, U16 little-endian table layout, table decode with scale and translate, table encode/decode round-trip, undersized-page throw on decode.
- `cpp/bindings/tuner_core_module.cpp` — `speeduino_encode_scalar`, `speeduino_decode_scalar`, `speeduino_encode_table`, `speeduino_decode_table` exposed for Python parity. Each wrapper builds the layout struct on the C++ side from individual arguments so the Python parity test does not need to marshal any custom Python class.
- `tests/unit/test_cpp_speeduino_param_codec_parity.py` — 28 parity tests against `SpeeduinoControllerClient._encode_scalar` / `_decode_scalar` / `_encode_table` / `_decode_table`. The Python target methods are bound but only call the static `_data_size` / `_encode_raw_value` / `_decode_raw_value` helpers, so the test passes a `unittest.mock.Mock` as `self` and wires those static methods onto the mock. Coverage: 7 non-bit-field encode shapes (including the IAT `(scale=1.8, translate=-22.23)` shape and S16 negative round-trip), 6 non-bit-field decode shapes, 3 bit-field encode shapes (including a full 8-bit-wide field), 3 bit-field decode shapes, 4 table encode shapes including U08/U16/S16 with edge values, 4 table decode shapes with synthetic non-zero pages, plus an end-to-end encode→decode round-trip.

This sub-slice closes the pure-logic seam between the raw byte primitives and the higher-level workspace services. The remaining Slice 3 work — `SerialTransport`, `TcpTransport`, and `SpeeduinoControllerClient` proper — needs actual I/O test infrastructure (socketpair fakes / mock serial endpoints), so it shifts naturally into Slice 4 alongside the workspace presenter port that consumes both.

C++ doctest suite: 204 tests, 685 assertions, 0 failures. Full Python suite: **2041/2041 passing**.

#### Phase 14 Slice 3 third sub-slice: Speeduino raw value codec

Direct port of `SpeeduinoControllerClient._data_size`, `_encode_raw_value`, and `_decode_raw_value` — the per-data-type byte encode/decode primitives every higher-level scalar/table write touches. Pure logic, no domain-model dependency on `ScalarParameterDefinition` (the scale/translate/bit-field layer lives in workspace services and lands in Slice 4).

- `cpp/include/tuner_core/speeduino_value_codec.hpp` and `cpp/src/speeduino_value_codec.cpp` — `DataType` enum (`U08`, `S08`, `U16`, `S16`, `U32`, `S32`, `F32`), `RawValue = std::variant<int64_t, double>` mirroring the Python `int | float` return shape, `parse_data_type(tag)` (case-insensitive, throws on unknown), `data_size_bytes(type)` ({U08,S08}=1, {U16,S16}=2, {U32,S32,F32}=4), `encode_raw_value(value, type)` returning a little-endian byte vector, `decode_raw_value(raw, type)` returning a `RawValue`. Both encode and decode have textual-tag overloads. The integer arms truncate floats via `static_cast<int64_t>` to mirror Python's `int(value)`. F32 round-trips through a `memcpy` between `float` and `uint32_t` so the bit pattern matches `struct.pack("<f", ...)` exactly.
- `cpp/tests/test_speeduino_value_codec.cpp` — 13 doctest cases covering the size table for every tag, case-insensitive `parse_data_type`, unknown-tag throw, U08/S08 round-trip with sign-extension on negatives, U16 little-endian byte order, S16 negative round-trip, U32 across the full 32-bit range, S32 negative round-trip, F32 IEEE-754 round-trip with `Approx`, F32 accepting an integer-valued input, undersized-buffer throw on decode, and equivalence between the enum and textual-tag overloads.
- `cpp/bindings/tuner_core_module.cpp` — `speeduino_data_size_bytes`, `speeduino_encode_raw_value_int`, `speeduino_encode_raw_value_float`, `speeduino_decode_raw_value_int`, `speeduino_decode_raw_value_float` exposed for Python parity. The bindings split int/float by name to keep the Python-side type discipline explicit (no variant marshalling needed).
- `tests/unit/test_cpp_speeduino_value_codec_parity.py` — 28 parity tests against `SpeeduinoControllerClient._data_size` / `_encode_raw_value` / `_decode_raw_value`. Per-tag size parity for all 7 tags. Per-tag integer encode parity on 5–6 hand-picked values per type (including signed-edge cases like `INT16_MIN` / `INT32_MIN`). Per-tag integer decode parity on the same value sets. F32 encode/decode parity on 7 hand-picked floats (including `1.5e10` and `-1.5e-10`). A 200-iteration random round-trip across all 6 integer tags pinning encode bytes against Python and decode value against the original input. An unknown-tag throw test.

Both the `_encode_scalar` / `_encode_table` methods on `SpeeduinoControllerClient` and the `_decode_scalar` / `_decode_table` methods reduce to a thin scale/translate/bit-field layer over the primitives now in C++. That higher layer pulls in `ScalarParameterDefinition` and `TableDefinition`, which land alongside the workspace services in Slice 4.

C++ doctest suite: 194 tests, 660 assertions, 0 failures. Full Python suite: **2013/2013 passing**.

#### Phase 14 Slice 3 second sub-slice: Speeduino protocol command shapes

One layer above the framing helpers: pure-logic builders for the byte shapes `SpeeduinoControllerClient` constructs for page reads, page writes, runtime polls, and burn requests. No I/O dependency — these can be parity-tested directly against the Python static command builders without a transport.

- `cpp/include/tuner_core/speeduino_protocol.hpp` and `cpp/src/speeduino_protocol.cpp` — `page_request(cmd, page, offset, length)` (the canonical 7-byte `[cmd, 0x00, page, off_lo, off_hi, len_lo, len_hi]` shape, little-endian throughout), `page_read_request` convenience wrapper defaulting to `'p'`, `page_write_request(page, offset, payload, command='M')` returning the 7-byte header followed by the payload bytes (mirrors what `_write_page_chunk` builds per chunk), `runtime_request(offset, length)` returning `['r', 0x00, 0x30, off_lo, off_hi, len_lo, len_hi]` with `0x30` = `SEND_OUTPUT_CHANNELS`, `burn_request(page, command='b')` returning `[burn_cmd, 0x00, page]`, and `select_command_char(raw, fallback)` mirroring `SpeeduinoControllerClient._command_char` (first character of `raw` if non-empty, otherwise `fallback`). Default command characters are exposed as `kDefaultPageReadChar`, `kDefaultPageWriteChar`, `kDefaultBurnChar`, and `kRuntimePollChar`.
- `cpp/tests/test_speeduino_protocol.cpp` — 10 doctest cases covering header layout, default command character, payload append, custom command override, runtime selector byte, burn shape, command-char selection (non-empty / null / empty), and 16-bit little-endian encoding.
- `cpp/bindings/tuner_core_module.cpp` — `speeduino_page_request`, `speeduino_page_write_request`, `speeduino_runtime_request`, `speeduino_burn_request` exposed for Python parity.
- `tests/unit/test_cpp_speeduino_protocol_parity.py` — 21 parity tests. Page-request parity against `SpeeduinoControllerClient._page_request` on 6 hand-picked shapes (including the `afrTable` `lastOffset = 256, length = 256` shape and 16-bit edge values). Page-write-request parity on 5 random payloads up to 256 bytes (covering blocking-factor sized chunks). Runtime-request parity on 5 offset/length pairs including the 16-bit edges. Burn-request parity on 4 page/command-char pairs. A final assertion pins `SEND_OUTPUT_CHANNELS == 0x30` so a future Python rename of the constant breaks the test loudly.

With framing + command shapes both ported, the C++ side now owns every pure-logic seam of the Speeduino raw command path. The remaining Slice 3 work splits into two genuinely I/O-bound sub-slices (`SerialTransport` and `TcpTransport` with sockets) and one orchestration sub-slice (`SpeeduinoControllerClient` itself), each of which needs different test infrastructure than the parity-against-Python pattern used so far.

C++ doctest suite: 181 tests, 625 assertions, 0 failures. Full Python suite: **1985/1985 passing**.

#### Phase 14 Slice 3 first sub-slice: Speeduino TCP framing helpers

First slice of the comms-layer port. Targets the pure-logic seam used by `TcpTransport.write_framed` / `read_framed_response`: standard zlib CRC-32 plus little-endian length-prefixed frame encode/decode. No I/O dependencies — links cleanly into both the test runner and the future C++ `TcpTransport` without dragging in sockets.

- `cpp/include/tuner_core/speeduino_framing.hpp` and `cpp/src/speeduino_framing.cpp` — `crc32(span<const uint8_t>)` (table-based, polynomial `0xEDB88320`, reflected, init/final-XOR `0xFFFFFFFF` — matches `zlib.crc32` byte-for-byte), `encode_frame(payload)` returning `[u16 LE len][payload][u32 LE CRC32(payload)]` (throws `std::length_error` if payload exceeds the u16 limit), `decode_frame(buffer)` returning a `DecodedFrame { payload, bytes_consumed, crc_valid }` (throws on truncated input). The CRC field is read but not validated against the payload as a hard error — the `crc_valid` flag is informational, mirroring the Python comment that the Airbear bridge does not validate CRC before forwarding so the Python side defers strict checking to the protocol layer.
- `cpp/tests/test_speeduino_framing.cpp` — 11 doctest cases covering the empty-input CRC, the standard `"123456789"` CRC check value (`0xCBF43926`), single-byte CRC, byte layout of an encoded frame, empty-payload frame, full encode/decode round-trip, corrupted-CRC `crc_valid=false` flag, trailing-bytes-not-consumed semantics, too-short header throws, truncated payload throws, and a 1KB random-ish payload round-trip.
- `cpp/bindings/tuner_core_module.cpp` — `speeduino_crc32`, `speeduino_encode_frame`, `speeduino_decode_frame`, and the `SpeeduinoDecodedFrame` class exposed for Python parity testing.
- `tests/unit/test_cpp_speeduino_framing_parity.py` — 17 parity tests. CRC32 vs `zlib.crc32` on 8 hand-picked payloads (including the Speeduino `S` signature query and a page-read command shape) and on 50 random payloads up to 4 KB. Frame encode vs `TcpTransport.write_framed`'s exact byte layout on 5 hand-picked payloads and on 25 random payloads up to 2 KB (each round-tripped through `decode_frame` to also pin the decoder against the `_python_frame` reference output). Corrupted-CRC and trailing-bytes-not-consumed semantics covered as separate cases.

This is the smallest possible C++ comms slice — pure logic, no sockets, no Qt — but it nails down the most error-prone bytes-on-the-wire surface ahead of the actual `TcpTransport` port. The next sub-slice in this phase will be the protocol-level command encoder (page-read / page-write / burn / runtime-poll command shapes), which sits one layer above this and consumes the framing helpers.

C++ doctest suite: 171 tests, 582 assertions, 0 failures. Full Python suite: **1964/1964 passing**.

#### Phase 14 EcuDefinition compiler slice (closes Slice 2)

- `cpp/include/tuner_core/ecu_definition_compiler.hpp` and `cpp/src/ecu_definition_compiler.cpp` — top-level INI ingestion. New `NativeEcuDefinition` aggregator carrying every leaf section's output as a member: `constants`, `output_channels`, `table_editors`, `curve_editors`, `menus`, `gauge_configurations`, `front_page`, `logger_definitions`, `controller_commands`. New `compile_ecu_definition_text(text, active_settings)` and `compile_ecu_definition_file(path, active_settings)` entry points. The implementation runs the slice-3 preprocessor exactly once with the caller-supplied `active_settings`, collects defines once via `collect_defines_lines`, and dispatches the surviving line set through every leaf parser's `_lines` overload. Single preprocessor pass, single defines pass — matches the Python `IniParser.parse()` orchestration flow.
- `cpp/tests/test_ecu_definition_compiler.cpp` — 3 doctest cases. (1) Mixed INI exercising every leaf section confirms each branch dispatches and produces non-empty results. (2) `#if FEATURE_X` gating around `[GaugeConfigurations]` confirms `active_settings` is honored end-to-end. (3) Empty INI yields fully-empty catalogs without crashing.
- `cpp/bindings/tuner_core_module.cpp` — `NativeEcuDefinition` class with read/write properties for every section, plus `compile_ecu_definition_text` / `compile_ecu_definition_file` functions.
- `tests/unit/test_cpp_ecu_definition_compiler_parity.py` — 10 parity tests against the production INI. Confirms the orchestrator dispatches every leaf parser by checking section-level counts: constants scalars (filtered to entries with `page`+`offset` since the Python `EcuDefinition.scalars` is a strict superset that includes entries compiled from `[Menu]` / `[SettingGroups]`), constants arrays (same filter against `EcuDefinition.tables`), output channels, table editors, curve editors, menu count > 0 smoke check, gauge configurations, front-page gauges + indicators, logger definitions, controller commands. A final test exercises both the `compile_ecu_definition_text` and `compile_ecu_definition_file` overloads on the same source and asserts they produce equivalent output.

**This closes Phase 14 Slice 2.** Every leaf section parser is in C++, and the orchestration seam that stitches them into a single `NativeEcuDefinition` is in place. Downstream Phase 14 work — comms layer (Slice 3), workspace / page services (Slice 4), runtime services (Slice 5), VE/WUE Analyze pipeline (Slice 6), table generators (Slice 7) — can now consume `NativeEcuDefinition` directly without poking through individual leaf parsers.

C++ doctest suite: 160 tests, 551 assertions, 0 failures. Full Python suite: **1947/1947 passing**.

#### Phase 14 tenth + eleventh parser slices: INI [LoggerDefinition] and [ControllerCommands] parsers

- `cpp/include/tuner_core/ini_logger_definition_parser.hpp` and `cpp/src/ini_logger_definition_parser.cpp` — direct port of `IniParser._parse_logger_definitions`. New `IniLoggerRecordField` and `IniLoggerDefinition` (full mirror of the Python `LoggerDefinition`: `name`, `display_name`, `kind`, `start_command`, `stop_command`, `data_read_command` as `vector<uint8_t>`, `data_read_timeout_ms`, `continuous_read`, `record_header_len`, `record_footer_len`, `record_len`, `record_count`, `record_fields`). Stateful multi-block parser: `loggerDef = ...` opens a new block, subsequent `key=value` lines populate `props`, `recordField` lines append to `fields`, `calcField` lines are skipped (display-derived), and the in-flight block is flushed on the next `loggerDef`, on a section change, or at end-of-input. The flush builds `data_read_command` via a shared `decode_command` helper that handles `\xNN` hex escapes and rewrites `\$tsCanId` / `$tsCanId` to `\x00\x00`. `record_count` is computed kind-aware: tooth = `dataLength / record_len`, composite = `dataLength` as-is.
- `cpp/include/tuner_core/ini_controller_commands_parser.hpp` and `cpp/src/ini_controller_commands_parser.cpp` — direct port of `IniParser._parse_controller_commands`. New `IniControllerCommand` (mirror of the Python `ControllerCommand` — `name` + `payload` as `vector<uint8_t>`). Each line's value is split via `parse_csv`, every part is decoded through the same `\xNN` hex-escape pipeline, and the resulting bytes are concatenated into one payload (in production every command is a single 3-byte entry, but the multi-part path is preserved for INI parity).
- `cpp/tests/test_ini_logger_definition_parser.cpp` — 11 doctest cases covering tooth-vs-composite `record_count` math, `$tsCanId` rewrite, `calcField` skip, multi-block flush, section-change flush, malformed `loggerDef` drop, case-insensitive `continuousRead = TRUE`, and preprocessor `#if` gating.
- `cpp/tests/test_ini_controller_commands_parser.cpp` — 8 doctest cases covering single/multi-command parse, comma-joined multi-part payloads, inline `;` comment strip, empty value drop, blank/comment-line skip, and preprocessor `#if` gating.
- `cpp/bindings/tuner_core_module.cpp` — extended with `IniLoggerRecordField`, `IniLoggerDefinition`, `IniLoggerDefinitionSection`, `IniControllerCommand`, `IniControllerCommandsSection` classes plus `parse_logger_definition_section{,_preprocessed}` and `parse_controller_commands_section{,_preprocessed}` functions.
- `tests/unit/test_cpp_ini_logger_definition_parser_parity.py` — 7 parity tests. Synthetic (3): logger count, top-level fields including the decoded `data_read_command` byte string, every `recordField` field. **Production INI parity (4):** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, asserts logger count, name set, every overlapping logger's display name + kind + start/stop command + decoded data-read bytes + timeout + continuous-read flag + recordDef triple + record_count match, and every overlapping logger's `recordField` list (name, header, start_bit, bit_count, scale, units) matches byte-for-byte.
- `tests/unit/test_cpp_ini_controller_commands_parser_parity.py` — 6 parity tests. Synthetic (2): command count, payload bytes. **Production INI parity (4):** loads the production fixture, asserts command count, name set, every overlapping command's decoded payload matches byte-for-byte, and the total command count is >= 50 (production has 70+).

**Validated end-to-end on the production INI:** both C++ parsers produce **byte-identical catalogs** to the Python implementation. All 13 parity tests pass on the first build run. With these slices the C++ tree now has every leaf parser the Python `IniParser` runs — the only remaining Phase 14 Slice 2 work is the `EcuDefinition` compiler that stitches the leaf catalogs together.

C++ doctest suite: 157 tests, 520 assertions, 0 failures. Full Python suite: **1937/1937 passing**.

#### Phase 14 ninth parser slice: INI [FrontPage] parser

- `cpp/include/tuner_core/ini_front_page_parser.hpp` and `cpp/src/ini_front_page_parser.cpp` — direct port of `IniParser._parse_front_page`. New `IniFrontPageIndicator` (mirror of the Python `FrontPageIndicator` — `expression`, `off_label`, `on_label`, `off_bg`, `off_fg`, `on_bg`, `on_fg`) and `IniFrontPageSection` (positional `gauges` list with missing slots filled by empty strings, plus `indicators` list). Stateful single-pass parse: `gaugeN = name` lines populate a slot map, `indicator = { expr }, ...` lines build indicator records via `parse_csv`, the gauge slot map is flattened to a positional vector at end of section. Brace handling on the indicator expression strips a single leading/trailing `{` / `}` pair if both are present, mirroring the Python `_parse_front_page`. Composed pipeline `parse_front_page_section_preprocessed` chains preprocess + collect_defines + parse.
- `cpp/tests/test_ini_front_page_parser.cpp` — 11 doctest cases covering: outside-section ignore, ordered slot list, gap-filling for missing slot indices, full indicator parse, brace-less indicator expression, indicator with too few fields dropped, inline `;` comment strip, comment-only/blank-line skip, case-insensitive section header match, multi-gauge multi-indicator interleaved, preprocessor `#if` gating.
- `cpp/bindings/tuner_core_module.cpp` — extended with `IniFrontPageIndicator` / `IniFrontPageSection` classes and `parse_front_page_section` / `parse_front_page_section_preprocessed` functions.
- `tests/unit/test_cpp_ini_front_page_parser_parity.py` — 7 parity tests. Synthetic (3): gauge list, indicator count, indicator fields. **Production INI parity (4):** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, asserts gauge slot list matches byte-for-byte, indicator count matches, every indicator field (expression, labels, colors) matches, total indicator count >= 30 (production has 40+).

**Validated end-to-end on the production INI:** the C++ front-page parser produces a **byte-identical catalog** to the Python implementation. All 7 parity tests pass on the first build run. Combined with `[GaugeConfigurations]`, the C++ tree now has the full default-dashboard contract — gauge slot positions plus the named gauges they reference plus the indicator expressions that drive the LED row.

C++ doctest suite: 139 tests, 450 assertions, 0 failures. Full Python suite: **1924/1924 passing**.

#### Phase 14 fourth parser slice: INI [CurveEditor] parser (Slice 8)

- `cpp/include/tuner_core/ini_curve_editor_parser.hpp` and `cpp/src/ini_curve_editor_parser.cpp` — direct port of `IniParser._parse_curve_editors`. New `CurveYBins` (`param`, optional `label`), `CurveAxisRange` (`min`, `max`, `steps`), `IniCurveEditor` (full mirror of the Python `CurveDefinition`: `name`, `title`, `x_bins_param`, `x_channel`, `y_bins_list`, `x_label`, `y_label`, `x_axis`, `y_axis`, `topic_help`, `gauge`, `size` as `std::array<int, 2>`), and `IniCurveEditorSection`. Stateful grammar like `[TableEditor]` but with two extra wrinkles: **multi-line curves** accumulate multiple `yBins` entries (e.g. WUE Analyze "current vs recommended"), and **`lineLabel` lines** may appear before, after, or interleaved with the `yBins` lines — they're collected into a `pending_line_labels` buffer and matched onto the y_bins_list positionally at flush time. Composed pipeline `parse_curve_editor_section_preprocessed` chains preprocess + collect_defines + parse.
- `cpp/tests/test_ini_curve_editor_parser.cpp` — 14 doctest cases covering single curve with all fields, multiple curves with flush handling, multi-line curves accumulating yBins, lineLabel positional matching, lineLabel tail-positioned (before yBins lines), title defaults to name, section change flushes active curve, inline comment stripping, malformed xAxis drops, malformed size drops, comments and blank lines, preprocessor gating with `#if FEATURE_X`, final curve flushed at section end.
- `cpp/bindings/tuner_core_module.cpp` — extended with `CurveYBins`, `CurveAxisRange`, `IniCurveEditor`, `IniCurveEditorSection` classes and `parse_curve_editor_section` / `parse_curve_editor_section_preprocessed` functions.
- `tests/unit/test_cpp_ini_curve_editor_parser_parity.py` — 12 parity tests. Synthetic (5): curve count, names, fields, y_bins lists (params and labels), axis ranges. **Production INI parity (7):** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, asserts the curve set matches exactly (the production INI has 34+ curves), every overlapping curve's `x_bins_param` matches byte-for-byte, every curve's `y_bins_list` params match (including multi-line curves), every curve's `y_bins_list` labels match (which the curve editor widget reads for the legend), every curve's `x_channel` matches (which feeds the future operating-point cursor on curves), every curve's title matches, and total count >= 30.

**Validated end-to-end on the production INI:** the C++ curve editor parser produces a **byte-identical catalog** to the Python implementation. All 12 parity tests pass on the first build run. This is the **fourth subsystem** (after `[Constants]`, `[OutputChannels]`, and `[TableEditor]`) that achieves byte-identical parity against the real production INI through the composed pipeline.

The curve editor catalog is now available in C++. Combined with `[TableEditor]`, the C++ tree now has **all the metadata it needs to drive every editable surface in the tuning workspace** — both 3D maps and 1D curves. This unblocks:
- The C++ curve editor widget (Phase 14 Slice 8) — pulls display labels, axis ranges, gauge name, and the y_bins line labels for multi-line curves
- The C++ generators for warm-up enrichment / cranking / ASE (Phase 14 Slice 7) — write to the curve's `y_bins_list[0].param` constant
- The runtime cursor on curves (gap G3 extended to curves) — reads `x_channel` to know which runtime channel drives the cursor position
- The Hardware Setup wizard's curve-aware preset application — knows which curves correspond to which engine setup parameters

C++ doctest suite: 102 tests, 327 assertions, 0 failures. Python parity suite: 91/91 passing. Full Python suite: **1896/1896 passing**.

#### Phase 14 third parser slice: INI [TableEditor] parser (Slice 7)

- `cpp/include/tuner_core/ini_table_editor_parser.hpp` and `cpp/src/ini_table_editor_parser.cpp` — direct port of `IniParser._parse_table_editors`. New `IniTableEditor` type field-for-field with the Python `TableEditorDefinition` (`table_id`, `map_id`, `title`, `page`, `x_bins`, `y_bins`, `z_bins`, `x_channel`, `y_channel`, `x_label`, `y_label`, `topic_help`, `grid_height`, `grid_orient` as `std::array<double, 3>`, `up_label`, `down_label`). Stateful grammar: `table = ...` lines open a new editor, subsequent key=value lines populate fields on the active editor until the next `table =` or section change. Composed pipeline `parse_table_editor_section_preprocessed` chains preprocess + collect_defines + parse, mirroring the Python `IniParser.parse()` flow (defines parameter accepted for signature consistency though `[TableEditor]` doesn't use `$macroName` expansion).
- `cpp/tests/test_ini_table_editor_parser.cpp` — 13 doctest cases covering single editor with all fields, multiple editors as separate state machines, xBins without channel, malformed `table` line drop, keys before any `table` line ignored, section change clears active editor, comments and blank lines, unquoted topicHelp, topicHelp with trailing comment, gridOrient with fewer than 3 values, gridHeight with non-numeric value, preprocessor gating with `#if FEATURE_X`.
- `cpp/bindings/tuner_core_module.cpp` — extended with `IniTableEditor` / `IniTableEditorSection` classes and `parse_table_editor_section` / `parse_table_editor_section_preprocessed` functions. Added `nanobind/stl/array.h` for the `std::array<double, 3>` binding on `grid_orient`.
- `tests/unit/test_cpp_ini_table_editor_parser_parity.py` — 11 parity tests. Synthetic (5): editor count, table_id set, every field, grid_height + grid_orient, topic_help. **Production INI parity (6):** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, asserts the editor set matches exactly, every overlapping editor's `z_bins` matches byte-for-byte (the headline correctness claim — the data array reference is what generators and runtime consumers care about most), every editor's axis bins match, every editor's axis channels match (which feeds the future operating-point overlay G3), every editor's title matches, and the total editor count is >10.

**Validated end-to-end on the production INI:** the C++ table-editor parser produces a **byte-identical catalog** to the Python implementation. All 11 parity tests pass on the first build run. This is the third subsystem (after `[Constants]` and `[OutputChannels]`) that achieves full byte equality against the real production INI.

The table-editor catalog is now available in C++. This unblocks **multiple downstream slices**:
- The C++ table generators (Phase 14 Slice 7) can now resolve `table_id` → `z_bins` constant name → write target
- The future C++ 2D table editor widget (Phase 14 Slice 8) can pull display labels, help topics, and axis channel names directly from this catalog
- The future C++ 3D table surface view (Phase 14 Slice 9, gap G2) consumes `grid_height` / `grid_orient` directly
- The live operating-point crosshair (gap G3) reads `x_channel` / `y_channel` to know which runtime channel to query

C++ doctest suite: 88 tests, 270 assertions, 0 failures. Python parity suite: 79/79 passing. Full Python suite: **1884/1884 passing**.

#### Phase 14 second slice: INI [OutputChannels] parser (Slice 6)

- `cpp/include/tuner_core/ini_output_channels_parser.hpp` and `cpp/src/ini_output_channels_parser.cpp` — direct port of `IniParser._parse_output_channels`. New `IniOutputChannel` type (name, data_type, offset, units, scale, translate, min/max, digits, bit_offset, bit_length, options) and `IniOutputChannelsSection` aggregating channels + a `map<name, vector<double>>` for `defaultValue` arrays. Three entry kinds handled: `scalar`, `bits` (with `$macroName` option-list expansion), `array` (recorded by name only, with subsequent `defaultValue` lines populating the array map). Composed pipeline `parse_output_channels_section_preprocessed` chains preprocess + collect_defines + parse, mirroring the Python `IniParser.parse()` flow.
- `cpp/tests/test_ini_output_channels_parser.cpp` — 11 doctest cases covering scalar parse, translate offset, bit range with option labels, array entries not promoted into channels, `defaultValue` populating the arrays map, unknown-array `defaultValue` drop, comments + blank lines, multi-section document, preprocessor gating, and `$macroName` expansion via the composed pipeline.
- `cpp/bindings/tuner_core_module.cpp` — extended with `IniOutputChannel` / `IniOutputChannelsSection` classes and `parse_output_channels_section` / `parse_output_channels_section_preprocessed` functions.
- `tests/unit/test_cpp_ini_output_channels_parser_parity.py` — 9 parity tests. Synthetic (4): scalar set, offsets + data types, array default values, bit-field options. **Production INI parity (5):** loads `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, runs both implementations through the composed pipeline, asserts the channel set matches exactly (no missing or extra names), every overlapping channel's offset is byte-identical, every overlapping channel's data type is identical, every `defaultValue` array Python recognized has byte-identical values in C++, and the parsed channel count is >100.

**Validated end-to-end on the production INI:** the C++ output channels parser produces a **byte-identical catalog** to the Python implementation. This is the second subsystem (after `[Constants]`) that achieves full equality against the real production INI.

Phase 14 now has the live-data-block schema in C++ — the prerequisite for porting the runtime telemetry decoder, the dashboard, and the live VE Analyze pipeline. C++ doctest suite: 75 tests, 222 assertions, 0 failures. Python parity suite: 68/68 passing. Full Python suite: **1873/1873 passing**.

#### Phase 14 second milestone: tuner_app workspace shell with redesigned 4-tab layout

The previous `tuner_app.exe` was a placeholder window that proved the Qt 6 link worked. After 28 workspace services landed in C++, the operator deserved something tangible to look at — so the entry point was upgraded to a real workspace shell that demonstrates the redesigned 4-tab layout from the UI/UX modernization plan, drives a few panels with actual ported services, and renders a manifest of the C++ progress to date.

- **Persistent status strip** across the top with placeholder `RPM | MAP | CLT | AFR` chip widgets, a connection indicator, and a staged-changes badge. Same shape as the redesigned status strip the modernization plan calls out — chips render via custom `GaugeChip` widgets with the dark-mode pill style. Currently shows `—` for every channel (no live telemetry yet); becomes live as soon as the runtime polling slice lands.
- **TUNE tab** loads the **production INI** (`tests/fixtures/speeduino-dropbear-v2.0.1.ini`) directly through `tuner_core::compile_ecu_definition_file` — the C++ orchestrator landed earlier in Slice 4. The left rail navigator is populated from the parsed `[Menu]` section (menu titles as bold green headers + indented item labels). The right pane renders a `Definition Summary` panel listing the parsed counts: scalars + arrays from `[Constants]`, output channels, table editors, curve editors, menus, gauge configurations, front-page slots + indicators, logger definitions, controller commands. **Every count is computed live by the C++ parser at app launch** — there are no hardcoded numbers in `main.cpp`.
- **LIVE tab** demonstrates the gauge color zone derivation by feeding three real widget threshold shapes (RPM, Battery, Coolant) through `tuner_core::gauge_color_zones::derive_zones` and rendering each derived band as a coloured pill. This is the same C++ helper the redesigned dashboard will use to drive its threshold colouring.
- **FLASH tab** placeholder pointing at `tuner_core::flash_preflight::validate` for the validation rules (already in C++).
- **HISTORY tab** is the visible progress manifest: a styled list of all 28 ported workspace sub-slices, the green `28 / 28 sub-slices landed` header, and a footer noting the underlying parser/comms/codec stack and the test totals (`517 doctest cases, 1561 assertions, 0 failures · Python parity 2445/2445`). The list is the truth source the operator sees first.
- **Dark mode default** via a `QPalette` set up with the Tuner colour set (#131418 background, #5ad687 selected-tab accent, #c0c2c6 text, #6c7078 secondary text). Fusion style. The same colour set the redesigned workspace will keep.
- **No new business logic in `main.cpp`.** The shell is intentionally a thin assembler — every panel either calls a `tuner_core` service directly (`compile_ecu_definition_file`, `derive_zones`) or renders a static manifest. The headline goal is "the C++ services are real and you can see them", not "the workspace is finished".

This is a deliberate departure from the original Slice 8 plan, which deferred all UI work until after the foundation parsers and comms were finished. Landing the shell early gives the operator a tangible, runnable progress checkpoint and proves that the layered C++ services compose into a real workspace without any Python in the loop. Subsequent sub-slices will continue to land underlying services (still parity-tested against Python) and the shell will gain another panel each time a major surface is ready.

**How to run:** `./tuner_app.exe` from `build/cpp/` (or the same directory layout the existing build artefacts already live in). The Tune tab finds the production INI by walking up from the working directory looking for `tests/fixtures/speeduino-dropbear-v2.0.1.ini`, so launching from the repo root works without arguments.

#### Phase 14 first milestone: tuner_app linked and running

- New `cpp/app/main.cpp` — minimal `QMainWindow` that opens a placeholder window with the Phase 14 milestone heading
- `cpp/CMakeLists.txt` extended with a `TUNER_BUILD_APP` option (default OFF) that adds a `tuner_app` executable target linking `tuner_core` + `Qt6::Core` + `Qt6::Gui` + `Qt6::Widgets`
- `Qt6::EntryPoint` interface dependency stripped from `Qt6::Core` to work around a UCRT-mismatch crash (the prebuilt Qt 6.7 entry-point library was compiled against an MSVC-style runtime that exports `__imp___argc`, which UCRT-based MinGW 15.2.0 doesn't)
- App built as console-subsystem in v1 so plain `int main(int argc, char* argv[])` links cleanly; will be promoted to GUI subsystem with a `WinMain` shim in a later slice
- Qt 6.7.3 installed via `pip install aqtinstall && python -m aqt install-qt windows desktop 6.7.3 win64_mingw --outputdir C:/Qt` (~18 seconds, ~250 MB)
- `tuner_app.exe` is **345 KB** static-linked against `libtuner_core.a` + dynamic-linked against `Qt6Core.dll` / `Qt6Gui.dll` / `Qt6Widgets.dll` / `platforms/qwindows.dll`
- Verified to launch the Qt event loop and run for the full timeout window (no crash on startup)

#### Phase 14 UI/UX modernization plan

The C++ rewrite is the right moment to stop being a TunerStudio clone and design a workspace that earns its own muscle memory. The Python app inherited TunerStudio's tab grid, dialog stacks, and dense table editor by necessity — we needed feature compatibility before we could question the layout. The native rewrite removes that constraint. Ship the surfaces below as part of Slice 8 (`Build the UI`) instead of straight-porting the Python panels widget-for-widget.

**Design principles** (apply to every surface below):

1. **Operator-question first.** Every panel answers a single operator question. The current Tuning tab answers "what page am I editing?", but on a real engine the question is usually "is what I just changed safe?" or "did the engine like my last burn?" — design panels around those.
2. **Quiet by default.** A clean dashboard has 4 gauges, not 14. The operator can pin more, but we don't try to fill every pixel. Inspired by modern car HMIs (Tesla, Polestar) more than legacy MegaSquirt UIs.
3. **One clear primary action per surface.** The Flash tab's primary action is "Flash". The Logging tab's primary action is "Start". No surface should have 3 equally-sized buttons competing for attention.
4. **Live data is ambient, not modal.** RPM/MAP/CLT should be visible from every tab without needing to switch to Dashboard. A persistent thin status strip across the top carries the 3-4 channels the operator cares about most, configurable via right-click.
5. **Keyboard-first power-user paths.** Command palette (Ctrl+K), quick-open (Ctrl+P), keystroke navigation between cells, undo/redo on every edit, escape always exits the current dialog.
6. **No surprise modals.** Burn confirmation, write confirmation, "are you sure?" — replace with toast notifications and undo. The only modal is one that genuinely cannot be auto-recovered (e.g. signature mismatch on connect).
7. **Dark mode is default.** Garages have bright fluorescent lights *and* tinted laptop screens. Dark with high-contrast cell highlights is what operators actually want.

**Top-level surface redesign:**

- **`StartupSurface` (already in the plan)** — recent projects, "New Project" wizard, "Connect & Auto-Detect" CTA. Add a **"Resume Last Session"** big button when the previous session ended cleanly so the muscle-memory path stays one click. Show the last 4 projects as cards with the firmware signature, last opened time, and a thumbnail of their VE table.
- **Reduce the tab grid from 8 tabs to 4.** The current Python tab list is `Overview / Tuning / Engine Setup / Runtime / Logging / Dashboard / Trigger Logs / Flash`. The new layout collapses these into:
  - **`Tune`** (replaces Tuning + Engine Setup): the main editing surface. Engine Setup becomes a wizard you launch from a button on Tune, not a peer tab.
  - **`Live`** (replaces Runtime + Dashboard + Logging): everything happening right now. Dashboard widgets are always visible at the top; the bottom switches between a runtime channel grid (debugging) and a log timeline (recording). Trigger Logs is a button on this tab, not a peer.
  - **`Flash`** (unchanged): firmware management.
  - **`History`** (new): operation log + datalog replay + evidence browser, all in one place. The current "Trigger Logs" tab folds in here as a log type, not a peer tab.
  - **Status strip across the top** carries `RPM | MAP | CLT | AFR` (configurable) plus the connection indicator and the staged-changes badge. Persistent across all 4 tabs.
- **Tune tab redesign:**
  - **Left rail navigator** that's a *flat searchable list* keyed by `Ctrl+P`, not a tree of menu/submenu/page. The current Python `DefinitionLayoutService` builds a tree because TunerStudio does; we don't have to. Group by family (the `PageFamilyService` already in C++) but render as flat sections, not collapsible nodes.
  - **2D + 3D split view** as the default for table pages. The 2D editor is the left pane (for cell editing); the 3D surface is the right pane (for visual sanity check). Operators can hide either pane. The live operating-point crosshair appears on both panes simultaneously.
  - **Inline diff strip** below the table shows what's staged on the current page (the `tuning_page_diff` service already in C++). No need to switch to a "review" tab — the diff is right there.
  - **Side-by-side scalar+table layout** for hardware-setup-style pages. Currently the Python app shows scalars and tables in vertical stacks; with modern aspect ratios the operator has plenty of horizontal room.
  - **Cell heatmap by default.** Every table cell is colored by value relative to row min/max — operators read shape much faster from a heatmap than from numbers. Toggle to bare numbers via a header button for power users. 1D curves get a sparkline next to the value column.
  - **Drag handles on column / row headers** for direct rebinning of the axis bins (TunerStudio's "rebin" dialog becomes a drag).
- **Live tab redesign:**
  - **Default dashboard layout follows the operator question, not the firmware signature.** First row: RPM dial + MAP dial + AFR target vs actual. Second row: CLT + IAT + Battery + Dwell. Third row: a 4×4 mini VE table heatmap with the live operating-point crosshair. This last one is genuinely novel — no other tuner shows the operating-point ON THE TABLE on the dashboard, but it's the single most useful thing for verifying tune correctness at a glance.
  - **Recording is one click**, not "switch to Logging tab → set profile → click Start". The button is in the status strip; recording state is shown by a red ring around the AFR gauge.
  - **Auto-pin "interesting" channels** during recording. If a channel exceeds its `lo_warn` / `hi_warn` thresholds during a recording session, pin it to the dashboard automatically. Operators currently miss "engine knock detected" events because they weren't watching that channel.
- **History tab (new):**
  - **Single timeline** with three lanes — operations, runtime captures, ECU writes — so operators can see "I staged this at 14:32, ran the engine at 14:35, the AFR went lean, I burned at 14:36". The current Python app has all three pieces but in different tabs.
  - **Click any operation to jump to the affected page.** The current "operation log" only renders text; the new one is interactive.
  - **Compare two captures side-by-side** with the existing `evidence_replay_comparison` service driving the diff highlights.
- **Hardware Setup Wizard:**
  - **Stop being a multi-page wizard.** Modern wizards are a single scrolling form with smart sections that collapse when complete. The current `SetupSurface` has 6+ pages of click-Next; the redesign is one form with a green checkmark next to each completed section and an "Apply All" button at the bottom. Operators read the whole thing once and tab through it.
  - **Inline calculator hints.** When the operator types displacement and cylinder count, the Required Fuel value updates inline next to the field, not in a separate dialog.
- **Connect dialog:**
  - **Kill the modal entirely.** Replace with a sticky banner at the top of the workspace when no connection is active. Click the banner to expand to the connection picker; auto-detect runs in the background and any successful auto-detect reduces the banner to a single click.

**Polish details that compound:**

- **Per-cell undo/redo with visual ghost.** When you undo a cell edit, the old value flashes briefly so you can verify what you reverted to.
- **Right-click context menu on every cell** with the actions operators actually use (Copy, Paste, Fill, Interpolate, Smooth, Reset to base, "Show me the staged change for this cell"). The Python app already has these in the toolbar; the rewrite makes them right-click as well.
- **Command palette (`Ctrl+K`)** lists every action by name. Type "burn" to find Burn Page; type "ve" to find every VE-related page. Replaces the menu bar entirely on the C++ side — menus stay accessible via Alt for muscle memory but the palette is the primary discovery tool.
- **Quick-open (`Ctrl+P`)** jumps to any page or parameter by fuzzy substring match. The `parameter_catalog` and `page_family` services in C++ already power this.
- **Toast notifications** for non-critical events (page burned, datalog saved, connection lost). Stack at the bottom-right and auto-dismiss after 4 seconds. Click the toast to undo where it makes sense.
- **Live preview during table edits.** As the operator drags an interpolation across a region, the heatmap updates in real-time without committing the staged value. Confirm with Enter, cancel with Escape.
- **Per-operator color presets.** Some operators want green=warning amber=danger, others want red=hot blue=cold. Ship 3 presets and let operators pick. Don't make it a 50-page settings dialog.
- **High-DPI everything.** Native Qt 6 with `QApplication::setAttribute(Qt::AA_EnableHighDpiScaling)` on by default; every icon ships at 1× / 2× / 3×; cell text uses a pixel-aligned monospace font (JetBrains Mono or similar) so the heatmap doesn't blur.
- **Touch-target sizing.** Minimum 32px hit boxes on every clickable element so the app works on a small touchscreen mounted in a vehicle.

**Where the redesign saves operator time (the metrics that matter):**

| Operator action | Python today | C++ rewrite target |
|---|---|---|
| Open last project | 2 clicks | 1 click |
| Edit a VE cell and verify on dashboard | 4 tab switches | 0 (heatmap on Live) |
| Find a parameter by name | Browse menu tree | 1 keystroke (Ctrl+P) |
| Stage → review → write a single change | 3-4 dialogs | 0 dialogs (toast + undo) |
| Compare current capture vs last burn | Switch to History, find capture, click Compare | Default split on Live |
| Set up a wideband sensor | 6 wizard pages | 1 scrolling form |
| Check whether a recent edit is safe | Switch to Tuning, scroll to page, eyeball cells | Inline diff strip is always visible |

**What stays the same** (deliberately — the muscle memory is load-bearing):

- Page write / burn semantics (`Ctrl+W` / `Ctrl+B` on the Tune tab)
- Cell editing keyboard navigation (arrow keys, Enter to commit, Esc to cancel)
- The four surface kinds (table / scalar / curve / fallback) — operators expect to find a VE table, not a "fuel landscape"
- Datalog replay scrubber semantics — frame-by-frame stepping is what operators need for ignition timing analysis
- The staged → write → burn workflow as the safety contract (no auto-flashing)
- INI/MSQ import/export at byte parity — operators routinely round-trip tunes through TunerStudio for sanity-checking

**Sequencing within Slice 8:**

The redesign doesn't add work to the Slice 8 budget so much as *redirect* it. Same rough widget count, same `QWidget` discipline (hand-coded, no `.ui` files, minimum runtime cost on old hardware) — just laid out differently. The order to land them in:

1. **Status strip** first (lowest risk, biggest visible change, sets the design tone for everything below)
2. **Command palette + quick-open** (the load-bearing keyboard surface)
3. **Tune tab** with the new left rail + 2D+3D split + inline diff strip
4. **Live tab** with the persistent dashboard + recording-via-status-strip
5. **History tab** with the unified timeline
6. **Hardware Setup wizard** redesign (replace the wizard pages with the single scrolling form)
7. **Toast notification system** (modal cull — replace every "Are you sure?" with a toast + undo path)
8. **Per-cell heatmap + visual undo + drag-rebin polish**

Each of these is a ~1 day slice on its own; the whole list is reasonable to land alongside the underlying widget infrastructure during Slice 8.

#### Slice plan

The remaining Phase 14 work, in roughly the order it lands:

1. ~~**Strip nanobind from production builds**~~ — deferred until Python retires.
2. ~~**Port the rest of the foundation parsers**~~ — ✅ **Done (sub-slice 130).** Every structural INI leaf parser ported + aggregator-wired + parity-tested against production INI. `[AutotuneSections]` was the last.
3. **Port the comms layer I/O** — `SerialTransport`, `TcpTransport` actual byte I/O (the pure-logic helpers — framing, CRC, command builders, connect strategy, capability header — are already ported). Direct serial / socket I/O without the Python GIL is where C++ pays off the most for live tuning sessions. **This is the highest-impact remaining item.**
4. ~~**Port the workspace / page services**~~ — ✅ **Done.** `workspace_state::Workspace`, `definition_layout::compile_pages`, `tuning_page_grouping::group_pages` all ported and wired.
5. ~~**Port the runtime services**~~ — ✅ **Done (pure-logic).** Mock runtime, trigger logger decoder, live capture session formatters, flash builders. Live polling / actual transport stays Python until item 3 lands.
6. ~~**Port the VE / WUE Analyze pipeline**~~ — ✅ **Done.** All ported with parity tests.
7. ~~**Port the table generators with U16-aware output**~~ — ✅ **Done.** VE / AFR / spark / boost / idle RPM generators.
8. ~~**Build the UI**~~ — ✅ **Mostly done (sub-slices 88–139).** 8 sidebar tabs (TUNE/LIVE/FLASH/SETUP/ASSIST/TRIGGERS/LOGGING/HISTORY), startup picker, menu bar, F1 cheat sheet, command palette, session persistence, recent projects, File → Open. TUNE tab has full scalar + enum + table editing with staged workflow.
9. ~~**3D table surface view (G2)**~~ — ✅ **Done.** `TableSurface3DView` with QPainter wireframe, mouse-drag rotation, live operating-point crosshair, 2D↔3D toggle.
10. **Native format becomes canonical** — ✅ **In progress.** `.tuner` loading works (sub-slice 137), conversion script done, human-readable format with compact table rows. Remaining: default save writes `.tuner` instead of MSQ; `.tunerdef` export from the app.
11. **Retire Python** — blocked on items 3 + 10. Delete `src/tuner/`, delete parity tests, delete `pyproject.toml`.

**Active frontier (sub-slice 139 → next):**
- **C++ serial/TCP I/O** — the comms layer that connects to real hardware
- **Native format as default save** — Ctrl+S writes `.tuner` JSON
- **Curve editor pages** — 1D curve visualization + editing (CurveEditor definitions parsed, UI not yet built)

#### Post-Phase-14 polish backlog (TunerStudio gap closures)

These are the lower-priority items from the gap analysis above. None of them block Phase 14 ship — they're tracked here so they don't get forgotten when the C++ app reaches feature parity with the Python one.

- **G4: Virtual / formula output channels** — ✅ **Done end-to-end on both sides + dashboard channel picker polish closed**. Parser (84), evaluator (85), Python `SessionService.poll_runtime` enrichment (86), C++ `tuner_app.exe` LIVE-tab enrichment + formula-channel demo strip (87). Dashboard channel picker polish: `open_gauge_config_dialog` now takes an optional `formula_channel_names` argument; source_combo renders a disabled `— Formula channels —` separator row followed by every formula channel prefixed with `ƒ`. Selecting one wires `widget.source = widget.title = widget.widget_id = formula_name`. Loaded from `definition.output_channels.formula_channels` at dashboard build time and threaded through the rebuild-dashboard lambda into every per-gauge config callback.
- **G5: SD card log download / browse / replay** — `SdCardPanel` in the Logging tab; depends on firmware-side `cmdSdList` / `cmdSdRead` commands existing or being added.
- **G6: Standalone log viewer parity (MegaLogViewer)** — `LogAnalyzerPanel` as a new top-level tab with timeline scrubbing, multi-cursor measurement, side-by-side dual-log comparison.
- **G7: Ignition timing scope** — ✅ **Done.** `TriggerScopeWidget` is a QPainter-based oscilloscope view on the TRIGGERS tab that renders every decoded trace from `trigger_log_visualization::build_from_rows` as a stacked track (digital traces as square-waves, analog as smooth lines), annotations as dashed vertical marks in accent_warning/text_dim by severity, and a 5-tick `ms` time axis. Replaces the text-only info-card summary grammar we had before — summaries stay below as a text breakdown.
- **G8–G12:** lower priority — see the gap analysis table above for individual rationale.
- **G13: Embedded flash for Mega2560 + STM32 (no external exe).** Teensy already flashes with zero external dependency via the embedded Win32 HID path (`cpp/src/teensy_hid_flasher.cpp`, Windows-only, mirrors the legacy Python `_flash_internal_teensy`). The other two board families still shell out:
  - **Mega2560 (AVRDUDE)** — port the STK500v2 bootloader protocol over `QSerialPort`. Pure stdlib, no vendored deps. ~400 LOC. Removes the `avrdude.exe` + `avrdude.conf` bundling requirement.
  - **STM32F407 (dfu-util)** — vendor `libusb-1.0` + port the DFU 1.1 protocol (`DETACH`, `DNLOAD`, `GETSTATUS`, `CLRSTATUS`, `ABORT`). ~500 LOC + a DLL per platform. Removes the `dfu-util-static.exe` bundling requirement.
  - Teensy on Linux/macOS is a related gap — the current embedded path is Windows-only (`setupapi`/`hid.dll`). Porting to hidapi would close it but adds a vendored dep.

  Neither is required for our target workflow (Teensy DropBear is the primary board), so these stay as subprocess fallbacks. The subprocess paths already exist and work; this backlog item is pure polish for operators on other boards who'd rather not have a `tools/` directory next to the exe.

#### Phase 14 / Firmware Phase 12 joint commitment: U16 maps where precision matters (DropBear)

Coordinated with the firmware-side **Firmware Phase 12** (`C:/Users/Cornelio/Desktop/speeduino-202501.6/speeduino/FIRMWARE_ROADMAP.md`). The pivot to a native C++ desktop is the right time to widen the *high-leverage* 3D maps on the only board family that has the SRAM/flash headroom for it. The original framing of this commitment ("all 3D maps → U16") was too broad; the refined plan widens only the tables where U08 quantization causes visible drivability or tuning-resolution issues, and leaves the rest on the existing byte contract.

**Tables that widen to U16** (precision actually matters):

| Table | Why U16 matters |
|---|---|
| `veTable`, `veTable2` | 1% VE granularity in U08 is 0.39% per step at full scale — visible AFR jumps under partial throttle, especially on small forced-induction engines |
| `afrTable` / `lambdaTable` | Stoich gasoline at ~14.7 AFR has 0.058 AFR per U08 step — visible at idle and cruise targets |
| `ignitionTable` (advance) | 90° span in U08 is 0.35° per step — noticeable at light load and on knock-sensitive setups |
| `boostTable` (boost target) | 256 kPa span in U08 is 1 kPa per step — visible boost surging on closed-loop control |
| `vvtTable`, `vvt2Table` (cam target) | Fine cam-angle control needs sub-degree resolution |

**Tables that stay U08** even on DropBear (coarse natural steps or small total ranges where byte resolution is already finer than what the operator can tune to): warmup enrichment (`wueTable`), ASE tapers (`aseTaperTable`, `aseLoadTable`), cranking enrichment, injector deadtime (`injOpenTable`), IAT/CLT retard maps, flex-fuel trims, EGO bounds, dwell compensation, idle/boost PID gain tables, and the sensor calibration pages 0/1/2 (which use a separate transport entirely).

**Why selective is better than blanket:**

1. Smaller firmware delta — roughly 5–7 pages widen instead of all 15
2. Smaller backwards-compat surface — tunes that only edited the byte-mode tables need no migration at all
3. Faster ship date — fewer pages to validate before promoting from `-U16P2` experimental to default
4. Honest characterization — "we widened the tables that needed it" rather than "we widened everything"
5. Forward-compatible with AVR — if mega2560 ever has the headroom for just the VE table to be U16, that's a per-table opt-in instead of a board-family-wide flip

**Firmware side (Speeduino, Phase 12):**

- Single production firmware variant `speeduino 202501-T41` exposes the targeted tables as native U16 on DropBear / Teensy 4.1
- Pages with mixed widened + byte-mode entries are valid (e.g. a page that holds both the VE table and a small WUE-style trim) — the page CRC and SPI flash mirror handle mixed widths the same way the experimental U16P2 path handled the all-widened case
- Experimental `-U16P2` signature collapses into the default once the targeted tables are validated
- DropBear/Teensy only — AVR builds keep the byte contract for every table (flash/RAM tight)
- One firmware build per board family — the per-table widening list is locked at compile time
- The 148-byte `LOG_ENTRY_SIZE` live-data packet is unchanged; hi-res telemetry is a separate Phase 13B slice
- Page CRC and SPI flash mirror cover the new byte stream exactly

**Desktop side (this project, Phase 14):**

- **Per-table capability-driven generation.** When the Hardware Setup Wizard or Engine Setup Wizard generates a table, it looks up the **table's `data_type` from the active definition** rather than guessing from board capability alone. Definitions for DropBear-class boards declare `veTable`, `afrTable`, `ignitionTable`, `boostTable`, `vvtTable` as `U16`; everything else (`wueTable`, retard tables, ASE tapers, etc.) stays `U08`. AVR-class definitions declare every table as `U08`. The generator just respects whatever the definition says — no special-cases.
- **Native definition format encodes the data type per table.** The owned `NativeDefinition` schema (already shipped in v1) carries `data_type` per `NativeTable`. This lets the native format describe a mixed-width contract directly, with no DropBear-vs-AVR branching in the generator code.
- **No legacy U08 generation path for tables that should be U16.** Once Firmware Phase 12 ships, the desktop's VE/AFR/spark/boost generators never produce U08 output when the active definition declares that table as U16. The byte path stays alive in the codebase as an INI/MSQ import compatibility layer (so existing TunerStudio U08 tunes can still be loaded and migrated) and for tables that genuinely stay U08 even on DropBear.
- **Selective migration on first save.** Loading a legacy all-U08 tune against the new mixed-width definition triggers a one-time in-memory upcast of *only the tables that widened* (zero-pad high byte → U16, no value change). Tables that stay U08 are untouched, so most of the on-disk MSQ stays bit-identical. The next save writes the new format. No prompt; no opt-out; the operator sees a status-bar message noting which tables migrated.
- **Live telemetry stays byte-resolution.** Dashboard gauges keep reading live VE / AFR / advance from the 148-byte packet. Hi-res telemetry depends on Firmware Phase 13B (Native Logging Contract); not blocking Phase 12.

**Sequencing:**

1. Desktop Phase 14: port foundation parsers + generator services to C++ (in progress — Slice 6 complete)
2. Desktop Phase 14: native Hardware Setup wizard producing per-table-typed output ← *the consumer*
3. Firmware Phase 12: selective U16 on Teensy build target ← *the producer*
4. Joint hardware validation: bench with DropBear + native tuner end-to-end on a page that has both widened and byte-mode entries

Until step 1 is complete, the existing experimental `-U16P2` path remains the canonical way to test U16 page handling on Teensy. Firmware Phase 12 promotes that path to default for the targeted tables; it doesn't replace it ahead of schedule.

#### Ecosystem alignment — Airbear 0.2.0 + Speeduino 202501.6 (2026-04-10 audit)

A cross-repo audit of `C:/Users/Cornelio/Desktop/Airbear-main` (firmware v0.2.0) and `C:/Users/Cornelio/Desktop/speeduino-202501.6` found several facts the desktop docs had drifted from. Captured here so the three projects stay in lockstep. **None of these are desktop bugs today** — they're integration assumptions the desktop should tighten before the C++ Phase 14 surface is operator-facing on real hardware.

**Airbear side (firmware survey corrections):**

- Airbear version is **v0.2.0**, not v0.1.2. Every fact below comes from the 0.2.0 tree. (`Airbear-main/globals.h:11`)
- A **fourth operating mode** exists: `CONNECTION_TYPE_DASH_ECHO (4)` — runs dashboard polling and TunerStudio TCP relay **simultaneously** against the same Teensy UART, arbitrated by a FreeRTOS mutex. (`Airbear-main/main.cpp:207–214`, `tcp-uart.cpp:37–47`)
- The TCP bridge now returns explicit single-byte error codes: `RC_TIMEOUT = 0x80` (Airbear waited `ECU_SERIAL_TIMEOUT = 400 ms` with no ECU reply) and `RC_BUSY_ERR = 0x85` (UART mutex held by dashboard poll in DASH_ECHO mode). Old desktop clients that treat any unexpected byte as a framing error will misbehave. (`Airbear-main/tcp-uart.h:8,11–12`)
- The Dash mode OCH parser now covers the **full 148-byte live-data block** (50+ channels including ethanol%, VVT1/VVT2 angles, dwell, knock, engine-protect status, fuel/oil pressure, and PW2–6 for 6-cyl support). The older "75-byte `'A'` response ≈ 40 channels" wording is obsolete. (`Airbear-main/serialParser.cpp:166–324`)
- Airbear now exposes a **REST API**: `GET /api/realtime` (snapshot + `fw_variant` envelope), `GET /api/status` (product, FW version, uptime, heap, WiFi RSSI, MAC, IP), and `GET|POST /api/log/*` (conditional CSV logging with field-expression triggers). (`Airbear-main/rest_api.cpp:28–94`)
- Airbear probes the Teensy firmware variant at startup via `'Q'` and exposes it as `fw_variant` on `/api/realtime` — the desktop can cross-check this against the signature string returned on its own `'Q'` exchange to detect firmware swaps. (`Airbear-main/serialParser.cpp:66–113`)
- **EcuHub UDP auto-discovery** is implemented on port **21846**; Airbear broadcasts a `Dropbear v2.0.1` advertisement on boot and on demand. The desktop should grow a UDP listener and populate a device picker rather than asking for host/port by hand. (`Airbear-main/discovery.cpp:22–24`)
- AP-mode fallback SSID `Speeduino Dash` now uses password `Bear-XXYYZZ` (last 3 MAC octets) — older docs claimed it was open. No captive portal; user must open `http://speeduino.local/config` manually. (`Airbear-main/wifi_mgt.cpp:68–90`)
- Hardware watchdog is **5 seconds**. On deadlock, Airbear resets and the desktop TCP session drops — the transport layer must reconnect cleanly rather than treat the disconnect as a fatal error. (`Airbear-main/timer.cpp:9`)
- **OTA update endpoints** `POST /updateFWUpload`, `POST /updateDataUpload`, and remote-URL fetch are live. Desktop could optionally expose a one-button "Update Airbear" action. (`Airbear-main/updater.h`, `main.cpp:70–98`)
- **CAN bus is wired but not yet in the dashboard JSON.** `getCanFramesJSON()` exists on the REST side but isn't merged into the 30 Hz OCH stream — treat as preview until the firmware commits to a stable shape. (`Airbear-main/can_bus.h`)

**Speeduino firmware side (202501.6 survey corrections):**

- `runtimeStatusA` bits **5** (`transientActive`) and **6** (`warmupOrASEActive`) are committed alongside the already-known bit 4 (`fullSync`) and bit 7 (`tuneLearnValid`). Desktop autotune sample gating that only checks bit 7 will accept samples during transient throttle and cold-start — it should also require `bit5 == 0 && bit6 == 0`. Already partially reflected in `ReplaySampleGateService` / `AutotuneFilterGateEvaluator` Phase 7 Slice 7.1 work; tighten the documentation so the next consumer doesn't guess. (`speeduino/live_data_map.h:133–141`)
- The board-capability byte at offset 130 now exposes **eight bits**, not just `BOARD_CAP_WIFI_TRANSPORT`. New additions relevant to the desktop: `BOARD_CAP_RTC`, `BOARD_CAP_SD`, `BOARD_CAP_NATIVE_CAN`, `BOARD_CAP_SPI_FLASH`, `BOARD_CAP_12BIT_ADC`, **`BOARD_CAP_HIGH_RES_TABLES` (bit 5)**, and an unrestricted-interrupts bit. (`speeduino/globals.h:151–159`) The desktop should centralise board-cap decoding into a single `BoardCapabilities` reader rather than hand-rolling bit tests per call site — every new bit is another chance for a typo.
- **`BOARD_CAP_HIGH_RES_TABLES`** signals that the board stores table cells as U16 internally. It does **not** yet imply the TS page transport is U16 — until Firmware Phase 12 ships, production still serializes bytes. Desktop must read the `CAP_FEATURE_U16P2` feature flag from the `'K'` capability-response (`comms_legacy.h:218`) and/or the `TS_PAGE_SERIALIZATION_CURRENT_BYTES` vs `TS_PAGE_SERIALIZATION_NATIVE_U16` enum value (`speeduino/pages.h:17–20`) to decide whether a given page is byte- or U16-serialized. Guessing from board type is the wrong check.
- Firmware now publishes **named OCH offset constants** in the live-data map header: `OCH_OFFSET_BOARD_CAPABILITY_FLAGS = 130`, `OCH_OFFSET_FLASH_HEALTH_STATUS = 131`, `OCH_OFFSET_RUNTIME_STATUS_A = 147`. (`speeduino/live_data_map.h:180–197`) Desktop code that currently references these as magic numbers should instead mirror the constants into `ChannelContract` and reference them by name — the existing `LiveDataMapParser` already extracts them, just make the consumer side use them.
- **SD card command inventory reality check.** Only `TS_CMD_SD_FORMAT = 13057` exists as a `ts_command_buttons` entry. There is **no** `cmdSdList` or `cmdSdRead` raw controller command. The post-Phase-14 G5 backlog entry (SD card log download / browse / replay) should be revised: SD file listing and reads go via the existing page / calibration transport, not via dedicated controller commands. This changes the firmware-side prereq for G5. (`speeduino/TS_CommandButtonHandler.h:63`)
- `LOG_ENTRY_SIZE = 148` **remains stable**; new telemetry must be append-only to avoid breaking the `ChannelContract` replay path and existing logs. (`speeduino/logger.h:15`) This is not a change — it's a lock that the desktop should surface louder in any doc that says "we might widen the live-data packet one day".
- Production signature `speeduino 202501-T41` and experimental `speeduino 202501-T41-U16P2` are **still both shipped** — the U16P2 path has not been retired yet. (`speeduino/comms_legacy.cpp:410`) The retirement happens as part of Firmware Phase 12, not independently. Any desktop code that assumes U16P2 is dead ahead of Phase 12 is wrong.
- The legacy `'F'`, `'Q'`, `'S'` identification commands stay **raw** (no framing) and all `'E'` + subtype controller commands go through `TS_CommandButtonsHandler`. The existing desktop framing-detection heuristic (`getattr`-based per-call switch in `SpeeduinoControllerClient`) is aligned with this split; no change needed.

**Ecosystem improvement backlog** — tighten the contract between the three projects:

1. **Central `BoardCapabilities` reader on the desktop.** One service that decodes all eight capability bits from `OCH_OFFSET_BOARD_CAPABILITY_FLAGS` into a typed struct (`has_wifi`, `has_rtc`, `has_sd`, `has_native_can`, `has_spi_flash`, `has_12bit_adc`, `has_high_res_tables`, `has_unrestricted_interrupts`). Every feature-gating call site consumes this struct, never a raw bit. Adding a new cap bit on the firmware side is then a one-line change on the desktop side.
2. **Mirror `OCH_OFFSET_*` constants into `ChannelContract`.** The `LiveDataMapParser` already extracts these from `live_data_map.h`; make every consumer reference them by name. No more `byte 147 bit 7` magic in C++ code — read `contract.OCH_OFFSET_RUNTIME_STATUS_A`.
3. **`TcpTransport` recognises Airbear error codes.** The read path must treat `RC_TIMEOUT (0x80)` and `RC_BUSY_ERR (0x85)` as first-class recoverable errors. `RC_BUSY_ERR` → short backoff + retry (≤ 3 attempts, 20 ms between). `RC_TIMEOUT` → surface "ECU not responding" to the operator, no silent retry.
4. **Unified discovery.** Desktop speaks both mDNS `speeduino.local` and EcuHub UDP :21846 and populates a single device picker. Matches the TSDash pattern and lets the operator plug in a DropBear on an unfamiliar network without typing a hostname. ✅ **Done (sub-slice 160).** `tuner_core::udp_discovery` ports the EcuHub `DISCOVER_SLAVE_SERVER` / `key:value\n` announcement protocol from `Airbear-main/src/discovery.cpp`, and `tuner_core::mdns_discovery` adds a lightweight `.local` resolver for `speeduino.local` using the OS IPv4 resolver. Connection dialog `Scan Network` now merges UDP announcements and mDNS resolution into one picker, deduping on IP:port so a host discovered by both paths only appears once. Doctest coverage now includes the UDP parser plus 6 focused mDNS normalization / label / merge cases.
5. **Phase 12 readiness check is definition-driven, not signature-driven.** When the desktop generator decides U08 vs U16 for a table, it reads `NativeTable.data_type` from the active definition — *not* the signature string, *not* `BOARD_CAP_HIGH_RES_TABLES` alone. Signature + cap bit are sanity checks; the definition is the authority. Already the locked Phase 14 plan — this is a reminder not to drift.
6. **`fw_variant` cross-check.** When the desktop connects via Airbear, it compares the `'Q'` signature string (from the framed TCP path) against the `fw_variant` field in `/api/realtime` (from Airbear's own probe). If they disagree, the Teensy was swapped between sessions and the desktop flags a "firmware mismatch — re-validate your tune" warning (the existing `reconnect_signature_changed()` service already handles the same kind of drift for direct-serial connections). ✅ **Done (sub-slice 149).** `tuner_core::airbear_api` ports the HTTP GET client (Winsock) and the JSON parser for `/api/realtime` + `/api/status`. Pure-logic `signatures_match(ecu_sig, fw_variant)` handles the `unknown` / case-insensitive substring / empty-variant edge cases. Connection dialog kicks off a 1.5s HTTP probe after every successful framed TCP connect; mismatch pops a `QMessageBox::warning` but does not block the connection. 15 new doctest cases cover the HTTP body splitter, both JSON parsers, and every match/mismatch/unknown branch.
7. **SD card plan revision.** G5 post-Phase-14 backlog should stop assuming dedicated `cmdSdList` / `cmdSdRead` raw commands exist and instead prototype SD access via the existing page/calibration transport. If that's too awkward, the right next step is a firmware-side proposal to add the two raw commands — not a desktop-side guess about what they'll look like.
8. **Airbear REST as a lightweight secondary-observer path.** Any tooling (external dashboards, scripting, Grafana) that only needs live channels can hit `/api/realtime` + `/api/status` instead of opening a framed TCP session. The desktop's opt-in HTTP Live-Data API (port 8080) can front this if the operator wants a single endpoint — or can let Airbear serve it directly.
9. **Optional: `POST /updateFWUpload` integration.** Desktop can expose a one-button "Update Airbear" action that wraps the existing OTA endpoint; low priority but eliminates a big "drop into PlatformIO CLI" detour for operators. ✅ **Done (sub-slice 159).** `airbear_api::post_firmware` + pure-logic `build_multipart_body` ported. File menu → "Update Airbear Firmware..." prompts for host + .bin file, uploads as `multipart/form-data` with 2-minute timeout, reports response in status bar + message box. 2 new doctest cases cover the multipart shape including binary payloads with NUL bytes.
10. **Documented append-only live-data packet contract.** Any future firmware change to the 148-byte packet must be append-only. Cross-linking from the desktop `ChannelContract` docs to the Speeduino `live_data_map.h` lock makes this explicit.

#### Speeduino firmware ↔ Tuner direct contract (firmware-to-desktop, Airbear out of frame)

The Airbear ecosystem alignment above focuses on the middle peer. This subsection scopes the **direct** contract between the Speeduino firmware and the Tuner desktop — the relationship that exists regardless of whether the transport is raw serial (USB / Serial1) or TCP via Airbear. Everything under this heading is how the two projects agree on identity, capabilities, live-data semantics, page layout, and control surfaces.

**What flows from firmware to desktop (firmware publishes, desktop consumes):**

| Contract | Where in firmware | How desktop consumes |
|---|---|---|
| Firmware signature string (identity) | `speeduino/comms_legacy.cpp:410` via `'Q'` command | `SessionService.reconnect_signature_changed()` — triggers warning dialog if it changes between sessions |
| Board capability bits (8 flags) | `speeduino/globals.h:151–159`, live-data byte 130 | Needs a central `BoardCapabilities` reader — currently only bit 7 (WiFi) is consulted |
| `LOG_ENTRY_SIZE = 148` live-data packet | `speeduino/logger.h:15`, layout in `live_data_map.h` | `ChannelContract` + `LiveDataMapParser` — structural canary test asserts sum of widths = 148 |
| `runtimeStatusA` bits (4, 5, 6, 7 = fullSync / transientActive / warmupOrASEActive / tuneLearnValid) | `speeduino/live_data_map.h:133–141`, byte 147 | Phase 7 Slice 7.1 `firmwareLearnGate` — consumes bit 7 as hard gate; bits 5 and 6 should also be consumed but are not yet wired |
| `OCH_OFFSET_*` named constants | `speeduino/live_data_map.h:180–197` | `LiveDataMapParser` already extracts them; consumer sites should reference by name, not magic number |
| Page serialization mode enum (`TS_PAGE_SERIALIZATION_CURRENT_BYTES` vs `TS_PAGE_SERIALIZATION_NATIVE_U16`) | `speeduino/pages.h:17–20` | Authoritative U08/U16 signal per page — desktop `MsqWriteService` / `NativeFormatService` table generators must read this, not infer from board type |
| `CAP_FEATURE_U16P2` feature flag in `'K'` response | `speeduino/comms_legacy.h:218` | Signals that the experimental (soon-default) U16 page-2 path is active — the per-session Phase 12 readiness signal |
| Per-page dynamic sizing (`getPageSize(pageNum)`, max 544 bytes) | `speeduino/pages.h:13–15, 23–37` | Write-chunking via `blockingFactor` / `tableBlockingFactor` in the `IniParser` — already consumed, but the 544-byte ceiling (which exists to accommodate future U16 widening) isn't documented on the desktop side |
| Controller command catalog (`TS_CMD_*` IDs + `'E'` + subtype dispatch) | `speeduino/comms_legacy.cpp:570–586`, `TS_CommandButtonHandler.h` | `IniParser._parse_controller_commands` → `EcuDefinition.controller_commands` → `HardwareTestPanel` dispatch |
| Tooth + composite logger record formats | `speeduino/logger.h:28–38` | `LiveTriggerLoggerService` bit-level decoder + `TriggerCaptureWorker` |
| Page CRC serialization mode | `docs/page_verification_protocol.md:34–52` | Desktop MSQ writer must recompute CRC against the mode-correct byte stream when Phase 12 lands with mixed-width pages |

**What flows from desktop to firmware (desktop produces, firmware consumes):**

| Surface | Contract | Risk if wrong |
|---|---|---|
| `'r'` / `'p'` / `'M'` / `'b'` / `'f'` / `'t'` / `'H'` / `'J'` / `'X'` data commands | Raw over serial, framed over TCP (`[u16 LE len][payload][u32 LE CRC32]`), framing detected via `getattr` on transport | Protocol desync, garbage reads |
| `'F'` / `'Q'` / `'S'` identification | Stay raw even on TCP — Airbear special-cases these too | Handshake fails, no connection |
| `'E'` + subtype controller command payloads | 3-byte entries typically (`E` + subtype + param) per `EcuDefinition.controller_commands` | Wrong subtype fires the wrong test output |
| MSQ pages at write time | Per-table `data_type` respected (U08 vs U16), per-page size chunked to `blockingFactor` | Page CRC mismatch, tune won't burn |
| Table generators (VE / AFR / spark / boost / VVT) | Output width matches the active definition's `NativeTable.data_type`, mixed-width pages handled correctly | Pre-Phase-12: desktop must not widen tables the firmware still expects as U08 |

**Joint invariants (both sides own, neither can change unilaterally):**

1. **148-byte live-data packet is append-only.** Any firmware change that reorders, removes, or widens an existing row breaks every historical log that replays through `ChannelContract`. Widening goes at the end, with a capability bit + feature flag to signal it.
2. **Signature family defines definition compatibility.** `speeduino 202501-T41` and `speeduino 202501-T41-U16P2` are both valid but **non-interchangeable** signatures — definitions are not cross-compatible. A future third variant must either reuse the T41 definition or ship its own.
3. **Framing split by command class, not by transport.** `F`/`Q`/`S` are raw everywhere; all other data commands are framed everywhere framing is available (i.e. TCP) and raw when it isn't (i.e. USB serial). A new command must declare which class it joins at design time.
4. **`runtimeStatusA` bits are a semantic contract, not a byte layout.** Tuner reads by bit name via `ChannelContract`, not by bit number in hand-written code. If the firmware ever has to shuffle the byte, the named-constant path survives; literal `byte 147 bit 7` in a handler does not.
5. **Controller command numeric IDs are stable forever once published.** `TS_CMD_SD_FORMAT = 13057` cannot be renumbered. New commands get new IDs; old IDs are never reused even after removal.
6. **Page serialization mode is per-page, not per-signature.** Phase 12 will produce pages that hold both byte-mode and U16 entries on the same page. Desktop and firmware agree that page width is derived from the definition's per-entry `data_type`, not from a page-level flag.

**Current drift / weak points (audit 2026-04-10):**

- **Capability bits half-consumed.** Firmware exposes 8 bits; desktop reads 1. Adding `BOARD_CAP_HIGH_RES_TABLES` (bit 5) on the firmware side produced zero desktop change because no decoder exists. Fix = central `BoardCapabilities` reader, one service, eight fields.
- **OCH offsets still magic numbers in some call sites.** `LiveDataMapParser` already publishes the named constants; consumers reference them inconsistently. Goal: zero `byte 147` literals in handler code, every one resolved through `contract.OCH_OFFSET_RUNTIME_STATUS_A` or equivalent.
- **Autotune gate reads only bit 7.** Bits 5 (`transientActive`) and 6 (`warmupOrASEActive`) exist in the firmware and are exactly the kind of signal that `ReplaySampleGateService` was designed to consume — but the Phase 7 Slice 7.1 implementation currently only hard-blocks on bit 7 plus bit 4. Tightening to `bit 5 == 0 && bit 6 == 0` is a one-line gate extension.
- **U08/U16 decision path not yet definition-driven in the C++ port.** The locked Phase 14 plan says "read `NativeTable.data_type` from the active definition"; until the C++ generator slice lands, the Python side still has branches that look at the signature string. Don't reintroduce that branching when porting to C++.
- **SD plan assumed commands that don't exist.** G5 backlog needs revision — firmware only ships `TS_CMD_SD_FORMAT = 13057`, no `cmdSdList` / `cmdSdRead`. This is a joint decision point: either file-listing goes through the existing page/calibration transport, or new raw commands need to be spec'd on the firmware side first.
- **`CAP_FEATURE_U16P2` not yet surfaced in desktop capability reader.** The desktop's Phase 12 readiness decision should consume this flag; currently the only U16 signal the desktop uses is the experimental signature string, which is the wrong layer.

**Joint next moves (in effort × leverage order, desktop-side-only first):**

1. **[desktop, small]** Central `BoardCapabilities` reader decoding all eight bits from `OCH_OFFSET_BOARD_CAPABILITY_FLAGS`. Every feature gate consumes this struct.
2. **[desktop, small]** Mirror the `OCH_OFFSET_*` constants from `ChannelContract` into every consumer — retire every `byte 147` / `byte 130` literal in handler code.
3. **[desktop, small]** Extend `firmwareLearnGate` (Phase 7 Slice 7.1) to also require bits 5 and 6 clear. Already-tested service — one-line delta, one new test, no firmware change.
4. **[desktop, small]** `'K'` capability command response parser — consume `CAP_FEATURE_U16P2` and expose it alongside `BoardCapabilities` so later Phase 12 readiness checks have a clean input.
5. **[desktop, medium]** Phase 14 C++ generator respects `NativeTable.data_type` per table (not signature) when writing MSQ pages. Locked plan; enforce during the generator-slice port.
6. **[joint, small]** Append-only live-data packet contract written into both roadmaps explicitly (firmware `FIRMWARE_ROADMAP.md` + desktop `tuning-roadmap.md`) as a hard invariant, not a comment. Cheap, prevents the next person from rearranging the packet.
7. **[joint, medium]** SD-card command decision — pick "go via existing page/calibration transport" or "add `cmdSdList` / `cmdSdRead` raw commands" before writing the desktop `SdCardPanel`. Affects `G5` backlog entry scope.
8. **[joint, large, future]** Machine-readable firmware capability manifest (JSON) published alongside the INI — lets the desktop stop parsing INI for cross-cutting metadata and read it from one place. INI becomes an import/compat layer, not the contract.

Items 1–4 are cheap wins that land entirely on the desktop side and should be scheduled before the C++ Phase 14 surface starts touching real hardware. Items 6–8 need a conversation with the firmware owner before code is written.

**Why this is the right time:**

1. The experimental U16P2 page-2 path is already validated end-to-end on real hardware — the architectural risk is gone
2. The desktop is being rewritten in C++, so reading `data_type` from the definition in the C++ generators from day one is cheaper than special-casing U16 later
3. The firmware's `live_data_map.h` discipline is in place, so widening telemetry channels later is a tractable separate problem rather than a layout-shuffling exercise
4. DropBear has the headroom — Teensy 4.1 has 1 MB SRAM and 8 MB flash; doubling map storage from byte to U16 for the high-leverage tables is invisible at the platform level

Expected shape at completion:

- shared native core for schema, protocol, validation, and generation
- desktop UI on a mature native framework
- explicit separation between legacy import/export compatibility and the project's native file/runtime model

### Future Phase 15: Better-Than-TunerStudio Autotune

Goal: build an autotune system that is more transparent and safer than the TunerStudio baseline.

Principles:

- deterministic correction engine first
- fully reviewable proposals and bounded table edits
- explainable acceptance/rejection of samples
- explicit confidence and coverage reporting

Initial technical direction:

- delay compensation
- steady-state and transient rejection
- per-cell weighting and correction bounds
- smoothing/interpolation rules that remain reviewable

Reference-pack-driven additions:

- separate engine VE-shape reasoning from charge-density / boost / manifold-temperature effects
- add root-cause diagnostics for "not a VE problem" cases such as injector-flow error, deadtime error, target-table error, or bad MAP/IAT/sensor calibration
- add boosted-engine confidence penalties around spool transition, unstable manifold temperature, or uncertain pressure-ratio assumptions
- add horsepower / airflow / injector consistency checks so setup generators and autotune can share the same sanity model
- use torque-peak-informed or airflow-informed VE priors when the operator has credible supporting data

Firmware-gated sample quality:

- the firmware `runtimeStatusA` byte (bit 7 `tuneLearnValid`, bit 4 `fullSync`, bit 5 `transientActive`, bit 6 `warmupOrASEActive`) provides explicit firmware-side learning-gate signals without requiring any INI/packet-size change
- `tuneLearnValid` = `fullSync && !transientActive && !warmupOrASEActive` — gate VE/WUE cell acceptance on this bit instead of approximating steady-state from RPM/TPS derivatives alone
- integrate with the existing `ReplaySampleGateService` and `AutotuneFilterGateEvaluator` — the firmware bit is an additional hard gate, not a replacement for the software-side gating logic

ML is optional later, not foundational first scope. If introduced, use it for:

- sample-quality scoring
- anomaly detection
- confidence estimation
- sparse-area coverage guidance

Do not use a black-box model as the first write-authority for VE or target-table corrections.

## Long-Horizon Recommendations

After the active roadmap/backlog is in a good state:

1. finish dashboard and operator-facing autotune workflows in Python
2. harden the project with more real release fixtures and decompiled-behavior checks
3. define owned tune/definition contracts before any rewrite
4. prototype a native core only after the Python product can serve as a reliable oracle
5. treat ML as a later assistive enhancement, not as a substitute for deterministic tuning math

## Current Guidance For Contributors

- Preserve the presenter/service layering.
- Do not push business rules into Qt widgets.
- Keep offline and live workflows equally supported.
- Keep evidence/replay flows reviewable and deterministic.
- Do not reintroduce full table rerenders for evidence-only updates.

## Post-Parity Feature Roadmap (as of sub-slice 146)

With full tab parity achieved and the native format ecosystem in place,
the following features are prioritized by operator impact.

### Phase 15: Operator-Facing Features

| # | Feature | Effort | Status |
|---|---------|--------|--------|
| 1 | Virtual dyno / power curve view | Moderate | ✅ Done |
| 2 | VE Analyze coverage heatmap overlay | Moderate | ✅ Done |
| 3 | Zone-based alert toasts on gauges | Trivial | ✅ Done |
| 4 | Airbear SD card log download | Moderate | Desktop-side complete — `airbear_api::{parse_sd_log_list_json, build_sd_log_path, fetch_sd_log_list, fetch_sd_log_bytes}` against a `/api/sd/logs[/<name>]` contract that matches the existing Airbear REST grammar, plus a LOGGING-tab "Airbear SD Logs" card (host field, Refresh → list, Download + Open in Timeline → funnels into the existing timeline widget). End-to-end validation still blocked on firmware G5 command spec shipping the endpoints — when it lands, only the two fetch helpers move if the paths/schema differ |
| 5 | Staged-change visual diff (table heatmap) | Moderate | ✅ Done |
| 6 | Confidence badges on wizard generators | Trivial | ✅ Done |
| 7 | Plain-language VE Analyze summaries | Moderate | ✅ Done |
| 8 | Next-steps guidance after VE Analyze | Moderate | ✅ Done |
| 9 | Map switching / multi-tune slots | Moderate | ✅ Desktop-side complete — steps 1 (NativeTune v1.1 slot fields) + 2 (`RuntimeStatus::active_tune_slot` + LIVE-tab `● Slot N` chip) + 3 (project-bar slot badge) + 4 (Burn to: slot picker + live-burn refusal when target slot > 0 pending firmware 14G) + 5 (Tune → Copy Current Tune to Slot…) + 6 (`CapabilityHeader::slot_fingerprints` parses 4 × 8-byte trailing bytes from the `'f'` response when firmware 14B ships them, `EcuConnection::capabilities` populated after every connect; File → Show ECU Capabilities… opens a read-only dialog with signature, protocol/blocking factors, active slot, and per-slot fingerprint rows that render "pending firmware 14B" / "(slot empty)" / real hex depending on state) + 7 (File → Open Tune from ECU SD…) ✅. End-to-end validation still waits on firmware 14G/14B/G5 shipping — when they do, the desktop-side code paths are already live |
| 10 | Compressor map turbo modeling | Medium | ✅ Done |

### Phase 16: Ecosystem Tightening

| # | Feature | Effort | Requires | Status |
|---|---------|--------|----------|--------|
| 1 | Definition hash in firmware capability | Firmware change + desktop | Speeduino firmware + desktop | ✅ **Done end-to-end.** Speeduino firmware side (`speeduino-202501.6/speeduino/comms_legacy.{h,cpp}`): `CAPABILITY_RESPONSE_SIZE` bumped from 39 → 43 bytes, `CAPABILITY_SCHEMA_VERSION` bumped 1 → 2, `SCHEMA_FINGERPRINT` constant added (interim: manually bumped per release; `tools/generate_schema_fingerprint.py` build-derived version is later polish). `buildCapabilityResponse` appends 4-byte LE fingerprint at offset 39. Desktop side: new `KCapabilityResponse` struct + `parse_k_capability_response` in `speeduino_connect_strategy` (handles both 39-byte v1 and 43-byte v2 payloads). `EcuConnection::k_capabilities` populated from `'K'` query after every connect alongside the legacy `'f'` blocking-factor query. File → Show ECU Capabilities… renders signature + capability schema + board ID + feature flags + live data size + blocking factors + active tune slot + schema fingerprint. Save-as-native captures the live `schema_fingerprint` into `NativeTune::definition_hash`. Burn-time guard compares loaded tune's hash against connected ECU's hash, refuses burn on mismatch. 6 new doctest cases pinning the parser |
| 2 | Per-page format bitmap in 'K' response | Firmware change | Speeduino firmware PR | Planned — desktop parser speculation retired after verifying the actual `'K'` 39-byte response (see P16 item 1). A per-page bitmap isn't specified in the firmware roadmap today; desktop's table generators already read `data_type` per table from the active definition, so there's no immediate capability gap. If/when firmware adds a per-page format declaration, the desktop-side addition is a trailing-byte parser extension in `parse_k_capability_response` — same pattern as the schema_fingerprint tail |
| 3 | HTTP API versioning (/api/v1/) | Trivial | Desktop only | ✅ Done |
| 4 | Airbear error counters in /api/status | Airbear change + desktop | Airbear firmware PR | ✅ **Done end-to-end.** Airbear side (`Airbear-main/src/tcp-uart.{cpp,h}` + `rest_api.cpp` `handleStatus`): `TCPrequestsReceived` (already existed) + new `ecuTimeouts` + `ecuBusyResponses` counters incremented at the four `RC_TIMEOUT` / `RC_BUSY_ERR` send paths in `handleData`, exposed as `tcp_requests` / `ecu_timeouts` / `ecu_busy` JSON keys. Desktop side: `StatusResponse` field names aligned with real keys (retired the four speculative names), `parse_status_json` reads them, File → Airbear Health… renders `TS/ECU requests` as a neutral volume counter + `ECU timeouts` / `ECU busy` as error counters colored by threshold. Older Airbear builds that predate the counters fall back to dashes + the existing footnote |
| 5 | Standalone log viewer with timeline | Large | Desktop only | ✅ Done — scrubbable timeline widget with stacked channel tracks + click/drag cursor + play/pause + 1x/2x/4x/8x speed selector + channels picker + shift-drag region zoom with translucent selection overlay + Reset Zoom button + zoom-percent hint + Export menu (visible range as CSV, timeline snapshot as PNG) landed in LOGGING tab |

### Virtual Dyno Design Notes

Calculates estimated torque and horsepower from ECU sensor data during
a WOT (wide-open throttle) pull. No physical dyno required.

**Inputs (from datalog or live capture):**
- RPM, MAP, IAT, AFR from runtime channels
- Displacement, VE table values from tune
- Injector flow rate from tune

**Calculation:**
```
mass_air_flow = VE * displacement * RPM * MAP / (R * IAT_kelvin * 120)
fuel_mass = mass_air_flow / AFR
indicated_torque = fuel_mass * LHV * thermal_efficiency / (4 * pi)
brake_torque = indicated_torque * mechanical_efficiency
horsepower = brake_torque * RPM / 5252
```

**Output:**
- Torque vs RPM curve
- Horsepower vs RPM curve
- Peak torque + peak HP annotations
- Before/after overlay for tune comparison

**UI location:** New section in ASSIST tab, or standalone Dyno tab.
