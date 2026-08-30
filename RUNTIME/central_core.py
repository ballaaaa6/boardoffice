from __future__ import annotations

from pathlib import Path
from typing import Any

from CHARACTER.RUNTIME.character_system import CharacterSystem, CharacterSystemError
from CHARACTER.RUNTIME.asset_registry import AssetRegistry as CharacterAssetRegistry, AssetResolutionError
from CHARACTER.IDENTITY.RUNTIME.identity_resolver import (
    CharacterIdentityLookupError,
    CharacterIdentityResolver,
)
from WORLD.RUNTIME.direction_core import DirectionCore
from WORLD.RUNTIME.floor_renderer import FloorRenderer
from WORLD.RUNTIME.ground_footprint_core import GroundFootprintCore
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore
from WORLD.RUNTIME.layout_core import LayoutCore
from WORLD.RUNTIME.spatial_core import SpatialCore
from WORLD.RUNTIME.pathfinding_core import PathfindingCore, PathfindingError
from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore
from WORLD.RUNTIME.gameplay_metadata_family_core import GameplayMetadataFamilyCore
from RUNTIME.work_seat_core import WorkSeatCore, WorkSeatError
from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from RUNTIME.portal_actor_lifecycle import PortalActorLifecycle, PortalActorLifecycleError


class CentralGameCoreError(ValueError):
    pass


