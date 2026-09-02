from __future__ import annotations

"""Build the derived component bundle consumed by the browser Canvas renderer.

The builder is intentionally the only new place that materializes component
images.  The live ``renderer=canvas`` request path consumes the generated
files and metadata; it never calls this module.
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from CHARACTER.RUNTIME.asset_registry import AssetRegistry
from CHARACTER.RUNTIME.frame_rules import load_frame_registry
from RUNTIME.central_core import CentralGameCore
from WORLD.RUNTIME.layout_core import LayoutCore


SCHEMA = "gds.runtime_render_manifest.v1"
VERSION = "1.0.0"
BUILDER_VERSION = "lean-component-renderer-2026-09-03"
DEFAULT_FLOOR_ID = "floor02"
CANVAS_SIZE = {"width": 600, "height": 600}
CHARACTER_SIZE = (32, 42)
EFFECT_SIZE = (33, 65)
HUMANBALL_SIZE = (18, 18)


class RuntimeRenderManifestError(ValueError):
    """Raised when a component bundle cannot be resolved deterministically."""


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes(root: Path) -> dict[str, str]:
    paths = (
        "WORLD/REGISTRY/floors.json",
        "WORLD/REGISTRY/floor_skins.json",
        "WORLD/REGISTRY/layouts.json",
        "WORLD/REGISTRY/world_assets.json",
        "WORLD/REGISTRY/visual_variants.json",
        "WORLD/REGISTRY/pc_animation.json",
        "WORLD/REGISTRY/walking_depth_profiles.json",
        "CHARACTER/CHARACTERS/characters.json",
        "CHARACTER/ACTIONS/gds_standard_v1.json",
        "CHARACTER/FRAME_RULES/frame_registry.json",
        "CHARACTER/ASSETS/asset_registry.json",
        "CHARACTER/EFFECTS/gds_effects_v1.json",
        "CHARACTER/EFFECTS/humanball_v1.json",
    )
    result: dict[str, str] = {}
    for relative in paths:
        path = root / relative
        if not path.is_file():
            raise RuntimeRenderManifestError(f"Missing canonical source: {relative}")
        result[relative] = _sha256_bytes(path)
    return result


def _file_record(output_dir: Path, path: Path, *, kind: str) -> dict[str, Any]:
    relative = path.relative_to(output_dir).as_posix()
    record: dict[str, Any] = {
        "file": relative,
        "url": f"/runtime_assets/{relative}",
        "kind": kind,
        "sha256": _sha256_bytes(path),
    }
    with Image.open(path) as image:
        record["width"] = int(image.width)
        record["height"] = int(image.height)
    return record


def _copy_asset(
    source: Path,
    output_dir: Path,
    relative: str,
    *,
    kind: str,
) -> dict[str, Any]:
    destination = output_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return _file_record(output_dir, destination, kind=kind)


def _write_image(
    image: Image.Image,
    output_dir: Path,
    relative: str,
    *,
    kind: str,
) -> dict[str, Any]:
    destination = output_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGBA").save(destination, format="PNG", optimize=False)
    return _file_record(output_dir, destination, kind=kind)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeRenderManifestError(f"Expected JSON object: {path}")
    return value


def _humanball_offsets(data: dict[str, Any]) -> dict[str, list[list[int] | None]]:
    animation = data["animation"]
    visible = int(animation["visible_frames"])
    hidden = int(animation["hidden_frames"])
    raw = data["motion_offsets_from_character_top_left_px"]
    result: dict[str, list[list[int] | None]] = {}
    for direction in ("NW", "SE", "SW", "NE"):
        source_direction = {"SW": "SE", "NE": "NW"}.get(direction, direction)
        offsets = [[int(pair[0]), int(pair[1])] for pair in raw[source_direction]]
        if direction in {"SW", "NE"}:
            offsets = [
                [CHARACTER_SIZE[0] - (x + HUMANBALL_SIZE[0]), y]
                for x, y in offsets
            ]
        if len(offsets) != visible:
            raise RuntimeRenderManifestError(
                f"HumanBall {direction} expected {visible} visible offsets"
            )
        result[direction] = offsets + [None] * hidden
    return result


def _effect_frames(
    root: Path,
    character_assets: AssetRegistry,
    effects: dict[str, Any],
    output_dir: Path,
    asset_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def ensure_asset(asset_id: str) -> dict[str, Any]:
        existing = asset_records.get(asset_id)
        if existing is not None:
            return existing
        source = character_assets.resolve(asset_id)
        metadata = character_assets.metadata(asset_id)
        relative = f"components/{_safe_name(asset_id)}.png"
        record = _copy_asset(source, output_dir, relative, kind="effect_frame")
        record.update({
            "asset_id": asset_id,
            "domain": "effect",
            "dimensions": list(metadata.get("dimensions", [record["width"], record["height"]])),
        })
        asset_records[asset_id] = record
        return record

    for effect_id in sorted(effects):
        meta = effects[effect_id]
        source_ids = list(meta["frame_asset_ids"])
        order = [int(value) for value in meta["animation"]["frame_order"]]
        if len(source_ids) != int(meta["animation"]["source_frames"]):
            raise RuntimeRenderManifestError(f"Effect source count mismatch: {effect_id}")
        source_frames = []
        for direction in ("NW", "SE", "SW", "NE"):
            source_direction = {"SW": "SE", "NE": "NW"}.get(direction, direction)
            mirror_x = direction in {"SW", "NE"}
            if source_direction not in {"NW", "SE"}:
                raise RuntimeRenderManifestError(f"Unsupported effect direction: {direction}")
            frames = []
            for index in order:
                asset_id = source_ids[index]
                record = ensure_asset(asset_id)
                frames.append({
                    "asset_id": asset_id,
                    "file": record["file"],
                    "url": record["url"],
                    "mirror_x": mirror_x,
                })
            source_frames.append((direction, frames))
        result[effect_id] = {
            "effect_id": effect_id,
            "frame_ms": int(meta["animation"].get("frame_ms", 240)),
            "loop": meta["animation"].get("mode", "loop") == "loop",
            "frames": dict(source_frames),
        }
    return result


def build_manifest(
    root: str | Path,
    *,
    floor_id: str = DEFAULT_FLOOR_ID,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build and write one deterministic component manifest."""
    root = Path(root).resolve()
    output = (
        Path(output_dir).resolve()
        if output_dir is not None
        else (root / "WEB" / "runtime_assets").resolve()
    )
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output.parent / "runtime_render_manifest.json"

    source_hashes = _source_hashes(root)
    core = CentralGameCore(root)
    layout: LayoutCore = core.world
    if floor_id not in layout.floors:
        raise RuntimeRenderManifestError(f"Unknown floor: {floor_id}")
    floor = layout.floor_record(floor_id)
    canvas_meta = floor.get("canvas", {})
    if {
        "width": int(canvas_meta.get("width_px", 0)),
        "height": int(canvas_meta.get("height_px", 0)),
    } != CANVAS_SIZE:
        raise RuntimeRenderManifestError(f"{floor_id}: expected a 600x600 canvas")

    placements = layout.resolve_floor_placements(floor_id)
    placement_by_id = {str(item["placement_id"]): item for item in placements}
    if len(placement_by_id) != len(placements):
        raise RuntimeRenderManifestError(f"{floor_id}: duplicate placement id")

    files: dict[str, dict[str, Any]] = {}
    variants: dict[str, dict[str, Any]] = {}
    asset_records: dict[str, dict[str, Any]] = {}

    def ensure_variant(variant_id: str) -> dict[str, Any]:
        existing = variants.get(variant_id)
        if existing is not None:
            return existing
        try:
            metadata = layout.variants[variant_id]
        except KeyError as exc:
            raise RuntimeRenderManifestError(f"Unknown world variant: {variant_id}") from exc
        image = layout.load_variant(variant_id).convert("RGBA")
        relative = f"world/{_safe_name(variant_id)}.png"
        record = _write_image(image, output, relative, kind="world_variant")
        record.update({
            "variant_id": variant_id,
            "asset_id": metadata["asset_id"],
            "transform": metadata["transform"],
        })
        variants[variant_id] = record
        files[relative] = record
        return record

    base_variant_id = str(layout.floor_skin(floor_id)["base_variant_id"])
    ensure_variant(base_variant_id)
    for placement in placements:
        ensure_variant(str(placement["variant_id"]))

    workstation_records: dict[str, dict[str, Any]] = {}
    workstation_placement_ids: set[str] = set()
    effect_profile = core.work_seats.effect_work_local_profile
    humanball_data = core.characters.humanballs.data
    humanball_offsets = _humanball_offsets(humanball_data)

    for workstation_id in sorted(layout.floor_layout(floor_id)["workstation_groups"]):
        seat = core.work_seats.resolve_workstation_seat(floor_id, workstation_id)
        components = []
        for role in ("desk", "pc", "chair_main", "chair_foreground"):
            placement = seat["component_placements"].get(role)
            if not isinstance(placement, dict):
                continue
            placement_id = str(placement["placement_id"])
            if placement_id in workstation_placement_ids:
                raise RuntimeRenderManifestError(
                    f"{floor_id}: workstation placement reused: {placement_id}"
                )
            workstation_placement_ids.add(placement_id)
            variant = ensure_variant(str(placement["variant_id"]))
            components.append({
                "role": role,
                "placement_id": placement_id,
                "asset_id": str(placement["asset_id"]),
                "variant_id": str(placement["variant_id"]),
                "file": variant["file"],
                "url": variant["url"],
                "x_px": int(placement["x_px"]),
                "y_px": int(placement["y_px"]),
                "layer": int(placement["layer"]),
            })
        chair = seat["component_placements"]["chair_main"]
        chair_image = layout.load_variant(str(chair["variant_id"]))
        offset = core.work_seats.resolve_world_offset(
            str(seat["direction"]),
            chair_size=chair_image.size,
            human_size=CHARACTER_SIZE,
        )
        top_left = [
            int(seat["chair_x_px"]) + int(offset[0]),
            int(seat["chair_y_px"]) + int(offset[1]),
        ]
        pc_placement = seat["component_placements"]["pc"]
        pc_frames = []
        for requested_index in range(core.work_seats.resolve_pc_frame_count(str(seat["direction"]))):
            asset_id, variant_id, normalized, frame_count = core.work_seats.resolve_pc_frame_asset(
                seat,
                requested_index,
            )
            variant = ensure_variant(str(variant_id))
            pc_frames.append({
                "frame_index": int(normalized),
                "frame_count": int(frame_count),
                "asset_id": str(asset_id),
                "variant_id": str(variant_id),
                "file": variant["file"],
                "url": variant["url"],
                "x_px": int(pc_placement["x_px"]),
                "y_px": int(pc_placement["y_px"]),
                "layer": int(pc_placement["layer"]),
            })
        direction = str(seat["direction"]).upper()
        effect_offset = core.work_seats.resolve_effect_world_position(
            direction,
            human_top_left_px=(0, 0),
            human_size=CHARACTER_SIZE,
            effect_size=EFFECT_SIZE,
        )
        workstation_records[workstation_id] = {
            "workstation_id": workstation_id,
            "direction": direction,
            "components": sorted(components, key=lambda row: (row["layer"], row["role"])),
            "character_top_left": top_left,
            "character_layer": int(seat["chair_layer"]) + 1,
            "effect_layer": int(seat["chair_layer"]) - 1,
            "effect_world_offset": [int(effect_offset[0]), int(effect_offset[1])],
            "pc_frame_ms": 720,
            "pc_frames": pc_frames,
            "humanball_offsets": humanball_offsets,
        }

    if not workstation_records:
        raise RuntimeRenderManifestError(f"{floor_id}: no workstations")

    # The static cache contains the immutable floor and non-workstation world.
    # Workstation components remain individually drawable so PC frames and the
    # authored chair/human/desk ordering can change without a full-frame image.
    static_image = layout.load_variant(base_variant_id).convert("RGBA")
    static_placements = []
    for placement in placements:
        placement_id = str(placement["placement_id"])
        if placement_id in workstation_placement_ids:
            continue
        variant = ensure_variant(str(placement["variant_id"]))
        sprite = layout.load_variant(str(placement["variant_id"]))
        static_image.alpha_composite(sprite, (int(placement["x_px"]), int(placement["y_px"])))
        static_placements.append({
            "placement_id": placement_id,
            "object_type": str(placement["object_type"]),
            "asset_id": str(placement["asset_id"]),
            "variant_id": str(placement["variant_id"]),
            "file": variant["file"],
            "url": variant["url"],
            "x_px": int(placement["x_px"]),
            "y_px": int(placement["y_px"]),
            "layer": int(placement["layer"]),
        })
    static_record = _write_image(
        static_image,
        output,
        f"{floor_id}.static.png",
        kind="static_scene",
    )
    files[static_record["file"]] = static_record

    occluders = []
    for row in core.walking_depth.resolve_occluders(floor_id):
        placement = row["placement"]
        placement_id = str(row["placement_id"])
        mask = core.walking_depth._load_occluder_visual(row).convert("RGBA")
        mask_record = _write_image(
            mask,
            output,
            f"occluders/{_safe_name(placement_id)}.png",
            kind="occluder_mask",
        )
        files[mask_record["file"]] = mask_record
        occluders.append({
            "placement_id": placement_id,
            "object_type": str(row["object_type"]),
            "x_px": int(placement["x_px"]),
            "y_px": int(placement["y_px"]),
            "layer": int(row["authored_layer"]),
            "always_foreground": bool(row["always_foreground"]),
            "foreground_fragment": bool(row["foreground_fragment"]),
            "depth_anchor_y_px": row.get("depth_anchor_y_px"),
            "file": mask_record["file"],
            "url": mask_record["url"],
            "width": mask_record["width"],
            "height": mask_record["height"],
        })
    occluders.sort(key=lambda row: (row["layer"], row["placement_id"]))

    characters_json = _load_json(root / "CHARACTER" / "CHARACTERS" / "characters.json")
    characters_by_id = {
        str(row["character_id"]): row for row in characters_json["characters"]
    }
    character_assets = AssetRegistry(root / "CHARACTER")
    character_records: dict[str, dict[str, Any]] = {}
    roster = core.employee_metadata.initial_roster(floor_id)
    for roster_row in roster:
        character_id = str(roster_row["character_id"])
        character = characters_by_id.get(character_id)
        if character is None:
            raise RuntimeRenderManifestError(f"Unknown roster character: {character_id}")
        if character_id in character_records:
            continue
        body_id = str(character["body_asset_id"])
        face_id = str(character["face_asset_id"])
        body_meta = character_assets.metadata(body_id)
        face_meta = character_assets.metadata(face_id)
        body = asset_records.get(body_id)
        if body is None:
            body = _copy_asset(
                character_assets.resolve(body_id),
                output,
                f"characters/{_safe_name(body_id)}.png",
                kind="character_body",
            )
            body.update({"asset_id": body_id, "domain": "character", "dimensions": list(body_meta["dimensions"])})
            asset_records[body_id] = body
            files[body["file"]] = body
        face = asset_records.get(face_id)
        if face is None:
            face = _copy_asset(
                character_assets.resolve(face_id),
                output,
                f"characters/{_safe_name(face_id)}.png",
                kind="character_face",
            )
            face.update({"asset_id": face_id, "domain": "character", "dimensions": list(face_meta["dimensions"])})
            asset_records[face_id] = face
            files[face["file"]] = face
        character_records[character_id] = {
            "character_id": character_id,
            "body_asset_id": body_id,
            "face_asset_id": face_id,
            "body_file": body["file"],
            "body_url": body["url"],
            "face_file": face["file"],
            "face_url": face["url"],
            "render_canvas": list(character.get("render_canvas", CHARACTER_SIZE)),
        }

    action_set = _load_json(root / "CHARACTER" / "ACTIONS" / "gds_standard_v1.json")
    frame_registry = load_frame_registry(root / "CHARACTER")
    effect_registry = _load_json(root / "CHARACTER" / "EFFECTS" / "gds_effects_v1.json")
    effects = _effect_frames(
        root,
        character_assets,
        effect_registry["effects"],
        output,
        asset_records,
    )
    for record in asset_records.values():
        files[record["file"]] = record

    humanballs: dict[str, dict[str, Any]] = {}
    for humanball_id in humanball_data["humanball_order"]:
        meta = humanball_data["humanballs"][humanball_id]
        asset_id = str(meta["asset_id"])
        record = asset_records.get(asset_id)
        if record is None:
            record = _copy_asset(
                character_assets.resolve(asset_id),
                output,
                f"components/{_safe_name(asset_id)}.png",
                kind="humanball",
            )
            record.update({"asset_id": asset_id, "domain": "effect", "dimensions": list(HUMANBALL_SIZE)})
            asset_records[asset_id] = record
            files[record["file"]] = record
        humanballs[str(humanball_id)] = {
            "humanball_id": str(humanball_id),
            "asset_id": asset_id,
            "file": record["file"],
            "url": record["url"],
            "frame_ms": int(humanball_data["animation"]["frame_ms"]),
            "visible_frame_count": int(humanball_data["animation"]["visible_frames"]),
            "total_frame_count": int(humanball_data["animation"]["total_frames"]),
        }

    revision_payload = {
        "builder": BUILDER_VERSION,
        "schema": SCHEMA,
        "source_registry_sha256": source_hashes,
    }
    revision = hashlib.sha256(
        json.dumps(revision_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema": SCHEMA,
        "version": VERSION,
        "builder": BUILDER_VERSION,
        "floor_id": floor_id,
        "revision": revision,
        "canvas": dict(CANVAS_SIZE),
        "coordinate_frame_id": floor["coordinate_frame_id"],
        "static_scene": {
            "file": static_record["file"],
            "url": static_record["url"],
            "width": static_record["width"],
            "height": static_record["height"],
            "sha256": static_record["sha256"],
        },
        "static_placements": sorted(
            static_placements,
            key=lambda row: (row["layer"], row["placement_id"]),
        ),
        "workstations": workstation_records,
        "occluders": occluders,
        "variants": dict(sorted(variants.items())),
        "assets": dict(sorted(asset_records.items())),
        "characters": dict(sorted(character_records.items())),
        "frame_profile": frame_registry["render_profile"],
        "frame_rules": dict(sorted(frame_registry["frames"].items())),
        "actions": action_set["actions"],
        "effects": effects,
        "humanballs": humanballs,
        "files": [files[key] for key in sorted(files)],
        "source_registry_sha256": source_hashes,
    }
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest_path.write_text(serialized, encoding="utf-8", newline="\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--floor-id", default=DEFAULT_FLOOR_ID)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    manifest = build_manifest(
        args.root,
        floor_id=args.floor_id,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "schema": manifest["schema"],
        "floor_id": manifest["floor_id"],
        "revision": manifest["revision"],
        "file_count": len(manifest["files"]),
        "manifest": str((Path(args.output_dir).resolve() if args.output_dir else Path(args.root).resolve() / "WEB" / "runtime_assets").parent / "runtime_render_manifest.json"),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
