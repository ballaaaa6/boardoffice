# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`  
**Source of truth:** the unpacked root project  
**Historical starting point:** `00_STARTING_POINT/`

This roadmap belongs to the current project, not to the received v1.8.4 handoff set. It is updated when milestone scope, acceptance status or the next engineering target changes.

## Current position

Phase 8B is the approved foundation. Phase 8C portal actor lifecycle is implemented, regression-tested, visually accepted, clean-packaged, and closed. The narrowly scoped canonical CEO-desk walking-depth corrective gate is implemented, regression-tested, visually accepted and closed. Phase 8D single-actor WorkSeat lifecycle is implemented, regression/audit verified, visually author-approved, clean-packaged and closed.

The active product direction is now Phase 8E: a dashboard-ready fixed floor roster, persistent workstation ownership, per-character stamina and a small deterministic behavior loop. The 8E.W four-way Work/WorkSeat direction slice and the PC workstation frame-channel integration are complete and author-approved; current authored world slots still contain no NE record, but the derived NE runtime path is ready for future use. Multi-actor workstation queues and crowd slot contention are no longer on the active roadmap; they remain optional future work only if a later product need proves them necessary.

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

- 302 canonical character identities and 60 registered Work frame records (46 native, 14 derived);
- action families `idle`, `move`, `variants`, `sad`, `happy` and seated `work`;
- four-way seated `work` character actions: native `SE`/`NW`, derived `SW`/`NE`, each with `normal_work`, direction-named `turn_side_<direction>` and `happy` subactions; WorkSeat now supports a four-way bridge with NE derived from NW while current authored world slots remain three-way;
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

#### Kept outside this single-actor slice

- multi-actor slot contention, queue order, waiting positions, cancellation and timeout policy;
- integration of slot reservations into the crowd scheduler;
- directional entry/exit lanes or multiple slots per furniture object;
- new sit/stand animation artwork;
- any TV Studio Story tuple values, timings, scheduler rules, map markers or assets.

The dashboard-first direction does not require any of these items. Workstation ownership will prevent normal seat contention by construction: one assigned character owns one authored workstation, temporary absence does not vacate it, and only an explicit dashboard unassignment makes it available again.

### Phase 8E — dashboard-ready roster, stamina and behavior loop — conversation one-loop presentation implemented; stamina/home reducer pending

**Author-confirmed current implementation slice:** Dialogue presentation, editable content catalog and the first conversation movement vertical slice. On 2026-08-31 the author requested importing the prepared English/Thai reference phrases into Central and keeping them editable. The active one-line CSV now holds the original 204 imported phrase IDs plus 800 approved authored expansion IDs in both EN and TH, plus the original test line: 1,005 IDs / 2,009 localized rows with category/scope/enabled metadata, full/reference text, provenance, filtered listing and validated reload. It reuses the approved development `fukidashi_base.png` whole-crop skin and existing font/frame rules. WorkSeat turns are named directly as `turn_side_<direction>`: `SE/NW` use `turn_side_sw` / `turn_side_ne` with `V+/V-` axes, while `SW` uses `turn_side_se` / `turn_side_nw` with `U+/U-` axes. The implemented behavior slice is CEO host-only (self-talk and inbound employee talk, no outbound CEO leave-seat talk), employee-to-employee standing pairs in an open axis-aligned slot, employee-to-CEO front talk at the red outward/front envelope, and a derived outward-only seated-host resolver. For current general-employee seats, the preferred outward side is V (`u` equal, `v` changed), with the inner-between-desks side rejected; the resolver still derives the axis from the Work mapping rather than hard-code V. Central now exposes JSON-safe snapshot/spot/plan/advance/cancel operations, deterministic locks, inverse idle facing and return-to-owned-workstation tracks. The approved initial talk loop is one exchange: first bubble at the shared talk boundary, partner at +500ms, both visible until 4,000ms from the first bubble, a shared 300ms fade, then return. Pair text is selected from `conversation_open` → `conversation_reply`; self-talk uses a general office pool; selection is deterministic and assignment-safe. No canonical release is promoted.

**Approved content expansion:** The review draft in `LOCAL_REVIEW/DIALOGUE_CATALOG_DRAFT_20260831/` contained 50 new EN/TH pairs for each of the 16 current office categories (800 pairs / 1,600 rows) and had no normalized exact duplicates or collisions with the active catalog. The author approved it on 2026-08-31, and all pairs were appended to the active CSV. The current fit gate enables 1,108 localized rows and keeps 492 overflow rows stored with `enabled=false`; the import report and pre-import backup are in `LOCAL_REVIEW/DIALOGUE_CATALOG_IMPORT_20260831/`. Future edits use the active CSV directly; shortening and enabling an overflow row requires another fit/reload check.

**Author approval and next seam (2026-09-01):** The movement/facing principle, the initial one-loop timing and the refreshed direct-anchor bubble GIFs are accepted. The runtime timing seam now exposes the 4,000ms global bubble window, 500ms partner gap, 300ms fade and one loop; the partner bubble overlaps the first until the shared fade. Explicit compact `talk_frames` callers remain a legacy review compatibility path. Bubble placement uses the renderer's exact head anchor with pair offsets fixed at `[0, 0]`; no collision resolver, displacement or connector is applied, and a later speaker paints over an earlier bubble when rectangles overlap. Seated bubbles use the composed human offset instead of the chair origin. The draw-order audit confirms that y-sort applies only to walking actors; static/WorkSeat composition uses authored layers and bubbles remain a post-actor overlay. Visual acceptance for this bubble/movement slice is closed; remaining Thai shaping/content quality and stamina/home work stay open.

**PC workstation animation integration (2026-09-01):** The authored `office/pc_*.png` sheets were recovered as a canonical registry for all 25 active PC families. Cell 0 remains the static `SE/SW` frame; cells 1–5 are five distinct `NW/NE` frames, materialized as 100 content-addressed assets and normal variants without changing floor placement geometry. `WorkSeatCore` resolves the independent PC channel, `CentralGameCore.resolve_workstation_pc_frame()` exposes it, and `WorkSeatLifecycle` advances one PC cell after each complete work-action loop (`220ms × action-frame-count`; 440ms for current two-frame normal/turn work). Static floor PNG/RGBA hashes remain exact. Focused PC tests (including derived NE), full regression (239 tests), Central integrity, WorkSeat, Room Navigation, Navigation Occupancy, Phase 6 Spatial and F2 gameplay-metadata audits all pass. The PC GIF evidence is review-only under `LOCAL_REVIEW/PHASE8E_PC_ANIMATION_POC_20260901/`; stamina/event weighting and home/return remain the next engineering seam.

#### Product outcome

Turn the closed Phase 8C/8D movement and WorkSeat primitives into a small persistent office simulation that a future dashboard can drive and observe:

`assigned workstation → enter floor → work → recover by talk/wander/popup or go home → return to the same workstation`

This phase is intentionally smaller than a general crowd scheduler. It must provide stable ownership, actor state, stamina and event transitions without inventing hot-desking, queues, automatic hiring or a database inside Central Core.

#### Existing implementation to reuse

- 302 canonical character identities with stable movement profiles;
- 25 floors and 219 runtime-derived, capacity-one WorkSeat interaction slots;
- the accepted `walking_to_seat → approach → seated_work → exit_seat → walking_from_seat` lifecycle;
- portal `unspawned → entering → active → exiting → despawned` lifecycle;
- canonical pathfinding, movement sampling, crowd collision support, walking depth and render ownership;
- directional `idle` semantics suitable for two standing characters facing one another;
- `move`, seated `work`, and directionless `happy`/`sad` event actions;
- 11 existing effect animations and six HumanBall popup assets, presentation-only and available to seated `normal_work` in all four Work directions through the same derived relation;
- the recovered PC animation registry covers 25 active families with one static cell (`cell0`) and five animated NW/NE cells (`cell1`–`cell5`).

The remaining work is full persistent simulation state, event weighting and stamina/home behavior. No new floor geometry or navigation cells are required for the conversation slice; the PC cells above are the explicitly approved source-sheet recovery for workstation presentation.

#### Author-directed conversation first-slice plan (8E.3; movement and initial presentation)

This plan freezes the movement, seating, geometry, facing and initial one-loop presentation rules. The implementation is renderer-agnostic, JSON-safe and deterministic, and does not edit floor geometry, static art or the employee metadata source. Later work may tune event weights or persistent stamina/home behavior without changing this contract.

**Behavior policy**

