from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_floor06_workstation_seat_resolution_uses_directional_chair_roles():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)

    se = core.resolve_workstation_seat('floor06', 'ws1')
    assert se['direction'] == 'SE'
    assert se['chair_family_id'] == 'chair_006'
    assert se['chair_asset_id'] == 'chair_006.part_01'
    assert se['chair_placement_id'] == 'ws1_chair_main'
    assert se['foreground_asset_id'] is None

    nw = core.resolve_workstation_seat('floor06', 'ws3')
    assert nw['direction'] == 'NW'
    assert nw['chair_family_id'] == 'chair_006'
    assert nw['chair_asset_id'] == 'chair_006.part_00'
    assert nw['foreground_asset_id'] == 'chair_006.part_03'
    assert nw['foreground_static_present'] is False
    assert nw['foreground_slot_id'] == 'ws3_chair_sub'
    assert nw['foreground_layer'] == 570

    sw = core.resolve_workstation_seat('floor06', 'ceo')
    assert sw['direction'] == 'SW'
    assert sw['chair_family_id'] == 'chair_006'
    assert sw['chair_asset_id'] == 'chair_006.part_02'
    assert sw['foreground_asset_id'] is None


def test_floor02_nw_reuses_existing_static_foreground_instead_of_double_drawing():
    from RUNTIME.work_seat_core import WorkSeatCore

    core = WorkSeatCore(ROOT)
    nw = core.resolve_workstation_seat('floor02', 'ws3')
    assert nw['foreground_static_present'] is True
    assert nw['foreground_placement_id'] == 'ws3_chair_sub'
    assert nw['foreground_asset_id'] == 'chair_002.part_03'


def test_floor06_se_dynamic_frame_matches_independent_manual_layer_insertion():
    from RUNTIME.work_seat_core import WorkSeatCore
    from CHARACTER.RUNTIME.character_system import CharacterSystem
    from WORLD.RUNTIME.layout_core import LayoutCore

    seat = WorkSeatCore(ROOT)
    actual = seat.render_floor_with_work(
        'floor06',
        [{'workstation_id': 'ws1', 'character_id': 'TP_000', 'subaction': 'normal_work'}],
        frame_index=0,
    )

    world = LayoutCore(ROOT / 'WORLD')
    chars = CharacterSystem(ROOT / 'CHARACTER')
    skin = world.floor_skin('floor06')
    expected = world.load_variant(skin['base_variant_id']).copy().convert('RGBA')
    human = chars.render('TP_000', 'work', 'SE', 'normal_work').frames[0].convert('RGBA')
    for placement in world.resolve_floor_placements('floor06'):
        expected.alpha_composite(world.load_variant(placement['variant_id']), (placement['x_px'], placement['y_px']))
        if placement['placement_id'] == 'ws1_chair_main':
            expected.alpha_composite(human, (placement['x_px'] + 2, placement['y_px'] + 2))

    assert actual.tobytes() == expected.tobytes()


def test_floor06_nw_dynamic_frame_inserts_recovered_foreground_at_authored_optional_layer():
    from RUNTIME.work_seat_core import WorkSeatCore
    from CHARACTER.RUNTIME.character_system import CharacterSystem
    from WORLD.RUNTIME.layout_core import LayoutCore

    seat = WorkSeatCore(ROOT)
    actual = seat.render_floor_with_work(
        'floor06',
        [{'workstation_id': 'ws3', 'character_id': 'TP_000', 'subaction': 'normal_work'}],
        frame_index=0,
    )

    world = LayoutCore(ROOT / 'WORLD')
    chars = CharacterSystem(ROOT / 'CHARACTER')
    skin = world.floor_skin('floor06')
    expected = world.load_variant(skin['base_variant_id']).copy().convert('RGBA')
    human = chars.render('TP_000', 'work', 'NW', 'normal_work').frames[0].convert('RGBA')
    front = world.load_asset('chair_006.part_03')

    events = []
    for placement in world.resolve_floor_placements('floor06'):
        events.append((placement['layer'], 0, 'static', placement))
        if placement['placement_id'] == 'ws3_chair_main':
            events.append((placement['layer'], 1, 'human', placement))
    events.append((570, 1, 'foreground', {'x_px': 278, 'y_px': 282}))

    for _, _, kind, payload in sorted(events, key=lambda e: (e[0], e[1], e[2])):
        if kind == 'static':
            expected.alpha_composite(world.load_variant(payload['variant_id']), (payload['x_px'], payload['y_px']))
        elif kind == 'human':
            expected.alpha_composite(human, (payload['x_px'] - 10, payload['y_px'] - 6))
        else:
            expected.alpha_composite(front, (payload['x_px'], payload['y_px']))

    assert actual.tobytes() == expected.tobytes()


def test_central_facade_exposes_work_seat_without_changing_legacy_work_api():
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(ROOT)
    seat = core.resolve_work_seat('floor06', 'ws3')
    assert seat['direction'] == 'NW'
    assert seat['chair_family_id'] == 'chair_006'

    composed = core.compose_work_seat(0, 'chair_006', 'NW', subaction='normal_work')
    assert composed.character_id == 'TP_000'
    assert composed.human_offset_from_chair_px == (-10, -6)

    legacy = core.render_character_at_workstation(0, 'floor06', 'ws3', subaction='normal_work')
    assert legacy.direction == 'NW'
    assert legacy.frames[0].size == (32, 42)

    scene = core.render_floor_with_work(
        'floor06',
        [{'workstation_id': 'ws3', 'character': 0, 'subaction': 'normal_work'}],
        frame_index=0,
    )
    assert scene.size == (600, 600)
