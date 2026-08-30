from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from .action_renderer import CharacterActionRenderer, ActionRenderResult, ActionRenderError
from .effect_renderer import EffectRenderer, EffectRenderError, EffectRenderResult
from .effect_registry import EffectRegistry


class PresentationRenderError(ValueError):
    pass


@dataclass
class WorkEffectRenderResult:
    character_id: str
    action: str
    direction: str
    subaction: str
    frame_ids: list[str]
    frames: list[Image.Image]
    loop: bool
    effect_id: str
    effect_frame_asset_ids: list[str]
    effect_source_frame_count: int
    effect_frame_ms: int
    presentation_canvas: tuple[int, int]
    derived_from: str | None = None
    transform: str | None = None


class WorkEffectPresentationRenderer:
    """Composes normal_work character frames with central VFX on a transparent work-local canvas.

    This intentionally does not import floor/map/furniture systems. The relative offsets are the
    approved FIREMATCH character/effect relationship reduced to source-pixel coordinates. SW is
    always derived from the fully resolved SE presentation by horizontal pixel mirror.
    """

    def __init__(self, core_root: str | Path, actions: CharacterActionRenderer):
        self.core_root = Path(core_root)
        self.actions = actions
        self.effects = EffectRenderer(self.core_root)
        self.registry = EffectRegistry(self.core_root)
        profile = self.registry.data['work_local_profile']
        self.canvas = tuple(profile['canvas'])
        self.profile = profile

    @staticmethod
    def _cycle_ids(ids: list[str], count: int) -> list[str]:
        return [ids[i % len(ids)] for i in range(count)]

    def _combine_native(
        self,
        character_result: ActionRenderResult,
        effect_result: EffectRenderResult,
        direction: str,
    ) -> list[Image.Image]:
        if direction not in {'NW', 'SE'}:
            raise PresentationRenderError(f'Native presentation direction must be NW or SE: {direction}')
        node = self.profile[direction]
        effect_pos = tuple(node['effect_pos'])
        character_pos = tuple(node['character_pos'])
        frames: list[Image.Image] = []
        for i, effect in enumerate(effect_result.frames):
            character = character_result.frames[i % len(character_result.frames)]
            if character.size != (32, 42):
                raise PresentationRenderError(f'Character frame must be 32x42, got {character.size}')
            stage = Image.new('RGBA', self.canvas, (0, 0, 0, 0))
            stage.alpha_composite(effect, effect_pos)
            stage.alpha_composite(character.convert('RGBA'), character_pos)
            frames.append(stage)
        return frames

    def _validate_request(self, action: str, direction: str | None, subaction: str | None) -> str:
        if action != 'work' or subaction != 'normal_work':
            raise PresentationRenderError('VFX presentation is supported only for work/normal_work')
        if direction is None:
            raise PresentationRenderError('VFX work presentation requires direction')
        direction = direction.upper()
        if direction not in {'NW', 'SE', 'SW'}:
            raise PresentationRenderError(f'VFX work direction must be NW, SE, or SW: {direction}')
        return direction

    def render_character(
        self,
        character_id: str,
        action: str,
        direction: str | None,
        subaction: str | None,
        effect_id: str,
    ) -> WorkEffectRenderResult:
        direction = self._validate_request(action, direction, subaction)
        try:
            if direction == 'SW':
                se_char = self.actions.render_action(character_id, 'work', 'SE', 'normal_work')
                sw_char = self.actions.render_action(character_id, 'work', 'SW', 'normal_work')
                se_effect = self.effects.render_effect(effect_id, 'SE')
                se_frames = self._combine_native(se_char, se_effect, 'SE')
                frames = [f.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for f in se_frames]
                frame_ids = self._cycle_ids(sw_char.frame_ids, len(frames))
                return WorkEffectRenderResult(
                    character_id=character_id,
                    action='work', direction='SW', subaction='normal_work',
                    frame_ids=frame_ids, frames=frames, loop=True,
                    effect_id=effect_id,
                    effect_frame_asset_ids=list(se_effect.frame_asset_ids),
                    effect_source_frame_count=se_effect.source_frame_count,
                    effect_frame_ms=se_effect.frame_ms,
                    presentation_canvas=self.canvas,
                    derived_from='SE', transform='mirror_y',
                )

            char = self.actions.render_action(character_id, 'work', direction, 'normal_work')
            effect = self.effects.render_effect(effect_id, direction)
            frames = self._combine_native(char, effect, direction)
            return WorkEffectRenderResult(
                character_id=character_id,
                action='work', direction=direction, subaction='normal_work',
                frame_ids=self._cycle_ids(char.frame_ids, len(frames)),
                frames=frames, loop=True,
                effect_id=effect_id,
                effect_frame_asset_ids=list(effect.frame_asset_ids),
                effect_source_frame_count=effect.source_frame_count,
                effect_frame_ms=effect.frame_ms,
                presentation_canvas=self.canvas,
            )
        except (ActionRenderError, EffectRenderError) as exc:
            raise PresentationRenderError(str(exc)) from exc

    def render_composition(
        self,
        body_asset_id: str,
        face_asset_id: str,
        action: str,
        direction: str | None,
        subaction: str | None,
        effect_id: str,
    ) -> WorkEffectRenderResult:
        direction = self._validate_request(action, direction, subaction)
        key = f'composition:{body_asset_id}+{face_asset_id}'
        try:
            if direction == 'SW':
                se_char = self.actions.render_composition_action(
                    body_asset_id, face_asset_id, 'work', 'SE', 'normal_work'
                )
                sw_char = self.actions.render_composition_action(
                    body_asset_id, face_asset_id, 'work', 'SW', 'normal_work'
                )
                se_effect = self.effects.render_effect(effect_id, 'SE')
                se_frames = self._combine_native(se_char, se_effect, 'SE')
                frames = [f.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for f in se_frames]
                return WorkEffectRenderResult(
                    character_id=key,
                    action='work', direction='SW', subaction='normal_work',
                    frame_ids=self._cycle_ids(sw_char.frame_ids, len(frames)),
                    frames=frames, loop=True,
                    effect_id=effect_id,
                    effect_frame_asset_ids=list(se_effect.frame_asset_ids),
                    effect_source_frame_count=se_effect.source_frame_count,
                    effect_frame_ms=se_effect.frame_ms,
                    presentation_canvas=self.canvas,
                    derived_from='SE', transform='mirror_y',
                )
            char = self.actions.render_composition_action(
                body_asset_id, face_asset_id, 'work', direction, 'normal_work'
            )
            effect = self.effects.render_effect(effect_id, direction)
            frames = self._combine_native(char, effect, direction)
            return WorkEffectRenderResult(
                character_id=key,
                action='work', direction=direction, subaction='normal_work',
                frame_ids=self._cycle_ids(char.frame_ids, len(frames)),
                frames=frames, loop=True,
                effect_id=effect_id,
                effect_frame_asset_ids=list(effect.frame_asset_ids),
                effect_source_frame_count=effect.source_frame_count,
                effect_frame_ms=effect.frame_ms,
                presentation_canvas=self.canvas,
            )
        except (ActionRenderError, EffectRenderError) as exc:
            raise PresentationRenderError(str(exc)) from exc
