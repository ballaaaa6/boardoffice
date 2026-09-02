# Lean Component Renderer Implementation Plan

> **Required sub-skill:** Use `superpowers:executing-plans` to implement this plan task-by-task with verification checkpoints.

## Goal

Create a `floor02` prototype that keeps `CentralGameCore`, navigation, WorkSeat, speech, stamina, replay and local raster review behavior unchanged, while adding a renderer-neutral JSON state path and a browser Canvas renderer. The lean path must advance the same simulation but must not call Pillow, materialize full-frame images, or send `image_data_url`. The existing raster path remains the compatibility fallback and visual reference.

Success means:

- local `python -m pytest -q` remains green;
- the lean server path produces deterministic `gds.runtime_render_state.v1` JSON with no image/base64 field;
- a canvas review page shows the same static floor, character frames, work-seat effects, walking depth, and dialogue overlays from small cached components;
- raster review still behaves as before when explicitly selected or when the browser has no canvas prototype mode;
- the lean payload is materially smaller and the measured hot path contains no full-frame Pillow encode;
- canonical world/character assets, starting-point files and reference hashes are unchanged.

## Architecture

The simulation remains authoritative in Python. Only presentation is split:

```text
CentralGameCore
  -> resolve_runtime_presentation()          existing behavior resolver
  -> RuntimeRenderStateProjector              metadata-only, no image calls
  -> gds.runtime_render_state.v1 JSON        small network state
       -> RuntimeCanvasRenderer               browser component compositor
            static cached floor + dynamic canvas layers
            RAF interpolation, lazy sprite cache, occluder masks

CentralGameCore
  -> RuntimePresentationRenderer              existing Pillow path
  -> raster image_data_url                    compatibility fallback
```

The projector consumes the already resolved actor presentation rather than recreating gameplay rules in JavaScript. It sends frame IDs, source rectangle references, layer IDs, positions, timing, dialogue data and the authoritative list of occluders in front of each walking actor. The browser only performs visual composition and interpolation.

The first prototype is single-user and HTTP polling based. It uses the existing `/api/state` and `/api/tick` endpoints with an explicit `renderer=canvas` request mode. A later Cloudflare slice can move the same state contract behind a Worker/Durable Object without moving gameplay or Pillow into the Worker.

## Tech Stack

- Python 3.10+ type-annotated runtime modules.
- Existing `CentralGameCore`, `CharacterSystem`, `LayoutCore`, `WorkSeatCore` and `WalkingDepthCore` metadata contracts.
- `dataclasses`/plain dictionaries and `json` for the protocol; no new runtime dependency.
- Browser ES modules, HTML Canvas 2D, `requestAnimationFrame`, `Image.decode()` and `OffscreenCanvas` where available.
- Pillow only for the existing raster renderer and build-time static/mask asset generation, never in the lean request path.
- `pytest` for protocol, no-Pillow, determinism, server and web contract tests.

## Spec

### Protocol

The lean payload has this shape:

```python
{
    "schema": "gds.runtime_render_state.v1",
    "version": "1.0.0",
    "floor_id": "floor02",
    "sequence": 12,
    "clock_ms": 720,
    "full": True,
    "manifest_revision": "<sha256>",
    "static_scene_id": "floor02",
    "actors": [
        {
            "employee_id": "...",
            "visible": True,
            "render_owner": "stationary|walking_depth",
            "character_id": "...",
            "action": "work|move|emotion|...",
            "resolved_action": "...",
            "subaction": "...",
            "resolved_subaction": "...",
            "direction": "NE|NW|SE|SW|...",
            "resolved_direction": "...",
            "frame_index": 0,
            "character_frame_count": 4,
            "animation_clock_ms": 0,
            "ground_xy": [100.0, 220.0],
            "anchor_xy": [16, 31],
            "workstation_id": "...",
            "occluder_placement_ids": [],
            "channels": {
                "pc": {"asset_id": "...", "frame_index": 0},
                "effect": {"asset_id": "...", "frame_index": 0},
                "humanball": {"asset_id": "...", "frame_index": 0}
            },
            "dialogue": {"visible": False, "text": "", "bubble_id": None}
        }
    ],
    "paint_order": {"actors": ["..."], "dialogue": ["..."]},
    "events": []
}
```

