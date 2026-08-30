# GDS Central Game Core — Handoff

**Updated:** 2026-08-31 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** `PHASE8C_PORTAL_LIFECYCLE_CLOSED_AUTHOR_APPROVED__CEO_DESK_DEPTH_AUTHOR_APPROVED`
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
- The author approved all five dense visual samples on 2026-08-31. Phase 8C remains closed and Phase 8D has not started.
- A newly reported F2 CEO-desk walking-depth defect was diagnosed and corrected without changing world/character art, placement or navigation: `ceo_desk_cell2` and its inheriting `ceo_pc` now use one centralized policy with layout-specific front-edge metadata for F0, F1 and F2+. The proven Reception depth mechanism was reused only for this desk class; standard desks/chairs and existing Reception profiles remain unchanged. The author approved the five-floor CEO visual QA on 2026-08-31, so this corrective gate is closed.

## Latest verification

- Full regression from the new root: `158 passed` (`pytest.ini` now excludes ignored `releases/.staging/` extraction snapshots from duplicate collection).
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

## Most recent project changes

- Added three render-only CEO desk walking-depth profiles and F0/F1/F2+ bindings in `WORLD/REGISTRY/walking_depth_profiles.json`; extended its schema to permit desk profiles.
- Added the centralized omission guard, canonical CEO front/behind/boundary regressions, and deterministic five-floor 10-actor GIF QA tool/report.
- Added `pytest.ini` exclusion for ignored `releases/.staging/` snapshots so the required root test command cannot collect duplicate module names.
- No world artwork, character artwork, layout placement, navigation occupancy, closure, clearance or portal geometry was changed.

## Research input retained for future work

- The TV reference does not reset Phase 8C: the current GDS portal lifecycle already separates navigation portal data from world art and has explicit inside/outside plus entry/exit rules. Its useful lessons remain recorded for Phase 8D design.
- A future directional entry/exit lane refinement is optional and should be added only if Phase 8C crowd/portal visual review demonstrates a real bottleneck or crossing defect.
- The strongest Phase 8D lesson is an object-owned interaction-slot contract layered over the existing WorkSeat geometry, transition gate and pose compositor. Start with one deterministic slot per workstation while keeping the schema extensible to multiple slots.
- GDS already has the semantic character action registry in `CHARACTER/ACTIONS/gds_standard_v1.json`; Phase 8D should extend/reuse it rather than create a competing registry.
- No TV tuple values, scheduler behavior or queue policy should be copied as fact without runtime/code evidence.

## Next exact task

1. Write the Phase 8D WorkSeat contract/test matrix before changing runtime behavior.
2. Implement and verify the planned single-actor WorkSeat lifecycle, then repeat the same acceptance and packaging gates.

## Current blocker

No technical blocker. The CEO-desk corrective gate is author-approved; Phase 8D is the next implementation milestone. A release archive/version refresh remains a separate packaging step when requested.
