# UX Design: Beyond TunerStudio

## Design Philosophy

TunerStudio is powerful but assumes expertise. Every surface shows raw parameter names, cryptic units, and walls of numbers. A first-time Speeduino user opens it and faces 50+ menu items with no guidance on what to change or in what order.

Our opportunity: **guided power**. The same information TunerStudio shows, organized around what the operator is trying to accomplish — not around the firmware's internal page/offset structure. Power users still get direct access to everything; new users get context and guidance that disappears as they gain confidence.

### Core Principles

1. **Progressive disclosure** — show what matters now, reveal depth on demand
2. **Context over structure** — organize by task, not by firmware page
3. **Explain as you go** — every surface should help the operator understand why, not just what
4. **Staged everything** — never apply changes silently; always preview → review → commit
5. **Keyboard-first** — every action reachable without the mouse
6. **No beginner/expert toggle** — one interface that works for both through smart defaults and progressive depth

---

## Surface-by-Surface Design

### 1. TUNE Tab — Context-Aware Editing

**Current state:** Tree navigator with grouped pages, field-level detail on click, real tune values from MSQ.

**Target state:**

#### Page context header
When a page is selected, show a brief context block above the fields:
- **What this page does** — one sentence (e.g., "Controls how much fuel the engine gets at every RPM and load point")
- **What to check first** — actionable hint (e.g., "Start by reviewing idle cells at row 0, columns 0–3")
- **Related pages** — links to pages that affect or are affected by this one

#### Live operating point overlay
When connected to the ECU:
- Highlight the current RPM × load cell in table pages
- Show the current value vs. the tune value for scalar pages
- Animate the cursor position as the engine moves through the map

#### Visual diff for staged changes
Before committing a staged edit:
- Show a before/after comparison for scalars (old → new with arrow)
- Show a heatmap diff overlay for table edits (cells that changed highlighted)
- Show net effect summary ("VE increased by avg 3.2% in the idle region")

#### Smart warnings
- Out-of-range values get specific messages, not just "out of bounds" (e.g., "Dwell of 8.5ms is unusually high for a Speeduino coil pack — typical range is 2.0–5.0ms")
- Cross-parameter warnings (e.g., "reqFuel changed but injector flow was not updated — these should be consistent")

#### Implementation priority
- [ ] Page context header with description text (from INI help or generated)
- [ ] Live operating point highlight on table pages (uses TableReplayContextService)
- [ ] Staged-change visual diff (uses TuningPageDiffService)
- [ ] Smart warning messages (uses HardwareSetupValidationService)

---

### 2. SETUP Tab — Wizard-Driven, Not Form-Driven

**Current state:** Generator heatmap demos with simulated engine context.

**Target state:**

#### Step-by-step guided flow
Replace the flat parameter view with a progressive wizard:
1. **Engine** — displacement, cylinders, compression ratio, cam duration
2. **Induction** — NA / turbo / supercharger / twin-charge (shows only relevant fields)
3. **Injectors** — flow rate, dead time, characterization depth, pressure model
4. **Ignition** — coil type, dwell, trigger pattern
5. **Sensors** — CLT/IAT thermistor preset, wideband preset, MAP sensor
6. **Review** — shows all assumptions, confidence indicators, generated table previews

#### Confidence indicators
Each generator assumption shows a badge:
- 🟢 **From context** — operator provided this value
- 🟡 **Computed** — derived from other inputs
- 🔴 **Conservative fallback** — value was missing, using safe default

#### Visual table previews
Before staging, show the generated VE/AFR/spark tables as heatmaps with a "Stage All" or "Stage Selected" button. The operator can see exactly what they're about to write.

#### Smart defaults
When the operator selects a turbo topology, automatically adjust:
- VE table shape (pre-spool reduction)
- AFR targets (richer WOT)
- Spark advance (retarded under boost)
- Idle RPM (slightly elevated)
Show these adjustments as a diff against the NA baseline.

#### Implementation priority
- [ ] Wizard step navigator (sidebar or top progress bar)
- [ ] Conditional field visibility based on topology
- [ ] Confidence badge rendering on assumptions
- [ ] "Stage All" button wiring to LocalTuneEditService
- [ ] Generated table diff against current tune values

---

### 3. LIVE Tab — Dashboard as Primary Runtime Surface

