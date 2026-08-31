"""Catalog boundaries: editable data, safe visibility, and atomic reload."""
import csv
import json
from pathlib import Path
import shutil

import pytest

from CHARACTER.RUNTIME.character_system import CharacterSystem
from CHARACTER.RUNTIME.dialogue_content import DialogueContentError, DialogueContentRegistry
from RUNTIME.central_core import CentralGameCore

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = (
    'dialogue_id', 'locale', 'line_index', 'speaker_role', 'text',
    'category', 'usage_scope', 'enabled', 'full_text', 'source_id', 'source_text',
)
EXAMPLES = [
    ['greet', 'en', '0', 'speaker', 'Hello!', 'greeting', 'office', 'true',
     'Hello there!', 'reference.greeting', 'Hello!'],
    ['greet', 'th', '0', 'speaker', 'สวัสดี!', 'greeting', 'office', 'true',
     'สวัสดีนะ!', 'reference.greeting', 'Hello!'],
    ['paused', 'th', '0', 'speaker', '<0>', 'tv_specific', 'template', 'false',
     '<0>', 'reference.template', '<0>'],
]


def write_csv(character_root, rows, columns=COLUMNS):
    path = character_root / 'DIALOGUE' / 'dialogue.csv'
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def editable_central(tmp_path):
    # The real CharacterSystem reads an isolated CSV/assets; the frozen world
    # stays at ROOT. No mocks, source mutation, or copied navigation caches.
    character_root = tmp_path / 'CHARACTER'
    shutil.copytree(ROOT / 'CHARACTER', character_root,
                    ignore=shutil.ignore_patterns('__pycache__'))
    write_csv(character_root, EXAMPLES)
    central = CentralGameCore(ROOT)
    central.characters = CharacterSystem(character_root)
    return central, character_root


def test_catalog_filters_language_category_scope_and_enabled_metadata(tmp_path):
    write_csv(tmp_path, EXAMPLES)
    registry = DialogueContentRegistry(tmp_path)

    rows = registry.list(locale='th-TH', category='greeting',
                         usage_scope='office', enabled_only=True)
    assert [row.dialogue_id for row in rows] == ['greet']
    payload = rows[0].as_dict()
    assert payload['text'] == 'สวัสดี!'
    assert payload['full_text'] == 'สวัสดีนะ!'
    assert payload['source_text'] == 'Hello!'
    assert payload['source_id'] == 'reference.greeting'
    assert payload['enabled'] is True
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    assert registry.list(category='not_a_category') == []
    assert registry.list(usage_scope='template', enabled_only=True) == []
    assert registry.get('paused', locale='th').enabled is False


@pytest.mark.parametrize('bad_value', ['ture', '0', 'yes'])
def test_mistyped_enabled_flag_is_not_silently_treated_as_true(tmp_path, bad_value):
    rows = [EXAMPLES[0].copy()]
    rows[0][7] = bad_value
    write_csv(tmp_path, rows)
    with pytest.raises(DialogueContentError, match='enabled'):
        DialogueContentRegistry(tmp_path)


def test_enabled_template_cannot_enter_the_plain_text_pool(tmp_path):
    rows = [EXAMPLES[2].copy()]
    rows[0][7] = 'true'
    write_csv(tmp_path, rows)
    with pytest.raises(DialogueContentError, match='markup|placeholder'):
        DialogueContentRegistry(tmp_path)


@pytest.mark.parametrize('contents', [
    'dialogue_id,locale,line_index,speaker_role,text\na,en,0,speaker,Hi!,unquoted extra\n',
    'dialogue_id,locale,line_index,speaker_role,text,enabled,enabled\na,en,0,speaker,Hi!,true,false\n',
])
def test_ambiguous_csv_columns_are_rejected_instead_of_losing_content(tmp_path, contents):
    path = tmp_path / 'DIALOGUE' / 'dialogue.csv'
    path.parent.mkdir()
    path.write_text(contents, encoding='utf-8')
    with pytest.raises(DialogueContentError, match='column|header'):
        DialogueContentRegistry(tmp_path)


def test_legacy_five_column_csv_remains_usable(tmp_path):
    write_csv(tmp_path, [EXAMPLES[0][:5]], columns=COLUMNS[:5])
    row = DialogueContentRegistry(tmp_path).get('greet')
    assert row.text == 'Hello!'
    assert row.enabled is True
    assert row.full_text == 'Hello!'


def test_reload_applies_edits_and_new_thai_category_through_central(editable_central):
    central, character_root = editable_central
    rows = [row.copy() for row in EXAMPLES]
    rows[0][4] = 'Ready!'
    rows.append(['new_break', 'th', '0', 'speaker', 'พักก่อน', 'new_category',
                 'office', 'true', 'ขอพักก่อนนะ', '', ''])
    write_csv(character_root, rows)

    assert central.resolve_dialogue_line('greet').text == 'Hello!'
    summary = central.reload_dialogue_content()
    assert summary['line_count'] == 4
    assert summary['dialogue_count'] == 3
    assert summary['locales'] == ['en', 'th']
    assert central.resolve_dialogue_line('greet').text == 'Ready!'
    selected = central.list_dialogue_lines(locale='th', category='new_category',
                                          usage_scope='office', enabled_only=True)
    assert [row['dialogue_id'] for row in selected] == ['new_break']
    employee = central.list_employees(wave=1, assigned=True)[0]
    rendered = central.render_employee_dialogue_line(
        employee['employee_id'], 'M0', 'new_break', locale='th')
    assert rendered.text == 'พักก่อน'
    assert rendered.layout.fit


@pytest.mark.parametrize('problem', ['duplicate', 'overflow'])
def test_failed_reload_keeps_the_previously_usable_catalog(editable_central, problem):
    central, character_root = editable_central
    rows = [row.copy() for row in EXAMPLES]
    if problem == 'duplicate':
        rows.append(rows[0].copy())
    else:
        rows[0][4] = 'x' * 100
    write_csv(character_root, rows)

    with pytest.raises(DialogueContentError):
        central.reload_dialogue_content()
    assert central.resolve_dialogue_line('greet').text == 'Hello!'
    assert central.render_dialogue_line_for_character(
        'RND_F_004', 'M0', 'greet').layout.fit


def test_disabled_content_is_inspectable_but_all_id_render_paths_reject_it(editable_central):
    central, _ = editable_central
    assert central.resolve_dialogue_line('paused', locale='th').text == '<0>'
    employee = central.list_employees(wave=1, assigned=True)[0]
    render_calls = [
        lambda: central.characters.render_dialogue_line_for_frame(
            'RND_F_004', 'M0', 'paused', locale='th'),
        lambda: central.render_dialogue_line_for_character(
            'RND_F_004', 'M0', 'paused', locale='th'),
        lambda: central.render_employee_dialogue_line(
            employee['employee_id'], 'M0', 'paused', locale='th'),
    ]
    for render in render_calls:
        with pytest.raises(DialogueContentError, match='disabled'):
            render()


def test_active_office_catalog_can_render_every_enabled_localization():
    central = CentralGameCore(ROOT)
    for locale in ('en', 'th'):
        lines = central.list_dialogue_lines(locale=locale, usage_scope='office',
                                           enabled_only=True)
        assert lines
        for line in lines:
            result = central.render_dialogue_line_for_character(
                'RND_F_004', 'M0', line['dialogue_id'], locale=locale,
                line_index=line['line_index'])
            assert result.layout.fit
            assert result.bubble_id != 'BB5'
