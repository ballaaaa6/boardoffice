# Non-blocking Speech Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep WorkSeat animation, stamina drain and persistent work-loop phase advancing while in-work speech bubbles are painted, without changing routed conversation behavior.

**Architecture:** Reuse `start_talk_session` as the Central commit boundary, but classify its payload by whether a physical outbound route exists. No-route sessions remain `present/working` with explicit `behavior.talk.route_committed=false`; routed sessions retain the current `talking` route state. Presentation copies dialogue from SpeechScheduler and uses the actor work clock for stationary overlays.

**Tech Stack:** Python 3, JSON Schema Draft 2020-12, pytest, Pillow-based runtime renderer, the existing Python review server on port 8765.

**Spec:** `docs/superpowers/specs/2026-09-02-nonblocking-speech-overlay-design.md`

## Global Constraints

- Work from `D:\antigravity\board office`; the unpacked project root is the source of truth.
- Do not edit `00_STARTING_POINT/` or create a second project root.
- Preserve static world/character assets and their reference hashes.
- Keep the fixed simulation cadence at 60 ms and all timestamps integer milliseconds.
- Keep standing-pair `v` alignment, four-cell `u` gap, lower-`u` `SW`, higher-`u` `NE`, opener `[0, -20]`, reply `[0, 0]`, persisted d6 and 240 ms seat-entry behavior unchanged.
- Use `apply_patch` for source/document edits and do not revert unrelated user changes in the dirty worktree.
- Use TDD: every production behavior change must have a regression test that fails before the implementation and passes afterward.
- Reuse the healthy project server at `127.0.0.1:8765`; do not start a duplicate listener.

---

### Task 1: Add failing actor/runtime regressions

**Files:**
- Modify: `D:\antigravity\board office\TESTS\test_talk_runtime.py`
- Modify: `D:\antigravity\board office\TESTS\test_runtime_presentation_renderer.py`

**Interfaces:**
- Consume the existing `CentralGameCore.advance_runtime_snapshot()` and `resolve_runtime_presentation()` APIs.
- Produce executable regression tests for self-talk, seated host, routed talk return and stationary frame ownership.

- [x] **Step 1: Add a self-talk clock regression.**

Create a quiet runtime fixture using the existing test helper pattern, force a self-talk fallback, advance through the active bubble in 60 ms slices, and assert that the actor remains `working`, has no route, and has a changing `work_loop_elapsed_ms`.

```python
def test_stationary_self_talk_keeps_working_clock_and_stamina_running():
    core, runtime = _quiet_runtime()
    initiator = INITIATOR
    for employee_id, speech_actor in runtime["speech_snapshot"]["actors"].items():
        if employee_id != initiator:
            speech_actor["speech_phase"] = "active"
    actor = runtime["actor_snapshot"]["actors"][initiator]
    actor["behavior"]["next_event_due_ms"] = 0
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"

    current = core.advance_runtime_snapshot(runtime, 60)
    started = next(
        event for event in current["speech_events"]
        if event["type"] == "speech_session_started" and event["mode"] == "self_talk"
    )
    before_stamina = current["actor_snapshot"]["actors"][initiator]["stamina"]["current_milli"]
    phases = []
    for _ in range(8):
        row = current["actor_snapshot"]["actors"][initiator]
        phases.append(row["behavior"]["work_loop_elapsed_ms"])
        assert row["activity"] == "working"
        assert row["position"]["route"] is None
        current = core.advance_runtime_snapshot(current, 60)

    final = current["actor_snapshot"]["actors"][initiator]
    assert max(phases) > min(phases)
    assert final["stamina"]["current_milli"] < before_stamina
    assert started["fade_end_ms"] > 0
```

- [x] **Step 2: Add a stationary host presentation regression.**

Extend the existing mode-parametrized renderer test with a host assertion that the stationary host stays `working`, keeps `work_seat`, and gets a frame index derived from the actor work clock rather than a pinned zero frame.

```python
def test_stationary_seated_host_uses_actor_work_clock_for_turn_side_frames():
    core = CentralGameCore(ROOT)
    runtime = _quiet_runtime(core)
    first_employee, second_employee, _ceo = _ids(core)
    initiator, host = first_employee, second_employee

    core.speech_scheduler._mode_request = lambda _snapshot, initiator_id, *, counter: {
        "kind": "pair", "initiator_id": initiator_id, "partner_id": host,
        "participants": [initiator_id, host], "mode": "seated_host",
        "category": "conversation_open",
        "dialogue_categories": ["conversation_open", "conversation_reply"],
    } if initiator_id == initiator else None
    core.actor_simulation.choose_behavior_event = lambda *args, **kwargs: "talk"
    runtime["actor_snapshot"]["actors"][initiator]["behavior"]["next_event_due_ms"] = 0

    current = core.advance_runtime_snapshot(runtime, 60)
    frames = []
    for _ in range(10):
        host_actor = current["actor_snapshot"]["actors"][host]
        host_row = core.resolve_runtime_presentation(current, floor_id="floor02", validate=False)["actors"][host]
        assert host_actor["activity"] == "working"
        assert host_actor["position"]["route"] is None
        assert host_row["render_owner"] == "work_seat"
        assert host_row["action"] == "work"
        frames.append(host_row["character_frame_index"])
        current = core.advance_runtime_snapshot(current, 60)
    assert len(set(frames)) == 2
```

