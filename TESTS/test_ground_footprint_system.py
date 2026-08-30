from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def core():
    return CentralGameCore(ROOT)


def test_central_core_exposes_ground_footprint_queries():
    c = core()
    desk = c.resolve_ground_footprint('desk_000.part_00')
    assert desk['profile_id'] == 'footprint.desk.standard'
    assert desk['outer_corners_asset_px'] == [[36, 37], [50, 44], [14, 62], [0, 55]]


def test_ceo_desk_uses_visual_orientation_without_duplicate_profile():
    c = core()
    normal = c.resolve_ground_footprint('desk_000.part_00')
    f0 = c.resolve_ground_footprint('floor00.ceo_desk')
    f1 = c.resolve_ground_footprint('floor01.ceo_desk')
    f2 = c.resolve_ground_footprint('floor02.ceo_desk')
    assert f0['profile_id'] == f1['profile_id'] == f2['profile_id'] == normal['profile_id'] == 'footprint.desk.standard'
    assert f0['derived_transform'] == 'NORMAL'
    assert f1['derived_transform'] == 'NORMAL'
    assert f2['derived_transform'] == 'FLIP_X'
    assert 'footprint.desk.mirrored' not in c.footprints.profiles


def test_visual_only_assets_have_no_ground_footprint():
    c = core()
    assert c.resolve_ground_footprint('chair_000.part_03') is None
    assert c.resolve_ground_footprint('pc_000.slot_00') is None


def test_floor00_embedded_reception_uses_canonical_asset_adjusted_anchor():
    c = core()
    f0 = c.resolve_ground_footprint('floor00.reception')
    assert f0['profile_id'] == 'footprint.reception.f0'
    assert f0['canvas_size_px'] == [43, 51]
    assert f0['outer_corners_asset_px'] == [[6, 15], [44, 34], [14, 49], [-24, 30]]


def test_floor01_reception_profile_expands_to_16_by_20_with_shifted_origin():
    c = core()
    f1 = c.resolve_ground_footprint('floor01.reception')
    assert f1['profile_id'] == 'footprint.reception.f1'
    assert f1['axes'] == {'u_cells': 16, 'v_cells': 20}
    assert f1['author_size_fine_cells'] == [20, 16]
    assert f1['outer_corners_asset_px'] == [[25, 9], [57, 25], [17, 45], [-15, 29]]


def test_world_projection_uses_asset_top_left_translation():
    c = core()
    out = c.project_ground_footprint('floor01.reception', [200, 300])
    assert out['outer_corners_world_px'] == [[225, 309], [257, 325], [217, 345], [185, 329]]


def test_fine_grid_is_available_from_central_facade():
    c = core()
    g = c.resolve_fine_occupancy_grid()
    assert g['tile_width_px'] == 4
    assert g['tile_height_px'] == 2
    assert 'subdivision_of' not in g


def test_variant_resolution_bridges_existing_spatial_variant_ids():
    c = core()
    desk = c.resolve_ground_footprint_variant('desk_002.part_00@normal')
    assert desk['asset_id'] == 'desk_002.part_00'
    assert desk['profile_id'] == 'footprint.desk.standard'
    chair = c.resolve_ground_footprint_variant('chair_000.part_01@normal')
    assert chair['profile_id'] == 'footprint.chair.standard'
    assert c.resolve_ground_footprint_variant('pc_002.slot_00@flip_x') is None
    f1 = c.resolve_ground_footprint_variant('floor01.reception@normal')
    assert f1['profile_id'] == 'footprint.reception.f1'


def test_ceo_crop_variants_keep_binding_defined_orientation():
    c = core()
    f0 = c.resolve_ground_footprint_variant('floor00.ceo_desk@crop')
    f1 = c.resolve_ground_footprint_variant('floor01.ceo_desk@crop')
    f2 = c.resolve_ground_footprint_variant('floor02.ceo_desk@crop')
    assert f0['profile_id'] == f1['profile_id'] == f2['profile_id'] == 'footprint.desk.standard'
    assert f0['derived_transform'] == 'NORMAL'
    assert f1['derived_transform'] == 'NORMAL'
    assert f2['derived_transform'] == 'FLIP_X'


def test_f2_plus_reception_footprint_origin_tracks_visual_content_padding():
    c = core()
    f2 = c.resolve_ground_footprint_variant('floor02.reception@normal')
    f3 = c.resolve_ground_footprint_variant('reception_003@normal')
    f9 = c.resolve_ground_footprint_variant('reception_009@normal')
    f11 = c.resolve_ground_footprint_variant('reception_011@normal')

    assert f2['profile_id'] == f3['profile_id'] == f9['profile_id'] == f11['profile_id'] == 'footprint.reception.f2_plus'
    assert f2['axes'] == {'u_cells': 35, 'v_cells': 23}
    assert f2['author_size_fine_cells'] == [23, 35]
    assert f2['outer_corners_asset_px'][0] == [20, 4]
    assert f3['outer_corners_asset_px'][0] == [20, 29]  # 4 + 25px transparent top
    assert f9['outer_corners_asset_px'][0] == [20, 18]  # 4 + 14px transparent top
    assert f11['outer_corners_asset_px'][0] == [20, 9]  # 4 + 5px transparent top
