# GDS Central Game Core — Handoff

**Updated:** 2026-09-03 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Branch:** `codex/browser-simulation`
**Status:** The browser-owned simulation exploration branch is isolated and has a reviewed design plus implementation plan. No browser simulation source has been implemented yet; the parent lean renderer remains the engineering-verified baseline, and author/design acceptance is **acceptance-pending**.

## Current state

- Static world/character assets, WorkSeat placement, navigation occupancy and reference hashes are unchanged.
- Standing-pair geometry/facing remains the approved contract: equal `v`, four-cell `u` separation, lower `u` → `SW`, higher `u` → `NE`.
- The opener bubble retains `[0, -20]`; the reply retains `[0, 0]`. Standing-pair emotion uses one persisted replayable d6 with even → `happy` and odd → `sad`.
- Talk return retains the owned WorkSeat and the existing 240ms `seat_entry` boundary before exposing `work_seat/work/normal_work`.

## Implemented follow-up correction — 2026-09-02

- Actor-side `talk_pending` now continues the normal work clock and stamina while waiting for the single floor speech lane; critical/cancel/timeout paths have explicit ownership.
- Cancelling a pending talk no longer clears the actor's owned WorkSeat position. Routed talks still use their authored route/hold/return flow, and completion preserves the work-loop clock instead of forcing a frame-zero hold.
- Speech requests retain request id, category, mode, participants, due time and external/lifecycle identity in the queue. Lifecycle priority is ordered before routine pair/solo talk, and unrelated lifecycle completion cannot clear another actor's pending request.
- `spawned`, `workseat_entered` and `returned_to_work` are explicit Central → SpeechScheduler boundaries carrying the actor event timestamp. Greeting and work-start BBs are armed from those boundaries; generic actor sync no longer re-arms work-start on unrelated transitions.
- Live behavior-timer arming skips actors whose stationary SpeechScheduler overlay is active, preventing a new weighted event from competing with the overlay.
- The review panel now exposes speech queue position/category/request id/due time, so a waiting BB can be distinguished from a frozen actor.

## Lean component-renderer branch prototype — 2026-09-03

- Isolated worktree: `D:\antigravity\board office\.worktrees\lean-component-renderer`.
- Design spec committed as `15be4fa`; implementation plan as `93fcafb`; implementation and verification commit as `dc36f55`.
- CentralGameCore, navigation, WorkSeat, speech, stamina, replay semantics, canonical world/character assets and reference hashes remain unchanged.
- `RuntimePresentationLoop(render_mode="headless")` advances the same Central snapshot without materializing a Pillow frame. `renderer=canvas` returns `gds.runtime_render_state.v1` metadata with no `image_data_url`; `renderer=raster` remains the default compatibility path.
- The deterministic floor02 bundle contains a 600×600 static scene plus 181 derived component files for workstation layers, character crops, effects, HumanBall and occluder masks.
- The review page has a visible Canvas/Raster toggle; Canvas uses 100ms polling plus RAF composition/interpolation, while Raster retains the decoded double-buffered image path.

## Browser-owned simulation exploration branch — 2026-09-03

- Isolated worktree: `D:\antigravity\board office\.worktrees\browser-simulation` on `codex/browser-simulation`, branched from the verified lean renderer commit `abc0d86`.
- Design spec: `docs/superpowers/specs/2026-09-03-browser-owned-simulation-design.md`.
- Implementation plan: `docs/superpowers/plans/2026-09-03-browser-owned-simulation.md`.
- The proposed target is single-user browser-owned simulation: one generated Python bootstrap bundle, deterministic JavaScript fixed-step runtime, existing Canvas component renderer, and zero `/api/tick` calls after bootstrap.
- Python `CentralGameCore` remains the source/oracle for generated data, parity traces, local fallback and raster comparison. No Pyodide, Pillow-in-browser, WebGL or shared Durable Object authority is part of this branch.
- No canonical world/character asset, starting-point file or reference hash has been changed. No Cloudflare deployment has started.

## Verification

- Full suite: `python -m pytest -p no:cacheprovider -q` → **364 passed** in 251.85s.
- Focused renderer/web/server/parity/benchmark tests → **57 passed**; final web contract rerun → **10 passed**.
- Benchmark on equal floor02 60ms ticks (60 samples, 5 warmups): Canvas p50 request **1.13ms**, raster **10.63ms**; Canvas payload **23.7KB**, raster **136.4KB**; payload reduction **82.63%**; raster encode p50 **9.774ms**, Canvas encode **0ms**. Canvas RSS stayed approximately flat during the sample; raster grew while initializing/caching its image path.
- Parity trace passed across spawn/work, Talk, Effects/HumanBall and Critical paths for actor IDs, resolved action/direction/subaction, frame metadata, workstation channels, dialogue and paint order.
- No-Pillow guard passed: Canvas API/demo requests do not call full-frame, character, effect, HumanBall or WorkSeat image renderers.
- Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, F2/gameplay-metadata family and conversation audits passed. Runtime presentation QA passed.
- Fresh branch API/static smoke: manifest, static PNG and JS assets returned HTTP 200; Canvas state returned 9 actors with `gds.runtime_render_state.v1` and no `image_data_url`; raw encoded traversal returned HTTP 404. Browser smoke showed Canvas/Raster, Full, Talk, Effects, Critical, Save/Load and Replay with no browser console errors.
- `git diff --check` passed. No release archive was created. The central audit's semantic checks pass; its `release_clean` flag is separate and currently reflects test-generated local Python cache files, not committed package content.

## Acceptance gate

Engineering verification for the parent lean renderer is complete. For this branch, the browser-owned simulation design and plan still need author review before implementation begins. After implementation, the author must review the browser-owned page for visual parity, pixel-art sharpness, dialogue bubble appearance, walking depth, save/load/replay behavior and perceived smoothness. The Canvas bubble is intentionally drawn as a lightweight browser overlay, so exact raster visual parity remains an author decision.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.

**Next concrete task:** review the committed browser-owned simulation spec and plan; after approval, execute Task 1 to export the deterministic `floor02` bootstrap bundle and Python parity traces before porting any runtime behavior.
