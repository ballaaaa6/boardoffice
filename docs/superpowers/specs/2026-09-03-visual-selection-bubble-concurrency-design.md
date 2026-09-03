# Deterministic Visual Selection and Per-Actor Bubble Concurrency

**Date:** 2026-09-03  
**Status:** Draft — review requested  
**Scope:** Lean-first runtime correction before the TypeScript/JavaScript production migration

## Decision summary

This change combines two policy corrections behind one deterministic runtime contract:

1. VFX and HumanBall popup selection will use a replayable shuffle-bag owned by each actor and visual channel. The VFX bag contains all 11 IDs in `CHARACTER/EFFECTS/gds_effects_v1.json`; the popup bag contains all 6 IDs in `CHARACTER/EFFECTS/humanball_v1.json`. An item cannot repeat within the same actor/channel bag generation.
2. Speech admission will own one bubble/session slot per actor instead of one speech lane per floor. Different actors on the same floor may display bubbles at the same time. A pair claims both actor slots atomically, while talk spots, paths, reserved cells and crowd occupancy remain independent physical resources.

Python remains the gameplay oracle for this implementation slice. Browser JavaScript must mirror the same contract and deterministic algorithms. The implementation must not add a request per visual event and must preserve the single-bootstrap/no-periodic-tick direction required for the later TS/JS handoff.

## Evidence and current behavior

The current BB symptom is caused by an explicit scheduler policy, not by missing assets or a renderer limitation:

- `CONTRACTS/speech_scheduler.json` declares `timing.no_overlap_scope` as `one_speech_lane_per_floor`.
- `SCHEMA/speech_scheduler.schema.json` enforces that value and the snapshot shape contains `lanes` keyed by floor.
- `RUNTIME/speech_scheduler_core.py` groups due requests by floor and stops admission when that floor's `active_session_id` is non-null.
- `WEB/runtime_simulation_speech.js` mirrors the same `byFloor` grouping and floor-lane gate.
- `RUNTIME/central_core.py` already builds bubble rows per actor, and `RUNTIME/runtime_presentation_renderer.py` already paints every visible actor bubble. The presentation layer can therefore render concurrent bubbles once the scheduler admits them.

A same-floor reproduction with two otherwise eligible actors produced one active session, zero starts for the second actor, one queued request and an idle second actor while the floor lane was active. Focused scheduler and talk regression coverage currently passes under the old contract (`35 passed`), including a test that intentionally asserts floor-wide serialization. That test is expected to change with this design.

The visual inventory is already complete:

- 11 VFX IDs and 104 unique VFX source frame files are present and represented in the browser render manifest.
- 6 HumanBall popup IDs/assets are present and represented in the browser render manifest.
- The dialogue registry has 5 active bubble presets (`BB1`, `BB2`, `BB3`, `BB4`, `BB6`); `BB5` is intentionally excluded.
- All 44 VFX direction renders and 24 HumanBall direction renders have passed the current renderer checks.
- The current automatic VFX selector uses only six positive recovery IDs, and the current popup selector uses all six popup IDs but may repeat indefinitely because both selectors use hash modulo rather than a bag.

## Goals

- Make every canonical VFX and popup asset reachable by normal automatic events through a deterministic, no-repeat bag.
- Make bubble ownership actor-local so unrelated actors on the same floor do not wait for each other’s fade-out.
- Preserve same-actor exclusion, pair atomicity, physical collision protection, existing dialogue fit rules and current event frequencies.
- Keep Python and browser results byte-for-byte or value-for-value equivalent for the same seed, snapshot and event sequence.
- Make save/load and replay state compact, versioned and migratable from the current floor-lane snapshot.
- Keep asset selection local to the already loaded catalog so visual events do not issue network requests.
- Leave the codebase with one clear ownership model before the later TS/JS production migration.

## Non-goals

