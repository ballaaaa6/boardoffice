from __future__ import annotations

import hashlib
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
    DEFAULT_PLAYBACK_TICK_MS = 60
    MIN_MOVE_SPEED_PERCENT = 125
    MAX_MOVE_SPEED_PERCENT = 175
    MOVEMENT_PROFILE_SEED = 'gds-character-movement-speed-v1'
    DEFAULT_WALK_FRAME_DISTANCE_CELLS = 0.65
    DEFAULT_DIRECTION_LOOKAHEAD_CELLS = 3
    DEFAULT_DIRECTION_CONFIRM_STEPS = 2
    DEFAULT_DIRECTION_MIN_HOLD_CELLS = 0.75
    DIRECTION_SCREEN_VECTORS = {
        'SE': (2.0, 1.0),
        'SW': (-2.0, 1.0),
        'NW': (-2.0, -1.0),
        'NE': (2.0, -1.0),
    }
    OPPOSITE_DIRECTIONS = {
        'SE': 'NW',
        'NW': 'SE',
        'SW': 'NE',
        'NE': 'SW',
    }

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

    def resolve_movement_profile(
        self,
        character_query: int | str,
        *,
        actor_seed: str | None = None,
    ) -> dict:
        """Return one deterministic movement profile for a character/actor.

        Speed is sampled once from the author-approved 125-175% range.  SHA-256
        keeps the assignment stable across processes and independent of actor
        creation order; an optional actor seed can intentionally vary repeated
        instances of the same character without re-rolling every frame.
        """
        try:
            character_id = self.identity.resolve_character_id(character_query)
        except CharacterIdentityLookupError as exc:
            raise CharacterMovementError(str(exc)) from exc
        key_parts = [self.MOVEMENT_PROFILE_SEED, character_id]
        if actor_seed is not None:
            key_parts.append(str(actor_seed))
        digest = hashlib.sha256('|'.join(key_parts).encode('utf-8')).digest()
        span = self.MAX_MOVE_SPEED_PERCENT - self.MIN_MOVE_SPEED_PERCENT + 1
        speed_percent = (
            self.MIN_MOVE_SPEED_PERCENT
            + int.from_bytes(digest[:8], 'big') % span
        )
        speed_multiplier = speed_percent / 100.0
        return {
            'character_id': character_id,
            'speed_percent': speed_percent,
            'speed_multiplier': speed_multiplier,
            'speed_range_percent': [self.MIN_MOVE_SPEED_PERCENT, self.MAX_MOVE_SPEED_PERCENT],
            'walk_frame_distance_cells': self.walk_frame_distance_cells(speed_multiplier),
            'playback_tick_ms': self.DEFAULT_PLAYBACK_TICK_MS,
            'direction_lookahead_cells': self.DEFAULT_DIRECTION_LOOKAHEAD_CELLS,
            'direction_confirm_steps': self.DEFAULT_DIRECTION_CONFIRM_STEPS,
            'direction_min_hold_cells': self.DEFAULT_DIRECTION_MIN_HOLD_CELLS,
            'assignment_policy': (
                'stable_sha256_per_character'
                if actor_seed is None
                else 'stable_sha256_per_actor_seed'
            ),
        }

    @classmethod
    def walk_frame_distance_cells(cls, speed_multiplier: float) -> float:
        """Scale stride distance with travel speed so fast actors do not pedal."""
        speed_multiplier = float(speed_multiplier)
        if speed_multiplier <= 0:
            raise CharacterMovementError('speed_multiplier must be positive')
        return round(cls.DEFAULT_WALK_FRAME_DISTANCE_CELLS * speed_multiplier, 4)

    @classmethod
    def base_move_speed_cells_per_second(cls) -> float:
        return 1000.0 / (cls.DEFAULT_PLAYBACK_TICK_MS * cls.DEFAULT_SUBSTEPS_PER_CELL)

    @classmethod
    def _direction_from_screen_vector(
        cls,
        dx: float,
        dy: float,
        *,
        preferred: str,
    ) -> str:
        scores = {
            direction: dx * vector[0] + dy * vector[1]
            for direction, vector in cls.DIRECTION_SCREEN_VECTORS.items()
        }
        best = max(scores.values())
        tied = [direction for direction, score in scores.items() if math.isclose(score, best, abs_tol=1e-9)]
        if preferred in tied:
            return preferred
        return tied[0]

    def visual_directions_for_path(
        self,
        path_cells_uv: Iterable[list[int] | tuple[int, int]],
        *,
        lookahead_cells: int = DEFAULT_DIRECTION_LOOKAHEAD_CELLS,
        confirm_steps: int = DEFAULT_DIRECTION_CONFIRM_STEPS,
        min_hold_cells: float = DEFAULT_DIRECTION_MIN_HOLD_CELLS,
    ) -> list[str]:
        """Resolve stable sprite facings without changing the navigation path.

        A* legitimately produces U/V staircases. Looking a few cells ahead in
        screen space and keeping the previous direction on an exact tie avoids
        rapidly alternating SE/SW or NE/NW artwork on those staircases.
        """
        path = [self._normalize_uv(cell) for cell in path_cells_uv]
        if len(path) < 2:
            return []
        lookahead_cells = int(lookahead_cells)
        confirm_steps = int(confirm_steps)
        min_hold_cells = float(min_hold_cells)
        if lookahead_cells < 1:
            raise CharacterMovementError('lookahead_cells must be >= 1')
        if confirm_steps < 1:
            raise CharacterMovementError('confirm_steps must be >= 1')
        if min_hold_cells < 0:
            raise CharacterMovementError('min_hold_cells must be >= 0')

        raw = [self.direction_for_step(path[index], path[index + 1]) for index in range(len(path) - 1)]
        stable = raw[0]
        pending: str | None = None
        pending_count = 0
        last_change_step = 0
        facings: list[str] = []

        for step_index, raw_direction in enumerate(raw):
            end_index = min(len(path) - 1, step_index + lookahead_cells)
            sx, sy = self.uv_cell_center_to_pixel(*path[step_index])
            ex, ey = self.uv_cell_center_to_pixel(*path[end_index])
            candidate = self._direction_from_screen_vector(
                ex - sx,
                ey - sy,
                preferred=stable,
            )

            if candidate == stable:
                pending = None
                pending_count = 0
            elif candidate == self.OPPOSITE_DIRECTIONS[stable]:
                stable = candidate
                last_change_step = step_index
                pending = None
                pending_count = 0
            else:
                if pending == candidate:
                    pending_count += 1
                else:
                    pending = candidate
                    pending_count = 1
                held_cells = step_index - last_change_step
                if held_cells >= min_hold_cells and pending_count >= confirm_steps:
                    stable = candidate
                    last_change_step = step_index
                    pending = None
                    pending_count = 0

            # A final isolated cell should keep the stabilized facing; true
            # persistent turns have already passed the confirmation rule.
            facings.append(stable if stable in self.DIRECTION_SCREEN_VECTORS else raw_direction)
        return facings

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
        visual_directions = self.visual_directions_for_path(path)

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
                    'raw_direction': direction,
                    'visual_direction': visual_directions[step_index],
                    'progress_t': round(t, 4),
                    'ground_xy': [sx + dx * t, sy + dy * t],
                    'cumulative_distance_px': round(sample_distance_px, 4),
                })
            cumulative_distance_px += step_distance_px
        return states

    def sample_path_timeline(
        self,
        path_cells_uv: Iterable[list[int] | tuple[int, int]],
        *,
        speed_multiplier: float,
        tick_ms: int = DEFAULT_PLAYBACK_TICK_MS,
    ) -> list[dict]:
        """Sample one actor on a shared fixed tick using its own travel speed."""
        path = [self._normalize_uv(cell) for cell in path_cells_uv]
        if len(path) < 2:
            return []
        speed_multiplier = float(speed_multiplier)
        tick_ms = int(tick_ms)
        if speed_multiplier <= 0:
            raise CharacterMovementError('speed_multiplier must be positive')
        if tick_ms <= 0:
            raise CharacterMovementError('tick_ms must be >= 1')

        raw_directions = [
            self.direction_for_step(path[index], path[index + 1])
            for index in range(len(path) - 1)
        ]
        visual_directions = self.visual_directions_for_path(path)
        total_cells = float(len(path) - 1)
        cells_per_second = self.base_move_speed_cells_per_second() * speed_multiplier
        cells_per_tick = cells_per_second * tick_ms / 1000.0
        tick_count = max(1, int(math.ceil(total_cells / cells_per_tick)))
        step_distance_px = self.fine_step_distance_px()
        states: list[dict] = []

        for tick_index in range(1, tick_count + 1):
            distance_cells = min(total_cells, tick_index * cells_per_tick)
            nearest_cell = int(round(distance_cells))
            if distance_cells > 0 and math.isclose(distance_cells, nearest_cell, abs_tol=1e-9):
                step_index = min(nearest_cell - 1, len(path) - 2)
                progress = 1.0
            else:
                step_index = min(int(math.floor(distance_cells)), len(path) - 2)
                progress = distance_cells - step_index
            cur = path[step_index]
            nxt = path[step_index + 1]
            sx, sy = self.uv_cell_center_to_pixel(*cur)
            ex, ey = self.uv_cell_center_to_pixel(*nxt)
            elapsed_ms = tick_index * tick_ms
            states.append({
                'tick_index': tick_index - 1,
                'tick_ms': tick_ms,
                'elapsed_ms': elapsed_ms,
                'speed_multiplier': speed_multiplier,
                'speed_percent': round(speed_multiplier * 100, 4),
                'distance_cells': round(distance_cells, 4),
                'step_index': step_index,
                'from_uv': list(cur),
                'to_uv': list(nxt),
                'direction': visual_directions[step_index],
                'visual_direction': visual_directions[step_index],
                'raw_direction': raw_directions[step_index],
                'progress_t': round(progress, 4),
                'ground_xy': [sx + (ex - sx) * progress, sy + (ey - sy) * progress],
                'cumulative_distance_px': round(distance_cells * step_distance_px, 4),
            })
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
        path_positions = [list(self.uv_cell_center_to_pixel(*cell)) for cell in path_cells]
        waypoints = [self._normalize_uv(cell) for cell in path['compressed_waypoints_uv']]
        waypoint_positions = [list(self.uv_cell_center_to_pixel(*cell)) for cell in waypoints]
        movement_profile = self.resolve_movement_profile(character_id)
        dense_samples = self.sample_path_states(path_cells, substeps_per_cell=self.DEFAULT_SUBSTEPS_PER_CELL)
        timed_samples = self.sample_path_timeline(
            path_cells,
            speed_multiplier=movement_profile['speed_multiplier'],
            tick_ms=movement_profile['playback_tick_ms'],
        )
        if timed_samples:
            arrival_direction = timed_samples[-1]['direction']
        try:
            arrival_frame_ids = self.characters.resolve_frame_ids(
                character_id,
                'idle',
                arrival_direction,
            )
        except CharacterSystemError as exc:
            raise CharacterMovementError(str(exc)) from exc
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
            'movement_profile': movement_profile,
            'dense_motion_substeps_per_cell': self.DEFAULT_SUBSTEPS_PER_CELL,
            'dense_motion_samples': dense_samples,
            'timed_motion_tick_ms': movement_profile['playback_tick_ms'],
            'timed_motion_samples': timed_samples,
            'ground_anchor_px': list(self.GROUND_ANCHOR_PX),
            'arrival_action': {
                'action': 'idle',
                'direction': arrival_direction,
                'frame_ids': arrival_frame_ids,
            },
        }
