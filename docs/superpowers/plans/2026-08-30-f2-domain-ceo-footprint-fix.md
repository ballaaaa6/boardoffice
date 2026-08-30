# F2 Domain + CEO Desk Footprint Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Correct F0/F1 CEO desk footprint orientation and patch the canonical F2/F2+ Room Domain and portal from the approved markup.

**Architecture:** Keep one canonical desk footprint profile and select transform through ordered binding rules. Keep one canonical F2 room-navigation family and regenerate its portal strips/compiled mask after changing only the canonical F2 polygon; all `layout.floor02.large` floors continue to resolve through that family.

**Tech Stack:** Python 3, JSON registries, Pillow preview rendering, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-f2-domain-ceo-footprint-fix-design.md`

## Global Constraints
- Permanent fine grid stays `4×2 px`, U=`(2,1)`, V=`(-2,1)`, origin=`(28,0)`.
- No image generation; previews derive from canonical assets/metadata with code.
- No duplicate mirrored desk footprint profile.
- No duplicate Floor03+ room-domain/portal/mask geometry.
- Legacy floor-solid collision remains inactive/external.

---

### Task 1: CEO Desk Footprint Binding Patch

**Files:**
- Modify: `WORLD/REGISTRY/footprint_bindings.json`
- Modify: `TESTS/test_ground_footprint_system.py`

**Interfaces:**
- Consumes: `GroundFootprintCore.resolve_asset()` first-match binding semantics.
- Produces: F0/F1 CEO `NORMAL`; F2+ CEO `FLIP_X` using `footprint.desk.standard`.

- [x] **Step 1: Write failing tests** asserting F0/F1 CEO normal and F2 mirrored, including crop variants.
- [x] **Step 2: Run the focused footprint tests and confirm the F0/F1 assertions fail under the old catch-all mirror rule.**
- [x] **Step 3: Replace the catch-all CEO rule with ordered exact F0/F1 normal rules followed by an F2+ mirror regex rule.**
- [x] **Step 4: Run focused footprint tests and confirm PASS.**

### Task 2: Canonical F2/F2+ Room Domain + Portal Patch

**Files:**
- Modify: `WORLD/REGISTRY/room_domains.json`
- Modify: `WORLD/REGISTRY/portals.json`
- Regenerate: `WORLD/COMPILED_NAV/floor02_room_cells.json`
- Modify: `TESTS/test_room_navigation_canonical.py`

**Interfaces:**
- Consumes: existing F2 layout-family binding in `room_navigation_bindings.json`.
- Produces: canonical F2 polygon `[[188,45],[188,117],[217,117],[217,134],[240,134],[240,189],[268,189],[268,128],[279,128],[279,71],[217,71],[217,45]]` and portal `[[240,189],[268,189]]` inherited by F2+.

- [x] **Step 1: Write failing tests** for exact F2 polygon, 28-cell portal strip, and F3/F36 derivation.
- [x] **Step 2: Run focused room-navigation tests and confirm the new expected geometry fails against v1.5.0 data.**
- [x] **Step 3: Update canonical F2 domain/portal and regenerate portal inside/outside strips and compiled row-runs using cell-center polygon rasterization.**
- [x] **Step 4: Run focused room-navigation tests and audit consistency.**

### Task 3: Regenerate Review Previews and Occupancy Proof

**Files:**
- Update: `PREVIEW/NAVIGATION/*`
- Create proof package derived from patched Core: `GDS_NAV_OCCUPANCY_PROOF_v0.2.0`

**Interfaces:**
- Consumes: patched canonical navigation and footprint bindings.
- Produces: code-generated F0/F1/F2 occupancy/walkability/instance previews showing corrected CEO orientation and new F2 corridor/portal.

- [x] **Step 1: Rebuild canonical F0/F1/F2 author/cell-map previews from registries.**
- [x] **Step 2: Rebuild occupancy proof against the patched Core.**
- [x] **Step 3: Verify F0/F1 CEO instances report `NORMAL`, F2 reports `FLIP_X`, F2 portal has 28 inside cells, and connectivity has zero isolated walkable cells.**

### Task 4: Version, Audit, Package

**Files:**
- Modify: `CENTRAL_MANIFEST.json`, `README.md`, `README_TH.md`, `HANDOFF.md`
- Regenerate: `REPORTS/ROOM_NAVIGATION_AUDIT.json`, `checksums.sha256`

**Interfaces:**
- Produces: `GDS_CENTRAL_GAME_CORE_v1.5.1.zip` and review proof ZIP.

- [x] **Step 1: Update version/handoff metadata with the two approved corrections.**
- [x] **Step 2: Run full active pytest suite and navigation/footprint audits.**
- [x] **Step 3: Generate checksums, package ZIPs, fresh-extract, verify checksums, and rerun focused/full tests from extracted Core.**
