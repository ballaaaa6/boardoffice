# Lean-First Runtime Unification and TS/JS Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task with review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current Python/browser runtime lean, single-purpose and contract-stable before the next phase migrates the production runtime to TypeScript/JavaScript. The resulting web path must load its deterministic data once, advance locally, render locally and avoid a request per simulation tick without changing gameplay, assets, authored geometry or replay semantics.

**Architecture:** Keep Python as the behavior oracle, exporter and local raster fallback during cleanup. Establish one language-neutral runtime contract and one presentation-frame pipeline. The future TS/JS runtime will consume the generated browser bundle and own the single-user web simulation after parity and author-acceptance gates close. Python is retired from the live web path only after the browser implementation proves exact replay/parity behavior; it remains available as an oracle or CLI until then.

**Tech Stack:** Python 3.10+, existing `CentralGameCore`/`RUNTIME`/`WORLD`/`CHARACTER` registries, deterministic JSON, Python `pytest`, Ruff, browser ES modules/TypeScript-compatible interfaces, Node built-in tests, Canvas 2D and the existing local review host. No new runtime dependency, bundler, WebAssembly/Pyodide, WebGL or Worker-hosted Pillow runtime is required for the lean phase.

**Spec:** `docs/LEAN_RELEASE_POLICY.md`, `docs/CENTRAL_CORE_ARCHITECTURE_DESIGN.md`, `HANDOFF.md`, `ROADMAP.md`, and the user requirement that lean cleanup precede the TS/JS web migration.

## Audit baseline

The repository is functionally healthy but not structurally lean.

- Current verification is green: `python -B -m pytest -p no:cacheprovider -q` → **377 passed in 411.14s**; `node --test TESTS/browser_runtime_test.mjs` → **10 passed**; `git diff --check` → **PASS**.
- Tracked source contains about 160 Python files. The main runtime is about 16,870 lines: `RUNTIME/actor_simulation_core.py` is about 3,367 lines, `RUNTIME/central_core.py` about 2,529, `RUNTIME/conversation_behavior_core.py` about 2,216 and `RUNTIME/speech_scheduler_core.py` about 1,873. These files mix validation, migration, orchestration, state reduction and presentation boundaries.
- Ruff reports **30** unused-import/unused-variable findings, including imports and locals in `RUNTIME`, `TOOLS`, `VALIDATION` and `WORLD/RUNTIME`. Complexity inspection reports **70** `C901` functions and **181** findings from the supported `PLR0911/12/13/14/15/17` selectors. These are not all bugs, but they prove that the implementation still has large responsibility clusters.
- No cloned non-empty code files were found. The one confirmed exact duplicate payload is `CHARACTER/BUILD_MANIFEST.json` and `CHARACTER/FINAL_MANIFEST.json`; the five empty `__init__.py` files are package markers, not meaningful dead code.
- At least 19 repeated helper/function bodies were found across QA/build scripts and tests, including file/RGBA SHA-256 helpers, palette conversion, floor selection, cell polygons, labels and quiet-runtime setup. About 41 repeated project-root/`sys.path` bootstrap snippets also exist across `TOOLS` and `VALIDATION`.
- The largest architectural duplication is deliberate but currently expensive: Python simulation, Python raster presentation, Python headless projection, browser simulation and Canvas presentation all coexist. The review server can project a frame in the headless loop and project it again while serializing a Canvas payload. `WEB/runtime_review.html` and `WEB/runtime_render_client.js` also split overlapping mode/lifecycle behavior.
- Legacy seams are still exercised: discrete crowd reservation alongside trajectory scheduling, retired-wander snapshot migration, action `legacy_materialized_path` resolution, legacy walking-depth metadata/scalar fallbacks and explicit manual `demo_wander` review support. They are migration candidates, not safe blind deletions.
- Generated workspace output is large but not runtime source: `LOCAL_REVIEW/` is about 3.05 GiB, `releases/.staging/` about 185.67 MiB and overlapping prototype worktrees about 163.33 MiB. These must be cleaned only as an explicit maintenance action.

