from pathlib import Path

from RUNTIME.central_core import CentralGameCore

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CORNERS = [[243, 360], [311, 394], [267, 416], [199, 382]]


def _reception(core, floor_id):
    compiled = core.resolve_navigation_cells(floor_id)
    return next(row for row in compiled['instances'] if row['placement_id'] == 'reception')


def test_f2_reception_profile_is_34_by_22_after_minus_u1_retraction():
    core = CentralGameCore(ROOT)
    profile = core.footprints.profile('footprint.reception.f2_plus')
    assert profile['axes'] == {'u_cells': 34, 'v_cells': 22}
    assert profile['author_size_fine_cells'] == [22, 34]
    assert len(core.footprints.local_occupied_cells('footprint.reception.f2_plus')) == 748


def test_reception_world_anchor_is_locked_across_padding_variants():
    core = CentralGameCore(ROOT)
    for floor_id in ('floor02', 'floor03', 'floor14', 'floor36'):
        row = _reception(core, floor_id)
        assert row['outer_corners_world_px'] == EXPECTED_CORNERS
        assert row['canonical_ground_anchor_world_px'] == [259, 376]
        assert row['profile_origin_offset_uv_cells'] == [-12, -4]
        assert row['navigation_anchor_policy'] == 'fixed_world_ground_anchor_independent_of_reception_visual_padding'


def test_all_23_f2_family_receptions_share_748_cells_and_identical_corners():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    for floor_id in family['family_floor_ids']:
        row = _reception(core, floor_id)
        assert len(row['occupied_cells_uv']) == 748
        assert row['outer_corners_world_px'] == EXPECTED_CORNERS


def test_f2_family_navigation_remains_valid_after_reception_expansion():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    for floor_id in family['family_floor_ids']:
        compiled = core.resolve_navigation_cells(floor_id)
        audit = core.validate_navigation_floor(floor_id)
        assert compiled['room_cell_count'] == 7774
        assert compiled['base_occupied_cell_count'] == 2026
        assert compiled['occupied_cell_count'] == 3921
        assert compiled['walkable_cell_count'] == 3853
        assert compiled['portal_inside_cell_count'] == 28
        assert audit['valid'] is True


def test_f2_minus_u1_retraction_opens_four_neighbor_blue_side_connector():
    core = CentralGameCore(ROOT)
    assert core.is_walkable_cell('floor02', 233, 147)
    assert core.is_walkable_cell('floor02', 233, 148)

    start = tuple(core.resolve_portal_navigation_start('floor02'))
    goal = (230, 121)
    path = core.find_navigation_path('floor02', start, goal)['path_cells_uv']
    assert any(
        int(u) < 234 and 126 <= int(v) <= 147
        for u, v in path
    )
