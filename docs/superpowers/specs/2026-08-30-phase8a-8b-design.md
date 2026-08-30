# Phase 8A + 8B Design

## Goal
Freeze navigation geometry through deterministic visual QA, then add a thin reusable pathfinding/movement layer that uses the existing runtime-derived navigation and existing four-way character actions.

## Non-negotiable constraints
- Canonical baseline is GDS_CENTRAL_GAME_CORE_v1.7.0.
- Visual output uses real project assets plus deterministic PIL/compositing only. No image generation or invented artwork.
- PREVIEW and generated review artifacts stay outside the canonical release payload.
- WORLD/COMPILED_NAV/OCCUPANCY is optional cache only and must not be required.
- Fine grid remains grid.iso.occupancy_fine.v1 (4x2 px, U=(+2,+1), V=(-2,+1), origin=(28,0)).
- F0 and F1 geometry remain unique; F2 geometry remains canonical for all F2+ floors.
- Active navigation remains ROOM DOMAIN - ACTIVE FOOTPRINTS.
- 8B does not implement fade, portal exit/despawn, WorkSeat takeover, final depth/occlusion, or multi-character avoidance.

## Phase 8A architecture
Create a dedicated deterministic QA renderer that consumes FloorRenderer, RoomNavigationCore, and NavigationOccupancyCore. It forces runtime compilation from canonical metadata during QA so review output cannot accidentally depend on a disk occupancy cache. It generates two images per reviewed floor: a real-floor navigation overlay and an abstract cell map, plus machine-readable metrics and contact sheets.

Review floors: floor00, floor01, floor02, floor03, floor06, and the final floor in the registry that uses layout.floor02.large (currently floor36).

Overlay semantics: real floor asset, readable dark fine grid, blue room boundary, green walkable cells, red occupied cells, yellow portal. No object-name labels over the clean map.

Abstract map semantics: black outside, green walkable, red occupied, yellow portal.

8A ends at a hard human visual-review gate. No 8B implementation begins until the user approves the generated QA set.

## Phase 8B architecture
Add WORLD/RUNTIME/pathfinding_core.py as a pure A* service over NavigationOccupancyCore walkable cells. Use 4-neighbor movement, unit edge costs, Manhattan heuristic, and deterministic tie-breaking. No sprite or animation logic belongs in this file.

Add RUNTIME/character_movement_core.py as a thin movement resolver. It converts UV cell centers to screen coordinates, maps cardinal UV steps to NE/SE/SW/NW character directions, compresses straight runs into movement segments, drives existing move/idle actions, and preserves a shared ground/feet anchor contract.

Expose the functionality through CentralGameCore rather than forcing consumers to reach into internals.

8B first proves three deterministic F0 routes: portal-inside to near open target, portal-inside to distant target, and portal-inside to one reachable workstation approach cell. Cross-floor smoke tests verify generic behavior on F1/F2/F2+.

## Review gates
1. Baseline gate: 57/57 existing tests pass on a fresh extracted copy. Automated only; proceed when green.
2. 8A visual gate: stop and present the generated overlays/cell maps/report to the user. Continue only after explicit approval.
3. 8B anchor/motion proof gate: after first F0 movement proof is generated, stop and present it before extending to the remaining route proofs if visual alignment or direction needs human judgment.
4. 8B release gate: full regression + route proofs + cross-floor smoke must pass before packaging v1.8.0.
