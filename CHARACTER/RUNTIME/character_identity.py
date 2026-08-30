from __future__ import annotations

import json
from pathlib import Path


class CharacterIdentityError(ValueError):
    pass


class CharacterIdentityRegistry:
    """Stable character identity + composition + provenance lookup.

    Origin/collection are metadata only and never select a different render path.
    """

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        p = self.core_root / 'CHARACTERS' / 'characters.json'
        data = json.loads(p.read_text(encoding='utf-8'))
        chars = data.get('characters', [])
        self.characters = {c['character_id']: c for c in chars}
        if len(self.characters) != len(chars):
            raise CharacterIdentityError('Duplicate character_id in registry')

        idx_path = self.core_root / 'CHARACTERS' / 'composition_index.json'
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        self.compositions = idx.get('compositions', {})

    @staticmethod
    def composition_key(body_asset_id: str, face_asset_id: str) -> str:
        return f'{body_asset_id}+{face_asset_id}'

    def get(self, character_id: str) -> dict:
        rec = self.characters.get(character_id)
        if rec is None:
            raise CharacterIdentityError(f'Unknown character: {character_id}')
        return rec

    def list(self, *, origin: str | None = None, collection: str | None = None) -> list[str]:
        out = []
        for cid, rec in self.characters.items():
            prov = rec.get('origin') or {
                'type': rec.get('package_class'),
                'collection': None,
            }
            if origin is not None and prov.get('type') != origin:
                continue
            if collection is not None and prov.get('collection') != collection:
                continue
            out.append(cid)
        return sorted(out)

    def find(self, body_asset_id: str, face_asset_id: str) -> list[str]:
        return list(self.compositions.get(self.composition_key(body_asset_id, face_asset_id), []))
