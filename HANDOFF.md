# GDS Central Game Core — Handoff

**Updated:** 2026-09-04 17:09 +07:00 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** The pre-migration survey and scope clarification are recorded. The
accepted production default on `main` remains Python + Raster. At the author's
request on 2026-09-04, the non-accepted `codex/tsjs-runtime-migration` branch,
its isolated worktree and its uncommitted TypeScript candidate were discarded.
Only `main` remains as an active local worktree; the migration design and plan
were removed during the author's cleanup and are not active implementation.
Python remains the oracle and fallback.

## Current state

- `main` remains the only active checkout at `fde8279`; static world/character assets, authored geometry, WorkSeat placement, navigation occupancy and reference pixels were preserved. The former migration branch/worktree was removed without merging any of its changes into `main`.
- Push checkpoint: commit `cefa4bd` (`fix: normalize startup stamina and CEO bubbles`) is pushed to `origin/main` on 2026-09-03. The author intentionally removed the no-longer-needed `00_STARTING_POINT/` archive; it is excluded from active project scope. The untracked scratch image was removed during cleanup.
- Python remains the gameplay oracle and local raster fallback. The browser-owned `floor02` slice is deterministic and metadata-only after its bootstrap load; its core does not poll `/api/tick` while stepping. The review page still intentionally exposes the existing raster/API fallback.
- Canonical data remains in the authored `WORLD/`, `CHARACTER/` and `CONTRACTS/` trees, with `CENTRAL_MANIFEST.json` and `CHARACTER/FINAL_MANIFEST.json` serving as indexes/integrity maps. `WEB/runtime_simulation_bootstrap.json`, `WEB/runtime_render_manifest.json` and `WEB/runtime_assets/` are generated browser/deployment outputs, not a replacement source of truth; the deleted starting-point archive is outside the active source scope.
- Migration-tool spike: no safe one-click converter covers the full runtime. An AST Python-to-TypeScript tool can scaffold pure logic, while schema-generated TS types, runtime JSON validation, complete Python/TypeScript differential traces, authored pixel checks and Workers/browser integration tests remain required. The non-accepted migration design and plans were removed during cleanup; reopening that direction requires explicit approval.
- Survey checkpoint: the repository has 25 floors, 219 resolved workstations, 429 world PNG blobs, 163 canonical character assets, 11 VFX IDs, 6 HumanBall IDs, 42 JSON Schemas and 9 contract documents. The selected `floor02` browser bundle has 9 actors and is generated output, not a replacement for canonical `WORLD/`, `CHARACTER/` or `CONTRACTS/` data.
- Cleanup audit: no active canonical/runtime file was confirmed dead. The author-approved cleanup removed generated caches, the untracked scratch image, historical migration documents and the selected historical reports. The superseded `v1.8.4` release archive and QA-only scripts remain for separate review.
- Operational preflight finding: the former migration worktree could cause duplicate test-module discovery and import-mismatch errors during an unfiltered root `pytest` run. That worktree is now removed; the clean survey collection command remains `python -m pytest --collect-only -q --ignore=.worktrees` (404 items).
- The migration review servers on ports `8766` and `8767` were stopped as part of the branch cleanup. The `main` review listener on `8765` passed the final smoke check and was stopped after author acceptance. Active static assets were untouched; the author separately removed the starting-point archive.
- Startup stamina correction: the canonical actor snapshot, browser bootstrap bundle and `/api/reset` start every actor at `100000` milli-stamina (`100`, `normal`), and the browser boot/reset path now gets the same normal default from `/api/live-start`. The explicit Critical demo still sets its selected actor to `5000` (`5`, `critical`).
- `RUNTIME/visual_selection_core.py` is the canonical selector for both channels. It derives the catalog from the registries, persists only profile/generation/cursor/active binding, and selects at event admission with a per-actor/per-channel deterministic shuffle bag.
- Automatic visual coverage is now all **11/11 VFX** IDs and all **6/6 HumanBall** IDs. Rendering reads the persisted binding and never reselects per frame or performs a per-event request.
- `SpeechSchedulerCore` and `BrowserSpeechReducer` now use one bubble slot per actor. Same-actor overlap is rejected; pair participants claim both slots atomically; physical conversation spot/path cells remain independently claimed. `lanes` remains only a compatibility/diagnostic projection and is not an admission mutex.
- Legacy speech v1 snapshots migrate to scheduler v2 actor slots, pending requests and resource claims. Browser state migration mirrors the same shape.
- The checked-in bundle is regenerated and validated: visual catalog profile `gds.visual_catalog.v1:e224b1dcf9091c77ef3c057cf31636365fe500c3c1af9ee2b94a411b3cf6c527`, bundle revision `6f47b47bd47a94bfdfadebc8d9a4d943e04fa960d5601e5bba762fc3ca640f13`, speech snapshot v2.
- The walking-visitor BB behavior is now mode-specific: `seated_host` keeps the visitor extra `[0, -20]` on top of the normal `-20px` anchor for an actual `-40px` total; `ceo_front` carries explicit `[0, 0]` extras for visitor and CEO so both are actually `-20px`; `standing_pair` keeps its existing explicit opener lift.
- The discarded typed candidate had known comparison gaps: long-run `conversation_plan` state, dynamic occluder IDs/depth, effect frame-clock alignment, Talk/Wander metadata and cross-runtime save/replay shapes. No candidate/runtime changes from that branch are part of `main`.
- Session tooling: installed the user-scoped `BuildContext/fable-orchestrator` Claude Code plugin as `fable-orchestrator@fable-orchestrator` v1.4.1; the pre-existing `fable-orchestrator@fables` v0.1.0 remains enabled. The local `fable` orchestration call is currently blocked because Claude Code is not logged in; no project source, canonical asset or local server was changed.

