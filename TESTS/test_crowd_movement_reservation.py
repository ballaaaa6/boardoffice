from pathlib import Path

from RUNTIME.central_core import CentralGameCore
import pytest

from RUNTIME.crowd_movement_core import (
    CrowdMovementReservationError,
    DynamicActorReservationCore,
)


ROOT = Path(__file__).resolve().parents[1]


def _state(current, *, start=None, end=None, action='move', ground_xy=None, actor_id=None):
    row = {
        'phase': 'active',
        'action': action,
        'visible': True,
        'current_uv': list(current),
        'ground_xy': list(ground_xy or (float(current[0]), float(current[1]))),
    }
    if start is not None:
        row['from_uv'] = list(start)
    if end is not None:
        row['to_uv'] = list(end)
    if actor_id is not None:
        row['actor_id'] = actor_id
    return row


def test_later_actor_waits_before_entering_a_reserved_destination_cell():
    # Exercise the discrete cell/edge contract without the optional visual
    # ground-distance buffer used by the production facade.
    coordinator = DynamicActorReservationCore(reservation_radius_cells=0, ground_clearance_px=0)
    result = coordinator.schedule([
        {
            'actor_id': 'A',
            'priority': 0,
            'states': [
                _state((0, 0)),
                _state((1, 0), start=(0, 0), end=(1, 0)),
            ],
        },
        {
            'actor_id': 'B',
            'priority': 1,
            'states': [
                _state((2, 0)),
                _state((1, 0), start=(2, 0), end=(1, 0)),
            ],
        },
    ])

    actor_b = result['actors'][1]
    assert result['collision_free'] is True
    assert result['same_cell_conflicts'] == 0
    assert result['edge_swap_conflicts'] == 0
    assert actor_b['wait_ticks'] >= 1
    assert actor_b['states'][1]['phase'] == 'crowd_wait'
    assert actor_b['states'][1]['action'] == 'idle'


def test_edge_swap_is_rejected_and_queued_deterministically():
    coordinator = DynamicActorReservationCore(reservation_radius_cells=0)
    actors = [
        {
            'actor_id': 'A',
            'priority': 0,
            'states': [_state((0, 0), start=(0, 0), end=(1, 0))],
        },
        {
            'actor_id': 'B',
            'priority': 1,
            'states': [_state((1, 0), start=(1, 0), end=(0, 0))],
        },
    ]

    first = coordinator.schedule(actors)
    second = coordinator.schedule(actors)

    assert first == second
    assert first['collision_free'] is True
    assert first['edge_swap_blocking'] is True
    assert first['actors'][1]['start_delay'] > 0


def test_reservation_radius_is_reported_and_expands_ground_anchor_space():
    coordinator = DynamicActorReservationCore(reservation_radius_cells=1)
    result = coordinator.schedule([
        {'actor_id': 'A', 'states': [_state((4, 4))]},
        {'actor_id': 'B', 'states': [_state((5, 4))]},
    ])

    assert result['reservation_radius_cells'] == 1
    assert result['collision_free'] is True
    assert result['actors'][1]['start_delay'] > 0


def test_central_facade_exposes_dynamic_crowd_scheduler():
    core = CentralGameCore(ROOT)
    result = core.resolve_crowd_movement_schedule([
        {'actor_id': 'smoke-a', 'states': [_state((1, 1))]},
    ])

    assert result['schema'] == 'gds.dynamic_actor_reservation.v1'
    assert result['actor_count'] == 1
    assert result['collision_free'] is True


def test_swept_ground_segment_blocks_a_crossing_that_has_no_shared_uv_cell():
    coordinator = DynamicActorReservationCore(reservation_radius_cells=0, ground_clearance_px=0)
    result = coordinator.schedule([
        {
            'actor_id': 'A',
            'priority': 0,
            'states': [
                _state((0, 0), ground_xy=(0, 0)),
                _state((0, 1), start=(0, 0), end=(0, 1), ground_xy=(2, 2)),
            ],
        },
        {
            'actor_id': 'B',
            'priority': 1,
            'states': [
                _state((5, 0), ground_xy=(2, 0)),
                _state((5, 1), start=(5, 0), end=(5, 1), ground_xy=(0, 2)),
            ],
        },
    ])

    assert result['collision_free'] is True
    assert result['swept_segment_conflicts'] == 0
    assert result['actors'][1]['start_delay'] > 0 or result['actors'][1]['wait_ticks'] > 0


