# `cpp/app/main.cpp` Refactor Plan

**Target:** Decompose `cpp/app/main.cpp` into focused translation units without changing runtime behavior or breaking the test suites.

**Current state (as of plan authoring):**
- All eight `build_<tab>_tab` functions live in a single `main.cpp` (~22,400 lines at session start).
- Shared state is already passed as explicit `std::shared_ptr` parameters (not top-level closure captures).
- Custom Qt widgets (`DialGaugeWidget`, `BarGaugeWidget`, `TableSurface3DView`, `EditableCurveChartWidget`, LED face painters) are defined inline in the same file.
- `theme.hpp` already exists as precedent for extracting pure concerns.
- `CMakeLists.txt` builds a single `tuner_app` target from `cpp/app/main.cpp` under the `TUNER_BUILD_APP` option.

---

## Progress (2026-04-18 session)

**main.cpp: 22,430 → 19,895 lines (-2,535, -11.3%) across 15 commits, every commit green at the validation gate (`tuner_core_tests` 1528/11378 pass, `tuner_app` builds + bundles flash tools).**

### Step 1 — Custom Qt widgets ✅ Done

All twelve inline widget classes moved to `cpp/app/widgets/`. Plus one dead class deleted along the way.

| Commit | Class | hpp/cpp |
|---|---|---|
| `ba74c29` | `DialGaugeWidget` | `widgets/dial_gauge_widget.{hpp,cpp}` |
| `a4b22af` | `BarGaugeWidget` | `widgets/bar_gauge_widget.{hpp,cpp}` |
| `45316c3` | `LedGaugeWidget` | `widgets/led_gauge_widget.{hpp,cpp}` |
| `d6ba8d4` | `DraggableCardLabel` | `widgets/draggable_card_label.{hpp,cpp}` |
| `6057c07` | `HistogramWidget` | `widgets/histogram_widget.{hpp,cpp}` |
| `1e64264` | `DynoChartWidget` | `widgets/dyno_chart_widget.{hpp,cpp}` |
| `c679102` | `LogTimelineWidget` | `widgets/log_timeline_widget.{hpp,cpp}` |
| `45bf34d` | `TriggerScopeWidget` | `widgets/trigger_scope_widget.{hpp,cpp}` |
| `b40eef1` | `PaintedHeatmapWidget` | `widgets/painted_heatmap_widget.{hpp,cpp}` |
| `46f4d28` | `CellClickFilter` | (deleted — dead since sub-slice 147) |
| `fdf331f` | `TableSurface3DView` | `widgets/table_surface_3d_view.{hpp,cpp}` |
| `1074f59` | `EditableCurveChartWidget` | `widgets/editable_curve_chart_widget.{hpp,cpp}` |

`cpp/CMakeLists.txt` gained `target_include_directories(tuner_app PRIVATE app)` so future siblings include `"widgets/<name>.hpp"` without a relative climb.

### Step 2 — Style helpers ✅ Done

| Commit | Move | Destination |
|---|---|---|
| `abc468c` | `make_tab_header` + `make_info_card` | `ui/styles.{hpp,cpp}` |

`theme.hpp` keeps the design tokens + pure stylesheet-string helpers (`section_header_style`, `field_label_style`, `card_style`, etc — already in place from earlier slices); `ui/styles.{hpp,cpp}` owns the small Qt-aware widget factories that wrap a few tokens with QLabel/QVBoxLayout boilerplate.

### Step 3 — Tab builders 🚧 In progress

| Commit | Move | Destination | Notes |
|---|---|---|---|
| `c363a82` | `build_history_tab` | `tabs/history_tab.{hpp,cpp}` | Smallest tab, zero state deps — proved the tab-extraction pattern |
| `08646f1` | `EcuConnection` struct | `shell/ecu_connection.{hpp,cpp}` | Foundation step. Required so subsequent state-bearing tabs can include the shared ECU struct. |

**Paused before extracting `build_triggers_tab`.** Triggers calls `load_active_definition()` (a 100+ line file-scope helper that itself depends on `find_native_definition`, `find_production_ini`, `debug_log`, `synthesize_ecu_definition`). Per the plan's stop-condition rule for *"references a file-scope helper in main.cpp that isn't an obvious helper"*, the right next move is to pre-extract a `cpp/app/shell/project_helpers.{hpp,cpp}` cluster covering `load_active_definition` + its dependency chain before touching any more tabs. Estimated 3–5 commits of foundation work before any tab beyond `history` becomes a clean drop.

