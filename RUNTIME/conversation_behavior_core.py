from __future__ import annotations

"""Deterministic conversation movement, dialogue and presentation runtime.

Conversation state is transient: assignments, work ownership and the normal
work action remain authoritative while a visual conversation temporarily
borrows the actor pose.  The initial approved presentation is deliberately
small and predictable: one line per participant, the first bubble starts the
window, the partner follows after a short gap, both bubbles fade together,
then visitors return to their seats.
"""

import copy
import hashlib
import json
from bisect import bisect_right
from pathlib import Path
from typing import Any, Iterable

from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from CHARACTER.RUNTIME.character_system import CharacterSystemError
from RUNTIME.conversation_spot_core import ConversationSpotCore
from RUNTIME.crowd_movement_core import CrowdMovementReservationError, DynamicActorReservationCore
from RUNTIME.employee_registry import EmployeeMetadataError, EmployeeMetadataRegistry
from RUNTIME.work_seat_core import WorkSeatCore, WorkSeatError
from RUNTIME.work_seat_lifecycle import WorkSeatLifecycle, WorkSeatLifecycleError
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore
from WORLD.RUNTIME.pathfinding_core import PathfindingCore, PathfindingError


class ConversationBehaviorError(ValueError):
    pass


class ConversationBehaviorCore:
    SCHEMA = "gds.conversation_behavior_runtime.v1"
    SNAPSHOT_SCHEMA = "gds.conversation_actor_snapshot.v1"
    TICK_MS = 60
    PREVIEW_TALK_FRAMES = 8  # legacy compact timing input; not the active default
    DEFAULT_LOOP_COUNT = 1
    MAX_LOOP_COUNT = 8
    DEFAULT_SPEAKER_CADENCE = "staggered_persistent"
    DEFAULT_BUBBLE_VISIBLE_MS = 4000
    DEFAULT_SPEAKER_GAP_MS = 500
    DEFAULT_BUBBLE_FADE_MS = 300
    DEFAULT_EMOTION_HOLD_MS = 1200
    CEO_WORKSTATION_ID = "ceo"

    def __init__(
        self,
        root: str | Path,
        *,
        employee_registry: EmployeeMetadataRegistry | None = None,
        movement: CharacterMovementCore | None = None,
        navigation: NavigationOccupancyCore | None = None,
        pathfinding: PathfindingCore | None = None,
        work_seats: WorkSeatCore | None = None,
        work_seat_lifecycle: WorkSeatLifecycle | None = None,
        spots: ConversationSpotCore | None = None,
        crowd: DynamicActorReservationCore | None = None,
    ):
        self.root = Path(root).resolve()
        self.employee_registry = employee_registry or EmployeeMetadataRegistry(self.root)
        self.navigation = navigation or NavigationOccupancyCore(self.root / "WORLD")
        self.pathfinding = pathfinding or PathfindingCore(self.root / "WORLD", occupancy=self.navigation)
        self.movement = movement or CharacterMovementCore(
            self.root,
            pathfinding=self.pathfinding,
            employee_registry=self.employee_registry,
        )
        self.work_seats = work_seats or WorkSeatCore(self.root)
        self.work_seat_lifecycle = work_seat_lifecycle or WorkSeatLifecycle(
            self.root,
            movement=self.movement,
            navigation=self.navigation,
            pathfinding=self.pathfinding,
            work_seats=self.work_seats,
        )
        self.spots = spots or ConversationSpotCore(
            self.root,
            navigation=self.navigation,
            work_seats=self.work_seats,
            work_seat_lifecycle=self.work_seat_lifecycle,
        )
        self.crowd = crowd or DynamicActorReservationCore()
        self.contract = json.loads(
            (self.root / "CONTRACTS" / "conversation_behavior.json").read_text(encoding="utf-8")
        )
        coordinate_contract = self.contract.get("coordinate_contract", {})
        standing_contract = coordinate_contract.get("standing_pair", {})
        try:
            opener_offset = list(standing_contract.get("opener_bubble_extra_offset_px", [0, 0]))
        except TypeError as exc:
            raise ConversationBehaviorError("standing pair opener bubble offset must be a pair") from exc
        if len(opener_offset) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in opener_offset
        ):
            raise ConversationBehaviorError("standing pair opener bubble offset must contain two integers")
        self.standing_pair_opener_bubble_offset_px = list(opener_offset)
        try:
            visitor_offset = list(coordinate_contract.get("walking_visitor_bubble_extra_offset_px", [0, 0]))
        except TypeError as exc:
            raise ConversationBehaviorError("walking visitor bubble offset must be a pair") from exc
        if len(visitor_offset) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in visitor_offset
        ):
            raise ConversationBehaviorError("walking visitor bubble offset must contain two integers")
        self.walking_visitor_bubble_extra_offset_px = list(visitor_offset)
        timing_contract = self.contract.get("timing", {})
        try:
            self.default_bubble_visible_ms = int(
                timing_contract.get("default_bubble_visible_ms", self.DEFAULT_BUBBLE_VISIBLE_MS)
            )
            self.default_speaker_gap_ms = int(
                timing_contract.get("default_speaker_gap_ms", self.DEFAULT_SPEAKER_GAP_MS)
            )
            self.default_bubble_fade_ms = int(
                timing_contract.get("default_bubble_fade_ms", self.DEFAULT_BUBBLE_FADE_MS)
            )
        except (TypeError, ValueError) as exc:
            raise ConversationBehaviorError("conversation timing contract has invalid defaults") from exc
        if (
            self.default_bubble_visible_ms <= 0
            or self.default_speaker_gap_ms < 0
            or self.default_bubble_fade_ms < 0
        ):
            raise ConversationBehaviorError("conversation timing contract defaults are out of range")
        # Character frame counts are immutable for a canonical action request.
        # Conversation planning asks for the same work/move counts repeatedly;
        # keeping this cache local to the planner avoids re-reading sprite
        # sheets while retaining deterministic, in-process behaviour.
        self._frame_count_cache: dict[tuple[Any, ...], int] = {}

    @staticmethod
    def _uv(value: Iterable[int]) -> tuple[int, int]:
        cells = list(value)
        if len(cells) != 2:
            raise ConversationBehaviorError(f"Expected a UV pair, got {value!r}")
        return int(cells[0]), int(cells[1])

    @staticmethod
    def _json(value: Any) -> Any:
        if isinstance(value, tuple):
            return [ConversationBehaviorCore._json(item) for item in value]
        if isinstance(value, list):
            return [ConversationBehaviorCore._json(item) for item in value]
        if isinstance(value, dict):
            return {str(key): ConversationBehaviorCore._json(item) for key, item in value.items()}
        return value

    def _frame_count(
        self,
        character_id: str,
        action: str,
        direction: str | None,
        subaction: str | None = None,
    ) -> int:
        """Return a cached canonical frame count for planner tracks."""
        normalized_action = str(action)
        normalized_direction = None if direction is None else str(direction).upper()
        if normalized_action in {"happy", "sad"}:
            normalized_direction = None
            normalized_subaction = None
        elif normalized_action in {"move", "idle"}:
            normalized_subaction = None
        else:
            normalized_subaction = None if subaction is None else str(subaction)
        key = (
            str(character_id),
            normalized_action,
            normalized_direction,
            normalized_subaction,
        )
        cached = self._frame_count_cache.get(key)
        if cached is not None:
            return cached
        try:
            count = len(self.movement.characters.render(
                str(character_id),
                normalized_action,
                normalized_direction,
                normalized_subaction,
            ).frames)
        except (CharacterSystemError, CharacterMovementError, KeyError, TypeError, ValueError):
            count = 1
        count = max(1, int(count))
        self._frame_count_cache[key] = count
        return count

    @staticmethod
    def _assignment(row: dict[str, Any]) -> dict[str, Any]:
        assignment = row.get("assignment")
        if not isinstance(assignment, dict) or assignment.get("status") != "assigned":
            raise ConversationBehaviorError(f"{row.get('employee_id')}: employee is unassigned")
        return assignment

    def _actor_from_employee(self, row: dict[str, Any]) -> dict[str, Any]:
        assignment = self._assignment(row)
        workstation_id = str(assignment["workstation_id"])
        facing = str(assignment.get("facing") or "SE").upper()
        return {
            "employee_id": row["employee_id"],
            "character_id": row["character_id"],
            "floor_id": assignment["floor_id"],
            "workstation_id": workstation_id,
            "assignment_slot_id": assignment.get("slot_id"),
            "assignment_order": int(assignment.get("assignment_order", 0)),
            "role": "ceo" if workstation_id == self.CEO_WORKSTATION_ID else "employee",
            "presence": "present",
            "phase": "working",
            "current_uv": None,
            "direction": facing,
            "action": "work",
            "subaction": "normal_work",
            "render_owner": "work_seat",
            "workseat_state": "occupied",
            "path_cells_uv": [],
            "locked": False,
            "dialogue_visible": False,
            "dialogue_opacity": 0.0,
            "dialogue_phase": "hidden",
            "dialogue_bubble_offset_px": [0, 0],
        }

    def initial_snapshot(self, floor_id: str | None = None) -> dict[str, Any]:
        """Build a JSON-safe transient snapshot from immutable assignments."""
        try:
            rows = self.employee_registry.initial_roster(floor_id)
            by_id = {row["employee_id"]: self.employee_registry.get(row["employee_id"]) for row in rows}
        except EmployeeMetadataError as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        actors = {
            employee_id: self._actor_from_employee(by_id[employee_id])
            for employee_id in sorted(by_id, key=lambda key: (int(by_id[key]["assignment"]["assignment_order"]), key))
        }
        return {
            "schema": self.SNAPSHOT_SCHEMA,
            "version": 1,
            "clock_ms": 0,
            "actors": actors,
            "locks": {
                "participant_lock": [],
                "talk_slot_lock": [],
            },
            "conversation_id": None,
            "active_conversation": None,
        }

    def validate_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict) or snapshot.get("schema") != self.SNAPSHOT_SCHEMA:
            raise ConversationBehaviorError("snapshot schema must be gds.conversation_actor_snapshot.v1")
        actors = snapshot.get("actors")
        if not isinstance(actors, dict):
            raise ConversationBehaviorError("snapshot.actors must be an object")
        seen_slots: set[str] = set()
        for employee_id, actor in actors.items():
            if not isinstance(actor, dict) or actor.get("employee_id") != employee_id:
                raise ConversationBehaviorError(f"snapshot actor key mismatch: {employee_id!r}")
            try:
                source = self.employee_registry.get(employee_id)
            except EmployeeMetadataError as exc:
                raise ConversationBehaviorError(str(exc)) from exc
            assignment = self._assignment(source)
            expected = {
                "floor_id": assignment["floor_id"],
                "workstation_id": assignment["workstation_id"],
                "assignment_slot_id": assignment.get("slot_id"),
            }
            for key, value in expected.items():
                if actor.get(key) != value:
                    raise ConversationBehaviorError(
                        f"{employee_id}: snapshot assignment changed for {key}: {actor.get(key)!r} != {value!r}"
                    )
            slot = expected["assignment_slot_id"]
            if slot in seen_slots:
                raise ConversationBehaviorError(f"duplicate assignment slot in snapshot: {slot}")
            seen_slots.add(slot)
            if actor.get("phase") not in {
                "working", "talk_pending", "leaving_workseat", "walking_to_talk", "talk_arrival",
                "talking", "talk_complete", "returning_to_work", "cancelled", "no_path", "blocked", "self_talk",
            }:
                raise ConversationBehaviorError(f"{employee_id}: unknown actor phase {actor.get('phase')!r}")
        locks = snapshot.get("locks", {})
        if not isinstance(locks, dict):
            raise ConversationBehaviorError("snapshot.locks must be an object")
        for key in ("participant_lock", "talk_slot_lock"):
            if not isinstance(locks.get(key, []), list):
                raise ConversationBehaviorError(f"snapshot.locks.{key} must be a list")
        return copy.deepcopy(snapshot)

    def _ensure_snapshot(self, snapshot: dict[str, Any] | None, floor_id: str | None) -> dict[str, Any]:
        if snapshot is None:
            return self.initial_snapshot(floor_id)
        return self.validate_snapshot(snapshot)

    def resolve_conversation_timing(
        self,
        *,
        mode: str = "standing_pair",
        participant_ids: Iterable[str],
        initiator_id: str,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-safe speaker schedule without resolving geometry.

        This is the tuning seam for the caller/dashboard.  It deliberately
        does not inspect or mutate employee metadata, workstation occupancy or
        the navigation grid.
        """
        participants = [str(employee_id) for employee_id in participant_ids]
        if len(set(participants)) != len(participants):
            raise ConversationBehaviorError("conversation timing participants must be unique")
        return self._json(self._resolve_timing(
            mode=str(mode),
            participants=participants,
            initiator_id=str(initiator_id),
            talk_frames=talk_frames,
            timing=timing,
        ))

    def _employee(self, employee_id: str) -> dict[str, Any]:
        try:
            row = self.employee_registry.get(employee_id)
        except EmployeeMetadataError as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        self._assignment(row)
        return row

    def _dialogue_lines(
        self,
        *,
        locale: str,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return enabled office lines from the live editable catalog.

        The catalog intentionally stores one localized line per dialogue ID;
        pairing is a behavior concern.  ``conversation_open`` and
        ``conversation_reply`` are the authored pair pools.  The fallback pool
        is still deterministic and fit-gated, so adding/editing CSV content
        does not require a code change.
        """
        try:
            rows = self.movement.characters.dialogue.list(
                locale=locale,
                category=category,
                usage_scope="office",
                enabled_only=True,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        return [line.as_dict() for line in rows]

    @staticmethod
    def _stable_dialogue_index(seed: str, size: int) -> int:
        if size <= 0:
            raise ConversationBehaviorError("dialogue selection pool is empty")
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % size

    def resolve_conversation_dialogue(
        self,
        *,
        mode: str = "standing_pair",
        participant_ids: Iterable[str],
        initiator_id: str,
        locale: str = "en",
        category: str | None = None,
        selection_seed: str | int = "0",
        start_speaker_id: str | None = None,
        dialogue_line_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Select one line per speaker without mutating gameplay state.

        A pair uses an opening line for the first speaker and a reply line for
        the partner.  Self-talk uses a general office line (never the pair
        opening/reply pools unless the caller explicitly asks for that
        category).  Selection is a stable hash of the participant/event
        inputs; it is therefore reproducible in previews and live replay.
        """
        mode_key = str(mode).strip().casefold()
        participants = [str(value) for value in participant_ids]
        if not participants or len(set(participants)) != len(participants):
            raise ConversationBehaviorError("dialogue participants must be non-empty and unique")
        if initiator_id not in participants:
            raise ConversationBehaviorError("dialogue initiator must be a participant")
        if mode_key == "self_talk" and len(participants) != 1:
            raise ConversationBehaviorError("self_talk dialogue requires one participant")
        if mode_key != "self_talk" and len(participants) != 2:
            raise ConversationBehaviorError("pair dialogue requires one speaker and one partner")
        try:
            locale_key = str(locale).strip().casefold().replace("_", "-").split("-", 1)[0]
        except AttributeError as exc:
            raise ConversationBehaviorError("dialogue locale must be a string") from exc
        if not locale_key:
            raise ConversationBehaviorError("dialogue locale cannot be empty")

        start_speaker = str(start_speaker_id or initiator_id)
        if start_speaker not in participants:
            raise ConversationBehaviorError("dialogue start speaker must be a participant")
        order = [start_speaker] + [value for value in participants if value != start_speaker]
        seed_prefix = f"{mode_key}|{','.join(order)}|{selection_seed}|{locale_key}|{category or ''}"

        overrides = dialogue_line_overrides or {}

        def override_from_pool(pool: list[dict[str, Any]], employee_id: str) -> dict[str, Any] | None:
            """Resolve a scheduler-owned shuffle-bag choice from this pool.

            The conversation planner remains the authority for locale/category
            eligibility.  The speech scheduler may provide an exact line key so a
            persisted bag can guarantee every authored line is visited before
            refill; invalid keys deliberately fall back to the seeded choice.
            """
            raw = overrides.get(employee_id)
            if raw is None:
                return None
            if isinstance(raw, dict):
                override_id = raw.get("dialogue_id")
                override_index = raw.get("line_index", 0)
            else:
                override_id = raw
                override_index = 0
            if not isinstance(override_id, str):
                return None
            try:
                override_index = int(override_index)
            except (TypeError, ValueError):
                return None
            for row in pool:
                if (
                    row.get("dialogue_id") == override_id
                    and int(row.get("line_index", 0)) == override_index
                ):
                    return row
            return None

        if mode_key == "self_talk":
            if category:
                pool = self._dialogue_lines(locale=locale_key, category=category)
            else:
                pool = [
                    row for row in self._dialogue_lines(locale=locale_key)
                    if row.get("category") not in {"conversation_open", "conversation_reply"}
                ]
            if not pool:
                raise ConversationBehaviorError("no enabled general self-talk dialogue line")
            selected = override_from_pool(pool, order[0])
            if selected is None:
                selected = pool[self._stable_dialogue_index(seed_prefix, len(pool))]
            lines = [selected]
            selection_policy = "self_talk_general"
        else:
            if category:
                opening_pool = self._dialogue_lines(locale=locale_key, category=category)
                reply_pool = list(opening_pool)
                selection_policy = "pair_same_category_distinct_lines"
            else:
                opening_pool = self._dialogue_lines(locale=locale_key, category="conversation_open")
                reply_pool = self._dialogue_lines(locale=locale_key, category="conversation_reply")
                selection_policy = "pair_open_then_reply"
            if not opening_pool or not reply_pool:
                # A future content edit may temporarily remove one authored
                # pool.  Keep the behavior live by falling back to any two
                # different fit-gated office lines, while recording the
                # fallback in the returned contract for QA.
                fallback = self._dialogue_lines(locale=locale_key)
                fallback = [
                    row for row in fallback
                    if row.get("category") not in {"conversation_open", "conversation_reply"}
                ]
                if len(fallback) < 2:
                    raise ConversationBehaviorError("not enough enabled pair dialogue lines")
                opening_pool = fallback
                reply_pool = fallback
                selection_policy = "pair_general_distinct_lines_fallback"
            first = override_from_pool(opening_pool, order[0])
            if first is None:
                first = opening_pool[
                    self._stable_dialogue_index(seed_prefix + "|opening", len(opening_pool))
                ]
            second = override_from_pool(reply_pool, order[1])
            reply_start = self._stable_dialogue_index(seed_prefix + "|reply", len(reply_pool))
            if second is None:
                second = reply_pool[reply_start]
            if second.get("dialogue_id") == first.get("dialogue_id") and len(reply_pool) > 1:
                second = reply_pool[(reply_start + 1) % len(reply_pool)]
            if second.get("dialogue_id") == first.get("dialogue_id"):
                alternatives = [
                    row for row in self._dialogue_lines(locale=locale_key)
                    if row.get("dialogue_id") != first.get("dialogue_id")
                ]
                if not alternatives:
                    raise ConversationBehaviorError(
                        "pair dialogue selection requires two distinct enabled lines"
                    )
                second = alternatives[
                    self._stable_dialogue_index(seed_prefix + "|fallback", len(alternatives))
                ]
            lines = [first, second]

        lines_by_actor = {
            employee_id: dict(line)
            for employee_id, line in zip(order, lines)
        }
        return self._json({
            "schema": "gds.conversation_dialogue_selection.v1",
            "mode": mode_key,
            "locale": locale_key,
            "category": category,
            "selection_seed": str(selection_seed),
            "selection_policy": selection_policy,
            "start_speaker_id": start_speaker,
            "speaker_lines": [
                {"employee_id": employee_id, **lines_by_actor[employee_id]}
                for employee_id in order
            ],
            "lines_by_actor": lines_by_actor,
        })

    def _select_partner(self, snapshot: dict[str, Any], initiator_id: str) -> str | None:
        initiator = snapshot["actors"].get(initiator_id)
        if initiator is None:
            return None
        candidates = [
            actor for employee_id, actor in snapshot["actors"].items()
            if employee_id != initiator_id
            and actor.get("floor_id") == initiator.get("floor_id")
            and actor.get("role") == "employee"
            and actor.get("presence") == "present"
            and actor.get("phase") == "working"
            and not actor.get("locked")
        ]
        candidates.sort(key=lambda actor: (
            int(actor.get("assignment_order", 0)),
            str(actor.get("employee_id")),
        ))
        return candidates[0]["employee_id"] if candidates else None

    def _select_partner_seeded(
        self,
        snapshot: dict[str, Any],
        initiator_id: str,
        *,
        role: str,
        selection_seed: str | int,
        mode: str,
    ) -> str | None:
        """Select a currently free same-floor partner using a stable ticket."""
        initiator = snapshot["actors"].get(initiator_id)
        if initiator is None:
            return None
        candidates = [
            actor for employee_id, actor in snapshot["actors"].items()
            if employee_id != initiator_id
            and actor.get("floor_id") == initiator.get("floor_id")
            and actor.get("role") == role
            and actor.get("presence") == "present"
            and actor.get("phase") == "working"
            and not actor.get("locked")
        ]
        candidates.sort(key=lambda actor: (
            int(actor.get("assignment_order", 0)),
            str(actor.get("employee_id")),
        ))
        if not candidates:
            return None
        ticket = self._stable_dialogue_index(
            f"partner|{selection_seed}|{initiator_id}|{mode}", len(candidates)
        )
        return str(candidates[ticket]["employee_id"])

    def plan_automatic_conversation(
        self,
        initiator_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
        selection_seed: str | int = "0",
        dialogue_locale: str = "en",
        dialogue_seed: str | int | None = None,
        timing: dict[str, Any] | None = None,
        blocked_cells: Iterable[Iterable[int]] | None = None,
        reserved_cells: Iterable[Iterable[int]] | None = None,
    ) -> dict[str, Any]:
        """Choose one valid employee conversation mode and partner.

        The choice is uniform over modes with an eligible participant set;
        each candidate is then passed through the existing geometry/path
        planner.  A failed path/spot simply advances to the next deterministic
        candidate, never to an invented fallback.
        """
        state = self._ensure_snapshot(snapshot, None)
        initiator = state["actors"].get(initiator_id)
        if initiator is None:
            return self._json({"ready": False, "reason": "unknown_employee", "snapshot": state})
        if initiator.get("role") == "ceo":
            return self._json({"ready": False, "reason": "ceo_outbound", "snapshot": state})
        if initiator.get("phase") != "working" or initiator.get("locked"):
            return self._json({"ready": False, "reason": "actor_not_available", "snapshot": state})

        ceo_partner = self._select_partner_seeded(
            state, initiator_id, role="ceo", selection_seed=selection_seed, mode="ceo_front"
        )
        employee_partner = self._select_partner_seeded(
            state, initiator_id, role="employee", selection_seed=selection_seed, mode="employee"
        )
        available = []
        if ceo_partner is not None:
            available.append(("ceo_front", ceo_partner))
        if employee_partner is not None:
            available.extend((("seated_host", employee_partner), ("standing_pair", employee_partner)))
        if not available:
            return self._json({"ready": False, "reason": "no_valid_conversation_mode", "snapshot": state})

        # Stable hash ordering is a seeded uniform permutation, so the first
        # element is a random-looking mode while retries remain reproducible.
        available.sort(key=lambda row: self._stable_dialogue_index(
            f"mode|{selection_seed}|{initiator_id}|{row[0]}", 2**31 - 1
        ))
        selected_mode, selected_partner = available[0]
        attempts = list(available)
        selected_reason = "no_open_pair_slot"
        for mode, partner_id in attempts:
            plan = self.plan_conversation(
                initiator_id,
                partner_id=partner_id,
                mode=mode,
                snapshot=state,
                timing=timing,
                dialogue_locale=dialogue_locale,
                dialogue_seed=dialogue_seed if dialogue_seed is not None else selection_seed,
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
            )
            if plan.get("ready"):
                plan["automatic_selection"] = {
                    "selection_seed": str(selection_seed),
                    "available_modes": [item[0] for item in available],
                    "selected_mode": mode,
                    "selected_partner_id": partner_id,
                    "selection_policy": "uniform_valid_mode_then_seeded_partner",
                }
                return self._json(plan)
            selected_reason = str(plan.get("reason", selected_reason))
        return self._json({
            "ready": False,
            "reason": selected_reason,
            "available_modes": [item[0] for item in available],
            "snapshot": state,
        })

    def _check_lock_free(self, snapshot: dict[str, Any], participants: list[str], slot_id: str) -> str | None:
        participant_locks = set(snapshot.get("locks", {}).get("participant_lock", []))
        collision = sorted(participant_locks & set(participants))
        if collision:
            return "duplicate_participant_lock"
        slot_locks = set(snapshot.get("locks", {}).get("talk_slot_lock", []))
        if slot_id in slot_locks:
            return "duplicate_talk_slot_lock"
        for participant in participants:
            actor = snapshot["actors"].get(participant)
            if actor is None:
                return "unknown_employee"
            if actor.get("phase") != "working" or actor.get("presence") != "present" or actor.get("locked"):
                return "actor_not_available"
        return None

    def _resolve_timing(
        self,
        *,
        mode: str,
        participants: list[str],
        initiator_id: str,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize timing without coupling it to assignment or movement.

        The active policy is a single staggered exchange.  ``bubble_visible_ms``
        is measured from the first bubble appearing, not from the second
        speaker and not from the end of the walk.  Every visible bubble shares
        the same fade window, so the visitor starts walking back only after the
        global fade has completed.  ``talk_frames`` remains a deliberately
        supported compact legacy input for old review callers; it uses the old
        alternating-turn schedule and never changes the active default.
        """
        if not participants:
            raise ConversationBehaviorError("conversation timing requires at least one participant")
        if initiator_id not in participants:
            raise ConversationBehaviorError("conversation timing initiator must be a participant")
        if timing is not None and not isinstance(timing, dict):
            raise ConversationBehaviorError("timing must be an object when supplied")
        supplied = dict(timing or {})
        tick_ms = self.TICK_MS

        explicit_frames = supplied.get("talk_frames")
        if explicit_frames is not None and talk_frames is not None:
            try:
                frames_a = int(explicit_frames)
                frames_b = int(talk_frames)
            except (TypeError, ValueError) as exc:
                raise ConversationBehaviorError("talk_frames must be an integer") from exc
            if frames_a != frames_b:
                raise ConversationBehaviorError(
                    "timing.talk_frames conflicts with the talk_frames argument"
                )
        if explicit_frames is None:
            explicit_frames = talk_frames

        explicit_visible = supplied.get("bubble_visible_ms")
        explicit_duration = supplied.get("talk_duration_ms")
        if explicit_visible is not None and explicit_duration is not None:
            try:
                if int(explicit_visible) != int(explicit_duration):
                    raise ConversationBehaviorError(
                        "timing.bubble_visible_ms conflicts with timing.talk_duration_ms"
                    )
            except (TypeError, ValueError) as exc:
                raise ConversationBehaviorError(
                    "timing.bubble_visible_ms and timing.talk_duration_ms must be integers"
                ) from exc
        if explicit_visible is None:
            explicit_visible = explicit_duration

        # A caller using only the old talk_frames seam gets the compact
        # alternating schedule used by the original review GIFs.  New callers
        # omit it (or use bubble_visible_ms/talk_duration_ms) and receive the
        # approved four-second persistent-bubble exchange.
        legacy_compact = explicit_visible is None and explicit_frames is not None
        if explicit_visible is not None:
            try:
                bubble_visible_ms = int(explicit_visible)
            except (TypeError, ValueError) as exc:
                raise ConversationBehaviorError(
                    "timing.bubble_visible_ms must be an integer"
                ) from exc
            if bubble_visible_ms <= 0:
                raise ConversationBehaviorError(
                    "timing.bubble_visible_ms must be positive"
                )
            if explicit_frames is not None:
                try:
                    frames_value = int(explicit_frames)
                except (TypeError, ValueError) as exc:
                    raise ConversationBehaviorError("talk_frames must be an integer") from exc
                if frames_value * tick_ms != bubble_visible_ms:
                    raise ConversationBehaviorError(
                        "timing.talk_duration_ms conflicts with timing.talk_frames"
                    )
            frames = max(1, (bubble_visible_ms + tick_ms - 1) // tick_ms)
            source = "explicit_bubble_visible_ms"
        elif explicit_frames is not None:
            try:
                frames = int(explicit_frames)
            except (TypeError, ValueError) as exc:
                raise ConversationBehaviorError("talk_frames must be an integer") from exc
            if frames <= 0:
                raise ConversationBehaviorError("talk_frames must be positive")
            bubble_visible_ms = frames * tick_ms
            source = "explicit_talk_frames"
        else:
            bubble_visible_ms = self.default_bubble_visible_ms
            frames = max(1, (bubble_visible_ms + tick_ms - 1) // tick_ms)
            source = "approved_default"

        if supplied.get("talk_duration_ms") is None and supplied.get("duration_ms") is not None:
            raise ConversationBehaviorError("use timing.talk_duration_ms instead of timing.duration_ms")

        try:
            loop_count = int(supplied.get("loop_count", self.DEFAULT_LOOP_COUNT))
        except (TypeError, ValueError) as exc:
            raise ConversationBehaviorError("timing.loop_count must be an integer") from exc
        if loop_count < 1 or loop_count > self.MAX_LOOP_COUNT:
            raise ConversationBehaviorError(
                f"timing.loop_count must be between 1 and {self.MAX_LOOP_COUNT}"
            )

        cadence = str(
            supplied.get("speaker_cadence", self.DEFAULT_SPEAKER_CADENCE)
        ).strip().casefold()
        allowed_cadences = {self.DEFAULT_SPEAKER_CADENCE}
        if legacy_compact:
            allowed_cadences.add("alternating_equal")
        if cadence not in allowed_cadences:
            raise ConversationBehaviorError(
                f"unsupported speaker cadence: {cadence!r}; expected one of {sorted(allowed_cadences)!r}"
            )

        start_speaker = str(supplied.get("start_speaker_id", initiator_id))
        if start_speaker not in participants:
            raise ConversationBehaviorError("timing.start_speaker_id must be a participant")

        order = [start_speaker] + [employee_id for employee_id in participants if employee_id != start_speaker]
        listener_for = {
            speaker_id: next(
                (employee_id for employee_id in order if employee_id != speaker_id),
                None,
            )
            for speaker_id in order
        }

        if legacy_compact:
            # Preserve the old explicit frame seam for existing callers and
            # review tooling.  It is opt-in and is intentionally not the
            # default runtime policy.
            speaker_sequence = (
                order * loop_count
                if len(order) == 1
                else [order[index % len(order)] for index in range(len(order) * loop_count)]
            )
            turn_count = len(speaker_sequence)
            base_duration = bubble_visible_ms // turn_count
            remainder = bubble_visible_ms % turn_count
            segments: list[dict[str, Any]] = []
            cursor = 0
            for turn_index, speaker_id in enumerate(speaker_sequence):
                segment_duration = base_duration + (1 if turn_index < remainder else 0)
                segments.append({
                    "turn_index": turn_index,
                    "loop_index": turn_index // len(order),
                    "speaker_id": speaker_id,
                    "listener_id": listener_for[speaker_id],
                    "start_offset_ms": cursor,
                    "end_offset_ms": cursor + segment_duration,
                })
                cursor += segment_duration
            return {
                "mode": str(mode),
                "source": source,
                "schedule_style": "alternating_turns",
                "tick_ms": tick_ms,
                "talk_frames": frames,
                "bubble_visible_ms": bubble_visible_ms,
                "speaker_gap_ms": 0,
                "bubble_fade_ms": 0,
                "talk_duration_ms": bubble_visible_ms,
                "loop_count": loop_count,
                "speaker_cadence": "alternating_equal",
                "start_speaker_id": start_speaker,
                "speaker_sequence": speaker_sequence,
                "turn_count": turn_count,
                "sub_tick_turns": bubble_visible_ms < turn_count * tick_ms,
                "segments": segments,
                "preview_only": True,
                "tuning_status": "legacy_compatibility",
            }

        if loop_count != self.DEFAULT_LOOP_COUNT:
            raise ConversationBehaviorError(
                "the approved persistent-bubble exchange supports loop_count=1; "
                "use the legacy talk_frames seam for compact review loops"
            )
        if len(order) > 2:
            raise ConversationBehaviorError(
                "persistent-bubble conversations support one speaker and one partner"
            )
        try:
            speaker_gap_ms = int(supplied.get("speaker_gap_ms", self.default_speaker_gap_ms))
            bubble_fade_ms = int(supplied.get("bubble_fade_ms", supplied.get("fade_ms", self.default_bubble_fade_ms)))
        except (TypeError, ValueError) as exc:
            raise ConversationBehaviorError(
                "timing.speaker_gap_ms and timing.bubble_fade_ms must be integers"
            ) from exc
        if speaker_gap_ms < 0:
            raise ConversationBehaviorError("timing.speaker_gap_ms must be >= 0")
        if bubble_fade_ms < 0:
            raise ConversationBehaviorError("timing.bubble_fade_ms must be >= 0")
        if len(order) > 1 and speaker_gap_ms > bubble_visible_ms:
            raise ConversationBehaviorError(
                "timing.speaker_gap_ms must not exceed bubble_visible_ms"
            )
        try:
            first_delay_ms = int(supplied.get("first_bubble_delay_ms", 0))
        except (TypeError, ValueError) as exc:
            raise ConversationBehaviorError(
                "timing.first_bubble_delay_ms must be an integer"
            ) from exc
        if first_delay_ms < 0:
            raise ConversationBehaviorError("timing.first_bubble_delay_ms must be >= 0")
        fade_start_offset_ms = first_delay_ms + bubble_visible_ms
        fade_end_offset_ms = fade_start_offset_ms + bubble_fade_ms
        speaker_sequence = list(order)
        turn_count = len(speaker_sequence)
        segments = []
        for turn_index, speaker_id in enumerate(speaker_sequence):
            start_offset_ms = first_delay_ms + (speaker_gap_ms * turn_index)
            segments.append({
                "turn_index": turn_index,
                "loop_index": 0,
                "speaker_id": speaker_id,
                "listener_id": listener_for[speaker_id],
                "start_offset_ms": start_offset_ms,
                "end_offset_ms": fade_end_offset_ms,
                "bubble_start_offset_ms": start_offset_ms,
                "bubble_visible_end_offset_ms": fade_start_offset_ms,
                "fade_start_offset_ms": fade_start_offset_ms,
                "fade_end_offset_ms": fade_end_offset_ms,
            })

        return {
            "mode": str(mode),
            "source": source,
            "schedule_style": "persistent_bubbles",
            "tick_ms": tick_ms,
            "talk_frames": max(1, (fade_end_offset_ms + tick_ms - 1) // tick_ms),
            "bubble_visible_ms": bubble_visible_ms,
            "speaker_gap_ms": speaker_gap_ms,
            "bubble_fade_ms": bubble_fade_ms,
            "first_bubble_delay_ms": first_delay_ms,
            "fade_start_offset_ms": fade_start_offset_ms,
            "fade_end_offset_ms": fade_end_offset_ms,
            "talk_duration_ms": fade_end_offset_ms,
            "loop_count": loop_count,
            "speaker_cadence": cadence,
            "start_speaker_id": start_speaker,
            "speaker_sequence": speaker_sequence,
            "turn_count": turn_count,
            "sub_tick_turns": False,
            "segments": segments,
            "preview_only": False,
            "tuning_status": "author_approved_initial",
        }

    def _reserve(
        self,
        snapshot: dict[str, Any],
        participants: list[str],
        slot_id: str,
        conversation_id: str,
    ) -> dict[str, Any]:
        reserved = copy.deepcopy(snapshot)
        reserved.setdefault("locks", {}).setdefault("participant_lock", []).extend(participants)
        reserved["locks"].setdefault("talk_slot_lock", []).append(slot_id)
        reserved["conversation_id"] = conversation_id
        reserved["active_conversation"] = conversation_id
        for participant in participants:
            reserved["actors"][participant]["locked"] = True
            reserved["actors"][participant]["phase"] = "talk_pending"
        return reserved

    @staticmethod
    def _pair_assignment(
        actors: list[dict[str, Any]],
        endpoints: list[tuple[int, int]],
    ) -> list[tuple[str, tuple[int, int]]]:
        if len(actors) != 2 or len(endpoints) != 2:
            raise ConversationBehaviorError("standing pair requires exactly two actors and endpoints")
        ordered = sorted(actors, key=lambda actor: (int(actor.get("assignment_order", 0)), actor["employee_id"]))
        return [(ordered[0]["employee_id"], endpoints[0]), (ordered[1]["employee_id"], endpoints[1])]

    def _gate(self, actor: dict[str, Any]) -> tuple[int, int]:
        try:
            slot = self.work_seat_lifecycle.resolve_interaction_slot(
                actor["floor_id"], actor["workstation_id"]
            )
        except (WorkSeatLifecycleError, WorkSeatError, KeyError, ValueError) as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        gate = slot.get("transition_gate_uv")
        if gate is None:
            raise ConversationBehaviorError(
                f"{actor['floor_id']}.{actor['workstation_id']}: missing transition gate"
            )
        return self._uv(gate)

    def _path(self, floor_id: str, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        try:
            result = self.pathfinding.find_path(floor_id, start, goal)
        except (PathfindingError, KeyError, ValueError) as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        return [self._uv(cell) for cell in result["path_cells_uv"]]

    def _track_state(
        self,
        actor: dict[str, Any],
        *,
        phase: str,
        timestamp_ms: int,
        action: str,
        direction: str,
        render_owner: str,
        current_uv: tuple[int, int] | None = None,
        ground_xy: Iterable[float] | None = None,
        path_cells_uv: Iterable[tuple[int, int]] | None = None,
        dialogue_visible: bool = False,
        dialogue_opacity: float = 0.0,
        dialogue_phase: str = "hidden",
        dialogue_id: str | None = None,
        dialogue_line_index: int | None = None,
        dialogue_text: str | None = None,
        dialogue_locale: str | None = None,
        dialogue_bubble_offset_px: Iterable[int] | None = None,
        workseat_state: str = "free",
        frame_index: int = 0,
        cumulative_distance_px: float | None = None,
        subaction: str | None = None,
        speaker_id: str | None = None,
        listener_id: str | None = None,
        loop_index: int | None = None,
        turn_index: int | None = None,
    ) -> dict[str, Any]:
        state = {
            "employee_id": actor["employee_id"],
            "character_id": actor["character_id"],
            "floor_id": actor["floor_id"],
            "phase": phase,
            "timestamp_ms": int(timestamp_ms),
            "action": action,
            "direction": str(direction).upper(),
            "raw_direction": str(direction).upper(),
            "render_owner": render_owner,
            "current_uv": list(current_uv) if current_uv is not None else None,
            "ground_xy": list(ground_xy) if ground_xy is not None else None,
            "path_cells_uv": [list(cell) for cell in (path_cells_uv or ())],
            "dialogue_visible": bool(dialogue_visible),
            "dialogue_opacity": round(max(0.0, min(1.0, float(dialogue_opacity))), 4),
            "dialogue_phase": str(dialogue_phase),
            "workseat_state": workseat_state,
            "seated_visible": render_owner == "work_seat",
            "walking_visible": render_owner == "walking_depth",
            "frame_index": int(frame_index),
            "cumulative_distance_px": (
                round(float(cumulative_distance_px), 4)
                if cumulative_distance_px is not None else None
            ),
        }
        if ground_xy is not None:
            state["ground_anchor_px"] = [16, 31]
        if subaction is not None:
            state["subaction"] = str(subaction)
        if dialogue_id is not None:
            state["dialogue_id"] = str(dialogue_id)
        if dialogue_line_index is not None:
            state["dialogue_line_index"] = int(dialogue_line_index)
        if dialogue_text is not None:
            state["dialogue_text"] = str(dialogue_text)
        if dialogue_locale is not None:
            state["dialogue_locale"] = str(dialogue_locale)
        if dialogue_bubble_offset_px is not None:
            offset = list(dialogue_bubble_offset_px)
            if len(offset) != 2:
                raise ConversationBehaviorError(
                    "dialogue_bubble_offset_px must contain two values"
                )
            state["dialogue_bubble_offset_px"] = [int(offset[0]), int(offset[1])]
        if speaker_id is not None:
            state["speaker_id"] = str(speaker_id)
        if listener_id is not None:
            state["listener_id"] = str(listener_id)
        if loop_index is not None:
            state["loop_index"] = int(loop_index)
        if turn_index is not None:
            state["turn_index"] = int(turn_index)
        return state

    def _movement_track(
        self,
        actor: dict[str, Any],
        path: list[tuple[int, int]],
        *,
        phase: str,
        start_ms: int,
        end_phase: str | None = None,
        end_direction: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            profile = self.movement.resolve_employee_movement_profile(actor["employee_id"])
            samples = self.movement.sample_path_timeline(
                path,
                speed_multiplier=float(profile["speed_multiplier"]),
                tick_ms=int(profile["playback_tick_ms"]),
            )
        except (CharacterMovementError, ValueError) as exc:
            raise ConversationBehaviorError(str(exc)) from exc
        states: list[dict[str, Any]] = []
        for sample in samples:
            direction = str(sample.get("visual_direction") or sample["direction"]).upper()
            frame_count = self._frame_count(actor["character_id"], "move", direction)
            frame = self.movement.walk_cycle_frame_index(
                float(sample["cumulative_distance_px"]),
                max(1, frame_count),
                frame_distance_cells=float(profile["walk_frame_distance_cells"]),
            )
            states.append(self._track_state(
                actor,
                phase=phase,
                timestamp_ms=start_ms + int(sample["elapsed_ms"]),
                action="move",
                direction=direction,
                render_owner="walking_depth",
                current_uv=self._uv(sample["to_uv"]),
                ground_xy=sample["ground_xy"],
                path_cells_uv=path,
                frame_index=frame,
                cumulative_distance_px=sample["cumulative_distance_px"],
            ))
        elapsed = int(samples[-1]["elapsed_ms"]) if samples else 0
        if end_phase is not None:
            endpoint = path[-1]
            states.append(self._track_state(
                actor,
                phase=end_phase,
                timestamp_ms=start_ms + elapsed,
                action="idle",
                direction=end_direction or (states[-1]["direction"] if states else actor["direction"]),
                render_owner="walking_depth",
                current_uv=endpoint,
                ground_xy=self.movement.uv_cell_center_to_pixel(*endpoint),
                path_cells_uv=path,
                workseat_state="free",
            ))
        return states, start_ms + elapsed

    def _hold_state(
        self,
        actor: dict[str, Any],
        *,
        states: list[dict[str, Any]],
        phase: str,
        start_ms: int,
        end_ms: int,
        direction: str,
        endpoint: tuple[int, int] | None,
        dialogue_visible: bool,
        dialogue_opacity: float = 0.0,
        dialogue_phase: str = "hidden",
        dialogue_line: dict[str, Any] | None = None,
        dialogue_bubble_offset_px: Iterable[int] | None = None,
        render_owner: str = "walking_depth",
        action: str | None = None,
        subaction: str | None = None,
        speaker_id: str | None = None,
        listener_id: str | None = None,
        loop_index: int | None = None,
        turn_index: int | None = None,
    ) -> None:
        if end_ms < start_ms:
            return
        xy = self.movement.uv_cell_center_to_pixel(*endpoint) if endpoint is not None else None
        states.append(self._track_state(
            actor,
            phase=phase,
            timestamp_ms=end_ms,
            action=action or ("idle" if render_owner == "walking_depth" else "work"),
            direction=direction,
            render_owner=render_owner,
            current_uv=endpoint,
            ground_xy=xy,
            dialogue_visible=dialogue_visible,
            dialogue_opacity=dialogue_opacity,
            dialogue_phase=dialogue_phase,
            dialogue_id=(dialogue_line or {}).get("dialogue_id"),
            dialogue_line_index=(dialogue_line or {}).get("line_index"),
            dialogue_text=(dialogue_line or {}).get("text"),
            dialogue_locale=(dialogue_line or {}).get("locale"),
            dialogue_bubble_offset_px=dialogue_bubble_offset_px,
            workseat_state="free" if render_owner == "walking_depth" else "occupied",
            subaction=subaction,
            speaker_id=speaker_id,
            listener_id=listener_id,
            loop_index=loop_index,
            turn_index=turn_index,
        ))

    def _working_state(
        self,
        actor: dict[str, Any],
        timestamp_ms: int,
        *,
        subaction: str = "normal_work",
        direction: str | None = None,
    ) -> dict[str, Any]:
        return self._track_state(
            actor,
            phase="working",
            timestamp_ms=timestamp_ms,
            action="work",
            direction=direction or actor["direction"],
            render_owner="work_seat",
            workseat_state="occupied",
            subaction=subaction,
        )

    def _append_talk_states(
        self,
        actor: dict[str, Any],
        states: list[dict[str, Any]],
        *,
        talk_start_ms: int,
        talk_end_ms: int,
        talk_segments: list[dict[str, Any]],
        direction: str,
        endpoint: tuple[int, int] | None,
        render_owner: str,
        action: str,
        subaction: str | None,
        talk_phase: str = "talking",
        dialogue_by_actor: dict[str, dict[str, Any]] | None = None,
        bubble_offset_px: Iterable[int] | None = None,
    ) -> None:
        """Append deterministic visual talk states for one actor.

        Persistent-bubble timing keeps the actor in a single idle/work pose.
        The first state marks the shared talk window, each speaker's bubble
        starts at its staggered offset, and opacity samples are emitted at the
        simulation tick during the global fade.  The legacy alternating path
        is retained for explicit ``talk_frames`` review callers.
        """
        if not talk_segments:
            return
        by_actor = dialogue_by_actor or {}
        # schedule_style lives on timing, not each segment.  The caller may
        # attach it to the first segment for direct helper use; otherwise the
        # presence of bubble offsets identifies the active policy.
        persistent = "bubble_start_offset_ms" in talk_segments[0]
        first = talk_segments[0]

        def append_state(
            timestamp_ms: int,
            *,
            phase: str,
            visible: bool,
            opacity: float,
            segment: dict[str, Any],
            dialogue_phase_override: str | None = None,
        ) -> None:
            speaker_id = segment.get("speaker_id")
            line = by_actor.get(str(speaker_id)) if speaker_id is not None else None
            self._hold_state(
                actor,
                states=states,
                phase=phase,
                start_ms=timestamp_ms,
                end_ms=timestamp_ms,
                direction=direction,
                endpoint=endpoint,
                dialogue_visible=visible,
                dialogue_opacity=opacity,
                dialogue_phase=dialogue_phase_override or (
                    "visible" if visible and phase in {"talking", "self_talk"} else phase
                ),
                dialogue_line=line if visible else None,
                render_owner=render_owner,
                action=action,
                subaction=subaction,
                dialogue_bubble_offset_px=bubble_offset_px,
                speaker_id=speaker_id,
                listener_id=segment.get("listener_id"),
                loop_index=segment.get("loop_index"),
                turn_index=segment.get("turn_index"),
            )

        if not persistent:
            for segment in talk_segments:
                segment_start = talk_start_ms + int(segment["start_offset_ms"])
                segment_end = talk_start_ms + int(segment["end_offset_ms"])
                append_state(
                    segment_start,
                    phase=talk_phase,
                    visible=actor["employee_id"] == segment.get("speaker_id"),
                    opacity=1.0 if actor["employee_id"] == segment.get("speaker_id") else 0.0,
                    segment=segment,
                )
                append_state(
                    segment_end,
                    phase=talk_phase,
                    visible=actor["employee_id"] == segment.get("speaker_id"),
                    opacity=1.0 if actor["employee_id"] == segment.get("speaker_id") else 0.0,
                    segment=segment,
                )
            return

        # Both actors enter the same conversation hold at the first bubble
        # boundary.  The listener is deliberately hidden until its own line
        # starts; it still carries the pair's speaker/listener metadata.
        append_state(
            talk_start_ms,
            phase=talk_phase,
            visible=False,
            opacity=0.0,
            segment=first,
        )
        actor_id = actor["employee_id"]
        own_segments = [
            segment for segment in talk_segments
            if str(segment.get("speaker_id")) == actor_id
        ]
        if not own_segments:
            return
        own = own_segments[0]
        bubble_start = talk_start_ms + int(own.get("bubble_start_offset_ms", own["start_offset_ms"]))
        fade_start = talk_start_ms + int(own.get("fade_start_offset_ms", talk_end_ms - talk_start_ms))
        fade_end = talk_start_ms + int(own.get("fade_end_offset_ms", talk_end_ms - talk_start_ms))
        if bubble_start <= talk_end_ms:
            append_state(
                bubble_start,
                phase=talk_phase,
                visible=True,
                opacity=1.0,
                segment=own,
            )
        if fade_start < bubble_start:
            fade_start = bubble_start
        if fade_end < fade_start:
            fade_end = fade_start
        append_state(
            fade_start,
            phase=talk_phase,
            visible=True if fade_end > fade_start else False,
            opacity=1.0 if fade_end > fade_start else 0.0,
            segment=own,
            dialogue_phase_override="fading" if fade_end > fade_start else "hidden",
        )
        if fade_end > fade_start:
            fade_samples = list(range(fade_start + self.TICK_MS, fade_end, self.TICK_MS))
            fade_samples.append(fade_end)
            for timestamp_ms in sorted(set(fade_samples)):
                progress = (timestamp_ms - fade_start) / max(1, fade_end - fade_start)
                opacity = max(0.0, min(1.0, 1.0 - progress))
                append_state(
                    timestamp_ms,
                    phase=talk_phase,
                    visible=opacity > 0,
                    opacity=opacity,
                    segment=own,
                    dialogue_phase_override="fading" if opacity > 0 else "hidden",
                )
        else:
            append_state(
                fade_end,
                phase=talk_phase,
                visible=False,
                opacity=0.0,
                segment=own,
                dialogue_phase_override="hidden",
            )

    def _build_host_track(
        self,
        host: dict[str, Any],
        *,
        talk_start_ms: int,
        talk_end_ms: int,
        talk_segments: list[dict[str, Any]],
        host_subaction: str,
        dialogue_by_actor: dict[str, dict[str, Any]],
        bubble_offset_px: Iterable[int] | None = None,
    ) -> list[dict[str, Any]]:
        """Hold a seated host in its normal or outward turn-side Work pose."""
        states = [self._working_state(host, 0)]
        self._append_talk_states(
            host,
            states,
            talk_start_ms=talk_start_ms,
            talk_end_ms=talk_end_ms,
            talk_segments=talk_segments,
            direction=host["direction"],
            endpoint=None,
            render_owner="work_seat",
            action="work",
            subaction=host_subaction,
            dialogue_by_actor=dialogue_by_actor,
            bubble_offset_px=bubble_offset_px,
        )
        states.append(self._working_state(host, talk_end_ms))
        return states

    def _build_track(
        self,
        actor: dict[str, Any],
        endpoint: tuple[int, int],
        endpoint_facing: str,
        *,
        talk_start_ms: int,
        talk_end_ms: int,
        talk_segments: list[dict[str, Any]] | None = None,
        dialogue_by_actor: dict[str, dict[str, Any]] | None = None,
        bubble_offset_px: Iterable[int] | None = None,
        post_talk_hold_ms: int = 0,
        post_talk_action: str | None = None,
        return_to_work: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        gate = self._gate(actor)
        outbound = self._path(actor["floor_id"], gate, endpoint)
        inbound = self._path(actor["floor_id"], endpoint, gate) if return_to_work else []
        states = [self._working_state(actor, 0)]
        states.append(self._track_state(
            actor,
            phase="leaving_workseat",
            timestamp_ms=self.TICK_MS,
            action="idle",
            direction=actor["direction"],
            render_owner="walking_depth",
            current_uv=gate,
            ground_xy=self.movement.uv_cell_center_to_pixel(*gate),
            path_cells_uv=[gate],
            workseat_state="free",
        ))
        outbound_states, arrival_ms = self._movement_track(
            actor,
            outbound,
            phase="walking_to_talk",
            start_ms=self.TICK_MS,
            end_phase="talk_arrival",
            end_direction=endpoint_facing,
        )
        states.extend(outbound_states)
        self._hold_state(
            actor,
            states=states,
            phase="talk_arrival",
            start_ms=arrival_ms,
            end_ms=talk_start_ms,
            direction=endpoint_facing,
            endpoint=endpoint,
            dialogue_visible=False,
            action="idle",
            subaction="idle",
        )
        self._append_talk_states(
            actor,
            states,
            talk_start_ms=talk_start_ms,
            talk_end_ms=talk_end_ms,
            talk_segments=list(talk_segments or ()),
            direction=endpoint_facing,
            endpoint=endpoint,
            render_owner="walking_depth",
            action="idle",
            subaction="idle",
            dialogue_by_actor=dialogue_by_actor,
            bubble_offset_px=bubble_offset_px,
        )
        return_info = {
            "gate_uv": list(gate),
            "outbound_path_cells_uv": [list(cell) for cell in outbound],
            "inbound_path_cells_uv": [list(cell) for cell in inbound],
            "arrival_ms": arrival_ms,
        }
        if return_to_work:
            states.append(self._track_state(
                actor,
                phase="talk_complete",
                timestamp_ms=talk_end_ms,
                action=post_talk_action or "idle",
                direction=endpoint_facing,
                render_owner="walking_depth",
                current_uv=endpoint,
                ground_xy=self.movement.uv_cell_center_to_pixel(*endpoint),
                path_cells_uv=outbound,
                workseat_state="free",
                subaction=(post_talk_action if post_talk_action in {"sad", "happy"} else "idle"),
            ))
            return_start_ms = int(talk_end_ms) + max(0, int(post_talk_hold_ms))
            if return_start_ms > int(talk_end_ms):
                states.append(self._track_state(
                    actor,
                    phase="talk_complete",
                    timestamp_ms=return_start_ms,
                    action=post_talk_action or "idle",
                    direction=endpoint_facing,
                    render_owner="walking_depth",
                    current_uv=endpoint,
                    ground_xy=self.movement.uv_cell_center_to_pixel(*endpoint),
                    path_cells_uv=outbound,
                    workseat_state="free",
                    subaction=(post_talk_action if post_talk_action in {"sad", "happy"} else "idle"),
                ))
            inbound_states, return_ms = self._movement_track(
                actor,
                inbound,
                phase="returning_to_work",
                start_ms=return_start_ms,
                end_phase=None,
                end_direction=actor["direction"],
            )
            states.extend(inbound_states)
            states.append(self._working_state(actor, return_ms))
            return_info["return_ms"] = return_ms
            return_info["return_start_ms"] = return_start_ms
            if post_talk_action in {"sad", "happy"}:
                return_info["emotion"] = post_talk_action
                return_info["emotion_hold_ms"] = max(0, int(post_talk_hold_ms))
        return states, return_info

    def _timeline(
        self,
        tracks: dict[str, list[dict[str, Any]]],
        *,
        end_ms: int,
        tick_ms: int = TICK_MS,
    ) -> list[dict[str, Any]]:
        # Keep the fixed simulation cadence, but also expose authored event
        # boundaries (the 500 ms speaker gap and 4.0/4.3 s fade edges are not
        # multiples of 60 ms).  This makes the reducer and preview renderer
        # observe the exact same visual transitions.
        times = set(range(0, max(0, int(end_ms)) + int(tick_ms), int(tick_ms)))
        for states in tracks.values():
            times.update(
                int(row["timestamp_ms"])
                for row in states
                if 0 <= int(row.get("timestamp_ms", 0)) <= int(end_ms)
            )
        # Index each track once.  The previous implementation scanned every
        # state row for every timestamp, which made a 4–7 second talk plan
        # quadratic in the number of authored samples and blocked the live
        # HTTP tick.  ``bisect_right`` preserves the same "latest state at or
        # before timestamp" semantics in logarithmic time.
        indexed_tracks: dict[str, tuple[list[dict[str, Any]], list[int]]] = {}
        for employee_id, states in tracks.items():
            ordered = [
                (index, state) for index, state in enumerate(states)
                if isinstance(state, dict)
            ]
            ordered.sort(key=lambda item: (int(item[1].get("timestamp_ms", 0)), item[0]))
            rows = [state for _index, state in ordered]
            timestamps = [int(state.get("timestamp_ms", 0)) for state in rows]
            if rows:
                indexed_tracks[employee_id] = (rows, timestamps)

        timeline = []
        for timestamp in sorted(times):
            actors: dict[str, dict[str, Any]] = {}
            for employee_id, (states, timestamps) in indexed_tracks.items():
                state_index = bisect_right(timestamps, timestamp) - 1
                state = copy.deepcopy(states[max(0, state_index)])
                # A seated host remains in the normal Work action while the
                # speech scheduler owns its bubble.  Keep that action animated on
                # the authored 360 ms character clock instead of leaving the
                # first frame pinned for the whole conversation window.  Move
                # and explicit one-shot states already carry their own frame
                # index, so only the continuous work pose is derived here.
                if state.get("action") == "work":
                    frame_count = self._frame_count(
                        state["character_id"],
                        "work",
                        state.get("direction") or "SE",
                        state.get("subaction") or "normal_work",
                    )
                    state["frame_index"] = (int(timestamp) // 360) % max(1, frame_count)
                    state["character_frame_ms"] = 360
                actors[employee_id] = state
            timeline.append({"timestamp_ms": timestamp, "actors": actors})
        return timeline

    def _crowd_audit(self, tracks: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        specs = []
        for employee_id, states in tracks.items():
            visible = [
                row for row in states
                if row.get("phase") in {"walking_to_talk", "returning_to_work"}
                and row.get("ground_xy") is not None
            ]
            if visible:
                specs.append({"actor_id": employee_id, "states": visible})
        if len(specs) < 2:
            return {
                "checked": False,
                "collision_free": True,
                "reason": "single_visible_visitor_or_no_overlap",
            }
        try:
            result = self.crowd.schedule_trajectories(specs)
        except (CrowdMovementReservationError, ValueError) as exc:
            return {"checked": True, "collision_free": False, "reason": str(exc)}
        return {
            "checked": True,
            "collision_free": bool(result.get("collision_free", False)),
            "active_wait_ticks_total": int(result.get("active_wait_ticks_total", 0)),
            "pre_spawn_delay_ticks_total": int(result.get("pre_spawn_delay_ticks_total", 0)),
            "min_synchronized_distance_px": result.get("min_synchronized_distance_px"),
            "same_cell_conflicts": result.get("same_cell_conflicts", []),
            "head_clearance_conflicts": result.get("head_clearance_conflicts", []),
        }

    def plan_self_talk(
        self,
        initiator_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
        dialogue_locale: str = "en",
        dialogue_category: str | None = None,
        dialogue_seed: str | int = "0",
        dialogue_line_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self._ensure_snapshot(snapshot, None)
        actor = state["actors"].get(initiator_id)
        if actor is None:
            return {"ready": False, "reason": "unknown_employee", "snapshot": state}
        if actor["phase"] != "working" or actor.get("locked"):
            return {"ready": False, "reason": "actor_not_available", "snapshot": state}
        timing_plan = self._resolve_timing(
            mode="self_talk",
            participants=[initiator_id],
            initiator_id=initiator_id,
            talk_frames=talk_frames,
            timing=timing,
        )
        dialogue_plan = self.resolve_conversation_dialogue(
            mode="self_talk",
            participant_ids=[initiator_id],
            initiator_id=initiator_id,
            locale=dialogue_locale,
            category=dialogue_category,
            selection_seed=dialogue_seed,
            start_speaker_id=str(timing_plan["start_speaker_id"]),
            dialogue_line_overrides=dialogue_line_overrides,
        )
        talk_frames = int(timing_plan["talk_frames"])
        end_ms = int(timing_plan["talk_duration_ms"])
        talk_states = [self._working_state(actor, 0)]
        self._append_talk_states(
            actor,
            talk_states,
            talk_start_ms=0,
            talk_end_ms=end_ms,
            talk_segments=list(timing_plan["segments"]),
            direction=actor["direction"],
            endpoint=None,
            render_owner="work_seat",
            action="work",
            subaction="normal_work",
            talk_phase="self_talk",
            dialogue_by_actor=dialogue_plan["lines_by_actor"],
        )
        talk_states.append(self._working_state(actor, end_ms))
        tracks = {initiator_id: talk_states}
        conversation_id = f"conversation:self_talk:{initiator_id}"
        snapshot_after = copy.deepcopy(state)
        snapshot_after["clock_ms"] = end_ms
        return self._json({
            "ready": True,
            "schema": self.SCHEMA,
            "conversation_id": conversation_id,
            "mode": "self_talk",
            "floor_id": actor["floor_id"],
            "initiator_id": initiator_id,
            "participants": [initiator_id],
            "talk_start_ms": 0,
            "talk_end_ms": end_ms,
            "talk_frames": talk_frames,
            "talk_duration_ms": end_ms,
            "timing": timing_plan,
            "speaker_schedule": [
                {
                    **segment,
                    "start_ms": int(segment["start_offset_ms"]),
                    "end_ms": int(segment["end_offset_ms"]),
                    "dialogue_id": dialogue_plan["lines_by_actor"].get(
                        str(segment.get("speaker_id")), {}
                    ).get("dialogue_id"),
                    "dialogue_line_index": dialogue_plan["lines_by_actor"].get(
                        str(segment.get("speaker_id")), {}
                    ).get("line_index"),
                    "dialogue_text": dialogue_plan["lines_by_actor"].get(
                        str(segment.get("speaker_id")), {}
                    ).get("text"),
                    "dialogue_locale": dialogue_plan["lines_by_actor"].get(
                        str(segment.get("speaker_id")), {}
                    ).get("locale"),
                    **({
                        "bubble_start_ms": int(segment["bubble_start_offset_ms"]),
                        "bubble_visible_end_ms": int(segment["bubble_visible_end_offset_ms"]),
                        "fade_start_ms": int(segment["fade_start_offset_ms"]),
                        "fade_end_ms": int(segment["fade_end_offset_ms"]),
                    } if "bubble_start_offset_ms" in segment else {}),
                }
                for segment in timing_plan["segments"]
            ],
            "dialogue": dialogue_plan,
            "dialogue_by_actor": dialogue_plan["lines_by_actor"],
            "dialogue_layout_policy": "direct_head_anchor_overlay_paint_order",
            "pose_bindings": {
                initiator_id: {
                    "render_owner": "work_seat",
                    "action": "work",
                    "subaction": "normal_work",
                    "role": "seated_speaker",
                }
            },
            "emotion": {
                "outcome": None,
                "roll": None,
                "hold_ms": 0,
                "stamina_effect_hook": "actor_snapshot_numeric_delta",
                "stamina_effect_milli_by_emotion": {"sad": -1000, "happy": 2000},
                "starts_after": "bubble_fade_end",
                "return_after": True,
            },
            "loop_count": int(timing_plan["loop_count"]),
            "preview_only_timing": bool(timing_plan["preview_only"]),
            "tracks": tracks,
            "timeline": self._timeline(tracks, end_ms=end_ms),
            "snapshot_before": state,
            "snapshot_after": snapshot_after,
            "locks": {"participant_lock": [], "talk_slot_lock": []},
            "events": [
                {"timestamp_ms": 0, "phase": "working"},
                {"timestamp_ms": 0, "phase": "self_talk"},
                {"timestamp_ms": end_ms, "phase": "working"},
            ],
        })

    def plan_conversation(
        self,
        initiator_id: str,
        *,
        partner_id: str | None = None,
        mode: str | None = None,
        snapshot: dict[str, Any] | None = None,
        floor_id: str | None = None,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
        dialogue_locale: str = "en",
        dialogue_category: str | None = None,
        dialogue_seed: str | int = "0",
        dialogue_line_overrides: dict[str, Any] | None = None,
        emotion_roll: int | None = None,
        gap_cells: int | None = None,
        blocked_cells: Iterable[Iterable[int]] | None = None,
        reserved_cells: Iterable[Iterable[int]] | None = None,
        origin_uvs: Iterable[Iterable[int]] | None = None,
    ) -> dict[str, Any]:
        state = self._ensure_snapshot(snapshot, floor_id)
        initiator = state["actors"].get(initiator_id)
        if initiator is None:
            return self._json({"ready": False, "reason": "unknown_employee", "snapshot": state})
        if mode is None:
            if partner_id is not None and partner_id in state["actors"] and state["actors"][partner_id]["role"] == "ceo":
                mode = "ceo_front"
            elif initiator["role"] == "ceo":
                # With no partner request a CEO's only automatic fallback is
                # the explicitly allowed seated self-talk state.  Supplying
                # another partner still follows the host-only refusal below.
                return self.plan_self_talk(
                    initiator_id,
                    snapshot=state,
                    talk_frames=talk_frames,
                    timing=timing,
                    dialogue_locale=dialogue_locale,
                    dialogue_category=dialogue_category,
                    dialogue_seed=dialogue_seed,
                    dialogue_line_overrides=dialogue_line_overrides,
                )
            else:
                mode = "standing_pair"
        mode = str(mode).strip().casefold()
        if mode == "self_talk":
            return self.plan_self_talk(
                initiator_id,
                snapshot=state,
                talk_frames=talk_frames,
                timing=timing,
                dialogue_locale=dialogue_locale,
                dialogue_category=dialogue_category,
                dialogue_seed=dialogue_seed,
                dialogue_line_overrides=dialogue_line_overrides,
            )
        if mode not in {"standing_pair", "ceo_front", "seated_host"}:
            return self._json({"ready": False, "reason": "unsupported_mode", "snapshot": state})

        if partner_id is None:
            partner_id = self._select_partner(state, initiator_id)
        if partner_id is None:
            return self._json({"ready": False, "reason": "no_eligible_partner", "snapshot": state})
        if partner_id == initiator_id:
            return self._json({"ready": False, "reason": "self_pair", "snapshot": state})
        partner = state["actors"].get(partner_id)
        if partner is None:
            return self._json({"ready": False, "reason": "unknown_employee", "snapshot": state})
        if initiator["floor_id"] != partner["floor_id"]:
            return self._json({"ready": False, "reason": "cross_floor_partner", "snapshot": state})
        if initiator["role"] == "ceo" and mode != "self_talk":
            return self._json({"ready": False, "reason": "ceo_outbound", "snapshot": state})

        participants = [initiator_id, partner_id]
        visitor_ids: list[str]
        host_id: str | None
        if mode == "ceo_front":
            if partner["role"] != "ceo" or initiator["role"] == "ceo":
                return self._json({"ready": False, "reason": "ceo_front_requires_employee_visitor", "snapshot": state})
            visitor_ids, host_id = [initiator_id], partner_id
            spot = self.spots.resolve_ceo_front(
                initiator["floor_id"],
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
            )
        elif mode == "seated_host":
            if partner["role"] == "ceo" or initiator["role"] == "ceo":
                return self._json({"ready": False, "reason": "ceo_seated_host_excluded", "snapshot": state})
            visitor_ids, host_id = [initiator_id], partner_id
            spot = self.spots.resolve_seated_host_side(
                partner["floor_id"],
                partner["workstation_id"],
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
            )
        else:
            if initiator["role"] == "ceo" or partner["role"] == "ceo":
                return self._json({"ready": False, "reason": "standing_pair_ceo_excluded", "snapshot": state})
            visitor_ids, host_id = participants, None
            origins = (
                [self._uv(cell) for cell in origin_uvs]
                if origin_uvs is not None
                else [self._gate(initiator), self._gate(partner)]
            )
            spot = self.spots.resolve_standing_pair(
                initiator["floor_id"],
                gap_cells=gap_cells,
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
                origin_uvs=origins,
            )
        if not spot.get("ready"):
            return self._json({
                "ready": False,
                "reason": spot.get("reason", "no_open_pair_slot"),
                "mode": mode,
                "spot": spot,
                "snapshot": state,
            })

        slot_id = str(spot["slot_id"])
        lock_reason = self._check_lock_free(state, participants, slot_id)
        if lock_reason:
            return self._json({"ready": False, "reason": lock_reason, "mode": mode, "spot": spot, "snapshot": state})
        conversation_id = f"conversation:{mode}:{initiator_id}:{partner_id}:{slot_id}"
        reserved_snapshot = self._reserve(state, participants, slot_id, conversation_id)
        timing_plan = self._resolve_timing(
            mode=mode,
            participants=participants,
            initiator_id=initiator_id,
            talk_frames=talk_frames,
            timing=timing,
        )
        dialogue_plan = self.resolve_conversation_dialogue(
            mode=mode,
            participant_ids=participants,
            initiator_id=initiator_id,
            locale=dialogue_locale,
            category=dialogue_category,
            selection_seed=dialogue_seed,
            start_speaker_id=str(timing_plan["start_speaker_id"]),
            dialogue_line_overrides=dialogue_line_overrides,
        )
        talk_frames = int(timing_plan["talk_frames"])
        talk_duration_ms = int(timing_plan["talk_duration_ms"])
        talk_segments = list(timing_plan["segments"])
        emotion_outcome: str | None = None
        emotion_hold_ms = 0
        if mode == "standing_pair":
            try:
                supplied_emotion_hold = int((timing or {}).get("emotion_hold_ms", self.DEFAULT_EMOTION_HOLD_MS))
            except (TypeError, ValueError) as exc:
                raise ConversationBehaviorError("timing.emotion_hold_ms must be an integer") from exc
            if supplied_emotion_hold < 0:
                raise ConversationBehaviorError("timing.emotion_hold_ms must be >= 0")
            if emotion_roll is not None:
                if (
                    isinstance(emotion_roll, bool)
                    or not isinstance(emotion_roll, int)
                    or not 1 <= emotion_roll <= 6
                ):
                    raise ConversationBehaviorError("emotion_roll must be an integer from 1 through 6")
                emotion_hold_ms = supplied_emotion_hold
                emotion_outcome = "happy" if emotion_roll % 2 == 0 else "sad"

        endpoint_by_actor: dict[str, tuple[int, int]] = {}
        facing_by_actor: dict[str, str] = {}
        if mode == "standing_pair":
            endpoints = [self._uv(cell) for cell in spot["endpoint_uv"]]
            assignments = self._pair_assignment([initiator, partner], endpoints)
            endpoint_facings = list(spot["endpoint_facings"])
            for index, (employee_id, endpoint) in enumerate(assignments):
                endpoint_by_actor[employee_id] = endpoint
                facing_by_actor[employee_id] = endpoint_facings[index]
        elif mode == "ceo_front":
            endpoint = self._uv(spot["endpoint_uv"][0])
            endpoint_by_actor[initiator_id] = endpoint
            facing_by_actor[initiator_id] = str(spot["endpoint_facing"]).upper()
        else:
            endpoint = self._uv(spot["selected_side"]["candidate_uv"])
            endpoint_by_actor[initiator_id] = endpoint
            facing_by_actor[initiator_id] = str(spot["visitor_idle_direction"]).upper()

        # The pair's world positions remain on the chosen UV line.  Bubble
        # placement is deliberately not derived from this geometry: the
        # dialogue renderer already owns the exact head anchor.  The opener's
        # extra vertical lift is an explicit contract value; the reply stays
        # at the base anchor so the two bubbles do not stack on one another.
        bubble_offset_by_actor: dict[str, list[int]] = {}
        if mode == "standing_pair" and len(endpoint_by_actor) == 2:
            opening_speaker_id = str(timing_plan["speaker_sequence"][0])
            bubble_offset_by_actor = {
                employee_id: (
                    list(self.standing_pair_opener_bubble_offset_px)
                    if employee_id == opening_speaker_id else [0, 0]
                )
                for employee_id in endpoint_by_actor
            }
        elif mode in {"seated_host", "ceo_front"}:
            bubble_offset_by_actor = {
                initiator_id: list(self.walking_visitor_bubble_extra_offset_px),
            }

        tracks: dict[str, list[dict[str, Any]]] = {}
        route_info: dict[str, Any] = {}
        for employee_id, endpoint in endpoint_by_actor.items():
            actor = state["actors"][employee_id]
            track, info = self._build_track(
                actor,
                endpoint,
                facing_by_actor[employee_id],
                talk_start_ms=0,
                talk_end_ms=0,
                talk_segments=[],
                return_to_work=True,
            )
            tracks[employee_id] = track
            route_info[employee_id] = info

        # The first build above uses zero-length talk windows to discover
        # arrival durations.  Rebuild with one shared talk boundary so both
        # standing actors and the visitor/host line up at the same frame.
        arrival_ms = max(int(info["arrival_ms"]) for info in route_info.values())
        talk_start_ms = max(self.TICK_MS, arrival_ms)
        talk_end_ms = talk_start_ms + talk_duration_ms
        tracks = {}
        route_info = {}
        for employee_id, endpoint in endpoint_by_actor.items():
            actor = state["actors"][employee_id]
            track, info = self._build_track(
                actor,
                endpoint,
                facing_by_actor[employee_id],
                talk_start_ms=talk_start_ms,
                talk_end_ms=talk_end_ms,
                talk_segments=talk_segments,
                dialogue_by_actor=dialogue_plan["lines_by_actor"],
                bubble_offset_px=bubble_offset_by_actor.get(employee_id),
                post_talk_hold_ms=emotion_hold_ms,
                post_talk_action=emotion_outcome,
                return_to_work=True,
            )
            tracks[employee_id] = track
            route_info[employee_id] = info
        if host_id is not None:
            host = state["actors"][host_id]
            host_subaction = (
                str(spot.get("selected_side", {}).get("side", "normal_work"))
                if mode == "seated_host"
                else "normal_work"
            )
            tracks[host_id] = self._build_host_track(
                host,
                talk_start_ms=talk_start_ms,
                talk_end_ms=talk_end_ms,
                talk_segments=talk_segments,
                host_subaction=host_subaction,
                dialogue_by_actor=dialogue_plan["lines_by_actor"],
            )

        if mode == "ceo_front":
            pose_bindings = {
                initiator_id: {
                    "render_owner": "walking_depth",
                    "action": "idle",
                    "subaction": "idle",
                    "role": "visitor",
                },
                partner_id: {
                    "render_owner": "work_seat",
                    "action": "work",
                    "subaction": "normal_work",
                    "role": "ceo_host",
                },
            }
        elif mode == "seated_host":
            host_turn = str(spot.get("selected_side", {}).get("side", "turn_side_target_direction"))
            pose_bindings = {
                initiator_id: {
                    "render_owner": "walking_depth",
                    "action": "idle",
                    "subaction": "idle",
                    "role": "visitor",
                },
                partner_id: {
                    "render_owner": "work_seat",
                    "action": "work",
                    "subaction": host_turn,
                    "role": "seated_host",
                },
            }
        else:
            pose_bindings = {
                employee_id: {
                    "render_owner": "walking_depth",
                    "action": "idle",
                    "subaction": "idle",
                    "role": "standing_pair_participant",
                }
                for employee_id in participants
            }

        end_ms = max(
            int(row["timestamp_ms"])
            for states in tracks.values()
            for row in states
        )
        crowd_audit = self._crowd_audit(tracks)
        endpoint_cells = [tuple(endpoint) for endpoint in endpoint_by_actor.values()]
        locks = {
            "participant_lock": participants,
            "talk_slot_lock": [slot_id],
        }
        final_snapshot = copy.deepcopy(reserved_snapshot)
        for employee_id in participants:
            final_snapshot["actors"][employee_id]["phase"] = "working"
            final_snapshot["actors"][employee_id]["locked"] = False
            final_snapshot["actors"][employee_id]["current_uv"] = None
            final_snapshot["actors"][employee_id]["render_owner"] = "work_seat"
            final_snapshot["actors"][employee_id]["workseat_state"] = "occupied"
        final_snapshot["locks"] = {"participant_lock": [], "talk_slot_lock": []}
        final_snapshot["active_conversation"] = None
        final_snapshot["conversation_id"] = None
        final_snapshot["clock_ms"] = end_ms

        return self._json({
            "ready": True,
            "schema": self.SCHEMA,
            "conversation_id": conversation_id,
            "mode": mode,
            "floor_id": initiator["floor_id"],
            "initiator_id": initiator_id,
            "partner_id": partner_id,
            "visitor_ids": visitor_ids,
            "host_id": host_id,
            "participants": participants,
            "spot": spot,
            "endpoint_by_actor": {key: list(value) for key, value in endpoint_by_actor.items()},
            "facing_by_actor": facing_by_actor,
            "bubble_offset_by_actor": bubble_offset_by_actor,
            "dialogue_layout_policy": "direct_head_anchor_overlay_paint_order",
            "endpoint_inverse": (
                bool(spot.get("endpoint_inverse", False)) if mode == "standing_pair" else True
            ),
            "talk_start_ms": talk_start_ms,
            "talk_end_ms": talk_end_ms,
            "talk_frames": talk_frames,
            "talk_duration_ms": talk_duration_ms,
            "timing": timing_plan,
            "dialogue": dialogue_plan,
            "dialogue_by_actor": dialogue_plan["lines_by_actor"],
            "pose_bindings": pose_bindings,
            "emotion": {
                "outcome": emotion_outcome,
                "roll": emotion_roll,
                "hold_ms": emotion_hold_ms,
                "stamina_effect_hook": "actor_snapshot_numeric_delta",
                "stamina_effect_milli_by_emotion": {"sad": -1000, "happy": 2000},
                "starts_after": "bubble_fade_end",
                "return_after": True,
            },
            "speaker_schedule": [
                {
                    **segment,
                    "start_ms": talk_start_ms + int(segment["start_offset_ms"]),
                    "end_ms": talk_start_ms + int(segment["end_offset_ms"]),
                    **({
                        "dialogue_id": dialogue_plan["lines_by_actor"].get(
                            str(segment.get("speaker_id")), {}
                        ).get("dialogue_id"),
                        "dialogue_line_index": dialogue_plan["lines_by_actor"].get(
                            str(segment.get("speaker_id")), {}
                        ).get("line_index"),
                        "dialogue_text": dialogue_plan["lines_by_actor"].get(
                            str(segment.get("speaker_id")), {}
                        ).get("text"),
                        "dialogue_locale": dialogue_plan["lines_by_actor"].get(
                            str(segment.get("speaker_id")), {}
                        ).get("locale"),
                    } if segment.get("speaker_id") is not None else {}),
                    **({
                        "bubble_start_ms": talk_start_ms + int(segment["bubble_start_offset_ms"]),
                        "bubble_visible_end_ms": talk_start_ms + int(segment["bubble_visible_end_offset_ms"]),
                        "fade_start_ms": talk_start_ms + int(segment["fade_start_offset_ms"]),
                        "fade_end_ms": talk_start_ms + int(segment["fade_end_offset_ms"]),
                    } if "bubble_start_offset_ms" in segment else {}),
                }
                for segment in talk_segments
            ],
            "loop_count": int(timing_plan["loop_count"]),
            "preview_only_timing": bool(timing_plan["preview_only"]),
            "route_info": route_info,
            "endpoint_cells_uv": [list(cell) for cell in endpoint_cells],
            "locks": locks,
            "lock_order": self.contract["state_vocabulary"]["lock_order"],
            "snapshot_before": state,
            "snapshot_reserved": reserved_snapshot,
            "snapshot_after": final_snapshot,
            "tracks": tracks,
            "timeline": self._timeline(tracks, end_ms=end_ms),
            "crowd_audit": crowd_audit,
            "events": [
                {"timestamp_ms": 0, "phase": "working"},
                {"timestamp_ms": 0, "phase": "talk_pending", "locks_acquired": True},
                {"timestamp_ms": self.TICK_MS, "phase": "leaving_workseat"},
                {"timestamp_ms": talk_start_ms, "phase": "talk_arrival"},
                {"timestamp_ms": talk_start_ms, "phase": "talking"},
                {"timestamp_ms": talk_end_ms, "phase": "talk_complete"},
                *(
                    [
                        {"timestamp_ms": talk_end_ms, "phase": "emotion_started", "emotion": emotion_outcome, "roll": emotion_roll},
                        {"timestamp_ms": talk_end_ms + emotion_hold_ms, "phase": "emotion_complete", "emotion": emotion_outcome},
                    ]
                    if emotion_outcome is not None and emotion_hold_ms > 0 else []
                ),
                {"timestamp_ms": end_ms, "phase": "returning_to_work"},
                {"timestamp_ms": end_ms, "phase": "working", "locks_released": True},
            ],
        })

    def advance_conversation(
        self,
        snapshot: dict[str, Any],
        plan: dict[str, Any],
        *,
        tick_ms: int = TICK_MS,
    ) -> dict[str, Any]:
        """Advance a reserved plan by one deterministic behavior window."""
        current = self.validate_snapshot(snapshot)
        if not plan.get("ready"):
            return self._json({"snapshot": current, "event": {"phase": "working"}, "complete": True})
        timestamp = int(current.get("clock_ms", 0)) + max(1, int(tick_ms))
        timeline = plan.get("timeline", [])
        if timeline:
            prior = [item for item in timeline if int(item["timestamp_ms"]) <= timestamp]
            row = prior[-1] if prior else timeline[0]
        else:
            row = {"timestamp_ms": timestamp, "actors": {}}
        end_ms = int(plan.get("snapshot_after", {}).get("clock_ms", plan.get("timeline", [{}])[-1].get("timestamp_ms", timestamp)))
        complete = timestamp >= end_ms
        next_snapshot = copy.deepcopy(current)
        next_snapshot["clock_ms"] = min(timestamp, end_ms)
        if complete:
            after = plan.get("snapshot_after")
            if isinstance(after, dict):
                next_snapshot = copy.deepcopy(after)
        else:
            for employee_id, actor_state in row.get("actors", {}).items():
                if employee_id not in next_snapshot.get("actors", {}):
                    continue
                actor = next_snapshot["actors"][employee_id]
                actor.update({
                    "phase": actor_state.get("phase"),
                    "current_uv": actor_state.get("current_uv"),
                    "direction": actor_state.get("direction", actor.get("direction")),
                    "action": actor_state.get("action", actor.get("action", "work")),
                    "subaction": actor_state.get("subaction", actor.get("subaction", "normal_work")),
                    "render_owner": actor_state.get("render_owner"),
                    "workseat_state": actor_state.get("workseat_state"),
                    "dialogue_visible": actor_state.get("dialogue_visible", False),
                    "dialogue_opacity": actor_state.get("dialogue_opacity", 0.0),
                    "dialogue_phase": actor_state.get("dialogue_phase", "hidden"),
                    "dialogue_text": actor_state.get("dialogue_text"),
                    "dialogue_id": actor_state.get("dialogue_id"),
                    "dialogue_line_index": actor_state.get("dialogue_line_index"),
                    "dialogue_locale": actor_state.get("dialogue_locale"),
                    "dialogue_bubble_offset_px": actor_state.get("dialogue_bubble_offset_px", [0, 0]),
                })
                for key in (
                    "speaker_id", "listener_id", "loop_index", "turn_index",
                ):
                    if key in actor_state:
                        actor[key] = actor_state[key]
                    else:
                        actor.pop(key, None)
        return self._json({
            "snapshot": next_snapshot,
            "event": {"timestamp_ms": int(row.get("timestamp_ms", timestamp)), "actors": row.get("actors", {})},
            "complete": complete,
        })

    def cancel_conversation(
        self,
        snapshot: dict[str, Any],
        plan: dict[str, Any],
        *,
        reason: str = "cancelled_by_caller",
    ) -> dict[str, Any]:
        """Release locks and restore assignment-backed seated ownership.

        This first-slice cancellation is a safe boundary operation.  A later
        live reducer can consume the immutable return paths in ``plan`` before
        committing this same final snapshot.
        """
        current = self.validate_snapshot(snapshot)
        cancelled = copy.deepcopy(current)
        participants = list(plan.get("participants", [])) if plan.get("ready") else []
        for employee_id in participants:
            actor = cancelled.get("actors", {}).get(employee_id)
            if actor is None:
                continue
            actor.update({
                "phase": "cancelled",
                "current_uv": None,
                "render_owner": "work_seat",
                "workseat_state": "occupied",
                "locked": False,
                "dialogue_visible": False,
                "dialogue_opacity": 0.0,
                "dialogue_phase": "hidden",
                "dialogue_bubble_offset_px": [0, 0],
                "subaction": "normal_work",
                "cancel_reason": str(reason),
            })
        cancelled["locks"] = {"participant_lock": [], "talk_slot_lock": []}
        cancelled["active_conversation"] = None
        cancelled["conversation_id"] = None
        for employee_id in participants:
            if employee_id in cancelled["actors"]:
                cancelled["actors"][employee_id]["phase"] = "working"
        return self._json({
            "cancelled": True,
            "reason": str(reason),
            "snapshot": cancelled,
            "event": {"phase": "cancelled", "locks_released": True},
        })
