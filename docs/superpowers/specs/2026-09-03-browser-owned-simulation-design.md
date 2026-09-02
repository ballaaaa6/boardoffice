# Browser-Owned Simulation Design

## Goal

Make the single-user web runtime execute its live simulation in the browser
after one bootstrap load. The browser must advance the same movement, action,
WorkSeat, speech, dialogue, effect, stamina, save/load and replay behavior as
the current Python runtime while continuing to use the lean Canvas component
renderer. Normal animation must not call `/api/tick`; Python remains the
canonical behavior oracle, data-bundle generator and local compatibility
runtime.

## Design status and scope

This is an exploratory architecture branch based on the approved lean
component-renderer prototype. The branch is `codex/browser-simulation` in
`.worktrees/browser-simulation`. The first implementation target is a single
`floor02` browser session with the existing nine-actor review scenarios.

### In scope

- Export the canonical runtime inputs needed by the browser from the existing
  Python registries and `CentralGameCore`.
- Implement a pure JavaScript, deterministic browser simulation core with a
  fixed simulation step and the existing runtime snapshot shape.
- Preserve actor movement, navigation/portal transitions, action and frame
  clocks, WorkSeat ownership, PC animation, stamina, effects/HumanBall,
  speech scheduling, conversation/dialogue state, critical/home flow,
  save/load and deterministic replay.
- Reuse `RuntimeCanvasRenderer` as the visual consumer of browser-produced
  `gds.runtime_render_state.v1` state.
- Make the review page choose between the current Python-hosted runtime and
  the browser-owned runtime without breaking raster fallback.
- Prove parity against Python traces before expanding beyond `floor02`.
- Measure request count, browser frame rate, simulation step time, heap
  stability and initial bootstrap size.

### Out of scope for this branch

- Multi-user shared world authority, server reconciliation or Durable Object
  synchronization.
- WebSocket transport for the normal single-user loop.
- Running Python, Pillow or Pyodide inside the browser.
- Changing gameplay rules, timing constants, dialogue catalog policy,
  navigation geometry, WorkSeat placement or canonical artwork.
- Replacing Canvas 2D with WebGL/WebGPU or adding a game engine.
- Removing the Python-hosted runtime or raster fallback.
- Cloudflare production deployment. A separate deployment slice follows local
  parity and endurance acceptance.

## Current boundary and why it changes

The lean branch already has the correct visual boundary:

```text
Python CentralGameCore
  -> gds.runtime_render_state.v1
  -> browser RuntimeCanvasRenderer
```

The remaining repeated request is in `RuntimeRenderClient`: the browser sends
`POST /api/tick` every 100ms so Python can advance `CentralGameCore` and return
the next render state. The benchmark of the lean path shows that this request
is cheap locally, but it still creates request volume and prevents a static
asset-only deployment.

The new branch changes the authority boundary for single-user mode:

```text
Python build/oracle
  -> browser bootstrap bundle + manifest
  -> BrowserRuntimeCore
       fixed simulation steps
       commands / speech / seeded RNG
       runtime snapshot
       render-state projection
  -> RuntimeCanvasRenderer at requestAnimationFrame
```

The Python host remains available as a second source mode:

```text
Python ReviewState -> /api/tick -> RuntimeCanvasRenderer or raster fallback
```

The browser and Python paths must exchange the same canonical snapshot and
trace vocabulary. The JavaScript layer may implement simulation rules, but it
must not invent a second visual policy or silently alter authored data.

## Alternatives considered

### A. Browser-owned deterministic simulation — recommended

Port the runtime logic that changes during a live session to dependency-light
JavaScript modules. Generate world, character, WorkSeat, dialogue and timing
inputs from Python at build time. Keep Python as the oracle for parity traces
and local fallback.

This is the only option that removes periodic HTTP requests and keeps the
browser deployable as static assets. It has the largest initial implementation
cost, so the work is staged by deterministic behavior family and stopped at a
parity gate whenever a rule is unclear.

### B. Python in the browser through a WebAssembly Python runtime

This could reuse more Python code, but it adds a large runtime, startup cost,
memory pressure and a second compatibility surface. It directly conflicts
with the goal of a small Cloudflare/browser payload and keeps Pillow-oriented
dependencies near the live path. It is rejected for this branch.

### C. Keep Python authoritative and switch polling to WebSocket/delta updates

This is the lowest-risk path for a shared multi-user world and should remain a
future authority mode. It reduces HTTP request overhead but still requires a
live server and network connection, so it does not satisfy the single-user
zero-periodic-request goal. The existing render-state protocol is deliberately
kept compatible with this future mode.

## Recommended architecture

### 1. Canonical data export

`TOOLS/build_runtime_simulation_bundle.py` creates a deterministic, derived
browser bundle. It reads existing world and character registries; it does not
rewrite them. The bundle contains:

- schema/version, source revision and SHA-256 manifest hash;
- the selected floor id and static scene/renderer manifest revision;
- navigation cells, portals, room domains, clearance and authored movement
  profiles needed by the browser pathfinder;
