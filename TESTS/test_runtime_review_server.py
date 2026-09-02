from __future__ import annotations

import json
import time

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


def test_review_host_exposes_all_floors_channels_and_runtime_metrics():
    state = ReviewState()

    floors = state.floors()
    capabilities = state.capabilities()
    assert len(floors) == 25
    assert {row["floor_id"] for row in floors} == set(capabilities["floors"])
    assert {"live", "full", "talk", "effects", "critical", "wander"} <= set(capabilities["scenarios"])
    assert {"actor", "movement", "workseat", "pc", "speech", "bubble", "vfx", "humanball", "stamina", "portal", "persistence", "replay"} <= set(capabilities["channels"])

    payload = state.live_start(floor_id="floor00", include_runtime=False)
    assert payload["floor_id"] == "floor00"
    assert len(payload["actors"]) == 5
    assert payload["metrics"]["render_ms"] is not None
    assert payload["metrics"]["encode_ms"] is not None


def test_review_talk_demo_can_force_self_talk_mode():
    state = ReviewState()
    payload = state.demo_talk(
        floor_id="floor00",
        mode="self_talk",
        dialogue_locale="th",
        include_runtime=False,
    )

    speech = next(event for event in payload["events"] if event["type"] == "speech_session_started")
    assert speech["mode"] == "self_talk"
    assert len(speech["participants"]) == 1
    assert speech["dialogue_lines"]
    actor = next(row for row in payload["actors"] if row["employee_id"] == payload["demo_employee_id"])
    assert actor["speech_mode"] == "self_talk"
    assert actor["route_phase"] is None


def test_review_wander_demo_exposes_moving_frames_and_completes():
    state = ReviewState()
    payload = state.demo_wander(floor_id="floor02", include_runtime=False)
    actor_id = payload["demo_employee_id"]
    actor = next(row for row in payload["actors"] if row["employee_id"] == actor_id)
    assert actor["route_phase"] == "wander_out"
    assert actor["character_frame_count"] == 2

    saw_nonzero_frame = False
    for _ in range(30):
        payload = state.tick(60, include_runtime=False)
        actor = next(row for row in payload["actors"] if row["employee_id"] == actor_id)
        saw_nonzero_frame |= actor["character_frame_index"] > 0
        if payload["demo_complete"]:
            break
    assert saw_nonzero_frame
    assert payload["demo_complete"] is True


def test_review_critical_demo_restarts_from_a_valid_seated_state_and_completes():
    state = ReviewState()
    live = state.live_start(floor_id="floor02", include_runtime=False)
    actor_id = live["actors"][0]["employee_id"]

    # The button may be pressed while the live run has the selected actor on
    # an inbound route.  Critical must discard that transient display state
    # and construct a valid working/WorkSeat boundary of its own.
    payload = state.demo_critical(actor_id, floor_id="floor02", include_runtime=False)
    actor = next(row for row in payload["actors"] if row["employee_id"] == actor_id)
    assert payload["demo_kind"] == "critical"
    assert payload["demo_employee_id"] == actor_id
    assert actor["activity"] == "working"
    assert actor["presence"] == "present"
    assert actor["stamina_band"] == "critical"
    assert any(event["type"] == "home_queued" for event in payload["events"])

    for _ in range(70):
        payload = state.tick(360, autopilot=True, include_runtime=False)
        if payload["demo_complete"]:
            break

    actor = next(row for row in payload["actors"] if row["employee_id"] == actor_id)
    assert payload["demo_complete"] is True
    assert actor["activity"] == "home_recovery"
    assert actor["presence"] == "home"


def test_review_full_demo_starts_all_systems_with_normal_stamina():
    state = ReviewState()
    payload = state.full_demo(floor_id="floor02", include_runtime=False)

    assert payload["demo_kind"] == "full"
    assert "full normal system run" in payload["note"]
    assert payload["demo_complete"] is False
    assert payload["actors"]
    assert {actor["stamina_band"] for actor in payload["actors"]} == {"normal"}
    assert any(actor["route_phase"] in {"portal_entry", "to_workseat"} for actor in payload["actors"])


def test_review_live_ticks_remain_bounded_after_talk_plan_is_accepted():
    state = ReviewState()
    start = time.perf_counter()
    state.demo_talk(include_runtime=False)
    first_ms = (time.perf_counter() - start) * 1000
    durations = []
    for _ in range(24):
        tick_start = time.perf_counter()
        state.tick(60, include_runtime=False)
        durations.append((time.perf_counter() - tick_start) * 1000)

    # The first deterministic plan may pay the one-time catalog/geometry cost;
    # the repeating host slice must not reintroduce the old 0.5–1.1s stalls.
    assert first_ms < 1000
    assert max(durations) < 250


def test_persistence_replay_and_load_restore_their_snapshot_floor():
    state = ReviewState()
    state.live_start(floor_id="floor00", include_runtime=False)
    saved = state.save()
    state.live_start(floor_id="floor02", include_runtime=False)

    loaded = state.load(saved["runtime_snapshot"])
    assert loaded["floor_id"] == "floor00"
    replayed = state.replay(json.loads(saved["replay_json"]))
    assert replayed["floor_id"] == "floor00"
