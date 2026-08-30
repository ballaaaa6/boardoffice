# Phase 8B Walking Depth Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make walking characters visually respect desks, PCs, chairs, reception, and authored foreground overlays without changing navigation/collision geometry.

**Architecture:** Add one walking-depth runtime that derives depth anchors from existing ground footprints. Desk/chair/reception use their footprint front-edge depth; PCs inherit the workstation desk depth; chair foreground fragments inherit the chair depth; authored `top_character_occluder` overlays always redraw after the character. Movement rendering remains complete-floor → character → selected occluder redraws.

**Tech Stack:** Python 3, Pillow, existing LayoutCore / NavigationOccupancyCore / FloorRenderer / CentralGameCore, pytest.

**Spec:** Approved in-chat 2026-08-30 after Phase 8B distant-route review.

## Global Constraints
- Do not change Room Domain, Portal, pathfinding, or collision footprints for this fix.
- Do not add collision to PC/chair foreground visual fragments.
- Do not use sprite top-left Y or authored static layer as world depth.
- Use existing real project assets only; no generated artwork.
- Keep current v1.8.0 as an unapproved release candidate until the new distant-route proof passes human review.

---

### Task 1: Walking depth metadata resolver

**Files:**
- Create: `WORLD/RUNTIME/walking_depth_core.py`
- Create: `TESTS/test_walking_depth_core.py`

**Interfaces:**
- `WalkingDepthCore(world_root)`
- `resolve_occluders(floor_id) -> list[dict]`
- `occluders_in_front(floor_id, character_ground_y_px) -> list[dict]`

- [ ] Write failing tests for footprint-based desk/chair/reception depth, PC→desk inheritance, chair_sub→chair inheritance, and always-foreground overlay semantics.
- [ ] Run focused tests and confirm RED.
- [ ] Implement minimal metadata resolver using existing placements and footprint instances.
- [ ] Run focused tests and confirm GREEN.

### Task 2: Walking occlusion compositor

**Files:**
- Modify: `WORLD/RUNTIME/walking_depth_core.py`
- Modify: `TESTS/test_walking_depth_core.py`

**Interfaces:**
- `composite_character(floor_id, sprite, ground_xy, ground_anchor_px) -> Image.Image`

- [ ] Write failing image-behavior tests proving an in-front desk redraw changes overlapping character pixels while a behind desk does not redraw.
- [ ] Run focused tests and confirm RED.
- [ ] Implement complete-floor → human → depth-selected redraw with original authored placement/variant.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Runtime facade + QA integration

**Files:**
- Modify: `RUNTIME/central_core.py`
- Modify: `TOOLS/render_phase8b_floor00_movement.py`
- Modify/Create tests under `TESTS/`.

**Interfaces:**
- Central runtime owns one shared `WalkingDepthCore`.
- Phase 8B GIF renderer uses walking-depth compositor for every movement/idle frame.

- [ ] Write failing facade/QA tests.
- [ ] Wire shared runtime core and update GIF compositor.
- [ ] Run focused movement/depth tests.

### Task 4: Distant-route human gate

**Files:**
- External output only: `/mnt/data/GDS_PHASE8B_DEPTH_QA/`.

- [ ] Regenerate the Floor00 distant-target GIF with walking occlusion enabled.
- [ ] Generate a before/after comparison strip using existing artifacts only.
- [ ] Run relevant navigation/movement/depth regression tests.
- [ ] Present distant-route proof and STOP for human approval before repackaging v1.8.0.
