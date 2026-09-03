# Deterministic Visual Selection and Per-Actor Bubble Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Replace hash-modulo visual selection and floor-wide speech serialization with deterministic per-actor visual bags and per-actor speech slots while preserving physical conversation safety and Python/Browser parity.

**Architecture:** Add one focused Python visual-selection core and one mirrored Browser JS selector. Store only generation/cursor/active binding in actor state, derive permutations from the existing SHA-256/stableHash64 contract, and source both pools from generated registry data. Upgrade the speech snapshot to v2 with actor bubble slots, pending requests and resource claims; keep `ConversationBehaviorCore`/`ConversationSpotCore` as the physical-plan boundary and make Python/Browser admission scan candidates without a floor mutex.

**Tech Stack:** Python 3, `jsonschema`, pytest, ES modules, Node’s built-in test runner, deterministic JSON bundle generation, existing Canvas/Raster review server.

**Spec:** `docs/superpowers/specs/2026-09-03-visual-selection-bubble-concurrency-design.md`

## Global Constraints

- Python remains the gameplay oracle for this implementation slice.
- The automatic VFX pool is exactly the registry `effect_order` with 11 IDs; the automatic HumanBall pool is exactly `humanball_order` with 6 IDs.
- The bubble set remains `BB1`, `BB2`, `BB3`, `BB4`, `BB6`; `BB5` stays excluded and selection remains `smallest_allowed_fit`.
- A different actor on the same floor may run a speech session concurrently; the same actor may not overlap two sessions.
- Pair admission must claim both actor slots atomically and must pass the physical talk-spot/path/crowd resource checks.
- No visual event may call `fetch`, `/api/tick` or an asset endpoint.
- Do not edit `00_STARTING_POINT/`, static world/character assets, authored geometry or reference hashes.
- The checkout already contains approved dirty cleanup changes. Do not reset, stash, stage or commit unrelated changes; use narrowly scoped patches and file-specific staging.
- Do not start a second review server. Reuse healthy project PID `11232` on `http://127.0.0.1:8765/` and stop no process owned by the user or Codex.

---

## File map before implementation

| File | Responsibility in this plan |
| --- | --- |
| `RUNTIME/visual_selection_core.py` | Python catalog validation, catalog profile hash, compact bag state, stable permutation and active visual binding. |
| `RUNTIME/actor_simulation_core.py` | Initialize, migrate, validate and consume actor visual channel state at event admission/completion. |
| `SCHEMA/actor_snapshot.schema.json` | Persisted actor visual state contract. |
| `CONTRACTS/actor_simulation.json` | Actor snapshot contract/version notes for visual selection. |
| `WEB/runtime_simulation_visual_selection.js` | Browser mirror of the Python bag algorithm and active binding helpers. |
| `WEB/runtime_simulation_effects.js` | Resolve only persisted active bindings; no selection during rendering. |
| `WEB/runtime_simulation_actor.js` | Initialize/migrate browser visual state and consume/clear bindings at event boundaries. |
| `WEB/runtime_simulation_state.js` | Validate the new actor state fields and speech v2 shape. |
| `RUNTIME/browser_bundle_contract.py` | Validate and expose generated visual catalog/profile in the bundle. |
| `TOOLS/build_runtime_simulation_bundle.py` | Generate the visual catalog from canonical registries. |
| `WEB/runtime_simulation_speech.js` | Browser v2 actor-slot admission and v1 migration mirror. |
| `RUNTIME/speech_scheduler_core.py` | Python v2 speech state, migration, candidate scan, actor slots and resource claims. |
| `CONTRACTS/speech_scheduler.json` | Canonical speech v2 timing/ownership contract. |
| `SCHEMA/speech_scheduler.schema.json` | Canonical speech v2 snapshot schema. |
| `SCHEMA/speech_scheduler_snapshot.schema.json` | Canonical persisted speech v2 schema used by the runtime validator. |
| `RUNTIME/conversation_behavior_core.py` | Expose deterministic physical claim data to speech admission without widening the floor gate. |
| `RUNTIME/conversation_spot_core.py` | Preserve blocked/reserved cell inputs and candidate-specific conflict reporting. |
| `RUNTIME/central_core.py` | Keep actor route commands synchronized with accepted v2 sessions and release claims on completion/cancel. |
| `TESTS/test_visual_selection.py` | Python shuffle-bag, catalog and persistence tests. |
| `TESTS/test_speech_scheduler.py` | Python v2 ownership, same-floor concurrency and migration tests. |
| `TESTS/test_talk_runtime.py` | Central/conversation physical conflict and actor route regression tests. |
| `TESTS/test_browser_parity_trace.py` | Python/Browser v2 snapshot and sequence parity. |
| `TESTS/browser_runtime_test.mjs` | Browser selector, v2 speech and no-request smoke tests. |
| `TESTS/test_runtime_review_server.py` | Review telemetry and concurrent-row assertions. |
| `HANDOFF.md` | Current implementation status and verification evidence. |
| `ROADMAP.md` | Combined milestone acceptance state. |

