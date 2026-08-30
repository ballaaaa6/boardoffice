# Phase 8A Navigation QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce deterministic navigation QA images and metrics from canonical v1.7.0 runtime inputs, then stop for human visual approval.

**Architecture:** Add one focused QA rendering module/tool that uses existing FloorRenderer, RoomNavigationCore, and NavigationOccupancyCore. The tool forces runtime occupancy derivation, writes review artifacts outside canonical PREVIEW, and never mutates navigation metadata.

**Tech Stack:** Python 3, Pillow, pytest, existing GDS runtime modules.

**Spec:** `docs/superpowers/specs/2026-08-30-phase8a-8b-design.md`

## Global Constraints
- Use real project assets and deterministic compositing only; no image generation.
- Do not modify room/portal/footprint/layout registries during 8A unless the human review identifies a real defect.
- Generated QA artifacts live outside the canonical release tree.
- Force runtime-derived occupancy during QA; do not rely on WORLD/COMPILED_NAV/OCCUPANCY.
- Human approval is mandatory after artifacts are generated.

---

### Task 1: QA renderer contract

**Files:**
- Create: `TOOLS/phase8a_navigation_qa.py`
- Create: `TESTS/test_phase8a_navigation_qa.py`

**Interfaces:**
- Consumes: `FloorRenderer.render(floor_id)`, `RoomNavigationCore`, `NavigationOccupancyCore.compile_floor(floor_id)`.
- Produces: `render_floor_overlay(floor_id)`, `render_cell_map(floor_id)`, `build_floor_metrics(floor_id)`.

- [ ] Step 1: Write failing tests asserting overlay/cell-map images are produced at nonzero size and metrics equal NavigationOccupancyCore compiled counts for floor00.
- [ ] Step 2: Run `python -m pytest TESTS/test_phase8a_navigation_qa.py -q`; expected failure because module does not exist.
- [ ] Step 3: Implement minimal renderer helpers using existing runtime cores and PIL polygons/lines.
- [ ] Step 4: Re-run the test; expected PASS.

### Task 2: Review set and external artifact writer

**Files:**
- Modify: `TOOLS/phase8a_navigation_qa.py`
- Modify: `TESTS/test_phase8a_navigation_qa.py`

**Interfaces:**
- Produces: `resolve_review_floors()` = floor00, floor01, floor02, floor03, floor06, final layout.floor02.large floor; `generate_review_bundle(output_root)`.

- [ ] Step 1: Add failing tests for review-floor resolution, absence of duplicate floors, final large-layout floor selection, JSON report keys, and output paths outside canonical PREVIEW.
- [ ] Step 2: Run focused tests and verify expected failures.
- [ ] Step 3: Implement deterministic bundle writer with OVERLAY, CELL_MAP, CONTACT_SHEETS, and PHASE8A_NAVIGATION_QA.json.
- [ ] Step 4: Run focused tests; expected PASS.

### Task 3: Machine QA and regression

**Files:**
- Modify: `TOOLS/phase8a_navigation_qa.py`
- Modify: `TESTS/test_phase8a_navigation_qa.py`

**Interfaces:**
- Metrics include floor_id, canonical_room_floor_id, room_cell_count, occupied_cell_count, walkable_cell_count, portal_inside_cell_count, outside_room_instance_count, portal_overlap_cell_count, isolated_walkable_cell_count, workstation_count, unreachable_workstation_count.

- [ ] Step 1: Add failing tests that floor00/01/02 expected counts remain 3939/710/3229/12, 6380/1176/5204/26, 7884/1503/6381/28 and that every review floor has zero outside-room instances, zero portal overlap, zero isolated walkable cells, and zero unreachable workstations.
- [ ] Step 2: Run focused tests; verify failures if metrics are incomplete.
- [ ] Step 3: Implement missing audit aggregation using NavigationOccupancyCore.validate_floor and workstation_access.
- [ ] Step 4: Run `python -m pytest -q`; expected 57 existing tests plus new 8A tests all PASS.

### Task 4: Generate review artifacts and stop

**Files:**
- No canonical source modification beyond the tested tool.
- External output: `/mnt/data/GDS_PHASE8A_NAV_QA/`.

- [ ] Step 1: Run `python TOOLS/phase8a_navigation_qa.py --output /mnt/data/GDS_PHASE8A_NAV_QA`.
- [ ] Step 2: Inspect report programmatically for PASS on all six floors.
- [ ] Step 3: Package the external review directory as `/mnt/data/GDS_PHASE8A_NAV_QA.zip`.
- [ ] Step 4: Present contact sheets, report, and ZIP to the user and STOP for explicit visual approval before Phase 8B.
