# GDS Central Game Core — Handoff

**Updated:** 2026-09-03 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** `main` (`18f0436`) now contains the engineering-verified lean component-renderer, browser-owned simulation slice (Tasks 1–4), and the approved standing-pair orientation correction. Visual/gameplay acceptance and the remaining browser persistence/UI/endurance gates remain **acceptance-pending**.

## Current state

- Static world/character assets, WorkSeat placement, navigation occupancy and reference hashes are unchanged.
- Current standing-pair geometry/facing contract is equal `u`, four-cell `v` separation, upper-right/lower-`v` endpoint → `SW`, lower-left/higher-`v` endpoint → `NE`.
- Implemented standing-pair orientation correction (2026-09-03): the contract/schema now prefer V with U fallback and `ascending_v`; the resolver default reads that contract, the browser bundle was regenerated, and browser transition/fade sampling was aligned with the Python oracle. Static world/character assets, WorkSeat placement and reference hashes are unchanged.
- The opener bubble retains `[0, -20]`; the reply retains `[0, 0]`. Standing-pair emotion uses one persisted replayable d6 with even → `happy` and odd → `sad`.
- Talk return retains the owned WorkSeat and the existing 240ms `seat_entry` boundary before exposing `work_seat/work/normal_work`.

## Implemented follow-up correction — 2026-09-02

- Actor-side `talk_pending` now continues the normal work clock and stamina while waiting for the single floor speech lane; critical/cancel/timeout paths have explicit ownership.
- Cancelling a pending talk no longer clears the actor's owned WorkSeat position. Routed talks still use their authored route/hold/return flow, and completion preserves the work-loop clock instead of forcing a frame-zero hold.
- Speech requests retain request id, category, mode, participants, due time and external/lifecycle identity in the queue. Lifecycle priority is ordered before routine pair/solo talk, and unrelated lifecycle completion cannot clear another actor's pending request.
- `spawned`, `workseat_entered` and `returned_to_work` are explicit Central → SpeechScheduler boundaries carrying the actor event timestamp. Greeting and work-start BBs are armed from those boundaries; generic actor sync no longer re-arms work-start on unrelated transitions.
- Live behavior-timer arming skips actors whose stationary SpeechScheduler overlay is active, preventing a new weighted event from competing with the overlay.
- The review panel now exposes speech queue position/category/request id/due time, so a waiting BB can be distinguished from a frozen actor.
- Cloudflare feasibility baseline: the current web path is a local Python/Pillow review host, not a deployable Worker. A warmed live `floor02` probe measured simulation-only p50 `0.23ms`, but advance+render p50 `12.2ms`, WebP encode p50 `8.76ms`, no-HTTP tick wall p50 `20.98ms`, and compact payload p50 about `140KB`; the active local server process was about `275MB` working set. The primary hotspot is full-frame rasterization/Base64 transport, not actor simulation.
- Recommended migration is staged: publish JSON-only state/delta and render the existing 600×600 scene in browser Canvas while keeping raster fallback; then choose Workers Static Assets + client-side JS/TS simulation for single-user use, or add a Durable Object authority/WebSocket only if multiple viewers must share one world clock. Do not move the current resident Python/Pillow server into a Worker as-is.
- Lean component renderer and browser-owned simulation (2026-09-03): the latest browser branch was fast-forwarded into `main` at `18f0436`; its lean parent is included in the same history. The merged slice adds the image-free headless/Canvas path plus deterministic browser simulation Tasks 1–4 while retaining Python/raster compatibility; canonical gameplay/assets/reference hashes are unchanged.
- Local feature worktrees and branches `codex/browser-simulation` and `codex/lean-component-renderer` were removed after merge. The only local branch/worktree remaining is `main`; `origin/main` remains untouched and `main` is ahead by 13 commits.
- Read-only lean audit (2026-09-03): canonical tracked source has no cloned code/image payloads beyond the exact duplicate `CHARACTER/BUILD_MANIFEST.json` / `CHARACTER/FINAL_MANIFEST.json` pair and empty package initializers. All 429 hashed world blobs are referenced; 458 registry entries intentionally resolve to those 429 shared blobs.
- Main retains the raster path as compatibility fallback while the merged browser path is still an exploration slice: after bootstrap it can advance image-free state locally, but browser persistence/replay hardening, no-request UI source-mode wiring and endurance/Cloudflare gates are not yet closed.

## Verification

- `python -B -m pytest -p no:cacheprovider -q` after the orientation correction → **377 passed in 411.33s**.
- `node --test TESTS/browser_runtime_test.mjs` → **10 passed**.
- Focused conversation, live-talk, bundle and browser-parity regression → **38 passed in 192.04s**.
- Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family and conversation audits → **PASS**.
- Runtime presentation QA (`TOOLS/render_runtime_presentation_qa.py`) → **PASS**; static assets and reference hashes unchanged.
- Fresh API long-run on `floor02` with the project server: simulated clock reached `137400ms`; 9 portal entries, 9 work-start bubbles, 6 observed WorkSeat entries, 0 lifecycle-boundary violations, and queue category telemetry present. The full noncompact stationary-overlay regression confirms work-loop/stamina progress for pending actors.
- `git diff --check` → **PASS**. No release package was created; release-clean packaging remains a separate operation.
- Conversation visual QA renderer (`python TOOLS/render_conversation_pair_gif.py`) → **PASS**; floor02 standing-pair manifest resolves `axis=V`, endpoints `[250,150]`/`[250,154]`, `EMP_W1_0031` → `SW` and `EMP_W1_0010` → `NE`.
- Review server: `http://127.0.0.1:8765/`, health HTTP 200, project process PID `6688`, intentionally left running for author review.
- Cloudflare spike used the existing healthy review server and in-memory/read-only probes; no duplicate development server was started, no canonical asset/reference hash was changed, and no release package was created.
- Workspace audit: `LOCAL_REVIEW/` is about `3.05GiB` (mostly generated GIF/PNG review runs), `releases/.staging/` is `185.67MiB` with 17 extracted candidates, and the two overlapping prototype worktrees total about `163.33MiB`; these are ignored/non-runtime artifacts. `WORLD/COMPILED_NAV/OCCUPANCY/` and `PREVIEW/` are absent.
- Current server observation: PID `6688` is the existing project review host on port `8765`; it was not started or stopped by this merge task. Port `8766` has no listener. Restart the existing review host before visual review if it must load the newly merged source from a fresh process.

## Acceptance gate

Engineering verification is complete for the merged raster/lean/browser slice. The author should review the Canvas/Raster page for visual parity, pixel-art sharpness, dialogue bubble appearance, walking depth, perceived smoothness and the existing full-system/Talk/Effects/Critical/save-load/replay behavior. Do not close the visual/gameplay gate until it is explicitly accepted.

**Next concrete task:** get explicit author visual/gameplay acceptance of the corrected standing-pair orientation on the review page. After that, resume Canvas/Raster acceptance, browser persistence/replay, zero-request UI mode, soak and Cloudflare decisions. Before packaging, trim duplicate telemetry/projection work and clean generated workspace artifacts through an explicit maintenance action.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