## Execution protocol

- Use `superpowers:executing-plans` inline, because the user explicitly authorized implementation in this shared checkout and the pre-existing dirty state cannot safely be moved into a fresh worktree without committing unrelated work.
- For every behavior change, follow TDD: write one focused failing test, run it and record the expected failure, implement the smallest change, rerun the focused test, then run the relevant regression family.
- Keep source files and tests in the same patch for each task; do not use broad formatter rewrites.
- At each checkpoint inspect `git diff --stat`, `git diff --check` and `git status --short`; stage only new files or exact files whose existing diff is part of the approved task.

## Task 1: Add the Python visual catalog and shuffle-bag core

**Files:**
- Create: `RUNTIME/visual_selection_core.py`
- Create: `TESTS/test_visual_selection.py`
- Modify: `RUNTIME/actor_simulation_core.py` only after the core tests are green

**Interfaces:**
- `VisualSelectionCore(root: str | Path)` loads and validates the two canonical registries.
- `VisualSelectionCore.catalog()` returns a JSON-safe object with `profile_id`, ordered `vfx` IDs, ordered `humanball` IDs and their registry SHA-256 hashes.
- `VisualSelectionCore.initial_channel_state(channel: str)` returns `{"catalog_profile": str, "generation": 0, "cursor": 0, "active_binding": None}`.
- `VisualSelectionCore.select(state: dict, *, channel: str, simulation_seed: str, employee_id: str, event_id: str, started_at_ms: int, ends_at_ms: int)` mutates a copied state and returns `(state, binding)` where `binding` contains `channel`, `asset_id`, `event_id`, `employee_id`, `started_at_ms`, `ends_at_ms`, `generation` and `cursor_after`.
- `VisualSelectionCore.clear_active(state: dict, *, event_id: str | None = None)` returns a copied state with `active_binding` cleared and rejects an unrelated event ID.

- [ ] **Step 1: Write failing catalog and bag tests**

Add tests with real registries and a fixed seed:

```python
def test_visual_catalog_exposes_all_canonical_ids():
    visual = VisualSelectionCore(ROOT)
    catalog = visual.catalog()
    assert catalog["vfx"]["ids"] == json.loads(
        (ROOT / "CHARACTER/EFFECTS/gds_effects_v1.json").read_text()
    )["effect_order"]
    assert len(catalog["vfx"]["ids"]) == 11
    assert len(catalog["humanball"]["ids"]) == 6

def test_vfx_bag_has_no_repeat_then_refills_deterministically():
    visual = VisualSelectionCore(ROOT)
    first = visual.initial_channel_state("vfx")
    selected = []
    state = first
    for index in range(23):
        state, binding = visual.select(
            state,
            channel="vfx",
            simulation_seed="bag-seed",
            employee_id="EMP_W1_0010",
            event_id=f"event-{index}",
            started_at_ms=index * 60,
            ends_at_ms=(index + 1) * 60,
        )
        selected.append(binding["asset_id"])
        state = visual.clear_active(state, event_id=f"event-{index}")
    assert len(set(selected[:11])) == 11
    assert len(set(selected[11:22])) == 11
    assert selected == visual_sequence(visual, "vfx", "bag-seed", "EMP_W1_0010", 23)

def test_visual_bags_are_independent_by_actor_and_channel():
    visual = VisualSelectionCore(ROOT)
    vfx_a = visual.select(visual.initial_channel_state("vfx"), channel="vfx", simulation_seed="s", employee_id="EMP_W1_0010", event_id="a", started_at_ms=0, ends_at_ms=60)[1]["asset_id"]
    vfx_b = visual.select(visual.initial_channel_state("vfx"), channel="vfx", simulation_seed="s", employee_id="EMP_W1_0011", event_id="b", started_at_ms=0, ends_at_ms=60)[1]["asset_id"]
    popup_a = visual.select(visual.initial_channel_state("humanball"), channel="humanball", simulation_seed="s", employee_id="EMP_W1_0010", event_id="c", started_at_ms=0, ends_at_ms=60)[1]["asset_id"]
    assert vfx_a in visual.catalog()["vfx"]["ids"]
    assert vfx_b in visual.catalog()["vfx"]["ids"]
    assert popup_a in visual.catalog()["humanball"]["ids"]
```

Use a small `visual_sequence` test helper that repeatedly calls the public interface; keep it in the test module, not production code. Add failure tests for duplicate/empty registry IDs, catalog profile mismatch, invalid channel and clear of the wrong event.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_visual_selection.py
```

Expected: collection fails because `RUNTIME/visual_selection_core.py` and `VisualSelectionCore` do not exist. Correct test import/setup errors before proceeding; the behavior assertions must then fail for the missing implementation.

- [ ] **Step 3: Implement the minimal Python core**

Read `effect_order` and `humanball_order`, reject duplicates/empty lists and compute each registry file hash with the existing `RUNTIME.asset_utils.file_sha256`. Use the existing stable hash material format: UTF-8 strings joined with `\x1f`, SHA-256 digest first 8 bytes, unsigned big-endian integer.

Implement the permutation exactly as:

```python
def _permutation(self, *, channel, simulation_seed, employee_id, generation):
    return sorted(
        self._ids[channel],
        key=lambda asset_id: (
            self._stable_hash(
                simulation_seed,
                "visual-bag",
                employee_id,
                channel,
                generation,
                asset_id,
            ),
            asset_id,
        ),
    )
```

Validate `catalog_profile` on every selection, increment generation when `cursor == len(pool)`, consume exactly one ID, and attach the active binding before returning. Do not use `random`, `secrets` or a full persisted permutation.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same command. Expected: all catalog, sequence, independence and error tests pass with no warnings.

- [ ] **Step 5: Refactor only after green**

Remove any duplicate registry parsing or hash implementation introduced during the red-green cycle. Keep the public core limited to catalog/state/select/clear operations.

## Task 2: Persist Python actor visual state and bind events once

**Files:**
- Modify: `SCHEMA/actor_snapshot.schema.json`
- Modify: `CONTRACTS/actor_simulation.json`
- Modify: `RUNTIME/actor_simulation_core.py`
- Modify: `TESTS/test_visual_selection.py`
- Modify: `TESTS/test_actor_simulation_core.py`

**Interfaces:**
- Add `behavior.visual_channels.vfx` and `behavior.visual_channels.humanball` using the compact state from Task 1.
- `ActorSimulationCore` owns `self.visual_selection` and calls `select` only from `_start_event` for `background_effect` or `popup`.
- `_presentation_for_behavior` reads `behavior.visual_channels[channel].active_binding`; it never computes an asset ID.
- `_complete_event`, home transitions and event cancellation clear only the matching channel binding.

- [ ] **Step 1: Write failing actor-state tests**

Add tests that assert initial snapshots contain two empty channel states, that the first `background_effect` event advances only the VFX cursor, that repeated `_presentation_for_behavior` calls return the same `asset_id`, and that consuming 11 VFX events exposes all 11 IDs. Add a save/load assertion by JSON round-tripping the snapshot between event starts and comparing the next binding.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_visual_selection.py TESTS/test_actor_simulation_core.py
```

