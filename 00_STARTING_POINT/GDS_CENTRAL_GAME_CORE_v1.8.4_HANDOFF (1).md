# GDS_CENTRAL_GAME_CORE v1.8.4 — CURRENT HANDOFF

**Date:** 2026-08-30  
**Status:** **WORKING / REVIEW CANDIDATE**  
**Last fully normalized canonical:** `v1.8.2`  
**Detailed roadmap:** `GDS_CURRENT_HANDOFF_ROADMAP_v1.8.4.md`

## Current state

Phase 8B room/portal/navigation geometry is closed and author-approved. Post-8B hardening added smooth continuous movement, F2→F2+ canonical metadata synchronization, larger reception reservations, no-flicker walking depth, and crowd/portal QA across every registered floor.

### Movement

- permanent fine-grid movement
- `4` spatial substeps per fine-grid cell
- walk-cycle animation phase driven by cumulative travelled distance
- character ground anchor `(16,31)`
- full portal fade-out/despawn, no lingering translucent actor
- no-redraw world occlusion, preventing baked-shadow flicker

v1.8.4 tempo candidate:

```text
v1.8.3 frame time = 70ms
v1.8.4 frame time = 60ms
≈ 16.7% faster preview playback
```

The movement geometry/substeps are unchanged; only review/playback tempo was increased.

## Navigation geometry

```text
F0 Room = 4129 / Portal = 12
F1 Room = 5950 / Portal = 21
F2 Room = 7942 / Portal = 28
```

F0 and F1 are unique. F2 is canonical for all floors using `layout.floor02.large`.

## Reception

### F1

```text
16U × 20V = 320 cells
P0 (243,362)
P1 (275,378)
P2 (235,398)
P3 (203,382)
```

Expansion policy:

```text
-U +3
+U +0 (wall-facing side fixed)
-V +3
+V +3
```

Latest navigation counts:

```text
Room     5950
Base     1314
Occupied 2817
Walkable 3133
Portal   21
```

### F2 / F2+

Canonical anchor:

```text
ground anchor world px = (259,376)
origin offset uv       = (-13,-4)
```

Final reservation:

```text
35U × 23V = 805 cells
P0 (241,359)
P1 (311,394)
P2 (265,417)
P3 (195,382)
```

All 23 F2-family floors inherit this same world footprint.

Latest F2-family navigation counts:

```text
Room     7942
Base     2083
Occupied 3978
Walkable 3964
Portal   28
```

## v1.8.4 all-floor crowd QA

Output:

```text
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA
```

Result:

```text
25 registered floors rendered
status = PASS
```

Crowd configuration:

```text
floor00 = 4 agents
floor01 = 4 agents
F2-family floors = 5 agents
```

Every floor has a crowd GIF and route overlay.

Main files:

```text
PHASE8C_V184_ALL_FLOOR_CROWD_QA.json
ALL_FLOORS_CROWD_CONTACT_V184.png
GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA_SUMMARY.zip
```

## Important release note

`GDS_CENTRAL_GAME_CORE_v1.8.4.zip` is currently a working/review package. Its internal `CENTRAL_MANIFEST.json` still identifies `1.8.2 / PHASE8B_HARDENED_CANONICAL`.

Do not promote v1.8.4 to canonical until movement tempo is visually approved and the package is normalized:

1. update manifest/version/status
2. update internal handoff
3. regenerate checksums
4. strip caches/generated QA
5. create clean ZIP
6. fresh-extract the actual ZIP
7. run full tests + audits
8. require `release_clean=true`

## Next milestone

After tempo approval and release normalization, implement the **real Phase 8C portal actor lifecycle**:

```text
unspawned/outside
→ portal entry
→ fade in
→ normal navigation
→ return to portal
→ cross outside
→ fade out
→ despawn
```

The existing GIF crowd flow is QA/playback proof; it is not yet the production actor lifecycle/state machine.

After Phase 8C, integrate the WorkSeat lifecycle:

```text
walking → approach → seated/work → exit seat → walking
```

## Files for continuation

```text
/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.4.zip
/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.4_HANDOFF.md
/mnt/data/GDS_CURRENT_HANDOFF_ROADMAP_v1.8.4.md
/mnt/data/GDS_PHASE8C_V184_ALL_FLOOR_CROWD_QA_SUMMARY.zip
```
