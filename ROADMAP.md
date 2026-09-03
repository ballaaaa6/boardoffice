# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`
**Source of truth:** unpacked project root
**Updated:** 2026-09-03 (Asia/Bangkok)

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

The original Phase 8E gate is closed. The rejected host-first realtime experiment and its non-active design documents have been removed; the active browser-owned simulation work remains tracked separately below.

## Post-close conversation-runtime correction — 2026-09-02

The previously approved correction is implemented and verified; visual/gameplay acceptance is **acceptance-pending** until the author reviews the live page.

- [x] Carry planned standing-pair endpoint facings through Central into the actor `talk_hold` pose: the original 2026-09-02 U-axis mapping was later superseded by the V-axis orientation correction below.
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

## Standing-pair orientation correction — 2026-09-03

The attached reference requires the standing pair to occupy the V axis: equal `u`, four-cell `v` separation, with the upper-right/lower-`v` actor facing `SW` and the lower-left/higher-`v` actor facing `NE`. Engineering verification is complete; visual/gameplay acceptance remains a separate author gate.

- [x] Change the conversation contract/schema to prefer V, fall back to U, and order endpoints by ascending `v`.
- [x] Make the resolver default read the contract instead of hardcoding U; keep the authored `SW`/`NE` endpoint-facing order.
- [x] Regenerate the deterministic browser bundle and add core/live-route/browser geometry assertions.
- [x] Align browser transition rounding and persistent-bubble fade sampling with the Python parity oracle exposed by the V-axis route.
- [x] Verify with full pytest **377 passed**, browser unit tests **10 passed**, focused conversation/browser regression **38 passed**, required navigation/occupancy/WorkSeat/Phase 6/Central/F2/conversation audits **PASS**, and conversation visual QA **PASS**.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8765/`.

## Lean component-renderer prototype — 2026-09-03

The merged `main` history now contains the engineering-verified headless JSON + browser Canvas prototype. The raster compatibility path remains available until the author accepts the Canvas behavior.

- [x] Add a metadata-only `gds.runtime_render_state.v1` projection and headless loop without materializing Pillow frames.
- [x] Preserve the Python/Pillow raster path as the explicit compatibility fallback.
- [x] Build the deterministic `floor02` static/component manifest and Canvas renderer with 100ms polling plus RAF composition/interpolation.
- [x] Verify parity across spawn/work, Talk, Effects/HumanBall and Critical traces, plus no-Pillow Canvas requests.
- [x] Measure Canvas p50 request `1.13ms` versus raster `10.63ms`, payload `23.7KB` versus `136.4KB`, and `82.63%` payload reduction.
- [ ] Author visual/gameplay acceptance for Canvas/Raster parity, pixel sharpness, dialogue bubbles, walking depth and perceived smoothness.
- [x] Merge the derived lean renderer history into `main` while retaining raster fallback and canonical asset/hash contracts.
- [ ] After acceptance, trim duplicate canvas telemetry/projection work, publish the derived bundle, and choose the Cloudflare authority model.

The prototype is intentionally not yet a closed production milestone: it is limited to `floor02`, retains two presentation implementations for fallback/parity, and carries generated derived browser assets that should be treated as build/deployment output rather than new gameplay source.

## Browser-owned simulation slice — 2026-09-03

The latest browser-owned simulation work is now merged into `main` at `18f0436`. After one bootstrap load, a single-user browser can advance deterministic runtime state locally and use the existing Canvas component renderer. The Python runtime remains the canonical oracle and local fallback. Tasks 1–4 are engineering-complete; persistence/replay hardening, UI source-mode integration and endurance/Cloudflare gates remain open.

- [x] Export and validate the deterministic `floor02` browser bootstrap bundle and Python parity traces.
- [x] Add deterministic browser PRNG/state/clock primitives, a no-DOM core shell and stdin parity checkpoint.
- [x] Port bundle-backed navigation, actor movement/action clocks and WorkSeat ownership with spawn/work and home-route parity.
- [x] Port speech/dialogue, standing-pair conversation, effects, HumanBall, stamina/lifecycle and critical-home boundaries with focused parity traces.
- [ ] Harden browser save/load/replay behavior with an explicit versioned package and exact replay parity.
- [ ] Integrate Browser source mode with zero periodic `/api/tick` calls while preserving Python Canvas/Raster fallback.
- [ ] Pass simulated 24-hour, real browser soak, author visual/gameplay and release-clean gates.
- [ ] Decide the separate Cloudflare static deployment/persistence or shared Durable Object/WebSocket slice.

## Lean-first cleanup prerequisite — 2026-09-03

Before starting the production TypeScript/JavaScript migration, the current runtime must be made lean and contract-stable. The detailed execution plan is `docs/superpowers/plans/2026-09-03-lean-first-tsjs-migration.md`. This prerequisite does not change the current Python oracle, canonical assets or raster fallback.

- [x] Establish a reproducible lean audit and clear the reviewed Ruff unused-import/unused-local findings.
- [ ] Consolidate repeated QA/build/validation helpers and centralize source-hash profiles without changing output hashes.
- [ ] Reduce the duplicate runtime presentation/projection path to one neutral frame per simulation slice.
- [ ] Split high-responsibility runtime façades behind compatibility-preserving interfaces.
- [ ] Retire legacy crowd/action/wander/depth seams only after caller inventories and replay migration tests prove they are unused.
- [ ] Freeze the browser bundle/snapshot/render-state contracts and verify one bootstrap request with zero periodic `/api/tick` calls before handing off to the TS/JS migration.

The standing-pair visual/gameplay acceptance, Canvas/Raster acceptance, browser persistence/replay, endurance and Cloudflare gates remain separate and must not be marked closed by the lean audit alone.

Track A engineering checkpoint (2026-09-03): the audit/hygiene gate is green, proven preview/POC debris and generated workspace output were removed, and the canonical duplicate manifest was collapsed to `CHARACTER/FINAL_MANIFEST.json`. Remaining duplicate function-body groups are retained as domain/test candidates until a semantics-preserving boundary is approved; source-hash profiles and the later runtime tracks remain open.

## Combined visual selection and per-actor bubble correction — 2026-09-03 (engineering complete)

The asset/rendering inventory and BB root-cause audit are complete. The written design spec is `docs/superpowers/specs/2026-09-03-visual-selection-bubble-concurrency-design.md` (committed as `b7d03b9`) and is author-approved. The execution plan is `docs/superpowers/plans/2026-09-03-visual-selection-bubble-concurrency.md` (committed as `9c11ef0`). Implementation and engineering verification are complete; author visual/gameplay acceptance remains a separate gate.

- [x] Replace hash-modulo VFX selection with deterministic per-actor/per-channel shuffle bags covering all 11 canonical VFX IDs.
- [x] Keep all 6 canonical HumanBall popup IDs in a deterministic per-actor popup shuffle bag with no repeat before refill.
- [x] Replace floor-wide bubble serialization with one bubble slot per actor; allow different actors on the same floor to show bubbles concurrently.
- [x] Keep same-actor exclusion, atomic participant locks for pair sessions and physical talk-spot/path/crowd collision protection.
- [x] Mirror the scheduler and visual-bag algorithms in Browser JS with exact Python parity, compact save/load state and one-bootstrap/no-per-event-request behavior.
- [x] Add same-floor concurrency, VFX/popup coverage, legacy migration, replay/parity and full regression gates before TS/JS migration.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8765/`.

