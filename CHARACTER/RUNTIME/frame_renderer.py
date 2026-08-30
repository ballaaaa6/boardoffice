from __future__ import annotations

from pathlib import Path
from PIL import Image

from .character_assets import CharacterAssetResolver, CharacterAssetResolutionError
from .frame_rules import load_frame_registry, resolve_frame_rule, FrameRuleError


class FrameRenderError(ValueError):
    pass


class CharacterFrameRenderer:
    def __init__(self, core_root: str | Path, *, verify_asset_hashes: bool = False):
        self.core_root = Path(core_root)
        self.verify_asset_hashes = verify_asset_hashes
        self.assets = CharacterAssetResolver(self.core_root)
        self.frame_registry = load_frame_registry(self.core_root)
        profile = self.frame_registry['render_profile']
        self.canvas = tuple(profile['canvas'])
        self.origin = tuple(profile['origin'])
        self._image_cache: dict[Path, Image.Image] = {}

    def _load_rgba(self, path: Path) -> Image.Image:
        cached = self._image_cache.get(path)
        if cached is None:
            with Image.open(path) as im:
                cached = im.convert('RGBA')
            self._image_cache[path] = cached
        return cached

    @staticmethod
    def _crop(sheet: Image.Image, src: list[int]) -> Image.Image:
        x, y, w, h = src
        return sheet.crop((x, y, x + w, y + h))

    def _position(self, dst: list[int], *, dy: int = 0) -> tuple[int, int]:
        return self.origin[0] + dst[0], self.origin[1] + dst[1] + dy

    def _render_native(self, body: Image.Image, face: Image.Image, rule: dict) -> Image.Image:
        canvas = Image.new('RGBA', self.canvas, (0, 0, 0, 0))
        body_rule = rule['body']
        face_rule = rule['face']

        if not rule.get('special_split_body', False):
            body_part = self._crop(body, body_rule['src'])
            face_part = self._crop(face, face_rule['src'])
            canvas.alpha_composite(body_part, self._position(body_rule['dst']))
            canvas.alpha_composite(face_part, self._position(face_rule['dst']))
            return canvas

        split = rule.get('split_body')
        if not split:
            raise FrameRenderError(f"Missing split_body definition for {rule.get('frame_id')}")

        sx, sy, bw, _ = body_rule['src']
        top_h = split['top_height']
        full_h = split['full_body_height']
        shift_y = split['shift_y']
        if not (0 < top_h < full_h):
            raise FrameRenderError(f"Invalid split heights for {rule.get('frame_id')}")

        top = body.crop((sx, sy, sx + bw, sy + top_h))
        lower = body.crop((sx, sy + top_h, sx + bw, sy + full_h))
        face_part = self._crop(face, face_rule['src'])
        bx, by = self._position(body_rule['dst'])

        # Verified special animation rule: head/upper body bob down by one pixel,
        # while the lower body remains anchored at the ordinary body baseline.
        canvas.alpha_composite(top, (bx, by + shift_y))
        canvas.alpha_composite(face_part, self._position(face_rule['dst'], dy=shift_y))
        canvas.alpha_composite(lower, (bx, by + top_h))
        return canvas

    def _render_resolved(self, resolved: dict, frame_id: str) -> Image.Image:
        try:
            rule = resolve_frame_rule(self.frame_registry, frame_id)
        except FrameRuleError as exc:
            raise FrameRenderError(str(exc)) from exc

        if rule['kind'] == 'derived':
            source = self._render_resolved(resolved, rule['source_frame_id'])
            transform = rule['transform']
            if transform == 'mirror_y':
                return source.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            raise FrameRenderError(f'Unsupported transform: {transform}')

        if rule['kind'] != 'native':
            raise FrameRenderError(f"Unsupported frame kind: {rule.get('kind')}")
        body = self._load_rgba(resolved['body'])
        face = self._load_rgba(resolved['face'])
        return self._render_native(body, face, rule)

    def render_composition_frame(self, body_asset_id: str, face_asset_id: str, frame_id: str) -> Image.Image:
        try:
            resolved = self.assets.resolve_composition(
                body_asset_id, face_asset_id, verify_hash=self.verify_asset_hashes
            )
        except CharacterAssetResolutionError as exc:
            raise FrameRenderError(str(exc)) from exc
        return self._render_resolved(resolved, frame_id)

    def render_frame(self, character_id: str, frame_id: str) -> Image.Image:
        try:
            resolved = self.assets.resolve(character_id, verify_hash=self.verify_asset_hashes)
        except CharacterAssetResolutionError as exc:
            raise FrameRenderError(str(exc)) from exc
        return self._render_resolved(resolved, frame_id)
