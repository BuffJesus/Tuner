# Reconstruction Spec

## Product Surface

The target application combines:

- project management (project open/save, definition loading, tune load/save)
- ECU connection management (serial/TCP/UDP/Bluetooth transport, offline mode)
- live dashboards and gauges (DashTuningPanel inline editing, designer, save/load)
- hardware setup workflows (injectors, ignition coils, trigger patterns, sensor calibration)
- guided setup and base tune generation (injector helpers, required fuel helpers, conservative VE/AFR starters)
- forced-induction setup and modeling (turbo, supercharger, twin-charge, compressor-map-assisted airflow modeling)
- tune parameter and table editing (scalar sections, table editors, staged edits, burn flow)
- datalog viewing and playback (cell-hit overlays, charting, timeline scrubbing)
- triggered logging workflows (tooth log, composite log, trigger log)
- autotune / VE Analyze (deterministic baseline parity, then confidence-scored enhanced mode)
- programmable output port editing
- board and firmware management (detection, preflight, flashing, audit trail)
- project health diagnostics (compatibility matrix, mismatch detection)

## Primary Working Reference Set

Current real-world artifacts in active use for reconstruction and validation:

- release directory: `C:\Users\Cornelio\Desktop\speeduino-202501.6\release`
- firmware hex: `C:\Users\Cornelio\Desktop\speeduino-202501.6\release\speeduino-dropbear-v2.0.1-teensy41-u16p2-experimental.hex`
- tune file: `C:\Users\Cornelio\Desktop\speeduino-202501.6\release\Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq`
- ECU definition: `C:\Users\Cornelio\Desktop\speeduino-202501.6\release\speeduino-dropbear-v2.0.1-u16p2-experimental.ini`

Prefer validating reconstruction work against these exact artifacts when testing real workflows, UI layout assumptions, hardware setup visibility, and live controller behavior.

### Artifact Pairing Rules (from release README)

The release ships two matched sets. Mixing them breaks signature matching:

| Set | Firmware | INI | Base tune | Signature |
|-----|----------|-----|-----------|-----------|
| Production DropBear / T41 | `speeduino-dropbear-v2.0.1-teensy41.hex` | `speeduino-dropbear-v2.0.1.ini` | `speeduino-dropbear-v2.0.1-base-tune.msq` | `speeduino 202501-T41` |
| Experimental Native-U16 P2 | `speeduino-dropbear-v2.0.1-teensy41-u16p2-experimental.hex` | `speeduino-dropbear-v2.0.1-u16p2-experimental.ini` | `speeduino-dropbear-v2.0.1-u16p2-experimental-base-tune.msq` | `speeduino 202501-T41-U16P2` |

Note: older projects using signature `speeduino 202501` (AVR) will not attach cleanly to the Teensy 4.1 firmware without updating the project INI.

### Validated MSQ Structure (Ford300_TwinGT28_BaseStartup_u16p2_experimental.msq)

Confirmed by inspection:

- `nPages="15"`, `signature="speeduino 202501-T41-U16P2"` — matches INI
- Both `lambdaTable` (16×16, Lambda units, offset 0) and `afrTable` (16×16, AFR units, offset 256 via `lastOffset`) are present in page 4 with real data
- `wueAFR` is in AFR units in this tune (values −2.0 to 0.0), confirming the `#else` branch of `#if LAMBDA` is the correct default when `LAMBDA` is not set
- `lastOffset` resolution: `lambdaTable` occupies 256 bytes (16×16×U08); `afrTable` starts at offset 256 — computed automatically by the parser

### Known INI Parser Correctness Evidence

- `lastOffset` is implemented and tested: `test_parsers.py::test_ini_parser_resolves_lastoffset_for_following_arrays_and_scalars` confirms `lambdaTable.offset == 0`, `afrTable.offset == 256`, and subsequent scalars chain correctly
- `#unset enablehardware_test` at the top of both Speeduino INIs is now correctly handled by the preprocessor — Hardware Testing menu is hidden by default
- `blockingFactor = 251` and `tableBlockingFactor` are parsed and consumed by write chunking via `_effective_blocking_factor()`

## Two-Axis Parameter Model

TunerStudio's core distinction, which the rewrite must preserve:

**Controller parameters (constants):**
- owned by the INI/MSQ
- editable offline
- written to ECU RAM on demand, burned to flash
- source of truth: definition + tune file

