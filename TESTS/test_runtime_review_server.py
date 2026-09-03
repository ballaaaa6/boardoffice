from __future__ import annotations

import json
import time

from TOOLS.runtime_review_server import ReviewState


def test_canvas_payload_is_image_free_and_does_not_call_raster_encoder(monkeypatch):
    state = ReviewState()

    def fail_encode(*args, **kwargs):
        raise AssertionError("canvas payload must not encode a raster")

    monkeypatch.setattr(type(state), "_image_data_url", staticmethod(fail_encode))
    payload = state.current(renderer="canvas", include_runtime=False)

    assert payload["renderer"] == "canvas"
    assert payload["render_state"]["schema"] == "gds.runtime_render_state.v1"
    assert "image_data_url" not in payload
    assert payload["metrics"]["encode_ms"] == 0.0


def test_raster_payload_remains_available_as_explicit_fallback():
    state = ReviewState()
    payload = state.current(renderer="raster", include_runtime=False)

    assert payload["renderer"] == "raster"
    assert payload["image_data_url"].startswith("data:image/")


def test_canvas_tick_does_not_call_full_frame_renderer(monkeypatch):
    state = ReviewState()

    def fail_render(*args, **kwargs):
        raise AssertionError("canvas tick must not render a full frame")

    monkeypatch.setattr(
        "RUNTIME.runtime_presentation_renderer.RuntimePresentationRenderer.render_runtime_snapshot",
        fail_render,
    )
    payload = state.tick(60, renderer="canvas", include_runtime=False)

    assert payload["renderer"] == "canvas"
    assert payload["render_state"]["clock_ms"] == 60


def test_canvas_request_does_not_call_pillow_character_effect_or_workseat_renderers(monkeypatch):
    state = ReviewState()

    def fail_render(*args, **kwargs):
        raise AssertionError("canvas request must stay metadata-only")

    for target in (state.core.characters, state.core, state.core.work_seats):
        for name in (
            "render",
            "render_effect",
            "render_humanball",
            "render_floor_with_work",
            "render_floor_with_work_effects",
        ):
            if hasattr(target, name):
                monkeypatch.setattr(target, name, fail_render)

    payload = state.demo_effects(renderer="canvas", include_runtime=False)

    assert payload["renderer"] == "canvas"
    assert payload["render_state"]["schema"] == "gds.runtime_render_state.v1"
    assert "image_data_url" not in payload


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
    participant_ids = {
        str(event["employee_id"])
        for event in all_events
        if event.get("type") == "talk_session_accepted"
        and event.get("session_id") == payload["demo_session_id"]
    }
    assert participant_ids
    for participant_id in participant_ids:
        actor = next(row for row in payload["actors"] if row["employee_id"] == participant_id)
        assert actor["activity"] == "working"
        assert actor["action"] == "work"
        assert actor["subaction"] == "normal_work"
        assert actor["render_owner"] == "work_seat"
        assert actor["route_phase"] is None
        assert actor["presentation_transition"] is None


def test_review_talk_demo_noncompact_ticks_keep_speech_lane_references_valid():
    state = ReviewState()
    payload = state.demo_talk(include_runtime=True)

    for _ in range(60):
        payload = state.tick(360, include_runtime=True)
        if payload["demo_complete"]:
            break

    assert payload["demo_complete"] is True
    assert payload["runtime_snapshot"]["speech_snapshot"]["lanes"]


def test_review_standing_pair_demo_waits_for_both_normal_work_poses():
    state = ReviewState()
    payload = state.demo_talk(
        floor_id="floor02",
        mode="standing_pair",
        include_runtime=False,
    )
    session_id = payload["demo_session_id"]
    participant_ids = {
        str(event["employee_id"])
        for event in payload["events"]
        if event.get("type") == "talk_session_accepted"
        and event.get("session_id") == session_id
    }
    assert len(participant_ids) == 2

    for _ in range(120):
        payload = state.tick(360, include_runtime=False)
        if payload["demo_complete"]:
            break

    assert payload["demo_complete"] is True
    for participant_id in participant_ids:
        actor = next(row for row in payload["actors"] if row["employee_id"] == participant_id)
        assert actor["activity"] == "working"
        assert actor["action"] == "work"
        assert actor["subaction"] == "normal_work"
        assert actor["render_owner"] == "work_seat"
        assert actor["route_phase"] is None
        assert actor["presentation_transition"] is None


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


def test_compact_event_stream_preserves_standing_pair_emotion_roll():
    events = [{
        "source": "speech",
        "event_index": 1,
        "timestamp_ms": 4300,
        "employee_id": "EMP_W1_0010",
        "type": "emotion_started",
        "emotion": "happy",
        "emotion_roll": 6,
    }]

    compact = ReviewState._compact_events(events)

    assert compact[0]["emotion_roll"] == 6


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


def test_review_live_start_defaults_every_actor_to_normal_stamina():
    state = ReviewState()
    payload = state.live_start(floor_id="floor02", include_runtime=False)

    assert payload["actors"]
    assert {actor["stamina"] for actor in payload["actors"]} == {100.0}
    assert {actor["stamina_band"] for actor in payload["actors"]} == {"normal"}


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


