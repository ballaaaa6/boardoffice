# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`
**Source of truth:** unpacked project root
**Updated:** 2026-09-02 (Asia/Bangkok)

## Completed milestone — Phase 8E runtime review

The implementation slice, required verification and original browser review were completed, and the baseline author acceptance remains recorded. Static floor geometry, workstation ownership, character artwork and reference assets remain unchanged. Phase 8E baseline is closed; a later live multi-actor follow-up blocker is recorded below. The rejected host-first realtime experiment was deleted and is not part of this milestone.

### Engineering scope complete

- [x] Restrict out-of-seat behavior to authored Talk or Home; retire automatic idle/wander and migrate stale snapshots.
- [x] Preserve the WorkSeat exit/entry presentation boundary and finish-current-work-loop behavior for Critical/Home.
- [x] Keep popup/background/HumanBall effects seated and preserve Work/PC animation clocks.
- [x] Rotate all 11 in-work dialogue categories through persisted locale/category shuffle bags with no visible repetition until refill.
- [x] Treat `encouragement`, `praise`, `celebration`, `disappointment` and `fatigue` as ordinary work dialogue; do not attach them to conversation result status.
- [x] Keep lifecycle speech score/stamina-safe; retain only Talk recovery and standing-pair `sad`/`happy` numeric effects.
- [x] Use every enabled office line through the bag; enabled catalog rows are render-fit and observable in telemetry.
- [x] Select the smallest fitting allowed bubble from BB1/BB2/BB3/BB4/BB6; exclude BB5 and reject overflow.
- [x] Expose dialogue id/category/locale/bubble/bag coverage in API v2 and the web review panel.
- [x] Add focused regression, persistence/replay, catalog-fit and no-wander coverage plus the all-floor audit matrix.

### Verification evidence

- `python -m pytest -q` → **326 passed**.
- Required Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central, gameplay-metadata family and conversation audits → **PASS**.
- All-floor probe → **25 floors / 219 actors**, zero automatic wander choices.
- Dialogue reload → **2,009 rows / 1,873 enabled rows**; all enabled office rows render; BB1/2/3/4/6 all observed.
- Browser host → `http://127.0.0.1:8765/`, API v2, normal Full system demo plus Talk/Effects/Critical controls, no console warning/error in smoke.

### Closeout

1. Author visual/gameplay acceptance: **APPROVED — 2026-09-02**.
2. Final stamina/Thai-content tuning: **APPROVED — 2026-09-02**.
3. Phase 8E implementation and verification gate: **CLOSED**.

The original Phase 8E gate is closed. The host-first realtime design documents remain non-active reference material after the experimental branch was deleted.

## Post-close conversation-runtime correction — 2026-09-02

The previously approved correction is implemented and verified; visual/gameplay acceptance is **acceptance-pending** until the author reviews the live page.

- [x] Carry planned standing-pair endpoint facings through Central into the actor `talk_hold` pose: lower `u` → `SW`, higher `u` → `NE`.
- [x] Keep the opener bubble at the explicit extra `[0, -20]` offset and the reply at `[0, 0]`.
- [x] Use one persisted replayable d6 per standing pair with even → `happy` and odd → `sad`.
- [x] Make the review demo completion gate wait for every participant to finish `seat_entry` and expose `work_seat/work/normal_work`.
- [x] Fix the newly diagnosed seated in-work BB frame stall: keep the normal-work clock advancing while the bubble is an overlay, preserve routed talk behavior, and add active/post-return frame regression coverage. Engineering verification completed with the actor-clock, stationary-host and routed-return regressions.
- [x] Verify with `337 passed`, the required navigation/WorkSeat/Phase 6/Central/F2/conversation audits, runtime-presentation QA, and a fresh browser run on port `8765`.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8765/`.

The engineering gate for the non-blocking speech overlay is closed. The page was rechecked on 2026-09-02: active BB frames continue to change while stamina/work time advances, routed talks retain their movement/facing contract, and both participants return to `work/normal_work`. Author acceptance remains a separate pending gate.

## Live multi-actor follow-up correction — 2026-09-02

The long-running full live trace exposed a pending-talk/lifecycle ownership seam. The correction is now implemented, regression-covered and stress-verified. Engineering follow-up is closed; visual/gameplay acceptance remains a separate author gate.

- [x] Prevent actor-side `talk_pending` from freezing the normal-work frame/stamina when the floor speech lane is occupied; define explicit accept, cancel and timeout ownership.
- [x] Keep the queued speech request's category and identity, and prevent an unrelated lifecycle session completion from clearing a still-valid actor talk request.
- [x] Arm greeting and start-work timers at the intended spawn/work-session boundaries instead of initializing the review runtime with both already emitted and relying only on later return events.
- [x] Prevent `_arm_live_behavior_timers()` from scheduling a new weighted event while a stationary talk overlay owns the actor.
- [x] Add multi-actor long-run and noncompact runtime regressions, queue telemetry, and a fresh API/browser stress run; rerun `python -m pytest -q` plus the required navigation/WorkSeat/Phase 6/Central/F2/conversation audits.

Engineering verification result: **348 tests passed**, all required audits and runtime presentation QA passed, and the fresh `floor02` API run reached `137400ms` with 9 work-start bubbles and 0 lifecycle-boundary violations. Author visual/gameplay acceptance at `http://127.0.0.1:8765/` is still pending.

