# Host-First Realtime Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace client-driven full-image ticking with one host-owned simulation clock, compact state delivery, and a lightweight Canvas 2D browser view while preserving the current raster review path and one shared world.

**Architecture:** `WorldAuthority` owns the all-floor `CentralGameCore` snapshot and advances it on a fixed 60ms host clock, independent of HTTP requests. `runtime_state_protocol` projects render-ready per-floor state, keeps bounded deltas, and serves full/delta responses; the browser polls that state at 10–20Hz and draws cached static layers/sprites at `requestAnimationFrame` frequency. The current Pillow/raster path remains a feature-flagged fallback until floor-by-floor visual parity is accepted.

**Tech Stack:** Python 3.10 standard library (`threading`, `time`, `gzip`, `hashlib`, `json`, `tempfile`, `os`), existing `CentralGameCore`/Pillow runtime, vanilla browser JavaScript, Canvas 2D, pytest. No new runtime dependency is introduced.

**Spec:** `docs/superpowers/specs/2026-09-02-host-first-realtime-runtime-design.md`

## Global Constraints

- Preserve `CentralGameCore`, `gds.runtime_presentation_snapshot.v1`, gameplay rules, navigation geometry, authored dialogue, and all static asset/reference hashes.
- The live authority is the only component allowed to advance simulation time; HTTP clients only read state or enqueue validated commands.
- The authority continues while zero browsers are connected and performs no Pillow render, image encode, or JSON network serialization without a subscriber.
- The first transport is HTTP polling; do not add Cloudflare, WebSocket, WebRTC, WebGL, or video streaming in this plan.
- Keep `presentation_mode=raster|state`; raster is the rollback/default mode until Canvas parity is explicitly accepted.
- Use `validate=False` only inside the trusted, normalized authority hot path; validate snapshots at construction, checkpoint load, and explicit boundaries. Never remove validation/copy behavior from existing public APIs without a regression test.
- Use test-first development: every production behavior change has a failing test observed before implementation.
- Run `python -m pytest -q` after each runtime task. Run navigation/world/WorkSeat/Phase 6/Central/gameplay-metadata audits when affected.
- Do not package or promote a release in this plan; the Phase 8E author visual/gameplay gate remains open.

---

### Task 1: Define the compact render-state protocol

**Files:**
- Create: `RUNTIME/runtime_state_protocol.py`
- Create: `TESTS/test_runtime_state_protocol.py`

**Interfaces:**
- `STATE_SCHEMA = "gds.runtime_presentation_state.v1"`
- `project_presentation_state(presentation: Mapping[str, Any], *, floor_id: str, sequence: int, clock_ms: int) -> dict[str, Any]`
- `diff_presentation_state(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]`
- `apply_presentation_delta(base: Mapping[str, Any], delta: Mapping[str, Any]) -> dict[str, Any]`
- `class PresentationHistory(max_entries: int = 256)` with `publish(state) -> None` and `response(*, floor_id: str, since: int | None) -> dict[str, Any]`

The full state shape is `{schema, floor_id, sequence, clock_ms, full: true, actors, events}`. Each actor row contains only render and low-cost HUD fields: `employee_id`, `visible`, `ground_xy`, `depth`, `character_id`, `action`, `subaction`, `direction`, character/PC/effect/HumanBall frame indices and counts, opacity, dialogue state, stamina band, presence, activity, route phase, and presentation transition. A delta contains `base_sequence`, `sequence`, `clock_ms`, `full: false`, `actors_upsert`, `removed_actor_ids`, and `events`.

- [ ] **Step 1: Write the projection failure test**

```python
def test_project_presentation_state_keeps_render_fields_and_drops_debug_payload():
    from RUNTIME.runtime_state_protocol import project_presentation_state

    state = project_presentation_state(
        {
            "schema": "gds.runtime_presentation_snapshot.v1",
            "actors": {
                "A": {
                    "employee_id": "A", "visible": True,
                    "ground_xy": [10.0, 20.0], "action": "move",
                    "direction": "SE", "character_frame_index": 1,
                    "debug_trace": ["omit-me"],
                }
            },
            "events": [{"type": "route_sample"}],
        },
        floor_id="floor02", sequence=7, clock_ms=420,
    )

    assert state["schema"] == "gds.runtime_presentation_state.v1"
    assert state["sequence"] == 7
    assert state["actors"][0]["ground_xy"] == [10.0, 20.0]
    assert "debug_trace" not in state["actors"][0]
```

