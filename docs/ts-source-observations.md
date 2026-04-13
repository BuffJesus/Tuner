# TunerStudio Source Observations

Observations extracted from the decompiled TunerStudio source tree at
`C:\Users\Cornelio\Desktop\Decompiled\TunerStudioMS` and the clean plugin API at
`C:\Users\Cornelio\Desktop\Decompiled\TunerStudioPluginAPI`.

---

## Parameter model

From `TunerStudioPluginAPI/com/efiAnalytics/plugin/ecu/ControllerParameter.java`:

- Every parameter has a `paramClass`: `"bits"`, `"scalar"`, or `"array"`.
- Values are stored uniformly as `double[][]` regardless of class. A scalar is a 1×1 array;
  `getScalarValue()` returns `arrayValues[0][0]`. String-valued parameters carry a separate
  `stringValue` field.
- Shape is a `java.awt.Dimension` (width = columns, height = rows).
- Metadata fields: `units`, `min`, `max`, `decimalPlaces`, `optionDescriptions` (for bits/enums).
- Change notifications use a subscription model: `ControllerParameterServer.subscribe(configName,
  paramName, listener)`. Unsubscription is by listener reference, not by name.

### Implications for the Python rewrite

The Python `ControllerParameter` equivalent should represent scalars, arrays, and bits with a
single value container (e.g. `numpy` array or nested list). The subscription model maps cleanly
to a signal/slot pattern. `optionDescriptions` is the runtime source for enum label lists — do
not source these from INI alone at display time.

---

## Output channels

From `OutputChannel.java` and `OutputChannelServer.java`:

- Each output channel carries: `name`, `units`, `formula`, `minValue`, `maxValue`.
- `formula` is present at the API level, confirming that output channel values in TunerStudio
  are computed expressions, not raw bytes — consistent with the INI `outputChannels` section.
- Subscription is per `(configName, channelName)` pair with an `OutputChannelClient` callback.
  Unsubscription is by client reference or by config name (bulk).

---

## Table and curve axis tracking (live crosshair)

From `UiTable.java` and `UiCurve.java`:

- `UiTable` holds: `name`, `xParameterName`, `yParametterName`, `zParameterName` (the table
  parameter itself), plus `xOutputChannel` and `yOutputChannel`.
- The live crosshair on a table is driven by output channels (real-time ECU values), not by the
  parameter values. The x/y output channels are what TunerStudio maps to RPM and load axes at
  runtime.
- `UiCurve` similarly carries x/y output channel names for live trace, plus separate lists of
  x and y parameter names (a curve can have multiple parameters per axis).

### Implications for the Python rewrite

The table crosshair and curve trace need two separate data paths: one from the tune (static
parameter values that define the axes) and one from the output channel stream (live ECU position).
These must not be conflated in the editor model.

---

## Burn vs write separation

From `BurnExecutor.java`, `ControllerParameterServer.java`, and `OnlineExecution.java`:

The plugin API formalises four distinct operations:

| Operation | API call | Effect |
|---|---|---|
| Update parameter | `ControllerParameterServer.updateParameter(config, param, value)` | Writes to ECU RAM |
| Burn | `BurnExecutor.burnData(configName)` | Persists RAM to flash |
| Go online | `OnlineExecution.goOnline()` | Establishes connection |
| Go offline | `OnlineExecution.goOffline()` | Tears down connection |

`burnData` is also exposed directly on `ControllerParameterServer` as a convenience, but the
`BurnExecutor` interface makes the separation explicit.

---

## Editor UI architecture

From `com/efiAnalytics/ui/BinTableView.java` and
`com/efiAnalytics/tuningwidgets/panels/SelectableTablePanel.java`:

- `BinTableView` extends `javax.swing.JTable`. It implements `ClipboardOwner` and
  `HierarchyListener`, confirming clipboard copy/paste is built into the table widget directly.
