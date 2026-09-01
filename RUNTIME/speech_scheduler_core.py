from __future__ import annotations

"""Deterministic speech timing and conversation trigger scheduler.

Speech is intentionally a presentation channel.  This runtime owns when a
line may start, which floor lane is occupied, and which conversation mode is
eligible; it does not mutate workstation ownership, animation registries or
stamina.  A movement/conversation planner may be supplied to enrich a pair
request with its already-authored paths and pose bindings.
"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from RUNTIME.employee_registry import EmployeeMetadataError, EmployeeMetadataRegistry


class SpeechSchedulerError(ValueError):
    """Raised when speech timing, lane state or trigger data is invalid."""


class SpeechSchedulerCore:
    SCHEMA = "gds.speech_scheduler_snapshot.v1"
    VERSION = "1.0.0"
    TICK_MS = 60
    BUBBLE_VISIBLE_MS = 4000
    BUBBLE_FADE_MS = 300
    SESSION_HOLD_MS = 4300
    EMOTION_HOLD_MS = 1200
    SOLO_CATEGORIES = (
        "encouragement",
        "uncertainty",
        "surprise",
        "work_progress",
        "idle_flavor",
    )
    PAIR_CATEGORIES = ("conversation_open", "conversation_reply")
    MODES = ("ceo_front", "seated_host", "standing_pair")
    PRIORITY = {
        "leaving": 0,
        "fatigue": 1,
        "greeting": 2,
        "work_start": 3,
        "pair": 4,
        "solo": 5,
    }

    def __init__(
        self,
        root: str | Path,
        *,
        employee_registry: EmployeeMetadataRegistry | None = None,
        conversation: Any | None = None,
    ):
        self.root = Path(root).resolve()
        self.employee_registry = employee_registry or EmployeeMetadataRegistry(self.root)
        self.conversation = conversation
        self.contract_path = self.root / "CONTRACTS" / "speech_scheduler.json"
        self.schema_path = self.root / "SCHEMA" / "speech_scheduler_snapshot.schema.json"
        try:
            self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
            self.snapshot_schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SpeechSchedulerError("Speech scheduler contract/schema cannot be loaded") from exc
        if self.contract.get("schema") != "gds.speech_scheduler.v1":
            raise SpeechSchedulerError("Unsupported speech scheduler contract")
        self._validator = Draft202012Validator(self.snapshot_schema)
        timing = self.contract.get("timing", {})
        emotion = self.contract.get("emotion", {})
        try:
            self.TICK_MS = int(timing.get("playback_tick_ms", self.TICK_MS))
            self.BUBBLE_VISIBLE_MS = int(timing.get("bubble_visible_ms", self.BUBBLE_VISIBLE_MS))
            self.BUBBLE_FADE_MS = int(timing.get("bubble_fade_ms", self.BUBBLE_FADE_MS))
            self.SESSION_HOLD_MS = int(timing.get("session_hold_ms", self.SESSION_HOLD_MS))
            self.EMOTION_HOLD_MS = int(emotion.get("hold_ms", self.EMOTION_HOLD_MS))
        except (TypeError, ValueError) as exc:
            raise SpeechSchedulerError("Speech scheduler timing contract is invalid") from exc
        if min(self.TICK_MS, self.BUBBLE_VISIBLE_MS, self.SESSION_HOLD_MS) <= 0:
            raise SpeechSchedulerError("Speech scheduler timing must be positive")
        if self.BUBBLE_FADE_MS < 0 or self.EMOTION_HOLD_MS < 0:
            raise SpeechSchedulerError("Speech scheduler fade/emotion timing cannot be negative")

    @staticmethod
    def _copy(value: Any) -> Any:
        return copy.deepcopy(value)

    @staticmethod
    def _stable_int(*parts: Any) -> int:
        material = "\x1f".join(str(part) for part in parts).encode("utf-8")
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")

    @staticmethod
    def _require_int(value: Any, name: str, *, minimum: int = 0) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise SpeechSchedulerError(f"{name} must be an integer >= {minimum}")
        return int(value)

    @classmethod
    def _quantize_up(cls, milliseconds: int) -> int:
        return max(cls.TICK_MS, ((int(milliseconds) + cls.TICK_MS - 1) // cls.TICK_MS) * cls.TICK_MS)

    @staticmethod
    def _actor_floor(actor: dict[str, Any]) -> str | None:
        assignment = actor.get("assignment")
        if isinstance(assignment, dict):
            floor_id = assignment.get("floor_id")
            if floor_id:
                return str(floor_id)
        floor_id = actor.get("floor_id")
        return str(floor_id) if floor_id else None

    @staticmethod
    def _actor_role(actor: dict[str, Any]) -> str:
        assignment = actor.get("assignment")
        if isinstance(assignment, dict) and assignment.get("workstation_id") == "ceo":
            return "ceo"
        return str(actor.get("role") or "employee")

    @staticmethod
    def _actor_activity(actor: dict[str, Any]) -> str:
        activity = actor.get("activity")
        if activity:
            return str(activity)
        # Speech actors mirror the renderer-agnostic actor reducer through
        # ``last_activity``.  Reading it here prevents a partner who is
        # currently wandering/talking/home from being treated as working
        # merely because this presentation snapshot has no duplicate field.
        mirrored = actor.get("last_activity")
        if mirrored:
            return str(mirrored)
        phase = str(actor.get("phase") or "working")
        return "working" if phase in {"working", "self_talk"} else phase

    @classmethod
    def _actor_present(cls, actor: dict[str, Any]) -> bool:
        presence = str(actor.get("presence") or "present")
        return presence in {"present", "entering"}

    @classmethod
    def _actor_available(cls, actor: dict[str, Any], *, allow_entering: bool = False) -> bool:
        if not cls._actor_present(actor):
            return False
        if not allow_entering and cls._actor_activity(actor) != "working":
            return False
        if actor.get("locked"):
            return False
        if actor.get("speech_phase") not in (None, "idle"):
            return False
        return True

    @classmethod
    def _canonical(cls, snapshot: dict[str, Any]) -> dict[str, Any]:
        result = cls._copy(snapshot)
        result["actors"] = {
            key: result["actors"][key] for key in sorted(result.get("actors", {}))
        }
        result["lanes"] = {
            key: result["lanes"][key] for key in sorted(result.get("lanes", {}))
        }
        result["active_sessions"] = {
            key: result["active_sessions"][key]
            for key in sorted(result.get("active_sessions", {}))
        }
        return result

    def _delay_ms(
        self,
        snapshot: dict[str, Any],
        employee_id: str,
        kind: str,
        counter: int,
    ) -> int:
        ranges = {
            "greeting": (2, 3),
            "solo": (30, 60),
            "pair": (45, 75),
            "retry": (15, 30),
        }
        try:
            lower, upper = ranges[kind]
        except KeyError as exc:
            raise SpeechSchedulerError(f"Unknown speech interval kind: {kind!r}") from exc
        ticket = self._stable_int(
            snapshot["determinism"]["simulation_seed"], employee_id, kind, counter
        )
        seconds = lower + ticket % (upper - lower + 1)
        return self._quantize_up(seconds * 1000)

    def _actor_state(
        self,
        employee_id: str,
        actor: dict[str, Any],
        *,
        now_ms: int,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        floor_id = self._actor_floor(actor)
        if not floor_id:
            raise SpeechSchedulerError(f"{employee_id}: actor has no floor")
        activity = self._actor_activity(actor)
        working = activity == "working"
        role = self._actor_role(actor)
        return {
            "employee_id": employee_id,
            "floor_id": floor_id,
            "role": role,
            "spawned_at_ms": int(now_ms),
            "greeting_due_ms": int(now_ms) + self._delay_ms(snapshot, employee_id, "greeting", 0),
            "greeting_emitted": False,
            "work_start_due_ms": int(now_ms) if working else None,
            "work_start_emitted": not working,
            "solo_next_due_ms": (
                int(now_ms) + self._delay_ms(snapshot, employee_id, "solo", 0)
                if working else None
            ),
            "pair_next_due_ms": (
                int(now_ms) + self._delay_ms(snapshot, employee_id, "pair", 0)
                if working and role != "ceo" else None
            ),
            "solo_pending": False,
            "pair_pending": False,
            "external_talk_pending": False,
            "external_talk_due_ms": None,
            "fatigue_pending": False,
            "fatigue_emitted": False,
            "leaving_pending": False,
            "leaving_emitted": False,
            "leaving_due_ms": None,
            "departure_token": 0,
            "speech_event_counter": 0,
            "last_activity": activity,
            "last_session_id": None,
            "last_partner_id": None,
            "speech_phase": "idle",
            "emotion": None,
            "emotion_until_ms": None,
        }

    def initial_snapshot(
        self,
        actor_snapshot: dict[str, Any] | None = None,
        *,
        floor_id: str | None = None,
        simulation_seed: str = "gds-speech-scheduler-v1",
        spawned_at_ms: int = 0,
    ) -> dict[str, Any]:
        """Create scheduler state from an actor snapshot without mutating it."""
        # Keep the facade ergonomic for callers that mirror
        # ``resolve_actor_snapshot('floor02')``.  A mapping remains the
        # canonical actor-snapshot input.
        if isinstance(actor_snapshot, str):
            if floor_id is not None:
                raise SpeechSchedulerError("floor_id was supplied twice")
            floor_id = actor_snapshot
            actor_snapshot = None
        spawned_at_ms = self._require_int(spawned_at_ms, "spawned_at_ms")
        if not isinstance(simulation_seed, str) or not simulation_seed:
            raise SpeechSchedulerError("simulation_seed must be a non-empty string")
        if actor_snapshot is None:
            try:
                rows = self.employee_registry.initial_roster(floor_id)
                actors_source = {
                    row["employee_id"]: self.employee_registry.get(row["employee_id"])
                    for row in rows
                }
            except EmployeeMetadataError as exc:
                raise SpeechSchedulerError(str(exc)) from exc
        else:
            if not isinstance(actor_snapshot, dict) or not isinstance(actor_snapshot.get("actors"), dict):
                raise SpeechSchedulerError("actor_snapshot.actors must be an object")
            actors_source = actor_snapshot["actors"]
        if floor_id is not None:
            actors_source = {
                key: value
                for key, value in actors_source.items()
                if self._actor_floor(value) == str(floor_id)
            }
        snapshot = {
            "schema": self.SCHEMA,
            "version": self.VERSION,
            "clock": {"simulation_time_ms": spawned_at_ms, "tick_ms": self.TICK_MS},
            "determinism": {
                "simulation_seed": simulation_seed,
                "root_event_counter": 0,
            },
            "actors": {},
            "lanes": {},
            "active_sessions": {},
        }
        for employee_id in sorted(actors_source):
            actor = actors_source[employee_id]
            if not isinstance(actor, dict):
                raise SpeechSchedulerError(f"{employee_id}: actor payload must be an object")
            snapshot["actors"][employee_id] = self._actor_state(
                str(employee_id), actor, now_ms=spawned_at_ms, snapshot=snapshot
            )
        snapshot["lanes"] = {
            floor: {
                "floor_id": floor,
                "active_session_id": None,
                "active_until_ms": None,
                "queued_session_ids": [],
                "last_completed_session_id": None,
            }
            for floor in sorted({row["floor_id"] for row in snapshot["actors"].values()})
        }
        return self.validate_snapshot(snapshot)

    def validate_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            raise SpeechSchedulerError("speech snapshot must be an object")
        try:
            json.dumps(snapshot, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise SpeechSchedulerError("speech snapshot must be JSON-safe") from exc
        errors = sorted(self._validator.iter_errors(snapshot), key=lambda error: list(error.path))
        if errors:
            first = errors[0]
            raise SpeechSchedulerError(f"{first.json_path or '$'}: {first.message}")
        current = self._canonical(snapshot)
        actor_ids = set(current["actors"])
        for employee_id, actor in current["actors"].items():
            if actor.get("employee_id") != employee_id:
                raise SpeechSchedulerError(f"speech actor key mismatch: {employee_id!r}")
            if actor.get("role") not in {"employee", "ceo"}:
                raise SpeechSchedulerError(f"{employee_id}: unknown speech actor role")
            if "external_talk_pending" in actor and not isinstance(
                actor.get("external_talk_pending"), bool
            ):
                raise SpeechSchedulerError(f"{employee_id}: external_talk_pending must be boolean")
            if actor.get("floor_id") not in current["lanes"]:
                raise SpeechSchedulerError(f"{employee_id}: missing speech lane")
            for key in (
                "greeting_due_ms", "work_start_due_ms", "solo_next_due_ms", "pair_next_due_ms",
                "emotion_until_ms", "leaving_due_ms", "external_talk_due_ms",
            ):
                value = actor.get(key)
                if value is not None:
                    self._require_int(value, f"{employee_id}.{key}")
            if actor.get("speech_phase") not in {"idle", "active", "emotion"}:
                raise SpeechSchedulerError(f"{employee_id}: unknown speech phase")
            if actor.get("emotion") not in {None, "sad", "happy"}:
                raise SpeechSchedulerError(f"{employee_id}: unknown emotion")
            if actor.get("speech_phase") == "emotion" and actor.get("emotion_until_ms") is None:
                raise SpeechSchedulerError(f"{employee_id}: emotion phase needs an end time")
        for floor_id, lane in current["lanes"].items():
            if lane.get("floor_id") != floor_id:
                raise SpeechSchedulerError(f"speech lane key mismatch: {floor_id!r}")
            active_id = lane.get("active_session_id")
            if active_id is not None:
                if active_id not in current["active_sessions"]:
                    raise SpeechSchedulerError(f"{floor_id}: lane points at unknown session")
                session = current["active_sessions"][active_id]
                if session.get("floor_id") != floor_id:
                    raise SpeechSchedulerError(f"{floor_id}: lane/session floor mismatch")
                if lane.get("active_until_ms") != session.get("fade_end_ms"):
                    raise SpeechSchedulerError(f"{floor_id}: lane end does not match session fade end")
        for session_id, session in current["active_sessions"].items():
            if session.get("session_id") != session_id:
                raise SpeechSchedulerError(f"speech session key mismatch: {session_id!r}")
            participants = session.get("participants", [])
            if len(participants) not in {1, 2} or len(set(participants)) != len(participants):
                raise SpeechSchedulerError(f"{session_id}: participants must be one or two unique actors")
            if not set(participants) <= actor_ids:
                raise SpeechSchedulerError(f"{session_id}: unknown participant")
            if session.get("kind") not in {"solo", "pair", "lifecycle"}:
                raise SpeechSchedulerError(f"{session_id}: unknown session kind")
            if session.get("mode") not in {"self_talk", *self.MODES}:
                raise SpeechSchedulerError(f"{session_id}: unknown session mode")
            if session.get("fade_end_ms") != int(session.get("start_ms", 0)) + self.SESSION_HOLD_MS:
                raise SpeechSchedulerError(f"{session_id}: speech session duration is not 4300ms")
        return current

    def _append_event(
        self,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        timestamp_ms: int,
        event_type: str,
        employee_id: str | None = None,
        **payload: Any,
    ) -> None:
        index = int(snapshot["determinism"]["root_event_counter"])
        snapshot["determinism"]["root_event_counter"] = index + 1
        event = {
            "event_index": index,
            "timestamp_ms": int(timestamp_ms),
            "type": str(event_type),
            **self._copy(payload),
        }
        if employee_id is not None:
            event["employee_id"] = str(employee_id)
        events.append(event)

    def _sync_actor_state(
        self,
        snapshot: dict[str, Any],
        actor_snapshot: dict[str, Any] | None,
        *,
        now_ms: int,
    ) -> None:
        if actor_snapshot is None:
            return
        source_actors = actor_snapshot.get("actors") if isinstance(actor_snapshot, dict) else None
        if not isinstance(source_actors, dict):
            raise SpeechSchedulerError("actor_snapshot.actors must be an object")
        for employee_id, speech_actor in snapshot["actors"].items():
            source = source_actors.get(employee_id)
            if not isinstance(source, dict):
                continue
            activity = self._actor_activity(source)
            previous = speech_actor.get("last_activity")
            if activity != previous:
                if activity == "working":
                    speech_actor["work_start_due_ms"] = now_ms
                    speech_actor["work_start_emitted"] = False
                    speech_actor["solo_next_due_ms"] = now_ms + self._delay_ms(
                        snapshot, employee_id, "solo", int(speech_actor.get("speech_event_counter", 0)) + 1
                    )
                    speech_actor["pair_next_due_ms"] = now_ms + self._delay_ms(
                        snapshot, employee_id, "pair", int(speech_actor.get("speech_event_counter", 0)) + 1
                    ) if speech_actor.get("role") != "ceo" else None
                    speech_actor["solo_pending"] = False
                    speech_actor["pair_pending"] = False
                elif speech_actor.get("solo_next_due_ms") is not None and activity not in {"working"}:
                    if int(speech_actor["solo_next_due_ms"]) <= now_ms:
                        speech_actor["solo_pending"] = True
                        speech_actor["solo_next_due_ms"] = None
                    if speech_actor.get("pair_next_due_ms") is not None and int(speech_actor["pair_next_due_ms"]) <= now_ms:
                        speech_actor["pair_pending"] = True
                        speech_actor["pair_next_due_ms"] = None
                if activity == "going_home" or str(source.get("presence")) == "leaving":
                    speech_actor["fatigue_pending"] = True
                    speech_actor["fatigue_emitted"] = False
                    speech_actor["leaving_emitted"] = False
                    speech_actor["leaving_due_ms"] = None
                    speech_actor["departure_token"] = int(speech_actor["departure_token"]) + 1
                speech_actor["last_activity"] = activity

    def _apply_command(
        self,
        snapshot: dict[str, Any],
        command: dict[str, Any],
        *,
        timestamp_ms: int,
    ) -> None:
        if not isinstance(command, dict):
            raise SpeechSchedulerError("speech commands must contain objects")
        employee_id = command.get("employee_id")
        command_type = command.get("type")
        if not isinstance(employee_id, str) or employee_id not in snapshot["actors"]:
            raise SpeechSchedulerError("speech command.employee_id must name an active actor")
        actor = snapshot["actors"][employee_id]
        if command_type == "behavior_started":
            if command.get("behavior") != "talk":
                raise SpeechSchedulerError(
                    "behavior_started speech bridge only accepts behavior=talk"
                )
            actor["external_talk_pending"] = True
            effective_at = command.get("effective_at_ms", timestamp_ms)
            actor["external_talk_due_ms"] = self._require_int(
                effective_at, "behavior_started.effective_at_ms"
            )
            return
        if command_type == "spawned":
            actor.update({
                "spawned_at_ms": timestamp_ms,
                "greeting_due_ms": timestamp_ms + self._delay_ms(snapshot, employee_id, "greeting", int(actor["departure_token"]) + 1),
                "greeting_emitted": False,
            })
            return
        if command_type == "workseat_entered":
            actor.update({"work_start_due_ms": timestamp_ms, "work_start_emitted": False})
            return
        if command_type == "going_home":
            actor.update({
                "fatigue_pending": True,
                "fatigue_emitted": False,
                "leaving_emitted": False,
                "leaving_due_ms": None,
                "departure_token": int(actor["departure_token"]) + 1,
            })
            return
        if command_type == "returned_to_work":
            actor.update({
                "speech_phase": "idle",
                "emotion": None,
                "emotion_until_ms": None,
                "work_start_due_ms": timestamp_ms,
                "work_start_emitted": False,
                "solo_next_due_ms": timestamp_ms + self._delay_ms(snapshot, employee_id, "solo", int(actor["departure_token"]) + 1),
                "pair_next_due_ms": (
                    timestamp_ms + self._delay_ms(
                        snapshot, employee_id, "pair", int(actor["departure_token"]) + 1
                    )
                    if actor.get("role") != "ceo" else None
                ),
                "solo_pending": False,
                "pair_pending": False,
                "leaving_pending": False,
                "leaving_due_ms": None,
            })
            return
        if command_type == "reception_depth_crossed":
            draws_over = command.get(
                "draws_over_reception",
                command.get("render_over_reception", False),
            )
            if not isinstance(draws_over, bool) or not draws_over:
                raise SpeechSchedulerError(
                    "reception_depth_crossed requires draws_over_reception=true"
                )
            actor["leaving_pending"] = True
            actor["leaving_emitted"] = False
            effective_at = command.get("effective_at_ms", timestamp_ms)
            actor["leaving_due_ms"] = self._require_int(
                effective_at, "reception_depth_crossed.effective_at_ms"
            )
            return
        raise SpeechSchedulerError(f"Unknown speech command type: {command_type!r}")

    def _eligible_partner_ids(
        self,
        snapshot: dict[str, Any],
        initiator_id: str,
        *,
        role: str | None = None,
    ) -> list[str]:
        initiator = snapshot["actors"][initiator_id]
        floor_id = initiator["floor_id"]
        result = []
        for employee_id, actor in snapshot["actors"].items():
            if employee_id == initiator_id or actor.get("floor_id") != floor_id:
                continue
            if role is not None and actor.get("role") != role:
                continue
            if not self._actor_available(actor):
                continue
            result.append(employee_id)
        result.sort(key=lambda employee_id: (
            int(snapshot["actors"][employee_id].get("assignment_order", 0)), employee_id
        ))
        return result

    def _mode_request(
        self,
        snapshot: dict[str, Any],
        initiator_id: str,
        *,
        counter: int,
    ) -> dict[str, Any] | None:
        requests = self._mode_requests(
            snapshot,
            initiator_id,
            counter=counter,
        )
        return requests[0] if requests else None

    def _mode_requests(
        self,
        snapshot: dict[str, Any],
        initiator_id: str,
        *,
        counter: int,
    ) -> list[dict[str, Any]]:
        """Return seeded mode/partner candidates in retry order.

        The first row is the uniform mode draw.  Remaining rows are only
        fallback candidates: they let a valid mode/partner win when the
        selected geometry or route is unavailable, without changing the
        three-mode probability when all modes are ready.
        """
        initiator = snapshot["actors"].get(initiator_id)
        external_talk = bool(initiator and initiator.get("external_talk_pending"))
        initiator_available = self._actor_available(initiator) if initiator is not None else False
        if external_talk and initiator is not None:
            # The actor reducer owns the talking activity window.  A bridge
            # event may therefore arrive while activity is ``talking``; the
            # speech lane may still choose a valid pair without stealing the
            # actor's independent pose/stamina clock.
            initiator_available = self._actor_available(initiator, allow_entering=True)
            if initiator_available and self._actor_activity(initiator) != "working":
                initiator_available = self._actor_present(initiator) and not initiator.get("locked") and initiator.get("speech_phase") in (None, "idle")
        if initiator is None or initiator.get("role") == "ceo" or not initiator_available:
            return []
        ceos = self._eligible_partner_ids(snapshot, initiator_id, role="ceo")
        employees = self._eligible_partner_ids(snapshot, initiator_id, role="employee")
        mode_groups: list[tuple[str, list[str]]] = []
        if ceos:
            mode_groups.append(("ceo_front", ceos))
        if employees:
            mode_groups.extend((("seated_host", employees), ("standing_pair", employees)))
        if not mode_groups:
            return []

        seed = snapshot["determinism"]["simulation_seed"]
        selected_index = self._stable_int(
            seed, initiator_id, "mode", counter
        ) % len(mode_groups)
        rotated_groups = mode_groups[selected_index:] + mode_groups[:selected_index]
        available_modes = [mode for mode, _ in mode_groups]
        requests: list[dict[str, Any]] = []
        for mode, candidates in rotated_groups:
            ordered_candidates = sorted(
                candidates,
                key=lambda employee_id: (
                    self._stable_int(seed, initiator_id, mode, counter, employee_id),
                    employee_id,
                ),
            )
            for partner_id in ordered_candidates:
                requests.append({
                    "kind": "pair",
                    "initiator_id": initiator_id,
                    "partner_id": partner_id,
                    "participants": [initiator_id, partner_id],
                    "mode": mode,
                    "category": "conversation_open",
                    "dialogue_categories": list(self.PAIR_CATEGORIES),
                    "available_modes": list(available_modes),
                })
        return requests

    def _pose_bindings(
        self,
        mode: str,
        participants: list[str],
        *,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if mode == "self_talk":
            return {
                employee_id: {
                    "render_owner": "work_seat",
                    "action": "work",
                    "subaction": "normal_work",
                    "role": "seated_speaker",
                }
                for employee_id in participants
            }
        if mode == "ceo_front":
            visitor = participants[0]
            host = participants[1]
            return {
                visitor: {"render_owner": "walking_depth", "action": "idle", "subaction": "idle", "role": "visitor"},
                host: {"render_owner": "work_seat", "action": "work", "subaction": "normal_work", "role": "ceo_host"},
            }
        if mode == "seated_host":
            visitor = participants[0]
            host = participants[1]
            host_subaction = "turn_side_target_direction"
            if isinstance(plan, dict):
                tracks = plan.get("tracks", {})
                host_rows = tracks.get(host, []) if isinstance(tracks, dict) else []
                host_subactions = [
                    row.get("subaction")
                    for row in host_rows
                    if row.get("phase") == "talking" and row.get("subaction")
                ]
                if host_subactions:
                    host_subaction = str(host_subactions[0])
            return {
                visitor: {"render_owner": "walking_depth", "action": "idle", "subaction": "idle", "role": "visitor"},
                host: {"render_owner": "work_seat", "action": "work", "subaction": host_subaction, "role": "seated_host"},
            }
        return {
            employee_id: {
                "render_owner": "walking_depth",
                "action": "idle",
                "subaction": "idle",
                "role": "standing_pair_participant",
            }
            for employee_id in participants
        }

    def _maybe_plan_session(
        self,
        snapshot: dict[str, Any],
        request: dict[str, Any],
        *,
        conversation_snapshot: dict[str, Any] | None,
        dialogue_locale: str,
        dialogue_seed: str | int,
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        if self.conversation is None or conversation_snapshot is None:
            return request, None
        candidates = [request]
        if request.get("kind") == "pair":
            generated = self._mode_requests(
                snapshot,
                request["initiator_id"],
                counter=int(snapshot["actors"][request["initiator_id"]].get("speech_event_counter", 0)) + 1,
            )
            seen = {
                (request.get("mode"), request.get("partner_id"))
            }
            for candidate in generated:
                key = (candidate.get("mode"), candidate.get("partner_id"))
                if key not in seen:
                    candidates.append(candidate)
                    seen.add(key)
        for candidate in candidates:
            try:
                if candidate["kind"] == "pair":
                    plan = self.conversation.plan_conversation(
                        candidate["initiator_id"],
                        partner_id=candidate["partner_id"],
                        mode=candidate["mode"],
                        snapshot=conversation_snapshot,
                        dialogue_locale=dialogue_locale,
                        dialogue_seed=dialogue_seed,
                    )
                else:
                    plan = self.conversation.plan_self_talk(
                        candidate["initiator_id"],
                        snapshot=conversation_snapshot,
                        dialogue_locale=dialogue_locale,
                        dialogue_category=candidate.get("category"),
                        dialogue_seed=dialogue_seed,
                    )
            except Exception:
                # A pair is not started without a valid movement/spot/dialogue
                # plan.  The next seeded candidate may still be usable.
                continue
            if plan.get("ready"):
                return candidate, plan
        return None

    def _start_session(
        self,
        snapshot: dict[str, Any],
        request: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        participants = list(request["participants"])
        kind = str(request["kind"])
        mode = str(request.get("mode") or ("self_talk" if kind != "pair" else "standing_pair"))
        category = str(request.get("category") or "idle_flavor")
        session_counter = int(snapshot["determinism"]["root_event_counter"])
        session_id = (
            f"speech:{snapshot['actors'][participants[0]]['floor_id']}:{kind}:"
            f"{participants[0]}:{session_counter}"
        )
        movement_started_ms = int(timestamp_ms)
        movement_arrival_ms = movement_started_ms
        if isinstance(plan, dict) and request["kind"] == "pair":
            # Conversation movement is a separate channel.  The scheduler
            # records the route start now; the bubble still begins only at the
            # planner's shared arrival boundary.
            movement_arrival_ms += max(0, int(plan.get("talk_start_ms", 0)))
        bubble_start_ms = movement_arrival_ms
        fade_end = bubble_start_ms + self.SESSION_HOLD_MS
        pose_bindings = self._pose_bindings(mode, participants, plan=plan)
        if kind == "lifecycle" and category in {"fatigue", "leaving"}:
            # Keep the actor reducer's live route/action (usually walking to
            # the portal).  The role is metadata for the renderer; omitting
            # render_owner/action/subaction prevents a bubble from snapping
            # the actor back into a WorkSeat pose.
            pose_bindings = {
                employee_id: {"role": "departure_speaker"}
                for employee_id in participants
            }
        elif kind == "lifecycle" and category == "greeting":
            pose_bindings = {
                employee_id: {"role": "spawn_speaker"}
                for employee_id in participants
            }
        session = {
            "session_id": session_id,
            "floor_id": snapshot["actors"][participants[0]]["floor_id"],
            "kind": kind,
            "mode": mode,
            "category": category,
            "pair_categories": list(request.get("dialogue_categories", [])),
            "participants": participants,
            "initiator_id": request.get("initiator_id", participants[0]),
            "partner_id": request.get("partner_id"),
            "available_modes": list(request.get("available_modes", [])),
            "selection_policy": "uniform_valid_mode_then_seeded_partner",
            "start_ms": bubble_start_ms,
            "movement_started_ms": movement_started_ms,
            "movement_arrival_ms": movement_arrival_ms,
            "bubble_start_ms": bubble_start_ms,
            "bubble_visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
            "fade_start_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
            "fade_end_ms": fade_end,
            "return_after_bubble": True,
            "bubble_schedule": [],
            "pose_bindings": pose_bindings,
            "conversation_plan": self._copy(plan) if plan is not None else None,
            "emotion_outcome": None,
            "emotion_hold_ms": 0,
            "stamina_effect_hook": "external_hook_no_numeric_delta_yet",
            "bubble_started": False,
            "bubble_start_event_emitted": False,
        }
        if kind == "pair":
            first, second = participants[0], participants[1]
            session["bubble_schedule"] = [
                {
                    "employee_id": first,
                    "category": "conversation_open",
                    "start_ms": bubble_start_ms,
                    "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                    "fade_end_ms": fade_end,
                    "turn_index": 0,
                },
                {
                    "employee_id": second,
                    "category": "conversation_reply",
                    "start_ms": bubble_start_ms + 500,
                    "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                    "fade_end_ms": fade_end,
                    "turn_index": 1,
                },
            ]
            if mode == "standing_pair":
                roll = self._stable_int(
                    snapshot["determinism"]["simulation_seed"], session_id, "emotion"
                )
                session["emotion_outcome"] = "happy" if roll % 2 == 0 else "sad"
                session["emotion_hold_ms"] = self.EMOTION_HOLD_MS
        else:
            session["bubble_schedule"] = [{
                "employee_id": participants[0],
                "category": category,
                "start_ms": bubble_start_ms,
                "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                "fade_end_ms": fade_end,
                "turn_index": 0,
            }]
        snapshot["active_sessions"][session_id] = session
        floor_id = session["floor_id"]
        lane = snapshot["lanes"][floor_id]
        lane["active_session_id"] = session_id
        lane["active_until_ms"] = fade_end
        for employee_id in participants:
            actor = snapshot["actors"][employee_id]
            actor["speech_event_counter"] = int(actor.get("speech_event_counter", 0)) + 1
            actor["speech_phase"] = "active"
            actor["external_talk_pending"] = False
            actor["external_talk_due_ms"] = None
            actor["last_session_id"] = session_id
            actor["last_partner_id"] = request.get("partner_id")
            if category == "greeting":
                actor["greeting_emitted"] = True
            elif category == "work_start":
                actor["work_start_emitted"] = True
            elif category == "fatigue":
                actor["fatigue_emitted"] = True
                actor["fatigue_pending"] = False
            elif category == "leaving":
                actor["leaving_emitted"] = True
                actor["leaving_pending"] = False
                actor["leaving_due_ms"] = None
            elif kind == "solo":
                actor["solo_pending"] = False
                actor["solo_next_due_ms"] = None
            elif kind == "pair":
                actor["pair_pending"] = False
                actor["pair_next_due_ms"] = None
        self._append_event(
            snapshot,
            events,
            timestamp_ms=timestamp_ms,
            event_type="speech_session_started",
            employee_id=participants[0],
            session_id=session_id,
            floor_id=floor_id,
            kind=kind,
            mode=mode,
            category=category,
            participants=participants,
            bubble_visible_end_ms=session["bubble_visible_end_ms"],
            fade_end_ms=fade_end,
            bubble_start_ms=bubble_start_ms,
            movement_started_ms=movement_started_ms,
            movement_arrival_ms=movement_arrival_ms,
            pose_bindings=session["pose_bindings"],
            bubble_schedule=session["bubble_schedule"],
            conversation_plan=session["conversation_plan"],
            available_modes=session["available_modes"],
            selection_policy=session["selection_policy"],
        )
        if bubble_start_ms <= int(timestamp_ms):
            self._append_bubble_started_event(
                snapshot,
                session,
                events=events,
                timestamp_ms=bubble_start_ms,
            )
        return session

    def _append_bubble_started_event(
        self,
        snapshot: dict[str, Any],
        session: dict[str, Any],
        *,
        events: list[dict[str, Any]],
        timestamp_ms: int,
    ) -> None:
        """Emit the presentation boundary once, after any movement wait."""
        if session.get("bubble_start_event_emitted"):
            return
        session["bubble_started"] = True
        session["bubble_start_event_emitted"] = True
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            event_type="speech_bubble_started",
            employee_id=session["participants"][0],
            session_id=session["session_id"],
            floor_id=session["floor_id"],
            kind=session["kind"],
            mode=session["mode"],
            category=session["category"],
            participants=session["participants"],
            bubble_visible_end_ms=session["bubble_visible_end_ms"],
            fade_start_ms=session["fade_start_ms"],
            fade_end_ms=session["fade_end_ms"],
            pose_bindings=session["pose_bindings"],
            bubble_schedule=session["bubble_schedule"],
        )

    def _complete_session(
        self,
        snapshot: dict[str, Any],
        session_id: str,
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        session = snapshot["active_sessions"].pop(session_id)
        floor_id = session["floor_id"]
        lane = snapshot["lanes"][floor_id]
        lane["active_session_id"] = None
        lane["active_until_ms"] = None
        lane["last_completed_session_id"] = session_id
        participants = list(session["participants"])
        self._append_event(
            snapshot,
            events,
            timestamp_ms=timestamp_ms,
            event_type="speech_session_completed",
            employee_id=participants[0],
            session_id=session_id,
            floor_id=floor_id,
            participants=participants,
            # A standing pair owns a short emotion hold before movement
            # return.  The final return_requested event is emitted after that
            # hold; ordinary sessions return as soon as the fade completes.
            return_requested=not (
                session.get("emotion_outcome") in {"sad", "happy"}
                and int(session.get("emotion_hold_ms", 0)) > 0
            ),
        )
        emotion = session.get("emotion_outcome")
        emotion_until = timestamp_ms
        if emotion in {"sad", "happy"} and session.get("emotion_hold_ms", 0):
            emotion_until = timestamp_ms + int(session["emotion_hold_ms"])
            emotion_pose_bindings = {
                employee_id: {
                    "render_owner": "walking_depth",
                    "action": emotion,
                    "subaction": emotion,
                    "role": "standing_pair_emotion",
                }
                for employee_id in participants
            }
            session["emotion_pose_bindings"] = emotion_pose_bindings
            for employee_id in participants:
                actor = snapshot["actors"][employee_id]
                actor["speech_phase"] = "emotion"
                actor["emotion"] = emotion
                actor["emotion_until_ms"] = emotion_until
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                event_type="emotion_started",
                employee_id=participants[0],
                session_id=session_id,
                emotion=emotion,
                participants=participants,
                stamina_effect_hook="external_hook_no_numeric_delta_yet",
                pose_bindings=emotion_pose_bindings,
            )
        else:
            self._finish_participants(snapshot, participants, timestamp_ms=timestamp_ms, events=events)
        if emotion in {"sad", "happy"} and session.get("emotion_hold_ms", 0):
            session["emotion_until_ms"] = emotion_until
            snapshot.setdefault("completed_sessions", {})[session_id] = session
        else:
            snapshot.setdefault("completed_sessions", {})[session_id] = session

    def _finish_participants(
        self,
        snapshot: dict[str, Any],
        participants: Iterable[str],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
        session_id: str | None = None,
    ) -> None:
        for employee_id in participants:
            actor = snapshot["actors"][employee_id]
            actor["speech_phase"] = "idle"
            actor["external_talk_pending"] = False
            actor["external_talk_due_ms"] = None
            actor["emotion"] = None
            actor["emotion_until_ms"] = None
            counter = int(actor.get("speech_event_counter", 0))
            actor["solo_next_due_ms"] = timestamp_ms + self._delay_ms(snapshot, employee_id, "solo", counter)
            actor["pair_next_due_ms"] = (
                timestamp_ms + self._delay_ms(snapshot, employee_id, "pair", counter)
                if actor.get("role") != "ceo" else None
            )
            actor["solo_pending"] = False
            actor["pair_pending"] = False
        if session_id:
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                event_type="emotion_completed",
                employee_id=list(participants)[0],
                session_id=session_id,
                return_requested=True,
            )

    def _finish_emotions(
        self,
        snapshot: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        for employee_id, actor in snapshot["actors"].items():
            until = actor.get("emotion_until_ms")
            if actor.get("speech_phase") != "emotion" or until is None or int(until) > timestamp_ms:
                continue
            session_id = actor.get("last_session_id")
            actor["speech_phase"] = "idle"
            actor["emotion"] = None
            actor["emotion_until_ms"] = None
            # The shared pair outcome is completed once for the first actor;
            # the event carries both participants from the completed record.
            completed = snapshot.get("completed_sessions", {}).get(session_id, {})
            participants = list(completed.get("participants", [employee_id]))
            if any(snapshot["actors"].get(item, {}).get("speech_phase") == "emotion" for item in participants):
                for item in participants:
                    snapshot["actors"][item]["speech_phase"] = "idle"
                    snapshot["actors"][item]["emotion"] = None
                    snapshot["actors"][item]["emotion_until_ms"] = None
                self._finish_participants(
                    snapshot,
                    participants,
                    timestamp_ms=timestamp_ms,
                    events=events,
                    session_id=session_id,
                )
                self._append_event(
                    snapshot,
                    events,
                    timestamp_ms=timestamp_ms,
                    event_type="return_requested",
                    employee_id=participants[0],
                    session_id=session_id,
                    participants=participants,
                    reason="standing_pair_emotion_complete",
                )

    def _request_for_actor(
        self,
        snapshot: dict[str, Any],
        employee_id: str,
        *,
        now_ms: int,
    ) -> dict[str, Any] | None:
        actor = snapshot["actors"][employee_id]
        if actor.get("speech_phase") != "idle":
            return None
        if (
            actor.get("leaving_pending")
            and not actor.get("leaving_emitted")
            and (
                actor.get("leaving_due_ms") is None
                or int(actor.get("leaving_due_ms")) <= now_ms
            )
        ):
            return {
                "kind": "lifecycle", "category": "leaving", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        if actor.get("fatigue_pending") and not actor.get("fatigue_emitted"):
            return {
                "kind": "lifecycle", "category": "fatigue", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        if (
            self._actor_present(actor)
            and not actor.get("greeting_emitted")
            and actor.get("greeting_due_ms") is not None
            and int(actor["greeting_due_ms"]) <= now_ms
        ):
            return {
                "kind": "lifecycle", "category": "greeting", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        if (
            self._actor_present(actor)
            and not actor.get("work_start_emitted")
            and actor.get("work_start_due_ms") is not None
            and int(actor["work_start_due_ms"]) <= now_ms
        ):
            return {
                "kind": "lifecycle", "category": "work_start", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        if (
            actor.get("external_talk_pending")
            and actor.get("role") != "ceo"
            and (
                actor.get("external_talk_due_ms") is None
                or int(actor.get("external_talk_due_ms")) <= now_ms
            )
        ):
            request = self._mode_request(
                snapshot,
                employee_id,
                counter=int(actor.get("speech_event_counter", 0)) + 1,
            )
            if request is not None:
                return request
        if not self._actor_available(actor):
            return None
        if actor.get("role") != "ceo" and (
            actor.get("pair_pending")
            or (
                actor.get("pair_next_due_ms") is not None
                and int(actor["pair_next_due_ms"]) <= now_ms
            )
        ):
            request = self._mode_request(
                snapshot,
                employee_id,
            counter=int(actor.get("speech_event_counter", 0)) + 1,
            )
            if request is not None:
                return request
            actor["pair_pending"] = True
            actor["pair_next_due_ms"] = None
        if actor.get("solo_pending") or (
            actor.get("solo_next_due_ms") is not None and int(actor["solo_next_due_ms"]) <= now_ms
        ):
            index = self._stable_int(
                snapshot["determinism"]["simulation_seed"], employee_id, "solo-category", int(actor.get("speech_event_counter", 0)) + 1
            ) % len(self.SOLO_CATEGORIES)
            return {
                "kind": "solo", "category": self.SOLO_CATEGORIES[index], "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        return None

    def _retry_request(self, snapshot: dict[str, Any], request: dict[str, Any], *, now_ms: int) -> None:
        employee_id = request["initiator_id"]
        actor = snapshot["actors"][employee_id]
        if request["kind"] == "pair":
            actor["pair_pending"] = False
            actor["pair_next_due_ms"] = now_ms + self._delay_ms(
                snapshot, employee_id, "retry", int(actor.get("departure_token", 0)) + 1
            )
        elif request["kind"] == "solo":
            actor["solo_pending"] = False
            actor["solo_next_due_ms"] = now_ms + self._delay_ms(
                snapshot, employee_id, "retry", int(actor.get("departure_token", 0)) + 1
            )

    def advance_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        actor_snapshot: dict[str, Any] | None = None,
        conversation_snapshot: dict[str, Any] | None = None,
        commands: Iterable[dict[str, Any]] | None = None,
        dialogue_locale: str = "en",
        dialogue_seed: str | int = "0",
    ) -> dict[str, Any]:
        """Advance speech timers and return events; input snapshots stay untouched."""
        current = self.validate_snapshot(snapshot)
        elapsed_ms = self._require_int(elapsed_ms, "elapsed_ms")
        start_ms = int(current["clock"]["simulation_time_ms"])
        target_ms = start_ms + elapsed_ms
        events: list[dict[str, Any]] = []
        self._sync_actor_state(current, actor_snapshot, now_ms=start_ms)
        for command in sorted(list(commands or ()), key=lambda item: str(item.get("employee_id", ""))):
            self._apply_command(current, command, timestamp_ms=start_ms)

        now_ms = start_ms
        first_pass = True
        while now_ms <= target_ms:
            self._finish_emotions(current, timestamp_ms=now_ms, events=events)
            for session in current["active_sessions"].values():
                if (
                    not session.get("bubble_start_event_emitted")
                    and int(session["bubble_start_ms"]) <= now_ms
                ):
                    self._append_bubble_started_event(
                        current,
                        session,
                        events=events,
                        timestamp_ms=int(session["bubble_start_ms"]),
                    )
            due_sessions = [
                session_id
                for session_id, session in current["active_sessions"].items()
                if int(session["fade_end_ms"]) <= now_ms
            ]
            for session_id in sorted(due_sessions):
                self._complete_session(current, session_id, timestamp_ms=now_ms, events=events)

            self._sync_actor_state(current, actor_snapshot, now_ms=now_ms)
            started_any = False
            by_floor: dict[str, list[dict[str, Any]]] = {}
            for employee_id in sorted(current["actors"]):
                request = self._request_for_actor(current, employee_id, now_ms=now_ms)
                if request is not None:
                    floor = current["actors"][employee_id]["floor_id"]
                    by_floor.setdefault(floor, []).append(request)
            for floor_id in sorted(by_floor):
                lane = current["lanes"][floor_id]
                if lane.get("active_session_id") is not None:
                    lane["queued_session_ids"] = [
                        request["initiator_id"] for request in by_floor[floor_id]
                    ]
                    continue
                lane["queued_session_ids"] = []
                requests = sorted(
                    by_floor[floor_id],
                    key=lambda request: (
                        self.PRIORITY.get(request.get("category"), self.PRIORITY["solo"]),
                        int(current["actors"][request["initiator_id"]].get("greeting_due_ms") or now_ms),
                        request["initiator_id"],
                    ),
                )
                for request in requests:
                    plan = None
                    planned = self._maybe_plan_session(
                        current,
                        request,
                        conversation_snapshot=conversation_snapshot,
                        dialogue_locale=dialogue_locale,
                        dialogue_seed=dialogue_seed,
                    )
                    if planned is None:
                        self._retry_request(current, request, now_ms=now_ms)
                        continue
                    request, plan = planned
                    self._start_session(current, request, timestamp_ms=now_ms, events=events, plan=plan)
                    started_any = True
                    break

            if started_any:
                first_pass = False
                if now_ms == target_ms:
                    break
                # A new lane now advances to its fade boundary.
                next_boundaries = [
                    int(session["bubble_start_ms"])
                    for session in current["active_sessions"].values()
                    if int(session["bubble_start_ms"]) > now_ms
                ] + [
                    int(session["fade_end_ms"])
                    for session in current["active_sessions"].values()
                    if int(session["fade_end_ms"]) > now_ms
                ]
                if next_boundaries:
                    next_ms = min(next_boundaries)
                    if next_ms <= target_ms:
                        now_ms = next_ms
                        continue
                break

            if now_ms >= target_ms:
                break
            boundaries = [target_ms]
            for session in current["active_sessions"].values():
                bubble_start_ms = int(session["bubble_start_ms"])
                if bubble_start_ms > now_ms:
                    boundaries.append(bubble_start_ms)
                end_ms = int(session["fade_end_ms"])
                if end_ms > now_ms:
                    boundaries.append(end_ms)
            for actor in current["actors"].values():
                for key in (
                    "greeting_due_ms",
                    "work_start_due_ms",
                    "solo_next_due_ms",
                    "pair_next_due_ms",
                    "leaving_due_ms",
                    "external_talk_due_ms",
                ):
                    due = actor.get(key)
                    if due is not None and int(due) > now_ms:
                        boundaries.append(int(due))
                emotion_until = actor.get("emotion_until_ms")
                if emotion_until is not None and int(emotion_until) > now_ms:
                    boundaries.append(int(emotion_until))
            next_ms = min(boundaries)
            if next_ms <= now_ms:
                next_ms = min(target_ms, now_ms + self.TICK_MS)
            now_ms = next_ms
            first_pass = False

        current["clock"]["simulation_time_ms"] = target_ms
        current = self.validate_snapshot(current)
        events.sort(key=lambda event: (int(event["timestamp_ms"]), int(event["event_index"])))
        return {"snapshot": current, "events": events}

    def resolve_initial_snapshot(
        self,
        actor_snapshot: dict[str, Any] | None = None,
        *,
        floor_id: str | None = None,
        simulation_seed: str = "gds-speech-scheduler-v1",
        spawned_at_ms: int = 0,
    ) -> dict[str, Any]:
        return self.initial_snapshot(
            actor_snapshot,
            floor_id=floor_id,
            simulation_seed=simulation_seed,
            spawned_at_ms=spawned_at_ms,
        )
