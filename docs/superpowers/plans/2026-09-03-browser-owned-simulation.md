# Browser-Owned Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task with review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the single-user live simulation into browser JavaScript after one bootstrap load while preserving Python behavior, Canvas visuals, local workflow, save/load, replay and raster fallback.

**Architecture:** Python remains the canonical gameplay implementation, source-data exporter and parity oracle. A deterministic browser runtime consumes a generated `floor02` bundle, advances the same fixed simulation slices locally, projects the existing `gds.runtime_render_state.v1` contract and feeds the existing `RuntimeCanvasRenderer`. The Python-hosted Canvas and Raster modes remain available as compatibility and visual-oracle paths.

**Tech Stack:** Python 3.10+, existing Central/RUNTIME/WORLD/CHARACTER registries, deterministic JSON, browser ES modules, HTML Canvas 2D, `requestAnimationFrame`, browser `localStorage`, Node built-in test runner and pytest; no new runtime dependency or Python-in-browser runtime.

**Spec:** `docs/superpowers/specs/2026-09-03-browser-owned-simulation-design.md`

## Global Constraints

- Do not edit `00_STARTING_POINT/` or replace canonical static world/character assets.
- Do not alter gameplay decisions, timing constants, authored floor geometry, WorkSeat placement, dialogue catalog policy or reference hashes.
- Keep Python `CentralGameCore` as the behavior oracle and keep the Python-hosted Canvas/Raster paths working.
- Browser mode must not call `/api/tick`, instantiate `RuntimeRenderClient` or use Pillow during normal animation after bootstrap.
- Do not run Python, Pillow or Pyodide in the browser; do not add WebGL, WebGPU, a game engine or a bundler for this slice.
- The browser core must be DOM/Canvas-independent; `RuntimeCanvasRenderer` remains the only pixel compositor.
- Use integer simulation milliseconds and the existing 60ms simulation boundary; compare non-integer positions with absolute tolerance `1e-6` only.
- Generated browser bundles must be deterministic, hash their canonical inputs and fail on unresolved ids, duplicate ids or missing frame metadata.
- Use `apply_patch` for text/code edits and deterministic builders for generated JSON/assets.
- Run focused tests after every behavior family, then `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q`, required navigation/world/WorkSeat/Phase 6/Central/F2/gameplay-metadata/conversation audits, Node browser tests, `git diff --check` and the browser benchmark before completion.
- Keep acceptance-pending separate from author-approved status in `HANDOFF.md` and `ROADMAP.md`.

## File Map

| File | Responsibility |
| --- | --- |
| `TOOLS/build_runtime_simulation_bundle.py` | Export deterministic browser bootstrap data from canonical Python registries and an initial runtime snapshot. |
| `TOOLS/export_browser_parity_trace.py` | Produce fixed Python oracle traces from selected commands, seeds and floors. |
| `RUNTIME/browser_bundle_contract.py` | Validate bundle/trace schemas and canonical source hashes without rendering images. |
| `WEB/runtime_simulation_prng.js` | Match the Python seeded-random sequence and expose deterministic choice/d6 helpers. |
| `WEB/runtime_simulation_state.js` | Clone, validate and normalize `gds.runtime_snapshot.v1` browser state. |
| `WEB/runtime_simulation_clock.js` | Fixed 60ms accumulator, bounded catch-up and visibility policy. |
| `WEB/package.json` | Scope the browser ES modules as Node/browser-compatible modules for the dependency-free test harness. |
| `WEB/runtime_simulation_navigation.js` | Browser data-backed room/occupancy/portal/path queries. |
| `WEB/runtime_simulation_actor.js` | Actor reducer, route progress, action/direction/subaction and animation clocks. |
| `WEB/runtime_simulation_work_seat.js` | WorkSeat ownership, seat entry/exit boundaries, workstation and PC channels. |
| `WEB/runtime_simulation_speech.js` | Speech lane, pending requests, conversation timing, dialogue selection and emotion result. |
| `WEB/runtime_simulation_effects.js` | Stamina, VFX, HumanBall and effect channel transitions. |
| `WEB/runtime_simulation_core.js` | Public `BrowserRuntimeCore` facade and deterministic step/command/snapshot/render-state flow. |
| `WEB/runtime_browser_loop.js` | Browser-owned fixed-step loop, RAF rendering and no-fetch runtime lifecycle. |
| `WEB/runtime_simulation_persistence.js` | Browser save/load/replay package validation and local-storage adapter. |
| `WEB/runtime_simulation_bootstrap.json` | Generated floor02 bootstrap bundle used by the review page. |
| `WEB/runtime_review.html` | Add Browser/Python source selection while preserving Canvas/Raster renderer selection and controls. |
| `TESTS/test_browser_bundle_contract.py` | Python bundle schema, determinism, source-hash and reference checks. |
| `TESTS/test_browser_parity_trace.py` | Python oracle trace generation and Node runner comparison. |
| `TESTS/browser_runtime_test.mjs` | Node built-in tests for pure browser runtime modules. |
| `TESTS/browser_runtime_parity_runner.mjs` | Read a JSON trace from stdin and emit normalized browser snapshots/events. |
| `TESTS/test_runtime_review_web.py` | Static contract checks for source modes and zero-poll browser path. |
| `TOOLS/benchmark_browser_simulation.py` | Compare Python lean polling, browser step cost, bootstrap size and zero-request behavior. |

