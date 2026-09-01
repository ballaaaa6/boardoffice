from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from RUNTIME.actor_simulation_core import ActorSimulationCore, ActorSimulationError
from RUNTIME.central_core import CentralGameCore


ROOT = Path(__file__).resolve().parents[1]
ACTOR_ID = "EMP_W1_0001"


@pytest.fixture(scope="module")
def actor_core() -> ActorSimulationCore:
    return ActorSimulationCore(ROOT)


@pytest.fixture(scope="module")
def central_core() -> CentralGameCore:
    return CentralGameCore(ROOT)


def test_initial_snapshot_is_persistent_json_safe_and_deterministic(actor_core: ActorSimulationCore):
    first = actor_core.initial_snapshot()
    second = actor_core.initial_snapshot()

    assert first == second
    assert len(first["actors"]) == 219
    assert first["clock"] == {"simulation_time_ms": 0, "tick_ms": 60}
    assert json.loads(json.dumps(first, sort_keys=True)) == first
    assert actor_core.validate_snapshot(first) == first


def test_central_facade_exposes_actor_snapshot_and_keeps_assignment_binding(
    central_core: CentralGameCore,
):
    snapshot = central_core.resolve_actor_snapshot("floor01")
    assert len(snapshot["actors"]) == 7
    actor = snapshot["actors"][ACTOR_ID]
    assert actor["assignment"]["floor_id"] == "floor01"
    assert actor["assignment"]["workstation_id"] == "ws1"

    advanced = central_core.advance_actor_snapshot(snapshot, 60)
    assert advanced["snapshot"]["clock"]["simulation_time_ms"] == 60
    assert advanced["snapshot"]["actors"][ACTOR_ID]["assignment"] == actor["assignment"]


