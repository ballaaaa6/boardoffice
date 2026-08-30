from pathlib import Path

from TOOLS.render_phase8b_floor00_movement import Phase8BFloor00MovementQA


ROOT = Path(__file__).resolve().parents[1]


def test_route_definitions_cover_near_distant_and_workstation_approach():
    qa = Phase8BFloor00MovementQA(ROOT)
    routes = qa.resolve_routes()

    assert [route['route_id'] for route in routes] == [
        'near_open_target',
        'distant_target',
        'workstation_approach',
    ]
    assert all(route['floor_id'] == 'floor00' for route in routes)
    assert routes[2]['workstation_id'] == 'ws4'


def test_generate_bundle_writes_three_debug_images_three_gifs_and_smoke_report(tmp_path):
    qa = Phase8BFloor00MovementQA(ROOT)
    result = qa.generate_bundle(tmp_path / 'phase8b')

    assert result['status'] == 'PASS'
    assert len(result['routes']) == 3
    for route in result['routes']:
        assert Path(route['debug_png']).is_file()
        assert Path(route['motion_gif']).is_file()
        assert route['path_cell_count'] > 1
        assert route['segment_count'] >= 1
    smoke = result['cross_floor_smoke']
    assert set(smoke) == {'floor00', 'floor01', 'floor02', 'floor36'}
    assert all(row['status'] == 'PASS' for row in smoke.values())
    assert Path(result['report_json']).is_file()


def test_movement_preview_compositor_uses_walking_depth_runtime(monkeypatch):
    qa = Phase8BFloor00MovementQA(ROOT)
    called = {}

    def fake_composite(floor_id, sprite, ground_xy, *, ground_anchor_px):
        called['floor_id'] = floor_id
        called['ground_xy'] = ground_xy
        called['ground_anchor_px'] = ground_anchor_px
        return qa.core.render_floor(floor_id).convert('RGBA')

    monkeypatch.setattr(qa.core.walking_depth, 'composite_character', fake_composite)
    sprite = qa.core.render_character(0, 'idle', 'NE').frames[0]
    qa._composite_character('floor00', sprite, (292.0, 437.0))

    assert called['floor_id'] == 'floor00'
    assert called['ground_xy'] == (292.0, 437.0)
    assert called['ground_anchor_px'] == qa.movement.GROUND_ANCHOR_PX
