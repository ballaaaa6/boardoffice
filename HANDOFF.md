# GDS Central Game Core — Handoff

**Updated:** 2026-08-31 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** `PHASE8C_PORTAL_LIFECYCLE_CLOSED_AUTHOR_APPROVED`
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
- The author approved all five dense visual samples on 2026-08-31. Phase 8C is closed; Phase 8D is the next milestone and has not started.

## Latest verification

- Full regression from the new root: `146 passed`.
- Focused portal/movement/crowd regression: `27 passed`.
- Focused Portal/Crowd/WorkSeat comparison regression after the TV Studio Story review: `39 passed`.
- Room Navigation: PASS.
- Navigation Occupancy: PASS for 25 floors / 219 workstations.
- WorkSeat: PASS.
- Phase 6 Spatial: PASS.
- F2 gameplay-metadata family: PASS.
- Central integrity: PASS, with `release_clean=false` because the working tree contains ignored caches/review outputs.
- Historical release candidates are preserved as `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_CLEAN_CANDIDATE.zip`, `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_NORMALIZATION_PROMOTED.zip`, and `releases/GDS_CENTRAL_GAME_CORE_v1.8.4_PRE_ACCEPTANCE_TECHNICAL.zip`; the accepted package is promoted at `releases/GDS_CENTRAL_GAME_CORE_v1.8.4.zip`.
- Fresh dense visual QA is now generated at `LOCAL_REVIEW/PHASE8C_DENSE_10_ACTOR_QA_20260831/`: F0, F1, F2 plus deterministic random floors F14 and F17 (seed `8042`), 10 actors per floor, farthest-point room coverage. The report is PASS with zero active waits, zero collisions, zero static-world diff pixels and all actors despawned.
- Focused portal/crowd regression: `27 passed`; current full regression: `146 passed`. All seven required root audits pass; root Central reports `pass=true` and `release_clean=false` only because local Python caches exist.
- Clean release fresh-extraction verification is complete: `146 passed`, all seven audits exit zero, Central `pass=true`, `release_clean=true`, Python cache count `0`, payload mismatches/missing `0`. Accepted package: `releases/GDS_CENTRAL_GAME_CORE_v1.8.4.zip`; SHA-256: `6d2b1920c5b162657ebe57fb29e5973cc870e39402f889c3c68f6c65d5e91d33` (recorded here after packaging so the in-archive handoff is not self-referential).
- GIF integrity check passed for all five samples: 600×600 canvas, nonzero actual frame counts (`floor00` 674, `floor01` 518, `floor02` 568, `floor14` 568, `floor17` 568), and first/last frames are identical (empty tail/no ghost actor).
- Author visual acceptance: `APPROVED` on 2026-08-31 for `floor00`, `floor01`, `floor02`, `floor14`, and `floor17`; each sample has 10 actors distributed across the walkable room with no visible collision, wait, static-world diff, or ghost tail.

## Most recent project changes

- Re-rooted the repository at `D:\antigravity\board office`; the former nested project directory was removed after its contents and `.git` metadata were moved successfully.
- Archived the four received starter files in `00_STARTING_POINT/` without editing them.
- Consolidated project status into this single active `HANDOFF.md`.
- Renamed former handoffs under `docs/history/` as non-authoritative state snapshots.
- Added the English documentation map at `docs/INDEX.md` and the repeatable release gate at `docs/RELEASE_CHECKLIST.md`.
- Independently checked the supplied TV Studio Story map, chip and visit-animation evidence against the extracted source package. The evidence supports separated portal semantics and object-owned interaction metadata, but does not expose runtime scheduling/queue algorithms or fully decode the foreign interaction tuple.
- Added the QA-only `TOOLS/render_phase8c_dense_crowd_qa.py` wrapper. It does not alter runtime behavior; it records the dense five-floor sample, deterministic random seed, room-wide target sampling and actual GIF frame counts.
- Added the deterministic `TOOLS/build_phase8c_release.py` packer used to produce and validate the clean Phase 8C candidate archive.
- No runtime logic, registries, world assets or character assets were changed during this organization work.

## Research input retained for future work

- The TV reference does not reset Phase 8C: the current GDS portal lifecycle already separates navigation portal data from world art and has explicit inside/outside plus entry/exit rules. Its useful lessons remain recorded for Phase 8D design.
- A future directional entry/exit lane refinement is optional and should be added only if Phase 8C crowd/portal visual review demonstrates a real bottleneck or crossing defect.
- The strongest Phase 8D lesson is an object-owned interaction-slot contract layered over the existing WorkSeat geometry, transition gate and pose compositor. Start with one deterministic slot per workstation while keeping the schema extensible to multiple slots.
- GDS already has the semantic character action registry in `CHARACTER/ACTIONS/gds_standard_v1.json`; Phase 8D should extend/reuse it rather than create a competing registry.
- No TV tuple values, scheduler behavior or queue policy should be copied as fact without runtime/code evidence.

## Next exact task

1. Write the Phase 8D WorkSeat contract and test matrix before changing runtime code.
2. Reuse the existing pathfinding, reachable WorkSeat transition gates, `WorkSeatCore` composition, character movement profile, and identity rules.
3. Implement one deterministic actor on F0, F1, and the F2 family first; expand to crowd interaction only after that contract is stable.
4. Apply the same tests, audits, visual acceptance, and clean-package gate to Phase 8D.

## Current blocker

None. Phase 8C is closed and author-approved; Phase 8D is the next planned implementation milestone.
