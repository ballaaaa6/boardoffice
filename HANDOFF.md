# GDS Central Game Core — Handoff

**Updated:** 2026-08-31 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** `PHASE8C_CLOSED__CEO_DEPTH_CLOSED__PHASE8D_CLOSED__AUTHOR_APPROVED__CLEAN_PACKAGED`
**Active handoff:** this file only

## Source of truth

- The unpacked project at the root is the active source of truth.
- `00_STARTING_POINT/` is the immutable four-file archive received at project start.
- `ROADMAP.md` defines milestone order; `AGENTS.md` defines working rules.
- `docs/history/` contains state snapshots only. They are not active handoffs.
- Explicit author acceptance is recorded below; the manifest/report remain machine-checkable evidence, not a substitute for the acceptance record.
- The original four-file project baseline remains preserved in `00_STARTING_POINT/`. The TV Studio Story archive currently stored there is external research evidence, not project status or a release input.

## Where the project is now

- Phase 8B navigation/world foundation is author-approved and remains frozen.
- Phase 8C portal actor lifecycle is implemented, visually accepted, and closed; it is wired through `RUNTIME/central_core.py`.
- The lifecycle runs `unspawned → entering → active → exiting → despawned`, keeps deterministic actor identity/movement data, and ends invisible after portal exit.
- Crowd movement/portal QA support is present.
- The author approved all five dense visual samples on 2026-08-31. Phase 8C remains closed.
- A newly reported F2 CEO-desk walking-depth defect was diagnosed and corrected without changing world/character art, placement or navigation: `ceo_desk_cell2` and its inheriting `ceo_pc` now use one centralized policy with layout-specific front-edge metadata for F0, F1 and F2+. The proven Reception depth mechanism was reused only for this desk class; standard desks/chairs and existing Reception profiles remain unchanged. The author approved the five-floor CEO visual QA on 2026-08-31, so this corrective gate is closed.
- Phase 8D is implemented and closed in the root: contract/schema, runtime-derived capacity-one interaction slots for all 219 workstations, deterministic single-actor lifecycle and Central facade. Navigation ends at the existing reachable exterior transition gate; seated visual placement remains owned by `WorkSeatCore`, and its visual offsets are not gameplay anchors. The author approved the corrected capacity-based visual QA on 2026-08-31, and the fresh v1.8.5 package/extract passed the clean-release gate.

## Latest verification

