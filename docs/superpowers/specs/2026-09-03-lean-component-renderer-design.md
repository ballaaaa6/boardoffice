# Lean Component Renderer Design

## Goal

Make the browser runtime substantially lighter while preserving the current
gameplay rules, authored world/character assets, local computer workflow and
visual behavior. The live path must stop generating and transporting a full
600x600 raster frame on every tick. The browser should render a cached static
scene plus small dynamic components from a JSON render state.

The first implementation target is the existing local review host and
`floor02`. Cloudflare deployment is a compatibility target for the resulting
shape, not part of the first production release.

## Design status and scope

This design was approved for a branch prototype on 2026-09-03. The prototype
is intentionally separated from the existing `main` checkout in
`codex/lean-component-renderer`.

### In scope

- Keep `CentralGameCore`, actor simulation, speech scheduling, stamina,
  navigation, WorkSeat ownership and replay semantics as the behavior source
  of truth.
- Extract a renderer-neutral, metadata-only render-state boundary.
- Add a JSON-only live response with no embedded image or Base64 payload.
- Add a browser Canvas renderer for `floor02` using cached static layers and
  small sprite/component draws.
- Keep the current Pillow/raster path selectable as a rollback and visual
  comparison oracle.
- Build a manifest that maps canonical asset ids and frame metadata to browser
  source rectangles, anchors and placement/layer data.
- Verify visual parity, behavior parity, payload size, frame rate and process
  memory before considering a Cloudflare migration.

### Out of scope for the first prototype

- Changing gameplay rules, timing constants, dialogue policy, navigation,
  authored floor geometry or character artwork.
- Porting the complete Python simulation to TypeScript in the same slice.
- Running Pillow, Pyodide or the current Python resident server inside a
  Cloudflare Worker.
- WebGL, a new game engine, DOM/SVG nodes for every actor, video streaming or
  dirty-rectangle bookkeeping.
- Removing the raster fallback before author visual acceptance.
- A shared multi-viewer authority or Durable Object. That is a later choice
  after the renderer contract is proven.

## Evidence from the current implementation

The current local path is already split conceptually into simulation and
presentation, but the live HTTP path still couples them:

```text
CentralGameCore snapshot
  -> resolve_runtime_presentation()
  -> Pillow WorkSeat/world composition
  -> Pillow walking/bubble overlay
  -> WebP/PNG encode
  -> Base64 data URL in every response
  -> browser <img> swap
```

The warmed `floor02` measurements were:

| Measurement | Current result |
| --- | ---: |
| simulation-only p50 | 0.23ms |
| advance + render p50 | 12.2ms |
| WebP encode p50 | 8.76ms |
| compact response | about 140KB per tick |
| active local process working set | about 275MB |

The evidence indicates that full-frame rasterization, image encoding and
transport—not actor simulation—are the main live-path costs. The relevant
existing rules already expose the data needed by a component renderer:

- WorkSeat resolves desk, PC, chair, foreground, direction and layer data.
- Central resolves walking ground position, action, direction, frame and
  actor paint order.
- WalkingDepth resolves which world occluders are in front of an actor.
- Speech resolves bubble id, text, opacity, offset and turn order.

The new renderer must consume those decisions; it must not recreate them.

## Core architectural decision

Use a headless render-state projector between the simulation and all visual
renderers.

```text
                 gameplay commands
Browser ─────────────────────────► local host
   ▲                                  │
   │ JSON render state                ▼
   │                       CentralGameCore
   │                                  │
   │                    headless presentation projection
   │                                  │
   │                  ┌───────────────┴───────────────┐
   │                  ▼                               ▼
   │        existing raster adapter              Canvas adapter
   │        (Pillow, fallback/oracle)             (browser)
   │
   └──────────── Canvas at requestAnimationFrame (60Hz)
              static cache + dynamic components + interpolation
```

The projection owns the existing presentation decisions—speech overlay
selection, actor visibility, action normalization, frame selection metadata,
paint ordering and bubble layout inputs—but does not materialize images.
Both the old raster renderer and the new Canvas renderer consume this same
state so behavior cannot silently diverge between render backends.

The live prototype may continue using the existing `/api/tick` compatibility
endpoint to advance the local review host. It will return JSON-only state when
the Canvas mode is selected. Separating the host-owned clock and adding a
shared-world authority remains a later transport/lifecycle slice; combining it
with renderer extraction would make parity failures difficult to isolate.

## Headless render-state contract

