# GDS CENTRAL GAME CORE — CURRENT HANDOFF / ROADMAP v1.8.4

**Handoff date:** 2026-08-30  
**Current working candidate:** `GDS_CENTRAL_GAME_CORE_v1.8.4`  
**Last fully fresh-extract verified canonical:** `GDS_CENTRAL_GAME_CORE_v1.8.2`  
**Current project state:** **Phase 8B geometry/navigation closed; post-8B movement + reception hardening completed; v1.8.4 movement tempo is under visual review**  
**Immediate next decision:** approve or retune v1.8.4 movement speed, then normalize release metadata + run full fresh-extract closeout before promoting a new canonical baseline.

---

# 0. NON-NEGOTIABLE VISUAL RULE

All visual QA, previews, GIFs, floor assembly and asset work must use **real project assets + deterministic code/PIL/compositor only**.

Do **not** use:

- image generation
- AI repainting
- invented replacement artwork
- generated substitutes for missing game assets

If a visual asset is missing, report it or derive only from real existing project assets according to the project contracts.

---

# 1. SOURCE-OF-TRUTH VERSION LINEAGE

```text
v1.7.0  Lean Central Runtime Derivation
v1.8.0  provisional Phase 8B movement candidate
v1.8.1  Phase 8B canonical closeout
v1.8.2  Phase 8B HARDENED CANONICAL
        - fresh-extract verified
        - 114/114 tests at closeout
        - 25 floors / 219 workstations navigation audit
        - F2 gameplay metadata family locked
        - no-redraw walking depth
        - fixed F2-family reception anchor

v1.8.3  Working functional increment
        - continuous/dense movement model
        - distance-synced walk animation
        - F1 reception enlarged
        - F2/F2+ reception enlarged and synchronized

v1.8.4  CURRENT WORKING / REVIEW CANDIDATE
        - movement tempo increased slightly from v1.8.3
        - all 25 registered floors rendered as crowd/portal QA GIFs
        - all-floor QA report = PASS
        - awaiting author visual approval of final movement tempo
```

## Important packaging note

The current `GDS_CENTRAL_GAME_CORE_v1.8.4.zip` package label is `v1.8.4`, but its internal `CENTRAL_MANIFEST.json` still reports:

```text
version      = 1.8.2
active_phase = PHASE8B_HARDENED_CANONICAL
status       = PHASE8B_HARDENED_CANONICAL_CLOSED
```

Therefore **do not treat v1.8.4 as a freshly normalized canonical release yet**.

Before promotion, update the internal manifest/handoff/checksums and run a clean fresh-extract verification pass.

---

# 2. PHASE 8B — CLOSED / AUTHOR-APPROVED FOUNDATION

The following systems are considered established unless a new visual/gameplay regression is explicitly discovered:

- deterministic 4-neighbor A* pathfinding
- permanent fine-grid navigation
- author-approved F0/F1/F2 Room Domain geometry
- author-approved F0/F1/F2 Portal geometry
- F2 canonical gameplay-metadata family inherited by F2+
- base object footprints
- semantic desk↔chair closure
- desk↔desk seam closure
- desk/chair navigation clearance
- chair Room-boundary relief
- chair↔chair pair relief
- WorkSeat approach / transition gates
- walking depth / occlusion
- no-redraw world compositor
- portal-adjacent spawn/exit QA behavior
- reception fixed-ground-anchor system for F2 family

Do not reopen these systems casually. Changes should be driven by a concrete regression and re-audited.

---

# 3. PERMANENT FINE GRID CONTRACT

```text
profile: grid.iso.occupancy_fine.v1
cell:    4 × 2 px
U step:  (+2,+1)
V step:  (-2,+1)
origin:  (28,0)

+U = SE
-U = NW
+V = SW
-V = NE
```

This fine-grid is the shared navigation coordinate space for Room Domain, footprints, closure, clearance, pathfinding and movement sampling.

---

# 4. CURRENT ROOM / PORTAL GEOMETRY