`RuntimeRenderStateProjector.project()` must accept a runtime snapshot and the presentation result's `at_ms`, preserve stable employee ordering, include only JSON-safe scalar/list/dict data, and reject a missing/invalid floor ID or negative sequence. It must never include `image`, `image_data_url`, a complete runtime snapshot, or replay state.

### Rendering modes

`RuntimePresentationLoop` gains `render_mode: Literal["raster", "headless"] = "raster"`. Raster is the default and keeps current tests and callers compatible. Headless calls `CentralGameCore.resolve_runtime_presentation()` and returns the same presentation plus `image: None`; it does not instantiate or call full-frame rendering during `_frame`.

`ReviewState` owns a headless loop for the live server. `frame_payload(renderer="canvas")` returns the projected state and no image field. `frame_payload(renderer="raster")` materializes a raster image only for that explicit request. Save/load/replay and existing demo endpoints keep their complete-state semantics and use raster-compatible behavior unless the request explicitly asks for the canvas mode.

### Static manifest and component assets

`TOOLS/build_runtime_render_manifest.py` generates derived files for `floor02`:

- `WEB/runtime_render_manifest.json`;
- `WEB/runtime_assets/floor02.static.png`, containing the base floor plus authored static placements while omitting the dynamic PC layer;
- `WEB/runtime_assets/occluders/<placement_id>.png`, cleaned masks matching `WalkingDepthCore`'s shadow-removal rule;
- per-asset URLs and dimensions for world sprites, character body/face sheets, frame rules, PC frames, effects and HumanBall frames.

The builder is deterministic: source registry bytes, floor/layout IDs and the builder schema form the manifest revision; sorted IDs and stable JSON separators are required. The generated outputs are derived/rebuildable and are not canonical gameplay data.

### Browser renderer

`RuntimeCanvasRenderer` must expose these concrete methods:

```javascript
export class RuntimeCanvasRenderer {
  constructor({canvas, manifestUrl, imageFactory = () => new Image()}) {}
  async loadManifest() {}
  setState(state) {}
  render(nowMs = performance.now()) {}
  destroy() {}
}
```

It keeps a cached static canvas, disables smoothing, draws dynamic components on each RAF, interpolates only between the last two server states, and snaps only on a sequence gap or a new floor. It resolves body/face frame rectangles from the manifest, draws PC/effect/HumanBall components using the state frame indices, applies only the server-provided occluder masks to walking actors, and paints dialogue last. Image loading is lazy and deduplicated by URL. The 2D canvas remains the only frame surface; no base64 image is created by the browser client.

`RuntimeRenderClient` polls at 100ms by default, calls `setState()` when a response arrives, and lets RAF continue at display refresh rate. It exposes `start()`, `stop()` and `tickOnce()` so the existing controls can reuse the same reset/demo/save/load/replay API actions.

## Global Constraints

- Do not edit `00_STARTING_POINT/` or replace canonical static world/character assets.
- Do not alter gameplay decisions or existing runtime snapshot fields unless a metadata-only frame-count fix is required to avoid an accidental Pillow render.
- Do not duplicate navigation, speech, stamina, WorkSeat ownership or depth policy in JavaScript.
- Do not make the live lean path call `CharacterSystem.render`, `WorkSeatCore.render_floor_with_work*`, Pillow image masking, or full-frame base64 encoding.
- Keep raster as the default compatibility path until the canvas prototype passes parity checks.
- Use `apply_patch` for text/code edits. Generated PNG/JSON files must come from the deterministic builder, not hand-edited binary output.
- Use explicit test commands; never infer success from a generated manifest alone.
- Before completion run `python -m pytest -q`, the required navigation/world/WorkSeat/Phase 6/Central/F2/gameplay-metadata audits, `git diff --check`, manifest determinism, server smoke and the renderer benchmark.
- Update `/HANDOFF.md` and `/ROADMAP.md` only with the current branch's actual status; keep acceptance-pending distinct from author-approved.

## File map

