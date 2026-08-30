from pathlib import Path

from PIL import Image

from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore


ROOT = Path(__file__).resolve().parents[1]
F1_DEPTH_CORNERS = [[243, 368], [269, 381], [241, 395], [215, 382]]
F2_DEPTH_CORNERS = [[239, 366], [297, 395], [267, 410], [209, 381]]
F2_NAV_CORNERS = [[243, 360], [311, 394], [267, 416], [199, 382]]


def _by_id(rows):
    return {row['placement_id']: row for row in rows}


def _selected_ids(depth, floor_id, ground_xy):
    return {row['placement_id'] for row in depth.occluders_in_front(floor_id, ground_xy)}


def test_f1_and_f2_bind_render_depth_profiles_but_floor00_does_not():
    depth = WalkingDepthCore(ROOT / 'WORLD')

    f1 = _by_id(depth.resolve_occluders('floor01'))['reception']
    f2 = _by_id(depth.resolve_occluders('floor02'))['reception']

    assert f1['depth_profile_id'] == 'walking_depth.reception.f1'
    assert f1['depth_footprint_corners_world_px'] == F1_DEPTH_CORNERS
    assert f2['depth_profile_id'] == 'walking_depth.reception.f2_plus'
    assert f2['depth_footprint_corners_world_px'] == F2_DEPTH_CORNERS
    assert 'reception' not in _by_id(depth.resolve_occluders('floor00'))


def test_f2_render_depth_is_independent_from_retracted_navigation_footprint():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    reception = _by_id(depth.resolve_occluders('floor02'))['reception']

    assert reception['footprint_corners_world_px'] == F2_NAV_CORNERS
    assert reception['depth_footprint_corners_world_px'] == F2_DEPTH_CORNERS
    assert reception['depth_anchor_y_px'] == 410
    assert max(y for _, y in reception['footprint_corners_world_px']) == 416


def test_f2_front_edge_uses_character_x_instead_of_one_global_max_y():
    depth = WalkingDepthCore(ROOT / 'WORLD')

    # The profile clamps this right-side position to the edge endpoint (297,395).
    # Y=394 is behind it; Y=396 is already in front even though both are < 410.
    assert 'reception' in _selected_ids(depth, 'floor02', (310, 394))
    assert 'reception' not in _selected_ids(depth, 'floor02', (310, 396))

    # At the front apex, the local boundary is Y=410.
    assert 'reception' in _selected_ids(depth, 'floor02', (267, 409))
    assert 'reception' not in _selected_ids(depth, 'floor02', (267, 410))


def test_f1_front_edge_interpolates_across_the_reception_face():
    depth = WalkingDepthCore(ROOT / 'WORLD')

    assert depth._front_edge_y_at_x([[215, 382], [241, 395], [269, 381]], 249) == 391
    assert 'reception' in _selected_ids(depth, 'floor01', (249, 390))
    assert 'reception' not in _selected_ids(depth, 'floor01', (249, 392))


def test_f2_front_side_actor_is_not_cut_by_reception_alpha():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    human = Image.new('RGBA', (32, 42), (255, 0, 255, 255))

    behind = depth._mask_character_by_world_occluders(
        'floor02', human, (310, 394), ground_anchor_px=(16, 31)
    )
    front = depth._mask_character_by_world_occluders(
        'floor02', human, (310, 396), ground_anchor_px=(16, 31)
    )

    assert behind.getchannel('A').getextrema()[0] < 255
    assert front.getchannel('A').getextrema() == (255, 255)


def test_all_f2_family_skins_share_one_world_depth_profile():
    depth = WalkingDepthCore(ROOT / 'WORLD')
    floor_ids = [
        floor_id
        for floor_id in depth.layout.floors
        if depth.layout.floor_record(floor_id)['layout_id'] == 'layout.floor02.large'
    ]

    assert len(floor_ids) == 23
    for floor_id in floor_ids:
        reception = _by_id(depth.resolve_occluders(floor_id))['reception']
        assert reception['depth_profile_id'] == 'walking_depth.reception.f2_plus'
        assert reception['depth_footprint_corners_world_px'] == F2_DEPTH_CORNERS
        assert reception['depth_front_edge_world_px'] == [[209, 381], [267, 410], [297, 395]]
