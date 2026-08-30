from pathlib import Path

import pytest

from RUNTIME.central_core import CentralGameCore
from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore


ROOT = Path(__file__).resolve().parents[1]


CEO_CASES = {
    'floor00': {
        'profile_id': 'walking_depth.ceo_desk.f0',
        'front_edge': [[226, 306], [240, 313], [276, 295]],
        'depth_corners': [[262, 288], [276, 295], [240, 313], [226, 306]],
        'navigation_corners': [[262, 288], [276, 295], [240, 313], [226, 306]],
        'boundary_xy': (240, 313),
        'walkable_front': ((213, 98), (258, 312)),
    },
    'floor01': {
        'profile_id': 'walking_depth.ceo_desk.f1',
        'front_edge': [[261, 282], [275, 289], [311, 271]],
        'depth_corners': [[297, 264], [311, 271], [275, 289], [261, 282]],
        'navigation_corners': [[297, 264], [311, 271], [275, 289], [261, 282]],
        'boundary_xy': (275, 289),
        'walkable_front': ((210, 77), (294, 288)),
    },
    'floor02': {
        'profile_id': 'walking_depth.ceo_desk.f2_plus',
        'front_edge': [[293, 263], [329, 281], [343, 274]],
        'depth_corners': [[307, 256], [293, 263], [329, 281], [343, 274]],
        'navigation_corners': [[307, 256], [293, 263], [329, 281], [343, 274]],
        'boundary_xy': (329, 281),
        'walkable_front': ((205, 69), (300, 275)),
    },
}


def _by_id(rows):
    return {row['placement_id']: row for row in rows}


@pytest.mark.parametrize('floor_id', list(CEO_CASES))
def test_ceo_desk_uses_layout_bound_front_edge_and_pc_inherits(floor_id):
    case = CEO_CASES[floor_id]
    core = CentralGameCore(ROOT)
    rows = _by_id(core.walking_depth.resolve_occluders(floor_id))

    desk = rows['ceo_desk_cell2']
    pc = rows['ceo_pc']

    assert desk['depth_profile_id'] == case['profile_id']
    assert desk['depth_mode'] == 'ground_front_envelope'
    assert desk['depth_footprint_corners_world_px'] == case['depth_corners']
    assert desk['depth_front_edge_world_px'] == case['front_edge']
    assert pc['depth_mode'] == 'inherit_workstation_desk'
    assert pc['depth_profile_id'] == case['profile_id']
    assert pc['depth_source_placement_id'] == 'ceo_desk_cell2'
    assert pc['depth_front_edge_world_px'] == case['front_edge']

    navigation_row = next(
        row
        for row in core.resolve_navigation_cells(floor_id)['instances']
        if row['placement_id'] == 'ceo_desk_cell2'
    )
    assert navigation_row['outer_corners_world_px'] == case['navigation_corners']

    # Standard desks/chairs remain on the legacy scalar fallback until a
    # separate visual audit proves they need a front-edge profile.
    assert rows['ws1_desk']['depth_profile_id'] is None
    assert rows['ws1_chair_main']['depth_profile_id'] is None


@pytest.mark.parametrize('floor_id', list(CEO_CASES))
def test_ceo_front_edge_controls_desk_and_pc_at_boundary(floor_id):
    case = CEO_CASES[floor_id]
    depth = WalkingDepthCore(ROOT / 'WORLD')
    x, y = case['boundary_xy']

    behind = {
        row['placement_id']
        for row in depth.occluders_in_front(floor_id, (x, y - 1))
    }
    exactly_on_edge = {
        row['placement_id']
        for row in depth.occluders_in_front(floor_id, (x, y))
    }

    assert {'ceo_desk_cell2', 'ceo_pc'} <= behind
    assert 'ceo_desk_cell2' not in exactly_on_edge
    assert 'ceo_pc' not in exactly_on_edge


@pytest.mark.parametrize('floor_id', list(CEO_CASES))
def test_known_walkable_ceo_front_points_are_not_masked_by_desk_or_pc(floor_id):
    case = CEO_CASES[floor_id]
    depth = WalkingDepthCore(ROOT / 'WORLD')
    uv, ground_xy = case['walkable_front']

    assert depth.occupancy.is_walkable(floor_id, *uv)
    front_y = depth._front_edge_y_at_x(
        case['front_edge'], float(ground_xy[0])
    )
    assert front_y < ground_xy[1]

    selected = {
        row['placement_id']
        for row in depth.occluders_in_front(floor_id, ground_xy)
    }
    assert 'ceo_desk_cell2' not in selected
    assert 'ceo_pc' not in selected
