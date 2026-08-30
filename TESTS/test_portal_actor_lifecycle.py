from pathlib import Path

import pytest

from RUNTIME.central_core import CentralGameCore, CentralGameCoreError


ROOT = Path(__file__).resolve().parents[1]


def test_portal_actor_cycle_is_deterministic_and_ends_despawned():
    core = CentralGameCore(ROOT)
    start = tuple(core.resolve_portal_navigation_start('floor00'))
    target = tuple(core.pathfinding.resolve_near_target('floor00', start, min_distance=6))

    first = core.resolve_portal_actor_cycle(0, 'floor00', target)
    second = core.resolve_portal_actor_cycle('TP_000', 'floor00', target)

    assert first == second
    assert first['schema'] == 'gds.portal_actor_lifecycle.v1'
    assert first['playback_tick_ms'] == 60
    assert 225 <= first['movement_profile']['speed_percent'] <= 250
    assert first['portal']['entry_exit_adjacent'] is True
    assert first['target_uv'] == list(target)
    assert first['outward_path_cells_uv'][0] == list(start)
    assert first['outward_path_cells_uv'][-1] == list(target)
    assert first['return_path_cells_uv'][0] == list(target)
    assert first['return_path_cells_uv'][-1] == list(start)
    assert first['phase_counts']['unspawned'] == 1
    assert first['phase_counts']['entering'] == first['fade_steps']
    assert first['phase_counts']['despawned'] == 1
    assert first['despawned'] is True
    assert first['final_state']['phase'] == 'despawned'
    assert first['final_state']['visible'] is False
    assert first['final_state']['alpha'] == 0.0
    assert all(
        state['speed_percent'] == first['movement_profile']['speed_percent']
        for state in first['states']
    )
    assert all(state['tick_ms'] == first['playback_tick_ms'] for state in first['states'])

    phases = [state['phase'] for state in first['states']]
    assert phases[0] == 'unspawned'
    assert phases.index('entering') > phases.index('unspawned')
    assert phases.index('active') > phases.index('entering')
    assert phases.index('exiting') > phases.index('active')
    assert phases[-1] == 'despawned'


def test_portal_actor_entry_and_exit_preserve_portal_pair_and_fade_order():
    core = CentralGameCore(ROOT)
    cycle = core.resolve_portal_actor_cycle(0, 'floor02')
    inside = cycle['portal']['inside_uv']
    outside = cycle['portal']['outside_uv']
    entering = [row for row in cycle['states'] if row['phase'] == 'entering']
    exiting = [row for row in cycle['states'] if row['phase'] == 'exiting']

    assert entering[0]['current_uv'] is None
    assert entering[-1]['current_uv'] == inside
    assert entering[0]['alpha'] > 0.0
    assert entering[-1]['alpha'] == 1.0
    assert [row['alpha'] for row in entering] == sorted(row['alpha'] for row in entering)
    assert exiting[0]['alpha'] == 1.0
    assert exiting[-1]['alpha'] > 0.0
    assert exiting[-1]['current_uv'] == outside
    assert cycle['final_state']['current_uv'] == outside


def test_portal_actor_cycle_rejects_unreachable_goal():
    core = CentralGameCore(ROOT)
    with pytest.raises(CentralGameCoreError):
        core.resolve_portal_actor_cycle(0, 'floor00', (0, 0))


def test_faster_portal_actor_uses_fewer_shared_tick_move_states_for_same_route():
    core = CentralGameCore(ROOT)
    start = tuple(core.resolve_portal_navigation_start('floor00'))
    target = tuple(core.pathfinding.resolve_near_target('floor00', start, min_distance=12))
    profiles = {
        query: core.resolve_character_movement_profile(query)
        for query in range(20)
    }
    fast_query = max(profiles, key=lambda query: profiles[query]['speed_percent'])
    slow_query = min(profiles, key=lambda query: profiles[query]['speed_percent'])
    fast = core.resolve_portal_actor_cycle(fast_query, 'floor00', target)
    slow = core.resolve_portal_actor_cycle(slow_query, 'floor00', target)

    assert fast['movement_profile']['speed_percent'] > slow['movement_profile']['speed_percent']
    fast_move_count = sum(
        state['phase'] == 'active' and state['action'] == 'move'
        for state in fast['states']
    )
    slow_move_count = sum(
        state['phase'] == 'active' and state['action'] == 'move'
        for state in slow['states']
    )
    assert fast_move_count < slow_move_count
    assert all('raw_direction' in state for state in fast['states'])