Expected: the new fields/assertions fail because the actor schema rejects `visual_channels` or the presentation still uses hash modulo.

- [ ] **Step 3: Extend the actor schema and initialize/migrate state**

Add a strict `visual_channels` object under behavior with required `vfx` and `humanball` states. In `_actor_from_employee`, initialize both states from `VisualSelectionCore.initial_channel_state`. In `_canonical_snapshot`, normalize legacy snapshots that do not have the fields by creating empty states using the current catalog profile. If a legacy snapshot contains an old asset ID only in a presentation event and no cursor, do not infer a cursor from it; the next bag starts at generation 0/cursor 0.

- [ ] **Step 4: Bind and clear at event boundaries**

In `_start_event`, derive a deterministic event ID from employee ID, event counter and timestamp, calculate the existing activity end, call `VisualSelectionCore.select`, and store the returned binding. In `_presentation_for_behavior`, return the stored binding plus existing render metadata. In `_complete_event` and all early event cancellation paths, call `clear_active` for the channel. Explicit semantic event preset presentation continues to use its fixed mapping and does not advance these automatic bags.

- [ ] **Step 5: Run focused and existing actor tests**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_visual_selection.py TESTS/test_actor_simulation_core.py TESTS/test_work_effect_floor_integration.py TESTS/test_humanball_popup_channel.py
```

Expected: all pass; the old six-ID expectation must be updated to assert catalog membership and full-bag coverage, not a hard-coded positive-only list.

## Task 3: Generate and mirror the visual selector in Browser JS

**Files:**
- Create: `WEB/runtime_simulation_visual_selection.js`
- Modify: `WEB/runtime_simulation_effects.js`
- Modify: `WEB/runtime_simulation_actor.js`
- Modify: `WEB/runtime_simulation_state.js`
- Modify: `RUNTIME/browser_bundle_contract.py`
- Modify: `TOOLS/build_runtime_simulation_bundle.py`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `TESTS/test_browser_bundle_contract.py`

**Interfaces:**
- Export `BrowserVisualSelection` with `catalog()`, `initialChannelState(channel)`, `select(state, args)` and `clearActive(state, eventId)` matching Python field names and outputs.
- `BrowserEffectsReducer` receives `catalog` and resolves persisted `actor.behavior.visual_channels` bindings only.
- `BrowserActorReducer` receives `visualSelection`, binds at `startEvent`, and clears at completion.

- [ ] **Step 1: Write failing Node tests**

Add tests that import `BrowserVisualSelection`, compare 23 selected IDs against a Python fixture, assert all 11/6 coverage, assert repeated effect renders keep the same `asset_id`, and instrument `globalThis.fetch` to prove visual stepping adds no request.

- [ ] **Step 2: Run the focused Node tests and verify RED**

Run:

```powershell
node --test TESTS/browser_runtime_test.mjs
```

Expected: import failure for the new module or assertion failure for the old hash-modulo presentation.

- [ ] **Step 3: Add generated catalog/profile data**

Update the bundle builder to load the existing canonical registries, copy their ordered IDs and hashes into `visual_catalog`, and include the catalog under the existing bundle revision payload. Extend `validate_bundle` to require unique non-empty IDs, the registry schema names and the catalog profile. Regenerate `WEB/runtime_simulation_bootstrap.json` and `WEB/runtime_simulation_bundle.js` only through the existing builder command.

- [ ] **Step 4: Implement BrowserVisualSelection and actor binding**

Mirror the Python sort key using `stableHash64(seed, "visual-bag", employeeId, channel, generation, assetId)` and lexical ID tie-break. Store the same compact fields. Pass the bundle catalog into `BrowserActorReducer` and `BrowserEffectsReducer`. On event start, bind one ID; on render, read the binding. Avoid importing or calling `Math.random`.

- [ ] **Step 5: Run Node/browser bundle tests**

Run:

```powershell
node --test TESTS/browser_runtime_test.mjs
python -B -m pytest -p no:cacheprovider -q TESTS/test_browser_bundle_contract.py TESTS/test_runtime_review_web.py
```

Expected: all current browser tests plus new visual parity/no-request checks pass.

## Task 4: Move the speech contract and snapshot to v2

**Files:**
- Modify: `CONTRACTS/speech_scheduler.json`
- Modify: `SCHEMA/speech_scheduler.schema.json`
- Modify: `SCHEMA/speech_scheduler_snapshot.schema.json`
- Modify: `RUNTIME/speech_scheduler_core.py`
- Create: `TESTS/fixtures/speech_scheduler_v1_migration.json`
- Modify: `TESTS/test_speech_scheduler.py`

**Interfaces:**
- `SpeechSchedulerCore.SCHEMA == "gds.speech_scheduler_snapshot.v2"` and `VERSION == "2.0.0"`.
- `SpeechSchedulerCore.migrate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]` accepts v1 or v2 and returns canonical v2.
- v2 actor records contain `bubble_slot: {active_session_id, active_until_ms, queued_request_ids, last_completed_session_id}`.
- v2 root records contain `pending_requests: dict[str, dict]` and `resource_claims: dict[str, dict]`; they do not contain a scheduling `lanes` object.

- [ ] **Step 1: Write failing v2/migration tests**

Add tests for v2 initial shape, one empty actor slot per actor, v1 fixture migration that drops `lanes`, active-session participant slot mapping, queued-request ownership indexing and invalid routed-pair migration rejection. Update the contract test to assert v2 scope and `no_overlap_scope == "one_bubble_slot_per_actor"`.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_speech_scheduler.py
```

