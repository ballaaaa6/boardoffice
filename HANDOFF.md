# GDS Central Game Core — Handoff

**Updated:** 2026-09-03 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Branch:** `codex/lean-component-renderer`
**Status:** The lean component-renderer prototype is engineering-verified in the isolated worktree. Author visual/gameplay acceptance is **acceptance-pending**; no Cloudflare deployment has started.

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

Engineering verification is complete. The author must review the Canvas page on the reference machine for visual parity, pixel-art sharpness, dialogue bubble appearance, walking depth and perceived smoothness, then explicitly accept or request adjustments. The Canvas bubble is intentionally drawn as a lightweight browser overlay, so exact raster visual parity remains an author decision.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.

**Next concrete task:** after author acceptance, publish the immutable component bundle and move the same metadata contract behind a Cloudflare Worker/Durable Object while retaining the raster fallback for local review.