## Non-goals and safety constraints

- Do not edit `00_STARTING_POINT/`, replace canonical PNGs, change authored floor geometry, move WorkSeats, alter reference hashes or change gameplay timing/policy during the lean phase.
- Do not delete a file solely because a text search finds no importer. CLI tools, generated-artifact builders and validation scripts are valid entrypoints; each candidate needs command/help/history evidence and a replacement or documented retirement.
- Do not remove Python, the raster renderer, the browser simulation slice or generated browser assets until the browser parity, save/load/replay, zero-request, endurance and author visual/gameplay gates pass.
- Do not infer acceptance from a generated manifest, benchmark or report. Every phase closes only with implementation tests, regression coverage, required audits, clean packaging checks and explicit author acceptance where visual/runtime behavior is involved.
- Keep the current public `CentralGameCore` and review-host API stable while internals are split. Compatibility wrappers are cheaper and safer than a flag-day interface rewrite.
- Do not introduce a request-driven web tick loop. The target runtime performs one bootstrap request, then local fixed-step simulation and Canvas rendering; persistence/replay may use explicit user actions or a later persistence service.

## Target boundaries

```text
Canonical registries / authored assets
             |
             v
Python source-contract + deterministic browser bundle builder
             |
             +--> Python CentralGameCore (oracle + local/raster fallback)
             |
             +--> gds.browser_runtime_bundle.v1
                         |
                         v
                 TS/JS BrowserRuntimeCore
                         |
                         v
                 gds.runtime_render_state.v1
                         |
                         v
                 Canvas compositor + local persistence/replay
```

The runtime contract is the seam, not a copy of Python internals. The bundle contains data, constants, initial snapshot and source revisions; browser code does not read Python modules, images or server endpoints after bootstrap. The presentation frame is produced once per simulation slice and is consumed by either the raster adapter or the Canvas adapter.

## Implementation tracks and order

The tracks are intentionally separated by risk. Complete Track A before Track B, and complete Tracks A–C before retiring any legacy seam. Track D is the preparation boundary for the next TS/JS implementation task, not permission to start that migration in the same change set.

### Track A — Establish the lean-audit and hygiene gate

**Purpose:** Remove objectively unused code and consolidate only semantics-proven helpers without changing runtime behavior.

**Files:**

- Create: `TOOLS/lean_audit.py`, `TOOLS/_bootstrap.py`, `TOOLS/_image_utils.py`, `VALIDATION/_common.py`, `TESTS/test_lean_audit.py`.
- Modify: Ruff findings in `RUNTIME/conversation_behavior_core.py`, `RUNTIME/conversation_spot_core.py`, `RUNTIME/runtime_presentation_renderer.py`, `RUNTIME/speech_scheduler_core.py`, `RUNTIME/work_seat_lifecycle.py`, `WORLD/RUNTIME/gameplay_metadata_family_core.py`, `TOOLS/build_runtime_render_manifest.py`, `TOOLS/build_runtime_simulation_bundle.py`, `TOOLS/export_browser_parity_trace.py`, `VALIDATION/self_audit_room_navigation.py`, `TESTS/test_navigation_occupancy_integration.py` and `TESTS/test_runtime_review_web.py`.
- Remove after caller/history review: obsolete preview/POC renderers with no first-party importer or test/manifest consumer; rejected host-first design documents; the byte-identical `CHARACTER/BUILD_MANIFEST.json` compatibility duplicate.

**Interfaces:**

- `lean_audit.py scan(root: Path) -> LeanAuditReport` classifies canonical source, generated output, CLI entrypoint, compatibility seam and historical/reference-only file. It reports duplicate bytes, duplicate AST function bodies, unused imports/locals from Ruff, repeated bootstrap/hash helpers, generated-file freshness and source-hash registry divergence.
- `_bootstrap.py.project_root(start: Path | None = None) -> Path` and `validation_root(...)` provide one path/bootstrap implementation for direct CLI execution and test imports.
- `_image_utils.py.file_sha256(path)`, `rgba_sha256(image)`, `build_global_palette(...)`, `to_palette(...)` are introduced only after comparing existing behavior and test vectors.
- `_common.py.load_json(...)`, `write_report(...)`, `parse_root(...)` standardize validation CLI behavior without changing report schemas or exit codes.