**Output channels (runtime telemetry):**
- owned by the ECU communication stream
- read-only in the tuning UI
- used as evidence for autotune, gauge display, and charting
- source of truth: live or replayed session

These must not be conflated. Autotune filter expressions, gauge properties, and visibility conditions that reference output channels must resolve against the runtime evidence pipeline, not against the tune file.

## Legacy Format Findings

The current Speeduino/legacy-compatible contract is a reconstruction target, not a good long-term native design target.

Findings from the validated release artifacts, firmware notes, and decompiled TunerStudio sources:

- the release INI is still fundamentally a storage-layout contract: page numbers, offsets, `lastOffset`, data widths, and table-editor/menu indirection all carry meaning that should be explicit in a native schema
- firmware/INI/tune compatibility remains tightly coupled to exact signature families and page-size expectations
- semantic concepts such as AFR/Lambda target tables are represented through multiple parallel names and paths instead of one canonical model
- the application layer wants to store richer metadata than the ECU storage contract naturally supports; decompiled TunerStudio sources show this via application-managed sections such as `EncodedData` and `TuningViews`
- parser correctness problems can surface as missing UI/table behavior even when the tune data itself exists, which is a sign that the format carries too much implicit structure

Implication:

For reconstruction work, INI/MSQ remain the compatibility source of truth. For the long-term owned platform, the project should aim for semantic native file formats and treat page/offset-based controller layouts as an import/export/runtime concern.

## Native Format Direction

Recommended long-term split:

- native definition/schema files: human-authored, comment-friendly, strongly structured, likely `JSON5`
- native tune files: semantic values, versioned migrations, deterministic diffs, likely `JSON`
- native project/workspace files: operator context, wizard state, generator assumptions, review state, evidence links, layouts, and other app-owned metadata
- firmware export/import layer: maps semantic tune data onto controller page/offset storage for legacy or transitional firmware

Expected gains from native files:

- stable semantic identities for tables, axes, calibrations, and capability-gated features
- explicit schema validation instead of parser inference and naming conventions
- cleaner separation between ECU storage bytes and richer app/workflow metadata
- easier migration/versioning as firmware and desktop evolve together
- better storage for deterministic autotune provenance, confidence, coverage, and review artifacts

## Custom Firmware Requirements For Native Files

Moving to owned tune/definition/project files is not just a desktop-file change. The custom firmware contract would also need to evolve.

Required firmware-side changes:

- expose explicit schema and capability versions rather than relying mainly on signature-family matching
- provide stable semantic identifiers for parameters, tables, axes, calibrations, and runtime channels
- separate the semantic contract from the internal memory layout so page/offset organization can change without invalidating authored tune files
- define deterministic import/export rules between native semantic tune data and controller storage bytes
- version runtime/log/output-channel contracts explicitly so dashboard, replay, evidence, and autotune consumers can trust field meaning across firmware revisions
- define defaults and migration behavior for newly added, removed, or renamed parameters and tables
- expose enough capability metadata for the desktop app to know which native schema features are supported by a given firmware build

Recommended firmware/runtime contract shape:

- firmware reports board identity, capability flags, schema version, runtime-channel version, and storage/export version independently
- semantic table/parameter IDs remain stable even if underlying page placement or data width changes
- native tune import is validated against schema/capability metadata before any write/burn operation
- firmware storage layout remains a private implementation detail or at most a transport/export concern

Practical implication:

The future owned platform should avoid replacing one brittle coupling with another. A custom tune file should not simply become a nicer wrapper around page numbers and offsets. The firmware contract itself needs a semantic layer.

## Autotune Design Principles

**Baseline goal:** deterministic VeAnalyze/WueAnalyze parity before any improvement.

**Filter gate model:** parse from INI `[VeAnalyze]` and `[WueAnalyze]` sections. Each filter gate has a name, a channel reference, a comparison operator, a threshold, and a default-enabled flag. The standard gates are: minCltFilter (coolant minimum), accelFilter (accel enrichment active), aseFilter (ASE active), overrunFilter (zero pulsewidth), maxTPS (TPS limit), minRPM (RPM floor), std_xAxisMin/Max (axis range), std_yAxisMin/Max (axis range), std_DeadLambda (implausible lambda), std_Custom (user-defined).

