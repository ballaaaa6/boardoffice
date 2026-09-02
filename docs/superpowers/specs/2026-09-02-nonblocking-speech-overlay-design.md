# Non-blocking Speech Overlay Design

**Status:** Approved for inline implementation on 2026-09-02.

## Problem

The speech scheduler correctly treats in-work dialogue as a presentation overlay, but `CentralGameCore` currently commits every `solo` and `pair` speech session through `ActorSimulationCore.start_talk_session`. A no-route self-talk or seated host therefore becomes `activity="talking"`, clears its event timer, and enters an actor branch that never advances `behavior.work_loop_elapsed_ms`. The renderer still emits `work/normal_work`, so the visible character can appear frozen. Talk completion then resets the work loop to zero, creating a second first-frame hold after the actor returns to work.

## Decision

Keep one `start_talk_session` bridge, but make the committed actor state route-aware:

- A session with an outbound route remains a physical talk session. The actor owns `talking`, route samples, endpoint facing, hold pose, return route and the 240 ms WorkSeat entry boundary.
- A session without an outbound route becomes a stationary speech overlay. The actor remains `present/working`; its WorkSeat pose, work-loop clock and working-only stamina drain continue. `next_event_due_ms` is held at `null` only for the duration of the overlay so a second recovery event cannot overlap the active speech.
- `behavior.talk.route_committed` explicitly records the distinction. Old snapshots without the field infer it from the outbound path.
- `talk_returned` remains the completion event for both paths so the existing Central → speech `returned_to_work` bridge stays compatible.

No new actor activity enum is introduced.

## Runtime invariants

1. `present/working` may carry `behavior.talk` only when `route_committed` is false and `position.route` is null.
2. Stationary overlays have `conversation_phase == null`, `next_event_due_ms == null`, and `activity_until_ms == null`; the overlay end is `behavior.talk.return_start_at_ms`.
3. A stationary initiator may retain `active_event == "talk"` so the existing Talk recovery amount and cooldown remain authoritative. A stationary participant has `active_event == null`.
4. During an overlay, `_drain_work` advances stamina and `work_loop_elapsed_ms`; event selection waits until the overlay is cleared.
5. Talk completion never resets `work_loop_elapsed_ms` or `work_loop_count`, whether the talk was routed or stationary. Home and other mobile/recovery events retain their existing reset policy.
6. A physical route remains authoritative for position and pose. Speech timing remains authoritative for bubble visibility, order, text and offsets.
7. The stationary `seated_host` keeps its existing authored turn-side subaction, but its frame index is derived from the actor's continuing 360 ms work clock.
8. Standing-pair geometry, endpoint facings, opener/reply offsets, persisted d6 outcome and the WorkSeat return gate are unchanged.

## Mode mapping

| Mode/role | Route | Actor state while speech is visible | Frame source |
| --- | --- | --- | --- |
| `self_talk` initiator | none | `working` with overlay | actor work clock |
| `ceo_front` host | none | `working` with overlay | actor work clock |
| `seated_host` host | none | `working` with overlay | actor work clock, authored turn-side subaction |
| `ceo_front` visitor | outbound/return | `talking` with route | actor route/hold |
| `seated_host` visitor | outbound/return | `talking` with route | actor route/hold |
| `standing_pair` participants | outbound/return | `talking` with route | actor route/hold |

## Presentation rule

`resolve_runtime_presentation` will copy dialogue fields for every valid plan track. For a stationary overlay it may copy the authored stationary action/subaction/direction, but it must not replace the actor's WorkSeat ownership, coordinates or frame clock with a plan timeline frame. For a physical route, the existing actor-authoritative motion rule remains.

## Persistence and review-host rule

The actor snapshot validator will accept and canonicalize the new route marker, including old in-flight talk records. The review host's routine-session suppression will clear any lane pointer that references a removed session, so non-compact demo payloads remain valid.

## Non-goals

- No character artwork, world geometry, WorkSeat placement, bubble assets or reference hashes change.
- No change to speech line rotation, bubble fitting, standing-pair coordinate selection, endpoint-facing rules, emotion d6 or numeric emotion effects.
- No concurrent weighted recovery event is introduced while a speech overlay is active.
