# GDS Central Game Core — Handoff

**Updated:** 2026-09-08 05:12 +07:00 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Zero-API Client-Side Browser Simulation Architecture active on `main`. Character crop and shadow occlusion defects resolved on branch `fix_character_crop_shadow` across all 25 office floors (219 workstations and employees). Occluder masks are now floor-isolated (`WEB/runtime_assets/occluders/{floor_id}/`) and correctly strip opaque dark shadows (rgb <= 64). Python remains offline data oracle, bundle compiler (`TOOLS/build_all_floors.py`), and review fallback.

## Current state

- Active branch: `fix_character_crop_shadow` based on `main`.
- Visual crop & shadow root cause identified and resolved:
  1. `TOOLS/build_runtime_render_manifest.py` previously exported occluder masks to `WEB/runtime_assets/occluders/{placement_id}.png` without floor isolation. Rebuilding all 25 floors caused each floor to overwrite common placement IDs.
  2. `build_runtime_render_manifest.py` omitted `depth_front_edge_world_px` from occluder records.
  3. `walking_depth_core.py` failed to strip opaque shadows (`a=255` but dark), causing desks and reception shadows to generate invisible vertical bounding boxes that clipped characters.
- Fixes applied:
  1. Updated `TOOLS/build_runtime_render_manifest.py` to write masks to `occluders/{floor_id}/{placement_id}.png` and export `"depth_front_edge_world_px"`.
  2. Updated `WEB/viewer_app.js` (`resolveActorOccluderIds`) to prioritize `occ.depth_front_edge_world_px`.
  3. Updated `WORLD/RUNTIME/walking_depth_core.py` to strip all dark pixels (`max(r, g, b) <= 64` and `a > 0`) from occluder masks, preventing opaque shadows from cropping actors.
  4. Rebuilt all 25 office floor manifests and simulation bundles using `TOOLS/build_all_floors.py`.