def test_actor_identity_cannot_be_changed_by_a_state_or_route_option():
    coordinator = DynamicActorReservationCore()
    with pytest.raises(CrowdMovementReservationError, match='actor_id'):
        coordinator.schedule([
            {
                'actor_id': 'A',
                'states': [_state((0, 0), actor_id='B')],
            },
        ])


def test_safe_route_option_is_selected_when_primary_route_is_blocked():
    coordinator = DynamicActorReservationCore(reservation_radius_cells=0, ground_clearance_px=0)
    result = coordinator.schedule([
        {
            'actor_id': 'A',
            'priority': 0,
            'states': [
                _state((0, 0), ground_xy=(0, 0)),
                _state((1, 0), start=(0, 0), end=(1, 0), ground_xy=(1, 0)),
            ],
        },
        {
            'actor_id': 'B',
            'priority': 1,
            'states': [
                _state((3, 0), ground_xy=(3, 0)),
                _state((1, 0), start=(3, 0), end=(1, 0), ground_xy=(1, 0)),
            ],
            'route_options': [[
                _state((3, 0), ground_xy=(3, 0)),
                _state((3, 1), start=(3, 0), end=(3, 1), ground_xy=(3, 1)),
                _state((1, 1), start=(3, 1), end=(1, 1), ground_xy=(1, 1)),
                _state((1, 0), start=(1, 1), end=(1, 0), ground_xy=(1, 0)),
            ]],
        },
    ])

    assert result['collision_free'] is True
    assert result['actors'][1]['route_option_index'] == 1
    assert result['actors'][1]['wait_ticks'] == 0


def test_trajectory_planner_allows_geometric_crossing_when_heads_are_asynchronous():
    coordinator = DynamicActorReservationCore(
        reservation_radius_cells=1,
        ground_clearance_px=0,
    )
    result = coordinator.schedule_trajectories([
        {
            'actor_id': 'A',
            'states': [
                _state((0, 0), ground_xy=(0, 0)),
                {
                    **_state((10, 10), ground_xy=(10, 10)),
                    'previous_ground_xy': [0, 0],
                },
            ],
        },
        {
            'actor_id': 'B',
            'states': [
                _state((10, 0), ground_xy=(10, 0)),
                {
                    **_state((2, 8), ground_xy=(2, 8)),
                    'previous_ground_xy': [10, 0],
                },
            ],
        },
    ])

    assert result['collision_free'] is True
    assert result['active_wait_ticks_total'] == 0
    assert result['wait_ticks_total'] == 0
    assert [row['start_delay'] for row in result['actors']] == [0, 0]


def test_trajectory_planner_uses_pre_spawn_offset_for_head_on_motion_without_wait_states():
    coordinator = DynamicActorReservationCore(
        reservation_radius_cells=1,
        ground_clearance_px=0,
    )
    result = coordinator.schedule_trajectories([
        {
            'actor_id': 'A',
            'states': [
                {
                    **_state((10, 0), ground_xy=(10, 0)),
                    'previous_ground_xy': [0, 0],
                },
            ],
        },
        {
            'actor_id': 'B',
            'states': [
                {
                    **_state((0, 0), ground_xy=(0, 0)),
                    'previous_ground_xy': [10, 0],
                },
            ],
        },
    ])

    assert result['collision_free'] is True
    assert result['active_wait_ticks_total'] == 0
    assert result['actors'][1]['pre_spawn_delay_ticks'] > 0
    assert all(
        state.get('phase') != 'crowd_wait'
        for row in result['actors']
        for state in row['states']
    )


def test_trajectory_planner_prefers_detour_before_pre_spawn_offset():
    coordinator = DynamicActorReservationCore(
        reservation_radius_cells=0,
        ground_clearance_px=0,
    )
    result = coordinator.schedule_trajectories([
        {
            'actor_id': 'A',
            'states': [
                _state((1, 0), ground_xy=(1, 0)),
                _state((2, 0), ground_xy=(2, 0)),
            ],
        },
        {
            'actor_id': 'B',
            'states': [
                _state((2, 0), ground_xy=(2, 0)),
                _state((1, 0), ground_xy=(1, 0)),
            ],
            'route_options': [[
                _state((2, 1), ground_xy=(2, 1)),
                _state((1, 1), ground_xy=(1, 1)),
            ]],
        },
    ])

    assert result['collision_free'] is True
    assert result['actors'][1]['route_option_index'] == 1
    assert result['actors'][1]['pre_spawn_delay_ticks'] == 0
    assert result['active_wait_ticks_total'] == 0