- This slice does not perform the TS/JS production migration.
- This slice does not change static character/world artwork, effect frame files, bubble artwork, reference hashes or authored geometry.
- This slice does not change event weights, dialogue content, locale bags, stamina effects, conversation mode probabilities or standing-pair orientation.
- This slice does not randomize BB shape. Bubble selection remains `smallest_allowed_fit` over the existing allowed IDs.
- This slice does not allow physically colliding conversation pairs merely because their actors have different bubble slots.
- This slice does not choose a Cloudflare persistence authority or replace the Python oracle.

## Contract invariants

The implementation is accepted only if all of these invariants hold:

### Visual channels

1. The automatic VFX pool is exactly the ordered `effect_order` from the canonical VFX registry: 11 unique IDs.
2. The automatic HumanBall pool is exactly the ordered `humanball_order` from the canonical popup registry: 6 unique IDs.
3. Each actor has an independent VFX bag and an independent HumanBall bag. Consuming an item for one actor or channel never advances another actor’s or channel’s bag.
4. Each item appears at most once between bag refill boundaries. After exhaustion, the next generation is a deterministic new permutation of the same pool.
5. The selected asset is committed once when an event starts. Re-rendering, interpolation, frame advancement and API polling never select a new asset for the active event.
6. The same simulation seed, actor ID, channel, catalog profile and event sequence produce the same selected IDs in Python and Browser JS. A different actor ID produces an independent sequence.
7. Explicit semantic event presets remain deterministic overrides. They are not a second random pool and do not consume the automatic bag unless the event is explicitly classified as an automatic bag event.
8. Selection reads IDs from the generated catalog already in the bootstrap bundle. It never calls `fetch`, `/api/tick`, an asset endpoint or another network service.

### Speech and bubbles

9. An actor has at most one active bubble/session slot at a time. A queued request owned by that actor cannot start until the actor slot is free.
10. Two different actors on the same floor may have active bubbles concurrently when their other constraints are satisfied.
11. A pair admission claims both participant actor slots atomically. If either participant is unavailable, neither participant is claimed and the request remains queued or follows the existing deterministic fallback/cancel policy.
12. Participant locks, talk-slot locks, route/path reservations and crowd occupancy are checked independently of bubble visibility. A collision blocks only the candidate that conflicts with the resource.
13. A blocked candidate does not stop unrelated candidates from being considered during the same scheduler pass. There is no floor-wide stop condition based only on another actor’s active bubble.
14. The v2 snapshot has no active floor speech lane as a scheduling gate. Any floor-indexed data that remains is a physical-resource index or diagnostic projection, not a global bubble mutex.
15. The existing bubble fit rule and allowed set remain unchanged: `BB1`, `BB2`, `BB3`, `BB4`, `BB6`; `BB5` remains excluded; overflow remains an error.

### Parity and persistence

16. Python is the oracle. Browser JS uses the same canonical ordering, hash inputs, tie-breakers, admission ordering, retry rules and snapshot version.
17. Loading a valid v1 snapshot through the migration adapter yields a valid v2 snapshot without retaining a floor lane in active runtime state.
18. Save/load at any accepted event boundary preserves the next visual ID, active visual binding, speech admission order and replay result.
19. Invalid or catalog-incompatible snapshots fail with a deterministic, actionable validation error rather than silently changing the sequence.

## Architecture

### 1. One canonical visual catalog

The registries remain the source of truth:

- `CHARACTER/EFFECTS/gds_effects_v1.json` supplies VFX order, IDs, frame metadata and render metadata.
- `CHARACTER/EFFECTS/humanball_v1.json` supplies popup order, IDs, frame metadata and render metadata.
- `CHARACTER/EFFECTS/event_presets.json` supplies explicit semantic event-to-effect mappings.
- `CHARACTER/DIALOGUE/bubble_presets.json` supplies the fixed bubble-fit policy.

The render-manifest builder derives the browser catalog from these registries. No new manually maintained list of 11 or 6 IDs is allowed in Python or JavaScript. The generated bundle carries:

```json
{
  "visual_catalog": {
    "profile_id": "gds.visual_catalog.v1",
    "vfx": {"ids": ["..."], "registry_schema": "gds_effect_registry_v1", "catalog_hash": "..."},
    "humanball": {"ids": ["..."], "registry_schema": "gds_humanball_registry_v1", "catalog_hash": "..."}
  }
}
```

The actual arrays are generated from `effect_order` and `humanball_order`; the abbreviated example above is structural only. The catalog hash is part of replay compatibility and changes when the ordered ID set or relevant render contract changes.

### 2. Deterministic per-actor/per-channel shuffle-bag

The bag does not store a shuffled array. It stores only the generation and cursor, then derives the permutation from stable inputs. The canonical pool is sorted for each generation by:

```text
sort_by(
  stableHash64(simulation_seed, "visual-bag", employee_id, channel, generation, asset_id),
  asset_id
)
```

The second key is an explicit lexical `asset_id` tie-breaker. `stableHash64` is the existing SHA-256-first-8-bytes implementation shared by `WEB/runtime_simulation_prng.js` and the Python parity utility. The separator, UTF-8 conversion, unsigned 64-bit interpretation and sort direction remain exactly those existing implementations use.

For each actor/channel state:

```json
{
  "catalog_profile": "gds.visual_catalog.v1:<catalog_hash>",
  "generation": 0,
  "cursor": 0,
  "active_binding": null
}
```

`cursor` is the number of IDs already consumed in the current generation. Selection proceeds as follows:

1. Validate that the catalog profile matches the loaded bundle and that the pool is non-empty and unique.
2. If `cursor` equals the pool length, increment `generation` and reset `cursor` to zero.
3. Derive the generation permutation using the exact stable sort above.
4. Select the ID at `cursor`, increment `cursor`, and persist the new cursor.
5. Attach the selected ID to the event’s active binding before any render occurs.

The active binding is per actor and channel and contains at least `event_id`, `asset_id`, `started_at_ms` and `ends_at_ms`. A render sample reads the binding; it never calls the bag selector. The binding is cleared only at the event lifecycle boundary. If an event is cancelled before it becomes visible, the implementation must use one explicit policy everywhere: the design chooses to consume the ID at event admission and retain that consumption on cancellation, because the admission itself is part of the deterministic event sequence and retrying must not reselect based on render timing.

Automatic event mapping is therefore:

```text
background_effect -> actor.vfx_bag -> one of all 11 VFX IDs
popup             -> actor.popup_bag -> one of all 6 HumanBall IDs
```

The existing automatic event weights remain unchanged. The no-repeat guarantee applies to each channel when that channel fires; it does not force a popup or VFX event to occur more frequently. Explicit mappings such as `heavy_stress -> thunder_cloud` and `system_error -> static_noise_field` remain fixed semantic overrides. The same IDs may also appear in the automatic all-11 VFX bag; the override path is intentionally distinct from automatic bag consumption.

### 3. Speech ownership layers

The scheduler must keep these layers separate:

| Layer | Owns | Blocks |
| --- | --- | --- |
| Actor bubble slot | one active speech visual/session reservation per actor | another request involving that actor |
| Participant lock | the actors participating in an accepted conversation | another conversation using those participants |
| Physical resource claim | talk spot, path, reserved cells and crowd/navigation occupancy | only candidates conflicting with those exact resources |
| Renderer | display order, frame clocks and bubble painting | nothing in scheduling |

For a seated self-talk/lifecycle line, the actor slot and any necessary participant claim are local to that actor. For a pair, both actor slots and the participant claim are acquired together. A pair may show two bubbles because each participant owns one slot; this is not a violation of the one-slot-per-actor rule.

`ConversationBehaviorCore` remains responsible for resolving a valid mode, talk spot, route and physical plan. The speech scheduler passes a working resource view containing active claims plus claims accepted earlier in the same tick. The conversation layer must evaluate that view before admission, and the scheduler commits the returned claim atomically with the actor-slot and participant-lock changes. The working view is rebuilt or incrementally extended for every accepted candidate in deterministic order, so two new pairs accepted in one tick cannot reserve the same spot or path.

