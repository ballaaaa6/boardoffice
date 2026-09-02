# Conversation Runtime Corrections — Proposed Design

**Status:** Proposed for user review; this document does not authorize runtime implementation.

## Goal

Correct the employee-to-employee standing conversation so that its UV placement, facing poses, opener bubble spacing, shared post-talk emotion, and return-to-work presentation all match the requested behavior without changing world geometry, character art, WorkSeat ownership, or unrelated conversation modes.

## User-visible target behavior

1. A walking standing pair uses equal `v` and different `u` values, separated by the existing four-cell talk gap.
2. The lower-`u` endpoint is the far side and uses `idle.SW`; the higher-`u` endpoint uses `idle.NE`.
3. The speaker whose line is `conversation_open` is the opener. Its bubble is one additional base head-distance higher than normal: the current base vertical offset is `-20px`, so the opener uses an additional `[0, -20]` translation and the reply remains `[0, 0]`.
4. A standing pair receives one shared six-sided emotion roll after the bubble fade. The scheduler owns the roll, stores the integer `1..6`, maps even to `happy` and odd to `sad`, and passes the same roll into the conversation plan and presentation. The roll sequence varies between consecutive live pair sessions and survives save/load/replay.
5. During the return `seat_entry` boundary, the actor reducer’s live transition pose is authoritative. Only after the existing `SEAT_TRANSITION_MS=240` boundary completes does the actor render as `work_seat/work/normal_work`.

## Coordinate clarification

The implementation treats the explicit phrase “`v` equal and `u` different” as authoritative. In the current isometric projection, literal screen-`x` equality is not the same thing as a single canonical U or V cardinal step; a literal screen-vertical line would require a diagonal UV delta and is outside this correction. The desired facing names are also not the global U-axis names, so the standing-pair resolver gets a pair-specific facing policy rather than changing the global axis-direction table.

## Current causes being corrected

- `ConversationSpotCore` tries preferred `V` first, producing equal `u` and different `v`; its global signed-axis map would produce `SE/NW` for U and `SW/NE` for V.
- `ConversationBehaviorCore` emits zero bubble offsets for both pair participants, while the raster renderer passes only the actor head anchor and ignores the offset field.
- `ConversationBehaviorCore` and `SpeechSchedulerCore` each calculate an independent stable hash result. Neither performs a random-generator draw, and a reset with the same seed/session inputs can repeatedly produce `sad`.
- `_begin_seat_entry_transition()` clears the route while talk metadata remains active. `resolve_runtime_presentation()` then lets a plan pose overwrite the live transition pose, creating the intermittent seated/idle seam.

## Design

### 1. Contract-first standing-pair geometry

Change only the standing-pair contract to preferred axis `U`, fallback axis `V`, endpoint order ascending `u`, and endpoint facing order `[SW, NE]`. Keep `AXIS_DELTAS`, `AXIS_DIRECTION`, the movement direction contract, and all WorkSeat turn-side mappings unchanged. The resolver returns the selected endpoint order and facing order together, so `ConversationBehaviorCore` can assign them to actors without guessing from actor identity.

### 2. Role-based bubble translation

Use the existing `dialogue_bubble_offset_px` field as an additive pixel translation of the bubble rectangle and its reported tail position. The actor head anchor remains the real sprite head anchor. For a standing pair, derive the opener from `timing.speaker_sequence[0]`/`conversation_open`, not from endpoint order; assign `[0, -20]` to that actor and `[0, 0]` to the reply. `seated_host`, `ceo_front`, `self_talk`, lifecycle speech, and non-pair overlays retain zero offset.

Thread the offset through `CentralGameCore.render_employee_dialogue_bubble()`, `DialogueBubbleRenderer.render_for_character()`, `RuntimePresentationRenderer`, and `ConversationPairGifRenderer`. The base `-20px` value remains in the existing bubble registry; no bubble asset is edited.

### 3. One scheduler-owned stateful d6

Add a JSON-safe 64-bit PRNG state to the speech snapshot determinism block. Initialize it from the simulation seed for new snapshots and derive a compatible initial state when loading an older snapshot. Advance it exactly once after a valid standing-pair plan has been selected and before the session is committed. Store `emotion_roll` and `emotion_outcome` on the session. `ConversationBehaviorCore.plan_conversation()` accepts an optional validated `emotion_roll`; the scheduler supplies the roll, while standalone preview callers either supply an explicit preview roll or leave the plan’s post-talk emotion absent. No renderer or preview call advances gameplay RNG state.

The PRNG is a persisted seeded sequence rather than an OS-entropy call on every frame: consecutive conversations vary, while save/load and replay remain reproducible. If a fresh-world demo needs a different first roll, its initial simulation seed can be generated once at world creation and then persisted.

### 4. Actor-transition authority at the presentation seam

Treat either a live route or a live `seat_transition` as authoritative motion. Conversation timing and bubble metadata may still overlay during the transition, but conversation plan pose keys must not overwrite `render_owner`, `action`, `subaction`, direction, frame, UV, or ground position while `seat_transition.phase == "seat_entry"`. After the transition reducer clears talk and the transition record, the normal baseline path emits `work_seat/work/normal_work` and advances its persisted work-loop clock.

## Compatibility and non-goals

- Do not edit `00_STARTING_POINT/`, `WORLD/`, character sprites, bubble image crops, WorkSeat placement, navigation occupancy, or reference hashes.
- Do not change `ceo_front`, `seated_host`, self-talk, lifecycle speech, or the existing four-cell gap and 240ms seat boundary.
- Preserve JSON-safe snapshots and accept/migrate existing speech snapshots that lack the new PRNG state.
- Preserve the existing raster review server and GIF QA path; both must use the same bubble offset and emotion metadata.
- Do not close Phase 8E or record visual acceptance until the user reviews the corrected walking pair, bubble placement, emotion variation, return boundary, and normal-work animation in the browser.

## Acceptance matrix

| Area | Required evidence |
| --- | --- |
| Geometry | All-floor conversation audit passes; every standing pair has equal `v`, `abs(u_delta)=4`, lower-`u` `SW`, higher-`u` `NE`, reachable endpoints, and inverse facing values. |
| Bubble | Plan marks only the opener with `[0,-20]`; raster and GIF renders move the opener bubble exactly 20px above the reply relative to the same head anchor. |
| Emotion | Every standing-pair session stores `emotion_roll` in `1..6`; consecutive sessions consume a changing persisted sequence; plan, event, pose binding, stamina effect, and session outcome agree. |
| Return | Boundary samples show live `seat_entry`/`move`/`idle` for 240ms, then `work_seat`/`work`/`normal_work`; no stale conversation pose appears in between. |
| Regression | Focused tests, full pytest, conversation/Central/WorkSeat/navigation/Phase 6/gameplay-metadata audits, and browser smoke pass. |
