from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from RUNTIME.central_core import CentralGameCore
from RUNTIME.runtime_presentation_renderer import (
    RuntimePresentationLoop,
    RuntimePresentationRenderError,
    RuntimePresentationRenderer,
)
from RUNTIME.runtime_presentation_host import (
    RuntimePresentationHostAdapter,
    RuntimePresentationHostError,
)


ROOT = Path(__file__).resolve().parents[1]


def _quiet_runtime(core: CentralGameCore) -> dict:
    runtime = core.resolve_runtime_snapshot("floor02")
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    # Keep the actor reducer quiet while the render-only bridge is sampled.
    for actor in runtime["actor_snapshot"]["actors"].values():
        actor["behavior"]["next_event_due_ms"] = 10**9
    return runtime


def _ids(core: CentralGameCore) -> tuple[str, str, str]:
    actors = core.resolve_actor_snapshot("floor02")["actors"]
    rows = sorted(
        actors.values(),
        key=lambda item: (int(item["assignment"]["assignment_order"]), item["employee_id"]),
    )
    ceo = next(
        row["employee_id"]
        for row in rows
        if row["assignment"]["workstation_id"] == "ceo"
    )
    employees = [
        row["employee_id"]
        for row in rows
        if row["assignment"]["workstation_id"] != "ceo"
    ]
    return employees[0], employees[1], ceo


@pytest.mark.parametrize("mode", ["ceo_front", "seated_host", "standing_pair"])
def test_runtime_renderer_consumes_all_pair_modes_and_keeps_channels_separate(mode: str):
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    first_employee, second_employee, ceo = _ids(core)
    if mode == "ceo_front":
        initiator, partner = first_employee, ceo
    else:
        initiator, partner = first_employee, second_employee

    def force_mode(_snapshot, initiator_id, *, counter):
        if initiator_id != initiator:
            return None
        return {
            "kind": "pair",
            "initiator_id": initiator,
            "partner_id": partner,
            "participants": [initiator, partner],
            "mode": mode,
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }

    core.speech_scheduler._mode_request = force_mode
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0

    advanced = core.advance_runtime_snapshot(runtime, 60)
    started = next(
        event
        for event in advanced["speech_events"]
        if event["type"] == "speech_session_started" and event["kind"] == "pair"
    )
    renderer = RuntimePresentationRenderer(core)
    at_reply = int(started["bubble_start_ms"]) + 500
    before_render = copy.deepcopy(advanced)
    image, presentation = renderer.render_runtime_snapshot(
        advanced,
        at_ms=at_reply,
        floor_id="floor02",
    )
    assert image.size == (600, 600)
    assert presentation["actors"][initiator]["dialogue_visible"] is True
    assert presentation["actors"][partner]["dialogue_visible"] is True
    if mode == "ceo_front":
        assert presentation["actors"][initiator]["action"] == "move"
        assert presentation["actors"][initiator]["ground_xy"] is not None
        assert presentation["actors"][partner]["action"] == "work"
        assert presentation["actors"][partner]["subaction"] == "normal_work"
    elif mode == "seated_host":
        assert presentation["actors"][initiator]["action"] == "move"
        assert presentation["actors"][initiator]["ground_xy"] is not None
        assert presentation["actors"][partner]["action"] == "work"
        assert presentation["actors"][partner]["subaction"].startswith("turn_side_")
    else:
        assert all(
            presentation["actors"][employee_id]["action"] == "move"
            and presentation["actors"][employee_id]["ground_xy"] is not None
            for employee_id in (initiator, partner)
        )
    # Rendering must be a pure consumer of the composed state.
    assert advanced == before_render