**Steps:**

- [x] Add the audit report and tests first. Tests distinguish a true duplicate from an intentional generated copy, treat empty package initializers as allowed markers and protect the source inventory from silently omitting canonical files.
- [x] Run `ruff check` and record the reviewed unused-import/unused-local gate. Fix the 30 concrete unused findings with the smallest local edits; each `F841` was reviewed before removal.
- [x] Extract the repeated bootstrap and image/hash helpers. Migrate representative tools, validation scripts and tests, then migrate the remaining semantically identical active callers. Helpers that differ in alpha handling, palette ordering or output format remain separate.
- [x] Add AST duplicate and reachability output to the audit. CLI-only scripts are reported as “entrypoint candidates” rather than dead; 16 current candidates remain retained after command/import/history review.
- [x] Run focused tests, `python -B -m pytest -p no:cacheprovider -q`, all required navigation/occupancy/WorkSeat/Phase 6/Central/F2/gameplay-metadata/conversation audits and `git diff --check`.

Track A result (2026-09-03): **PASS** — 388 Python tests, 10 browser tests, 0 exact duplicate files, 21 retained domain/test duplicate-function candidates, 3 bootstrap implementations and 0 reviewed Ruff unused findings. Obsolete preview/POC source, rejected host-first design docs, generated workspace output and the duplicate build manifest were removed under the user's explicit cleanup request.

**Exit gate:** Ruff has no unreviewed unused findings; helper duplication is reduced without changing output hashes; the audit report is reproducible; all 377+ regressions remain green; no canonical asset/reference hash changes.

### Track B — Make manifests, source hashes and generated web data single-source

**Purpose:** Prevent the future TS/JS migration from copying multiple subtly different source-of-truth lists and prevent a generated browser artifact from becoming an accidental gameplay source file.

**Files:**

- Create: `RUNTIME/source_contract.py`, `TESTS/test_source_contract.py`.
- Modify: `RUNTIME/browser_bundle_contract.py`, `TOOLS/build_runtime_simulation_bundle.py`, `TOOLS/build_runtime_render_manifest.py`, `VALIDATION/self_audit_central.py`, `VALIDATION/reference_hashes.json`, `CHARACTER/FINAL_MANIFEST.json` and relevant checksum/manifest tests.
- Generated only: `WEB/runtime_simulation_bootstrap.json`, `WEB/runtime_render_manifest.json`, `WEB/runtime_assets/`.

**Interfaces:**

- `source_contract.py.canonical_source_files(profile: Literal["browser_bundle", "render_manifest", "release"]) -> tuple[Path, ...]` owns named, sorted source profiles.
- `canonical_source_hashes(root, profile=...) -> dict[str, str]` is the only source-hash implementation used by builders and validators.
- `build_manifest(...)` remains deterministic and emits `source_profile`, `source_hashes`, `bundle_revision` and generated-output metadata; it never treats generated web files as canonical gameplay input.

**Steps:**

- [ ] Compare the two existing source-file lists and encode their intentional subset relationship as named profiles. Add a test that fails if a builder contains a second literal canonical-source list.
- [x] Confirm all first-party and release/audit consumers of `CHARACTER/BUILD_MANIFEST.json` and `CHARACTER/FINAL_MANIFEST.json`. No first-party consumer or external compatibility requirement is recorded; `FINAL_MANIFEST.json` is now the sole canonical payload and the build duplicate is removed from checksums/manifests. `00_STARTING_POINT/` was not touched.
- [ ] Keep browser assets and JSON at their existing web paths for compatibility, but make the builders the sole owners. Add freshness/determinism checks so hand-edited generated output fails validation and rebuilds are byte-stable.
- [ ] Verify bundle size, referenced asset existence, source revision and no-image/no-base64 simulation data. Do not reduce data by dropping fields that the future TS/JS runtime needs for local behavior or replay.

