# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`  
**Source of truth:** the unpacked root project  
**Historical starting point:** `00_STARTING_POINT/`

This roadmap belongs to the current project, not to the received v1.8.4 handoff set. It is updated when milestone scope, acceptance status or the next engineering target changes.

## Current position

Phase 8B is the approved foundation. Phase 8C portal actor lifecycle is implemented, regression-tested, visually accepted, clean-packaged, and closed. The narrowly scoped canonical CEO-desk walking-depth corrective gate is implemented, regression-tested, visually accepted and closed. Phase 8D single-actor WorkSeat lifecycle is implemented, regression/audit verified, visually author-approved, clean-packaged and closed.

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

### Phase 8D — WorkSeat runtime lifecycle — closed — author-approved

#### Objective

Implement one deterministic actor cycle:

`walking_to_seat → approach → seated_work → exit_seat → walking_from_seat`

Normal navigation must end at the existing reachable exterior transition gate. The lifecycle may hand render ownership to `WorkSeatCore`, but it must never fabricate a seat navigation cell, reinterpret a visual sprite offset as a gameplay anchor, or generate movement samples through chair clearance.

#### Existing inventory to reuse

- 302 canonical character identities and 47 registered body/frame records;
- action families `idle`, `move`, `variants`, `sad`, `happy` and seated `work`;
- seated `work` directions `SE`, `NW` and derived `SW`, each with `normal_work`, `turn_side_a`, `turn_side_b` and `happy` subactions;
- 25 floors and 219 workstation instances: 100 `SE`, 96 `NW` and 23 `SW`;
- all 219 workstation instances already pass `seat_transition_ready` and have one reachable exterior transition gate;
- 30 registered chair families, of which 21 are used by current floors, including the existing optional NW foreground-chair composition;
- 11 work VFX channels and 6 HumanBall popup choices, both already restricted to `work/normal_work`;
- canonical identity, pathfinding, 60 ms movement timelines, speed profiles, walking depth, workstation direction, navigation access and WorkSeat composition runtimes.

#### Data ownership and files

1. Add `CONTRACTS/work_seat_lifecycle.json` plus `SCHEMA/work_seat_lifecycle.schema.json`. The contract owns state vocabulary, legal transitions, render ownership, action bindings, timing policy, slot capacity and error policy.
2. Do **not** materialize another 219-row workstation registry. `RUNTIME/work_seat_lifecycle.py` must derive each interaction slot from canonical sources at runtime:
   - `transition_gate_uv` and readiness from `NavigationOccupancyCore`;
   - `facing`, chair placement/family and visual composition from `WorkSeatCore`;
   - character/action resolution from the existing identity and action registries.
3. Keep `CONTRACTS/work_pose_profiles.json` visual-only. Its character/chair offsets remain forbidden as gameplay anchors.
4. Use a stable derived slot ID such as `workseat:{floor_id}:{workstation_id}:primary`; expose slots as a list even though the first slice always returns one capacity-one slot. This leaves room for future multi-slot furniture without changing the response shape.
5. Extend `WorkSeatCore` only where needed to accept separate character, VFX and HumanBall frame indices while preserving the current `frame_index` API as the backward-compatible fallback.
6. Expose slot resolution and lifecycle construction through `RUNTIME/central_core.py`. The contract drift was corrected to the permanent embedded 225–250% metadata range, and `CENTRAL_MANIFEST.json`, schemas/readmes and reference hashes now describe the implementation-pending acceptance state.

The derived interaction-slot record must be JSON-safe and contain at least `slot_id`, `floor_id`, `workstation_id`, `capacity`, `transition_gate_uv`, `facing`, `chair_placement_id`, `chair_family_id`, `render_owner`, action/subaction bindings, optional `effect_id`/`humanball_id`, and nullable `enter_action`/`exit_action` hooks. The first slice keeps both transition hooks null because no dedicated sit/stand artwork is approved.

#### Actor, slot and render contract

The reservation is accepted atomically before the first inbound walking sample. Therefore the slot transition history is `free → reserved → occupied → releasing → free`, while inbound walking and approach both observe `reserved`.

| Actor phase | Slot state | Action binding | Sole render owner | Position rule |
| --- | --- | --- | --- | --- |
| `walking_to_seat` | `reserved` | `move`, then arrival `idle` if needed | `walking_depth` | existing movement timeline ending exactly at `transition_gate_uv` |
| `approach` | `reserved` | `idle`, facing the workstation | `walking_depth` | stationary at the exterior gate |
| `seated_work` | `occupied` | `work/{subaction}` | `work_seat` | visual placement resolved only by `WorkSeatCore`; actor is off the navigation graph |
| `exit_seat` | `releasing` | `idle`, facing the workstation | `walking_depth` | actor reappears at the same exterior gate; no interpolated chair-clearance path |
| `walking_from_seat` | `free` | `move`, then arrival `idle` if needed | `walking_depth` | existing movement timeline from the gate to the requested exit goal |

Every emitted state must make walking and seated visibility mutually exclusive. It must preserve the canonical `character_id`, movement profile, 60 ms lifecycle tick, raw/visual walking directions, slot ID and transition gate. The seated state retains the gate as a routing reference but must not claim it as the seated sprite position.

Timing rules for the first slice:

- movement retains the existing distance-based animation and per-character 225–250% stable speed profile;
- `approach` and `exit_seat` emit one semantic boundary tick each—no invented tween or hidden TV timing;
- work duration is an explicit positive `work_ticks` input; deterministic tests and QA use 24 ticks (1,440 ms at the shared 60 ms tick);
- work-character cadence is pinned to the existing 220 ms GDS character-render convention, while VFX and HumanBall retain the 140 ms cadence from their own registries; indices are derived from elapsed seated milliseconds instead of forcing all channels to advance together.

