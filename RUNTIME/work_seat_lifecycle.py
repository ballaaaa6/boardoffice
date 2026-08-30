from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

from CHARACTER.IDENTITY.RUNTIME.identity_resolver import CharacterIdentityLookupError
from CHARACTER.RUNTIME.character_system import CharacterSystem, CharacterSystemError
from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from RUNTIME.work_seat_core import WorkSeatCore, WorkSeatError
from WORLD.RUNTIME.navigation_occupancy_core import (
    NavigationOccupancyCore,
    NavigationOccupancyError,
)
from WORLD.RUNTIME.pathfinding_core import PathfindingCore, PathfindingError


class WorkSeatLifecycleError(ValueError):
    """Raised when a deterministic WorkSeat lifecycle cannot be resolved."""


class WorkSeatLifecycle:
    """Coordinate one actor's walk-to-seat, seated-work and walk-away cycle.

    The class emits renderer-agnostic JSON-safe state rows. Navigation owns the
    exterior transition gate; WorkSeatCore owns seated visual composition. No
    gameplay anchor is inferred from a visual sprite offset, and no queue or
    multi-actor scheduler is hidden in this resolver.
    """

    WALKING_TO_SEAT = "walking_to_seat"
    APPROACH = "approach"
    SEATED_WORK = "seated_work"
    EXIT_SEAT = "exit_seat"
    WALKING_FROM_SEAT = "walking_from_seat"

    FREE = "free"
    RESERVED = "reserved"
    OCCUPIED = "occupied"
    RELEASING = "releasing"

    WALKING_OWNER = "walking_depth"
    SEATED_OWNER = "work_seat"

    DEFAULT_TICK_MS = 60
    DEFAULT_WORK_TICKS = 24
    DEFAULT_CHARACTER_FRAME_MS = 220
    DEFAULT_OVERLAY_FRAME_MS = 140

    def __init__(
        self,
        root: str | Path,
        *,
        movement: CharacterMovementCore | None = None,
        navigation: NavigationOccupancyCore | None = None,
        pathfinding: PathfindingCore | None = None,
        work_seats: WorkSeatCore | None = None,
        characters: CharacterSystem | None = None,
    ):
        self.root = Path(root).resolve()
        self.contract = self._load_contract()
        self.navigation = navigation or NavigationOccupancyCore(self.root / "WORLD")
        self.pathfinding = pathfinding or PathfindingCore(
            self.root / "WORLD", occupancy=self.navigation
        )
        self.movement = movement or CharacterMovementCore(
            self.root, pathfinding=self.pathfinding
        )
        self.characters = characters or CharacterSystem(self.root / "CHARACTER")
        self.work_seats = work_seats or WorkSeatCore(
            self.root, characters=self.characters
        )

        timing = self.contract["timing"]
        self.tick_ms = self._positive_int("playback_tick_ms", timing["playback_tick_ms"])
        self.approach_ticks = self._positive_int("approach_ticks", timing["approach_ticks"])
        self.exit_ticks = self._positive_int("exit_ticks", timing["exit_ticks"])
        self.character_frame_ms = self._positive_int(
            "work_character_frame_ms", timing["work_character_frame_ms"]
        )
        self.effect_frame_ms = self._positive_int(
            "work_effect_frame_ms", timing["work_effect_frame_ms"]
        )
        self.humanball_frame_ms = self._positive_int(
            "work_humanball_frame_ms", timing["work_humanball_frame_ms"]
        )

    def _load_contract(self) -> dict[str, Any]:
        path = self.root / "CONTRACTS" / "work_seat_lifecycle.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkSeatLifecycleError(f"Unable to load WorkSeat lifecycle contract: {path}") from exc
        if payload.get("schema") != "gds.work_seat_lifecycle.v1":
            raise WorkSeatLifecycleError("Unsupported WorkSeat lifecycle contract")
        return payload

    @staticmethod
    def _positive_int(name: str, value: Any) -> int:
        if isinstance(value, bool):
            raise WorkSeatLifecycleError(f"{name} must be a positive integer")
        try:
            out = int(value)
        except (TypeError, ValueError) as exc:
            raise WorkSeatLifecycleError(f"{name} must be a positive integer") from exc
        if out <= 0:
            raise WorkSeatLifecycleError(f"{name} must be a positive integer")
        return out

    @staticmethod
    def _normalize_uv(uv: tuple[int, int] | list[int]) -> tuple[int, int]:
        if not isinstance(uv, (tuple, list)) or len(uv) != 2:
            raise WorkSeatLifecycleError(f"Expected uv pair, got: {uv!r}")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in uv):
            raise WorkSeatLifecycleError(f"UV coordinates must be integers: {uv!r}")
        return int(uv[0]), int(uv[1])

    @staticmethod
    def _round_xy(xy: Iterable[float | int]) -> list[float]:
        values = list(xy)
        if len(values) != 2:
            raise WorkSeatLifecycleError(f"Expected ground coordinate pair, got: {xy!r}")
        return [round(float(values[0]), 4), round(float(values[1]), 4)]

    @staticmethod
    def _phase_ranges(states: list[dict[str, Any]]) -> dict[str, list[int]]:
        ranges: dict[str, list[int]] = {}
        for index, state in enumerate(states):
            phase = state["phase"]
            if phase in ranges:
                ranges[phase][1] = index
            else:
                ranges[phase] = [index, index]
        return ranges

    @staticmethod
    def _phase_counts(states: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for state in states:
            phase = state["phase"]
            counts[phase] = counts.get(phase, 0) + 1
        return counts

    def _character_id(self, query: int | str) -> str:
        try:
            return self.movement.identity.resolve_character_id(query)
        except CharacterIdentityLookupError as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc

    def _resolve_subaction(self, subaction: str) -> str:
        if not isinstance(subaction, str) or not subaction:
            raise WorkSeatLifecycleError("work subaction must be a non-empty string")
        supported = set(self.work_seats.contract.get("supported_subactions", []))
        if subaction not in supported:
            raise WorkSeatLifecycleError(f"Unsupported work subaction: {subaction}")
        return subaction

    def _resolve_slot_sources(self, floor_id: str, workstation_id: str) -> tuple[dict, dict]:
        try:
            seat = self.work_seats.resolve_workstation_seat(floor_id, workstation_id)
            access = self.navigation.workstation_access(floor_id, workstation_id)
        except (WorkSeatError, NavigationOccupancyError, KeyError, ValueError) as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc
        if seat["chair_placement_id"] != access["chair_placement_id"]:
            raise WorkSeatLifecycleError(
                f"Navigation/work-seat chair mismatch for {floor_id}.{workstation_id}: "
                f"{access['chair_placement_id']} != {seat['chair_placement_id']}"
            )
        gate = access.get("transition_gate_uv")
        if gate is None:
            raise WorkSeatLifecycleError(
                f"{floor_id}.{workstation_id}: missing WorkSeat transition gate"
            )
        gate_uv = self._normalize_uv(gate)
        if not access.get("chair_fully_inside_room"):
            raise WorkSeatLifecycleError(
                f"{floor_id}.{workstation_id}: chair is not fully inside the room"
            )
        if int(access.get("reachable_approach_cell_count", 0)) <= 0:
            raise WorkSeatLifecycleError(
                f"{floor_id}.{workstation_id}: transition gate is not reachable"
            )
        if not self.navigation.is_walkable(floor_id, *gate_uv):
            raise WorkSeatLifecycleError(
                f"{floor_id}.{workstation_id}: transition gate is not walkable: {gate_uv}"
            )
        return seat, access

    def resolve_interaction_slot(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        """Derive one capacity-one object-owned interaction slot."""
        seat, access = self._resolve_slot_sources(floor_id, workstation_id)
        gate = self._normalize_uv(access["transition_gate_uv"])
        facing = str(seat["direction"]).upper()
        slot_id = f"workseat:{floor_id}:{workstation_id}:primary"
        return {
            "slot_id": slot_id,
            "floor_id": floor_id,
            "workstation_id": workstation_id,
            "capacity": 1,
            "transition_gate_uv": list(gate),
            "facing": facing,
            "chair_placement_id": seat["chair_placement_id"],
            "chair_family_id": seat["chair_family_id"],
            "chair_asset_id": seat["chair_asset_id"],
            "render_owner": self.SEATED_OWNER,
            "action_binding": {
                "idle": {"action": "idle", "direction": facing},
                "work": {
                    "action": "work",
                    "direction": facing,
                    "subaction": "normal_work",
                },
                "walking": {"action": "move", "direction_source": "movement_path"},
            },
            "effect_id": None,
            "humanball_id": None,
            "enter_action": None,
            "exit_action": None,
            "seat_transition_ready": True,
            "navigation_access": {
                "transition_gate_uv": list(gate),
                "reachable_approach_cell_count": int(
                    access["reachable_approach_cell_count"]
                ),
                "approach_cells_uv": [list(cell) for cell in access["approach_cells_uv"]],
                "reachable_approach_cells_uv": [
                    list(cell) for cell in access["reachable_approach_cells_uv"]
                ],
            },
        }

    def resolve_interaction_slots(self, floor_id: str) -> list[dict[str, Any]]:
        """Return derived slots for every authored workstation on a floor."""
        try:
            workstation_ids = sorted(self.work_seats.world.floor_layout(floor_id)["workstation_groups"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkSeatLifecycleError(f"Unknown floor: {floor_id}") from exc
        return [self.resolve_interaction_slot(floor_id, workstation_id) for workstation_id in workstation_ids]

    def audit_all_interaction_slots(self) -> dict[str, Any]:
        """Audit every derived slot without materializing a registry."""
        try:
            floor_ids = sorted(self.work_seats.world.floors)
        except AttributeError as exc:
            raise WorkSeatLifecycleError("World floor registry is unavailable") from exc
        slots: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for floor_id in floor_ids:
            try:
                slots.extend(self.resolve_interaction_slots(floor_id))
            except WorkSeatLifecycleError as exc:
                errors.append({"floor_id": floor_id, "error": str(exc)})
        ids = [slot["slot_id"] for slot in slots]
        return {
            "schema": "gds.work_seat_lifecycle_slot_audit.v1",
            "floor_count": len(floor_ids),
            "workstation_count": len(slots),
            "slot_count": len(slots),
            "unique_slot_id_count": len(set(ids)),
            "capacity_values": sorted(set(int(slot["capacity"]) for slot in slots)),
            "direction_counts": {
                direction: sum(slot["facing"] == direction for slot in slots)
                for direction in ("SE", "NW", "SW")
            },
            "all_ready": all(bool(slot["seat_transition_ready"]) for slot in slots),
            "duplicate_slot_ids": sorted({slot_id for slot_id in ids if ids.count(slot_id) > 1}),
            "errors": errors,
            "pass": bool(
                not errors
                and len(slots) == 219
                and len(set(ids)) == len(ids)
                and all(int(slot["capacity"]) == 1 for slot in slots)
                and all(bool(slot["seat_transition_ready"]) for slot in slots)
            ),
        }

    def _state(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        slot: dict[str, Any],
        phase: str,
        slot_state: str,
        action: str,
        direction: str,
        timestamp_ms: int,
        ground_xy: Iterable[float | int] | None,
        current_uv: tuple[int, int] | None,
        from_uv: tuple[int, int] | None = None,
        to_uv: tuple[int, int] | None = None,
        progress_t: float | None = None,
        raw_direction: str | None = None,
        render_owner: str,
        visible: bool,
        movement_profile: dict[str, Any],
        frame_index: int | None = None,
        work_render: dict[str, Any] | None = None,
        seated_elapsed_ms: int | None = None,
    ) -> dict[str, Any]:
        walking_visible = render_owner == self.WALKING_OWNER and bool(visible)
        seated_visible = render_owner == self.SEATED_OWNER and bool(visible)
        return {
            "actor_id": actor_id,
            "character_id": character_id,
            "floor_id": floor_id,
            "slot_id": slot["slot_id"],
            "phase": phase,
            "slot_state": slot_state,
            "action": action,
            "direction": direction,
            "raw_direction": raw_direction or direction,
            "timestamp_ms": int(timestamp_ms),
            "tick_ms": self.tick_ms,
            "ground_xy": self._round_xy(ground_xy) if ground_xy is not None else None,
            "current_uv": list(current_uv) if current_uv is not None else None,
            "from_uv": list(from_uv) if from_uv is not None else None,
            "to_uv": list(to_uv) if to_uv is not None else None,
            "progress_t": round(float(progress_t), 4) if progress_t is not None else None,
            "visible": bool(visible),
            "walking_visible": walking_visible,
            "seated_visible": seated_visible,
            "render_channels": {
                "walking_depth": walking_visible,
                "work_seat": seated_visible,
            },
            "render_owner": render_owner,
            "cumulative_distance_px": None,
            "frame_index": int(frame_index) if frame_index is not None else None,
            "speed_percent": int(movement_profile["speed_percent"]),
            "speed_multiplier": float(movement_profile["speed_multiplier"]),
            "movement_profile": dict(movement_profile),
            "transition_gate_uv": list(slot["transition_gate_uv"]),
            "seated_position_source": "WorkSeatCore" if phase == self.SEATED_WORK else None,
            "seated_position_is_navigation_anchor": False if phase == self.SEATED_WORK else None,
            "seated_elapsed_ms": seated_elapsed_ms,
            "work_render": work_render,
        }

    def _path_states(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        slot: dict[str, Any],
        phase: str,
        path: list[tuple[int, int]],
        start_timestamp_ms: int,
        slot_state: str,
        movement_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            samples = self.movement.sample_path_timeline(
                path,
                speed_multiplier=float(movement_profile["speed_multiplier"]),
                tick_ms=self.tick_ms,
            )
        except (CharacterMovementError, ValueError) as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc
        states: list[dict[str, Any]] = []
        for sample in samples:
            direction = str(sample["direction"]).upper()
            state = self._state(
                actor_id=actor_id,
                character_id=character_id,
                floor_id=floor_id,
                slot=slot,
                phase=phase,
                slot_state=slot_state,
                action="move",
                direction=direction,
                raw_direction=str(sample["raw_direction"]).upper(),
                timestamp_ms=start_timestamp_ms + int(sample["elapsed_ms"]),
                ground_xy=sample["ground_xy"],
                current_uv=(
                    self._normalize_uv(sample["to_uv"])
                    if math.isclose(float(sample["progress_t"]), 1.0, abs_tol=1e-9)
                    else None
                ),
                from_uv=self._normalize_uv(sample["from_uv"]),
                to_uv=self._normalize_uv(sample["to_uv"]),
                progress_t=float(sample["progress_t"]),
                render_owner=self.WALKING_OWNER,
                visible=True,
                movement_profile=movement_profile,
            )
            state["cumulative_distance_px"] = round(float(sample["cumulative_distance_px"]), 4)
            try:
                frame_ids = self.characters.resolve_frame_ids(character_id, "move", direction)
            except CharacterSystemError as exc:
                raise WorkSeatLifecycleError(str(exc)) from exc
            state["frame_index"] = self.movement.walk_cycle_frame_index(
                float(sample["cumulative_distance_px"]),
                len(frame_ids),
                frame_distance_cells=float(movement_profile["walk_frame_distance_cells"]),
            )
            states.append(state)
        return states

    def _arrival_state(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        slot: dict[str, Any],
        phase: str,
        slot_state: str,
        timestamp_ms: int,
        uv: tuple[int, int],
        direction: str,
        movement_profile: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            frame_ids = self.characters.resolve_frame_ids(character_id, "idle", direction)
        except CharacterSystemError as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc
        return self._state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=phase,
            slot_state=slot_state,
            action="idle",
            direction=direction,
            timestamp_ms=timestamp_ms,
            ground_xy=self.movement.uv_cell_center_to_pixel(*uv),
            current_uv=uv,
            render_owner=self.WALKING_OWNER,
            visible=True,
            movement_profile=movement_profile,
            frame_index=0 if frame_ids else None,
        )

    def _work_render_payload(
        self,
        *,
        character_id: str,
        slot: dict[str, Any],
        subaction: str,
        elapsed_ms: int,
        effect_id: str | None,
        humanball_id: str | None,
        character_frame_count: int,
        effect_frame_count: int | None,
        humanball_frame_count: int | None,
    ) -> dict[str, Any]:
        payload = {
            "render_owner": self.SEATED_OWNER,
            "character_id": character_id,
            "action": "work",
            "direction": slot["facing"],
            "subaction": subaction,
            "chair_family_id": slot["chair_family_id"],
            "chair_placement_id": slot["chair_placement_id"],
            "character_frame_index": (elapsed_ms // self.character_frame_ms) % character_frame_count,
            "effect_id": effect_id,
            "effect_frame_index": (
                (elapsed_ms // self.effect_frame_ms) % effect_frame_count
                if effect_id is not None and effect_frame_count
                else None
            ),
            "humanball_id": humanball_id,
            "humanball_frame_index": (
                (elapsed_ms // self.humanball_frame_ms) % humanball_frame_count
                if humanball_id is not None and humanball_frame_count
                else None
            ),
            "character_frame_ms": self.character_frame_ms,
            "effect_frame_ms": self.effect_frame_ms if effect_id is not None else None,
            "humanball_frame_ms": self.humanball_frame_ms if humanball_id is not None else None,
            "seated_position_source": "WorkSeatCore",
            "seated_position_is_navigation_anchor": False,
        }
        payload["frame_index"] = payload["character_frame_index"]
        return payload

    def resolve_actor_cycle(
        self,
        character_query: int | str,
        floor_id: str,
        workstation_id: str,
        start_uv: tuple[int, int] | list[int],
        exit_goal_uv: tuple[int, int] | list[int] | None = None,
        work_ticks: int = DEFAULT_WORK_TICKS,
        subaction: str = "normal_work",
        effect_id: str | None = None,
        humanball_id: str | None = None,
    ) -> dict[str, Any]:
        character_id = self._character_id(character_query)
        slot = self.resolve_interaction_slot(floor_id, workstation_id)
        start = self._normalize_uv(start_uv)
        exit_goal = self._normalize_uv(exit_goal_uv) if exit_goal_uv is not None else start
        try:
            work_ticks = self._positive_int("work_ticks", work_ticks)
        except WorkSeatLifecycleError:
            raise
        subaction = self._resolve_subaction(subaction)
        if (effect_id is not None or humanball_id is not None) and subaction != "normal_work":
            raise WorkSeatLifecycleError(
                "Work VFX/HumanBall overlays are supported only for normal_work"
            )

        movement_profile = self.movement.resolve_movement_profile(character_id)
        try:
            inbound_result = self.pathfinding.find_path(floor_id, start, slot["transition_gate_uv"])
            outbound_result = self.pathfinding.find_path(
                floor_id, slot["transition_gate_uv"], exit_goal
            )
        except (PathfindingError, ValueError) as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc
        inbound = [self._normalize_uv(cell) for cell in inbound_result["path_cells_uv"]]
        outbound = [self._normalize_uv(cell) for cell in outbound_result["path_cells_uv"]]
        if not inbound or inbound[-1] != tuple(slot["transition_gate_uv"]):
            raise WorkSeatLifecycleError("Inbound path does not end exactly at transition gate")
        if not outbound or outbound[0] != tuple(slot["transition_gate_uv"]):
            raise WorkSeatLifecycleError("Outbound path does not start exactly at transition gate")

        try:
            work_action = self.characters.render(
                character_id, "work", slot["facing"], subaction
            )
            if not work_action.frames:
                raise WorkSeatLifecycleError("Work action produced no frames")
            effect_result = (
                self.characters.render_effect(effect_id, slot["facing"])
                if effect_id is not None
                else None
            )
            humanball_result = (
                self.characters.render_humanball(
                    humanball_id, slot["facing"], human_size=(32, 42)
                )
                if humanball_id is not None
                else None
            )
        except CharacterSystemError as exc:
            raise WorkSeatLifecycleError(str(exc)) from exc
        effect_count = len(effect_result.frames) if effect_result is not None else None
        humanball_count = len(humanball_result.frames) if humanball_result is not None else None

        actor_id = f"{floor_id}:{workstation_id}:{character_id}"
        states: list[dict[str, Any]] = []
        slot_events: list[dict[str, Any]] = [
            {
                "from_state": self.FREE,
                "to_state": self.RESERVED,
                "phase": self.WALKING_TO_SEAT,
                "state_index": 0,
                "timestamp_ms": 0,
            }
        ]

        inbound_direction = (
            self.movement.direction_for_step(inbound[0], inbound[1])
            if len(inbound) > 1
            else slot["facing"]
        )
        initial = self._state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.WALKING_TO_SEAT,
            slot_state=self.RESERVED,
            action="move" if len(inbound) > 1 else "idle",
            direction=inbound_direction,
            timestamp_ms=0,
            ground_xy=self.movement.uv_cell_center_to_pixel(*start),
            current_uv=start,
            render_owner=self.WALKING_OWNER,
            visible=True,
            movement_profile=movement_profile,
            frame_index=0,
        )
        states.append(initial)

        inbound_states = self._path_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.WALKING_TO_SEAT,
            path=inbound,
            start_timestamp_ms=0,
            slot_state=self.RESERVED,
            movement_profile=movement_profile,
        )
        states.extend(inbound_states)
        inbound_end_time = states[-1]["timestamp_ms"] if inbound_states else 0
        approach_time = inbound_end_time + self.tick_ms * self.approach_ticks
        approach = self._arrival_state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.APPROACH,
            slot_state=self.RESERVED,
            timestamp_ms=approach_time,
            uv=tuple(slot["transition_gate_uv"]),
            direction=slot["facing"],
            movement_profile=movement_profile,
        )
        states.append(approach)

        seated_start_index = len(states)
        seated_start_time = approach_time
        slot_events.append(
            {
                "from_state": self.RESERVED,
                "to_state": self.OCCUPIED,
                "phase": self.SEATED_WORK,
                "state_index": seated_start_index,
                "timestamp_ms": seated_start_time + self.tick_ms,
            }
        )
        for index in range(work_ticks):
            elapsed = index * self.tick_ms
            work_payload = self._work_render_payload(
                character_id=character_id,
                slot=slot,
                subaction=subaction,
                elapsed_ms=elapsed,
                effect_id=effect_id,
                humanball_id=humanball_id,
                character_frame_count=len(work_action.frames),
                effect_frame_count=effect_count,
                humanball_frame_count=humanball_count,
            )
            states.append(
                self._state(
                    actor_id=actor_id,
                    character_id=character_id,
                    floor_id=floor_id,
                    slot=slot,
                    phase=self.SEATED_WORK,
                    slot_state=self.OCCUPIED,
                    action="work",
                    direction=slot["facing"],
                    timestamp_ms=seated_start_time + (index + 1) * self.tick_ms,
                    ground_xy=None,
                    current_uv=None,
                    render_owner=self.SEATED_OWNER,
                    visible=True,
                    movement_profile=movement_profile,
                    frame_index=work_payload["character_frame_index"],
                    work_render=work_payload,
                    seated_elapsed_ms=elapsed,
                )
            )

        exit_time = seated_start_time + (work_ticks + 1) * self.tick_ms
        exit_index = len(states)
        slot_events.append(
            {
                "from_state": self.OCCUPIED,
                "to_state": self.RELEASING,
                "phase": self.EXIT_SEAT,
                "state_index": exit_index,
                "timestamp_ms": exit_time,
            }
        )
        exit_state = self._arrival_state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.EXIT_SEAT,
            slot_state=self.RELEASING,
            timestamp_ms=exit_time,
            uv=tuple(slot["transition_gate_uv"]),
            direction=slot["facing"],
            movement_profile=movement_profile,
        )
        states.append(exit_state)

        outbound_start_time = exit_time + self.tick_ms * self.exit_ticks
        outbound_start_index = len(states)
        slot_events.append(
            {
                "from_state": self.RELEASING,
                "to_state": self.FREE,
                "phase": self.WALKING_FROM_SEAT,
                "state_index": outbound_start_index,
                "timestamp_ms": outbound_start_time,
            }
        )
        outbound_states = self._path_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.WALKING_FROM_SEAT,
            path=outbound,
            start_timestamp_ms=exit_time,
            slot_state=self.FREE,
            movement_profile=movement_profile,
        )
        # The gate is already visible at exit_time. Outbound movement starts
        # after the one semantic exit boundary tick, so shift every sampled
        # outbound row by that boundary duration.
        for state in outbound_states:
            state["timestamp_ms"] += self.tick_ms * self.exit_ticks
        states.extend(outbound_states)
        outbound_end_time = states[-1]["timestamp_ms"] if outbound_states else outbound_start_time
        outbound_direction = (
            outbound_states[-1]["direction"] if outbound_states else slot["facing"]
        )
        arrival = self._arrival_state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            slot=slot,
            phase=self.WALKING_FROM_SEAT,
            slot_state=self.FREE,
            timestamp_ms=outbound_end_time + self.tick_ms,
            uv=exit_goal,
            direction=outbound_direction,
            movement_profile=movement_profile,
        )
        states.append(arrival)

        # Ensure the emitted state stream is monotonic and the two visual
        # channels never claim ownership on the same tick.
        for previous, current in zip(states, states[1:]):
            if current["timestamp_ms"] <= previous["timestamp_ms"]:
                raise WorkSeatLifecycleError("Lifecycle timestamps must be strictly increasing")
            if current["walking_visible"] and current["seated_visible"]:
                raise WorkSeatLifecycleError("Walking and seated render channels overlap")

        slot_events[-1]["state_index"] = outbound_start_index
        return {
            "schema": "gds.work_seat_actor_cycle.v1",
            "actor_id": actor_id,
            "character_id": character_id,
            "floor_id": floor_id,
            "workstation_id": workstation_id,
            "inputs": {
                "character_query": character_id,
                "character_id": character_id,
                "floor_id": floor_id,
                "workstation_id": workstation_id,
                "start_uv": list(start),
                "exit_goal_uv": list(exit_goal),
                "work_ticks": work_ticks,
                "subaction": subaction,
                "effect_id": effect_id,
                "humanball_id": humanball_id,
            },
            "slot": slot,
            "slots": [dict(slot)],
            "movement_profile": movement_profile,
            "timing": {
                "playback_tick_ms": self.tick_ms,
                "approach_ticks": self.approach_ticks,
                "exit_ticks": self.exit_ticks,
                "work_ticks": work_ticks,
                "work_duration_ms": work_ticks * self.tick_ms,
                "work_character_frame_ms": self.character_frame_ms,
                "work_effect_frame_ms": self.effect_frame_ms,
                "work_humanball_frame_ms": self.humanball_frame_ms,
            },
            "inbound_path_cells_uv": [list(cell) for cell in inbound],
            "outbound_path_cells_uv": [list(cell) for cell in outbound],
            "phase_ranges": self._phase_ranges(states),
            "phase_counts": self._phase_counts(states),
            "slot_transition_history": [
                self.FREE,
                self.RESERVED,
                self.OCCUPIED,
                self.RELEASING,
                self.FREE,
            ],
            "slot_transition_events": slot_events,
            "states": states,
            "final_state": states[-1],
            "final_slot_state": self.FREE,
            "completed": True,
        }

    def render_seated_state(
        self,
        *,
        floor_id: str,
        workstation_id: str,
        character_query: int | str,
        subaction: str = "normal_work",
        effect_id: str | None = None,
        humanball_id: str | None = None,
        character_frame_index: int = 0,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
    ):
        """Render one seated state while keeping channel indices independent."""
        character_id = self._character_id(character_query)
        slot = self.resolve_interaction_slot(floor_id, workstation_id)
        if effect_frame_index is None:
            effect_frame_index = character_frame_index
        if humanball_frame_index is None:
            humanball_frame_index = character_frame_index
        assignment = {
            "workstation_id": workstation_id,
            "character_id": character_id,
            "subaction": self._resolve_subaction(subaction),
        }
        if effect_id is not None:
            assignment["effect_id"] = effect_id
        if humanball_id is not None:
            assignment["humanball_id"] = humanball_id
        if effect_id is None and humanball_id is None:
            return self.work_seats.render_floor_with_work(
                floor_id,
                [assignment],
                frame_index=int(character_frame_index),
                character_frame_index=int(character_frame_index),
            )
        return self.work_seats.render_floor_with_work_effects(
            floor_id,
            [assignment],
            frame_index=int(character_frame_index),
            character_frame_index=int(character_frame_index),
            effect_frame_index=int(effect_frame_index),
            humanball_frame_index=int(humanball_frame_index),
        )
