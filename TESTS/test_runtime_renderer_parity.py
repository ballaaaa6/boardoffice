from __future__ import annotations

from typing import Any

from TOOLS.runtime_review_server import ReviewState


ACTOR_FIELDS = (
    "employee_id",
    "character_id",
    "activity",
    "presence",
    "action",
    "subaction",
    "direction",
    "resolved_action",
    "resolved_direction",
    "resolved_subaction",
    "workstation_id",
    "render_owner",
    "visible",
    "pc_frame_index",
    "pc_frame_count",
    "pc_frame_ms",
    "route_phase",
    "route_elapsed_ms",
    "route_duration_ms",
    "ground_xy",
    "frame_index",
    "character_frame_index",
    "character_frame_count",
    "character_frame_ms",
    "cumulative_distance_px",
    "speech_mode",
    "speech_category",
    "speech_session_id",
)


def _dialogue_signature(lean: dict[str, Any], raster: dict[str, Any]) -> dict[str, Any]:
    dialogue = lean["dialogue"]
    return {
        "visible": bool(dialogue["visible"]) == bool(raster["dialogue_visible"]),
        "text": dialogue["text"] == raster["dialogue_text"],
        "dialogue_id": dialogue["dialogue_id"] == raster["dialogue_id"],
        "line_index": dialogue["line_index"] == raster["dialogue_line_index"],
        "locale": dialogue["locale"] == raster["dialogue_locale"],
        "bubble_id": dialogue["bubble_id"] == raster["dialogue_bubble_id"],
        "phase": dialogue["phase"] == raster["dialogue_phase"],
    }


def _actor_signature(lean: dict[str, Any], raster: dict[str, Any]) -> dict[str, Any]:
    assert {field: lean.get(field) for field in ACTOR_FIELDS} == {
        field: raster.get(field) for field in ACTOR_FIELDS
    }
    assert _dialogue_signature(lean, raster) == {
        "visible": True,
        "text": True,
        "dialogue_id": True,
        "line_index": True,
        "locale": True,
        "bubble_id": True,
        "phase": True,
    }

    lean_channels = lean.get("channels", {})
    raster_channels = raster.get("channels", {})
    for channel_name, raster_channel in raster_channels.items():
        lean_channel = lean_channels.get(channel_name)
        assert isinstance(lean_channel, dict)
        for key in (
            "asset_id",
            "effect_id",
            "humanball_id",
            "effect_frame_index",
            "humanball_frame_index",
            "effect_frame_count",
            "humanball_frame_count",
            "effect_frame_ms",
            "humanball_frame_ms",
        ):
            if key in raster_channel:
                assert lean_channel.get(key) == raster_channel[key]

    return {field: lean.get(field) for field in ACTOR_FIELDS}


def _assert_parity(canvas_state: ReviewState, raster_state: ReviewState, canvas: dict[str, Any], raster: dict[str, Any]) -> None:
    assert canvas["floor_id"] == raster["floor_id"] == "floor02"
    assert canvas["clock_ms"] == raster["clock_ms"]
    assert canvas["events"] == raster["events"]
    assert canvas["render_state"]["paint_order"] == raster_state.adapter.last_frame["presentation"]["paint_order"]
    canvas_actors = {
        actor["employee_id"]: actor for actor in canvas["render_state"]["actors"]
    }
    raster_actors = {actor["employee_id"]: actor for actor in raster["actors"]}
    assert list(canvas_actors) == list(raster_actors)
    for employee_id in canvas_actors:
        _actor_signature(canvas_actors[employee_id], raster_actors[employee_id])


def test_canvas_metadata_tracks_raster_metadata_across_runtime_trace():
    canvas_state = ReviewState("floor02")
    raster_state = ReviewState("floor02")

    def pair(method: str, *args: Any, **kwargs: Any) -> None:
        canvas = getattr(canvas_state, method)(
            *args, include_runtime=False, renderer="canvas", **kwargs
        )
        raster = getattr(raster_state, method)(
            *args, include_runtime=False, renderer="raster", **kwargs
        )
        _assert_parity(canvas_state, raster_state, canvas, raster)

    # Spawn/entry and normal work.
    pair("current")
    pair("full_demo")
    for _ in range(5):
        pair("tick", 360)

    # Routed conversation, effects/HumanBall, then the critical return path.
    pair("demo_talk", dialogue_seed="parity-talk")
    for _ in range(5):
        pair("tick", 360)
    pair("demo_effects", dialogue_seed="parity-effects")
    for _ in range(3):
        pair("tick", 240)
    pair("demo_critical", "EMP_W1_0010")
    for _ in range(5):
        pair("tick", 360)
