from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from CHARACTER.IDENTITY.RUNTIME.identity_resolver import CharacterIdentityLookupError
from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from WORLD.RUNTIME.pathfinding_core import PathfindingError


class PortalActorLifecycleError(ValueError):
    """Raised when a portal actor cycle cannot be resolved."""


class PortalActorLifecycle:
    """Resolve the deterministic runtime lifecycle for one portal actor.

    The lifecycle is deliberately renderer-agnostic.  It emits JSON-safe
    motion samples which a game renderer can consume with the existing
    character and walking-depth APIs:

    ``unspawned -> entering -> active -> exiting -> despawned``

    Portal geometry and movement remain owned by the canonical navigation and
    movement cores; this class only coordinates their transitions.
    """

    UNSPAWNED = 'unspawned'
    ENTERING = 'entering'
    ACTIVE = 'active'
    EXITING = 'exiting'
    DESPAWNED = 'despawned'

    DEFAULT_FADE_STEPS = 4
    DEFAULT_GOAL_HOLD_STEPS = 4
    DEFAULT_PORTAL_HOLD_STEPS = 3

    def __init__(
        self,
        root: str | Path,
        *,
        movement: CharacterMovementCore | None = None,
        fade_steps: int = DEFAULT_FADE_STEPS,
        goal_hold_steps: int = DEFAULT_GOAL_HOLD_STEPS,
        portal_hold_steps: int = DEFAULT_PORTAL_HOLD_STEPS,
    ):
        self.root = Path(root).resolve()
        self.movement = movement or CharacterMovementCore(self.root)
        self.pathfinding = self.movement.pathfinding
        self.navigation = self.movement.navigation
        self.fade_steps = self._positive_steps('fade_steps', fade_steps)
        self.goal_hold_steps = self._positive_steps('goal_hold_steps', goal_hold_steps)
        self.portal_hold_steps = self._positive_steps('portal_hold_steps', portal_hold_steps)

    @staticmethod
    def _positive_steps(name: str, value: int) -> int:
        value = int(value)
        if value <= 0:
            raise PortalActorLifecycleError(f'{name} must be >= 1')
        return value

    @staticmethod
    def _normalize_uv(uv: tuple[int, int] | list[int]) -> tuple[int, int]:
        if len(uv) != 2:
            raise PortalActorLifecycleError(f'Expected uv pair, got: {uv!r}')
        return int(uv[0]), int(uv[1])

    @staticmethod
    def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    @staticmethod
    def _round_xy(xy: tuple[float, float]) -> list[float]:
        return [round(float(xy[0]), 4), round(float(xy[1]), 4)]

    def _character_id(self, query: int | str) -> str:
        try:
            return self.movement.identity.resolve_character_id(query)
        except CharacterIdentityLookupError as exc:
            raise PortalActorLifecycleError(str(exc)) from exc

    def _portal_pair(self, floor_id: str) -> tuple[tuple[int, int], tuple[int, int]]:
        try:
            inside = self.pathfinding.resolve_portal_start(floor_id)
            portal = self.navigation.portal(floor_id)
        except (PathfindingError, KeyError, ValueError) as exc:
            raise PortalActorLifecycleError(str(exc)) from exc

        outside_cells = [self._normalize_uv(cell) for cell in portal.get('outside_cells_uv', [])]
        if not outside_cells:
            raise PortalActorLifecycleError(f'{floor_id}: portal has no outside cells')

        adjacent = [cell for cell in outside_cells if self._manhattan(cell, inside) == 1]
        if adjacent:
            outside = min(adjacent, key=lambda cell: (cell[1], cell[0]))
        else:
            outside = min(
                outside_cells,
                key=lambda cell: (self._manhattan(cell, inside), cell[1], cell[0]),
            )
        return inside, outside

    def _state(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        phase: str,
        action: str,
        direction: str,
        ground_xy: tuple[float, float],
        alpha: float,
        visible: bool,
        cumulative_distance_px: float,
        current_uv: tuple[int, int] | None = None,
        from_uv: tuple[int, int] | None = None,
        to_uv: tuple[int, int] | None = None,
        progress_t: float | None = None,
        frame_index: int | None = None,
        raw_direction: str | None = None,
        movement_profile: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            'actor_id': actor_id,
            'character_id': character_id,
            'floor_id': floor_id,
            'phase': phase,
            'action': action,
            'direction': direction,
            'raw_direction': raw_direction or direction,
            'ground_xy': self._round_xy(ground_xy),
            'current_uv': list(current_uv) if current_uv is not None else None,
            'from_uv': list(from_uv) if from_uv is not None else None,
            'to_uv': list(to_uv) if to_uv is not None else None,
            'progress_t': round(float(progress_t), 4) if progress_t is not None else None,
            'alpha': round(max(0.0, min(1.0, float(alpha))), 4),
            'visible': bool(visible),
            'cumulative_distance_px': round(float(cumulative_distance_px), 4),
            'frame_index': int(frame_index) if frame_index is not None else None,
            'speed_percent': int(movement_profile['speed_percent']),
            'speed_multiplier': float(movement_profile['speed_multiplier']),
            'tick_ms': int(movement_profile['playback_tick_ms']),
        }

    def _interpolated_states(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        start_uv: tuple[int, int],
        end_uv: tuple[int, int],
        direction: str,
        phase: str,
        alphas: list[float],
        distance_offset_px: float,
        movement_profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], float]:
        start_xy = self.movement.uv_cell_center_to_pixel(*start_uv)
        end_xy = self.movement.uv_cell_center_to_pixel(*end_uv)
        segment_distance = math.dist(start_xy, end_xy)
        states: list[dict[str, Any]] = []
        for index, alpha in enumerate(alphas, start=1):
            progress = index / len(alphas)
            xy = (
                start_xy[0] + (end_xy[0] - start_xy[0]) * progress,
                start_xy[1] + (end_xy[1] - start_xy[1]) * progress,
            )
            states.append(self._state(
                actor_id=actor_id,
                character_id=character_id,
                floor_id=floor_id,
                phase=phase,
                action='move',
                direction=direction,
                ground_xy=xy,
                alpha=alpha,
                visible=alpha > 0,
                cumulative_distance_px=distance_offset_px + segment_distance * progress,
                current_uv=end_uv if index == len(alphas) else None,
                from_uv=start_uv,
                to_uv=end_uv,
                progress_t=progress,
                movement_profile=movement_profile,
            ))
        return states, distance_offset_px + segment_distance

    def _path_states(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        path_cells_uv: list[tuple[int, int]],
        distance_offset_px: float,
        movement_profile: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], float]:
        try:
            samples = self.movement.sample_path_timeline(
                path_cells_uv,
                speed_multiplier=float(movement_profile['speed_multiplier']),
                tick_ms=int(movement_profile['playback_tick_ms']),
            )
        except CharacterMovementError as exc:
            raise PortalActorLifecycleError(str(exc)) from exc

        states: list[dict[str, Any]] = []
        for sample in samples:
            states.append(self._state(
                actor_id=actor_id,
                character_id=character_id,
                floor_id=floor_id,
                phase=self.ACTIVE,
                action='move',
                direction=sample['direction'],
                raw_direction=sample['raw_direction'],
                ground_xy=tuple(sample['ground_xy']),
                alpha=1.0,
                visible=True,
                cumulative_distance_px=distance_offset_px + float(sample['cumulative_distance_px']),
                current_uv=self._normalize_uv(sample['to_uv']),
                from_uv=self._normalize_uv(sample['from_uv']),
                to_uv=self._normalize_uv(sample['to_uv']),
                progress_t=float(sample['progress_t']),
                movement_profile=movement_profile,
            ))
        if samples:
            distance_offset_px += float(samples[-1]['cumulative_distance_px'])
        return states, distance_offset_px

    def _hold_states(
        self,
        *,
        actor_id: str,
        character_id: str,
        floor_id: str,
        phase: str,
        uv: tuple[int, int],
        direction: str,
        count: int,
        distance_px: float,
        movement_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        xy = self.movement.uv_cell_center_to_pixel(*uv)
        return [self._state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            phase=phase,
            action='idle',
            direction=direction,
            ground_xy=xy,
            alpha=1.0,
            visible=True,
            cumulative_distance_px=distance_px,
            current_uv=uv,
            frame_index=index,
            movement_profile=movement_profile,
        ) for index in range(count)]

    @staticmethod
    def _append_phase(
        states: list[dict[str, Any]],
        phase_ranges: dict[str, list[int]],
        phase_states: list[dict[str, Any]],
    ) -> None:
        if not phase_states:
            return
        phase = phase_states[0]['phase']
        start = len(states)
        states.extend(phase_states)
        end = len(states) - 1
        if phase in phase_ranges:
            phase_ranges[phase][1] = end
        else:
            phase_ranges[phase] = [start, end]

    def build_cycle(
        self,
        character_query: int | str,
        floor_id: str,
        goal_uv: tuple[int, int] | list[int] | None = None,
    ) -> dict[str, Any]:
        """Build a complete portal entry, movement, exit and despawn cycle."""
        character_id = self._character_id(character_query)
        movement_profile = self.movement.resolve_movement_profile(character_id)
        inside_uv, outside_uv = self._portal_pair(floor_id)
        target_uv = (
            self._normalize_uv(goal_uv)
            if goal_uv is not None
            else self.pathfinding.resolve_distant_target(floor_id, inside_uv)
        )
        try:
            outward = self.pathfinding.find_path(floor_id, inside_uv, target_uv)
            returning = self.pathfinding.find_path(floor_id, target_uv, inside_uv)
        except PathfindingError as exc:
            raise PortalActorLifecycleError(str(exc)) from exc

        outward_path = [self._normalize_uv(cell) for cell in outward['path_cells_uv']]
        return_path = [self._normalize_uv(cell) for cell in returning['path_cells_uv']]
        entry_direction = self.movement.direction_for_step(outside_uv, inside_uv)
        exit_direction = self.movement.direction_for_step(inside_uv, outside_uv)
        actor_id = f'{floor_id}:{character_id}'

        states = [self._state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            phase=self.UNSPAWNED,
            action='idle',
            direction=entry_direction,
            ground_xy=self.movement.uv_cell_center_to_pixel(*outside_uv),
            alpha=0.0,
            visible=False,
            cumulative_distance_px=0.0,
            current_uv=outside_uv,
            movement_profile=movement_profile,
        )]
        phase_ranges: dict[str, list[int]] = {self.UNSPAWNED: [0, 0]}

        entry_states, cumulative = self._interpolated_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            start_uv=outside_uv,
            end_uv=inside_uv,
            direction=entry_direction,
            phase=self.ENTERING,
            alphas=[(index + 1) / self.fade_steps for index in range(self.fade_steps)],
            distance_offset_px=0.0,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, entry_states)

        outward_states, cumulative = self._path_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            path_cells_uv=outward_path,
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, outward_states)
        goal_direction = outward_states[-1]['direction'] if outward_states else entry_direction
        goal_hold = self._hold_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            phase=self.ACTIVE,
            uv=target_uv,
            direction=goal_direction,
            count=self.goal_hold_steps,
            distance_px=cumulative,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, goal_hold)

        return_states, cumulative = self._path_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            path_cells_uv=return_path,
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, return_states)
        portal_direction = return_states[-1]['direction'] if return_states else goal_direction
        portal_hold = self._hold_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            phase=self.ACTIVE,
            uv=inside_uv,
            direction=portal_direction,
            count=self.portal_hold_steps,
            distance_px=cumulative,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, portal_hold)

        exit_states, cumulative = self._interpolated_states(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            start_uv=inside_uv,
            end_uv=outside_uv,
            direction=exit_direction,
            phase=self.EXITING,
            alphas=[1.0 - (index / self.fade_steps) for index in range(self.fade_steps)],
            distance_offset_px=cumulative,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, exit_states)
        despawned = self._state(
            actor_id=actor_id,
            character_id=character_id,
            floor_id=floor_id,
            phase=self.DESPAWNED,
            action='idle',
            direction=exit_direction,
            ground_xy=self.movement.uv_cell_center_to_pixel(*outside_uv),
            alpha=0.0,
            visible=False,
            cumulative_distance_px=cumulative,
            current_uv=outside_uv,
            movement_profile=movement_profile,
        )
        self._append_phase(states, phase_ranges, [despawned])

        phase_counts: dict[str, int] = {}
        for state in states:
            phase_counts[state['phase']] = phase_counts.get(state['phase'], 0) + 1

        return {
            'schema': 'gds.portal_actor_lifecycle.v1',
            'actor_id': actor_id,
            'character_id': character_id,
            'floor_id': floor_id,
            'movement_profile': movement_profile,
            'playback_tick_ms': movement_profile['playback_tick_ms'],
            'portal': {
                'inside_uv': list(inside_uv),
                'outside_uv': list(outside_uv),
                'entry_direction': entry_direction,
                'exit_direction': exit_direction,
                'entry_exit_adjacent': self._manhattan(inside_uv, outside_uv) == 1,
            },
            'target_uv': list(target_uv),
            'outward_path_cells_uv': [list(cell) for cell in outward_path],
            'return_path_cells_uv': [list(cell) for cell in return_path],
            'fade_steps': self.fade_steps,
            'phase_ranges': phase_ranges,
            'phase_counts': phase_counts,
            'state_count': len(states),
            'states': states,
            'final_state': despawned,
            'despawned': despawned['phase'] == self.DESPAWNED and not despawned['visible'],
        }

    resolve_cycle = build_cycle
