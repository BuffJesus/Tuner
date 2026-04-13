# tuner-py

Python PySide6 rewrite of a TunerStudio-like desktop tuning application, currently aimed at Speeduino-first workflows.

## Current State

This is a working desktop application, not a scaffold. The repo contains:

- definition-driven tuning pages compiled from Speeduino-style `.ini` metadata
- offline tune editing plus live Speeduino serial and TCP/WiFi read/write/burn/runtime support on the legacy raw protocol path
- a presenter-driven tuning workspace with navigator, scalar editors, table editors, 1D curve editors, sync state, workspace review, and parameter catalog
- Engine Setup and Hardware Setup Wizard flows for engine, induction, injectors, trigger, sensors, and setup-oriented helper actions
- staged starter generators for VE, spark, AFR, idle RPM, WUE, cranking, and ASE
- VE Analyze and WUE Analyze service layer, accumulation, review, proposal staging, and workspace UI integration
- runtime evidence, evidence history, pinned-vs-latest comparison, CSV datalog replay, table/page evidence hooks, and trigger-log analysis
- firmware catalog, target detection, flash preflight, and AVR/Teensy/STM32 flashing helpers
- command palette, quick-open, recent-project reopen, and offline-first reconnect behavior
- INI preprocessor for `#if`/`#else`/`#endif`/`#set`/`#unset` directives, with project-level `active_settings` support; validated against the Speeduino release INI
- INI gauge catalog (`[GaugeConfigurations]`) and front-page layout (`[FrontPage]`) fully parsed and consumed by the dashboard config dialog
- live trigger logger protocol: tooth and composite log capture from connected ECU, binary decode, CSV hand-off to the analysis pipeline
- HTTP live-data API: opt-in background HTTP server (port 8080) exposing runtime channels as JSON for browser dashboards, Raspberry Pi, or phone on the local network

**Dashboard** gauge cluster is a first-class tab: 11 default Speeduino gauges (RPM, MAP, TPS, AFR, coolant, IAT, battery, advance, VE, dwell, PW1), load/save layout as JSON, project-associated default path, live update on every runtime poll, fullscreen operator mode, and per-gauge configuration auto-filled from the INI gauge catalog (title, source channel, units, kind, min/max, color zones from warn/danger thresholds). Gauges can be rearranged by drag-and-drop.

**Logging** is a first-class top-level tab: profile quick-switch dropdown with add/delete, Start/Stop/Clear/Save Log, configurable polling interval (250ms–5s), real-time capture-to-file, and Datalog Import & Replay. Profile collection persisted as a `.logging-profile.json` sidecar alongside the project file.

**TCP/WiFi transport**: `TcpTransport` with Speeduino new-protocol framing (`[u16 LE len][payload][u32 LE CRC32]`). "Connect via WiFi" in the Runtime panel supports mDNS `speeduino.local` (Airbear **v0.2.0**, port 2000). All data commands framed over TCP; Q/S handshake stays raw. Airbear 0.2.0 can now return `RC_TIMEOUT (0x80)` or `RC_BUSY_ERR (0x85)` on the TCP path — the latter when dashboard polling holds the UART mutex in the new `DASH_ECHO` dual-mode — so the transport layer should recognise these as recoverable errors and retry rather than treat them as framing corruption.

## Top-Level App Surfaces

`MainWindow` currently exposes these primary tabs:

- `Overview`
- `Tuning`
- `Engine Setup`
- `Runtime`
- `Logging`
- `Dashboard`
- `Trigger Logs`
- `Flash`

The intent is TunerStudio-like workflow fidelity rather than a generic parameter browser:

1. open or reopen a project
2. load definition and tune
3. stay offline or connect to a controller (serial or WiFi/TCP)
4. inspect runtime channels and evidence
5. edit parameters, tables, and curves
6. review staged changes
7. write to RAM
8. burn to flash

## Architecture Snapshot

The app follows a strict inward-dependency model:

- `domain` — typed state and ECU models
- `parsers` — INI/MSQ/project ingestion
- `transports` — serial/TCP/UDP/mock I/O
- `comms` — protocol framing, CRC, and controller clients
- `services` — business rules and orchestration
- `plugins` — extension seams
- `ui` — thin PySide6 widgets

Notable service seams:

- `DefinitionLayoutService` — compiles loose INI dialogs/panels into stable editor-facing page layouts
- `TuningPageService` and `TuningWorkspacePresenter` — drive the tuning workspace state machine
- `TableEditService` — owns table transforms and undo/redo
- `CurvePageService` — builds 1D curve editor pages from `[CurveEditor]` definitions
- `HardwareSetupValidationService`, `HardwareSetupSummaryService`, `HardwareSetupGeneratorContextService` — support setup flows
- `SurfaceEvidenceService`, `EvidenceReplayService`, `DatalogReplayService`, `TableReplayContextService` — evidence/replay pipeline
- `LiveVeAnalyzeSessionService`, `LiveWueAnalyzeSessionService` — live autotune analysis
- `LiveTriggerLoggerService` — decodes binary tooth/composite log buffers from the ECU
- `LiveDataHttpServer` — opt-in HTTP server exposing live channels as JSON
- `DatalogProfileService`, `LiveCaptureSessionService` — logging pipeline

## Long-Term Direction

The current Python application remains the reference implementation while workflow, file semantics, and TunerStudio-compatibility edges are still being discovered against real firmware, INI, MSQ, and decompiled TunerStudio inputs.

Once the core product is stable:

- lock down the product model with stronger fixture-backed validation against real release artifacts
- define an owned tune/definition/project contract instead of staying permanently tied to external formats (`JSON5` for authored definitions, `JSON` for tune/project data)
- evaluate a native shared core (C++ leading candidate) for future protocol, parsing, validation, and packaging work
- keep autotune deterministic and reviewable first, then consider ML only for assistive roles

The repo roadmap and backlog focus on landing the current Python product first. Native-port and custom-format work is intentionally post-roadmap.

## Tests

Current collected suite: `2445` tests (Python) + `1063` tests (C++ doctest).

Quick commands:

```bash
pip install -e ".[dev,comms,math,graphs,flash]"
python main.py
python -m pytest tests/
python -m pytest --collect-only -q
```

## Key Docs

- [docs/architecture.md](/D:/Documents/JetBrains/Python/Tuner/docs/architecture.md)
- [docs/tuning-roadmap.md](/D:/Documents/JetBrains/Python/Tuner/docs/tuning-roadmap.md)
- [docs/implementation-prompt.md](/D:/Documents/JetBrains/Python/Tuner/docs/implementation-prompt.md)
- [docs/protocol-notes.md](/D:/Documents/JetBrains\Python\Tuner\docs\protocol-notes.md)
- [docs/ts-source-observations.md](/D:/Documents/JetBrains/Python/Tuner/docs/ts-source-observations.md)
