import importlib.util
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def test_phase8b_closure_qa_tool_exists_and_generates_review_bundle(tmp_path):
    spec = importlib.util.find_spec('TOOLS.render_phase8b_closure_qa')
    assert spec is not None
    from TOOLS.render_phase8b_closure_qa import Phase8BClosureQA

    qa = Phase8BClosureQA(ROOT)
    result = qa.generate_bundle(tmp_path / 'closure_qa')

    assert result['status'] == 'PASS'
    assert result['floor_id'] == 'floor00'
    assert result['closure_cell_count'] > 0
    assert result['clearance_cell_count'] > 0
    assert result['protected_ingress_cell_count'] == 5
    assert result['desk_desk_closure_count'] == 2
    assert result['workstation_desk_chair_closure_count'] == 5
    assert Path(result['overlay_png']).is_file()
    assert Path(result['detail_png']).is_file()
    assert Path(result['approach_detail_png']).is_file()
    assert Path(result['clearance_detail_png']).is_file()
    assert Path(result['distant_motion_gif']).is_file()
    with Image.open(result['overlay_png']) as im:
        assert im.size == (600, 600)
