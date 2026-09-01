from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from RUNTIME.actor_simulation_core import ActorSimulationCore
from RUNTIME.central_core import CentralGameCore, CentralGameCoreError
from RUNTIME.speech_scheduler_core import SpeechSchedulerCore


ROOT = Path(__file__).resolve().parents[1]


def _actor_snapshot(floor_id: str = "floor02"):
    return ActorSimulationCore(ROOT).initial_snapshot(floor_id)


def _quiet_scheduler(core: SpeechSchedulerCore, actor_snapshot: dict):
    snapshot = core.initial_snapshot(actor_snapshot)
    for actor in snapshot["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": 0,
        })
    return snapshot


def test_speech_contract_and_snapshot_schema_validate():
    contract = json.loads((ROOT / "CONTRACTS" / "speech_scheduler.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "SCHEMA" / "speech_scheduler.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(contract)) == []
    snapshot_schema = json.loads((ROOT / "SCHEMA" / "speech_scheduler_snapshot.schema.json").read_text(encoding="utf-8"))
    speech = SpeechSchedulerCore(ROOT)
    snapshot = speech.initial_snapshot(_actor_snapshot())
    assert list(Draft202012Validator(snapshot_schema).iter_errors(snapshot)) == []
    assert json.loads(json.dumps(snapshot, sort_keys=True)) == snapshot
    assert contract["actor_bridge"]["effective_timestamp_field"] == "effective_at_ms"
    assert contract["conversation_modes"]["unavailable_partner_fallback"] == "seated_self_talk"
    assert contract["conversation_modes"]["ceo_request_fallback"] == (
        "seated_self_talk_no_outbound_route"
    )


def test_initial_timers_use_authorized_categories_and_ranges():
    speech = SpeechSchedulerCore(ROOT)
    snapshot = speech.initial_snapshot(_actor_snapshot())
    for actor in snapshot["actors"].values():
        assert 2000 <= actor["greeting_due_ms"] <= 3000
        assert 30000 <= actor["solo_next_due_ms"] <= 60000
        if actor["role"] == "ceo":
            assert actor["pair_next_due_ms"] is None
        else:
            assert 45000 <= actor["pair_next_due_ms"] <= 75000
    assert speech.SOLO_CATEGORIES == (
        "encouragement", "uncertainty", "surprise", "work_progress", "idle_flavor"
    )
    assert speech.initial_snapshot("floor02")["lanes"]


def test_lane_blocks_new_session_until_fade_and_keeps_pose_binding_independent():
    actor_snapshot = _actor_snapshot()
    before = copy.deepcopy(actor_snapshot)
    speech = SpeechSchedulerCore(ROOT)
    snapshot = _quiet_scheduler(speech, actor_snapshot)
    first = speech.advance_snapshot(snapshot, 60, actor_snapshot=actor_snapshot)
    assert actor_snapshot == before
    started = [event for event in first["events"] if event["type"] == "speech_session_started"]
    assert len(started) == 1
    session_id = started[0]["session_id"]
    assert first["snapshot"]["lanes"]["floor02"]["active_session_id"] == session_id
    assert started[0]["pose_bindings"][started[0]["participants"][0]]["action"] in {"idle", "work"}

    held = speech.advance_snapshot(first["snapshot"], 4000, actor_snapshot=actor_snapshot)
    # The old window owns the lane through the 300 ms fade.  No second
    # session is allowed to start before the exact 4.3 s boundary.
    assert not any(event["type"] == "speech_session_started" for event in held["events"])
    finished = speech.advance_snapshot(held["snapshot"], 300, actor_snapshot=actor_snapshot)
    assert any(event["type"] == "speech_session_completed" for event in finished["events"])
    assert any(event["type"] == "speech_session_started" for event in finished["events"])


def test_reception_leaving_is_explicit_draw_over_trigger_and_has_priority():
    actor_snapshot = _actor_snapshot()
    speech = SpeechSchedulerCore(ROOT)
    snapshot = speech.initial_snapshot(actor_snapshot)
    actor_id = sorted(snapshot["actors"])[0]
    with pytest.raises(CentralGameCoreError):
        CentralGameCore(ROOT).advance_speech_snapshot(
            snapshot,
            60,
            actor_snapshot=actor_snapshot,
            commands=[{"type": "reception_depth_crossed", "employee_id": actor_id}],
        )
    for actor in snapshot["actors"].values():
        actor.update({
            "greeting_due_ms": None, "greeting_emitted": True,
            "work_start_due_ms": None, "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    result = speech.advance_snapshot(
        snapshot,
        60,
        actor_snapshot=actor_snapshot,
        commands=[{
            "type": "reception_depth_crossed",
            "employee_id": actor_id,
            "draws_over_reception": True,
        }],
    )
    assert result["events"][0]["category"] == "leaving"


def test_reception_depth_helper_matches_authored_front_edge_not_raw_uv_threshold():
    core = CentralGameCore(ROOT)
    assert core.actor_draws_over_reception("floor02", (310, 394)) is False
    assert core.actor_draws_over_reception("floor02", (310, 396)) is True
    assert core.actor_draws_over_reception("floor02", (267, 409)) is False
    assert core.actor_draws_over_reception("floor02", (267, 410)) is True


def test_standing_pair_has_one_shared_die_outcome_then_return_hook():
    actor_snapshot = _actor_snapshot()
    speech = SpeechSchedulerCore(ROOT)
    snapshot = _quiet_scheduler(speech, actor_snapshot)
    # Remove the floor CEO from the candidate set so the first valid mode is
    # standing_pair; this changes only scheduler state, not employee metadata.
    for actor in snapshot["actors"].values():
        if actor["role"] == "ceo":
            actor["speech_phase"] = "emotion"
            actor["emotion"] = "sad"
            actor["emotion_until_ms"] = 999999
    employee_ids = [
        employee_id for employee_id, actor in snapshot["actors"].items()
        if actor["role"] == "employee"
    ]
    forced_initiator, forced_partner = employee_ids[:2]
    def force_standing(_snapshot, initiator_id, *, counter):
        if initiator_id != forced_initiator:
            return None
        return {
            "kind": "pair",
            "initiator_id": forced_initiator,
            "partner_id": forced_partner,
            "participants": [forced_initiator, forced_partner],
            "mode": "standing_pair",
            "category": "conversation_open",
            "dialogue_categories": ["conversation_open", "conversation_reply"],
        }
    speech._mode_request = force_standing
    result = speech.advance_snapshot(snapshot, 60, actor_snapshot=actor_snapshot)
    start = next(event for event in result["events"] if event["type"] == "speech_session_started")
    assert start["mode"] == "standing_pair"
    session = result["snapshot"]["active_sessions"][start["session_id"]]
    assert session["emotion_outcome"] in {"sad", "happy"}
    completed = speech.advance_snapshot(result["snapshot"], 4240, actor_snapshot=actor_snapshot)
    emotion = next(event for event in completed["events"] if event["type"] == "emotion_started")
    assert emotion["emotion"] == session["emotion_outcome"]
    assert all(
        binding["action"] == session["emotion_outcome"]
        for binding in emotion["pose_bindings"].values()
    )
    finished = next(event for event in completed["events"] if event["type"] == "speech_session_completed")
    assert finished["return_requested"] is False
    returned = speech.advance_snapshot(completed["snapshot"], 1200, actor_snapshot=actor_snapshot)
    assert any(event["type"] == "return_requested" for event in returned["events"])
    assert all(actor["speech_phase"] == "idle" for actor in returned["snapshot"]["actors"].values() if actor["employee_id"] in session["participants"])


def test_pair_bubble_start_is_emitted_at_arrival_not_route_start():
    core = CentralGameCore(ROOT)
    actor_snapshot = core.resolve_actor_snapshot("floor02")
    conversation_snapshot = core.resolve_conversation_snapshot("floor02")
    speech = SpeechSchedulerCore(ROOT, employee_registry=core.employee_metadata, conversation=core.conversation)
    snapshot = _quiet_scheduler(speech, actor_snapshot)
    employee_ids = [
        employee_id for employee_id, actor in snapshot["actors"].items()
        if actor["role"] == "employee"
    ]
    initiator, partner = employee_ids[:2]

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

    speech._mode_request = force_standing
    first = speech.advance_snapshot(
        snapshot,
        60,
        actor_snapshot=actor_snapshot,
        conversation_snapshot=conversation_snapshot,
    )
    started = next(event for event in first["events"] if event["type"] == "speech_session_started")
    assert started["timestamp_ms"] < started["bubble_start_ms"]
    assert not any(event["type"] == "speech_bubble_started" for event in first["events"])
    arrived = speech.advance_snapshot(
        first["snapshot"],
        started["bubble_start_ms"] - first["snapshot"]["clock"]["simulation_time_ms"],
        actor_snapshot=actor_snapshot,
        conversation_snapshot=conversation_snapshot,
    )
    bubble = next(event for event in arrived["events"] if event["type"] == "speech_bubble_started")
    assert bubble["timestamp_ms"] == started["bubble_start_ms"]
    assert bubble["fade_end_ms"] == bubble["timestamp_ms"] + 4300


def test_automatic_conversation_plan_uses_seeded_mode_and_explicit_pose_bindings():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    employee_id = next(employee_id for employee_id, actor in snapshot["actors"].items() if actor["role"] == "employee")
    first = core.resolve_automatic_conversation_plan(
        employee_id, snapshot=snapshot, selection_seed="qa-seed"
    )
    second = core.resolve_automatic_conversation_plan(
        employee_id, snapshot=snapshot, selection_seed="qa-seed"
    )
    assert first == second
    assert first["ready"] is True
    assert first["mode"] in {"ceo_front", "seated_host", "standing_pair"}
    assert set(first["pose_bindings"]) == set(first["participants"])
    if first["mode"] == "ceo_front":
        assert first["pose_bindings"][first["partner_id"]]["subaction"] == "normal_work"
    elif first["mode"] == "seated_host":
        assert first["pose_bindings"][first["partner_id"]]["subaction"].startswith("turn_side_")
    else:
        assert all(binding["subaction"] == "idle" for binding in first["pose_bindings"].values())


def test_runtime_facade_advances_actor_and_speech_channels_separately():
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor02")
    assert core.validate_runtime_snapshot(runtime) == runtime
    before_actor = copy.deepcopy(runtime["actor_snapshot"])
    result = core.advance_runtime_snapshot(runtime, 60)
    assert result["schema"] == "gds.runtime_snapshot.v1"
    assert result["actor_snapshot"]["clock"]["simulation_time_ms"] == 60
    assert result["speech_snapshot"]["clock"]["simulation_time_ms"] == 60
    assert result["actor_snapshot"] != before_actor
    assert any(event["source"] == "speech" for event in result["events"])


def test_runtime_bridge_starts_speech_from_actor_talk_event_without_sharing_pose_clock():
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor02")
    initiator = next(
        employee_id
        for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
        if actor["assignment"]["workstation_id"] != "ceo"
    )
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    result = core.advance_runtime_snapshot(runtime, 60)
    started = next(event for event in result["speech_events"] if event["type"] == "speech_session_started")
    assert started["kind"] == "pair"
    assert started["participants"][0] == initiator
    assert result["actor_snapshot"]["actors"][initiator]["activity"] == "talking"
    assert result["speech_snapshot"]["actors"][initiator]["external_talk_pending"] is False


def test_runtime_bridge_arms_leaving_at_the_reception_crossing_timestamp():
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor02")
    employee_id = "EMP_W1_0010"
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    result = core.advance_runtime_snapshot(
        runtime,
        10000,
        actor_commands=[{"type": "request_home", "employee_id": employee_id}],
    )
    crossings = [
        event["timestamp_ms"]
        for event in result["actor_events"]
        if event.get("employee_id") == employee_id
        and event.get("type") == "actor_route_sample"
        and event.get("phase") in {"to_portal", "portal_exit"}
        and core.actor_draws_over_reception("floor02", event["ground_xy"])
    ]
    leaving = [
        event for event in result["speech_events"]
        if event.get("employee_id") == employee_id
        and event.get("type") == "speech_session_started"
        and event.get("category") == "leaving"
    ]
    assert crossings
    assert leaving and leaving[0]["timestamp_ms"] == crossings[0]


def test_runtime_presentation_crosses_speech_tracks_without_mutating_simulation():
    core = CentralGameCore(ROOT)
    runtime = core.resolve_runtime_snapshot("floor02")
    before = copy.deepcopy(runtime)
    initiator = next(
        employee_id
        for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
        if actor["assignment"]["workstation_id"] != "ceo"
    )
    for actor in runtime["speech_snapshot"]["actors"].values():
        actor.update({
            "greeting_due_ms": None,
            "greeting_emitted": True,
            "work_start_due_ms": None,
            "work_start_emitted": True,
            "solo_next_due_ms": None,
            "pair_next_due_ms": None,
        })
    runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    advanced = core.advance_runtime_snapshot(runtime, 60)
    advanced_before_presentation = copy.deepcopy(advanced)
    presentation = core.resolve_runtime_presentation(advanced)
    assert runtime != before, "the explicit test setup should only change the copied input"
    assert advanced == advanced_before_presentation
    assert presentation["schema"] == "gds.runtime_presentation_snapshot.v1"
    presentation_schema = json.loads(
        (ROOT / "SCHEMA" / "runtime_presentation_snapshot.schema.json").read_text(encoding="utf-8")
    )
    assert list(Draft202012Validator(presentation_schema).iter_errors(presentation)) == []
    assert presentation["timing_ms"] == {
        "simulation_tick": 60,
        "character_frame": 360,
        "effect_frame": 240,
        "humanball_frame": 240,
        "bubble_visible": 4000,
        "bubble_fade": 300,
    }
    started = next(
        event for event in advanced["speech_events"]
        if event["type"] == "speech_session_started" and event["kind"] == "pair"
    )
    assert set(started["participants"]) <= set(presentation["actors"])
    mode = started["mode"]
    if mode == "ceo_front":
        visitor, host = started["participants"]
        # Central now commits the visitor's physical talk route into the actor
        # snapshot; presentation must not overwrite the walking action with
        # the old pose-only timeline.
        assert presentation["actors"][visitor]["action"] == "move"
        assert presentation["actors"][visitor]["ground_xy"] is not None
        assert presentation["actors"][host]["action"] == "work"
        assert presentation["actors"][host]["subaction"] == "normal_work"
    elif mode == "seated_host":
        visitor, host = started["participants"]
        assert presentation["actors"][visitor]["action"] == "move"
        assert presentation["actors"][visitor]["ground_xy"] is not None
        assert presentation["actors"][host]["action"] == "work"
        assert presentation["actors"][host]["subaction"].startswith("turn_side_")
    else:
        assert all(
            presentation["actors"][employee_id]["action"] == "move"
            and presentation["actors"][employee_id]["ground_xy"] is not None
            for employee_id in started["participants"]
        )
    # The render seam is a pure read: no actor activity, stamina or assignment
    # is written back while the speech pose/bubble overlay is materialized.
    assert advanced["actor_snapshot"]["actors"][initiator]["assignment"] == runtime["actor_snapshot"]["actors"][initiator]["assignment"]
    assert presentation["actors"][initiator]["stamina"] == advanced["actor_snapshot"]["actors"][initiator]["stamina"]
