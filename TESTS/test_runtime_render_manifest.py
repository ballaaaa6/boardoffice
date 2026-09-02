from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image


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
