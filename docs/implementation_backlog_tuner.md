# Tuner Backlog

> **Note:** This backlog originated during the Python phase. Code references
> to Python classes are stale — the equivalent logic now lives in the C++ Qt
> app (`cpp/app/main.cpp`) and `tuner_core` services. The conceptual items
> remain valid. See `docs/tuning-roadmap.md` for the current roadmap.

- [ ] TN-001 Session connect rollback
  Summary: Make failed connect attempts leave a clean disconnected state.
  Deliverables:
  - rollback logic
  - cleanup on failure
  - tests
  Acceptance criteria:
  - failed connect leaves `SessionState.DISCONNECTED`
  - failed connect clears client
  - partially opened transport is closed
  - error detail is preserved for UI/reporting
  Files:
  - `session_service.py`
  - tests under `tests/unit`
  Estimate:
  - `0.5 day`
  Dependencies:
  - none

- [ ] TN-002 Release manifest reader
  Summary: Read `release_manifest.json` and use it as the primary packaging source.
  Deliverables:
  - manifest model
  - parser/service
  - fallback behavior when manifest is absent
  Acceptance criteria:
  - manifest overrides filename heuristics
  - fallback to current behavior still works
  Files:
  - new `release_manifest_service.py`
  - `firmware_catalog_service.py`
  - tests
  Estimate:
  - `0.5-1 day`
  Dependencies:
  - `FW-001 preferred`

- [ ] TN-003 Firmware catalog hardening
  Summary: Prevent normal users from being steered to diagnostic firmware.
  Deliverables:
  - artifact-kind aware selection
  - preferred artifact handling
  Acceptance criteria:
  - production flow hides diagnostics by default
  - experimental flow still picks preferred experimental artifact
  - selection uses manifest pairing when available
  Files:
  - `firmware_catalog_service.py`
  - tests
  Estimate:
  - `0.5-1 day`
  Dependencies:
  - `TN-002`

- [ ] TN-004 Flash preflight based on real compatibility
  Summary: Validate flash compatibility using signatures and manifest pairings.
  Deliverables:
  - stronger board/signature/artifact checks
  - reduced reliance on weak version-string matching
  Acceptance criteria:
  - explicit warning for prod vs experimental mismatch
  - explicit warning for mismatched INI/tune signature family
  - version text is secondary only
  Files:
  - `flash_preflight_service.py`
  - tests
  Estimate:
  - `0.5-1 day`
  Dependencies:
  - `TN-002`, `TN-003`

- [ ] TN-005 Real Speeduino verify/sync
  Summary: Replace stub verification with real page verification.
  Deliverables:
  - real `verify_crc()` behavior
  - sync-state support for verified/unsupported/failed
  - tests
  Acceptance criteria:
  - app does not treat "connected" as "verified"
  - page mismatch can be surfaced diagnostically
  Files:
  - `speeduino_controller_client.py`
  - `sync_state_service.py`
  - domain/tests
  Estimate:
  - `1-2 days`
  Dependencies:
  - `FW-005 preferred`

- [ ] TN-006 Capability handshake consumption
  Summary: Read and store firmware capability metadata at connect time.
  Deliverables:
  - capability model
  - connect-time probe
  - session storage
  Acceptance criteria:
  - older firmware without capability response still works
  - session stores board id, packet size/version, caps, feature flags
  Files:
  - `speeduino_controller_client.py`
  - session/domain models
  - tests
  Estimate:
  - `1 day`
  Dependencies:
  - `FW-003`, `FW-004`, `FW-006`, `FW-007`

- [ ] TN-007 Endianness contract cleanup
  Summary: Either support configured endianness or explicitly narrow the contract.
  Deliverables:
  - implementation or documentation cleanup
  - tests
  Acceptance criteria:
  - parser/runtime contract is no longer misleading
  Files:
  - `ecu_definition.py`
  - `speeduino_controller_client.py`
  - docs/tests
  Estimate:
  - `0.5 day`
  Dependencies:
  - none

