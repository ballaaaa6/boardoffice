from __future__ import annotations

import hashlib
import json
from pathlib import Path


class AssetResolutionError(ValueError):
    pass


class AssetRegistry:
    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root).resolve()
        unified = self.core_root / 'ASSETS' / 'asset_registry.json'
        legacy = self.core_root / 'ASSETS' / 'characters' / 'asset_registry.json'
        self.unified = unified.is_file()
        if self.unified:
            self.asset_root = (self.core_root / 'ASSETS').resolve()
            data = json.loads(unified.read_text(encoding='utf-8'))
            if data.get('schema') != 'gds_unified_asset_registry_v1':
                raise AssetResolutionError(f'Unsupported unified asset registry schema: {data.get("schema")}')
            assets = data.get('assets', [])
            aliases = data.get('aliases', {})
        elif legacy.is_file():
            # Phase 2-4 compatibility for builder/tests that materialize only character assets.
            self.asset_root = (self.core_root / 'ASSETS' / 'characters').resolve()
            data = json.loads(legacy.read_text(encoding='utf-8'))
            assets = data.get('assets', [])
            aliases = {}
        else:
            raise AssetResolutionError(f'Missing asset registry: {unified}')

        self.assets = {a['asset_id']: a for a in assets}
        if len(self.assets) != len(assets):
            raise AssetResolutionError('Duplicate asset_id in asset registry')
        if not isinstance(aliases, dict):
            raise AssetResolutionError('Invalid asset aliases')
        self.aliases = dict(aliases)
        for alias, target in self.aliases.items():
            if alias in self.assets:
                raise AssetResolutionError(f'Alias collides with canonical asset_id: {alias}')
            if target not in self.assets:
                raise AssetResolutionError(f'Alias target missing: {alias} -> {target}')

    def canonical_id(self, asset_id: str) -> str:
        if asset_id in self.assets:
            return asset_id
        target = self.aliases.get(asset_id)
        if target is None:
            raise AssetResolutionError(f'Unknown asset: {asset_id}')
        return target

    def metadata(self, asset_id: str) -> dict:
        return self.assets[self.canonical_id(asset_id)]

    def resolve(self, asset_id: str, verify_hash: bool = False) -> Path:
        canonical = self.canonical_id(asset_id)
        asset = self.assets[canonical]
        root = self.asset_root
        path = (root / asset['path']).resolve()
        if not path.is_relative_to(root):
            raise AssetResolutionError(f'Asset path escapes shared root: {canonical}')
        if not path.is_file():
            raise AssetResolutionError(f'Canonical asset missing: {canonical} -> {path}')
        if verify_hash:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != asset['sha256']:
                raise AssetResolutionError(f'Canonical asset hash mismatch: {canonical}')
        return path
