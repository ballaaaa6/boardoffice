from pathlib import Path

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def _reception(core, floor_id):
    compiled = core.resolve_navigation_cells(floor_id)
    return next(row for row in compiled['instances'] if row['placement_id'] == 'reception'), compiled


def test_floor01_reception_expansion_keeps_navigation_valid():
    core = CentralGameCore(ROOT)
    row, compiled = _reception(core, 'floor01')
    audit = core.validate_navigation_floor('floor01')

    assert len(row['occupied_cells_uv']) == 320
    assert row['outer_corners_world_px'] == [[243, 362], [275, 378], [235, 398], [203, 382]]
    assert compiled['base_occupied_cell_count'] == 1314
    assert compiled['occupied_cell_count'] == 2817
    assert compiled['walkable_cell_count'] == 3133
    assert audit['valid'] is True


def test_floor02_family_minus_u1_retraction_keeps_navigation_valid_and_synchronized():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    expected_corners = [[243, 360], [311, 394], [267, 416], [199, 382]]
    for floor_id in family['family_floor_ids']:
        row, compiled = _reception(core, floor_id)
        audit = core.validate_navigation_floor(floor_id)
        assert len(row['occupied_cells_uv']) == 748
        assert row['outer_corners_world_px'] == expected_corners
        assert compiled['base_occupied_cell_count'] == 2026
        assert compiled['occupied_cell_count'] == 3921
        assert compiled['walkable_cell_count'] == 3853
        assert audit['valid'] is True