| File | Responsibility |
| --- | --- |
| `RUNTIME/runtime_render_state.py` | Metadata-only projector and protocol validation. |
| `RUNTIME/runtime_presentation_renderer.py` | Preserve raster renderer and add headless loop mode. |
| `RUNTIME/central_core.py` | Make frame-count resolution metadata-only. |
| `TOOLS/runtime_review_server.py` | Select canvas JSON vs explicit raster response. |
| `TOOLS/build_runtime_render_manifest.py` | Build deterministic browser manifest/static/mask assets. |
| `WEB/runtime_render_manifest.json` | Generated floor02 component manifest. |
| `WEB/runtime_assets/` | Generated derived static and mask/component assets. |
| `WEB/runtime_canvas_renderer.js` | Canvas component compositor and interpolation. |
| `WEB/runtime_render_client.js` | Polling/RAF bridge for the review page. |
| `WEB/runtime_review.html` | Canvas mode toggle and compatibility UI integration. |
| `TESTS/test_runtime_render_state.py` | Projector, no-image and deterministic protocol tests. |
| `TESTS/test_runtime_review_server.py` | Canvas/raster payload and API mode tests. |
| `TESTS/test_runtime_render_manifest.py` | Deterministic manifest and asset reference tests. |
| `TESTS/test_runtime_review_web.py` | Static browser contract checks. |
| `TOOLS/benchmark_runtime_renderers.py` | Compare headless/raster CPU, payload and memory indicators. |

## Implementation tasks

### Task 1 — Add metadata-only runtime state and headless loop

- [x] Add `RUNTIME/runtime_render_state.py` with `RuntimeRenderStateProjector.project()` and helpers that copy only the approved actor fields, channels, dialogue, paint order, event summaries and server metadata.
- [x] Include `occluder_placement_ids` by calling existing `WalkingDepthCore.occluders_in_front()` with the resolved walking actor ground point. Do not load visual images in this calculation.
- [x] Change `CentralGameCore._runtime_frame_count()` to call `self.characters.resolve_frame_ids(...)` and count IDs. The method must not call `self.characters.render(...)`.
- [x] Add `render_mode` to `RuntimePresentationLoop`; keep the constructor default as `"raster"`, preserve transactional failure behavior, and return `image is None` in headless mode.
- [x] Export the projector from `RUNTIME/__init__.py` if the package currently exports runtime presentation symbols.

Write tests before implementation. The focused tests must include:

```python
def test_projector_does_not_materialize_character_or_floor_images(monkeypatch):
    core = CentralGameCore(ROOT)
    runtime = quiet_runtime(core, "floor02")
    monkeypatch.setattr(core.characters, "render", lambda *a, **k: (_ for _ in ()).throw(AssertionError("image")))
    state = RuntimeRenderStateProjector(core).project(runtime, floor_id="floor02")
    assert state["schema"] == "gds.runtime_render_state.v1"
    assert "image_data_url" not in state
    assert all("runtime_snapshot" not in actor for actor in state["actors"])

def test_headless_loop_advances_same_snapshot_without_image():
    loop = RuntimePresentationLoop(core, runtime_snapshot=runtime, floor_id="floor02", render_mode="headless")
    assert loop.render_current()["image"] is None
    frame = loop.tick(60)
    assert frame["image"] is None
    assert frame["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 60
```

Run `python -m pytest -q TESTS/test_runtime_render_state.py TESTS/test_runtime_presentation_renderer.py`; then run the full suite. Commit as `feat: add metadata-only runtime render state`.

### Task 2 — Add canvas/raster server selection

- [x] Import the projector in `TOOLS/runtime_review_server.py` and create one projector per `ReviewState`.
- [x] Add `renderer: Literal["raster", "canvas"] = "raster"` to `frame_payload`, `current` and `tick`. Validate unknown values with `ValueError`.
- [x] For canvas payloads, project the runtime/presentation state, return `renderer`, `render_state`, actor cards/events/telemetry needed by the existing side panel, and set `metrics.encode_ms` to `0.0`; do not access `frame["image"]`.
- [x] For raster payloads, preserve the current `image_data_url` and complete-state behavior.
- [x] Parse `renderer` from query strings and POST bodies for `/api/state`, `/api/tick`, `/api/reset`, `/api/live-start` and demo endpoints. Preserve current defaults.
- [x] Add focused tests that monkeypatch the raster encoder/renderer to raise and prove a canvas request still succeeds; assert raster still returns a data URL.

Run server unit tests and a direct handler/API smoke with `renderer=canvas`. Commit as `feat: expose lean render state from review host`.

### Task 3 — Build the deterministic floor02 manifest

