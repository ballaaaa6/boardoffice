# Host-First Realtime Runtime Design

## Goal

Make the local Python host lightweight and keep the web view smooth without changing the game rules, authored assets, or the shared-world requirement. One host-owned simulation must continue while browsers are disconnected; every browser must read the same authoritative clock and state. The first deployment target is the existing host process, not Cloudflare or another edge platform.

## Approved scope

- Keep the existing `CentralGameCore` simulation and `gds.runtime_presentation_snapshot.v1` seam as the source of truth.
- Move simulation time out of browser requests into one host-owned `WorldAuthority`.
- Send compact render state at a low network rate and render lightweight frames in the browser with Canvas 2D.
- Keep the current Pillow/raster path as a compatibility fallback until visual parity is accepted floor by floor.
- Continue the simulation with no subscribers, but skip presentation rendering, image encoding, and network serialization when no subscriber needs them.
- Persist checkpoints so a host restart can resume from a known state without requiring an unbounded replay.

## Out of scope

- Cloudflare deployment, Workers, Durable Objects, or WebSocket transport in the first host release.
- WebRTC, video streaming, WebGL, or a new game engine.
- Changes to character artwork, floor geometry, navigation, WorkSeat policy, dialogue policy, stamina rules, or authored asset hashes.
- Unlimited catch-up after a host has been stopped for a long time. Long-gap recovery is a separate design problem.

## Why the current path is expensive

The current review loop lets a browser call `/api/tick`; the handler advances the shared snapshot, renders a 600x600 Pillow image, encodes a new WebP, converts it to a Base64 data URL, serializes JSON, and waits for the browser to decode before displaying it. On warmed floor02 measurements, advance plus render took about 4–7ms, WebP encoding about 8–10ms, and the compact response was about 136KB JSON with a 122KB image data URL. The full presentation snapshot was about 11.4KB raw/1.2KB gzip and a typical recursive delta about 0.5KB raw/0.26KB gzip.

This is also a correctness problem: every browser request advances the world. Multiple viewers multiply work and can change the simulation rate; no browser means no tick at all. The browser's one-in-flight request in `WEB/runtime_review.html` makes network round-trip and decode time visible as stalls.

## Architecture

```text
                         commands
Browser ────────────────► HTTP host
   ▲                         │
   │ compact state/delta     │ enqueue only; never advances time
   │                         ▼
   │                  WorldAuthority
   │                  ├─ fixed 60ms simulation clock
   │                  ├─ one shared all-floor snapshot
   │                  ├─ bounded delta history
   │                  └─ checkpoint writer
   │                         │
   │                         ├─ no subscribers: advance only
   │                         └─ subscribers: publish state; render on demand
   │
   └─ Canvas 2D at requestAnimationFrame (60Hz)
      static layers + cached sprites + interpolated actor state
```

The authority initially lives in the same Python process as `ThreadingHTTPServer` to avoid deployment changes. The process owns one mutable runtime snapshot. HTTP handlers read immutable/versioned published data or enqueue validated commands; they never call `advance_runtime_snapshot` directly.

## WorldAuthority contract

`WorldAuthority` owns:

- the all-floor runtime snapshot returned by `CentralGameCore.resolve_runtime_snapshot(None)`;
- a fixed simulation quantum of 60ms;
- a monotonically increasing `sequence` and logical `clock_ms`;
- a FIFO command queue for user/demo actions;
- the latest compact state per floor and a bounded history of state deltas;
- subscriber count and publication metrics;
- checkpoint scheduling and lifecycle shutdown.

The loop uses `time.monotonic_ns()` and an accumulator. Normal operation advances one 60ms slice per deadline. A short scheduling delay may process several slices in one wake; the loop records backlog and never performs presentation rendering while catching up. A host restart loads the last checkpoint and resumes from that logical clock; it does not replay an unbounded offline interval.

The authority's critical section covers only command application, simulation mutation, sequence/clock update, and publication of a new immutable state. Pillow rendering, image encoding, and JSON compression happen after the lock from a stable version. No subscriber owns a mutable reference to the authority snapshot.

