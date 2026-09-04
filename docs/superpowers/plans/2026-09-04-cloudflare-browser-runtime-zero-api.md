# Cloudflare Browser Runtime Zero-API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task with review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing single-user browser simulation as a Cloudflare static web app with no recurring `/api/tick` or other simulation requests after bootstrap.

**Architecture:** Keep Python as the offline canonical-data builder, parity oracle, validation toolchain and local raster fallback. Make a browser-only controller drive the existing `BrowserRuntimeCore` with a 60ms fixed step and feed metadata-only state to `RuntimeCanvasRenderer`; package the page, generated bundle, manifest and PNG assets into `WEB/dist` for Cloudflare Workers Static Assets.

**Tech Stack:** Existing browser ES modules, Node ESM, optional strict TypeScript for the new controller/build boundary, Python bundle/manifest builders, Node `node:test`, Python `pytest`, and Wrangler Static Assets. The first deployment target is the existing `floor02` nine-actor bundle.

**Spec:** `docs/superpowers/specs/2026-09-04-cloudflare-browser-runtime-design.md`

## Global Constraints

- Do not edit canonical `WORLD/`, `CHARACTER/` or `CONTRACTS/` data, authored PNGs, geometry, WorkSeat placement, reference hashes or gameplay timing/policy.
- Keep `WEB/runtime_simulation_bootstrap.json`, `WEB/runtime_render_manifest.json` and `WEB/runtime_assets/` as generated outputs owned by the Python builders.
- Use the existing `BrowserRuntimeCore` contract: one asynchronous `create()` bootstrap, local `step()`, `snapshot()`, `renderState()`, `serialize()`, `load()`, `replay()` and `destroy()`.
- Use integer millisecond simulation time and the existing 60ms fixed step; do not add a request-driven tick loop.
- Keep `RuntimeRenderClient` only as the explicit Python-hosted compatibility adapter; production browser mode must not import or instantiate it.
- Preserve Python oracle/fallback until parity, network, endurance, Cloudflare dry-run and author visual/gameplay acceptance gates are all green.
- “Zero request” means zero recurring simulation/API requests after startup; static module, JSON and image loads are allowed and must be cacheable.
- The first cutover covers `floor02`; all-floor support requires a separately tested per-floor bundle/manifest strategy.

---

### Task 1: Define the static build and Cloudflare asset boundary

**Files:**

- Create: `WEB/wrangler.jsonc`
- Create: `WEB/scripts/build_static.mjs`
- Create: `TOOLS/build_static_web.py`
- Modify: `WEB/package.json`
- Test: `TESTS/test_cloudflare_static_build.py`

**Interfaces:**

- `python TOOLS/build_static_web.py --output WEB/dist` creates a clean static directory containing `index.html`, browser runtime modules, the floor02 bootstrap/manifest and `runtime_assets/`.
- `node WEB/scripts/build_static.mjs` validates the same output and exits nonzero on stale/missing generated inputs; production local-only/API checks are added in Task 3.
- `WEB/wrangler.jsonc` points `assets.directory` at `./dist` and defines no dynamic simulation/API route.

- [ ] **Step 1: Write the failing static-output test.**

```python
def test_static_build_contains_browser_runtime_only(tmp_path):
    from TOOLS.build_static_web import build_static

    output = build_static(ROOT, tmp_path / "dist")
    assert (output / "index.html").is_file()
    assert (output / "runtime_simulation_bootstrap.json").is_file()
    assert (output / "runtime_render_manifest.json").is_file()
    assert (output / "runtime_assets").is_dir()
    assert (output / "runtime_render_client.js").is_file()
    assert not list(output.rglob("*.py"))
```

- [ ] **Step 2: Run the focused test to verify it fails.**

Run: `python -m pytest -q TESTS/test_cloudflare_static_build.py::test_static_build_contains_browser_runtime_only`

Expected: FAIL because `TOOLS.build_static_web` and the static build entrypoint
do not exist yet.

- [ ] **Step 3: Implement the exact static copy boundary.**

Copy these inputs only, resolving all paths from the repository root:

```text
WEB/runtime_review.html              -> dist/index.html
WEB/runtime_canvas_renderer.js       -> dist/runtime_canvas_renderer.js
WEB/runtime_render_client.js         -> dist/runtime_render_client.js
WEB/runtime_simulation_*.js          -> dist/runtime_simulation_*.js
WEB/runtime_simulation_bootstrap.json -> dist/runtime_simulation_bootstrap.json
WEB/runtime_render_manifest.json     -> dist/runtime_render_manifest.json
WEB/runtime_assets/                  -> dist/runtime_assets/
```

The builder owns only the exact output directory, copies bytes
deterministically, reports file/byte counts and bundle/manifest revisions, and
rejects missing inputs. At this compatibility stage it may copy the existing
review HTML and Python client; the production no-localhost/no-API scan is an
explicit gate in Task 3 after the browser cutover. Do not run Python during
the Cloudflare deploy; Python is used before staging to generate and validate
the checked-in bundle and manifest.

