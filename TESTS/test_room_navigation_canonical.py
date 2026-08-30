from pathlib import Path

from RUNTIME.central_core import CentralGameCore

ROOT = Path(__file__).resolve().parents[1]


def core():
    return CentralGameCore(ROOT)


def test_fine_grid_is_the_only_active_navigation_grid_contract():
    c = core()
    g = c.resolve_fine_occupancy_grid()
    assert g['profile_id'] == 'grid.iso.occupancy_fine.v1'
    assert g['tile_width_px'] == 4
    assert g['tile_height_px'] == 2
    assert g['u_step_px'] == [2, 1]
    assert g['v_step_px'] == [-2, 1]
    assert g['grid_origin_px'] == [28, 0]
    assert 'subdivision_of' not in g
    assert not (ROOT / 'WORLD/REGISTRY/grid_calibration.json').exists()
    assert not (ROOT / 'WORLD/RUNTIME/grid_core.py').exists()


def test_room_domain_family_binding_uses_f0_f1_and_f2_for_every_large_floor():
    c = core()
    assert c.resolve_room_navigation_family('floor00')['canonical_floor_id'] == 'floor00'
    assert c.resolve_room_navigation_family('floor01')['canonical_floor_id'] == 'floor01'
    assert c.resolve_room_navigation_family('floor02')['canonical_floor_id'] == 'floor02'
    assert c.resolve_room_navigation_family('floor03')['canonical_floor_id'] == 'floor02'
    assert c.resolve_room_navigation_family('floor06')['canonical_floor_id'] == 'floor02'
    assert c.resolve_room_navigation_family('floor36')['canonical_floor_id'] == 'floor02'


def test_f2_plus_resolves_same_domain_geometry_without_duplicate_registry_geometry():
    c = core()
    f2 = c.resolve_room_domain('floor02')
    f3 = c.resolve_room_domain('floor03')
    f36 = c.resolve_room_domain('floor36')
    assert f3['canonical_floor_id'] == f36['canonical_floor_id'] == 'floor02'
    assert f3['polygon_uv'] == f2['polygon_uv'] == f36['polygon_uv']
    assert f3['room_cell_count'] == f2['room_cell_count'] == f36['room_cell_count']
    assert set(c.room_navigation.domain_registry['domains']) == {'floor00', 'floor01', 'floor02'}


def test_f2_plus_portal_derives_from_f2_canonical_portal():
    c = core()
    p2 = c.resolve_portal('floor02')
    p3 = c.resolve_portal('floor03')
    assert p3['canonical_floor_id'] == 'floor02'
    assert p3['edge_uv'] == p2['edge_uv']
    assert p3['inside_cells_uv'] == p2['inside_cells_uv']
    assert p3['outside_cells_uv'] == p2['outside_cells_uv']
    assert p3['portal_id'] == 'floor03.main_exit'
    assert p3['canonical_portal_id'] == 'floor02.main_exit'


def test_active_navigation_does_not_expose_legacy_embedded_solid_or_pixel_collision_systems():
    c = core()
    assert not hasattr(c, 'embedded')
    assert not hasattr(c, 'collision')
    assert not hasattr(c, 'grid')
    assert not hasattr(c, 'resolve_embedded_solid')
    assert not hasattr(c, 'compose_floor_solid_mask')
    assert not hasattr(c, 'grid_to_pixel')
    assert not (ROOT / 'WORLD/REGISTRY/embedded_solids.json').exists()
    assert not (ROOT / 'WORLD/REGISTRY/embedded_assets.json').exists()
    assert not (ROOT / 'WORLD/REGISTRY/pixel_collision_profiles.json').exists()
    assert not (ROOT / 'WORLD/RUNTIME/embedded_solid_core.py').exists()
    assert not (ROOT / 'WORLD/RUNTIME/pixel_collision_core.py').exists()


def test_legacy_floor_solid_archive_is_external_and_active_core_only_keeps_pointer():
    import json
    assert not (ROOT / 'LEGACY_ARCHIVE').exists()
    pointer = json.load(open(ROOT / 'LEGACY_ARCHIVE_POINTER.json', encoding='utf-8'))
    assert pointer['status'] == 'EXTERNAL_ARCHIVE_INACTIVE'
    assert pointer['active_runtime'] is False
    assert pointer['navigation_dependency'] is False
    assert pointer['embedded_solid_asset_count'] == 14
    assert pointer['package'] == 'GDS_LEGACY_FLOOR_SOLID_ARCHIVE_v1.0.0.zip'
    assert len(pointer['zip_sha256']) == 64


def test_compiled_room_cells_for_f2_plus_reuse_f2_without_duplicate_files():
    c = core()
    f2 = c.resolve_room_cells('floor02')
    f5 = c.resolve_room_cells('floor05')
    assert f5['canonical_floor_id'] == 'floor02'
    assert f5['room_cell_count'] == f2['room_cell_count']
    compiled = ROOT / 'WORLD/COMPILED_NAV'
    names = sorted(p.name for p in compiled.glob('*.json'))
    assert names == [
        'floor00_room_cells.json',
        'floor01_room_cells.json',
        'floor02_room_cells.json',
    ]