- [ ] **Step 2: Run the focused test and verify the expected missing-function failure**

Run: `python -m pytest TESTS/test_runtime_state_protocol.py::test_project_presentation_state_keeps_render_fields_and_drops_debug_payload -q`

Expected: FAIL because `RUNTIME.runtime_state_protocol` does not yet define `project_presentation_state`.

- [ ] **Step 3: Implement the schema constant, field projection, strict sequence checks, and deterministic actor sorting**

Use an explicit tuple of allowed actor keys, reject a non-dict presentation or wrong source schema with `RuntimeStateProtocolError`, normalize `depth` from `ground_xy[1]` when the source row has no depth, and sort actors by `employee_id`.

- [ ] **Step 4: Add delta reconstruction and bounded-history tests**

```python
def test_delta_reconstructs_current_and_history_resyncs_when_sequence_is_old():
    from RUNTIME.runtime_state_protocol import (
        PresentationHistory, apply_presentation_delta, diff_presentation_state,
    )

    first = {"schema": "gds.runtime_presentation_state.v1", "floor_id": "floor02", "sequence": 1, "clock_ms": 60, "full": True, "actors": [{"employee_id": "A", "x": 1}], "events": []}
    second = {**first, "sequence": 2, "clock_ms": 120, "actors": [{"employee_id": "A", "x": 2}, {"employee_id": "B", "x": 4}]}
    delta = diff_presentation_state(first, second)
    assert apply_presentation_delta(first, delta) == second

    history = PresentationHistory(max_entries=1)
    history.publish(first); history.publish(second)
    assert history.response(floor_id="floor02", since=1)["full"] is True
```

- [ ] **Step 5: Run the protocol tests and commit the self-contained contract**

Run: `python -m pytest TESTS/test_runtime_state_protocol.py -q`

Expected: PASS with projection, delta, sequence-gap, unchanged-response, and bounded-history coverage. Commit: `git add RUNTIME/runtime_state_protocol.py TESTS/test_runtime_state_protocol.py && git commit -m "feat: add compact runtime state protocol"`.

### Task 2: Implement the host-owned simulation authority

**Files:**
- Create: `RUNTIME/world_authority.py`
- Create: `TESTS/test_world_authority.py`

**Interfaces:**
- `class WorldAuthorityError(RuntimeError)`
- `class WorldAuthority`
- `WorldAuthority(core, *, runtime_snapshot=None, step_ms=60, clock_ns=time.monotonic_ns, publish_interval_ms=100, viewer_ttl_ms=2000, max_catchup_steps=8, on_step=None, on_publish=None)`
- `start() -> None`, `stop(timeout: float = 2.0) -> None`
- `enqueue_command(command: dict[str, Any]) -> int`
- `advance_once_for_test(elapsed_ms: int = 60) -> dict[str, Any]`
- `register_viewer(viewer_id: str, floor_id: str) -> None`, `touch_viewer(...)`, `unregister_viewer(viewer_id: str) -> None`
- `current_runtime() -> dict[str, Any]`, `stats() -> dict[str, Any]`

The default snapshot is `core.resolve_runtime_snapshot(None, simulation_seed=...)`. `advance_once_for_test` and the background loop consume queued commands in FIFO order, call `core.advance_runtime_snapshot(..., validate=False)` only after command normalization, replace the logical clock by exactly `step_ms`, increment `sequence`, and invoke `on_step` outside the mutation lock. `on_publish` is invoked only when a live viewer is active or a request force-materializes a state; it is never called for a zero-subscriber tick. A command/reducer exception retains the last published version, records `authority_errors`, marks the authority degraded, and stops the loop instead of publishing a partial version.

- [ ] **Step 1: Write tests proving one authority tick is independent of viewers**

```python
def test_authority_advances_once_with_zero_or_many_viewers(core):
    from RUNTIME.world_authority import WorldAuthority

    authority = WorldAuthority(core, runtime_snapshot=core.resolve_runtime_snapshot(None))
    authority.register_viewer("one", "floor02")
    authority.register_viewer("two", "floor02")
    first = authority.stats()["sequence"]
    authority.advance_once_for_test()
    assert authority.stats()["sequence"] == first + 1
    assert authority.stats()["clock_ms"] == 60
```

