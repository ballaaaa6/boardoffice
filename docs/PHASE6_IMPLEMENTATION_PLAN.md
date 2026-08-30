# Phase 6 Spatial Object Metadata Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-backed spatial metadata for chair, desk, pc, and reception to the Phase 5 Central Core without changing any character rendering, floor rendering, workstation direction, or existing canonical assets.

**Architecture:** Keep the system lean by storing one deterministic spatial profile per used visual variant rather than materializing per-floor object records. Runtime `SpatialCore` derives an object instance from existing `layout + skin + variant + direction` data, exposing measured alpha bounds, render/world visual bounds, known workstation relationships, and existing reception semantic anchors. Unknown collision, footprint, solidity, and interaction-anchor fields remain explicit `null` values.

**Tech Stack:** Python 3, Pillow, JSON/JSON Schema, pytest-style regression tests, deterministic ZIP packaging.

**Spec:** `/mnt/data/docs/superpowers/specs/2026-08-28-gds-central-core-design.md` plus the approved Phase 6 scope in the project conversation: only chair + desk + pc + reception; no speculative physics/navigation data.

## Global Constraints

- Base package is `GDS_CENTRAL_GAME_CORE_v1.0.0.zip`.
- Phase 6 release version is `GDS_CENTRAL_GAME_CORE_v1.1.0`.
- Primary spatial object types are exactly `chair`, `desk`, `pc`, `reception`.
- `chair_sub` is not a primary spatial object; it may appear only as a proven foreground render-fragment relationship of a chair/workstation.
- Existing Character, Identity, World asset/variant/layout/skin/floor/direction payloads must remain byte-identical unless a Phase 6 integration manifest/runtime file intentionally changes.
- No collision shape, solid flag, footprint, seat anchor, interaction radius, navigation grid, or pathfinding value may be guessed. Unknown values must be `null`.
- Visual bounds must be measured deterministically from the alpha channel of the rendered visual variant after its transform.
- Floor assembly must remain 25/25 exact against Phase 5 reference hashes.
- Workstation direction resolution must remain 219/219.
- No materialized floor or character frame cache may be added.

---

### Task 1: Freeze Phase 5 baseline and write failing spatial-profile tests

**Files:**
- Create: `/mnt/data/_phase6_work/tests/test_spatial_profiles.py`
- Create: `/mnt/data/_phase6_work/tests/test_spatial_runtime.py`

**Interfaces:**
- Consumes: Phase 5 registries under `WORLD/REGISTRY` and `WORLD/RUNTIME/layout_core.py`.
- Produces test contracts requiring `WORLD/REGISTRY/spatial_profiles.json` and `WORLD/RUNTIME/spatial_core.py`.

- [ ] **Step 1:** Test that the profile registry exists, scopes exactly the four approved object types, and has one profile for every visual variant actually used by those object types.
- [ ] **Step 2:** Test alpha bounding boxes by loading each variant through the existing `LayoutCore.load_variant()` and comparing `Image.getbbox()` against the profile.
- [ ] **Step 3:** Test that each profile carries explicit unknown placeholders: `physics.solid=null`, `physics.collision_shape=null`, `spatial.footprint=null`, `interaction.anchor=null`.
- [ ] **Step 4:** Run tests and confirm RED because Phase 6 files do not yet exist.

### Task 2: Build deterministic spatial profiles

**Files:**
- Create: `WORLD/REGISTRY/spatial_profiles.json`
- Create: `TOOLS/build_spatial_profiles.py`
- Create: `SCHEMA/WORLD/spatial_profiles.schema.json`

**Interfaces:**
- Consumes: `world_assets.json`, `visual_variants.json`, resolved placements from `LayoutCore`.
- Produces: `spatial_profiles.json` keyed by `variant_id`.

- [ ] **Step 1:** Collect only variants used by `chair`, `desk`, `pc`, `reception` placements across all 25 floors.
- [ ] **Step 2:** Render each variant using the canonical transform and measure canvas size, alpha bbox, visible size, and transparent padding.
- [ ] **Step 3:** Record evidence method `alpha_bbox_from_canonical_variant_pixels` and leave speculative fields null.
- [ ] **Step 4:** Write JSON with sorted keys and deterministic formatting.
- [ ] **Step 5:** Run profile tests and confirm GREEN.

