from __future__ import annotations

import json
import re
from pathlib import Path


class CharacterIdentityLookupError(LookupError):
    pass


class CharacterIdentityResolver:
    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        cards_data = json.loads(
            (self.core_root / 'CHARACTERS' / 'identity_cards.json').read_text(encoding='utf-8')
        )
        alias_data = json.loads(
            (self.core_root / 'CHARACTERS' / 'identity_alias_index.json').read_text(encoding='utf-8')
        )
        rows = cards_data['characters']
        self._by_id = {row['character_id']: row for row in rows}
        if len(self._by_id) != len(rows):
            raise CharacterIdentityLookupError('Duplicate character_id in identity cards')

        self._aliases = alias_data['aliases']
        self._flat_text_aliases: dict[str, str] = {}
        for group in ('character_code', 'full_name', 'nickname', 'character_id'):
            for key, cid in self._aliases[group].items():
                norm = key.strip().casefold()
                prior = self._flat_text_aliases.get(norm)
                if prior is not None and prior != cid:
                    raise CharacterIdentityLookupError(
                        f'Ambiguous alias {key!r}: {prior} vs {cid}'
                    )
                self._flat_text_aliases[norm] = cid

    def _from_number(self, number: int) -> str:
        cid = self._aliases['character_no'].get(str(number))
        if cid is None:
            raise CharacterIdentityLookupError(f'Unknown character number: {number}')
        return cid

    def resolve_character_id(self, query: int | str) -> str:
        if isinstance(query, bool):
            raise CharacterIdentityLookupError(f'Unsupported character query: {query!r}')
        if isinstance(query, int):
            return self._from_number(query)
        if not isinstance(query, str):
            raise CharacterIdentityLookupError(f'Unsupported character query type: {type(query).__name__}')

        text = query.strip()
        if not text:
            raise CharacterIdentityLookupError('Empty character query')

        if text.isdecimal():
            return self._from_number(int(text, 10))

        code_match = re.fullmatch(r'(?i)CHAR[_-]?(\d+)', text)
        if code_match:
            return self._from_number(int(code_match.group(1), 10))

        cid = self._flat_text_aliases.get(text.casefold())
        if cid is None:
            raise CharacterIdentityLookupError(f'Unknown character alias: {query!r}')
        return cid

    def resolve(self, query: int | str) -> dict:
        cid = self.resolve_character_id(query)
        return dict(self._by_id[cid])

    def get_by_character_id(self, character_id: str) -> dict:
        try:
            return dict(self._by_id[character_id])
        except KeyError as exc:
            raise CharacterIdentityLookupError(f'Unknown character_id: {character_id}') from exc