**Current state:** Runtime telemetry cards + gauge color zone demos + dashboard gauge grid.

**Target state:**

#### Gauge cluster as hero surface
The dashboard should be the **first thing the operator sees** when connected. Large, clear, and readable at arm's length (important for dyno/bench use).

#### Gauge rendering (when ABI-safe QPainter is available)
- **Analog dials** with 270° sweep, tick marks, zone arcs, smooth needle
- **Bar gauges** with horizontal/vertical fill and zone coloring
- **Number readouts** with large digits and zone-colored background
- **Histogram traces** for channels that benefit from trend visibility (AFR, MAP, RPM)

#### One-click tuning
Tap/click a gauge → opens the related tune page in a side panel or popup with the current operating point highlighted. No tab switching needed.

#### Alert system
When the engine enters a warning/danger zone:
- Flash the gauge border
- Show a toast notification at the top of the screen
- Log the event to the session history
- Optional: audible alert (configurable)

#### Session recording
One-button "Record" that captures:
- All runtime channel values at the configured poll interval
- All staged changes and operations
- Feeds directly into VE Analyze when stopped

#### Implementation priority
- [ ] Dashboard as the default connected view
- [ ] Gauge click → tune page navigation
- [ ] Zone-based alert toasts
- [ ] Session recording button (wraps LiveCaptureSessionService)
- [x] Histogram gauge kind (scrolling line chart for last N seconds)

---

### 4. ASSIST Tab — Explain Everything

**Current state:** Phase 7 pipeline demo with accumulator → smoothing → diagnostics → review cards.

**Target state:**

#### Plain language results
Instead of: `"VE Analyze: 80 accepted samples across 12 cell(s); 5 rejected; 8 cell(s) have correction proposals."`

Show: `"Your engine ran through 12 different RPM/load zones during this session. 8 of those zones need VE adjustments — mostly in the cruise region where the engine is running slightly lean."`

#### Coverage heatmap
Overlay the VE table with a color-coded coverage map:
- 🟢 Well-sampled cells (high confidence)
- 🟡 Low-sample cells (some data but not enough)
- ⚫ Unvisited cells (no data yet)
- Show this alongside the proposal heatmap so the operator can see where they still need to drive

#### Actionable next steps
After each analysis run, show:
1. "Apply these 8 proposals" (one-click staging)
2. "You need more data in the high-RPM region — try a few WOT pulls"
3. "Root-cause: your injector flow rate may be slightly off (all corrections are uniformly lean)"

#### Implementation priority
- [ ] Plain-language summary builder
- [ ] Coverage heatmap overlay on the VE table grid
- [ ] One-click "Apply proposals" button
- [ ] Next-steps guidance based on coverage gaps and diagnostics

---

### 5. FLASH Tab — Safe and Clear

**Current state:** Preflight validation cards with warning display.

**Target state:**

#### Preflight checklist as a visual flow
Instead of a list of warnings, show a checklist:
- ✅ Firmware file found
- ✅ Board family matches
- ⚠️ Tune signature doesn't match firmware — review before flashing
- ✅ Connection is active

#### One-click flash with confirmation
Big "Flash Firmware" button that:
1. Runs preflight validation
2. Shows any warnings with "Proceed Anyway" / "Cancel"
3. Shows a progress bar during flash
4. Verifies after flash and reports success/failure

#### Recovery guidance
If flash fails or board is bricked:
- Show board-specific recovery instructions
- For Teensy: "Hold the button on the Teensy board and reconnect USB"
- For STM32: "Enter DFU mode by holding BOOT0 and pressing RESET"

---

### 6. Shell / Navigation

**Current state:** 7-tab QTabWidget with status bar.

**Target state:**

#### Sidebar navigation
Replace the tab bar with a collapsible sidebar:
- Icon + text labels
- Status badges (staged change count, connection state, recording indicator)
- Collapse to icon-only mode for more workspace space

#### Command palette
`Ctrl+K` opens a search-everything dialog:
- Find any page by name ("VE Table", "Idle Control")
- Find any parameter by name ("reqFuel", "dwell")
- Find any action ("Connect", "Burn to Flash", "Start VE Analyze")

#### Breadcrumb context
Top bar shows: `Tuning > Fuel > VE Table` with clickable segments to navigate back up the hierarchy.

