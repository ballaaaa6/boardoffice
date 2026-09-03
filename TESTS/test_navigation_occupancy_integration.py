from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def test_navigation_occupancy_api_is_exposed():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor00')
    assert compiled['floor_id'] == 'floor00'
    assert compiled['room_cell_count'] == 4129
    assert compiled['base_occupied_cell_count'] == 710
    assert compiled['closure_cell_count'] == 116
    assert compiled['occupied_cell_count'] == 1917
    assert compiled['walkable_cell_count'] == 2212
    assert core.is_walkable_cell('floor00', *compiled['portal_inside_cells_uv'][0])


def test_navigation_occupancy_falls_back_to_source_when_disk_cache_is_absent(tmp_path):
    core = CentralGameCore(ROOT)
    core.navigation_occupancy.compiled_root = tmp_path / 'missing_occupancy_cache'

    compiled = core.resolve_navigation_cells('floor00')

    assert compiled['floor_id'] == 'floor00'
    assert compiled['room_cell_count'] == 4129
    assert compiled['base_occupied_cell_count'] == 710
    assert compiled['closure_cell_count'] == 116
    assert compiled['occupied_cell_count'] == 1917
    assert compiled['walkable_cell_count'] == 2212
    assert not core.navigation_occupancy.compiled_path('floor00').exists()


def test_approved_f0_f1_f2_counts_are_compiled():
    core = CentralGameCore(ROOT)
    expected = {
        'floor00': (4129, 1917, 2212, 12),
        'floor01': (5950, 2817, 3133, 21),
        'floor02': (7774, 3921, 3853, 28),
    }
    for floor_id, counts in expected.items():
        compiled = core.resolve_navigation_cells(floor_id)
        got = (
            compiled['room_cell_count'],
            compiled['occupied_cell_count'],
            compiled['walkable_cell_count'],
            compiled['portal_inside_cell_count'],
        )
        assert got == counts


def test_every_active_reserving_instance_is_fully_inside_room_and_off_portal():
    core = CentralGameCore(ROOT)
    for floor_id in core.world.floors:
        audit = core.validate_navigation_floor(floor_id)
        assert audit['outside_room_instance_count'] == 0, floor_id
        assert audit['portal_overlap_cell_count'] == 0, floor_id
        assert audit['isolated_walkable_cell_count'] == 0, floor_id


def test_all_workstations_have_portal_reachable_approach_cells():
    core = CentralGameCore(ROOT)
    for floor_id in core.world.floors:
        for workstation_id in core.world.floor_layout(floor_id)['workstation_groups']:
            access = core.resolve_workstation_navigation_access(floor_id, workstation_id)
            assert access['approach_cell_count'] > 0, (floor_id, workstation_id)
            assert access['reachable_approach_cell_count'] > 0, (floor_id, workstation_id)
            assert access['chair_fully_inside_room'] is True, (floor_id, workstation_id)
            assert access['seat_transition_ready'] is True, (floor_id, workstation_id)
            assert access['work_seat_direction'] in {'SE', 'SW', 'NW', 'NE'}, (floor_id, workstation_id)


def test_f2_plus_reuses_room_and_portal_geometry_but_keeps_per_floor_occupancy():
    core = CentralGameCore(ROOT)
    f2_domain = core.resolve_room_domain('floor02')['polygon_uv']
    f2_portal = core.resolve_portal('floor02')['edge_uv']
    for floor_id, rec in core.world.floors.items():
        if rec['layout_id'] != 'layout.floor02.large':
            continue
        assert core.resolve_room_domain(floor_id)['polygon_uv'] == f2_domain
        assert core.resolve_portal(floor_id)['edge_uv'] == f2_portal
        compiled = core.resolve_navigation_cells(floor_id)
        assert compiled['room_cell_count'] == 7774
        assert compiled['portal_inside_cell_count'] == 28
        assert compiled['floor_id'] == floor_id


def test_navigation_audit_covers_all_floors_and_workstations():
    from VALIDATION.self_audit_navigation_occupancy import build_audit

    report = build_audit(ROOT)
    assert report['status'] == 'PASS'
    assert report['floor_count'] == len(CentralGameCore(ROOT).world.floors)
    assert report['failed_floor_count'] == 0
    assert report['failed_workstation_count'] == 0
    assert report['rules']['active_footprints_must_be_inside_room'] is True
    assert report['rules']['active_footprints_must_not_overlap_portal'] is True
    assert report['rules']['all_walkable_cells_must_reach_portal'] is True
    assert report['rules']['workstations_need_reachable_approach_cell'] is True


def test_f2_plus_reception_world_footprint_tracks_visible_reception_base():
    core = CentralGameCore(ROOT)
    checked = []
    for floor_id, rec in core.world.floors.items():
        if rec['layout_id'] != 'layout.floor02.large':
            continue
        receptions = [
            inst for inst in core.navigation_occupancy.resolve_floor_instances(floor_id)
            if inst['object_type'] == 'reception'
        ]
        if not receptions:
            continue
        assert len(receptions) == 1, floor_id
        inst = receptions[0]
        placement = next(
            p for p in core.world.resolve_floor_placements(floor_id)
            if p['object_type'] == 'reception'
        )
        left = int(placement['visual_bounds_px']['left'])
        top = int(placement['visual_bounds_px']['top'])
        local = core.resolve_ground_footprint_variant(placement['variant_id'])
        assert local['outer_corners_asset_px'][0] == [20 + left, 4 + top], floor_id
        assert inst['outer_corners_world_px'][0] == [243, 360], floor_id
        checked.append(floor_id)
    assert 'floor02' in checked and len(checked) > 3