- [x] Implement the builder using existing `LayoutCore`/world registries and the current walking-depth metadata. Reuse authored slot/layer/transform data and reject duplicate IDs or unresolved asset/frame references.
- [x] Compose the static PNG at build time from the base floor variant and all non-PC static placements. Keep PC, character, effects, HumanBall and dialogue out of this image.
- [x] Generate cleaned occluder masks with the same alpha/shadow policy used by the existing walking-depth renderer and record dimensions/checksums.
- [x] Emit character body/face source sheets plus frame crop rules, action sequences, PC/effect/HumanBall frame URLs and workstation metadata. URLs must be relative to `WEB/` and every generated file must exist.
- [x] Make the manifest revision depend on canonical source bytes and builder schema, with sorted keys and stable serialization.
- [x] Add tests for determinism, 600x600 floor canvas, all referenced files, no duplicate IDs, and no changes to canonical source hashes.

Run `python TOOLS/build_runtime_render_manifest.py --floor-id floor02`, the manifest tests and the existing raster QA. Commit generated manifest/assets with `feat: build floor02 component render manifest`.

### Task 4 — Implement the browser Canvas component renderer

- [ ] Add `WEB/runtime_canvas_renderer.js` with the exact public methods in the spec. Draw static cache once, then dynamic layers per RAF. Set `ctx.imageSmoothingEnabled = false` for all pixel-art contexts.
- [ ] Add `WEB/runtime_render_client.js` with 100ms polling, timeout/retry, state sequencing and RAF lifecycle. Never fetch or decode from the RAF callback.
- [ ] Draw character body/face crops from manifest frame rules, workstation PC/effect/HumanBall channels, the authored occluder masks and dialogue bubbles. Keep paint order aligned with `presentation.character_order` and `bubble_order`.
- [ ] Interpolate ground coordinates between sequential states over the server interval; use current frame indices for sprite animation; snap on a sequence gap, floor change or missing previous state.
- [ ] Add a visible `Canvas`/`Raster` toggle to `WEB/runtime_review.html`. Canvas mode calls `renderer=canvas`; raster mode continues the existing double-buffered `<img>` path. Keep telemetry cards and all existing demo controls working in both modes.
- [ ] Add static web contract tests for Canvas, `requestAnimationFrame`, state polling, `renderer=canvas`, absence of a canvas-path `image_data_url` dependency and preservation of raster fallback.

Run the web contract tests, then open the explicit branch server port in a browser and inspect floor02, full system, Talk, Effects, Critical, save/load and replay in both modes. Record browser console errors and observed frame smoothness before committing as `feat: add lean canvas runtime preview`.

### Task 5 — Benchmark, parity audit and handoff

- [ ] Add `TOOLS/benchmark_runtime_renderers.py` to run equal floor02 simulation ticks through headless and raster paths, reporting p50/p95 tick time, render/encode time, payload bytes, actor count and process RSS where available.
- [ ] Verify the lean path does not import/use Pillow in request processing by instrumenting `RuntimePresentationRenderer.render_runtime_snapshot`, `_image_data_url` and the relevant WorkSeat/character render methods to raise during canvas API calls.
- [ ] Compare raster frame metadata to projected state for actor IDs, resolved action/direction/subaction, frame indices/counts, workstation channels, dialogue and paint order over a scripted spawn/work/talk/effects/critical trace.
- [ ] Run `python -m pytest -q`, all required navigation/world/WorkSeat/Phase 6/Central/F2/gameplay-metadata audits, `git diff --check`, manifest determinism and the benchmark. Inspect `git status` for generated caches/debug artifacts.
- [ ] Update `HANDOFF.md` with the actual branch commits, measured numbers, tests, current acceptance status and next CF gate. Update `ROADMAP.md` only if milestone scope or acceptance status changes.
- [ ] Use the finishing-development-branch procedure after all tests and audits are green; do not claim visual acceptance until the author reviews the browser output.

## Plan self-review

- Spec coverage: protocol, headless Python path, server selection, generated assets, Canvas renderer, fallback, benchmarks, audits and handoff are each mapped to a task.
- File coverage: every implementation and test file is listed in the file map; generated files have a deterministic builder owner.
- Type/API consistency: Python uses `RuntimeRenderStateProjector.project(runtime_snapshot, *, floor_id, sequence=0, at_ms=None, events=())`; JavaScript uses `RuntimeCanvasRenderer`/`RuntimeRenderClient` methods named in the spec; server mode uses `renderer` with `raster` default.
- Constraint scan: no task edits `00_STARTING_POINT/`, changes gameplay policy, or places Pillow/base64 in the lean request path.
- Verification coverage: every task has a focused test command and the final task repeats the full suite and required audits.