#### Status bar
Always visible:
- Connection state (disconnected / connected to COM3 @ 115200)
- Sync state (clean / 3 staged changes / signature mismatch)
- Active session mode (idle / recording / VE Analyze running)

---

### 7. Landing Page — First Impressions Matter

**Current state:** App opens directly to the TUNE tab with whatever was last loaded.

**Target state:**

#### Welcome surface
When the app launches with no active project, show a **landing page** instead of an empty workspace:

- **Recent projects** — list of recently opened projects with signature, last-opened date, and a thumbnail of the engine config (e.g., "Ford 300 Twin-GT28 | Speeduino 202501-T41 | Last opened 2 days ago")
- **New Project** — starts the setup wizard flow
- **Open Existing** — file picker for .msq / .ini / project files
- **Connect & Auto-Detect** — scans for connected Speeduino boards and offers to create a project from the detected firmware
- **Hardware Setup Wizard** — jumps directly into guided hardware configuration

#### Quick-resume
If the operator has a recent project, show a "Resume Last Project" button prominently at the top. One click gets them back to where they were.

#### First-run experience
On first launch ever, show a brief onboarding:
1. "Welcome to Tuner — a modern workstation for Speeduino engines"
2. "Start by connecting your ECU or opening an existing tune file"
3. "The setup wizard will help you configure your engine"

No forced tutorial — just three sentences and action buttons.

---

### 8. Contextual Filtering — Show Only What Matters

**Core idea:** The TUNE tab currently shows all 56 pages regardless of the engine's configuration. A naturally-aspirated engine doesn't need boost pages. An engine without VVT doesn't need VVT settings. An engine without nitrous doesn't need the nitrous page.

#### Setup-driven page filtering
After the operator completes the setup wizard (or selects presets), the workspace should **hide irrelevant pages** by default:

- **No turbo/supercharger** → hide Boost Control, Boost Targets/Duty, WMI Control, WMI Duty
- **No VVT** → hide VVT Control, VVT Target/Duty, VVT2 Target/Duty
- **No nitrous** → hide Nitrous
- **No staged injection** → hide Staged Injection, Second Fuel Table
- **No flex fuel sensor** → hide Flex Fuel, Second Spark Table
- **No CAN bus** → hide CAN Broadcasting, CAN/Serial IO
- **No SD card** → hide SD Logger setup
- **No RTC** → hide RTC setup

#### How it works
The INI definition already has visibility expressions (`{expression}`) on many pages and fields — these are currently used to show/hide fields based on tune settings. We extend this:

1. The setup wizard captures the engine's **feature set** (NA/turbo, VVT yes/no, etc.)
2. These features map to INI setting groups (which we already parse via `[SettingGroups]`)
3. Pages whose visibility expression evaluates to false under the active settings are **dimmed or hidden** in the TUNE tree
4. A "Show All" toggle at the top of the tree reveals everything for power users

#### "Show me everything" escape hatch
A toggle button or checkbox: "Show all pages (including unused features)". When enabled, hidden pages appear dimmed with a tooltip explaining why they're normally hidden ("This page is hidden because your engine is configured as naturally-aspirated").

#### Smart detection
When the operator connects to an ECU for the first time, detect features from the tune:
- If `boostEnabled = 0`, auto-hide boost pages
- If `vvtEnabled = 0`, auto-hide VVT pages
- If `flexEnabled = 0`, auto-hide flex pages

No manual configuration needed — the workspace adapts to what's actually in the tune.

---

### 9. Easy Board Workflow — Connect, Flash, Burn

**Current state:** Board detection and flashing exist as service logic but aren't surfaced prominently.

**Target state:**

#### Connection bar (always visible)
A slim bar at the top of the workspace showing:
- Board icon + name ("Teensy 4.1 on COM3")
- Connection status (green dot = connected, red = disconnected, amber = connecting)
- One-click Connect/Disconnect button
- Auto-detect dropdown showing all available ports/boards

#### One-click burn
When changes are staged:
- Status bar shows "3 changes staged" with a "Review & Burn" button
- Clicking it opens a confirmation dialog showing exactly what will change
- "Write to RAM" and "Burn to Flash" are distinct buttons with clear explanations:
  - Write to RAM: "Takes effect immediately but lost on power cycle"
  - Burn to Flash: "Permanent until next change — survives power cycles"