Create `WEB/wrangler.jsonc`:

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "gds-central-game-core",
  "compatibility_date": "2026-09-04",
  "assets": {
    "directory": "./dist",
    "not_found_handling": "404-page"
  }
}
```

Install Wrangler as a pinned dev dependency through npm and add package
scripts without implicit canonical-data regeneration:

```json
"scripts": {
  "build:static": "node scripts/build_static.mjs",
  "cf:dry-run": "wrangler deploy --dry-run"
}
```

- [ ] **Step 4: Run the focused test and static build.**

Run: `python -m pytest -q TESTS/test_cloudflare_static_build.py` and
`node WEB/scripts/build_static.mjs`.

Expected: PASS; the report identifies `floor02`, the checked-in bundle and
manifest revisions, and no Python/runtime-server files are staged. The copied
compatibility HTML may still mention the local fallback until Task 3.

- [ ] **Step 5: Run the Cloudflare dry-run without deploying.**

Run: `npm --prefix WEB install --ignore-scripts` followed by
`npm --prefix WEB run cf:dry-run`.

Expected: Wrangler accepts the config and reports a static asset upload plan.

- [ ] **Step 6: Commit the static boundary.**

```bash
git add WEB/package.json WEB/wrangler.jsonc WEB/scripts/build_static.mjs TOOLS/build_static_web.py TESTS/test_cloudflare_static_build.py
git commit -m "build: add Cloudflare static runtime packaging"
```

**Exit gate:** A clean `WEB/dist` can be built and dry-run through Wrangler;
the production page still has its old Python behavior at this point.

### Task 2: Add a browser-owned fixed-step controller

**Files:**

- Create: `WEB/runtime_browser_controller.js`
- Create: `TESTS/browser_browser_controller_test.mjs`
- Modify: `WEB/runtime_simulation_core.js` only if a public helper is needed

**Interfaces:**

```js
export class BrowserRuntimeController {
  constructor({ core, renderer, now, requestAnimationFrame, cancelAnimationFrame, onState, onError });
  start(): void;
  stop(): void;
  frame(nowMs?: number): void;
  step(elapsedMs: number, commands?: { actorCommands?: object[], speechCommands?: object[] }): object;
  destroy(): void;
}
```

The controller owns wall-clock scheduling only. It calls `core.step()` and
passes the returned metadata-only `renderState` to the Canvas renderer. It
never calls `/api/tick`, never uses `setInterval` for simulation, and bounds a
hidden-tab wall-clock jump to the existing core catch-up limit.

- [ ] **Step 1: Write the failing controller test.**

```js
test("controller advances the core locally and never polls an API", async () => {
  let fetchCalls = 0;
  const core = await BrowserRuntimeCore.create({
    bundleUrl: "/runtime_simulation_bootstrap.json",
    floorId: "floor02",
    seed: "controller-test",
    fetchImpl: async () => {
      fetchCalls += 1;
      return { ok: true, json: async () => checkedInBundle() };
    },
  });
  const states = [];
  const controller = new BrowserRuntimeController({
    core,
    renderer: { setState: (state) => states.push(state) },
    now: () => 100,
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
  });
  controller.step(600);
  assert.equal(core.snapshot().actor_snapshot.clock.simulation_time_ms, 600);
  assert.equal(fetchCalls, 1);
  assert.equal(states.at(-1).clock_ms, 600);
  controller.destroy();
});
```

- [ ] **Step 2: Run the test to verify it fails.**

Run: `node --test TESTS/browser_browser_controller_test.mjs`

Expected: FAIL with a missing controller module.

- [ ] **Step 3: Implement the controller.**

Use `performance.now()` only to calculate elapsed wall time. Call
`core.step(Math.min(Math.max(now - previousNow, 0), 1000))`, send the result to
`renderer.setState()` and `onState`, then schedule the next RAF. Bootstrap and
manifest loading happen once in page boot before `start()`.

- [ ] **Step 4: Run controller and existing browser tests.**

Run: `node --test TESTS/browser_browser_controller_test.mjs TESTS/browser_runtime_test.mjs`

Expected: PASS, with no fetch to `/api/*`.

- [ ] **Step 5: Commit the controller.**

```bash
git add WEB/runtime_browser_controller.js TESTS/browser_browser_controller_test.mjs
git commit -m "feat: drive browser runtime without simulation polling"
```

**Exit gate:** A loaded bundle advances and renders locally, independently of
the Python review server.

### Task 3: Make browser mode the deployed default

**Files:**

- Modify: `WEB/runtime_review.html`
- Modify: `WEB/runtime_canvas_renderer.js` only for manifest-driven asset URLs
- Keep: `WEB/runtime_render_client.js` as the explicit Python compatibility path
- Create: `WEB/runtime_browser_scenarios.js` only if retained demo controls need local setup
- Modify: `TESTS/test_runtime_review_web.py`
- Modify: `TESTS/browser_runtime_test.mjs`

**Interfaces:**

- `?mode=browser` is the default and performs one bootstrap load, one manifest load and local simulation.
- `?mode=python` retains the existing localhost review-server behavior for oracle/raster QA.
- Browser mode maps manual ticks to `controller.step()`, live to `controller.start()/stop()`, and save/load/replay to `core.serialize()/load()/replay()` plus `localStorage`.
- Browser mode must not call `/api/health`, `/api/live-start`, `/api/state`, `/api/tick`, `/api/save`, `/api/load` or `/api/replay`.

- [ ] **Step 1: Add a failing network-contract test.**

```python
def test_browser_mode_has_no_simulation_api_dependency():
    html = (ROOT / "WEB" / "runtime_review.html").read_text(encoding="utf-8")
    assert "runtime_browser_controller.js" in html
    assert "mode" in html
```

Add a Node fake-fetch test that boots browser mode, advances it for at least
60 simulated seconds, and fails if any requested URL starts with `/api/` or
contains `/api/tick`.

- [ ] **Step 2: Run the focused tests to capture the current polling behavior.**

Run: `python -m pytest -q TESTS/test_runtime_review_web.py` and
`node --test TESTS/browser_runtime_test.mjs`.

Expected: the new browser-mode assertion fails; existing Python/Canvas tests
remain green as a compatibility baseline.

- [ ] **Step 3: Add the browser boot path and local controls.**

Make browser mode select the floor from the loaded bundle rather than
`/api/floors`, derive capabilities locally, initialize the Canvas renderer once,
render `core.renderState()`, and start the controller. Keep Python behavior
behind an explicit `mode=python` branch. Do not silently fall back to network
APIs from browser mode.

For server-only demo buttons, either implement deterministic local setup in
`runtime_browser_scenarios.js` or leave those controls visible only in
`mode=python`; production must not issue a request to reproduce a demo.

- [ ] **Step 4: Add local persistence and replay.**

Store `core.serialize()` in local storage. Validate floor and bundle revision
through `core.load()` before replacing state. Pass the stored replay package to
`core.replay()` and render checkpoints locally. A malformed/stale package must
show an error without mutating the active core.

- [ ] **Step 5: Run the browser network and parity gates.**

```text
node --test TESTS/browser_browser_controller_test.mjs TESTS/browser_runtime_test.mjs
python -m pytest -q TESTS/test_runtime_review_web.py TESTS/test_browser_parity_trace.py
```

Expected: browser mode has no recurring API requests, current Python/Node
trace comparisons remain green, and Python mode still reaches the local review
host.

- [ ] **Step 6: Commit the browser cutover.**

```bash
git add WEB/runtime_review.html WEB/runtime_browser_controller.js WEB/runtime_browser_scenarios.js WEB/runtime_render_client.js WEB/runtime_canvas_renderer.js TESTS/test_runtime_review_web.py TESTS/browser_runtime_test.mjs TESTS/browser_browser_controller_test.mjs
git commit -m "feat: make browser runtime the static web default"
```

**Exit gate:** The page runs from static files with no simulation/API polling;
`mode=python` remains an explicit local fallback.

### Task 4: Verify the Cloudflare artifact and handoff

**Files:**

- Test: `TESTS/test_cloudflare_network_contract.mjs`
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Rebuild generated browser inputs from canonical data.**

```text
python TOOLS/build_runtime_simulation_bundle.py --floor-id floor02
python TOOLS/build_runtime_render_manifest.py --floor-id floor02
```

Validate source hashes and revisions before staging; do not hand-edit generated
JSON or assets.

- [ ] **Step 2: Build and inspect the static directory.**

Run: `python TOOLS/build_static_web.py --output WEB/dist` and
`node WEB/scripts/build_static.mjs`.

Expected: `WEB/dist/index.html` and every manifest-referenced file exist; no
local absolute paths, Python source, caches or debug artifacts are present.

- [ ] **Step 3: Run the full engineering matrix.**

```text
python -B -m pytest -p no:cacheprovider -q --ignore=.worktrees
node --test TESTS/browser_runtime_test.mjs TESTS/browser_browser_controller_test.mjs
python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_work_seat_lifecycle.py
python VALIDATION/self_audit_phase6.py
python VALIDATION/self_audit_central.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_conversation.py
npm --prefix WEB run cf:dry-run
git diff --check
```

Expected: required audits pass, the browser network test reports zero recurring
API calls, and Wrangler accepts the static upload.

- [ ] **Step 4: Fresh static smoke test.**

Serve only `WEB/dist` in a clean browser context, run at least 60 simulated
seconds, use manual step, save, load and replay, and inspect the network log.
Only initial static resource loads are allowed; no `/api/` request is allowed.

- [ ] **Step 5: Record acceptance without premature closure.**

Update `HANDOFF.md` with build revisions, test counts and network evidence.
Update `ROADMAP.md` only when each gate is actually green. Do not remove Python
or the raster fallback in this plan.

**Exit gate:** The Cloudflare static artifact is deployable and the browser owns
the live simulation; actual production deployment and author visual/gameplay
acceptance remain separate explicit actions.

## Deferred all-floor expansion

The current checked-in browser bundle and render manifest are `floor02` only.
To expose all 25 floors without reintroducing a server tick API, create a
deterministic floor catalog plus one static bundle and render manifest per floor
(or a validated combined equivalent), update the selector to perform at most
one load on floor change, and add parity/network tests for every floor. This is
not part of the first Cloudflare cutover.