The new contract is `gds.runtime_render_state.v1`. It is a render projection,
not a replacement for `gds.runtime_snapshot.v1` and not a second gameplay
state machine.

A full state contains:

- `schema`, `version`, `floor_id`, `sequence`, `clock_ms` and `full`;
- static scene id/version and manifest revision;
- visible actor rows with employee id, character id, render owner, action,
  subaction, direction, frame index/count, animation clock, opacity, ground
  position, anchor and workstation identity;
- optional channel rows for PC, VFX and HumanBall component ids/frame indices;
- dialogue bubble id, text, locale, offset and opacity when visible;
- published actor and bubble paint order;
- compact events needed by the review controls.

The shape is intentionally asset-reference based. A frame row identifies a
canonical character/action/frame; it does not contain the pixels for that
frame. A browser manifest resolves the reference to a source image and crop.

The first transport slice sends full JSON states at a low update rate to prove
the renderer independently. A bounded full/delta protocol can be added after
Canvas parity; its state contract must not change. If a client misses too many
updates, it requests a fresh full state rather than replaying an unbounded
history.

The lean response must not include:

- `image_data_url`;
- a Pillow `Image` object or serialized raster frame;
- the complete runtime snapshot, replay history or dialogue coverage on every
  animation update;
- implementation-specific Python objects.

Diagnostics, save/load, replay and the existing review telemetry remain on
slower or explicit endpoints so they do not dominate the render stream.

## Renderer-neutral implementation boundary

The implementation will extract the presentation-resolution logic currently
inside `CentralGameCore.resolve_runtime_presentation()` into a reusable
headless boundary, with responsibilities kept explicit:

- apply the authoritative actor and speech tracks;
- preserve the existing stationary-talk/work-loop behavior;
- normalize runtime action/direction/subaction labels;
- emit the same ground positions, WorkSeat ownership and paint order;
- resolve frame counts from registry metadata, not by calling image rendering;
- emit component keys and animation clocks for browser lookup.

The headless path must not call `CharacterSystem.render()`,
`WorkSeatCore.render_floor_with_work*()`, `WalkingDepthCore` image masking or
dialogue-bubble image composition. Those calls remain valid behind the raster
adapter only.

This is the key memory boundary: a Canvas request must not populate the
full-floor or dynamic Pillow image caches merely to calculate a frame index.
If an existing registry does not expose a required frame count or crop, the
build step adds that information to the manifest from canonical registries;
it does not render a new full-frame image at runtime.

## Browser component renderer

The browser owns a fixed-size 600x600 Canvas scene and a lightweight render
loop. Pixel-art settings use nearest-neighbor behavior (`imageSmoothingEnabled
= false`). The render loop runs independently of network responses:

1. Load the selected floor manifest and static scene resources once.
2. Keep the latest two valid render states in a small interpolation buffer.
3. At each `requestAnimationFrame`, interpolate walking positions using the
   published clocks and draw the current component frame.
4. Update network state at approximately 10–15Hz; never make a fetch per
   display frame.
5. Keep the last valid frame during a short network delay and show a stale
   indicator only after the configured timeout.

The first implementation uses a cached static layer and a dynamic layer. The
dynamic layer is redrawn every display frame, but the static floor is not
recomposed. At the current actor count this is simpler and safer than dirty
rectangles while still removing the expensive work from the host.

### Static and dynamic passes

The manifest separates authored placement data into render passes:

```text
static back scene
→ workstation desk/PC/chair components
→ seated character + PC/VFX/HumanBall components
→ walking actors sorted by published ground-y
→ foreground/occluder components
→ dialogue bubbles
```

Workstation placement ids that the current WorkSeat compositor suppresses or
derives are represented once in the manifest, so a static PC/chair is not
double-painted beneath its animated component. Walking-depth candidates carry
the same placement/layer/foreground metadata used by the current world
occlusion rules. The browser implementation must match the current
`occluders_in_front()` decision for `floor02`; it must not approximate
occlusion by simply sorting actors.

### Character and effect components

The asset manifest maps a canonical render key such as
`character/action/direction/subaction` to:

- source image or sprite sheet;
- frame source rectangles;
- frame count and frame duration;
- mirror/transform information;
- the canonical ground anchor and draw size.

Canvas uses `drawImage()` with source rectangles, so a frame is assembled from
small body/face or effect components at draw time. Assets are loaded lazily
for the selected floor/visible characters and cached as decoded browser
resources. No canonical `WORLD` or `CHARACTER` asset is rewritten.

### Dialogue bubbles