Expected: failures on the v1 schema/version and missing v2 fields. Existing lane assertions are intentionally red and will be rewritten only after the migration shape exists.

- [ ] **Step 3: Implement v2 schema and initial state**

Replace the active contract/schema constants with v2. Keep all existing timing/category/bubble-fit fields. Replace `lanes` with `pending_requests` and `resource_claims`; add strict actor `bubble_slot`; add session `resource_claim_id` and claim fields required to release/resume a physical plan. Update canonical ordering to sort actor/session/request/claim maps by key.

- [ ] **Step 4: Implement the v1 migration adapter**

Before schema validation, detect `gds.speech_scheduler_snapshot.v1`. Validate it with a local v1 validator loaded from the prior shape embedded in the migration module, copy common fields, initialize actor slots, map active lane sessions to every participant slot, move full `queued_requests` entries into `pending_requests`, retain request ownership under the initiator and rehydrate resource claims from stored conversation plan metadata. Reject an active routed session with no reconstructible claim. Drop `lanes`, set v2 schema/version, then validate the result.

- [ ] **Step 5: Run migration and existing persistence tests**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_speech_scheduler.py TESTS/test_talk_runtime.py
```

Expected: migrated v1 fixtures validate, current emotion/dialogue/persistence behavior remains green, and only the old floor-serialization assertions remain to be replaced in Task 5.

## Task 5: Implement Python actor-slot admission and physical claims

**Files:**
- Modify: `RUNTIME/speech_scheduler_core.py`
- Modify: `RUNTIME/conversation_behavior_core.py`
- Modify: `RUNTIME/conversation_spot_core.py`
- Modify: `RUNTIME/central_core.py`
- Modify: `TESTS/test_speech_scheduler.py`
- Modify: `TESTS/test_talk_runtime.py`

**Interfaces:**
- `SpeechSchedulerCore._actor_slot_available(snapshot, employee_id) -> bool` checks only the actor bubble slot and actor phase.
- `SpeechSchedulerCore._resource_view(snapshot) -> dict[str, Any]` returns active claims plus claims accepted during the current scan.
- `SpeechSchedulerCore._admit_request(snapshot, request, *, timestamp_ms, conversation_snapshot, dialogue_locale, dialogue_seed) -> tuple[dict, dict] | None` performs one candidate-specific admission and mutates state only after all participant/resource checks pass.
- `SpeechSchedulerCore._release_session_claims(snapshot, session_id) -> None` releases actor slots and physical claim exactly once.

- [ ] **Step 1: Write failing same-floor and atomicity tests**

Replace the old floor-lane tests with focused tests:

```python
def test_two_unrelated_same_floor_solo_bubbles_start_together():
    scheduler = SpeechSchedulerCore(ROOT)
    snapshot = scheduler.initial_snapshot("floor02", simulation_seed="same-floor")
    for actor in snapshot["actors"].values():
        actor.update({"greeting_due_ms": None, "work_start_due_ms": None, "solo_pending": False, "pair_pending": False, "solo_next_due_ms": None, "pair_next_due_ms": None})
    first_id, second_id = sorted(snapshot["actors"])[:2]
    snapshot["actors"][first_id]["solo_pending"] = True
    snapshot["actors"][second_id]["solo_pending"] = True
    result = scheduler.advance_snapshot(snapshot, 0, validate=True)
    sessions = result["snapshot"]["active_sessions"]
    assert len(sessions) == 2
    assert {first_id, second_id} == {session["participants"][0] for session in sessions.values()}

