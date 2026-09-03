from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _api():
    try:
        from RUNTIME.browser_bundle_contract import (
            BundleContractError,
            canonical_json,
            validate_bundle,
        )
        from TOOLS.build_runtime_simulation_bundle import build_bundle, write_bundle
    except ModuleNotFoundError as exc:
        pytest.fail(f"browser bundle contract is not available: {exc}")
    return BundleContractError, canonical_json, validate_bundle, build_bundle, write_bundle


def test_floor02_bundle_is_deterministic_and_contains_runtime_inputs(tmp_path):
    BundleContractError, canonical_json, validate_bundle, build_bundle, write_bundle = _api()

    first = build_bundle(ROOT, "floor02")
    second = build_bundle(ROOT, "floor02")

    assert canonical_json(first) == canonical_json(second)
    assert first["schema"] == "gds.browser_runtime_bundle.v1"
    assert first["version"] == "1.0.0"
    assert first["floor_id"] == "floor02"
    assert first["bundle_revision"]
    assert first["simulation"]["step_ms"] == 60
    assert first["world"]["navigation"]["floor_id"] == "floor02"
    assert first["work_seats"]
    assert first["characters"]
    assert first["dialogue"]["lines"]
    assert first["effects"]["effects"]
    assert first["initial_snapshot"]["schema"] == "gds.runtime_snapshot.v1"
    standing_pair = next(
        plan
        for key, plan in first["conversation"]["plans"].items()
        if key.endswith("|standing_pair")
    )
    endpoints = [tuple(cell) for cell in standing_pair["spot"]["endpoint_uv"]]
    assert standing_pair["spot"]["axis"] == "V"
    assert endpoints[0][0] == endpoints[1][0]
    assert endpoints[1][1] - endpoints[0][1] == 4
    assert standing_pair["spot"]["endpoint_facings"] == ["SW", "NE"]
    seated_host = next(
        plan
        for key, plan in first["conversation"]["plans"].items()
        if key.endswith("|seated_host")
    )
    ceo_front = next(
        plan
        for key, plan in first["conversation"]["plans"].items()
        if key.endswith("|ceo_front")
    )
    for plan in (seated_host, ceo_front):
        visitor_id = plan["visitor_ids"][0]
        assert plan["bubble_offset_by_actor"][visitor_id] == [0, -20]
        assert plan["bubble_offset_by_actor"].get(plan["host_id"], [0, 0]) == [0, 0]
    assert validate_bundle(first, root=ROOT, expected_floor_id="floor02")["bundle_revision"] == first[
        "bundle_revision"
    ]

    output = tmp_path / "runtime_simulation_bootstrap.json"
    written = write_bundle(ROOT, "floor02", output)
    assert json.loads(output.read_text(encoding="utf-8")) == written
    assert output.read_bytes().endswith(b"\n")


def test_bundle_rejects_unresolved_frame_and_asset_references():
    BundleContractError, _canonical_json, validate_bundle, build_bundle, _write_bundle = _api()
    bundle = build_bundle(ROOT, "floor02")
    character_id = sorted(bundle["characters"])[0]

    broken_frame = json.loads(json.dumps(bundle))
    broken_frame["characters"][character_id]["frame_refs"][0]["frame_ids"][0] = "missing-frame"
    with pytest.raises(BundleContractError, match="unresolved frame"):
        validate_bundle(broken_frame, root=ROOT, expected_floor_id="floor02")

    broken_asset = json.loads(json.dumps(bundle))
    broken_asset["characters"][character_id]["asset_refs"][0] = "missing-asset"
    with pytest.raises(BundleContractError, match="unresolved asset"):
        validate_bundle(broken_asset, root=ROOT, expected_floor_id="floor02")


def test_bundle_rejects_source_hash_mismatch():
    BundleContractError, _canonical_json, validate_bundle, build_bundle, _write_bundle = _api()
    bundle = build_bundle(ROOT, "floor02")
    bundle["source_hashes"]["WORLD/REGISTRY/floors.json"] = "0" * 64

    with pytest.raises(BundleContractError, match="source hash mismatch"):
        validate_bundle(bundle, root=ROOT, expected_floor_id="floor02")


def test_bundle_build_does_not_call_image_renderers(monkeypatch):
    _BundleContractError, _canonical_json, _validate_bundle, build_bundle, _write_bundle = _api()
    from CHARACTER.RUNTIME.character_system import CharacterSystem
    from WORLD.RUNTIME.layout_core import LayoutCore

    def fail(*_args, **_kwargs):
        raise AssertionError("browser bundle build must not render images")

    monkeypatch.setattr(CharacterSystem, "render", fail)
    monkeypatch.setattr(CharacterSystem, "render_composition", fail)
    monkeypatch.setattr(LayoutCore, "load_asset", fail)
    monkeypatch.setattr(LayoutCore, "load_variant", fail)

    bundle = build_bundle(ROOT, "floor02")
    assert bundle["schema"] == "gds.browser_runtime_bundle.v1"


def test_bundle_source_hashes_match_canonical_files():
    _BundleContractError, _canonical_json, _validate_bundle, build_bundle, _write_bundle = _api()
    bundle = build_bundle(ROOT, "floor02")
    for relative, digest in bundle["source_hashes"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
