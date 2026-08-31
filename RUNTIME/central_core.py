from __future__ import annotations

from pathlib import Path
from typing import Any

from CHARACTER.RUNTIME.character_system import CharacterSystem, CharacterSystemError
from CHARACTER.RUNTIME.dialogue_bubble import (
    BubbleSelection,
    DialogueBubbleError,
    DialogueBubbleRenderResult,
    TextMetrics,
)
from CHARACTER.RUNTIME.dialogue_content import DialogueLine
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
from RUNTIME.work_seat_lifecycle import WorkSeatLifecycle, WorkSeatLifecycleError
from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from RUNTIME.employee_registry import EmployeeMetadataError, EmployeeMetadataRegistry
from RUNTIME.portal_actor_lifecycle import PortalActorLifecycle, PortalActorLifecycleError
from RUNTIME.crowd_movement_core import (
    CrowdMovementReservationError,
    DynamicActorReservationCore,
)


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
        self.employee_metadata = EmployeeMetadataRegistry(self.root)
        self.world = LayoutCore(self.world_root)
        self.floors = FloorRenderer(self.world_root)
        self.directions = DirectionCore(self.world_root)
        self.spatial = SpatialCore(self.world_root)
        self.footprints = GroundFootprintCore(self.world_root)
        self.room_navigation = RoomNavigationCore(self.world_root)
        self.navigation_occupancy = NavigationOccupancyCore(self.world_root)
        self.pathfinding = PathfindingCore(self.world_root, occupancy=self.navigation_occupancy)
        self.character_movement = CharacterMovementCore(
            self.root,
            pathfinding=self.pathfinding,
            employee_registry=self.employee_metadata,
        )
        self.portal_lifecycle = PortalActorLifecycle(self.root, movement=self.character_movement)
        self.crowd_movement = DynamicActorReservationCore()
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
        self.work_seat_lifecycle = WorkSeatLifecycle(
            self.root,
            movement=self.character_movement,
            navigation=self.navigation_occupancy,
            pathfinding=self.pathfinding,
            work_seats=self.work_seats,
            characters=self.characters,
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
        if domain_key == 'dialogue':
            try:
                return self.characters.resolve_dialogue_asset_path(asset_id)
            except (CharacterSystemError, DialogueBubbleError) as exc:
                raise CentralGameCoreError(str(exc)) from exc
        raise CentralGameCoreError(f'Unknown asset domain: {domain!r}; expected character, world or dialogue')

    def resolve_character(self, query: int | str) -> dict[str, Any]:
        try:
            return self.identity.resolve(query)
        except CharacterIdentityLookupError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_character_id(self, query: int | str) -> str:
        return self.resolve_character(query)['character_id']

    def list_employees(
        self,
        *,
        wave: int | None = None,
        assigned: bool | None = None,
        character_pool: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self.employee_metadata.list(
                wave=wave,
                assigned=assigned,
                character_pool=character_pool,
            )
        except EmployeeMetadataError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee(self, employee_id: str) -> dict[str, Any]:
        try:
            return self.employee_metadata.resolve(employee_id)
        except EmployeeMetadataError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee_assignment(self, employee_id: str) -> dict[str, Any] | None:
        employee = self.resolve_employee(employee_id)
        assignment = employee.get('assignment')
        return None if assignment is None else dict(assignment)

    def resolve_initial_employee_roster(
        self,
        floor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self.employee_metadata.resolve_initial_roster(floor_id)
        except EmployeeMetadataError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee_stamina_profile(self, employee_id: str) -> dict[str, Any]:
        employee = self.resolve_employee(employee_id)
        return {
            'employee_id': employee['employee_id'],
            'character_id': employee['character_id'],
            'stamina_profile': dict(employee['stamina_profile']),
            'stamina_policy': self.employee_metadata.stamina_policy(),
        }

    def render_employee(
        self,
        employee_id: str,
        action: str,
        direction: str | None = None,
        subaction: str | None = None,
        *,
        effect_id: str | None = None,
    ):
        employee = self.resolve_employee(employee_id)
        return self.render_character(
            employee['character_id'],
            action,
            direction,
            subaction,
            effect_id=effect_id,
        )

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

    def render_employee_dialogue_bubble(
        self,
        employee_id: str,
        frame_id: str,
        text: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        employee = self.resolve_employee(employee_id)
        try:
            return self.characters.render_dialogue_bubble_for_frame(
                employee['character_id'],
                frame_id,
                text,
                actor_top_left=actor_top_left,
                locale=locale,
                font_size_px=font_size_px,
            )
        except (CharacterSystemError, DialogueBubbleError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_employee_dialogue_line(
        self,
        employee_id: str,
        frame_id: str,
        dialogue_id: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str | None = None,
        line_index: int = 0,
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        line = self.resolve_dialogue_line(
            dialogue_id,
            locale='en' if locale is None else locale,
            line_index=line_index,
            require_enabled=True,
        )
        return self.render_employee_dialogue_bubble(
            employee_id,
            frame_id,
            line.text,
            actor_top_left=actor_top_left,
            locale=line.locale,
            font_size_px=font_size_px,
        )

    def list_dialogue_bubbles(self) -> list[str]:
        return self.characters.list_dialogue_bubbles()

    def list_dialogue_lines(
        self, *, locale: str | None = None, category: str | None = None,
        usage_scope: str | None = None, enabled_only: bool = False,
    ) -> list[dict[str, object]]:
        return self.characters.list_dialogue_lines(
            locale=locale, category=category, usage_scope=usage_scope,
            enabled_only=enabled_only,
        )

    def reload_dialogue_content(self) -> dict[str, object]:
        return self.characters.reload_dialogue_content()

    def resolve_dialogue_line(
        self,
        dialogue_id: str,
        *,
        locale: str = 'en',
        line_index: int = 0,
        require_enabled: bool = False,
    ) -> DialogueLine:
        return self.characters.resolve_dialogue_line(
            dialogue_id,
            locale=locale,
            line_index=line_index,
            require_enabled=require_enabled,
        )

    def measure_dialogue_text(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> TextMetrics:
        return self.characters.measure_dialogue_text(
            text,
            locale=locale,
            font_size_px=font_size_px,
        )

    def select_dialogue_bubble(
        self,
        text: str,
        *,
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> BubbleSelection:
        return self.characters.select_dialogue_bubble(
            text,
            locale=locale,
            font_size_px=font_size_px,
        )

    def render_dialogue_bubble_for_character(
        self,
        query: int | str,
        frame_id: str,
        text: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str = 'en',
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        character_id = self.resolve_character_id(query)
        try:
            return self.characters.render_dialogue_bubble_for_frame(
                character_id,
                frame_id,
                text,
                actor_top_left=actor_top_left,
                locale=locale,
                font_size_px=font_size_px,
            )
        except (CharacterSystemError, DialogueBubbleError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_dialogue_line_for_character(
        self,
        query: int | str,
        frame_id: str,
        dialogue_id: str,
        *,
        actor_top_left: tuple[int, int] = (0, 0),
        locale: str | None = None,
        line_index: int = 0,
        font_size_px: int | None = None,
    ) -> DialogueBubbleRenderResult:
        line = self.resolve_dialogue_line(
            dialogue_id,
            locale='en' if locale is None else locale,
            line_index=line_index,
            require_enabled=True,
        )
        return self.render_dialogue_bubble_for_character(
            query,
            frame_id,
            line.text,
            actor_top_left=actor_top_left,
            locale=line.locale,
            font_size_px=font_size_px,
        )

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

    def resolve_work_turn_mapping(self, direction: str) -> dict[str, Any]:
        """Expose direction-named seated turn bindings for a work direction."""
        try:
            return self.work_seats.resolve_turn_side_mapping(direction)
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_work_turn_for_target(
        self, direction: str, target_idle_direction: str
    ) -> dict[str, Any]:
        """Select the seated turn whose named idle facing matches a target direction."""
        try:
            return self.work_seats.resolve_turn_side_for_target(
                direction, target_idle_direction
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_work_seat_interaction_slot(
        self, floor_id: str, workstation_id: str
    ) -> dict[str, Any]:
        try:
            return self.work_seat_lifecycle.resolve_interaction_slot(floor_id, workstation_id)
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_work_seat_interaction_slots(self, floor_id: str) -> list[dict[str, Any]]:
        try:
            return self.work_seat_lifecycle.resolve_interaction_slots(floor_id)
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def audit_work_seat_interaction_slots(self) -> dict[str, Any]:
        try:
            return self.work_seat_lifecycle.audit_all_interaction_slots()
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_work_seat_actor_cycle(
        self,
        query: int | str,
        floor_id: str,
        workstation_id: str,
        start_uv,
        exit_goal_uv=None,
        work_ticks: int = WorkSeatLifecycle.DEFAULT_WORK_TICKS,
        subaction: str = 'normal_work',
        effect_id: str | None = None,
        humanball_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.work_seat_lifecycle.resolve_actor_cycle(
                query,
                floor_id,
                workstation_id,
                start_uv,
                exit_goal_uv=exit_goal_uv,
                work_ticks=work_ticks,
                subaction=subaction,
                effect_id=effect_id,
                humanball_id=humanball_id,
            )
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee_work_seat_actor_cycle(
        self,
        employee_id: str,
        floor_id: str,
        workstation_id: str,
        start_uv,
        exit_goal_uv=None,
        work_ticks: int = WorkSeatLifecycle.DEFAULT_WORK_TICKS,
        subaction: str = 'normal_work',
        effect_id: str | None = None,
        humanball_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.work_seat_lifecycle.resolve_actor_cycle(
                employee_id,
                floor_id,
                workstation_id,
                start_uv,
                exit_goal_uv=exit_goal_uv,
                work_ticks=work_ticks,
                subaction=subaction,
                effect_id=effect_id,
                humanball_id=humanball_id,
                employee_id=employee_id,
            )
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_work_seat_lifecycle_state(
        self,
        floor_id: str,
        workstation_id: str,
        query: int | str,
        *,
        subaction: str = 'normal_work',
        effect_id: str | None = None,
        humanball_id: str | None = None,
        character_frame_index: int = 0,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
    ):
        try:
            return self.work_seat_lifecycle.render_seated_state(
                floor_id=floor_id,
                workstation_id=workstation_id,
                character_query=query,
                subaction=subaction,
                effect_id=effect_id,
                humanball_id=humanball_id,
                character_frame_index=character_frame_index,
                effect_frame_index=effect_frame_index,
                humanball_frame_index=humanball_frame_index,
            )
        except WorkSeatLifecycleError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_character_event_action(self, query: int | str, event: str) -> dict[str, Any]:
        """Resolve directionless sad/happy event animation outside work mode."""
        event_key = str(event).strip().casefold()
        if event_key not in {'sad', 'happy'}:
            raise CentralGameCoreError(
                f'Unknown character event: {event!r}; expected sad or happy'
            )
        character_id = self.resolve_character_id(query)
        try:
            result = self.characters.render(character_id, event_key, None, None)
        except CharacterSystemError as exc:
            raise CentralGameCoreError(str(exc)) from exc
        return {
            'character_id': character_id,
            'action': event_key,
            'direction': None,
            'subaction': None,
            'frame_ids': list(result.frame_ids),
            'frame_count': len(result.frames),
            'loop': bool(result.loop),
            'semantic_group': 'event_emotion',
            'direction_source': 'none',
        }

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
        character_frame_index: int | None = None,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
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
                floor_id,
                normalized,
                frame_index=frame_index,
                character_frame_index=character_frame_index,
                effect_frame_index=effect_frame_index,
                humanball_frame_index=humanball_frame_index,
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc


    def find_navigation_path(self, floor_id: str, start_uv, goal_uv) -> dict[str, Any]:
        try:
            return self.pathfinding.find_path(floor_id, start_uv, goal_uv)
        except PathfindingError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def find_alternate_navigation_path(
        self,
        floor_id: str,
        start_uv,
        goal_uv,
        *,
        max_candidates: int = 8,
    ) -> dict[str, Any] | None:
        try:
            return self.pathfinding.find_alternate_path(
                floor_id,
                start_uv,
                goal_uv,
                max_candidates=max_candidates,
            )
        except PathfindingError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def find_alternate_navigation_paths(
        self,
        floor_id: str,
        start_uv,
        goal_uv,
        *,
        max_candidates: int = 8,
    ) -> list[dict[str, Any]]:
        try:
            return self.pathfinding.find_alternate_paths(
                floor_id,
                start_uv,
                goal_uv,
                max_candidates=max_candidates,
            )
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

    def resolve_character_movement_profile(
        self,
        query: int | str,
        *,
        actor_seed: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.character_movement.resolve_movement_profile(
                query,
                actor_seed=actor_seed,
            )
        except CharacterMovementError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee_movement_profile(self, employee_id: str) -> dict[str, Any]:
        try:
            return self.character_movement.resolve_employee_movement_profile(employee_id)
        except CharacterMovementError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_employee_movement(
        self,
        employee_id: str,
        floor_id: str,
        start_uv,
        goal_uv,
    ) -> dict[str, Any]:
        try:
            return self.character_movement.resolve_employee_movement(
                employee_id,
                floor_id,
                start_uv,
                goal_uv,
            )
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

    def resolve_crowd_movement_schedule(self, actors) -> dict[str, Any]:
        """Resolve the production no-wait synchronized-head crowd plan."""
        try:
            return self.crowd_movement.schedule_trajectories(actors)
        except CrowdMovementReservationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_legacy_crowd_movement_schedule(self, actors) -> dict[str, Any]:
        """Resolve the legacy discrete reservation schedule for old tools."""
        try:
            return self.crowd_movement.schedule(actors)
        except CrowdMovementReservationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def render_floor_with_work_effects(
        self,
        floor_id: str,
        assignments: list[dict[str, Any]],
        *,
        frame_index: int = 0,
        character_frame_index: int | None = None,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
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
                floor_id,
                normalized,
                frame_index=frame_index,
                character_frame_index=character_frame_index,
                effect_frame_index=effect_frame_index,
                humanball_frame_index=humanball_frame_index,
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc
