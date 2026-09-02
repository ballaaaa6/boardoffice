# Conversation Runtime Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct standing-pair placement/facing, opener bubble spacing, shared post-talk d6 behavior, and the return-to-work presentation seam while preserving all existing assets and unrelated conversation modes.

**Architecture:** Keep `ConversationSpotCore` authoritative for valid UV endpoints, but add a standing-pair-specific facing order so global movement direction semantics remain unchanged. Let `SpeechSchedulerCore` own one persisted d6 sequence and pass its roll into the immutable conversation plan. Let the actor snapshot own live route/seat-transition pose at the presentation seam; speech timing and bubble metadata remain overlays.

**Tech Stack:** Python 3.10, existing JSON contracts/schemas, Pillow bubble renderer, existing CentralGameCore/ActorSimulationCore/SpeechSchedulerCore, pytest, and the existing local browser review server. No new external dependency and no asset rewrite.

**Spec:** `docs/superpowers/specs/2026-09-02-conversation-runtime-corrections-design.md`

## Global Constraints

- Treat `v` equal and `u` different as the standing-pair geometry requirement; do not silently reinterpret it as literal screen-`x` equality.
- Preserve the global `U+ -> SE`, `U- -> NW`, `V+ -> SW`, `V- -> NE` mapping; only the standing-pair endpoint facing policy changes.
- Keep the four-cell talk gap, reachable/open-ring/portal/between-desk checks, actor assignment ownership, and all static asset/reference hashes unchanged.
- Keep opener spacing role-based: `conversation_open`/first speaker gets additional `[0,-20]`; `conversation_reply` gets `[0,0]`; all non-standing-pair speech remains unchanged.
- Use one scheduler-owned persisted stateful d6 per completed standing pair; never roll in a renderer and never maintain a second independent emotion result.
- Treat `SEAT_TRANSITION_MS=240` as the exact visual boundary; a live `seat_entry` transition owns pose fields until it completes.
- Use test-first development: write each failing regression test, observe the failure, then implement the smallest change that makes it pass.
- Do not edit `00_STARTING_POINT/`, `WORLD/`, character assets, bubble crops, WorkSeat placement, navigation occupancy, or reference hashes.
- Run `python -m pytest -q` after runtime changes, plus the relevant validation scripts and browser smoke before recording acceptance.
- Leave acceptance-pending and author-approved states distinct in `HANDOFF.md`; do not close Phase 8E from test output alone.

---

### Task 1: Change the standing-pair coordinate and facing contract

**Files:**
- Modify: `CONTRACTS/conversation_behavior.json`
- Modify: `SCHEMA/conversation_behavior.schema.json`
- Modify: `RUNTIME/conversation_spot_core.py:301-395`
- Modify: `RUNTIME/conversation_behavior_core.py:1845-1853`
- Modify: `TESTS/test_conversation_behavior.py:31-80, 114-125`
- Modify: `VALIDATION/self_audit_conversation.py`

**Interfaces:**
- Preserve `ConversationSpotCore.resolve_standing_pair(...) -> dict[str, Any]`.
- Add contract fields under `coordinate_contract.standing_pair`: `preferred_axis="U"`, `fallback_axis="V"`, `endpoint_order="ascending_u"`, and `endpoint_facing_order=["SW", "NE"]`.
- Preserve `spot["endpoint_uv"]`, `spot["endpoint_facings"]`, `spot["endpoint_inverse"]`, `spot["axis"]`, and `spot["axis_delta_uv"]` as the downstream interface.

- [x] **Step 1: Write the failing contract and geometry tests**

Update the existing contract assertion and add explicit endpoint-order/facing assertions:

```python
def test_standing_pair_uses_equal_v_lower_u_sw_higher_u_ne():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    employee_ids = [
        employee_id for employee_id, actor in snapshot["actors"].items()
        if actor["role"] == "employee"
    ]
    plan = core.resolve_conversation_plan(
        employee_ids[0], partner_id=employee_ids[1], mode="standing_pair",
        snapshot=snapshot, talk_frames=2, origin_uvs=[],
    )
    first, second = [tuple(cell) for cell in plan["spot"]["endpoint_uv"]]
    assert plan["spot"]["axis"] == "U"
    assert first[1] == second[1]
    assert second[0] - first[0] == 4
    assert plan["spot"]["endpoint_facings"] == ["SW", "NE"]
    assert plan["spot"]["endpoint_inverse"] is True
```

