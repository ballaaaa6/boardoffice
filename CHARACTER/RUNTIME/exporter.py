from __future__ import annotations

import json
from pathlib import Path
from PIL import Image

from .character_system import CharacterSystem, CharacterSystemError


class CharacterExporter:
    def __init__(self, system: CharacterSystem):
        self.system = system

    @staticmethod
    def _write_json(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


    @staticmethod
    def _scale(im: Image.Image, scale: int) -> Image.Image:
        if scale < 1:
            raise CharacterSystemError('scale must be >= 1')
        if scale == 1:
            return im.copy()
        return im.resize((im.width * scale, im.height * scale), Image.Resampling.NEAREST)

    @staticmethod
    def _build_global_gif_palette(frames: list[Image.Image]) -> list[int]:
        if not frames:
            raise CharacterSystemError('GIF export requires at least one frame')
        strip = Image.new('RGBA', (frames[0].width * len(frames), frames[0].height), (0, 0, 0, 0))
        for idx, frame in enumerate(frames):
            if frame.size != frames[0].size:
                raise CharacterSystemError('All GIF frames must share the same size')
            strip.alpha_composite(frame.convert('RGBA'), (idx * frame.width, 0))
        alpha = strip.getchannel('A')
        rgb = Image.new('RGB', strip.size, (0, 0, 0))
        rgb.paste(strip, mask=alpha)
        pal = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        palette = pal.getpalette() or []
        if len(palette) < 768:
            palette += [0] * (768 - len(palette))
        return palette[:768]

    @classmethod
    def _to_gif_palette(cls, im: Image.Image, palette: list[int] | None = None) -> Image.Image:
        rgba = im.convert('RGBA')
        alpha = rgba.getchannel('A')
        rgb = Image.new('RGB', rgba.size, (0, 0, 0))
        rgb.paste(rgba, mask=alpha)
        if palette is None:
            pal = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
            palette = pal.getpalette() or []
            if len(palette) < 768:
                palette += [0] * (768 - len(palette))
            palette = palette[:768]
        palette_image = Image.new('P', (1, 1))
        palette_image.putpalette(palette)
        pal = rgb.quantize(colors=255, palette=palette_image, dither=Image.Dither.NONE)
        transparent_mask = alpha.point(lambda a: 255 if a == 0 else 0)
        pal.paste(255, mask=transparent_mask)
        pal.putpalette(palette)
        pal.info['transparency'] = 255
        return pal

    def export_composition_action(
        self,
        body_asset_id: str,
        face_asset_id: str,
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
            raise CharacterSystemError("format must be 'png', 'gif', or 'both'")
        if frame_ms < 1:
            raise CharacterSystemError('frame_ms must be >= 1')
        result = self.system.render_composition(
            body_asset_id, face_asset_id, action, direction, subaction
        )
        frames = [self._scale(im, scale) for im in result.frames]
        comp_slug = f'{body_asset_id.replace(".", "_")}__{face_asset_id.replace(".", "_")}'
        parts = ['COMPOSED', comp_slug, action]
        if result.direction:
            parts.append(result.direction.lower())
        if subaction:
            parts.append(subaction)
        out_dir = Path(output_root).joinpath(*parts)
        out_dir.mkdir(parents=True, exist_ok=True)

        png_files = []
        if format in {'png', 'both'}:
            for idx, im in enumerate(frames):
                path = out_dir / f'{idx:02d}.png'
                im.save(path)
                png_files.append(str(path))

        gif_files = []
        if format in {'gif', 'both'}:
            path = out_dir / f'{subaction or action}.gif'
            gif_frames = frames if len(frames) > 1 else [frames[0], frames[0].copy()]
            palette = self._build_global_gif_palette(gif_frames)
            pal = [self._to_gif_palette(im, palette) for im in gif_frames]
            pal[0].save(
                path, save_all=True, append_images=pal[1:],
                duration=[frame_ms] * len(pal), loop=0 if result.loop else 1,
                disposal=2, transparency=255,
            )
            gif_files.append(str(path))

        return {
            'composition': {'body': body_asset_id, 'face': face_asset_id},
            'matched_character_ids': self.system.find_characters(body_asset_id, face_asset_id),
            'action': action, 'direction': result.direction, 'subaction': subaction,
            'frame_ids': result.frame_ids, 'loop': result.loop,
            'png_files': png_files, 'gif_files': gif_files, 'cache_only': True,
        }

    def export_action(
        self,
        character_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        effect_id: str | None = None,
        output_root: str | Path,
        format: str = 'gif',
        scale: int = 1,
        frame_ms: int = 360,
    ) -> dict:
        if character_id not in self.system.core.characters:
            raise CharacterSystemError(f'Unknown character: {character_id}')
        if effect_id is None:
            return self.system.core.renderer.export_action(
                character_id,
                action,
                direction,
                subaction,
                output_root=output_root,
                format=format,
                scale=scale,
                frame_ms=frame_ms,
            )
        if format not in {'png', 'gif', 'both'}:
            raise CharacterSystemError("format must be 'png', 'gif', or 'both'")
        if frame_ms < 1:
            raise CharacterSystemError('frame_ms must be >= 1')
        result = self.system.render(
            character_id, action, direction, subaction, effect_id=effect_id
        )
        frames = [self._scale(im, scale) for im in result.frames]
        parts = [character_id, action]
        if result.direction:
            parts.append(result.direction.lower())
        if subaction:
            parts.append(subaction)
        parts.append(f'effect_{effect_id}')
        out_dir = Path(output_root).joinpath(*parts)
        out_dir.mkdir(parents=True, exist_ok=True)

        png_files: list[str] = []
        if format in {'png', 'both'}:
            for idx, im in enumerate(frames):
                path = out_dir / f'{idx:02d}.png'
                im.save(path)
                png_files.append(str(path))

        gif_files: list[str] = []
        if format in {'gif', 'both'}:
            path = out_dir / f'{effect_id}.gif'
            gif_frames = frames if len(frames) > 1 else [frames[0], frames[0].copy()]
            palette = self._build_global_gif_palette(gif_frames)
            pal = [self._to_gif_palette(im, palette) for im in gif_frames]
            pal[0].save(
                path, save_all=True, append_images=pal[1:],
                duration=[frame_ms] * len(pal), loop=0 if result.loop else 1,
                disposal=2, transparency=255,
            )
            gif_files.append(str(path))

        return {
            'character_id': character_id,
            'action': action, 'direction': result.direction, 'subaction': subaction,
            'frame_ids': result.frame_ids, 'loop': result.loop,
            'effect_id': effect_id,
            'effect_frame_asset_ids': result.effect_frame_asset_ids,
            'presentation_canvas': list(result.presentation_canvas),
            'png_files': png_files, 'gif_files': gif_files, 'cache_only': True,
        }

    def export_character(
        self,
        character_id: str,
        output_root: str | Path,
        *,
        format: str = 'gif',
        scale: int = 1,
        frame_ms: int = 360,
    ) -> dict:
        if character_id not in self.system.core.characters:
            raise CharacterSystemError(f'Unknown character: {character_id}')
        root = Path(output_root)
        entries = []
        frame_occurrences = 0
        for request in self.system.list_action_requests():
            result = self.export_action(
                character_id,
                request['action'],
                request['direction'],
                request['subaction'],
                output_root=root,
                format=format,
                scale=scale,
                frame_ms=frame_ms,
            )
            frame_occurrences += len(result['frame_ids'])
            entries.append({
                'action': result['action'],
                'direction': result['direction'],
                'subaction': result['subaction'],
                'frame_ids': result['frame_ids'],
                'loop': result['loop'],
                'png_files': [str(Path(p).relative_to(root)) for p in result['png_files']],
                'gif_files': [str(Path(p).relative_to(root)) for p in result['gif_files']],
            })
        manifest = {
            'schema': 'gds_character_export_v1',
            'character_id': character_id,
            'action_set': 'gds_standard_v1',
            'action_request_count': len(entries),
            'frame_occurrence_count': frame_occurrences,
            'format': format,
            'scale': scale,
            'frame_ms': frame_ms,
            'derived_cache_only': True,
            'actions': entries,
        }
        self._write_json(root / character_id / 'EXPORT_MANIFEST.json', manifest)
        return manifest

    def export_all(
        self,
        output_root: str | Path,
        *,
        character_ids: list[str] | None = None,
        format: str = 'gif',
        scale: int = 1,
        frame_ms: int = 360,
    ) -> dict:
        root = Path(output_root)
        ids = sorted(character_ids) if character_ids is not None else self.system.list_characters()
        manifests = []
        for character_id in ids:
            manifests.append(self.export_character(
                character_id,
                root,
                format=format,
                scale=scale,
                frame_ms=frame_ms,
            ))
        manifest = {
            'schema': 'gds_all_characters_export_v1',
            'character_count': len(manifests),
            'action_requests_per_character': len(self.system.list_action_requests()),
            'action_request_count': sum(m['action_request_count'] for m in manifests),
            'frame_occurrence_count': sum(m['frame_occurrence_count'] for m in manifests),
            'format': format,
            'scale': scale,
            'frame_ms': frame_ms,
            'derived_cache_only': True,
            'characters': [m['character_id'] for m in manifests],
        }
        self._write_json(root / 'EXPORT_ALL_MANIFEST.json', manifest)
        return manifest