- Canonical data remains untouched: `WORLD/`, `CHARACTER/`, and `CONTRACTS/` trees preserved with original reference hashes.

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
- Zero-API Living Office Viewer verification → **PASS**: `WEB/viewer.html`, `WEB/viewer_app.js`, and `WEB/viewer_style.css` created from scratch with complete fidelity to Python gameplay oracle:
  1. **Conversational Facing & Dynamic Head-Turn Animations**: Fixed seated host and visitor facing in `core.renderState()`. Seated hosts resolve `subaction = turn_side_*` (e.g., `turn_side_ne`) and dynamically alternate between turn pose and talking/reacting gesture frames (e.g., `M28` and `M45`) at 360ms per frame matching `work_loop_elapsed_ms`. Visitors at talk spots turn to face the host (`SW`) and animate between their two idle posture frames (e.g., `M8` and `M9`) matching `route_elapsed_ms`. Standing pair participants turn to face each other according to `facing_by_actor` and animate their idle postures, preserving happy/sad emotion frames upon session completion. Handled `ceo_front` visitor facing and animation. Fixed hardcoded `frame_ids[0]` bug that previously froze characters in static poses during conversations.
  2. **Authentic Dialogue Bubble (BB) Sprites & Fixed 9px Font**: Rendered authentic `CHARACTER/ASSETS/dialogue/fukidashi_base.png` sprite crops based on canonical `CHARACTER/DIALOGUE/bubble_presets.json` (BB1, BB2, BB3, BB4, BB6) with text rendered in canonical `#0c45fb` (`rgb(12, 69, 251)`). Removed font shrinking loop; font size is strictly fixed at `9px system-ui, -apple-system, 'Segoe UI', sans-serif` without downsizing. Text is clipped to the preset `safe_rect`.
  3. **Autonomous Pair Talks & Character Movement**: Corrected `core.speechReducer.startSession` wrapper to target only `kind === "solo"`, preventing lifecycle speech (`greeting`, `work_start`) from emitting spurious `start_talk_session` commands and getting trapped in an infinite `returned_to_work` loop. Actors now autonomously leave their desks, walk along `talk_outbound` to meet partners (in both `seated_host` and `standing_pair` configurations), converse with dialogue bubbles, walk back along `talk_return`, sit back down, and resume normal work.
  4. **Visual Effects & Popups (VFX & HumanBall)**: With speech lifecycle normalized, actors naturally roll and trigger `background_effect` (VFX like sunshine bloom, coffee energy) and `popup` (HumanBall). Added `✨ Effects` toolbar button for on-demand inspection alongside `💬 Talk` and `💤 Exhaustion`.
  5. **Walking Depth & Occlusion Parity**: Preserved dynamic walking depth front-edge profiles across all floors (F0, F1, F2-family), ensuring characters are never clipped when walking on the visitor side. Fixed Inspector mini-avatar preview by compositing character body and face via `renderer._drawCharacter`.
  6. **25-Floor Multi-Floor Switcher (Zero-API)**: Built all 25 office floor simulation bundles and manifests (`floor00` through `floor36`, 219 total workstations and employees) using `TOOLS/build_all_floors.py` into `WEB/floors/` with shared asset deduplication. Added dynamic floor switcher `<select id="floorSelect">` in toolbar and URL parameter support (`?floor=floorXX`). Switching floors dynamically resets `core` and `renderer` without page reload, restarts the authentic live simulation, and centers viewport with zero `/api/tick` requests. Resolved root manifest parity (`floor02` default) and added `isSwitchingFloor` simulation loop race guard.
  7. **Dialogue Bubble (BB) Fitting & Zero Clipping Enforcement**: Fixed dialogue bubble line selection and rendering to prevent oversized text overflow and clipping at fixed 9px font size without font downscaling. In `TOOLS/build_runtime_simulation_bundle.py`, pinned `font_size_px=9` in `select_bubble()`, filtering bundle lines down to the 1,347 lines that genuinely fit within canonical bubble safe rects (<= 63px for BB1). In `WEB/runtime_simulation_speech.js`, `dialogueFromBag` filters out lines without a verified fitting bubble. In `WEB/viewer_app.js`, `renderer._drawDialogue` measures text metrics at 9px and dynamically selects the smallest fitting bubble (`BB4` -> `BB3` -> `BB6` -> `BB2` -> `BB1`), rejecting/skipping any text wider than the safe rect so clipped text is never rendered. All 25 floor simulation bundles were rebuilt and verified.
  8. **Validation**: `node --check WEB/viewer_app.js` passed; `node --test TESTS/browser_runtime_test.mjs` passed (15/15); `python -m pytest -q TESTS/test_browser_bundle_contract.py` passed (5/5); all 25 floors verified end-to-end with static scene images and core stepping; `python -B -m compileall` passed; `ruff check` passed; static server running on port 8000. No canonical files modified.
  9. **Character Crop & Shadow Occlusion Fix**:
     - Diagnosed character clipping and floating body fragments (hair, shoulders under speech bubbles, straight dress cuts like Caitlin Mitchell at `(288, 329)` on `floor08`): root cause was cross-floor flat file collisions in `WEB/runtime_assets/occluders/{placement_id}.png` where building 25 floors overwrote earlier floor occluders with `floor02`'s furniture shapes, combined with missing `depth_front_edge_world_px` polygons in the runtime manifest.
     - Separated occluder masks into `WEB/runtime_assets/occluders/{floor_id}/{placement_id}.png` in `TOOLS/build_runtime_render_manifest.py`.
     - Exported exact `depth_front_edge_world_px` polygons in manifest occluder records and consumed them dynamically in `WEB/viewer_app.js`.
     - Rebuilt all 25 floor manifests and bundles; deleted deprecated flat occluders.
     - Added contract test `test_occluders_isolated_by_floor_and_export_front_edge` in `TESTS/test_runtime_render_manifest.py` (passed).
     - Verified across all 3,853 walkable cells on `floor08`: 0 cells produce stray floating fragments (reduced from 57 cells before fix); 0 pixels erased at Caitlin Mitchell (`288, 329`) and Clara (`280, 333`).



## Next task and open gates

1. Implement Task 1 of the active Cloudflare browser-runtime plan in a new
   isolated branch/worktree: static build boundary and Wrangler dry-run.
2. Then implement the browser controller and page cutover only after the
   static boundary and current parity tests remain green.
3. Keep Python as the gameplay oracle and fallback; no production cutover or
   Python deletion is approved yet.

No release archive was rebuilt in this cleanup session. No active canonical
data or asset was changed. The author removed the out-of-scope starting-point
archive; the discarded migration worktree, its review processes and the
approved cleanup candidates were also removed or moved to the Recycle Bin.
`main` remains the rollback/reference path. There is no approved production
cutover.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