## Interfaces

The Python builder produces `gds.browser_runtime_bundle.v1`:

```python
{
    "schema": "gds.browser_runtime_bundle.v1",
    "version": "1.0.0",
    "floor_id": "floor02",
    "bundle_revision": "<sha256>",
    "source_hashes": {"world": "<sha256>", "character": "<sha256>"},
    "simulation": {
        "step_ms": 60,
        "seed_namespace": "gds-browser-runtime-v1",
        "constants": {},
    },
    "world": {"navigation": {}, "portals": {}, "rooms": {}},
    "work_seats": {},
    "characters": {},
    "dialogue": {},
    "effects": {},
    "initial_snapshot": {},
}
```

The browser facade exposes these exact methods:

```javascript
export class BrowserRuntimeCore {
  static async create({ bundleUrl, bundle, floorId, seed, fetchImpl } = {}) {}
  constructor({ bundle, floorId, seed }) {}
  step(elapsedMs, { actorCommands = [], speechCommands = [] } = {}) {}
  snapshot() {}
  renderState(atMs = this.clockMs) {}
  command(command) {}
  serialize() {}
  load(payload) {}
  replay(packagePayload) {}
  destroy() {}
}
```

`step()` returns:

```javascript
{
  snapshot: { schema: "gds.runtime_snapshot.v1" },
  renderState: { schema: "gds.runtime_render_state.v1" },
  events: [],
}
```

The browser loop exposes:

```javascript
export class BrowserRuntimeLoop {
  constructor({ core, renderer, clock = globalThis.performance, raf = globalThis.requestAnimationFrame }) {}
  start() {}
  stop() {}
  handleVisibilityChange(hidden) {}
}
```

## Implementation Tasks

### Task 1: Freeze the browser bundle and parity contracts

**Files:**
- Create: `RUNTIME/browser_bundle_contract.py`
- Create: `TOOLS/build_runtime_simulation_bundle.py`
- Create: `TOOLS/export_browser_parity_trace.py`
- Create: `TESTS/test_browser_bundle_contract.py`
- Create: `TESTS/test_browser_parity_trace.py`
- Create: `WEB/runtime_simulation_bootstrap.json`
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- `build_bundle(root: Path, floor_id: str) -> dict[str, object]`
- `write_bundle(root: Path, floor_id: str, output: Path) -> dict[str, object]`
- `validate_bundle(bundle: Mapping[str, Any], *, expected_floor_id: str | None = None) -> dict[str, Any]`
- `export_trace(root: Path, floor_id: str, scenario: str, seed: str) -> dict[str, Any]`
- `validate_trace(trace: Mapping[str, Any]) -> dict[str, Any]`

- [ ] **Step 1: Write the failing bundle schema tests.**

  Add tests that build `floor02` twice and assert byte-identical canonical JSON,
  `schema == "gds.browser_runtime_bundle.v1"`, `simulation.step_ms == 60`,
  `initial_snapshot.schema == "gds.runtime_snapshot.v1"`, stable actor ids,
  non-empty navigation/work-seat/character/dialogue data and a non-empty
  `bundle_revision`. Add rejection tests for another floor id, a duplicate
  workstation id, a missing character frame reference and a changed source hash.

```python
def test_floor02_bundle_is_deterministic(project_root, tmp_path):
    first = build_bundle(project_root, "floor02")
    second = build_bundle(project_root, "floor02")
    assert canonical_json(first) == canonical_json(second)
    assert first["schema"] == "gds.browser_runtime_bundle.v1"
    assert first["simulation"]["step_ms"] == 60
    assert first["initial_snapshot"]["schema"] == "gds.runtime_snapshot.v1"
    assert first["bundle_revision"]

def test_bundle_rejects_unresolved_reference(project_root, monkeypatch):
    bundle = build_bundle(project_root, "floor02")
    bundle["characters"]["employee_001"]["frames"][0]["asset_id"] = "missing"
    with pytest.raises(BundleContractError, match="unresolved asset"):
        validate_bundle(bundle, expected_floor_id="floor02")
```