**Exit gate:** one canonical manifest payload, one hash registry with explicit profiles, deterministic generated bundle/manifest, release checks still resolve every canonical reference, and all Python/Node suites pass.

### Track C — Collapse the duplicated presentation/projection pipeline

**Purpose:** Ensure one simulation slice produces one neutral frame. This directly addresses the current duplicate projection/telemetry work and makes the future Canvas/TS path cheap.

**Files:**

- Create: `RUNTIME/runtime_frame_service.py`, `TESTS/test_runtime_frame_service.py`.
- Modify: `RUNTIME/runtime_presentation_renderer.py`, `RUNTIME/runtime_render_state.py`, `RUNTIME/central_core.py`, `TOOLS/runtime_review_server.py`, `WEB/runtime_review.html`, `WEB/runtime_render_client.js`, `WEB/runtime_canvas_renderer.js`, `TESTS/test_runtime_presentation_renderer.py`, `TESTS/test_runtime_review_server.py` and `TESTS/test_runtime_review_web.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class RuntimeFrame:
    runtime_snapshot: dict[str, object]
    presentation: dict[str, object]
    render_state: dict[str, object]
    events: tuple[dict[str, object], ...]
    metrics: dict[str, float]

class RuntimeFrameService:
    def advance(self, elapsed_ms: int, *, commands=()) -> RuntimeFrame: ...
    def current(self) -> RuntimeFrame: ...
```

**Steps:**

- [ ] Add a failing projection-count test: a Canvas frame must call `RuntimeRenderStateProjector.project()` once, carry that result through `RuntimePresentationLoop`/`ReviewState`, and never recompute it during payload serialization. A raster request must reuse the same neutral frame and invoke only the raster adapter when explicitly selected.
- [ ] Move frame assembly and one-time metrics ownership into `RuntimeFrameService`. Keep `CentralGameCore.resolve_runtime_presentation()` as the behavior resolver; make the projector and raster renderer pure consumers of the already assembled presentation.
- [ ] Make `ReviewState.frame_payload()` serialize a `RuntimeFrame` rather than rebuilding render state, event summaries or telemetry. Preserve all existing side-panel fields and default `renderer="raster"` behavior.
- [ ] Move dialogue bubble sizes/font-fit inputs and any other visual policy needed by Canvas into the generated manifest. Remove hard-coded duplicate bubble geometry from `WEB/runtime_canvas_renderer.js` only after Python/Canvas parity tests consume the same manifest values.
- [ ] Consolidate mode selection, polling and lifecycle ownership in one browser controller. `runtime_review.html` should provide markup/configuration; the controller should own Browser/Python source selection, renderer selection, start/stop and no-request instrumentation. Raster fallback remains explicit and unchanged.
- [ ] Benchmark equal traces before and after. Record projection count, payload bytes, simulation time, encode time and memory; the lean path must show no Pillow/base64 work during a Canvas frame.

**Exit gate:** one projection per frame, no duplicate telemetry assembly, Canvas still has no `/api/tick` requirement after browser bootstrap, raster parity remains green, and the browser review UI has no duplicated lifecycle implementation.

### Track D — Reduce core responsibility clusters while preserving the public façade

**Purpose:** Make the Python oracle and future TS/JS port understandable by separating pure state codecs/reducers from orchestration, without a flag-day rewrite of callers.

**Files:**

- Create: `RUNTIME/actor_snapshot_codec.py`, `RUNTIME/actor_motion_reducer.py`, `RUNTIME/actor_behavior_reducer.py`, `RUNTIME/conversation_runtime_service.py`, `RUNTIME/runtime_presentation_service.py` and focused tests for each boundary.
- Modify: `RUNTIME/actor_simulation_core.py`, `RUNTIME/central_core.py`, `RUNTIME/conversation_behavior_core.py`, `RUNTIME/speech_scheduler_core.py`, `RUNTIME/work_seat_core.py`, `RUNTIME/work_seat_lifecycle.py` and existing contract/replay tests.

