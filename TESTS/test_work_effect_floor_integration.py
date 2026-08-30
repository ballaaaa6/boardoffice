from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_sw_effect_world_position_matches_mirrored_work_local_contract():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    effect_pos, char_pos = core._effect_local_offsets('SW', human_size=(32, 42), effect_size=(33, 65))
    assert effect_pos == (7, 0)
    assert char_pos == (4, 27)


def test_floor06_effect_underlay_stays_behind_authored_chair_pixels():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    seat = core.resolve_work_seat('floor06', 'ws3')
    chair = core.world.load_asset(seat['chair_asset_id']).convert('RGBA')
    human = core.render_character(0, 'work', seat['direction'], 'normal_work').frames[0].convert('RGBA')
    effect = core.characters.render_effect('thunder_cloud', seat['direction']).frames[0].convert('RGBA')
    dx, dy = core.work_seats.resolve_world_offset(seat['direction'], chair_size=chair.size, human_size=human.size)
    human_x = seat['chair_x_px'] + dx
    human_y = seat['chair_y_px'] + dy
    effect_x, effect_y = core.work_seats.resolve_effect_world_position(
        seat['direction'],
        human_top_left_px=(human_x, human_y),
        human_size=human.size,
        effect_size=effect.size,
    )

    target = None
    for cy in range(chair.height):
        for cx in range(chair.width):
            if chair.getpixel((cx, cy))[3] == 0:
                continue
            hx = cx - dx
            hy = cy - dy
            if 0 <= hx < human.width and 0 <= hy < human.height and human.getpixel((hx, hy))[3] > 0:
                continue
            ex = seat['chair_x_px'] + cx - effect_x
            ey = seat['chair_y_px'] + cy - effect_y
            if 0 <= ex < effect.width and 0 <= ey < effect.height and effect.getpixel((ex, ey))[3] > 0:
                target = (seat['chair_x_px'] + cx, seat['chair_y_px'] + cy, chair.getpixel((cx, cy)))
                break
        if target is not None:
            break
    assert target is not None, 'expected a chair/effect overlap pixel not covered by human'

    x, y, chair_rgba = target
    frame = core.render_floor_with_work_effects(
        'floor06',
        [{'workstation_id': 'ws3', 'character': 0, 'subaction': 'normal_work', 'effect_id': 'thunder_cloud'}],
        frame_index=0,
    )
    assert frame.getpixel((x, y)) == chair_rgba


def test_central_facade_renders_floor_with_effects():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    scene = core.render_floor_with_work_effects(
        'floor06',
        [{'workstation_id': 'ws1', 'character': 0, 'subaction': 'normal_work', 'effect_id': 'coffee_energy'}],
        frame_index=0,
    )
    assert scene.size == (600, 600)