- [ ] **Step 2: Run the focused tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_browser_bundle_contract.py`

  Expected: FAIL because the bundle builder and contract validator do not yet exist.

- [ ] **Step 3: Implement the Python bundle contract and deterministic exporter.**

  Read only existing `LayoutCore`, `NavigationOccupancyCore`, `WorkSeatCore`,
  character action/frame registries, dialogue catalog, effect registries and
  `CentralGameCore.resolve_runtime_snapshot("floor02")`. Sort all mapping keys
  and id lists, use compact UTF-8 JSON, compute `bundle_revision` from the
  builder schema plus canonical source bytes, and validate every referenced
  asset/frame before returning. Do not call `CharacterSystem.render`, Pillow
  composition or any image encoder.

```python
def build_bundle(root: Path, floor_id: str) -> dict[str, object]:
    source_hashes = canonical_source_hashes(root)
    bundle = {
        "schema": "gds.browser_runtime_bundle.v1",
        "version": "1.0.0",
        "floor_id": floor_id,
        "source_hashes": source_hashes,
        "simulation": {"step_ms": 60, "seed_namespace": "gds-browser-runtime-v1", "constants": runtime_constants()},
        "world": export_world_runtime_inputs(root, floor_id),
        "work_seats": export_work_seat_inputs(root, floor_id),
        "characters": export_character_runtime_inputs(root),
        "dialogue": export_dialogue_runtime_inputs(root),
        "effects": export_effect_runtime_inputs(root),
        "initial_snapshot": CentralGameCore(root).resolve_runtime_snapshot(floor_id),
    }
    validate_bundle(bundle, expected_floor_id=floor_id)
    bundle["bundle_revision"] = sha256_canonical(bundle)
    return bundle
```

- [ ] **Step 4: Implement the Python parity-trace exporter.**

  Define scenario command lists in one ordered table: `spawn_work`,
  `talk_pair`, `effects_humanball`, `critical_home`, and `save_load_replay`.
  For each 60ms step, call the existing Python runtime boundary, record the
  canonical snapshot, the render state, events and commands, and validate the
  trace schema before writing it. Trace output must contain no images or full
  replay history beyond the explicit command steps.

- [ ] **Step 5: Generate and validate the checked-in floor02 bundle.**

  Run: `python TOOLS/build_runtime_simulation_bundle.py --floor-id floor02 --output WEB/runtime_simulation_bootstrap.json`

  Run: `python TOOLS/export_browser_parity_trace.py --floor-id floor02 --scenario spawn_work --seed gds-browser-runtime-v1 --output TESTS/browser_parity_spawn_work.json`

  Expected: the bundle and trace validate, all referenced data is present, and
  no canonical world/character file is modified.

- [ ] **Step 6: Commit the contract and generated bootstrap.**

```text
git add RUNTIME/browser_bundle_contract.py TOOLS/build_runtime_simulation_bundle.py TOOLS/export_browser_parity_trace.py TESTS/test_browser_bundle_contract.py TESTS/test_browser_parity_trace.py WEB/runtime_simulation_bootstrap.json HANDOFF.md ROADMAP.md
git commit -m "feat: define browser simulation bundle contract"
```

### Task 2: Add deterministic browser primitives and a no-DOM core shell

**Files:**
- Create: `WEB/runtime_simulation_prng.js`
- Create: `WEB/runtime_simulation_state.js`
- Create: `WEB/runtime_simulation_clock.js`
- Create: `WEB/runtime_simulation_core.js`
- Create: `TESTS/browser_runtime_test.mjs`
- Create: `TESTS/browser_runtime_parity_runner.mjs`
- Modify: `TESTS/test_browser_parity_trace.py`

**Interfaces:**
- `DeterministicRng(seed).nextUint32()`, `.nextFloat()`, `.choice(items)`, `.d6()`
- `validateRuntimeSnapshot(snapshot) -> snapshot`
- `cloneRuntimeSnapshot(snapshot) -> snapshot`
- `FixedStepClock({ stepMs = 60, maxCatchupMs = 1000 })`
- `FixedStepClock.pushElapsed(elapsedMs) -> number[]`
- `BrowserRuntimeCore.create(...)` and methods from the plan interface

- [x] **Step 1: Write failing Node tests for seed, state and clock contracts.**

  Use Node's built-in `node:test` and `node:assert/strict`. The seed vector
  must include the first five integer outputs and one d6 result exported by
  Python. State validation must reject a wrong schema, missing actor/speech/
  conversation channels and mismatched actor ids. The clock must consume 60ms
  fixed slices and clamp a 5,000ms foreground jump to the documented maximum.

```javascript
test("fixed clock returns bounded fixed slices", () => {
  const clock = new FixedStepClock({ stepMs: 60, maxCatchupMs: 180 });
  assert.deepEqual(clock.pushElapsed(200), [60, 60, 60]);
  assert.deepEqual(clock.pushElapsed(5000), [60, 60, 60]);
});