- [ ] **Step 2: Run the focused authority test and verify the missing-class failure**

Run: `python -m pytest TESTS/test_world_authority.py::test_authority_advances_once_with_zero_or_many_viewers -q`

Expected: FAIL because `RUNTIME.world_authority` does not yet define `WorldAuthority`.

- [ ] **Step 3: Implement command normalization, sequence/clock ownership, viewer TTL, and deterministic `advance_once_for_test`**

Reject booleans/non-integer elapsed values, require a non-empty command `type`, copy only the command envelope at enqueue time, and make `current_runtime()` return a defensive copy because it is an inspection API rather than the hot path.

- [ ] **Step 4: Implement the fixed-clock thread and lifecycle tests**

Use an accumulator over `time.monotonic_ns()` and `threading.Event.wait()`; process at most `max_catchup_steps` slices per wake, record remaining backlog, and make `stop()` idempotent. Test `start()`/`stop()`, no-viewer progression, FIFO commands, viewer expiry after `viewer_ttl_ms`, and reducer failure leaving the last published sequence unchanged.

- [ ] **Step 5: Run authority tests, then the full regression suite and commit**

Run: `python -m pytest TESTS/test_world_authority.py -q` and `python -m pytest -q`

Expected: both commands PASS; the full suite retains the current baseline behavior. Commit: `git add RUNTIME/world_authority.py TESTS/test_world_authority.py && git commit -m "feat: add host-owned world authority"`.

### Task 3: Add state publication and live HTTP endpoints without breaking review mode

**Files:**
- Modify: `TOOLS/runtime_review_server.py`
- Modify: `RUNTIME/world_authority.py`
- Modify: `TESTS/test_runtime_review_server.py`
- Create: `TESTS/test_runtime_live_http.py`

**Interfaces:**
- `PresentationPublisher(core, *, floor_ids: tuple[str, ...], publish_interval_ms: int = 100, max_history: int = 256)` in `RUNTIME/runtime_state_protocol.py`
- `PresentationPublisher.publish(runtime_snapshot, *, sequence, clock_ms, events) -> None`
- `PresentationPublisher.response(floor_id: str, since: int | None) -> dict[str, Any]`
- `WorldAuthority` accepts an optional publisher and publishes only when at least one viewer is active or a state request forces a materialization.

`main()` creates one publisher and one `WorldAuthority` from `STATE.core`, starts them before `serve_forever()`, and stops the authority before `server_close()`. Existing `ReviewState`, `/api/tick`, demos, save/load, and raster tests remain synchronous compatibility behavior. New paths are `/api/live/subscribe`, `/api/live/state`, `/api/live/command`, and `/api/live/health`; they parse query strings with `urllib.parse`, require a viewer id, touch a 2-second lease, and never call `STATE.tick`.

- [ ] **Step 1: Write HTTP contract tests for full, delta, unchanged, and command responses**

Use an in-process `ThreadingHTTPServer` bound to port `0` with a test-only authority/publisher, issue requests using `http.client.HTTPConnection`, and assert:

```python
def test_live_state_does_not_advance_on_read(live_server):
    before = live_server.authority.stats()["sequence"]
    response = live_server.get("/api/live/state?floor_id=floor02&viewer_id=test&since=0")
    assert response.status == 200
    assert response.json["sequence"] == before
    assert live_server.authority.stats()["sequence"] == before
```

- [ ] **Step 2: Run the new HTTP tests and verify endpoint-not-found failures**

Run: `python -m pytest TESTS/test_runtime_live_http.py -q`

Expected: FAIL because the live routes and publisher integration do not exist.

- [ ] **Step 3: Implement `PresentationPublisher` and wire authority publication**

Resolve presentations only for floors with active viewers, project them to the compact schema, retain a bounded history, and expose a force-materialize path for the first request after a no-subscriber interval. Keep full runtime JSON and review telemetry off the lean response.

- [ ] **Step 4: Add live routes and lifecycle wiring**

Return `400` for missing/invalid viewer or floor ids, `404` for an unknown live route, and `503` when the authority is degraded. `/api/live/command` enqueues a validated command and returns `{accepted: true, command_id, sequence}` without advancing simulation.

- [ ] **Step 5: Run live HTTP, server, and full regression tests; commit the compatibility seam**