## State and transport protocol

The first transport is ordinary HTTP polling so the host can use its existing standard-library server and remain easy to debug. A future transport may replace polling without changing the authority or browser renderer.

### Render state

The new protocol schema is `gds.runtime_presentation_state.v1`. A full state contains:

- `schema`, `floor_id`, `sequence`, `clock_ms`, and `full: true`;
- render-ready actor rows: employee id, visibility, world position, depth/z value, character id, action/subaction, direction, animation frame, workstation/PC frame, effect/HumanBall frame, opacity, and dialogue bubble state;
- a compact `events` array containing only events after the requested sequence;
- a `source_presentation_sequence` for parity/debugging.

Telemetry that is not needed to draw a frame (long event text, dialogue coverage, replay details, and diagnostics) is served on a slower or on-demand path so it cannot dominate the render update.

### Endpoints

- `GET /api/state?floor_id=<id>&since=<sequence>` returns a full state when `since` is absent or too old, a delta when the requested sequence is in the bounded history, and an unchanged response when no visible state changed.
- `GET /api/assets/manifest` returns immutable asset/layer metadata needed by the Canvas renderer.
- `GET /api/frame/<content-hash>.webp` serves an optional raster fallback or static layer with immutable caching headers; JSON never embeds a Base64 image in lean mode.
- `POST /api/command` validates and queues a command without advancing the clock.
- The existing `/api/tick` remains available only for review/debug compatibility and is not used by the production live client.

Responses use gzip when requested. The delta history is bounded; a client that falls behind receives a full state instead of an unbounded queue. A slow or disconnected client therefore cannot block the authority or consume unbounded host memory.

## Rendering strategy

### Host-side

The host renders no image when there are no subscribers. When a raster fallback is requested, it reuses an encoded image by content hash and encodes only when the visual hash changes. The renderer cache is split conceptually into static floor layers, workstation/static placement layers, and dynamic actor/effect/bubble content so a single animation frame cannot invalidate unrelated static work.

Static floor layers are generated once per floor from the existing assets. Where depth requires an object above a character, the floor publishes a foreground layer or an existing occlusion mask; floors that cannot yet meet parity stay on the raster fallback until their browser path is verified.

### Browser-side

The browser uses one 600x600 `CanvasRenderingContext2D` and redraws the complete canvas on `requestAnimationFrame`. Full-canvas redraw is intentional: at the current actor counts it is simpler and cheaper to reason about than dirty-rectangle bookkeeping.

- Preload static background/foreground layers and use `ImageBitmap` or equivalent decoded image caches for sprites and effect frames.
- Sort visible actors by the published depth value and draw their cached frame at the interpolated position.
- Cache dialogue bubbles by `(locale, bubble_id, text, opacity_band)` instead of rasterizing text every animation frame.
- Maintain a small interpolation buffer (target 100ms). Interpolation uses `clock_ms` and sequence timestamps from the authority; it never advances gameplay state or issues ticks.
- If a network update is late, keep the last valid frame and mark the view stale. Do not extrapolate indefinitely.
- Update diagnostic DOM cards at a lower rate and only when values change; do not rebuild all cards on every animation frame.

The existing double-buffered `<img>` renderer remains selectable with `presentation_mode=raster|state` while the Canvas path is being brought to screenshot parity.

## Persistence and recovery

`WorldStore` writes an atomic checkpoint at a fixed interval (target 1–5 seconds) containing the serialized runtime snapshot, simulation seed, dialogue shuffle-bag state, logical clock, sequence, and event cursor. The write uses a temporary file plus atomic replace, and a corrupt or incomplete temporary file is ignored.

The running authority is the continuity guarantee: if the process stays alive, the world continues with zero viewers. On restart, the host resumes from the newest valid checkpoint and reports the checkpoint age. It does not block HTTP startup on unlimited event-rich catch-up; long-gap deterministic fast-forward is intentionally excluded from this release.

## Error handling and lifecycle