**Steps:**

- [ ] Extract snapshot validation, normalization and retired-snapshot migration from `ActorSimulationCore` into `actor_snapshot_codec.py`. Preserve error types and `gds.runtime_snapshot.v1` fields byte-for-byte.
- [ ] Extract route/movement/action/frame-clock reduction into `actor_motion_reducer.py`; extract behavior/talk-pending/stamina ownership into `actor_behavior_reducer.py`. Keep deterministic ordering and event timestamps explicit in returned values.
- [ ] Extract conversation planning/timing/advance and speech-lane ownership behind `conversation_runtime_service.py`. Keep `CentralGameCore` methods as delegating compatibility wrappers until all tests and browser traces use the service boundary.
- [ ] Extract neutral presentation assembly behind `runtime_presentation_service.py`; it must accept a validated snapshot and return JSON-safe presentation metadata without loading images.
- [ ] Reduce `CentralGameCore` to façade/orchestration responsibilities. Do not rename public methods in this track; add contract tests that compare old façade calls and new service calls for spawn/work, Talk, Effects/HumanBall, Critical/Home, save/load and replay.
- [ ] Split `TOOLS/runtime_review_server.py` only after the frame service is stable: scenario/demo orchestration, payload serialization and HTTP routing should be separate modules. Keep the current port/API endpoints and do not start a second server for tests.

**Exit gate:** high-complexity methods are reduced into independently tested units, the public façade and snapshot/replay contracts remain compatible, browser parity traces are unchanged, and no asset/reference hash changes.

### Track E — Retire legacy seams only with evidence

**Purpose:** Remove compatibility code that is genuinely no longer needed, rather than preserving dead branches forever or breaking old fixtures accidentally.

**Candidate groups and prerequisites:**

- Crowd movement: migrate tests/tools from discrete `schedule`/`crowd_wait` to trajectory scheduling, then remove `resolve_legacy_crowd_movement_schedule` and the old branch only when the legacy API has no supported caller.
- Wander: keep retired-snapshot migration until versioned replay fixtures are converted; then remove automatic legacy route handling, zero-weight `wander` metadata, and the manual `demo_wander` capability if no author/review workflow still needs it. The UI currently does not expose `wander`, so this is a strong candidate but not yet proof of deadness.
- Action paths: migrate all consumers from `legacy_materialized_path`/`legacy_package_path` to canonical frame IDs, update schema/registry/tests, then remove the optional `character_root` compatibility resolver and `CHARACTER/RUNTIME/resolve_action.py --character-root` legacy mode if external use is ruled out.
- World depth/layout: replace legacy metadata and scalar max-Y fallbacks with explicit front-edge profiles for every supported floor, then remove the fallback after all-floor audits pass.
- Review host: after Browser source mode is accepted, keep Python raster as local fallback/oracle but remove only duplicate server-side tick/polling paths that are no longer called.

**Steps:**

- [ ] Add a compatibility inventory with exact callers, fixtures and removal tests for each group. A candidate cannot move to deletion based on grep alone.
- [ ] Add a versioned migration test for every replay/snapshot format that will lose a legacy field. Keep old fixtures in `TESTS/fixtures` or a clearly named history location until the migration is proven.
- [ ] Remove one group per change, run the full suite and required audits, then inspect `git diff` for accidental registry/asset changes. Do not combine legacy deletion with TS/JS behavior changes.

**Exit gate:** each removed seam has no supported caller, a migration/replay policy, a regression test proving the new path, and explicit approval if it changes author-visible review controls.

### Track F — Handoff to the TS/JS production migration

**Purpose:** Finish lean cleanup with a stable, language-neutral seam and a measurable no-request web contract. The actual TypeScript/JavaScript migration is the next task, not part of the cleanup commit.

