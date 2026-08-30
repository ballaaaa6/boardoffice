from __future__ import annotations

import json
from pathlib import Path


class HumanBallRegistryError(ValueError):
    pass


class HumanBallRegistry:
    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        path = self.core_root / 'EFFECTS' / 'humanball_v1.json'
        if not path.is_file():
            raise HumanBallRegistryError(f'Missing HumanBall registry: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema') != 'gds_humanball_registry_v1':
            raise HumanBallRegistryError(f"Unsupported HumanBall registry schema: {data.get('schema')}")
        items = data.get('humanballs')
        order = data.get('humanball_order')
        if not isinstance(items, dict) or not isinstance(order, list):
            raise HumanBallRegistryError('Invalid HumanBall registry structure')
        if len(order) != data.get('humanball_count') or set(order) != set(items):
            raise HumanBallRegistryError('humanball_order/humanball_count mismatch')
        if len(order) != 6:
            raise HumanBallRegistryError(f'Central HumanBall registry must contain exactly 6 entries, got {len(order)}')
        animation = data.get('animation', {})
        if int(animation.get('total_frames', -1)) != 12:
            raise HumanBallRegistryError('HumanBall animation must contain exactly 12 logical frames')
        if int(animation.get('visible_frames', -1)) != 10 or int(animation.get('hidden_frames', -1)) != 2:
            raise HumanBallRegistryError('HumanBall animation must contain 10 visible + 2 hidden frames')
        motion = data.get('motion_offsets_from_character_top_left_px', {})
        if any(len(motion.get(direction, [])) != 10 for direction in ('NW', 'SE')):
            raise HumanBallRegistryError('HumanBall NW/SE motion must contain 10 visible offsets')
        self.data = data
        self.items = items
        self.order = list(order)

    def list(self) -> list[str]:
        return list(self.order)

    def get(self, humanball_id: str) -> dict:
        try:
            return self.items[humanball_id]
        except KeyError as exc:
            raise HumanBallRegistryError(f'Unknown HumanBall: {humanball_id}') from exc
