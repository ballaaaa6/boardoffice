from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from .action_registry import load_action_set
from .frame_renderer import CharacterFrameRenderer, FrameRenderError


class ActionRenderError(ValueError):
    pass


@dataclass
class ActionRenderResult:
    character_id: str
    action: str
    direction: str | None
    subaction: str | None
    frame_ids: list[str]
    frames: list[Image.Image]
    loop: bool


class CharacterActionRenderer:
    def __init__(self, core_root: str | Path, *, verify_asset_hashes: bool = False):
        self.core_root = Path(core_root)
        self.action_set = load_action_set(self.core_root / 'ACTIONS' / 'gds_standard_v1.json')
        self.frames = CharacterFrameRenderer(
            self.core_root, verify_asset_hashes=verify_asset_hashes
        )

    def resolve_frame_ids(
        self,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> tuple[list[str], bool]:
        definition = self.action_set['actions'].get(action)
        if definition is None:
            raise ActionRenderError(f'Unknown action: {action}')

        mode = definition['direction_mode']
        if mode == 'none':
            if direction is not None or subaction is not None:
                raise ActionRenderError(f'{action} is directionless and has no subactions')
            return list(definition['frames']), bool(definition.get('loop', False))

        if action == 'work':
            if direction is None:
                raise ActionRenderError('work requires direction')
            direction = direction.upper()
            d = definition['directions'].get(direction)
            if d is None:
                raise ActionRenderError(f'work does not support direction {direction}')
            if subaction is None:
                raise ActionRenderError('work requires subaction')
            s = d['subactions'].get(subaction)
            if s is None:
                raise ActionRenderError(f'Unknown work subaction: {subaction}')
            return list(s['frames']), bool(s.get('loop', definition.get('loop', True)))

        if subaction is not None:
            raise ActionRenderError(f'{action} has no subactions')
        if direction is None:
            raise ActionRenderError(f'{action} requires direction')
        direction = direction.upper()
        d = definition['directions'].get(direction)
        if d is None:
            raise ActionRenderError(f'{action} does not support direction {direction}')
        return list(d['frames']), bool(definition.get('loop', False))

    def render_action(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> ActionRenderResult:
        normalized_direction = direction.upper() if direction is not None else None
        frame_ids, loop = self.resolve_frame_ids(
            action, normalized_direction, subaction
        )
        try:
            rendered = [self.frames.render_frame(character_id, frame_id) for frame_id in frame_ids]
        except FrameRenderError as exc:
            raise ActionRenderError(str(exc)) from exc
        return ActionRenderResult(
            character_id=character_id,
            action=action,
            direction=normalized_direction,
            subaction=subaction,
            frame_ids=frame_ids,
            frames=rendered,
            loop=loop,
        )

    def render_composition_action(
        self,
        body_asset_id: str,
        face_asset_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
    ) -> ActionRenderResult:
        normalized_direction = direction.upper() if direction is not None else None
        frame_ids, loop = self.resolve_frame_ids(
            action, normalized_direction, subaction
        )
        try:
            rendered = [
                self.frames.render_composition_frame(body_asset_id, face_asset_id, frame_id)
                for frame_id in frame_ids
            ]
        except FrameRenderError as exc:
            raise ActionRenderError(str(exc)) from exc
        key = f'composition:{body_asset_id}+{face_asset_id}'
        return ActionRenderResult(
            character_id=key,
            action=action,
            direction=normalized_direction,
            subaction=subaction,
            frame_ids=frame_ids,
            frames=rendered,
            loop=loop,
        )

    @staticmethod
    def _scale(im: Image.Image, scale: int) -> Image.Image:
        if scale < 1:
            raise ActionRenderError('scale must be >= 1')
        if scale == 1:
            return im.copy()
        return im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)

    @staticmethod
    def _to_gif_palette(im: Image.Image) -> Image.Image:
        rgba = im.convert('RGBA')
        alpha = rgba.getchannel('A')
        rgb = Image.new('RGB', rgba.size, (0, 0, 0))
        rgb.paste(rgba, mask=alpha)
        pal = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        transparent_mask = alpha.point(lambda a: 255 if a == 0 else 0)
        pal.paste(255, mask=transparent_mask)
        palette = pal.getpalette() or []
        if len(palette) < 768:
            palette += [0] * (768 - len(palette))
        pal.putpalette(palette[:768])
        pal.info['transparency'] = 255
        return pal

    def export_action(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        output_root: str | Path,
        format: str = 'gif',
        scale: int = 1,
        frame_ms: int = 360,
    ) -> dict:
        if format not in {'png', 'gif', 'both'}:
            raise ActionRenderError("format must be 'png', 'gif', or 'both'")
        if frame_ms < 1:
            raise ActionRenderError('frame_ms must be >= 1')
        result = self.render_action(character_id, action, direction, subaction)
        frames = [self._scale(im, scale) for im in result.frames]

        parts = [character_id, action]
        if result.direction:
            parts.append(result.direction.lower())
        if subaction:
            parts.append(subaction)
        out_dir = Path(output_root).joinpath(*parts)
        out_dir.mkdir(parents=True, exist_ok=True)

        png_files: list[str] = []
        if format in {'png', 'both'}:
            for idx, im in enumerate(frames):
                p = out_dir / f'{idx:02d}.png'
                im.save(p)
                png_files.append(str(p))

        gif_files: list[str] = []
        if format in {'gif', 'both'}:
            gif_path = out_dir / f'{subaction or action}.gif'
            gif_frames = frames if len(frames) > 1 else [frames[0], frames[0].copy()]
            pframes = [self._to_gif_palette(im) for im in gif_frames]
            pframes[0].save(
                gif_path,
                save_all=True,
                append_images=pframes[1:],
                duration=[frame_ms] * len(pframes),
                loop=0 if result.loop else 1,
                disposal=2,
                transparency=255,
            )
            gif_files.append(str(gif_path))

        return {
            'character_id': character_id,
            'action': action,
            'direction': result.direction,
            'subaction': subaction,
            'frame_ids': result.frame_ids,
            'loop': result.loop,
            'png_files': png_files,
            'gif_files': gif_files,
            'cache_only': True,
        }