test("browser core starts from the canonical snapshot without network", async () => {
  const core = await BrowserRuntimeCore.create({ bundle: fixtureBundle(), floorId: "floor02", seed: "test" });
  const result = core.step(60);
  assert.equal(result.snapshot.schema, "gds.runtime_snapshot.v1");
  assert.equal(result.renderState.schema, "gds.runtime_render_state.v1");
  core.destroy();
});
```

- [x] **Step 2: Run the Node tests to verify they fail.**

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Expected: FAIL because the browser modules and methods are not implemented.

- [x] **Step 3: Implement the exact seeded-random and snapshot primitives.**

  Match the Python seed namespace and integer ordering from the generated seed
  vector. Use unsigned 32-bit arithmetic explicitly, never `Math.random()`.
  Clone state through structured JSON-compatible values, preserve integer clock
  fields and validate actor-id sets across actor, speech and conversation
  channels before mutation.

- [x] **Step 4: Implement the fixed-step clock.**

  Keep `accumulatorMs`, `simulationClockMs`, `stepMs` and `maxCatchupMs` as
  integers. `pushElapsed()` caps elapsed input, emits at most
  `floor(maxCatchupMs / stepMs)` slices, and leaves any excess elapsed time out
  of the next visible frame. `reset()` clears the accumulator. Visibility
  handling belongs to the browser loop, not the simulation core.

- [x] **Step 5: Implement the no-DOM core shell.**

  `BrowserRuntimeCore.create()` accepts either an in-memory `bundle` for tests
  or fetches `bundleUrl` exactly once. Its constructor clones and validates the
  initial snapshot. Until behavior modules are wired, `step(60)` must advance
  the clock and return a valid unchanged-state projection; it must not touch
  Canvas, DOM, `Image` or a server endpoint.

- [x] **Step 6: Add the stdin parity runner and commit the primitive slice.**

  `TESTS/browser_runtime_parity_runner.mjs` reads one JSON trace from stdin,
  creates the core with the supplied bundle, runs each command step and writes
  compact normalized JSON to stdout. The Python test invokes it with
  `subprocess.run(..., check=True, input=trace_json, text=True, capture_output=True)`
  and asserts schema/sequence shape before later tasks add exact behavior
  comparisons.

  Run: `node --test TESTS/browser_runtime_test.mjs`

```text
git add WEB/runtime_simulation_prng.js WEB/runtime_simulation_state.js WEB/runtime_simulation_clock.js WEB/runtime_simulation_core.js TESTS/browser_runtime_test.mjs TESTS/browser_runtime_parity_runner.mjs TESTS/test_browser_parity_trace.py
git commit -m "feat: add deterministic browser runtime shell"
```

### Task 3: Port navigation, actor movement, action clocks and WorkSeat

**Files:**
- Create: `WEB/runtime_simulation_navigation.js`
- Create: `WEB/runtime_simulation_actor.js`
- Create: `WEB/runtime_simulation_work_seat.js`
- Modify: `WEB/runtime_simulation_core.js`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `TESTS/test_browser_parity_trace.py`

**Interfaces:**
- `BrowserNavigation({ world }).isWalkable(u, v)`
- `BrowserNavigation({ world }).findPath(startUv, goalUv)`
- `BrowserNavigation({ world }).portal(floorId)`
- `BrowserActorReducer.step(actor, context, elapsedMs, commands) -> { actor, events }`
- `BrowserWorkSeatReducer.step(actor, seatState, context, elapsedMs) -> { actor, seatState, events }`
- `BrowserRuntimeCore.step()` returns snapshots with movement/WorkSeat parity

- [ ] **Step 1: Add failing movement and WorkSeat trace assertions.**

  Extend the Python-generated `spawn_work` trace and Node runner comparison to
  assert actor ids, position coordinates, route phase, action, resolved action,
  direction, subaction, frame index/count, animation clock, workstation id,
  render owner, seat-entry boundary and PC channel at every trace step.

```javascript
assert.equal(actual.actors[0].workstation_id, expected.actors[0].workstation_id);
assert.equal(actual.actors[0].presentation.action, expected.actors[0].presentation.action);
assert.deepEqual(actual.events.map(eventKey), expected.events.map(eventKey));
assertPointClose(actual.actors[0].ground_xy, expected.actors[0].ground_xy, 1e-6);
```

- [ ] **Step 2: Run the movement trace to verify it fails.**

  Run: `python -m pytest -q TESTS/test_browser_parity_trace.py -k spawn_work`

  Expected: FAIL on movement/action/WorkSeat fields because the shell still
  returns the initial state.

- [ ] **Step 3: Implement bundle-backed navigation.**

  Port the data-backed queries needed by the existing pathfinder: walkability,
  room/portal membership, clearance, workstation access and authored movement
  profile. Reuse the exported occupancy cells and portal targets; do not read
  Python files or images from browser code. Return stable path arrays and the
  same no-path/error decisions as Python.

- [ ] **Step 4: Implement actor fixed-slice reduction.**

  Port the existing route timeline and boundary order from
  `ActorSimulationCore`: apply explicit commands, reserve/advance movement,
  resolve ground position and walking depth metadata, then resolve action,
  direction, subaction and frame clock. Preserve integer elapsed time,
  authored speed profiles, portal entry/exit events and frame-zero/normal-work
  boundaries. Emit event timestamps in the same order as Python.

- [ ] **Step 5: Implement WorkSeat ownership and workstation channels.**

  Port `WorkSeatCore` state transitions without image composition. Preserve
  owned seat identity through talk cancellation, critical/home exit, seat entry
  and return-to-work. Resolve PC frame count/index, desk/chair layer ids and
  workstation ownership from the bundle. Keep the state reducer independent of
  `RuntimeCanvasRenderer`.

- [ ] **Step 6: Wire actor and WorkSeat reducers into `BrowserRuntimeCore.step()`.**

  Apply commands in the same order as the Python snapshot boundary, advance
  the actor clock once per fixed slice, update the speech/conversation channels
  through their existing state objects without yet scheduling new speech, and
  project the render state after all reducers finish. Preserve stable employee
  order and sequence increments.

- [ ] **Step 7: Run focused parity and commit.**

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_browser_parity_trace.py -k spawn_work`

  Expected: movement, action, frame and WorkSeat assertions pass for the
  `spawn_work` trace with only the stated position tolerance.