| Family | Room cells | Portal inside cells | Contract |
|---|---:|---:|---|
| F0 | 4129 | 12 | unique; author-approved entrance wedge |
| F1 | 5950 | 21 | unique; author-approved lower-left domain / portal |
| F2 / F2+ | 7942 | 28 | F2 canonical; +V2 connector expansion |

Rules:

- F0 is unique.
- F1 is unique.
- F2 is the gameplay/spatial canonical baseline for every floor using `layout.floor02.large`.
- There are **23 floors** in the F2 gameplay-metadata family.

---

# 5. ACTIVE NAVIGATION FORMULA

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

Navigation clearance is navigation-only; it must not shift visual placement or depth anchors.

---

# 6. DESK / CHAIR CLEARANCE + RELIEF CONTRACT

Base clearance:

```text
desk  = +4 cells on -U/+U/-V/+V
chair = +4 cells on -U/+U/-V/+V
```

Special rules:

- Chair buffer outside Room Domain is clipped.
- If chair buffer touches/exceeds the Room edge, relieve that boundary-facing chair side by 2 cells.
- When two separate chair-buffer islands meet, relieve 1 cell from each facing chair buffer to preserve a 2-cell corridor.
- Base footprints and semantic closure cells cannot be deleted by relief.
- F1 CEO chair exception remains: `-U clearance = 0`.

---

# 7. WALKING DEPTH / NO-FLICKER CONTRACT

The old walking renderer used:

```text
floor → character → redraw furniture
```

That caused baked/semi-transparent shadow pixels to be alpha-composited repeatedly, producing dark flicker when actors passed furniture.

The accepted contract is:

```text
completed floor rendered once
→ resolve world occlusion from ground depth
→ mask actor where foreground world pixels should occlude it
→ composite actor only
```

The world itself is never redrawn per actor.

QA invariant:

```text
static world pixels outside actor bounds must remain unchanged
```

The no-flicker visual checkpoint was author-approved.

---

# 8. F2 GAMEPLAY METADATA FAMILY — PERMANENT SYNC RULE

Registry/runtime:

```text
WORLD/REGISTRY/gameplay_metadata_families.json
WORLD/RUNTIME/gameplay_metadata_family_core.py
```

Family contract:

```text
family_id          = gameplay.layout.floor02.large
layout_id          = layout.floor02.large
canonical_floor_id = floor02
family_floor_count = 23
```

## Gameplay/spatial data inherited from F2

- fine grid
- Room Domain
- Portal
- workstation placement geometry
- workstation directions
- footprint policy
- closure policy
- clearance / relief policy
- final navigation occupancy behavior
- canonical reception ground-anchor policy

## Per-floor data that remains visual/skin-specific

- floor/background artwork
- desk/chair/PC artwork
- reception artwork
- decorative overlays
- floor theme/skin

Practical workflow rule:

> If future work modifies gameplay/spatial metadata belonging to the F2 layout family, modify F2 canonical data and allow F2+ to inherit it. Do not patch F3/F4/etc. individually unless the difference is explicitly visual-only.

---

# 9. CURRENT RECEPTION CONTRACT

## 9.1 F1 reception

F1 remains unique.

Latest reservation expansion from v1.8.3:

```text
-U +3
+U +0  (wall-facing side stays fixed)
-V +3
+V +3
```

Final footprint:

```text
axes:           16U × 20V
occupied cells: 320
world corners:
P0 = (243,362)
P1 = (275,378)
P2 = (235,398)
P3 = (203,382)
```

Latest navigation values after this expansion:

```text
Room       = 5950
Base       = 1314
Occupied   = 2817
Walkable   = 3133
Portal     = 21
```

## 9.2 F2 / F2+ reception

Visual art can vary per skin, but navigation placement must not depend on transparent asset padding.

Canonical navigation anchor:

```text
ground anchor world px = (259,376)
origin offset uv       = (-13,-4)
```

Latest reservation expansion:

```text
from previous 29U × 15V baseline:
-U +3
+U +3
-V +4
+V +4
```

Final footprint:

```text
axes:           35U × 23V
occupied cells: 805
world corners:
P0 = (241,359)
P1 = (311,394)
P2 = (265,417)
P3 = (195,382)
```

All 23 F2-family floors must resolve this same world footprint.

Representative synchronization QA passed for F2/F3/F14/F36 and family-level comparison reported identical world corners/cell counts.

Latest F2-family navigation values after this expansion:

```text
Room       = 7942
Base       = 2083
Occupied   = 3978
Walkable   = 3964
Portal     = 28
```

---

# 10. MOVEMENT MODEL — v1.8.3 FOUNDATION

The coarse preview stepping was replaced with dense movement sampling.

Accepted movement principles:

```text
A* path cells
→ walk every fine-grid edge
→ 4 spatial substeps per fine-grid cell
→ ground anchor moves every motion frame
→ walk animation phase is derived from cumulative distance travelled
```

Core defaults:

```text
substeps_per_cell          = 4
walk_frame_distance_cells  = 0.5
shared character anchor    = (16,31)
```

This removed the visible behavior where the actor appeared to animate in place and then jump forward.

Portal exit still includes full fade-out/despawn; no translucent ghost actor should remain at the end of the loop.

---

# 11. CURRENT MOVEMENT TEMPO — v1.8.4 REVIEW CANDIDATE

v1.8.3 movement was visually judged smooth but slightly too slow.

v1.8.4 keeps the same movement geometry and animation synchronization but changes preview tempo:

```text
v1.8.3 GIF frame time = 70 ms
v1.8.4 GIF frame time = 60 ms
```

Approximate preview tempo increase:

```text
70 / 60 ≈ 1.167×
≈ 16.7% faster playback
```

Important:

- 4 substeps/cell are unchanged.
- walk-cycle distance synchronization is unchanged.
- pathfinding is unchanged.
- Room/Portal/reception metadata are unchanged from v1.8.3.
- Only preview/crowd playback tempo and QA export behavior changed in v1.8.4.

This speed is **pending author visual approval**.

---

# 12. v1.8.4 ALL-FLOOR CROWD / PORTAL QA

QA output root:

```text
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA
```

Main report:

```text
PHASE8C_V184_ALL_FLOOR_CROWD_QA.json
```

Result:

```text
status      = PASS
floor_count = 25
```

Every registered floor has:

```text
<floor>_crowd_portal_v184.gif
<floor>_crowd_routes_overlay_v184.png
```

Crowd defaults used in the final review bundle:

```text
F0           = 4 agents
F1           = 4 agents
F2-family    = 5 agents per floor
```

All generated loops preserve portal inside↔outside adjacency and include an empty tail after despawn so no ghost actor remains at loop end.

Registered floors covered:

```text
floor00 floor01 floor02 floor03 floor04 floor05 floor06 floor07 floor08 floor09
floor11 floor12 floor13 floor14 floor15 floor16 floor17 floor18 floor19 floor21
floor31 floor33 floor34 floor35 floor36
```

Review aids:

```text
ALL_FLOORS_CROWD_CONTACT_V184.png
GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA_SUMMARY.zip
```

---

# 13. CURRENT VALIDATION STATUS

## v1.8.2 canonical closeout

This remains the last fully normalized fresh-extract release gate:

```text
114 / 114 tests PASS
25 floors / 219 workstations navigation audit PASS
release_clean = true
F2 gameplay metadata family mismatch = 0
```

## v1.8.3 functional increment

Focused regression groups for the following passed during implementation:

- movement integration
- F2 reception anchor lock
- ground footprint system
- reception expansion
- navigation occupancy integration
- Phase 8A / Phase 8B QA regressions
- walking depth / work-seat regressions

## v1.8.4 review candidate

All-floor crowd export report:

```text
25 / 25 floors rendered
status = PASS
```

