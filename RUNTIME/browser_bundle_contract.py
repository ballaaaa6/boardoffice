from __future__ import annotations

"""Contracts shared by the browser simulation bundle and parity traces."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


BUNDLE_SCHEMA = "gds.browser_runtime_bundle.v1"
TRACE_SCHEMA = "gds.browser_runtime_parity_trace.v1"
VERSION = "1.0.0"

# These are the canonical registries read by the bundle exporter.  Keeping the
# list explicit prevents a generated bundle from silently depending on a new
# file that was not included in its source revision.
CANONICAL_SOURCE_FILES = (
    "WORLD/REGISTRY/character_direction_bridge.json",
    "WORLD/REGISTRY/chair_families.json",
    "WORLD/REGISTRY/coordinate_frames.json",
    "WORLD/REGISTRY/fine_grid_profiles.json",
    "WORLD/REGISTRY/floors.json",
    "WORLD/REGISTRY/floor_skins.json",
    "WORLD/REGISTRY/footprint_bindings.json",
    "WORLD/REGISTRY/footprint_profiles.json",
    "WORLD/REGISTRY/gameplay_metadata_families.json",
    "WORLD/REGISTRY/layouts.json",
    "WORLD/REGISTRY/navigation_clearance_profiles.json",
    "WORLD/REGISTRY/navigation_closure_profiles.json",
    "WORLD/REGISTRY/navigation_placement_bridges.json",
    "WORLD/REGISTRY/pc_animation.json",
    "WORLD/REGISTRY/portals.json",
    "WORLD/REGISTRY/room_domains.json",
    "WORLD/REGISTRY/room_navigation_bindings.json",
    "WORLD/REGISTRY/spatial_profiles.json",
    "WORLD/REGISTRY/visual_variants.json",
    "WORLD/REGISTRY/walking_depth_profiles.json",
    "WORLD/REGISTRY/workstation_directions.json",
    "WORLD/REGISTRY/world_assets.json",
    "WORLD/COMPILED_NAV/floor02_room_cells.json",
    "CHARACTER/CHARACTERS/characters.json",
    "CHARACTER/EMPLOYEES/employee_metadata.json",
    "CHARACTER/ACTIONS/gds_standard_v1.json",
    "CHARACTER/FRAME_RULES/frame_registry.json",
    "CHARACTER/ASSETS/asset_registry.json",
    "CHARACTER/EFFECTS/gds_effects_v1.json",
    "CHARACTER/EFFECTS/humanball_v1.json",
    "CHARACTER/DIALOGUE/dialogue.csv",
    "CHARACTER/DIALOGUE/bubble_presets.json",
)


class BundleContractError(ValueError):
    """Raised when a browser bundle is malformed or stale."""


class TraceContractError(ValueError):
    """Raised when a Python/browser parity trace is malformed."""


def canonical_json(value: Any) -> str:
    """Serialize JSON-safe data deterministically and reject non-finite floats."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BundleContractError(f"value is not canonical JSON: {exc}") from exc


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_source_hashes(root: str | Path) -> dict[str, str]:
    """Hash every canonical registry consumed by the browser bundle."""
    project_root = Path(root).resolve()
    result: dict[str, str] = {}
    for relative in CANONICAL_SOURCE_FILES:
        path = project_root / relative
        if not path.is_file():
            raise BundleContractError(f"missing canonical source: {relative}")
        result[relative] = _sha256_bytes(path)
    return result


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise BundleContractError(f"{name} must be an object")
    return value


def _require_non_empty_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise BundleContractError(f"{name} must be a non-empty list")
    return value


def _validate_snapshot_shape(snapshot: Any, name: str) -> None:
    data = _require_mapping(snapshot, name)
    if data.get("schema") != "gds.runtime_snapshot.v1":
        raise BundleContractError(f"{name} has unsupported schema")
    if data.get("version") != VERSION:
        raise BundleContractError(f"{name} has unsupported version")
    for channel in ("actor_snapshot", "speech_snapshot", "conversation_snapshot"):
        _require_mapping(data.get(channel), f"{name}.{channel}")