```text
git add WEB/runtime_simulation_navigation.js WEB/runtime_simulation_actor.js WEB/runtime_simulation_work_seat.js WEB/runtime_simulation_core.js TESTS/browser_runtime_test.mjs TESTS/test_browser_parity_trace.py
git commit -m "feat: port browser movement and workseat runtime"
```

### Task 4: Port speech, dialogue, effects, HumanBall, stamina and lifecycle

**Files:**
- Create: `WEB/runtime_simulation_speech.js`
- Create: `WEB/runtime_simulation_effects.js`
- Modify: `WEB/runtime_simulation_core.js`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `TESTS/test_browser_parity_trace.py`

**Interfaces:**
- `BrowserSpeechReducer.step(snapshot, commands, context, elapsedMs) -> { snapshot, events }`
- `BrowserEffectsReducer.step(snapshot, context, elapsedMs) -> { snapshot, events }`
- `BrowserRuntimeCore.step()` preserves speech/effects/lifecycle channels

- [ ] **Step 1: Add failing scenario assertions.**

  Generate and compare `talk_pair`, `effects_humanball` and `critical_home`
  traces. Assert pending request identity/category/due time, lane position,
  participant ids, standing-pair offsets/facings, one persisted d6 outcome,
  dialogue id/locale/text/bubble/opacity, VFX/HumanBall frame channels,
  stamina events, portal exit and return-to-work fields.

- [ ] **Step 2: Run the scenario tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_browser_parity_trace.py -k "talk_pair or effects_humanball or critical_home"`

  Expected: FAIL because the browser core has no speech/effect reducers.

- [ ] **Step 3: Implement the speech lane and seeded dialogue decisions.**

  Port request ordering, lifecycle priority, pending ownership, timeout and
  completion boundaries from `SpeechSchedulerCore` and the recent Central
  correction. Use the exact seed namespace and random draw ordering. Keep
  `talk_pending` actor clocks advancing while the lane is occupied. Select
  dialogue from exported enabled catalog rows and preserve locale, category,
  bubble id, line index, fade timings and opener/reply offsets.

- [ ] **Step 4: Implement standing-pair and conversation state.**

  Preserve lower-`u`/higher-`u` participant order, `SW`/`NE` endpoint facing,
  four-cell separation, one replayable d6 per pair and even/odd emotion
  mapping. Store session/request ids and completion events in the same snapshot
  channels so unrelated lifecycle completion cannot clear another request.

- [ ] **Step 5: Implement effects, HumanBall and stamina channels.**

  Port only metadata transitions: effect asset id/frame index/clock,
  HumanBall owner/position/frame, PC clock and stamina recovery events. Use
  exported frame counts and timing; never inspect image pixels or compose a
  full frame.

- [ ] **Step 6: Wire lifecycle ordering and run all scenario parity tests.**

  Apply speech/effect reducers at the same boundaries as Python, then call the
  existing browser render-state projector. Sort events by timestamp and event
  index before serializing. Keep replay steps explicit and bounded.

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_browser_parity_trace.py`

  Expected: all required scenario traces match ids, labels, clocks, events,
  channels, dialogue and paint order.