Run: `python -m pytest TESTS/test_runtime_live_http.py TESTS/test_runtime_review_server.py TESTS/test_runtime_review_web.py -q` and then `python -m pytest -q`.

Expected: new live tests PASS and existing review behavior remains green. Commit: `git add RUNTIME/runtime_state_protocol.py RUNTIME/world_authority.py TOOLS/runtime_review_server.py TESTS/test_runtime_live_http.py TESTS/test_runtime_review_server.py && git commit -m "feat: expose authoritative live state endpoints"`.

### Task 4: Make the raster fallback cheap and cacheable

**Files:**
- Modify: `TOOLS/runtime_review_server.py`
- Modify: `RUNTIME/runtime_presentation_renderer.py`
- Modify: `TESTS/test_runtime_review_server.py`
- Create: `TESTS/test_runtime_raster_cache.py`

**Interfaces:**
- `RasterFrameCache(max_entries: int = 64)` with `get(floor_id, visual_hash)`, `put(floor_id, visual_hash, encoded_bytes)`, and `stats()`.
- `_encode_image(image: Image.Image, *, compact: bool) -> tuple[str, bytes]` in the review server.
- `_send(...)` negotiates gzip for JSON and sets `Content-Encoding`/`Vary` only when compression is used.

Derive `visual_hash` from the canonical compact presentation state before encoding. Keep `image_data_url` in legacy `/api/tick` responses for compatibility, but use content-hash `/api/frame/<hash>.webp` for the lean path. Split renderer caches so static floor/workstation layers are not invalidated by an unrelated animation frame; preserve the existing walking-depth and foreground semantics.

- [ ] **Step 1: Write a failing cache test that counts image encodes**

```python
def test_identical_visual_hash_reuses_encoded_webp(monkeypatch):
    from TOOLS.runtime_review_server import RasterFrameCache

    cache = RasterFrameCache()
    cache.put("floor02", "same", b"webp")
    assert cache.get("floor02", "same") == b"webp"
    assert cache.get("floor02", "changed") is None
```

- [ ] **Step 2: Run the focused cache test and verify the missing-class failure**

Run: `python -m pytest TESTS/test_runtime_raster_cache.py::test_identical_visual_hash_reuses_encoded_webp -q`

Expected: FAIL because `RasterFrameCache` does not yet exist.

- [ ] **Step 3: Implement bounded image caching and response compression**

Use an insertion-ordered bounded dictionary, return immutable `bytes`, and keep encode work outside the authority lock. Compress only JSON when the request advertises `gzip`; never gzip already encoded image bytes.

- [ ] **Step 4: Add unchanged-frame, cache-eviction, frame-endpoint, and legacy-payload tests**

Monkeypatch the encoder to count calls; assert two identical frames perform one encode, a third distinct hash is retrievable, an evicted frame re-encodes, `/api/frame/<hash>.webp` returns immutable cache headers, and `/api/tick` still contains the legacy data URL.

- [ ] **Step 5: Run raster/server regression and commit**

Run: `python -m pytest TESTS/test_runtime_raster_cache.py TESTS/test_runtime_review_server.py TESTS/test_runtime_review_web.py -q`.

Expected: PASS with no changes to current decode-before-swap behavior. Commit: `git add TOOLS/runtime_review_server.py RUNTIME/runtime_presentation_renderer.py TESTS/test_runtime_raster_cache.py TESTS/test_runtime_review_server.py && git commit -m "perf: cache raster frames and compress live JSON"`.

### Task 5: Publish static layers and browser asset metadata

**Files:**
- Create: `RUNTIME/runtime_static_layers.py`
- Create: `TESTS/test_runtime_static_layers.py`
- Modify: `TOOLS/runtime_review_server.py`

**Interfaces:**
- `class RuntimeStaticLayerStore`
- `RuntimeStaticLayerStore(core, *, max_floors: int = 25)`
- `manifest(floor_id: str) -> dict[str, Any]`
- `layer_bytes(floor_id: str, layer: str) -> bytes`

Generate immutable per-floor background and foreground layers from existing `FloorRenderer`, WorkSeat placement resolution, and walking-depth metadata. The manifest includes the 600x600 canvas size, layer URLs/content hashes, character frame URLs/coordinates, effect/HumanBall frame metadata, bubble presets, and the depth/occlusion contract. Do not invent or edit assets. Generate lazily and cache in memory; `/api/assets/manifest` and `/api/assets/<floor>/<layer>` serve the result.

