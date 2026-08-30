from pathlib import Path

from RUNTIME.central_core import CentralGameCore

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CORNERS = [[241, 359], [311, 394], [265, 417], [195, 382]]


def _reception(core, floor_id):
    compiled = core.resolve_navigation_cells(floor_id)
    return next(row for row in compiled['instances'] if row['placement_id'] == 'reception')


def test_f2_reception_profile_is_35_by_23_after_symmetric_expansion():
    core = CentralGameCore(ROOT)
    profile = core.footprints.profile('footprint.reception.f2_plus')
    assert profile['axes'] == {'u_cells': 35, 'v_cells': 23}
    assert profile['author_size_fine_cells'] == [23, 35]
    assert len(core.footprints.local_occupied_cells('footprint.reception.f2_plus')) == 805


def test_reception_world_anchor_is_locked_across_padding_variants():
    core = CentralGameCore(ROOT)
    for floor_id in ('floor02', 'floor03', 'floor14', 'floor36'):
        row = _reception(core, floor_id)
        assert row['outer_corners_world_px'] == EXPECTED_CORNERS
        assert row['canonical_ground_anchor_world_px'] == [259, 376]
        assert row['profile_origin_offset_uv_cells'] == [-13, -4]
        assert row['navigation_anchor_policy'] == 'fixed_world_ground_anchor_independent_of_reception_visual_padding'


def test_all_23_f2_family_receptions_share_805_cells_and_identical_corners():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    for floor_id in family['family_floor_ids']:
        row = _reception(core, floor_id)
        assert len(row['occupied_cells_uv']) == 805
        assert row['outer_corners_world_px'] == EXPECTED_CORNERS


def test_f2_family_navigation_remains_valid_after_reception_expansion():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    for floor_id in family['family_floor_ids']:
        compiled = core.resolve_navigation_cells(floor_id)
        audit = core.validate_navigation_floor(floor_id)
        assert compiled['room_cell_count'] == 7942
        assert compiled['base_occupied_cell_count'] == 2083
        assert compiled['occupied_cell_count'] == 3978
        assert compiled['walkable_cell_count'] == 3964
        assert compiled['portal_inside_cell_count'] == 28
        assert audit['valid'] is True