```text
git add WEB/runtime_simulation_speech.js WEB/runtime_simulation_effects.js WEB/runtime_simulation_core.js TESTS/browser_runtime_test.mjs TESTS/test_browser_parity_trace.py
git commit -m "feat: port browser speech and effect runtime"
```

### Task 5: Add browser save/load/replay and exact parity harness

**Files:**
- Create: `WEB/runtime_simulation_persistence.js`
- Modify: `WEB/runtime_simulation_core.js`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `TESTS/browser_runtime_parity_runner.mjs`
- Modify: `TESTS/test_browser_parity_trace.py`

**Interfaces:**
- `createSavePackage({ bundleRevision, initialSnapshot, snapshot, steps }) -> object`
- `validateSavePackage(packagePayload, { bundleRevision, floorId }) -> object`
- `BrowserRuntimeCore.serialize() -> string`
- `BrowserRuntimeCore.load(payload) -> object`
- `BrowserRuntimeCore.replay(packagePayload) -> object`

- [ ] **Step 1: Add failing persistence and replay tests.**

  Step a runtime through a Talk and Effects boundary, serialize it, create a
  second runtime from the same bundle, load the package and compare snapshots.
  Replay the saved package from its initial snapshot and compare every trace
  checkpoint to the original. Add rejection tests for a wrong bundle revision,
  floor id, schema and mismatched actor ids.

```javascript
test("save/load and replay are deterministic", async () => {
  const first = await BrowserRuntimeCore.create({ bundle: fixtureBundle(), floorId: "floor02", seed: "test" });
  first.step(60, { actorCommands: [{ type: "start_demo", demo: "talk" }] });
  const saved = first.serialize();
  const second = await BrowserRuntimeCore.create({ bundle: fixtureBundle(), floorId: "floor02", seed: "test" });
  second.load(saved);
  assert.deepEqual(second.snapshot(), first.snapshot());
  assert.deepEqual(second.replay(JSON.parse(saved)), first.snapshot());
});
```

- [ ] **Step 2: Run persistence tests to verify they fail.**

  Run: `node --test TESTS/browser_runtime_test.mjs -t "save/load"`

  Expected: FAIL because serialization and load validation are not present.

- [ ] **Step 3: Implement versioned package creation and validation.**

  Store `schema`, `version`, `floor_id`, `bundle_revision`, `seed`,
  `initial_snapshot`, `current_snapshot` and the explicit command steps. Use
  stable JSON serialization. Validate every field before mutating the live
  runtime and return a new cloned state only after validation succeeds.

- [ ] **Step 4: Implement replay through the same `step()` path.**

  Reset from `initial_snapshot`, apply each recorded command and elapsed slice,
  and return the final snapshot plus trace. Do not call a separate replay
  reducer. Cap the live diagnostic history, while allowing an explicit save
  package to contain the finite recorded steps.

- [ ] **Step 5: Make the Python/Node parity harness compare full scenarios.**

  Normalize only object-key ordering and float positions. Require exact
  equality for all ids, labels, integer clocks, action/frame fields, events,
  WorkSeat channels, dialogue and paint order. Report the first mismatching
  path, Python value and browser value to make rule ownership obvious.

- [ ] **Step 6: Run the full parity gate and commit.**

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_browser_parity_trace.py`

  Expected: all five scenarios, save/load and replay pass; no browser test
  starts a server or calls `fetch` after the in-memory bundle is supplied.

```text
git add WEB/runtime_simulation_persistence.js WEB/runtime_simulation_core.js TESTS/browser_runtime_test.mjs TESTS/browser_runtime_parity_runner.mjs TESTS/test_browser_parity_trace.py
git commit -m "feat: add browser runtime persistence and parity harness"
```

### Task 6: Integrate the no-request browser loop into the review page

**Files:**
- Create: `WEB/runtime_browser_loop.js`
- Modify: `WEB/runtime_review.html`
- Modify: `TESTS/test_runtime_review_web.py`
- Modify: `TESTS/browser_runtime_test.mjs`

**Interfaces:**
- `BrowserRuntimeLoop.start()`, `.stop()`, `.handleVisibilityChange(hidden)`
- `Runtime source` selector values: `browser`, `python`
- Existing `Renderer` selector values: `canvas`, `raster`

- [ ] **Step 1: Add failing static and loop tests.**

  Assert the HTML contains a browser source selector, the bootstrap URL,
  `BrowserRuntimeCore`, `BrowserRuntimeLoop`, and no browser-mode call to
  `RuntimeRenderClient.start()`. Inject a fake `fetch` counter and fake RAF;
  after bootstrap, start the browser loop and assert the counter remains at
  the bootstrap count while frames advance.

```javascript
test("browser loop advances without periodic fetch", async () => {
  let fetchCount = 0;
  const core = await BrowserRuntimeCore.create({ bundle: fixtureBundle(), floorId: "floor02", fetchImpl: async () => { fetchCount += 1; } });
  const loop = new BrowserRuntimeLoop({ core, renderer: fakeRenderer(), raf: fakeRaf });
  loop.start();
  fakeRaf.flush(20);
  assert.equal(fetchCount, 0);
  assert.ok(loop.core.snapshot().actor_snapshot.clock.simulation_time_ms > 0);
  loop.stop();
});
```

- [ ] **Step 2: Run web and Node tests to verify they fail.**

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_runtime_review_web.py`

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Expected: FAIL because the source selector and browser loop do not exist.