def test_stationary_seated_host_uses_actor_work_clock_for_turn_side_frames():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    first_employee, second_employee, _ceo = _ids(core)

    def force_seated_host(_snapshot, initiator_id, *, counter):
        if initiator_id != first_employee:
            return None
        return {
            "kind": "pair",
            "initiator_id": first_employee,
            "partner_id": second_employee,
            "participants": [first_employee, second_employee],
            "mode": "seated_host",
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }

    core.speech_scheduler._mode_request = force_seated_host
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][first_employee]["behavior"]["next_event_due_ms"] = 0
    current = core.advance_runtime_snapshot(runtime, 60)
    current = core.advance_runtime_snapshot(current, 1740)

    samples = []
    for _ in range(12):
        host_actor = current["actor_snapshot"]["actors"][second_employee]
        host_row = core.resolve_runtime_presentation(
            current,
            floor_id="floor02",
            validate=False,
        )["actors"][second_employee]
        assert host_actor["activity"] == "working"
        assert host_actor["position"]["route"] is None
        assert host_row["render_owner"] == "work_seat"
        assert host_row["action"] == "work"
        assert host_row["subaction"].startswith("turn_side_")
        expected_frame = (
            int(host_actor["behavior"]["work_loop_elapsed_ms"]) // 360
        ) % int(host_row["character_frame_count"])
        assert host_row["character_frame_index"] == expected_frame
        samples.append(host_row["character_frame_index"])
        current = core.advance_runtime_snapshot(current, 60)

    assert len(set(samples)) >= 2


def test_central_normalizes_runtime_action_labels_for_every_direction_and_emotion():
    core = CentralGameCore(ROOT)
    actor = next(iter(core.resolve_actor_snapshot("floor02")["actors"].values()))

    for direction in ("NE", "SE", "SW", "NW"):
        assert core._runtime_frame_count(
            actor,
            action="move",
            direction=direction,
            subaction="idle",
        ) == 2
        assert core._runtime_frame_count(
            actor,
            action="idle",
            direction=direction,
            subaction="idle",
        ) == 2
        assert core._normalize_runtime_render_request(
            action="move",
            direction=direction,
            subaction="idle",
        ) == ("move", direction, None)

    for emotion in ("happy", "sad"):
        assert core._runtime_frame_count(
            actor,
            action=emotion,
            direction="SE",
            subaction=emotion,
        ) == 3
        assert core._normalize_runtime_render_request(
            action=emotion,
            direction="SE",
            subaction=emotion,
        ) == (emotion, None, None)


