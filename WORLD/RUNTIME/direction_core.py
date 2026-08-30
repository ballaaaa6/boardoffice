from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .layout_core import LayoutCore


class DirectionCore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.world = LayoutCore(self.root)
        self.direction_registry = self._read("workstation_directions.json")
        self.bridge = self._read("character_direction_bridge.json")
        self.layout_directions = self.direction_registry["layout_directions"]

    def _read(self, name: str) -> dict[str, Any]:
        return json.loads((self.root / "REGISTRY" / name).read_text(encoding="utf-8"))

    def resolve_direction_record(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        floor = self.world.floor_record(floor_id)
        layout_id = floor["layout_id"]
        layout = self.world.floor_layout(floor_id)
        if workstation_id not in layout["workstation_groups"]:
            raise KeyError(f"Unknown workstation for {floor_id}: {workstation_id}")
        try:
            profile = self.layout_directions[layout_id]
            record = profile["workstations"][workstation_id]
        except KeyError as exc:
            raise KeyError(f"No direction profile for {floor_id}.{workstation_id} via {layout_id}") from exc
        authoring_floor_id = profile["authoring_floor_id"]
        return {
            "floor_id": floor_id,
            "layout_id": layout_id,
            "workstation_id": workstation_id,
            "canonical_workstation_id": f"{floor_id}.{workstation_id}",
            "interaction_direction": record["interaction_direction"],
            "authoring_floor_id": authoring_floor_id,
            "authoring_source": record["authoring_source"],
            "resolution_mode": "authored_layout_profile" if floor_id == authoring_floor_id else "inherited_layout_profile",
        }

    def resolve_workstation_direction(self, floor_id: str, workstation_id: str) -> str:
        return self.resolve_direction_record(floor_id, workstation_id)["interaction_direction"]

    def map_world_direction_to_character_action(self, direction: str, action_family: str = "work") -> str:
        direction = direction.upper()
        if direction not in self.bridge["world_direction_vocabulary"]:
            raise ValueError(f"Unknown world direction: {direction}")
        try:
            action = self.bridge["action_families"][action_family]
        except KeyError as exc:
            raise KeyError(f"Unknown character action family: {action_family}") from exc
        mapping = action["mapping"]
        if direction not in mapping:
            raise ValueError(
                f"World direction {direction} is not supported by character action family {action_family}; "
                f"supported={action['supported_directions']} policy={action['unsupported_policy']}"
            )
        return mapping[direction]

    def resolve_character_action_direction(self, floor_id: str, workstation_id: str, action_family: str = "work") -> str:
        direction = self.resolve_workstation_direction(floor_id, workstation_id)
        return self.map_world_direction_to_character_action(direction, action_family=action_family)
