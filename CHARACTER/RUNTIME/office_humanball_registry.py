from __future__ import annotations

import json
from pathlib import Path

from .humanball_registry import HumanBallRegistryError


class OfficeHumanBallRegistryError(HumanBallRegistryError):
    """Raised when the office-specific HumanBall pool is invalid."""


class OfficeHumanBallRegistry:
    """Load the separate 38-item office HumanBall pool."""

    SCHEMA = "gds_office_humanball_registry_v1"
    COUNT = 38

    def __init__(self, core_root: str | Path):
        self.core_root = Path(core_root)
        path = self.core_root / "EFFECTS" / "office_humanball_v1.json"
        if not path.is_file():
            raise OfficeHumanBallRegistryError(f"Missing office HumanBall registry: {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OfficeHumanBallRegistryError(f"Cannot load office HumanBall registry: {path}") from exc
        if data.get("schema") != self.SCHEMA:
            raise OfficeHumanBallRegistryError(
                f"Unsupported office HumanBall registry schema: {data.get('schema')}"
            )
        items = data.get("office_humanballs")
        order = data.get("office_humanball_order")
        if not isinstance(items, dict) or not isinstance(order, list):
            raise OfficeHumanBallRegistryError("Invalid office HumanBall registry structure")
        if (
            len(order) != data.get("office_humanball_count")
            or len(order) != self.COUNT
            or set(order) != set(items)
        ):
            raise OfficeHumanBallRegistryError("office_humanball_order/count mismatch")
        if any(items[item_id].get("humanball_id") != item_id for item_id in order):
            raise OfficeHumanBallRegistryError("office HumanBall record IDs do not match order")
        animation = data.get("animation", {})
        if int(animation.get("total_frames", -1)) != 12:
            raise OfficeHumanBallRegistryError("Office HumanBall animation must contain 12 frames")
        if int(animation.get("visible_frames", -1)) != 10 or int(animation.get("hidden_frames", -1)) != 2:
            raise OfficeHumanBallRegistryError("Office HumanBall animation must contain 10 visible + 2 hidden frames")
        motion = data.get("motion_offsets_from_character_top_left_px", {})
        if any(len(motion.get(direction, [])) != 10 for direction in ("NW", "SE")):
            raise OfficeHumanBallRegistryError("Office HumanBall motion must contain 10 visible offsets")
        self.data = data
        self.items = items
        self.order = list(order)

    def list(self) -> list[str]:
        return list(self.order)

    def get(self, humanball_id: str) -> dict:
        try:
            return self.items[humanball_id]
        except KeyError as exc:
            raise OfficeHumanBallRegistryError(
                f"Unknown office HumanBall: {humanball_id}"
            ) from exc