- Validate command shape, employee ids, and allowed command types before enqueueing.
- If a simulation step fails, retain the last published version, record an authority error, and expose a degraded health state; do not publish a partially updated state.
- If a client requests a sequence outside the delta history, return a full snapshot.
- If the client times out, retain its last frame and retry with bounded backoff; the host continues independently.
- Shutdown sets an authority stop event, flushes one checkpoint, joins the authority thread, and only then closes the HTTP server.
- Metrics include tick duration, backlog, publication count, encode count, subscriber count, sequence age, checkpoint age, and authority errors.

## Performance targets

The first instrumentation pass establishes p50/p95/p99 baselines. The following are acceptance targets for the host-first implementation:

- A normal 60ms authority slice stays below 30ms p95 with no sustained backlog.
- With zero subscribers, image-render and image-encode counts remain zero.
- An unchanged visual hash performs zero new WebP encodes.
- A normal per-floor full state is at most about 20KB raw and a delta is at most about 2KB raw; gzip measurements are recorded separately.
- The browser maintains at least 55 rendered frames per second on the reference machine while network updates arrive at 10–20Hz.
- Five simultaneous viewers observe the same `sequence`/`clock_ms`; viewer count does not change simulation speed.
- Disconnecting for 30 seconds and reconnecting shows a clock advanced by the elapsed host time and a current full/delta state, not a replay from the disconnect point.

## Implementation phases and gates

1. **H0 instrumentation:** add host/browser timing and a reproducible benchmark matrix. Gate on a saved baseline report.
2. **H1 authority separation:** add `WorldAuthority`, command queue, sequence/clock, and background lifecycle. Gate on one-tick-per-wall-time and no-viewer continuation tests.
3. **H2 lean protocol/raster fallback:** add state/delta endpoints, gzip, content-hash image caching, static layer generation, and bounded history. Gate on payload/encode budgets and legacy raster parity.
4. **H3 Canvas client:** add asset manifest loading, Canvas renderer, interpolation, stale handling, and low-rate telemetry updates. Implement floor02 first, then expand floor by floor after screenshot comparison.
5. **H4 checkpointing:** add `WorldStore`, atomic checkpoint/load, and bounded restart behavior. Gate on save/load/replay and corrupted-checkpoint tests.
6. **H5 rollout:** run the full regression suite, runtime/web tests, performance benchmarks, browser smoke, and author visual acceptance. Keep `presentation_mode=raster` as the rollback switch until the author accepts Canvas parity.

## File responsibilities

- `RUNTIME/world_authority.py`: fixed-clock simulation owner, command queue, publication history, lifecycle.
- `RUNTIME/runtime_state_protocol.py`: full-state/delta projection, sequence cursors, compact render contract.
- `RUNTIME/world_store.py`: checkpoint serialization, atomic write, load and validation.
- `TOOLS/runtime_review_server.py`: HTTP endpoints, compatibility adapter, subscriber/request metrics; no direct client-driven ticking in live mode.
- `WEB/runtime_client.js`: polling, sequence reconciliation, reconnect/backoff and command submission.
- `WEB/runtime_canvas_renderer.js`: static layer loading, sprite/bubble caches, depth ordering, interpolation and Canvas drawing.
- `WEB/runtime_review.html`: feature switch and low-rate telemetry wiring while preserving the current review controls.
- `TESTS/test_world_authority.py`: clock ownership, multi-viewer consistency, no-subscriber continuation and lifecycle.
- `TESTS/test_runtime_state_protocol.py`: full/delta reconstruction, sequence gaps, bounded history and unchanged responses.
- `TESTS/test_world_store.py`: atomic checkpoint save/load, validation and corrupt-file recovery.
- `TESTS/test_runtime_review_web.py` plus browser smoke coverage: fallback compatibility, Canvas startup, stale/reconnect behavior and visual parity checkpoints.

## Validation and release constraints

- Run `python -m pytest -q` after every runtime change, plus the existing navigation/world/WorkSeat/Phase 6/Central/gameplay-metadata audits where affected.
- Preserve all static world/character assets and their reference hashes.
- Do not close the Phase 8E visual/gameplay acceptance gate based on automated output alone.
- Do not package a release until the author accepts the browser sequence and the release-clean audit passes.