def test_review_actor_rows_expose_the_speech_queue_reason():
    state = ReviewState()
    state.full_demo(floor_id="floor02", include_runtime=True)
    runtime = state.adapter.loop._runtime_snapshot
    actor_id = sorted(runtime["actor_snapshot"]["actors"])[0]
    runtime["speech_snapshot"]["lanes"]["floor02"].update({
        "queued_session_ids": [actor_id],
        "queued_requests": [{
            "request_id": f"speech-request:{actor_id}:greeting",
            "initiator_id": actor_id,
            "kind": "lifecycle",
            "category": "greeting",
            "mode": "self_talk",
            "participants": [actor_id],
            "due_ms": 2400,
            "external": False,
        }],
    })

    payload = state.current(include_runtime=True)
    row = next(item for item in payload["actors"] if item["employee_id"] == actor_id)

    assert row["speech_queue_position"] == 1
    assert row["speech_queue_category"] == "greeting"
    assert row["speech_queue_request_id"].startswith("speech-request:")


def test_review_behavior_arming_skips_a_stationary_speech_participant():
    state = ReviewState()
    state.demo_talk(
        floor_id="floor02",
        mode="seated_host",
        include_runtime=True,
        dialogue_seed="stationary-arming",
    )
    runtime = state.adapter.loop._runtime_snapshot
    host_id = next(
        employee_id
        for employee_id, actor in runtime["actor_snapshot"]["actors"].items()
        if (actor["behavior"].get("talk") or {}).get("route_committed") is False
        and (actor["behavior"].get("talk") or {}).get("role") == "participant"
    )
    host = runtime["actor_snapshot"]["actors"][host_id]
    state._behavior_arming_enabled = True
    state._live_behavior_armed = set()

    state._arm_live_behavior_timers()

    assert host["behavior"]["next_event_due_ms"] is None


def test_full_live_lifecycle_bubbles_follow_their_actor_boundaries():
    state = ReviewState()
    payload = state.full_demo(
        floor_id="floor02",
        include_runtime=False,
        dialogue_seed="lifecycle-boundaries",
    )
    events = list(payload["events"])
    # Let the deterministic actor-slot queue drain without rendering 1,700
    # separate browser frames; the actor-level 60 ms tests cover per-frame
    # progress.
    for _ in range(300):
        payload = state.tick(
            360,
            autopilot=True,
            include_runtime=False,
            dialogue_seed="lifecycle-boundaries",
        )
        events.extend(payload["events"])

    actor_entries = {
        event["employee_id"]: int(event["timestamp_ms"])
        for event in events
        if event.get("source") == "actor"
        and event.get("type") == "workseat_reentered"
    }
    portal_entries = {
        event["employee_id"]: int(event["timestamp_ms"])
        for event in events
        if event.get("source") == "actor"
        and event.get("type") == "portal_entered"
    }
    work_start_bubbles = {}
    greeting_bubble_times = {}
    for event in events:
        if event.get("source") != "speech" or event.get("type") != "speech_bubble_started":
            continue
        employee_id = event.get("employee_id")
        if not isinstance(employee_id, str):
            continue
        timestamp_ms = int(event["timestamp_ms"])
        if event.get("category") == "work_start":
            work_start_bubbles[employee_id] = min(
                timestamp_ms,
                int(work_start_bubbles.get(employee_id, timestamp_ms)),
            )
        elif event.get("category") == "greeting":
            greeting_bubble_times[employee_id] = min(
                timestamp_ms,
                int(greeting_bubble_times.get(employee_id, timestamp_ms)),
            )
    greeting_bubbles = {
        employee_id for employee_id in greeting_bubble_times
    }

    assert actor_entries
    assert set(portal_entries) <= set(greeting_bubbles)
    assert all(
        greeting_bubble_times[employee_id] >= portal_entries[employee_id]
        for employee_id in portal_entries
    )
    assert set(actor_entries) <= set(work_start_bubbles)
    assert all(
        work_start_bubbles[employee_id] >= entry_ms
        for employee_id, entry_ms in actor_entries.items()
    )
    assert set(actor_entries) <= greeting_bubbles


def test_noncompact_full_live_ticks_do_not_schedule_over_stationary_talk_overlay():
    state = ReviewState()
    state.full_demo(
        floor_id="floor02",
        include_runtime=True,
        dialogue_seed="stationary-overlay-timers",
    )
    pending_samples = {}

    for _ in range(420):
        payload = state.tick(
            60,
            autopilot=True,
            include_runtime=True,
            dialogue_seed="stationary-overlay-timers",
        )
        for actor in payload["runtime_snapshot"]["actor_snapshot"]["actors"].values():
            if (
                actor["activity"] == "talking"
                and actor["conversation_phase"] == "talk_pending"
                and actor["behavior"].get("talk") is None
            ):
                samples = pending_samples.setdefault(actor["employee_id"], [])
                samples.append((
                    int(actor["behavior"]["work_loop_elapsed_ms"]),
                    int(actor["stamina"]["current_milli"]),
                ))

    assert len(pending_samples) >= 3
    assert sum(
        len({loop_ms for loop_ms, _stamina in samples}) > 1
        for samples in pending_samples.values()
    ) >= 3
    assert all(samples[-1][1] < samples[0][1] for samples in pending_samples.values())


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
