from pathlib import Path

from RUNTIME.central_core import CentralGameCore
from RUNTIME.character_movement_core import CharacterMovementCore
from WORLD.RUNTIME.pathfinding_core import PathfindingCore


ROOT = Path(__file__).resolve().parents[1]



def test_uv_cell_center_projection_matches_permanent_fine_grid_contract():
    movement = CharacterMovementCore(ROOT)
    assert movement.uv_cell_center_to_pixel(0, 0) == (28, 1)
    assert movement.uv_cell_center_to_pixel(1, 0) == (30, 2)
    assert movement.uv_cell_center_to_pixel(0, 1) == (26, 2)



def test_direction_mapping_matches_uv_cardinal_steps():
    movement = CharacterMovementCore(ROOT)
    assert movement.direction_for_step((0, 0), (1, 0)) == 'SE'
    assert movement.direction_for_step((0, 0), (-1, 0)) == 'NW'
    assert movement.direction_for_step((0, 0), (0, 1)) == 'SW'
    assert movement.direction_for_step((0, 0), (0, -1)) == 'NE'



def test_dense_motion_sampling_subdivides_every_fine_grid_step_without_zero_motion_duplicates():
    movement = CharacterMovementCore(ROOT)
    path = [(10, 10), (11, 10), (11, 11)]
    samples = movement.sample_path_states(path, substeps_per_cell=4)

    assert len(samples) == 8
    assert samples[0]['direction'] == 'SE'
    assert samples[4]['direction'] == 'SW'
    assert samples[-1]['ground_xy'] == list(movement.uv_cell_center_to_pixel(11, 11))
    for a, b in zip(samples, samples[1:]):
        assert tuple(a['ground_xy']) != tuple(b['ground_xy'])
        assert b['cumulative_distance_px'] > a['cumulative_distance_px']



def test_resolve_movement_uses_existing_move_actions_and_arrives_in_idle():
    pathfinding = PathfindingCore(ROOT / 'WORLD')
    start = pathfinding.resolve_portal_start('floor00')
    goal = pathfinding.resolve_near_target('floor00', start, min_distance=6)
    movement = CharacterMovementCore(ROOT, pathfinding=pathfinding)

    record = movement.resolve_movement(0, 'floor00', start, goal)

    assert record['character_id'] == 'TP_000'
    assert record['floor_id'] == 'floor00'
    assert record['start_uv'] == list(start)
    assert record['goal_uv'] == list(goal)
    assert record['ground_anchor_px'] == [16, 31]
    assert record['path_cell_count'] == len(record['path_cells_uv'])
    assert record['path_positions_px'][0] == list(movement.uv_cell_center_to_pixel(*start))
    assert record['path_positions_px'][-1] == list(movement.uv_cell_center_to_pixel(*goal))
    assert len(record['segments']) >= 1
    for segment in record['segments']:
        assert segment['action'] == 'move'
        assert segment['direction'] in {'NE', 'SE', 'SW', 'NW'}
        assert len(segment['frame_ids']) >= 1
    assert record['dense_motion_substeps_per_cell'] == 4
    assert len(record['dense_motion_samples']) == max(0, record['path_cell_count'] - 1) * 4
    assert record['arrival_action']['action'] == 'idle'
    assert record['arrival_action']['direction'] == record['segments'][-1]['direction']
    assert len(record['arrival_action']['frame_ids']) >= 1



def test_central_facade_exposes_pathfinding_and_movement_smoke_across_floors():
    core = CentralGameCore(ROOT)
    assert core.pathfinding.occupancy is core.navigation_occupancy
    for floor_id in ('floor00', 'floor01', 'floor02', 'floor36'):
        start = tuple(core.resolve_portal_navigation_start(floor_id))
        goal = tuple(core.resolve_distant_navigation_target(floor_id, start))
        path = core.find_navigation_path(floor_id, start, goal)
        movement = core.resolve_character_movement(0, floor_id, start, goal)
        assert path['path_cells_uv'][0] == list(start)
        assert path['path_cells_uv'][-1] == list(goal)
        assert movement['path_cells_uv'] == path['path_cells_uv']
        assert movement['arrival_action']['action'] == 'idle'
