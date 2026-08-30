# GDS_CENTRAL_GAME_CORE_v1.8.3 — handoff

## Scope completed
This pass bundled the requested **3 gates** together in one release:

1. **Gate A — walking / movement smoothing**
   - upgraded movement sampling from coarse per-cell stepping to **dense 4-substep interpolation per fine-grid cell**
   - added distance-driven walk-cycle phase logic so sprite leg motion stays synchronized with slower/smoother travel
   - kept portal enter/exit despawn safety from v1.8.2 (no lingering ghost actor after fade-out)
   - exposed dense motion samples from `CharacterMovementCore.resolve_movement()`

2. **Gate B — F2-family reception canonical sync**
   - kept the fixed shared navigation ground anchor at **(259, 376)**
   - updated the F2-family reception footprint origin offset to **[-13, -4]**
   - verified all **23 floors** in `layout.floor02.large` now share the same reception world footprint

3. **Gate C — reception footprint enlargement**
   - **floor01 reception** expanded on 3 exposed sides:
     - `-U +3`
     - `-V +3`
     - `+V +3`
     - wall side kept fixed
   - **floor02+ reception family** expanded symmetrically from the previous 29x15 baseline:
     - `-U +3`, `+U +3`
     - `-V +4`, `+V +4`

## Final footprint sizes
- `footprint.reception.f1`
  - old: `13 x 14` = `182` cells
  - new: `16 x 20` = `320` cells
- `footprint.reception.f2_plus`
  - old: `29 x 15` = `435` cells
  - new: `35 x 23` = `805` cells

## Key code / data changes
- `RUNTIME/character_movement_core.py`
- `TOOLS/render_phase8b_crowd_portal_qa.py`
- `WORLD/REGISTRY/footprint_profiles.json`
- `WORLD/REGISTRY/gameplay_metadata_families.json`
- test updates + new reception regression coverage under `TESTS/`

## Validation performed
### Focused pytest runs
- movement integration
- reception anchor lock
- ground footprint system
- reception expansion regression
- navigation occupancy integration
- phase8a / phase8b QA tests
- walking depth + work-seat regressions

All targeted test groups passed.

## QA bundle
Generated external review bundle:
- `/mnt/data/GDS_PHASE8C_V183_3GATE_QA`

Important files:
- summary: `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/PHASE8C_V183_3GATE_SUMMARY.json`
- gate A: `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_A_MOVEMENT/GATE_A_MOVEMENT_REPORT.json`
- gate B/C: `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_BC_RECEPTION/PHASE8C_V183_RECEPTION_GATES.json`

Useful preview assets:
- `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_A_MOVEMENT/SINGLE_CHARACTER/CONTACT_SHEETS/floor00_phase8b_route_contact.png`
- `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_A_MOVEMENT/CROWD_FLOOR00/floor00_crowd_portal_v183.gif`
- `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_BC_RECEPTION/reception_compare_contact.png`
- `/mnt/data/GDS_PHASE8C_V183_3GATE_QA/GATE_BC_RECEPTION/f2_family_sync_contact.png`

## Packaging targets
- source folder: `/mnt/data/gds_v183_work/GDS_CENTRAL_GAME_CORE_v1.8.3`
- recommended release zip: `/mnt/data/GDS_CENTRAL_GAME_CORE_v1.8.3.zip`
- QA bundle zip: `/mnt/data/GDS_PHASE8C_V183_3GATE_QA.zip`

## Suggested next step
If this pass is accepted, next safest follow-up is:
1. apply the same denser movement playback policy to any crowd / ambient traversal tools beyond the floor00 proof bundle
2. extend reception-style footprint review to any future custom counters / lobby furniture using the same canonical-anchor method where visual padding varies between floors