def test_same_actor_request_waits_without_blocking_unrelated_actor():
    scheduler = SpeechSchedulerCore(ROOT)
    snapshot = scheduler.initial_snapshot("floor02", simulation_seed="actor-slot")
    first_id, second_id = sorted(snapshot["actors"])[:2]
    snapshot["actors"][first_id]["solo_pending"] = True
    snapshot["actors"][second_id]["solo_pending"] = True
    first = scheduler.advance_snapshot(snapshot, 0)
    first_session = next(session for session in first["snapshot"]["active_sessions"].values() if first_id in session["participants"])
    first["snapshot"]["actors"][first_id]["solo_pending"] = True
    second = scheduler.advance_snapshot(first["snapshot"], 0)
    assert any(first_id in request["participants"] for request in second["snapshot"]["pending_requests"].values())
    assert any(second_id in session["participants"] for session in second["snapshot"]["active_sessions"].values())
    assert first_session["session_id"] in second["snapshot"]["active_sessions"]
```

Add a pair test that supplies a conversation plan whose second participant is already slotted and asserts no half-created session or resource claim. Add a physical conflict test with two candidates sharing a talk slot: first candidate is admitted, second is retained with `blocked_reason == "talk_slot"`, and an unrelated candidate starts.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_speech_scheduler.py TESTS/test_talk_runtime.py
```

Expected: the old floor lane admits at most one session and the new tests fail on missing v2 admission behavior.

- [ ] **Step 3: Add candidate-specific request storage and actor slots**

Remove `by_floor` admission and the `lane.active_session_id` gate. At each boundary, derive requests, canonicalize metadata into `pending_requests`, and sort by the existing priority, due time, initiator ID and request ID. Skip a candidate whose participant actor slot or participant lock is busy, record its deterministic retry time/reason, and continue scanning.

- [ ] **Step 4: Add atomic physical resource planning**