**Evidence data flow:**
```
Runtime stream / datalog replay
    -> evidence sample (RPM, load, lambda, output channels, timestamp)
    -> filter gate evaluation (per VeAnalyze filter model)
    -> cell-hit resolution (table axis interpolation)
    -> per-sample correction delta computation
    -> per-cell aggregation with confidence scoring
    -> operator review surface (correction preview, evidence inspector)
    -> apply to staged tune (write-to-RAM or local stage only)
```

**Enhancement goals (Phase 7, after baseline is trusted):**
- per-sample transparency on cell overlays
- confidence scoring (sample count, lambda variance, recency, neighborhood consistency)
- gated apply modes (high-confidence-only, threshold, all)
- neighborhood smoothing preview (raw vs smoothed side by side)
- comparative preset analysis (same log, different filter configs, diff output)

## Better-Than-TunerStudio Autotune Inputs

Once baseline parity is trusted, the rewrite should make better use of data TunerStudio either does not surface clearly or does not weight aggressively enough:

- lambda variance over time, not just instantaneous AFR error
- sample dwell time within a cell, not just hit count
- neighborhood agreement across adjacent cells
- transient context: TPSdot, MAPdot, accel enrichment, decel fuel cut, ASE/WUE transitions, idle correction activity
- ignition/sync context: sync loss, half-sync, trigger instability, timing instability
- injector pulsewidth trust region, especially low-PW deadtime-dominated areas
- sensor trust metrics: heater state, implausible lambda behavior, calibration sanity, noisy or delayed signals
- repeatability across multiple logs / sessions
- correction history: whether prior changes improved or worsened error in that region
- environmental context: CLT, IAT, baro, battery voltage, flex content, accessory load
- generator baseline confidence, including divergence from conservative airflow and turbo assumptions when applicable

These should not be treated as opaque ML features. They should feed explicit confidence and gating logic the operator can inspect.

## Better-Than-TunerStudio Confidence Model

Phase 7 should score evidence using transparent factors such as:

- sample count
- time spent in-cell
- lambda stability / variance
- engine-state stability
- neighborhood consistency
- repeatability across runs
- confidence decay in transient or low-trust regions
- deviation from conservative generator assumptions when those assumptions were created with good confidence

Outputs should distinguish at least:

- high-confidence correction
- low-confidence suggestion
- rejected evidence with reason

## Better-Than-TunerStudio Apply Rules

Autotune should improve mainly by becoming better at knowing when *not* to act:

- require operator-visible evidence before apply
- support replay-first/offline review workflow
- allow high-confidence-only apply modes
- warn when the likely issue is not VE alone (deadtime, target table, sensor calibration, sync instability)
- preview raw correction vs smoothed correction vs clipped/safety-limited correction
- flag when a correction would create an obviously poor surface relative to neighboring cells
- preserve per-sample accepted/rejected reason trails

**Non-goals for autotune:** ML models, opaque scoring without explanation, applying corrections without operator review step.

Additional deterministic autotune improvements suggested by the reference pack:

- detect and warn when correction demand is more consistent with wrong injector flow, engine displacement, MAP/IAT calibration, deadtime, or AFR target data than with a true VE-shape error
- add boosted-engine gating or confidence penalties when manifold temperature, spool state, or pressure-ratio assumptions are unstable
- treat low pulsewidth / deadtime-dominated areas as lower-confidence correction regions by default
- distinguish likely VE error from transient fueling error, target-table error, and sensor-model error in the review surface

## Logging Reconstruction Direction

Logging is currently behind the rest of the product. The app has usable replay/evidence seams, but
it does not yet match the operator workflow TunerStudio provides around live datalogging.

### What exists now

- raw snapshot accumulation into an in-memory `DataLog`
- CSV datalog import
- row-by-row replay into evidence services
- lightweight chart review
- dedicated trigger-log analysis/visualization services

### What TunerStudio appears to provide that we still need

Based on the decompiled sources and existing observation pass:

- named datalog profiles
- operator-selectable log fields/channels
- persisted field order and per-profile configuration
- definition-driven field metadata such as label, format, enabled condition, and lag
- logging-limit enforcement based on output-channel count and log-block byte budget
- operator-facing diagnostics when configured channels are missing or invalid
- dedicated trigger/composite/tooth log surfaces as first-class workflows, not secondary charts

### Copy-first logging plan

The near-term goal should be to copy the TunerStudio operator model before trying to invent a new
native logging stack.

Phase-appropriate target behavior:

- expose a Data Log Profile editor
- let the operator select active channels from the current runtime/output-channel catalog
- persist profile membership, order, and disabled-field state with the project
- capture live logs with start/stop semantics instead of only accumulating raw snapshots
- store enough metadata for replay to preserve units, labels, and formatting intent
- feed the resulting logs directly into evidence review, VE/WUE Analyze, and trigger-log tooling

The compatibility-first rule is:

- if the legacy definition/runtime contract names a field and provides metadata, preserve it
- if a configured field becomes invalid, surface that explicitly instead of silently dropping it

### Improve-later native logging plan

Once the project owns the firmware and file contracts, logging should improve beyond the
legacy-compatible baseline.

Preferred native direction:

- keep authored definition/schema data in `JSON5`
- keep tune/project/log-session metadata in `JSON`
- use a separate capture storage layer for high-rate sample data if plain JSON becomes too heavy

Expected gains from native logging contracts:

- self-describing channel catalogs with stable semantic IDs
- explicit units, ranges, precision, derivation, and sampling-group metadata
- versioned runtime/log schemas independent of tune-storage schemas
- selectable channel groups without legacy output-channel-count or byte-offset assumptions
- capture annotations such as sync-loss markers, burn/write events, map changes, and wizard actions
- richer autotune evidence such as per-sample trust flags, delay-compensation metadata, and
  accepted/rejected reason trails

### Custom firmware requirements for better logging

Owning the firmware should allow the logging contract to become explicit rather than inferred.

Required firmware-side improvements:

- advertise a versioned runtime-channel catalog, not just a signature string
- provide stable semantic IDs for channels so dashboards, logs, replay, and autotune do not depend
  on fragile names alone
- advertise channel metadata directly: units, valid range, precision, rate/group membership,
  and whether the value is raw, derived, or diagnostic
- support selectable-channel capture or capability-declared stream groups instead of forcing one
  fixed monolithic runtime payload
- expose sync-loss, protection, and state-change events in a log-friendly way
- define how native log sessions map to firmware stream versions so replay remains trustworthy

Practical implication:

The future logging stack should stop treating datalogs as "CSV files with some columns" and treat
them as versioned evidence sessions with known channel contracts.

## Hardware Setup Requirements

Hardware parameters must be correct before autotune evidence is trustworthy:

- **Injectors**: flow rate, dead time base, dead time voltage correction table. Wrong dead time corrupts lambda readings.
- **Ignition coils**: dwell, output mode, advance limits. Wrong dwell can damage hardware.
- **Trigger pattern**: trigger type, tooth count, missing teeth, trigger angle, secondary trigger. Wrong tooth count corrupts RPM and ignition timing.
- **Sensors**: MAP voltage-to-kPa curve, CLT/IAT thermistor curves, AFR sensor type and calibration table. Wrong sensor calibration corrupts all evidence.

Hardware setup surfaces must: (a) cluster all related parameters into a clearly labeled section, (b) flag dangerous or inconsistent configurations before write, (c) surface requires-power-cycle hints prominently.

Hardware setup surfaces must also correctly reveal dependent fields when parent features are enabled. If enabling a subsystem such as knock sensing, trigger options, or sensor modes requires additional pin/configuration fields, those fields must become available through the workflow instead of remaining hidden in a fallback parameter list.

## Guided Setup Generator Principles

The rewrite should eventually include guided setup tools that generate conservative starting values and tables from known engine and hardware facts.

Examples:

- required fuel and injector deadtime helpers from injector specs
- conservative VE table starters
- starter AFR target tables
- conservative spark-table starters based on fuel / engine / boost / cam context
- idle, cranking, afterstart, and warmup starter generators

These are setup generators, not opaque autotune:

- user supplies known facts
- app generates reviewable starting values/tables
- results appear as staged edits
- user still approves write / burn actions

Design principles:

- deterministic
- explainable
- conservative
- hardware aware
- testable
- image-assisted but never image-dependent

Forced-induction-specific generator requirements:

- support forced-induction configuration inputs:
  - turbo count
  - turbo arrangement
  - supercharger presence and type
  - boost control strategy
- support compressor map image ingestion as an optional assisted input
- use confidence-weighted airflow modeling
- handle twin turbo airflow splitting explicitly
- handle compound turbo pressure-ratio stacking explicitly
- handle sequential turbo spool transitions explicitly
- handle twin-charge torque and airflow shaping explicitly