### Resume plan

When work resumes, the order is:

1. Extract `project_helpers` (`load_active_definition`, `find_native_definition`, `find_production_ini`, `synthesize_ecu_definition`, `debug_log`, etc.) to `cpp/app/shell/project_helpers.{hpp,cpp}`.
2. Then resume Step 3 in size order — `triggers` (419 lines), `flash` (696), `live` (1,388), `logging` (1,388), `assist` (2,382), `setup` (2,451), `tune` (4,793).
3. Step 4 (`WorkspaceShell` plain-data bundle) and Step 5 (`Tab` interface) remain optional and untouched.

Validation gate, guardrails, and stop-conditions in the rest of this document are unchanged and apply to every future commit.

**Non-goals:**
- No new features.
- No changes to `tuner_core` (the static library stays untouched).
- No changes to Python reference product.
- No rearchitecture of the service layer — this is purely a file-split of the Qt shell.

---

## Guiding principles

1. **Split by concern, not by line count.** "Get `main.cpp` under N lines" is the wrong target. Concerns are: custom widgets, style helpers, per-tab builders, shell state, window assembly.
2. **Keep free-function shape during extraction.** Do not convert `build_<tab>_tab` into classes mid-extract. A presenter-like bundle (`WorkspaceShell`) comes *after* tabs are in their own TUs, not before.
3. **No `#include`-based splits.** Do not split `main.cpp` by textually including `.ipp` fragments. It gives zero incremental-compile benefit, which is half the point of the refactor.
4. **Every step is independently committable.** If the session is interrupted between steps, the repo must still build and pass tests.
5. **Match the existing style.** Use the same brace/indent conventions, the same `tuner_theme` / `namespace tt =` aliasing, the same `debug_log` helpers. This is not an opportunity to modernize.

---

## Validation gate (run between every step)

Each step is "green" only when all of these pass:

```bash
# 1. C++ library tests still pass
cmake --build build/cpp --target tuner_core_tests
./build/cpp/tuner_core_tests
# Expect: 1513 tests · 11336 assertions · 0 failures (or current baseline)

# 2. Native app still builds
cmake --build build/cpp --target tuner_app

# 3. Native app still launches + loads production INI + renders all 8 tabs
#    without a crash. Run manually or via the existing smoke script.
./build/cpp/tuner_app.exe

# 4. Python suite unchanged (sanity — no cross-repo drift expected)
python -m pytest tests/ -q
```

**If any of the above regresses, stop and revert the current step before proceeding.** Do not layer further extractions on top of a red build.

---

## Step 1: Extract custom Qt widgets

**Goal:** Move pure widget classes out of `main.cpp`. These have no dependency on tab state, shell state, or `shared_ptr` plumbing. This is the lowest-risk, highest-return step.

**Target layout:**

```
cpp/app/widgets/
  dial_gauge_widget.hpp
  dial_gauge_widget.cpp
  bar_gauge_widget.hpp
  bar_gauge_widget.cpp
  table_surface_3d_view.hpp
  table_surface_3d_view.cpp
  editable_curve_chart_widget.hpp
  editable_curve_chart_widget.cpp
  led_face_widget.hpp
  led_face_widget.cpp
```

**Exact widget classes to extract (identify by grep in `main.cpp`):**
- `DialGaugeWidget`
- `BarGaugeWidget`
- `TableSurface3DView`
- `EditableCurveChartWidget`
- `_LedFace` / `LedFaceWidget` (whatever the LED indicator painter is named)
- Any other `: public QWidget` / `: public QLabel` subclass defined inline in `main.cpp`

**Extraction procedure (per widget):**

1. Create the header file. Declare the class, include only the Qt headers it actually uses (`QWidget`, `QPainter`, `QMimeData`, etc.).
2. Create the implementation file. Move the full class body, including any `paintEvent`, `mousePressEvent`, `dragEnterEvent`, etc.
3. In `main.cpp`, replace the class body with `#include "widgets/<name>.hpp"`.
4. Update `cpp/CMakeLists.txt` — add the new `.cpp` to the `tuner_app` target sources.
5. Run the validation gate.
6. Commit with message: `refactor(app): extract <WidgetName> to cpp/app/widgets/`

