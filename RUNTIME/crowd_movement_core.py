from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


Cell = tuple[int, int]
Edge = tuple[Cell, Cell]
Point = tuple[float, float]
MotionSegment = tuple[Point, Point]


class CrowdMovementReservationError(ValueError):
    """Raised when a deterministic crowd reservation cannot be built."""


class DynamicActorReservationCore:
    """Coordinate actors on a shared tick with optional static A* detours.

    Static navigation remains owned by :class:`PathfindingCore`.  Production
    playback uses :meth:`schedule_trajectories`: it compares synchronized
    closest approach of ground-anchor heads and applies only an invisible
    pre-spawn offset when a detour cannot resolve a conflict.  Historical path
    trails are not reserved, so actors do not stop in the middle of a route.
    The older :meth:`schedule` cell/edge reservation API is retained for tools
    that still need explicit ``crowd_wait`` states.
    """

    DEFAULT_RESERVATION_RADIUS_CELLS = 1
    # Two screen pixels is approximately one fine-grid step on the shortest
    # isometric axis.  It removes sub-pixel anchor grazing while keeping the
    # portal queue bounded; callers can opt into a larger visual separation
    # after checking the floor's corridor widths.
    DEFAULT_GROUND_CLEARANCE_PX = 2.0
    DEFAULT_MAX_WAIT_TICKS = 12
    DEFAULT_MAX_START_DELAY_TICKS = 240
    # Trajectory planning may search farther than the legacy reservation
    # queue.  This is still an invisible launch offset, never an in-floor wait.
    DEFAULT_MAX_PRE_SPAWN_DELAY_TICKS = 480

    def __init__(
        self,
        *,
        reservation_radius_cells: int = DEFAULT_RESERVATION_RADIUS_CELLS,
        ground_clearance_px: float = DEFAULT_GROUND_CLEARANCE_PX,
        max_wait_ticks: int = DEFAULT_MAX_WAIT_TICKS,
        max_start_delay_ticks: int = DEFAULT_MAX_START_DELAY_TICKS,
        max_pre_spawn_delay_ticks: int = DEFAULT_MAX_PRE_SPAWN_DELAY_TICKS,
    ):
        self.reservation_radius_cells = self._non_negative(
            'reservation_radius_cells', reservation_radius_cells
        )
        self.ground_clearance_px = self._non_negative_float(
            'ground_clearance_px', ground_clearance_px
        )
        self.max_wait_ticks = self._positive('max_wait_ticks', max_wait_ticks)
        self.max_start_delay_ticks = self._positive(
            'max_start_delay_ticks', max_start_delay_ticks
        )
        self.max_pre_spawn_delay_ticks = self._positive(
            'max_pre_spawn_delay_ticks', max_pre_spawn_delay_ticks
        )

    @staticmethod
    def _non_negative(name: str, value: int) -> int:
        value = int(value)
        if value < 0:
            raise CrowdMovementReservationError(f'{name} must be >= 0')
        return value

    @staticmethod
    def _positive(name: str, value: int) -> int:
        value = int(value)
        if value <= 0:
            raise CrowdMovementReservationError(f'{name} must be >= 1')
        return value

    @staticmethod
    def _non_negative_float(name: str, value: float) -> float:
        value = float(value)
        if value < 0.0:
            raise CrowdMovementReservationError(f'{name} must be >= 0')
        return value

    @staticmethod
    def _cell(value: Iterable[int] | Cell) -> Cell:
        value = tuple(value)
        if len(value) != 2:
            raise CrowdMovementReservationError(f'Expected a UV cell pair, got {value!r}')
        return int(value[0]), int(value[1])

    @classmethod
    def _expand_cells(cls, cells: Iterable[Cell], radius: int) -> set[Cell]:
        radius = int(radius)
        expanded: set[Cell] = set()
        for u, v in cells:
            for du in range(-radius, radius + 1):
                for dv in range(-radius, radius + 1):
                    if abs(du) + abs(dv) <= radius:
                        expanded.add((u + du, v + dv))
        return expanded

    @staticmethod
    def _visible(state: Mapping[str, Any]) -> bool:
        if 'visible' in state:
            return bool(state['visible'])
        if 'alpha' in state:
            return float(state['alpha']) > 0.0
        return state.get('phase') not in {'unspawned', 'despawned'}

    @classmethod
    def _state_cells(
        cls,
        state: Mapping[str, Any],
        *,
        include_transition: bool = True,
        radius: int = 0,
    ) -> set[Cell]:
        if not cls._visible(state):
            return set()
        raw: list[Cell] = []
        current = state.get('current_uv')
        if current is not None:
            raw.append(cls._cell(current))
        if include_transition:
            for key in ('from_uv', 'to_uv'):
                value = state.get(key)
                if value is not None:
                    raw.append(cls._cell(value))
        elif not raw:
            for key in ('to_uv', 'from_uv'):
                value = state.get(key)
                if value is not None:
                    raw.append(cls._cell(value))
                    break
        return cls._expand_cells(raw, radius)

    @classmethod
    def _state_edge(cls, state: Mapping[str, Any]) -> Edge | None:
        if not cls._visible(state):
            return None
        start = state.get('from_uv')
        end = state.get('to_uv')
        if start is None or end is None:
            return None
        a, b = cls._cell(start), cls._cell(end)
        return None if a == b else (a, b)

    @staticmethod
    def _ground_xy(state: Mapping[str, Any] | None) -> Point | None:
        if state is None or not DynamicActorReservationCore._visible(state):
            return None
        value = state.get('ground_xy')
        if value is None:
            return None
        value = tuple(value)
        if len(value) != 2:
            raise CrowdMovementReservationError(
                f'Expected ground_xy pair, got {value!r}'
            )
        return float(value[0]), float(value[1])

    @classmethod
    def _motion_segment(
        cls,
        state: Mapping[str, Any],
        previous_state: Mapping[str, Any] | None = None,
    ) -> MotionSegment | None:
        """Return the actor's swept ground-anchor segment for one tick.

        State samples are emitted at the end of each playback tick.  Comparing
        only their final points misses a head-on pass that happens between two
        samples, so reservations use the previous point as the segment start.
        """
        end = cls._ground_xy(state)
        if end is None:
            return None
        start = cls._ground_xy(previous_state)
        return (start or end), end

    @staticmethod
    def _point_segment_distance_sq(point: Point, start: Point, end: Point) -> float:
        px, py = point
        sx, sy = start
        ex, ey = end
        dx, dy = ex - sx, ey - sy
        length_sq = dx * dx + dy * dy
        if length_sq <= 1e-12:
            return (px - sx) ** 2 + (py - sy) ** 2
        t = ((px - sx) * dx + (py - sy) * dy) / length_sq
        t = max(0.0, min(1.0, t))
        qx, qy = sx + t * dx, sy + t * dy
        return (px - qx) ** 2 + (py - qy) ** 2

    @staticmethod
    def _orientation(a: Point, b: Point, c: Point) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    @classmethod
    def _segments_intersect(
        cls,
        first: MotionSegment,
        second: MotionSegment,
    ) -> bool:
        a, b = first
        c, d = second
        eps = 1e-9
        o1 = cls._orientation(a, b, c)
        o2 = cls._orientation(a, b, d)
        o3 = cls._orientation(c, d, a)
        o4 = cls._orientation(c, d, b)

        def on_segment(p: Point, q: Point, r: Point) -> bool:
            return (
                min(p[0], r[0]) - eps <= q[0] <= max(p[0], r[0]) + eps
                and min(p[1], r[1]) - eps <= q[1] <= max(p[1], r[1]) + eps
            )

        if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and (
            (o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)
        ):
            return True
        return (
            abs(o1) <= eps and on_segment(a, c, b)
            or abs(o2) <= eps and on_segment(a, d, b)
            or abs(o3) <= eps and on_segment(c, a, d)
            or abs(o4) <= eps and on_segment(c, b, d)
        )

    @classmethod
    def _segment_distance(cls, first: MotionSegment, second: MotionSegment) -> float:
        if cls._segments_intersect(first, second):
            return 0.0
        a, b = first
        c, d = second
        return math.sqrt(min(
            cls._point_segment_distance_sq(a, c, d),
            cls._point_segment_distance_sq(b, c, d),
            cls._point_segment_distance_sq(c, a, b),
            cls._point_segment_distance_sq(d, a, b),
        ))

    @staticmethod
    def _find_blocker(
        tick: int,
        actor_id: str,
        cells: set[Cell],
        edge: Edge | None,
        motion_segment: MotionSegment | None,
        occupied: Mapping[int, Mapping[Cell, str]],
        edges: Mapping[int, Mapping[Edge, str]],
        motions: Mapping[int, Mapping[str, MotionSegment]],
        ground_clearance_px: float,
    ) -> str | None:
        for cell in sorted(cells, key=lambda item: (item[1], item[0])):
            owner = occupied.get(tick, {}).get(cell)
            if owner is not None and owner != actor_id:
                return owner
        if edge is not None:
            reverse = (edge[1], edge[0])
            for other_edge, owner in edges.get(tick, {}).items():
                if owner != actor_id and other_edge == reverse:
                    return owner
        if motion_segment is not None:
            for owner, other_segment in sorted(motions.get(tick, {}).items()):
                if owner == actor_id:
                    continue
                if DynamicActorReservationCore._segment_distance(
                    motion_segment, other_segment
                ) <= max(ground_clearance_px, 1e-6):
                    return owner
        return None

    @staticmethod
    def _merge_reservations(
        first: Mapping[int, Mapping[Any, str]],
        second: Mapping[int, Mapping[Any, str]],
    ) -> dict[int, dict[Any, str]]:
        merged = {tick: dict(values) for tick, values in first.items()}
        for tick, values in second.items():
            merged.setdefault(tick, {}).update(values)
        return merged

    @staticmethod
    def _reserve(
        tick: int,
        actor_id: str,
        cells: set[Cell],
        edge: Edge | None,
        occupied: dict[int, dict[Cell, str]],
        edges: dict[int, dict[Edge, str]],
        motions: dict[int, dict[str, MotionSegment]],
        motion_segment: MotionSegment | None,
    ) -> None:
        tick_cells = occupied.setdefault(tick, {})
        for cell in cells:
            tick_cells[cell] = actor_id
        if edge is not None:
            edges.setdefault(tick, {})[edge] = actor_id
        if motion_segment is not None:
            motions.setdefault(tick, {})[actor_id] = motion_segment

    @classmethod
    def _wait_state(
        cls,
        last_safe: Mapping[str, Any],
        *,
        wait_ticks: int,
        blocked_by: str,
    ) -> dict[str, Any]:
        state = dict(last_safe)
        state['action'] = 'idle'
        state['phase'] = 'crowd_wait'
        state['wait_ticks'] = int(wait_ticks)
        state['blocked_by_actor_id'] = blocked_by
        state['collision_resolution'] = 'reserved_wait'
        state['idle_frame_index'] = int(wait_ticks)
        current = state.get('current_uv')
        if current is None:
            current = state.get('to_uv') or state.get('from_uv')
        if current is not None:
            current_cell = list(cls._cell(current))
            state['current_uv'] = current_cell
            state.pop('from_uv', None)
            state.pop('to_uv', None)
        state['progress_t'] = 1.0
        return state

    def _attempt_schedule(
        self,
        actor_id: str,
        states: list[dict[str, Any]],
        start_delay: int,
        occupied: Mapping[int, Mapping[Cell, str]],
        edges: Mapping[int, Mapping[Edge, str]],
        motions: Mapping[int, Mapping[str, MotionSegment]],
    ) -> dict[str, Any] | None:
        local_occupied: dict[int, dict[Cell, str]] = {}
        local_edges: dict[int, dict[Edge, str]] = {}
        local_motions: dict[int, dict[str, MotionSegment]] = {}
        scheduled: list[dict[str, Any]] = []
        blocked_events: list[dict[str, Any]] = []
        raw_index = 0
        safety_limit = max(
            len(states) * (self.max_wait_ticks + 32),
            self.max_start_delay_ticks + len(states) + 4,
            1024,
        )

        def rebuild_local_reservations() -> None:
            local_occupied.clear()
            local_edges.clear()
            local_motions.clear()
            for offset, existing in enumerate(scheduled):
                self._reserve(
                    int(start_delay) + offset,
                    actor_id,
                    self._state_cells(
                        existing,
                        radius=self.reservation_radius_cells,
                    ),
                    self._state_edge(existing),
                    local_occupied,
                    local_edges,
                    local_motions,
                    self._motion_segment(
                        existing,
                        scheduled[offset - 1] if offset > 0 else None,
                    ),
                )

        def find_wait_anchor(tick: int) -> int | None:
            """Find the latest prior state that can safely hold until tick."""
            occupied_view = self._merge_reservations(occupied, local_occupied)
            edges_view = self._merge_reservations(edges, local_edges)
            motions_view = self._merge_reservations(motions, local_motions)
            for anchor_index in range(len(scheduled) - 1, -1, -1):
                anchor = scheduled[anchor_index]
                anchor_cells = self._state_cells(
                    anchor,
                    include_transition=False,
                    radius=self.reservation_radius_cells,
                )
                if not anchor_cells:
                    continue
                safe = True
                anchor_segment = self._motion_segment(anchor, anchor)
                for hold_tick in range(int(start_delay) + anchor_index + 1, tick + 1):
                    if self._find_blocker(
                        hold_tick,
                        actor_id,
                        anchor_cells,
                        None,
                        anchor_segment,
                        occupied_view,
                        edges_view,
                        motions_view,
                        self.ground_clearance_px,
                    ) is not None:
                        safe = False
                        break
                if safe:
                    return anchor_index
            return None

        while raw_index < len(states):
            if len(scheduled) > safety_limit:
                return None
            candidate = dict(states[raw_index])
            candidate['actor_id'] = actor_id
            tick = int(start_delay) + len(scheduled)
            candidate_cells = self._state_cells(
                candidate,
                radius=self.reservation_radius_cells,
            )
            candidate_edge = self._state_edge(candidate)
            candidate_motion = self._motion_segment(
                candidate,
                scheduled[-1] if scheduled else None,
            )
            occupied_view = self._merge_reservations(occupied, local_occupied)
            edges_view = self._merge_reservations(edges, local_edges)
            motions_view = self._merge_reservations(motions, local_motions)
            blocker = self._find_blocker(
                tick,
                actor_id,
                candidate_cells,
                candidate_edge,
                candidate_motion,
                occupied_view,
                edges_view,
                motions_view,
                self.ground_clearance_px,
            )
            if blocker is not None:
                anchor_index = find_wait_anchor(tick)
                if anchor_index is None:
                    # The actor cannot hold at any previously planned cell at
                    # this time.  The caller can queue its complete route
                    # after the existing reservation horizon.
                    return None

                anchor = scheduled[anchor_index]
                prefix = scheduled[:anchor_index + 1]
                wait_count = len(scheduled) - anchor_index
                for offset in range(wait_count):
                    wait = self._wait_state(
                        anchor,
                        wait_ticks=offset + 1,
                        blocked_by=blocker,
                    )
                    wait['wait_blocked_candidate'] = raw_index
                    prefix.append(wait)
                scheduled = prefix
                rebuild_local_reservations()
                blocked_events.append({
                    'tick': tick,
                    'blocked_by_actor_id': blocker,
                    'candidate_state_index': raw_index,
                    'wait_ticks': wait_count,
                })
                continue

            scheduled.append(candidate)
            self._reserve(
                tick,
                actor_id,
                candidate_cells,
                    candidate_edge,
                    local_occupied,
                    local_edges,
                    local_motions,
                    candidate_motion,
                )
            raw_index += 1

        wait_rows = [state for state in scheduled if state.get('phase') == 'crowd_wait']
        max_wait_ticks = 0
        current_wait_ticks = 0
        for state in scheduled:
            if state.get('phase') == 'crowd_wait':
                current_wait_ticks += 1
                max_wait_ticks = max(max_wait_ticks, current_wait_ticks)
            else:
                current_wait_ticks = 0

        return {
            'states': scheduled,
            'start_delay': int(start_delay),
            'wait_ticks': len(wait_rows),
            'max_wait_ticks': int(max_wait_ticks),
            'blocked_events': blocked_events,
            'occupied': local_occupied,
            'edges': local_edges,
            'motions': local_motions,
        }

    # ------------------------------------------------------------------
    # Synchronized-head trajectory planner
    # ------------------------------------------------------------------
    # The original reservation scheduler above is kept for compatibility with
    # older callers that explicitly want a discrete ``crowd_wait`` schedule.
    # Production crowd playback uses the trajectory planner below.  It does
    # not reserve a whole trail or a geometric line segment.  At each shared
    # tick it compares the two moving heads at the same normalized time
    # (continuous closest approach of their two linear motions).  Therefore a
    # route may reuse another actor's trail, and two geometric lines may cross
    # safely when the actors reach the crossing at different times.

    @classmethod
    def _ground_xy_or_cell(cls, state: Mapping[str, Any]) -> Point | None:
        point = cls._ground_xy(state)
        if point is not None:
            return point
        if not cls._visible(state):
            return None
        for key in ('current_uv', 'to_uv', 'from_uv'):
            value = state.get(key)
            if value is not None:
                cell = cls._cell(value)
                return float(cell[0]), float(cell[1])
        return None

    @classmethod
    def _trajectory(
        cls,
        states: Iterable[Mapping[str, Any]],
        start_delay: int = 0,
    ) -> dict[str, Any]:
        """Convert sampled states into synchronized linear motion intervals.

        A state is the sample displayed at the end of one playback tick.  The
        optional ``previous_ground_xy`` field lets the first sample carry its
        real spawn-to-sample motion; older state producers remain supported by
        falling back to the previous visible sample or a stationary point.
        """
        segments: dict[int, MotionSegment] = {}
        points: dict[int, Point] = {}
        previous: Point | None = None
        for index, raw_state in enumerate(states):
            state = dict(raw_state)
            if not cls._visible(state):
                previous = None
                continue
            end = cls._ground_xy_or_cell(state)
            if end is None:
                previous = None
                continue
            explicit_previous = state.get('previous_ground_xy')
            if explicit_previous is not None:
                value = tuple(explicit_previous)
                if len(value) != 2:
                    raise CrowdMovementReservationError(
                        f'Expected previous_ground_xy pair, got {value!r}'
                    )
                begin = float(value[0]), float(value[1])
            else:
                begin = previous or end
            tick = int(start_delay) + index
            segments[tick] = (begin, end)
            points[tick] = end
            previous = end
        return {
            'start_delay': int(start_delay),
            'segments': segments,
            'points': points,
            'start_tick': min(segments) if segments else int(start_delay),
            'end_tick': max(segments) if segments else int(start_delay) - 1,
        }

    @staticmethod
    def _shift_trajectory(trajectory: Mapping[str, Any], delta: int) -> dict[str, Any]:
        delta = int(delta)
        segments = {
            int(tick) + delta: segment
            for tick, segment in trajectory.get('segments', {}).items()
        }
        points = {
            int(tick) + delta: point
            for tick, point in trajectory.get('points', {}).items()
        }
        return {
            'start_delay': int(trajectory.get('start_delay', 0)) + delta,
            'segments': segments,
            'points': points,
            'start_tick': (
                int(trajectory.get('start_tick', 0)) + delta
                if segments
                else int(trajectory.get('start_tick', 0)) + delta
            ),
            'end_tick': (
                int(trajectory.get('end_tick', -1)) + delta
                if segments
                else int(trajectory.get('end_tick', -1)) + delta
            ),
        }

    @staticmethod
    def _synchronized_distance(first: MotionSegment, second: MotionSegment) -> float:
        """Minimum distance between two heads at the same time in one tick."""
        (a0, a1), (b0, b1) = first, second
        r0x, r0y = a0[0] - b0[0], a0[1] - b0[1]
        rvx = (a1[0] - a0[0]) - (b1[0] - b0[0])
        rvy = (a1[1] - a0[1]) - (b1[1] - b0[1])
        velocity_sq = rvx * rvx + rvy * rvy
        if velocity_sq <= 1e-12:
            tau = 0.0
        else:
            tau = -(r0x * rvx + r0y * rvy) / velocity_sq
            tau = max(0.0, min(1.0, tau))
        dx = r0x + rvx * tau
        dy = r0y + rvy * tau
        return math.hypot(dx, dy)

    def _trajectory_conflicts(
        self,
        candidate: Mapping[str, Any],
        existing: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        candidate_segments = candidate.get('segments', {})
        existing_segments = existing.get('segments', {})
        if not candidate_segments or not existing_segments:
            return []
        threshold = max(
            self.ground_clearance_px,
            float(candidate.get('head_clearance_px', self.ground_clearance_px)),
            float(existing.get('head_clearance_px', self.ground_clearance_px)),
        )
        conflicts: list[dict[str, Any]] = []
        candidate_points = candidate.get('points', {})
        existing_points = existing.get('points', {})
        common_ticks = sorted(
            (set(candidate_segments) & set(existing_segments))
            | (set(candidate_points) & set(existing_points))
        )
        for tick in common_ticks:
            distances: list[float] = []
            if tick in candidate_segments and tick in existing_segments:
                distances.append(self._synchronized_distance(
                    candidate_segments[tick], existing_segments[tick]
                ))
            if tick in candidate_points and tick in existing_points:
                first = candidate_points[tick]
                second = existing_points[tick]
                distances.append(math.hypot(first[0] - second[0], first[1] - second[1]))
            distance = min(distances)
            if distance <= threshold + 1e-6:
                conflicts.append({
                    'tick': int(tick),
                    'distance_px': round(distance, 6),
                    'candidate_actor_id': candidate.get('actor_id'),
                    'blocked_by_actor_id': existing.get('actor_id'),
                })
        return conflicts

    @classmethod
    def _normalize_trajectory_specs(
        cls,
        actors: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        specs = [dict(item) for item in actors]
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, spec in enumerate(specs):
            actor_id = str(spec.get('actor_id', f'actor-{index}'))
            if actor_id in seen_ids:
                raise CrowdMovementReservationError(f'Duplicate actor_id: {actor_id}')
            seen_ids.add(actor_id)
            raw_states = spec.get('states')
            if raw_states is None:
                raise CrowdMovementReservationError(f'{actor_id}: states are required')

            def normalize_states(values: Iterable[Mapping[str, Any]], label: str) -> list[dict[str, Any]]:
                rows: list[dict[str, Any]] = []
                for state in values:
                    row = dict(state)
                    state_actor_id = row.get('actor_id')
                    if state_actor_id is not None and str(state_actor_id) != actor_id:
                        raise CrowdMovementReservationError(
                            f'{actor_id}: {label} actor_id does not match'
                        )
                    row['actor_id'] = actor_id
                    rows.append(row)
                return rows

            states = normalize_states(raw_states, 'state')
            options: list[list[dict[str, Any]]] = []
            for option_index, option in enumerate(spec.get('route_options', ())):
                option_states = normalize_states(option, f'route option {option_index}')
                if not option_states:
                    raise CrowdMovementReservationError(
                        f'{actor_id}: route option {option_index} is empty'
                    )
                options.append(option_states)
            normalized.append({
                **spec,
                'actor_id': actor_id,
                'states': states,
                'route_options': options,
                'start_delay': max(0, int(spec.get('start_delay', 0))),
                'priority': int(spec.get('priority', index)),
                '_input_index': index,
            })
        return normalized

    def _earliest_safe_pre_spawn_delay(
        self,
        relative_trajectory: Mapping[str, Any],
        initial_delay: int,
        planned: Iterable[Mapping[str, Any]],
    ) -> tuple[int, list[dict[str, Any]]]:
        """Find a launch tick with no synchronized head conflict.

        The delay is applied before the actor becomes visible.  Once spawned,
        the returned state list is continuous: no synthetic idle/wait samples
        are inserted.  A bounded probe keeps normal crowds cheap; if every
        probe collides, launching after the current planned horizon is a safe
        deterministic final fallback.
        """
        planned_rows = list(planned)
        probe_limit = max(0, int(self.max_pre_spawn_delay_ticks))
        for adjustment in range(probe_limit + 1):
            delay = int(initial_delay) + adjustment
            candidate = self._shift_trajectory(relative_trajectory, delay)
            conflicts: list[dict[str, Any]] = []
            for row in planned_rows:
                conflicts.extend(self._trajectory_conflicts(candidate, row['_trajectory']))
                if conflicts:
                    break
            if not conflicts:
                return delay, []

        latest_end = max(
            (int(row['_trajectory'].get('end_tick', -1)) for row in planned_rows),
            default=int(initial_delay) - 1,
        )
        delay = max(int(initial_delay) + probe_limit + 1, latest_end + 1)
        candidate = self._shift_trajectory(relative_trajectory, delay)
        for _ in range(4):
            conflicts = []
            for row in planned_rows:
                conflicts.extend(self._trajectory_conflicts(candidate, row['_trajectory']))
                if conflicts:
                    break
            if not conflicts:
                return delay, []
            latest_conflict_end = max(
                int(row['_trajectory'].get('end_tick', delay))
                for row in planned_rows
                if row['_trajectory'].get('segments')
            )
            delay = max(delay + 1, latest_conflict_end + 1)
            candidate = self._shift_trajectory(relative_trajectory, delay)
        # ``delay`` is after every currently planned trajectory in normal use;
        # returning the remaining diagnostics keeps failures inspectable if a
        # caller supplied a malformed, non-finite state stream.
        return delay, conflicts

    def audit_trajectories(
        self,
        actor_rows: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Audit only synchronized head separation, not trail overlap."""
        rows = [dict(row) for row in actor_rows]
        trajectories: list[dict[str, Any]] = []
        for row in rows:
            trajectory = self._trajectory(row.get('states', ()), int(row.get('start_delay', 0)))
            trajectory['actor_id'] = str(row.get('actor_id', ''))
            trajectory['_states'] = list(row.get('states', ()))
            trajectories.append(trajectory)

        head_collision_conflicts = 0
        head_clearance_conflicts = 0
        edge_swap_conflicts = 0
        same_cell_conflicts = 0
        min_distance: float | None = None
        synchronized_intervals_checked = 0
        for index, first in enumerate(trajectories):
            for second in trajectories[index + 1:]:
                common_ticks = sorted(
                    set(first.get('segments', {})) & set(second.get('segments', {}))
                )
                point_ticks = set(first.get('points', {})) & set(second.get('points', {}))
                common_tick_set = set(common_ticks) | point_ticks
                synchronized_distances: dict[int, float] = {}
                for tick in sorted(common_tick_set):
                    synchronized_intervals_checked += 1
                    distances: list[float] = []
                    if tick in first.get('segments', {}) and tick in second.get('segments', {}):
                        distances.append(self._synchronized_distance(
                            first['segments'][tick], second['segments'][tick]
                        ))
                    if tick in first.get('points', {}) and tick in second.get('points', {}):
                        first_point = first['points'][tick]
                        second_point = second['points'][tick]
                        distances.append(math.hypot(
                            first_point[0] - second_point[0],
                            first_point[1] - second_point[1],
                        ))
                    distance = min(distances)
                    synchronized_distances[tick] = distance
                    if min_distance is None or distance < min_distance:
                        min_distance = distance
                    if distance <= 1e-6:
                        head_collision_conflicts += 1
                    if distance <= self.ground_clearance_px + 1e-6:
                        head_clearance_conflicts += 1

                # Keep this diagnostic only for a genuine synchronized
                # conflict.  Merely sharing a coarse UV cell at different
                # screen positions is allowed by the head-only contract.
                first_states = {
                    int(first.get('start_delay', 0)) + offset: state
                    for offset, state in enumerate(first.get('_states', ()))
                }
                second_states = {
                    int(second.get('start_delay', 0)) + offset: state
                    for offset, state in enumerate(second.get('_states', ()))
                }
                for tick in sorted(set(first_states) & set(second_states)):
                    first_edge = self._state_edge(first_states[tick])
                    second_edge = self._state_edge(second_states[tick])
                    if first_edge is not None and second_edge == (first_edge[1], first_edge[0]):
                        if tick in common_tick_set:
                            edge_swap_conflicts += 1
                # Same-cell is intentionally not a reservation primitive here;
                # report it only when the synchronized head audit already says
                # the two actors are inside the configured clearance.
                for tick in sorted(common_tick_set & set(first_states) & set(second_states)):
                    first_state = first_states[tick]
                    second_state = second_states[tick]
                    if (
                        first_state.get('current_uv') is not None
                        and second_state.get('current_uv') is not None
                        and self._cell(first_state['current_uv']) == self._cell(second_state['current_uv'])
                        and synchronized_distances.get(tick, float('inf'))
                        <= self.ground_clearance_px + 1e-6
                    ):
                        same_cell_conflicts += 1

        active_wait_ticks = sum(
            1
            for row in rows
            for state in row.get('states', ())
            if state.get('phase') == 'crowd_wait'
        )
        return {
            'collision_free': head_clearance_conflicts == 0,
            'same_cell_conflicts': same_cell_conflicts,
            'edge_swap_conflicts': edge_swap_conflicts,
            'swept_segment_conflicts': head_collision_conflicts,
            'ground_clearance_conflicts': head_clearance_conflicts,
            'head_collision_conflicts': head_collision_conflicts,
            'head_clearance_conflicts': head_clearance_conflicts,
            'active_wait_ticks': active_wait_ticks,
            'synchronized_intervals_checked': synchronized_intervals_checked,
            'min_synchronized_distance_px': (
                round(min_distance, 4) if min_distance is not None else None
            ),
            'min_ground_distance_px': (
                round(min_distance, 4) if min_distance is not None else None
            ),
        }

    def schedule_trajectories(
        self,
        actors: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Plan independent, no-wait trajectories for a visible crowd.

        Route options are evaluated in a deterministic longest-trajectory-first
        order (priority and input index break ties), so bottleneck users claim
        a lane before short portal trips are fitted around them.
        The planner first tries the actor's requested launch tick on every
        route, then the smallest invisible pre-spawn offset.  It never inserts
        a ``crowd_wait`` state after spawn.  Only synchronized head distance is
        a conflict; line/trail overlap at different times remains legal.
        """
        normalized = self._normalize_trajectory_specs(actors)
        order = sorted(
            normalized,
            key=lambda row: (-len(row['states']), row['priority'], row['_input_index']),
        )
        planned: list[dict[str, Any]] = []
        chosen_by_id: dict[str, dict[str, Any]] = {}

        for spec in order:
            actor_id = spec['actor_id']
            initial_delay = int(spec['start_delay'])
            route_candidates = [spec['states'], *spec.get('route_options', [])]
            route_results: list[tuple[tuple[Any, ...], int, int, dict[str, Any], list[dict[str, Any]]]] = []
            for route_index, route_states in enumerate(route_candidates):
                relative = self._trajectory(route_states, 0)
                relative['actor_id'] = actor_id
                relative['_states'] = route_states
                delay, diagnostics = self._earliest_safe_pre_spawn_delay(
                    relative,
                    initial_delay,
                    planned,
                )
                shifted = self._shift_trajectory(relative, delay)
                shifted['actor_id'] = actor_id
                shifted['_states'] = route_states
                # Prefer no invisible delay first, then the shortest sampled
                # route, then the stable option index.
                score = (
                    delay - initial_delay,
                    len(route_states),
                    route_index,
                )
                route_results.append((score, route_index, delay, shifted, diagnostics))
            if not route_results:
                raise CrowdMovementReservationError(
                    f'{actor_id}: no trajectory route candidates'
                )

            _score, route_index, delay, trajectory, diagnostics = min(
                route_results, key=lambda row: row[0]
            )
            states = []
            for raw_state in route_candidates[route_index]:
                state = dict(raw_state)
                state['actor_id'] = actor_id
                if state.get('phase') == 'crowd_wait':
                    raise CrowdMovementReservationError(
                        f'{actor_id}: trajectory input contains active crowd_wait state'
                    )
                states.append(state)
            row = {
                'actor_id': actor_id,
                'priority': spec['priority'],
                'start_delay': int(delay),
                'start_delay_adjustment': int(delay) - initial_delay,
                'pre_spawn_delay_ticks': int(delay) - initial_delay,
                'states': states,
                'route_option_index': route_index,
                'route_option_count': len(route_candidates),
                'wait_ticks': 0,
                'max_wait_ticks': 0,
                'active_wait_ticks': 0,
                'blocked_events': diagnostics,
                'collision_resolution': (
                    'alternate_route' if route_index else
                    'pre_spawn_delay' if int(delay) > initial_delay else
                    'synchronized_head_trajectory'
                ),
                '_trajectory': trajectory,
                '_states': states,
            }
            planned.append(row)
            chosen_by_id[actor_id] = row

        actor_rows = [chosen_by_id[spec['actor_id']] for spec in normalized]
        public_rows = []
        for row in actor_rows:
            public = {key: value for key, value in row.items() if not key.startswith('_')}
            public_rows.append(public)
        audit = self.audit_trajectories(public_rows)
        wait_total = sum(int(row.get('wait_ticks', 0)) for row in public_rows)
        pre_spawn_total = sum(int(row.get('pre_spawn_delay_ticks', 0)) for row in public_rows)
        max_pre_spawn = max(
            (int(row.get('pre_spawn_delay_ticks', 0)) for row in public_rows),
            default=0,
        )
        return {
            # Keep the public reservation schema stable for existing central
            # consumers; the policy fields below identify the new semantics.
            'schema': 'gds.dynamic_actor_reservation.v1',
            'trajectory_schema': 'gds.dynamic_actor_trajectory_plan.v1',
            'policy': 'synchronized_head_trajectory_conflict_only',
            'tick_ms': 60,
            'reservation_radius_cells': self.reservation_radius_cells,
            'ground_clearance_px': self.ground_clearance_px,
            'max_wait_ticks': self.max_wait_ticks,
            'max_pre_spawn_delay_limit_ticks': self.max_pre_spawn_delay_ticks,
            'actor_count': len(public_rows),
            'wait_ticks_total': wait_total,
            'active_wait_ticks_total': int(audit['active_wait_ticks']),
            'max_actor_wait_ticks': max(
                (int(row.get('max_wait_ticks', 0)) for row in public_rows),
                default=0,
            ),
            'pre_spawn_delay_ticks_total': pre_spawn_total,
            'max_pre_spawn_delay_ticks': max_pre_spawn,
            'collision_free': audit['collision_free'],
            'same_cell_conflicts': audit['same_cell_conflicts'],
            'edge_swap_conflicts': audit['edge_swap_conflicts'],
            'swept_segment_conflicts': audit['swept_segment_conflicts'],
            'ground_clearance_conflicts': audit['ground_clearance_conflicts'],
            'head_collision_conflicts': audit['head_collision_conflicts'],
            'head_clearance_conflicts': audit['head_clearance_conflicts'],
            'min_ground_distance_px': audit['min_ground_distance_px'],
            'min_synchronized_distance_px': audit['min_synchronized_distance_px'],
            'synchronized_intervals_checked': audit['synchronized_intervals_checked'],
            'swept_segment_blocking': False,
            'synchronized_head_blocking': True,
            'trail_overlap_allowed': True,
            'edge_swap_blocking': True,
            'actors': public_rows,
        }

    def schedule(
        self,
        actors: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Schedule actor state sequences with deterministic reservations.

        Each actor mapping requires ``states`` and may provide ``actor_id``,
        ``start_delay``, ``priority`` and ``route_options``.  Lower priority
        values reserve first; ties retain input order.  Route options are
        already-sampled alternatives for the same immutable actor/goal, and
        the option with the lowest wait/queue cost is selected.  Returned actor
        rows retain input order so a renderer can replace its raw state list
        without changing character identity or color assignment.
        """
        specs = [dict(item) for item in actors]
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, spec in enumerate(specs):
            actor_id = str(spec.get('actor_id', f'actor-{index}'))
            if actor_id in seen_ids:
                raise CrowdMovementReservationError(f'Duplicate actor_id: {actor_id}')
            seen_ids.add(actor_id)
            states = spec.get('states')
            if states is None:
                raise CrowdMovementReservationError(f'{actor_id}: states are required')
            normalized_states = []
            for state in states:
                row = dict(state)
                state_actor_id = row.get('actor_id')
                if state_actor_id is not None and str(state_actor_id) != actor_id:
                    raise CrowdMovementReservationError(
                        f'{actor_id}: state actor_id does not match the actor schedule'
                    )
                row['actor_id'] = actor_id
                normalized_states.append(row)
            normalized_options: list[list[dict[str, Any]]] = []
            for option_index, option in enumerate(spec.get('route_options', ())):
                option_states: list[dict[str, Any]] = []
                for state in option:
                    row = dict(state)
                    state_actor_id = row.get('actor_id')
                    if state_actor_id is not None and str(state_actor_id) != actor_id:
                        raise CrowdMovementReservationError(
                            f'{actor_id}: route option {option_index} actor_id does not match'
                        )
                    row['actor_id'] = actor_id
                    option_states.append(row)
                if not option_states:
                    raise CrowdMovementReservationError(
                        f'{actor_id}: route option {option_index} is empty'
                    )
                normalized_options.append(option_states)
            normalized.append({
                **spec,
                'actor_id': actor_id,
                'states': normalized_states,
                'route_options': normalized_options,
                'start_delay': max(0, int(spec.get('start_delay', 0))),
                'priority': int(spec.get('priority', index)),
                '_input_index': index,
            })

        occupied: dict[int, dict[Cell, str]] = {}
        edges: dict[int, dict[Edge, str]] = {}
        motions: dict[int, dict[str, MotionSegment]] = {}
        scheduled_by_id: dict[str, dict[str, Any]] = {}
        order = sorted(normalized, key=lambda row: (row['priority'], row['_input_index']))

        for spec in order:
            actor_id = spec['actor_id']
            initial_delay = int(spec['start_delay'])
            # First try the requested launch slot.  If the actor is blocked
            # before it can safely establish a waiting cell, jump directly to
            # the end of the already-reserved horizon instead of retrying one
            # tick at a time.  This is the deterministic portal queue fallback
            # and keeps large crowds from spending O(horizon * path) work on
            # doomed launch attempts.
            route_candidates = [spec['states'], *spec.get('route_options', [])]
            route_results: list[tuple[tuple, int, dict[str, Any]]] = []
            latest_reserved_tick = max(occupied.keys(), default=initial_delay - 1)
            queued_delay = max(initial_delay + 1, latest_reserved_tick + 1)
            for route_index, route_states in enumerate(route_candidates):
                result = self._attempt_schedule(
                    actor_id,
                    route_states,
                    initial_delay,
                    occupied,
                    edges,
                    motions,
                )
                selected_delay = initial_delay
                if result is None:
                    # If the route cannot establish a safe waiting anchor,
                    # queue the complete route after the current reservation
                    # horizon and evaluate the same fallback for alternatives.
                    result = self._attempt_schedule(
                        actor_id,
                        route_states,
                        queued_delay,
                        occupied,
                        edges,
                        motions,
                    )
                    selected_delay = queued_delay
                if result is not None:
                    delay_adjustment = max(0, selected_delay - initial_delay)
                    score = (
                        int(result['wait_ticks']) + delay_adjustment * 2,
                        delay_adjustment,
                        len(result['states']),
                        route_index,
                    )
                    route_results.append((score, route_index, result))
            if not route_results:
                raise CrowdMovementReservationError(
                    f'{actor_id}: no collision-free reservation after route options and queue fallback'
                )

            _score, route_index, result = min(route_results, key=lambda row: row[0])

            for tick, cells in result['occupied'].items():
                occupied.setdefault(tick, {}).update(cells)
            for tick, tick_edges in result['edges'].items():
                edges.setdefault(tick, {}).update(tick_edges)
            for tick, tick_motions in result['motions'].items():
                motions.setdefault(tick, {}).update(tick_motions)
            scheduled_by_id[actor_id] = {
                'actor_id': actor_id,
                'priority': spec['priority'],
                'start_delay': result['start_delay'],
                'start_delay_adjustment': result['start_delay'] - initial_delay,
                'states': result['states'],
                'route_option_index': route_index,
                'route_option_count': len(route_candidates),
                'wait_ticks': result['wait_ticks'],
                'max_wait_ticks': result['max_wait_ticks'],
                'blocked_events': result['blocked_events'],
            }

        actor_rows = [scheduled_by_id[spec['actor_id']] for spec in normalized]
        wait_total = sum(row['wait_ticks'] for row in actor_rows)
        max_wait = max((row['max_wait_ticks'] for row in actor_rows), default=0)
        audit = self.audit(actor_rows)
        return {
            # Keep the public reservation schema stable; the additional
            # swept-segment fields are additive and do not invalidate existing
            # consumers of the v1 schedule contract.
            'schema': 'gds.dynamic_actor_reservation.v1',
            'policy': 'ground_anchor_cell_and_swept_screen_segment_reservation',
            'tick_ms': 60,
            'reservation_radius_cells': self.reservation_radius_cells,
            'ground_clearance_px': self.ground_clearance_px,
            'max_wait_ticks': self.max_wait_ticks,
            'actor_count': len(actor_rows),
            'wait_ticks_total': wait_total,
            'max_actor_wait_ticks': max_wait,
            'collision_free': audit['collision_free'],
            'same_cell_conflicts': audit['same_cell_conflicts'],
            'edge_swap_conflicts': audit['edge_swap_conflicts'],
            'swept_segment_conflicts': audit['swept_segment_conflicts'],
            'ground_clearance_conflicts': audit['ground_clearance_conflicts'],
            'min_ground_distance_px': audit['min_ground_distance_px'],
            'swept_segment_blocking': True,
            'edge_swap_blocking': True,
            'actors': actor_rows,
        }

    def audit(self, actor_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Audit grid, edge and swept screen-space separation constraints."""
        occupied: dict[int, dict[Cell, str]] = {}
        edges: dict[int, dict[Edge, str]] = {}
        motions: dict[int, dict[str, MotionSegment]] = {}
        same_cell_conflicts = 0
        edge_swap_conflicts = 0
        ground_clearance_conflicts = 0
        swept_segment_conflicts = 0
        min_ground_distance_px: float | None = None
        for row in actor_rows:
            actor_id = str(row['actor_id'])
            start_delay = int(row.get('start_delay', 0))
            for offset, state in enumerate(row.get('states', [])):
                tick = start_delay + offset
                cells = self._state_cells(
                    state,
                    radius=self.reservation_radius_cells,
                )
                for cell in cells:
                    owner = occupied.setdefault(tick, {}).get(cell)
                    if owner is not None and owner != actor_id:
                        same_cell_conflicts += 1
                    else:
                        occupied[tick][cell] = actor_id
                edge = self._state_edge(state)
                if edge is not None:
                    reverse = (edge[1], edge[0])
                    for other_edge, owner in edges.get(tick, {}).items():
                        if owner != actor_id and other_edge == reverse:
                            edge_swap_conflicts += 1
                    edges.setdefault(tick, {})[edge] = actor_id
                previous_state = (
                    row.get('states', [])[offset - 1]
                    if offset > 0
                    else None
                )
                motion_segment = self._motion_segment(state, previous_state)
                if motion_segment is not None:
                    for owner, other_segment in motions.get(tick, {}).items():
                        if owner == actor_id:
                            continue
                        distance = self._segment_distance(motion_segment, other_segment)
                        if min_ground_distance_px is None or distance < min_ground_distance_px:
                            min_ground_distance_px = distance
                        if distance <= 1e-6:
                            swept_segment_conflicts += 1
                        if (
                            self.ground_clearance_px > 0.0
                            and distance <= self.ground_clearance_px + 1e-6
                        ):
                            ground_clearance_conflicts += 1
                    motions.setdefault(tick, {})[actor_id] = motion_segment
        return {
            'collision_free': (
                same_cell_conflicts == 0
                and edge_swap_conflicts == 0
                and swept_segment_conflicts == 0
                and ground_clearance_conflicts == 0
            ),
            'same_cell_conflicts': same_cell_conflicts,
            'edge_swap_conflicts': edge_swap_conflicts,
            'swept_segment_conflicts': swept_segment_conflicts,
            'ground_clearance_conflicts': ground_clearance_conflicts,
            'min_ground_distance_px': (
                round(min_ground_distance_px, 4)
                if min_ground_distance_px is not None
                else None
            ),
        }


CrowdMovementCore = DynamicActorReservationCore
