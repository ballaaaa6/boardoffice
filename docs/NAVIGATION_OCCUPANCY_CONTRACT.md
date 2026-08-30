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
| F2 / F2+ | 7942 | 28 |

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

F2-family Reception visual-local debug projection remains `visual_bounds_top_left`, but **world navigation no longer derives from visual padding**. Navigation is locked to canonical ground anchor `(259,376)` with origin offset `-13U,-4V`. The prior reservation is expanded again by `-U5/+U4`, yielding `35×23 = 805` cells and exact world corners `(241,359) (311,394) (265,417) (195,382)` on all 23 F2-family floors.

## 5. Semantic Occupancy Closure

Closure is derived supplemental occupancy and preserves provenance separately from base footprints.

Required closure kinds:

1. `workstation_desk_chair`: closes the physical gap between the desk and its chair so normal walking cannot cut through the workstation.
2. `desk_desk_seam`: closes narrow seams between geometrically adjacent desks, including arbitrary multi-desk clusters.

Closure cells are solid. Relief is not allowed to remove base footprints or semantic closure cells.

## 6. Navigation Clearance

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

### 6.1 Chair boundary relief

If chair clearance touches/exceeds the Room Domain boundary:

1. clip clearance to Room Domain
2. reduce only the boundary-facing clearance side by 2 cells
3. keep every other side unchanged

Desk clearance is only clipped to Room Domain; it receives no additional boundary relief.

### 6.2 Chair↔chair pair relief

If chair clearances from **separate furniture islands** touch/overlap and would close a valid corridor:

- reduce the mutually-facing clearance sides symmetrically by 1 cell per chair
- target a 2-fine-cell corridor
- never cut base footprint or semantic closure

### 6.3 F1 CEO chair exception

Author-approved placement override:

```text
floor01 / ceo_chair / -U clearance = 0
```

All other chair directions keep the default profile.

## 7. WorkSeat transition contract

Normal pathfinding remains outside the furniture island.

```text
normal walk
→ reachable exterior transition gate
→ WorkSeat state takeover
→ authored seated pose
```

A transition gate must be portal-reachable after all closure/clearance/relief rules have been applied. It is not a tunnel through the chair buffer.

## 8. Required invariants

1. Every active base footprint is fully contained in its Room Domain.
2. Base footprints and semantic closures do not occupy Portal inside cells.
3. Every final walkable cell is reachable from at least one Portal inside cell using 4-neighbor connectivity.
4. Every workstation has a portal-reachable exterior WorkSeat transition gate.
5. Navigation and WorkSeat resolve the same chair placement.
6. Clearance never changes Ground Footprint geometry or walking-depth anchors.
7. Relief never removes base footprint or semantic closure.
8. Every `layout.floor02.large` floor resolves the F2 canonical gameplay metadata family; Room/Portal, workstation geometry/directions, base footprint geometry, closure, clearance and final walkability must match F2 exactly. Visual skins may differ.
9. HumanBall remains navigation-neutral.

## 9. Lean derivation policy

Only three canonical Room masks are materialized in the release:

- `WORLD/COMPILED_NAV/floor00_room_cells.json`
- `WORLD/COMPILED_NAV/floor01_room_cells.json`
- `WORLD/COMPILED_NAV/floor02_room_cells.json`

`WORLD/COMPILED_NAV/OCCUPANCY/` is optional derived cache and is not canonical release payload.

## 10. Phase 8B/8C closeout verification

- Phase 8B full regression: 114/114 PASS
- Phase 8C full regression: 121/121 PASS
- navigation audit: 25 floors / 219 workstations / 0 failures
- F0/F1/F2 final grid/clearance/portal visual QA: author approved
- F2 gameplay metadata family: 23 floors / 0 exact-cell mismatches
- F2-family Reception: 805 cells / fixed anchor `(259,376)` / identical world corners across all 23 floors
- no-redraw walking depth: static world outside actor bounds remains byte-stable
- portal actor lifecycle: deterministic `unspawned → entering → active → exiting → despawned`, final state invisible and despawned
