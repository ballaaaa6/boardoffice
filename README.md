# GDS CENTRAL GAME CORE v1.8.4

> v1.8.4 is the Phase 8C portal-lifecycle release. It preserves the author-approved Phase 8B navigation foundation, continuous movement and no-redraw walking depth, then adds the deterministic portal actor lifecycle and the final F2-family reception expansion.

## Current status

**PHASE 8C PORTAL LIFECYCLE / VERIFIED — 2026-08-30**

## Navigation formula

```text
FINAL_OCCUPIED = BASE_OBJECT_FOOTPRINTS + SEMANTIC_CLOSURES + NAVIGATION_CLEARANCE
WALKABLE       = APPROVED_ROOM_DOMAIN - FINAL_OCCUPIED
```

Clearance is navigation-only and does not alter base ground/depth anchors.

## Canonical Room / Portal geometry

| Family | Room cells | Portal inside cells |
|---|---:|---:|
| F0 | 4129 | 12 |
| F1 | 5950 | 21 |
| F2 / F2+ | 7774 | 28 |

F0 and F1 remain unique. All 23 floors using `layout.floor02.large` now resolve gameplay/spatial metadata through the explicit `gameplay.layout.floor02.large` family with `floor02` as canonical.

## Phase 8B hardened runtime

- deterministic 4-neighbor A* pathfinding
- fine-grid movement (`+U=SE`, `-U=NW`, `+V=SW`, `-V=NE`)
- shared character ground anchor `[16,31]`
- semantic desk↔chair and desk↔desk closures
- desk/chair +4 navigation clearance with boundary/pair relief
- exterior WorkSeat transition gates
- **no-redraw walking depth:** completed world is rendered once; foreground world geometry masks actor alpha instead of redrawing furniture over actors
- explicit F2 gameplay metadata family audit/runtime
- F2-family Reception fixed navigation ground anchor independent of transparent visual padding
- independent reception render-depth profiles for F1/F2+ use the visible ground front edge; F0 remains embedded and unbound
- deterministic portal actor lifecycle: unspawned → entering → active → exiting → despawned
- stable per-character movement profiles sampled once from the approved 225–250% range (re-rolled with the v3 speed seed)
- independent per-actor travel on a shared 60 ms tick; optional actor seeds support repeated instances
- distance-driven walk animation with a speed-scaled stride (`0.65 × speed` cells per frame step)
- visual-facing lookahead/hysteresis to suppress rapid direction flips on A* staircase paths
- deterministic crowd movement planning from synchronized head trajectories; trail overlap is allowed, alternate routes are tried, and no actor waits after spawn

## F2/F2+ Reception lock

Visual semantic anchor remains:

```text
sprite-left x = 221
visible alpha-top y = 355
```

Navigation reference:

```text
canonical ground anchor = (259,376)
profile origin offset   = -12U, -4V
axes                    = 34U × 22V
occupied cells          = 748
world corners           = (243,360) (311,394) (267,416) (199,382)
```

This is the prior 20×15 reservation expanded by `-U4`, `+U4`, `-V4`, and `+V3` (the approved `+V` retraction and final `-U1` retraction). All 23 F2-family floors produce identical Reception navigation geometry. Render depth is independent: the visible front edge is used for the F1/F2+ occlusion test instead of the expanded navigation envelope.

## Crowd movement reservation

`RUNTIME/crowd_movement_core.py` schedules renderer-agnostic actor states on the shared 60 ms tick. Production playback uses synchronized continuous head trajectories with a 2 px ground-clearance threshold: only the heads' closest approach at the same time is a conflict. Historical trails and geometric lines may overlap when their heads arrive at different times. Route alternatives are tried first; if a bottleneck has no detour, the actor receives an invisible pre-spawn offset. No `crowd_wait`/idle state is inserted after spawn, and actor identity, speed, and goal remain immutable. Static authored-object occupancy remains unchanged. The legacy discrete reservation API remains available for older tools.

## Final navigation state

| Floor | Room | Base | Closure | Clearance | Occupied | Walkable | Portal |
|---|---:|---:|---:|---:|---:|---:|---:|
| F0 | 4129 | 710 | 116 | 1091 | 1917 | 2212 | 12 |
| F1 | 5950 | 1176 | 156 | 1347 | 2679 | 3271 | 21 |
| F2 / F2+ | 7774 | 2026 | 220 | 1675 | 3921 | 3853 | 28 |

## Lean release policy

Keep canonical assets/shared blobs, registries, runtime, tests, schemas and small reports. Do not package generated QA images/GIFs, `PREVIEW/`, `LOCAL_REVIEW/`, `WORLD/COMPILED_NAV/OCCUPANCY/`, Python caches, or pytest caches.

## Verification

The release gate requires the full test suite, all navigation/work-seat/spatial/central audits, canonical metadata synchronization, and a clean fresh extraction of the release archive.

Required release audits cover Room Navigation, Ground Footprints, Navigation Occupancy (25 floors / 219 workstations), WorkSeat, Phase 6 Spatial, Central package integrity, and F2 gameplay-metadata/Reception synchronization.

See `HANDOFF.md`, `docs/NAVIGATION_OCCUPANCY_CONTRACT.md`, and the reports under `REPORTS/`.

## Grid Floor Editor

The local MVP editor is at `TOOLS/grid_floor_editor/index.html`. It loads the bundled F2
room mask, supports click/rectangle selection, opens or closes Room/Portal Inside/Portal
Outside cells, validates portal pairing/connectivity, and exports a reviewable patch JSON.
F2 is canonical for 23 F2+ floors, so the editor shows that family impact before export.

## Next milestone

**Phase 8D — WorkSeat runtime lifecycle:** walking → approach → seated/work → exit seat → walking.
