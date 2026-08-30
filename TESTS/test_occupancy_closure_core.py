from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def _closure_cells(compiled):
    return {tuple(cell) for cell in compiled['closure_cells_uv']}


def test_floor00_closes_desk_desk_seam_and_workstation_desk_chair_gap():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor00')
    closures = _closure_cells(compiled)
    walkable = {tuple(cell) for cell in compiled['walkable_cells_uv']}

    # ws1_desk (u 231..237) and ws3_desk (u 239..245) leave u=238 as a
    # one-cell seam in the old occupancy. It must become supplemental occupied.
    assert (238, 90) in closures
    assert (238, 90) not in walkable

    # ws3 desk/chair leave u=246..248 over the chair's v span. The interior
    # workstation gap is not a walking corridor and must be closed.
    assert (247, 88) in closures
    assert (247, 88) not in walkable


def test_closure_records_are_semantic_and_support_multi_desk_clusters():
    core = CentralGameCore(ROOT)
    compiled = core.resolve_navigation_cells('floor00')
    rows = compiled['closures']
    desk_desk = [row for row in rows if row['closure_type'] == 'desk_desk_seam']
    desk_chair = [row for row in rows if row['closure_type'] == 'workstation_desk_chair']

    assert {tuple(row['source_placement_ids']) for row in desk_desk} == {
        ('ws1_desk', 'ws3_desk'),
        ('ws2_desk', 'ws4_desk'),
    }
    assert len(desk_chair) == len(core.world.floor_layout('floor00')['workstation_groups'])
    assert all(row['occupied_cells_uv'] for row in rows)


def test_closure_preserves_workstation_entry_access_and_portal_connectivity():
    core = CentralGameCore(ROOT)
    for floor_id in core.world.floors:
        audit = core.validate_navigation_floor(floor_id)
        assert audit['outside_room_closure_count'] == 0, floor_id
        assert audit['portal_overlap_cell_count'] == 0, floor_id
        assert audit['isolated_walkable_cell_count'] == 0, floor_id
        for workstation_id in core.world.floor_layout(floor_id)['workstation_groups']:
            access = core.resolve_workstation_navigation_access(floor_id, workstation_id)
            assert access['reachable_approach_cell_count'] > 0, (floor_id, workstation_id)
            assert access['seat_transition_ready'] is True, (floor_id, workstation_id)


def test_distant_path_never_uses_supplemental_closure_cells():
    core = CentralGameCore(ROOT)
    floor_id = 'floor00'
    start = tuple(core.resolve_portal_navigation_start(floor_id))
    goal = tuple(core.resolve_distant_navigation_target(floor_id, start))
    path = core.find_navigation_path(floor_id, start, goal)
    closures = _closure_cells(core.resolve_navigation_cells(floor_id))

    assert not ({tuple(cell) for cell in path['path_cells_uv']} & closures)