- [ ] **Step 3: Implement the browser fixed-step/RAF loop.**

  On each RAF timestamp, pass the bounded real-time delta to
  `FixedStepClock.pushElapsed()`, call `core.step(60)` for each returned slice,
  set the latest render state on `RuntimeCanvasRenderer`, then call
  `renderer.render(timestamp)`. The RAF callback must not call `fetch`, decode
  images or rebuild static assets. Stop must cancel RAF and visibility listeners.

- [ ] **Step 4: Add Browser source mode without changing Python mode.**

  Add `Runtime source: Browser simulation | Python host`. Browser mode loads
  `runtime_simulation_bootstrap.json` once, creates the core and loop, and maps
  existing Full/Talk/Effects/Critical/demo controls to `core.command()`. Python
  mode keeps the current `RuntimeRenderClient` and `/api/tick` path. Browser
  mode always uses Canvas; Raster remains selectable for Python host.

- [ ] **Step 5: Add local persistence wiring.**

  Use a namespaced `localStorage` key containing the validated save package.
  Save/load/replay controls call `core.serialize()`, `core.load()` and
  `core.replay()` directly in browser mode. Preserve the existing download or
  import action if present. A validation failure leaves the current live core
  untouched and displays an actionable note.

- [ ] **Step 6: Add visibility and fallback behavior.**

  When the document becomes hidden, stop advancing simulation steps while
  leaving the last valid Canvas frame. On visibility restore, reset the
  accumulator rather than simulating an unbounded hidden-tab gap. If bootstrap
  validation or module loading fails, stop the browser loop and offer the
  Python-host mode; do not silently call `/api/tick` as a fallback.

- [ ] **Step 7: Run browser smoke and commit.**

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q TESTS/test_runtime_review_web.py TESTS/test_runtime_review_server.py`

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Open the branch page and inspect `floor02`, Full, Talk, Effects, Critical,
  save/load and replay in Browser mode, then switch to Python Canvas and Raster
  to verify rollback. Record console warnings/errors and source-mode changes.

```text
git add WEB/runtime_browser_loop.js WEB/runtime_review.html TESTS/test_runtime_review_web.py TESTS/browser_runtime_test.mjs
git commit -m "feat: run browser-owned simulation without polling"
```

### Task 7: Add performance, 24-hour simulation and browser soak validation

**Files:**
- Create: `TOOLS/benchmark_browser_simulation.py`
- Modify: `TESTS/test_browser_parity_trace.py`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- `benchmark_browser_simulation.py --floor-id floor02 --steps 120000`
- Benchmark JSON schema: `gds.browser_runtime_benchmark.v1`
- Browser metrics: bootstrap bytes, step p50/p95, render p50/p95, fetch count,
  heap checkpoints and actor count

- [ ] **Step 1: Add failing benchmark/long-run tests.**

  Add a Node test that advances a browser runtime through simulated 24 hours
  using 60ms slices in bounded batches, asserts monotonic integer clock,
  finite actor positions, bounded event/command buffers and unchanged bundle
  revision. Add a fake-fetch test that asserts zero calls after bootstrap.

```javascript
test("simulated 24-hour run stays finite and bounded", async () => {
  const core = await BrowserRuntimeCore.create({ bundle: fixtureBundle(), floorId: "floor02", seed: "long-run" });
  for (let batch = 0; batch < 2400; batch += 1) {
    for (let step = 0; step < 600; step += 1) core.step(60);
    assert.ok(Number.isFinite(core.snapshot().actor_snapshot.clock.simulation_time_ms));
    assert.ok(core.debugSizes().eventCount <= 256);
  }
  assert.equal(core.snapshot().actor_snapshot.clock.simulation_time_ms, 86_400_000);
});
```

- [ ] **Step 2: Run long-run tests to verify they fail or expose gaps.**

  Run: `node --test TESTS/browser_runtime_test.mjs -t "24-hour"`

  Expected: FAIL until all lifecycle buffers, fixed-clock accounting and
  browser debug-size reporting are implemented.

- [ ] **Step 3: Implement the benchmark and bounded diagnostics.**

  Measure the browser core in Node without a server, report p50/p95 per-step
  and render-state projection time, bootstrap JSON bytes, actor count and
  command/event buffer sizes. Do not compare Node CPU directly to Cloudflare
  CPU; label it as a local browser-core indicator. Keep the existing renderer
  benchmark for Python lean/raster comparison.

- [ ] **Step 4: Run all automated parity and endurance gates.**

  Run: `node --test TESTS/browser_runtime_test.mjs`

  Run: `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q`

  Run the required no-write Room Navigation, Navigation Occupancy, WorkSeat,
  WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata
  family and conversation audits. Run `git diff --check` and confirm the
  canonical asset/reference hash audit reports no source changes.

- [ ] **Step 5: Run real browser soak validation.**

  Start only the branch server after checking listeners, open the branch page,
  instrument network requests and browser performance, and keep Browser mode
  visible for at least 30 minutes before the 24-hour acceptance run. During
  the final 24-hour run, exercise Full, Talk, Effects, Critical, save/load and
  replay, record heap/frame checkpoints and confirm no `/api/tick` request
  occurs after bootstrap. Stop only the process started for this validation.

- [ ] **Step 6: Update the active handoff and roadmap, then commit evidence.**

  Record exact commands/results, parity status, browser source-mode behavior,
  benchmark numbers, simulated 24-hour result, real soak result and remaining
  author/Cloudflare gates. Do not mark visual/gameplay acceptance or Cloudflare
  deployment complete from automated output alone.

```text
git add TOOLS/benchmark_browser_simulation.py TESTS/test_browser_parity_trace.py TESTS/browser_runtime_test.mjs HANDOFF.md ROADMAP.md
git commit -m "test: verify browser simulation parity and endurance"
```

### Task 8: Keep the branch release-ready and prepare the Cloudflare follow-up

**Files:**
- Modify: `docs/RELEASE_CHECKLIST.md`
- Modify: `docs/LEAN_RELEASE_POLICY.md`
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`
- Create: `docs/superpowers/specs/2026-09-03-browser-simulation-cloudflare-follow-up.md`

