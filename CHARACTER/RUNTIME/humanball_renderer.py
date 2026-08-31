from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .asset_registry import AssetRegistry, AssetResolutionError
from .humanball_registry import HumanBallRegistry, HumanBallRegistryError


class HumanBallRenderError(ValueError):
    pass


@dataclass
class HumanBallRenderResult:
    humanball_id: str
    direction: str
    asset_id: str
    frames: list[Image.Image | None]
    offsets: list[tuple[int, int] | None]
    visible_frame_count: int
    loop: bool
    frame_ms: int
    derived_from: str | None = None
    transform: str | None = None


class HumanBallRenderer:
    def __init__(self, core_root: str | Path, *, verify_asset_hashes: bool = False):
        self.core_root = Path(core_root)
        self.registry = HumanBallRegistry(self.core_root)
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
            raise HumanBallRenderError(str(exc)) from exc
        with Image.open(path) as im:
            rgba = im.convert('RGBA')
        if rgba.size != (18, 18):
            raise HumanBallRenderError(f'{asset_id} must be 18x18, got {rgba.size}')
        self._image_cache[asset_id] = rgba
        return rgba.copy()

    def render_humanball(
        self,
        humanball_id: str,
        direction: str,
        *,
        human_size: tuple[int, int] = (32, 42),
    ) -> HumanBallRenderResult:
        key = direction.upper()
        if key not in {'NW', 'SE', 'SW', 'NE'}:
            raise HumanBallRenderError(f'HumanBall direction must be NW, SE, SW, or NE: {direction}')
        try:
            meta = self.registry.get(humanball_id)
        except HumanBallRegistryError as exc:
            raise HumanBallRenderError(str(exc)) from exc

        asset_id = meta['asset_id']
        icon = self._load_asset(asset_id)
        animation = self.registry.data['animation']
        visible_count = int(animation['visible_frames'])
        hidden_count = int(animation['hidden_frames'])
        source_direction = {'SW': 'SE', 'NE': 'NW'}.get(key, key)
        source_offsets = [tuple(map(int, pair)) for pair in self.registry.data['motion_offsets_from_character_top_left_px'][source_direction]]
        derived_from = None
        transform = None
        if key in {'SW', 'NE'}:
            human_w, _ = human_size
            popup_w, _ = icon.size
            source_offsets = [(int(human_w) - (x + popup_w), y) for x, y in source_offsets]
            derived_from = source_direction
            transform = 'mirror_relation_x'

        offsets: list[tuple[int, int] | None] = list(source_offsets) + [None] * hidden_count
        frames: list[Image.Image | None] = [icon.copy() for _ in range(visible_count)] + [None] * hidden_count
        if len(frames) != int(animation['total_frames']):
            raise HumanBallRenderError('HumanBall logical timeline does not match registry total_frames')
        return HumanBallRenderResult(
            humanball_id=humanball_id,
            direction=key,
            asset_id=asset_id,
            frames=frames,
            offsets=offsets,
            visible_frame_count=visible_count,
            loop=animation.get('mode', 'loop') == 'loop',
            frame_ms=int(animation.get('frame_ms', 140)),
            derived_from=derived_from,
            transform=transform,
        )