**Guardrails:**
- If a widget uses a callback type (e.g. `ConfigCallback`, `SwapCallback`), keep the type alias in the widget's own header. Do not promote it to a shared header yet.
- If a widget currently references a lambda from `main.cpp` via capture, that lambda is not part of the widget — it should already be injected via a setter or a `std::function` member. Verify during extraction that no hidden coupling exists.
- MIME type strings like `"application/x-gauge-widget-id"` stay with the widget that owns them.

**Expected reduction:** ~2000–3000 lines out of `main.cpp`.

---

## Step 2: Extract theme/style helpers

**Goal:** Consolidate the style-helper functions that have accumulated past `theme.hpp` during the beautification slices.

**Target layout:**

```
cpp/app/theme.hpp               # existing — tokens only
cpp/app/ui/styles.hpp           # NEW — QSS-string helpers
cpp/app/ui/styles.cpp
```

**Functions to move (identify by grep for `_style()` helpers in `main.cpp`):**
- `section_header_style()`
- `field_label_style()`
- `scalar_editor_style(EditorState)`
- `inline_value_chip_style()`
- `units_label_style()`
- `card_style()`
- `chip_style()`
- `make_info_card()` (if it's a helper rather than a tab-local lambda)

**Guardrails:**
- Do not change any token references during the move. Every hex/color in these helpers must come from `tuner_theme` already; if any inline hex remains, leave it — a later beautification slice owns that cleanup.
- Keep `EditorState` (or equivalent enum) co-located with `scalar_editor_style` in `styles.hpp`, not in `theme.hpp`.
- `theme.hpp` stays tokens-only. `styles.hpp` consumes `theme.hpp`. Not the reverse.

**Validation:** same gate as Step 1.

**Commit message:** `refactor(app): extract style helpers to cpp/app/ui/styles.{hpp,cpp}`

---

## Step 3: Extract tab builders (largest first)

**Goal:** Move each `build_<tab>_tab` free function into its own translation unit. Do this one tab per commit.

**Target layout:**

```
cpp/app/tabs/
  tune_tab.hpp
  tune_tab.cpp
  live_tab.hpp
  live_tab.cpp
  flash_tab.hpp
  flash_tab.cpp
  setup_tab.hpp
  setup_tab.cpp
  assist_tab.hpp
  assist_tab.cpp
  triggers_tab.hpp
  triggers_tab.cpp
  logging_tab.hpp
  logging_tab.cpp
  history_tab.hpp
  history_tab.cpp
```

**Order (largest → smallest for best early wins):**
1. `build_tune_tab` — the biggest tab, biggest return.
2. `build_live_tab`
3. `build_setup_tab`
4. `build_assist_tab`
5. `build_logging_tab`
6. `build_triggers_tab`
7. `build_flash_tab`
8. `build_history_tab`

**Extraction procedure (per tab):**

1. Create the header declaring the exact current signature of the builder. Do not change the signature.
   ```cpp
   // Example — tune_tab.hpp
   #pragma once
   #include <QWidget>
   #include <memory>
   #include <functional>
   // Forward-declare shared types; do not include tuner_core heavy headers here.
   namespace tuner_core { class Workspace; }
   namespace tuner_core::local_tune_edit { class EditService; }
   class EcuConnection;

   QWidget* build_tune_tab(
       std::shared_ptr<tuner_core::Workspace> workspace,
       std::shared_ptr<tuner_core::local_tune_edit::EditService> edit_svc,
       std::shared_ptr<EcuConnection> ecu_conn,
       std::shared_ptr<std::string> tune_signature,
       std::function<void()> refresh_tune_badge,
       std::shared_ptr<std::optional<int>> tune_slot_index,
       std::shared_ptr<std::optional<std::string>> tune_slot_name);
   ```
2. Move the function body, plus any tab-local helper lambdas defined adjacent to it, plus any tab-local file-scope helpers (`load_active_definition`, etc. — see note below).
3. In `main.cpp`, replace the function body with `#include "tabs/<name>_tab.hpp"`.
4. Update `cpp/CMakeLists.txt`.
5. Run the validation gate.
6. Commit: `refactor(app): extract build_<tab>_tab to cpp/app/tabs/<tab>_tab.cpp`

**Shared helper handling:**
- Helpers used by more than one tab (e.g. `load_active_definition`, `find_production_ini`, `active_project`, `push_recent_project`, `project_from_file`) go to `cpp/app/shell/project_helpers.{hpp,cpp}` on first extraction. Subsequent tab extractions `#include` that header.
- Helpers used by exactly one tab stay inside that tab's `.cpp` as file-scope `static` functions.
- The per-tab-construction profiling helpers (`prof_lap`) stay in `main.cpp` — they are window-assembly concerns, not tab concerns.

**Guardrails:**
- **Do not change the builder signature** during extraction. If a parameter list is painful, note it for Step 4; do not fix it here.
- **Do not turn the tab into a class.** Free function with explicit parameters, same as today.
- **Do not split a tab file** further during this step. A 4000-line `tune_tab.cpp` is an improvement over a 14,500-line `main.cpp`; optimize that later if at all.
- If you find a lambda inside `build_tune_tab` that gets passed to a widget extracted in Step 1, that lambda stays in the tab file. Widgets accept `std::function` callbacks; tabs provide them.

**Expected state after Step 3:** `main.cpp` is under ~3000 lines and contains only:
- `main()` entry point
- `TunerMainWindow` class (window assembly, sidebar wiring, menu bar, startup picker dispatch)
- Lazy-loading tab-build switch
- File → Open / Save / Save As handlers (unless those already want their own file — see optional Step 3b)

---

## Step 3b (optional): Extract file/project commands

**Trigger:** Only do this if Step 3 leaves `main.cpp` with obvious project/file-menu bloat (Save As handlers, recent-projects plumbing, SD tune ingest logic).

**Target layout:**

```
cpp/app/shell/
  project_helpers.hpp           # already created during Step 3 if shared helpers warranted it
  project_helpers.cpp
  file_menu_actions.hpp         # NEW — New Project / Open / Save / Save As / Open from SD
  file_menu_actions.cpp
  startup_picker.hpp            # NEW — the "what would you like to do today" surface
  startup_picker.cpp
```

Same extraction + validation pattern as Step 3. Commit per logical unit.

---

## Step 4: Introduce `WorkspaceShell`

**Prerequisite:** Steps 1–3 complete. This step is much harder to do cleanly while code is still in `main.cpp`.

**Goal:** Replace the repeated 5–8 `std::shared_ptr` parameters on every tab builder with a single `const WorkspaceShell&` reference. This is the spiritual successor to the Python reference product's presenter — but shaped by what the C++ parameter lists already tell you is shared, not by copying Python's class layout.

**Target:**

```cpp
// cpp/app/shell/workspace_shell.hpp
#pragma once
#include <functional>
#include <memory>
#include <optional>
#include <string>

namespace tuner_core { class Workspace; }
namespace tuner_core::local_tune_edit { class EditService; }
class EcuConnection;
class HttpServer;
struct SharedDashboard;

struct WorkspaceShell {
    std::shared_ptr<tuner_core::Workspace> workspace;
    std::shared_ptr<tuner_core::local_tune_edit::EditService> edit_svc;
    std::shared_ptr<EcuConnection> ecu_conn;
    std::shared_ptr<std::string> tune_signature;
    std::shared_ptr<std::optional<int>> tune_slot_index;
    std::shared_ptr<std::optional<std::string>> tune_slot_name;
    std::shared_ptr<HttpServer> http_server;
    std::shared_ptr<SharedDashboard> shared_dash;

    // Callbacks the shell publishes back up to the window.
    std::function<void()> refresh_tune_badge;
    std::function<void()> rebuild_dashboard;
    std::function<void(int, const std::string&)> navigate;
};
```

**Refactor order:**

1. Create `workspace_shell.hpp` with the struct. Empty `.cpp` is fine if everything is inline.
2. In `TunerMainWindow`'s constructor, populate a local `WorkspaceShell shell;` from the existing shared_ptrs.
3. Change **one** tab builder at a time to take `const WorkspaceShell&` instead of the explicit parameter list. Update its header, its call site in `main.cpp`, and its body (replace `workspace` with `shell.workspace`, etc.).
4. Run the validation gate.
5. Commit: `refactor(app): route <tab> through WorkspaceShell`
6. Repeat for each tab.

**Guardrails:**
- **Do not add methods to `WorkspaceShell`** in this step. It is a plain-data bundle. Behavior stays in the tab builders and the services they call.
- **Do not touch the lazy-loading switch** beyond updating the builder call. The switch-case structure is fine.
- If a tab needs something that isn't in `WorkspaceShell`, stop and decide: is that field genuinely shared (add to shell) or tab-local (leave as explicit parameter alongside the shell reference)? Do not grow the shell for single-consumer state.

---

## Step 5 (optional, defer): `Tab` interface

**Trigger:** Only consider this once a second tab-author appears, or once plugin-provided tabs become a concrete requirement (currently aspirational per `plugins/` directory in the Python repo shape).

**Sketch:**

```cpp
class Tab {
public:
    virtual ~Tab() = default;
    virtual QWidget* construct(const WorkspaceShell&) = 0;
    virtual void on_project_changed(const WorkspaceShell&) {}
    virtual void on_connection_changed(const WorkspaceShell&) {}
    virtual const char* title() const = 0;
    virtual const char* keyword() const = 0;  // for Alt+N shortcut matching
};
```

The current lazy-loading switch statement becomes a `std::vector<std::unique_ptr<Tab>>` iteration. Do not build this speculatively. Leave the switch in place until the second consumer exists.

---

## Anti-patterns to avoid

1. **Line-count targeting.** "Get `main.cpp` under 5000 lines by Friday" leads to bad splits. Split by concern; line count is a lagging indicator.
2. **Textual `#include` splits.** Putting tab bodies in `.ipp` files included from `main.cpp` changes nothing about incremental compile time and makes navigation worse. Use real translation units.
3. **Classifying during extraction.** Turning `build_tune_tab` into a `TuneTab` class mid-extract fights the parameter list. Extract free function first, bundle state in Step 4, classify (if ever) in Step 5.
4. **Premature shared headers.** Do not create `cpp/app/common.hpp` or `cpp/app/tab_helpers.hpp` as a dumping ground. Each helper lives with its clearest owner; promote to a shared location only when a second consumer appears.
5. **Reformatting during extraction.** Do not reflow braces, rename variables, or modernize `.size() > 0` to `!.empty()` during a move. Pure moves are easier to review and bisect.
6. **Skipping the validation gate.** Do not batch two extractions between test runs. The whole point of the incremental approach is that a bad step is cheap to revert.

---

## Stop conditions

Pause the refactor and ask the maintainer before proceeding if any of the following:

- A widget or tab turns out to have hidden coupling that resists extraction (e.g. references a file-scope `static` in `main.cpp` that isn't an obvious helper).
- `cpp/CMakeLists.txt` needs restructuring beyond adding source files (e.g. new library targets, new include directories beyond `cpp/app/`).
- A validation gate fails and the cause isn't obvious within ~15 minutes of investigation.
- The extraction would require changing a `tuner_core` header.
- The builder signature for a tab genuinely needs to change to be extractable — note it and skip that tab for the current pass.

---

## Summary of expected commits

```
refactor(app): extract DialGaugeWidget to cpp/app/widgets/
refactor(app): extract BarGaugeWidget to cpp/app/widgets/
refactor(app): extract TableSurface3DView to cpp/app/widgets/
refactor(app): extract EditableCurveChartWidget to cpp/app/widgets/
refactor(app): extract LED face widget to cpp/app/widgets/
refactor(app): extract style helpers to cpp/app/ui/styles.{hpp,cpp}
refactor(app): extract build_tune_tab to cpp/app/tabs/tune_tab.cpp
refactor(app): extract build_live_tab to cpp/app/tabs/live_tab.cpp
refactor(app): extract build_setup_tab to cpp/app/tabs/setup_tab.cpp
refactor(app): extract build_assist_tab to cpp/app/tabs/assist_tab.cpp
refactor(app): extract build_logging_tab to cpp/app/tabs/logging_tab.cpp
refactor(app): extract build_triggers_tab to cpp/app/tabs/triggers_tab.cpp
refactor(app): extract build_flash_tab to cpp/app/tabs/flash_tab.cpp
refactor(app): extract build_history_tab to cpp/app/tabs/history_tab.cpp
refactor(app): introduce WorkspaceShell, route tabs through it (one commit per tab)
```

Approximate 15–20 commits total across Steps 1–4. Each individually reviewable, individually revertible, each with a green validation gate.