def test_live_route_uses_distance_based_character_frames_instead_of_pinning_frame_zero():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    employee_id, _second_employee, _ceo = _ids(core)
    requested = core.advance_runtime_snapshot(
        runtime,
        0,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    samples = []
    current = requested
    for _ in range(120):
        row = core.resolve_runtime_presentation(
            current,
            floor_id="floor02",
            validate=False,
        )["actors"][employee_id]
        if row.get("visible") and row.get("action") == "move":
            samples.append(row)
        if current["actor_snapshot"]["actors"][employee_id]["presence"] == "home":
            break
        current = core.advance_runtime_snapshot(current, 60)

    assert samples
    assert {row["character_frame_count"] for row in samples} == {2}
    assert len({row["character_frame_index"] for row in samples}) == 2
    assert any(float(row["cumulative_distance_px"]) > 0 for row in samples)


def test_runtime_presentation_bridges_workseat_to_gate_without_a_first_frame_snap():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    employee_id, _second_employee, _ceo = _ids(core)
    requested = core.advance_runtime_snapshot(
        runtime,
        0,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    first = core.resolve_runtime_presentation(
        requested,
        floor_id="floor02",
        validate=False,
    )["actors"][employee_id]
    assert first["render_owner"] == "walking_depth"
    assert first["presentation_transition"]["phase"] == "seat_exit"
    assert first["ground_xy"] == first["presentation_transition"]["from_ground_xy"]

    stepped = core.advance_runtime_snapshot(requested, 60)
    second = core.resolve_runtime_presentation(
        stepped,
        floor_id="floor02",
        validate=False,
    )["actors"][employee_id]
    assert second["presentation_transition"]["elapsed_ms"] == 60
    assert second["ground_xy"] != first["ground_xy"]
    assert second["ground_xy"] != second["presentation_transition"]["to_ground_xy"]


def test_visible_runtime_rows_always_have_a_resolved_action_and_frame():
    core = CentralGameCore(ROOT)
    for floor_id in sorted(core.world.floors):
        runtime = core.resolve_runtime_snapshot(floor_id)
        presentation = core.resolve_runtime_presentation(
            runtime,
            floor_id=floor_id,
        )
        ceo_id = next(
            employee_id
            for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
            if actor["assignment"]["workstation_id"] == "ceo"
        )
        ceo = presentation["actors"][ceo_id]
        assert ceo["visible"] is True
        assert ceo["action"] == "work"
        assert ceo["resolved_action"] == "work"
        assert 0 <= ceo["character_frame_index"] < ceo["character_frame_count"]


def test_runtime_renderer_reuses_seated_base_composition_without_aliasing_overlays():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    renderer = RuntimePresentationRenderer(core)

    first, _presentation = renderer.render_runtime_snapshot(
        runtime,
        floor_id="floor02",
    )
    cache_size = len(renderer._base_floor_cache)
    second, _presentation = renderer.render_runtime_snapshot(
        runtime,
        floor_id="floor02",
    )

    assert cache_size == 1
    assert len(renderer._base_floor_cache) == cache_size
    assert first.size == second.size == (600, 600)
    assert first.tobytes() == second.tobytes()


def test_runtime_renderer_paints_shared_emotion_and_return_window():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    first_employee, second_employee, _ceo = _ids(core)

    def force_standing(_snapshot, initiator_id, *, counter):
        if initiator_id != first_employee:
            return None
        return {
            "kind": "pair",
            "initiator_id": first_employee,
            "partner_id": second_employee,
            "participants": [first_employee, second_employee],
            "mode": "standing_pair",
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }

    core.speech_scheduler._mode_request = force_standing
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][first_employee]["behavior"]["next_event_due_ms"] = 0
    advanced = core.advance_runtime_snapshot(runtime, 60)
    started = next(
        event
        for event in advanced["speech_events"]
        if event["type"] == "speech_session_started" and event["kind"] == "pair"
    )
    to_fade_end = int(started["fade_end_ms"]) - int(advanced["speech_snapshot"]["clock"]["simulation_time_ms"])
    completed = core.advance_runtime_snapshot(advanced, to_fade_end)
    emotion = next(
        event for event in completed["speech_events"] if event["type"] == "emotion_started"
    )
    numeric_effects = {
        event["employee_id"]: event["effect_milli"]
        for event in completed["actor_events"]
        if event["type"] == "stamina_emotion_effect"
    }
    assert set(emotion["participants"]) <= set(numeric_effects)
    assert set(numeric_effects.values()) == ({2000} if emotion["emotion"] == "happy" else {-1000})
    renderer = RuntimePresentationRenderer(core)
    image, presentation = renderer.render_runtime_snapshot(
        completed,
        floor_id="floor02",
    )
    assert image.size == (600, 600)
    assert presentation["actors"][first_employee]["action"] == emotion["emotion"]
    assert presentation["actors"][second_employee]["action"] == emotion["emotion"]
    assert presentation["actors"][first_employee]["presentation_phase"] == "emotion"
    assert presentation["actors"][second_employee]["presentation_phase"] == "emotion"

    returned = core.advance_runtime_snapshot(completed, 1200)
    assert any(
        event["type"] == "return_requested"
        for event in returned["speech_events"]
    )


def test_talk_return_seat_entry_transition_owns_pose_until_normal_work():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    first_employee, second_employee, _ceo = _ids(core)

    def force_standing(_snapshot, initiator_id, *, counter):
        if initiator_id != first_employee:
            return None
        return {
            "kind": "pair",
            "initiator_id": first_employee,
            "partner_id": second_employee,
            "participants": [first_employee, second_employee],
            "mode": "standing_pair",
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }

    core.speech_scheduler._mode_request = force_standing
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][first_employee]["behavior"]["next_event_due_ms"] = 0
    current = core.advance_runtime_snapshot(runtime, 60)

    transition_sample = None
    for _ in range(200):
        for employee_id in (first_employee, second_employee):
            transition = current["actor_snapshot"]["actors"][employee_id]["position"].get(
                "seat_transition"
            )
            if (
                isinstance(transition, dict)
                and transition.get("phase") == "seat_entry"
                and transition.get("completion") == "talk_return"
            ):
                transition_sample = (current, employee_id)
                break
        if transition_sample is not None:
            break
        current = core.advance_runtime_snapshot(current, 60)

    assert transition_sample is not None
    current, employee_id = transition_sample
    transition = current["actor_snapshot"]["actors"][employee_id]["position"]["seat_transition"]
    row = core.resolve_runtime_presentation(current, floor_id="floor02", validate=False)["actors"][employee_id]
    assert row["presentation_transition"]["phase"] == "seat_entry"
    assert row["render_owner"] == "walking_depth"
    assert row["action"] == "move"
    assert row["ground_xy"] != row["presentation_transition"]["to_ground_xy"]

    remaining_ms = int(transition["duration_ms"]) - int(transition["elapsed_ms"])
    finished = core.advance_runtime_snapshot(current, remaining_ms)
    finished_row = core.resolve_runtime_presentation(
        finished,
        floor_id="floor02",
        validate=False,
    )["actors"][employee_id]
    assert finished["actor_snapshot"]["actors"][employee_id]["position"].get("seat_transition") is None
    assert finished_row["render_owner"] == "work_seat"
    assert finished_row["action"] == "work"
    assert finished_row["subaction"] == "normal_work"