- [ ] TN-008 Runtime telemetry integration
  Summary: Use current firmware telemetry and capability bits in runtime UX.
  Deliverables:
  - named `runtimeStatusA` decoding
  - board caps / SPI flash health exposure
  - UI gating based on firmware capabilities
  Acceptance criteria:
  - Tune Learn Valid, `fullSync`, board caps, and flash health are visible
  - UI can react to actual capabilities instead of board-name inference
  Files:
  - runtime services/UI layers
  - tests/fixtures
  Estimate:
  - `1-2 days`
  Dependencies:
  - `TN-006`

# Sprint Plan

## Sprint 1: Packaging And Safety

Goal: Remove the highest-risk operator errors in firmware selection and connection handling.

Scope:

- `FW-001`
- `FW-002`
- `TN-001`
- `TN-002`
- `TN-003`
- `TN-004`

Estimate:

- `4-6 days`

Exit criteria:

- manifest exists
- tuner consumes it
- diagnostic firmware no longer pollutes normal selection
- failed connects leave clean state

## Sprint 2: Capability Handshake

Goal: Make the tuner trust firmware-advertised facts instead of string heuristics.

Scope:

- `FW-003`
- `FW-004`
- `FW-006`
- `FW-007`
- `TN-006`

Estimate:

- `4-5 days`

Exit criteria:

- connect path retrieves capability metadata
- session stores capabilities
- UI/services can use actual board id and feature flags

## Sprint 3: Verification

Goal: Make "verified" actually mean something.

Scope:

- `FW-005`
- `TN-005`

Estimate:

- `3-4 days`

Exit criteria:

- page verification works for production path
- expected behavior for experimental `U16P2` is documented and test-covered
- sync state distinguishes verified vs unsupported

## Sprint 4: UX Integration

Goal: Use the new firmware contract to improve daily tuning and bench workflows.

Scope:

- `TN-008`
- `TN-007`

Estimate:

- `2-4 days`

Exit criteria:

- runtime UI shows `runtimeStatusA` and board capability data
- telemetry/capability features are not inferred from naming
- endianness contract is explicit and clean

# Dependency Map

- `FW-001 -> TN-002 -> TN-003 -> TN-004`
- `FW-003 -> FW-004/FW-006/FW-007 -> TN-006 -> TN-008`
- `FW-005 -> TN-005`
- `TN-001` is independent and should be done immediately
- `TN-007` is independent and can be slotted wherever convenient

# Recommended Execution Order

1. `TN-001`
2. `FW-001`
3. `FW-002`
4. `TN-002`
5. `TN-003`
6. `TN-004`
7. `FW-003`
8. `FW-004`
9. `FW-006`
10. `FW-007`
11. `TN-006`
12. `FW-005`
13. `TN-005`
14. `TN-008`
15. `TN-007`

# Post-Roadmap Backlog

These items are intentionally not part of the active delivery backlog above. They should not displace current product-completion, safety, and validation work. They exist so the long-horizon direction is explicit once the Python product is stable enough to justify it.

- [ ] LT-001 Product-model freeze
  Summary: Lock the behavioral contract of the Python application before any native-port work begins.
  Deliverables:
  - subsystem status review: implemented / partial / fragile / unvalidated
  - expanded real-artifact fixtures
  - documented Python-reference-product baseline
  Acceptance criteria:
  - core workflow behavior is test-backed against real release artifacts
  - parser/layout/table-generation edge cases are documented and reproducible
  - the Python app can act as the oracle for later ports

- [ ] LT-002 Owned tune file contract
  Summary: Design the project's native tune format rather than inheriting all long-term constraints from legacy external formats.
  Deliverables:
  - schema proposal
  - versioning/migration rules
  - import/export boundary definition
  Acceptance criteria:
  - native tune contract is documented
  - legacy MSQ handling is clearly separated into compatibility import/export behavior
  Notes:
  - prefer semantic values over page/offset-oriented storage declarations
  - likely canonical storage format: `JSON`