- Full regression from the new root: `179 passed` (`pytest.ini` excludes ignored `releases/.staging/` extraction snapshots from duplicate collection).
- Focused portal/movement/crowd regression: `27 passed`.
- Focused Portal/Crowd/WorkSeat comparison regression after the TV Studio Story review: `39 passed`.
- Focused walking-depth, Reception-depth, no-redraw and F2-family regression after the CEO-depth diagnosis: `21 passed`.
- CEO desk depth/profile and guard regression: `12 passed`; profile guard: PASS for 25 floors / 462 rows, 49 profiled rows and zero unprofiled front-envelope issues.
- Diagnostic evidence: F2 CEO desk footprint corners are `[(307,256),(293,263),(329,281),(343,274)]`; the new profile uses front envelope `[(293,263),(329,281),(343,274)]`. Walkable cell `(205,69)` maps to ground `(300,275)`, which now remains in front of both CEO desk and PC because the local desk front edge at `X=300` is `Y=266.5`.
- Cross-floor scope audit: considering walkable ground anchors that lie within each object's own footprint X span and whose actor box overlaps real asset alpha, the scalar/front-envelope disagreement appeared only for `ceo_desk_cell2` and its inheriting `ceo_pc`: 30 positions on F0, 25 on F1 and 25 on every F2-family floor. Standard desks/chairs only produced lateral, outside-footprint-X differences, which are not proven visual defects and must not be bulk-migrated without separate visual evidence.
- Room Navigation: PASS.
- Navigation Occupancy: PASS for 25 floors / 219 workstations.
- WorkSeat: PASS.
- Phase 6 Spatial: PASS.
- F2 gameplay-metadata family: PASS.
- Central integrity: PASS, with `release_clean=false` because the working tree contains ignored caches/review outputs.
- CEO-desk visual QA: PASS at `LOCAL_REVIEW/CEO_DESK_DEPTH_QA_20260831/`; F0, F1, F2 plus deterministic random F14/F17 (seed `8042`), 10 actors per floor, reachable targets deliberately inside the former scalar false band. All five reports have zero collisions, active waits, static-world diff pixels and portal adjacency failures; actual GIFs are 600×600 with nonzero frames and non-identical first/last frames.
- Historical release candidates are preserved as `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_CLEAN_CANDIDATE.zip`, `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_NORMALIZATION_PROMOTED.zip`, and `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_ACCEPTANCE_TECHNICAL.zip`; the accepted package is promoted at `releases/GDS_CENTRAL_GAME_CORE_v1.8.4.zip`.
- Fresh dense visual QA is now generated at `LOCAL_REVIEW/PHASE8C_DENSE_10_ACTOR_QA_20260831/`: F0, F1, F2 plus deterministic random floors F14 and F17 (seed `8042`), 10 actors per floor, farthest-point room coverage. The report is PASS with zero active waits, zero collisions, zero static-world diff pixels and all actors despawned.
- CEO-desk author acceptance: **APPROVED** on 2026-08-31 for F0, F1, F2, F14 and F17 keyframe/GIF samples. The accepted change remains render-only; no release archive/version bump was requested in this push.
- Phase 8D inventory/planning audit (read-only): 302 character identities, 47 registered frame records, 25 floors, 219 workstation instances (`SE=100`, `NW=96`, `SW=23`), 30 registered chair families / 21 currently used, 11 work VFX and 6 HumanBall choices. All 219 workstation instances resolve `seat_transition_ready=true`.
- Permanent movement metadata is now embedded for all 302 characters in both technical and identity-card registries. The new v4 reroll covers the inclusive 225–250% range (26 distinct values), is synchronized across aliases and actor seeds, and is read without runtime reroll. `CONTRACTS/central_contract.json` and `CENTRAL_MANIFEST.json` now describe this policy.
- Required audits after implementation: Room Navigation PASS; Navigation Occupancy PASS (25 floors / 219 workstations); WorkSeat PASS; Phase 6 Spatial PASS; Central integrity PASS (`release_clean=false` only because local caches/review outputs remain); F2 gameplay-metadata family PASS; dedicated Phase 8D lifecycle audit PASS (9 canonical cycles).
- Supporting visual QA remains generated at `LOCAL_REVIEW/PHASE8D_WORKSEAT_SINGLE_ACTOR_QA_20260831/` and `LOCAL_REVIEW/PHASE8D_SPAWN_TO_WORK_QA_20260831/`; both reports are PASS and are retained as lifecycle evidence.
- The incorrectly scoped all-character GIF batch and renderer were removed after clarification. They were generated review outputs only; no source code, runtime behavior, world art or character assets were removed.
- Capacity-based visual QA is generated at `LOCAL_REVIEW/PHASE8D_WORKSTATION_CAPACITY_QA_20260831/`: F0 has 5 actors for 5 computers, F1 has 7 for 7, and F2/F14/F17 have 9 for 9 each. The report is PASS across 39 independent actor cycles: all workstation/slot assignments are unique, every slot has capacity one and is ready, all actors reach `seated=computer_count`, duplicate active slots are zero, static-world diff is zero, and every final slot is `free`. The five GIFs total about 161 MB, with the largest about 44 MB. The author approved this visual gate on 2026-08-31.
- Fresh v1.8.5 package verification: archive `releases/GDS_CENTRAL_GAME_CORE_v1.8.5.zip` has 738 entries and excludes review outputs, caches, staging and materialized occupancy. A fresh extraction passed `179 passed`; Room Navigation, Ground Footprints, Navigation Occupancy, WorkSeat, Phase 6 Spatial, Central integrity, F2 gameplay-metadata family, Phase 8D lifecycle and walking-depth audits all pass, with Central reporting `release_clean=true` and zero Python-cache paths.
- Phase 8D closeout evidence is recorded in `REPORTS/PHASE8D_CLOSEOUT.json`; the accepted visual QA remains externalized under `LOCAL_REVIEW/` and is intentionally not packaged.

## Most recent project changes

