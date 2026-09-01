from __future__ import annotations

import json
from pathlib import Path

from PIL import ImageChops
from jsonschema import Draft202012Validator

from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]


def _nonzero_rgb_pixels(image):
    return sum(1 for pixel in image.convert("RGBA").getdata() if pixel[:3] != (0, 0, 0))


def test_pc_animation_registry_schema_and_all_active_families_are_complete():
    schema = json.loads(
        (ROOT / "SCHEMA" / "WORLD" / "pc_animation.schema.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (ROOT / "WORLD" / "REGISTRY" / "pc_animation.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(schema).iter_errors(registry)) == []
    core = CentralGameCore(ROOT)
    assert len(registry["families"]) == 25
    for family_id, family in registry["families"].items():
        assert family["family_id"] == family_id
        assert family["static_asset_id"] in core.world.assets
        assert len(family["animated_asset_ids"]) == 5
        assert all(asset_id in core.world.assets for asset_id in family["animated_asset_ids"])
        assert all(
            f"{asset_id}@normal" in core.world.variants
            for asset_id in family["animated_asset_ids"]
        )


def test_central_pc_frame_resolution_maps_nw_cells_and_keeps_se_sw_static():
    core = CentralGameCore(ROOT)
    nw = [core.resolve_workstation_pc_frame("floor06", "ws3", index) for index in range(7)]
    assert [item["sequence"] for item in nw] == [
        "cell1",
        "cell2",
        "cell3",
        "cell4",
        "cell5",
        "cell1",
        "cell2",
    ]
    assert [item["frame_count"] for item in nw] == [5] * 7

    for workstation_id in ("ceo", "ws1"):
        static = core.resolve_workstation_pc_frame("floor06", workstation_id, 99)
        assert static["sequence"] == "cell0"
        assert static["frame_count"] == 1
        assert static["frame_index"] == 0


def test_work_floor_pc_frame_channel_changes_only_the_requested_nw_pc():
    core = CentralGameCore(ROOT)
    assignment = {
        "workstation_id": "ws3",
        "character_id": "TP_046",
        "subaction": "normal_work",
    }
    frames = [
        core.render_floor_with_work(
            "floor06",
            [{**assignment, "pc_frame_index": index}],
            frame_index=0,
        )
        for index in range(5)
    ]
    pc_crops = [frame.crop((249, 264, 299, 296)) for frame in frames]
    assert len({crop.tobytes() for crop in pc_crops}) == 5
    for first, second in zip(frames, frames[1:]):
        diff = ImageChops.difference(first, second).convert("RGBA")
        # PC cell changes are intentionally tiny screen-pixel changes, but no
        # human/floor pixels should be redrawn by the channel.
        assert _nonzero_rgb_pixels(diff) > 0
        assert ImageChops.difference(
            first.crop((230, 290, 280, 340)),
            second.crop((230, 290, 280, 340)),
        ).convert("RGBA").getbbox() is None


def test_work_effect_floor_uses_the_same_pc_frame_channel():
    core = CentralGameCore(ROOT)
    frames = [
        core.render_floor_with_work_effects(
            "floor06",
            [{
                "workstation_id": "ws3",
                "character_id": "TP_046",
                "subaction": "normal_work",
                "effect_id": "thunder_cloud",
                "pc_frame_index": index,
            }],
            frame_index=0,
        )
        for index in (0, 1)
    ]
    assert frames[0].size == (600, 600)
    assert _nonzero_rgb_pixels(ImageChops.difference(frames[0], frames[1])) > 0


def test_workseat_lifecycle_exposes_pc_frame_after_each_complete_work_loop():
    core = CentralGameCore(ROOT)
    cycle = core.resolve_employee_work_seat_actor_cycle(
        "EMP_W1_0038",
        "floor06",
        "ws3",
        (249, 182),
        work_ticks=20,
    )
    seated = [state["work_render"] for state in cycle["states"] if state["phase"] == "seated_work"]
    assert seated
    assert all(payload["pc_frame_count"] == 5 for payload in seated)
    assert all(payload["pc_frame_loop_ms"] == 720 for payload in seated)
    assert [payload["pc_frame_index"] for payload in seated[:14]] == [0] * 12 + [1, 1]

    se_cycle = core.resolve_employee_work_seat_actor_cycle(
        "EMP_W1_0020",
        "floor06",
        "ws1",
        (243, 182),
        work_ticks=10,
    )
    se_payloads = [state["work_render"] for state in se_cycle["states"] if state["phase"] == "seated_work"]
    assert all(payload["pc_frame_count"] == 1 for payload in se_payloads)
    assert all(payload["pc_frame_index"] == 0 for payload in se_payloads)


def test_runtime_presentation_advances_pc_cell_from_persistent_completed_loop_count():
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor06")
    # Keep all actors in normal work so the sample is isolated from seeded
    # behavior events.  Pick a native NW seat, whose authored PC has cells 1–5.
    for speech_actor in runtime["speech_snapshot"]["actors"].values():
        speech_actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    for actor in runtime["actor_snapshot"]["actors"].values():
        actor["behavior"]["next_event_due_ms"] = 10**9
    nw_employee = next(
        employee_id
        for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
        if actor["assignment"]["facing"] == "NW"
    )
    actor = runtime["actor_snapshot"]["actors"][nw_employee]
    actor["behavior"].update({
        "work_loop_elapsed_ms": 0,
        "work_loop_count": 0,
    })
    runtime = core.validate_runtime_snapshot(runtime)
    first = core.resolve_runtime_presentation(runtime, floor_id="floor06")
    assert first["actors"][nw_employee]["pc_frame_index"] == 0
    advanced = core.advance_runtime_snapshot(runtime, 720)
    second = core.resolve_runtime_presentation(advanced, floor_id="floor06")
    advanced_actor = advanced["actor_snapshot"]["actors"][nw_employee]
    assert advanced_actor["behavior"]["work_loop_elapsed_ms"] == 0
    assert advanced_actor["behavior"]["work_loop_count"] == 1
    assert second["actors"][nw_employee]["pc_frame_index"] == 1


def test_derived_ne_workstation_uses_the_same_animated_pc_channel(monkeypatch):
    core = CentralGameCore(ROOT)
    original = core.directions.resolve_character_action_direction

    def force_future_ne(floor_id, workstation_id, action_family="work"):
        if (floor_id, workstation_id) == ("floor02", "ws8"):
            return "NE"
        return original(floor_id, workstation_id, action_family=action_family)

    monkeypatch.setattr(core.directions, "resolve_character_action_direction", force_future_ne)
    assert core.resolve_workstation_pc_frame("floor02", "ws8", 4)["sequence"] == "cell5"
    frames = [
        core.render_floor_with_work(
            "floor02",
            [{"workstation_id": "ws8", "character_id": "TP_000", "pc_frame_index": index}],
            frame_index=0,
        ).convert("RGB")
        for index in (0, 1)
    ]
    diff = ImageChops.difference(frames[0], frames[1])
    assert sum(pixel != (0, 0, 0) for pixel in diff.getdata()) > 0
