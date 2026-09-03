from __future__ import annotations

"""Runtime-derived conversation positions.

This module deliberately owns only navigation-space decisions.  It does not
author a second workstation registry, mutate employee metadata, or use the
visual WorkSeat sprite offset as a gameplay coordinate.
"""

import json
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from RUNTIME.work_seat_core import WorkSeatCore, WorkSeatError
from RUNTIME.work_seat_lifecycle import WorkSeatLifecycle, WorkSeatLifecycleError
from WORLD.RUNTIME.layout_core import LayoutCore
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore
from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore


class ConversationSpotError(ValueError):
    pass


class ConversationSpotCore:
    """Resolve deterministic, walkable talk spots from the current world.

    A spot is a normal navigation cell.  A seated WorkSeat has no navigation
    position, therefore a seated host is represented by a turn-side ray and a
    visitor endpoint; the transition gate is used only as the departure and
    return anchor by the behavior reducer.
    """

    AXIS_DELTAS = {
        "U": (1, 0),
        "V": (0, 1),
    }
    AXIS_DIRECTION = {
        (1, 0): "SE",
        (-1, 0): "NW",
        (0, 1): "SW",
        (0, -1): "NE",
    }
    OPPOSITE = {"SE": "NW", "NW": "SE", "SW": "NE", "NE": "SW"}

    def __init__(
        self,
        root: str | Path,
        *,
        layout: LayoutCore | None = None,
        navigation: NavigationOccupancyCore | None = None,
        work_seats: WorkSeatCore | None = None,
        work_seat_lifecycle: WorkSeatLifecycle | None = None,
        walking_depth: WalkingDepthCore | None = None,
    ):
        self.root = Path(root).resolve()
        self.layout = layout or LayoutCore(self.root / "WORLD")
        self.navigation = navigation or NavigationOccupancyCore(self.root / "WORLD")
        self.work_seats = work_seats or WorkSeatCore(self.root)
        self.work_seat_lifecycle = work_seat_lifecycle or WorkSeatLifecycle(
            self.root,
            navigation=self.navigation,
            work_seats=self.work_seats,
        )
        self.walking_depth = walking_depth or WalkingDepthCore(
            self.root / "WORLD",
            layout=self.layout,
            occupancy=self.navigation,
        )
        contract_path = self.root / "CONTRACTS" / "conversation_behavior.json"
        self.contract = json.loads(contract_path.read_text(encoding="utf-8"))
        standing = self.contract["coordinate_contract"]["standing_pair"]
        self.standing_pair_preferred_axis = str(standing["preferred_axis"]).upper()
        self.standing_pair_endpoint_order = str(standing["endpoint_order"])
        self.standing_pair_endpoint_facing_order = tuple(
            str(value).upper() for value in standing["endpoint_facing_order"]
        )
        self.default_gap_cells = int(standing["talk_gap_cells"])
        self.minimum_gap_cells = int(standing["minimum_gap_cells"])
        self.open_ring_radius_cells = int(standing["open_ring_radius_cells"])
        self.portal_margin_cells = int(standing["portal_margin_cells"])
        self._region_cache: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _uv(value: Iterable[int] | tuple[int, int]) -> tuple[int, int]:
        values = list(value)
        if len(values) != 2:
            raise ConversationSpotError(f"Expected a UV pair, got {value!r}")
        return int(values[0]), int(values[1])

    @staticmethod
    def _cell_list(cells: Iterable[tuple[int, int]]) -> list[list[int]]:
        return [list(cell) for cell in sorted(set(cells), key=lambda c: (c[1], c[0]))]

    def _compiled(self, floor_id: str) -> dict[str, Any]:
        try:
            return self.navigation.resolve_floor(floor_id)
        except (KeyError, ValueError) as exc:
            raise ConversationSpotError(f"Unknown floor: {floor_id!r}") from exc

    def _reachable(self, compiled: dict[str, Any]) -> set[tuple[int, int]]:
        walkable = {tuple(cell) for cell in compiled["walkable_cells_uv"]}
        starts = {tuple(cell) for cell in compiled["portal_inside_cells_uv"]} & walkable
        seen = set(starts)
        queue = deque(sorted(starts, key=lambda c: (c[1], c[0])))
        while queue:
            u, v = queue.popleft()
            for du, dv in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nxt = (u + du, v + dv)
                if nxt in walkable and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def _context(self, floor_id: str) -> dict[str, Any]:
        compiled = self._compiled(floor_id)
        reachable = self._reachable(compiled)
        protected = {
            tuple(row["cell_uv"])
            for row in compiled.get("protected_ingress", [])
            if row.get("cell_uv") is not None
        }
        portal = {tuple(cell) for cell in compiled.get("portal_inside_cells_uv", [])}
        clearance = {
            tuple(cell)
            for cell in compiled.get("clearance_cells_uv", [])
        }
        relief = {
            tuple(cell)
            for row in compiled.get("chair_pair_relief_records", [])
            for cell in row.get("restored_cells_uv", [])
        }
        return {
            "compiled": compiled,
            "walkable": {tuple(cell) for cell in compiled["walkable_cells_uv"]},
            "reachable": reachable,
            "protected": protected,
            "portal": portal,
            "clearance": clearance,
            "relief": relief,
        }

    def _ring(self, center: tuple[int, int], radius: int | None = None) -> set[tuple[int, int]]:
        radius = self.open_ring_radius_cells if radius is None else int(radius)
        return {
            (center[0] + du, center[1] + dv)
            for du in range(-radius, radius + 1)
            for dv in range(-radius, radius + 1)
            if abs(du) + abs(dv) <= radius
        }

    def _portal_distance(self, cell: tuple[int, int], portal: set[tuple[int, int]]) -> int:
        if not portal:
            return 999999
        return min(abs(cell[0] - p[0]) + abs(cell[1] - p[1]) for p in portal)

    def _station_regions(self, floor_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Return clearance islands used only for between-desk rejection.

        The global clearance union is already removed from walkability.  The
        named islands let the conversation resolver reject the rare restored
        chair-pair corridor without changing NavigationOccupancyCore.
        """
        cached = self._region_cache.get(floor_id)
        if cached is not None:
            return cached
        compiled = context["compiled"]
        by_source: dict[str, set[tuple[int, int]]] = {}
        for row in compiled.get("clearance_records", []):
            source = row.get("source_placement_id")
            if source:
                by_source[source] = {tuple(cell) for cell in row.get("occupied_cells_uv", [])}
        regions: list[dict[str, Any]] = []
        for workstation_id, group in sorted(self.layout.floor_layout(floor_id).get("workstation_groups", {}).items()):
            source_ids = [
                group.get("component_slots", {}).get("desk"),
                group.get("component_slots", {}).get("chair_main"),
            ]
            cells = set().union(*(by_source.get(source, set()) for source in source_ids if source))
            if not cells:
                continue
            regions.append({
                "workstation_id": workstation_id,
                "cells": cells,
                "u_min": min(cell[0] for cell in cells),
                "u_max": max(cell[0] for cell in cells),
                "v_min": min(cell[1] for cell in cells),
                "v_max": max(cell[1] for cell in cells),
                "center": (
                    (min(cell[0] for cell in cells) + max(cell[0] for cell in cells)) / 2,
                    (min(cell[1] for cell in cells) + max(cell[1] for cell in cells)) / 2,
                ),
            })
        self._region_cache[floor_id] = regions
        return regions

    def _between_furniture(
        self,
        floor_id: str,
        endpoints: Iterable[tuple[int, int]],
        axis: str,
        context: dict[str, Any],
    ) -> bool:
        points = list(endpoints)
        if not points:
            return True
        point_set = set(points)
        if point_set & context["relief"]:
            return True
        regions = self._station_regions(floor_id, context)
        u_min = min(p[0] for p in points)
        u_max = max(p[0] for p in points)
        v_min = min(p[1] for p in points)
        v_max = max(p[1] for p in points)
        for first in regions:
            for second in regions:
                if first["workstation_id"] >= second["workstation_id"]:
                    continue
                if axis == "V":
                    aligned = (
                        first["u_min"] <= u_max + 1
                        and first["u_max"] >= u_min - 1
                        and second["u_min"] <= u_max + 1
                        and second["u_max"] >= u_min - 1
                        and (
                            (first["v_max"] < v_min and second["v_min"] > v_max)
                            or (second["v_max"] < v_min and first["v_min"] > v_max)
                        )
                    )
                else:
                    aligned = (
                        first["v_min"] <= v_max + 1
                        and first["v_max"] >= v_min - 1
                        and second["v_min"] <= v_max + 1
                        and second["v_max"] >= v_min - 1
                        and (
                            (first["u_max"] < u_min and second["u_min"] > u_max)
                            or (second["u_max"] < u_min and first["u_min"] > u_max)
                        )
                    )
                if aligned:
                    return True
        return False

    def _open_endpoint(
        self,
        floor_id: str,
        cell: tuple[int, int],
        context: dict[str, Any],
        *,
        blocked: set[tuple[int, int]],
        require_portal_margin: bool = True,
        ring_radius: int | None = None,
        reject_protected_ring: bool = True,
    ) -> bool:
        if cell not in context["reachable"] or cell in blocked:
            return False
        if cell in context["protected"] or cell in context["clearance"]:
            return False
        ring = self._ring(cell, ring_radius)
        if ring & blocked:
            return False
        if not ring <= context["reachable"]:
            return False
        if reject_protected_ring and ring & context["protected"]:
            return False
        if require_portal_margin and self._portal_distance(cell, context["portal"]) < self.portal_margin_cells:
            return False
        return True

    @staticmethod
    def _axis_delta(axis: str, sign: str = "+") -> tuple[int, int]:
        axis = str(axis).strip().upper()
        if axis not in {"U", "V"}:
            raise ConversationSpotError(f"Unsupported conversation axis: {axis!r}")
        du, dv = ConversationSpotCore.AXIS_DELTAS[axis]
        return (du, dv) if sign == "+" else (-du, -dv)

    @classmethod
    def _facing_for_delta(cls, delta: tuple[int, int]) -> str:
        try:
            return cls.AXIS_DIRECTION[delta]
        except KeyError as exc:
            raise ConversationSpotError(f"Unsupported axis delta: {delta!r}") from exc

    def _score_pair(
        self,
        pair: tuple[tuple[int, int], tuple[int, int]],
        origin_uvs: list[tuple[int, int]],
    ) -> tuple[Any, ...]:
        if not origin_uvs:
            center_u = sum(cell[0] for cell in pair) / 2
            center_v = sum(cell[1] for cell in pair) / 2
            return (abs(center_u - 250), abs(center_v - 95), pair[0][1], pair[0][0], pair[1][1], pair[1][0])
        costs = [
            min(
                abs(origin[0] - endpoint[0]) + abs(origin[1] - endpoint[1])
                for endpoint in pair
            )
            for origin in origin_uvs
        ]
        return (sum(costs), max(costs), pair[0][1], pair[0][0], pair[1][1], pair[1][0])

    def resolve_standing_pair(
        self,
        floor_id: str,
        *,
        preferred_axis: str | None = None,
        gap_cells: int | None = None,
        blocked_cells: Iterable[Iterable[int]] | None = None,
        reserved_cells: Iterable[Iterable[int]] | None = None,
        origin_uvs: Iterable[Iterable[int]] | None = None,
    ) -> dict[str, Any]:
        context = self._context(floor_id)
        gap = self.default_gap_cells if gap_cells is None else int(gap_cells)
        if gap < self.minimum_gap_cells:
            raise ConversationSpotError(
                f"standing_pair gap_cells must be >= {self.minimum_gap_cells}: {gap}"
            )
        preferred = (
            self.standing_pair_preferred_axis
            if preferred_axis is None
            else str(preferred_axis).strip().upper()
        )
        if preferred not in {"U", "V"}:
            raise ConversationSpotError(f"Unsupported preferred axis: {preferred_axis!r}")
        axes = [preferred, "U" if preferred == "V" else "V"]
        blocked = {self._uv(cell) for cell in (blocked_cells or ())}
        blocked.update(self._uv(cell) for cell in (reserved_cells or ()))
        origins = [self._uv(cell) for cell in (origin_uvs or ())]
        candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        reachable = context["reachable"]
        for axis_rank, axis in enumerate(axes):
            du, dv = self._axis_delta(axis, "+")
            for first in sorted(reachable, key=lambda cell: (cell[1], cell[0])):
                second = (first[0] + du * gap, first[1] + dv * gap)
                if second not in reachable:
                    continue
                segment = [
                    (first[0] + du * offset, first[1] + dv * offset)
                    for offset in range(gap + 1)
                ]
                if any(cell in blocked for cell in segment):
                    continue
                if any(cell not in reachable for cell in segment):
                    continue
                if not self._open_endpoint(floor_id, first, context, blocked=blocked):
                    continue
                if not self._open_endpoint(floor_id, second, context, blocked=blocked):
                    continue
                ring = self._ring(first) | self._ring(second)
                if ring & context["relief"]:
                    continue
                if self._between_furniture(floor_id, segment, axis, context):
                    continue
                pair = (first, second)
                if axis == self.standing_pair_preferred_axis:
                    first_facing, second_facing = self.standing_pair_endpoint_facing_order
                else:
                    first_facing = self._facing_for_delta((du, dv))
                    second_facing = self.OPPOSITE[first_facing]
                row = {
                    "ready": True,
                    "mode": "standing_pair",
                    "floor_id": floor_id,
                    "slot_id": f"talk:standing_pair:{floor_id}:{axis}:{first[0]}_{first[1]}__{second[0]}_{second[1]}",
                    "capacity": 2,
                    "axis": axis,
                    "axis_delta_uv": [du, dv],
                    "gap_cells": gap,
                    "endpoint_uv": [list(first), list(second)],
                    "segment_cells_uv": self._cell_list(segment),
                    "ring_cells_uv": self._cell_list(ring),
                    "endpoint_facings": [first_facing, second_facing],
                    "endpoint_inverse": self.OPPOSITE[first_facing] == second_facing,
                    "constraints": {
                        "preferred_axis": preferred,
                        "axis_rank": axis_rank,
                        "open_ring_radius_cells": self.open_ring_radius_cells,
                        "portal_margin_cells": self.portal_margin_cells,
                        "between_desks_rejected": True,
                        "dynamic_blocked_cells": self._cell_list(blocked),
                    },
                }
                score = (axis_rank, *self._score_pair(pair, origins))
                candidates.append((score, row))
        if not candidates:
            return {
                "ready": False,
                "mode": "standing_pair",
                "floor_id": floor_id,
                "reason": "no_open_pair_slot",
                "gap_cells": gap,
                "preferred_axis": preferred,
                "constraints": {
                    "minimum_gap_cells": self.minimum_gap_cells,
                    "open_ring_radius_cells": self.open_ring_radius_cells,
                    "portal_margin_cells": self.portal_margin_cells,
                },
            }
        candidates.sort(key=lambda item: item[0])
        selected = deepcopy(candidates[0][1])
        selected["selection_score"] = list(candidates[0][0])
        selected["candidate_count"] = len(candidates)
        return selected

    def _chair_center(self, floor_id: str, workstation_id: str, context: dict[str, Any]) -> tuple[int, int]:
        try:
            seat = self.work_seats.resolve_workstation_seat(floor_id, workstation_id)
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise ConversationSpotError(str(exc)) from exc
        by_id = {row["placement_id"]: row for row in context["compiled"]["instances"]}
        try:
            cells = [tuple(cell) for cell in by_id[seat["chair_placement_id"]]["occupied_cells_uv"]]
        except KeyError as exc:
            raise ConversationSpotError(
                f"{floor_id}.{workstation_id}: chair navigation footprint is missing"
            ) from exc
        return (
            int(round(sum(cell[0] for cell in cells) / len(cells))),
            int(round(sum(cell[1] for cell in cells) / len(cells))),
        )

    def resolve_seated_host_side(
        self,
        floor_id: str,
        workstation_id: str,
        *,
        blocked_cells: Iterable[Iterable[int]] | None = None,
        reserved_cells: Iterable[Iterable[int]] | None = None,
    ) -> dict[str, Any]:
        context = self._context(floor_id)
        blocked = {self._uv(cell) for cell in (blocked_cells or ())}
        blocked.update(self._uv(cell) for cell in (reserved_cells or ()))
        try:
            seat = self.work_seats.resolve_workstation_seat(floor_id, workstation_id)
            mapping = self.work_seats.resolve_turn_side_mapping(seat["direction"])
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise ConversationSpotError(str(exc)) from exc
        center = self._chair_center(floor_id, workstation_id, context)
        sides: list[dict[str, Any]] = []
        for subaction in sorted(key for key in mapping if key.startswith("turn_side_")):
            entry = mapping[subaction]
            delta = tuple(entry["axis_delta_uv"])
            candidate = None
            for distance in range(1, 40):
                probe = (center[0] + delta[0] * distance, center[1] + delta[1] * distance)
                if probe in context["clearance"] or probe not in context["reachable"]:
                    continue
                # A seated host only needs one visitor cell.  Requiring the
                # pair-oriented two-cell ring here would incorrectly reject
                # valid side lanes beside a wall; the ray/collision checks
                # below still reject the inner between-desk side.
                if self._open_endpoint(
                    floor_id,
                    probe,
                    context,
                    blocked=blocked,
                    require_portal_margin=False,
                    ring_radius=0,
                ):
                    candidate = probe
                    break
            reason = None
            ready = candidate is not None
            if candidate is not None:
                ray = [
                    (center[0] + delta[0] * offset, center[1] + delta[1] * offset)
                    for offset in range(1, max(2, abs(candidate[0] - center[0]) + abs(candidate[1] - center[1])) + 1)
                ]
                if any(cell in blocked for cell in ray) or self._between_furniture(floor_id, ray, entry["axis"], context):
                    ready = False
                    reason = "between_desks_or_reserved"
            if not ready and reason is None:
                reason = "no_open_outward_side"
            sides.append({
                "side": subaction,
                "ready": ready,
                "axis": entry["axis"],
                "sign": entry["sign"],
                "axis_direction": entry["axis_direction"],
                "axis_delta_uv": list(delta),
                "target_idle_direction": entry["target_idle_direction"],
                "candidate_uv": list(candidate) if candidate is not None and ready else None,
                "reason": reason,
            })
        ready_sides = [row for row in sides if row["ready"]]
        if not ready_sides:
            return {
                "ready": False,
                "mode": "seated_host",
                "floor_id": floor_id,
                "workstation_id": workstation_id,
                "host_work_direction": seat["direction"],
                "chair_center_uv": list(center),
                "sides": sides,
                "reason": "no_open_outward_side",
            }
        # Prefer more free cells in the side's straight continuation.  The
        # distance is capped for determinism and does not reserve those cells.
        def side_score(row: dict[str, Any]) -> tuple[int, int, str]:
            delta = tuple(row["axis_delta_uv"])
            endpoint = tuple(row["candidate_uv"])
            free = 0
            for extra in range(0, 5):
                probe = (endpoint[0] + delta[0] * extra, endpoint[1] + delta[1] * extra)
                if probe in context["reachable"] and probe not in blocked:
                    free += 1
            return (free, -int(row["candidate_uv"][1]), row["side"])
        selected = max(ready_sides, key=side_score)
        return {
            "ready": True,
            "mode": "seated_host",
            "floor_id": floor_id,
            "workstation_id": workstation_id,
            "slot_id": f"talk:seated_host:{floor_id}:{workstation_id}",
            "capacity": 1,
            "host_work_direction": seat["direction"],
            "chair_center_uv": list(center),
            "selected_side": deepcopy(selected),
            "sides": sides,
            "visitor_idle_direction": self.OPPOSITE[selected["target_idle_direction"]],
            "constraints": {
                "outward_only": True,
                "inner_between_desks_rejected": True,
                "dynamic_blocked_cells": self._cell_list(blocked),
            },
        }

    def _ceo_front_direction(self, work_direction: str) -> tuple[str, tuple[int, int]]:
        direction = str(work_direction).upper()
        mapping = {
            "SE": ("U", (1, 0)),
            "NW": ("U", (-1, 0)),
            "SW": ("V", (0, 1)),
            "NE": ("V", (0, -1)),
        }
        try:
            return mapping[direction]
        except KeyError as exc:
            raise ConversationSpotError(f"Unsupported CEO work direction: {work_direction!r}") from exc

    def resolve_ceo_front(
        self,
        floor_id: str,
        *,
        blocked_cells: Iterable[Iterable[int]] | None = None,
        reserved_cells: Iterable[Iterable[int]] | None = None,
    ) -> dict[str, Any]:
        context = self._context(floor_id)
        blocked = {self._uv(cell) for cell in (blocked_cells or ())}
        blocked.update(self._uv(cell) for cell in (reserved_cells or ()))
        try:
            seat = self.work_seats.resolve_workstation_seat(floor_id, "ceo")
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise ConversationSpotError(str(exc)) from exc
        center = self._chair_center(floor_id, "ceo", context)
        axis, front_delta = self._ceo_front_direction(seat["direction"])
        occluders = {row["placement_id"]: row for row in self.walking_depth.resolve_occluders(floor_id)}
        desk = occluders.get("ceo_desk_cell2")
        if not desk or desk.get("depth_front_edge_world_px") is None:
            return {
                "ready": False,
                "mode": "ceo_front",
                "floor_id": floor_id,
                "reason": "no_ceo_front_slot",
            }
        corners = desk["depth_footprint_corners_world_px"]
        min_x = min(point[0] for point in corners)
        max_x = max(point[0] for point in corners)
        scalar_anchor = float(desk["depth_anchor_y_px"])
        front_edge = desk["depth_front_edge_world_px"]
        candidates: list[tuple[tuple[Any, ...], tuple[int, int], float]] = []
        for cell in sorted(context["reachable"], key=lambda c: (c[1], c[0])):
            if not self._open_endpoint(
                floor_id,
                cell,
                context,
                blocked=blocked,
                ring_radius=1,
                reject_protected_ring=False,
            ):
                continue
            x, y = self._uv_to_pixel(cell)
            if not (min_x <= x <= max_x):
                continue
            local_front_y = self.walking_depth._front_edge_y_at_x(front_edge, x)
            front_margin = float(y) - float(local_front_y)
            if not (4.0 <= front_margin <= 24.0 and y < scalar_anchor):
                continue
            # The depth envelope is the CEO's authored red/front lane.  It is
            # intentionally allowed to sit beside the CEO furniture even when
            # another desk island is on the far side; the generic standing
            # between-desks predicate would incorrectly erase this lane.
            # The exact ingress gate is a WorkSeat resource, not a talk target.
            if cell in context["protected"]:
                continue
            distance = abs(cell[0] - center[0]) + abs(cell[1] - center[1])
            axis_distance = (cell[0] - center[0]) * front_delta[0] + (cell[1] - center[1]) * front_delta[1]
            candidates.append(((distance, abs(axis_distance), cell[1], cell[0]), cell, front_margin))
        if not candidates:
            return {
                "ready": False,
                "mode": "ceo_front",
                "floor_id": floor_id,
                "workstation_id": "ceo",
                "host_work_direction": seat["direction"],
                "reason": "no_ceo_front_slot",
            }
        candidates.sort(key=lambda row: row[0])
        _score, endpoint, front_margin = candidates[0]
        visitor_facing = self.OPPOSITE[seat["direction"]]
        return {
            "ready": True,
            "mode": "ceo_front",
            "floor_id": floor_id,
            "workstation_id": "ceo",
            "slot_id": f"talk:ceo_front:{floor_id}:ceo",
            "capacity": 1,
            "axis": axis,
            "axis_delta_uv": list(front_delta),
            "endpoint_uv": [list(endpoint)],
            "endpoint_facing": visitor_facing,
            "endpoint_inverse": self.OPPOSITE[visitor_facing] == seat["direction"],
            "host_work_direction": seat["direction"],
            "host_render": "work_seat.normal_work",
            "host_movement": "none",
            "front_margin_px": round(front_margin, 4),
            "candidate_count": len(candidates),
            "constraints": {
                "depth_profile_id": desk.get("depth_profile_id"),
                "front_edge_world_px": deepcopy(front_edge),
                "protected_ingress_rejected": True,
                "dynamic_blocked_cells": self._cell_list(blocked),
            },
        }

    def _uv_to_pixel(self, cell: tuple[int, int]) -> tuple[int, int]:
        # Navigation's grid mapping is shared with CharacterMovementCore; use
        # the same affine transform locally to keep this resolver independent
        # from a renderer/core facade.
        grid = self.navigation.navigation.grid
        ox, oy = grid["grid_origin_px"]
        ux, uy = grid["u_step_px"]
        vx, vy = grid["v_step_px"]
        u, v = cell
        return (
            int(round(ox + (u + 0.5) * ux + (v + 0.5) * vx)),
            int(round(oy + (u + 0.5) * uy + (v + 0.5) * vy)),
        )

    def resolve_spot(self, mode: str, floor_id: str, **kwargs: Any) -> dict[str, Any]:
        key = str(mode).strip().casefold()
        if key == "standing_pair":
            return self.resolve_standing_pair(floor_id, **kwargs)
        if key == "seated_host":
            workstation_id = kwargs.pop("workstation_id", None)
            if not workstation_id:
                raise ConversationSpotError("seated_host requires workstation_id")
            return self.resolve_seated_host_side(floor_id, workstation_id, **kwargs)
        if key == "ceo_front":
            return self.resolve_ceo_front(floor_id, **kwargs)
        if key == "self_talk":
            return {
                "ready": True,
                "mode": "self_talk",
                "floor_id": floor_id,
                "capacity": 1,
                "reason": "no_movement_self_talk",
            }
        raise ConversationSpotError(f"Unsupported conversation mode: {mode!r}")