The existing `blocked_cells` and `reserved_cells` inputs in `ConversationSpotCore` are the physical-resource boundary to preserve. They must be populated from active and already-accepted claims, not from a single floor-wide speech flag. A floor may still have many physical locks; it simply no longer has one speech mutex.

### 4. Canonical v2 scheduler state

The current v1 `lanes` object is replaced at the persistence boundary by actor slots, pending requests and explicit active-session claims. The canonical v2 shape is:

```json
{
  "schema": "gds.speech_scheduler_snapshot.v2",
  "version": "2.0.0",
  "clock": {"simulation_time_ms": 0, "tick_ms": 60},
  "determinism": {
    "simulation_seed": "...",
    "root_event_counter": 0,
    "emotion_rng_state": 0
  },
  "actors": {
    "EMP_W1_0001": {
      "...existing speech actor fields...": "...",
      "bubble_slot": {
        "active_session_id": null,
        "active_until_ms": null,
        "queued_request_ids": [],
        "last_completed_session_id": null
      }
    }
  },
  "active_sessions": {},
  "pending_requests": {},
  "resource_claims": {},
  "dialogue_bags": {}
}
```

The example is a shape contract, not a second source of actor fields. Existing actor timing, lifecycle and dialogue-bag fields remain in the v2 actor record. `pending_requests` is the canonical queue; `bubble_slot.queued_request_ids` is an index for requests owned by that actor. A pair request is owned by its initiator and references both participants in its request metadata, so a blocked partner does not create duplicate queue entries.

Each active session contains its existing identity, kind, mode, category, participants and bubble timing plus a `resource_claim_id` (nullable for sessions without a physical conversation plan). `resource_claims` maps that ID to the deterministic claim returned by the conversation layer, including participant IDs, talk-slot identity and the reserved spatial resources required to resume or release the plan. Resource claims are runtime ownership records, not a materialized static occupancy cache.

The v2 validation rules must reject:

- an actor referenced by more than one active session;
- a pair with a missing or duplicate participant;
- a pending request owned by an actor not present in the actor table;
- a resource claim owned by more than one session;
- a bubble slot whose `active_session_id` does not exist;
- a visual bag whose catalog profile does not match the loaded catalog;
- duplicate or missing IDs in either generated visual pool.

### 5. Admission and retry flow

At each speech tick:

1. Collect due lifecycle, pair and solo requests using the existing request metadata and priority policy.
2. Remove stale requests whose initiator has departed or whose lifecycle token is no longer valid, preserving the current cancellation ownership rules.
3. Sort candidates by the existing deterministic priority, due time, initiator ID and request ID tie-breakers.
4. Scan the sorted list without grouping by floor. For each candidate, check every participant’s bubble slot and participant lock.
5. For a pair candidate, ask the conversation layer for a plan against the current working physical-resource view. A plan that conflicts with another accepted claim returns a candidate-specific block reason.
6. If the candidate is valid, atomically create the session, claim all participant actor slots, claim its physical resources, and remove its request from `pending_requests`.
7. If the candidate is blocked by an actor or resource, retain it with a deterministic retry time and reason, then continue scanning other candidates. The retry time uses the existing retry interval semantics and does not change event weights.
8. Emit queue/admission telemetry that identifies the exact blocking layer (`actor_slot`, `participant_lock`, `talk_slot`, `path`, `crowd`, `no_valid_plan` or `stale_request`).

An actor slot is claimed at session admission, even if the first bubble is scheduled for a later talk arrival. This prevents a second request from entering during the route-to-talk window. If the route or plan is cancelled before the first bubble, the slot and all physical claims are released atomically. The visual active binding is created at the same deterministic event boundary as the current renderer contract requires; the renderer remains responsible only for displaying it at its prescribed first-bubble boundary.

At completion, release the session’s physical claims and actor slots together at the existing fade boundary/return boundary for that mode. Record `last_completed_session_id` per actor and remove the active session. A pair releases both actors even if only one participant’s bubble was the visible opener.

