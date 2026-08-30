from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from CHARACTER.RUNTIME.character_system import CharacterSystem
from WORLD.RUNTIME.layout_core import LayoutCore


def _manual_se_reference(subaction: str, frame_index: int) -> Image.Image:
    chars = CharacterSystem(ROOT / 'CHARACTER')
    world = LayoutCore(ROOT / 'WORLD')
    human = chars.render('TP_000', 'work', 'SE', subaction).frames[frame_index].convert('RGBA')
    chair = world.load_asset('chair_000.part_01')
    desk = world.load_asset('desk_000.part_00')
    pc = world.load_asset('pc_000.slot_00')
    out = Image.new('RGBA', (58, 64), (0, 0, 0, 0))
    origin = (4, 10)
    out.alpha_composite(chair, (origin[0] + 0, origin[1] + 0))
    out.alpha_composite(human, (origin[0] + 2, origin[1] + 2))
    out.alpha_composite(desk, (origin[0] + 2, origin[1] - 8))
    out.alpha_composite(pc, (origin[0] + 2, origin[1] + 3))
    return out


def test_se_reference_presentation_matches_verified_assembler_formula():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for subaction in ('normal_work', 'turn_side_a', 'turn_side_b', 'happy'):
        result = core.compose_reference_presentation('TP_000', 'SE', subaction)
        assert result.direction == 'SE'
        assert result.viewport == (-4, -10, 54, 54)
        for i, frame in enumerate(result.frames):
            assert frame.tobytes() == _manual_se_reference(subaction, i).tobytes()


def test_nw_reference_presentation_is_native_seat_formula():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    native = core.compose_seat('TP_000', 'chair_000', 'NW', 'normal_work')
    ref = core.compose_reference_presentation('TP_000', 'NW', 'normal_work')
    assert ref.viewport == native.viewport
    assert ref.frames[0].tobytes() == native.frames[0].tobytes()
    assert ref.frames[1].tobytes() == native.frames[1].tobytes()


def test_sw_reference_presentation_is_pixel_exact_final_mirror_of_se():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for subaction in ('normal_work', 'turn_side_a', 'turn_side_b', 'happy'):
        se = core.compose_reference_presentation('TP_000', 'SE', subaction)
        sw = core.compose_reference_presentation('TP_000', 'SW', subaction)
        assert sw.derived_from == 'SE'
        assert sw.transform == 'FLIP_LEFT_RIGHT'
        assert len(sw.frames) == len(se.frames)
        for se_frame, sw_frame in zip(se.frames, sw.frames):
            expected = se_frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            assert sw_frame.tobytes() == expected.tobytes()
