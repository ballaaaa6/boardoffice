from __future__ import annotations

"""Deterministic speech timing and conversation trigger scheduler.

Speech owns when a line may start, which floor lane is occupied, and which
conversation mode/plan is eligible.  It does not mutate workstation
ownership, animation registries or stamina.  Central commits an accepted
plan into the actor reducer, which owns the physical talk route and return.
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
    EMOTION_RNG_MASK = (1 << 64) - 1
    EMOTION_RNG_INCREMENT = 0x9E3779B97F4A7C15
    EMOTION_RNG_MIX_1 = 0xBF58476D1CE4E5B9
    EMOTION_RNG_MIX_2 = 0x94D049BB133111EB
    SOLO_CATEGORIES = (
        "encouragement",
        "uncertainty",
        "surprise",
        "work_progress",
        "idle_flavor",
    )
    # The original five-item tuple is kept as a compatibility constant for
    # older callers, but the live work lane now rotates through every authored
    # office category.  These lines are all seated work chatter; none is
    # inferred from a conversation outcome.
    IN_WORK_CATEGORIES = (
        "anticipation",
        "work_progress",
        "work_complete",
        "encouragement",
        "praise",
        "celebration",
        "disappointment",
        "fatigue",
        "surprise",
        "uncertainty",
        "idle_flavor",
    )
    PAIR_CATEGORIES = ("conversation_open", "conversation_reply")
    MODES = ("ceo_front", "seated_host", "standing_pair")
    # Safety and entry lifecycle speech must not starve behind routine pair or
    # solo requests.  Pair requests are represented by the conversation_open
    # category, so keep that key explicit instead of falling through to the
    # solo default.
    PRIORITY = {
        "leaving": 0,
        "fatigue": 1,
        "greeting": 2,
        "work_start": 3,
        "conversation_open": 4,
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

    @classmethod
    def _initial_emotion_rng_state(
        cls,
        simulation_seed: str,
        root_event_counter: int = 0,
    ) -> int:
        """Derive the persisted starting state for the standing-pair d6."""
        return cls._stable_int(
            simulation_seed,
            "standing-pair-emotion-d6",
            int(root_event_counter),
        ) & cls.EMOTION_RNG_MASK

    @classmethod
    def _splitmix64_step(cls, state: int) -> tuple[int, int]:
        """Advance one 64-bit state and return ``(next_state, value)``."""
        next_state = (int(state) + cls.EMOTION_RNG_INCREMENT) & cls.EMOTION_RNG_MASK
        value = next_state
        value = ((value ^ (value >> 30)) * cls.EMOTION_RNG_MIX_1) & cls.EMOTION_RNG_MASK
        value = ((value ^ (value >> 27)) * cls.EMOTION_RNG_MIX_2) & cls.EMOTION_RNG_MASK
        value = (value ^ (value >> 31)) & cls.EMOTION_RNG_MASK
        return next_state, value

    def _peek_emotion_d6(self, snapshot: dict[str, Any]) -> tuple[int, int]:
        """Return the next standing-pair d6 and state without consuming it."""
        determinism = snapshot.get("determinism")
        if not isinstance(determinism, dict):
            raise SpeechSchedulerError("speech snapshot determinism must be an object")
        raw_state = determinism.get("emotion_rng_state")
        if raw_state is None:
            raw_state = self._initial_emotion_rng_state(
                str(determinism.get("simulation_seed", "")),
                int(determinism.get("root_event_counter", 0)),
            )
        state = self._require_int(raw_state, "determinism.emotion_rng_state")
        if state > self.EMOTION_RNG_MASK:
            raise SpeechSchedulerError(
                f"determinism.emotion_rng_state must be <= {self.EMOTION_RNG_MASK}"
            )
        value_space = self.EMOTION_RNG_MASK + 1
        rejection_limit = value_space - (value_space % 6)
        while True:
            state, value = self._splitmix64_step(state)
            if value < rejection_limit:
                return (value % 6) + 1, state

    def _next_emotion_d6(self, snapshot: dict[str, Any]) -> int:
        """Consume one persisted, replayable standing-pair d6 roll."""
        roll, next_state = self._peek_emotion_d6(snapshot)
        snapshot["determinism"]["emotion_rng_state"] = next_state
        return roll

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
        if actor.get("stamina_band") == "critical":
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
        if not isinstance(result.get("dialogue_bags"), dict):
            result["dialogue_bags"] = {}
        for actor in result["actors"].values():
            actor.setdefault("stamina_band", "normal")
            actor.setdefault("work_dialogue_cursor", 0)
            actor.setdefault("work_dialogue_emitted", 0)
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
        stamina = actor.get("stamina") if isinstance(actor.get("stamina"), dict) else {}
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
            "stamina_band": str(stamina.get("threshold_band") or "normal"),
            "last_session_id": None,
            "last_partner_id": None,
            "speech_phase": "idle",
            "emotion": None,
            "emotion_until_ms": None,
            "work_dialogue_cursor": 0,
            "work_dialogue_emitted": 0,
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
                "emotion_rng_state": self._initial_emotion_rng_state(simulation_seed),
            },
            "actors": {},
            "lanes": {},
            "active_sessions": {},
            "dialogue_bags": {},
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
                "queued_requests": [],
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
        determinism = current["determinism"]
        for lane in current["lanes"].values():
            lane.setdefault("queued_requests", [])
        if "emotion_rng_state" not in determinism:
            # Old snapshots did not persist a d6 state.  Seed the migrated
            # state from their deterministic identity so replay remains
            # stable after the first save.
            determinism["emotion_rng_state"] = self._initial_emotion_rng_state(
                str(determinism["simulation_seed"]),
                int(determinism["root_event_counter"]),
            )
        emotion_rng_state = self._require_int(
            determinism["emotion_rng_state"],
            "determinism.emotion_rng_state",
        )
        if emotion_rng_state > self.EMOTION_RNG_MASK:
            raise SpeechSchedulerError(
                f"determinism.emotion_rng_state must be <= {self.EMOTION_RNG_MASK}"
            )
        actor_ids = set(current["actors"])
        for employee_id, actor in current["actors"].items():
            if actor.get("employee_id") != employee_id:
                raise SpeechSchedulerError(f"speech actor key mismatch: {employee_id!r}")
            if actor.get("role") not in {"employee", "ceo"}:
                raise SpeechSchedulerError(f"{employee_id}: unknown speech actor role")
            if actor.get("stamina_band") not in {"normal", "low", "critical"}:
                raise SpeechSchedulerError(f"{employee_id}: unknown stamina band")
            for key in ("work_dialogue_cursor", "work_dialogue_emitted"):
                self._require_int(actor.get(key, 0), f"{employee_id}.{key}")
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
            source_stamina = source.get("stamina") if isinstance(source.get("stamina"), dict) else {}
            if source_stamina.get("threshold_band") in {"normal", "low", "critical"}:
                speech_actor["stamina_band"] = str(source_stamina["threshold_band"])
            previous = speech_actor.get("last_activity")
            if activity != previous:
                if activity == "working":
                    # Work-start is a lifecycle boundary, not a generic
                    # activity-transition side effect.  Central arms it from
                    # an effective ``workseat_entered``/``returned_to_work``
                    # command so a scheduler tick cannot observe the actor
                    # one slice before its seat transition has completed.
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
                    # ``fatigue`` is now an ordinary seated work-dialogue
                    # category.  Keep the old lifecycle line only as an
                    # explicit-home compatibility fallback; an automatic
                    # critical-home route must not create a second departure
                    # bubble while the actor is already walking to the portal.
                    explicit_home = source.get("last_event") == "home_requested"
                    speech_actor["fatigue_pending"] = bool(explicit_home)
                    speech_actor["fatigue_emitted"] = not explicit_home
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
        effective_at = timestamp_ms
        if command_type in {"spawned", "workseat_entered", "returned_to_work"}:
            effective_at = self._require_int(
                command.get("effective_at_ms", timestamp_ms),
                f"{command_type}.effective_at_ms",
            )
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
        if command_type == "cancel_talk":
            actor["external_talk_pending"] = False
            actor["external_talk_due_ms"] = None
            actor["pair_pending"] = False
            actor["pair_next_due_ms"] = timestamp_ms + self._delay_ms(
                snapshot,
                employee_id,
                "retry",
                int(actor.get("departure_token", 0)) + 1,
            )
            return
        if command_type == "spawned":
            actor.update({
                "spawned_at_ms": effective_at,
                "greeting_due_ms": effective_at + self._delay_ms(snapshot, employee_id, "greeting", int(actor["departure_token"]) + 1),
                "greeting_emitted": False,
            })
            return
        if command_type == "workseat_entered":
            actor.update({"work_start_due_ms": effective_at, "work_start_emitted": False})
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
                # Returning actors get the authored entry line again before
                # their next work-start line.  This is the presentation
                # boundary that was previously missing from the live host.
                "greeting_due_ms": effective_at + self._delay_ms(
                    snapshot, employee_id, "greeting", int(actor["departure_token"]) + 1
                ),
                "greeting_emitted": False,
                "work_start_due_ms": effective_at,
                "work_start_emitted": False,
                "solo_next_due_ms": effective_at + self._delay_ms(snapshot, employee_id, "solo", int(actor["departure_token"]) + 1),
                "pair_next_due_ms": (
                    effective_at + self._delay_ms(
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

    @staticmethod
    def _dialogue_key(row: dict[str, Any]) -> str:
        return f"{row.get('dialogue_id')}|{int(row.get('line_index', 0))}"

    def _dialogue_pool(
        self,
        *,
        locale: str,
        category: str,
    ) -> list[dict[str, Any]]:
        """Read the enabled office pool through the conversation registry."""
        if self.conversation is None:
            return []
        try:
            rows = self.conversation._dialogue_lines(locale=locale, category=category)
        except Exception:
            return []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def _take_dialogue_from_bag(
        self,
        snapshot: dict[str, Any],
        *,
        locale: str,
        category: str,
        seed: str | int,
        bag_state: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Reserve one authored line without repeating until the bag refills.

        Bag state is returned separately and committed only after a movement
        plan succeeds.  That keeps retries from burning dialogue lines and
        makes save/load/replay reproduce the exact same sequence.
        """
        locale_key = str(locale).strip().casefold().split("-", 1)[0]
        category_key = str(category).strip()
        pool = self._dialogue_pool(locale=locale_key, category=category_key)
        if not pool:
            return None, None
        by_key = {self._dialogue_key(row): row for row in pool}
        key = f"{locale_key}|{category_key}"
        source = bag_state.get(key) or snapshot.get("dialogue_bags", {}).get(key) or {}
        generation = int(source.get("generation", 0) or 0)
        used_count = int(source.get("used_count", 0) or 0)
        remaining = [item for item in source.get("remaining", []) if item in by_key]
        recent = [str(item) for item in source.get("recent_texts", [])]
        if not remaining:
            generation += 1
            remaining = sorted(
                by_key,
                key=lambda item: self._stable_int(
                    seed, "dialogue-bag", locale_key, category_key, generation, item
                ),
            )
        chosen_key = next(
            (item for item in remaining if str(by_key[item].get("text", "")) not in recent),
            remaining[0],
        )
        remaining.remove(chosen_key)
        chosen = by_key[chosen_key]
        next_recent = (recent + [str(chosen.get("text", ""))])[-4:]
        used_count += 1
        bag_state[key] = {
            "locale": locale_key,
            "category": category_key,
            "generation": generation,
            "used_count": used_count,
            "remaining": remaining,
            "recent_texts": next_recent,
        }
        return chosen, bag_state[key]

    def _dialogue_overrides_for_request(
        self,
        snapshot: dict[str, Any],
        request: dict[str, Any],
        *,
        locale: str,
        seed: str | int,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str]:
        """Build deterministic line overrides for one candidate session."""
        bags = copy.deepcopy(snapshot.get("dialogue_bags", {}))
        overrides: dict[str, Any] = {}
        if request.get("kind") == "pair":
            categories = ("conversation_open", "conversation_reply")
            for employee_id, category in zip(request.get("participants", []), categories):
                row, _state = self._take_dialogue_from_bag(
                    snapshot,
                    locale=locale,
                    category=category,
                    seed=seed,
                    bag_state=bags,
                )
                if row is not None:
                    overrides[str(employee_id)] = {
                        "dialogue_id": row.get("dialogue_id"),
                        "line_index": int(row.get("line_index", 0)),
                    }
            return overrides, bags, "pair_open_reply_bags"

        actor_id = str(request.get("initiator_id"))
        category = str(request.get("category") or "idle_flavor")
        row, _state = self._take_dialogue_from_bag(
            snapshot,
            locale=locale,
            category=category,
            seed=seed,
            bag_state=bags,
        )
        if row is not None:
            overrides[actor_id] = {
                "dialogue_id": row.get("dialogue_id"),
                "line_index": int(row.get("line_index", 0)),
            }
        return overrides, bags, "in_work_category_bag"

    def _bubble_id_for_dialogue(self, line: dict[str, Any] | None) -> str | None:
        """Resolve the registry's smallest-fitting bubble for one line.

        The scheduler records the result in its event/telemetry payload so a
        renderer and the review UI agree on the exact crop.  Shape choice is
        content-driven; it is deliberately not a random or cursor rotation.
        """
        if not isinstance(line, dict) or self.conversation is None:
            return None
        text = line.get("text")
        if not isinstance(text, str) or not text:
            return None
        try:
            selection = self.conversation.movement.characters.dialogue_bubbles.select_bubble(
                text,
                locale=str(line.get("locale") or "en"),
            )
        except Exception:
            return None
        return str(getattr(selection, "bubble_id", "")) or None

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
            candidate = dict(candidate)
            if candidate.get("kind") == "solo" and not candidate.get("category"):
                # Explicit self-talk callers may omit a category.  Put them
                # into the same in-work rotation as automatic speech instead
                # of falling back to a hash-selected line forever.
                actor = snapshot["actors"][candidate["initiator_id"]]
                cursor = int(actor.get("work_dialogue_cursor", 0))
                candidate["category"] = self.IN_WORK_CATEGORIES[cursor % len(self.IN_WORK_CATEGORIES)]
            overrides, bag_state, bag_policy = self._dialogue_overrides_for_request(
                snapshot,
                candidate,
                locale=dialogue_locale,
                seed=f"{dialogue_seed}|{snapshot['determinism']['root_event_counter']}|{candidate.get('initiator_id')}",
            )
            emotion_roll = None
            next_emotion_rng_state = None
            if candidate.get("kind") == "pair" and candidate.get("mode") == "standing_pair":
                emotion_roll, next_emotion_rng_state = self._peek_emotion_d6(snapshot)
            try:
                if candidate["kind"] == "pair":
                    plan = self.conversation.plan_conversation(
                        candidate["initiator_id"],
                        partner_id=candidate["partner_id"],
                        mode=candidate["mode"],
                        snapshot=conversation_snapshot,
                        dialogue_locale=dialogue_locale,
                        dialogue_seed=dialogue_seed,
                        dialogue_line_overrides=overrides,
                        emotion_roll=emotion_roll,
                    )
                else:
                    plan = self.conversation.plan_self_talk(
                        candidate["initiator_id"],
                        snapshot=conversation_snapshot,
                        dialogue_locale=dialogue_locale,
                        dialogue_category=(
                            candidate.get("category")
                        ),
                        dialogue_seed=dialogue_seed,
                        dialogue_line_overrides=overrides,
                    )
            except Exception:
                # A pair is not started without a valid movement/spot/dialogue
                # plan.  The next seeded candidate may still be usable.
                continue
            if plan.get("ready"):
                if next_emotion_rng_state is not None:
                    snapshot["determinism"]["emotion_rng_state"] = next_emotion_rng_state
                snapshot["dialogue_bags"] = bag_state
                plan["dialogue_selection"] = {
                    "policy": bag_policy,
                    "overrides": copy.deepcopy(overrides),
                }
                return candidate, plan
        if request.get("external") and request.get("kind") == "pair":
            # A valid partner may exist while every pair geometry candidate is
            # temporarily unavailable.  Do not leave the actor in an
            # unbounded pending state: use the declared seated self-talk
            # fallback and let the actor reducer own the same completion path.
            fallback = {
                "kind": "solo",
                "category": "idle_flavor",
                "mode": "self_talk",
                "participants": [request["initiator_id"]],
                "initiator_id": request["initiator_id"],
                "external": True,
                "fallback": "self_talk",
            }
            try:
                overrides, bag_state, bag_policy = self._dialogue_overrides_for_request(
                    snapshot,
                    fallback,
                    locale=dialogue_locale,
                    seed=f"{dialogue_seed}|{snapshot['determinism']['root_event_counter']}|{fallback['initiator_id']}",
                )
                plan = self.conversation.plan_self_talk(
                    fallback["initiator_id"],
                    snapshot=conversation_snapshot,
                    dialogue_locale=dialogue_locale,
                    dialogue_category=fallback["category"],
                    dialogue_seed=dialogue_seed,
                    dialogue_line_overrides=overrides,
                )
            except Exception:
                plan = None
            if isinstance(plan, dict) and plan.get("ready"):
                snapshot["dialogue_bags"] = bag_state
                plan["dialogue_selection"] = {
                    "policy": bag_policy,
                    "overrides": copy.deepcopy(overrides),
                }
                return fallback, plan
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
            "emotion_roll": None,
            "emotion_outcome": None,
            "emotion_hold_ms": 0,
            # Lifecycle and seated work speech are presentation-only.  Only
            # the standing-pair emotion boundary below is allowed to carry a
            # numeric stamina delta into Central/ActorSimulationCore.
            "numeric_effect_policy": "none",
            "stamina_effect_milli": 0,
            "score_delta": 0,
            "stamina_effect_hook": "none",
            "stamina_effect_milli_by_emotion": {"sad": -1000, "happy": 2000},
            "bubble_selection_policy": "smallest_allowed_fit",
            "bubble_started": False,
            "bubble_start_event_emitted": False,
        }
        dialogue_by_actor = (
            plan.get("dialogue_by_actor", {})
            if isinstance(plan, dict) and isinstance(plan.get("dialogue_by_actor"), dict)
            else {}
        )
        if kind == "pair":
            first, second = participants[0], participants[1]
            first_bubble = self._bubble_id_for_dialogue(dialogue_by_actor.get(first))
            second_bubble = self._bubble_id_for_dialogue(dialogue_by_actor.get(second))
            session["bubble_schedule"] = [
                {
                    "employee_id": first,
                    "category": "conversation_open",
                    "start_ms": bubble_start_ms,
                    "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                    "fade_end_ms": fade_end,
                    "turn_index": 0,
                    "preferred_bubble_id": first_bubble,
                },
                {
                    "employee_id": second,
                    "category": "conversation_reply",
                    "start_ms": bubble_start_ms + 500,
                    "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                    "fade_end_ms": fade_end,
                    "turn_index": 1,
                    "preferred_bubble_id": second_bubble,
                },
            ]
            if mode == "standing_pair":
                if plan is None:
                    # Keep the scheduler usable as a standalone timing
                    # reducer.  The Central path supplies the same roll to
                    # the conversation plan before reaching this branch.
                    emotion_roll = self._next_emotion_d6(snapshot)
                    emotion_outcome = "happy" if emotion_roll % 2 == 0 else "sad"
                    emotion_hold_ms = self.EMOTION_HOLD_MS
                else:
                    emotion = plan.get("emotion", {}) if isinstance(plan, dict) else {}
                    emotion_roll = emotion.get("roll") if isinstance(emotion, dict) else None
                    emotion_outcome = emotion.get("outcome") if isinstance(emotion, dict) else None
                    if (
                        isinstance(emotion_roll, bool)
                        or not isinstance(emotion_roll, int)
                        or not 1 <= emotion_roll <= 6
                    ):
                        raise SpeechSchedulerError(
                            "standing_pair session needs one conversation-plan emotion d6 roll"
                        )
                    if emotion_outcome != ("happy" if emotion_roll % 2 == 0 else "sad"):
                        raise SpeechSchedulerError(
                            "standing_pair emotion outcome does not match the conversation-plan d6 roll"
                        )
                    emotion_hold_ms = emotion.get("hold_ms", 0) if isinstance(emotion, dict) else 0
                    emotion_hold_ms = self._require_int(
                        emotion_hold_ms,
                        "conversation_plan.emotion.hold_ms",
                    )
                session["emotion_roll"] = emotion_roll
                session["emotion_outcome"] = emotion_outcome
                session["emotion_hold_ms"] = emotion_hold_ms
        else:
            preferred_bubble = self._bubble_id_for_dialogue(dialogue_by_actor.get(participants[0]))
            session["bubble_schedule"] = [{
                "employee_id": participants[0],
                "category": category,
                "start_ms": bubble_start_ms,
                "visible_end_ms": bubble_start_ms + self.BUBBLE_VISIBLE_MS,
                "fade_end_ms": fade_end,
                "turn_index": 0,
                "preferred_bubble_id": preferred_bubble,
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
            if request.get("external"):
                actor["external_talk_pending"] = False
                actor["external_talk_due_ms"] = None
            actor["last_session_id"] = session_id
            actor["last_partner_id"] = request.get("partner_id")
            if kind == "solo":
                actor["work_dialogue_cursor"] = int(actor.get("work_dialogue_cursor", 0)) + 1
                actor["work_dialogue_emitted"] = int(actor.get("work_dialogue_emitted", 0)) + 1
            if kind == "lifecycle" and category == "greeting":
                actor["greeting_emitted"] = True
            elif kind == "lifecycle" and category == "work_start":
                actor["work_start_emitted"] = True
            elif kind == "lifecycle" and category == "fatigue":
                actor["fatigue_emitted"] = True
                actor["fatigue_pending"] = False
            elif kind == "lifecycle" and category == "leaving":
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
            emotion_roll=session["emotion_roll"],
            emotion_outcome=session["emotion_outcome"],
            available_modes=session["available_modes"],
            selection_policy=session["selection_policy"],
            numeric_effect_policy=session["numeric_effect_policy"],
            stamina_effect_milli=session["stamina_effect_milli"],
            score_delta=session["score_delta"],
            bubble_selection_policy=session["bubble_selection_policy"],
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
            session["numeric_effect_policy"] = "standing_pair_emotion_only"
            session["stamina_effect_hook"] = "actor_snapshot_numeric_delta"
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
                emotion_roll=session.get("emotion_roll"),
                participants=participants,
                stamina_effect_hook="actor_snapshot_numeric_delta",
                stamina_effect_milli_by_emotion={"sad": -1000, "happy": 2000},
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
        lifecycle_available = (
            self._actor_present(actor)
            and not actor.get("locked")
            and actor.get("stamina_band") != "critical"
            and (
                self._actor_activity(actor) == "working"
                or bool(actor.get("external_talk_pending"))
            )
        )
        if lifecycle_available and (
            not actor.get("greeting_emitted")
            and actor.get("greeting_due_ms") is not None
            and int(actor["greeting_due_ms"]) <= now_ms
        ):
            return {
                "kind": "lifecycle", "category": "greeting", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        if lifecycle_available and (
            not actor.get("work_start_emitted")
            and actor.get("work_start_due_ms") is not None
            and int(actor["work_start_due_ms"]) <= now_ms
        ):
            return {
                "kind": "lifecycle", "category": "work_start", "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        # A bridge-requested talk is an actor lifecycle request, not a
        # presentation-only hint.  Keep it pending if an entry lifecycle line
        # is due so greeting/work-start cannot be starved by pair traffic.
        if (
            actor.get("external_talk_pending")
            and (
                actor.get("external_talk_due_ms") is None
                or int(actor.get("external_talk_due_ms")) <= now_ms
            )
        ):
            # The CEO is host-only: an actor-generated talk request cannot
            # make the CEO leave the desk, so its declared fallback is a
            # seated self-talk session.  Employees use the same fallback
            # when no same-floor partner/mode is currently available.
            if actor.get("role") == "ceo":
                return {
                    "kind": "solo",
                    "category": "idle_flavor",
                    "mode": "self_talk",
                    "participants": [employee_id],
                    "initiator_id": employee_id,
                    "external": True,
                    "fallback": "self_talk",
                }
            request = self._mode_request(
                snapshot,
                employee_id,
                counter=int(actor.get("speech_event_counter", 0)) + 1,
            )
            if request is not None:
                request["external"] = True
                return request
            return {
                "kind": "solo",
                "category": "idle_flavor",
                "mode": "self_talk",
                "participants": [employee_id],
                "initiator_id": employee_id,
                "external": True,
                "fallback": "self_talk",
            }
        if not self._actor_available(actor):
            return None
        # Entry lifecycle speech owns the first visible moment at a desk.
        # A pair that became due while the actor was away must wait until the
        # greeting/work-start boundary has been emitted, otherwise a return
        # can appear to skip its authored arrival line.
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
            # Rotate the complete authored in-work category set in order.  A
            # cursor is persisted on the speech actor, so every category gets
            # a turn and save/replay cannot collapse to the same five lines.
            index = int(actor.get("work_dialogue_cursor", 0)) % len(self.IN_WORK_CATEGORIES)
            return {
                "kind": "solo", "category": self.IN_WORK_CATEGORIES[index], "mode": "self_talk",
                "participants": [employee_id], "initiator_id": employee_id,
            }
        return None

    def _queued_request_metadata(
        self,
        snapshot: dict[str, Any],
        request: dict[str, Any],
        *,
        now_ms: int,
    ) -> dict[str, Any]:
        employee_id = str(request["initiator_id"])
        actor = snapshot["actors"][employee_id]
        category = str(request.get("category") or request.get("kind") or "solo")
        due_key = {
            "greeting": "greeting_due_ms",
            "work_start": "work_start_due_ms",
            "pair": "pair_next_due_ms",
            "conversation_open": "pair_next_due_ms",
            "solo": "solo_next_due_ms",
            "leaving": "leaving_due_ms",
            "fatigue": "external_talk_due_ms",
        }.get(category)
        due_value = actor.get(due_key) if due_key else None
        due_ms = int(due_value) if due_value is not None else int(now_ms)
        token = ":".join((
            str(actor.get("departure_token", 0)),
            str(actor.get("speech_event_counter", 0)),
            category,
            str(request.get("partner_id") or ""),
        ))
        return {
            "request_id": f"speech-request:{employee_id}:{token}",
            "initiator_id": employee_id,
            "kind": str(request.get("kind") or "solo"),
            "category": category,
            "mode": str(request.get("mode") or "self_talk"),
            "participants": [str(value) for value in request.get("participants", [employee_id])],
            "due_ms": due_ms,
            "external": bool(request.get("external", False)),
        }

    def _retry_request(self, snapshot: dict[str, Any], request: dict[str, Any], *, now_ms: int) -> None:
        employee_id = request["initiator_id"]
        actor = snapshot["actors"][employee_id]
        if request.get("external"):
            # Keep the actor-owned request pending.  A failed geometry/partner
            # plan must retry deterministically instead of being silently
            # converted into routine chatter.
            actor["external_talk_pending"] = True
            actor["external_talk_due_ms"] = now_ms + self._delay_ms(
                snapshot, employee_id, "retry", int(actor.get("departure_token", 0)) + 1
            )
        elif request["kind"] == "pair":
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
        validate: bool = True,
    ) -> dict[str, Any]:
        """Advance speech timers and return events.

        The default keeps the input snapshot untouched; trusted in-place host
        loops may pass ``validate=False`` to avoid a defensive deep copy.
        """
        # A host that owns a previously validated snapshot can opt into the
        # in-place path.  This avoids repeatedly deep-copying active talk
        # route/dialogue plans during a live preview; callers keep the safe,
        # copy-isolated default by omitting ``validate``.
        current = self.validate_snapshot(snapshot) if validate else snapshot
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
            # Queue metadata is a live projection, not a durable request
            # store.  Clear it before rebuilding eligibility so an actor that
            # became locked/talking/away cannot leave a ghost request visible
            # after its lane has stopped reporting it.
            for lane in current["lanes"].values():
                lane["queued_session_ids"] = []
                lane["queued_requests"] = []
            for employee_id in sorted(current["actors"]):
                request = self._request_for_actor(current, employee_id, now_ms=now_ms)
                if request is not None:
                    floor = current["actors"][employee_id]["floor_id"]
                    by_floor.setdefault(floor, []).append(request)
            for floor_id in sorted(by_floor):
                lane = current["lanes"][floor_id]
                request_records = [
                    (
                        request,
                        self._queued_request_metadata(
                            current,
                            request,
                            now_ms=now_ms,
                        ),
                    )
                    for request in by_floor[floor_id]
                ]
                request_records.sort(
                    key=lambda record: (
                        self.PRIORITY.get(
                            record[1]["category"],
                            self.PRIORITY["solo"],
                        ),
                        int(record[1]["due_ms"]),
                        record[1]["initiator_id"],
                    )
                )
                queued_metadata = [metadata for _request, metadata in request_records]
                if lane.get("active_session_id") is not None:
                    lane["queued_session_ids"] = [item["initiator_id"] for item in queued_metadata]
                    lane["queued_requests"] = queued_metadata
                    continue
                lane["queued_session_ids"] = []
                lane["queued_requests"] = []
                for request, _metadata in request_records:
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
        if validate:
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
