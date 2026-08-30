from pathlib import Path

from PIL import Image

from TOOLS.render_phase8b_edge_relief_qa import Phase8BEdgeReliefQA


ROOT = Path(__file__).resolve().parents[1]


def test_edge_relief_qa_renders_real_grid_overlays_for_f0_f1_f2(tmp_path):
    qa = Phase8BEdgeReliefQA(ROOT)
    output = tmp_path / 'EDGE_RELIEF_QA'
    report = qa.generate_bundle(output)

    assert report['status'] == 'PASS'
    assert report['floors'] == ['floor00', 'floor01', 'floor02']
    assert (output / 'CONTACT_SHEETS' / 'f0_f1_f2_edge_relief_grid_contact.png').is_file()
    for floor_id in report['floors']:
        path = output / 'FLOORS' / f'{floor_id}_edge_relief_grid_overlay.png'
        assert path.is_file()
        with Image.open(path) as image:
            assert image.size == (600, 600)


def test_edge_relief_qa_reports_boundary_and_pair_relief_counts(tmp_path):
    qa = Phase8BEdgeReliefQA(ROOT)
    report = qa.generate_bundle(tmp_path / 'EDGE_RELIEF_QA')
    by_floor = {row['floor_id']: row for row in report['metrics']}

    assert by_floor['floor00']['boundary_relief_cell_count'] > 0
    assert by_floor['floor01']['chair_pair_relief_cell_count'] > 0
    assert by_floor['floor01']['chair_pair_relief_count'] == 2
    assert by_floor['floor02']['boundary_relief_cell_count'] > 0
    assert all(row['isolated_walkable_cell_count'] == 0 for row in report['metrics'])
    assert all(row['unreachable_workstation_count'] == 0 for row in report['metrics'])