- [x] **Step 2: Run the focused geometry test and observe the old behavior failure**

Run: `python -m pytest TESTS/test_conversation_behavior.py::test_standing_pair_uses_equal_v_lower_u_sw_higher_u_ne -q`

Expected: FAIL because the current plan selects `axis == "V"`, equal `u`, and different `v`.

- [x] **Step 3: Update the contract and schema without changing global axis semantics**

Change only the standing-pair values and formalize the new fields in the nested coordinate schema. Keep the global `axis_direction_convention` values unchanged. Add schema validation for `endpoint_order` and the two-item `endpoint_facing_order` so a future contract edit cannot silently change the requested pair order.

- [x] **Step 4: Implement pair-specific endpoint facing in `ConversationSpotCore`**

Read the new facing order from the standing-pair contract. Try `U` first, so each candidate is `(u, v)` followed by `(u+4, v)`. For the preferred standing-pair axis, return the contract’s `["SW", "NE"]` facing order instead of calling the global `_facing_for_delta()` mapping. For fallback `V` candidates, retain the existing signed-axis mapping. Keep endpoint reachability, blocked segment, open-ring, portal margin, relief, and between-furniture rejection identical.

- [x] **Step 5: Verify actor assignment uses endpoint order, not opener identity**

Keep `_pair_assignment()`’s existing actor ordering and make `facing_by_actor` consume `spot["endpoint_facings"]` at the same endpoint index. The opener/reply role must not determine which actor is lower or higher `u`; it only determines speaker timing and bubble offset in Task 2.

- [x] **Step 6: Run focused and all-floor geometry validation**

Run: `python -m pytest TESTS/test_conversation_behavior.py -q`

Run: `python VALIDATION/self_audit_conversation.py`

Expected: all conversation tests and the all-floor audit pass; every floor still has a reachable standing-pair slot and no assignment/occupancy mutation.

- [x] **Step 7: Review the diff before moving to bubble work**

Run: `git diff --check` and `git diff -- CONTRACTS/conversation_behavior.json SCHEMA/conversation_behavior.schema.json RUNTIME/conversation_spot_core.py RUNTIME/conversation_behavior_core.py TESTS/test_conversation_behavior.py VALIDATION/self_audit_conversation.py`.

Confirm that no `WORLD/`, `CHARACTER/`, `00_STARTING_POINT/`, WorkSeat, or global movement mapping file changed.

### Task 2: Apply opener-only bubble spacing in every renderer

**Files:**
- Modify: `CONTRACTS/conversation_behavior.json`
- Modify: `SCHEMA/conversation_behavior.schema.json`
- Modify: `RUNTIME/conversation_behavior_core.py:1863-1873, 1206-1229`
- Modify: `RUNTIME/central_core.py:321-344`
- Modify: `CHARACTER/RUNTIME/dialogue_bubble.py:460-504, 554-575`
- Modify: `RUNTIME/runtime_presentation_renderer.py:244-308`
- Modify: `TOOLS/render_conversation_pair_gif.py:120-155`
- Modify: `TESTS/test_conversation_behavior.py:202-230, 270-317`
- Modify: `TESTS/test_dialogue_bubble.py`
- Modify: `TESTS/test_runtime_presentation_renderer.py`

**Interfaces:**
- Extend `CentralGameCore.render_employee_dialogue_bubble(..., bubble_offset_px: Iterable[int] = (0, 0))`.
- Extend `DialogueBubbleRenderer.render_bubble(..., bubble_offset_px: Iterable[int] = (0, 0))` and `render_for_character(..., bubble_offset_px: Iterable[int] = (0, 0))`.
- Offset semantics: translate `bubble_top_left` and `bubble_tail_global` by the supplied pixel pair; keep `head_anchor` and `actor_top_left` tied to the actual actor.
- Preserve `dialogue_bubble_offset_px` in plan/state JSON so existing telemetry and callers remain compatible.