- [ ] **Step 1: Write failing tests for deterministic layers and immutable hashes**

```python
def test_static_layer_manifest_is_deterministic(core):
    from RUNTIME.runtime_static_layers import RuntimeStaticLayerStore

    store = RuntimeStaticLayerStore(core)
    first = store.manifest("floor02")
    second = store.manifest("floor02")
    assert first == second
    assert first["canvas"] == {"width": 600, "height": 600}
    assert {layer["name"] for layer in first["layers"]} == {"background", "foreground"}
```

- [ ] **Step 2: Run the focused test and verify the missing-store failure**

Run: `python -m pytest TESTS/test_runtime_static_layers.py::test_static_layer_manifest_is_deterministic -q`

Expected: FAIL because `RuntimeStaticLayerStore` does not yet exist.

- [ ] **Step 3: Implement lazy static-layer generation using existing render/compositing helpers**

Use `FloorRenderer.render()` for the base, preserve WorkSeat static/foreground ordering, encode deterministic WebP/PNG bytes once, and compute hashes from canonical pixels. Store only generated bytes and metadata; never modify `WORLD/ASSETS`.

- [ ] **Step 4: Add server routes and layer cache-hit tests**

Assert two manifest requests do not rerender the floor, unknown layers return `400`, and layer responses include immutable cache headers and the manifest hash.

- [ ] **Step 5: Run static-layer and affected world/render tests; commit**

Run: `python -m pytest TESTS/test_runtime_static_layers.py TESTS/test_runtime_presentation_renderer.py TESTS/test_work_seat_floor_integration.py -q`.

Expected: PASS with pixel-identical existing renderer output. Commit: `git add RUNTIME/runtime_static_layers.py TESTS/test_runtime_static_layers.py TOOLS/runtime_review_server.py && git commit -m "feat: serve cached runtime static layers"`.

### Task 6: Add the Canvas 2D client with interpolation and raster fallback

**Files:**
- Create: `WEB/runtime_client.js`
- Create: `WEB/runtime_canvas_renderer.js`
- Modify: `WEB/runtime_review.html`
- Modify: `TESTS/test_runtime_review_web.py`
- Create: `TESTS/test_runtime_canvas_client.py`

**Interfaces:**
- `class LiveRuntimeClient` with `start()`, `stop()`, `setFloor(floorId)`, `sendCommand(command)`, and `pollOnce()`.
- `class CanvasRuntimeRenderer` with `setManifest(manifest)`, `applyState(state)`, `render(nowMs)`, and `dispose()`.
- Client options: `{apiRoot, floorId, viewerId, pollIntervalMs: 100, interpolationDelayMs: 100}`.

The client creates a stable random viewer id, polls `/api/live/state` at 10Hz, requests a full snapshot on a sequence gap, and backs off on errors without changing the host clock. The renderer preloads immutable layer/sprite URLs, caches decoded images and dialogue bubbles, sorts actors by published depth, draws the full 600x600 canvas every `requestAnimationFrame`, and interpolates only between authoritative samples. DOM telemetry updates at most every 250ms. The existing `<img>` double-buffer and `target.decode()` path remains intact behind `presentation_mode=raster`.

- [ ] **Step 1: Write failing JavaScript contract tests**

Use the repository's existing text-based web test style plus a small Node-free fake-fetch harness embedded in `TESTS/test_runtime_canvas_client.py` to assert:

```python
def test_canvas_client_does_not_post_tick_or_advance_on_poll():
    html = (ROOT / "WEB" / "runtime_review.html").read_text(encoding="utf-8")
    client = (ROOT / "WEB" / "runtime_client.js").read_text(encoding="utf-8")
    assert "/api/live/state" in client
    assert "/api/tick" not in client
    assert "requestAnimationFrame" in (ROOT / "WEB" / "runtime_canvas_renderer.js").read_text(encoding="utf-8")
    assert "target.decode" in html
```

- [ ] **Step 2: Run the focused web tests and verify the missing-script failure**

Run: `python -m pytest TESTS/test_runtime_canvas_client.py TESTS/test_runtime_review_web.py -q`

Expected: FAIL because the new client/renderer files and state-mode hooks do not yet exist.

