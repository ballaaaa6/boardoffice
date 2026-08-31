from __future__ import annotations

from pathlib import Path

from .action_core import ActionCore, ActionResolutionError
from .action_renderer import ActionRenderError
from .character_identity import CharacterIdentityRegistry, CharacterIdentityError
from .effect_registry import EffectRegistry, EffectRegistryError
from .effect_renderer import EffectRenderer, EffectRenderError
from .humanball_registry import HumanBallRegistry, HumanBallRegistryError
from .humanball_renderer import HumanBallRenderer, HumanBallRenderError
from .presentation_renderer import WorkEffectPresentationRenderer, PresentationRenderError
from .dialogue_bubble import (
    DialogueBubbleError,
    BubbleSelection,
    DialogueBubbleRenderResult,
    DialogueBubbleRenderer,
    TextMetrics,
)
from .dialogue_content import DialogueLine, DialogueContentRegistry, DialogueContentError


class CharacterSystemError(ValueError):
    pass


class CharacterSystem:
    """Final public facade for unified GDS character identity/action rendering."""

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        self.core = ActionCore(self.core_root)
        self.identity = CharacterIdentityRegistry(self.core_root)
        self.effects = EffectRegistry(self.core_root)
        self.effect_renderer = EffectRenderer(self.core_root)
        self.humanballs = HumanBallRegistry(self.core_root)
        self.humanball_renderer = HumanBallRenderer(self.core_root)
        self.presentation = WorkEffectPresentationRenderer(self.core_root, self.core.renderer)
        self.dialogue = DialogueContentRegistry(self.core_root)
        self.dialogue_bubbles = DialogueBubbleRenderer(self.core_root)

    def list_characters(
        self, *, origin: str | None = None, collection: str | None = None
    ) -> list[str]:
        return self.identity.list(origin=origin, collection=collection)

    def get_character(self, character_id: str) -> dict:
        try:
            return self.identity.get(character_id)
        except CharacterIdentityError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def find_characters(self, body_asset_id: str, face_asset_id: str) -> list[str]:
        return self.identity.find(body_asset_id, face_asset_id)


    def list_effects(self) -> list[str]:
        return self.effects.list()

    def list_humanballs(self) -> list[str]:
        return self.humanballs.list()

    def get_humanball(self, humanball_id: str) -> dict:
        try:
            return self.humanballs.get(humanball_id)
        except HumanBallRegistryError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def render_humanball(
        self,
        humanball_id: str,
        direction: str,
        *,
        human_size: tuple[int, int] = (32, 42),
    ):
        try:
            return self.humanball_renderer.render_humanball(
                humanball_id, direction, human_size=human_size
            )
        except HumanBallRenderError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def get_effect(self, effect_id: str) -> dict:
        try:
            return self.effects.get(effect_id)
        except EffectRegistryError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def render_effect(self, effect_id: str, direction: str):
        try:
            return self.effect_renderer.render_effect(effect_id, direction)
        except EffectRenderError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def list_action_requests(self) -> list[dict]:
        actions = self.core.action_set['actions']
        requests: list[dict] = []
        for action in ('idle', 'move', 'variants'):
            for direction in ('NE', 'SE', 'SW', 'NW'):
                if direction in actions[action]['directions']:
                    requests.append({'action': action, 'direction': direction, 'subaction': None})
        for action in ('happy', 'sad'):
            requests.append({'action': action, 'direction': None, 'subaction': None})
        for direction in ('NE', 'SE', 'SW', 'NW'):
            node = actions['work']['directions'][direction]
            for subaction in node['subactions']:
                requests.append({'action': 'work', 'direction': direction, 'subaction': subaction})
        return requests

    def resolve_frame_ids(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> list[str]:
        try:
            return self.core.resolve_frame_ids(character_id, action, direction, subaction)
        except ActionResolutionError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def render(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        effect_id: str | None = None,
    ):
        if effect_id is None:
            try:
                return self.core.render_action(character_id, action, direction, subaction)
            except ActionResolutionError as exc:
                raise CharacterSystemError(str(exc)) from exc
        try:
            self.core._require_character(character_id)
            return self.presentation.render_character(
                character_id, action, direction, subaction, effect_id
            )
        except (ActionResolutionError, PresentationRenderError) as exc:
            raise CharacterSystemError(str(exc)) from exc

    def render_composition(
        self,
        body_asset_id: str,
        face_asset_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        effect_id: str | None = None,
    ):
        if effect_id is None:
            try:
                return self.core.renderer.render_composition_action(
                    body_asset_id, face_asset_id, action, direction, subaction
                )
            except ActionRenderError as exc:
                raise CharacterSystemError(str(exc)) from exc
        try:
            return self.presentation.render_composition(
                body_asset_id, face_asset_id, action, direction, subaction, effect_id
            )
        except PresentationRenderError as exc:
            raise CharacterSystemError(str(exc)) from exc

    def list_dialogue_bubbles(self) -> list[str]:
        return self.dialogue_bubbles.list_bubbles()

    def list_dialogue_lines(
        self, *, locale: str | None = None, category: str | None = None,
        usage_scope: str | None = None, enabled_only: bool = False,
    ) -> list[dict[str, object]]:
        return [line.as_dict() for line in self.dialogue.list(
            locale=locale, category=category, usage_scope=usage_scope,
            enabled_only=enabled_only,
        )]

    def reload_dialogue_content(self) -> dict[str, object]:
        """Validate the edited catalog before replacing the in-memory snapshot."""
        candidate = DialogueContentRegistry(self.core_root)
        for line in candidate.list(enabled_only=True):
            try:
                self.dialogue_bubbles.select_bubble(line.text, locale=line.locale)
            except DialogueBubbleError as exc:
                raise DialogueContentError(
                    f'Cannot reload {line.dialogue_id}/{line.locale}/{line.line_index}: {exc}'
                ) from exc
        self.dialogue = candidate
        lines = candidate.list()
        return {
            'line_count': len(lines),
            'dialogue_count': len({line.dialogue_id for line in lines}),
            'enabled_line_count': sum(line.enabled for line in lines),
            'locales': sorted({line.locale for line in lines}),
        }

    def resolve_dialogue_line(
        self,
        dialogue_id: str,
        *,
        locale: str = 'en',
        line_index: int = 0,
        require_enabled: bool = False,
    ) -> DialogueLine:
        return self.dialogue.get(
            dialogue_id, locale=locale, line_index=line_index,
            require_enabled=require_enabled,
        )

    def measure_dialogue_text(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> TextMetrics:
        return self.dialogue_bubbles.measure_text(
            text,
            locale=locale,
            font_size_px=font_size_px,
        )

    def select_dialogue_bubble(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> BubbleSelection:
        return self.dialogue_bubbles.select_bubble(
            text,
            locale=locale,
            font_size_px=font_size_px,
        )

    def render_dialogue_bubble_for_frame(
        self,
        character_id: str,
        frame_id: str,
        text: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        return self.dialogue_bubbles.render_for_character(
            character_id,
            frame_id,
            text,
            actor_top_left=actor_top_left,
            locale=locale,
            font_size_px=font_size_px,
        )

    def render_dialogue_line_for_frame(
        self,
        character_id: str,
        frame_id: str,
        dialogue_id: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str | None = None,
        line_index: int = 0,
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        line = self.resolve_dialogue_line(
            dialogue_id,
            locale='en' if locale is None else locale,
            line_index=line_index,
            require_enabled=True,
        )
        return self.render_dialogue_bubble_for_frame(
            character_id,
            frame_id,
            line.text,
            actor_top_left=actor_top_left,
            locale=line.locale,
            font_size_px=font_size_px,
        )

    def resolve_dialogue_asset_path(self, asset_id: str):
        return self.dialogue_bubbles.resolve_asset_path(asset_id)