### Task 3: Add runtime-derived spatial object records

**Files:**
- Create: `WORLD/RUNTIME/spatial_core.py`
- Modify: `RUNTIME/central_core.py`

**Interfaces:**
- Consumes: existing `LayoutCore`, `DirectionCore`, `spatial_profiles.json`.
- Produces: `SpatialCore.resolve_object()`, `SpatialCore.list_objects()`, `SpatialCore.resolve_workstation_spatial()` and Central Core facade methods.

- [ ] **Step 1:** Add runtime test for `floor36.ws7_desk`: object type desk, workstation `ws7`, component role desk, direction NW, known render coordinate, measured visual world bounds, and all speculative fields null.
- [ ] **Step 2:** Add reception test for `floor03.reception`: semantic Y anchor 355, legacy render Y 330, and world visible-top Y 355.
- [ ] **Step 3:** Add `floor01.reception` test showing no invented shared semantic anchor; retain render-position/visual-bounds evidence only.
- [ ] **Step 4:** Add chair relationship test showing `floor02.ws3_chair_main` is in workstation `ws3` and points to optional `ws3_chair_sub` as a proven `foreground_fragment` relationship without promoting chair_sub to a primary spatial object.
- [ ] **Step 5:** Implement minimal runtime derivation and Central facade methods.
- [ ] **Step 6:** Run runtime tests and confirm GREEN.

### Task 4: Add spatial contract and release metadata

**Files:**
- Create: `CONTRACTS/spatial_object_contract.json`
- Modify: `CONTRACTS/central_contract.json`
- Modify: `CENTRAL_MANIFEST.json`
- Create: `DOCS/PHASE6_SPATIAL_METADATA.md`

**Interfaces:**
- Consumes: approved Phase 6 scope and runtime behavior.
- Produces: stable contract for future Phase 6 object-type extensions and Phase 7 consumers.

- [ ] **Step 1:** Declare render coordinate versus semantic/world coordinate semantics.
- [ ] **Step 2:** Declare primary scope and the `chair_sub` foreground-fragment exception.
- [ ] **Step 3:** Declare null policy for unknown physics/interaction/navigation fields.
- [ ] **Step 4:** Bump package version to 1.1.0 and mark Phase 6 metadata included while Phase 7 remains excluded.

### Task 5: Regression and standalone validation

**Files:**
- Create: `VALIDATION/self_audit_phase6.py`
- Create: `REPORTS/PHASE6_SPATIAL_AUDIT.json`
- Update: `checksums.sha256`

**Interfaces:**
- Consumes: full Central Core package.
- Produces: standalone proof that Phase 6 added metadata without changing Phase 5 behavior.

- [ ] **Step 1:** Verify existing Character payload hashes against Phase 5 reference data.
- [ ] **Step 2:** Verify existing World registries/assets that are not Phase 6 files remain byte-identical to Phase 5.
- [ ] **Step 3:** Verify all 25 floors render to the frozen Phase 5 RGBA/PNG reference hashes.
- [ ] **Step 4:** Verify 219 workstation directions still resolve and Character work bridge remains compatible.
- [ ] **Step 5:** Verify spatial-profile coverage, schema validity, null policy, reception semantic-anchor invariants, and foreground-fragment relationships.
- [ ] **Step 6:** Verify no RAW audit payload, materialized render caches, or Python cache files are included.

### Task 6: Deterministic release packaging

**Files:**
- Create: `/mnt/data/GDS_CENTRAL_GAME_CORE_v1.1.0.zip`

**Interfaces:**
- Consumes: verified Phase 6 package tree.
- Produces: deterministic release ZIP.

- [ ] **Step 1:** Rebuild `spatial_profiles.json` twice and require byte-identical output.
- [ ] **Step 2:** Run the complete Phase 6 test and audit suite fresh.
- [ ] **Step 3:** Remove `__pycache__`, `.pytest_cache`, and `.pyc` files.
- [ ] **Step 4:** Generate checksums after all reports/docs are final.
- [ ] **Step 5:** Create deterministic ZIP with fixed timestamps and sorted file order.
- [ ] **Step 6:** Fresh-extract the release ZIP and rerun checksum, schema, self-audit, floor render, direction, and runtime smoke tests.
- [ ] **Step 7:** Repack the fresh extract and require the ZIP to be byte-identical.