## Guided Setup / Base Table Generation

Purpose:

- generate conservative starter tunes
- reduce first-start risk
- improve operator workflow
- improve autotune baseline quality
- allow a mix of manual, inferred, and extracted hardware inputs

Inputs when available:

- displacement
- cylinder count
- compression ratio
- RPM range
- cam specs
- NA / turbo / supercharged
- turbo / supercharger / twin-charge configuration
- turbo count and arrangement
- target boost
- intercooler presence
- intake manifold style
- fuel type
- injector flow
- injector deadtime
- fuel pressure
- ignition type
- MAP range
- AFR sensor type
- calibration intent such as first start vs drivable base
- boost control strategy

Additional optional turbo-specific inputs:

- compressor inducer / exducer if known
- turbine information if known
- A/R if known
- turbo model / part number if known
- compressor map numeric data if manually entered
- compressor map image if provided by the operator

Additional optional forced-induction inputs:

- twin turbo symmetry vs unequal sizing
- supercharger type and drive assumptions
- bypass behavior where relevant
- sequential handoff assumptions
- compound staging assumptions

Outputs:

- VE table starter
- AFR target starter
- spark starter future
- injector configuration helpers
- required fuel helpers
- boost and airflow confidence notes
- compressor-map-derived spool / efficiency guidance where confidence is sufficient

Constraints:

- conservative defaults
- explainable generation
- staged edits only
- never silent writes
- hardware validation first
- image-derived values must remain reviewable and never be treated as unquestioned truth

## Guided Base Tune Generation

- conservative VE shape heuristics should reflect engine geometry, compression, airflow path, intended RPM range, and hardware context
- camshaft influence should bias idle quality, low-speed filling, and high-RPM VE expectations conservatively
- boost influence should shape VE and target assumptions carefully, with extra caution in turbo and supercharged contexts
- compression influence should affect conservative spark and airflow assumptions without pretending to replace real evidence
- engine geometry influence should matter before any runtime evidence exists
- optional compressor map influence may inform turbo airflow and spool heuristics when the operator supplies sufficient reviewable data
- forced-induction topology should explicitly influence conservative VE shaping:
  - single turbo vs parallel twins
  - sequential twin transition zones
  - compound PR stacking
  - supercharger low-end airflow support
  - twin-charge low/mid/high RPM shaping
- confidence should be reduced explicitly when important inputs are missing, inferred indirectly, or extracted from images

Additional findings from `docs/engine-model-reference.md` and the linked Garrett / Haltech references:

- boosted modeling should separate engine VE from charge-density effects; boost alone is not a direct VE multiplier
- turbo airflow guidance should use pressure ratio, manifold temperature assumptions, intercooler effectiveness, and inlet/restriction losses explicitly
- torque-peak-informed VE shaping is a better prior than generic symmetric RPM shaping when credible torque or airflow context is known
- injector helper guidance should cross-check horsepower target, BSFC range, AFR target, injector count, and duty-cycle assumptions rather than only sizing from one formula
- boosted guidance confidence should fall when atmospheric pressure, intake depression, intercooler effectiveness, or manifold temperature are guessed instead of known

Concrete generator improvements to plan for:

- add a charge-density layer distinct from base VE shape for boosted engines
- add compressor operating-point estimation using pressure ratio + mass flow with surge/choke confidence notes
- add horsepower / airflow / injector consistency checks and warnings
- add optional torque-peak or peak-VE anchor input for better RPM-shape scaling
- add explicit altitude / barometric and inlet-restriction assumptions for turbo modeling

## Guided Generator Input Catalog

Useful inputs for setup and base-table generation include:

### Core Engine Geometry

- engine displacement
- cylinder count
- firing order
- bore and stroke
- rod length if available
- static compression ratio
- expected operating RPM range / rev limit

### Airflow And Volumetric Context

- naturally aspirated / turbo / supercharged
- single turbo / parallel twin / sequential twin / compound twin / unequal twin / supercharger / twin-charge
- target boost range
- intercooler presence
- throttle body style and approximate size
- intake manifold style
- cylinder head / valve size / flow characteristics if known
- cam specs:
  - intake duration
  - exhaust duration
  - lobe separation angle
  - intake / exhaust centerlines
  - lift
  - overlap characterization
