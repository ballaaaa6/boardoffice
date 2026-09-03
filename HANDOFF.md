# GDS Central Game Core — Handoff

**Updated:** 2026-09-03 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Track A lean cleanup, the combined VFX/Popup + per-actor BB correction, and the approved startup stamina/CEO bubble-offset correction are engineering-complete. The production TypeScript/JavaScript migration has not started. Author visual/gameplay acceptance is still separate and pending.

## Current state

- `main` remains the active checkout. Static world/character assets, authored geometry, WorkSeat placement, navigation occupancy and reference pixels were preserved.
- Push checkpoint: commit `c3f3d3c` (`feat: finalize lean runtime and visual bubble corrections`) is pushed to `origin/main` on 2026-09-03. The immutable `00_STARTING_POINT/` archive and scratch image remain untracked and untouched.
- Python remains the gameplay oracle and local raster fallback. The browser-owned `floor02` slice is deterministic and metadata-only after its bootstrap load; its core does not poll `/api/tick` while stepping. The review page still intentionally exposes the existing raster/API fallback.
- The project review server was restarted from the updated source for live verification and then stopped after the check; port `8765` has no listener and no duplicate project server remains. Static assets and the user's untracked starting-point files were untouched.
- Startup stamina correction: the canonical actor snapshot, browser bootstrap bundle and `/api/reset` start every actor at `100000` milli-stamina (`100`, `normal`), and the browser boot/reset path now gets the same normal default from `/api/live-start`. The explicit Critical demo still sets its selected actor to `5000` (`5`, `critical`).
- `RUNTIME/visual_selection_core.py` is the canonical selector for both channels. It derives the catalog from the registries, persists only profile/generation/cursor/active binding, and selects at event admission with a per-actor/per-channel deterministic shuffle bag.
- Automatic visual coverage is now all **11/11 VFX** IDs and all **6/6 HumanBall** IDs. Rendering reads the persisted binding and never reselects per frame or performs a per-event request.
- `SpeechSchedulerCore` and `BrowserSpeechReducer` now use one bubble slot per actor. Same-actor overlap is rejected; pair participants claim both slots atomically; physical conversation spot/path cells remain independently claimed. `lanes` remains only a compatibility/diagnostic projection and is not an admission mutex.
- Legacy speech v1 snapshots migrate to scheduler v2 actor slots, pending requests and resource claims. Browser state migration mirrors the same shape.
- The checked-in bundle is regenerated and validated: visual catalog profile `gds.visual_catalog.v1:e224b1dcf9091c77ef3c057cf31636365fe500c3c1af9ee2b94a411b3cf6c527`, bundle revision `6f47b47bd47a94bfdfadebc8d9a4d943e04fa960d5601e5bba762fc3ca640f13`, speech snapshot v2.
- The walking-visitor BB behavior is now mode-specific: `seated_host` keeps the visitor extra `[0, -20]` on top of the normal `-20px` anchor for an actual `-40px` total; `ceo_front` carries explicit `[0, 0]` extras for visitor and CEO so both are actually `-20px`; `standing_pair` keeps its existing explicit opener lift.

## Verification

- `python -m pytest -q` → **404 passed**.
- `node --test TESTS/browser_runtime_test.mjs` → **14 passed**.
- Final focused conversation/speech/contract/parity/renderer regressions → **48 passed**.
- `python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS` → **PASS**.
- `ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS --select F401,F841` → **PASS**.
- Lean audit → **0 exact duplicates, 21 duplicate function-body groups, 3 shared bootstrap calls, 16 direct CLI candidates, 0 selected Ruff findings**. The remaining function groups are retained domain/test helpers until a safe shared boundary is proven.
- Central, Conversation, F2 gameplay metadata, Phase 6, Room Navigation, Navigation Occupancy, WorkSeat and WorkSeat lifecycle audits → **PASS**.
- `git diff --check` → **PASS**.
- `CONTRACTS/central_contract.json` SHA256 matches its checked-in `checksums.sha256` entry; after the live verification process was stopped, port `8765` has no listener and no duplicate project server remains.
- Live browser/API recheck → **PASS**: the updated server reports speech snapshot v2 with per-actor slots and physical resource claims. `seated_host` retains visitor `[0, -20]`, while `ceo_front` carries `[0, 0]` for both participants; the Effects demo exposes independent `humanball:controller` and `vfx:low_battery_drain` bindings. The regenerated bundle contains all **11 VFX** and **6 HumanBall** IDs.
- Browser review page → **PASS**: Canvas renderer loaded the regenerated bundle, Talk mode was set to `seated host`, and the page was paused at the `8400ms` arrival/bubble-start boundary with the visitor BB visible in telemetry while the seated host remained unchanged.
- Startup API probe → **PASS**: updated `/api/live-start` at `60ms` returned all nine actors at `100.0/normal`; explicit `/api/demo-critical` still returned `EMP_W1_0010` at `5.0/critical`.
- CEO bubble-offset probe → **PASS**: `seated_host` remains visitor `-40px`/host `-20px`; updated `ceo_front` plan carries `[0, 0]` for both and renders visitor/CEO at `-20px` each.
- Focused conversation/review/bundle tests → **51 passed**: `python -B -m pytest -q TESTS/test_conversation_behavior.py TESTS/test_browser_bundle_contract.py TESTS/test_runtime_review_server.py TESTS/test_runtime_review_web.py`.

## Next task and open gates

1. Author reviews and accepts the updated startup stamina and CEO bubble behavior at `http://127.0.0.1:8765/`, including Canvas/Raster parity and the unchanged seated/standing modes.
2. Close the remaining browser persistence/replay, zero-request UI source-mode, endurance and Cloudflare/deployment gates.
3. Only after those contracts are frozen, begin the planned TS/JS production migration from the canonical Python contracts and browser parity tests.

No release archive was rebuilt in this session. There is no blocker for the current engineering slice; author acceptance is the remaining approval gate.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