### 6. v1 to v2 migration

The migration adapter runs only at the save/replay boundary and is shared conceptually by Python and Browser JS:

1. Validate the incoming v1 snapshot before transforming it.
2. Copy clock, determinism, actors, active sessions and dialogue bags into the v2 shape.
3. For every v1 floor lane with an active session, find that session’s participants and create one v2 actor-slot claim for each participant. Use the session’s recorded fade/active boundary, taking the later of the lane’s active boundary and the session’s own fade boundary when both exist.
4. Convert each valid v1 `queued_requests` entry into one v2 `pending_requests` entry and index it under its `initiator_id`. The legacy `queued_session_ids` list is diagnostic only; it is not used to invent duplicate requests when full request metadata exists.
5. Rehydrate a v2 resource claim from the active session’s conversation plan metadata. If an active routed pair lacks enough plan data to reconstruct its physical claim, reject the snapshot with `speech_snapshot_migration_error` rather than allowing an unsafe collision.
6. Drop the v1 `lanes` object from the canonical result and set schema/version to v2.
7. Validate the migrated v2 snapshot, including the no-duplicate-actor and resource ownership invariants, before the next simulation tick.

Migration is deterministic and does not generate a new gameplay event. It is safe to run once on load and is idempotent when given an already-v2 snapshot. Browser JS must produce the same migrated JSON ordering and values as Python for the parity fixtures.

## Browser and web-request boundary

The browser bundle receives the generated catalog, contract profile and initial runtime state in its bootstrap payload. The visual bag selector consumes IDs already in memory. The render loop only advances clocks and resolves frame URLs from the static manifest. No visual event may trigger a network request.

The browser scheduler must remove its `byFloor`/floor-lane admission gate and implement the same v2 actor-slot/resource-claim flow. The browser may keep a diagnostic floor index for drawing or telemetry, but that index must not be consulted as a global speech mutex. Production source-mode acceptance remains one bootstrap request followed by zero periodic `/api/tick` requests; this design does not weaken that gate.

To make parity failures diagnosable, event telemetry includes:

```json
{
  "channel": "vfx|humanball",
  "asset_id": "...",
  "selection_source": "shuffle_bag|event_preset",
  "employee_id": "EMP_W1_0001",
  "generation": 0,
  "cursor_after": 1,
  "catalog_profile": "gds.visual_catalog.v1:<catalog_hash>"
}
```

Speech telemetry includes session ID, participants, floor ID, admission status, blocking layer/reason and claimed resource IDs. The UI can show concurrent rows by actor without introducing another scheduling policy.

## Error and fallback policy

- Empty, duplicated or unknown catalog IDs are a bootstrap/contract error.
- A catalog hash mismatch during snapshot load is a persistence compatibility error.
- An invalid explicit event preset is a registry validation error; it must not silently select a random replacement.
- A physical conversation conflict is a normal candidate-level retry, not a floor-wide error.
- A same-actor conflict is a normal actor-queue retry, not a renderer error.
- Existing semantic conversation fallbacks remain in force when a partner or mode is unavailable. They still pass through the same actor-slot and physical-resource admission layers.
- Asset files remain static manifest entries. Missing files are caught by the existing manifest/render audits before runtime acceptance.

## Verification plan and acceptance gates

### Unit and contract tests

- Registry tests assert exactly 11 VFX IDs, exactly 6 HumanBall IDs, stable order, uniqueness and manifest coverage.
- Shuffle-bag tests consume one full generation and assert no duplicates, assert deterministic refill, assert independent actor/channel sequences, assert save/load cursor continuity and assert active binding stability across repeated render calls.
- Preset tests assert fixed semantic mappings remain fixed and do not silently alter the automatic bag cursor.
- Snapshot schema tests cover v2 valid state, all duplicate ownership failures, catalog mismatch and v1→v2 migration.

### Speech regression tests