#### Flash firmware flow
When the operator needs to update firmware:
1. Auto-detect the board family from USB
2. Show the matching firmware from the release folder
3. Preflight validation (the service we already ported)
4. One-click flash with progress bar
5. Post-flash verification and auto-reconnect

#### Power cycle guidance
After a burn that requires a power cycle:
- Show a clear message: "Power cycle required — turn the ignition off and back on"
- When the ECU reconnects, verify the values match what was burned

---

## Visual System

The native C++ app (`tuner_app.exe`) was accumulating palette drift — 10
slightly-different near-black backgrounds, 4 near-identical amber
accents, and typography sizes picked ad hoc per stylesheet. Sub-slice 88
introduced a centralized design token system at `cpp/app/theme.hpp` to
keep the look coherent as surfaces evolve.

### Tokens

All color, type, and spacing decisions live in the `tuner_theme`
namespace. Inline stylesheet code should reference these tokens instead
of hard-coding hex literals.

#### Background levels (darkest → lightest)

| Token          | Hex       | Role                                     |
|----------------|-----------|------------------------------------------|
| `bg_deep`      | `#0f1116` | App shell, behind everything             |
| `bg_base`      | `#14171e` | Tab content backdrop                     |
| `bg_panel`     | `#1a1d24` | Regular card / content container         |
| `bg_elevated`  | `#20242c` | Header strip / hovered / "tier above"    |
| `bg_inset`     | `#262a33` | Input field, inset cell, chip background |

Five levels. If you need a new level, add a token in `theme.hpp` with a
rationale — don't inline-a-new-hex in a stylesheet.

#### Text hierarchy (loud → quiet)

| Token            | Hex       | Use                              |
|------------------|-----------|----------------------------------|
| `text_primary`   | `#e8edf5` | Titles, hero values              |
| `text_secondary` | `#c9d1e0` | Body text                        |
| `text_muted`     | `#8a93a6` | Labels, field names              |
| `text_dim`       | `#6a7080` | Captions, inter-value separators |
| `text_inverse`   | `#0f1116` | Text on bright chips             |

Rule of thumb: pick the quietest level that still reads at a glance.
Reserve `text_primary` for the few headline values you want the eye to
land on first.

#### Semantic accents (exactly one per meaning)

| Token            | Hex       | Meaning                                    |
|------------------|-----------|--------------------------------------------|
| `accent_primary` | `#5a9ad6` | Informational, selection, default accent   |
| `accent_ok`      | `#5ad687` | Value inside healthy zone                  |
| `accent_warning` | `#d6a55a` | Attention needed, not urgent               |
| `accent_danger`  | `#d65a5a` | Urgent — engine at risk                    |
| `accent_special` | `#9a7ad6` | Derived / computed / formula channel       |

Five hues, named by intent rather than color. Code reads as
*"accent_danger"* (intent) instead of *"#d65a5a"* (choice), which is why
the LIVE tab's driving-phase indicator and the gauge zone logic now use
the same tokens — the mapping from "urgent" to "red" happens in one
place.

**`accent_special` is deliberately rare.** It only shows up on surfaces
that display derived / computed values (today: the LIVE tab's formula
channel strip). Keeping it scarce is what makes it visually distinctive
when it does appear.

#### Type scale

Six pixel sizes. If you need something between two values, round to the
nearer one rather than adding a new token.

| Token          | Size | Use                               |
|----------------|------|-----------------------------------|
| `font_micro`   | 10px | Edge labels, tiny captions        |
| `font_small`   | 11px | Muted labels, dividers, chips     |
| `font_body`    | 12px | Body text                         |
| `font_medium`  | 13px | Emphasised value, chip value      |
| `font_label`   | 14px | Header label                      |
| `font_heading` | 18px | Section heading                   |
| `font_hero`    | 28px | Gauge number, hero value          |

#### Spacing

`space_xs` (4) · `space_sm` (8) · `space_md` (12) · `space_lg` (16) ·
`space_xl` (24). Use these for `setContentsMargins` / `setSpacing`
instead of raw pixel integers so layout rhythm stays consistent.

#### Corner radius

`radius_sm` (4) · `radius_md` (6) · `radius_lg` (10).

### Composed helpers

Three of the most-repeated stylesheet patterns have inline helper
functions so you don't re-type the ingredient list every time:

- `card_style(accent=nullptr)` — bg_panel + 1px border + optional 3px
  left-accent bar + 6px radius