def test_work_drain_uses_integer_milli_units_and_remainder(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    before = copy.deepcopy(snapshot)
    profile = actor_core.employee_registry.get(ACTOR_ID)["stamina_profile"]
    rate = profile["work_drain_milli_per_second"]

    result = actor_core.advance_snapshot(snapshot, 60)
    actor = result["snapshot"]["actors"][ACTOR_ID]
    assert actor["stamina"]["current_milli"] == 100000 - (rate * 60 // 1000)
    assert actor["stamina"]["drain_remainder"] == (rate * 60) % 1000
    assert result["events"] == []
    assert snapshot == before, "reducer must not mutate its input snapshot"

    assert actor_simulation_json(result["snapshot"]) == result["snapshot"]


def test_large_work_window_emits_each_downward_threshold_once(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    actor = snapshot["actors"][ACTOR_ID]
    actor["stamina"].update(
        {"current_milli": 30500, "threshold_band": "normal", "drain_remainder": 0}
    )
    actor["behavior"]["next_event_due_ms"] = 999999

    result = actor_core.advance_snapshot(snapshot, 60000)
    changed = result["snapshot"]["actors"][ACTOR_ID]
    threshold_events = [
        event
        for event in result["events"]
        if event["employee_id"] == ACTOR_ID and event["type"] == "threshold_crossed"
    ]
    assert [event["threshold_band"] for event in threshold_events] == ["low", "critical"]
    # Critical now queues a smooth home exit.  A large window may already
    # contain the portal route/home recovery, but the threshold events remain
    # exactly once and the actor never remains stuck in work.
    assert changed["presence"] in {"leaving", "home"}
    assert any(event["type"] == "home_requested" for event in result["events"])

    again = actor_core.advance_snapshot(result["snapshot"], 60)
    assert not any(
        event["employee_id"] == ACTOR_ID and event["type"] == "threshold_crossed"
        for event in again["events"]
    )


def test_critical_actor_finishes_normal_work_loop_before_auto_home(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot("floor01")
    actor = snapshot["actors"][ACTOR_ID]
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

    held = actor_core.advance_snapshot(snapshot, 300)
    held_actor = held["snapshot"]["actors"][ACTOR_ID]
    assert held_actor["activity"] == "working"
    assert held_actor["presence"] == "present"
    assert held_actor["behavior"]["pending_home"] is True
    assert held_actor["behavior"]["pending_home_due_ms"] == 720
    assert not any(event["type"] == "home_requested" for event in held["events"])

    left = actor_core.advance_snapshot(held["snapshot"], 420)
    left_actor = left["snapshot"]["actors"][ACTOR_ID]
    assert left_actor["activity"] == "going_home"
    assert left_actor["presence"] == "leaving"
    home_event = next(event for event in left["events"] if event["type"] == "home_requested")
    assert home_event["work_loop_completed"] is True
    assert home_event["reason"] == "stamina_critical"


def test_emotion_effects_are_numeric_clamped_and_persistent(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot("floor01")
    actor = snapshot["actors"][ACTOR_ID]
    actor["stamina"].update({
        "current_milli": 50000,
        "threshold_band": "normal",
        "drain_remainder": 0,
    })
    sad = actor_core.apply_emotion_effect(snapshot, ACTOR_ID, "sad", timestamp_ms=0)
    sad_actor = sad["snapshot"]["actors"][ACTOR_ID]
    assert sad_actor["stamina"]["current_milli"] == 49000
    assert sad["events"][0]["type"] == "stamina_emotion_effect"
    assert sad["events"][0]["effect_milli"] == -1000

    happy = actor_core.apply_emotion_effect(
        sad["snapshot"], ACTOR_ID, "happy", timestamp_ms=0
    )
    assert happy["snapshot"]["actors"][ACTOR_ID]["stamina"]["current_milli"] == 51000


def test_central_facade_routes_emotion_effect_to_actor_snapshot(central_core: CentralGameCore):
    snapshot = central_core.resolve_actor_snapshot("floor01")
    actor = snapshot["actors"][ACTOR_ID]
    actor["stamina"].update({
        "current_milli": 50000,
        "threshold_band": "normal",
        "drain_remainder": 0,
    })
    result = central_core.apply_actor_emotion_effect(snapshot, ACTOR_ID, "happy")
    assert result["snapshot"]["actors"][ACTOR_ID]["stamina"]["current_milli"] == 52000


def test_runtime_snapshot_save_load_and_replay_are_deterministic(central_core: CentralGameCore):
    runtime = central_core.resolve_runtime_snapshot("floor02")
    steps = [
        {"elapsed_ms": 60, "actor_commands": [], "speech_commands": []},
        {"elapsed_ms": 360, "actor_commands": [], "speech_commands": []},
    ]
    encoded = central_core.serialize_runtime_snapshot(runtime)
    restored = central_core.deserialize_runtime_snapshot(encoded)
    assert restored == runtime
    replay = central_core.replay_runtime_snapshot(runtime, steps)
    sequential = runtime
    for step in steps:
        sequential = central_core.advance_runtime_snapshot(
            sequential,
            step["elapsed_ms"],
            actor_commands=step["actor_commands"],
            speech_commands=step["speech_commands"],
        )
    assert replay["snapshot"] == {
        key: sequential[key]
        for key in ("schema", "version", "actor_snapshot", "speech_snapshot", "conversation_snapshot")
    }
    package = central_core.serialize_runtime_replay(runtime, steps)
    replay_from_package = central_core.replay_runtime_package(package)
    assert replay_from_package["snapshot"] == replay["snapshot"]


def test_recovery_event_is_deterministic_and_clamped(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    actor = snapshot["actors"][ACTOR_ID]
    actor["activity"] = "wandering"
    actor["conversation_phase"] = None
    actor["stamina"].update(
        {"current_milli": 99000, "threshold_band": "normal", "drain_remainder": 0}
    )
    actor["behavior"].update(
        {
            "event_counter": 1,
            "next_event_due_ms": None,
            "activity_started_ms": 0,
            "activity_until_ms": 60,
            "active_event": "wander",
            "cooldowns": {},
        }
    )

    result = actor_core.advance_snapshot(snapshot, 60)
    changed = result["snapshot"]["actors"][ACTOR_ID]
    recovery_events = [
        event
        for event in result["events"]
        if event["employee_id"] == ACTOR_ID and event["type"] == "stamina_recovery"
    ]
    assert len(recovery_events) == 1
    assert recovery_events[0]["behavior"] == "wander"
    assert changed["activity"] == "working"
    assert changed["behavior"]["active_event"] is None
    assert changed["stamina"]["current_milli"] == 100000
    assert changed["stamina"]["threshold_band"] == "normal"


def test_weighted_event_choice_is_stable_and_honors_cooldowns(actor_core: ActorSimulationCore):
    first = actor_core.choose_behavior_event(
        ACTOR_ID, simulation_time_ms=12345, event_counter=7
    )
    second = actor_core.choose_behavior_event(
        ACTOR_ID, simulation_time_ms=12345, event_counter=7
    )
    assert first == second
    assert first in actor_core.WEIGHTED_EVENTS

    with pytest.raises(ActorSimulationError, match="No eligible"):
        actor_core.choose_behavior_event(
            ACTOR_ID,
            simulation_time_ms=12345,
            event_counter=7,
            cooldowns={event: 999999 for event in actor_core.WEIGHTED_EVENTS},
        )


def test_due_behavior_event_emits_one_ordered_start(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    snapshot["actors"][ACTOR_ID]["behavior"]["next_event_due_ms"] = 0

    result = actor_core.advance_snapshot(snapshot, 60)
    actor = result["snapshot"]["actors"][ACTOR_ID]
    starts = [
        event
        for event in result["events"]
        if event["employee_id"] == ACTOR_ID and event["type"] == "behavior_started"
    ]
    assert len(starts) == 1
    assert starts[0]["timestamp_ms"] == 0
    assert actor["behavior"]["active_event"] == starts[0]["behavior"]
    # Talk is now an actor-owned request that remains pending until Central
    # commits a speech session; it must not fall back to the old generic
    # 5–8-second recovery window.
    if starts[0]["behavior"] == "talk":
        assert actor["behavior"]["activity_until_ms"] is None
        assert actor["conversation_phase"] == "talk_pending"
    else:
        assert actor["behavior"]["activity_until_ms"] > 0
    assert result["snapshot"]["determinism"]["root_event_counter"] == len(result["events"])


def test_request_home_retains_owned_workstation_and_is_explicit(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    assignment = copy.deepcopy(snapshot["actors"][ACTOR_ID]["assignment"])

    result = actor_core.advance_snapshot(
        snapshot,
        0,
        commands=[{"type": "request_home", "employee_id": ACTOR_ID}],
    )
    actor = result["snapshot"]["actors"][ACTOR_ID]
    assert actor["presence"] == "leaving"
    assert actor["activity"] == "going_home"
    assert actor["assignment"] == assignment
    assert result["events"] == [
        {
            "event_index": 0,
            "timestamp_ms": 0,
            "employee_id": ACTOR_ID,
            "type": "home_requested",
            "assignment_retained": True,
        }
    ]


def test_home_route_reaches_recovery_then_returns_to_the_same_workseat(
    central_core: CentralGameCore,
):
    employee_id = "EMP_W1_0010"
    snapshot = central_core.resolve_actor_snapshot("floor02")
    assignment = copy.deepcopy(snapshot["actors"][employee_id]["assignment"])
    requested = central_core.advance_actor_snapshot(
        snapshot,
        0,
        commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    actor = requested["snapshot"]["actors"][employee_id]
    assert actor["position"]["route"]["phase"] == "to_portal"
    outbound_ms = actor["position"]["route"]["duration_ms"]
    exited = central_core.advance_actor_snapshot(requested["snapshot"], outbound_ms + 240)
    actor = exited["snapshot"]["actors"][employee_id]
    assert actor["presence"] == "home"
    assert actor["activity"] == "home_recovery"
    assert actor["position"] == {"floor_id": None, "uv": None, "ground_xy": None, "route": None}
    assert actor["assignment"] == assignment
    assert actor["stamina"]["current_milli"] == 100000
    assert any(event["type"] == "home_recovery_started" for event in exited["events"])

    ready_at = actor["behavior"]["activity_until_ms"]
    if ready_at > exited["snapshot"]["clock"]["simulation_time_ms"]:
        exited = central_core.advance_actor_snapshot(
            exited["snapshot"], ready_at - exited["snapshot"]["clock"]["simulation_time_ms"]
        )
    returned = central_core.advance_actor_snapshot(
        exited["snapshot"],
        0,
        commands=[{"type": "request_return", "employee_id": employee_id}],
    )
    actor = returned["snapshot"]["actors"][employee_id]
    assert actor["presence"] == "entering"
    assert actor["activity"] == "returning_to_work"
    inbound_ms = actor["position"]["route"]["duration_ms"]
    completed = central_core.advance_actor_snapshot(
        returned["snapshot"], inbound_ms + 20000
    )
    actor = completed["snapshot"]["actors"][employee_id]
    assert actor["presence"] == "present"
    assert actor["activity"] == "working"
    assert actor["assignment"] == assignment
    assert actor["position"]["route"] is None
    assert any(event["type"] == "workseat_reentered" for event in completed["events"])


def test_behavior_start_emits_renderer_channel_without_mutating_stamina(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot("floor01")
    actor = snapshot["actors"][ACTOR_ID]
    actor["behavior"]["next_event_due_ms"] = 0
    before = actor["stamina"]["current_milli"]
    actor_core.choose_behavior_event = lambda *args, **kwargs: "popup"
    result = actor_core.advance_snapshot(snapshot, 60)
    started = next(event for event in result["events"] if event["type"] == "behavior_started")
    assert started["presentation"]["channel"] == "humanball"
    assert started["presentation"]["render_owner"] == "work_seat"
    assert result["snapshot"]["actors"][ACTOR_ID]["stamina"]["current_milli"] == before


def test_snapshot_rejects_assignment_mutation_and_malformed_commands(actor_core: ActorSimulationCore):
    snapshot = actor_core.initial_snapshot()
    snapshot["actors"][ACTOR_ID]["assignment"]["workstation_id"] = "ws999"
    with pytest.raises(ActorSimulationError, match="assignment changed"):
        actor_core.validate_snapshot(snapshot)

    with pytest.raises(ActorSimulationError, match="commands must contain objects"):
        actor_core.advance_snapshot(actor_core.initial_snapshot(), 0, commands=["not-an-object"])


def actor_simulation_json(snapshot: dict) -> dict:
    return json.loads(json.dumps(snapshot, allow_nan=False))
