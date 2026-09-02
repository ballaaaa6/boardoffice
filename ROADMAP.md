# GDS Central Game Core — Living Roadmap

**Project root:** `D:\antigravity\board office`
**Source of truth:** unpacked project root
**Updated:** 2026-09-02 (Asia/Bangkok)

## Current milestone — Phase 8E runtime review

The implementation slice is complete. Static floor geometry, workstation ownership, character artwork and reference assets remain unchanged. The only open gate is author visual/gameplay acceptance followed by final stamina/Thai-content tuning and a clean release rebuild.

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

### Open acceptance gate

1. Author checks the live browser sequence: spawn → walk to WorkSeat → normal work/PC/VFX → Talk and return → Critical/Home and seat re-entry.
2. Author approves or requests targeted visual smoothness, Thai wording and drain/recovery tuning changes.
3. Only after approval, rebuild/fresh-extract the release archive, require `release_clean=true`, and then close Phase 8E.

No release promotion, commit or push is part of this milestone until the author explicitly approves the browser/gameplay gate.
