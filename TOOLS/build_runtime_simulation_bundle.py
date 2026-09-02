from __future__ import annotations

"""Build the metadata-only bootstrap consumed by the browser simulation."""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from CHARACTER.RUNTIME.frame_rules import load_frame_registry
from RUNTIME.browser_bundle_contract import (
    BUNDLE_SCHEMA,
    VERSION,
    bundle_revision,
    canonical_json,
    canonical_source_hashes,
    validate_bundle,
)
from RUNTIME.central_core import CentralGameCore


DEFAULT_FLOOR_ID = "floor02"
SEED_NAMESPACE = "gds-browser-runtime-v1"
BUILDER_VERSION = "browser-owned-simulation-2026-09-03"


class BrowserBundleBuildError(ValueError):
    """Raised when browser runtime inputs cannot be exported."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserBundleBuildError(f"cannot load JSON source: {path}") from exc
    if not isinstance(value, dict):
        raise BrowserBundleBuildError(f"JSON source must be an object: {path}")
    return value


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise BrowserBundleBuildError(f"runtime input is not JSON-safe: {exc}") from exc


def _world_inputs(core: CentralGameCore, floor_id: str) -> dict[str, Any]:
    layout = core.world.floor_layout(floor_id)
    return _json_copy({
        "floor": core.world.floor_record(floor_id),
        "layout": layout,
        "placements": core.world.resolve_floor_placements(floor_id),
        "navigation": core.navigation_occupancy.resolve_floor(floor_id),
        "room_navigation": {
            "grid": core.room_navigation.grid_profile(),
            "family": core.room_navigation.family(floor_id),
            "domain": core.room_navigation.domain(floor_id),
            "portal": core.room_navigation.portal(floor_id),
            "room_cells": core.room_navigation.room_cells(floor_id),
        },
    })


def _work_seat_inputs(core: CentralGameCore, floor_id: str) -> dict[str, Any]:
    groups = core.world.floor_layout(floor_id).get("workstation_groups", {})
    result: dict[str, Any] = {}
    for workstation_id in sorted(groups):
        result[workstation_id] = {
            "seat": core.work_seats.resolve_workstation_seat(floor_id, workstation_id),
            "navigation_access": core.navigation_occupancy.workstation_access(
                floor_id, workstation_id
            ),
        }
    return _json_copy(result)


def _character_inputs(core: CentralGameCore, floor_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    roster = core.employee_metadata.initial_roster(floor_id)
    employees = {
        row["employee_id"]: {
            **row,
            "movement_profile": core.employee_metadata.movement_profile(row["employee_id"]),
            "stamina_profile": core.resolve_employee_stamina_profile(
                row["employee_id"]
            ),
        }
        for row in roster
    }
    character_records: dict[str, dict[str, Any]] = {}
    requests = core.characters.list_action_requests()
    for row in roster:
        character_id = str(row["character_id"])
        if character_id in character_records:
            continue
        technical = core.characters.get_character(character_id)
        body_asset_id = str(technical["body_asset_id"])
        face_asset_id = str(technical["face_asset_id"])
        frame_refs: list[dict[str, Any]] = []
        for request in requests:
            frame_ids = core.characters.resolve_frame_ids(
                character_id,
                request["action"],
                request["direction"],
                request["subaction"],
            )
            frame_refs.append({
                "action": request["action"],
                "direction": request["direction"],
                "subaction": request["subaction"],
                "frame_ids": list(frame_ids),
            })
        character_records[character_id] = {
            "character_id": character_id,
            "body_asset_id": body_asset_id,
            "face_asset_id": face_asset_id,
            "asset_refs": [body_asset_id, face_asset_id],
            "render_canvas": technical.get("render_canvas", [32, 42]),
            "frame_refs": frame_refs,
        }
    return _json_copy(employees), _json_copy(dict(sorted(character_records.items())))


def _asset_inputs(core: CentralGameCore, characters: dict[str, Any]) -> dict[str, Any]:
    refs = {
        str(asset_id)
        for record in characters.values()
        for asset_id in record["asset_refs"]
    }
    assets: dict[str, Any] = {}
    for asset_id in sorted(refs):
        metadata = core.character_assets.metadata(asset_id)
        assets[asset_id] = {
            "asset_id": asset_id,
            "domain": "character",
            "path": metadata.get("path"),
            "sha256": metadata.get("sha256"),
            "dimensions": metadata.get("dimensions"),
        }
    for asset_id, metadata in sorted(core.world.assets.items()):
        assets[str(asset_id)] = {
            "asset_id": str(asset_id),
            "domain": "world",
            "blob_id": metadata.get("blob_id"),
            "dimensions": [metadata.get("width"), metadata.get("height")],
        }
    return _json_copy(assets)


def _dialogue_inputs(core: CentralGameCore) -> dict[str, Any]:
    bubble_data = core.characters.dialogue_bubbles.data
    return _json_copy({
        "lines": core.characters.list_dialogue_lines(enabled_only=True),
        "bubble_policy": {
            "allowed_bubble_ids": bubble_data.get("allowed_bubble_ids", []),
            "excluded_bubble_ids": bubble_data.get("excluded_bubble_ids", []),
            "selection": bubble_data.get("selection", {}),
            "text_layout": bubble_data.get("text_layout", {}),
            "presets": bubble_data.get("presets", []),
        },
    })


def _effect_inputs(core: CentralGameCore) -> dict[str, Any]:
    return _json_copy({
        "effects": core.characters.effects.data,
        "humanballs": core.characters.humanballs.data,
    })


def _simulation_constants(core: CentralGameCore) -> dict[str, Any]:
    return _json_copy({
        "actor_tick_ms": int(core.actor_simulation.TICK_MS),
        "speech_tick_ms": int(core.speech_scheduler.TICK_MS),
        "character_canvas": [32, 42],
        "directions": ["NE", "SE", "SW", "NW"],
        "event_emotions": ["happy", "sad"],
    })


def build_bundle(root: str | Path, floor_id: str = DEFAULT_FLOOR_ID) -> dict[str, Any]:
    """Build one deterministic, image-free browser runtime bundle."""
    project_root = Path(root).resolve()
    if not isinstance(floor_id, str) or not floor_id.strip():
        raise BrowserBundleBuildError("floor_id must be non-empty text")
    core = CentralGameCore(project_root)
    if floor_id not in core.world.floors:
        raise BrowserBundleBuildError(f"unknown floor: {floor_id}")

    employees, characters = _character_inputs(core, floor_id)
    action_set = _load_json(project_root / "CHARACTER" / "ACTIONS" / "gds_standard_v1.json")
    frame_registry = load_frame_registry(project_root / "CHARACTER")
    bundle: dict[str, Any] = {
        "schema": BUNDLE_SCHEMA,
        "version": VERSION,
        "builder": BUILDER_VERSION,
        "floor_id": floor_id,
        "source_hashes": canonical_source_hashes(project_root),
        "simulation": {
            "step_ms": 60,
            "seed_namespace": SEED_NAMESPACE,
            "constants": _simulation_constants(core),
        },
        "world": _world_inputs(core, floor_id),
        "work_seats": _work_seat_inputs(core, floor_id),
        "employees": employees,
        "characters": characters,
        "assets": _asset_inputs(core, characters),
        "actions": _json_copy(action_set["actions"]),
        "frame_profile": _json_copy(frame_registry["render_profile"]),
        "frame_rules": _json_copy(frame_registry["frames"]),
        "dialogue": _dialogue_inputs(core),
        "effects": _effect_inputs(core),
        "initial_snapshot": core.resolve_runtime_snapshot(
            floor_id,
            simulation_seed=SEED_NAMESPACE,
        ),
    }
    bundle["bundle_revision"] = bundle_revision(bundle)
    return validate_bundle(bundle, root=project_root, expected_floor_id=floor_id)


def write_bundle(
    root: str | Path,
    floor_id: str = DEFAULT_FLOOR_ID,
    output: str | Path | None = None,
) -> dict[str, Any]:
    project_root = Path(root).resolve()
    output_path = (
        Path(output).resolve()
        if output is not None
        else project_root / "WEB" / "runtime_simulation_bootstrap.json"
    )
    bundle = build_bundle(project_root, floor_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_json(bundle) + "\n", encoding="utf-8", newline="\n")
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--floor-id", default=DEFAULT_FLOOR_ID)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    bundle = write_bundle(args.root, args.floor_id, args.output)
    output_path = (
        Path(args.output).resolve()
        if args.output is not None
        else Path(args.root).resolve() / "WEB" / "runtime_simulation_bootstrap.json"
    )
    print(json.dumps({
        "schema": bundle["schema"],
        "floor_id": bundle["floor_id"],
        "bundle_revision": bundle["bundle_revision"],
        "employee_count": len(bundle["employees"]),
        "character_count": len(bundle["characters"]),
        "output": str(output_path),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
