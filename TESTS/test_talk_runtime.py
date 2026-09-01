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


def test_external_talk_request_precedes_routine_greeting():
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
    assert request["kind"] == "pair"
    assert request["external"] is True
    assert request["category"] == "conversation_open"


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
    assert actor["activity"] == "talking"
    assert actor["conversation_phase"] == "self_talk"
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
    assert result["actor_snapshot"]["actors"][INITIATOR]["activity"] == "talking"


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