def _revision_payload(bundle: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(bundle))
    payload.pop("bundle_revision", None)
    return payload


def bundle_revision(bundle: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_revision_payload(bundle)).encode("utf-8")).hexdigest()


def _validate_source_hashes(
    hashes: Any,
    *,
    root: str | Path | None,
) -> dict[str, str]:
    values = _require_mapping(hashes, "source_hashes")
    expected_keys = set(CANONICAL_SOURCE_FILES)
    if set(values) != expected_keys:
        missing = sorted(expected_keys - set(values))
        extra = sorted(set(values) - expected_keys)
        raise BundleContractError(
            f"source_hashes keys differ; missing={missing}, extra={extra}"
        )
    normalized: dict[str, str] = {}
    for relative in CANONICAL_SOURCE_FILES:
        digest = values.get(relative)
        if not isinstance(digest, str) or len(digest) != 64:
            raise BundleContractError(f"invalid source hash: {relative}")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise BundleContractError(f"invalid source hash: {relative}") from exc
        normalized[relative] = digest
    if root is not None:
        actual = canonical_source_hashes(root)
        for relative in CANONICAL_SOURCE_FILES:
            if normalized[relative] != actual[relative]:
                raise BundleContractError(f"source hash mismatch: {relative}")
    return normalized


def validate_bundle(
    bundle: Mapping[str, Any],
    *,
    root: str | Path | None = None,
    expected_floor_id: str | None = None,
) -> dict[str, Any]:
    """Validate and return an isolated browser bundle copy."""
    data = _require_mapping(bundle, "bundle")
    if data.get("schema") != BUNDLE_SCHEMA:
        raise BundleContractError("bundle has unsupported schema")
    if data.get("version") != VERSION:
        raise BundleContractError("bundle has unsupported version")
    floor_id = data.get("floor_id")
    if not isinstance(floor_id, str) or not floor_id.strip():
        raise BundleContractError("bundle.floor_id must be non-empty text")
    if expected_floor_id is not None and floor_id != expected_floor_id:
        raise BundleContractError(
            f"bundle floor mismatch: expected {expected_floor_id}, got {floor_id}"
        )

    source_hashes = _validate_source_hashes(data.get("source_hashes"), root=root)
    simulation = _require_mapping(data.get("simulation"), "simulation")
    if simulation.get("step_ms") != 60:
        raise BundleContractError("simulation.step_ms must be 60")
    if not isinstance(simulation.get("seed_namespace"), str) or not simulation["seed_namespace"]:
        raise BundleContractError("simulation.seed_namespace must be non-empty text")
    _require_mapping(simulation.get("constants"), "simulation.constants")

    world = _require_mapping(data.get("world"), "world")
    navigation = _require_mapping(world.get("navigation"), "world.navigation")
    if navigation.get("floor_id") != floor_id:
        raise BundleContractError("world.navigation floor does not match bundle floor")
    _require_mapping(world.get("floor"), "world.floor")
    _require_mapping(world.get("layout"), "world.layout")
    _require_non_empty_list(world.get("placements"), "world.placements")
    _require_mapping(data.get("work_seats"), "work_seats")
    if not data["work_seats"]:
        raise BundleContractError("work_seats must be non-empty")

    assets = _require_mapping(data.get("assets"), "assets")
    frame_rules = _require_mapping(data.get("frame_rules"), "frame_rules")
    if not frame_rules:
        raise BundleContractError("frame_rules must be non-empty")
    characters = _require_mapping(data.get("characters"), "characters")
    if not characters:
        raise BundleContractError("characters must be non-empty")
    for character_id, character in characters.items():
        record = _require_mapping(character, f"characters.{character_id}")
        refs = _require_non_empty_list(record.get("asset_refs"), f"characters.{character_id}.asset_refs")
        for asset_id in refs:
            if not isinstance(asset_id, str) or asset_id not in assets:
                raise BundleContractError(
                    f"unresolved asset: characters.{character_id}.{asset_id}"
                )
        frame_refs = _require_non_empty_list(
            record.get("frame_refs"), f"characters.{character_id}.frame_refs"
        )
        for frame_ref in frame_refs:
            row = _require_mapping(frame_ref, f"characters.{character_id}.frame_ref")
            frame_ids = _require_non_empty_list(
                row.get("frame_ids"), f"characters.{character_id}.frame_ids"
            )
            for frame_id in frame_ids:
                if not isinstance(frame_id, str) or frame_id not in frame_rules:
                    raise BundleContractError(
                        f"unresolved frame: characters.{character_id}.{frame_id}"
                    )

    dialogue = _require_mapping(data.get("dialogue"), "dialogue")
    _require_non_empty_list(dialogue.get("lines"), "dialogue.lines")
    _require_mapping(dialogue.get("bubble_policy"), "dialogue.bubble_policy")
    effects = _require_mapping(data.get("effects"), "effects")
    _require_mapping(effects.get("effects"), "effects.effects")
    _require_mapping(effects.get("humanballs"), "effects.humanballs")
    _validate_snapshot_shape(data.get("initial_snapshot"), "initial_snapshot")

    revision = data.get("bundle_revision")
    if not isinstance(revision, str) or revision != bundle_revision(data):
        raise BundleContractError("bundle revision mismatch")
    return copy.deepcopy({**data, "source_hashes": source_hashes})