- workstation, WorkSeat, chair, PC frame and layer metadata;
- employee/character identity, allowed action/direction/subaction frame rules
  and animation timing metadata;
- effect/HumanBall frame metadata and channel timing;
- enabled dialogue lines, bubble policy inputs and locale/category metadata;
- deterministic simulation constants and seed namespace;
- an initial `gds.runtime_snapshot.v1` for the selected floor.

The export must fail on unresolved asset ids, duplicate placement ids, missing
frame metadata or a source/reference hash change. It must use stable key and
list ordering so two builds from the same source produce byte-identical JSON.

### 2. Browser runtime core

The first browser runtime is plain ES modules with JSDoc-style contracts rather
than a new bundler or framework. This preserves the current static web shape
and avoids adding a dependency whose only purpose is compilation.

The core exposes:

```javascript
const runtime = await BrowserRuntimeCore.create({
  bundleUrl,
  floorId: "floor02",
  seed: "gds-browser-runtime-v1",
});

runtime.step(60, { actorCommands: [], speechCommands: [] });
const snapshot = runtime.snapshot();
const renderState = runtime.renderState();
runtime.command(command);
const saved = runtime.serialize();
runtime.load(saved);
```

The exact implementation may split these methods across focused modules, but
the public behavior is fixed:

- `create()` loads and validates the bundle once;
- `step(elapsedMs, commands)` advances deterministic fixed slices and returns
  the canonical snapshot plus event summary;
- `snapshot()` returns a JSON-safe `gds.runtime_snapshot.v1` object;
- `renderState(atMs)` returns `gds.runtime_render_state.v1` without image data;
- `command(command)` validates and queues an actor, speech or demo command;
- `serialize()` and `load(payload)` preserve the same save/load contract;
- `replay(package)` reproduces a recorded command trace without network I/O;
- `destroy()` releases timers/listeners and image-independent runtime data.

The browser core owns no Canvas or DOM references. It only resolves gameplay
and presentation metadata. `RuntimeCanvasRenderer` remains responsible for
image lookup, layer composition, interpolation and dialogue drawing.

### 3. Fixed-step clock and smooth display

Simulation time remains integer milliseconds and uses the existing runtime
step boundary (`SIM_STEP_MS`, currently 60ms). The browser loop has separate
clocks:

```text
requestAnimationFrame timestamp
  -> accumulator
  -> zero or more 60ms BrowserRuntimeCore.step() calls
  -> runtime.renderState()
  -> RuntimeCanvasRenderer.render(timestamp)
```

The accumulator is bounded to prevent a background-tab resume from creating an
unbounded catch-up loop. While visible, normal frames may run multiple fixed
steps if needed; the render layer still draws at display refresh rate. A hidden
tab pauses visual advancement and records the last simulation clock. Continuous
wall-clock progression while hidden is explicitly not part of this first
single-user slice; adding it would require a persisted wall-clock policy and
fast-forward rules rather than silently dropping elapsed time.

### 4. Runtime behavior modules

The port is organized around existing Python contracts, not around the old
file names. Each module has one responsibility:

- deterministic seeded random and integer clock helpers;
- navigation/pathfinding and occupancy queries;
- actor reducer, movement route and action/frame clocks;
- WorkSeat ownership, entry/exit boundaries and workstation channels;
- speech lane, pending requests, conversation sessions and dialogue selection;
- effects/HumanBall/stamina event channels;
- snapshot validation, render-state projection, save/load and replay.

The browser port may call generated data helpers, but it must not call image
renderers, inspect PNG pixels or duplicate Canvas paint-order decisions.

### 5. Review-page source modes

The page adds an explicit source selector:

```text
Runtime source: Browser simulation | Python host
Renderer: Canvas components | Raster fallback (Python host)
```

Browser simulation mode loads the bootstrap bundle once, starts the local
fixed-step loop and sends commands directly to the browser core. It does not
instantiate `RuntimeRenderClient` and does not call `/api/tick` during normal
animation. Save/load uses a namespaced local-storage record plus the existing
download/import path where available.

Python-host mode keeps the current Canvas/raster behavior unchanged. This mode
is the rollback and the parity visual oracle.

## Parity contract

Python is the oracle, not a runtime dependency of the browser path. A parity
trace contains:

```json
{
  "schema": "gds.browser_runtime_parity_trace.v1",
  "floor_id": "floor02",
  "seed": "...",
  "initial_snapshot": {},
  "steps": [
    {
      "elapsed_ms": 60,
      "actor_commands": [],
      "speech_commands": [],
      "python_snapshot": {},
      "python_render_state": {},
      "events": []
    }
  ]
}
```

The comparison is exact for ids, labels, clocks, events, frame indices,
WorkSeat/channel ownership, dialogue ids/text/bubble offsets, paint order and
replay serialization. Position floats use a documented absolute tolerance of
`1e-6` only where the existing Python arithmetic produces non-integer values.
Interpolation is not compared as gameplay state; it is tested separately at
the renderer boundary.

Required first traces cover:

- quiet spawn-to-work and normal work animation;
- Full system live behavior and route/portal transitions;
- Talk pending, accepted, standing pair, bubble offsets, emotion d6 and
  return-to-work;
- Effects, HumanBall, PC animation and stamina recovery;
- Critical/home flow and portal exit;
- save/load and deterministic replay at a mid-session boundary.

The Python trace exporter must use the same command sequence, floor and seed
for every comparison. A mismatch is a branch blocker until its owning rule or
data export is identified; JS-side visual exceptions are not allowed to mask a
gameplay mismatch.

## Persistence and recovery

Browser mode serializes the canonical runtime snapshot, command trace and
bundle revision. Loading rejects a different schema, floor, bundle revision or
invalid snapshot before mutating the live runtime. Replay starts from the
stored initial snapshot and applies recorded steps through the same `step()`
method. The runtime keeps a bounded in-memory command/event history for the
review UI; save packages may contain the full explicit trace, but the live
render loop must not grow an unbounded diagnostic array.

If the browser bundle cannot load or validation fails, the page shows the
existing Python-host option and does not enter a partially initialized loop.
No server request is used as a hidden recovery path in browser-owned mode;
the user can explicitly switch source mode when a server is available.

## Performance and endurance gates

All numbers are recorded on the reference machine and compared with the lean
branch baseline.

### Zero-periodic-request gate

- Browser mode loads only HTML/modules, manifest/assets and one bootstrap data
  bundle during startup.
- An instrumented `fetch`/XHR counter remains unchanged during a normal live
  run after bootstrap.
- Save/load/replay in browser mode are local operations; explicit import/export
  may use a user-selected file but not `/api/tick`.

### Browser runtime gate

- `floor02` remains at least 55 rendered FPS with nine actors and all normal
  Canvas overlays.
- Fixed simulation step p95 is recorded and remains below 2ms on the reference
  machine for the floor02 baseline.
- No actor snap occurs during normal fixed-step display interpolation.
- Heap usage is measured after bootstrap, 10 minutes, 1 hour and the end of a
  simulated 24-hour trace; command/event buffers remain bounded.

### Parity and compatibility gate

- Every required trace matches the Python oracle under the stated tolerance.
- Existing Python-host Canvas and raster paths retain their current tests and
  browser controls.
- Canonical world/character assets and all reference hashes remain unchanged.
- Required navigation, occupancy, WorkSeat, Phase 6, Central, gameplay
  metadata, conversation and runtime-presentation audits remain green.

### 24-hour gate

The first acceptance run is a deterministic simulated 24-hour trace so it can
run in CI. A separate real-browser soak is required before Cloudflare release:
keep a visible browser session open for 24 hours, record periodic heap/frame
metrics, exercise at least one Talk, Effects, Critical, save/load and replay
cycle, and verify that the normal loop still has zero periodic API requests.

## Cloudflare direction after local proof

For the single-user shape, the deployment artifact is static HTML, ES modules,
the render manifest/assets and the generated simulation bootstrap bundle. A
Worker is optional for serving assets and explicit persistence endpoints; the
animation loop does not depend on a resident Python process.

If the product later needs multiple viewers to share one world, retain the
browser core and render-state contract but introduce an authority adapter:
the Durable Object owns the canonical snapshot and clients receive commands or
delta state. That is a separate architecture because it changes authority,
reconnect, conflict and lifecycle semantics.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Python and JS behavior drifts | Generate fixed traces from Python and compare exact state/events before visual review. |
| Port duplicates too much presentation logic | Browser core emits canonical metadata; existing Canvas renderer owns all pixels. |
| Generated bundle becomes a hidden second source of truth | Include source hashes/schema revision and regenerate only from canonical registries. |
| Browser tab throttling causes timing drift | Use integer fixed steps, bounded accumulator and an explicit hidden-tab policy. |
| Dialogue/seeded d6 differs | Port the exact seed namespace/ordering and compare dialogue/emotion trace fields. |
| Save data becomes incompatible | Store schema, floor, bundle revision and validate before mutation. |
| Scope expands into multiplayer | Keep authority/network adapter out of this branch and require a separate design. |
| JS core becomes too large for a static page | Keep modules dependency-free, split by behavior family and measure bootstrap/parse cost before adding tooling. |

## Implementation sequence

1. Freeze the Python snapshot/trace contract and export a deterministic
   `floor02` bootstrap bundle.
2. Add a Node-compatible browser core shell with clock, seeded RNG, snapshot
   validation and a no-DOM test harness.
3. Port actor movement, navigation, action/frame clocks and WorkSeat behavior.
4. Port speech, conversation, dialogue, effects, HumanBall, stamina and
   lifecycle boundaries.
5. Add save/load/replay and exact cross-language parity traces.
6. Integrate browser mode into the review page while preserving Python/raster
   fallback and Canvas rendering.
7. Run performance, zero-request, simulated 24-hour and browser soak gates.
8. Record acceptance and prepare a separate Cloudflare packaging/deployment
   plan only after the browser branch is accepted.