**Interfaces:**
- No runtime API changes in this task.
- Follow-up spec records static bundle deployment, optional persistence,
  multi-viewer authority and WebSocket/Durable Object decisions separately.

- [ ] **Step 1: Add release checks for generated browser data.**

  Require `runtime_simulation_bootstrap.json` schema/revision validation, all
  generated referenced files present, no `__pycache__`, `.pytest_cache`,
  `LOCAL_REVIEW`, preview/debug files or materialized occupancy caches, and
  `release_clean=true` before any canonical package promotion.

- [ ] **Step 2: Write the separate Cloudflare follow-up spec.**

  Document the single-user static deployment first, optional save/load API,
  bundle cache invalidation, and the separate multi-viewer authority choice.
  Explicitly state that WebSocket/Durable Object work is not part of the
  browser simulation branch acceptance.

- [ ] **Step 3: Run release audit and update status.**

  Create any release archive only from the clean branch root, extract it into a
  fresh temporary directory, run the same browser bundle and parity checks on
  the extracted files, and remove only the temporary extracted directory after
  verification. Do not promote a package unless `release_clean=true`.

- [ ] **Step 4: Commit the follow-up documentation.**

```text
git add docs/RELEASE_CHECKLIST.md docs/LEAN_RELEASE_POLICY.md docs/superpowers/specs/2026-09-03-browser-simulation-cloudflare-follow-up.md HANDOFF.md ROADMAP.md
git commit -m "docs: define browser simulation cloudflare gate"
```

## Plan Self-Review

- Spec coverage: bundle export, deterministic browser core, fixed clock,
  movement/WorkSeat, speech/effects, persistence/replay, no-request UI mode,
  parity, simulated/real endurance and Cloudflare separation each have tasks.
- File coverage: every named module, generated bundle, test harness, benchmark
  and handoff/release document has one owning task.
- Interface consistency: `BrowserRuntimeCore.step()` returns `snapshot`,
  `renderState` and `events`; the loop consumes `renderState`; persistence
  stores the same snapshot/command contract; the Python trace runner feeds the
  Node runner through stdin.
- Placeholder scan: no incomplete marker, vague implementation step or unnamed
  test step remains in the plan.
- Authority check: Python is the parity oracle, browser is the single-user
  runtime, and a shared Durable Object authority is explicitly deferred.
- Verification coverage: focused Node/Python tests, full pytest, required
  audits, static web checks, no-request instrumentation, simulated 24-hour
  trace, real browser soak and release cleanliness are all explicit.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-03-browser-owned-simulation.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review between tasks.
2. **Inline Execution** — execute tasks in this session using executing-plans with checkpoints.