1. A CEO workstation is host-only. The actor assigned to `workstation_id=ceo` may self-talk while seated and may receive an employee, but may not leave the seat to initiate an outbound conversation. Because the current employee metadata has no role field, binding the first slice to the CEO workstation is the implementable policy; a future role-only policy can be added without changing the geometry resolver.
2. An employee-to-employee conversation uses `standing_pair`: both actors leave their transient WorkSeat occupancy, keep their original workstation assignments, walk to a free pair of standing cells and face one another with opposite `idle` directions.
3. An employee-to-CEO conversation uses `ceo_front`: only the employee leaves and walks to the reachable outward/front envelope represented by the red arrow; the CEO remains seated and uses `work/normal_work` facing the front slot.
4. A general employee may later be a seated host through `seated_host`: the visitor uses only the outward green side of the host's workstation. The side between two desks is never selected. This is a small extension of the same resolver, not a new coordinate convention.
5. The first slice excludes CEO outbound talk, seated-to-seated/group talk, walk-and-talk, cross-floor partners, queues and automatic vacancy filling. Self-talk is a no-movement fallback, not a hidden partner search.

**Coordinate and facing contract**

- The canonical lattice is `+U=SE`, `-U=NW`, `+V=SW`, `-V=NE`; pathfinding stays 4-neighbor only.
- `u` equal with `v` changed is a V-axis line. A pair `(u,v)` and `(u,v+gap)` faces `SW` and `NE`; reversing the signs swaps the actors without changing the rule.
- `v` equal with `u` changed is a U-axis line. A pair `(u,v)` and `(u+gap,v)` faces `SE` and `NW`.
- Current general-employee Work directions are `SE/NW`, whose authored side turns are V-axis (`turn_side_sw`/`turn_side_ne`), so V is the preferred seated-side and standing-pair axis for the current maps. The resolver must still read `axis`, `sign`, `uv_delta` and `target_idle_direction` from `WorkSeatCore`; it must not hard-code V for a future `SW/NE` employee seat.
- For a seated host, the host turn is the direction named by the side target and the visitor's idle direction is its exact inverse. For example, host `turn_side_sw` + visitor `idle NE`, or host `turn_side_ne` + visitor `idle SW`. For a standing pair, both actors use `idle` only; the final endpoint delta determines the inverse directions, never the last movement step.
- Seated talk positions are derived from the chair footprint/clearance and the walkable grid, never from the visual sprite offset or the WorkSeat transition gate. A seated Work state has no navigation `current_uv`, so the resolver must not invent one.

**Talk-spot resolver**

Add a read-only runtime-derived resolver (proposed `RUNTIME/conversation_spot_core.py`) with a contract/schema (proposed `CONTRACTS/conversation_behavior.json` and `SCHEMA/conversation_behavior.schema.json`). It returns a plan plus a rejection reason without mutating the employee registry.

1. `standing_pair`: enumerate reachable walkable cells on the same floor; prefer V-axis pairs with a named `talk_gap_cells` (initial geometry default 4, collision-safe minimum 3), require every straight segment cell to be walkable, keep a two-cell open navigation ring around both endpoints, reject portals/ingress gates/active furniture clearance and reject the corridor between workstation clearance islands. If V has no candidate, try U with the same rules. Sort by deterministic distance, axis preference, assignment order and UV tie-breaks.
2. `seated_host`: read the host Work direction's two `turn_side_<direction>` bindings, project each side from the chair's navigation footprint and clearance, and expose `ready`, `axis`, `sign`, `target_idle_direction`, `candidate_uv` and `reason` per side. Reject a side whose ray or open ring enters another workstation's clearance or the between-desks corridor; choose the outward side by the larger free-space score, with deterministic tie-breaking.
3. `ceo_front`: resolve the CEO desk's reachable front/depth envelope, not a side-turn lane and not the transition gate. The front direction follows the existing Work facing (floor00/floor01 CEO `SE`/`U+`; floor02-family CEO `SW`/`V+`), and the returned plan keeps the CEO seated.
4. Every returned plan includes floor, mode, axis, signed endpoint delta, endpoint UVs, host/visitor roles, exact facings, path goals, slot identity and the static constraints used. No materialized 219-row talk registry is created.

**Eligibility and atomic locks**