- `header_strip_style()` — bg_elevated + border + 4×12 padding + 6px
  radius
- `chip_style(accent=nullptr)` — bg_inset + 1px border + 4px radius +
  2×8 padding

Don't grow this API — everything else should compose tokens inline.

### Runtime header pattern (LIVE tab)

Sub-slice 88 also introduced the **runtime header** composite as a
reference example of the tokens in use:

```
┌─────────────────────────────────────────────────────────┐
│  ◉ REC   ◉ CRUISE   ·  RPM 3400  ·  TPS 42.1%          │  ← phase (hero)
│ ─────────────────────────────────────────────────────── │  ← border_soft
│  COMPUTED  λ 1.002 · throttle 42.1% · map 0.4 PSI ...   │  ← formula strip
└─────────────────────────────────────────────────────────┘
```

One bordered `bg_elevated` card containing two rows separated by a thin
`border_soft` divider. Progressive disclosure: the eye lands on the
phase first (biggest, boldest, semantic accent), then drops to the
formula row (smaller, `accent_special` purple, uppercase "COMPUTED"
label). Keeping both rows inside one container signals "this is one
thing — the current engine state at a glance" rather than two unrelated
chips stacked.

### Migration status

Sub-slice 88 migrated **three surfaces** to the token system as proof:

- LIVE tab runtime header (phase indicator + formula strip composite)
- LIVE tab driving-phase accent mapping (now uses `accent_danger` etc.
  instead of raw hex)
- `make_info_card()` helper (used across multiple tabs)

Sub-slice 90 extended the migration into the **app shell chrome**:

- Sidebar navigation stylesheet (background, borders, item padding,
  hover + selected states) — now consumes tokens via `snprintf` into
  a single composed stylesheet string
- Sidebar container background
- Connection indicator (bottom-of-sidebar green dot + port/baud label)
- Stale `"81 services · 1052 tests"` counter removed from the status
  bar (see "Show only what's true now", below)

Sub-slice 91 closed the **biggest remaining inline-hex surface**: the
TUNE-tab right-panel detail card. Every surface in `build_tune_tab`
now consumes tokens:

- Project identity bar (hero name + metadata chain)
- Selected-page label + context detail card
- Section header dividers (`section_header_style()` helper)
- Field label + editor row (`field_label_style()`,
  `scalar_editor_style(Default|Ok|Warning)`, `units_label_style()`)
- Staged-edit tint cycle (3-state enum, no more inline hex literals)
- String value chips (`inline_value_chip_style()`)
- Table card container (`card_style()`)
- Table info line (dimension + axis chain)
- X/Y axis labels on the heatmap grid
- 2D/3D toggle buttons (semantic `accent_primary` active state)

Five new helpers landed in `theme.hpp` during the TUNE-tab pass:
`scalar_editor_style(EditorState)`, `section_header_style()`,
`field_label_style()`, `inline_value_chip_style()`,
`units_label_style()`.

The heatmap cell `background_hex` / `foreground_hex` values are
**deliberately not** tokenized — they come from
`table_rendering::RenderModel` and are derived from the data gradient.
Those hues are data, not chrome. Only the cell borders, fonts, and
surrounding grid structure use tokens.

Remaining surfaces in `main.cpp` (FLASH / SETUP / ASSIST / TRIGGERS /
LOGGING / HISTORY tabs) still use inline hex literals, but none of
them have anywhere near the visual density of the TUNE tab. They can
migrate incrementally as each tab gets touched for functional work —
the token system is additive, not a rewrite.

### Philosophy wordmark (sub-slice 90)

One place in the chrome — the bottom of the sidebar, below the
connection indicator — carries a quiet two-line identity footer:

```
┌──────────────┐
│  🔧 Tune     │
│  📊 Live     │
│  ⚡ Flash    │  ← nav items
│  ...         │
│              │
│              │  ← stretch
├──────────────┤
│ ● COM3·115200│  ← connection indicator (bg_deep)
├──────────────┤
│    TUNER     │  ← wordmark, text_muted · font_small · 3px letter-spacing
│ guided power │  ← tagline, text_dim · font_micro · 1px letter-spacing
└──────────────┘
```

This is the single place in the chrome that says *"what is this app
about"*. It's intentionally tiny, dim, and monochrome — reflecting the
"Don't over-animate — automotive tuning is precision work" principle.
It's there for anyone curious enough to look, not to dominate the
workspace. The tagline is a literal echo of the opening paragraph of
this document ("guided power").

