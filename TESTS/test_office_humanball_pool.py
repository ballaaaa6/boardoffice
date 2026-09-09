import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

from CHARACTER.RUNTIME.character_system import CharacterSystem
from RUNTIME.central_core import CentralGameCore
from RUNTIME.visual_selection_core import VisualSelectionCore


ROOT = Path(__file__).resolve().parents[1]


def test_office_humanball_registry_is_schema_valid_and_has_38_selected_items():
    schema = json.loads(
        (ROOT / "SCHEMA/CHARACTER/office_humanball_registry.schema.json").read_text(
            encoding="utf-8"
        )
    )
    payload = json.loads(
        (ROOT / "CHARACTER/EFFECTS/office_humanball_v1.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert payload["office_humanball_count"] == 38
    assert len(payload["office_humanball_order"]) == 38
    assert len(payload["office_humanballs"]) == 38


def test_office_humanball_assets_are_canonical_18x18_rgba_with_locked_hashes():
    registry = json.loads(
        (ROOT / "CHARACTER/EFFECTS/office_humanball_v1.json").read_text(encoding="utf-8")
    )
    assets = json.loads(
        (ROOT / "CHARACTER/ASSETS/asset_registry.json").read_text(encoding="utf-8")
    )
    by_id = {row["asset_id"]: row for row in assets["assets"]}
    for humanball_id in registry["office_humanball_order"]:
        row = registry["office_humanballs"][humanball_id]
        asset = by_id[row["asset_id"]]
        path = ROOT / "CHARACTER/ASSETS" / asset["path"]
        assert path.is_file()
        assert asset["dimensions"] == [18, 18]
        assert asset["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == (18, 18)


def test_character_and_central_facades_render_office_humanballs_without_changing_six():
    system = CharacterSystem(ROOT / "CHARACTER")
    core = CentralGameCore(ROOT)
    assert len(system.list_humanballs()) == 6
    assert len(system.list_popup_humanballs()) == 44
    assert len(system.list_office_humanballs()) == 38
    assert system.list_office_humanballs() == core.list_office_humanballs()

    result = system.render_office_humanball("office.food_drinks.pizza", "SE")
    assert result.asset_id == "humanball.office.food_drinks.pizza"
    assert result.frame_ms == 240
    assert result.visible_frame_count == 10
    assert len(result.frames) == 12
    assert result.offsets[:10] == [
        (5, -13), (6, -15), (5, -17), (4, -18), (5, -20),
        (6, -21), (5, -23), (4, -24), (5, -26), (5, -27),
    ]
    assert result.frames[0] is not None and result.frames[0].size == (18, 18)
    assert result.frames[10:] == [None, None]
    mixed_result = system.render_humanball("office.food_drinks.pizza", "SE")
    assert mixed_result.asset_id == result.asset_id
    assert core.list_humanballs() == [
        "controller", "coin", "horse", "bench", "purple_bot", "purple_bot_body"
    ]


def test_office_visual_bag_covers_all_38_before_refill():
    visual = VisualSelectionCore(ROOT)
    state = visual.initial_channel_state("office_humanball")
    selected = []
    for index in range(39):
        state, binding = visual.select(
            state,
            channel="office_humanball",
            simulation_seed="office-bag-seed",
            employee_id="EMP_W1_0010",
            event_id=f"office-event-{index}",
            started_at_ms=index * 60,
            ends_at_ms=(index + 1) * 60,
        )
        selected.append(binding["asset_id"])
        state = visual.clear_active(
            state, channel="office_humanball", event_id=f"office-event-{index}"
        )
    ids = visual.catalog()["office_humanball"]["ids"]
    assert len(ids) == 38
    assert set(selected[:38]) == set(ids)
    assert len(set(selected[:38])) == 38
    assert selected[38] in ids


def test_runtime_render_manifest_exports_office_humanballs(tmp_path):
    from TOOLS.build_runtime_render_manifest import build_manifest

    manifest = build_manifest(ROOT, floor_id="floor02", output_dir=tmp_path)
    assert len(manifest["humanballs"]) == 6
    assert len(manifest["office_humanballs"]) == 38
    for record in manifest["office_humanballs"].values():
        path = tmp_path / record["file"]
        assert path.is_file()
        assert record["file"].startswith("components/humanball.office.")
        assert record["url"].startswith("/runtime_assets/components/")
