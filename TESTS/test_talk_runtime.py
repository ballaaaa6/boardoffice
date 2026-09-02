from __future__ import annotations

import copy
from pathlib import Path

from RUNTIME.actor_simulation_core import ActorSimulationCore
from RUNTIME.central_core import CentralGameCore
from RUNTIME.speech_scheduler_core import SpeechSchedulerCore


ROOT = Path(__file__).resolve().parents[1]
INITIATOR = "EMP_W1_0010"


def _quiet_runtime() -> tuple[CentralGameCore, dict]:
    core = CentralGameCore(ROOT)
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
    return core, runtime


def _start_talk() -> tuple[CentralGameCore, dict, dict]:
    core, runtime = _quiet_runtime()
    runtime["actor_snapshot"]["actors"][INITIATOR]["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    result = core.advance_runtime_snapshot(runtime, 60)
    return core, runtime, result


def test_central_commits_talk_plan_into_actor_routes_before_rendering():
    _core, _runtime, result = _start_talk()
    actor = result["actor_snapshot"]["actors"][INITIATOR]
    started = next(
        event for event in result["speech_events"]
        if event["type"] == "speech_session_started" and event["kind"] == "pair"
    )
    accepted = next(
        event for event in result["actor_events"]
        if event["type"] == "talk_session_accepted"
        and event["employee_id"] == INITIATOR
    )

    assert accepted["session_id"] == started["session_id"]
    assert actor["activity"] == "talking"
    assert actor["conversation_phase"] == "walking_to_talk"
    assert actor["position"]["route"]["phase"] == "talk_outbound"
    assert actor["behavior"]["talk"]["session_id"] == started["session_id"]
    assert actor["behavior"]["talk"]["outbound_path_cells_uv"]
    assert actor["position"]["ground_xy"] is not None


def test_standing_pair_hold_uses_planned_endpoint_facings_in_live_actor_route():
    core, runtime = _quiet_runtime()
    rows = sorted(
        runtime["actor_snapshot"]["actors"].values(),
        key=lambda actor: (
            int(actor["assignment"]["assignment_order"]),
            actor["employee_id"],
        ),
    )
    employees = [
        actor["employee_id"]
        for actor in rows
        if actor["assignment"]["workstation_id"] != "ceo"
    ]
    initiator, partner = employees[:2]

    def force_standing(_snapshot, initiator_id, *, counter):
        if initiator_id != initiator:
            return None
        return {
            "kind": "pair",
            "initiator_id": initiator,
            "partner_id": partner,
            "participants": [initiator, partner],
            "mode": "standing_pair",
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }

    core.speech_scheduler._mode_request = force_standing
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0

    accepted = core.advance_runtime_snapshot(runtime, 60)
    started = next(
        event
        for event in accepted["speech_events"]
        if event["type"] == "speech_session_started"
        and event["mode"] == "standing_pair"
    )
    plan = started["conversation_plan"]
    endpoints = plan["endpoint_by_actor"]
    lower_u = min(endpoints, key=lambda employee_id: tuple(endpoints[employee_id])[0])
    higher_u = max(endpoints, key=lambda employee_id: tuple(endpoints[employee_id])[0])
    assert plan["facing_by_actor"] == {lower_u: "SW", higher_u: "NE"}

    arrival_ms = int(started["movement_arrival_ms"])
    held = core.advance_runtime_snapshot(
        accepted,
        arrival_ms - int(accepted["actor_snapshot"]["clock"]["simulation_time_ms"]),
    )

    for employee_id in (lower_u, higher_u):
        route = held["actor_snapshot"]["actors"][employee_id]["position"]["route"]
        assert route["phase"] == "talk_hold"
        assert route["direction"] == plan["facing_by_actor"][employee_id]


def test_actor_talk_route_completes_hold_return_and_recovery_owner():
    core, _runtime, first = _start_talk()
    actor_snapshot = first["actor_snapshot"]
    before = copy.deepcopy(actor_snapshot)
    completed = core.actor_simulation.advance_snapshot(actor_snapshot, 15_000)
    actor = completed["snapshot"]["actors"][INITIATOR]
    types = [
        event["type"]
        for event in completed["events"]
        if event.get("employee_id") == INITIATOR
    ]

    assert actor_snapshot == before
    assert "actor_route_sample" in types
    assert "talk_arrived" in types
    assert "talk_return_started" in types
    assert "talk_returned" in types
    assert "stamina_recovery" in types
    assert actor["activity"] == "working"
    assert actor["conversation_phase"] is None
    assert actor["position"]["route"] is None
    assert actor["behavior"]["talk"] is None


def test_talk_start_trace_is_deterministic():
    first = _start_talk()[2]
    second = _start_talk()[2]
    assert first["actor_snapshot"] == second["actor_snapshot"]
    assert first["speech_snapshot"] == second["speech_snapshot"]
    assert first["actor_events"] == second["actor_events"]
    assert first["speech_events"] == second["speech_events"]


def test_entry_lifecycle_speech_precedes_external_talk_when_both_are_due():
    actor_snapshot = ActorSimulationCore(ROOT).initial_snapshot("floor02")
    scheduler = SpeechSchedulerCore(ROOT)
    snapshot = scheduler.initial_snapshot(actor_snapshot)
    for actor in snapshot["actors"].values():
        actor.update({
            "greeting_due_ms": 0,
            "greeting_emitted": False,
            "work_start_due_ms": 0,
            "work_start_emitted": False,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    snapshot["actors"][INITIATOR]["external_talk_pending"] = True
    snapshot["actors"][INITIATOR]["external_talk_due_ms"] = 0

    request = scheduler._request_for_actor(snapshot, INITIATOR, now_ms=0)

    assert request is not None
    assert request["kind"] == "lifecycle"
    assert request.get("external", False) is False
    assert request["category"] == "greeting"


def test_ceo_talk_request_uses_seated_self_talk_fallback():
    core, runtime = _quiet_runtime()
    ceo = next(
        employee_id
        for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
        if actor["assignment"]["workstation_id"] == "ceo"
    )
    runtime["actor_snapshot"]["actors"][ceo]["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    result = core.advance_runtime_snapshot(runtime, 60)
    session = next(
        event for event in result["speech_events"]
        if event["type"] == "speech_session_started"
        and event["employee_id"] == ceo
    )
    actor = result["actor_snapshot"]["actors"][ceo]

    assert session["kind"] == "solo"
    assert session["mode"] == "self_talk"
    assert actor["activity"] == "working"
    assert actor["conversation_phase"] is None
    assert actor["behavior"]["talk"]["route_committed"] is False
    assert actor["position"]["route"] is None


def test_unavailable_partner_uses_bounded_self_talk_fallback():
    core, runtime = _quiet_runtime()
    for employee_id, actor in runtime["speech_snapshot"]["actors"].items():
        if employee_id != INITIATOR:
            actor["speech_phase"] = "active"
    runtime["actor_snapshot"]["actors"][INITIATOR]["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    result = core.advance_runtime_snapshot(runtime, 60)
    session = next(
        event for event in result["speech_events"]
        if event["type"] == "speech_session_started"
        and event["employee_id"] == INITIATOR
    )

    assert session["kind"] == "solo"
    assert session["mode"] == "self_talk"
    actor = result["actor_snapshot"]["actors"][INITIATOR]
    assert actor["activity"] == "working"
    assert actor["conversation_phase"] is None
    assert actor["behavior"]["talk"]["route_committed"] is False


def test_stationary_self_talk_overlay_keeps_working_clock_and_stamina_running():
    core, runtime = _quiet_runtime()
    for employee_id, actor in runtime["speech_snapshot"]["actors"].items():
        if employee_id != INITIATOR:
            actor["speech_phase"] = "active"
    actor = runtime["actor_snapshot"]["actors"][INITIATOR]
    actor["behavior"].update({
        "next_event_due_ms": 0,
        "work_loop_elapsed_ms": 240,
        "work_loop_count": 2,
    })
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    current = core.advance_runtime_snapshot(runtime, 60)
    started_actor = current["actor_snapshot"]["actors"][INITIATOR]
    assert started_actor["behavior"]["talk"]["route_committed"] is False
    assert started_actor["activity"] == "working"
    assert started_actor["conversation_phase"] is None
    assert started_actor["position"]["route"] is None

    phase_before = int(started_actor["behavior"]["work_loop_elapsed_ms"])
    stamina_before = int(started_actor["stamina"]["current_milli"])
    for _ in range(8):
        current = core.advance_runtime_snapshot(current, 60)

    progressed_actor = current["actor_snapshot"]["actors"][INITIATOR]
    assert int(progressed_actor["behavior"]["work_loop_elapsed_ms"]) != phase_before
    assert int(progressed_actor["stamina"]["current_milli"]) < stamina_before


def test_routed_talk_preserves_work_loop_phase_after_return():
    core, runtime = _quiet_runtime()
    actor = runtime["actor_snapshot"]["actors"][INITIATOR]
    actor["behavior"].update({
        "next_event_due_ms": 0,
        "work_loop_elapsed_ms": 240,
        "work_loop_count": 2,
    })
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    current = core.advance_runtime_snapshot(runtime, 60)
    phase_before = int(
        current["actor_snapshot"]["actors"][INITIATOR]["behavior"]["work_loop_elapsed_ms"]
    )
    count_before = int(
        current["actor_snapshot"]["actors"][INITIATOR]["behavior"]["work_loop_count"]
    )
    returned = None
    for _ in range(400):
        current = core.advance_runtime_snapshot(current, 60)
        if any(
            event["type"] == "talk_returned"
            and event.get("employee_id") == INITIATOR
            for event in current["actor_events"]
        ):
            returned = current
            break

    assert returned is not None
    actor = returned["actor_snapshot"]["actors"][INITIATOR]
    returned_at = next(
        int(event["timestamp_ms"])
        for event in returned["actor_events"]
        if event["type"] == "talk_returned" and event.get("employee_id") == INITIATOR
    )
    continued_work_ms = (
        int(returned["actor_snapshot"]["clock"]["simulation_time_ms"]) - returned_at
    )
    expected_total = phase_before + continued_work_ms
    assert actor["activity"] == "working"
    assert actor["behavior"]["talk"] is None
    assert actor["position"]["route"] is None
    assert int(actor["behavior"]["work_loop_elapsed_ms"]) == expected_total % core.actor_simulation.WORK_LOOP_MS
    assert int(actor["behavior"]["work_loop_count"]) == count_before + expected_total // core.actor_simulation.WORK_LOOP_MS


def test_pending_talk_can_be_cancelled_without_consuming_a_generic_window():
    actor_core = ActorSimulationCore(ROOT)
    snapshot = actor_core.initial_snapshot("floor02")
    snapshot["actors"][INITIATOR]["behavior"]["next_event_due_ms"] = 0
    actor_core.choose_behavior_event = lambda *args, **kwargs: "talk"
    pending = actor_core.advance_snapshot(snapshot, 60)
    cancelled = actor_core.advance_snapshot(
        pending["snapshot"],
        0,
        commands=[{
            "type": "cancel_talk",
            "employee_id": INITIATOR,
            "reason": "no_valid_partner",
        }],
    )
    actor = cancelled["snapshot"]["actors"][INITIATOR]

    assert actor["activity"] == "working"
    assert actor["conversation_phase"] is None
    assert actor["behavior"]["talk"] is None
    assert any(event["type"] == "talk_cancelled" for event in cancelled["events"])


def test_pending_talk_cancellation_preserves_the_owned_workseat_position():
    actor_core = ActorSimulationCore(ROOT)
    snapshot = actor_core.initial_snapshot("floor02")
    actor = snapshot["actors"][INITIATOR]
    actor["position"].update({
        "floor_id": "floor02",
        "uv": [20, 12],
        "ground_xy": [640.0, 384.0],
        "route": None,
    })
    actor["behavior"]["next_event_due_ms"] = 0
    actor_core.choose_behavior_event = lambda *args, **kwargs: "talk"

    pending = actor_core.advance_snapshot(snapshot, 60)
    pending_position = copy.deepcopy(pending["snapshot"]["actors"][INITIATOR]["position"])
    assert pending["snapshot"]["actors"][INITIATOR]["conversation_phase"] == "talk_pending"

    cancelled = actor_core.advance_snapshot(
        pending["snapshot"],
        0,
        commands=[{
            "type": "cancel_talk",
            "employee_id": INITIATOR,
            "reason": "no_valid_partner",
        }],
    )

    assert cancelled["snapshot"]["actors"][INITIATOR]["position"] == pending_position


def test_pending_talk_keeps_work_clock_running_while_speech_lane_is_busy():
    core, runtime = _quiet_runtime()
    actor_ids = sorted(runtime["actor_snapshot"]["actors"])
    blocker, initiator = actor_ids[:2]

    blocker_speech = runtime["speech_snapshot"]["actors"][blocker]
    blocker_speech.update({
        "greeting_due_ms": 0,
        "greeting_emitted": False,
    })
    first = core.advance_runtime_snapshot(runtime, 60)
    assert first["speech_snapshot"]["lanes"]["floor02"]["active_session_id"] is not None

    actor = first["actor_snapshot"]["actors"][initiator]
    actor["behavior"]["next_event_due_ms"] = int(
        first["actor_snapshot"]["clock"]["simulation_time_ms"]
    )
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    before = first["actor_snapshot"]["actors"][initiator]
    before_loop = int(before["behavior"]["work_loop_elapsed_ms"])
    before_stamina = int(before["stamina"]["current_milli"])

    current = first
    for _ in range(5):
        current = core.advance_runtime_snapshot(current, 60)

    pending = current["actor_snapshot"]["actors"][initiator]
    assert pending["activity"] == "talking"
    assert pending["conversation_phase"] == "talk_pending"
    assert pending["behavior"]["talk"] is None
    assert int(pending["behavior"]["work_loop_elapsed_ms"]) != before_loop
    assert int(pending["stamina"]["current_milli"]) < before_stamina
    assert current["speech_snapshot"]["actors"][initiator]["external_talk_pending"] is True


def test_unaccepted_talk_request_times_out_back_to_working():
    actor_core = ActorSimulationCore(ROOT)
    snapshot = actor_core.initial_snapshot("floor02")
    snapshot["actors"][INITIATOR]["behavior"]["next_event_due_ms"] = 0
    actor_core.choose_behavior_event = lambda *args, **kwargs: "talk"

    result = actor_core.advance_snapshot(snapshot, 30_060)
    actor = result["snapshot"]["actors"][INITIATOR]

    assert actor["activity"] == "working"
    assert actor["conversation_phase"] is None
    assert any(
        event["type"] == "talk_cancelled" and event["reason"] == "talk_queue_timeout"
        for event in result["events"]
    )