- [ ] **Step 3: Implement `LiveRuntimeClient` polling, full/delta reconciliation, reconnect backoff, and command submission**

Keep one poll in flight, schedule the next poll with `setTimeout` rather than tying network cadence to animation frames, and retain the last valid state on errors. A sequence mismatch requests `since` omission for a full snapshot.

- [ ] **Step 4: Implement `CanvasRuntimeRenderer` static-layer preload, sprite/bubble caches, depth sorting, and 100ms interpolation**

Use a complete-canvas redraw, not dirty rectangles. Clamp interpolation to the two buffered samples; after the buffer is exhausted, hold the last state and expose a stale flag.

- [ ] **Step 5: Add the feature switch and preserve all existing review controls**

Add a `presentation_mode` selector/default, a `<canvas id="sceneCanvas">`, and route live state-mode controls through `sendCommand`. Keep manual tick/demo/save/load controls on raster mode until their live command equivalents are covered by server tests.

- [ ] **Step 6: Run web tests and local browser smoke; commit**

Run: `python -m pytest TESTS/test_runtime_canvas_client.py TESTS/test_runtime_review_web.py -q`, then open `http://127.0.0.1:8765/` with `presentation_mode=state` and verify floor02 spawn, walking, work/PC/VFX, Talk, Critical/Home, pause/resume, stale/reconnect, and raster rollback. Commit: `git add WEB/runtime_client.js WEB/runtime_canvas_renderer.js WEB/runtime_review.html TESTS/test_runtime_review_web.py TESTS/test_runtime_canvas_client.py && git commit -m "feat: render authoritative state with Canvas"`.

### Task 7: Add atomic checkpoint storage and restart behavior

**Files:**
- Create: `RUNTIME/world_store.py`
- Create: `TESTS/test_world_store.py`
- Modify: `RUNTIME/world_authority.py`
- Modify: `TOOLS/runtime_review_server.py`

**Interfaces:**
- `class WorldStoreError(ValueError)`
- `WorldStore(core, path: str | Path)`
- `save(snapshot: dict[str, Any], *, sequence: int, clock_ms: int, simulation_seed: str, dialogue_locale: str, dialogue_seed: str | int, event_cursor: int) -> Path`
- `load() -> dict[str, Any] | None`

Checkpoint schema is `gds.runtime_checkpoint.v1` and wraps the validated runtime snapshot plus sequence/clock/seed/dialogue/event metadata. Use `RuntimePersistence.snapshot_to_json` for canonical validation, write a sibling temporary file, flush it, and `os.replace` it atomically. Ignore incomplete temporary files and raise `WorldStoreError` for malformed committed checkpoints.

- [ ] **Step 1: Write failing save/load and corruption tests**

```python
def test_world_store_round_trips_snapshot_and_metadata(core, tmp_path):
    from RUNTIME.world_store import WorldStore

    store = WorldStore(core, tmp_path / "runtime.checkpoint.json")
    snapshot = core.resolve_runtime_snapshot("floor02")
    store.save(snapshot, sequence=9, clock_ms=540, simulation_seed="seed", dialogue_locale="en", dialogue_seed="0", event_cursor=12)
    loaded = store.load()
    assert loaded["sequence"] == 9
    assert loaded["runtime_snapshot"] == snapshot
```

- [ ] **Step 2: Run the focused tests and verify the missing-store failure**

Run: `python -m pytest TESTS/test_world_store.py -q`

Expected: FAIL because `RUNTIME.world_store` does not yet define `WorldStore`.

- [ ] **Step 3: Implement canonical checkpoint envelope and atomic replace**

Create the parent directory, write UTF-8 JSON with a newline to a same-directory temporary path, flush/close it, replace the destination, and remove only the exact temporary path on failure.

- [ ] **Step 4: Wire periodic checkpoint and startup load into the authority lifecycle**

Checkpoint on the configured interval (target 1–5 seconds) without holding the simulation lock during disk I/O. On startup load the newest valid checkpoint; if absent, resolve a fresh all-floor snapshot. Resume from the saved logical clock and expose `checkpoint_age_ms` in `stats()`.

- [ ] **Step 5: Run persistence, authority, server, and full regression tests; commit**

Run: `python -m pytest TESTS/test_world_store.py TESTS/test_world_authority.py TESTS/test_runtime_live_http.py -q` and `python -m pytest -q`.