- Resolve candidates from the mutable actor snapshot, not by rereading a guessed character identity. Both actors must be assigned, present on the same floor, not home/leaving/talking and not already reserved. CEO may be a host but never an initiator.
- Select a partner deterministically (same-floor eligible employee, then reachable route cost, assignment order and employee ID). A later seeded selector may vary this without changing the slot contract.
- Acquire locks in one order before any actor leaves a seat: `participant_lock` → `talk_slot_lock` → transient WorkSeat release. A pair has capacity two; a CEO front slot has capacity one visitor plus the seated CEO. Duplicate requests, self-pairing and a slot already reserved return explicit refusal reasons.
- Releasing a WorkSeat means only that its transient occupancy is free. The employee's `assignment`, `floor_id`, `workstation_id` and `slot_id` remain unchanged. Locks release only after both actors are safely at the conversation boundary or after a cancellation return is secured.

**Actor state sequence**

1. `working` receives an explicit talk event or deterministic behavior request; validate policy and snapshot version.
2. `talk_pending` resolves the partner and talk spot, then commits the atomic locks. If no partner/spot/route exists, remain working or use the declared self-talk fallback without half-releasing a seat.
3. `leaving_workseat` runs the existing WorkSeat exit boundary to its canonical transition gate. The seated render owner ends before walking ownership begins; no seat assignment is deleted.
4. `walking_to_talk` routes each visitor through existing 4-neighbor pathfinding and the production crowd reservation helper. Both paths and endpoint reservations are accepted before the pair is shown as talking.
5. `talk_arrival` snaps each actor to its reserved endpoint and explicitly sets inverse `idle` facings. The arrival direction is not reused if the path approached from another side.
6. `talking` exposes participant IDs, mode, endpoint UVs, facings and a presentation hook. The active timing policy keeps one line per participant, starts the partner after 500ms, keeps both bubbles through a shared 4,000ms window, fades for 300ms and holds a seated host in its turn-side Work pose. Assignment/work ownership remains unchanged.
7. `talk_complete` ends the presentation hook, then releases the talk slot and participant lock at one boundary.
8. `returning_to_work` routes each employee back to that employee's original transition gate and invokes the existing WorkSeat lifecycle for the same assigned workstation. CEO front talk routes only the visitor; the CEO never leaves.
9. `cancelled`/`no_path`/`blocked` paths are idempotent. Before leaving, the actor remains working; after leaving, the reducer routes to the safest owned gate/endpoint and returns to `present/idle` with assignment intact. No actor may remain permanently locked or in an occupied seat without its seated render owner.

**Central-facing operations**

Expose read-only and advance operations through `CentralGameCore` (exact names frozen with the contract): resolve a talk spot/plan, validate an actor snapshot, advance one behavior window, cancel a conversation and return JSON-safe events/render states. The facade must reuse `EmployeeMetadataRegistry`, `WorkSeatCore`, `WorkSeatLifecycle`, `NavigationOccupancyCore`, `PathfindingCore`, `CharacterMovementCore`, `DynamicActorReservationCore` and the existing dialogue bubble presenter; it must not mutate the metadata JSON or add a database/UI/network dependency.

**Implementation order**

1. **Completed:** freeze contract/schema, policy refusal reasons, state vocabulary, lock order and snapshot fields; add contract-first tests.
2. **Completed:** implement and audit the read-only spot resolver for all 25 floors/219 WorkSeats, including outward-side and CEO-front classifications.
3. **Completed:** implement atomic participant/talk-slot locks and the minimal mutable actor snapshot while keeping workstation ownership immutable.
4. **Completed:** implement `standing_pair` end-to-end: leave two employee seats, route, reserve, face, expose the presentation hook, cancel safely and return both actors.
5. **Completed:** implement `ceo_front`: one employee leaves, reaches the red front envelope, the CEO stays in `normal_work`, then the visitor returns.
6. **Implemented as a derived resolver:** `seated_host` for general employees with outward-side filtering and existing `turn_side_<direction>` semantics; live production scheduling remains a follow-up.
7. **Completed and visually author-approved:** add rendering/event integration, pair/self-talk content selection, one-loop staggered bubble scheduling, opacity fade, exact head-anchor overlay paint order and GIF evidence. Explicit event weighting, stamina mutation and persistent home/return behavior remain follow-up work.

**Acceptance and regression gates**