## Verification

- Gate 0 oracle freeze completed: annotated tag
  `oracle/python-runtime-2026-09-04` points to `fde8279`; the clean suite ran
  twice with `python -B -m pytest -p no:cacheprovider -q --ignore=.worktrees`
  and returned **404 passed** on both runs. The candidate worktree's
  uncommitted inventory fixture was discarded with that worktree and is not
  part of `main`.
- Gate 1 strict boundary checkpoint → `npm --prefix WEB run typecheck`,
  `typecheck:browser` and `typecheck:node` all pass; contract generation is
  deterministic across 46 files; Vitest passes 32 files / 84 tests; Node
  browser compatibility passes 16/16; Python review/default-route tests pass
  32/32. These checks do not yet establish complete runtime or pixel parity.
- `node --test TESTS/browser_runtime_test.mjs` → **14 passed**.
- Final focused conversation/speech/contract/parity/renderer regressions → **48 passed**.
- `python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS` → **PASS**.
- `ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS --select F401,F841` → **PASS**.
- Lean audit → **0 exact duplicates, 21 duplicate function-body groups, 3 shared bootstrap calls, 16 direct CLI candidates, 0 selected Ruff findings**. The remaining function groups are retained domain/test helpers until a safe shared boundary is proven.
- Central, Conversation, F2 gameplay metadata, Phase 6, Room Navigation, Navigation Occupancy, WorkSeat and WorkSeat lifecycle audits → **PASS**.
- `git diff --check` → **PASS**.
- `CONTRACTS/central_contract.json` SHA256 matches its checked-in `checksums.sha256` entry; the single `main` review server on port `8765` was stopped after verification and no duplicate project server remains.
- Cleanup and live smoke check → **PASS**: 28 approved cleanup targets were moved to the Recycle Bin; no `__pycache__` directory or `*.pyc` file remains outside the excluded starting-point archive. The main page returned `200`, `/api/health` returned `ok=true` with API `v2` and 25 floors, and `/api/live-start` returned `floor02` with 9 actors using Canvas.
- The post-cleanup full regression run was started but intentionally stopped after the author accepted the live-page result; no failure had appeared before interruption.
- Live browser/API recheck → **PASS**: the updated server reports speech snapshot v2 with per-actor slots and physical resource claims. `seated_host` retains visitor `[0, -20]`, while `ceo_front` carries `[0, 0]` for both participants; the Effects demo exposes independent `humanball:controller` and `vfx:low_battery_drain` bindings. The regenerated bundle contains all **11 VFX** and **6 HumanBall** IDs.
- Browser review page → **PASS**: Canvas renderer loaded the regenerated bundle, Talk mode was set to `seated host`, and the page was paused at the `8400ms` arrival/bubble-start boundary with the visitor BB visible in telemetry while the seated host remained unchanged.
- Startup API probe → **PASS**: updated `/api/live-start` at `60ms` returned all nine actors at `100.0/normal`; explicit `/api/demo-critical` still returned `EMP_W1_0010` at `5.0/critical`.
- CEO bubble-offset probe → **PASS**: `seated_host` remains visitor `-40px`/host `-20px`; updated `ceo_front` plan carries `[0, 0]` for both and renders visitor/CEO at `-20px` each.
- Focused conversation/review/bundle tests → **51 passed**: `python -B -m pytest -q TESTS/test_conversation_behavior.py TESTS/test_browser_bundle_contract.py TESTS/test_runtime_review_server.py TESTS/test_runtime_review_web.py`.
- Planning-session inspection → **PASS** before cleanup: the scope-corrected plan mapped each user-listed responsibility to an authoritative Python source, TypeScript boundary, parity evidence and an explicit exit gate. The plan was subsequently removed at the author's request; no source/runtime implementation files were changed.
- Claude Code plugin verification → **PASS**: `claude plugin list` reports both `fable-orchestrator@fable-orchestrator` v1.4.1 and the existing `fable-orchestrator@fables` v0.1.0 enabled. Fable execution remains **blocked pending `/login`**; the project Git worktree remains limited to the pre-existing user changes plus this handoff refresh.

## Next task and open gates

1. Continue only on `main` and select the next explicitly approved task.
2. The TypeScript/JavaScript migration design and plan were removed; reopening
   that direction requires explicit approval and a new isolated branch/worktree.
3. Keep Python as the gameplay oracle and fallback; no production cutover or
   Python deletion is approved.

No release archive was rebuilt in this cleanup session. No active canonical
data or asset was changed. The author removed the out-of-scope starting-point
archive; the discarded migration worktree, its review processes and the
approved cleanup candidates were also removed or moved to the Recycle Bin.
`main` remains the rollback/reference path. There is no approved production
cutover.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
