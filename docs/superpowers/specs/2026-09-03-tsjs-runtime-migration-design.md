# TypeScript/JavaScript Runtime Migration Design

**Date:** 2026-09-03 (Asia/Bangkok)
**Status:** Design approved in conversation; implementation is not started.
**Scope:** Single-user browser-owned production runtime and its Cloudflare static deployment path.

## Decision summary

Move the live production simulation from the Python-hosted web path to a
dependency-light, strict TypeScript runtime. Keep the existing Python runtime
as the canonical oracle, deterministic bundle builder, validation toolchain and
local raster fallback until every acceptance gate is green.

This is a contract-preserving port, not a gameplay rewrite. The canonical
`WORLD/`, `CHARACTER/` and `CONTRACTS/` data, authored geometry, asset files,
simulation timing and public snapshot/render contracts remain unchanged.

The current browser JavaScript is the first implementation reference. A
Python-to-TypeScript converter may be used to scaffold small pure modules, but
its output is never accepted without cross-language parity evidence.

## Assumed product boundary

This design targets a single user/session:

- the browser owns its local simulation after bootstrap;
- normal animation has no recurring `/api/tick` request;
- static HTML, ES modules, generated JSON and assets are deployable through
  Cloudflare static assets;
- Python is not shipped into the browser or Worker;
- multi-user authority, reconciliation, Durable Objects and WebSockets are a
  separate future design.

“Zero request” means zero recurring simulation requests after startup. The
browser still needs to load the page, modules, bootstrap data and assets unless
those resources are deliberately bundled or inlined.

## Current inventory

The repository already has a useful migration seam:

| Area | Current condition | Migration implication |
| --- | --- | --- |
| Canonical data | Authored registries under `WORLD/`, `CHARACTER/`, `CONTRACTS/` | Keep unchanged and hash-addressed |
| Python runtime | Roughly 16–17k lines across the runtime families | Keep as oracle/fallback; port by behavior family |
| Python dependencies | `Pillow`, `jsonschema`, filesystem-oriented helpers | Isolate from the browser path |
| Browser runtime | Existing ES modules, roughly 200KB of runtime code | Convert and type this path instead of translating every Python file |
| Generated input | `WEB/runtime_simulation_bootstrap.json` and render manifest | Preserve as deterministic derived output |
| Browser scope | Deterministic `floor02` slice | Migrate and prove `floor02` first |
| Parity harness | Python trace exporter plus Node runner and golden traces | Make this the main correctness oracle |
| Toolchain | No TypeScript/Wrangler/Vitest configuration yet | Add a small explicit web toolchain |

The large Python files, especially the actor simulation, central facade,
conversation behavior and speech scheduler, must not be translated as one
large class. Their responsibilities need to be represented by focused
TypeScript services/reducers behind the existing browser-core contract.

## Scope partition

### Production TypeScript runtime

Port or type the behavior that changes during a live browser session:

1. deterministic PRNG and fixed clock;
2. runtime state and state migration;
3. navigation, pathfinding, occupancy and portals;
4. WorkSeat ownership and lifecycle;
5. actor movement, actions, frame clocks and stamina;
6. conversation, speech slots and dialogue selection;
7. effects and HumanBall channels;
8. visual selection metadata;
9. runtime snapshot and render-state projection;
10. persistence and deterministic replay;
11. `BrowserRuntimeCore` orchestration;
12. browser fixed-step controller.

### Python retained outside the production path

Keep these in Python unless a later, separate all-tooling migration is
explicitly approved:

- `CentralGameCore` oracle and compatibility facade;
- Pillow raster rendering;
- canonical registry readers and asset pipeline;
- deterministic bundle/export tools;
- validation/audit scripts and release packaging;
- parity trace generation and offline simulations.

Converting these tools does not reduce Cloudflare request volume or Worker
runtime weight, so it is not part of the first production migration.

## Target architecture

```text
WORLD / CHARACTER / CONTRACTS
              |
              v
  Python deterministic bundle builder
              |
              v
  gds.browser_runtime_bundle.v1
              |
              v
       TypeScript runtime core
              |
       +------+------+
       |             |
       v             v
  Browser UI   Optional Worker adapter
       |
       v
  gds.runtime_render_state.v1
       |
       v
  Canvas component renderer
```