- [x] **Step 1: Write failing plan and renderer tests**

Add plan-level role assertions and a renderer-level translation assertion:

```python
def test_standing_pair_bubble_offset_belongs_to_opening_speaker():
    core = CentralGameCore(ROOT)
    snapshot = core.resolve_conversation_snapshot("floor02")
    employees = [
        employee_id for employee_id, actor in snapshot["actors"].items()
        if actor["role"] == "employee"
    ]
    plan = core.resolve_conversation_plan(
        employees[0], partner_id=employees[1], mode="standing_pair",
        snapshot=snapshot, origin_uvs=[],
    )
    opener, reply = plan["timing"]["speaker_sequence"]
    assert plan["bubble_offset_by_actor"][opener] == [0, -20]
    assert plan["bubble_offset_by_actor"][reply] == [0, 0]
```

```python
def test_bubble_offset_moves_box_and_tail_but_not_head_anchor():
    result = central.render_employee_dialogue_bubble(
        employee_id, frame_id, "hello", actor_top_left=(100, 100),
        bubble_offset_px=(0, -20),
    )
    base = central.render_employee_dialogue_bubble(
        employee_id, frame_id, "hello", actor_top_left=(100, 100),
    )
    assert result.head_anchor == base.head_anchor
    assert result.bubble_top_left == (base.bubble_top_left[0], base.bubble_top_left[1] - 20)
    assert result.bubble_tail_global == (base.bubble_tail_global[0], base.bubble_tail_global[1] - 20)
```

- [x] **Step 2: Run the focused tests and observe the missing spacing behavior**

Run: `python -m pytest TESTS/test_conversation_behavior.py::test_standing_pair_bubble_offset_belongs_to_opening_speaker TESTS/test_dialogue_bubble.py::test_bubble_offset_moves_box_and_tail_but_not_head_anchor -q`

Expected: the plan test fails because both offsets are `[0, 0]`; the renderer test fails because the bubble APIs do not accept/apply `bubble_offset_px`.

- [x] **Step 3: Add the explicit opener spacing policy to the conversation contract**

Store the additional pair-opener offset as `[0, -20]`, document that it is one extra copy of the registry’s current `vertical_offset_from_actor_frame_top_px` magnitude, and validate its two integer values. Do not change `CHARACTER/DIALOGUE/bubble_presets.json`; its existing `-20` base remains the reply position.

- [x] **Step 4: Compute offsets from speaker role in the conversation plan**

In `plan_conversation()`, use `timing_plan["speaker_sequence"][0]` as the opener. Build `bubble_offset_by_actor` only for `standing_pair` with two participants:

```python
bubble_offset_by_actor = {
    employee_id: ([0, -20] if employee_id == opening_speaker_id else [0, 0])
    for employee_id in endpoint_by_actor
}
```

Pass each actor’s own value through `_build_track()` and `_append_talk_states()` so invisible/listener states retain the same role metadata when the reply bubble starts.

- [x] **Step 5: Thread the offset through the bubble result and raster/GIF compositors**

Validate the two offset components, preserve the actual head anchor, and translate the bubble rectangle/tail in `DialogueBubbleRenderer`. Pass each presentation row’s `dialogue_bubble_offset_px` from `RuntimePresentationRenderer._paint_bubble()` into CentralGameCore. Apply the same offset in `ConversationPairGifRenderer._bubble_payload()`/draw path. Keep default `(0, 0)` for callers that do not provide an offset.

- [x] **Step 6: Add non-pair regression assertions and run focused tests**

Assert that `self_talk`, `ceo_front`, `seated_host`, lifecycle speech, and ordinary seated work dialogue all keep `[0, 0]`. Run:

`python -m pytest TESTS/test_conversation_behavior.py TESTS/test_dialogue_bubble.py TESTS/test_runtime_presentation_renderer.py -q`

Expected: all focused conversation, bubble, and raster tests pass, including GIF paint-order tests and head-anchor tests.

### Task 3: Replace hash parity with one persisted scheduler-owned d6

