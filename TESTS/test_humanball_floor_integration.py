from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_floor_assignment_anchors_humanball_to_resolved_human_top_left():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    cid = core.resolve_character_id(0)
    by_ws, _ = core.work_seats._resolve_floor_assignment_data(
        'floor06',
        [{'workstation_id': 'ws1', 'character_id': cid, 'subaction': 'normal_work', 'humanball_id': 'controller'}],
        frame_index=0,
    )
    data = by_ws['ws1']
    assert data['direction'] == 'SE'
    assert (data['humanball_x_px'], data['humanball_y_px']) == (
        data['human_x_px'] + 5,
        data['human_y_px'] - 13,
    )
    assert data['humanball'].size == (18, 18)
    assert data['humanball_frame_count'] == 12
    assert data['humanball_frame_ms'] == 240


def test_floor_humanball_is_hidden_on_frames_10_and_11():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    base_assignment = {'workstation_id': 'ws1', 'character': 0, 'subaction': 'normal_work'}
    popup_assignment = {**base_assignment, 'humanball_id': 'controller'}
    without_popup = core.render_floor_with_work_effects('floor06', [base_assignment], frame_index=10)
    with_popup = core.render_floor_with_work_effects('floor06', [popup_assignment], frame_index=10)
    assert with_popup.tobytes() == without_popup.tobytes()


def test_work_vfx_and_humanball_coexist_with_popup_as_final_overlay():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    assignment = {
        'workstation_id': 'ws3',
        'character': 0,
        'subaction': 'normal_work',
        'effect_id': 'thunder_cloud',
        'humanball_id': 'controller',
    }
    frame = core.render_floor_with_work_effects('floor06', [assignment], frame_index=0)

    cid = core.resolve_character_id(0)
    by_ws, _ = core.work_seats._resolve_floor_assignment_data(
        'floor06',
        [{**assignment, 'character_id': cid, 'character': 0}],
        frame_index=0,
    )
    data = by_ws['ws3']
    icon = data['humanball']
    ix, iy = 2, 5
    assert icon.getpixel((ix, iy))[3] == 255
    assert frame.getpixel((data['humanball_x_px'] + ix, data['humanball_y_px'] + iy)) == icon.getpixel((ix, iy))

    chair = core.world.load_asset(data['chair_asset_id']).convert('RGBA')
    effect = data['effect']
    target = None
    for cy in range(chair.height):
        for cx in range(chair.width):
            if chair.getpixel((cx, cy))[3] == 0:
                continue
            hx = data['chair_x_px'] + cx - data['human_x_px']
            hy = data['chair_y_px'] + cy - data['human_y_px']
            if 0 <= hx < data['human'].width and 0 <= hy < data['human'].height and data['human'].getpixel((hx, hy))[3] > 0:
                continue
            ex = data['chair_x_px'] + cx - data['effect_x_px']
            ey = data['chair_y_px'] + cy - data['effect_y_px']
            if 0 <= ex < effect.width and 0 <= ey < effect.height and effect.getpixel((ex, ey))[3] > 0:
                target = (data['chair_x_px'] + cx, data['chair_y_px'] + cy, chair.getpixel((cx, cy)))
                break
        if target is not None:
            break
    assert target is not None
    x, y, chair_rgba = target
    assert frame.getpixel((x, y)) == chair_rgba
