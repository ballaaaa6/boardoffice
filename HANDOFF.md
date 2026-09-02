# GDS Central Game Core — Handoff

**Updated:** 2026-09-02 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** The live multi-actor conversation-runtime follow-up is implemented and engineering-verified. Visual/gameplay acceptance remains **acceptance-pending** for the author.

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

## Verification

- `python -m pytest -q` → **348 passed in 250.10s**.
- Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family and conversation audits → **PASS**.
- Runtime presentation QA (`TOOLS/render_runtime_presentation_qa.py`) → **PASS**; static assets and reference hashes unchanged.
- Fresh API long-run on `floor02` with the project server: simulated clock reached `137400ms`; 9 portal entries, 9 work-start bubbles, 6 observed WorkSeat entries, 0 lifecycle-boundary violations, and queue category telemetry present. The full noncompact stationary-overlay regression confirms work-loop/stamina progress for pending actors.
- `git diff --check` → **PASS**. No release package was created; release-clean packaging remains a separate operation.
- Review server: `http://127.0.0.1:8765/`, health HTTP 200, project process PID `6688`, intentionally left running for author review.

## Acceptance gate

Engineering verification is complete. The author should refresh/open the live review page and check the full system run, greeting/start-work bubbles, multi-actor queue telemetry, stationary work animation, standing-pair facing/offsets/d6 outcome, and return-to-work behavior. Do not close the visual/gameplay gate until that review is explicitly accepted.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
