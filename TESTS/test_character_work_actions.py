from __future__ import annotations

from PIL import Image

from VALIDATION._common import resolve_root

ROOT = resolve_root(anchor=__file__)

from CHARACTER.RUNTIME.character_system import CharacterSystem
from CHARACTER.RUNTIME.frame_rules import load_frame_registry


EXPECTED_WORK = {
    'SE': {
        'normal_work': ['M20', 'M21'],
        'turn_side_sw': ['M22', 'M42'],
        'turn_side_ne': ['M23', 'M43'],
        'happy': ['M24'],
    },
    'SW': {
        'normal_work': ['Mp20', 'Mp21'],
        'turn_side_se': ['Mp22', 'Mp42'],
        'turn_side_nw': ['Mp23', 'Mp43'],
        'happy': ['Mp24'],
    },
    'NW': {
        'normal_work': ['M25', 'M26'],
        'turn_side_sw': ['M27', 'M44'],
        'turn_side_ne': ['M28', 'M45'],
        'happy': ['M29'],
    },
    'NE': {
        'normal_work': ['Mp25', 'Mp26'],
        'turn_side_se': ['Mp27', 'Mp44'],
        'turn_side_nw': ['Mp28', 'Mp45'],
        'happy': ['Mp29'],
    },
}


def test_work_action_registry_is_four_way_with_fixed_head_turn_pairs():
    system = CharacterSystem(ROOT / 'CHARACTER')
    work = system.core.action_set['actions']['work']

    assert work['direction_mode'] == 'four_way'
    assert set(work['directions']) == {'NE', 'SE', 'SW', 'NW'}
    for direction, subactions in EXPECTED_WORK.items():
        actual = {
            name: payload['frames']
            for name, payload in work['directions'][direction]['subactions'].items()
        }
        assert actual == subactions

    assert work['directions']['SW']['derived_from'] == 'SE'
    assert work['directions']['NE']['derived_from'] == 'NW'
    assert len(system.list_action_requests()) == 30


def test_new_side_turn_frame_rules_keep_head_crop_and_alternate_body_crop():
    registry = load_frame_registry(ROOT / 'CHARACTER')
    frames = registry['frames']

    assert registry['render_profile']['canonical_composite_modes'] == [42, 43, 44, 45]
    for frame_id in ('M42', 'M43', 'M44', 'M45'):
        assert frames[frame_id]['included_in_standard_actions'] is True
        assert frames[frame_id]['kind'] == 'native'

    for first, second in (('M22', 'M42'), ('M23', 'M43'), ('M27', 'M44'), ('M28', 'M45')):
        assert frames[first]['face'] == frames[second]['face']
        assert frames[first]['body'] != frames[second]['body']


def test_all_four_way_work_actions_render_from_the_character_creation_facade():
    system = CharacterSystem(ROOT / 'CHARACTER')

    for direction, subactions in EXPECTED_WORK.items():
        for subaction, frame_ids in subactions.items():
            result = system.render('TP_000', 'work', direction, subaction)
            assert result.frame_ids == frame_ids
            assert all(frame.size == (32, 42) for frame in result.frames)


def test_mirrored_work_directions_flip_the_complete_resolved_character_frame():
    system = CharacterSystem(ROOT / 'CHARACTER')

    mirror_pairs = (
        ('SE', 'normal_work', 'SW', 'normal_work'),
        ('SE', 'turn_side_sw', 'SW', 'turn_side_se'),
        ('SE', 'turn_side_ne', 'SW', 'turn_side_nw'),
        ('SE', 'happy', 'SW', 'happy'),
        ('NW', 'normal_work', 'NE', 'normal_work'),
        ('NW', 'turn_side_sw', 'NE', 'turn_side_se'),
        ('NW', 'turn_side_ne', 'NE', 'turn_side_nw'),
        ('NW', 'happy', 'NE', 'happy'),
    )

    for source_direction, source_subaction, target_direction, target_subaction in mirror_pairs:
        source = system.render('TP_000', 'work', source_direction, source_subaction)
        target = system.render('TP_000', 'work', target_direction, target_subaction)
        assert len(source.frames) == len(target.frames)
        for source_frame, target_frame in zip(source.frames, target.frames):
            assert target_frame.tobytes() == source_frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