**Why bother with this at all?** Because the app's identity is a
design decision: "guided power for Speeduino" is what makes this
different from TunerStudio. The wordmark is the one place that states
that out loud. Every other surface implements the principles
(progressive disclosure, context over structure, explain as you go);
the wordmark is the source.

### Show only what's true now (sub-slice 90)

The pre-sub-slice-90 status bar hard-coded a "81 services · 1052 tests"
counter to brag about the test suite. That counter went stale on
literally the next sub-slice (83 services, 1117 tests, then 1126...).
Sub-slice 90 removed it rather than updating the literal — because
**the status bar should only show things that are true *now***.
Hard-coded counters are a lie waiting to happen. If we want to surface
the test count, we'd compute it at build time from the actual suite.
Short of that, silence is more honest than stale.

This is a small thing, but it's load-bearing for the design philosophy:
*"Don't add features without operator value"* extends to informational
chrome — every visible number either reflects reality or gets removed.

## What We Should NOT Do

- **Don't hide power** behind "beginner mode" toggles — make power accessible through progressive disclosure
- **Don't add wizards that block** experienced users from direct access to any parameter
- **Don't over-animate** — automotive tuning is precision work, not entertainment
- **Don't copy TunerStudio's layout** just because it's familiar — copy its *workflow* (the things operators actually do) and improve the *interface* around that workflow
- **Don't add features without operator value** — every surface should help someone tune their engine better

---

## Implementation Phases

### Phase A: Foundation (current session)
- [x] Keyword-grouped TUNE tree with field detail
- [x] Real MSQ values displayed
- [x] Generator heatmap previews
- [x] Runtime telemetry cards
- [x] Dashboard gauge grid

### Phase B: Context and Guidance
- [x] Page context headers in TUNE tab (all 56 pages)
- [x] Table heatmap rendering in TUNE tab right pane
- [x] Confidence badges on SETUP assumptions
- [x] Plain-language ASSIST summaries
- [x] Flash preflight checklist

### Phase C: Live Interaction
- [x] Live operating point overlay on tables
- [x] Gauge click → tune page navigation
- [x] Session recording
- [x] Zone-based alerts

### Phase D: Polish
- [x] Sidebar navigation
- [x] Command palette
- [x] Histogram gauge
- [x] Smart cross-parameter warnings
- [x] Setup wizard flow

---

## Native Format Strategy

### Why now

The app currently reads INI files (firmware definitions) and MSQ files (tune data) — both are TunerStudio legacy formats with significant complexity:

- INI: `lastOffset` arithmetic, `#if/#else` preprocessing, indirect table identity through 4-hop naming chains, page/offset byte-level details mixed with semantic metadata
- MSQ: XML with namespace `http://www.msefi.com/:msq`, values stored as inner-text strings requiring row/col-aware parsing

Every service in the app translates these formats into clean internal models, then works on the clean models. The native format should **be** the clean internal model, serialized directly. INI/MSQ become import/export adapters, not the source of truth.

### Architecture

```
INI + MSQ (import)  ──→  Native Format (internal truth)  ──→  MSQ (export for TS compat)
                              ↕
                         .tuner files (save/load)
```

### Three native file types

#### 1. Definition (`.tunerdef` — JSON5)

The firmware definition file. Describes what parameters exist, their types, ranges, relationships, and presentation. Authored by firmware developers or generated from INI.

