from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

from WORLD.RUNTIME.layout_core import LayoutCore


ROOT = Path(__file__).resolve().parents[1]


def _builder():
    try:
        from TOOLS.build_runtime_render_manifest import build_manifest
    except ModuleNotFoundError as exc:
        pytest.fail(f"manifest builder is not available: {exc}")
    return build_manifest


def test_manifest_builder_creates_deterministic_floor02_component_bundle():
    build_manifest = _builder()
    with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
        first_output = Path(first_dir)
        second_output = Path(second_dir)
        first = build_manifest(ROOT, floor_id="floor02", output_dir=first_output)
        second = build_manifest(ROOT, floor_id="floor02", output_dir=second_output)

        assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
            second,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert first["schema"] == "gds.runtime_render_manifest.v1"
        assert first["floor_id"] == "floor02"
        assert first["canvas"] == {"width": 600, "height": 600}
        assert first["workstations"]
        assert all(
            placement["object_type"] != "pc"
            for placement in first["static_placements"]
        )

        static = first_output / first["static_scene"]["file"]
        static_copy = second_output / second["static_scene"]["file"]
        assert static.is_file()
        assert static.read_bytes() == static_copy.read_bytes()
        with Image.open(static) as image:
            assert image.size == (600, 600)


def test_manifest_references_only_existing_derived_files_and_canonical_hashes():
    build_manifest = _builder()
    source = ROOT / "WORLD" / "REGISTRY" / "floors.json"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with TemporaryDirectory() as output_dir:
        output = Path(output_dir)
        manifest = build_manifest(ROOT, floor_id="floor02", output_dir=output)

        assert manifest["source_registry_sha256"]["WORLD/REGISTRY/floors.json"] == source_hash
        assert manifest["source_registry_sha256"]["WORLD/REGISTRY/layouts.json"]
        assert manifest["source_registry_sha256"]["CHARACTER/FRAME_RULES/frame_registry.json"]
        for record in manifest["files"]:
            path = output / record["file"]
            assert path.is_file(), record["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]

        for character in manifest["characters"].values():
            assert (output / character["body_file"]).is_file()
            assert (output / character["face_file"]).is_file()
        for workstation in manifest["workstations"].values():
            assert workstation["pc_frames"]
            assert workstation["character_top_left"]
            assert len(workstation["humanball_offsets"]["SE"]) == 12
        assert manifest["frame_rules"]["M0"]["body"]["src"] == [0, 0, 16, 16]


def test_occluders_isolated_by_floor_and_export_front_edge():
    build_manifest = _builder()
    with TemporaryDirectory() as output_dir:
        output = Path(output_dir)
        manifest_f02 = build_manifest(ROOT, floor_id="floor02", output_dir=output)
        manifest_f08 = build_manifest(ROOT, floor_id="floor08", output_dir=output)

        reception_02 = next(o for o in manifest_f02["occluders"] if o["placement_id"] == "reception")
        reception_08 = next(o for o in manifest_f08["occluders"] if o["placement_id"] == "reception")

        assert reception_02["file"] == "occluders/floor02/reception.png"
        assert reception_08["file"] == "occluders/floor08/reception.png"
        assert (output / reception_02["file"]).is_file()
        assert (output / reception_08["file"]).is_file()

        # Check front edge is exported for objects with depth profiles
        assert reception_02.get("depth_front_edge_world_px") is not None
        assert reception_08.get("depth_front_edge_world_px") is not None
        assert len(reception_08["depth_front_edge_world_px"]) >= 2

        # Verify floor08 reception height is 80 and floor02 reception height is 55 (no collision)
        assert reception_08["height"] == 80
        assert reception_02["height"] == 55


def test_manifest_occluder_mask_keeps_dark_sprite_contours():
    build_manifest = _builder()
    with TemporaryDirectory() as output_dir:
        output = Path(output_dir)
        manifest = build_manifest(ROOT, floor_id="floor02", output_dir=output)
        occluder = next(
            row for row in manifest["occluders"] if row["placement_id"] == "ws3_desk"
        )
        source = LayoutCore(ROOT / "WORLD").load_variant(
            "desk_002.part_01@normal"
        ).convert("RGBA")
        mask = Image.open(output / occluder["file"]).convert("RGBA")

        assert mask.getchannel("A").tobytes() == source.getchannel("A").tobytes()
        assert any(
            pixel[3] == 255 and max(pixel[:3]) <= 64
            for pixel in mask.getdata()
        )