Build a working resource view from active claims and accepted plans in this pass. For pair candidates, pass active/accepted reserved cells to `ConversationSpotCore` and carry the returned talk slot/path claim into the new session. Commit session, all actor slots, participant lock and resource claim in one mutation after plan success. If plan resolution fails, retain only that request with the existing deterministic fallback/cancel policy.

- [ ] **Step 5: Release slots and claims on completion/cancel**

Replace lane cleanup in `_complete_session` with `_release_session_claims`. Release every participant slot and claim exactly once, preserve emotion completion semantics, and ensure a pair’s two actor slots are released together. Add telemetry fields `blocking_layer`, `resource_claim_id` and `bubble_slot_ids` to speech events.

- [ ] **Step 6: Run the Python speech/conversation family**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_speech_scheduler.py TESTS/test_talk_runtime.py TESTS/test_runtime_render_state.py TESTS/test_runtime_presentation_renderer.py
```

Expected: same-floor concurrency, same-actor exclusion, pair atomicity and physical collision tests pass without changing route geometry or bubble fit behavior.

## Task 6: Mirror speech v2 and migration in Browser JS

**Files:**
- Modify: `WEB/runtime_simulation_speech.js`
- Modify: `WEB/runtime_simulation_state.js`
- Modify: `WEB/runtime_simulation_core.js`
- Modify: `TESTS/browser_runtime_test.mjs`
- Modify: `TESTS/test_browser_parity_trace.py`

**Interfaces:**
- `BrowserSpeechReducer.migrateSnapshot(snapshot) -> snapshot` mirrors Python v1→v2.
- `BrowserSpeechReducer.processAt(...)` scans all canonical pending candidates without a floor mutex.
- `BrowserSpeechReducer.startSession(...)` writes actor slots and resource claim IDs atomically.
- `BrowserSpeechReducer.completeSession(...)` releases actor slots/claims and preserves the existing emotion hook.

- [ ] **Step 1: Write failing Browser concurrency/migration tests**

Add a same-floor browser fixture with two due solo requests and assert two active sessions, an actor-slot collision fixture that leaves one pending request while another actor starts, and a v1 migration fixture whose result has `pending_requests` and no `lanes`. Add a Python-generated expected JSON checkpoint for identical admission order.

- [ ] **Step 2: Run Node tests and verify RED**

Run:

```powershell
node --test TESTS/browser_runtime_test.mjs
```

Expected: failures on `lanes`, one-session-per-floor assumptions or missing migration methods.

- [ ] **Step 3: Implement Browser v2 state and candidate scan**

Port the Python field names and sort order exactly. Maintain a `pending_requests` map and actor `bubble_slot` indices. Clear a blocked request’s old projection before rebuilding it, retain a request-specific retry reason, and continue to later candidates after any block. Do not create a second Browser-only concurrency policy.

- [ ] **Step 4: Wire the Browser runtime and render rows**

Update `BrowserRuntimeCore` to validate v2 snapshots, pass physical claim data to the existing route command bridge, and keep `dialogueForActor` actor-local. Preserve deterministic actor sort order for multiple visible rows. Keep `completed_sessions` only as a presentation history projection; it cannot act as a lock.

- [ ] **Step 5: Run Browser tests and parity tests**

Run:

```powershell
node --test TESTS/browser_runtime_test.mjs
python -B -m pytest -p no:cacheprovider -q TESTS/test_browser_parity_trace.py TESTS/test_runtime_review_web.py
```

Expected: Python and Browser agree on same-floor sessions, actor slots, migration output and bubble visibility.

## Task 7: Regenerate bundle, update review UI and run live verification

**Files:**
- Modify generated: `WEB/runtime_simulation_bootstrap.json`
- Modify generated: `WEB/runtime_simulation_bundle.js` when the builder emits it
- Modify: `WEB/runtime_review.html` only for displaying new telemetry fields if existing rows cannot show them
- Modify: `TESTS/test_runtime_review_web.py`
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Add failing review assertions**

Assert the review payload exposes `visual_catalog`, `selection_source`, `generation`, `cursor_after`, `blocking_layer`, and concurrent actor dialogue rows. Assert an instrumented Browser source-mode run makes exactly one bootstrap request and zero `/api/tick` requests after stepping.

- [ ] **Step 2: Run the review tests and verify RED**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q TESTS/test_runtime_review_web.py
```

