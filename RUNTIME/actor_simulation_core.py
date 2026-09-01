from __future__ import annotations

"""Persistent, renderer-agnostic actor state and stamina runtime.

This module owns only JSON-safe simulation state.  Employee metadata remains
the immutable source for identity, workstation ownership and per-employee
stamina profiles.  Conversation plans are accepted through an explicit
``start_talk_session`` command; this reducer then owns the outbound/hold/
return route and the recovery-owner completion.  Renderers may consume the
returned state/events, but visual registries never mutate stamina here.
"""

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable

from jsonschema import Draft202012Validator

from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from RUNTIME.employee_registry import EmployeeMetadataError, EmployeeMetadataRegistry
from WORLD.RUNTIME.pathfinding_core import PathfindingError


class ActorSimulationError(ValueError):
    """Raised when an actor snapshot or deterministic tick cannot be resolved."""


class ActorSimulationCore:
    CONTRACT_SCHEMA = "gds.actor_simulation.v1"
    SNAPSHOT_SCHEMA = "gds.actor_snapshot.v1"
    VERSION = "1.0.0"
    TICK_MS = 60
    MILLI_SCALE = 1000
    MAX_STAMINA_MILLI = 100000
    LOW_THRESHOLD_MILLI = 30000
    CRITICAL_THRESHOLD_MILLI = 10000
    # The canonical ``normal_work`` action is two character frames.  With the
    # approved 360ms character cadence, one complete work pose loop is 720ms.
    # Critical actors finish this visual loop before the home route starts.
    WORK_CHARACTER_FRAME_MS = 360
    WORK_NORMAL_FRAME_COUNT = 2
    WORK_LOOP_MS = WORK_CHARACTER_FRAME_MS * WORK_NORMAL_FRAME_COUNT
    # Emotion outcomes are gameplay bonuses/penalties in display stamina
    # units.  Keep the storage math integer and clamp at [0, max].
    EMOTION_STAMINA_EFFECT_MILLI = {"sad": -1000, "happy": 2000}
    PRESENCE_VALUES = ("home", "entering", "present", "leaving")
    ACTIVITY_VALUES = (
        "walking_to_work",
        "working",
        "talking",
        "wandering",
        "popup_event",
        "going_home",
        "home_recovery",
        "returning_to_work",
    )
    THRESHOLD_BANDS = ("normal", "low", "critical")
    WEIGHTED_EVENTS = ("talk", "background_effect", "popup", "wander")
    EVENT_ACTIVITY = {
        "talk": "talking",
        "background_effect": "popup_event",
        "popup": "popup_event",
        "wander": "wandering",
    }
    EVENT_LAST_EVENT = {
        "talk": "talk_recovery",
        "background_effect": "background_effect_recovery",
        "popup": "popup_recovery",
        "wander": "wander_recovery",
    }
    EVENT_COOLDOWN_KEYS = (*WEIGHTED_EVENTS, "going_home")
    PORTAL_FADE_STEPS = 4
    ROUTE_PHASES = (
        "to_portal",
        "portal_exit",
        "portal_entry",
        "to_workseat",
        "wander_out",
        "wander_back",
        "talk_outbound",
        "talk_hold",
        "talk_return",
    )
    ROUTE_ACTIVITIES = ("going_home", "returning_to_work")
    WANDER_ROUTE_PHASES = ("wander_out", "wander_back")
    TALK_ROUTE_PHASES = ("talk_outbound", "talk_hold", "talk_return")
    TALK_QUEUE_TIMEOUT_MS = 30_000

    def __init__(
        self,
        root: str | Path,
        *,
        employee_registry: EmployeeMetadataRegistry | None = None,
        slot_resolver: Callable[[str, str], dict[str, Any]] | None = None,
        movement: CharacterMovementCore | None = None,
        pathfinding: Any | None = None,
        portal_lifecycle: Any | None = None,
        work_seat_lifecycle: Any | None = None,
    ):
        self.root = Path(root).resolve()
        self.employee_registry = employee_registry or EmployeeMetadataRegistry(self.root)
        self.slot_resolver = slot_resolver
        self.movement = movement or CharacterMovementCore(
            self.root,
            employee_registry=self.employee_registry,
        )
        self.pathfinding = pathfinding or self.movement.pathfinding
        self.portal_lifecycle = portal_lifecycle
        self.work_seat_lifecycle = work_seat_lifecycle
        self.contract_path = self.root / "CONTRACTS" / "actor_simulation.json"
        self.snapshot_schema_path = self.root / "SCHEMA" / "actor_snapshot.schema.json"
        try:
            self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
            self.snapshot_schema = json.loads(
                self.snapshot_schema_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ActorSimulationError("Actor simulation contract/schema cannot be loaded") from exc
        if self.contract.get("schema") != self.CONTRACT_SCHEMA:
            raise ActorSimulationError(
                f"Unsupported actor simulation contract: {self.contract.get('schema')!r}"
            )
        self._snapshot_validator = Draft202012Validator(self.snapshot_schema)
        stamina = self.contract.get("stamina", {})
        behavior = self.contract.get("behavior", {})
        talk_policy = behavior.get("talk_session_policy", {})
        try:
            self.TALK_QUEUE_TIMEOUT_MS = int(
                talk_policy.get("queue_timeout_ms", self.TALK_QUEUE_TIMEOUT_MS)
            )
        except (TypeError, ValueError) as exc:
            raise ActorSimulationError("Actor talk queue timeout is invalid") from exc
        if self.TALK_QUEUE_TIMEOUT_MS <= 0:
            raise ActorSimulationError("Actor talk queue timeout must be positive")
        self._selection_weights = {
            event: int(weight)
            for event, weight in behavior.get("selection_weights", {}).items()
        }
        self._recovery_events = self.employee_registry.stamina_policy().get(
            "recovery_events", {}
        )
        self._work_cycle_range = self.employee_registry.stamina_policy().get(
            "target_work_cycle_seconds_range", [120, 300]
        )
        policy = self.employee_registry.stamina_policy()
        if policy.get("tuning_status") != "initial_runtime_tuning_author_review_pending":
            raise ActorSimulationError(
                "Employee stamina policy must remain initial tuning until author review"
            )
        if int(policy.get("normal_work_loop_ms", self.WORK_LOOP_MS)) != self.WORK_LOOP_MS:
            raise ActorSimulationError("Employee stamina policy has unexpected normal-work loop")
        emotion_policy = policy.get("emotion_effects", {})
        for emotion, expected in (("sad", -1000), ("happy", 2000)):
            actual = (
                emotion_policy.get(emotion, {}).get("milli_delta")
                if isinstance(emotion_policy.get(emotion), dict)
                else None
            )
            if int(actual or 0) != expected:
                raise ActorSimulationError(
                    f"Employee stamina policy has unexpected {emotion} emotion delta"
                )
        if not self._selection_weights or sum(self._selection_weights.values()) != 100:
            raise ActorSimulationError("Actor simulation selection weights must sum to 100")
        if (
            int(stamina.get("max_milli", 0)) != self.MAX_STAMINA_MILLI
            or int(stamina.get("low_threshold_milli", 0)) != self.LOW_THRESHOLD_MILLI
            or int(stamina.get("critical_threshold_milli", 0))
            != self.CRITICAL_THRESHOLD_MILLI
        ):
            raise ActorSimulationError("Actor simulation stamina contract has unexpected thresholds")

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
            raise ActorSimulationError(f"{name} must be an integer >= {minimum}")
        return int(value)

    @classmethod
    def _quantize_ms(cls, milliseconds: int) -> int:
        milliseconds = max(cls.TICK_MS, int(milliseconds))
        return max(cls.TICK_MS, int(round(milliseconds / cls.TICK_MS)) * cls.TICK_MS)

    @classmethod
    def _threshold_band(cls, current_milli: int) -> str:
        if current_milli <= cls.CRITICAL_THRESHOLD_MILLI:
            return "critical"
        if current_milli <= cls.LOW_THRESHOLD_MILLI:
            return "low"
        return "normal"

    @staticmethod
    def _threshold_rank(band: str) -> int:
        return {"normal": 2, "low": 1, "critical": 0}[band]

    @classmethod
    def _work_loop_elapsed(cls, actor: dict[str, Any]) -> int:
        """Return the current normal-work animation phase in milliseconds."""
        behavior = actor.get("behavior", {})
        value = behavior.get("work_loop_elapsed_ms", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ActorSimulationError("work_loop_elapsed_ms must be an integer")
        if value < 0 or value >= cls.WORK_LOOP_MS:
            raise ActorSimulationError(
                f"work_loop_elapsed_ms must be in [0, {cls.WORK_LOOP_MS})"
            )
        return int(value)

    @classmethod
    def _advance_work_loop(cls, actor: dict[str, Any], elapsed_ms: int) -> int:
        """Advance the work-pose phase and return how many loop boundaries crossed."""
        if elapsed_ms <= 0:
            return 0
        before = cls._work_loop_elapsed(actor)
        total = before + int(elapsed_ms)
        completed = total // cls.WORK_LOOP_MS
        actor["behavior"]["work_loop_elapsed_ms"] = total % cls.WORK_LOOP_MS
        # ``work_loop_elapsed_ms`` is deliberately bounded because it is also
        # the critical-home boundary clock.  PC animation needs the separate
        # count of completed normal-work loops so its five authored cells can
        # advance instead of dividing the already-wrapped phase.
        if completed:
            previous_count = actor["behavior"].get("work_loop_count", 0)
            if (
                isinstance(previous_count, bool)
                or not isinstance(previous_count, int)
                or previous_count < 0
            ):
                raise ActorSimulationError("work_loop_count must be an integer >= 0")
            actor["behavior"]["work_loop_count"] = previous_count + completed
        return completed

    @classmethod
    def _next_work_loop_boundary_ms(
        cls,
        *,
        timestamp_ms: int,
        loop_elapsed_ms: int,
    ) -> int:
        """Return the next 720ms boundary at or after ``timestamp_ms``."""
        elapsed = int(loop_elapsed_ms)
        if elapsed < 0 or elapsed >= cls.WORK_LOOP_MS:
            raise ActorSimulationError("Invalid normal-work loop phase")
        remaining = cls.WORK_LOOP_MS - elapsed
        return int(timestamp_ms) + remaining

    @staticmethod
    def _assignment_fields() -> tuple[str, ...]:
        return ("floor_id", "workstation_id", "slot_id", "assignment_order", "facing")

    def _assignment_payload(self, employee: dict[str, Any]) -> dict[str, Any]:
        assignment = employee.get("assignment")
        if not isinstance(assignment, dict):
            raise ActorSimulationError(
                f"{employee.get('employee_id')}: unassigned employees are not active actors"
            )
        return {field: self._copy(assignment[field]) for field in self._assignment_fields()}

    def _profile(self, employee: dict[str, Any]) -> dict[str, Any]:
        profile = employee.get("stamina_profile")
        if not isinstance(profile, dict):
            raise ActorSimulationError(f"{employee.get('employee_id')}: stamina profile is missing")
        if profile.get("stamina_max") != 100:
            raise ActorSimulationError(
                f"{employee.get('employee_id')}: stamina profile max must be 100"
            )
        return profile

    def _validate_slot(self, assignment: dict[str, Any]) -> None:
        if self.slot_resolver is None:
            return
        try:
            slot = self.slot_resolver(assignment["floor_id"], assignment["workstation_id"])
        except Exception as exc:  # runtime resolver errors become contract errors at this boundary
            raise ActorSimulationError(
                f"Unable to resolve workstation slot {assignment['floor_id']}.{assignment['workstation_id']}"
            ) from exc
        for field in ("slot_id", "floor_id", "workstation_id", "capacity"):
            expected = assignment.get(field)
            if field == "capacity":
                expected = 1
            if slot.get(field) != expected:
                raise ActorSimulationError(
                    f"Assignment slot mismatch for {assignment['floor_id']}.{assignment['workstation_id']}: "
                    f"{field}={assignment.get(field)!r} != {slot.get(field)!r}"
                )
        if not slot.get("seat_transition_ready"):
            raise ActorSimulationError(
                f"Assignment slot is not ready: {assignment['floor_id']}.{assignment['workstation_id']}"
            )

    @staticmethod
    def _normalize_uv(uv: tuple[int, int] | list[int], *, name: str = "uv") -> tuple[int, int]:
        if not isinstance(uv, (tuple, list)) or len(uv) != 2:
            raise ActorSimulationError(f"{name} must be a two-item coordinate")
        values: list[int] = []
        for value in uv:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ActorSimulationError(f"{name} must contain integer coordinates")
            values.append(int(value))
        return values[0], values[1]

    @staticmethod
    def _round_xy(xy: tuple[float, float] | list[float]) -> list[float]:
        return [round(float(xy[0]), 4), round(float(xy[1]), 4)]

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _portal_pair(self, floor_id: str) -> tuple[tuple[int, int], tuple[int, int]]:
        """Resolve the authored inside/outside portal cells without copying geometry."""
        try:
            inside = self._normalize_uv(
                self.pathfinding.resolve_portal_start(floor_id),
                name="portal inside_uv",
            )
            portal = self.movement.navigation.portal(floor_id)
        except (PathfindingError, KeyError, ValueError, AttributeError) as exc:
            raise ActorSimulationError(f"Unable to resolve portal for {floor_id}") from exc
        outside_cells = [
            self._normalize_uv(cell, name="portal outside_uv")
            for cell in portal.get("outside_cells_uv", [])
        ]
        if not outside_cells:
            raise ActorSimulationError(f"{floor_id}: portal has no outside cells")
        adjacent = [cell for cell in outside_cells if self._manhattan(cell, inside) == 1]
        outside = min(
            adjacent or outside_cells,
            key=lambda cell: (self._manhattan(cell, inside), cell[1], cell[0]),
        )
        return inside, outside

    def _workseat_gate(self, assignment: dict[str, Any]) -> tuple[int, int]:
        floor_id = str(assignment["floor_id"])
        workstation_id = str(assignment["workstation_id"])
        try:
            if self.slot_resolver is not None:
                slot = self.slot_resolver(floor_id, workstation_id)
                gate = slot.get("transition_gate_uv") if isinstance(slot, dict) else None
            else:
                # The occupancy compiler is the fallback source when this
                # reducer is used directly instead of through Central.
                gate = self.pathfinding.occupancy.workstation_access(
                    floor_id, workstation_id
                ).get("transition_gate_uv")
        except Exception as exc:
            raise ActorSimulationError(
                f"Unable to resolve workstation gate {floor_id}.{workstation_id}"
            ) from exc
        if gate is None:
            raise ActorSimulationError(
                f"{floor_id}.{workstation_id}: workstation has no transition gate"
            )
        return self._normalize_uv(gate, name="transition_gate_uv")

    def _route_path(
        self,
        floor_id: str,
        start_uv: tuple[int, int],
        goal_uv: tuple[int, int],
    ) -> list[tuple[int, int]]:
        try:
            result = self.pathfinding.find_path(floor_id, start_uv, goal_uv)
            path = [
                self._normalize_uv(cell, name="path_cells_uv")
                for cell in result.get("path_cells_uv", [])
            ]
        except (PathfindingError, KeyError, TypeError, ValueError) as exc:
            raise ActorSimulationError(
                f"Unable to route {floor_id}: {start_uv} -> {goal_uv}"
            ) from exc
        if not path or path[0] != start_uv or path[-1] != goal_uv:
            raise ActorSimulationError(
                f"Invalid route {floor_id}: {start_uv} -> {goal_uv}"
            )
        return path

    def _movement_profile(self, employee: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.movement.resolve_employee_movement_profile(employee["employee_id"])
        except (CharacterMovementError, KeyError, TypeError, ValueError) as exc:
            raise ActorSimulationError(
                f"Unable to resolve movement profile for {employee.get('employee_id')}"
            ) from exc

    def _route_duration_ms(
        self,
        path: list[tuple[int, int]],
        employee: dict[str, Any],
    ) -> int:
        if len(path) < 2:
            return self.TICK_MS
        profile = self._movement_profile(employee)
        try:
            samples = self.movement.sample_path_timeline(
                path,
                speed_multiplier=float(profile["speed_multiplier"]),
                tick_ms=self.TICK_MS,
            )
        except (CharacterMovementError, KeyError, TypeError, ValueError) as exc:
            raise ActorSimulationError("Unable to sample actor route") from exc
        return max(self.TICK_MS, len(samples) * self.TICK_MS)

    def _route_record(
        self,
        *,
        phase: str,
        start_uv: tuple[int, int],
        target_uv: tuple[int, int],
        path: list[tuple[int, int]],
        duration_ms: int,
        elapsed_ms: int = 0,
        direction: str | None = None,
        action: str = "move",
        subaction: str = "idle",
        visibility_alpha: float = 1.0,
    ) -> dict[str, Any]:
        if phase not in self.ROUTE_PHASES:
            raise ActorSimulationError(f"Unknown actor route phase: {phase!r}")
        if action not in {"move", "idle", "happy", "sad"}:
            raise ActorSimulationError(f"Unknown actor route action: {action!r}")
        return {
            "phase": phase,
            "start_uv": list(start_uv),
            "target_uv": list(target_uv),
            "path_cells_uv": [list(cell) for cell in path],
            "elapsed_ms": int(elapsed_ms),
            "duration_ms": int(duration_ms),
            "render_owner": "walking_depth",
            "action": action,
            "subaction": subaction,
            "direction": direction,
            "raw_direction": direction,
            "visibility_alpha": round(max(0.0, min(1.0, float(visibility_alpha))), 4),
        }

    def _queue_critical_home(
        self,
        actor: dict[str, Any],
        *,
        timestamp_ms: int,
        boundary_ms: int | None = None,
    ) -> int:
        """Mark a working actor for a smooth home exit at a work-loop boundary."""
        behavior = actor["behavior"]
        if bool(behavior.get("pending_home")):
            due = behavior.get("pending_home_due_ms")
            if due is None:
                raise ActorSimulationError(
                    f"{actor['employee_id']}: pending home lacks a boundary timestamp"
                )
            return int(due)
        loop_elapsed = self._work_loop_elapsed(actor)
        due = (
            int(boundary_ms)
            if boundary_ms is not None
            else self._next_work_loop_boundary_ms(
                timestamp_ms=int(timestamp_ms),
                loop_elapsed_ms=loop_elapsed,
            )
        )
        if due < int(timestamp_ms):
            raise ActorSimulationError(
                f"{actor['employee_id']}: home boundary precedes current time"
            )
        behavior["pending_home"] = True
        behavior["pending_home_due_ms"] = due
        return due

    def _begin_home_route(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
        reason: str = "explicit",
        work_loop_completed: bool = False,
    ) -> None:
        """Start the authored gate-to-portal route, preserving assignment ownership."""
        if actor["presence"] != "present" or actor["activity"] == "talking":
            raise ActorSimulationError(
                f"{actor['employee_id']}: actor cannot begin home route in current state"
            )
        assignment = actor["assignment"]
        floor_id = assignment["floor_id"]
        gate = self._workseat_gate(assignment)
        inside, _outside = self._portal_pair(floor_id)
        path = self._route_path(floor_id, gate, inside)
        actor["presence"] = "leaving"
        actor["activity"] = "going_home"
        actor["conversation_phase"] = None
        actor["behavior"]["next_event_due_ms"] = None
        actor["behavior"]["active_event"] = None
        actor["behavior"]["pending_home"] = False
        actor["behavior"]["pending_home_due_ms"] = None
        actor["behavior"]["work_loop_elapsed_ms"] = 0
        actor["behavior"]["work_loop_count"] = 0
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = None
        actor["last_event"] = "critical_home_requested" if reason == "stamina_critical" else "home_requested"
        self._start_route(
            actor,
            employee,
            phase="to_portal",
            start_uv=gate,
            target_uv=inside,
            path=path,
        )
        payload: dict[str, Any] = {"assignment_retained": True}
        if reason != "explicit" or work_loop_completed:
            payload.update({
                "reason": reason,
                "work_loop_completed": bool(work_loop_completed),
            })
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            employee_id=actor["employee_id"],
            event_type="home_requested",
            **payload,
        )

    def _home_recovery_delay_ms(self, employee: dict[str, Any], actor: dict[str, Any]) -> int:
        profile = self._profile(employee)
        values = profile.get("home_delay_seconds_range")
        if not isinstance(values, list) or len(values) != 2:
            values = self.employee_registry.stamina_policy().get("home_policy", {}).get(
                "delay_seconds_range", [8, 20]
            )
        if not isinstance(values, list) or len(values) != 2:
            raise ActorSimulationError("Invalid home delay range")
        lower, upper = int(values[0]), int(values[1])
        if lower < 1 or upper < lower:
            raise ActorSimulationError("Invalid home delay range")
        ticket = self._stable_int(
            employee["employee_id"],
            profile.get("profile_seed"),
            "home-recovery",
            int(actor["behavior"].get("event_counter", 0)),
        )
        return self._quantize_ms((lower + ticket % (upper - lower + 1)) * 1000)

    def _presentation_for_behavior(
        self,
        employee: dict[str, Any],
        event: str,
        *,
        counter: int,
    ) -> dict[str, Any]:
        """Describe the visual channel while leaving its clock to the renderer."""
        refs = self.employee_registry.stamina_policy().get(
            "visual_recovery_references", {}
        )
        if event == "talk":
            return {
                "channel": "conversation",
                "behavior": "talk",
                "binding": "speech_scheduler_behavior_request",
            }
        if event == "background_effect":
            ids = refs.get("effect_ids", []) if isinstance(refs, dict) else []
            asset_id = ids[
                self._stable_int(employee["employee_id"], event, counter) % len(ids)
            ] if ids else None
            return {
                "channel": "vfx",
                "asset_id": asset_id,
                "render_owner": "work_seat",
                "action": "work",
                "subaction": "normal_work",
                "character_frame_ms": 360,
                "effect_frame_ms": 240,
            }
        if event == "popup":
            ids = refs.get("humanball_ids", []) if isinstance(refs, dict) else []
            asset_id = ids[
                self._stable_int(employee["employee_id"], event, counter) % len(ids)
            ] if ids else None
            return {
                "channel": "humanball",
                "asset_id": asset_id,
                "render_owner": "work_seat",
                "action": "work",
                "subaction": "normal_work",
                "character_frame_ms": 360,
                "humanball_frame_ms": 240,
            }
        return {
            "channel": "movement",
            "render_owner": "walking_depth",
            "action": "move",
            "subaction": "idle",
        }

    def _interval_bounds(self, event: str | None = None) -> tuple[int, int]:
        if event is not None:
            policy = self._recovery_events.get(event)
            if not isinstance(policy, dict):
                raise ActorSimulationError(f"Unknown recovery event: {event!r}")
            values = policy.get("interval_seconds_range")
        else:
            values = self._work_cycle_range
        if not isinstance(values, list) or len(values) != 2:
            raise ActorSimulationError(f"Invalid interval range for event {event!r}")
        lower, upper = (int(values[0]), int(values[1]))
        if lower < 1 or upper < lower:
            raise ActorSimulationError(f"Invalid interval range for event {event!r}")
        return lower, upper

    def _profile_multiplier(self, employee: dict[str, Any]) -> int:
        value = self._profile(employee).get("event_timing_multiplier_percent")
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ActorSimulationError(
                f"{employee.get('employee_id')}: invalid event timing multiplier"
            )
        return value

    def _next_interval_ms(
        self,
        employee: dict[str, Any],
        *,
        counter: int,
        now_ms: int,
        event: str | None = None,
    ) -> int:
        lower, upper = self._interval_bounds(event)
        ticket = self._stable_int(
            employee["employee_id"],
            self._profile(employee).get("profile_seed"),
            "interval",
            event or "schedule",
            counter,
            now_ms,
        )
        seconds = lower + ticket % (upper - lower + 1)
        milliseconds = seconds * 1000 * self._profile_multiplier(employee) // 100
        return self._quantize_ms(milliseconds)

    def _activity_duration_ms(self, employee: dict[str, Any], event: str, *, counter: int) -> int:
        policy = self._recovery_events.get(event)
        if not isinstance(policy, dict):
            raise ActorSimulationError(f"Unknown recovery event: {event!r}")
        values = policy.get("activity_duration_seconds_range")
        if not isinstance(values, list) or len(values) != 2:
            raise ActorSimulationError(f"Invalid activity duration for event {event!r}")
        lower, upper = int(values[0]), int(values[1])
        if lower < 1 or upper < lower:
            raise ActorSimulationError(f"Invalid activity duration for event {event!r}")
        ticket = self._stable_int(
            employee["employee_id"],
            self._profile(employee).get("profile_seed"),
            "duration",
            event,
            counter,
        )
        seconds = lower + ticket % (upper - lower + 1)
        milliseconds = seconds * 1000 * self._profile_multiplier(employee) // 100
        return self._quantize_ms(milliseconds)

    def _recovery_amount_milli(self, employee: dict[str, Any], event: str, *, counter: int) -> int:
        policy = self._recovery_events.get(event)
        if not isinstance(policy, dict):
            raise ActorSimulationError(f"Unknown recovery event: {event!r}")
        values = policy.get("recovery_amount_range")
        if not isinstance(values, list) or len(values) != 2:
            raise ActorSimulationError(f"Invalid recovery amount for event {event!r}")
        lower, upper = int(values[0]), int(values[1])
        if lower < 0 or upper < lower:
            raise ActorSimulationError(f"Invalid recovery amount for event {event!r}")
        ticket = self._stable_int(
            employee["employee_id"],
            self._profile(employee).get("profile_seed"),
            "recovery",
            event,
            counter,
        )
        return (lower + ticket % (upper - lower + 1)) * self.MILLI_SCALE

    def _schedule_next_event(
        self,
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        now_ms: int,
    ) -> int:
        counter = int(actor["behavior"]["event_counter"])
        return now_ms + self._next_interval_ms(
            employee,
            counter=counter,
            now_ms=now_ms,
        )

    def choose_behavior_event(
        self,
        employee_id: str,
        *,
        simulation_time_ms: int = 0,
        event_counter: int = 0,
        cooldowns: dict[str, int] | None = None,
    ) -> str:
        """Choose one weighted recovery event reproducibly for an employee."""
        now_ms = self._require_int(simulation_time_ms, "simulation_time_ms")
        counter = self._require_int(event_counter, "event_counter")
        try:
            employee = self.employee_registry.get(employee_id)
        except EmployeeMetadataError as exc:
            raise ActorSimulationError(str(exc)) from exc
        self._assignment_payload(employee)
        cooldowns = cooldowns or {}
        eligible: list[tuple[str, int]] = []
        for event in self.WEIGHTED_EVENTS:
            weight = int(self._selection_weights.get(event, 0))
            cooldown_until = cooldowns.get(event, 0)
            if isinstance(cooldown_until, bool) or not isinstance(cooldown_until, int):
                raise ActorSimulationError(f"Invalid cooldown for event {event!r}")
            if weight > 0 and now_ms >= cooldown_until:
                eligible.append((event, weight))
        if not eligible:
            raise ActorSimulationError("No eligible weighted recovery event")
        total = sum(weight for _, weight in eligible)
        ticket = self._stable_int(
            employee_id,
            self._profile(employee).get("profile_seed"),
            counter,
            now_ms,
        ) % total
        for event, weight in eligible:
            if ticket < weight:
                return event
            ticket -= weight
        return eligible[-1][0]

    def _actor_from_employee(self, employee: dict[str, Any]) -> dict[str, Any]:
        assignment = self._assignment_payload(employee)
        profile = self._profile(employee)
        return {
            "employee_id": employee["employee_id"],
            "character_id": employee["character_id"],
            "assignment": assignment,
            "presence": "present",
            "activity": "working",
            "position": {
                "floor_id": assignment["floor_id"],
                "uv": None,
                "ground_xy": None,
                "route": None,
            },
            "stamina": {
                "current_milli": self.MAX_STAMINA_MILLI,
                "max_milli": self.MAX_STAMINA_MILLI,
                "threshold_band": "normal",
                "drain_remainder": 0,
            },
            "behavior": {
                "profile_seed": profile["profile_seed"],
                "event_counter": 0,
                "next_event_due_ms": None,
                "activity_started_ms": 0,
                "activity_until_ms": None,
                "active_event": None,
                "cooldowns": {},
                "work_loop_elapsed_ms": 0,
                "work_loop_count": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
                "talk": None,
            },
            "conversation_phase": None,
            "last_event": "initial",
        }

    def initial_snapshot(self, floor_id: str | None = None) -> dict[str, Any]:
        """Build a deterministic snapshot from the immutable initial roster."""
        try:
            rows = self.employee_registry.initial_roster(floor_id)
        except EmployeeMetadataError as exc:
            raise ActorSimulationError(str(exc)) from exc
        actors: dict[str, dict[str, Any]] = {}
        for row in sorted(rows, key=lambda item: str(item["employee_id"])):
            try:
                employee = self.employee_registry.get(row["employee_id"])
            except EmployeeMetadataError as exc:
                raise ActorSimulationError(str(exc)) from exc
            actors[row["employee_id"]] = self._actor_from_employee(employee)
        snapshot = {
            "schema": self.SNAPSHOT_SCHEMA,
            "version": self.VERSION,
            "clock": {
                "simulation_time_ms": 0,
                "tick_ms": self.TICK_MS,
            },
            "determinism": {
                "simulation_seed": "gds-actor-simulation-v1",
                "root_event_counter": 0,
            },
            "actors": actors,
        }
        # Initial snapshots schedule the first event without mutating stamina.
        for employee_id in sorted(actors):
            actor = actors[employee_id]
            employee = self.employee_registry.get(employee_id)
            actor["behavior"]["next_event_due_ms"] = self._schedule_next_event(
                actor,
                employee,
                now_ms=0,
            )
        return self.validate_snapshot(snapshot)

    def resolve_initial_snapshot(self, floor_id: str | None = None) -> dict[str, Any]:
        return self.initial_snapshot(floor_id)

    def _canonical_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        result = self._copy(snapshot)
        result["actors"] = {
            employee_id: result["actors"][employee_id]
            for employee_id in sorted(result["actors"])
        }
        for actor in result["actors"].values():
            behavior = actor["behavior"]
            # Snapshots created before the smooth critical-home contract did
            # not carry these presentation-boundary fields.  Normalize them
            # at the validation boundary so saved v1 snapshots remain loadable.
            behavior.setdefault("work_loop_elapsed_ms", 0)
            # Backward-compatible migration for snapshots created before the
            # persistent completed-loop counter existed.
            behavior.setdefault("work_loop_count", 0)
            behavior.setdefault("pending_home", False)
            behavior.setdefault("pending_home_due_ms", None)
            behavior.setdefault("talk", None)
            behavior["cooldowns"] = {
                key: behavior["cooldowns"][key]
                for key in sorted(behavior["cooldowns"])
            }
        return result

    def validate_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            raise ActorSimulationError("snapshot must be an object")
        try:
            json.dumps(snapshot, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ActorSimulationError("snapshot must be JSON-safe") from exc
        errors = sorted(
            self._snapshot_validator.iter_errors(snapshot),
            key=lambda error: list(error.path),
        )
        if errors:
            first = errors[0]
            path = first.json_path or "$"
            raise ActorSimulationError(f"{path}: {first.message}")

        current = self._canonical_snapshot(snapshot)
        simulation_time_ms = self._require_int(
            current["clock"]["simulation_time_ms"],
            "clock.simulation_time_ms",
        )
        self._require_int(
            current["determinism"]["root_event_counter"],
            "determinism.root_event_counter",
        )
        seen_characters: set[str] = set()
        seen_slots: set[str] = set()
        for employee_id, actor in current["actors"].items():
            if actor.get("employee_id") != employee_id:
                raise ActorSimulationError(f"snapshot actor key mismatch: {employee_id!r}")
            try:
                employee = self.employee_registry.get(employee_id)
            except EmployeeMetadataError as exc:
                raise ActorSimulationError(str(exc)) from exc
            if employee.get("character_id") != actor.get("character_id"):
                raise ActorSimulationError(
                    f"{employee_id}: character_id does not match employee metadata"
                )
            if employee.get("assignment") is None:
                raise ActorSimulationError(f"{employee_id}: unassigned employee cannot be active")
            assignment = actor["assignment"]
            expected_assignment = self._assignment_payload(employee)
            for field in self._assignment_fields():
                if assignment.get(field) != expected_assignment.get(field):
                    raise ActorSimulationError(
                        f"{employee_id}: assignment changed for {field}: "
                        f"{assignment.get(field)!r} != {expected_assignment.get(field)!r}"
                    )
            self._validate_slot(assignment)
            character_id = str(actor["character_id"])
            slot_id = str(assignment["slot_id"])
            if character_id in seen_characters:
                raise ActorSimulationError(f"duplicate character in snapshot: {character_id}")
            if slot_id in seen_slots:
                raise ActorSimulationError(f"duplicate assignment slot in snapshot: {slot_id}")
            seen_characters.add(character_id)
            seen_slots.add(slot_id)

            presence = actor["presence"]
            activity = actor["activity"]
            position = actor["position"]
            if position["floor_id"] is not None and position["floor_id"] != assignment["floor_id"]:
                raise ActorSimulationError(f"{employee_id}: position floor differs from assignment")
            if presence == "home":
                if any(position[field] is not None for field in ("floor_id", "uv", "ground_xy", "route")):
                    raise ActorSimulationError(f"{employee_id}: home actor cannot retain floor position")
            elif position["floor_id"] != assignment["floor_id"]:
                raise ActorSimulationError(f"{employee_id}: present actor needs its assignment floor")

            route = position.get("route")
            if route is not None:
                if not isinstance(route, dict):
                    raise ActorSimulationError(f"{employee_id}: route must be an object or null")
                phase = route.get("phase")
                if phase not in self.ROUTE_PHASES:
                    raise ActorSimulationError(f"{employee_id}: unknown route phase")
                for field in ("elapsed_ms", "duration_ms"):
                    self._require_int(route.get(field), f"{employee_id}.route.{field}")
                if int(route["duration_ms"]) < self.TICK_MS:
                    raise ActorSimulationError(f"{employee_id}: route duration is too short")
                if int(route["elapsed_ms"]) > int(route["duration_ms"]):
                    raise ActorSimulationError(f"{employee_id}: route elapsed exceeds duration")
                if not isinstance(route.get("path_cells_uv"), list) or not route["path_cells_uv"]:
                    raise ActorSimulationError(f"{employee_id}: route path is empty")
                route_start = self._normalize_uv(route.get("start_uv"), name="route.start_uv")
                route_target = self._normalize_uv(route.get("target_uv"), name="route.target_uv")
                path = [
                    self._normalize_uv(cell, name="route.path_cells_uv")
                    for cell in route["path_cells_uv"]
                ]
                if path[0] != route_start or path[-1] != route_target:
                    raise ActorSimulationError(f"{employee_id}: route endpoints do not match path")
                if phase in {"to_portal", "portal_exit"} and activity != "going_home":
                    raise ActorSimulationError(f"{employee_id}: outbound route has wrong activity")
                if phase in {"portal_entry", "to_workseat"} and activity != "returning_to_work":
                    raise ActorSimulationError(f"{employee_id}: inbound route has wrong activity")
                if phase in self.WANDER_ROUTE_PHASES and activity != "wandering":
                    raise ActorSimulationError(f"{employee_id}: wander route has wrong activity")
                if phase in self.TALK_ROUTE_PHASES and activity != "talking":
                    raise ActorSimulationError(f"{employee_id}: talk route has wrong activity")
            elif activity in self.ROUTE_ACTIVITIES:
                raise ActorSimulationError(f"{employee_id}: routed activity needs a route")
            if presence == "home" and activity != "home_recovery":
                raise ActorSimulationError(f"{employee_id}: home actor has invalid activity")
            if presence == "leaving" and activity != "going_home":
                raise ActorSimulationError(f"{employee_id}: leaving actor has invalid activity")
            if presence == "entering" and activity not in {"walking_to_work", "returning_to_work"}:
                raise ActorSimulationError(f"{employee_id}: entering actor has invalid activity")

            behavior = actor["behavior"]
            profile = self._profile(employee)
            if behavior["profile_seed"] != profile.get("profile_seed"):
                raise ActorSimulationError(f"{employee_id}: behavior profile seed changed")
            self._require_int(behavior["event_counter"], f"{employee_id}.event_counter")
            self._require_int(
                behavior["activity_started_ms"],
                f"{employee_id}.activity_started_ms",
            )
            work_loop_elapsed_ms = self._require_int(
                behavior.get("work_loop_elapsed_ms", 0),
                f"{employee_id}.work_loop_elapsed_ms",
            )
            if work_loop_elapsed_ms >= self.WORK_LOOP_MS:
                raise ActorSimulationError(
                    f"{employee_id}: work_loop_elapsed_ms exceeds normal-work loop"
                )
            self._require_int(
                behavior.get("work_loop_count", 0),
                f"{employee_id}.work_loop_count",
            )
            pending_home = behavior.get("pending_home", False)
            if not isinstance(pending_home, bool):
                raise ActorSimulationError(f"{employee_id}: pending_home must be boolean")
            pending_home_due_ms = behavior.get("pending_home_due_ms")
            if pending_home_due_ms is not None:
                self._require_int(
                    pending_home_due_ms,
                    f"{employee_id}.pending_home_due_ms",
                )
            if pending_home:
                if activity != "working":
                    raise ActorSimulationError(
                        f"{employee_id}: pending home is only valid while working"
                    )
                if pending_home_due_ms is None:
                    raise ActorSimulationError(
                        f"{employee_id}: pending home lacks a boundary timestamp"
                    )
                if int(pending_home_due_ms) < simulation_time_ms:
                    raise ActorSimulationError(
                        f"{employee_id}: pending home boundary is stale"
                    )
            elif pending_home_due_ms is not None:
                raise ActorSimulationError(
                    f"{employee_id}: home boundary exists without pending home"
                )
            if behavior["activity_until_ms"] is not None:
                if behavior["activity_until_ms"] < behavior["activity_started_ms"]:
                    raise ActorSimulationError(f"{employee_id}: activity window is reversed")
                if behavior["activity_until_ms"] < simulation_time_ms and activity != "home_recovery":
                    raise ActorSimulationError(f"{employee_id}: activity window is stale")
            talk = behavior.get("talk")
            if talk is not None:
                if not isinstance(talk, dict):
                    raise ActorSimulationError(f"{employee_id}: talk metadata must be an object or null")
                talk_start = self._require_int(talk.get("talk_start_at_ms"), f"{employee_id}.talk.talk_start_at_ms")
                talk_end = self._require_int(talk.get("talk_end_at_ms"), f"{employee_id}.talk.talk_end_at_ms")
                return_start = self._require_int(talk.get("return_start_at_ms"), f"{employee_id}.talk.return_start_at_ms")
                effective_at = self._require_int(talk.get("effective_at_ms"), f"{employee_id}.talk.effective_at_ms")
                if not effective_at <= talk_start <= talk_end <= return_start:
                    raise ActorSimulationError(f"{employee_id}: talk metadata timing is not monotonic")
                if talk.get("emotion") not in {None, "sad", "happy"}:
                    raise ActorSimulationError(f"{employee_id}: talk emotion is invalid")
                emotion_until = talk.get("emotion_until_at_ms")
                if emotion_until is not None:
                    self._require_int(emotion_until, f"{employee_id}.talk.emotion_until_at_ms")
                    if int(emotion_until) < talk_end or int(emotion_until) > return_start:
                        raise ActorSimulationError(f"{employee_id}: talk emotion hold timing is invalid")
                for path_name in ("outbound_path_cells_uv", "inbound_path_cells_uv"):
                    if not isinstance(talk.get(path_name), list):
                        raise ActorSimulationError(f"{employee_id}.talk.{path_name} must be a list")
                if talk.get("outbound_path_cells_uv"):
                    endpoint = self._normalize_uv(talk.get("endpoint_uv"), name=f"{employee_id}.talk.endpoint_uv")
                    gate = self._normalize_uv(talk.get("gate_uv"), name=f"{employee_id}.talk.gate_uv")
                    outbound = self._talk_path(talk.get("outbound_path_cells_uv"), name=f"{employee_id}.talk.outbound_path_cells_uv")
                    inbound = self._talk_path(talk.get("inbound_path_cells_uv"), name=f"{employee_id}.talk.inbound_path_cells_uv")
                    if outbound[0] != gate or outbound[-1] != endpoint:
                        raise ActorSimulationError(f"{employee_id}: talk outbound path endpoints are invalid")
                    if inbound[0] != endpoint or inbound[-1] != gate:
                        raise ActorSimulationError(f"{employee_id}: talk inbound path endpoints are invalid")
            if activity == "talking":
                pending = actor["conversation_phase"] == "talk_pending" and talk is None
                participant = behavior["active_event"] is None and talk is not None
                if pending:
                    if behavior["active_event"] != "talk":
                        raise ActorSimulationError(f"{employee_id}: pending talk needs an active talk request")
                elif talk is None:
                    raise ActorSimulationError(f"{employee_id}: talking actor lacks talk metadata")
                elif behavior["active_event"] not in {None, "talk"}:
                    raise ActorSimulationError(f"{employee_id}: talking actor has a non-talk active event")
                if not pending and not participant and behavior["active_event"] != "talk":
                    raise ActorSimulationError(f"{employee_id}: talk session has no recovery owner or participant")
            elif talk is not None:
                raise ActorSimulationError(f"{employee_id}: non-talking actor retains talk metadata")
            if activity in self.EVENT_ACTIVITY.values() and activity != "talking":
                if behavior["active_event"] is None or behavior["activity_until_ms"] is None:
                    raise ActorSimulationError(f"{employee_id}: active recovery event lacks a window")
            elif activity in self.ROUTE_ACTIVITIES or activity == "home_recovery":
                if behavior["active_event"] is not None:
                    raise ActorSimulationError(f"{employee_id}: administrative activity has an active recovery event")
                if behavior["activity_until_ms"] is None:
                    raise ActorSimulationError(f"{employee_id}: administrative activity lacks a window")
            elif activity != "talking" and (behavior["active_event"] is not None or behavior["activity_until_ms"] is not None):
                raise ActorSimulationError(f"{employee_id}: inactive actor has an active recovery window")
            if activity == "talking" and actor["conversation_phase"] is None:
                raise ActorSimulationError(f"{employee_id}: talking actor needs a conversation phase")
            if activity != "talking" and actor["conversation_phase"] is not None:
                raise ActorSimulationError(f"{employee_id}: non-talking actor has a conversation phase")

            stamina = actor["stamina"]
            current_milli = stamina["current_milli"]
            if stamina["threshold_band"] != self._threshold_band(current_milli):
                raise ActorSimulationError(f"{employee_id}: threshold band is not derived from stamina")
            if stamina["max_milli"] != self.MAX_STAMINA_MILLI:
                raise ActorSimulationError(f"{employee_id}: stamina max changed")

        return current

    def _append_event(
        self,
        snapshot: dict[str, Any],
        events: list[dict[str, Any]],
        *,
        timestamp_ms: int,
        employee_id: str,
        event_type: str,
        **payload: Any,
    ) -> None:
        event_index = int(snapshot["determinism"]["root_event_counter"])
        snapshot["determinism"]["root_event_counter"] = event_index + 1
        event = {
            "event_index": event_index,
            "timestamp_ms": int(timestamp_ms),
            "employee_id": employee_id,
            "type": event_type,
            **self._copy(payload),
        }
        events.append(event)

    def _drain_work(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        start_ms: int,
        elapsed_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        if elapsed_ms <= 0 or actor["activity"] != "working":
            return
        profile = self._profile(employee)
        rate = int(profile["work_drain_milli_per_second"])
        stamina = actor["stamina"]
        before = int(stamina["current_milli"])
        remainder_before = int(stamina["drain_remainder"])
        loop_before = self._work_loop_elapsed(actor)
        previous_band = stamina["threshold_band"]
        full_numerator = rate * int(elapsed_ms) + remainder_before
        full_drain, _full_remainder = divmod(full_numerator, 1000)
        full_after = max(0, before - full_drain)
        full_band = self._threshold_band(full_after)
        critical_crossing_elapsed: int | None = None
        crossed_bands: list[str] = []
        if self._threshold_rank(full_band) < self._threshold_rank(previous_band):
            if self._threshold_rank(previous_band) > self._threshold_rank("low") >= self._threshold_rank(full_band):
                crossed_bands.append("low")
            if self._threshold_rank(previous_band) > self._threshold_rank("critical") >= self._threshold_rank(full_band):
                crossed_bands.append("critical")
            # Keep threshold crossings observable even when one large reducer
            # window skips over more than one band.  The timestamp is the
            # first millisecond at which the exact integer drain reaches the
            # corresponding threshold, using the carried remainder.
            for band in crossed_bands:
                threshold_milli = {
                    "low": self.LOW_THRESHOLD_MILLI,
                    "critical": self.CRITICAL_THRESHOLD_MILLI,
                }[band]
                required_drain = max(0, before - threshold_milli)
                numerator_needed = max(
                    0,
                    required_drain * self.MILLI_SCALE - remainder_before,
                )
                crossing_elapsed = min(
                    int(elapsed_ms),
                    (numerator_needed + rate - 1) // rate if rate else int(elapsed_ms),
                )
                self._append_event(
                    snapshot,
                    events,
                    timestamp_ms=start_ms + crossing_elapsed,
                    employee_id=actor["employee_id"],
                    event_type="threshold_crossed",
                    threshold_band=band,
                    stamina_milli=threshold_milli,
                )
                if band == "critical":
                    critical_crossing_elapsed = crossing_elapsed
        # Once critical is reached, stop gameplay drain at that exact
        # crossing.  The remainder of a large host window advances only the
        # normal-work presentation phase until the queued loop boundary; it
        # must not keep consuming stamina while the actor is waiting to leave.
        effective_elapsed = (
            min(int(elapsed_ms), int(critical_crossing_elapsed))
            if critical_crossing_elapsed is not None
            else int(elapsed_ms)
        )
        numerator = rate * effective_elapsed + remainder_before
        drain, remainder = divmod(numerator, 1000)
        stamina["current_milli"] = max(0, before - drain)
        stamina["drain_remainder"] = remainder
        self._advance_work_loop(actor, effective_elapsed)
        current_band = self._threshold_band(stamina["current_milli"])
        stamina["threshold_band"] = current_band
        actor["last_event"] = "work_tick"
        if crossed_bands:
            actor["last_event"] = f"{crossed_bands[-1]}_threshold"
            if current_band == "critical":
                actor["behavior"]["next_event_due_ms"] = None
        if current_band == "critical":
            # Critical is a visual/state boundary, not an abrupt animation
            # stop.  Queue the home route at the first normal-work boundary
            # after the crossing (or after the current time if already
            # critical), while the actor keeps rendering normal_work.
            crossing = critical_crossing_elapsed if critical_crossing_elapsed is not None else 0
            phase_at_crossing = (loop_before + crossing) % self.WORK_LOOP_MS
            boundary_offset = self.WORK_LOOP_MS - phase_at_crossing
            if boundary_offset == self.WORK_LOOP_MS:
                boundary_offset = 0
            boundary_ms = int(start_ms) + crossing + boundary_offset
            due = self._queue_critical_home(
                actor,
                timestamp_ms=int(start_ms) + crossing,
                boundary_ms=boundary_ms,
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=int(start_ms) + crossing,
                employee_id=actor["employee_id"],
                event_type="home_queued",
                reason="stamina_critical",
                stamina_milli=int(stamina["current_milli"]),
                finish_work_loop_at_ms=due,
                work_loop_ms=self.WORK_LOOP_MS,
            )

    def _path_pose(
        self,
        path: list[tuple[int, int]],
        elapsed_ms: int,
        employee: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve a continuous walking pose on the existing movement timeline."""
        start = path[0]
        if len(path) < 2:
            return {
                "ground_xy": self._round_xy(self.movement.uv_cell_center_to_pixel(*start)),
                "current_uv": list(start),
                "from_uv": list(start),
                "to_uv": list(start),
                "progress_t": 1.0,
                "direction": "SE",
                "raw_direction": "SE",
                "cumulative_distance_px": 0.0,
            }
        profile = self._movement_profile(employee)
        speed_multiplier = float(profile["speed_multiplier"])
        cells_per_second = self.movement.base_move_speed_cells_per_second() * speed_multiplier
        total_cells = float(len(path) - 1)
        distance_cells = min(total_cells, max(0.0, int(elapsed_ms)) / 1000.0 * cells_per_second)
        nearest_cell = int(round(distance_cells))
        if distance_cells > 0 and math.isclose(distance_cells, nearest_cell, abs_tol=1e-9):
            step_index = min(nearest_cell - 1, len(path) - 2)
            progress = 1.0
        else:
            step_index = min(int(math.floor(distance_cells)), len(path) - 2)
            progress = distance_cells - step_index
        current = path[step_index]
        target = path[step_index + 1]
        sx, sy = self.movement.uv_cell_center_to_pixel(*current)
        ex, ey = self.movement.uv_cell_center_to_pixel(*target)
        visual_directions = self.movement.visual_directions_for_path(path)
        direction = visual_directions[step_index]
        raw_direction = self.movement.direction_for_step(current, target)
        current_uv = list(target) if math.isclose(progress, 1.0, abs_tol=1e-9) else None
        return {
            "ground_xy": self._round_xy((sx + (ex - sx) * progress, sy + (ey - sy) * progress)),
            "current_uv": current_uv,
            "from_uv": list(current),
            "to_uv": list(target),
            "progress_t": round(float(progress), 4),
            "direction": direction,
            "raw_direction": raw_direction,
            "cumulative_distance_px": round(
                distance_cells * float(self.movement.fine_step_distance_px()), 4
            ),
        }

    def _portal_pose(
        self,
        route: dict[str, Any],
        elapsed_ms: int,
    ) -> dict[str, Any]:
        start = self._normalize_uv(route["start_uv"], name="route.start_uv")
        target = self._normalize_uv(route["target_uv"], name="route.target_uv")
        duration = max(self.TICK_MS, int(route["duration_ms"]))
        progress = min(1.0, max(0.0, int(elapsed_ms) / duration))
        sx, sy = self.movement.uv_cell_center_to_pixel(*start)
        ex, ey = self.movement.uv_cell_center_to_pixel(*target)
        direction = self.movement.direction_for_step(start, target)
        phase = route["phase"]
        alpha = progress if phase == "portal_entry" else 1.0 - progress
        return {
            "ground_xy": self._round_xy((sx + (ex - sx) * progress, sy + (ey - sy) * progress)),
            "current_uv": list(target) if math.isclose(progress, 1.0, abs_tol=1e-9) else None,
            "from_uv": list(start),
            "to_uv": list(target),
            "progress_t": round(progress, 4),
            "direction": direction,
            "raw_direction": direction,
            "cumulative_distance_px": round(
                math.dist((sx, sy), (ex, ey)) * progress, 4
            ),
            "visibility_alpha": round(max(0.0, min(1.0, alpha)), 4),
        }

    def _emit_route_sample(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        route: dict[str, Any],
        pose: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        actor["position"]["floor_id"] = actor["assignment"]["floor_id"]
        actor["position"]["ground_xy"] = list(pose["ground_xy"])
        actor["position"]["uv"] = pose.get("current_uv")
        route["direction"] = pose.get("direction")
        route["raw_direction"] = pose.get("raw_direction")
        route["visibility_alpha"] = float(pose.get("visibility_alpha", 1.0))
        self._append_event(
            snapshot,
            events,
            timestamp_ms=timestamp_ms,
            employee_id=actor["employee_id"],
            event_type="actor_route_sample",
            phase=route["phase"],
            ground_xy=list(pose["ground_xy"]),
            current_uv=pose.get("current_uv"),
            from_uv=pose.get("from_uv"),
            to_uv=pose.get("to_uv"),
            progress_t=pose.get("progress_t"),
            direction=pose.get("direction"),
            raw_direction=pose.get("raw_direction"),
            visibility_alpha=float(pose.get("visibility_alpha", 1.0)),
            route_elapsed_ms=int(route["elapsed_ms"]),
            route_duration_ms=int(route["duration_ms"]),
            render_owner="walking_depth",
            action=str(route.get("action") or "move"),
            subaction=str(route.get("subaction") or "idle"),
        )

    def _start_route(
        self,
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        phase: str,
        start_uv: tuple[int, int],
        target_uv: tuple[int, int],
        path: list[tuple[int, int]],
        duration_ms: int | None = None,
        update_window: bool = True,
        action: str = "move",
        subaction: str = "idle",
    ) -> None:
        duration = duration_ms if duration_ms is not None else self._route_duration_ms(path, employee)
        direction = None
        if start_uv != target_uv:
            try:
                direction = self.movement.direction_for_step(start_uv, target_uv)
            except (CharacterMovementError, ValueError):
                direction = None
        actor["position"]["route"] = self._route_record(
            phase=phase,
            start_uv=start_uv,
            target_uv=target_uv,
            path=path,
            duration_ms=duration,
            action=action,
            subaction=subaction,
            direction=direction,
        )
        actor["position"]["floor_id"] = actor["assignment"]["floor_id"]
        actor["position"]["uv"] = list(start_uv)
        actor["position"]["ground_xy"] = list(self.movement.uv_cell_center_to_pixel(*start_uv))
        if update_window:
            actor["behavior"]["activity_until_ms"] = (
                int(actor["behavior"]["activity_started_ms"]) + int(duration)
            )

    @staticmethod
    def _talk_path(value: Any, *, name: str) -> list[tuple[int, int]]:
        if not isinstance(value, list) or not value:
            raise ActorSimulationError(f"{name} must be a non-empty path")
        path: list[tuple[int, int]] = []
        for index, cell in enumerate(value):
            if not isinstance(cell, (list, tuple)) or len(cell) != 2:
                raise ActorSimulationError(f"{name}[{index}] must be a two-item coordinate")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in cell):
                raise ActorSimulationError(f"{name}[{index}] must contain integer coordinates")
            path.append((int(cell[0]), int(cell[1])))
        return path

    def _talk_pose(
        self,
        route: dict[str, Any],
        elapsed_ms: int,
        employee: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve a talk route pose, including the stationary talk hold."""
        if route.get("phase") == "talk_hold":
            endpoint = self._normalize_uv(route["target_uv"], name="talk endpoint_uv")
            ground_xy = self.movement.uv_cell_center_to_pixel(*endpoint)
            direction = str(route.get("direction") or employee.get("assignment", {}).get("facing") or "SE").upper()
            return {
                "ground_xy": self._round_xy(ground_xy),
                "current_uv": list(endpoint),
                "from_uv": list(endpoint),
                "to_uv": list(endpoint),
                "progress_t": 1.0,
                "direction": direction,
                "raw_direction": direction,
                "cumulative_distance_px": 0.0,
            }
        return self._path_pose(
            [self._normalize_uv(cell, name="talk route.path_cells_uv") for cell in route["path_cells_uv"]],
            int(elapsed_ms),
            employee,
        )

    def _begin_talk_return_route(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        talk = actor["behavior"].get("talk")
        if not isinstance(talk, dict):
            raise ActorSimulationError(f"{actor['employee_id']}: talk return metadata is missing")
        inbound = self._talk_path(talk.get("inbound_path_cells_uv"), name="talk.inbound_path_cells_uv")
        endpoint = self._normalize_uv(talk.get("endpoint_uv"), name="talk.endpoint_uv")
        gate_value = talk.get("gate_uv")
        gate = (
            self._normalize_uv(gate_value, name="talk.gate_uv")
            if gate_value is not None
            else None
        )
        if inbound[0] != endpoint or inbound[-1] != gate:
            raise ActorSimulationError(f"{actor['employee_id']}: talk return path endpoints are invalid")
        duration = int(talk.get("return_duration_ms", 0))
        if duration <= 0:
            duration = self._route_duration_ms(inbound, employee)
        actor["conversation_phase"] = "returning_to_work"
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = int(timestamp_ms) + int(duration)
        self._start_route(
            actor,
            employee,
            phase="talk_return",
            start_uv=endpoint,
            target_uv=gate,
            path=inbound,
            duration_ms=duration,
            update_window=False,
        )
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            employee_id=actor["employee_id"],
            event_type="talk_return_started",
            session_id=talk.get("session_id"),
            mode=talk.get("mode"),
            partner_id=talk.get("partner_id"),
            return_duration_ms=int(duration),
        )

    def _finish_talk_actor(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        talk = actor["behavior"].get("talk")
        if not isinstance(talk, dict):
            raise ActorSimulationError(f"{actor['employee_id']}: talk completion metadata is missing")
        floor_id = actor["assignment"]["floor_id"]
        gate_value = talk.get("gate_uv")
        gate = (
            self._normalize_uv(gate_value, name="talk.gate_uv")
            if gate_value is not None
            else None
        )
        actor["position"] = {
            "floor_id": floor_id,
            "uv": None,
            "ground_xy": None,
            "route": None,
        }
        actor["presence"] = "present"
        actor["conversation_phase"] = None
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            employee_id=actor["employee_id"],
            event_type="talk_returned",
            session_id=talk.get("session_id"),
            mode=talk.get("mode"),
            partner_id=talk.get("partner_id"),
            gate_uv=list(gate) if gate is not None else None,
            assignment_retained=True,
        )
        recovery_owner = bool(talk.get("recovery_owner", False))
        actor["behavior"]["talk"] = None
        if recovery_owner and actor["behavior"].get("active_event") == "talk":
            self._complete_event(
                snapshot,
                actor,
                employee,
                timestamp_ms=int(timestamp_ms),
                events=events,
            )
            return
        actor["activity"] = "working"
        actor["behavior"]["active_event"] = None
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = None
        actor["behavior"]["work_loop_elapsed_ms"] = 0
        actor["behavior"]["work_loop_count"] = 0
        actor["behavior"]["next_event_due_ms"] = self._schedule_next_event(
            actor,
            employee,
            now_ms=int(timestamp_ms),
        )

    def _start_talk_session(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        command: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        session_id = command.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ActorSimulationError("start_talk_session.session_id is required")
        mode = str(command.get("mode") or "standing_pair")
        if mode not in {"self_talk", "ceo_front", "seated_host", "standing_pair"}:
            raise ActorSimulationError(f"Unknown talk mode: {mode!r}")
        role = str(command.get("role") or "initiator")
        if role not in {"initiator", "participant", "visitor"}:
            raise ActorSimulationError(f"Unknown talk role: {role!r}")
        if actor["presence"] != "present":
            raise ActorSimulationError(f"{actor['employee_id']}: talk session requires a present actor")
        if actor["activity"] == "talking" and actor["conversation_phase"] not in {"talk_pending", "self_talk"}:
            raise ActorSimulationError(f"{actor['employee_id']}: actor is already in a talk session")
        if actor["activity"] == "working" and actor["behavior"].get("active_event") is not None:
            raise ActorSimulationError(f"{actor['employee_id']}: working actor has another active event")
        if actor["activity"] == "working" and (
            actor["behavior"].get("pending_home")
            or actor["stamina"].get("threshold_band") == "critical"
        ):
            raise ActorSimulationError(
                f"{actor['employee_id']}: critical actor cannot enter a talk session"
            )
        effective_at = self._require_int(
            command.get("effective_at_ms", timestamp_ms),
            "start_talk_session.effective_at_ms",
        )
        if effective_at > int(timestamp_ms):
            raise ActorSimulationError(f"{actor['employee_id']}: talk session starts in the future")
        talk_start = self._require_int(
            command.get("talk_start_at_ms", timestamp_ms),
            "start_talk_session.talk_start_at_ms",
        )
        talk_end = self._require_int(
            command.get("talk_end_at_ms", talk_start),
            "start_talk_session.talk_end_at_ms",
        )
        return_start = self._require_int(
            command.get("return_start_at_ms", talk_end),
            "start_talk_session.return_start_at_ms",
        )
        if not effective_at <= talk_start <= talk_end <= return_start:
            raise ActorSimulationError(f"{actor['employee_id']}: talk session timing is not monotonic")
        partner_id = command.get("partner_id")
        if partner_id is not None and not isinstance(partner_id, str):
            raise ActorSimulationError("start_talk_session.partner_id must be text or null")
        emotion = command.get("emotion")
        if emotion not in {None, "sad", "happy"}:
            raise ActorSimulationError("start_talk_session.emotion is invalid")
        emotion_until = command.get("emotion_until_at_ms")
        if emotion_until is not None:
            emotion_until = self._require_int(
                emotion_until,
                "start_talk_session.emotion_until_at_ms",
            )
            if emotion_until < talk_end or emotion_until > return_start:
                raise ActorSimulationError(f"{actor['employee_id']}: emotion hold timing is invalid")
        route_info = command.get("route_info")
        outbound: list[tuple[int, int]] | None = None
        inbound: list[tuple[int, int]] | None = None
        endpoint: tuple[int, int] | None = None
        gate: tuple[int, int] | None = None
        outbound_duration = 0
        return_duration = 0
        if route_info is not None:
            if not isinstance(route_info, dict):
                raise ActorSimulationError("start_talk_session.route_info must be an object")
            outbound = self._talk_path(
                route_info.get("outbound_path_cells_uv"),
                name="route_info.outbound_path_cells_uv",
            )
            inbound = self._talk_path(
                route_info.get("inbound_path_cells_uv"),
                name="route_info.inbound_path_cells_uv",
            )
            gate = self._normalize_uv(route_info.get("gate_uv"), name="route_info.gate_uv")
            endpoint = self._normalize_uv(command.get("endpoint_uv"), name="start_talk_session.endpoint_uv")
            if outbound[0] != gate or outbound[-1] != endpoint:
                raise ActorSimulationError(f"{actor['employee_id']}: talk outbound path endpoints are invalid")
            if inbound[0] != endpoint or inbound[-1] != gate:
                raise ActorSimulationError(f"{actor['employee_id']}: talk inbound path endpoints are invalid")
            outbound_duration = int(route_info.get("arrival_ms", 0))
            if outbound_duration <= 0:
                outbound_duration = self._route_duration_ms(outbound, employee)
            return_duration = int(route_info.get("return_ms", 0)) - int(route_info.get("return_start_ms", 0))
            if return_duration <= 0:
                return_duration = self._route_duration_ms(inbound, employee)
            if talk_start < effective_at + outbound_duration:
                raise ActorSimulationError(f"{actor['employee_id']}: talk starts before route arrival")
        is_initiator = bool(command.get("recovery_owner", role == "initiator"))
        if actor["activity"] == "working" and is_initiator:
            actor["behavior"]["event_counter"] = int(actor["behavior"].get("event_counter", 0)) + 1
            actor["behavior"]["active_event"] = "talk"
            actor["behavior"]["cooldowns"]["talk"] = int(timestamp_ms) + self._next_interval_ms(
                employee,
                counter=int(actor["behavior"]["event_counter"]),
                now_ms=int(timestamp_ms),
                event="talk",
            )
        actor["presence"] = "present"
        actor["activity"] = "talking"
        actor["behavior"]["next_event_due_ms"] = None
        actor["behavior"]["activity_started_ms"] = int(effective_at)
        actor["behavior"]["activity_until_ms"] = int(return_start) + int(return_duration)
        actor["behavior"]["talk"] = {
            "session_id": session_id,
            "mode": mode,
            "role": role,
            "partner_id": partner_id,
            "recovery_owner": is_initiator,
            "effective_at_ms": int(effective_at),
            "talk_start_at_ms": int(talk_start),
            "talk_end_at_ms": int(talk_end),
            "return_start_at_ms": int(return_start),
            "emotion": emotion,
            "emotion_until_at_ms": emotion_until,
            "endpoint_uv": list(endpoint) if endpoint is not None else None,
            "gate_uv": list(gate) if gate is not None else None,
            "outbound_path_cells_uv": [list(cell) for cell in outbound] if outbound is not None else [],
            "inbound_path_cells_uv": [list(cell) for cell in inbound] if inbound is not None else [],
            "outbound_duration_ms": int(outbound_duration),
            "return_duration_ms": int(return_duration),
        }
        if outbound is None:
            actor["conversation_phase"] = (
                "self_talk"
                if mode == "self_talk"
                else ("talking" if int(timestamp_ms) >= int(talk_start) else "talk_arrival")
            )
            actor["position"]["route"] = None
            actor["position"]["uv"] = None
            actor["position"]["ground_xy"] = None
        else:
            actor["conversation_phase"] = "walking_to_talk"
            self._start_route(
                actor,
                employee,
                phase="talk_outbound",
                start_uv=gate,
                target_uv=endpoint,
                path=outbound,
                duration_ms=outbound_duration,
                update_window=False,
            )
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(effective_at),
            employee_id=actor["employee_id"],
            event_type="talk_session_accepted",
            session_id=session_id,
            mode=mode,
            role=role,
            partner_id=partner_id,
            route_committed=outbound is not None,
            talk_start_at_ms=int(talk_start),
            talk_end_at_ms=int(talk_end),
            return_start_at_ms=int(return_start),
        )
        # The actor clock may be one host slice beyond the acceptance boundary
        # because Central accepts the speech plan after advancing that slice.
        # Materialize that small elapsed portion immediately so the next frame
        # does not visibly snap back to the gate.
        elapsed_since_accept = max(0, int(timestamp_ms) - int(effective_at))
        if outbound is not None and elapsed_since_accept:
            route = actor["position"].get("route")
            if isinstance(route, dict):
                route["elapsed_ms"] = min(int(route["duration_ms"]), elapsed_since_accept)
                pose = self._talk_pose(route, int(route["elapsed_ms"]), employee)
                self._emit_route_sample(
                    snapshot,
                    actor,
                    route,
                    pose,
                    timestamp_ms=int(timestamp_ms),
                    events=events,
                )
                if int(route["elapsed_ms"]) >= int(route["duration_ms"]):
                    self._finish_route_segment(
                        snapshot,
                        actor,
                        employee,
                        timestamp_ms=int(timestamp_ms),
                        events=events,
                    )

    def _cancel_talk(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
        reason: str,
    ) -> None:
        if actor["activity"] != "talking" or actor["conversation_phase"] != "talk_pending":
            raise ActorSimulationError(f"{actor['employee_id']}: only pending talk can be cancelled")
        actor["position"]["route"] = None
        actor["position"]["uv"] = None
        actor["position"]["ground_xy"] = None
        actor["activity"] = "working"
        actor["conversation_phase"] = None
        actor["behavior"]["active_event"] = None
        actor["behavior"]["talk"] = None
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = None
        actor["behavior"]["next_event_due_ms"] = self._schedule_next_event(
            actor,
            employee,
            now_ms=int(timestamp_ms),
        )
        actor["last_event"] = "conversation_cancelled"
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            employee_id=actor["employee_id"],
            event_type="talk_cancelled",
            reason=str(reason),
        )

    def _finish_route_segment(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        route = actor["position"].get("route")
        if not isinstance(route, dict):
            raise ActorSimulationError(f"{actor['employee_id']}: route segment is missing")
        phase = route.get("phase")
        floor_id = actor["assignment"]["floor_id"]
        if phase == "talk_outbound":
            talk = actor["behavior"].get("talk")
            if not isinstance(talk, dict):
                raise ActorSimulationError(f"{actor['employee_id']}: talk outbound metadata is missing")
            endpoint = self._normalize_uv(talk.get("endpoint_uv"), name="talk.endpoint_uv")
            actor["position"]["floor_id"] = floor_id
            actor["position"]["uv"] = list(endpoint)
            actor["position"]["ground_xy"] = list(
                self.movement.uv_cell_center_to_pixel(*endpoint)
            )
            actor["position"]["route"] = self._route_record(
                phase="talk_hold",
                start_uv=endpoint,
                target_uv=endpoint,
                path=[endpoint],
                duration_ms=max(
                    self.TICK_MS,
                    int(talk.get("return_start_at_ms", timestamp_ms)) - int(timestamp_ms),
                ),
                action="idle",
                subaction="idle",
                direction=str(route.get("direction") or actor["assignment"].get("facing") or "SE"),
            )
            actor["conversation_phase"] = "talk_arrival"
            actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
            actor["behavior"]["activity_until_ms"] = int(
                talk.get("return_start_at_ms", timestamp_ms)
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=int(timestamp_ms),
                employee_id=actor["employee_id"],
                event_type="talk_arrived",
                session_id=talk.get("session_id"),
                mode=talk.get("mode"),
                partner_id=talk.get("partner_id"),
                endpoint_uv=list(endpoint),
            )
            if int(talk.get("return_start_at_ms", timestamp_ms)) <= int(timestamp_ms):
                self._begin_talk_return_route(
                    snapshot,
                    actor,
                    employee,
                    timestamp_ms=int(timestamp_ms),
                    events=events,
                )
            return
        if phase == "talk_hold":
            self._begin_talk_return_route(
                snapshot,
                actor,
                employee,
                timestamp_ms=int(timestamp_ms),
                events=events,
            )
            return
        if phase == "talk_return":
            self._finish_talk_actor(
                snapshot,
                actor,
                employee,
                timestamp_ms=int(timestamp_ms),
                events=events,
            )
            return
        if phase == "to_portal":
            inside, outside = self._portal_pair(floor_id)
            actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
            self._start_route(
                actor,
                employee,
                phase="portal_exit",
                start_uv=inside,
                target_uv=outside,
                path=[inside, outside],
                duration_ms=self.PORTAL_FADE_STEPS * self.TICK_MS,
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="portal_exit_started",
                inside_uv=list(inside),
                outside_uv=list(outside),
                fade_ms=self.PORTAL_FADE_STEPS * self.TICK_MS,
            )
            return
        if phase == "portal_exit":
            actor["position"] = {
                "floor_id": None,
                "uv": None,
                "ground_xy": None,
                "route": None,
            }
            actor["presence"] = "home"
            actor["activity"] = "home_recovery"
            actor["conversation_phase"] = None
            actor["stamina"].update({
                "current_milli": self.MAX_STAMINA_MILLI,
                "threshold_band": "normal",
                "drain_remainder": 0,
            })
            actor["behavior"].update({
                "next_event_due_ms": None,
                "active_event": None,
                "activity_started_ms": int(timestamp_ms),
                "activity_until_ms": int(timestamp_ms) + self._home_recovery_delay_ms(employee, actor),
                "work_loop_elapsed_ms": 0,
                "work_loop_count": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
            })
            actor["last_event"] = "home_recovered"
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="portal_exited",
                assignment_retained=True,
                render_owner="walking_depth",
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="home_recovery_started",
                ready_at_ms=actor["behavior"]["activity_until_ms"],
                stamina_restored_milli=self.MAX_STAMINA_MILLI,
                assignment_retained=True,
            )
            return
        if phase == "portal_entry":
            inside, _outside = self._portal_pair(floor_id)
            gate = self._workseat_gate(actor["assignment"])
            path = self._route_path(floor_id, inside, gate)
            actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
            self._start_route(
                actor,
                employee,
                phase="to_workseat",
                start_uv=inside,
                target_uv=gate,
                path=path,
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="portal_entered",
                inside_uv=list(inside),
                assignment_retained=True,
            )
            return
        if phase == "wander_out":
            path = [
                self._normalize_uv(cell, name="route.path_cells_uv")
                for cell in route["path_cells_uv"]
            ]
            self._start_route(
                actor,
                employee,
                phase="wander_back",
                start_uv=path[-1],
                target_uv=path[0],
                path=list(reversed(path)),
                update_window=False,
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="wander_turnaround",
                target_uv=list(path[-1]),
                render_owner="walking_depth",
            )
            return
        if phase == "wander_back":
            actor["position"] = {
                "floor_id": floor_id,
                "uv": None,
                "ground_xy": None,
                "route": None,
            }
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="wander_returned",
                render_owner="work_seat",
                action="work",
                subaction="normal_work",
            )
            return
        if phase == "to_workseat":
            actor["position"] = {
                "floor_id": floor_id,
                "uv": None,
                "ground_xy": None,
                "route": None,
            }
            actor["presence"] = "present"
            actor["activity"] = "working"
            actor["conversation_phase"] = None
            actor["behavior"].update({
                "next_event_due_ms": self._schedule_next_event(
                    actor, employee, now_ms=int(timestamp_ms)
                ),
                "active_event": None,
                "activity_started_ms": int(timestamp_ms),
                "activity_until_ms": None,
                "work_loop_elapsed_ms": 0,
                "work_loop_count": 0,
                "pending_home": False,
                "pending_home_due_ms": None,
            })
            actor["last_event"] = "return_requested"
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=actor["employee_id"],
                event_type="workseat_reentered",
                assignment_retained=True,
                slot_id=actor["assignment"]["slot_id"],
                render_owner="work_seat",
                action="work",
                subaction="normal_work",
            )
            return
        raise ActorSimulationError(f"{actor['employee_id']}: unknown route phase {phase!r}")

    def _advance_route(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        start_ms: int,
        target_ms: int,
        events: list[dict[str, Any]],
    ) -> int:
        now_ms = int(start_ms)
        while now_ms < target_ms and (
            actor["activity"] in self.ROUTE_ACTIVITIES
            or (
                actor["activity"] == "wandering"
                and actor["position"].get("route") is not None
            )
            or (
                actor["activity"] == "talking"
                and (actor["position"].get("route") or {}).get("phase") in self.TALK_ROUTE_PHASES
            )
        ):
            route = actor["position"].get("route")
            if not isinstance(route, dict):
                raise ActorSimulationError(
                    f"{actor['employee_id']}: {actor['activity']} actor needs a route"
                )
            duration = max(self.TICK_MS, int(route["duration_ms"]))
            elapsed = int(route.get("elapsed_ms", 0))
            if elapsed < 0 or elapsed > duration:
                raise ActorSimulationError(f"{actor['employee_id']}: route elapsed is invalid")
            remaining = duration - elapsed
            if remaining <= 0:
                self._finish_route_segment(
                    snapshot, actor, employee, timestamp_ms=now_ms, events=events
                )
                continue
            # Emit one renderer sample on each shared 60 ms boundary.  This
            # keeps depth crossings observable even when a caller advances a
            # large window in one reducer call, while still supporting a
            # partial final window without inventing a new clock.
            until_tick = self.TICK_MS - (elapsed % self.TICK_MS)
            step = min(target_ms - now_ms, remaining, until_tick)
            route["elapsed_ms"] = elapsed + step
            now_ms += step
            phase = route["phase"]
            if phase == "talk_outbound":
                actor["conversation_phase"] = "walking_to_talk"
            if phase in {"to_portal", "to_workseat", "wander_out", "wander_back", "talk_outbound", "talk_return"}:
                pose = self._path_pose(
                    [self._normalize_uv(cell, name="route.path_cells_uv") for cell in route["path_cells_uv"]],
                    int(route["elapsed_ms"]),
                    employee,
                )
            elif phase == "talk_hold":
                pose = self._talk_pose(route, int(route["elapsed_ms"]), employee)
            else:
                pose = self._portal_pose(route, int(route["elapsed_ms"]))
            if phase == "talk_hold":
                talk = actor["behavior"].get("talk") or {}
                talk_start = int(talk.get("talk_start_at_ms", now_ms))
                talk_end = int(talk.get("talk_end_at_ms", talk_start))
                return_start = int(talk.get("return_start_at_ms", talk_end))
                emotion = talk.get("emotion")
                if now_ms < talk_start:
                    actor["conversation_phase"] = "talk_arrival"
                    route["action"] = "idle"
                    route["subaction"] = "idle"
                elif now_ms < talk_end:
                    actor["conversation_phase"] = "talking"
                    route["action"] = "idle"
                    route["subaction"] = "idle"
                elif emotion in {"sad", "happy"} and now_ms < return_start:
                    actor["conversation_phase"] = "talk_complete"
                    route["action"] = str(emotion)
                    route["subaction"] = str(emotion)
                else:
                    actor["conversation_phase"] = "talk_complete"
                    route["action"] = "idle"
                    route["subaction"] = "idle"
            self._emit_route_sample(
                snapshot, actor, route, pose, timestamp_ms=now_ms, events=events
            )
            if actor["activity"] in self.ROUTE_ACTIVITIES:
                actor["behavior"]["activity_until_ms"] = now_ms + max(
                    0, duration - int(route["elapsed_ms"])
                )
            if int(route["elapsed_ms"]) >= duration:
                self._finish_route_segment(
                    snapshot, actor, employee, timestamp_ms=now_ms, events=events
                )
                continue
            # Continue through the remainder of the requested window.  The
            # next iteration either emits the next fixed-tick sample or
            # finishes the current segment and hands off to the next phase.
        return now_ms

    def _start_event(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        event: str,
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        if event not in self.WEIGHTED_EVENTS:
            raise ActorSimulationError(f"Unknown weighted recovery event: {event!r}")
        counter = int(actor["behavior"]["event_counter"]) + 1
        actor["behavior"]["event_counter"] = counter
        actor["behavior"]["active_event"] = event
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = (
            None
            if event == "talk"
            else int(timestamp_ms) + self._activity_duration_ms(
                employee,
                event,
                counter=counter,
            )
        )
        actor["behavior"]["next_event_due_ms"] = None
        actor["behavior"]["talk"] = None
        actor["behavior"]["cooldowns"][event] = int(timestamp_ms) + self._next_interval_ms(
            employee,
            counter=counter,
            now_ms=timestamp_ms,
            event=event,
        )
        actor["presence"] = "present"
        actor["activity"] = self.EVENT_ACTIVITY[event]
        actor["conversation_phase"] = "talk_pending" if event == "talk" else None
        if event == "wander":
            assignment = actor["assignment"]
            floor_id = assignment["floor_id"]
            gate = self._workseat_gate(assignment)
            try:
                target = self._normalize_uv(
                    self.pathfinding.resolve_near_target(floor_id, gate, min_distance=3),
                    name="wander target_uv",
                )
            except (PathfindingError, KeyError, TypeError, ValueError) as exc:
                raise ActorSimulationError(
                    f"Unable to resolve wander target for {actor['employee_id']}"
                ) from exc
            path = self._route_path(floor_id, gate, target)
            self._start_route(
                actor,
                employee,
                phase="wander_out",
                start_uv=gate,
                target_uv=target,
                path=path,
                update_window=False,
            )
        self._append_event(
            snapshot,
            events,
            timestamp_ms=timestamp_ms,
            employee_id=actor["employee_id"],
            event_type="behavior_started",
            behavior=event,
            activity=actor["activity"],
            activity_until_ms=actor["behavior"]["activity_until_ms"],
            presentation=self._presentation_for_behavior(
                employee,
                event,
                counter=counter,
            ),
        )

    def _complete_event(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        event = actor["behavior"].get("active_event")
        if event not in self.WEIGHTED_EVENTS:
            raise ActorSimulationError(f"{actor['employee_id']}: missing active recovery event")
        counter = int(actor["behavior"]["event_counter"])
        stamina = actor["stamina"]
        before = int(stamina["current_milli"])
        amount = self._recovery_amount_milli(employee, event, counter=counter)
        stamina["current_milli"] = min(self.MAX_STAMINA_MILLI, before + amount)
        stamina["threshold_band"] = self._threshold_band(stamina["current_milli"])
        actor["last_event"] = self.EVENT_LAST_EVENT[event]
        actor["activity"] = "working"
        actor["presence"] = "present"
        actor["conversation_phase"] = None
        actor["behavior"]["active_event"] = None
        actor["behavior"]["work_loop_elapsed_ms"] = 0
        actor["behavior"]["work_loop_count"] = 0
        actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
        actor["behavior"]["activity_until_ms"] = None
        actor["behavior"]["next_event_due_ms"] = self._schedule_next_event(
            actor,
            employee,
            now_ms=timestamp_ms,
        )
        self._append_event(
            snapshot,
            events,
            timestamp_ms=timestamp_ms,
            employee_id=actor["employee_id"],
            event_type="stamina_recovery",
            behavior=event,
            recovery_milli=amount,
            stamina_before_milli=before,
            stamina_after_milli=stamina["current_milli"],
            presentation_ended=True,
        )

    def apply_emotion_effect(
        self,
        snapshot: dict[str, Any],
        employee_id: str,
        emotion: str,
        *,
        timestamp_ms: int | None = None,
        source_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply one standing-pair emotion bonus/penalty to actor stamina.

        Speech owns the deterministic ``sad``/``happy`` outcome, while this
        reducer remains the sole owner of numeric stamina mutation.  The
        operation is pure with respect to the caller's snapshot and emits a
        JSON-safe event suitable for persistence/replay.
        """
        current = self.validate_snapshot(snapshot)
        if not isinstance(employee_id, str) or not employee_id:
            raise ActorSimulationError("employee_id is required")
        if emotion not in self.EMOTION_STAMINA_EFFECT_MILLI:
            raise ActorSimulationError(f"Unknown emotion stamina effect: {emotion!r}")
        actor = current["actors"].get(employee_id)
        if actor is None:
            raise ActorSimulationError(f"Unknown or inactive employee: {employee_id!r}")
        if timestamp_ms is None:
            timestamp_ms = int(current["clock"]["simulation_time_ms"])
        timestamp_ms = self._require_int(timestamp_ms, "timestamp_ms")
        events: list[dict[str, Any]] = []
        self._apply_emotion_effect_in_place(
            current,
            actor,
            emotion,
            timestamp_ms=timestamp_ms,
            source_session_id=source_session_id,
            events=events,
        )
        current = self.validate_snapshot(current)
        return {"snapshot": current, "events": events}

    def _apply_emotion_effect_in_place(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        emotion: str,
        *,
        timestamp_ms: int,
        source_session_id: str | None,
        events: list[dict[str, Any]],
    ) -> None:
        delta = int(self.EMOTION_STAMINA_EFFECT_MILLI[emotion])
        stamina = actor["stamina"]
        before = int(stamina["current_milli"])
        after = max(0, min(self.MAX_STAMINA_MILLI, before + delta))
        stamina["current_milli"] = after
        stamina["threshold_band"] = self._threshold_band(after)
        actor["last_event"] = f"emotion_{emotion}_{'bonus' if delta > 0 else 'penalty'}"
        payload: dict[str, Any] = {
            "emotion": emotion,
            "effect_milli": delta,
            "effect_display": delta / self.MILLI_SCALE,
            "stamina_before_milli": before,
            "stamina_after_milli": after,
            "source": "speech_scheduler",
        }
        if source_session_id is not None:
            payload["session_id"] = str(source_session_id)
        self._append_event(
            snapshot,
            events,
            timestamp_ms=int(timestamp_ms),
            employee_id=actor["employee_id"],
            event_type="stamina_emotion_effect",
            **payload,
        )
        previous_band = self._threshold_band(before)
        current_band = self._threshold_band(after)
        if self._threshold_rank(current_band) < self._threshold_rank(previous_band):
            for band, threshold_milli in (
                ("low", self.LOW_THRESHOLD_MILLI),
                ("critical", self.CRITICAL_THRESHOLD_MILLI),
            ):
                if self._threshold_rank(previous_band) > self._threshold_rank(band) >= self._threshold_rank(current_band):
                    self._append_event(
                        snapshot,
                        events,
                        timestamp_ms=int(timestamp_ms),
                        employee_id=actor["employee_id"],
                        event_type="threshold_crossed",
                        threshold_band=band,
                        stamina_milli=threshold_milli,
                        source="emotion_effect",
                    )
        if (
            current_band == "critical"
            and actor["activity"] == "working"
            and not actor["behavior"].get("pending_home", False)
        ):
            # The speech event may have occurred inside a large host advance;
            # the state we are mutating is already at that advance's end.  Do
            # not create a stale boundary in the past.
            queue_timestamp = max(
                int(timestamp_ms),
                int(snapshot["clock"]["simulation_time_ms"]),
            )
            due = self._queue_critical_home(actor, timestamp_ms=queue_timestamp)
            self._append_event(
                snapshot,
                events,
                timestamp_ms=queue_timestamp,
                employee_id=actor["employee_id"],
                event_type="home_queued",
                reason="stamina_critical",
                stamina_milli=after,
                finish_work_loop_at_ms=due,
                work_loop_ms=self.WORK_LOOP_MS,
            )

    def _advance_actor(
        self,
        snapshot: dict[str, Any],
        actor: dict[str, Any],
        employee: dict[str, Any],
        *,
        start_ms: int,
        target_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        now_ms = int(start_ms)
        while now_ms < target_ms:
            activity = actor["activity"]
            if activity in self.ROUTE_ACTIVITIES or (
                activity == "wandering" and actor["position"].get("route") is not None
            ) or (
                activity == "talking"
                and (actor["position"].get("route") or {}).get("phase") in self.TALK_ROUTE_PHASES
            ):
                advanced_to = self._advance_route(
                    snapshot,
                    actor,
                    employee,
                    start_ms=now_ms,
                    target_ms=target_ms,
                    events=events,
                )
                if advanced_to <= now_ms:
                    break
                now_ms = advanced_to
                continue
            if activity == "talking":
                # A weighted talk event is a request until Central accepts a
                # speech/conversation session.  It must not consume the old
                # generic 5–8 second activity window while waiting in the
                # speech lane.
                talk = actor["behavior"].get("talk")
                if actor["conversation_phase"] == "talk_pending" and talk is None:
                    queue_deadline = int(actor["behavior"].get("activity_started_ms", now_ms)) + self.TALK_QUEUE_TIMEOUT_MS
                    if queue_deadline <= target_ms:
                        now_ms = queue_deadline
                        self._cancel_talk(
                            snapshot,
                            actor,
                            employee,
                            timestamp_ms=now_ms,
                            events=events,
                            reason="talk_queue_timeout",
                        )
                        continue
                    break
                if talk is None:
                    raise ActorSimulationError(
                        f"{actor['employee_id']}: talking actor lacks talk session metadata"
                    )
                # Stationary hosts (CEO/seated-host) have no locomotion route,
                # but their actor phase still follows the shared speech clock.
                # Keep the phase observable even while the host remains seated.
                if actor["position"].get("route") is None and actor["conversation_phase"] != "self_talk":
                    talk_start = int(talk.get("talk_start_at_ms", now_ms))
                    talk_end = int(talk.get("talk_end_at_ms", talk_start))
                    return_start = int(talk.get("return_start_at_ms", talk_end))
                    emotion = talk.get("emotion")
                    if now_ms < talk_start:
                        actor["conversation_phase"] = "talk_arrival"
                    elif now_ms < talk_end:
                        actor["conversation_phase"] = "talking"
                    elif emotion in {"sad", "happy"} and now_ms < return_start:
                        actor["conversation_phase"] = "talk_complete"
                    else:
                        actor["conversation_phase"] = "talk_complete"
                until = actor["behavior"].get("activity_until_ms")
                if until is None:
                    break
                if int(until) > target_ms:
                    break
                now_ms = int(until)
                if actor["position"].get("route") is None:
                    self._finish_talk_actor(
                        snapshot,
                        actor,
                        employee,
                        timestamp_ms=now_ms,
                        events=events,
                    )
                    continue
                # A routed talk session should always transition through its
                # talk_return route before this branch is reached.
                raise ActorSimulationError(
                    f"{actor['employee_id']}: routed talk reached its end without a return route"
                )
            if activity == "working":
                behavior = actor["behavior"]
                if actor["stamina"]["threshold_band"] == "critical" and not behavior.get(
                    "pending_home", False
                ):
                    due = self._queue_critical_home(actor, timestamp_ms=now_ms)
                    self._append_event(
                        snapshot,
                        events,
                        timestamp_ms=now_ms,
                        employee_id=actor["employee_id"],
                        event_type="home_queued",
                        reason="stamina_critical",
                        stamina_milli=int(actor["stamina"]["current_milli"]),
                        finish_work_loop_at_ms=due,
                        work_loop_ms=self.WORK_LOOP_MS,
                    )
                if behavior.get("pending_home", False):
                    due = int(behavior["pending_home_due_ms"])
                    if due <= now_ms:
                        self._begin_home_route(
                            snapshot,
                            actor,
                            employee,
                            timestamp_ms=now_ms,
                            events=events,
                            reason="stamina_critical",
                            work_loop_completed=True,
                        )
                        continue
                    step_target = min(target_ms, due)
                    self._advance_work_loop(actor, step_target - now_ms)
                    now_ms = step_target
                    if now_ms >= due:
                        self._begin_home_route(
                            snapshot,
                            actor,
                            employee,
                            timestamp_ms=now_ms,
                            events=events,
                            reason="stamina_critical",
                            work_loop_completed=True,
                        )
                        continue
                    break
                due = actor["behavior"].get("next_event_due_ms")
                if due is None:
                    due = self._schedule_next_event(actor, employee, now_ms=now_ms)
                    actor["behavior"]["next_event_due_ms"] = due
                boundary = min(target_ms, int(due))
                self._drain_work(
                    snapshot,
                    actor,
                    employee,
                    start_ms=now_ms,
                    elapsed_ms=boundary - now_ms,
                    events=events,
                )
                now_ms = boundary
                if actor["behavior"].get("pending_home", False):
                    home_due = int(actor["behavior"]["pending_home_due_ms"])
                    if home_due <= now_ms:
                        self._begin_home_route(
                            snapshot,
                            actor,
                            employee,
                            timestamp_ms=home_due,
                            events=events,
                            reason="stamina_critical",
                            work_loop_completed=True,
                        )
                        now_ms = home_due
                        continue
                    if home_due <= target_ms:
                        now_ms = home_due
                        self._begin_home_route(
                            snapshot,
                            actor,
                            employee,
                            timestamp_ms=home_due,
                            events=events,
                            reason="stamina_critical",
                            work_loop_completed=True,
                        )
                        continue
                    if now_ms < target_ms:
                        self._advance_work_loop(actor, target_ms - now_ms)
                        now_ms = target_ms
                    break
                if now_ms >= target_ms:
                    break
                try:
                    event = self.choose_behavior_event(
                        actor["employee_id"],
                        simulation_time_ms=now_ms,
                        event_counter=int(actor["behavior"]["event_counter"]),
                        cooldowns=actor["behavior"]["cooldowns"],
                    )
                except ActorSimulationError as exc:
                    # A review host may shorten ``next_event_due_ms`` to make
                    # behaviors visible, while each event still owns its
                    # longer cooldown.  If all weighted events are cooling
                    # down, wait for the earliest one instead of turning a
                    # valid actor state into a fatal tick error.
                    if str(exc) != "No eligible weighted recovery event":
                        raise
                    future_cooldowns = [
                        int(value)
                        for value in actor["behavior"]["cooldowns"].values()
                        if int(value) > now_ms
                    ]
                    if not future_cooldowns:
                        raise
                    actor["behavior"]["next_event_due_ms"] = min(future_cooldowns)
                    continue
                self._start_event(
                    snapshot,
                    actor,
                    employee,
                    event,
                    timestamp_ms=now_ms,
                    events=events,
                )
                continue

            if activity in self.EVENT_ACTIVITY.values() and activity != "talking":
                until = actor["behavior"].get("activity_until_ms")
                if until is None:
                    raise ActorSimulationError(
                        f"{actor['employee_id']}: active recovery activity has no end time"
                    )
                if int(until) > target_ms:
                    break
                now_ms = int(until)
                self._complete_event(
                    snapshot,
                    actor,
                    employee,
                    timestamp_ms=now_ms,
                    events=events,
                )
                continue

            # Home recovery intentionally holds the actor off the map until an
            # explicit request_return command.  Its ready timestamp remains a
            # deterministic gate but does not auto-spawn the actor.
            break

    def _apply_command(
        self,
        snapshot: dict[str, Any],
        command: dict[str, Any],
        *,
        timestamp_ms: int,
        events: list[dict[str, Any]],
    ) -> None:
        if not isinstance(command, dict):
            raise ActorSimulationError("commands must contain objects")
        employee_id = command.get("employee_id")
        command_type = command.get("type")
        if not isinstance(employee_id, str) or not employee_id:
            raise ActorSimulationError("command.employee_id is required")
        actor = snapshot["actors"].get(employee_id)
        if actor is None:
            raise ActorSimulationError(f"Unknown or inactive employee: {employee_id!r}")
        if command_type == "start_talk_session":
            self._start_talk_session(
                snapshot,
                actor,
                self.employee_registry.get(employee_id),
                command,
                timestamp_ms=timestamp_ms,
                events=events,
            )
            return
        if command_type == "cancel_talk":
            self._cancel_talk(
                snapshot,
                actor,
                self.employee_registry.get(employee_id),
                timestamp_ms=timestamp_ms,
                events=events,
                reason=str(command.get("reason") or "cancelled_by_caller"),
            )
            return
        if command_type == "request_home":
            if actor["presence"] != "present" or actor["activity"] == "talking":
                raise ActorSimulationError(f"{employee_id}: actor cannot request home in current state")
            # Explicit host requests retain their historical immediate route
            # semantics.  Stamina-triggered requests use the smooth
            # work-loop boundary path in _advance_actor.
            self._begin_home_route(
                snapshot,
                actor,
                self.employee_registry.get(employee_id),
                timestamp_ms=timestamp_ms,
                events=events,
            )
            return
        if command_type == "request_return":
            if actor["presence"] != "home" or actor["activity"] != "home_recovery":
                raise ActorSimulationError(f"{employee_id}: actor cannot return in current state")
            ready_at = actor["behavior"].get("activity_until_ms")
            if ready_at is None or int(ready_at) > int(timestamp_ms):
                raise ActorSimulationError(f"{employee_id}: home recovery is not ready")
            floor_id = actor["assignment"]["floor_id"]
            inside, outside = self._portal_pair(floor_id)
            actor["presence"] = "entering"
            actor["activity"] = "returning_to_work"
            actor["conversation_phase"] = None
            actor["behavior"]["next_event_due_ms"] = None
            actor["behavior"]["active_event"] = None
            actor["behavior"]["activity_started_ms"] = int(timestamp_ms)
            actor["behavior"]["activity_until_ms"] = None
            actor["last_event"] = "return_requested"
            self._start_route(
                actor,
                self.employee_registry.get(employee_id),
                phase="portal_entry",
                start_uv=outside,
                target_uv=inside,
                path=[outside, inside],
                duration_ms=self.PORTAL_FADE_STEPS * self.TICK_MS,
            )
            self._append_event(
                snapshot,
                events,
                timestamp_ms=timestamp_ms,
                employee_id=employee_id,
                event_type="return_requested",
                assignment_retained=True,
            )
            return
        raise ActorSimulationError(f"Unknown actor command: {command_type!r}")

    def advance_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        commands: Iterable[dict[str, Any]] | None = None,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Advance one validated snapshot and return the next snapshot plus events."""
        # Trusted host loops may already validate at their lifecycle boundary.
        # Skipping this defensive canonical/deep-copy pass keeps a 60ms review
        # tick from copying long talk routes several times. The default remains
        # fully validating and copy-isolated for normal callers.
        current = self.validate_snapshot(snapshot) if validate else snapshot
        elapsed_ms = self._require_int(elapsed_ms, "elapsed_ms")
        start_ms = int(current["clock"]["simulation_time_ms"])
        target_ms = start_ms + elapsed_ms
        events: list[dict[str, Any]] = []

        if commands is not None:
            command_list = list(commands)
            if any(not isinstance(item, dict) for item in command_list):
                raise ActorSimulationError("commands must contain objects")
            command_list.sort(key=lambda item: str(item.get("employee_id", "")))
            for command in command_list:
                self._apply_command(
                    current,
                    command,
                    timestamp_ms=start_ms,
                    events=events,
                )

        for employee_id in sorted(current["actors"]):
            actor = current["actors"][employee_id]
            try:
                employee = self.employee_registry.get(employee_id)
            except EmployeeMetadataError as exc:
                raise ActorSimulationError(str(exc)) from exc
            self._advance_actor(
                current,
                actor,
                employee,
                start_ms=start_ms,
                target_ms=target_ms,
                events=events,
            )
        current["clock"]["simulation_time_ms"] = target_ms
        if validate:
            current = self.validate_snapshot(current)
        events.sort(key=lambda event: (str(event["employee_id"]), int(event["event_index"])))
        return {
            "snapshot": current,
            "events": events,
        }

    def advance_actor_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        commands: Iterable[dict[str, Any]] | None = None,
        validate: bool = True,
    ) -> dict[str, Any]:
        return self.advance_snapshot(
            snapshot,
            elapsed_ms,
            commands=commands,
            validate=validate,
        )
