from __future__ import annotations

import json
from pathlib import Path


class EffectRegistryError(ValueError):
    pass


class EffectRegistry:
    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        path = self.core_root / 'EFFECTS' / 'gds_effects_v1.json'
        if not path.is_file():
            raise EffectRegistryError(f'Missing effect registry: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema') != 'gds_effect_registry_v1':
            raise EffectRegistryError(f"Unsupported effect registry schema: {data.get('schema')}")
        effects = data.get('effects')
        order = data.get('effect_order')
        if not isinstance(effects, dict) or not isinstance(order, list):
            raise EffectRegistryError('Invalid effect registry structure')
        if len(order) != data.get('effect_count') or set(order) != set(effects):
            raise EffectRegistryError('effect_order/effect_count mismatch')
        if len(order) != 11:
            raise EffectRegistryError(f'Central Core must contain exactly 11 effects, got {len(order)}')
        canonical = data.get('canonical_effect_id')
        fallback = data.get('fallback_effect_id')
        if canonical not in effects or fallback not in effects:
            raise EffectRegistryError('Canonical/fallback effect is missing')
        self.data = data
        self.effects = effects
        self.order = list(order)

    def list(self) -> list[str]:
        return list(self.order)

    def get(self, effect_id: str) -> dict:
        try:
            return self.effects[effect_id]
        except KeyError as exc:
            raise EffectRegistryError(f'Unknown effect: {effect_id}') from exc

    @property
    def canonical_effect_id(self) -> str:
        return self.data['canonical_effect_id']

    @property
    def fallback_effect_id(self) -> str:
        return self.data['fallback_effect_id']