```json5
{
  // Human-readable, no page/offset concerns
  "firmware": "speeduino",
  "version": "202501-T41",
  "board": "teensy41",

  "tables": {
    "veTable": {
      "title": "VE Table",
      "type": "u16",  // or "u8"
      "rows": 16, "cols": 16,
      "x_axis": { "source": "rpmBins", "label": "RPM", "units": "rpm" },
      "y_axis": { "source": "mapBins", "label": "MAP", "units": "kPa" },
      "units": "%",
      "range": [0, 200],
      "help": "Volumetric efficiency lookup table",
      "group": "fuel"
    }
  },

  "scalars": {
    "reqFuel": {
      "title": "Required Fuel",
      "type": "f32",
      "units": "ms",
      "range": [0, 25.5],
      "digits": 1,
      "help": "Base fuel pulse width for 100% VE at stoich",
      "group": "fuel",
      "requires_power_cycle": false
    }
  },

  "curves": {
    "wueCurve": {
      "title": "Warmup Enrichment",
      "x_axis": { "source": "wueBins", "label": "CLT", "units": "°C" },
      "y_axis": { "source": "wueRates", "label": "Enrichment", "units": "%" }
    }
  },

  "groups": {
    "fuel": { "title": "Fuel", "order": 10 },
    "ignition": { "title": "Ignition", "order": 20 }
  },

  "features": {
    "boost": { "enabled_by": "boostEnabled", "label": "Boost Control" },
    "vvt": { "enabled_by": "vvtEnabled", "label": "Variable Valve Timing" }
  },

  "gauges": { /* ... */ },
  "commands": { /* ... */ }
}
```

**Key differences from INI:**
- No page/offset — the firmware transport layer maps names to addresses
- No `lastOffset` arithmetic — every parameter has an explicit identity
- No `#if/#else` preprocessing — features are declared, not compiled
- No indirect naming chains — `veTable` IS `veTable`, not `veTable` → `veTable1Tbl` → `veTable1Map` → `zBins = veTable`
- Type information is semantic (`u16`, `f32`) not storage-format (`U08`, `S16`)
- Groups are first-class, not derived from menu structure

#### 2. Tune (`.tuner` — JSON)

The tune data file. Contains parameter values keyed by name.

```json
{
  "format": "tuner-tune-v1",
  "definition": "speeduino-202501-T41",
  "created": "2026-04-09T20:00:00Z",
  "modified": "2026-04-09T21:30:00Z",

  "values": {
    "reqFuel": 6.1,
    "nCylinders": 6,
    "veTable": [80, 82, 85, ...],  // flat array, row-major
    "wueBins": [-40, -26, 10, 19, 28, 37, 46, 58, 63, 64],
    "wueRates": [180, 175, 168, 154, 134, 121, 112, 104, 102, 100]
  },

  "operator_context": {
    "displacement_cc": 2998,
    "compression_ratio": 10.5,
    "cam_duration_deg": 280,
    "forced_induction": "single_turbo"
  }
}
```

**Key differences from MSQ:**
- JSON not XML — trivial to parse, no namespace handling
- Values are typed (numbers are numbers, not strings)
- Tables are flat arrays with dimensions from the definition
- Operator context is embedded (displacement, CR, etc.)
- No page structure — just named values

#### 3. Project (`.tunerproj` — JSON)

Project metadata tying everything together.

```json
{
  "format": "tuner-project-v1",
  "name": "Ford 300 Twin-GT28",
  "definition_path": "speeduino-202501-T41.tunerdef",
  "tune_path": "Ford300_TwinGT28.tuner",
  "active_settings": ["LAMBDA", "mcu_teensy"],
  "dashboard_layout": "default",
  "logging_profiles": ["default", "wideband-focus"],
  "last_connected": "COM3:115200:SPEEDUINO",
  "calibration_intent": "drivable_base"
}
```

### Migration path

1. **Now:** INI + MSQ remain the import format. The app opens them through the existing parsers.
2. **Soon:** Add "Save as Native" that exports the current session as `.tunerdef` + `.tuner` + `.tunerproj`. The operator can then reopen from native format.
3. **Later:** Add "New Project" that starts with a native definition (generated from the setup wizard or from a firmware-provided `.tunerdef`).
4. **Eventually:** The firmware ships `.tunerdef` files alongside the hex. INI becomes a legacy compatibility layer only used for TunerStudio users.

### What to implement first

1. **Tune export/import** (`.tuner`) — simplest, most immediately useful. The `LocalTuneEditService` already holds typed values; serializing them to JSON is trivial.
2. **Project file** (`.tunerproj`) — enables "recent projects" on the landing page.
3. **Definition export** (`.tunerdef`) — convert the compiled `NativeEcuDefinition` to JSON. This is the hardest because it requires deciding which INI concepts survive.

### What NOT to do

- Don't break INI/MSQ compatibility — existing Speeduino users need to open their existing files
- Don't invent a binary format — JSON is readable, diffable, and mergeable
- Don't try to represent every INI quirk in the native format — the native format is simpler because it doesn't need to
- Don't block the C++ port on the native format — the existing parsers work fine as import adapters