#### Runtime API and output

The first public facade should provide the equivalent of:

- `resolve_work_seat_interaction_slot(floor_id, workstation_id)`;
- `resolve_work_seat_actor_cycle(character, floor_id, workstation_id, start_uv, exit_goal_uv=None, work_ticks=24, subaction="normal_work", effect_id=None, humanball_id=None)`.

If `exit_goal_uv` is omitted, the cycle returns to `start_uv`. The result must include the normalized inputs, derived slot, inbound/outbound paths, state rows, phase ranges/counts, slot transition events, timing metadata and final state. It is a deterministic single-cycle resolver, not yet a crowd scheduler or persistent queue.

#### Contract-first test matrix

1. Schema and derivation: validate the new contract; resolve all 219 workstation instances; assert unique per-floor/workstation slot IDs, capacity one, correct direction/chair binding and `seat_transition_ready=true` without a duplicated geometry registry.
2. Canonical directional cases:
   - F0: `floor00.ceo` (`SE`) and `floor00.ws3` (`NW`);
   - F1: `floor01.ceo` (`SE`) and `floor01.ws3` (`NW`);
   - F2: `floor02.ws1` (`SE`), `floor02.ws3` (`NW`) and `floor02.ceo` (`SW`).
3. Identity and determinism: numeric ID, numeric string, character code, full name/nickname and canonical ID aliases must resolve to the same character and byte-equivalent JSON-safe cycle; repeated runs must not reroll speed or timing.
4. Navigation: inbound path starts at the requested walkable cell and ends exactly at the gate; outbound path starts at that same gate; every consecutive cell is four-neighbor and walkable; no walking sample enters an occupied chair/desk cell.
5. State lockstep: assert legal actor order, exact slot transition order, reserve-before-walk, occupied-only-while-seated, release-before-outbound-walk and final slot `free`.
6. Render ownership: at most one visible actor representation per tick; `walking_depth XOR work_seat`; NW foreground ordering and SW single-mirror rules remain intact; static-world pixels are unchanged when dynamic layers are removed.
7. Timing and overlays: exact 60 ms timestamps, exact caller-supplied work duration, elapsed-time-derived character/VFX/HumanBall indices, overlays only during `seated_work`, and rejection of overlays on unsupported subactions.
8. Failure policy: reject unknown floors/workstations/characters, bad UV shapes, non-walkable or unreachable start/exit cells, non-positive work ticks, unsupported subactions/effects/HumanBalls and non-ready transition gates with explicit errors and no fallback guessing.

Planned focused files are `TESTS/test_work_seat_lifecycle_contract.py`, `TESTS/test_work_seat_lifecycle.py` and `TESTS/test_work_seat_lifecycle_rendering.py`; existing WorkSeat, movement, navigation, identity, walking-depth and Central tests remain regression guards.

#### Implementation and acceptance sequence

1. **8D.0 — contract freeze:** completed — schema/contract and contract-first tests; no static asset/world/navigation/action-frame mutation.
2. **8D.1 — derived slot resolver:** completed — one runtime-derived capacity-one slot and all-floor audit over 25 floors / 219 workstations.
3. **8D.2 — lifecycle coordinator:** completed — deterministic inbound/approach/work/exit/outbound states using existing movement/pathfinding and Central facade.
4. **8D.3 — render-channel handoff:** completed — elapsed-time character/VFX/HumanBall indices and exclusive walking/WorkSeat composition; optional overlays only while seated normal_work.
5. **8D.4 — automated verification:** completed — focused tests, full `python -m pytest -q`, required Room Navigation, Navigation Occupancy, WorkSeat, Phase 6 Spatial, Central integrity and F2 gameplay-metadata audits, plus the dedicated Phase 8D lifecycle audit.
6. **8D.5 — visual QA:** completed and author-approved on 2026-08-31 — generated and internally inspected capacity-based five-floor GIF evidence at `LOCAL_REVIEW/PHASE8D_WORKSTATION_CAPACITY_QA_20260831/`. The QA uses exactly one actor per authored computer: F0 `5/5`, F1 `7/7`, F2 `9/9`, F14 `9/9`, and F17 `9/9`, for 39 independent actor cycles. The report is PASS with unique workstation/slot assignments, zero duplicate active slots, zero static-world diff pixels and all final slots free; the five GIFs total about 161 MB.
7. **8D.6 — author gate and release hygiene:** completed — author approval was recorded on 2026-08-31; fresh v1.8.5 packaging produced 738 entries, a fresh extraction passed `179 passed`, all required audits passed, and Central reported `release_clean=true` with zero Python-cache paths. Phase 8D is closed.

#### Deferred beyond this single-actor slice

- multi-actor slot contention, queue order, waiting positions, cancellation and timeout policy;
- integration of slot reservations into the crowd scheduler;
- directional entry/exit lanes or multiple slots per furniture object;
- new sit/stand animation artwork;
- any TV Studio Story tuple values, timings, scheduler rules, map markers or assets.

The next proposal after this accepted single-actor slice will choose a deterministic busy-slot policy and crowd integration from observed GDS behavior; no queue semantics are guessed in this closed slice.

## Immediate execution order

1. Select and scope the next milestone.
2. Keep multi-actor queue/slot-contention semantics deferred until that scope is explicitly approved.

## Definition of done for every phase

A phase is complete only when implementation, automated tests, required audits, artifact/package verification and explicit author acceptance all agree. A generated report or a stale manifest label alone is not sufficient.