- Added three render-only CEO desk walking-depth profiles and F0/F1/F2+ bindings in `WORLD/REGISTRY/walking_depth_profiles.json`; extended its schema to permit desk profiles.
- Added the centralized omission guard, canonical CEO front/behind/boundary regressions, and deterministic five-floor 10-actor GIF QA tool/report.
- Added `pytest.ini` exclusion for ignored `releases/.staging/` snapshots so the required root test command cannot collect duplicate module names.
- No world artwork, character artwork, layout placement, navigation occupancy, closure, clearance or portal geometry was changed.
- Added `CONTRACTS/work_seat_lifecycle.json` and `SCHEMA/work_seat_lifecycle.schema.json`; implemented `RUNTIME/work_seat_lifecycle.py`, Central slot/cycle/event facades, separate WorkSeat character/effect/HumanBall frame indices, and `VALIDATION/self_audit_work_seat_lifecycle.py`.
- Added explicit action semantics (`idle` conversation standing, `move` walking, seated `work`, directionless `sad/happy` event emotions) and permanent per-character speed metadata with its assignment/audit tool. No world artwork, static placement, navigation geometry or character frame pixels changed.
- Added `TOOLS/render_spawn_to_work_gif.py` and its reproducible full spawn-to-work visual artifact for direct author review.
- Added `TOOLS/render_workstation_capacity_qa.py` and `TESTS/test_workstation_capacity_qa.py`; the QA renderer launches exactly one deterministic actor per authored computer across the five review floors without adding queue or contention semantics to production runtime.
- Expanded `ROADMAP.md` from a locked plan to implementation-complete / visual-acceptance-pending, then closed Phase 8D after author acceptance and clean-package verification; updated manifests, schemas, reference hashes and generated audit reports.

## Research input retained for future work

- A read-only static review of `00_STARTING_POINT/TV_Studio_Story_v1.2.7_EXTRACTED_ASSETS.zip` was completed on 2026-08-31. The archive remains external research evidence only; it is not a project asset or release input, and no runtime/source/asset behavior changed during the review.
- Confirmed static evidence: `chips.txt` contains 89 object rows with four directional local-tuple groups; 20 rows expose more than one tuple in at least one direction. Examples include two-position Audience Seating, a three-position panel and a six-position board. This supports an orientation-aware object-owned interaction-slot list, but the unnamed tuple fields and exact runtime meaning remain unverified.
- Confirmed static evidence: `body/seb.inf` maps stable numeric action IDs to semantic stand/walk/sit/special-work resources and reuses resources with a transform flag; `s_pc0_u.seb` is a separate two-layer, 12-global-frame work resource and its monitor overlay is another resource. Furniture and desk presentation resources are likewise layered and separate from their image atlases.
- Confirmed static evidence: each recovered map references a base floor image plus three flattened `object_id&variant` grids. This reinforces GDS's existing separation of static world art, placement metadata and navigation; it does not justify replacing the approved Phase 8B world/navigation model.
- Phase 8D locked planning basis: keep actor lifecycle and slot occupancy as synchronized tracks—actor `walking_to_seat/approach/seated_work/exit_seat/walking_from_seat`; slot transition history `free/reserved/occupied/releasing/free`. Reserve atomically before inbound walking, keep inbound/approach reserved, and release before outbound walking. Start with one capacity-one slot per workstation, while defining the contract as a list so future furniture can expose multiple orientation-specific slots.
- Phase 8D locked planning basis: name all GDS fields explicitly (`slot_id`, `transition_gate_uv`, `facing`, `render_owner`, action binding and optional effect channels) instead of importing anonymous tuples. Walking and seated render channels must be mutually exclusive; existing `WorkSeatCore`, chair foreground, VFX and HumanBall composition remain the owners of visual placement.
- GDS already has the semantic character action registry in `CHARACTER/ACTIONS/gds_standard_v1.json`; lifecycle phases should bind to that registry. Optional enter/exit clip hooks may be present but null in the first slice because GDS has no approved sit/stand transition frames.
- A future directional entry/exit lane refinement remains optional and should be added only if GDS crowd/portal visual review demonstrates a real bottleneck. No TV tuple values, timing, scheduler behavior, queue policy, map markers or asset resources should be copied as fact without runtime/code evidence.

## Next exact task

Select and scope the next milestone. Phase 8D has no remaining implementation or release gate; multi-actor queue/slot-contention semantics remain deferred until a new milestone is approved.

## Current blocker

No technical blocker. Phase 8D runtime, automated gates, author visual acceptance and clean packaging are green. The existing character action set has `idle`, `move` and seated `work` frames but no dedicated sit/stand frames, so approach/exit remain one-tick semantic takeover states with null transition-action hooks. Multi-actor queue semantics remain intentionally deferred and are the next proposal only; the approved capacity QA uses independent one-actor cycles mapped one-to-one to computers.