- Contract tests reject CEO outbound, cross-floor/self/duplicate partners and occupied locks; repeated input snapshots produce byte-equivalent plans. Unassigned/invalid-UV refusal paths are represented by the runtime error policy and remain in the next negative-case expansion.
- Geometry tests prove `u`/`v` axis invariants, exact inverse facings, walkable endpoints/segments, no portal/clearance/between-desk endpoint, outward-side selection and CEO front direction on F0/F1/F2 plus the 23 F2-family floors.
- State tests prove reserve-before-walk, WorkSeat transient release without assignment loss, walking/Work render-channel exclusivity, atomic lock release, deterministic cancellation and return to the same workstation.
- Render evidence covers standing pair and CEO front on F0/F1/F2 geometry families, one existing bubble presentation hook, depth compositing, exact head anchoring, later-speaker overwrite and labeled return states. Bubble/movement visual acceptance is author-approved; Thai shaping/content quality, F14/F17 expansion and remaining simulation work stay open.
- Run the full Python regression plus Room Navigation, Navigation Occupancy, WorkSeat, Phase 6 Spatial, Central integrity, F2 gameplay-metadata family and a new conversation/spot audit. Visual/behavior author approval remains a gate; generated reports alone cannot close 8E.3.

#### Completed metadata foundation slice

- Added a separate employee-instance registry at CHARACTER/EMPLOYEES/employee_metadata.json. employee_id is the persistent actor key; character_id remains the canonical visual/template key.
- Wave 1 contains all 302 existing character templates. Its deterministic initial roster assigns the 64 original templates first and then 155 custom templates across the 219 authored computer slots, ordered from floor00.ceo through the existing floor/workstation registry. The remaining 83 Wave 1 employees are explicitly unassigned.
- Wave 2 contains 302 pre-generated employee records. All 302 canonical templates are reused exactly once in a new deterministic order; every Wave 2 assignment is null until an explicit future roster decision.
- Wave 2 first names, surnames and nicknames are English-style, gender-aligned to the template name pool, unique within Wave 2 and disjoint from Wave 1 in their corresponding fields. No new character art is created.
- Each employee now carries stable movement speed metadata, stamina profile metadata and a deterministic profile seed. The existing Central, movement and WorkSeat APIs have employee bridges while the original character APIs remain unchanged.
- Existing movement, effect and HumanBall registries are referenced by metadata only. The conversation behavior itself remains a separate next implementation slice.

#### Roster and workstation ownership

1. A floor exposes a dashboard-configured hard capacity that cannot exceed its authored workstation count.
2. Each rostered character owns exactly one workstation on exactly one floor; each workstation has at most one owner.
3. Assignment ownership is separate from transient WorkSeat occupancy. A Phase 8D slot returning to runtime state `free` means no active seat cycle, not that its dashboard assignment is vacant.
4. Going to talk, wandering or going home keeps the workstation assigned to the same character.
5. Only an explicit dashboard `unassign`/dismissal makes a workstation vacant. Vacancies remain empty until the dashboard explicitly fills them; Central Core must not auto-hire or auto-fill.
6. Re-entry always resolves the actor's stored workstation assignment and routes to that workstation's existing transition gate. No nearest-seat search or queue fallback is allowed.
7. Do not duplicate the 219-slot registry. Validate assignments against the existing runtime-derived slot resolver.

#### Persistence boundary and actor snapshot

The first slice should keep Central Core renderer-agnostic and storage-neutral. The dashboard or calling application owns durable storage; Central accepts a JSON-safe snapshot, validates and advances it deterministically, and returns the next snapshot plus events. No database, authentication or network transport belongs in this phase.

At minimum each actor snapshot needs:

- canonical `character_id`, `floor_id`, `workstation_id` and derived `slot_id`;
- presence such as `home`, `entering`, `present` or `leaving`;
- current activity such as `walking_to_work`, `working`, `talking`, `wandering`, `popup_event`, `going_home`, `home_recovery` or `returning_to_work`;
- current position/routing reference when present on a floor;
- `stamina_current`, `stamina_max`, active threshold band and last behavior event;
- stable per-character behavior profile and deterministic event counter/seed material.

The exact vocabulary and legal transitions must be frozen in 8E.0 before implementation. Render actions (`idle`, `move`, `work`, `happy`, `sad`) remain presentation bindings and must not be confused with the higher-level activity state.

#### Stamina contract