**Files:**
- Modify: `CONTRACTS/speech_scheduler.json`
- Modify: `CONTRACTS/conversation_behavior.json`
- Modify: `CONTRACTS/runtime_presentation.json`
- Modify: `SCHEMA/speech_scheduler_snapshot.schema.json`
- Modify: `SCHEMA/conversation_behavior.schema.json`
- Modify: `SCHEMA/runtime_presentation.schema.json`
- Modify: `RUNTIME/speech_scheduler_core.py:109-117, 277-346, 348-415, 884-957, 998-1112`
- Modify: `RUNTIME/conversation_behavior_core.py:1829-1843`
- Modify: `RUNTIME/central_core.py:1378-1412`
- Modify: `TESTS/test_speech_scheduler.py:138-175`
- Modify: `TESTS/test_conversation_behavior.py`

**Interfaces:**
- Add `SpeechSchedulerCore._next_emotion_d6(snapshot: dict[str, Any]) -> int`, which advances and persists the snapshot’s 64-bit PRNG state and returns an integer in `1..6`.
- Add optional `emotion_roll: int | None = None` to `ConversationBehaviorCore.plan_conversation()` and the CentralGameCore wrapper.
- Store `emotion_roll: int` and `emotion_outcome: Literal["sad", "happy"]` on standing-pair sessions; expose the same values in `emotion_started` and `conversation_plan["emotion"]`.
- Add optional `determinism.emotion_rng_state` to the speech snapshot schema and initialize/migrate it without invalidating old saved snapshots.

- [x] **Step 1: Write failing tests for one shared varying roll and plan/session agreement**

Extend the standing-pair scheduler test:

```python
assert 1 <= session["emotion_roll"] <= 6
assert session["emotion_outcome"] == (
    "happy" if session["emotion_roll"] % 2 == 0 else "sad"
)
assert session["conversation_plan"]["emotion"]["roll"] == session["emotion_roll"]
assert session["conversation_plan"]["emotion"]["outcome"] == session["emotion_outcome"]
```

Add a fixed-seed sequence test that starts multiple valid standing pairs without recreating the speech snapshot, records the session rolls, and asserts the sequence contains more than one value and more than one parity. Add a save/load/replay test that deep-copies a snapshot before a pair start and asserts both copies produce the same next roll and outcome.

- [x] **Step 2: Run the focused scheduler tests and observe the old hash behavior**

Run: `python -m pytest TESTS/test_speech_scheduler.py::test_standing_pair_emotion_roll_is_shared_and_replayable -q`

Expected: FAIL because `emotion_roll` is absent and the current scheduler stores only a hash-parity outcome. The current implementation may also disagree with the plan’s separate hash result.

- [x] **Step 3: Add and migrate the persisted PRNG state**

Initialize `determinism.emotion_rng_state` from the simulation seed using the existing stable integer helper only once. Use a documented 64-bit SplitMix-style next-state function (mask every operation to `2**64 - 1`), reject the incomplete final interval so `1..6` is uniform, then persist the next state before returning the roll. When an old snapshot lacks the field, derive its initial state from `simulation_seed` and `root_event_counter`, return the canonical copy, and leave all existing actor/lane/session fields intact.

- [x] **Step 4: Make the scheduler the only runtime roll owner**

Change `_maybe_plan_session()`/`_start_session()` so a valid standing-pair candidate receives exactly one roll at commit time. Do not consume the PRNG for rejected candidates. Pass that roll into the conversation planner, store it on the session, and emit it in the start/emotion events. Remove the scheduler’s `_stable_int(..., "emotion")` parity decision and remove the planner’s independent `_stable_dialogue_index(..., 6)` emotion decision.

- [x] **Step 5: Make standalone plan and preview behavior explicit**

When `emotion_roll` is supplied, validate `1 <= roll <= 6`, calculate the outcome, and build the emotion hold/return track from it. When it is omitted, keep the pure plan valid but leave the post-talk emotion fields absent rather than inventing a gameplay result. Update GIF/preview callers that need an emotion frame to pass a fixed explicit preview roll; they must not mutate a live scheduler snapshot.

- [x] **Step 6: Update contracts and schema ownership statements**

