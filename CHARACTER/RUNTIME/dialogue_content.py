from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path


class DialogueContentError(ValueError):
    pass


@dataclass(frozen=True)
class DialogueLine:
    dialogue_id: str
    locale: str
    line_index: int
    speaker_role: str
    text: str
    category: str = 'uncategorized'
    usage_scope: str = 'office'
    enabled: bool = True
    full_text: str = ''
    source_id: str = ''
    source_text: str = ''

    def as_dict(self) -> dict[str, object]:
        return {
            'dialogue_id': self.dialogue_id,
            'locale': self.locale,
            'line_index': self.line_index,
            'speaker_role': self.speaker_role,
            'text': self.text,
            'category': self.category,
            'usage_scope': self.usage_scope,
            'enabled': self.enabled,
            'full_text': self.full_text or self.text,
            'source_id': self.source_id,
            'source_text': self.source_text,
        }


class DialogueContentRegistry:
    """Loads editable localized text and eligibility metadata from UTF-8 CSV.

    Source references are descriptive only; no archive/review files are loaded.
    Missing optional columns preserve the original five-column CSV contract.
    """

    REQUIRED_COLUMNS = ('dialogue_id', 'locale', 'line_index', 'speaker_role', 'text')

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        self.path = self.core_root / 'DIALOGUE' / 'dialogue.csv'
        if not self.path.is_file():
            raise DialogueContentError(f'Missing dialogue CSV: {self.path}')

        self.lines: dict[tuple[str, str, int], DialogueLine] = {}
        with self.path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            fieldnames = tuple(reader.fieldnames or ())
            if len(fieldnames) != len(set(fieldnames)):
                raise DialogueContentError('Dialogue CSV has duplicate column headers')
            missing = [column for column in self.REQUIRED_COLUMNS if column not in fieldnames]
            if missing:
                raise DialogueContentError(
                    f'Missing dialogue CSV columns: {", ".join(missing)}'
                )

            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise DialogueContentError(
                        f'Dialogue CSV row {row_number} has extra columns; quote commas in text'
                    )
                self._add_row(row_number, row)

        if not self.lines:
            raise DialogueContentError(f'Dialogue CSV has no rows: {self.path}')

    @staticmethod
    def _locale_key(value: str) -> str:
        normalized = value.strip().casefold().replace('_', '-')
        if not normalized:
            raise DialogueContentError('Dialogue locale cannot be empty')
        return normalized.split('-', 1)[0]

    def _add_row(self, row_number: int, row: dict[str, str | None]) -> None:
        def required(name: str) -> str:
            value = row.get(name)
            if value is None or not value.strip():
                raise DialogueContentError(
                    f'Dialogue CSV row {row_number} has empty {name}'
                )
            return value.strip()

        dialogue_id = required('dialogue_id')
        locale = self._locale_key(required('locale'))
        speaker_role = required('speaker_role')
        text = row.get('text') or ''
        if not text:
            raise DialogueContentError(f'Dialogue CSV row {row_number} has empty text')
        if '\n' in text or '\r' in text:
            raise DialogueContentError(
                f'Dialogue CSV row {row_number} must contain one line of text'
            )
        enabled_value = (row.get('enabled') or 'true').strip().casefold()
        if enabled_value not in ('true', 'false'):
            raise DialogueContentError(
                f'Dialogue CSV row {row_number} enabled must be true or false'
            )
        enabled = enabled_value == 'true'
        if enabled and re.search(r'<[^<>]+>', text):
            raise DialogueContentError(
                f'Dialogue CSV row {row_number}: enabled text cannot contain '
                'markup or placeholders; disable it until the final text is ready'
            )
        try:
            line_index = int(required('line_index'))
        except ValueError as exc:
            raise DialogueContentError(
                f'Dialogue CSV row {row_number} has invalid line_index'
            ) from exc
        if line_index < 0:
            raise DialogueContentError(
                f'Dialogue CSV row {row_number} line_index must be >= 0'
            )

        line = DialogueLine(
            dialogue_id, locale, line_index, speaker_role, text,
            category=(row.get('category') or 'uncategorized').strip(),
            usage_scope=(row.get('usage_scope') or 'office').strip(),
            enabled=enabled,
            full_text=row.get('full_text') or text,
            source_id=(row.get('source_id') or '').strip(),
            source_text=row.get('source_text') or '',
        )
        key = (dialogue_id, locale, line_index)
        if key in self.lines:
            raise DialogueContentError(
                f'Duplicate dialogue line: {dialogue_id}/{locale}/{line_index}'
            )
        self.lines[key] = line

    def list(
        self, *, locale: str | None = None, category: str | None = None,
        usage_scope: str | None = None, enabled_only: bool = False,
    ) -> list[DialogueLine]:
        locale_key = None if locale is None else self._locale_key(locale)
        rows = [
            line for line in self.lines.values()
            if (locale_key is None or line.locale == locale_key)
            and (category is None or line.category == category)
            and (usage_scope is None or line.usage_scope == usage_scope)
            and (not enabled_only or line.enabled)
        ]
        return sorted(rows, key=lambda line: (line.dialogue_id, line.locale, line.line_index))

    def get(
        self,
        dialogue_id: str,
        *,
        locale: str = 'en',
        line_index: int = 0,
        require_enabled: bool = False,
    ) -> DialogueLine:
        dialogue_key = str(dialogue_id).strip()
        locale_key = self._locale_key(locale)
        try:
            index = int(line_index)
        except (TypeError, ValueError) as exc:
            raise DialogueContentError('Dialogue line_index must be an integer') from exc
        key = (dialogue_key, locale_key, index)
        try:
            line = self.lines[key]
        except KeyError as exc:
            raise DialogueContentError(
                f'Unknown dialogue line: {dialogue_key}/{locale_key}/{index}'
            ) from exc
        if require_enabled and not line.enabled:
            raise DialogueContentError(
                f'Dialogue line is disabled: {dialogue_key}/{locale_key}/{index}'
            )
        return line