1. Each character receives a stable profile; values must not reroll every time a snapshot is resolved. The profile includes at least maximum stamina, work drain rate, recovery rates, low/critical thresholds and behavior-choice weights.
2. Stamina drains only while the actor is actively working and is clamped to its valid range.
3. Talking, wandering and approved popup events may recover stamina according to explicit gameplay rules. Visual effect metadata alone must never mutate stamina.
4. Crossing the low threshold requests one deterministic recovery behavior. Crossing the critical threshold may force `going_home` after an optional fatigue popup.
5. Completing home recovery restores stamina to maximum. Return timing is supplied by the dashboard/schedule input rather than guessed by Central Core.
6. Random-looking choices must be reproducible from stable actor identity plus explicit simulation/event counters so tests and dashboard replays are byte-equivalent.

The metadata contract now records the initial tuning policy: stamina max 100, critical threshold <=10, target work cycle 120–300 seconds, per-employee work drain 600–850 milli-stamina/second, talk recovery 5–9, background-effect recovery 1–3, popup recovery 1–2, wander recovery 1–4, and home delay 8–20 seconds. Event intervals and activity durations are also stored as seeded ranges. These are data-level tuning values; the state reducer and conversation effects are still runtime work.

#### Recovery behaviors and event presentation

- **Talk:** select an eligible present actor on the same floor, resolve reachable standing cells, face the pair with existing `idle` frames, prevent one actor from joining two simultaneous conversations, apply the approved recovery rule, then return each participant to their own assignment. If no partner is available, use the declared fallback.
- **Wander:** select a deterministic reachable room cell, use existing movement/walking-depth ownership, hold briefly if required, then return to the assigned workstation.
- **Popup event:** add a generic actor event/popup channel that can render approved existing effects or HumanBall assets outside seated `normal_work`. Gameplay mapping owns trigger, stamina delta, duration and cooldown; the visual registries remain presentation-only.
- **Go home:** leave WorkSeat through the existing transition gate, route to the portal, exit/despawn, retain assignment while home, restore stamina according to the contract, then re-enter through the portal and return to the same workstation when requested.

The first slice does not require a new sit/stand clip, social furniture, directional queue lane or home scene.

Conversation presentation remains independent from assignment and gameplay stamina. The active presentation slice uses only `fukidashi_base.png` as six complete PNG-derived whole crops. `BB1`, `BB2`, `BB3`, `BB4` and `BB6` are allowed; `BB5` is explicitly excluded. The renderer measures the actual locale font advance/ink bounds, chooses the smallest allowed crop that fits its safe rectangle, rejects overflow instead of wrapping/clipping, and anchors the tail to the visible face center plus the existing frame bob. Following the author's explicit catalog-import request, `CHARACTER/DIALOGUE/dialogue.csv` is the editable source for imported English references, assistant-prepared Thai drafts and future project-authored additions. `reference_import.json` records provenance; runtime does not read the research archive or LOCAL_REVIEW. Keep stable dialogue IDs while editing text, preserve the legacy five-column CSV contract, and require enabled plain text to fit before committing a reload to memory. Context-specific, future-activity, template and oversized English rows are retained but initially disabled; every dialogue-ID render facade rejects disabled rows. Category filtering and deterministic `conversation_open` → `conversation_reply` / self-talk selection are available through Central; event weighting remains pending. The implementation is in `CHARACTER/DIALOGUE/`, `CHARACTER/RUNTIME/dialogue_content.py` / `dialogue_bubble.py` and `RUNTIME/conversation_behavior_core.py`.

The source guide does not specify dialogue font, maximum width, padding or wrapping. APK/native evidence fills in part of that gap: the locale font assets are embedded dynamic fonts (`M+ 1p medium` for English and `Noto Sans Thai` for Thai, serialized at size 16), while the runtime exposes `TextLayout` measurement/wrapping inputs and `Balloon` sizing, padding, tail, clipping and repeat controls. `DrawTalkBox` confirms the selected TV skin is assembled with 3-pixel corners/borders and 20-pixel repeated pieces. The exact original caller settings remain an evidence gap; GDS owns those authored values.