- Two solo/lifecycle actors on the same floor can start and display concurrently.
- Two actors with different floors continue to behave deterministically.
- Repeated requests for one actor queue behind that actor and never overlap.
- A pair claims both actor slots atomically; a failed second claim leaves no half-started session.
- A pair blocked by one talk spot does not block an unrelated pair with a different valid spot on the same floor.
- A path/crowd conflict blocks only the conflicting candidate.
- Active session completion releases every actor and resource exactly once.
- Save/load and replay preserve active sessions, queues, resource claims and admission order.
- The old floor-lane test is rewritten to assert per-actor behavior rather than floor serialization.

### Python/Browser parity tests

- Identical seed/catalog fixtures produce identical VFX and popup sequences for multiple actors and multiple bag generations.
- Identical v1 snapshots migrate to identical v2 JSON in both runtimes.
- Identical request traces produce identical accepted sessions, queued requests, blocking reasons and completion times.
- Browser smoke verifies concurrent same-floor bubbles, one actor’s independent retry, all visual channels and zero console errors/warnings.

### Full gates before the next TS/JS migration track

- `python -B -m pytest -p no:cacheprovider -q` passes.
- Browser runtime/parity tests pass.
- Required navigation, occupancy, WorkSeat, Phase 6, Central integrity, gameplay-metadata and conversation audits pass.
- Lean audit remains free of newly introduced duplicate pools, dead entrypoints or selected Ruff findings.
- Render-manifest and static asset/hash audits pass without changing authored assets.
- Review server demonstrates concurrent same-floor bubbles and all 11/6 visual coverage.
- Browser source mode confirms one bootstrap and zero periodic `/api/tick` requests.
- Release packaging remains clean: no caches, preview artifacts or materialized occupancy caches.

## Implementation order after spec approval

1. Update the v2 speech contract/schema and add failing migration/ownership tests.
2. Implement the Python actor-slot admission loop and physical working-claim view; remove the floor-lane gate from the canonical path.
3. Implement the Python visual catalog/bag state and active bindings.
4. Regenerate the browser bundle from the canonical registries and mirror the bag and speech algorithms in Browser JS.
5. Add parity fixtures, telemetry assertions, browser concurrency smoke and zero-request checks.
6. Run the full validation/audit/release-clean gates and inspect the live page.
7. Only after these gates and explicit visual/gameplay acceptance are closed, begin the TS/JS production migration against the frozen v2 contracts.

## Alternatives considered

### Keep a floor lane and only loosen solo overlays

This is the smallest code change, but it leaves pair/lifecycle behavior governed by a hidden floor-wide mutex and does not satisfy the requirement that ownership be per actor. It also keeps the current conceptual mismatch between a floor lane and a renderer that already supports per-actor bubbles.

### Add a second overlay lane beside the existing floor lane

This could make some bubbles appear concurrently, but it creates two scheduling systems with duplicated queue, retry and persistence rules. It would make the later TS/JS migration harder to reason about.

### Use actor bubble slots plus participant and physical resource claims

This is the selected design. It matches the user-visible ownership rule, preserves safety around the real physical constraints, gives one admission model to mirror in Python and Browser JS, and removes the unnecessary floor-wide gate without pretending that physical collisions are harmless.

## Self-review checklist

- All 11 VFX IDs are in the automatic VFX pool; the five currently underused semantic IDs are not lost, while explicit event presets remain deterministic.
- All 6 HumanBall IDs are in the automatic popup pool.
- BB shape selection is deliberately unchanged, so “one per actor” cannot be confused with randomizing bubble art.
- Same-floor concurrency is allowed only after actor and physical claims pass.
- A pair can show two bubbles because it owns two actor slots, while the same actor still cannot overlap.
- The browser and Python paths use one catalog, one hash definition, one snapshot version and one admission ordering.
- Migration removes the old lane from active v2 state rather than leaving a hidden compatibility mutex.
- Visual selection happens at event admission and remains bound through rendering, preventing frame/poll timing from changing gameplay.
- No new per-event request, periodic polling dependency or asset mutation is introduced.

This spec is ready for review. Implementation planning should begin only after the author confirms this design or requests changes.
