from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_verified_se_and_nw_profiles_and_derived_sw_offset():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    se = core.resolve_profile('SE')
    nw = core.resolve_profile('NW')
    sw = core.resolve_profile('SW')

    assert se['mode'] == 'native_verified'
    assert se['world_chair_role'] == 'part_01'
    assert se['visual_character_offset_from_chair_px'] == [2, 2]
    assert se['composition_viewport'] == {
        'min_x': -4, 'min_y': -10, 'max_x': 54, 'max_y': 54, 'width': 58, 'height': 64
    }

    assert nw['mode'] == 'native_verified'
    assert nw['world_chair_role'] == 'part_00'
    assert nw['world_chair_foreground_role'] == 'part_03'
    assert nw['foreground_optional'] is True
    assert nw['visual_character_offset_from_chair_px'] == [-10, -6]

    assert sw['mode'] == 'derived'
    assert sw['derived_from'] == 'SE'
    assert sw['standalone_transform'] == 'FLIP_LEFT_RIGHT'
    assert sw['standalone_transform_scope'] == 'final_composite'
    assert sw['world_chair_role'] == 'part_02'
    assert core.resolve_world_offset('SW', chair_size=(21, 32), human_size=(32, 42)) == (-13, 2)


def test_visual_offsets_are_not_gameplay_seat_anchors():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for direction in ('SE', 'NW', 'SW'):
        p = core.resolve_profile(direction)
        assert 'seat_anchor' not in p
        assert 'approach_anchor' not in p
        assert 'exit_anchor' not in p


def test_chair_family_resolver_handles_present_and_transparent_parts():
    from WORLD.RUNTIME.chair_family_core import ChairFamilyCore

    chairs = ChairFamilyCore(ROOT / 'WORLD')
    assert chairs.infer_family_from_asset_id('chair_006.part_01') == 'chair_006'
    assert chairs.resolve_part_asset('chair_006', 'part_00') == 'chair_006.part_00'
    assert chairs.resolve_part_asset('chair_006', 'part_03') == 'chair_006.part_03'
    assert chairs.resolve_part_asset('chair_004', 'part_03') is None
