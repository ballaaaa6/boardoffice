from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .direction_core import DirectionCore
from .layout_core import LayoutCore


class SpatialCore:
    PRIMARY_OBJECT_TYPES = frozenset({"chair", "desk", "pc", "reception"})

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.world = LayoutCore(self.root)
        self.directions = DirectionCore(self.root)
        data = json.loads((self.root / "REGISTRY" / "spatial_profiles.json").read_text(encoding="utf-8"))
        self.registry = data
        self.profiles = data["profiles"]

    @staticmethod
    def _world_bounds(render_x: int, render_y: int, bounds: dict[str, int] | None) -> dict[str, int] | None:
        if bounds is None:
            return None
        return {
            "left": render_x + bounds["left"],
            "top": render_y + bounds["top"],
            "right": render_x + bounds["right"],
            "bottom": render_y + bounds["bottom"],
            "width": bounds["width"],
            "height": bounds["height"],
        }

    def _placement_map(self, floor_id: str) -> dict[str, dict[str, Any]]:
        return {p["placement_id"]: p for p in self.world.resolve_floor_placements(floor_id)}

    def _slot_metadata(self, floor_id: str, placement_id: str) -> dict[str, Any] | None:
        layout = self.world.floor_layout(floor_id)
        for slot in layout.get("slots", []):
            if slot["slot_id"] == placement_id:
                return slot
        for slot in layout.get("semantic_slots", []):
            if slot["slot_id"] == placement_id:
                return slot
        return None

    def _foreground_fragment(self, floor_id: str, workstation_id: str | None, placements: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        if workstation_id is None:
            return None
        group = self.world.workstation_group(floor_id, workstation_id)
        fragment_id = group.get("optional_component_slots", {}).get("chair_foreground")
        if not fragment_id or fragment_id not in placements:
            return None
        fragment = placements[fragment_id]
        return {
            "placement_id": fragment_id,
            "object_type": fragment["object_type"],
            "relationship": "foreground_fragment",
            "layer": fragment["layer"],
        }

    def resolve_object(self, floor_id: str, placement_id: str) -> dict[str, Any]:
        placements = self._placement_map(floor_id)
        try:
            placement = placements[placement_id]
        except KeyError as exc:
            raise KeyError(f"Unknown placement for {floor_id}: {placement_id}") from exc

        if placement["object_type"] not in self.PRIMARY_OBJECT_TYPES:
            raise KeyError(
                f"Placement {floor_id}.{placement_id} is not a Phase 6 primary spatial object: "
                f"{placement['object_type']}"
            )

        profile = self.profiles[placement["variant_id"]]
        floor = self.world.floor_record(floor_id)
        slot = self._slot_metadata(floor_id, placement_id)
        workstation_id = slot.get("workstation_id") if slot else None
        component_role = slot.get("component_role") if slot else None
        direction = None
        if workstation_id is not None:
            direction = self.directions.resolve_workstation_direction(floor_id, workstation_id)

        render_x = int(placement["x_px"])
        render_y = int(placement["y_px"])
        bounds_world = self._world_bounds(render_x, render_y, profile["visual_bounds_px"])
        semantic_anchor = placement.get("semantic_anchor")

        foreground_fragment = None
        if component_role == "chair_main":
            foreground_fragment = self._foreground_fragment(floor_id, workstation_id, placements)

        return {
            "object_id": placement["canonical_placement_id"],
            "floor_id": floor_id,
            "placement_id": placement_id,
            "object_type": placement["object_type"],
            "asset_id": placement["asset_id"],
            "variant_id": placement["variant_id"],
            "transform": placement["transform"],
            "workstation_direction": direction,
            "render": {
                "x_px": render_x,
                "y_px": render_y,
                "layer": int(placement["layer"]),
                "anchor_type": "sprite_top_left",
            },
            "visual": {
                "canvas_size_px": profile["canvas_size_px"],
                "visual_bounds_local_px": profile["visual_bounds_px"],
                "visual_bounds_world_px": bounds_world,
                "transparent_padding_px": profile["transparent_padding_px"],
                "evidence": profile["evidence"],
            },
            "spatial": {
                "coordinate_frame_id": floor["coordinate_frame_id"],
                "semantic_anchor": semantic_anchor,
                "footprint": None,
            },
            "physics": {
                "solid": None,
                "collision_shape": None,
            },
            "interaction": {
                "anchor": None,
                "radius_px": None,
            },
            "relationships": {
                "workstation_id": workstation_id,
                "component_role": component_role,
                "foreground_fragment": foreground_fragment,
            },
        }

    def list_objects(self, floor_id: str, object_types: Iterable[str] | None = None) -> list[dict[str, Any]]:
        allowed = self.PRIMARY_OBJECT_TYPES if object_types is None else frozenset(object_types)
        unknown = allowed - self.PRIMARY_OBJECT_TYPES
        if unknown:
            raise ValueError(f"Unsupported Phase 6 object types: {sorted(unknown)}")
        result = []
        for placement in self.world.resolve_floor_placements(floor_id):
            if placement["object_type"] in allowed:
                result.append(self.resolve_object(floor_id, placement["placement_id"]))
        return result

    def resolve_workstation_spatial(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        group = self.world.workstation_group(floor_id, workstation_id)
        direction = self.directions.resolve_workstation_direction(floor_id, workstation_id)
        components: dict[str, dict[str, Any]] = {}
        for role, placement_id in group["component_slots"].items():
            components[role] = self.resolve_object(floor_id, placement_id)

        placements = self._placement_map(floor_id)
        foreground = self._foreground_fragment(floor_id, workstation_id, placements)
        return {
            "floor_id": floor_id,
            "workstation_id": workstation_id,
            "canonical_workstation_id": f"{floor_id}.{workstation_id}",
            "direction": direction,
            "components": components,
            "foreground_fragment": foreground,
            "interaction_anchor": None,
            "seat_anchor": None,
            "footprint": None,
        }
