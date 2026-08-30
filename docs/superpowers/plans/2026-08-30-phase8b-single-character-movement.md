# Phase 8B Single Character Movement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic single-character A* pathfinding and smooth four-way movement on existing runtime-derived navigation, first proven on Floor00.

**Architecture:** PathfindingCore is pure grid/path logic over NavigationOccupancyCore. CharacterMovementCore consumes a path, converts cell centers to screen-space, maps UV steps to existing NE/SE/SW/NW move actions, compresses straight runs, and stops in idle. CentralGameCore exposes the public facade.

**Tech Stack:** Python 3, Pillow, pytest, existing GDS character/world runtime.

**Spec:** `docs/superpowers/specs/2026-08-30-phase8a-8b-design.md`

## Global Constraints
- Do not start until the user approves Phase 8A visual QA.
- No new navigation grid or occupancy system.
- 4-neighbor only; no diagonal shortcuts.
- Use existing character idle/move frames only; no generated artwork.
- No 8C/8D/8E/8G features in this phase.
- Generated GIF/debug images stay outside canonical release.

---

### Task 1: Pure A* pathfinding core

**Files:**
- Create: `WORLD/RUNTIME/pathfinding_core.py`
- Create: `TESTS/test_pathfinding_core.py`

**Interfaces:**
- `PathfindingCore(world_root)`
- `find_path(floor_id: str, start_uv: tuple[int,int], goal_uv: tuple[int,int]) -> dict`
- `compress_path(path_cells_uv: list[list[int]]) -> list[list[int]]`

- [x] Step 1: Write failing tests for start==goal, valid F0 route, every path cell walkable, 4-neighbor adjacency, deterministic path output, invalid start, invalid goal, and unknown floor.
- [x] Step 2: Run focused tests; verify expected failures.
- [x] Step 3: Implement deterministic A* using unit costs, Manhattan heuristic, and stable neighbor order.
- [x] Step 4: Run focused tests; expected PASS.
- [x] Step 5: Add a BFS reference assertion for sampled routes proving A* path length is optimal; run PASS.

### Task 2: Portal start and target resolvers

**Files:**
- Modify: `WORLD/RUNTIME/pathfinding_core.py`
- Modify: `TESTS/test_pathfinding_core.py`

**Interfaces:**
- `resolve_portal_start(floor_id) -> tuple[int,int]`: walkable portal-inside cell nearest the portal strip midpoint.
- `resolve_distant_target(floor_id, start_uv) -> tuple[int,int]`: deterministic farthest reachable walkable cell with stable tie-break.

- [x] Step 1: Write failing tests for deterministic portal-start selection and valid distant targets on F0/F1/F2/floor36.
- [x] Step 2: Run focused tests; verify failures.
- [x] Step 3: Implement resolvers using existing portal and walkable data only.
- [ ] Step 4: Run focused tests; expected PASS.

### Task 3: UV cell-center projection and direction contract

**Files:**
- Create: `RUNTIME/character_movement_core.py`
- Create: `TESTS/test_character_movement_integration.py`

**Interfaces:**
- `uv_cell_center_to_pixel(u, v) -> tuple[float,float]`
- `direction_for_step((u0,v0),(u1,v1)) -> str`
- Mapping: +U=SE, -U=NW, +V=SW, -V=NE.

- [x] Step 1: Write failing tests for cell-center projection and all four direction mappings.
- [ ] Step 2: Run focused tests; verify failures.
- [x] Step 3: Implement minimal projection using the permanent RoomNavigationCore grid profile and strict cardinal-step validation.
- [ ] Step 4: Run focused tests; expected PASS.

### Task 4: Existing action integration and shared ground anchor

**Files:**
- Modify: `RUNTIME/character_movement_core.py`
- Modify: `TESTS/test_character_movement_integration.py`

**Interfaces:**
- `resolve_movement(character_query, floor_id, start_uv, goal_uv) -> movement record`
- Movement record contains full path, compressed waypoints, direction segments, projected positions, and arrival idle direction.

- [x] Step 1: Write failing tests that movement segments select existing `move` direction actions and arrival selects existing `idle` with last direction.
- [ ] Step 2: Run focused tests; verify failures.
- [x] Step 3: Inspect canonical 32x42 rendered movement frames to validate one shared ground anchor; encode the verified anchor contract in movement core rather than per-character metadata.
- [x] Step 4: Implement movement record generation without portal fade, seating, or depth sorting.
- [x] Step 5: Run focused tests; expected PASS.

### Task 5: Central facade and generic smoke

**Files:**
- Modify: `RUNTIME/central_core.py`
- Modify: `TESTS/test_character_movement_integration.py`

**Interfaces:**
- `CentralGameCore.find_navigation_path(floor_id, start_uv, goal_uv)`
- `CentralGameCore.resolve_character_movement(query, floor_id, start_uv, goal_uv)`

- [ ] Step 1: Write failing facade tests.
- [ ] Step 2: Run focused tests; verify failures.
- [ ] Step 3: Wire PathfindingCore and CharacterMovementCore into CentralGameCore.
- [ ] Step 4: Add cross-floor smoke for F0/F1/F2/floor36; run PASS.

### Task 6: F0 visual movement proof and human gate

**Files:**
- Create: `TOOLS/render_phase8b_floor00_movement.py`
- Create: `TESTS/test_phase8b_movement_preview.py`
- External output: `/mnt/data/GDS_PHASE8B_F0_MOVEMENT_QA/`.

**Interfaces:**
- Deterministic proof renders use real floor asset + real character move/idle frames.

- [ ] Step 1: Write failing tests for deterministic proof output and three route definitions: near open target, distant target, one reachable workstation approach cell.
- [ ] Step 2: Run focused tests; verify failures.
- [ ] Step 3: Implement deterministic debug overlay and GIF renderer using PIL only.
- [ ] Step 4: Generate the first F0 movement proof and STOP for human inspection of feet alignment, direction, and visual motion before finalizing remaining route proofs.

### Task 7: Complete 8B proofs and release gate

**Files:**
- Modify docs/README/HANDOFF only after behavior is approved.
- Package target: `GDS_CENTRAL_GAME_CORE_v1.8.0.zip`.

- [ ] Step 1: Generate all three F0 route proofs and cross-floor path smoke report.
- [ ] Step 2: Run full `python -m pytest -q` and all validation scripts used by v1.7.0 fresh-extract gate.
- [ ] Step 3: Verify no PREVIEW or materialized occupancy cache is required/package source-of-truth.
- [ ] Step 4: Update version/handoff docs to v1.8.0 single-character movement foundation.
- [ ] Step 5: Fresh-extract the new ZIP and re-run the complete release gate.
- [ ] Step 6: Present release artifacts and stop for final approval.
