from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from CHARACTER.RUNTIME.character_system import CharacterSystem
from WORLD.RUNTIME.layout_core import LayoutCore


def _manual_se(character_id: str, subaction: str, frame_index: int) -> Image.Image:
    chars = CharacterSystem(ROOT / 'CHARACTER')
    world = LayoutCore(ROOT / 'WORLD')
    human = chars.render(character_id, 'work', 'SE', subaction).frames[frame_index].convert('RGBA')
    chair = world.load_asset('chair_000.part_01')
    out = Image.new('RGBA', (58, 64), (0, 0, 0, 0))
    origin = (4, 10)
    out.alpha_composite(chair, origin)
    out.alpha_composite(human, (origin[0] + 2, origin[1] + 2))
    return out


def _manual_nw(character_id: str, subaction: str, frame_index: int) -> Image.Image:
    chars = CharacterSystem(ROOT / 'CHARACTER')
    world = LayoutCore(ROOT / 'WORLD')
    human = chars.render(character_id, 'work', 'NW', subaction).frames[frame_index].convert('RGBA')
    main = world.load_asset('chair_000.part_00')
    front = world.load_asset('chair_000.part_03')
    out = Image.new('RGBA', (40, 54), (0, 0, 0, 0))
    origin = (16, 10)
    out.alpha_composite(main, origin)
    out.alpha_composite(human, (origin[0] - 10, origin[1] - 6))
    out.alpha_composite(front, origin)
    return out


def test_se_local_seat_matches_verified_native_formula_for_all_subactions():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for subaction in ('normal_work', 'turn_side_sw', 'turn_side_ne', 'happy'):
        result = core.compose_seat('TP_000', 'chair_000', 'SE', subaction)
        assert result.viewport == (-4, -10, 54, 54)
        assert result.human_offset_from_chair_px == (2, 2)
        assert result.chair_asset_id == 'chair_000.part_01'
        assert result.foreground_asset_id is None
        for i, frame in enumerate(result.frames):
            assert frame.tobytes() == _manual_se('TP_000', subaction, i).tobytes()


def test_nw_local_seat_matches_verified_native_formula_for_all_subactions():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for subaction in ('normal_work', 'turn_side_sw', 'turn_side_ne', 'happy'):
        result = core.compose_seat('TP_000', 'chair_000', 'NW', subaction)
        assert result.viewport == (-16, -10, 24, 44)
        assert result.human_offset_from_chair_px == (-10, -6)
        assert result.chair_asset_id == 'chair_000.part_00'
        assert result.foreground_asset_id == 'chair_000.part_03'
        for i, frame in enumerate(result.frames):
            assert frame.tobytes() == _manual_nw('TP_000', subaction, i).tobytes()


def test_nw_transparent_foreground_family_is_valid():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    result = core.compose_seat('TP_000', 'chair_004', 'NW', 'normal_work')
    assert result.foreground_asset_id is None
    assert result.used_foreground is False


def test_sw_world_seat_uses_authored_part02_and_mirrored_relation_without_double_mirror():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    result = core.compose_seat('TP_000', 'chair_006', 'SW', 'normal_work')
    assert result.chair_asset_id == 'chair_006.part_02'
    assert result.human_offset_from_chair_px == (-13, 2)
    assert result.derived_from == 'SE'
    assert result.transform == 'mirror_relation_within_chair_canvas'

    chars = CharacterSystem(ROOT / 'CHARACTER')
    sw = chars.render('TP_000', 'work', 'SW', 'normal_work')
    assert result.frame_ids == sw.frame_ids