Expected: missing telemetry or old lane fields cause failures.

- [ ] **Step 3: Regenerate the deterministic bundle**

Run the repository’s existing bundle generation command from the project root, then validate the generated bundle with `RUNTIME.browser_bundle_contract.validate_bundle`. Confirm `visual_catalog.vfx.ids` has 11 IDs, `visual_catalog.humanball.ids` has 6 IDs, source hashes are current, and no static asset hash changed.

- [ ] **Step 4: Run the review server smoke path**

Inspect listeners first:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
Get-CimInstance Win32_Process -Filter "ProcessId = 11232" | Select-Object ProcessId,CommandLine
```

Reuse PID `11232`. Use the existing browser tab at `http://127.0.0.1:8765/`, run Full system and targeted Talk/Effects demos, and verify:

- two unrelated actors on one floor can show bubbles concurrently;
- a second request for an actor waits without preventing another actor’s bubble;
- VFX eventually shows all 11 IDs and popup eventually shows all 6 IDs;
- the same active visual stays bound across frames;
- console has no error/warning and network has no per-event request.

- [ ] **Step 5: Run all regression/audit gates**

Run:

```powershell
python -B -m pytest -p no:cacheprovider -q
node --test TESTS/browser_runtime_test.mjs
python -B -m compileall -q RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS
ruff check RUNTIME WORLD CHARACTER TOOLS VALIDATION TESTS --select F401,F841
python TOOLS/lean_audit.py
python VALIDATION/self_audit_room_navigation.py
python VALIDATION/self_audit_navigation_occupancy.py
python VALIDATION/self_audit_work_seat.py
python VALIDATION/self_audit_phase6.py
python VALIDATION/self_audit_central.py
python VALIDATION/self_audit_gameplay_metadata_family.py
python VALIDATION/self_audit_conversation.py
git diff --check
```

Record exact counts and failures in `HANDOFF.md`; do not call the milestone closed before live visual/gameplay acceptance.

- [ ] **Step 6: Commit only separable implementation changes**

Because the checkout contains earlier dirty work, inspect `git diff HEAD -- <file>` before staging. Commit new standalone modules/tests and exact contract/generated changes only when their pre-existing diff is part of this task. Leave unrelated approved cleanup changes unstaged and list them in the handoff.

## Task 8: Final review and handoff to TS/JS migration

**Files:**
- Modify: `HANDOFF.md`
- Modify: `ROADMAP.md`

- [ ] **Step 1: Run the complete verification commands again after the final patch**

Use the full commands from Task 7 Step 5. Read exit codes and test counts; do not infer from an earlier run.

- [ ] **Step 2: Inspect the final diff for lean boundaries**

Confirm there is one Python visual selector, one Browser visual selector, one v2 speech admission model, no manually duplicated visual pool arrays and no remaining active `one_speech_lane_per_floor` gate. Confirm static assets, reference hashes and `00_STARTING_POINT/` are untouched.

- [ ] **Step 3: Request a code review before claiming completion**

Provide the reviewer with the implementation diff, this plan, the spec, baseline commit `b7d03b9` and the final implementation commit(s). Fix every critical/important finding or document a technically justified deferral in `HANDOFF.md`.

- [ ] **Step 4: Update handoff and roadmap**

Mark engineering items complete only when the implementation and audits are green. Keep author visual/gameplay acceptance, Canvas/Raster acceptance, browser endurance and Cloudflare authority as separate open gates until explicitly accepted.