def test_floor02_author_patch_updates_canonical_domain_and_narrows_portal_for_f2_plus():
    c = core()
    expected_polygon = [
        [188,45],[188,123],[217,123],[217,129],[240,157],[240,189],
        [268,189],[268,159],[271,159],[271,128],[279,128],[279,71],[217,71],[217,45],
    ]
    f2 = c.resolve_room_domain('floor02')
    f3 = c.resolve_room_domain('floor03')
    assert f2['polygon_uv'] == expected_polygon
    assert f3['polygon_uv'] == expected_polygon
    p2 = c.resolve_portal('floor02')
    p36 = c.resolve_portal('floor36')
    assert p2['edge_uv'] == [[240,189],[268,189]]
    assert len(p2['inside_cells_uv']) == 28
    assert len(p2['outside_cells_uv']) == 28
    assert p36['edge_uv'] == p2['edge_uv']
    assert p36['inside_cells_uv'] == p2['inside_cells_uv']


def test_floor02_author_plus_v_two_extension_opens_left_connector_without_moving_portal():
    c = core()
    expected_polygon = [
        [188,45],[188,123],[217,123],[217,129],[240,157],[240,189],
        [268,189],[268,159],[271,159],[271,128],[279,128],[279,71],[217,71],[217,45],
    ]
    f2 = c.resolve_room_domain('floor02')
    f36 = c.resolve_room_domain('floor36')
    assert f2['polygon_uv'] == expected_polygon
    assert f36['polygon_uv'] == expected_polygon
    room = c.room_navigation.room_cell_set('floor02')
    # The two restored +V rows directly below the old v=121 edge are now room.
    assert all((u, v) in room for u in range(188, 217) for v in (121, 122))
    assert c.resolve_portal('floor02')['edge_uv'] == [[240,189],[268,189]]


def test_floor02_compiled_mask_matches_patched_domain_and_f2_plus_reuses_it():
    c = core()
    f2 = c.resolve_room_cells('floor02')
    f8 = c.resolve_room_cells('floor08')
    assert f8['canonical_floor_id'] == 'floor02'
    assert f8['room_cell_count'] == f2['room_cell_count']
    assert f2['portal_inside_cells_uv'] == [[u,188] for u in range(240,268)]
    assert f2['portal_outside_cells_uv'] == [[u,189] for u in range(240,268)]


def test_room_cell_set_reads_canonical_row_runs_format_for_f2_plus():
    c = core()
    f2 = c.room_navigation.room_cell_set('floor02')
    f3 = c.room_navigation.room_cell_set('floor03')
    assert len(f2) == c.resolve_room_domain('floor02')['room_cell_count']
    assert f3 == f2
    assert (240,188) in f2
    assert (268,188) not in f2


def test_floor00_author_entry_wedge_expands_room_domain_without_changing_portal_edge():
    c = core()
    expected_polygon = [
        [190,84],[190,106],[198,106],[198,124],[267,124],[267,101],
        [279,101],[279,153],[291,153],[291,94],[272,94],[253,75],
        [214,75],[214,84],
    ]
    domain = c.resolve_room_domain('floor00')
    assert domain['polygon_uv'] == expected_polygon
    assert c.resolve_portal('floor00')['edge_uv'] == [[279,153],[291,153]]
    room = c.room_navigation.room_cell_set('floor00')
    assert (260, 86) in room
    assert (270, 92) in room


def test_floor01_author_lower_left_extension_moves_portal_and_keeps_reception_inside_room():
    c = core()
    expected_polygon = [
        [189,59],[189,118],[219,120],[220,148],[241,149],
        [251,149],[252,114],[274,115],[274,59],
    ]
    domain = c.resolve_room_domain('floor01')
    portal = c.resolve_portal('floor01')
    assert domain['polygon_uv'] == expected_polygon
    assert portal['edge_uv'] == [[220,148],[241,149]]
    room = c.room_navigation.room_cell_set('floor01')
    assert (220, 147) in room
    assert (240, 148) in room
    assert len(portal['inside_cells_uv']) == 21
    assert len(portal['outside_cells_uv']) == 21
    assert set(map(tuple, portal['inside_cells_uv'])) <= room
    assert not (set(map(tuple, portal['outside_cells_uv'])) & room)

    compiled = c.resolve_navigation_cells('floor01')
    reception = next(row for row in compiled['instances'] if row['placement_id'] == 'reception')
    reception_cells = {tuple(cell) for cell in reception['occupied_cells_uv']}
    assert reception_cells <= room
    audit = c.validate_navigation_floor('floor01')
    assert audit['outside_room_instance_count'] == 0
