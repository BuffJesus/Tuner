# Tuner — Operator Manual

> First pass of the operator manual. Covers install, project setup,
> connecting to a Speeduino ECU, and each tab's role. Written for
> someone who knows their way around an engine but has not tuned
> before.

## Contents

1. [Install and first launch](#install-and-first-launch)
2. [Projects, definitions, and tunes](#projects-definitions-and-tunes)
3. [Connecting to an ECU](#connecting-to-an-ecu)
4. [The TUNE tab — editing values](#the-tune-tab--editing-values)
5. [Write to RAM, Burn to Flash, Power Cycle](#write-to-ram-burn-to-flash-power-cycle)
6. [The SETUP tab — guided hardware setup](#the-setup-tab--guided-hardware-setup)
7. [The Engine Setup Wizard](#the-engine-setup-wizard)
8. [LIVE / LOGGING / TRIGGERS / FLASH / ASSIST](#live--logging--triggers--flash--assist)
9. [Keyboard shortcuts](#keyboard-shortcuts)
10. [Troubleshooting](#troubleshooting)

---

## Install and first launch

1. Copy `tuner_app.exe` and the bundled DLLs to any folder.
2. Double-click `tuner_app.exe`. On first launch you see the Startup
   picker — **Open Last Project**, **New Project**, **Open Existing**,
   or **Connect & Detect**.
3. If you have no project yet, pick **New Project** (see next section).
4. If the ECU is on the bench, pick **Connect & Detect** — the app
   probes serial ports at 115200 and auto-fills the connection if it
   finds a Speeduino signature.

## Projects, definitions, and tunes

A project bundles three files:

- **`.tunerdef` / `.ini`** — the *definition*. Describes every tunable
  parameter the firmware exposes. `.tunerdef` is the native format;
  `.ini` is the legacy TunerStudio format, still supported.
- **`.tuner` / `.msq`** — the *tune*. The actual parameter values for
  your engine. `.tuner` is the native JSON format; `.msq` is legacy
  XML, still supported.
- **`.tunerproj`** — optional wrapper that points at both of the
  above and remembers project-level flags (active INI settings,
  firmware signature, friendly name).

**File → New Project** creates a directory, writes a `.project` file,
and optionally copies a starter tune into the project directory. If
you pick a tune that lives outside the project directory, the app
copies it in automatically so future saves don't overwrite the
source file.

**File → Open Project** opens a `.tunerproj`, a `.tuner`, or an
`.msq` directly. The app reloads the whole workspace to pick up the
new definition and tune.

**File → Save Tune** (Ctrl+S) saves the current tune to disk. First
save opens a dialog defaulting to the project directory; subsequent
saves write in place.

**File → Save Project** (Ctrl+Shift+S) writes a `.tunerproj` sidecar.
The dialog defaults to the project directory, then to the last-used
save location on later invocations.

## Connecting to an ECU

**File → Connect to ECU** opens the Connection dialog.

### Serial (USB to the Teensy / Mega / STM32 directly)

1. Pick **Serial** from the Transport dropdown.
2. Select the COM port. If the right port isn't listed, click the
   refresh icon.
3. Click **Auto** to have the app probe every COM port at 115200
   for a Speeduino signature and auto-fill the port + baud when it
   finds one.
4. If Auto finds nothing, manually pick the port + baud. 115200 is
   the Speeduino default.
5. Click **Connect**.

The status bar shows the live signature once the handshake completes.
The sidebar's connection indicator turns green.

### TCP / WiFi (via Airbear bridge)

1. Pick **TCP / WiFi** from the Transport dropdown.
2. Leave the Host field as `speeduino.local` if your Airbear uses
   mDNS; otherwise type the IP.
3. Click **Scan Network** to auto-discover devices broadcasting
   on the EcuHub UDP discovery port.
4. Click a discovered row to auto-fill host + port, then **Connect**.

Connection settings (transport / port / baud / host) persist across
sessions.

## The TUNE tab — editing values

The TUNE tab is where you read and edit every tunable parameter.

### Tree navigation

The left panel is a tree grouping every tunable page by category:

- **Filter toggles** above the search box — **Scalars** / **Tables** /
  **Curves** — hide leaves of each kind. Useful when you want to see
  only the tables or only the curves on a large definition.
- **Search field** — types filter the tree by page name.
- **Ctrl+K** opens the command palette — search pages, actions,
  parameters.

### Scalar pages

Scalar pages show one field per row with a label, editor widget, and
units. Most fields accept a number; some accept a dropdown selection.
Edit the value and press Enter (or Tab) to stage the change.

- An **amber border** on the editor means the value was clamped to
  the parameter's min/max range. Hover for the clamp tooltip.
- A small **⟳ chip** next to the label means the parameter requires
  a power cycle to take effect after burning. See [Power Cycle](#write-to-ram-burn-to-flash-power-cycle).

### Table pages

Table pages show a heatmap (rows = load, columns = RPM). Cell colors
go from green (low) to red (high).

- **Click** a cell to select it.
- **Double-click** to edit inline.
- **Drag** to select a rectangular range.
- **+ / -** increment / decrement selected cells by 1.
- **I** interpolates a selection between its corners.
- **S** smooths the selection.
- **F** fills the selection with the anchor value.
- **Ctrl+C / Ctrl+V** copy/paste tab-delimited.
- **Ctrl+Z / Ctrl+Y** undo / redo.

The **Operating Point** crosshair (white dot with red outline)
overlays the cell the engine is currently running in when connected.

### Curve pages

Curve pages show a line chart with draggable vertices plus an
editable value table below.

- **Click a vertex** and drag vertically to change that bin's Y.
- Or edit the value table — chart and table stay in sync.
- **Smooth** — 3-point moving average, endpoints held.
- **Interpolate** — linear ramp from the first Y to the last Y.
- **Revert** — restore the original values from when the page opened.

## Write to RAM, Burn to Flash, Power Cycle

Staged edits flow through three explicit steps:

1. **Write to RAM** (Ctrl+W). The app sends every staged change to
   the ECU's volatile memory. The engine picks them up immediately.
   The values are lost if the ECU is power-cycled.
2. **Burn to Flash** (Ctrl+B). The ECU copies RAM to flash. Values
   survive a power cycle. This is destructive — the old flash
   contents are overwritten. Takes ~1 second per changed page.
3. **Power cycle** (optional). Some parameters — cylinder count,
   trigger pattern, injector layout, a few others — only take effect
   after the ECU reboots. The app tracks these and:
   - Tags them with a ⟳ chip on the edit row.
   - Shows a status toast after Write: `⟳ 3 change(s) require a
     power cycle after burn`.
   - Offers **automatic reboot** after a successful Burn when the
     firmware supports `cmdstm32reboot` (STM32 boards). Answers
     **Yes** to send the reset command and reconnect.
   - Prompts you to manually disconnect and reconnect power for
     AVR / Teensy firmware.

**Ctrl+R** opens the Review dialog — a scrollable list of every
staged change with its base and new values side-by-side. From here
you Write, Burn, or Revert All.

### Write / Burn feedback

- **Success**: status-bar toast for 5-10 seconds — `✅ Wrote 14
  parameter(s) to ECU RAM`.
- **Partial failure**: modal warning listing the count + first
  error message. The Review dialog stays open so you can retry.
- **Offline** (no ECU connected): changes still stage locally, with
  an info toast `ℹ Offline — 14 change(s) staged (not written to ECU)`.

## The SETUP tab — guided hardware setup

The SETUP tab has two halves: **table previews** (VE, AFR, Spark,
Idle, WUE, Cranking — each generated from your engine's config) and
**six guided cards** for hardware configuration.

The six cards are:

### 1. Engine Advanced

- **Stroke Type** — Four-stroke / Two-stroke.
- **MAP Sampling** — Instantaneous / Cycle Average / Cycle Minimum /
  Event Average. Cycle Average is recommended for 3+ cylinders.
- **Fuel Trim Master** — master on/off for the four fuelTrimN tables.

### 2. TPS Calibration

- **TPS Min (ADC)** — raw ADC with throttle fully closed. Press
  **Capture closed** to read the current tpsADC reading from the
  ECU.
- **TPS Max (ADC)** — raw ADC at wide-open throttle. Press
  **Capture WOT** with the pedal pinned. **Engine must be OFF for
  safety.**

Capture buttons disable when offline; manual entry stays available
for multimeter probing.

### 3. Hardware Outputs (IAC + Fan)

- **IAC Algorithm** — None, On/Off, PWM Open/Closed, Stepper
  Open/Closed, combined.
- **Fan Mode** — Off / On-Off / PWM.
- **Fan On Temp (°C)** — coolant temperature at which the fan
  activates. Typical 90-95°C for street.
- **Fan Hysteresis (°C)** — temperature drop before the fan turns
  off. 5-8°C stops rapid cycling.

### 4. Flex Fuel Sensor

- **Enable** — Off / On. Enables ethanol-content-based fuel and
  timing adjustments.
- **Low Frequency (E0, Hz)** — sensor output at 0% ethanol.
- **High Frequency (E100, Hz)** — sensor output at 100% ethanol.
- **GM / Continental preset** button — one-click set 50 / 150 Hz
  for the standard sensor.

### 5. Safety & Protection

**Knock detection** (use only with wired sensor + dyno-verified
threshold):

- **Knock Detection Mode** — Off / Digital / Analog.
- **Knock Threshold (V)** — voltage above which a knock event
  triggers.

**AFR Protection** (fuel cut when AFR deviates from target):

- **Mode** — Off / Fixed / Table.
- **Deviation (AFR)** — lean deviation before cut. Typical 1.0-2.0.
- **Cut Delay (seconds)** — time AFR must stay outside the window.
  0.5-1.0 s suppresses one-shot spikes.
- **Min MAP / Min RPM / Min TPS** — protection arms only when all
  three are exceeded, so idle / overrun never triggers a cut.
- **Reactivation TPS** — fuel resumes when throttle drops below this.

### 6. Advanced Turbo Parameters

Only shown when boostEnabled = On. Feeds the Compressor-Map
Modeling card directly below.

- **Surge Flow (lb/min)** — min flow from compressor datasheet.
- **Choke Flow (lb/min)** — peak flow before stall.
- **Max Pressure Ratio (PR)** — peak PR before efficiency collapses.
- **Turbine A/R Ratio** — informational (not used in map math).

Edit any field and revisit the SETUP tab to see the compressor map
recompute against your turbo's real envelope.

## The Engine Setup Wizard

**File → New Project** optionally launches the Engine Setup Wizard
on accept. The wizard walks through six steps:

1. **Engine** — cylinders, displacement, CR, cycle (4/2-stroke),
   load algorithm (Speed Density / Alpha-N), board, injector count
   + layout, calibration intent (first-start vs drivable-base).
2. **Induction** — NA / turbo / twin-turbo / supercharged, boost
   target, intercooler.
3. **Injectors** — 18 preset injectors, dead time, stoich, reqFuel
   preview.
4. **Trigger & Ignition** — teeth, missing teeth, spark mode, coil
   presets.
5. **Sensors** — O2 type, wideband preset, MAP sensor preset, CLT /
   IAT thermistor presets, baro preset.
6. **Review** — summary card. Click **Finish** to generate and stage
   a complete base tune (VE, AFR, Spark, WUE, Cranking, Idle RPM,
   plus every supporting scalar).

The generated values are **staged**, not written. Review on the
TUNE tab, then Write + Burn when ready.

## LIVE / LOGGING / TRIGGERS / FLASH / ASSIST

- **LIVE** — animated dial gauges + number cards driven by the INI's
  `[FrontPage]` + `[GaugeConfigurations]`. Connect to see real data;
  offline shows the mock. Fullscreen via F11 for bench/driver view.
- **LOGGING** — capture runtime data to CSV. Profile picker + channel
  checkboxes let you select which channels to record. Start / Stop /
  Clear / Save buttons. Import a CSV to replay it against the current
  tune.
- **TRIGGERS** — capture tooth / composite log from the ECU, or
  import a CSV. The scope widget shows stacked traces with time axis;
  the analysis panel highlights sync / tooth-spacing findings.
- **FLASH** — preflight checklist + firmware file picker + flash
  button. Teensy boards use the embedded HID flasher (no external
  tool needed). Mega2560 and STM32 spawn avrdude / dfu-util.
- **ASSIST** — VE Analyze (turn driving data into VE corrections),
  WUE Analyze (warmup-enrichment corrections), Virtual Dyno (torque /
  HP estimate from logged data).

## Keyboard shortcuts

Press **F1** at any time for the full cheat sheet.

### Navigation

| Shortcut | Action |
|---|---|
| Alt+1..8 | Jump to sidebar tab 1-8 |
| Ctrl+K | Command palette (search pages + actions) |
| F1 / ? | Open this shortcut cheat sheet |

### Tune workflow (TUNE tab)

| Shortcut | Action |
|---|---|
| Ctrl+R | Open Review dialog (staged changes) |
| Ctrl+W | Write staged changes to ECU RAM |
| Ctrl+B | Burn current RAM contents to flash |
| Ctrl+Z / Ctrl+Y | Undo / redo (on tables) |
| Ctrl+C / Ctrl+V | Copy / paste table cells |
| + / - | Increment / decrement selected table cells |
| I | Interpolate selected table range |
| S | Smooth selected table range |
| F | Fill selected cells with anchor value |

### Files

| Shortcut | Action |
|---|---|
| Ctrl+N | File → New Project |
| Ctrl+O | File → Open Project |
| Ctrl+S | Save Tune |
| Ctrl+Shift+S | Save Project |
| F11 | Toggle fullscreen dashboard (from LIVE tab) |

## Troubleshooting

### "No Speeduino detected" on Connect → Auto

- Is the USB cable plugged into a data-capable port (not charge-only)?
- Is the ECU powered? Check the 12V supply.
- Is the baud rate unusual? Auto-detect only tries 115200. If your
  firmware uses 230400 / 57600 / 9600, set baud manually.
- Is another program holding the port? Close TunerStudio, Arduino
  IDE, or any other serial monitor.

### "Schema mismatch" warning on Burn

The tune was built against a different firmware schema fingerprint
than the connected ECU is running. Either:

- Reconnect to the firmware the tune was built for, OR
- Regenerate the tune by opening a project from the current
  firmware's `.ini` / `.tunerdef`.

Burning anyway could write this tune into a firmware build it wasn't
designed for. The app blocks the burn.

### Values changed but no effect on the engine

Check the ⟳ power-cycle chip on the edited parameter. Some settings
(cylinder count, trigger pattern, injector layout, fan pin, reqFuel)
only take effect after the ECU reboots. Either:

- Let the app auto-reboot after Burn (STM32 firmware), or
- Disconnect and reconnect ECU power manually.

### Curve / table not updating on the chart

The chart and the value table edit the same list — one should
update the other. If they fall out of sync, navigate away and back
to the page to force a redraw.

### SETUP tab shows weird values (VE Table looks wrong)

The previews read your loaded tune's `boostEnabled`, `compressionRatio`,
and other scalars. If no tune is loaded, you see conservative NA
defaults. Run the Engine Setup Wizard (File → New Project or the
SETUP tab's wizard button) to populate real values.

### Auto-reboot does nothing

Only STM32 firmware exposes `cmdstm32reboot`. On AVR (Mega) and
Teensy, the app falls back to a "please power-cycle manually" prompt.
Disconnect and reconnect the 12V supply to the ECU.

---

## Further reading

Other docs in this tree cover different angles:

- **`ux-design.md`** — the design philosophy ("guided power") and
  per-surface design goals. Worth reading if you want to understand
  *why* the app organizes information the way it does, rather than
  how to use it.
- **`architecture.md`** — how the app is built internally (layer
  boundaries, service model, `tuner_core` + Qt app split). Useful if
  you're building against the app or contributing.
- **`engine-model-reference.md`** — the math behind the SETUP-tab
  table generators (VE / AFR / spark / turbo modeling). Useful if
  you want to understand what the "first-start" generators assume
  and where their numbers come from.
- **`tuning-roadmap.md`** — living roadmap with phase status,
  parity tracker, and the current critical path.

---

*This manual is a first pass. The tabs' specifics will evolve —
check the PR history and the in-app context hints (every TUNE-tab
page has a one-line hint at the top) for details not yet covered
here.*
