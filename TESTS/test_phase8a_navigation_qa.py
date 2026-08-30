from pathlib import Path

from PIL import Image

from TOOLS.phase8a_navigation_qa import Phase8ANavigationQA


ROOT = Path(__file__).resolve().parents[1]


def test_floor00_overlay_cellmap_and_metrics_match_runtime_compilation(tmp_path):
    qa = Phase8ANavigationQA(ROOT)

    overlay = qa.render_floor_overlay('floor00')
    cell_map = qa.render_cell_map('floor00')
    metrics = qa.build_floor_metrics('floor00')

    assert isinstance(overlay, Image.Image)
    assert overlay.size == (600, 600)
    assert isinstance(cell_map, Image.Image)
    assert cell_map.width > 0 and cell_map.height > 0

    compiled = qa.occupancy.compile_floor('floor00')
    assert metrics['floor_id'] == 'floor00'
    assert metrics['room_cell_count'] == compiled['room_cell_count']
    assert metrics['occupied_cell_count'] == compiled['occupied_cell_count']
    assert metrics['walkable_cell_count'] == compiled['walkable_cell_count']
    assert metrics['portal_inside_cell_count'] == compiled['portal_inside_cell_count']


def test_review_floor_set_covers_unique_families_and_selected_f2_plus_samples():
    qa = Phase8ANavigationQA(ROOT)
    floors = qa.resolve_review_floors()

    assert floors == ['floor00', 'floor01', 'floor02', 'floor03', 'floor06', 'floor36']
    assert len(floors) == len(set(floors))
    assert qa.occupancy.layout.floor_record(floors[-1])['layout_id'] == 'layout.floor02.large'


def test_floor_metrics_include_machine_qa_and_locked_counts():
    qa = Phase8ANavigationQA(ROOT)
    expected = {
        'floor00': (4129, 1917, 2212, 12),
        'floor01': (5950, 2817, 3133, 21),
        'floor02': (7942, 3978, 3964, 28),
    }
    for floor_id, counts in expected.items():
        metrics = qa.build_floor_metrics(floor_id)
        assert (
            metrics['room_cell_count'],
            metrics['occupied_cell_count'],
            metrics['walkable_cell_count'],
            metrics['portal_inside_cell_count'],
        ) == counts
        assert metrics['outside_room_instance_count'] == 0
        assert metrics['portal_overlap_cell_count'] == 0
        assert metrics['isolated_walkable_cell_count'] == 0
        assert metrics['unreachable_workstation_count'] == 0
        assert metrics['workstation_count'] > 0
        assert metrics['valid'] is True


def test_generate_review_bundle_writes_external_review_artifacts(tmp_path):
    qa = Phase8ANavigationQA(ROOT)
    output_root = tmp_path / 'GDS_PHASE8A_NAV_QA'

    result = qa.generate_review_bundle(output_root)

    assert result['status'] == 'PASS'
    assert Path(result['output_root']) == output_root.resolve()
    assert len(result['floors']) == 6
    assert (output_root / 'PHASE8A_NAVIGATION_QA.json').is_file()
    assert (output_root / 'CONTACT_SHEETS' / 'phase8a_overlay_contact.png').is_file()
    assert (output_root / 'CONTACT_SHEETS' / 'phase8a_cellmap_contact.png').is_file()
    for floor_id in qa.resolve_review_floors():
        assert (output_root / 'OVERLAY' / f'{floor_id}_navigation_overlay.png').is_file()
        assert (output_root / 'CELL_MAP' / f'{floor_id}_navigation_cellmap.png').is_file()


def test_phase8a_cli_can_run_as_a_direct_script():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / 'TOOLS' / 'phase8a_navigation_qa.py'), '--help'],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert '--output' in result.stdout