- [x] **Step 3: Add the post-return no-reset regression.**

Capture the work-loop phase before a routed talk, advance until the actor returns to its WorkSeat, and assert that the final actor still has a non-reset phase or has continued through a normal-work tick instead of being forced to frame zero.

- [x] **Step 4: Run only the new tests and verify RED.**

Run:

```powershell
python -m pytest -q TESTS/test_talk_runtime.py TESTS/test_runtime_presentation_renderer.py
```

Expected: the new stationary tests fail because the actor is currently `talking`, the work clock is zero, or the host frame is plan-owned. Existing tests may pass; do not proceed until the new assertions fail for the diagnosed reason rather than a fixture error.

### Task 2: Implement route-aware actor state and preserve Talk work phase

**Files:**
- Modify: `D:\antigravity\board office\RUNTIME\actor_simulation_core.py:1894-2140, 2564-2688, 2810-3073, 3080-3165`
- Modify: `D:\antigravity\board office\SCHEMA\actor_snapshot.schema.json:414-603`
- Modify: `D:\antigravity\board office\SCHEMA\actor_simulation.schema.json:356-614`
- Modify: `D:\antigravity\board office\CONTRACTS\actor_simulation.json:190-262`

**Interfaces:**
- Consume `start_talk_session` commands with optional `route_info`.
- Produce `behavior.talk.route_committed`, legal `working` stationary overlay states, progressing work clocks and unchanged routed talk events.

- [x] **Step 1: Add the optional schema marker and canonical migration.**

Allow `route_committed` inside the talk object. In `_canonical_snapshot`, derive the value for old snapshots from whether `outbound_path_cells_uv` is non-empty. Keep the field optional at the JSON Schema boundary so old saved snapshots validate before canonicalization.

- [x] **Step 2: Add validator invariants for stationary overlays.**

Accept `activity == "working"` with a talk object only when the talk has no route, the actor has no position route or seat transition, `conversation_phase` is null, `next_event_due_ms` is null, and `active_event` is either null or `talk`. Reject stationary overlays with a route and reject non-talk active events.

- [x] **Step 3: Change `_start_talk_session` only after route parsing.**

Set `route_committed = outbound is not None` in the metadata. For `route_committed == false`, retain `presence == "present"` and `activity == "working"`, leave the WorkSeat position untouched, clear `conversation_phase`, set `activity_until_ms` to null, and keep `next_event_due_ms` null. Do not increment the event counter a second time when accepting the actor's existing pending Talk request.

- [x] **Step 4: Advance stationary overlays through the work branch.**

Before normal working-event selection, detect a no-route talk record. Drain work only until `talk.return_start_at_ms`, preserve critical-home pending state, clear the talk record at the boundary, and then resume normal event selection. Use the existing `_finish_talk_actor` completion event and do not allow a second weighted event inside the active overlay.

- [x] **Step 5: Preserve the work clock on Talk completion.**

Remove the Talk-specific reset of `work_loop_elapsed_ms` and `work_loop_count` in `_finish_talk_actor` and `_complete_event`. Keep the reset behavior for other mobile/recovery events. The Talk recovery owner still receives the existing recovery amount and cooldown.

- [x] **Step 6: Run the focused tests and verify GREEN.**

Run:

```powershell
python -m pytest -q TESTS/test_talk_runtime.py TESTS/test_runtime_presentation_renderer.py
```

Expected: the new stationary actor tests and existing routed-talk tests pass. If a failure involves schema state, fix the validator/migration before touching the presentation layer.

### Task 3: Make Central and presentation respect the two talk authorities

**Files:**
- Modify: `D:\antigravity\board office\RUNTIME\central_core.py:1382-1557, 2180-2385`
- Modify: `D:\antigravity\board office\CONTRACTS\central_contract.json:72-87`
- Modify: `D:\antigravity\board office\CONTRACTS\runtime_presentation.json:23-46`
- Modify: `D:\antigravity\board office\CONTRACTS\speech_scheduler.json:140-157`
- Modify: `D:\antigravity\board office\SCHEMA\speech_scheduler.schema.json:126-146`
- Modify: `D:\antigravity\board office\CONTRACTS\conversation_behavior.json`
- Modify: `D:\antigravity\board office\SCHEMA\conversation_behavior.schema.json`