Additional read-only comparison: `com/fukidashi_base.png` visibly contains six complete bubble drawings (four above, two below), usable as fixed-size whole crops without assembly. Its companion `fukidashi_base.seb` separately samples four pieces from the first drawing—left cap `4x18`, right cap `5x18`, body `30x18` and tail `3x5`. The native `DrawFukidashiWindow`/resource ID 6 path uses these pieces to vary width by repeating the body and trimming its final repeat; it does not define an inventory of all complete drawings in the PNG. The six pixel-exact whole crops and full-atlas reconstruction audit are in `LOCAL_REVIEW/FUKIDASHI_BASE_WHOLE_BUBBLES_20260831/`, with bounds explicitly labeled PNG-derived rather than an original six-frame metadata table. The earlier `LOCAL_REVIEW/FUKIDASHI_BASE_AUDIT_20260831/` documents only the four SEB components. No original six-preset selection rule was found; the fixed whole-crop selection rule is therefore an explicit GDS-owned policy rather than a claim about the original TV caller.

The follow-up capacity probe at `LOCAL_REVIEW/FUKIDASHI_BASE_A_TEST_20260831/` overlays `aaaaaaaaaaaaa` on all six whole crops using the recovered blue `M+ 1p medium` baseline at render size 9 and center alignment, then provides a `1/5/9/13/17/21` count ladder. With the probe's explicit 4-pixel horizontal / 3-pixel vertical safe inset, the rough repeated-`a` fit counts are bubbles 1–6: `12/9/6/3/6/8`; the 13-character string measures `65px` and exceeds every tested safe width. These figures remain visual calibration only; the active renderer measures rendered pixel width per string. Its project-owned registry records the safe rectangles, selection order (`BB4`, `BB3`, `BB6`, `BB2`, `BB1`), font files and overflow policy.

The review-only contact sheet at `LOCAL_REVIEW/FUKIBOX_HELLO_WORLD_REVIEW_20260831/` contains 18 tested compositions. With 4-pixel content padding, `hello world` fits at font size 9 in a `66x26` bubble and at font size 16 in a `106x46` bubble; smaller shells are retained as empty-skin/minimum-size references or wrapped-height tests. The safe-area manifest reports no overflow.

#### Dashboard-facing boundary

The Central facade should expose JSON-safe operations equivalent to:

- validate/set a floor capacity and roster snapshot;
- assign or explicitly unassign one character and workstation;
- validate or advance one deterministic actor/floor simulation tick window;
- read a floor snapshot containing assignment, presence, activity, stamina and last event;
- request home/return or another explicit administrative transition when permitted by the contract.

The exact API names are frozen during 8E.0. Persistence, UI widgets, dashboard authentication, networking and database selection remain outside Central Core.

#### Contract-first acceptance matrix

1. **Assignment integrity:** reject over-capacity floors, duplicate characters, duplicate workstation ownership, cross-floor mismatches and unknown/non-ready slots; validate all 25 floors against their authored workstation counts.
2. **Ownership persistence:** talking, wandering, popup and home absence never vacate an assignment; only explicit unassignment creates a vacancy; no vacancy is auto-filled.
3. **Stable identity and stamina:** aliases resolve to one canonical actor; profiles remain stable; stamina drains/recovers only in declared activities, clamps correctly and reproduces from the same snapshot.
4. **Behavior transitions:** low and critical thresholds trigger only legal deterministic choices; cooldowns and no-partner/no-path fallbacks cannot deadlock an actor.
5. **Conversation safety:** both participants are eligible, unique, reachable and never simultaneously seated/rendered elsewhere; they face one another using existing idle actions and return to their own workstations.
6. **Popup separation:** existing effect/HumanBall pixels are reused without changing static assets; gameplay stamina deltas come from the behavior contract, not the visual registry.
7. **Home and return:** the actor exits through the canonical portal, becomes invisible while home, reaches full stamina under the approved rule, re-enters and returns to the same assigned slot.
8. **Render and navigation safety:** walking and WorkSeat representations remain mutually exclusive; all dynamic paths are walkable; no desk/chair occupancy or static-world pixels change.
9. **Dashboard replay:** input snapshot plus explicit events produces byte-equivalent output; snapshots round-trip through JSON without hidden process state.

#### Implementation and acceptance sequence