The state carries the server-selected bubble id, text, locale, offset and
opacity. The browser uses the bundled font and the existing bubble policy to
draw the small component at the published anchor. The first parity pass must
check Thai and English line metrics, fade opacity and the existing opener/reply
offsets.

If browser text metrics create a visible mismatch, the rollback is a cached
small bubble component generated only when the bubble content changes—not a
full-frame image per tick. The browser path must remain compatible with a
future static-asset/JavaScript deployment.

## Local compatibility and rollback

The current review controls and local startup remain available. The browser
gets an explicit renderer switch:

```text
renderer=canvas   lean JSON + Canvas components
renderer=raster   existing Pillow image path
```

During the prototype, raster remains the default for the untouched `main`
branch. The branch review page may expose Canvas as an opt-in mode. No phase
or acceptance gate is closed until the author checks the Canvas run against
the existing raster view.

## Performance and acceptance gates

All targets are measured on the existing reference machine; they are not
assumed from theory.

### Protocol and host gates

- Canvas responses contain no `image_data_url` and no Base64 raster.
- Lean mode performs zero full-frame Pillow renders and zero per-tick image
  encodes.
- A normal full render state is at most 20KB raw; typical updates should be
  measured separately before adding deltas.
- Simulation behavior and event traces remain equivalent to the existing
  runtime for the same commands and seed.
- Process working set is recorded before and after the lean path; the result
  must demonstrate a material reduction or identify the remaining cache that
  prevents it.

### Browser gates

- `floor02` maintains at least 55 rendered frames per second on the reference
  machine while state updates arrive at 10–15Hz.
- No visible actor snapping during normal interpolation or a short delayed
  response.
- Static world, WorkSeat layering, walking occlusion, effects and bubbles are
  visually accepted against raster checkpoints.
- Diagnostic cards update at a lower rate and do not rebuild the whole actor
  list on every animation frame.

### Regression gates

- `python -m pytest -q` remains green.
- Existing Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat
  lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family,
  conversation and runtime-presentation audits remain green where affected.
- Canonical world/character asset hashes remain unchanged.
- Raster fallback still produces the existing review output.
- Author visual/gameplay acceptance remains separate from automated parity
  reports.

## Implementation sequence after this design

1. Record this design as the branch spec and review the committed document.
2. Add focused protocol/projector tests before implementation code.
3. Build the `floor02` manifest from existing registries and verify its hashes
   and placement counts.
4. Extract the metadata-only render projection while keeping the raster
   adapter on the existing path.
5. Add the JSON-only response and a feature switch without changing the
   legacy response shape.
6. Implement the Canvas static/dynamic passes, interpolation and low-rate
   telemetry updates.
7. Run scenario-by-scenario raster/Canvas parity and performance benchmarks.
8. Only after the branch passes, expand the manifest floor by floor and write
   a separate Cloudflare deployment plan.

## Cloudflare compatibility direction

The resulting browser renderer and manifest are designed to be served as
static assets. For a single-user deployment, Workers Static Assets can serve
the page, JavaScript, manifests and component assets while the browser runs
the lightweight render/simulation client. The current Python/Pillow resident
server should not be placed inside a Worker: Workers have a 128MB isolate
memory limit and request CPU limits, making full-frame Python image work a
poor fit. See the official [Workers Static Assets](https://developers.cloudflare.com/workers/static-assets/)
and [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
documentation.

If multiple viewers must share one world clock, a later deployment can move
only the compact authority/command layer to a Durable Object and use a
WebSocket, while keeping the same Canvas renderer. That choice is deferred
because it adds lifecycle and cost complexity; see the official [Durable Objects WebSocket guidance](https://developers.cloudflare.com/durable-objects/best-practices/websockets/).

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Canvas differs from Pillow in occlusion or layer order | Keep raster as oracle; compare fixed scenarios and publish placement/foreground metadata. |
| Browser Thai font metrics differ | Load the bundled font, test bubble selection/layout, and allow a small content-change-only bubble fallback. |
| Presentation logic gets duplicated in JavaScript | Keep gameplay/presentation decisions in the shared headless projector; JS only resolves assets and draws. |
| Full-floor base image remains larger than desired | First prove cached static texture + dynamic components; later split static placement layers without changing the state contract. |
| A slow client causes memory growth | Bound interpolation/state history and recover with a full state after a sequence gap. |
| Porting to Cloudflare happens too early | Require local parity, performance and author acceptance before the Cloudflare adapter is designed. |
