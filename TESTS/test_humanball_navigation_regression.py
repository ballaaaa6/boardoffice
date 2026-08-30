from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rgba_sha(image) -> str:
    return hashlib.sha256(image.convert('RGBA').tobytes()).hexdigest()


def test_humanball_is_visual_only_and_navigation_occupancy_neutral():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)

    expected = {
        'floor00': (4129, 2212),
        'floor01': (5950, 3133),
        'floor02': (7774, 3796),
    }
    before = {}
    for floor_id, (room_count, walkable_count) in expected.items():
        room = core.resolve_room_domain(floor_id)
        nav = core.resolve_navigation_cells(floor_id)
        assert room['room_cell_count'] == room_count
        assert nav['walkable_cell_count'] == walkable_count
        before[floor_id] = (room['room_cell_count'], nav['walkable_cell_count'])

    floor_hash_before = _rgba_sha(core.render_floor('floor06'))
    core.render_floor_with_work_effects(
        'floor06',
        [{
            'workstation_id': 'ws1',
            'character': 0,
            'subaction': 'normal_work',
            'effect_id': 'coffee_energy',
            'humanball_id': 'controller',
        }],
        frame_index=0,
    )
    floor_hash_after = _rgba_sha(core.render_floor('floor06'))
    assert floor_hash_after == floor_hash_before

    for floor_id, pair in before.items():
        room = core.resolve_room_domain(floor_id)
        nav = core.resolve_navigation_cells(floor_id)
        assert (room['room_cell_count'], nav['walkable_cell_count']) == pair

    access = core.resolve_workstation_navigation_access('floor06', 'ws1')
    assert access['seat_transition_ready'] is True
    assert access['reachable_approach_cell_count'] > 0