However, v1.8.4 has **not yet received a full clean-release/fresh-extract promotion pass** equivalent to v1.8.2.

---

# 14. LEAN RELEASE POLICY

A canonical release should retain:

- canonical shared assets/blobs
- registries
- schemas/contracts
- runtime code
- tests
- small reports/handoff

Do not package generated runtime/QA clutter:

- `PREVIEW/`
- bulk QA GIF/PNG output
- `WORLD/COMPILED_NAV/OCCUPANCY/`
- `__pycache__/`
- `.pytest_cache/`
- `*.pyc`

Navigation occupancy should remain runtime-derived/cache-optional.

---

# 15. IMMEDIATE NEXT STEPS

## Gate 1 — visual approval of v1.8.4 tempo

Review several crowd GIFs, especially:

```text
floor00
floor01
floor02
representative F2+ skins
```

Decision:

```text
A. speed is correct → lock tempo
B. still slow → increase tempo slightly
C. too fast → move back toward v1.8.3
```

Do not change movement geometry/substeps unless an actual smoothness regression appears.

## Gate 2 — normalize the next canonical package

After tempo approval:

1. set the internal manifest to the actual promoted version
2. update `active_phase/status`
3. update canonical handoff/roadmap inside the source tree
4. regenerate checksums
5. remove caches/generated QA output from release tree
6. package clean ZIP
7. fresh-extract the actual ZIP
8. run the complete test suite
9. run Room/Footprint/Navigation/WorkSeat/Spatial/Central/F2-family audits
10. require `release_clean=true`

Only after this pass should the new package replace v1.8.2 as canonical.

---

# 16. ROADMAP AFTER MOVEMENT TEMPO LOCK

The next gameplay milestone remains **real Phase 8C portal lifecycle integration**, not merely GIF QA.

Target lifecycle:

```text
floor load
→ actor is outside / unspawned
→ resolve portal entry cell
→ cross outside → inside
→ fade in
→ normal runtime navigation
→ interact / work / idle lifecycle later
→ return to portal
→ cross inside → outside
→ fade out
→ despawn
```

Important distinction:

- Current crowd GIFs prove pathing, spawn/exit adjacency, fade/despawn visualization and all-floor traversal.
- They are still QA/playback tooling.
- A production gameplay actor lifecycle/state machine should be implemented explicitly in Phase 8C.

After that, move to the WorkSeat lifecycle integration:

```text
walking
→ approach cell
→ WorkSeat transition
→ seated/work action
→ exit seat
→ walking
```

---

# 17. FILES TO HAND TO THE NEXT SESSION

Primary working artifacts:

```text
/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.4.zip
/mnt/data/GDS_CURRENT_HANDOFF_ROADMAP_v1.8.4.md
/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.4_HANDOFF.md
```

Movement QA:

```text
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA/
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA/PHASE8C_V184_ALL_FLOOR_CROWD_QA.json
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA/ALL_FLOORS_CROWD_CONTACT_V184.png
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA_SUMMARY.zip
```

Historical fully verified canonical fallback:

```text
/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.2.zip
/mnt/data/GDS_CURRENT_HANDOFF_ROADMAP_v1.8.2.md
```

---

# 18. ONE-PARAGRAPH HANDOFF SUMMARY

The project currently has author-approved Phase 8B room/portal/navigation geometry, semantic occupancy closure/clearance, no-flicker walking-depth occlusion, a permanent F2→F2+ gameplay metadata family, fixed F2-family reception anchors, enlarged F1 and F2/F2+ reception reservations, and a continuous movement preview using 4 spatial substeps per fine-grid cell with distance-synchronized walk animation. v1.8.4 increases preview tempo from 70ms to 60ms per GIF frame and successfully exports crowd/portal traversal QA for all 25 registered floors. The next session should first obtain visual approval of that tempo; then perform a clean manifest/checksum/fresh-extract release normalization before promoting a new canonical baseline. After that, proceed to the real Phase 8C production portal actor lifecycle and later WorkSeat lifecycle integration.
