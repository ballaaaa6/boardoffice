# GDS Central Game Core — Handoff

**Updated:** 2026-09-02 (Asia/Bangkok)
**Project root:** `D:\antigravity\board office`
**Status:** Phase 8E engineering scope complete; author visual/gameplay acceptance and final stamina tuning remain open. Realtime-web discovery is now explicitly host-first: make the local host lean before any Cloudflare/deployment work, while retaining the requirement for one shared world that continues while viewers are disconnected. No realtime implementation or release promotion was approved in this session.

## Completed in this session

- **Movement policy:** new actors leave a WorkSeat only for an authored Talk route or Home route. Automatic idle/wander selection is retired (`wander` weight 0); old snapshots are migrated without restarting a wander walk. Popup/background/HumanBall effects remain seated.
- **Seat lifecycle:** the existing navigation geometry and assets are unchanged. Seat exit/entry uses a JSON-safe presentation boundary, and Home/Critical finishes the current work loop before routing home and re-entering the seat.
- **Dialogue:** all 11 active in-work categories are used during normal work: `anticipation`, `work_progress`, `work_complete`, `encouragement`, `praise`, `celebration`, `disappointment`, `fatigue`, `surprise`, `uncertainty`, `idle_flavor`. The latest policy does not map the five result-like names to conversation outcomes; they are ordinary work chatter. Lifecycle lines are presentation-only and score/stamina-safe; only the existing Talk recovery and standing-pair `sad`/`happy` outcome can apply numeric effects.
- **Coverage/no-repeat:** enabled office lines are selected from persisted deterministic shuffle bags by locale/category, with used counts and recent rendered-text history. Lines are consumed before a bag refills and save/load/replay keeps the bag state.
- **Bubble policy:** BB5 remains excluded. BB1/BB2/BB3/BB4/BB6 are supported; the renderer chooses the smallest allowed shape that fits the actual line (with adaptive font fallback and no clipping/wrap). Current enabled office content renders successfully across all allowed shapes.
- **Web review:** `http://127.0.0.1:8765/` runs API v2 with the normal **Full system demo**, deterministic Critical demo, Talk/Effects controls, actor/event telemetry, and a dialogue-coverage panel showing bag generation, pool and usage. There is no automatic Wander control.
- **Realtime delivery investigation:** the existing `gds.runtime_presentation_snapshot.v1` is already a JSON-safe renderer seam. Local measurement on floor02 showed a 600x600 compact raster response around 136KB JSON (WebP data URL about 122KB), versus a full presentation snapshot around 11.4KB raw / 1.2KB gzip and a typical recursive delta around 0.5KB raw / 0.26KB gzip. The current Python host spends roughly 4–7ms on advance+render and 8–10ms on WebP encode per tick in the warmed benchmark.
- **Host-first bottleneck finding:** the current `/api/tick` path still advances the shared snapshot and renders/encodes a new full image inside the client request. `compact=true` removes the full runtime JSON but does not remove the roughly 122KB image data URL; the browser has one in-flight fetch and waits for response/decode before swapping frames. There is no independent background clock, so a disconnected browser stops progress and multiple viewers multiply request-driven work.
- **Shared-world requirement:** the author confirmed that all viewers must see one identical world and that the simulation must continue while no browser is connected. `CentralGameCore.resolve_runtime_snapshot(None)` already composes all **219 actors / 25 floors**; the warmed no-event reducer step measured about **4.7ms**, while an event-rich 60-second catch-up probe measured about **15.1s**, so the future authority must run continuously and avoid image rendering when there are no subscribers. Long offline catch-up needs its own bounded/recovery design.

## Evidence

- `python -m pytest -q` → **326 passed**.
- Required audits pass: Room Navigation, Navigation Occupancy, WorkSeat, WorkSeat lifecycle, Phase 6 Spatial, Central integrity, gameplay-metadata family, and conversation.
- All-floor smoke: **25 floors / 219 assigned actors**, zero automatic wander choices; dialogue catalog reload: **2,009 rows / 1,873 enabled rows** (1,872 office + legacy test); all enabled office rows fit the renderer.
- Browser smoke after restart: decoded frame buffers, live clock advancing, Talk bubble visible and returning to work, no warning/error console entries. Project server is intentionally left running on port 8765 (PID 2772).

## Acceptance gate / next task

The next task remains the author’s browser pass for Phase 8E. The realtime-web proposal must first receive explicit approval for the host-first optimization, then the shared-world authority, persistence and browser-rendering design. After approval, prepare a separate design/spec before implementation; only then, and after the Phase 8E visual gate, rebuild and freshly extract a clean release archive.

**Active handoff:** this file only. `ROADMAP.md` is the single active milestone plan.
