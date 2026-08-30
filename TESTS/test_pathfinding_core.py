from collections import deque
from pathlib import Path

import pytest

from WORLD.RUNTIME.pathfinding_core import (
    InvalidGoal,
    InvalidStart,
    PathfindingCore,
    UnknownFloor,
)


ROOT = Path(__file__).resolve().parents[1]
WORLD_ROOT = ROOT / 'WORLD'



def _bfs_distance(pathfinding: PathfindingCore, floor_id: str, start: tuple[int, int], goal: tuple[int, int]) -> int:
    compiled = pathfinding.occupancy.resolve_floor(floor_id)
    walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        cur, dist = queue.popleft()
        if cur == goal:
            return dist
        for du, dv in pathfinding.NEIGHBOR_DELTAS:
            nxt = (cur[0] + du, cur[1] + dv)
            if nxt in walkable and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    raise AssertionError(f'BFS could not reach {goal} from {start} on {floor_id}')



def test_find_path_accepts_start_equals_goal_and_compresses_runs():
    p = PathfindingCore(WORLD_ROOT)
    start = p.resolve_portal_start('floor00')

    same = p.find_path('floor00', start, start)
    assert same['path_cells_uv'] == [list(start)]
    assert same['compressed_waypoints_uv'] == [list(start)]

    assert p.compress_path([[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]]) == [[0, 0], [2, 0], [2, 2]]



def test_find_path_returns_deterministic_valid_walkable_route_on_floor00():
    p = PathfindingCore(WORLD_ROOT)
    start = p.resolve_portal_start('floor00')
    goal = p.resolve_distant_target('floor00', start)

    a = p.find_path('floor00', start, goal)
    b = p.find_path('floor00', start, goal)

    assert a == b
    assert a['start_uv'] == list(start)
    assert a['goal_uv'] == list(goal)
    assert a['path_cell_count'] == len(a['path_cells_uv'])
    assert a['path_cell_count'] > 1

    compiled = p.occupancy.resolve_floor('floor00')
    walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
    for cell in a['path_cells_uv']:
        assert tuple(cell) in walkable
    for cur, nxt in zip(a['path_cells_uv'], a['path_cells_uv'][1:]):
        du = abs(nxt[0] - cur[0])
        dv = abs(nxt[1] - cur[1])
        assert du + dv == 1



def test_invalid_start_goal_and_unknown_floor_raise_specific_errors():
    p = PathfindingCore(WORLD_ROOT)
    start = p.resolve_portal_start('floor00')
    with pytest.raises(InvalidStart):
        p.find_path('floor00', (-999, -999), start)
    with pytest.raises(InvalidGoal):
        p.find_path('floor00', start, (-999, -999))
    with pytest.raises(UnknownFloor):
        p.find_path('floorXX', start, start)



def test_astar_path_length_matches_bfs_reference_for_sampled_routes():
    p = PathfindingCore(WORLD_ROOT)
    samples = []
    for floor_id in ('floor00', 'floor01', 'floor02'):
        start = p.resolve_portal_start(floor_id)
        goal = p.resolve_distant_target(floor_id, start)
        samples.append((floor_id, start, goal))
    for floor_id, start, goal in samples:
        result = p.find_path(floor_id, start, goal)
        assert result['path_cell_count'] - 1 == _bfs_distance(p, floor_id, start, goal)



def test_portal_start_and_distant_target_are_deterministic_and_valid_across_floor_families():
    p = PathfindingCore(WORLD_ROOT)
    for floor_id in ('floor00', 'floor01', 'floor02', 'floor36'):
        start = p.resolve_portal_start(floor_id)
        start2 = p.resolve_portal_start(floor_id)
        assert start == start2
        compiled = p.occupancy.resolve_floor(floor_id)
        walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}
        portal = {tuple(cell) for cell in compiled['portal_inside_cells_uv']}
        assert start in walkable
        assert start in portal
        target = p.resolve_distant_target(floor_id, start)
        target2 = p.resolve_distant_target(floor_id, start)
        assert target == target2
        assert target in walkable
        assert target != start
