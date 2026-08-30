from __future__ import annotations

import json
from pathlib import Path


class FrameRuleError(ValueError):
    pass


def load_frame_registry(core_root: str | Path) -> dict:
    core_root = Path(core_root)
    path = core_root / 'FRAME_RULES' / 'frame_registry.json'
    if not path.is_file():
        raise FrameRuleError(f'Missing frame registry: {path}')
    registry = json.loads(path.read_text(encoding='utf-8'))
    if registry.get('schema') != 'gds_frame_registry_v1':
        raise FrameRuleError(f"Unsupported frame registry schema: {registry.get('schema')}")
    if registry.get('render_profile', {}).get('canvas') != [32, 42]:
        raise FrameRuleError('Frame registry canvas must be 32x42')
    if registry.get('render_profile', {}).get('origin') != [5, 2]:
        raise FrameRuleError('Frame registry origin must be [5, 2]')
    frames = registry.get('frames')
    if not isinstance(frames, dict) or not frames:
        raise FrameRuleError('Frame registry has no frames')
    return registry


def resolve_frame_rule(registry: dict, frame_id: str) -> dict:
    try:
        return registry['frames'][frame_id]
    except KeyError as exc:
        raise FrameRuleError(f'Unknown frame_id: {frame_id}') from exc
