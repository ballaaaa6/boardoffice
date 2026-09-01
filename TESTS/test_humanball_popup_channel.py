from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_IDS = [
    'controller',
    'coin',
    'horse',
    'bench',
    'purple_bot',
    'purple_bot_body',
]
EXPECTED_SHA256 = {
    'controller': '307fe1363d14977edd0568c3cb42c6c6fa239d59a0604a8253098189d78c7ae6',
    'coin': '05486b016ef6451d0bbcc2fcd0626ac533f4d0fe1da8a5396455f05a43babf96',
    'horse': 'af17f27210cffdeb6f4338eed2e60ef6a103d32147b09ffc2faedc5382cc596b',
    'bench': '4595aea9b67eb82fe27dfd86c7405ddebd6a3bd437e1b0951cca5dc34c054ce4',
    'purple_bot': '61b32f3daa9f66fb529568494fae654a4e6d785c1d750ca745057c81ba0e32f3',
    'purple_bot_body': 'e94eb06be4eeb70e5be592780ecc794e5e2fbcf1269c0276c83951124d27a7cf',
}
NW_OFFSETS = [
    (7, -21), (8, -23), (7, -25), (6, -26), (7, -28),
    (8, -29), (7, -31), (6, -32), (7, -34), (7, -35),
]
SE_OFFSETS = [
    (5, -13), (6, -15), (5, -17), (4, -18), (5, -20),
    (6, -21), (5, -23), (4, -24), (5, -26), (5, -27),
]


def test_humanball_registry_keeps_six_source_exact_assets_separate_from_work_vfx():
    from CHARACTER.RUNTIME.character_system import CharacterSystem

    system = CharacterSystem(ROOT / 'CHARACTER')
    assert system.list_effects() and len(system.list_effects()) == 11
    assert system.list_humanballs() == EXPECTED_IDS

    asset_registry = json.loads((ROOT / 'CHARACTER' / 'ASSETS' / 'asset_registry.json').read_text(encoding='utf-8'))
    by_id = {node['asset_id']: node for node in asset_registry['assets']}
    for name in EXPECTED_IDS:
        asset_id = f'humanball.{name}'
        node = by_id[asset_id]
        path = ROOT / 'CHARACTER' / 'ASSETS' / node['path']
        assert node['dimensions'] == [18, 18]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == EXPECTED_SHA256[name]
        assert node['sha256'] == EXPECTED_SHA256[name]


def test_humanball_nw_and_se_use_locked_native_motion_with_two_hidden_frames():
    from CHARACTER.RUNTIME.character_system import CharacterSystem

    system = CharacterSystem(ROOT / 'CHARACTER')
    for direction, expected in [('NW', NW_OFFSETS), ('SE', SE_OFFSETS)]:
        result = system.render_humanball('controller', direction)
        assert result.direction == direction
        assert result.frame_ms == 240
        assert result.loop is True
        assert result.visible_frame_count == 10
        assert len(result.frames) == 12
        assert result.offsets[:10] == expected
        assert result.offsets[10:] == [None, None]
        assert all(frame is not None and frame.size == (18, 18) for frame in result.frames[:10])
        assert result.frames[10:] == [None, None]


def test_humanball_sw_derives_only_relation_from_se_and_does_not_flip_artwork():
    from CHARACTER.RUNTIME.character_system import CharacterSystem

    system = CharacterSystem(ROOT / 'CHARACTER')
    se = system.render_humanball('controller', 'SE', human_size=(32, 42))
    sw = system.render_humanball('controller', 'SW', human_size=(32, 42))
    expected_sw = [(32 - (x + 18), y) for x, y in SE_OFFSETS]

    assert sw.offsets[:10] == expected_sw
    assert sw.offsets[10:] == [None, None]
    assert sw.derived_from == 'SE'
    assert sw.transform == 'mirror_relation_x'
    assert sw.frames[0] is not None and se.frames[0] is not None
    assert sw.frames[0].tobytes() == se.frames[0].tobytes()


def test_humanball_ne_derives_only_relation_from_nw_and_does_not_flip_artwork():
    from CHARACTER.RUNTIME.character_system import CharacterSystem

    system = CharacterSystem(ROOT / 'CHARACTER')
    nw = system.render_humanball('controller', 'NW', human_size=(32, 42))
    ne = system.render_humanball('controller', 'NE', human_size=(32, 42))
    expected_ne = [(32 - (x + 18), y) for x, y in NW_OFFSETS]

    assert ne.offsets[:10] == expected_ne
    assert ne.offsets[10:] == [None, None]
    assert ne.derived_from == 'NW'
    assert ne.transform == 'mirror_relation_x'
    assert ne.frames[0] is not None and nw.frames[0] is not None
    assert ne.frames[0].tobytes() == nw.frames[0].tobytes()



def test_humanball_registry_has_schema_and_central_facade():
    import json
    from jsonschema import Draft202012Validator
    from RUNTIME.central_core import CentralGameCore

    schema = json.loads((ROOT / 'SCHEMA' / 'CHARACTER' / 'humanball_registry.schema.json').read_text(encoding='utf-8'))
    payload = json.loads((ROOT / 'CHARACTER' / 'EFFECTS' / 'humanball_v1.json').read_text(encoding='utf-8'))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    core = CentralGameCore(ROOT)
    assert core.list_humanballs() == EXPECTED_IDS
    result = core.render_humanball('controller', 'NW')
    assert result.offsets[0] == (7, -21)
