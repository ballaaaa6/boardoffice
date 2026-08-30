# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`  
**Source of truth:** the unpacked root project  
**Historical starting point:** `00_STARTING_POINT/`

This roadmap belongs to the current project, not to the received v1.8.4 handoff set. It is updated when milestone scope, acceptance status or the next engineering target changes.

## Current position

Phase 8B is the approved foundation. Phase 8C portal actor lifecycle is implemented, regression-tested, visually accepted, clean-packaged, and closed. The narrowly scoped canonical CEO-desk walking-depth corrective gate is implemented, regression-tested, visually accepted and closed. Phase 8D is next.

## Milestones

### 0. Starting point — archived

The original ZIP and the three handoff/roadmap documents are preserved unchanged in `00_STARTING_POINT/`. They describe the incoming baseline and are not living project status.

### Phase 8B — foundation closed

Keep the permanent fine grid, room/portal geometry, navigation occupancy, desk/chair closure and clearance, reception contracts, walking depth and WorkSeat approach gates stable. Static world hashes and canonical F2-family geometry remain protected invariants.

### Phase 8C — closed — author-approved

The production portal actor lifecycle exists in `RUNTIME/portal_actor_lifecycle.py`, is exposed by `RUNTIME/central_core.py`, and has deterministic lifecycle tests. Crowd movement and portal QA layers are present in the root project as supporting runtime/verification code.

Acceptance evidence and exit criteria:

- author approved representative `F0`, `F1`, `F2`, plus deterministic random `F14` and `F17` on 2026-08-31;
- dense QA used 10 actors per floor, seed `8042`, and farthest-point walkable-room targets;
- no ghost/translucent actor after exit, active waits, collisions, or static-world diff pixels;
- portal pair, fade order, facing, speed, and walking depth passed the visual review;
- full regression is `146 passed`; all seven required audits pass;
- the canonical archive is fresh-extracted and reports `release_clean=true`.

### Pre-8D corrective gate — canonical CEO-desk walking depth — closed; author-approved

Correct the visual ordering defect where a walking actor on the front side of a CEO desk can be masked by the desk/PC. The initial F2 report exposed a class-level condition: F0, F1 and the F2 family all fall back to one scalar CEO-desk depth anchor even though their visible front envelopes vary by ground X. Use the proven Reception `front_edge_by_ground_x` mechanism as three canonical render-only profiles—F0, F1 and F2+—for `ceo_desk_cell2`; `ceo_pc` must continue to inherit its desk depth.

Scope and acceptance:

- no world/character artwork, layout placement, Ground Footprint, closure, clearance, Room/Portal or navigation-cell changes;
- F0 and F1 resolve their own canonical CEO front envelopes, while all 23 `layout.floor02.large` floors share the F2 world front-edge contract and retain their visual skins;
- the existing Reception profiles remain unchanged, PC inherits from its owning desk, and standard desks/chairs keep their current behavior because no equivalent reachable front-face defect has been proven for them;
- one centralized validation guard flags future unprofiled objects when reachable actor anchors inside the object's footprint X span disagree between scalar depth and the derived front envelope; this guard does not bulk-change runtime rendering;
- regression covers known real walkable front points, behind points, depth boundaries, PC inheritance and no-redraw pixel stability on all three canonical layouts;
- full regression is `158 passed`; all required audits and the dedicated profile guard pass;
- the dedicated QA render is PASS for F0, F1, F2 and deterministic random F14/F17, with 10 actors per floor targeting the former scalar false band and zero collision/wait/static-world-diff failures;
- author approved the five GIFs/keyframe sheets on 2026-08-31;
- keep this gate distinct from Phase 8D WorkSeat behavior.

### Phase 8D — WorkSeat runtime lifecycle

Implement the actor state machine:

`walking → approach → seated/work → exit seat → walking`

The implementation must reuse the existing pathfinding, reachable WorkSeat transition gates, `WorkSeatCore` seat placement/composition, character movement profile and identity rules. Normal navigation must stop at the exterior gate; the actor must not tunnel through chair clearance.

Initial acceptance should cover one deterministic actor on F0, F1 and F2-family floors, then expand to multi-actor/crowd interaction after the single-actor contract is stable.

## Immediate execution order

1. Write the Phase 8D contract/test matrix before implementing runtime lifecycle behavior.
2. Implement and verify the WorkSeat lifecycle, then repeat the same acceptance and packaging gates.

## Definition of done for every phase

A phase is complete only when implementation, automated tests, required audits, artifact/package verification and explicit author acceptance all agree. A generated report or a stale manifest label alone is not sufficient.
