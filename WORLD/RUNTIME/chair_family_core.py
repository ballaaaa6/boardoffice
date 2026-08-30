from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ChairFamilyError(ValueError):
    pass


class ChairFamilyCore:
    _ASSET_RE = re.compile(r'^(chair_[0-9]{3})\.part_[0-9]{2}$')

    def __init__(self, world_root: str | Path):
        self.root = Path(world_root).resolve()
        payload = json.loads((self.root / 'REGISTRY' / 'chair_families.json').read_text(encoding='utf-8'))
        self.registry = payload
        self.families = payload['families']

    def resolve_family(self, family_id: str) -> dict[str, Any]:
        try:
            return self.families[family_id]
        except KeyError as exc:
            raise ChairFamilyError(f'Unknown chair family: {family_id}') from exc

    def resolve_part_asset(self, family_id: str, role: str) -> str | None:
        family = self.resolve_family(family_id)
        try:
            part = family['parts'][role]
        except KeyError as exc:
            raise ChairFamilyError(f'Unknown chair role {role!r} for {family_id}') from exc
        return part['asset_id']

    def infer_family_from_asset_id(self, asset_id: str) -> str:
        match = self._ASSET_RE.fullmatch(asset_id)
        if match is None:
            raise ChairFamilyError(f'Not a canonical chair part asset id: {asset_id}')
        family_id = match.group(1)
        self.resolve_family(family_id)
        return family_id