**Files:**

- Modify: `SCHEMA/`, `RUNTIME/browser_bundle_contract.py`, `WEB/runtime_simulation_core.js`, `WEB/runtime_browser_loop.js`, `TESTS/test_browser_bundle_contract.py`, `TESTS/test_browser_parity_trace.py`, `TESTS/browser_runtime_test.mjs`, `TESTS/test_runtime_review_web.py`, `TOOLS/benchmark_browser_simulation.py`, `HANDOFF.md` and `ROADMAP.md`.
- Add only if needed by the approved next migration plan: generated TypeScript contract types alongside the existing JSON schemas; do not hand-maintain two incompatible type definitions.

**Steps:**

- [ ] Freeze `gds.runtime_snapshot.v1`, `gds.runtime_render_state.v1` and `gds.browser_runtime_bundle.v1` with schema validation, source revisions, deterministic ordering and explicit replay command fields.
- [ ] Make `BrowserRuntimeCore` the target public browser interface: one bootstrap load, local `step()`, `snapshot()`, `renderState()`, `serialize()`, `load()` and `replay()`. Keep the core DOM/Canvas-independent.
- [ ] Add an automated network assertion that Browser source mode makes exactly one bootstrap request, zero periodic `/api/tick` requests and no image/base64 requests during normal animation. Explicit save/load/replay actions may be separately counted.
- [ ] Run Python-to-browser parity on fixed traces at every 60ms boundary, including spawn/work, Talk/standing-pair V-axis orientation, Effects/HumanBall, Critical/Home, speech queue ownership, save/load and replay. Fail on event order, timing, actor ids, frame metadata or numeric positions beyond the documented tolerance.
- [ ] Run the simulated 24-hour trace, real browser soak, author visual/gameplay review and release-clean extraction before allowing Python live-web code to be retired. Keep the Python oracle until all gates are explicitly accepted.

**Exit gate:** the next migration can implement TS/JS against a frozen contract, one browser runtime owns the live single-user clock, normal animation is request-free after bootstrap, and the Python fallback/oracle remains available for rollback.

## Validation matrix

Run the narrowest relevant command after each track, then the complete matrix before any completion claim:

```text
python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
python -B -m pytest -p no:cacheprovider -q
node --test TESTS/browser_runtime_test.mjs
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_work_seat_lifecycle.py
python VALIDATION/self_audit_phase6_spatial.py
python VALIDATION/self_audit_central.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_conversation.py
python TOOLS/render_runtime_presentation_qa.py
python TOOLS/benchmark_runtime_renderers.py
git diff --check
```

Before a release package, remove only explicitly approved generated workspace artifacts, rebuild the archive from the project root, extract it into a fresh directory and require `release_clean=true`. Never package `LOCAL_REVIEW/`, `releases/.staging/`, `.pytest_cache/`, `__pycache__/`, preview/debug outputs or materialized occupancy caches.

## Acceptance and rollback gates

- Track A–B are code hygiene/data-lineage changes. Roll back the individual change if any canonical hash, generated revision or behavior trace changes unexpectedly.
- Track C–D are runtime refactors. Keep old façade/adapter paths until parity tests pass; if a refactor changes a trace, restore the last green adapter and isolate the behavior difference before continuing.
- Track E is deletion. Require a caller inventory, migration fixture and explicit author approval for any author-visible control removal.
- Track F is the handoff. Do not claim “web migration ready” until the one-bootstrap/zero-tick network test, parity suite, browser soak, visual/gameplay acceptance and release-clean package all pass.

## Execution handoff

This plan is intentionally ordered as: objective hygiene → one source of truth → one frame pipeline → smaller Python boundaries → evidence-based legacy retirement → TS/JS migration handoff. Do not execute Track F in the same branch as Tracks A–E.

Recommended execution mode: use a fresh subagent/checkpoint per track, review the diff and validation evidence between tracks, and keep each track in a separate commit. Inline execution is acceptable for Track A only if the user wants the cleanup performed in the current task.