- compressor inducer / exducer if known
- turbine information if known
- A/R if known
- turbo model / part number if known
- manual compressor map numeric data if known
- compressor map image if the operator wants assisted extraction
- boost control strategy

### Fuel System

- fuel type / ethanol content expectation
- injector flow rate
- injector deadtime / latency data
- deadtime voltage correction data
- injector count and staging strategy
- fuel pressure and regulator style
- injector location / port vs throttle-body context

### Ignition And Combustion

- ignition type (distributor, wasted spark, COP, CDI, etc.)
- coil dwell expectations / constraints
- plug type / heat range if relevant
- chamber type and known knock sensitivity
- target fuel octane

### Sensors And Hardware Context

- MAP sensor range
- AFR / lambda sensor type
- CLT / IAT sensor type or calibration family
- knock sensor presence and style
- baro strategy
- flex fuel sensor presence
- idle valve / drive-by-wire / boost-control hardware presence

### Use-Case And Calibration Intent

- first-start only vs conservative drivable base tune
- idle quality bias vs performance bias
- cruise economy bias vs boost safety bias
- emissions / smoothness priority where relevant
- target idle speed
- target lambda strategy by use case

These inputs should feed explicit, reviewable generation rules. Missing inputs should degrade gracefully to conservative defaults rather than blocking the workflow.

## Compressor Map Image Recognition

This is a planned capability for guided turbo setup, not a prerequisite for turbo-aware tuning.

Intended workflow:

- operator provides a compressor map image
- system attempts to detect axes, labels, units, speed lines, efficiency islands, surge line, and choke boundary
- system extracts approximate numeric data into a structured internal model
- system shows an operator review / correction step before any generator logic uses the extracted data
- corrected or confirmed data can then inform conservative turbo airflow and VE heuristics

Design expectations:

- image extraction is assistive, not authoritative
- extraction confidence must be surfaced
- ambiguous detections must be flagged
- manual correction must be supported
- raw extracted points and cleaned/normalized points should be distinguishable
- image ingestion should tolerate imperfect scans/screenshots but degrade gracefully
- generation should still function without a compressor map image

Data that may be extracted:

- pressure ratio axis
- corrected airflow axis
- efficiency island contours
- turbo shaft speed lines
- surge line
- choke region or right boundary
- approximate operating window relevant to the entered engine setup

Likely limitations:

- poor image quality
- skewed or cropped maps
- nonstandard units
- unlabeled axes
- overlapping annotations
- stylized manufacturer graphics
- incomplete map boundaries

Conservative usage rules:

- if extraction confidence is low, reduce weighting or ignore the map
- do not let uncertain image extraction aggressively shape the generated VE table
- prefer safe, reviewable approximations
- require operator review before use in tune generation

Extraction principles:

- extracted image data must be reviewable
- preserve provenance of values from image vs manual entry
- confidence and ambiguity must be visible
- manual override is first-class
- no silent reliance on uncertain extraction
- raw extracted points and cleaned/normalized points must remain distinguishable
- uncertain extraction must never silently dominate forced-induction modeling

## Architecture Layers

```
Qt Widgets (thin renderers, no business logic)
    <->
Presenters / View-Models (snapshot-based, immutable output)
    <->
Services (editor state, validation, autotune, operation log, evidence, generators)
    <->
Definition Compiler (INI -> stable Python models: pages, fields, filter gates, autotune metadata)
    <->
Parsers (INI, MSQ, project, datalog)
    <->
Domain Models (EcuDefinition, TuneFile, TuneValue, SessionState, EvidenceSample, GuidedSetupInputs)
    <->
Transport Layer (serial, TCP, mock, XCP)
```

## Non-Goals

- binary-compatible Java plugin loading
- updater recreation
- full cloud service parity
- pixel-perfect Swing UI cloning
- ML-based opaque autotune corrections
- support for non-Speeduino ECUs before Speeduino workflows are complete

## Completed Work

