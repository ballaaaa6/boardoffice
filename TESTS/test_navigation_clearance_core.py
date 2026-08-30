from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def test_floor00_adds_navigation_clearance_without_changing_base_or_closure_geometry():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor00')

    assert compiled['base_occupied_cell_count'] == 710
    assert compiled['closure_cell_count'] == 116
    assert compiled['clearance_cell_count'] > 0

    clearance = {tuple(cell) for cell in compiled['clearance_cells_uv']}
    walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}

    # Four fine cells of desk clearance should block cells immediately outside
    # the authored ws1 desk footprint without changing that base footprint.
    for cell in ((227, 90), (228, 90), (229, 90), (230, 90)):
        assert cell in clearance
        assert cell not in walkable

    desk_rule = core.navigation_occupancy.clearance.rules['desk']['expand_cells']
    chair_rule = core.navigation_occupancy.clearance.rules['chair']['expand_cells']
    assert desk_rule == {'u_minus': 4, 'u_plus': 4, 'v_minus': 4, 'v_plus': 4}
    assert chair_rule == {'u_minus': 4, 'u_plus': 4, 'v_minus': 4, 'v_plus': 4}


def test_floor00_preserves_one_reachable_seat_ingress_gate_per_workstation():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor00')

    protected = {tuple(cell) for cell in compiled['protected_ingress_cells_uv']}
    occupied = {tuple(cell) for cell in compiled['occupied_cells_uv']}
    walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}

    workstation_ids = set(core.world.floor_layout('floor00')['workstation_groups'])
    protected_rows = compiled['protected_ingress']
    assert {row['workstation_id'] for row in protected_rows} == workstation_ids
    assert len(protected_rows) == len(workstation_ids)
    assert len(protected) == len(workstation_ids)
    assert protected <= walkable
    assert not (protected & occupied)

    for workstation_id in workstation_ids:
        access = core.resolve_workstation_navigation_access('floor00', workstation_id)
        reachable = {tuple(cell) for cell in access['reachable_approach_cells_uv']}
        gate = next(
            tuple(row['cell_uv'])
            for row in protected_rows
            if row['workstation_id'] == workstation_id
        )
        assert gate in reachable, (workstation_id, gate, sorted(reachable))


def test_clearance_is_navigation_only_and_does_not_change_walking_depth_anchors():
    core = CentralGameCore(ROOT)
    rows = {row['placement_id']: row for row in core.walking_depth.resolve_occluders('floor00')}

    assert rows['ws1_desk']['depth_anchor_y_px'] == 337
    assert rows['ws1_chair_main']['depth_anchor_y_px'] == 315
    assert rows['ws3_desk']['depth_anchor_y_px'] == 345
    assert rows['ws3_chair_main']['depth_anchor_y_px'] == 344


def test_clearance_keeps_all_floors_portal_connected_and_workstations_reachable():
    core = CentralGameCore(ROOT)
    for floor_id in core.world.floors:
        audit = core.validate_navigation_floor(floor_id)
        assert audit['outside_room_instance_count'] == 0, floor_id
        assert audit['outside_room_closure_count'] == 0, floor_id
        assert audit['portal_overlap_cell_count'] == 0, floor_id
        assert audit['isolated_walkable_cell_count'] == 0, floor_id
        for workstation_id in core.world.floor_layout(floor_id)['workstation_groups']:
            access = core.resolve_workstation_navigation_access(floor_id, workstation_id)
            assert access['reachable_approach_cell_count'] > 0, (floor_id, workstation_id)
            assert access['seat_transition_ready'] is True, (floor_id, workstation_id)


def test_chair_clearance_profile_declares_boundary_and_pair_relief_rules():
    core = CentralGameCore(ROOT)
    chair_rule = core.navigation_occupancy.clearance.rules['chair']
    assert chair_rule['boundary_relief_cells'] == 2
    assert chair_rule['pair_overlap_relief_cells'] == 1
    assert chair_rule['pair_target_corridor_cells'] == 2


def test_chairs_touching_room_boundary_reduce_only_the_facing_clearance_side():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor02')
    rows = compiled['boundary_relief_records']

    by_chair = {row['source_placement_id']: row for row in rows}
    assert by_chair['ceo_chair']['relieved_directions']['v_minus'] == 2
    assert by_chair['ws1_chair_main']['relieved_directions']['u_minus'] == 2
    assert by_chair['ws2_chair_main']['relieved_directions']['u_minus'] == 2

    for row in rows:
        for direction, amount in row['relieved_directions'].items():
            assert amount == 2, (row['source_placement_id'], direction, amount)


def test_different_furniture_islands_with_touching_chair_buffers_open_two_cell_corridor_symmetrically():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor01')
    rows = compiled['chair_pair_relief_records']

    pairs = {
        tuple(sorted(row['chair_placement_ids'])): row
        for row in rows
    }
    pair_a = pairs[tuple(sorted(('ws3_chair_main', 'ws5_chair_main')))]
    pair_b = pairs[tuple(sorted(('ws4_chair_main', 'ws6_chair_main')))]

    for row in (pair_a, pair_b):
        assert row['relief_cells_per_chair'] == 1
        assert row['target_corridor_cells'] == 2
        assert row['corridor_width_cells'] >= 2
        assert row['same_furniture_island'] is False

    # These two pairs face each other along U, so each side gives back one cell.
    assert pair_a['first_direction'] in {'u_minus', 'u_plus'}
    assert pair_a['second_direction'] in {'u_minus', 'u_plus'}
    assert pair_a['first_direction'] != pair_a['second_direction']


def test_relief_never_removes_base_footprints_or_semantic_closures():
    core = CentralGameCore(ROOT)
    for floor_id in ('floor00', 'floor01', 'floor02'):
        compiled = core.resolve_navigation_cells(floor_id)
        base = {tuple(cell) for cell in compiled['base_occupied_cells_uv']}
        closure = {tuple(cell) for cell in compiled['closure_cells_uv']}
        occupied = {tuple(cell) for cell in compiled['occupied_cells_uv']}
        assert base <= occupied, floor_id
        assert closure <= occupied, floor_id
        assert not (base & {tuple(cell) for cell in compiled['boundary_relief_cells_uv']}), floor_id
        assert not (closure & {tuple(cell) for cell in compiled['chair_pair_relief_cells_uv']}), floor_id


def test_floor01_ceo_chair_disables_only_u_minus_clearance_side():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor01')
    record = next(
        row for row in compiled['clearance_records']
        if row['source_placement_id'] == 'ceo_chair'
    )
    assert record['expand_cells']['u_minus'] == 0
    assert record['default_expand_cells']['u_minus'] == 0
    assert record['expand_cells']['u_plus'] > 0
    assert record['expand_cells']['v_minus'] > 0
    assert record['expand_cells']['v_plus'] > 0
