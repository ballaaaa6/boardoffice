from pathlib import Path

import pytest

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


def test_movement_profile_is_stable_per_character_and_stays_in_approved_range():
    core = CentralGameCore(ROOT)
    numeric = core.resolve_character_movement_profile(0)
    canonical = core.resolve_character_movement_profile('TP_000')

    assert numeric == canonical
    assert numeric['speed_range_percent'] == [125, 175]
    assert 125 <= numeric['speed_percent'] <= 175
    assert numeric['speed_multiplier'] == numeric['speed_percent'] / 100
    assert numeric['walk_frame_distance_cells'] == pytest.approx(
        0.65 * numeric['speed_multiplier']
    )

    profiles = [core.resolve_character_movement_profile(index) for index in range(20)]
    assert len({row['speed_percent'] for row in profiles}) >= 10
    assert all(125 <= row['speed_percent'] <= 175 for row in profiles)


def test_actor_seed_can_vary_an_instance_without_rerolling_between_calls():
    movement = CharacterMovementCore(ROOT)
    first = movement.resolve_movement_profile(0, actor_seed='lobby-a')
    repeated = movement.resolve_movement_profile('TP_000', actor_seed='lobby-a')

    assert first == repeated
    assert first['assignment_policy'] == 'stable_sha256_per_actor_seed'


def test_shared_tick_timeline_moves_faster_profiles_farther_and_finishes_earlier():
    movement = CharacterMovementCore(ROOT)
    path = [(10, 10), (11, 10), (11, 11), (12, 11), (12, 12)]
    slow = movement.sample_path_timeline(path, speed_multiplier=1.25)
    fast = movement.sample_path_timeline(path, speed_multiplier=1.75)

    assert len(fast) < len(slow)
    assert fast[0]['distance_cells'] > slow[0]['distance_cells']
    assert fast[-1]['ground_xy'] == slow[-1]['ground_xy']
    assert fast[-1]['ground_xy'] == list(movement.uv_cell_center_to_pixel(*path[-1]))
    assert all(row['tick_ms'] == 60 for row in fast + slow)


def test_visual_facing_suppresses_alternating_astar_staircase_directions():
    movement = CharacterMovementCore(ROOT)
    path = [
        (10, 10),
        (11, 10),
        (11, 11),
        (12, 11),
        (12, 12),
        (13, 12),
        (13, 13),
        (14, 13),
        (14, 14),
    ]
    raw = [movement.direction_for_step(a, b) for a, b in zip(path, path[1:])]
    visual = movement.visual_directions_for_path(path)

    assert raw == ['SE', 'SW', 'SE', 'SW', 'SE', 'SW', 'SE', 'SW']
    assert visual == ['SE'] * len(raw)



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
    assert record['movement_profile'] == movement.resolve_movement_profile(0)
    assert record['timed_motion_tick_ms'] == 60
    assert record['timed_motion_samples'][-1]['ground_xy'] == list(
        movement.uv_cell_center_to_pixel(*goal)
    )
    assert record['arrival_action']['action'] == 'idle'
    assert record['arrival_action']['direction'] == record['timed_motion_samples'][-1]['direction']
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
