from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

from CHARACTER.IDENTITY.RUNTIME.identity_resolver import (
    CharacterIdentityLookupError,
    CharacterIdentityResolver,
)
from CHARACTER.RUNTIME.character_system import CharacterSystem, CharacterSystemError
from WORLD.RUNTIME.pathfinding_core import PathfindingCore
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore


class CharacterMovementError(ValueError):
    pass


class CharacterMovementCore:
    """Thin movement resolver over pathfinding + existing character actions.

    Phase 8B follow-up additions:
    - expose dense per-step movement sampling for smooth preview/runtime playback
    - keep walk animation phase tied to cumulative travelled distance rather than
      raw output frame count so leg motion slows down naturally when movement is
      rendered more densely.
    """

    GROUND_ANCHOR_PX = (16, 31)
    DEFAULT_SUBSTEPS_PER_CELL = 4
    DEFAULT_WALK_FRAME_DISTANCE_CELLS = 0.5

    def __init__(self, root: str | Path, *, pathfinding: PathfindingCore | None = None):
        self.root = Path(root).resolve()
        self.world_root = self.root / 'WORLD'
        self.character_root = self.root / 'CHARACTER'
        self.identity_root = self.character_root / 'IDENTITY'
        self.navigation = RoomNavigationCore(self.world_root)
        self.pathfinding = pathfinding or PathfindingCore(self.world_root)
        self.characters = CharacterSystem(self.character_root)
        self.identity = CharacterIdentityResolver(self.identity_root)

    @staticmethod
    def _normalize_uv(uv: tuple[int, int] | list[int]) -> tuple[int, int]:
        if len(uv) != 2:
            raise ValueError(f'Expected uv pair, got: {uv!r}')
        return int(uv[0]), int(uv[1])

    def uv_cell_center_to_pixel(self, u: int, v: int) -> tuple[int, int]:
        grid = self.navigation.grid_profile()
        ox, oy = grid['grid_origin_px']
        ux, uy = grid['u_step_px']
        vx, vy = grid['v_step_px']
        cu = int(u) + 0.5
        cv = int(v) + 0.5
        x = ox + cu * ux + cv * vx
        y = oy + cu * uy + cv * vy
        return int(round(x)), int(round(y))

    def direction_for_step(self, start_uv: tuple[int, int] | list[int], end_uv: tuple[int, int] | list[int]) -> str:
        a = self._normalize_uv(start_uv)
        b = self._normalize_uv(end_uv)
        delta = (b[0] - a[0], b[1] - a[1])
        mapping = {
            (1, 0): 'SE',
            (-1, 0): 'NW',
            (0, 1): 'SW',
            (0, -1): 'NE',
        }
        try:
            return mapping[delta]
        except KeyError as exc:
            raise CharacterMovementError(f'Unsupported movement step: {a} -> {b}') from exc

    def fine_step_distance_px(self) -> float:
        a = self.uv_cell_center_to_pixel(0, 0)
        b = self.uv_cell_center_to_pixel(1, 0)
        return math.dist(a, b)

    def walk_cycle_frame_index(
        self,
        cumulative_distance_px: float,
        frame_count: int,
        *,
        frame_distance_cells: float = DEFAULT_WALK_FRAME_DISTANCE_CELLS,
    ) -> int:
        if frame_count <= 0:
            raise CharacterMovementError('frame_count must be positive')
        phase_distance_px = self.fine_step_distance_px() * float(frame_distance_cells)
        if phase_distance_px <= 0:
            raise CharacterMovementError('frame_distance_cells must be positive')
        return int(math.floor(float(cumulative_distance_px) / phase_distance_px)) % frame_count

    def sample_path_states(
        self,
        path_cells_uv: Iterable[list[int] | tuple[int, int]],
        *,
        substeps_per_cell: int = DEFAULT_SUBSTEPS_PER_CELL,
    ) -> list[dict]:
        """Return dense motion samples across every fine-grid edge in a path.

        Each returned row covers a single interpolated substep. Samples are
        emitted at the end of each substep (t = 1/N .. N/N) so there are no
        duplicated ground positions while the actor is in a moving state.
        """
        path = [self._normalize_uv(cell) for cell in path_cells_uv]
        if len(path) < 2:
            return []
        if int(substeps_per_cell) <= 0:
            raise CharacterMovementError('substeps_per_cell must be >= 1')
        substeps_per_cell = int(substeps_per_cell)

        states: list[dict] = []
        cumulative_distance_px = 0.0
        for step_index in range(len(path) - 1):
            cur = path[step_index]
            nxt = path[step_index + 1]
            direction = self.direction_for_step(cur, nxt)
            sx, sy = self.uv_cell_center_to_pixel(*cur)
            ex, ey = self.uv_cell_center_to_pixel(*nxt)
            dx, dy = ex - sx, ey - sy
            step_distance_px = math.hypot(dx, dy)
            if step_distance_px <= 0:
                continue
            for substep_index in range(substeps_per_cell):
                t = (substep_index + 1) / substeps_per_cell
                sample_distance_px = cumulative_distance_px + step_distance_px * t
                states.append({
                    'step_index': step_index,
                    'substep_index': substep_index,
                    'substep_count': substeps_per_cell,
                    'from_uv': list(cur),
                    'to_uv': list(nxt),
                    'direction': direction,
                    'progress_t': round(t, 4),
                    'ground_xy': [sx + dx * t, sy + dy * t],
                    'cumulative_distance_px': round(sample_distance_px, 4),
                })
            cumulative_distance_px += step_distance_px
        return states

    def _segment_path(self, path_cells_uv: Iterable[list[int] | tuple[int, int]]) -> list[dict]:
        path = [self._normalize_uv(cell) for cell in path_cells_uv]
        if len(path) < 2:
            return []
        segments: list[dict] = []
        seg_start = path[0]
        seg_direction = self.direction_for_step(path[0], path[1])
        step_count = 1
        for idx in range(1, len(path) - 1):
            step_direction = self.direction_for_step(path[idx], path[idx + 1])
            if step_direction == seg_direction:
                step_count += 1
                continue
            segments.append({
                'start_uv': list(seg_start),
                'end_uv': list(path[idx]),
                'direction': seg_direction,
                'step_count': step_count,
                'action': 'move',
            })
            seg_start = path[idx]
            seg_direction = step_direction
            step_count = 1
        segments.append({
            'start_uv': list(seg_start),
            'end_uv': list(path[-1]),
            'direction': seg_direction,
            'step_count': step_count,
            'action': 'move',
        })
        return segments

    def resolve_movement(
        self,
        character_query: int | str,
        floor_id: str,
        start_uv: tuple[int, int] | list[int],
        goal_uv: tuple[int, int] | list[int],
    ) -> dict:
        try:
            character_id = self.identity.resolve_character_id(character_query)
        except CharacterIdentityLookupError as exc:
            raise CharacterMovementError(str(exc)) from exc
        path = self.pathfinding.find_path(floor_id, start_uv, goal_uv)
        path_cells = [self._normalize_uv(cell) for cell in path['path_cells_uv']]
        segments = self._segment_path(path_cells)
        try:
            for segment in segments:
                segment['frame_ids'] = self.characters.resolve_frame_ids(character_id, 'move', segment['direction'])
        except CharacterSystemError as exc:
            raise CharacterMovementError(str(exc)) from exc
        arrival_direction = segments[-1]['direction'] if segments else 'SE'
        try:
            arrival_frame_ids = self.characters.resolve_frame_ids(character_id, 'idle', arrival_direction)
        except CharacterSystemError as exc:
            raise CharacterMovementError(str(exc)) from exc
        path_positions = [list(self.uv_cell_center_to_pixel(*cell)) for cell in path_cells]
        waypoints = [self._normalize_uv(cell) for cell in path['compressed_waypoints_uv']]
        waypoint_positions = [list(self.uv_cell_center_to_pixel(*cell)) for cell in waypoints]
        dense_samples = self.sample_path_states(path_cells, substeps_per_cell=self.DEFAULT_SUBSTEPS_PER_CELL)
        return {
            'character_id': character_id,
            'floor_id': floor_id,
            'start_uv': list(self._normalize_uv(start_uv)),
            'goal_uv': list(self._normalize_uv(goal_uv)),
            'path_cells_uv': [list(cell) for cell in path_cells],
            'path_cell_count': len(path_cells),
            'compressed_waypoints_uv': [list(cell) for cell in waypoints],
            'path_positions_px': path_positions,
            'waypoint_positions_px': waypoint_positions,
            'segments': segments,
            'dense_motion_substeps_per_cell': self.DEFAULT_SUBSTEPS_PER_CELL,
            'dense_motion_samples': dense_samples,
            'ground_anchor_px': list(self.GROUND_ANCHOR_PX),
            'arrival_action': {
                'action': 'idle',
                'direction': arrival_direction,
                'frame_ids': arrival_frame_ids,
            },
        }