def validate_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Python oracle trace before it is handed to browser tests."""
    data = _require_mapping(trace, "trace")
    if data.get("schema") != TRACE_SCHEMA:
        raise TraceContractError("trace has unsupported schema")
    if data.get("version") != VERSION:
        raise TraceContractError("trace has unsupported version")
    if not isinstance(data.get("floor_id"), str) or not data["floor_id"]:
        raise TraceContractError("trace.floor_id must be non-empty text")
    if not isinstance(data.get("seed"), str) or not data["seed"]:
        raise TraceContractError("trace.seed must be non-empty text")
    _validate_trace_snapshot(data.get("initial_snapshot"), "initial_snapshot")
    steps = _require_non_empty_list(data.get("steps"), "trace.steps")
    for index, step in enumerate(steps):
        row = _require_mapping(step, f"trace.steps[{index}]")
        elapsed_ms = row.get("elapsed_ms")
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
            raise TraceContractError(f"trace.steps[{index}].elapsed_ms must be >= 0")
        for name in ("actor_commands", "speech_commands", "events"):
            if not isinstance(row.get(name), list):
                raise TraceContractError(f"trace.steps[{index}].{name} must be a list")
        _validate_trace_snapshot(row.get("python_snapshot"), f"trace.steps[{index}].python_snapshot")
        render_state = _require_mapping(
            row.get("python_render_state"), f"trace.steps[{index}].python_render_state"
        )
        if render_state.get("schema") != "gds.runtime_render_state.v1":
            raise TraceContractError(f"trace.steps[{index}].python_render_state has unsupported schema")
        if "image_data_url" in render_state or "image" in render_state:
            raise TraceContractError(f"trace.steps[{index}].python_render_state contains image data")
    return copy.deepcopy(dict(data))


def _validate_trace_snapshot(snapshot: Any, name: str) -> None:
    try:
        _validate_snapshot_shape(snapshot, name)
    except BundleContractError as exc:
        raise TraceContractError(str(exc)) from exc


__all__ = [
    "BUNDLE_SCHEMA",
    "TRACE_SCHEMA",
    "VERSION",
    "BundleContractError",
    "TraceContractError",
    "bundle_revision",
    "canonical_json",
    "canonical_source_hashes",
    "validate_bundle",
    "validate_trace",
]
