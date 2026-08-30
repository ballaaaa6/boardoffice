# GDS CENTRAL GAME CORE — CURRENT HANDOFF / PHASE 8C

**Handoff date:** 2026-08-30  
**Current release candidate:** `GDS_CENTRAL_GAME_CORE_v1.8.4`  
**Status:** `PHASE8C_PORTAL_LIFECYCLE_CLOSED`

## Release summary

The Phase 8B foundation is closed and author-approved. It includes the permanent
fine grid, F0/F1/F2 room and portal geometry, deterministic 4-neighbor A*,
desk/chair semantic closure and clearance, WorkSeat approach gates, and
no-redraw walking-depth occlusion.

v1.8.4 adds the continuous movement preview and the production portal actor
lifecycle. Each character now receives one deterministic movement profile in
the author-approved 125–175% range. Actors advance independently on a shared
60 ms tick, keep the shared ground anchor `[16,31]`, scale walk stride with
travel speed, and stabilize visual facing across A* staircase paths.

## Navigation contract

```text
FINAL_OCCUPIED = BASE_OBJECT_FOOTPRINTS + SEMANTIC_CLOSURES + NAVIGATION_CLEARANCE
WALKABLE       = APPROVED_ROOM_DOMAIN - FINAL_OCCUPIED
```

The permanent fine grid is `grid.iso.occupancy_fine.v1` with 4×2 px cells,
`U=(2,1)`, `V=(-2,1)`, and origin `(28,0)`. F0 and F1 are unique. F2 is the
canonical gameplay/spatial family for all 23 `layout.floor02.large` floors.

| Family | Room cells | Portal inside cells |
|---|---:|---:|
| F0 | 4129 | 12 |
| F1 | 5950 | 21 |
| F2 / F2+ | 7774 | 28 |

## Reception contract

F1 remains unique at 16U×20V / 320 cells. F2/F2+ use the fixed world ground
anchor `(259,376)` with origin offset `(-13,-4)` and a 35U×23V reservation:

```text
occupied cells = 805
corners        = (241,359) (311,394) (265,417) (195,382)
```

All 23 F2-family floors must resolve the same F2 reception navigation geometry;
visual reception padding remains skin-specific.

## Portal actor lifecycle

`RUNTIME/portal_actor_lifecycle.py` emits renderer-agnostic, JSON-safe samples
for the complete deterministic lifecycle:

```text
unspawned → entering → active → exiting → despawned
```

Entry and exit use the canonical portal inside/outside pair. Normal movement
uses the existing pathfinding and character movement cores. The final state is
invisible and despawned, so no translucent actor remains after portal exit.

Every lifecycle record includes its movement profile, shared playback tick,
raw path direction, and stabilized sprite-facing direction. Speed assignment is
stable by canonical character ID; an optional actor seed is available through
the movement-profile API when repeated instances need distinct stable speeds.

## Verification and packaging gate

Before publishing a release, run the full test suite and these audits:

- Room Navigation
- Ground Footprints
- Navigation Occupancy: 25 floors / 219 workstations
- WorkSeat
- Phase 6 Spatial
- Central package integrity
- F2 gameplay-metadata/reception family synchronization

The release archive must be freshly extracted and must contain no `PREVIEW/`,
`LOCAL_REVIEW/`, materialized occupancy cache, Python cache, or pytest cache.
The final central audit must report `release_clean=true`.

## Next milestone

Phase 8D — WorkSeat runtime lifecycle:

```text
walking → approach → seated/work → exit seat → walking
```