## Lean component-renderer prototype — 2026-09-03

This isolated prototype keeps the existing Python simulation and raster review
fallback, while adding an image-free `floor02` render-state contract and a
browser Canvas compositor. It is ready for author review before any Cloudflare
deployment work begins.

- [x] Define and implement the renderer-neutral `gds.runtime_render_state.v1` protocol without changing gameplay, navigation, WorkSeat or canonical assets.
- [x] Add explicit `renderer=canvas` API responses with no `image_data_url`; retain `renderer=raster` as the default compatibility path.
- [x] Build the deterministic 600×600 `floor02` static/component manifest and 181 derived browser assets without editing source registries.
- [x] Add Canvas static caching, pixel-art component composition, walking occluder masks, interpolation, dialogue overlays and 100ms polling with RAF rendering.
- [x] Verify Canvas and Raster in the local review page across Full, Talk, Effects, Critical, Save/Load and Replay flows.
- [x] Benchmark: Canvas payload p50 **23.7KB** vs Raster **136.4KB** (−**82.63%**); server call p50 **1.13ms** vs **10.63ms** (−**89.34%**); lean encode **0ms**.
- [x] Engineering verification: **364 tests passed**, parity/no-Pillow guards passed, required navigation/world/WorkSeat/Phase 6/Central/F2/gameplay audits passed, and raster presentation QA passed.
- [ ] Author visual acceptance of the Canvas output and smoothness on the reference machine.
- [ ] Cloudflare slice: move the same metadata contract behind Worker/Durable Object and publish static component assets after author acceptance.

## Browser-owned simulation exploration — 2026-09-03

This branch explores the next optimization: after one bootstrap load, a
single-user browser advances the runtime locally and uses the existing Canvas
component renderer. The Python runtime remains the canonical oracle and local
fallback. This is a design/planning gate; no browser simulation code is marked
complete yet.

- [x] Create isolated branch `codex/browser-simulation` from the verified lean renderer branch.
- [x] Write `docs/superpowers/specs/2026-09-03-browser-owned-simulation-design.md` with the browser authority boundary, alternatives, parity contract, persistence, timing and 24-hour gates.
- [x] Write `docs/superpowers/plans/2026-09-03-browser-owned-simulation.md` with bundle export, deterministic JS runtime, behavior-port, persistence, no-request UI, parity and endurance tasks.
- [ ] Author review and approval of the browser-owned simulation design/plan.
- [ ] Export and validate the deterministic `floor02` browser bootstrap bundle and Python parity traces.
- [ ] Port navigation, actor, WorkSeat, speech, dialogue, effects, stamina, save/load and replay behavior with exact trace parity.
- [ ] Integrate Browser source mode with zero periodic `/api/tick` calls while preserving Python Canvas/Raster fallback.
- [ ] Pass simulated 24-hour, real browser soak, author visual/gameplay and release-clean gates.
- [ ] Decide the separate Cloudflare static deployment/persistence or shared Durable Object/WebSocket slice.