def test_runtime_loop_keeps_critical_actor_in_worknormal_until_loop_boundary():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    employee_id, _second_employee, _ceo = _ids(core)
    actor = runtime["actor_snapshot"]["actors"][employee_id]
    actor["stamina"].update({
        "current_milli": 5000,
        "threshold_band": "critical",
        "drain_remainder": 0,
    })
    actor["behavior"].update({
        "next_event_due_ms": 10**9,
        "work_loop_elapsed_ms": 0,
        "pending_home": False,
        "pending_home_due_ms": None,
    })
    loop = RuntimePresentationLoop(core, runtime_snapshot=runtime, floor_id="floor02")
    held = loop.tick(360)
    row = held["presentation"]["actors"][employee_id]
    assert row["action"] == "work"
    assert row["subaction"] == "normal_work"
    assert held["runtime_snapshot"]["actor_snapshot"]["actors"][employee_id]["behavior"]["pending_home"] is True

    left = loop.tick(360)
    left_row = left["presentation"]["actors"][employee_id]
    assert left_row["action"] == "move"
    assert left_row["render_owner"] == "walking_depth"
    assert any(event["type"] == "home_requested" for event in left["actor_events"])


def test_lifecycle_bubble_preserves_departure_route_instead_of_seating_actor():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    employee_id, _second_employee, _ceo = _ids(core)
    requested = core.advance_runtime_snapshot(
        runtime,
        0,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    started = next(
        event
        for event in requested["speech_events"]
        if event["type"] == "speech_session_started"
        and event["kind"] == "lifecycle"
        and event["category"] == "fatigue"
    )
    assert started["conversation_plan"] is not None  # text selection remains available
    presentation = core.resolve_runtime_presentation(requested, floor_id="floor02")
    actor = presentation["actors"][employee_id]
    assert actor["render_owner"] == "walking_depth"
    assert actor["action"] == "move"
    assert actor["ground_xy"] is not None
    assert actor["dialogue_visible"] is True
    assert actor["dialogue_text"]
    image = RuntimePresentationRenderer(core).render_presentation(
        presentation,
        floor_id="floor02",
    )
    assert image.size == (600, 600)


def test_hidden_home_actor_drops_lifecycle_bubble_overlay():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    employee_id, _second_employee, _ceo = _ids(core)
    requested = core.advance_runtime_snapshot(
        runtime,
        0,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    actor = requested["actor_snapshot"]["actors"][employee_id]
    actor.update({
        "presence": "home",
        "activity": "home_recovery",
        "position": {"floor_id": None, "uv": None, "ground_xy": None, "route": None},
    })
    actor["behavior"].update({
        "activity_started_ms": 0,
        "activity_until_ms": 1000,
        "active_event": None,
        "next_event_due_ms": None,
        "work_loop_elapsed_ms": 0,
        "pending_home": False,
        "pending_home_due_ms": None,
    })
    hidden = core.validate_runtime_snapshot(requested)
    presentation = core.resolve_runtime_presentation(hidden, floor_id="floor02")
    row = presentation["actors"][employee_id]
    assert row["visible"] is False
    assert row["dialogue_visible"] is False
    image = RuntimePresentationRenderer(core).render_presentation(
        presentation,
        floor_id="floor02",
    )
    assert image.size == (600, 600)


def test_workseat_compositor_honors_per_assignment_channel_indices():
    core = CentralGameCore(ROOT)
    actors = core.resolve_actor_snapshot("floor02")["actors"]
    ordered = sorted(
        actors.values(),
        key=lambda item: int(item["assignment"]["assignment_order"]),
    )[:2]
    first, second = ordered
    assignments = [
        {
            "workstation_id": first["assignment"]["workstation_id"],
            "character_id": first["character_id"],
            "subaction": "normal_work",
            "character_frame_index": 1,
            "effect_frame_index": 2,
            "humanball_frame_index": 3,
            "pc_frame_index": 4,
            "effect_id": "coffee_energy",
            "humanball_id": "controller",
        },
        {
            "workstation_id": second["assignment"]["workstation_id"],
            "character_id": second["character_id"],
            "subaction": "normal_work",
            "character_frame_index": 0,
            "pc_frame_index": 0,
        },
    ]
    by_workstation, _rendered = core.work_seats._resolve_floor_assignment_data(
        "floor02",
        assignments,
        frame_index=0,
        character_frame_index=0,
        effect_frame_index=0,
        humanball_frame_index=0,
        pc_frame_index=0,
    )
    first_data = by_workstation[first["assignment"]["workstation_id"]]
    second_data = by_workstation[second["assignment"]["workstation_id"]]
    assert first_data["character_frame_index"] == 1
    assert first_data["effect_frame_index"] == 2 % first_data["effect_frame_count"]
    assert first_data["humanball_frame_index"] == 3 % first_data["humanball_frame_count"]
    assert first_data["pc_frame_index"] == 4 % first_data["pc_frame_count"]
    assert second_data["character_frame_index"] == 0
    assert second_data["pc_frame_index"] == 0


def test_runtime_loop_advances_and_renders_one_host_frame_without_mutating_input():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    original = copy.deepcopy(runtime)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=runtime,
        floor_id="floor02",
    )

    initial = loop.render_current()
    assert initial["image"].size == (600, 600)
    assert initial["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 0
    assert runtime == original

    frame = loop.tick(60)
    assert frame["image"].size == (600, 600)
    assert frame["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 60
    assert frame["runtime_snapshot"]["speech_snapshot"]["clock"]["simulation_time_ms"] == 60
    assert isinstance(frame["events"], list)
    assert loop.runtime_snapshot == frame["runtime_snapshot"]
    # The loop owns a defensive replacement; the caller's source snapshot is
    # still safe to reuse for deterministic replay or another view.
    assert runtime == original


def test_runtime_loop_failed_tick_keeps_last_good_snapshot():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=runtime,
        floor_id="floor02",
    )
    before = loop.runtime_snapshot
    with pytest.raises(RuntimePresentationRenderError):
        loop.tick(-1)
    assert loop.runtime_snapshot == before


def test_runtime_loop_render_failure_is_transactional(monkeypatch):
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=runtime,
        floor_id="floor02",
    )
    before = loop.runtime_snapshot

    def fail_render(*_args, **_kwargs):
        raise RuntimePresentationRenderError("forced render failure")

    monkeypatch.setattr(loop.renderer, "render_runtime_snapshot", fail_render)
    with pytest.raises(RuntimePresentationRenderError):
        loop.tick(60)
    assert loop.runtime_snapshot == before


def test_runtime_host_adapter_ticks_once_and_dispatches_defensive_frame_and_events():
    core = CentralGameCore(ROOT)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=_quiet_runtime(core),
        floor_id="floor02",
    )
    calls = []
    frame = {
        "image": Image.new("RGBA", (2, 2), (1, 2, 3, 255)),
        "presentation": {"schema": "gds.runtime_presentation_snapshot.v1"},
        "runtime_snapshot": {"clock": 60},
        "events": [{"source": "speech", "type": "bubble_started"}],
        "actor_events": [],
        "speech_events": [{"type": "bubble_started"}],
    }

    def fake_tick(elapsed_ms, *, actor_commands=None, speech_commands=None, at_ms=None):
        calls.append((elapsed_ms, actor_commands, speech_commands, at_ms))
        return frame

    loop.tick = fake_tick
    received_frames = []
    received_events = []
    host = RuntimePresentationHostAdapter(
        loop,
        frame_sink=received_frames.append,
        event_sink=received_events.append,
    )
    result = host.tick(
        60,
        actor_commands=[{"type": "noop"}],
        speech_commands=[{"type": "noop"}],
        at_ms=120,
    )

    assert result is frame
    assert calls == [(60, [{"type": "noop"}], [{"type": "noop"}], 120)]
    assert host.frame_count == 1
    assert received_events == frame["events"]
    assert received_frames[0] is not frame
    assert received_frames[0]["image"] is not frame["image"]
    received_frames[0]["events"].clear()
    assert frame["events"] == [{"source": "speech", "type": "bubble_started"}]
    assert host.last_frame is not frame


