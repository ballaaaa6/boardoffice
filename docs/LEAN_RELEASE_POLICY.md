# Lean Release Policy — v1.8.4

## Purpose

The canonical Core must carry the minimum authoritative data needed to reproduce gameplay behavior. Generated review material and data that can be deterministically rebuilt from canonical registries are not source-of-truth.

## Canonical payload

Keep:

- `CENTRAL_MANIFEST.json`
- `CHARACTER/` canonical assets, metadata, registries, and runtime
- `WORLD/` canonical shared assets, registries, runtime, and the three canonical Room masks
- `RUNTIME/`
- `CONTRACTS/`
- `SCHEMA/`
- runtime dependency metadata such as `requirements.txt`
- the inactive legacy archive pointer

## Generated / optional payload

Do not require or package as canonical payload:

- `PREVIEW/`
- `LOCAL_REVIEW/`
- generated GIFs, review sheets, debug overlays, acceptance screenshots
- `WORLD/COMPILED_NAV/OCCUPANCY/`
- other per-floor outputs that can be deterministically derived from canonical registries

`REPORTS/`, `TESTS/`, `TOOLS/`, `VALIDATION/`, `DOCS/`, and `HANDOFF.md` are small development/support material. They may ship for maintainability but are excluded from the canonical payload checksum scope.

## Navigation cache contract

`NavigationOccupancyCore` follows this rule:

1. If an optional per-floor occupancy JSON cache exists, load it.
2. If it does not exist, call `compile_floor(floor_id)` using canonical Room Domain, Portal, Layout, Ground Footprint, and placement data.
3. Cache the result in memory for subsequent queries.
4. Never treat the optional disk cache as source-of-truth.

The canonical v1.8.4 release intentionally ships with zero materialized per-floor occupancy cache files.

## Image/review contract

All visual review outputs must use real project assets with deterministic compositing/crop/mirror/overlay operations. Image-generation models must not be used for project visual output.

## Packaging gate

Before declaring a canonical release:

```text
PREVIEW/                              must be absent
LOCAL_REVIEW/                         local-only; excluded from release archive
WORLD/COMPILED_NAV/OCCUPANCY/        must be absent
pytest                               must pass on a fresh extraction
navigation occupancy audit           must pass without disk cache
canonical checksums                  must pass
```
