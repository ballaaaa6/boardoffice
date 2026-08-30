from __future__ import annotations

import json
from pathlib import Path

from .action_registry import load_action_set
from .action_renderer import CharacterActionRenderer, ActionRenderError, ActionRenderResult


class ActionResolutionError(ValueError):
    pass


class ActionCore:
    def __init__(self, core_root: str | Path, character_root: str | Path | None = None):
        self.core_root = Path(core_root)
        self.character_root = Path(character_root) if character_root is not None else None
        self.action_set = load_action_set(self.core_root / 'ACTIONS' / 'gds_standard_v1.json')
        registry = json.loads((self.core_root / 'CHARACTERS' / 'characters.json').read_text(encoding='utf-8'))
        self.characters = {c['character_id']: c for c in registry['characters']}
        self.renderer = CharacterActionRenderer(self.core_root)

    def _require_character(self, character_id: str) -> dict:
        char = self.characters.get(character_id)
        if char is None:
            raise ActionResolutionError(f'Unknown character: {character_id}')
        return char

    def resolve_frame_ids(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> list[str]:
        self._require_character(character_id)
        try:
            frame_ids, _loop = self.renderer.resolve_frame_ids(
                action, direction, subaction
            )
        except ActionRenderError as exc:
            raise ActionResolutionError(str(exc)) from exc
        return frame_ids

    def render_action(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> ActionRenderResult:
        self._require_character(character_id)
        try:
            return self.renderer.render_action(character_id, action, direction, subaction)
        except ActionRenderError as exc:
            raise ActionResolutionError(str(exc)) from exc

    def _legacy_relative_path(
        self,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> str:
        definition = self.action_set['actions'].get(action)
        if definition is None:
            raise ActionResolutionError(f'Unknown action: {action}')
        mode = definition['direction_mode']
        if mode == 'none':
            if direction is not None or subaction is not None:
                raise ActionResolutionError(f'{action} is directionless and has no subactions')
            return definition['legacy_materialized_path']
        if action == 'work':
            if direction is None:
                raise ActionResolutionError('work requires direction')
            d = definition['directions'].get(direction.upper())
            if d is None:
                raise ActionResolutionError(f'work does not support direction {direction.upper()}')
            if subaction is None:
                raise ActionResolutionError('work requires subaction')
            s = d['subactions'].get(subaction)
            if s is None:
                raise ActionResolutionError(f'Unknown work subaction: {subaction}')
            return s['legacy_materialized_path']
        if subaction is not None:
            raise ActionResolutionError(f'{action} has no subactions')
        if direction is None:
            raise ActionResolutionError(f'{action} requires direction')
        d = definition['directions'].get(direction.upper())
        if d is None:
            raise ActionResolutionError(f'{action} does not support direction {direction.upper()}')
        return d['legacy_materialized_path']

    def resolve_legacy_paths(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> list[Path]:
        char = self._require_character(character_id)
        if self.character_root is None:
            raise ActionResolutionError(
                'Legacy materialized path resolution requires character_root; Core rendering does not.'
            )
        frame_ids = self.resolve_frame_ids(character_id, action, direction, subaction)
        rel = self._legacy_relative_path(action, direction, subaction)
        folder = self.character_root / char['legacy_package_path'] / '02_ACTIONS' / rel
        paths = [folder / f'{i:02d}.png' for i in range(len(frame_ids))]
        missing = [p for p in paths if not p.is_file()]
        if missing:
            raise ActionResolutionError(f'Missing materialized frames: {missing}')
        return paths

    def resolve(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ):
        """Compatibility shim.

        With a legacy character root, preserve Phase 1/2 path resolution.
        Without one, return canonical frame IDs from the Core.
        """
        if self.character_root is not None:
            return self.resolve_legacy_paths(character_id, action, direction, subaction)
        return self.resolve_frame_ids(character_id, action, direction, subaction)