- It carries its own `DecimalFormat`, font management (normal and bold), and color/rendering state.
- `SelectableTablePanel` wraps a `BinTableView` with a "Select a table" dropdown button that
  opens a popup selector. The panel fires `panelSelectionChanged` when the user picks a different
  table — the selection drives a full reinitialisation of the embedded view.
- `TableCellCrossHair` (`tuneComps/`) is a separate component layered over the table to render
  the live ECU position indicator.

### Implications for the Python rewrite

The Python `QTableWidget`-based table editor should keep the crosshair overlay as a separate
concern from the cell editing widget. The "selectable table" pattern (dropdown selector + embedded
editor) is a confirmed TunerStudio UI pattern worth preserving for the table-selector surfaces.

---

## Dashboard architecture

From `com/efiAnalytics/apps/ts/dashboard/`:

Gauge rendering uses a painter/renderer strategy pattern. The `Gauge` widget delegates to a
`GaugePainter` interface. Confirmed painter implementations:

- `AnalogGaugePainter`, `RoundAnalogGaugePainter`, `AnalogMovingBarGaugePainter`
- `AnalogBarPainter`, `HorizontalBarPainter`, `HorizontalDashedBar`, `VerticalBarPainter`,
  `VerticalDashedBarPainter`
- `BasicReadoutGaugePainter` (numeric readout)
- `BulbIndicatorPainter`, `LedPainter`, `RectangleIndicatorPainter`
- `HistogramPainter`
- `AsymetricSweepRenderer`

Other confirmed dashboard component types: `DashLabel`, `HtmlDisplay`, `Indicator`,
`SingleChannelDashComponent`, `SelectableTableComponent` (table view embedded in dashboard),
`DashTuningPanel` (tuning controls embedded directly in the dashboard surface).

`DashTuningPanel` confirms that inline tune editing within a dashboard is a deliberate product
feature in TunerStudio, not an incidental overlap.

From `com/efiAnalytics/apps/ts/dashboard/DashTuningPanel.java` specifically:

- the component is a small dashboard shell with a header row, a `#` settings-selection button,
  and a scrollable embedded settings panel
- pressing the button opens a popup built from the active ECU configuration menu, then swaps the
  selected settings panel into the scroll viewport

### Implications for the Python rewrite

Dashboard-hosted tune editing should be modeled as a focused embedded editor with explicit page
selection, not as a full duplicate of the main workspace. The current rewrite's dashboard plans
should preserve this "small selector + embedded settings panel" interaction pattern.

---

## Datalog profile model

From `aa/b.java`, `aC/h.java`, `aC/r.java`, and `W/ab.java`:

- datalog configuration is definition-driven, not just ad-hoc CSV export
- each datalog field carries:
  - output-channel name
  - log header label
  - format string
  - enabled condition
  - optional lag expression
- TunerStudio logs configuration and parsing problems during project opening and treats bad
  datalog field references as configuration issues worth surfacing

### Implications for the Python rewrite

The rewrite should treat datalog profiles as first-class project/configuration data. Replay and
log review work should not stop at "open CSV and chart it"; it should preserve field metadata,
enable conditions, formatting intent, and configuration diagnostics.

Additional logging-surface observations from `com/efiAnalytics/tunerStudio/panels/g.java` and
`com/efiAnalytics/tuningwidgets/panels/ae.java`:

- TunerStudio ships a dedicated Data Log Profile Editor with named profiles, add/delete actions,
  help integration, and persisted per-profile disabled-field state
- replay/log field selection is operator-configurable, not fixed to a tiny hard-coded chart set
- active log-field selection is constrained by both:
  - maximum number of output channels that may be logged
  - total log data block size / byte budget
- invalid field references and output-channel problems are treated as configuration/runtime
  issues worth surfacing to the operator

### Implications for the Python rewrite

To copy the TunerStudio workflow credibly, the project needs more than CSV import:

- named datalog profiles
- selectable logging channels/fields
- persisted field-order and enable/disable state
- field-budget validation against firmware/logging constraints
- operator-facing diagnostics when a configured field cannot be resolved or captured

