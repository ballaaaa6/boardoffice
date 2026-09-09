from __future__ import annotations

from pathlib import Path

from .humanball_renderer import HumanBallRenderer
from .office_humanball_registry import OfficeHumanBallRegistry


class OfficeHumanBallRenderer(HumanBallRenderer):
    """Render office icons with the canonical HumanBall timeline and offsets."""

    def __init__(self, core_root: str | Path, *, verify_asset_hashes: bool = False):
        super().__init__(
            core_root,
            verify_asset_hashes=verify_asset_hashes,
            registry=OfficeHumanBallRegistry(core_root),
        )