- PySide6 desktop shell and bootstrapping
- INI parser: Constants, PcVariables, TableEditor, UserDefined dialogs/panels/fields, SettingContextHelp, Menu, ConstantsExtensions, visibility expressions, VeAnalyze/WueAnalyze metadata, and `addTool`
- MSQ and project parsers
- EcuDefinition, TuneFile, TuneValue domain models
- TuningPageService: groups pages from definition, including a dedicated Hardware Setup navigation group
- TuningWorkspacePresenter: snapshot-based page state (clean/staged/invalid), staged edits, table cell edits, fill/interpolate/smooth, undo/redo, revert, write/burn, read-from-ECU, sync state, and workspace review
- OperatorEngineContext domain model and service for session-level engine facts not stored in the ECU
- reqFuel calculator snapshots and UI wiring in injector pages plus the top-level Engine Setup panel
- Engine Setup top-level tab for operator-supplied engine and induction facts, with conservative VE generation hooks
- ScalarPageEditorService: sections, fields, labels, units, help, visibility filtering
- VisibilityExpressionService: recursive descent evaluator for INI `{expr}` format
- TuningPageValidationService: missing tables, axis problems, out-of-bounds warnings
- OperationLogService: staged/reverted/written/burned entries with timestamps
- Bounds validation: immediate rejection at stage time + persistent warnings
- LocalTuneEditService: per-parameter staged values, undo/redo history
- Table editor context: help text, axis range tooltips, page diff, power-cycle warnings, and dynamic sizing
- Table editor shell modernization: compact workspace shell, staged/sync review tabs, multi-cell range editing, better selection responsiveness, and a three-panel table editor layout with dedicated header/grid/footer regions
- Table interaction parity still needs final polish: closer legacy-style row/region selection edge cases, viewport-fit behavior, and a few spreadsheet-style edit/apply refinements remain pending
- Logging/replay parity remains incomplete, but Phase 5 is now materially underway: freshness-aware evidence summaries, operation-evidence grouping, replayable evidence bundle snapshots, evidence history review, pinned-vs-latest comparison, trigger-log analysis, CSV datalog import/replay, lightweight chart review, and active tuning-page/table evidence hooks now exist; formal sample gating, richer timeline navigation, and VE Analyze-ready evidence evaluation are still pending
- Sync mismatch detection: signature mismatch, page-size mismatch, ECU-vs-tune mismatch, stale staged changes
- Hardware setup validation scaffolding: injector / ignition / trigger / sensor checks surfaced as warnings and errors, plus first summary cards for hardware pages
- Hardware-setup completeness is still pending for feature-dependent field visibility, especially pin/sensor assignment flows when subsystems are enabled
- Transport, protocol, mock, and XCP scaffolding
- Runtime polling scaffolding
- Native Speeduino serial controller client for legacy raw serial commands: connect, runtime poll, page read, parameter write, and burn
- project reopen and auto-connect now preserve offline-first startup by probing saved live profiles off the UI thread
- OutputChannels parsing with runtime field offsets for live telemetry decoding
- Firmware catalog, board detection, preflight, and flash helpers
- Unit and integration tests across parsers, comms, tuning services, visibility, flashing, workspace startup, evidence/replay services, and fixture-based compatibility checks (currently 1054 collected tests)

## Pending Work (ordered by roadmap priority)

1. Guided hardware-setup surfaces (injector, ignition, trigger, sensor calibration) (Phase 4)
2. Persist operator engine context and guided-setup progress through project/session restore where appropriate (Phase 4 / 8)
3. Formalize the new runtime evidence pipeline into VE Analyze-ready sample gating, replay filtering, and active-page review logic (Phase 5 / 6)
4. Baseline VE Analyze autotune (Phase 6)
5. Enhanced autotune with transparency and confidence scoring (Phase 7)
6. Dashboard rendering parity and DashTuningPanel pattern (Phase 8)
   - split explicitly into:
     - gauge-cluster runtime surface
     - dashboard layout load/save and project linkage
     - DashTuningPanel-style embedded editing
     - fullscreen/operator dash mode
7. Final table editor parity polish: footer density, axis-strip continuity, and alignment cleanup (Phase 8)
8. Table interaction parity with TunerStudio: multi-cell/multi-row selection, keyboard-driven editing, and repeated apply/fill workflows (Phase 8)
9. Logging/replay workflow parity: deeper datalog replay navigation, timeline scrubbing, filter/gate inspection, tooth/composite/trigger logs, and chart review surfaces with stronger page-aware semantics (Phases 5 and 8)
10. Guided setup/base-table generators from engine/injector/fuel/cam/airflow/boost specs, with optional compressor map assistance (cross-phase)
11. Extend workspace/session restore, quick-open, command palette, and recent-project workflows further where needed (Phase 8)
12. Bench workflow integration for board/firmware/tune recovery (Phase 9)
