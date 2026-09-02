# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`
**Source of truth:** unpacked project root
**Updated:** 2026-09-02 (Asia/Bangkok)

## Completed milestone — Phase 8E runtime review

The implementation slice, required verification, browser review and author acceptance are complete. Static floor geometry, workstation ownership, character artwork and reference assets remain unchanged. Phase 8E is closed; no implementation gate remains. The rejected host-first realtime experiment was deleted and is not part of this milestone.

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

No implementation task or blocker remains for Phase 8E. The host-first realtime design documents remain non-active reference material after the experimental branch was deleted.
