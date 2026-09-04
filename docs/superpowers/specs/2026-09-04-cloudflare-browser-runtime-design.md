# Cloudflare Browser Runtime Design

**Date:** 2026-09-04 (Asia/Bangkok)
**Status:** Approved scope for planning; implementation has not started.

## Goal

Deploy the web runtime as Cloudflare-served static assets where the browser
owns the single-user simulation after one bootstrap load. Normal animation and
simulation must not send recurring `/api/tick` requests.

## Current finding

The current page is still Python-hosted:

```text
runtime_review.html
  -> /api/live-start, /api/state, /api/tick, /api/save, /api/load, /api/replay
  -> TOOLS/runtime_review_server.py
  -> RUNTIME/central_core.py and Pillow/jsonschema runtime
```

The repository already contains a browser-owned JavaScript core:

```text
runtime_simulation_bootstrap.json (one-time fetch)
  -> BrowserRuntimeCore
  -> gds.runtime_snapshot.v1
  -> gds.runtime_render_state.v1
  -> RuntimeCanvasRenderer + runtime_render_manifest.json/assets
```

`BrowserRuntimeCore` is currently exercised by Node parity tests and supports
fixed stepping, navigation, WorkSeat, actor behavior, speech/conversation,
effects/HumanBall, persistence and replay. `RuntimeRenderClient` is the old
Python-hosted Canvas polling adapter and must not be used by the production
browser path.

## Target boundary

- `WORLD/`, `CHARACTER/` and `CONTRACTS/` remain canonical source data.
- Python remains the offline bundle/manifest builder, parity oracle, audit
  toolchain and local raster fallback.
- The deployed runtime consists of HTML, ES modules, generated JSON and PNG
  assets; it contains no Python, Pillow, filesystem access or API dependency.
- The first deployment target is the existing deterministic `floor02` bundle
  with nine actors. All-floor support is a separate expansion using one static
  bundle/manifest per floor or a deliberately larger combined bundle.
- “Zero request” means zero recurring simulation/API requests after startup.
  The page may still make one-time requests for the HTML, JS modules, bundle,
  manifest and static PNG assets.
- This is a behavior-preserving port and packaging change, not a gameplay,
  geometry, asset or multiplayer change.

## Cloudflare choice

Use Cloudflare Workers Static Assets for the first deployment. The Worker
needs no simulation handler; Wrangler serves the built `dist/` directory as
static assets. A Pages deployment is also compatible, but the repository will
standardize on one `wrangler.jsonc`/`dist` contract so local build and deploy
verification are identical.

## Non-goals

- Translating every Python module, validator, renderer or QA script to
  TypeScript.
- Running Python, Pyodide or Pillow in the browser or on a Worker.
- Shared server authority, Durable Objects, WebSockets or multiplayer state.
- Removing Python fallback/oracle before parity, network, endurance and author
  visual acceptance gates are green.

## Acceptance gates

1. A clean static build contains only deployable HTML/JS/JSON/PNG assets and
   no Python or local absolute paths.
2. Browser boot succeeds from the static directory with exactly one bootstrap
   fetch and one manifest fetch; simulation frames use local `step()` calls.
3. A network test observes zero `/api/*` and zero `/api/tick` requests during a
   long live run; image requests are static asset loads only.
4. Existing Python suite, required audits, Node browser tests and Python/JS
   differential traces remain green.
5. Save/load/replay, manual stepping, Talk/Effects/Critical review paths that
   remain in the deployed UI work locally without a server.
6. `wrangler deploy --dry-run` succeeds, and a fresh static extraction serves
   the same entrypoint and generated assets.
7. Author visual/gameplay acceptance is recorded separately from engineering
   test results.