The simulation core owns no DOM, Canvas, image object, filesystem, Pillow or
network reference. The renderer consumes metadata-only render state and owns
image lookup, composition, interpolation and pixel drawing.

The logical target layout is:

```text
WEB/
  src/
    runtime/
    browser/
    renderer/
    contracts/generated/
  public/
    runtime_simulation_bootstrap.json
    runtime_render_manifest.json
    runtime_assets/
  dist/
```

The migration may mirror modules in place first to keep diffs reviewable.
Moving files into `WEB/src` is a packaging step after the typed path is
verified; it must not change runtime behavior.

## Stable contracts

The following contracts are frozen for the first port:

- `gds.browser_runtime_bundle.v1`;
- `gds.runtime_snapshot.v1`;
- `gds.runtime_render_state.v1`;
- command and event vocabulary used by the parity traces;
- 60ms integer simulation step;
- source revision and SHA-256 freshness metadata.

The public browser core remains behaviorally compatible with:

```ts
interface BrowserRuntimeCore {
  step(elapsedMs: number, commands?: RuntimeCommandSet): StepResult;
  snapshot(): RuntimeSnapshot;
  renderState(atMs?: number): RuntimeRenderState;
  command(command: RuntimeCommand): void;
  serialize(): RuntimeSavePackage;
  load(payload: RuntimeSavePackage): void;
  replay(trace: ReplayPackage): ReplayResult;
  destroy(): void;
}
```

`create()` remains the one-time asynchronous bootstrap operation. A schema
version or gameplay-rule change requires an explicit contract revision; the
TypeScript port must not silently create a new incompatible shape.

## Type and validation strategy

1. Generate TypeScript declarations from the existing JSON Schemas.
2. Treat generated declarations as build output, never hand-edit them.
3. Validate untrusted JSON with a runtime validator before it reaches reducers.
4. Keep schema validation at bundle, snapshot, command, save and replay
   boundaries.
5. Use explicit normalization for `null`/`undefined`, numeric values, stable
   key ordering and list ordering.

The first web toolchain should add strict TypeScript, a Node-compatible test
runner and deterministic build scripts. Cloudflare-specific configuration is
added only when the local browser path has passed parity and endurance.

## Module migration order

Port by dependency direction, with a test checkpoint after every family:

### 1. Primitives

- PRNG and seed namespace;
- integer clock and fixed-step accumulator;
- numeric constants;
- JSON-safe cloning and stable ordering;
- snapshot validation and migration helpers.

### 2. World services

- walkable-cell and room queries;
- pathfinding and route representation;
- occupancy and portal transitions;
- WorkSeat and workstation ownership.

### 3. Actor behavior

- actor reducer/state transitions;
- movement/action/frame clocks;
- direction and animation metadata;
- stamina and lifecycle boundaries.

### 4. Social and visual events

- speech queue, pending requests and per-actor slots;
- conversation route/endpoint behavior;
- dialogue bag/category selection;
- effects and HumanBall channel timing;
- visual selection bindings.

### 5. Persistence and orchestration

- runtime snapshot projection;
- metadata-only render-state projection;
- save/load validation;
- bounded command/event history;
- exact replay;
- `BrowserRuntimeCore` facade.

The existing browser algorithms should be reused and typed where they already
match the Python oracle. A direct one-to-one translation of
`CentralGameCore` is deliberately avoided.

## Converter policy

The migration tool is an accelerator, not a correctness mechanism.

- Pilot `python2ts` only on isolated pure modules such as PRNG, clock and
  simple reducers.
- Do not feed Pillow/rendering, filesystem, `pathlib`-heavy code or the full
  central facade into an automated conversion pass.
- Treat generated output as disposable scaffolding that must be reviewed,
  typed and covered by parity tests.
- Do not use Transcrypt or `py2many` as the production migration path; their
  supported subsets/targets do not match this runtime boundary.
- Prefer porting the existing browser JavaScript when it already implements
  the required behavior.

## Bundle and data rules

`TOOLS/build_runtime_simulation_bundle.py` remains the initial source of the
browser bundle. It must:

- read only canonical registries and approved contract inputs;
- fail on missing asset ids, duplicate placement ids or unresolved metadata;
- emit stable object keys and list ordering;
- include source hashes, schema revision and bundle revision;
- produce byte-identical JSON for identical source inputs;
- keep generated output separate from canonical source data.