Expected: PASS, including corrupt checkpoint recovery and clean shutdown checkpoint flush. Commit: `git add RUNTIME/world_store.py RUNTIME/world_authority.py TOOLS/runtime_review_server.py TESTS/test_world_store.py && git commit -m "feat: checkpoint authoritative runtime state"`.

### Task 8: Performance gates, scenario parity, and rollout switch

**Files:**
- Create: `TOOLS/benchmark_runtime_host.py`
- Create: `TESTS/test_runtime_host_performance.py`
- Modify: `TOOLS/runtime_review_server.py`
- Modify: `HANDOFF.md`

**Interfaces:**
- Benchmark command: `python TOOLS/benchmark_runtime_host.py --floor floor02 --ticks 120 --mode raster|state`
- Report fields: `simulation_ms`, `presentation_ms`, `render_ms`, `encode_ms`, `json_bytes`, `gzip_bytes`, `sequence_backlog`, `subscriber_count`, `frames_per_second`, and `authority_errors`.

The benchmark runs quiet seated, walking, dialogue, effects, zero-subscriber, and five-viewer cases. It records p50/p95/p99 rather than asserting a single noisy wall-clock number in unit tests. The rollout keeps `presentation_mode=raster` as default until floor02 screenshot comparison is accepted, then expands one floor at a time.

- [ ] **Step 1: Write failing structural performance tests**

```python
def test_zero_subscribers_never_publish_or_encode_images(core):
    from RUNTIME.world_authority import WorldAuthority

    calls = []
    authority = WorldAuthority(
        core,
        runtime_snapshot=core.resolve_runtime_snapshot(None),
        on_publish=lambda _tick: calls.append(True),
    )
    authority.advance_once_for_test()
    assert calls == []
```

Also assert that two registered viewers produce one authority sequence increment per test step, that a state delta is smaller than its full state for a normal frame, and that the benchmark report contains every required field.

- [ ] **Step 2: Run focused performance tests and verify missing instrumentation failures**

Run: `python -m pytest TESTS/test_runtime_host_performance.py -q`

Expected: FAIL until the authority/publisher/benchmark metrics are wired.

- [ ] **Step 3: Add boundary timing and benchmark report generation**

Use `time.perf_counter()` around simulation, presentation, raster, encode, and serialization boundaries; use gzip byte counts without changing production payload semantics. Keep benchmark output outside `LOCAL_REVIEW` and release packages.

- [ ] **Step 4: Run the full validation matrix and compare against the approved targets**

Run `python -m pytest -q`, the existing Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family, and conversation audits, then run the benchmark command for each scenario. Confirm: no encode with zero viewers, unchanged visual hash performs no encode, normal authority p95 is below 30ms with no sustained backlog, per-floor full state is near/below 20KB raw, delta is near/below 2KB raw, and browser Canvas view is at least 55 FPS on the reference host.

- [ ] **Step 5: Perform author browser acceptance and update handoff**

Inspect spawn → walk → work/PC/VFX → Talk → return → Critical/Home → re-entry in state mode and raster rollback. Record exact commands/results, acceptance-pending versus approved status, and the next task in `HANDOFF.md`; do not close Phase 8E or create a release archive without explicit author acceptance.

- [ ] **Step 6: Commit the benchmark and rollout documentation**

Run `git diff --check`, review the complete diff, then commit: `git add TOOLS/benchmark_runtime_host.py TESTS/test_runtime_host_performance.py TOOLS/runtime_review_server.py HANDOFF.md && git commit -m "test: gate host-first realtime rollout"`.

## Plan self-review checklist

- Every spec section maps to at least one task: authority (Task 2), state/delta protocol (Tasks 1 and 3), raster fallback/cache (Task 4), static layers (Task 5), Canvas/interpolation (Task 6), persistence/recovery (Task 7), error/lifecycle handling (Task 2/3/7), metrics/acceptance (Task 8).
- No task changes gameplay rules or static assets; all visual changes have raster fallback and screenshot gates.
- All new public interfaces are named with concrete parameters and return values; sequence-gap and stale-client behavior is explicit.
- The plan intentionally uses HTTP polling first and leaves transport replacement independent of authority/renderer.
- No release promotion, Cloudflare work, or unlimited long-gap replay is included.
