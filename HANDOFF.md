# GDS Central Game Core — Handoff

**Updated:** 2026-09-03 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Track A lean cleanup and the combined VFX/Popup + per-actor BB correction are engineering-complete. The production TypeScript/JavaScript migration has not started. Author visual/gameplay acceptance is still separate and pending. Startup stamina behavior was audited on 2026-09-03; no runtime fix has been applied and the small review-host correction is pending author approval.

## Current state

- `main` remains the active checkout. Static world/character assets, authored geometry, WorkSeat placement, navigation occupancy and reference pixels were preserved.
- Python remains the gameplay oracle and local raster fallback. The browser-owned `floor02` slice is deterministic and metadata-only after its bootstrap load; its core does not poll `/api/tick` while stepping. The review page still intentionally exposes the existing raster/API fallback.
- The existing project review server is healthy at `http://127.0.0.1:8765/` (PID `17724`). The prior PID `9780` was replaced after applying the walking-visitor BB change; the stale PID `11232` had previously loaded speech v1. There is now one project listener on port `8765`.
- Startup stamina audit: the canonical actor snapshot, browser bootstrap bundle and `/api/reset` all start every actor at `100000` milli-stamina (`100`, `normal`). The browser boot/reset path calls `/api/live-start`, whose review-only default intentionally selects `EMP_W1_0010` and overrides it to `5000` (`5`, `critical`) for the critical-route demonstration. No source, asset, schema or bundle change was made; the review server was restored to reset state after the probe.
- `RUNTIME/visual_selection_core.py` is the canonical selector for both channels. It derives the catalog from the registries, persists only profile/generation/cursor/active binding, and selects at event admission with a per-actor/per-channel deterministic shuffle bag.
- Automatic visual coverage is now all **11/11 VFX** IDs and all **6/6 HumanBall** IDs. Rendering reads the persisted binding and never reselects per frame or performs a per-event request.
- `SpeechSchedulerCore` and `BrowserSpeechReducer` now use one bubble slot per actor. Same-actor overlap is rejected; pair participants claim both slots atomically; physical conversation spot/path cells remain independently claimed. `lanes` remains only a compatibility/diagnostic projection and is not an admission mutex.
- Legacy speech v1 snapshots migrate to scheduler v2 actor slots, pending requests and resource claims. Browser state migration mirrors the same shape.
- The checked-in bundle is regenerated and validated: visual catalog profile `gds.visual_catalog.v1:e224b1dcf9091c77ef3c057cf31636365fe500c3c1af9ee2b94a411b3cf6c527`, bundle revision `0c44dc981c2fd4d157d456e8f67967a928f64fd5a4695de8b1bed7d97efbdd05`, speech snapshot v2.
- The walking-visitor BB correction is implemented in the contract, Python conversation planner and browser bundle generator. In `seated_host` and `ceo_front`, the visitor receives an extra `[0, -20]` on top of the normal `-20px` anchor, giving an actual `-40px` total; the seated host remains at the normal `-20px`. `standing_pair` keeps its existing explicit opener lift.

## Verification

- `python -B -m pytest -q` → **403 passed**.
- `node --test TESTS/browser_runtime_test.mjs` → **14 passed**.
- Final focused conversation/speech/contract/parity/renderer regressions → **48 passed**.
- `python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS` → **PASS**.
- `ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS --select F401,F841` → **PASS**.
- Lean audit → **0 exact duplicates, 21 duplicate function-body groups, 3 shared bootstrap calls, 16 direct CLI candidates, 0 selected Ruff findings**. The remaining function groups are retained domain/test helpers until a safe shared boundary is proven.
- Central, Conversation, F2 gameplay metadata, Phase 6, Room Navigation, Navigation Occupancy, WorkSeat and WorkSeat lifecycle audits → **PASS**.
- `git diff --check` → **PASS**.
- `CONTRACTS/central_contract.json` SHA256 matches its checked-in `checksums.sha256` entry; after replacing the prior process, the review server is PID `17724` on port `8765` with no duplicate project listener.
- Live browser/API recheck → **PASS**: the fresh server reports speech snapshot v2 with per-actor slots and physical resource claims. The `seated_host` and `ceo_front` live plans carry visitor `[0, -20]` and leave the host at default; the Effects demo exposes independent `humanball:controller` and `vfx:low_battery_drain` bindings. The regenerated bundle contains all **11 VFX** and **6 HumanBall** IDs.
- Browser review page → **PASS**: Canvas renderer loaded the regenerated bundle, Talk mode was set to `seated host`, and the page was paused at the `8400ms` arrival/bubble-start boundary with the visitor BB visible in telemetry while the seated host remained unchanged.
- Startup API probe → **PASS/DIAGNOSIS**: `/api/live-start` at `60ms` returned exactly one forced critical actor (`EMP_W1_0010`, `5.0`) and eight actors at `100.0`; `/api/reset`, `CentralGameCore.resolve_runtime_snapshot()` and `runtime_simulation_bootstrap.json` returned all actors at `100.0`.
- Focused review tests → **31 passed**: `python -B -m pytest -q TESTS/test_runtime_review_server.py TESTS/test_runtime_review_web.py`.

## Next task and open gates

1. On author approval, make the normal `/api/live-start` path preserve `100` stamina for every actor; retain low-energy behavior only behind the explicit Critical demo. Expected change is limited to the review host default, its text and a regression assertion; no gameplay contract/bundle/asset regeneration is expected.
2. Author reviews and accepts the live walking-visitor BB lift and complete VFX/HumanBall catalog behavior at `http://127.0.0.1:8765/` (especially Canvas/Raster parity and standing-pair orientation).
3. Close the remaining browser persistence/replay, zero-request UI source-mode, endurance and Cloudflare/deployment gates.
4. Only after those contracts are frozen, begin the planned TS/JS production migration from the canonical Python contracts and browser parity tests.

No release archive was rebuilt in this session. There is no blocker for the current engineering slice; author acceptance is the remaining approval gate.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