This should remain definition-driven for legacy compatibility. Once the project owns the firmware
and file contracts, the same product seam can evolve into a native logging schema rather than an
INI-defined field list.

---

## Trigger/composite/tooth log surface

From `com/efiAnalytics/tunerStudio/panels/TriggerLoggerPanel.java` and related panel classes:

- trigger logging is implemented as a dedicated multi-control panel, not a tiny popup widget
- the panel owns:
  - a graph/visualization area
  - a data table
  - split-pane layout
  - multiple selectors and toggles
  - scroll/navigation helpers and playback-style controls

### Implications for the Python rewrite

Tooth/composite/trigger logs should land as dedicated top-level or tool-level surfaces with their
own controls and evidence views. A simple chart embedded beside tuning pages would miss an
important part of the TunerStudio workflow.

---

## Forced-induction modeling gaps in TunerStudio

Based on the decompiled source currently referenced for reconstruction, there is no clear sign that TunerStudio itself provides a dedicated forced-induction modeling layer for:

- turbo configuration topology
- twin turbo arrangements
- sequential turbo arrangements
- compound turbo arrangements
- supercharger-specific airflow modeling
- twin-charge modeling
- compressor map ingestion from images

That means the Python rewrite can extend beyond TunerStudio here without breaking the core operator model, as long as the implementation stays conservative and reviewable.

### Implications for the Python rewrite

The rewrite should add:

- an explicit forced-induction modeling layer
- optional compressor map ingestion and review
- confidence-weighted VE generation

It should not assume perfect OCR or image extraction, and it should not make compressor-map-assisted generation mandatory for turbo support.

---

## Plugin system

From `ApplicationPlugin.java`:

Three plugin display types:
- `DIALOG_WIDGET = 1` — shown as a dialog
- `PERSISTENT_DIALOG_PANEL = 2` — shown as a persistent panel
- `TAB_PANEL = 4` — shown as a tab

Plugin lifecycle: `initialize(ControllerAccess)` → `displayPlugin(configName)` →
`getPluginPanel()` → `close()`.

Plugin API version is `1.0`. `getRequiredPluginSpec()` allows plugins to declare a minimum API
version; the host should gate loading on this.

---

## Cloud services

From `efiaServicesClient/com/efianalytics/ecudef/`:

TunerStudio ships a SOAP web service client for the efiAnalytics cloud with these operations:

- `FindEcuDefForSerialSignature` — looks up an ECU definition file by the firmware's serial
  signature string (the primary auto-detection path)
- `FindEcuDefForQueryString` — text-based ECU definition search
- `GetEcuDefinition` — fetches a specific definition file by ID
- `GetAllKnownFirmwares` — lists all known firmware identifiers on the cloud
- `SubmitEcuDefFile` — uploads a user-contributed ECU definition

The `FirmwareIdentifier` type used across these calls is what TunerStudio sends when it detects
a connected ECU and tries to find a matching INI automatically.

### Implications for the Python rewrite

Cloud ECU definition lookup is milestone 10 (optional remote services) and is explicitly
non-goal for phase 1. When it does land, the signature-based lookup path is the primary one to
match; the text-search path is secondary.

---

## Third-party dependencies and what they imply

| Library | Version | Likely use in TunerStudio |
|---|---|---|
| `commons-math3` | 3.6.1 | Table interpolation, smoothing, and VE Analyze math |
| `commons-net` | 3.6 | TCP/UDP transport, FTP for remote file access |
| `gson` | 2.9.0 | JSON serialisation for cloud API payloads |
| `icepdf-core/viewer` | — | In-app PDF rendering (help documentation) |
| `zip4j` | 1.3.1 | Project/tune file packaging (ZIP-based project files likely) |
| `tinylaf` | — | Custom Swing look-and-feel |
| `jfxrt` / `jfxswt` | — | JavaFX present but likely unused in core tuning path |

`zip4j` bundled at this version is a strong signal that project files or tune archives are
ZIP-based. This is worth testing against the `.msq` and project file formats before writing the
Python project packager.
