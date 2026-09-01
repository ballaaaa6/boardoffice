from __future__ import annotations

import json

from TOOLS.runtime_review_server import ReviewState


def test_review_talk_demo_starts_real_route_and_compact_event_stream():
    state = ReviewState()
    payload = state.demo_talk(dialogue_locale="th", dialogue_seed="review-talk", include_runtime=False)

    assert payload["clock_ms"] == 60
    assert "talk demo" in payload["note"]
    assert any(event["type"] == "talk_session_accepted" for event in payload["events"])
    assert any(
        actor["route_phase"] == "talk_outbound"
        for actor in payload["actors"]
        if actor["employee_id"] == payload["events"][0]["employee_id"]
    )
    speech = next(event for event in payload["events"] if event["type"] == "speech_session_started")
    assert speech["mode"] in {"ceo_front", "seated_host", "standing_pair", "self_talk"}
    assert speech["dialogue_lines"]
    assert all("conversation_plan" not in event for event in payload["events"])
    assert len(json.dumps(payload, ensure_ascii=False)) < 600_000

    # The seated host can emit its own immediate ``talk_returned`` event;
    # completion must wait for the visiting initiator to finish its authored
    # inbound route and return to its owned WorkSeat.
    initiator_id = payload["demo_employee_id"]
    assert initiator_id
    all_events = list(payload["events"])
    for _ in range(60):
        payload = state.tick(360, include_runtime=False)
        all_events.extend(payload["events"])
        if payload["demo_complete"]:
            break
    assert payload["demo_complete"] is True
    assert any(
        event["type"] == "talk_returned" and event.get("employee_id") == initiator_id
        for event in payload["events"]
    )
    assert not any(
        event.get("type") == "speech_session_started"
        and event.get("category") in {"work_start", "idle_flavor"}
        for event in all_events
    )
    assert not any(actor["dialogue_visible"] for actor in payload["actors"])


def test_compact_event_stream_keeps_latest_route_sample_per_actor():
    events = [
        {"source": "actor", "event_index": 1, "timestamp_ms": 60, "employee_id": "A", "type": "actor_route_sample", "phase": "talk_outbound", "progress_t": 0.1},
        {"source": "actor", "event_index": 2, "timestamp_ms": 120, "employee_id": "A", "type": "actor_route_sample", "phase": "talk_outbound", "progress_t": 0.2},
        {"source": "actor", "event_index": 3, "timestamp_ms": 120, "employee_id": "A", "type": "talk_returned"},
    ]

    compact = ReviewState._compact_events(events)

    assert len(compact) == 2
    assert {event["type"] for event in compact} == {"actor_route_sample", "talk_returned"}
    route = next(event for event in compact if event["type"] == "actor_route_sample")
    assert route["progress_t"] == 0.2


def test_review_effects_demo_exposes_humanball_and_vfx_then_completes():
    state = ReviewState()
    payload = state.demo_effects(dialogue_seed="review-effects", include_runtime=False)

    overlays = {actor["overlay"] for actor in payload["actors"] if actor["overlay"]}
    assert any(value.startswith("humanball:") for value in overlays)
    assert any(value.startswith("vfx:") for value in overlays)
    assert payload["demo_kind"] == "effects"
    assert payload["demo_complete"] is False

    for _ in range(10):
        payload = state.tick(360, include_runtime=False)
        if payload["demo_complete"]:
            break
    assert payload["demo_complete"] is True
    assert payload["demo_kind"] == "effects"