def test_runtime_host_adapter_render_current_does_not_advance_or_dispatch_events():
    core = CentralGameCore(ROOT)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=_quiet_runtime(core),
        floor_id="floor02",
    )
    received_frames = []
    received_events = []
    host = RuntimePresentationHostAdapter(
        loop,
        frame_sink=received_frames.append,
        event_sink=received_events.append,
    )
    frame = host.render_current()

    assert frame["runtime_snapshot"]["actor_snapshot"]["clock"]["simulation_time_ms"] == 0
    assert host.frame_count == 0
    assert len(received_frames) == 1
    assert received_events == []


def test_runtime_host_adapter_rejects_reentrant_tick_without_second_loop_call():
    core = CentralGameCore(ROOT)
    loop = RuntimePresentationLoop(
        core,
        runtime_snapshot=_quiet_runtime(core),
        floor_id="floor02",
    )
    calls = []
    frame = {
        "image": Image.new("RGBA", (1, 1)),
        "presentation": {},
        "runtime_snapshot": {},
        "events": [],
        "actor_events": [],
        "speech_events": [],
    }

    def fake_tick(elapsed_ms, *, actor_commands=None, speech_commands=None, at_ms=None):
        calls.append(elapsed_ms)
        return frame

    loop.tick = fake_tick
    host = None

    def reenter(_frame):
        host.tick(60)

    host = RuntimePresentationHostAdapter(loop, frame_sink=reenter)
    with pytest.raises(RuntimePresentationHostError, match="re-entrant"):
        host.tick(60)
    assert calls == [60]