Change emotion descriptions from stable-hash parity to a scheduler-owned persisted d6 while retaining even=`happy`, odd=`sad`, one shared roll, 1200ms hold, and the existing stamina deltas. Add the optional PRNG field to the speech snapshot schema and the optional `emotion_roll` session/plan metadata validation. Keep schema IDs and JSON-safe persistence compatibility unchanged.

- [x] **Step 7: Run scheduler, persistence, and full regression tests**

Run:

`python -m pytest TESTS/test_speech_scheduler.py TESTS/test_conversation_behavior.py -q`

`python -m pytest -q`

Expected: the roll varies across consecutive live pair sessions, identical snapshot replays agree, plan/session/event outcomes agree, old snapshots validate/migrate, and the full suite remains green.

### Task 4: Make `seat_entry` the authoritative return pose

**Files:**
- Modify: `CONTRACTS/runtime_presentation.json`
- Modify: `SCHEMA/runtime_presentation.schema.json`
- Modify: `RUNTIME/central_core.py:1812-2000, 2168-2265`
- Modify: `RUNTIME/actor_simulation_core.py:481-516, 596-655, 1893-1953`
- Modify: `TESTS/test_runtime_presentation_renderer.py:260-320`
- Modify: `TESTS/test_talk_runtime.py`

**Interfaces:**
- Preserve `CentralGameCore.resolve_runtime_presentation(...)` output keys.
- Define `authoritative_motion = authoritative_route or authoritative_seat_transition` for pose selection.
- Continue copying conversation presentation keys (`dialogue_*`, speaker/listener/turn metadata) during a transition, but do not copy conversation plan pose keys while a route or seat transition is live.
- Preserve `ActorSimulationCore._finish_talk_actor()` as the owner of final `activity="working"`, talk cleanup, and next work event scheduling.

- [x] **Step 1: Write a failing transition-boundary regression test**

Force a standing pair, advance through the shared fade/emotion window, and sample the first actor at its return gate:

```python
row = presentation["actors"][employee_id]
assert row["presentation_transition"]["phase"] == "seat_entry"
assert row["render_owner"] == "walking_depth"
assert row["action"] == "move"
assert row["subaction"] == "idle"
assert row["activity"] in {"talking", "working"}
```

Then advance exactly `core.actor_simulation.SEAT_TRANSITION_MS` and assert:

```python
row = completed_presentation["actors"][employee_id]
assert row["render_owner"] == "work_seat"
assert row["action"] == "work"
assert row["subaction"] == "normal_work"
assert completed_actor["behavior"]["talk"] is None
```

- [x] **Step 2: Run the boundary test and observe stale-plan or transition-pose failure**

Run: `python -m pytest TESTS/test_runtime_presentation_renderer.py::test_standing_pair_return_keeps_live_seat_entry_pose_until_normal_work -q`

Expected: FAIL because the current condition copies `pose_keys` whenever talk metadata exists but the route has already been cleared, allowing the stale plan row to overwrite the live `seat_entry` row.

- [x] **Step 3: Update the presentation ownership condition**

In `resolve_runtime_presentation()`, detect `source_actor["position"]["seat_transition"]` as `authoritative_seat_transition`. Replace the route-only exception with the combined motion check so pose keys are copied from the plan only when no live route and no live seat transition are present. Keep `presentation_keys` copy behavior unchanged so bubble timing, opacity, dialogue text, and role metadata remain synchronized.

- [x] **Step 4: Verify the actor reducer’s 240ms completion path**

Use the existing `_advance_seat_entry_transition()` and `_finish_seat_transition()` flow. Confirm that `talk_return` invokes `_finish_talk_actor()`, which clears the position route, clears talk metadata, sets `activity="working"`, resets the work-loop counters, and schedules the next event. Do not add a second completion path or mutate WorkSeat assignment ownership.

- [x] **Step 5: Add the plan-ended-before-transition case**

Add a test where the presentation plan has reached its final timeline row before the actor’s 240ms `seat_entry` completes. Assert the row remains the live `walking_depth/move/idle` transition instead of either a stale `work/normal_work` plan frame or an invalid seated row. Assert the final sample after completion is `work_seat/work/normal_work`.