Engineering evidence: full Python suite **403 passed**, browser unit suite **14 passed**, focused conversation/browser regression suite **48 passed**, compile/Ruff/diff checks passed, required runtime audits passed, and the live page showed simultaneous VFX/HumanBall channels plus two actor-owned BBs. This section does not close the existing Canvas/Raster, browser persistence, endurance or Cloudflare gates.

## Walking visitor bubble lift follow-up — 2026-09-03

The author-approved behavior correction is implemented and regenerated into the browser bundle. Engineering verification is complete; visual/gameplay acceptance remains a separate pending gate.

- [x] Add the contract/schema field for the visitor extra `[0, -20]` offset.
- [x] Apply the extra offset only to the walking visitor in `seated_host` and `ceo_front`, producing actual `-40px` total height while leaving the seated host at normal `-20px`.
- [x] Regenerate the `floor02` browser bundle and verify all **11 VFX** and **6 HumanBall** IDs remain present.
- [x] Add Python/browser bundle regressions; full Python suite **403 passed**, focused conversation/browser suite **48 passed**, browser unit suite **14 passed**.
- [ ] Author visual/gameplay acceptance at `http://127.0.0.1:8765/` before push.

## Integration checkpoint — 2026-09-03

- [x] Fast-forward merge of the latest browser-owned simulation work into `main` at `18f0436`.
- [x] Remove the merged local feature worktrees and branches; retain only `main` locally and leave `origin/main` unchanged.
- [x] Run merged verification: full Python suite **377 passed**, browser runtime **10 passed**, browser parity **8 passed**, focused renderer/server/web/benchmark/bundle suite **62 passed**.
- [ ] Author visual/gameplay acceptance and complete browser persistence/replay, zero-request UI source mode, soak and Cloudflare gates.
