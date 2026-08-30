from __future__ import annotations

from collections import deque
from heapq import heappop, heappush
from pathlib import Path
from typing import Iterable

from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore


class PathfindingError(ValueError):
    pass


class UnknownFloor(PathfindingError):
    pass


class InvalidStart(PathfindingError):
    pass


class InvalidGoal(PathfindingError):
    pass


class PathNotFound(PathfindingError):
    pass


class PathfindingCore:
    """Deterministic 4-neighbor A* over runtime-derived walkable cells."""

    NEIGHBOR_DELTAS = ((1, 0), (0, 1), (-1, 0), (0, -1))  # +U, +V, -U, -V

    def __init__(self, world_root: str | Path, *, occupancy: NavigationOccupancyCore | None = None):
        self.root = Path(world_root).resolve()
        self.occupancy = occupancy or NavigationOccupancyCore(self.root)

    @staticmethod
    def _normalize_uv(uv: tuple[int, int] | list[int]) -> tuple[int, int]:
        if len(uv) != 2:
            raise ValueError(f'Expected uv pair, got: {uv!r}')
        return int(uv[0]), int(uv[1])

    def _compiled(self, floor_id: str) -> dict:
        try:
            return self.occupancy.resolve_floor(floor_id)
        except KeyError as exc:
            raise UnknownFloor(f'Unknown floor: {floor_id}') from exc

    @staticmethod
    def _walkable_set(compiled: dict) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in compiled['walkable_cells_uv']}

    @staticmethod
    def _portal_set(compiled: dict) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in compiled['portal_inside_cells_uv']}

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _distance_map(self, walkable: set[tuple[int, int]], start: tuple[int, int]) -> dict[tuple[int, int], int]:
        distances = {start: 0}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            for du, dv in self.NEIGHBOR_DELTAS:
                nxt = (cur[0] + du, cur[1] + dv)
                if nxt in walkable and nxt not in distances:
                    distances[nxt] = distances[cur] + 1
                    queue.append(nxt)
        return distances

    def find_path(self, floor_id: str, start_uv: tuple[int, int] | list[int], goal_uv: tuple[int, int] | list[int]) -> dict:
        compiled = self._compiled(floor_id)
        walkable = self._walkable_set(compiled)
        start = self._normalize_uv(start_uv)
        goal = self._normalize_uv(goal_uv)
        if start not in walkable:
            raise InvalidStart(f'{floor_id}: start is not a walkable cell: {start}')
        if goal not in walkable:
            raise InvalidGoal(f'{floor_id}: goal is not a walkable cell: {goal}')
        if start == goal:
            return {
                'floor_id': floor_id,
                'start_uv': list(start),
                'goal_uv': list(goal),
                'path_cells_uv': [list(start)],
                'path_cell_count': 1,
                'compressed_waypoints_uv': [list(start)],
                'reachable': True,
            }

        frontier: list[tuple[int, int, int, int, int, tuple[int, int]]] = []
        push_seq = 0
        heappush(frontier, (self._manhattan(start, goal), 0, start[1], start[0], push_seq, start))
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        best_g: dict[tuple[int, int], int] = {start: 0}

        while frontier:
            _f, g, _v, _u, _seq, current = heappop(frontier)
            if g != best_g.get(current):
                continue
            if current == goal:
                break
            for du, dv in self.NEIGHBOR_DELTAS:
                nxt = (current[0] + du, current[1] + dv)
                if nxt not in walkable:
                    continue
                candidate_g = g + 1
                if candidate_g < best_g.get(nxt, 1 << 60):
                    best_g[nxt] = candidate_g
                    came_from[nxt] = current
                    push_seq += 1
                    heappush(
                        frontier,
                        (
                            candidate_g + self._manhattan(nxt, goal),
                            candidate_g,
                            nxt[1],
                            nxt[0],
                            push_seq,
                            nxt,
                        ),
                    )
        else:
            raise PathNotFound(f'{floor_id}: no route from {start} to {goal}')

        path: list[tuple[int, int]] = []
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came_from[cur]
        path.reverse()
        out = [list(cell) for cell in path]
        return {
            'floor_id': floor_id,
            'start_uv': list(start),
            'goal_uv': list(goal),
            'path_cells_uv': out,
            'path_cell_count': len(out),
            'compressed_waypoints_uv': self.compress_path(out),
            'reachable': True,
        }

    def compress_path(self, path_cells_uv: Iterable[list[int] | tuple[int, int]]) -> list[list[int]]:
        path = [self._normalize_uv(cell) for cell in path_cells_uv]
        if len(path) <= 2:
            return [list(cell) for cell in path]
        out = [path[0]]
        prev_delta = (path[1][0] - path[0][0], path[1][1] - path[0][1])
        for idx in range(1, len(path) - 1):
            cur = path[idx]
            nxt = path[idx + 1]
            delta = (nxt[0] - cur[0], nxt[1] - cur[1])
            if delta != prev_delta:
                out.append(cur)
                prev_delta = delta
        out.append(path[-1])
        return [list(cell) for cell in out]

    def resolve_portal_start(self, floor_id: str) -> tuple[int, int]:
        compiled = self._compiled(floor_id)
        walkable = self._walkable_set(compiled)
        portal_cells = self._portal_set(compiled) & walkable
        if not portal_cells:
            raise PathNotFound(f'{floor_id}: no walkable portal-inside cells')
        mu = sum(u for u, _ in portal_cells) / len(portal_cells)
        mv = sum(v for _, v in portal_cells) / len(portal_cells)
        return min(portal_cells, key=lambda uv: (abs(uv[0] - mu) + abs(uv[1] - mv), uv[1], uv[0]))

    def resolve_distant_target(self, floor_id: str, start_uv: tuple[int, int] | list[int]) -> tuple[int, int]:
        compiled = self._compiled(floor_id)
        walkable = self._walkable_set(compiled)
        start = self._normalize_uv(start_uv)
        if start not in walkable:
            raise InvalidStart(f'{floor_id}: start is not a walkable cell: {start}')
        distances = self._distance_map(walkable, start)
        if len(distances) <= 1:
            return start
        return min(distances.keys(), key=lambda uv: (-distances[uv], uv[1], uv[0]))

    def resolve_near_target(
        self,
        floor_id: str,
        start_uv: tuple[int, int] | list[int],
        *,
        min_distance: int = 6,
    ) -> tuple[int, int]:
        compiled = self._compiled(floor_id)
        walkable = self._walkable_set(compiled)
        start = self._normalize_uv(start_uv)
        if start not in walkable:
            raise InvalidStart(f'{floor_id}: start is not a walkable cell: {start}')
        distances = self._distance_map(walkable, start)
        candidates = [uv for uv, dist in distances.items() if dist >= min_distance]
        if not candidates:
            candidates = [uv for uv in distances if uv != start]
        if not candidates:
            return start
        return min(candidates, key=lambda uv: (distances[uv], uv[1], uv[0]))