- [x] **Step 6: Run focused return and renderer tests**

Run: `python -m pytest TESTS/test_runtime_presentation_renderer.py TESTS/test_talk_runtime.py -q`

Expected: the return seam, actor cleanup, WorkSeat ownership, emotion overlay, and existing critical-work-loop tests all pass.

### Task 5: Full integration audit, visual acceptance, and handoff

**Files:**
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md` only if the milestone acceptance/status actually changes after user review
- Review only: `00_STARTING_POINT/`, `WORLD/`, `CHARACTER/`, `VALIDATION/work_seat_floor_reference_hashes.json`

**Interfaces:**
- No new runtime interface. The delivered behavior is the combination of the existing `CentralGameCore`, scheduler, actor reducer, and raster renderer interfaces updated in Tasks 1–4.

- [x] **Step 1: Run the complete focused conversation matrix**

Run:

`python -m pytest TESTS/test_conversation_behavior.py TESTS/test_dialogue_bubble.py TESTS/test_speech_scheduler.py TESTS/test_runtime_presentation_renderer.py TESTS/test_talk_runtime.py -q`

Expected: all relevant tests pass, including geometry, bubble offsets, d6 persistence/replay, and the 240ms return seam.

- [x] **Step 2: Run the required project audits**

Run:

`python -m pytest -q`

`python VALIDATION/self_audit_room_navigation.py`

`python VALIDATION/self_audit_navigation_occupancy.py`

`python VALIDATION/self_audit_work_seat.py`

`python VALIDATION/self_audit_work_seat_lifecycle.py`

`python VALIDATION/self_audit_phase6.py`

`python VALIDATION/self_audit_central.py`

`python VALIDATION/self_audit_gameplay_metadata_family.py`

`python VALIDATION/self_audit_conversation.py`

Expected: all audits pass; no materialized occupancy cache, generated preview, or release artifact is added to the package.

- [x] **Step 3: Run the existing browser/GIF visual checks using the current project server**

Before starting anything, inspect listeners and process command lines for port 8765. Reuse the healthy project server already running there; do not start a second server. Review a standing pair on floor02 and verify:

1. both actors stop on equal-`v`/different-`u` endpoints;
2. lower `u` visibly uses SW and higher `u` visibly uses NE;
3. the opener’s bubble is one extra 20px base head-distance above the reply and the reply remains at the normal offset;
4. repeated live pair sessions show both `happy` and `sad` over a sequence of sessions, with telemetry roll values `1..6`;
5. return samples show live `seat_entry` motion for 240ms and then animated `normal_work`, not a frozen stale plan pose.

Use the existing `TOOLS/render_conversation_pair_gif.py` and browser review controls for visual evidence. Do not stop PID 2772 or any Codex-owned process; stop only a process created by this task, and only if one was actually started.

- [x] **Step 4: Update current-state documentation without falsely closing acceptance**

Record exact test/audit commands and results in `HANDOFF.md`. If the user has not yet reviewed the browser result, write `acceptance-pending`; change it to `author-approved` only after explicit confirmation. Update `ROADMAP.md` only if the accepted scope or milestone status changes.

- [x] **Step 5: Package hygiene check**

Run `git diff --check`, inspect `git status --short`, and verify no source/reference asset hashes changed. Do not create a release archive for this correction until the visual/gameplay acceptance gate is explicitly approved.

## Plan self-review

- Geometry requirement maps to Task 1; opener spacing maps to Task 2; d6 ownership/persistence maps to Task 3; return-to-work seam maps to Task 4; acceptance and release hygiene map to Task 5.
- The plan intentionally leaves global axis mappings and all assets untouched.
- The plan distinguishes a role-based opener from endpoint order, so changing which employee is the initiator cannot swap the requested far/near facing policy.
- The plan removes both independent hash emotion decisions and names the scheduler session as the single runtime source of truth.
- The plan tests the exact 240ms transition boundary, including the case where the timeline ends before the visual transition.
- Implementation was authorized inline by the user; code, tests, audits, and browser review are complete, with author visual/gameplay acceptance still pending.
