# Navigation Occupancy Contract — v1.8.4

## 1. Active formula

```text
FINAL_OCCUPIED
=
BASE_OBJECT_FOOTPRINTS
+ SEMANTIC_CLOSURES
+ NAVIGATION_CLEARANCE

WALKABLE
=
APPROVED_ROOM_DOMAIN
- FINAL_OCCUPIED
```

`NAVIGATION_CLEARANCE` is runtime navigation policy only. It must never mutate the authored Ground Footprint used by object geometry/depth logic.

## 2. Permanent fine-grid

Profile: `grid.iso.occupancy_fine.v1`

- fine cell: 4×2 px
- U step: `(+2,+1)`
- V step: `(-2,+1)`
- origin: `(28,0)`

Direction mapping used by movement:

- `+U = SE`
- `-U = NW`
- `+V = SW`
- `-V = NE`

## 3. Canonical Room/Portal families

- Floor00 → unique F0 domain/portal
- Floor01 → unique F1 domain/portal
- Floor02 and every `layout.floor02.large` floor → canonical F2 domain/portal

Final author-approved counts:

| Family | Room cells | Portal inside cells |
|---|---:|---:|
| F0 | 4129 | 12 |
| F1 | 5950 | 21 |
| F2 / F2+ | 7774 | 28 |

Approved geometry refinements:

- F0: entrance wedge expanded so navigation clearance does not close the exit connector.
- F1: lower-left Room Domain and Portal repositioned; Reception is fully inside Room Domain.
- F2: connector edge expanded `+V` by 2 fine cells; inherited by F2+.

## 4. Base object footprints

Active reserving types:

- desk
- chair parts 00–02
- reception

Visual-only / zero occupancy:

- PC / monitor
- chair part_03
- HumanBall
- Work VFX

F2-family Reception visual-local debug projection remains `visual_bounds_top_left`, but **world navigation no longer derives from visual padding**. Navigation is locked to canonical ground anchor `(259,376)` with origin offset `-12U,-4V`. The approved reservation is expanded by `-U4/+U4/-V4/+V3`, yielding `34×22 = 748` cells and exact world corners `(243,360) (311,394) (267,416) (199,382)` on all 23 F2-family floors. The `+V` and final `-U1` retractions are navigation-only; walking depth uses the independent visible front-edge profiles for F1/F2+.

## 5. Dynamic actor occupancy

Static object occupancy above remains the only input to primary A*. Runtime crowd
motion uses `RUNTIME/crowd_movement_core.py` as a separate time-layer. Production
playback samples every visible actor on the shared 60 ms tick and compares the
continuous closest approach of their ground-anchor heads at the same normalized
time, using the default 2 px clearance. Historical trails and geometric route
lines are not reservations, so a line may be reused or crossed when the heads
arrive at different times. Static alternate A* routes are tried first; if no
detour can resolve a bottleneck, the launch is shifted before spawn. No active
`crowd_wait`/idle state is inserted after visibility begins, and actor ID,
character identity, speed, and goal remain immutable. Planning is deterministic:
longer trajectories claim lanes first, then priority and input order break ties.
No authored furniture footprint or walking-depth profile is mutated. The legacy
discrete reservation API is retained only for older tools.

## 6. Semantic Occupancy Closure

Closure is derived supplemental occupancy and preserves provenance separately from base footprints.

Required closure kinds:

1. `workstation_desk_chair`: closes the physical gap between the desk and its chair so normal walking cannot cut through the workstation.
2. `desk_desk_seam`: closes narrow seams between geometrically adjacent desks, including arbitrary multi-desk clusters.

Closure cells are solid. Relief is not allowed to remove base footprints or semantic closure cells.

## 7. Navigation Clearance

Default profile `clearance.navigation.default.v1`:

```text
desk:
  -U 4
  +U 4
  -V 4
  +V 4

chair:
  -U 4
  +U 4
  -V 4
  +V 4
```

### 7.1 Chair boundary relief

If chair clearance touches/exceeds the Room Domain boundary:

1. clip clearance to Room Domain
2. reduce only the boundary-facing clearance side by 2 cells
3. keep every other side unchanged

Desk clearance is only clipped to Room Domain; it receives no additional boundary relief.

### 7.2 Chair↔chair pair relief

If chair clearances from **separate furniture islands** touch/overlap and would close a valid corridor:

- reduce the mutually-facing clearance sides symmetrically by 1 cell per chair
- target a 2-fine-cell corridor
- never cut base footprint or semantic closure

### 7.3 F1 CEO chair exception

Author-approved placement override:

```text
floor01 / ceo_chair / -U clearance = 0
```

All other chair directions keep the default profile.

## 8. WorkSeat transition contract

Normal pathfinding remains outside the furniture island.

```text
normal walk
→ reachable exterior transition gate
→ WorkSeat state takeover
→ authored seated pose
```

A transition gate must be portal-reachable after all closure/clearance/relief rules have been applied. It is not a tunnel through the chair buffer.

## 9. Required invariants

1. Every active base footprint is fully contained in its Room Domain.
2. Base footprints and semantic closures do not occupy Portal inside cells.
3. Every final walkable cell is reachable from at least one Portal inside cell using 4-neighbor connectivity.
4. Every workstation has a portal-reachable exterior WorkSeat transition gate.
5. Navigation and WorkSeat resolve the same chair placement.
6. Clearance never changes Ground Footprint geometry or walking-depth anchors.
7. Relief never removes base footprint or semantic closure.
8. Every `layout.floor02.large` floor resolves the F2 canonical gameplay metadata family; Room/Portal, workstation geometry/directions, base footprint geometry, closure, clearance and final walkability must match F2 exactly. Visual skins may differ.
9. HumanBall remains navigation-neutral.

## 10. Lean derivation policy

Only three canonical Room masks are materialized in the release:

- `WORLD/COMPILED_NAV/floor00_room_cells.json`
- `WORLD/COMPILED_NAV/floor01_room_cells.json`
- `WORLD/COMPILED_NAV/floor02_room_cells.json`

`WORLD/COMPILED_NAV/OCCUPANCY/` is optional derived cache and is not canonical release payload.

## 11. Phase 8B/8C closeout verification

- Phase 8B full regression: 114/114 PASS
- Phase 8C lifecycle baseline regression: 121/121 PASS
- Reception depth/`+V` retraction regression: 133/133 PASS
- Crowd reservation regression: swept-segment crossing, actor-identity lock, and
  alternate-route selection covered by the dedicated crowd tests
- Synchronized-head trajectory regression: asynchronous line crossing is allowed,
  head-on motion is resolved before spawn, and active `crowd_wait` remains zero
- navigation audit: 25 floors / 219 workstations / 0 failures
- F0/F1/F2 final grid/clearance/portal visual QA: author approved
- F2 gameplay metadata family: 23 floors / 0 exact-cell mismatches
- F2-family Reception: 748 cells / fixed anchor `(259,376)` / identical world corners across all 23 floors
- F1/F2+ Reception walking depth: independent front-edge-by-ground-X profiles; F0 Reception remains embedded and unbound
- no-redraw walking depth: static world outside actor bounds remains byte-stable
- portal actor lifecycle: deterministic `unspawned → entering → active → exiting → despawned`, final state invisible and despawned
