# GDS Central Game Core — Handoff

**Updated:** 2026-09-02 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Phase 8E engineering scope complete; author visual/gameplay acceptance and final stamina tuning remain open. No release archive has been promoted.

## Completed in this session

- **Movement policy:** new actors leave a WorkSeat only for an authored Talk route or Home route. Automatic idle/wander selection is retired (`wander` weight 0); old snapshots are migrated without restarting a wander walk. Popup/background/HumanBall effects remain seated.
- **Seat lifecycle:** the existing navigation geometry and assets are unchanged. Seat exit/entry uses a JSON-safe presentation boundary, and Home/Critical finishes the current work loop before routing home and re-entering the seat.
- **Dialogue:** all 11 active in-work categories are used during normal work: `anticipation`, `work_progress`, `work_complete`, `encouragement`, `praise`, `celebration`, `disappointment`, `fatigue`, `surprise`, `uncertainty`, `idle_flavor`. The latest policy does not map the five result-like names to conversation outcomes; they are ordinary work chatter. Lifecycle lines are presentation-only and score/stamina-safe; only the existing Talk recovery and standing-pair `sad`/`happy` outcome can apply numeric effects.
- **Coverage/no-repeat:** enabled office lines are selected from persisted deterministic shuffle bags by locale/category, with used counts and recent rendered-text history. Lines are consumed before a bag refills and save/load/replay keeps the bag state.
- **Bubble policy:** BB5 remains excluded. BB1/BB2/BB3/BB4/BB6 are supported; the renderer chooses the smallest allowed shape that fits the actual line (with adaptive font fallback and no clipping/wrap). Current enabled office content renders successfully across all allowed shapes.
- **Web review:** `http://127.0.0.1:8765/` runs API v2 with the normal **Full system demo**, deterministic Critical demo, Talk/Effects controls, actor/event telemetry, and a dialogue-coverage panel showing bag generation, pool and usage. There is no automatic Wander control.

## Evidence

- `python -m pytest -q` → **326 passed**.
- Required audits pass: Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family, and conversation.
- All-floor smoke: **25 floors / 219 assigned actors**, zero automatic wander choices; dialogue catalog reload: **2,009 rows / 1,873 enabled rows** (1,872 office + legacy test); all enabled office rows fit the renderer.
- Browser smoke after restart: decoded frame buffers, live clock advancing, Talk bubble visible and returning to work, no warning/error console entries. Project server is intentionally left running on port 8765 (PID 2772).

## Acceptance gate / next task

The next task is the author’s one browser pass: inspect spawn → walk to seat → normal work/PC/VFX → Talk → return → Critical/Home → re-entry, then approve or request targeted visual/Thai/stamina tuning. After approval, rebuild and freshly extract a clean release archive; do not close Phase 8E before that visual gate.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