1. **8E.0 — identity and employee metadata contract:** completed for the metadata slice — stable employee/template split, Wave 1 initial allocation, Wave 2 pre-generation, seeded names, movement and stamina profiles.
2. **8E.P — dialogue presentation and editable catalog:** implementation completed in the root — CSV/content loader, 204 reference phrase IDs plus 800 author-approved expansion phrase IDs in EN/TH, provenance, category/scope/enabled filters, validated atomic reload, `fukidashi_base` whole-crop registry, BB5 exclusion, locale font/fallback policy, pixel-fit selection, character-head/bob anchor and Central/employee presentation facades. The expansion is in Central with fit-based enable flags; 492 overflow rows remain disabled until shortened. Import authorization is recorded; visual/behavior author acceptance, final content review and borrowed-asset/font replacement remain open gates.
3. **8E.W — Work pose, WorkSeat direction and PC frame-channel completeness:** completed and author-approved — canonical Work now has fixed-head/alternating-body turns with exact `turn_side_<direction>` names, native M42–M45 composite frame rules, derived SW/NE final-frame mirrors and a callable four-way NE action series from NW. The runtime WorkSeat bridge now derives a complete NE workstation composite from NW with one mirror relation for character, chair, desk, PC, optional foreground, offsets, VFX and HumanBall channels while preserving source draw layers. PC cells 1–5 are recovered for all 25 active PC families; NW/NE advances one cell per complete work-action loop while SE/SW remain on cell0. Focused exact-composite/PC-channel coverage, WorkSeat audit, navigation/occupancy, Phase 6 spatial, Central integrity and F2 family audits pass; current authored world slots remain 100 SE / 96 NW / 23 SW / 0 NE and floor geometry/static floor hashes remain unchanged.
4. **8E.1 — roster and ownership resolver:** in progress — static initial ownership is wired and validated; mutable snapshot assignment, explicit vacancy commands and all-floor mutation validation remain.
5. **8E.2 — actor snapshot and stamina reducer:** pending — stable per-character profiles, deterministic state-in/state-out advancement, threshold events and clamps.
6. **8E.3 — talk, wander and popup behaviors:** conversation movement and the initial talk timing/presentation are implemented and visually author-approved, including direct head-anchor overlay paint order — one deterministic pair exchange, `conversation_open` → `conversation_reply` content selection, 500ms speaker gap, 4,000ms global bubble window, 300ms fade, seated turn-side hold and assignment-safe return. Thai shaping/content quality, explicit event weighting, stamina mutation, wander, popup and the full live reducer remain pending.
7. **8E.4 — home and return composition:** pending — join WorkSeat, movement and portal primitives while retaining assignment and restoring stamina.
8. **8E.5 — dashboard-facing Central facade:** pending — JSON-safe validation, commands, snapshots and deterministic replay; no persistence backend.
9. **8E.6 — automated and visual verification:** pending — focused contract/runtime/rendering tests, full regression, required navigation/WorkSeat/spatial/integrity/F2 audits, and representative multi-actor QA on F0, F1, F2 plus deterministic random F14/F17.
10. **8E.7 — author gate and release hygiene:** pending — explicit visual/behavior acceptance followed by a fresh clean archive and fresh-extraction verification.

#### Explicitly outside the active roadmap

- workstation queues, hot-desking, slot contention, auto-staffing and a general task scheduler;
- database, network protocol, authentication or dashboard UI implementation;
- skill, productivity, salary, morale or needs systems beyond stamina;
- new character/world artwork, sit/stand clips or a rendered home location;
- TV Studio Story timings, tuple meanings, scheduler rules, map markers and permanent/release visual asset use. Approved development inputs are the provenance-tagged Phase 8E bubble/fonts and the explicitly requested English/Thai dialogue reference import. Bubble/font inputs must be replaced with project-owned artwork/font policy before clean release promotion; the content import does not imply final release acceptance.

## Immediate execution order

1. Completed and author-approved: review the refreshed conversation bubble evidence and preserve the direct head-anchor overlay/paint-order policy, including seated WorkSeat offsets.
2. Add the persistent actor/stamina reducer and bind event weighting to the completed conversation movement/presentation slice without changing its geometry or assignment contract.
3. Add the actor snapshot/stamina reducer and bind the existing wander/effect/popup channels to the stored ranges.
4. Add home/return behavior while retaining the same employee workstation assignment.
5. Keep dashboard infrastructure, database/network persistence, queue/slot-contention and auto-fill outside the active scope until explicitly requested.

## Definition of done for every phase

A phase is complete only when implementation, automated tests, required audits, artifact/package verification and explicit author acceptance all agree. A generated report or a stale manifest label alone is not sufficient.
