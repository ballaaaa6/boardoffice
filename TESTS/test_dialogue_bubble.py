from pathlib import Path
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from CHARACTER.RUNTIME.character_system import CharacterSystem
from CHARACTER.RUNTIME.dialogue_bubble import DialogueBubbleError
from CHARACTER.RUNTIME.dialogue_content import DialogueContentError


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_ROOT = ROOT / 'CHARACTER'
TEST_TEXT = 'hello world..!?'


def test_project_dialogue_line_is_loaded_from_utf8_csv():
    system = CharacterSystem(CHARACTER_ROOT)

    line = system.resolve_dialogue_line('hello_world_test')

    assert line.dialogue_id == 'hello_world_test'
    assert line.locale == 'en'
    assert line.line_index == 0
    assert line.speaker_role == 'speaker'
    assert line.text == TEST_TEXT


def test_dialogue_content_rejects_unknown_line():
    system = CharacterSystem(CHARACTER_ROOT)

    with pytest.raises(DialogueContentError, match='Unknown dialogue line'):
        system.resolve_dialogue_line('does_not_exist')


def test_fukidashi_base_exposes_only_authorized_whole_bubbles():
    system = CharacterSystem(CHARACTER_ROOT)

    assert system.list_dialogue_bubbles() == ['BB1', 'BB2', 'BB3', 'BB4', 'BB6']
    assert system.dialogue_bubbles.selection_order == ['BB4', 'BB3', 'BB6', 'BB2', 'BB1']

    with pytest.raises(DialogueBubbleError, match='BB5'):
        system.dialogue_bubbles.get_bubble('BB5')


def test_text_is_measured_in_rendered_pixels_and_smallest_fitting_bubble_is_selected():
    system = CharacterSystem(CHARACTER_ROOT)

    metrics = system.measure_dialogue_text(TEST_TEXT)
    hello_metrics = system.measure_dialogue_text('Hello!!')

    assert metrics.advance_width_px == 62
    assert hello_metrics.advance_width_px == 28
    assert system.select_dialogue_bubble('Hello!!').bubble_id == 'BB3'
    assert system.select_dialogue_bubble(TEST_TEXT).bubble_id == 'BB1'


def test_thai_uses_thai_runs_and_english_font_for_ascii_symbols():
    system = CharacterSystem(CHARACTER_ROOT)

    metrics = system.measure_dialogue_text('หิวข้าวจัง..!', locale='th')

    assert metrics.advance_width_px == 42
    assert system.select_dialogue_bubble('หิวข้าวจัง..!', locale='th').bubble_id == 'BB2'


def test_dialogue_bubble_rejects_unwrappable_overflow_and_newlines():
    system = CharacterSystem(CHARACTER_ROOT)

    with pytest.raises(DialogueBubbleError, match='cannot fit'):
        system.select_dialogue_bubble('x' * 100)
    with pytest.raises(DialogueBubbleError, match='one line'):
        system.select_dialogue_bubble('hello\nworld')


def test_bubble_is_anchored_to_visible_head_and_moves_with_actor():
    system = CharacterSystem(CHARACTER_ROOT)

    first = system.render_dialogue_bubble_for_frame(
        'RND_F_004', 'M0', TEST_TEXT, actor_top_left=(74, 68)
    )
    moved = system.render_dialogue_bubble_for_frame(
        'RND_F_004', 'M0', TEST_TEXT, actor_top_left=(84, 68)
    )
    bobbed = system.render_dialogue_bubble_for_frame(
        'RND_F_004', 'M1', TEST_TEXT, actor_top_left=(74, 68)
    )

    assert first.bubble_id == 'BB1'
    assert first.image.size == (71, 20)
    assert first.head_anchor == (86, 68)
    assert first.bubble_top_left == (51, 48)
    assert first.bubble_tail_global == (86, 67)
    assert moved.bubble_top_left == (61, 48)
    assert moved.bubble_tail_global == (96, 67)
    assert bobbed.bubble_top_left == (51, 49)
    assert bobbed.bubble_tail_global == (86, 68)


def test_dialogue_id_can_drive_frame_presentation_without_manual_text_lookup():
    system = CharacterSystem(CHARACTER_ROOT)

    result = system.render_dialogue_line_for_frame(
        'RND_F_004', 'M0', 'hello_world_test', actor_top_left=(74, 68)
    )

    assert result.text == TEST_TEXT
    assert result.bubble_id == 'BB1'


def test_central_facade_exposes_presentation_without_movement_coordination():
    from RUNTIME.central_core import CentralGameCore

    central = CentralGameCore(ROOT)
    result = central.render_dialogue_bubble_for_character(
        'RND_F_004', 'M0', TEST_TEXT, actor_top_left=(74, 68)
    )

    assert result.bubble_id == 'BB1'
    assert result.frame_id == 'M0'
    assert result.actor_top_left == (74, 68)


def test_central_resolves_dialogue_asset_and_employee_identity_bridge():
    from RUNTIME.central_core import CentralGameCore

    central = CentralGameCore(ROOT)
    asset = central.resolve_asset_path('dialogue', 'dialogue.fukidashi_base')
    employee = central.list_employees(wave=1, assigned=True)[0]
    result = central.render_employee_dialogue_bubble(
        employee['employee_id'], 'M0', TEST_TEXT, actor_top_left=(74, 68)
    )

    assert asset == CHARACTER_ROOT / 'ASSETS' / 'dialogue' / 'fukidashi_base.png'
    assert result.bubble_id == 'BB1'
    assert result.actor_top_left == (74, 68)

    from_csv = central.render_dialogue_line_for_character(
        'RND_F_004', 'M0', 'hello_world_test', actor_top_left=(74, 68)
    )
    assert from_csv.text == TEST_TEXT

    employee_from_csv = central.render_employee_dialogue_line(
        employee['employee_id'], 'M0', 'hello_world_test', actor_top_left=(74, 68)
    )
    assert employee_from_csv.text == TEST_TEXT


def test_dialogue_registries_match_schemas_and_borrowed_asset_hashes():
    bubble_schema = json.loads(
        (ROOT / 'SCHEMA' / 'CHARACTER' / 'dialogue_bubble_registry.schema.json').read_text(
            encoding='utf-8'
        )
    )
    bubble_registry = json.loads(
        (CHARACTER_ROOT / 'DIALOGUE' / 'bubble_presets.json').read_text(encoding='utf-8')
    )
    font_schema = json.loads(
        (ROOT / 'SCHEMA' / 'CHARACTER' / 'dialogue_font_registry.schema.json').read_text(
            encoding='utf-8'
        )
    )
    font_registry = json.loads(
        (CHARACTER_ROOT / 'DIALOGUE' / 'dialogue_fonts.json').read_text(encoding='utf-8')
    )

    assert list(Draft202012Validator(bubble_schema).iter_errors(bubble_registry)) == []
    assert list(Draft202012Validator(font_schema).iter_errors(font_registry)) == []
    for record in font_registry['fonts'].values():
        path = CHARACTER_ROOT / record['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    source = CHARACTER_ROOT / 'ASSETS' / 'dialogue' / 'fukidashi_base.png'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == bubble_registry['source_asset']['sha256']
