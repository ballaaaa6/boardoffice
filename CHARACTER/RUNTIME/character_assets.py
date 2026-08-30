from __future__ import annotations

import json
from pathlib import Path
from .asset_registry import AssetRegistry, AssetResolutionError


class CharacterAssetResolutionError(ValueError):
    pass


class CharacterAssetResolver:
    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        char_path = self.core_root / 'CHARACTERS' / 'characters.json'
        if not char_path.is_file():
            raise CharacterAssetResolutionError(f'Missing character registry: {char_path}')
        registry = json.loads(char_path.read_text(encoding='utf-8'))
        chars = registry.get('characters', [])
        self.characters = {c['character_id']: c for c in chars}
        if len(self.characters) != len(chars):
            raise CharacterAssetResolutionError('Duplicate character_id in character registry')
        self.assets = AssetRegistry(self.core_root)

    def resolve(self, character_id: str, verify_hash: bool = False) -> dict:
        char = self.characters.get(character_id)
        if char is None:
            raise CharacterAssetResolutionError(f'Unknown character: {character_id}')
        composition = char.get('composition') or {}
        body_id = composition.get('body', char.get('body_asset_id'))
        face_id = composition.get('face', char.get('face_asset_id'))
        try:
            body = self.assets.resolve(body_id, verify_hash=verify_hash)
            face = self.assets.resolve(face_id, verify_hash=verify_hash)
        except AssetResolutionError as exc:
            raise CharacterAssetResolutionError(str(exc)) from exc
        return {
            'character_id': character_id,
            'body_asset_id': body_id,
            'face_asset_id': face_id,
            'body': body,
            'face': face,
        }
    def resolve_composition(self, body_asset_id: str, face_asset_id: str, verify_hash: bool = False) -> dict:
        try:
            body = self.assets.resolve(body_asset_id, verify_hash=verify_hash)
            face = self.assets.resolve(face_asset_id, verify_hash=verify_hash)
        except AssetResolutionError as exc:
            raise CharacterAssetResolutionError(str(exc)) from exc
        if not body_asset_id.startswith('character.body.'):
            raise CharacterAssetResolutionError(f'Not a character body asset: {body_asset_id}')
        if not face_asset_id.startswith('character.face.'):
            raise CharacterAssetResolutionError(f'Not a character face asset: {face_asset_id}')
        return {
            'character_id': None,
            'body_asset_id': body_asset_id,
            'face_asset_id': face_asset_id,
            'body': body,
            'face': face,
        }