- [ ] LT-003 Owned definition/schema contract
  Summary: Define a native definition model that can express the product's needs without depending indefinitely on legacy INI quirks.
  Deliverables:
  - schema proposal
  - capability/metadata model
  - migration strategy from imported INI definitions
  Acceptance criteria:
  - definition responsibilities are separated into native schema vs imported compatibility behavior
  - firmware/desktop capability negotiation expectations are documented
  Notes:
  - remove dependence on constructs such as `lastOffset` and indirect table identity through menu/layout naming
  - likely authored format: `JSON5` or equivalent comment-friendly structured schema

- [ ] LT-003A Firmware schema/capability contract
  Summary: Define the firmware-facing contract required to support native tune/definition files cleanly.
  Deliverables:
  - schema-version and capability-version proposal
  - stable semantic ID strategy for tune/runtime entities
  - import/export contract between native semantic tune data and controller storage
  - migration/defaulting rules for schema revisions
  Acceptance criteria:
  - tune compatibility is not defined only by signature strings
  - runtime/log consumers can identify channel-contract revisions explicitly
  - controller page layout is documented as storage/export detail, not primary authored contract

- [ ] LT-003B Native logging contract
  Summary: Define the logging/evidence contract that sits between native firmware capabilities and
  replay/autotune/dashboard consumers.
  Deliverables:
  - runtime-channel catalog proposal
  - log-session metadata schema
  - channel/event annotation strategy
  - compatibility boundary for legacy CSV/INI-style logs
  Acceptance criteria:
  - log files are not just unlabeled columns with inferred meaning
  - replay can identify the runtime schema/channel contract used to capture a session
  - dashboards, evidence review, and autotune share the same channel metadata model
  Notes:
  - likely metadata storage: `JSON`
  - high-rate sample payload may need a separate binary/container format later

- [ ] LT-004 Native core feasibility pass
  Summary: Evaluate a shared native core, with C++ as the leading candidate, only after the current product model is stable.
  Deliverables:
  - measured pain points in Python
  - subsystem port candidates
  - staged migration proposal
  Acceptance criteria:
  - decision is based on observed startup/memory/protocol/parsing/packaging issues, not assumption
  - first-pass native candidates are limited to backend/model layers

- [ ] LT-005 Shared-core prototype
  Summary: Prototype one contained subsystem in a native shared library and validate it against the Python oracle.
  Deliverables:
  - one native component prototype
  - fixture-based parity tests
  - integration notes
  Acceptance criteria:
  - parity can be measured against Python behavior
  - the prototype improves an identified bottleneck or deployment concern

- [ ] LT-006 Deterministic autotune engine hardening
  Summary: Finish a transparent, reviewable correction engine before exploring ML.
  Deliverables:
  - deterministic correction rules
  - sample gating and confidence model
  - explainable proposal review UX
  Acceptance criteria:
  - each correction can be explained from source samples and bounds
  - operator can review, reject, and stage changes safely
  Notes:
  - include "not a VE problem" diagnostics for injector, deadtime, target-table, MAP/IAT, and sensor-calibration mismatches
  - add boosted-engine confidence penalties for uncertain manifold temperature, pressure-ratio, and spool-transition conditions

- [ ] LT-007 ML-assisted autotune research
  Summary: Explore ML only as an assistive layer on top of a deterministic autotune core.
  Deliverables:
  - candidate use cases
  - required logging/data fields
  - offline evaluation plan
  Acceptance criteria:
  - ML scope is limited to classification/scoring/anomaly tasks unless stronger evidence exists
  - no black-box model becomes first-authority for table writes without auditability and safety constraints

- [ ] LT-008 Engine-model refinement for generators
  Summary: Use the engine reference pack to harden generator math and cross-checks without making generation opaque.
  Deliverables:
  - separation of base VE shape vs boosted charge-density effects
  - compressor operating-point estimator with surge/choke confidence notes
  - horsepower / airflow / injector consistency checks
  - optional torque-peak-informed VE anchor input
  Acceptance criteria:
  - generator summaries explain pressure-ratio, temperature, and airflow assumptions when boosted
  - boosted modeling does not treat boost as a direct VE multiplier
  - injector helper and VE generator share the same airflow / BSFC sanity model