The first acceptance target remains the current `floor02` nine-actor bundle.
All-floor support is a later expansion after the typed core is stable.

## Correctness plan

### Differential traces

For every scenario, run Python and TypeScript with the same:

- bundle;
- floor;
- seed;
- initial snapshot;
- elapsed-time sequence;
- commands.

Compare IDs, labels, clocks, event ordering, frame indices, WorkSeat/channel
ownership, dialogue identity, bubble offsets, paint order and replay output
exactly. Position floats may use the documented absolute tolerance of `1e-6`
only where non-integer Python arithmetic requires it. A mismatch must report a
JSON path and stop the migration gate.

Initial required scenarios:

- spawn to work and normal-work animation;
- portal/home route;
- Talk pending/accepted/return-to-work;
- V-axis standing pair and bubble offsets;
- speech queue contention and per-actor ownership;
- effects, HumanBall and PC animation;
- stamina and Critical flow;
- save/load at a mid-session boundary;
- deterministic replay;
- nine-actor occupancy stress.

### Unit and property tests

- strict TypeScript typecheck;
- unit tests for every reducer/service;
- JSON Schema/Ajv validation tests;
- property tests for route validity, unique ownership, stamina bounds,
  monotonic clocks and replay determinism;
- Python `Hypothesis` and TypeScript `fast-check` for generated trace cases;
- existing Python suite and required project audits remain mandatory.

### Browser tests

Use a real browser test to verify:

- exactly one bootstrap load;
- no periodic `/api/tick` in browser-owned mode;
- no image/base64 request during stepping;
- no hidden Python fallback;
- save/load/replay without server calls;
- no console errors;
- Canvas output at fixed checkpoints.

### Performance and soak

Record and compare with the existing lean baseline:

- rendered FPS, target at least 55 FPS on the reference machine;
- fixed-step p95, target below 2ms for the `floor02` baseline;
- heap after bootstrap, 10 minutes, 1 hour and simulated 24 hours;
- bounded command/event history;
- deterministic simulated 24-hour trace;
- real-browser soak before deployment.

## Acceptance gates

The production source switch is blocked until all gates pass:

| Gate | Required evidence |
| --- | --- |
| G0 baseline | Existing tests green; canonical asset/reference hashes unchanged |
| G1 contracts | Generated types, runtime validation and bundle revision are deterministic |
| G2 primitives | PRNG, clock, state and world-service parity |
| G3 runtime | Actor, WorkSeat, speech, effects and lifecycle parity |
| G4 persistence | Save/load/replay exactness |
| G5 browser | One bootstrap and zero recurring simulation requests |
| G6 presentation | Canvas/render-state parity and explicit author visual/gameplay acceptance |
| G7 endurance | Performance, memory and simulated/real soak evidence |
| G8 Cloudflare | Preview build, Worker-environment tests and static deployment smoke |
| G9 release | Fresh package/extraction, no caches/debug artifacts, `release_clean=true` |

Engineering green does not close author visual/gameplay acceptance.

## Rollback strategy

Keep the Python source mode and current renderer until G9. The review page must
have an explicit source-mode switch so a failed browser build can return to the
Python oracle without reverting canonical data. Each behavior family should be
landed in a separately reviewable commit with its parity fixture. No Python
runtime, raster renderer or old browser module is deleted merely because the
typed replacement compiles.

## Implementation checkpoints

1. Complete the lean-first prerequisite tracks for source profiles, neutral
   frame, facade boundaries, legacy caller inventory and contract freeze.
2. Add the TypeScript/tooling skeleton and generated contract types.
3. Type/port primitives and world services with module-level parity.
4. Port actor, WorkSeat, speech, effects and lifecycle families.
5. Add persistence/replay and full trace comparison.
6. Integrate the browser source mode while preserving Python/raster fallback.
7. Run browser, performance, endurance and author-acceptance gates.
8. Add Cloudflare static packaging and Worker-specific tests.
9. Cut over only after release-clean verification.

## Definition of done for this design

This design is complete when:

- the typed browser runtime produces the same accepted contract outputs as the
  Python oracle;
- browser mode requires no recurring simulation request;
- static deployment can serve the production path without Python/Pillow;
- Python remains available for build, QA and rollback;
- all acceptance gates and author approval are recorded separately;
- canonical source data and reference assets remain unchanged.