**Interfaces:**
- Consume actor `behavior.talk.route_committed` and the existing conversation plan tracks.
- Produce stationary WorkSeat rows with dialogue overlays and actor-clock frames; routed rows retain actor-authoritative motion.

- [x] **Step 1: Mark the bridge payload route explicitly.**

In `_talk_commands_from_speech_events`, pass `route_committed` based on the participant's route payload while retaining `route_info` only for routed participants. Do not change session timing, dialogue selection or emotion handling.

- [x] **Step 2: Split presentation keys for stationary and routed actors.**

For a no-route actor that remains working, copy dialogue metadata and the authored stationary action/subaction/direction only. Keep baseline WorkSeat ownership and coordinates. Recompute `frame_index` using `behavior.work_loop_elapsed_ms // 360` and the row's resolved frame count. For any actor with an active route or seat transition, retain the existing route-authoritative key set.

- [x] **Step 3: Preserve plan metadata without making its frame authoritative.**

Keep `speech_session_id`, `speech_mode`, `speech_category`, bubble schedule, speaker order and offsets. Clarify the conversation contract that timeline frame values are for route/preview tracks, while stationary runtime frame ownership belongs to the actor snapshot.

- [x] **Step 4: Add Central-level regressions.**

Add tests for `self_talk`, `ceo_front` host, `seated_host` host and routed visitor. Assert that presentation remains pure, dialogue is visible at the scheduler boundary, and routed standing pairs still expose the planned `SW`/`NE` hold directions.

- [x] **Step 5: Run Central/presentation focused tests.**

Run:

```powershell
python -m pytest -q TESTS/test_talk_runtime.py TESTS/test_runtime_presentation_renderer.py TESTS/test_speech_scheduler.py TESTS/test_conversation_behavior.py
```

Expected: all focused tests pass, including existing d6, bubble offset, geometry, route, return and timeline tests.

### Task 4: Fix review-host cleanup validation

**Files:**
- Modify: `D:\antigravity\board office\TOOLS\runtime_review_server.py:850-930`
- Modify: `D:\antigravity\board office\WEB\runtime_review.html:305-330`
- Test: `D:\antigravity\board office\TESTS\test_runtime_review_server.py`

**Interfaces:**
- Consume the existing review demo suppression path.
- Produce valid compact and non-compact runtime payloads after routine sessions are removed.

- [x] **Step 1: Add a failing cleanup test.**

Run the existing Talk demo with `include_runtime=True` and assert that no lane points to a deleted session. If the current fixture raises before returning, capture that as the expected RED failure.

- [x] **Step 2: Clear removed session lane pointers.**

When `_suppress_demo_routine_speech` removes a routine session, set any `lane.active_session_id` and `lane.active_until_ms` that reference it to `None`. Preserve `last_completed_session_id` only when it still names a retained session.

- [x] **Step 3: Keep manual tick payload options consistent.**

Make manual web ticks request the same compact runtime shape as the live loop so the review page does not take the known non-compact path accidentally.

- [x] **Step 4: Run review-host tests.**

Run:

```powershell
python -m pytest -q TESTS/test_runtime_review_server.py
```

Expected: Talk demo, self-talk demo and cleanup tests pass without `lane points at unknown session`.

### Task 5: Full verification and browser acceptance gate

**Files:**
- Modify: `D:\antigravity\board office\HANDOFF.md`
- Modify: `D:\antigravity\board office\ROADMAP.md`

- [x] **Step 1: Run the complete test suite.**

```powershell
python -m pytest -q
```

Record the exact pass count and any failure output in `HANDOFF.md`.

- [x] **Step 2: Run required audits.**

```powershell
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_work_seat_lifecycle.py
python VALIDATION/self_audit_phase6.py
python VALIDATION/self_audit_central.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_conversation.py
python TOOLS/render_runtime_presentation_qa.py
```

Do not change world or asset inputs to make these audits pass.

- [x] **Step 3: Verify the exact project server lifecycle.**

Inspect port 8765 and the command line for PID 15408 before restarting. Stop and restart only that project process after source edits, confirm HTTP 200 from `http://127.0.0.1:8765/`, and leave the healthy server running for the user review. Do not terminate Codex-owned processes.

- [x] **Step 4: Inspect live mode traces.**

On the review page, exercise self-talk, `ceo_front`, `seated_host` and standing pair. Confirm active stationary rows keep changing work frames, post-return rows remain `work/normal_work` without a reset hold, routed visitors still walk, and standing-pair facings/offset/d6 remain correct.

- [x] **Step 5: Update handoff and roadmap.**

Replace `HANDOFF.md` with the current date, implementation summary, exact tests/audits, server status, acceptance-pending state and next gate. Mark only the new frame-stall item complete in `ROADMAP.md`; keep author visual/gameplay acceptance separate from engineering verification.
