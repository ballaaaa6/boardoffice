from __future__ import annotations

from VALIDATION._common import resolve_root

ROOT = resolve_root(anchor=__file__)


def test_verified_se_and_nw_profiles_and_derived_sw_ne_offsets():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    se = core.resolve_profile('SE')
    nw = core.resolve_profile('NW')
    sw = core.resolve_profile('SW')
    ne = core.resolve_profile('NE')

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

    assert ne['mode'] == 'derived'
    assert ne['derived_from'] == 'NW'
    assert ne['standalone_transform'] == 'FLIP_LEFT_RIGHT'
    assert ne['standalone_transform_scope'] == 'complete_workstation_composite'
    assert ne['world_chair_role'] == 'part_00'
    assert ne['world_chair_foreground_role'] == 'part_03'
    assert ne['world_component_derivation'] == 'mirror_relation_within_chair_canvas'
    assert core.resolve_world_offset('NE', chair_size=(21, 32), human_size=(32, 42)) == (-1, -6)


def test_visual_offsets_are_not_gameplay_seat_anchors():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    for direction in ('SE', 'NW', 'SW', 'NE'):
        p = core.resolve_profile(direction)
        assert 'seat_anchor' not in p
        assert 'approach_anchor' not in p
        assert 'exit_anchor' not in p


def test_turn_side_mapping_uses_canonical_uv_axes_and_target_idle_directions():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)

    assert core.contract['axis_direction_convention'] == {
        'U+': {'axis': 'U', 'sign': '+', 'direction': 'SE', 'uv_delta': [1, 0]},
        'U-': {'axis': 'U', 'sign': '-', 'direction': 'NW', 'uv_delta': [-1, 0]},
        'V+': {'axis': 'V', 'sign': '+', 'direction': 'SW', 'uv_delta': [0, 1]},
        'V-': {'axis': 'V', 'sign': '-', 'direction': 'NE', 'uv_delta': [0, -1]},
    }
    assert core.contract['supported_subactions'] == [
        'normal_work', 'turn_side_sw', 'turn_side_ne',
        'turn_side_se', 'turn_side_nw', 'happy',
    ]
    work_actions = core.characters.core.action_set['actions']['work']['directions']
    assert list(work_actions['SE']['subactions']) == [
        'normal_work', 'turn_side_sw', 'turn_side_ne', 'happy'
    ]
    assert list(work_actions['SW']['subactions']) == [
        'normal_work', 'turn_side_se', 'turn_side_nw', 'happy'
    ]
    assert list(work_actions['NW']['subactions']) == [
        'normal_work', 'turn_side_sw', 'turn_side_ne', 'happy'
    ]
    assert work_actions['NE']['source'] == 'derived'
    assert work_actions['NE']['derived_from'] == 'NW'
    assert list(work_actions['NE']['subactions']) == [
        'normal_work', 'turn_side_se', 'turn_side_nw', 'happy'
    ]

    expected = {
        'SE': {
            'turn_side_sw': ('V+', 'SW', [0, 1]),
            'turn_side_ne': ('V-', 'NE', [0, -1]),
        },
        'SW': {
            'turn_side_se': ('U+', 'SE', [1, 0]),
            'turn_side_nw': ('U-', 'NW', [-1, 0]),
        },
        'NW': {
            'turn_side_sw': ('V+', 'SW', [0, 1]),
            'turn_side_ne': ('V-', 'NE', [0, -1]),
        },
        'NE': {
            'turn_side_se': ('U+', 'SE', [1, 0]),
            'turn_side_nw': ('U-', 'NW', [-1, 0]),
        },
    }

    for work_direction, expected_sides in expected.items():
        mapping = core.resolve_turn_side_mapping(work_direction)
        assert mapping['work_direction'] == work_direction
        for subaction, (axis_direction, target, uv_delta) in expected_sides.items():
            entry = mapping[subaction]
            assert entry['axis_direction'] == axis_direction
            assert entry['target_idle_direction'] == target
            assert entry['axis_delta_uv'] == uv_delta
            assert entry['direction'] == work_direction
            assert entry['action'] == 'work'
            assert entry['subaction'] == subaction


def test_turn_side_can_be_selected_from_partner_relative_idle_direction():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)

    assert core.resolve_turn_side_for_target('SE', 'SW')['subaction'] == 'turn_side_sw'
    assert core.resolve_turn_side_for_target('SE', 'NE')['subaction'] == 'turn_side_ne'
    assert core.resolve_turn_side_for_target('SW', 'SE')['subaction'] == 'turn_side_se'
    assert core.resolve_turn_side_for_target('SW', 'NW')['subaction'] == 'turn_side_nw'
    assert core.resolve_turn_side_for_target('NW', 'SW')['subaction'] == 'turn_side_sw'
    assert core.resolve_turn_side_for_target('NW', 'NE')['subaction'] == 'turn_side_ne'
    assert core.resolve_turn_side_for_target('NE', 'SE')['subaction'] == 'turn_side_se'
    assert core.resolve_turn_side_for_target('NE', 'NW')['subaction'] == 'turn_side_nw'

    import pytest

    with pytest.raises(ValueError, match='does not have a direction-named turn mapping'):
        core.resolve_turn_side_for_target('SE', 'SE')


def test_chair_family_resolver_handles_present_and_transparent_parts():
    from WORLD.RUNTIME.chair_family_core import ChairFamilyCore

    chairs = ChairFamilyCore(ROOT / 'WORLD')
    assert chairs.infer_family_from_asset_id('chair_006.part_01') == 'chair_006'
    assert chairs.resolve_part_asset('chair_006', 'part_00') == 'chair_006.part_00'
    assert chairs.resolve_part_asset('chair_006', 'part_03') == 'chair_006.part_03'
    assert chairs.resolve_part_asset('chair_004', 'part_03') is None