class CentralGameCore:
    """Phase 5 facade joining character identity/rendering and world layout/direction."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.character_root = self.root / 'CHARACTER'
        self.identity_root = self.character_root / 'IDENTITY'
        self.world_root = self.root / 'WORLD'

        self.characters = CharacterSystem(self.character_root)
        self.character_assets = CharacterAssetRegistry(self.character_root)
        self.identity = CharacterIdentityResolver(self.identity_root)
        self.world = LayoutCore(self.world_root)
        self.floors = FloorRenderer(self.world_root)
        self.directions = DirectionCore(self.world_root)
        self.spatial = SpatialCore(self.world_root)
        self.footprints = GroundFootprintCore(self.world_root)
        self.room_navigation = RoomNavigationCore(self.world_root)
        self.navigation_occupancy = NavigationOccupancyCore(self.world_root)
        self.pathfinding = PathfindingCore(self.world_root, occupancy=self.navigation_occupancy)
        self.character_movement = CharacterMovementCore(self.root, pathfinding=self.pathfinding)
        self.portal_lifecycle = PortalActorLifecycle(self.root, movement=self.character_movement)
        self.walking_depth = WalkingDepthCore(
            self.world_root,
            layout=self.world,
            occupancy=self.navigation_occupancy,
            floor_renderer=self.floors,
        )
        self.gameplay_metadata = GameplayMetadataFamilyCore(
            self.world_root,
            layout=self.world,
            room_navigation=self.room_navigation,
            occupancy=self.navigation_occupancy,
            directions=self.directions,
        )
        self.work_seats = WorkSeatCore(
            self.root, characters=self.characters, world=self.world, directions=self.directions
        )

    def resolve_asset_path(self, domain: str, asset_id: str) -> Path:
        domain_key = domain.strip().casefold()
        if domain_key == 'character':
            try:
                return self.character_assets.resolve(asset_id, verify_hash=False)
            except AssetResolutionError as exc:
                raise CentralGameCoreError(str(exc)) from exc
        if domain_key == 'world':
            try:
                return self.world.resolve_asset_blob(asset_id)
            except KeyError as exc:
                raise CentralGameCoreError(f'Unknown world asset: {asset_id}') from exc
        raise CentralGameCoreError(f'Unknown asset domain: {domain!r}; expected character or world')

    def resolve_character(self, query: int | str) -> dict[str, Any]:
        try:
            return self.identity.resolve(query)
        except CharacterIdentityLookupError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_character_id(self, query: int | str) -> str:
        return self.resolve_character(query)['character_id']

    def render_character(
        self,
        query: int | str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        effect_id: str | None = None,
    ):
        character_id = self.resolve_character_id(query)
        try:
            return self.characters.render(
                character_id,
                action,
                direction,
                subaction,
                effect_id=effect_id,
            )
        except CharacterSystemError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def list_humanballs(self) -> list[str]:
        return self.characters.list_humanballs()

    def get_humanball(self, humanball_id: str) -> dict[str, Any]:
        try:
            return self.characters.get_humanball(humanball_id)
        except CharacterSystemError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_humanball(
        self,
        humanball_id: str,
        direction: str,
        *,
        human_size: tuple[int, int] = (32, 42),
    ):
        try:
            return self.characters.render_humanball(
                humanball_id, direction, human_size=human_size
            )
        except CharacterSystemError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_floor(self, floor_id: str):
        return self.floors.render(floor_id)

    def resolve_workstation_direction(self, floor_id: str, workstation_id: str) -> str:
        return self.directions.resolve_workstation_direction(floor_id, workstation_id)

    def resolve_workstation(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        direction = self.directions.resolve_direction_record(floor_id, workstation_id)
        group = self.world.workstation_group(floor_id, workstation_id)
        return {
            **direction,
            'group': group,
        }

    def render_character_at_workstation(
        self,
        query: int | str,
        floor_id: str,
        workstation_id: str,
        *,
        subaction: str = 'normal_work',
        effect_id: str | None = None,
    ):
        direction = self.directions.resolve_character_action_direction(
            floor_id,
            workstation_id,
            action_family='work',
        )
        return self.render_character(
            query,
            'work',
            direction,
            subaction,
            effect_id=effect_id,
        )
    def resolve_spatial_object(self, floor_id: str, placement_id: str) -> dict[str, Any]:
        return self.spatial.resolve_object(floor_id, placement_id)

    def list_spatial_objects(self, floor_id: str, object_types=None) -> list[dict[str, Any]]:
        return self.spatial.list_objects(floor_id, object_types=object_types)

    def resolve_workstation_spatial(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        return self.spatial.resolve_workstation_spatial(floor_id, workstation_id)


    def resolve_ground_footprint(self, asset_id: str, *, transform: str | None = None):
        return self.footprints.resolve_asset(asset_id, transform=transform)

    def resolve_ground_footprint_variant(self, variant_id: str):
        return self.footprints.resolve_variant(variant_id)

    def project_ground_footprint(self, asset_id: str, asset_top_left_px, *, transform: str | None = None):
        return self.footprints.project_asset(asset_id, asset_top_left_px, transform=transform)

    def resolve_fine_occupancy_grid(self) -> dict[str, Any]:
        return self.footprints.fine_grid_profile()

    def resolve_room_navigation_family(self, floor_id: str) -> dict[str, Any]:
        return self.room_navigation.family(floor_id)

    def resolve_room_domain(self, floor_id: str) -> dict[str, Any]:
        return self.room_navigation.domain(floor_id)

    def resolve_portal(self, floor_id: str) -> dict[str, Any]:
        return self.room_navigation.portal(floor_id)

    def resolve_room_cells(self, floor_id: str) -> dict[str, Any]:
        return self.room_navigation.room_cells(floor_id)

    def is_room_cell(self, floor_id: str, u: int, v: int) -> bool:
        return self.room_navigation.is_room_cell(floor_id, u, v)

    def resolve_navigation_cells(self, floor_id: str) -> dict[str, Any]:
        return self.navigation_occupancy.resolve_floor(floor_id)

    def is_walkable_cell(self, floor_id: str, u: int, v: int) -> bool:
        return self.navigation_occupancy.is_walkable(floor_id, u, v)

    def validate_navigation_floor(self, floor_id: str) -> dict[str, Any]:
        return self.navigation_occupancy.validate_floor(floor_id)

    def resolve_gameplay_metadata_family(self, floor_id: str) -> dict[str, Any]:
        return self.gameplay_metadata.family_for_floor(floor_id)

    def audit_gameplay_metadata_family(self, floor_or_family_id: str) -> dict[str, Any]:
        return self.gameplay_metadata.audit_family(floor_or_family_id)

    def resolve_workstation_navigation_access(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        access = self.navigation_occupancy.workstation_access(floor_id, workstation_id)
        seat = self.resolve_work_seat(floor_id, workstation_id)
        if seat['chair_placement_id'] != access['chair_placement_id']:
            raise CentralGameCoreError(
                f'Navigation/work-seat chair mismatch for {floor_id}.{workstation_id}: '
                f"{access['chair_placement_id']} != {seat['chair_placement_id']}"
            )
        out = dict(access)
        out['work_seat_direction'] = seat['direction']
        out['work_seat_chair_asset_id'] = seat['chair_asset_id']
        out['seat_transition_ready'] = bool(
            out['chair_fully_inside_room'] and out['reachable_approach_cell_count'] > 0
        )
        return out

    def resolve_work_seat(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        try:
            return self.work_seats.resolve_workstation_seat(floor_id, workstation_id)
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def compose_work_seat(
        self,
        query: int | str,
        chair_family_id: str,
        direction: str,
        *,
        subaction: str = 'normal_work',
    ):
        character_id = self.resolve_character_id(query)
        try:
            return self.work_seats.compose_seat(
                character_id, chair_family_id, direction, subaction
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_floor_with_work(
        self,
        floor_id: str,
        assignments: list[dict[str, Any]],
        *,
        frame_index: int = 0,
    ):
        normalized: list[dict[str, Any]] = []
        for assignment in assignments:
            if 'workstation_id' not in assignment:
                raise CentralGameCoreError('work assignment requires workstation_id')
            if 'character' in assignment:
                query = assignment['character']
            elif 'character_id' in assignment:
                query = assignment['character_id']
            else:
                raise CentralGameCoreError('work assignment requires character or character_id')
            item = dict(assignment)
            item.pop('character', None)
            item['character_id'] = self.resolve_character_id(query)
            normalized.append(item)
        try:
            return self.work_seats.render_floor_with_work(
                floor_id, normalized, frame_index=frame_index
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc


    def find_navigation_path(self, floor_id: str, start_uv, goal_uv) -> dict[str, Any]:
        try:
            return self.pathfinding.find_path(floor_id, start_uv, goal_uv)
        except PathfindingError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_portal_navigation_start(self, floor_id: str) -> list[int]:
        try:
            return list(self.pathfinding.resolve_portal_start(floor_id))
        except PathfindingError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_distant_navigation_target(self, floor_id: str, start_uv) -> list[int]:
        try:
            return list(self.pathfinding.resolve_distant_target(floor_id, start_uv))
        except PathfindingError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_character_movement(self, query: int | str, floor_id: str, start_uv, goal_uv) -> dict[str, Any]:
        try:
            return self.character_movement.resolve_movement(query, floor_id, start_uv, goal_uv)
        except CharacterMovementError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_portal_actor_cycle(
        self,
        query: int | str,
        floor_id: str,
        goal_uv=None,
    ) -> dict[str, Any]:
        try:
            return self.portal_lifecycle.build_cycle(query, floor_id, goal_uv)
        except PortalActorLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_floor_with_work_effects(
        self,
        floor_id: str,
        assignments: list[dict[str, Any]],
        *,
        frame_index: int = 0,
    ):
        normalized: list[dict[str, Any]] = []
        for assignment in assignments:
            if 'workstation_id' not in assignment:
                raise CentralGameCoreError('work assignment requires workstation_id')
            if 'character' in assignment:
                query = assignment['character']
            elif 'character_id' in assignment:
                query = assignment['character_id']
            else:
                raise CentralGameCoreError('work assignment requires character or character_id')
            item = dict(assignment)
            item.pop('character', None)
            item['character_id'] = self.resolve_character_id(query)
            normalized.append(item)
        try:
            return self.work_seats.render_floor_with_work_effects(
                floor_id, normalized, frame_index=frame_index
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc
