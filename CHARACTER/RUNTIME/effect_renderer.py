from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from PIL import Image

from .asset_registry import AssetRegistry, AssetResolutionError
from .effect_registry import EffectRegistry, EffectRegistryError


class EffectRenderError(ValueError):
    pass


@dataclass
class EffectRenderResult:
    effect_id: str
    direction: str
    source_frame_count: int
    frame_asset_ids: list[str]
    frames: list[Image.Image]
    loop: bool
    frame_ms: int
    derived_from: str | None = None
    transform: str | None = None


class EffectRenderer:
    def __init__(self, core_root: str | Path, *, verify_asset_hashes: bool = False):
        self.core_root = Path(core_root)
        self.registry = EffectRegistry(self.core_root)
        self.assets = AssetRegistry(self.core_root)
        self.verify_asset_hashes = verify_asset_hashes
        self._image_cache: dict[str, Image.Image] = {}

    def _load_asset(self, asset_id: str) -> Image.Image:
        cached = self._image_cache.get(asset_id)
        if cached is not None:
            return cached.copy()
        try:
            path = self.assets.resolve(asset_id, verify_hash=self.verify_asset_hashes)
        except AssetResolutionError as exc:
            raise EffectRenderError(str(exc)) from exc
        with Image.open(path) as im:
            rgba = im.convert('RGBA')
        if rgba.size != (33, 65):
            raise EffectRenderError(f'{asset_id} must be 33x65, got {rgba.size}')
        self._image_cache[asset_id] = rgba
        return rgba.copy()

    def render_effect(self, effect_id: str, direction: str) -> EffectRenderResult:
        direction = direction.upper()
        if direction not in {'NW', 'SE', 'SW'}:
            raise EffectRenderError(f'Effect direction must be NW, SE, or SW: {direction}')
        try:
            meta = self.registry.get(effect_id)
        except EffectRegistryError as exc:
            raise EffectRenderError(str(exc)) from exc

        if direction == 'SW':
            se = self.render_effect(effect_id, 'SE')
            return EffectRenderResult(
                effect_id=effect_id,
                direction='SW',
                source_frame_count=se.source_frame_count,
                frame_asset_ids=list(se.frame_asset_ids),
                frames=[f.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for f in se.frames],
                loop=se.loop,
                frame_ms=se.frame_ms,
                derived_from='SE',
                transform='mirror_y',
            )

        source_ids = list(meta['frame_asset_ids'])
        source_frames = [self._load_asset(aid) for aid in source_ids]
        anim = meta['animation']
        declared_source = int(anim['source_frames'])
        if len(source_frames) != declared_source:
            raise EffectRenderError(
                f'{effect_id}: source frame count {len(source_frames)} != {declared_source}'
            )
        order = list(anim['frame_order'])
        if any(i < 0 or i >= declared_source for i in order):
            raise EffectRenderError(f'{effect_id}: frame_order outside source frame range')
        frames = [source_frames[i].copy() for i in order]
        ids = [source_ids[i] for i in order]
        return EffectRenderResult(
            effect_id=effect_id,
            direction=direction,
            source_frame_count=declared_source,
            frame_asset_ids=ids,
            frames=frames,
            loop=anim.get('mode', 'loop') == 'loop',
            frame_ms=int(anim.get('frame_ms', 140)),
        )
