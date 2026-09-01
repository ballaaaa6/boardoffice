from __future__ import annotations

import copy
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
from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore, WalkingDepthError
from WORLD.RUNTIME.gameplay_metadata_family_core import GameplayMetadataFamilyCore
from RUNTIME.work_seat_core import WorkSeatCore, WorkSeatError
from RUNTIME.work_seat_lifecycle import WorkSeatLifecycle, WorkSeatLifecycleError
from RUNTIME.character_movement_core import CharacterMovementCore, CharacterMovementError
from RUNTIME.employee_registry import EmployeeMetadataError, EmployeeMetadataRegistry
from RUNTIME.actor_simulation_core import ActorSimulationCore, ActorSimulationError
from RUNTIME.portal_actor_lifecycle import PortalActorLifecycle, PortalActorLifecycleError
from RUNTIME.crowd_movement_core import (
    CrowdMovementReservationError,
    DynamicActorReservationCore,
)
from RUNTIME.conversation_spot_core import ConversationSpotCore, ConversationSpotError
from RUNTIME.conversation_behavior_core import ConversationBehaviorCore, ConversationBehaviorError
from RUNTIME.speech_scheduler_core import SpeechSchedulerCore, SpeechSchedulerError
from RUNTIME.runtime_persistence import RuntimePersistence, RuntimePersistenceError


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
        self.actor_simulation = ActorSimulationCore(
            self.root,
            employee_registry=self.employee_metadata,
            slot_resolver=self.work_seat_lifecycle.resolve_interaction_slot,
            movement=self.character_movement,
            pathfinding=self.pathfinding,
            portal_lifecycle=self.portal_lifecycle,
            work_seat_lifecycle=self.work_seat_lifecycle,
        )
        self.conversation_spots = ConversationSpotCore(
            self.root,
            layout=self.world,
            navigation=self.navigation_occupancy,
            work_seats=self.work_seats,
            work_seat_lifecycle=self.work_seat_lifecycle,
            walking_depth=self.walking_depth,
        )
        self.conversation = ConversationBehaviorCore(
            self.root,
            employee_registry=self.employee_metadata,
            movement=self.character_movement,
            navigation=self.navigation_occupancy,
            pathfinding=self.pathfinding,
            work_seats=self.work_seats,
            work_seat_lifecycle=self.work_seat_lifecycle,
            spots=self.conversation_spots,
            crowd=self.crowd_movement,
        )
        self.speech_scheduler = SpeechSchedulerCore(
            self.root,
            employee_registry=self.employee_metadata,
            conversation=self.conversation,
        )
        self.runtime_persistence = RuntimePersistence(self)

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

    def resolve_actor_snapshot(self, floor_id: str | None = None) -> dict[str, Any]:
        try:
            return self.actor_simulation.initial_snapshot(floor_id)
        except ActorSimulationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def validate_actor_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.actor_simulation.validate_snapshot(snapshot)
        except ActorSimulationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def advance_actor_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        commands: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.actor_simulation.advance_snapshot(
                snapshot,
                elapsed_ms,
                commands=commands,
            )
        except ActorSimulationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def apply_actor_emotion_effect(
        self,
        snapshot: dict[str, Any],
        employee_id: str,
        emotion: str,
        *,
        timestamp_ms: int | None = None,
        source_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply a speech-owned sad/happy result through the actor reducer."""
        try:
            return self.actor_simulation.apply_emotion_effect(
                snapshot,
                employee_id,
                emotion,
                timestamp_ms=timestamp_ms,
                source_session_id=source_session_id,
            )
        except ActorSimulationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_actor_behavior_event(
        self,
        employee_id: str,
        *,
        simulation_time_ms: int = 0,
        event_counter: int = 0,
        cooldowns: dict[str, int] | None = None,
    ) -> str:
        try:
            return self.actor_simulation.choose_behavior_event(
                employee_id,
                simulation_time_ms=simulation_time_ms,
                event_counter=event_counter,
                cooldowns=cooldowns,
            )
        except ActorSimulationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

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

    def resolve_workstation_pc_frame(
        self,
        floor_id: str,
        workstation_id: str,
        frame_index: int = 0,
    ) -> dict[str, Any]:
        """Resolve the independent PC frame channel for one workstation."""
        try:
            seat = self.work_seats.resolve_workstation_seat(floor_id, workstation_id)
            asset_id, variant_id, normalized, frame_count = self.work_seats.resolve_pc_frame_asset(
                seat, frame_index
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc
        return {
            'floor_id': floor_id,
            'workstation_id': workstation_id,
            'direction': seat['direction'],
            'frame_index': normalized,
            'frame_count': frame_count,
            'asset_id': asset_id,
            'variant_id': variant_id,
            'sequence': (
                'cell0'
                if frame_count == 1
                else f'cell{normalized + 1}'
            ),
        }

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
        pc_frame_index: int | None = None,
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
                pc_frame_index=pc_frame_index,
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
        pc_frame_index: int | None = None,
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
                pc_frame_index=pc_frame_index,
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

    def actor_draws_over_reception(
        self,
        floor_id: str,
        ground_xy,
    ) -> bool:
        """Use authored reception depth to gate the one-shot leaving line."""
        try:
            return self.walking_depth.actor_draws_over_reception(floor_id, ground_xy)
        except (WalkingDepthError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_legacy_crowd_movement_schedule(self, actors) -> dict[str, Any]:
        """Resolve the legacy discrete reservation schedule for old tools."""
        try:
            return self.crowd_movement.schedule(actors)
        except CrowdMovementReservationError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_spot(
        self,
        mode: str,
        floor_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve a read-only, navigation-backed conversation position."""
        try:
            return self.conversation_spots.resolve_spot(mode, floor_id, **kwargs)
        except ConversationSpotError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_plan(
        self,
        initiator_id: str,
        *,
        partner_id: str | None = None,
        mode: str | None = None,
        snapshot: dict[str, Any] | None = None,
        floor_id: str | None = None,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
        dialogue_locale: str = "en",
        dialogue_category: str | None = None,
        dialogue_seed: str | int = "0",
        gap_cells: int | None = None,
        blocked_cells=None,
        reserved_cells=None,
        origin_uvs=None,
    ) -> dict[str, Any]:
        """Build a deterministic conversation movement plan and lock snapshot."""
        try:
            return self.conversation.plan_conversation(
                initiator_id,
                partner_id=partner_id,
                mode=mode,
                snapshot=snapshot,
                floor_id=floor_id,
                talk_frames=talk_frames,
                timing=timing,
                dialogue_locale=dialogue_locale,
                dialogue_category=dialogue_category,
                dialogue_seed=dialogue_seed,
                gap_cells=gap_cells,
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
                origin_uvs=origin_uvs,
            )
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_automatic_conversation_plan(
        self,
        initiator_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
        selection_seed: str | int = '0',
        dialogue_locale: str = 'en',
        dialogue_seed: str | int | None = None,
        timing: dict[str, Any] | None = None,
        blocked_cells=None,
        reserved_cells=None,
    ) -> dict[str, Any]:
        """Choose a seeded valid conversation mode/partner and build its plan."""
        try:
            return self.conversation.plan_automatic_conversation(
                initiator_id,
                snapshot=snapshot,
                selection_seed=selection_seed,
                dialogue_locale=dialogue_locale,
                dialogue_seed=dialogue_seed,
                timing=timing,
                blocked_cells=blocked_cells,
                reserved_cells=reserved_cells,
            )
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_self_talk(
        self,
        initiator_id: str,
        *,
        snapshot: dict[str, Any] | None = None,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
        dialogue_locale: str = "en",
        dialogue_category: str | None = None,
        dialogue_seed: str | int = "0",
    ) -> dict[str, Any]:
        try:
            return self.conversation.plan_self_talk(
                initiator_id,
                snapshot=snapshot,
                talk_frames=talk_frames,
                timing=timing,
                dialogue_locale=dialogue_locale,
                dialogue_category=dialogue_category,
                dialogue_seed=dialogue_seed,
            )
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_snapshot(self, floor_id: str | None = None) -> dict[str, Any]:
        try:
            return self.conversation.initial_snapshot(floor_id)
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def validate_conversation_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.conversation.validate_snapshot(snapshot)
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_dialogue(
        self,
        *,
        mode: str = "standing_pair",
        participant_ids,
        initiator_id: str,
        locale: str = "en",
        category: str | None = None,
        selection_seed: str | int = "0",
        start_speaker_id: str | None = None,
    ) -> dict[str, Any]:
        """Select one fit-gated line per conversation speaker deterministically."""
        try:
            return self.conversation.resolve_conversation_dialogue(
                mode=mode,
                participant_ids=participant_ids,
                initiator_id=initiator_id,
                locale=locale,
                category=category,
                selection_seed=selection_seed,
                start_speaker_id=start_speaker_id,
            )
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_conversation_timing(
        self,
        *,
        mode: str = "standing_pair",
        participant_ids,
        initiator_id: str,
        talk_frames: int | None = None,
        timing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize duration/loop/speaker tuning without touching world state."""
        try:
            return self.conversation.resolve_conversation_timing(
                mode=mode,
                participant_ids=participant_ids,
                initiator_id=initiator_id,
                talk_frames=talk_frames,
                timing=timing,
            )
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def advance_conversation(
        self,
        snapshot: dict[str, Any],
        plan: dict[str, Any],
        *,
        tick_ms: int = ConversationBehaviorCore.TICK_MS,
    ) -> dict[str, Any]:
        try:
            return self.conversation.advance_conversation(snapshot, plan, tick_ms=tick_ms)
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def cancel_conversation(
        self,
        snapshot: dict[str, Any],
        plan: dict[str, Any],
        *,
        reason: str = "cancelled_by_caller",
    ) -> dict[str, Any]:
        try:
            return self.conversation.cancel_conversation(snapshot, plan, reason=reason)
        except ConversationBehaviorError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_speech_snapshot(
        self,
        actor_snapshot: dict[str, Any] | None = None,
        *,
        floor_id: str | None = None,
        simulation_seed: str = 'gds-speech-scheduler-v1',
        spawned_at_ms: int = 0,
    ) -> dict[str, Any]:
        """Create the independent speech timer/lane snapshot."""
        try:
            return self.speech_scheduler.initial_snapshot(
                actor_snapshot,
                floor_id=floor_id,
                simulation_seed=simulation_seed,
                spawned_at_ms=spawned_at_ms,
            )
        except SpeechSchedulerError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def validate_speech_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.speech_scheduler.validate_snapshot(snapshot)
        except SpeechSchedulerError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def advance_speech_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        actor_snapshot: dict[str, Any] | None = None,
        conversation_snapshot: dict[str, Any] | None = None,
        commands=None,
        dialogue_locale: str = 'en',
        dialogue_seed: str | int = '0',
    ) -> dict[str, Any]:
        """Advance speech timers without advancing pose, movement or stamina."""
        try:
            return self.speech_scheduler.advance_snapshot(
                snapshot,
                elapsed_ms,
                actor_snapshot=actor_snapshot,
                conversation_snapshot=conversation_snapshot,
                commands=commands,
                dialogue_locale=dialogue_locale,
                dialogue_seed=dialogue_seed,
            )
        except SpeechSchedulerError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def resolve_runtime_snapshot(
        self,
        floor_id: str | None = None,
        *,
        simulation_seed: str = 'gds-speech-scheduler-v1',
    ) -> dict[str, Any]:
        """Compose actor/stamina and speech state while keeping their clocks separate."""
        actor_snapshot = self.resolve_actor_snapshot(floor_id)
        speech_snapshot = self.resolve_speech_snapshot(
            actor_snapshot,
            simulation_seed=simulation_seed,
        )
        conversation_snapshot = self.resolve_conversation_snapshot(floor_id)
        return self.validate_runtime_snapshot({
            'schema': 'gds.runtime_snapshot.v1',
            'version': '1.0.0',
            'actor_snapshot': actor_snapshot,
            'speech_snapshot': speech_snapshot,
            'conversation_snapshot': conversation_snapshot,
        })

    def validate_runtime_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Validate the composed actor/speech/conversation channels together."""
        if not isinstance(snapshot, dict):
            raise CentralGameCoreError('runtime snapshot must be an object')
        if snapshot.get('schema') != 'gds.runtime_snapshot.v1':
            raise CentralGameCoreError('runtime snapshot has an unsupported schema')
        if snapshot.get('version') != '1.0.0':
            raise CentralGameCoreError('runtime snapshot has an unsupported version')
        actor_snapshot = snapshot.get('actor_snapshot')
        speech_snapshot = snapshot.get('speech_snapshot')
        conversation_snapshot = snapshot.get('conversation_snapshot')
        if not all(isinstance(value, dict) for value in (
            actor_snapshot, speech_snapshot, conversation_snapshot
        )):
            raise CentralGameCoreError(
                'runtime snapshot needs actor_snapshot, speech_snapshot and conversation_snapshot'
            )
        try:
            actor_snapshot = self.actor_simulation.validate_snapshot(actor_snapshot)
            speech_snapshot = self.speech_scheduler.validate_snapshot(speech_snapshot)
            conversation_snapshot = self.conversation.validate_snapshot(conversation_snapshot)
        except (ActorSimulationError, SpeechSchedulerError, ConversationBehaviorError) as exc:
            raise CentralGameCoreError(str(exc)) from exc
        actor_ids = set(actor_snapshot.get('actors', {}))
        speech_ids = set(speech_snapshot.get('actors', {}))
        conversation_ids = set(conversation_snapshot.get('actors', {}))
        if actor_ids != speech_ids or actor_ids != conversation_ids:
            raise CentralGameCoreError(
                'runtime snapshot actor maps must contain the same employee IDs'
            )
        return {
            'schema': 'gds.runtime_snapshot.v1',
            'version': '1.0.0',
            'actor_snapshot': actor_snapshot,
            'speech_snapshot': speech_snapshot,
            'conversation_snapshot': conversation_snapshot,
        }

    def advance_runtime_snapshot(
        self,
        snapshot: dict[str, Any],
        elapsed_ms: int,
        *,
        actor_commands=None,
        speech_commands=None,
        dialogue_locale: str = 'en',
        dialogue_seed: str | int = '0',
        validate: bool = True,
    ) -> dict[str, Any]:
        """Advance the authoritative actor/speech loop in deterministic slices.

        The actor reducer owns activity, locomotion and stamina.  Speech owns
        lane timing and dialogue selection.  A talk request is accepted only
        after the speech lane has a valid plan; Central then commits that plan
        back into the actor reducer (outbound route, hold/emotion boundary and
        return route).  Keeping the bridge at the shared 60 ms boundary avoids
        the old failure mode where speech showed a conversation while the
        actor had already returned to ``working`` at its workstation.
        """
        # The public/default path validates and copy-isolates every channel.
        # A trusted presentation host can opt into the in-place path after it
        # has validated the initial snapshot, avoiding repeated deep copies of
        # long talk route plans on every visual tick.
        runtime_snapshot = self.validate_runtime_snapshot(snapshot) if validate else snapshot
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, int) or elapsed_ms < 0:
            raise CentralGameCoreError("elapsed_ms must be an integer >= 0")

        actor_snapshot = runtime_snapshot['actor_snapshot']
        speech_snapshot = runtime_snapshot['speech_snapshot']
        conversation_snapshot = runtime_snapshot['conversation_snapshot']
        pending_actor_commands = list(actor_commands or [])
        pending_speech_commands = list(speech_commands or [])
        actor_events_all: list[dict[str, Any]] = []
        speech_events_all: list[dict[str, Any]] = []
        started_session_ids: set[str] = set()
        remaining = int(elapsed_ms)
        first_slice = True

        def _bridge_from_actor_events(
            actor_events: list[dict[str, Any]],
            commands: list[dict[str, Any]],
        ) -> list[dict[str, Any]]:
            bridge = list(commands)
            bridge_keys = {
                (command.get("type"), command.get("employee_id"))
                for command in bridge
                if isinstance(command, dict)
            }
            crossed: set[str] = set()
            for event in actor_events:
                employee_id = event.get("employee_id")
                if not isinstance(employee_id, str):
                    continue
                event_type = event.get("type")
                if event_type == "behavior_started" and event.get("behavior") == "talk":
                    key = ("behavior_started", employee_id)
                    if key not in bridge_keys:
                        bridge.append({
                            "type": "behavior_started",
                            "employee_id": employee_id,
                            "behavior": "talk",
                            "effective_at_ms": int(event.get("timestamp_ms", 0)),
                        })
                        bridge_keys.add(key)
                elif event_type in {"workseat_reentered", "talk_returned"}:
                    key = ("returned_to_work", employee_id)
                    if key not in bridge_keys:
                        bridge.append({
                            "type": "returned_to_work",
                            "employee_id": employee_id,
                        })
                        bridge_keys.add(key)
                elif event_type == "talk_cancelled":
                    key = ("cancel_talk", employee_id)
                    if key not in bridge_keys:
                        bridge.append({
                            "type": "cancel_talk",
                            "employee_id": employee_id,
                        })
                        bridge_keys.add(key)
                elif event_type == "actor_route_sample" and event.get("phase") in {
                    "to_portal", "portal_exit"
                } and employee_id not in crossed:
                    ground_xy = event.get("ground_xy")
                    actor = actor_snapshot.get("actors", {}).get(employee_id)
                    if (
                        isinstance(ground_xy, (list, tuple))
                        and len(ground_xy) == 2
                        and isinstance(actor, dict)
                    ):
                        if self.actor_draws_over_reception(
                            actor["assignment"]["floor_id"],
                            ground_xy,
                        ):
                            key = ("reception_depth_crossed", employee_id)
                            if key not in bridge_keys:
                                bridge.append({
                                    "type": "reception_depth_crossed",
                                    "employee_id": employee_id,
                                    "draws_over_reception": True,
                                    "effective_at_ms": int(event.get("timestamp_ms", 0)),
                                })
                                bridge_keys.add(key)
                            crossed.add(employee_id)
            return bridge

        def _talk_commands_from_speech_events(
            speech_events: list[dict[str, Any]],
            speech_state: dict[str, Any],
        ) -> list[dict[str, Any]]:
            commands: list[dict[str, Any]] = []
            for event in speech_events:
                if event.get("type") != "speech_session_started":
                    continue
                session_id = event.get("session_id")
                if not isinstance(session_id, str) or session_id in started_session_ids:
                    continue
                session = speech_state.get("active_sessions", {}).get(session_id)
                if not isinstance(session, dict) or session.get("kind") not in {"pair", "solo"}:
                    continue
                participants = [
                    str(value) for value in session.get("participants", [])
                    if isinstance(value, str)
                ]
                if not participants:
                    continue
                plan = session.get("conversation_plan")
                if plan is not None and not isinstance(plan, dict):
                    continue
                mode = str(session.get("mode") or ("self_talk" if len(participants) == 1 else "standing_pair"))
                initiator_id = str(session.get("initiator_id") or participants[0])
                partner_id = session.get("partner_id")
                if partner_id is not None:
                    partner_id = str(partner_id)
                movement_started = int(session.get("movement_started_ms", session.get("start_ms", 0)))
                movement_arrival = int(session.get("movement_arrival_ms", movement_started))
                talk_end = int(session.get("fade_end_ms", movement_arrival))
                emotion = session.get("emotion_outcome")
                emotion_hold = int(session.get("emotion_hold_ms", 0) or 0)
                return_start = talk_end + emotion_hold
                route_map = plan.get("route_info", {}) if isinstance(plan, dict) else {}
                endpoint_map = plan.get("endpoint_by_actor", {}) if isinstance(plan, dict) else {}
                for employee_id in participants:
                    route_info = route_map.get(employee_id) if isinstance(route_map, dict) else None
                    endpoint = endpoint_map.get(employee_id) if isinstance(endpoint_map, dict) else None
                    role = "initiator" if employee_id == initiator_id else "participant"
                    if mode == "self_talk":
                        role = "initiator"
                    command: dict[str, Any] = {
                        "type": "start_talk_session",
                        "employee_id": employee_id,
                        "session_id": session_id,
                        "mode": mode,
                        "role": role,
                        "partner_id": partner_id,
                        "recovery_owner": employee_id == initiator_id,
                        "effective_at_ms": movement_started,
                        "talk_start_at_ms": movement_arrival,
                        "talk_end_at_ms": talk_end,
                        "return_start_at_ms": return_start,
                        "emotion": emotion if emotion in {"sad", "happy"} else None,
                        "emotion_until_at_ms": return_start if emotion in {"sad", "happy"} else None,
                        "endpoint_uv": endpoint,
                    }
                    if isinstance(route_info, dict):
                        command["route_info"] = route_info
                    commands.append(command)
                started_session_ids.add(session_id)
            return commands

        try:
            while first_slice or remaining > 0:
                step_ms = min(self.actor_simulation.TICK_MS, remaining)
                actor_result = self.actor_simulation.advance_snapshot(
                    actor_snapshot,
                    step_ms,
                    commands=(pending_actor_commands if first_slice else None),
                    validate=validate,
                )
                actor_snapshot = actor_result["snapshot"]
                chunk_actor_events = list(actor_result.get("events", []))
                bridge_commands = _bridge_from_actor_events(
                    chunk_actor_events,
                    pending_speech_commands if first_slice else [],
                )
                speech_result = self.speech_scheduler.advance_snapshot(
                    speech_snapshot,
                    step_ms,
                    actor_snapshot=actor_snapshot,
                    conversation_snapshot=conversation_snapshot,
                    commands=bridge_commands,
                    dialogue_locale=dialogue_locale,
                    dialogue_seed=dialogue_seed,
                    validate=validate,
                )
                speech_snapshot = speech_result["snapshot"]
                chunk_speech_events = list(speech_result.get("events", []))

                # Speech chooses the shared standing-pair outcome; the actor
                # reducer remains the sole owner of numeric stamina mutation.
                for speech_event in chunk_speech_events:
                    if speech_event.get("type") != "emotion_started":
                        continue
                    emotion = speech_event.get("emotion")
                    participants = speech_event.get("participants", [])
                    if not isinstance(emotion, str) or not isinstance(participants, list):
                        continue
                    for employee_id in participants:
                        if not isinstance(employee_id, str):
                            continue
                        effect_result = self.actor_simulation.apply_emotion_effect(
                            actor_snapshot,
                            employee_id,
                            emotion,
                            timestamp_ms=int(speech_event.get("timestamp_ms", 0)),
                            source_session_id=(
                                str(speech_event.get("session_id"))
                                if speech_event.get("session_id") is not None else None
                            ),
                        )
                        actor_snapshot = effect_result["snapshot"]
                        chunk_actor_events.extend(effect_result.get("events", []))

                # Commit every newly accepted pair/solo plan into actor state.
                talk_commands = _talk_commands_from_speech_events(
                    chunk_speech_events,
                    speech_snapshot,
                )
                if talk_commands:
                    accepted = self.actor_simulation.advance_snapshot(
                        actor_snapshot,
                        0,
                        commands=talk_commands,
                        validate=validate,
                    )
                    actor_snapshot = accepted["snapshot"]
                    chunk_actor_events.extend(accepted.get("events", []))

                # A talk return can finish in the same actor slice in which the
                # speech lane was advanced.  Feed that completion back without
                # advancing the speech clock, then commit any newly-started
                # non-lifecycle plan on the next pass through the same helper.
                return_commands = _bridge_from_actor_events(chunk_actor_events, [])
                return_commands = [
                    command for command in return_commands
                    if command.get("type") == "returned_to_work"
                ]
                if return_commands:
                    speech_return = self.speech_scheduler.advance_snapshot(
                        speech_snapshot,
                        0,
                        actor_snapshot=actor_snapshot,
                        conversation_snapshot=conversation_snapshot,
                        commands=return_commands,
                        dialogue_locale=dialogue_locale,
                        dialogue_seed=dialogue_seed,
                        validate=validate,
                    )
                    speech_snapshot = speech_return["snapshot"]
                    return_events = list(speech_return.get("events", []))
                    chunk_speech_events.extend(return_events)
                    late_talk_commands = _talk_commands_from_speech_events(
                        return_events,
                        speech_snapshot,
                    )
                    if late_talk_commands:
                        accepted = self.actor_simulation.advance_snapshot(
                            actor_snapshot,
                            0,
                            commands=late_talk_commands,
                            validate=validate,
                        )
                        actor_snapshot = accepted["snapshot"]
                        chunk_actor_events.extend(accepted.get("events", []))

                actor_events_all.extend(chunk_actor_events)
                speech_events_all.extend(chunk_speech_events)
                remaining -= step_ms
                first_slice = False

            actor_events_all.sort(key=lambda event: int(event.get("event_index", 0)))
            speech_events_all.sort(key=lambda event: (int(event.get("timestamp_ms", 0)), int(event.get("event_index", 0))))
            events = [
                {'source': 'actor', **event} for event in actor_events_all
            ] + [
                {'source': 'speech', **event} for event in speech_events_all
            ]
            events.sort(key=lambda event: (
                int(event.get('timestamp_ms', 0)),
                event.get('source', ''),
                int(event.get('event_index', 0)),
            ))
        except (ActorSimulationError, SpeechSchedulerError) as exc:
            raise CentralGameCoreError(str(exc)) from exc

        return {
            'schema': 'gds.runtime_snapshot.v1',
            'version': '1.0.0',
            'actor_snapshot': actor_snapshot,
            'speech_snapshot': speech_snapshot,
            'conversation_snapshot': conversation_snapshot,
            'events': events,
            'actor_events': actor_events_all,
            'speech_events': speech_events_all,
        }

    def serialize_runtime_snapshot(self, snapshot: dict[str, Any]) -> str:
        """Encode a validated runtime snapshot for caller-owned storage."""
        try:
            return self.runtime_persistence.snapshot_to_json(snapshot)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def deserialize_runtime_snapshot(
        self,
        payload: str | bytes | bytearray | dict[str, Any],
    ) -> dict[str, Any]:
        """Load/validate a snapshot saved by :meth:`serialize_runtime_snapshot`."""
        try:
            return self.runtime_persistence.snapshot_from_json(payload)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def build_runtime_replay(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build a JSON-safe replay package from explicit host steps."""
        try:
            return self.runtime_persistence.build_replay(initial_snapshot, steps)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def serialize_runtime_replay(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> str:
        try:
            return self.runtime_persistence.replay_to_json(initial_snapshot, steps)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def replay_runtime_snapshot(
        self,
        initial_snapshot: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Replay explicit steps and return the final snapshot plus event trace."""
        try:
            return self.runtime_persistence.replay(initial_snapshot, steps)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def replay_runtime_package(
        self,
        payload: str | bytes | dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.runtime_persistence.replay_package(payload)
        except RuntimePersistenceError as exc:
            raise CentralGameCoreError(str(exc)) from exc

    def _runtime_frame_count(
        self,
        actor: dict[str, Any],
        *,
        action: str,
        direction: str,
        subaction: str | None,
    ) -> int:
        """Resolve a frame count without making presentation state authoritative."""
        try:
            return max(1, len(self.characters.render(
                actor['character_id'], action, direction, subaction
            ).frames))
        except (CharacterSystemError, KeyError, TypeError, ValueError):
            # A render-state read should not make a valid simulation snapshot
            # unusable.  The canonical action resolver remains the owner of
            # hard validation; this facade falls back to a single frame for
            # an incomplete/temporary presentation request.
            return 1

    def _runtime_base_render_actor(
        self,
        actor: dict[str, Any],
        *,
        sample_ms: int,
    ) -> dict[str, Any]:
        """Build the renderer-facing baseline for one actor.

        The actor reducer owns activity, stamina and routes.  This method only
        derives a read-only visual record; speech/conversation overlays are
        applied afterwards and never written back to the simulation snapshot.
        """
        assignment = actor['assignment']
        position = actor.get('position', {})
        route = position.get('route')
        presence = str(actor.get('presence'))
        visible = presence != 'home'
        if isinstance(route, dict):
            render_owner = str(route.get('render_owner') or 'walking_depth')
            action = str(route.get('action') or 'move')
            subaction = str(route.get('subaction') or 'idle')
            direction = str(
                route.get('direction') or route.get('raw_direction') or assignment.get('facing') or 'SE'
            ).upper()
            ground_xy = copy.deepcopy(position.get('ground_xy'))
            current_uv = copy.deepcopy(position.get('uv'))
            visibility_alpha = float(route.get('visibility_alpha', 1.0))
            frame_clock_ms = int(route.get('elapsed_ms', 0))
        elif visible:
            render_owner = 'work_seat'
            action = 'work'
            subaction = 'normal_work'
            direction = str(assignment.get('facing') or 'SE').upper()
            ground_xy = None
            current_uv = None
            visibility_alpha = 1.0
            # Work animation is anchored to the actor reducer's persisted
            # normal-work loop phase.  This keeps a critical actor visibly in
            # the same worknormal pose until its loop boundary, even when a
            # host renders a saved snapshot at a different wall-clock sample.
            frame_clock_ms = int(
                actor.get('behavior', {}).get('work_loop_elapsed_ms', sample_ms)
            )
        else:
            render_owner = 'none'
            action = None
            subaction = None
            direction = str(assignment.get('facing') or 'SE').upper()
            ground_xy = None
            current_uv = None
            visibility_alpha = 0.0
            frame_clock_ms = 0

        frame_count = self._runtime_frame_count(
            actor,
            action=action,
            direction=direction,
            subaction=subaction,
        ) if action is not None else 1
        row: dict[str, Any] = {
            'employee_id': actor['employee_id'],
            'character_id': actor['character_id'],
            'floor_id': assignment['floor_id'],
            'workstation_id': assignment['workstation_id'],
            'slot_id': assignment['slot_id'],
            'assignment_order': assignment['assignment_order'],
            'assignment_retained': True,
            'presence': presence,
            'activity': actor.get('activity'),
            'stamina': copy.deepcopy(actor.get('stamina')),
            'render_owner': render_owner,
            'visible': bool(visible and visibility_alpha > 0),
            'visibility_alpha': round(max(0.0, min(1.0, visibility_alpha)), 4),
            'action': action,
            'direction': direction,
            'subaction': subaction,
            'current_uv': current_uv,
            'ground_xy': ground_xy,
            'frame_index': (frame_clock_ms // 360) % frame_count if action is not None else 0,
            'character_frame_index': (frame_clock_ms // 360) % frame_count if action is not None else 0,
            'character_frame_ms': 360,
            'pc_frame_index': (frame_clock_ms // 720) % 5 if render_owner == 'work_seat' else None,
            'pc_frame_ms': 720,
            'dialogue_visible': False,
            'dialogue_opacity': 0.0,
            'dialogue_phase': 'hidden',
            'dialogue_id': None,
            'dialogue_line_index': None,
            'dialogue_text': None,
            'dialogue_locale': None,
            'dialogue_bubble_offset_px': [0, 0],
            'presentation_phase': None,
            'speech_session_id': None,
            'speech_mode': None,
            'speech_category': None,
            'channels': {},
        }

        active_event = actor.get('behavior', {}).get('active_event')
        if active_event in {'background_effect', 'popup'} and visible:
            try:
                employee = self.employee_metadata.get(actor['employee_id'])
                binding = self.actor_simulation._presentation_for_behavior(
                    employee,
                    active_event,
                    counter=int(actor.get('behavior', {}).get('event_counter', 0)),
                )
            except (EmployeeMetadataError, ActorSimulationError, KeyError, TypeError, ValueError):
                binding = None
            if isinstance(binding, dict):
                channel = str(binding.get('channel'))
                channel_payload = copy.deepcopy(binding)
                elapsed = max(0, int(sample_ms) - int(
                    actor.get('behavior', {}).get('activity_started_ms', sample_ms)
                ))
                if channel == 'vfx':
                    channel_payload['effect_frame_index'] = (elapsed // 240)
                    channel_payload['effect_frame_ms'] = 240
                elif channel == 'humanball':
                    channel_payload['humanball_frame_index'] = (elapsed // 240)
                    channel_payload['humanball_frame_ms'] = 240
                row['channels'][channel] = channel_payload
        return row

    @staticmethod
    def _runtime_timeline_row(plan: dict[str, Any], relative_ms: int) -> dict[str, Any] | None:
        timeline = plan.get('timeline')
        if not isinstance(timeline, list) or not timeline:
            return None
        rows = [row for row in timeline if isinstance(row, dict)]
        if not rows:
            return None
        prior = [row for row in rows if int(row.get('timestamp_ms', 0)) <= int(relative_ms)]
        return copy.deepcopy(prior[-1] if prior else rows[0])

    @staticmethod
    def _runtime_bubble_from_schedule(
        session: dict[str, Any],
        employee_id: str,
        *,
        sample_ms: int,
    ) -> dict[str, Any] | None:
        for item in session.get('bubble_schedule', []):
            if item.get('employee_id') != employee_id:
                continue
            start_ms = int(item.get('start_ms', session.get('bubble_start_ms', 0)))
            visible_end_ms = int(item.get(
                'visible_end_ms', start_ms + SpeechSchedulerCore.BUBBLE_VISIBLE_MS
            ))
            fade_end_ms = int(item.get(
                'fade_end_ms', visible_end_ms + SpeechSchedulerCore.BUBBLE_FADE_MS
            ))
            if sample_ms < start_ms or sample_ms >= fade_end_ms:
                continue
            if sample_ms <= visible_end_ms:
                opacity = 1.0
                phase = 'visible'
            else:
                opacity = max(0.0, min(1.0, 1.0 - (
                    (sample_ms - visible_end_ms) / max(1, fade_end_ms - visible_end_ms)
                )))
                phase = 'fading' if opacity > 0 else 'hidden'
            dialogue = item.get('dialogue')
            if not isinstance(dialogue, dict):
                plan = session.get('conversation_plan')
                plan_lines = plan.get('dialogue_by_actor') if isinstance(plan, dict) else None
                dialogue = plan_lines.get(employee_id) if isinstance(plan_lines, dict) else None
            if not isinstance(dialogue, dict):
                dialogue = {}
            return {
                'dialogue_visible': opacity > 0,
                'dialogue_opacity': round(opacity, 4),
                'dialogue_phase': phase,
                'turn_index': int(item.get('turn_index', 0)),
                'speaker_id': employee_id,
                'dialogue_id': dialogue.get('dialogue_id'),
                'dialogue_line_index': dialogue.get('line_index'),
                'dialogue_text': dialogue.get('text'),
                'dialogue_locale': dialogue.get('locale'),
            }
        return None

    def resolve_runtime_presentation(
        self,
        runtime_snapshot: dict[str, Any],
        *,
        at_ms: int | None = None,
        floor_id: str | None = None,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Materialize a read-only render snapshot from the three runtime channels.

        Actor/stamina state and speech timing stay independent.  The only
        cross-channel operation is selecting the active conversation track at
        the speech sample time and overlaying its pose/bubble fields on the
        actor's baseline render record.  This is the seam a real renderer can
        consume each frame without mutating gameplay state or workstation
        ownership.
        """
        runtime = (
            self.validate_runtime_snapshot(runtime_snapshot)
            if validate else runtime_snapshot
        )
        actor_snapshot = runtime['actor_snapshot']
        speech_snapshot = runtime['speech_snapshot']
        actor_clock_ms = int(actor_snapshot['clock']['simulation_time_ms'])
        speech_clock_ms = int(speech_snapshot['clock']['simulation_time_ms'])
        if at_ms is None:
            actor_sample_ms = actor_clock_ms
            speech_sample_ms = speech_clock_ms
        else:
            if isinstance(at_ms, bool) or not isinstance(at_ms, int) or at_ms < 0:
                raise CentralGameCoreError('at_ms must be an integer >= 0')
            actor_sample_ms = int(at_ms)
            speech_sample_ms = int(at_ms)

        actors = {
            employee_id: self._runtime_base_render_actor(
                actor,
                sample_ms=actor_sample_ms,
            )
            for employee_id, actor in actor_snapshot['actors'].items()
            if floor_id is None or actor['assignment']['floor_id'] == str(floor_id)
        }
        sessions: list[dict[str, Any]] = []
        active_ids = set(speech_snapshot.get('active_sessions', {}))
        all_sessions = list(speech_snapshot.get('active_sessions', {}).values())
        all_sessions += list(speech_snapshot.get('completed_sessions', {}).values())
        # Apply older return tracks first so a newer speech session wins if a
        # caller deliberately starts it as soon as the lane's fade lock ends.
        all_sessions.sort(key=lambda item: (
            int(item.get('movement_started_ms', item.get('start_ms', 0))),
            str(item.get('session_id', '')),
        ))
        for session in all_sessions:
            if not isinstance(session, dict):
                continue
            if floor_id is not None and session.get('floor_id') != str(floor_id):
                continue
            participants = [
                employee_id for employee_id in session.get('participants', [])
                # A lifecycle bubble can outlive the final portal fade by a
                # few host ticks.  Do not keep painting a hidden home actor:
                # its baseline row intentionally has no character/action,
                # and the presentation lane must end with the portal exit.
                if employee_id in actors
                and actors[employee_id].get('visible')
                and isinstance(actors[employee_id].get('character_id'), str)
                and isinstance(actors[employee_id].get('action'), str)
            ]
            if not participants:
                continue
            origin_ms = int(session.get(
                'movement_started_ms', session.get('start_ms', 0)
            ))
            relative_ms = speech_sample_ms - origin_ms
            if relative_ms < 0:
                continue
            plan = session.get('conversation_plan')
            # Lifecycle lines (greeting/work-start/fatigue/leaving) may use a
            # self-talk plan solely to select localized text.  Their visual
            # pose must remain the actor reducer's current route/WorkSeat
            # state, so only pair/solo plans drive a timeline overlay.
            plan_for_overlay = plan if session.get('kind') != 'lifecycle' else None
            plan_row = (
                self._runtime_timeline_row(plan_for_overlay, relative_ms)
                if isinstance(plan_for_overlay, dict) and plan_for_overlay.get('ready') else None
            )
            plan_end = None
            if (
                isinstance(plan_for_overlay, dict)
                and isinstance(plan_for_overlay.get('timeline'), list)
                and plan_for_overlay['timeline']
            ):
                plan_end = max(
                    int(row.get('timestamp_ms', 0))
                    for row in plan_for_overlay['timeline']
                )
            if plan_end is not None and relative_ms > plan_end:
                continue
            if plan_end is None and session.get('session_id') not in active_ids:
                if speech_sample_ms >= int(session.get('fade_end_ms', 0)):
                    continue
            sessions.append({
                'session_id': session.get('session_id'),
                'floor_id': session.get('floor_id'),
                'kind': session.get('kind'),
                'mode': session.get('mode'),
                'category': session.get('category'),
                'participants': participants,
                'relative_ms': relative_ms,
                'status': 'active' if session.get('session_id') in active_ids else 'returning',
            })
            if plan_row and isinstance(plan_row.get('actors'), dict):
                source_rows = plan_row['actors']
                for employee_id in participants:
                    track = source_rows.get(employee_id)
                    if not isinstance(track, dict):
                        continue
                    row = actors[employee_id]
                    source_actor = actor_snapshot['actors'].get(employee_id, {})
                    authoritative_talk = (
                        isinstance(source_actor.get('behavior', {}).get('talk'), dict)
                        if isinstance(source_actor, dict) else False
                    )
                    authoritative_route = (
                        isinstance(source_actor.get('position', {}).get('route'), dict)
                        if isinstance(source_actor, dict) else False
                    )
                    # Dialogue timing/layout still comes from the planner, but
                    # a committed actor talk route is the sole source of
                    # locomotion and pose.  Copying the old presentation track
                    # here would snap a walking actor back to the workstation
                    # on every render sample.
                    presentation_keys = (
                        'dialogue_visible', 'dialogue_opacity', 'dialogue_phase',
                        'dialogue_id', 'dialogue_line_index', 'dialogue_text',
                        'dialogue_locale', 'dialogue_bubble_offset_px',
                        'speaker_id', 'listener_id', 'loop_index', 'turn_index',
                    )
                    pose_keys = (
                        'phase', 'current_uv', 'ground_xy', 'path_cells_uv',
                        'direction', 'raw_direction', 'render_owner', 'action',
                        'subaction', 'frame_index', 'cumulative_distance_px',
                    )
                    keys = presentation_keys + (
                        () if authoritative_talk and authoritative_route else pose_keys
                    )
                    for key in keys:
                        if key in track:
                            row[key] = copy.deepcopy(track[key])
                    if row.get('action') in {'move', 'idle'} and 'subaction' not in track:
                        row['subaction'] = 'idle'
                    row['visible'] = bool(
                        row.get('render_owner') != 'none'
                        and float(row.get('visibility_alpha', 1.0)) > 0
                    )
                    row['presentation_phase'] = (
                        source_actor.get('conversation_phase')
                        if authoritative_talk and authoritative_route
                        else track.get('phase')
                    )
                    row['speech_session_id'] = session.get('session_id')
                    row['speech_mode'] = session.get('mode')
                    row['speech_category'] = session.get('category')
            else:
                bindings = session.get('pose_bindings', {})
                for employee_id in participants:
                    binding = bindings.get(employee_id) if isinstance(bindings, dict) else None
                    if isinstance(binding, dict):
                        actors[employee_id].update({
                            key: copy.deepcopy(binding[key])
                            for key in ('render_owner', 'action', 'subaction')
                            if key in binding
                        })
                    bubble = self._runtime_bubble_from_schedule(
                        session,
                        employee_id,
                        sample_ms=speech_sample_ms,
                    )
                    if bubble:
                        actors[employee_id].update(bubble)
                    actors[employee_id]['speech_session_id'] = session.get('session_id')
                    actors[employee_id]['speech_mode'] = session.get('mode')
                    actors[employee_id]['speech_category'] = session.get('category')

        # A completed standing-pair session may be in the shared emotion hold
        # after the lane is released.  Keep its pose visible until the plan's
        # return track takes over, using the speech state as the gate.
        for employee_id, speech_actor in speech_snapshot.get('actors', {}).items():
            if employee_id not in actors or speech_actor.get('speech_phase') != 'emotion':
                continue
            emotion = speech_actor.get('emotion')
            if emotion not in {'sad', 'happy'}:
                continue
            actors[employee_id].update({
                'render_owner': 'walking_depth',
                'action': emotion,
                'subaction': emotion,
                'visible': True,
                'presentation_phase': 'emotion',
                'emotion': emotion,
                'speech_session_id': speech_actor.get('last_session_id'),
            })

        character_order = sorted(
            actors,
            key=lambda employee_id: (
                1 if actors[employee_id].get('ground_xy') is None else 0,
                float((actors[employee_id].get('ground_xy') or [0, 0])[1]),
                int(actors[employee_id].get('assignment_order', 0)),
                employee_id,
            ),
        )
        bubble_order = sorted(
            (
                employee_id for employee_id, actor in actors.items()
                if actor.get('dialogue_visible')
            ),
            key=lambda employee_id: (
                int(actors[employee_id].get('turn_index', 0)), employee_id
            ),
        )
        return {
            'schema': 'gds.runtime_presentation_snapshot.v1',
            'version': '1.0.0',
            'clock': {
                'actor_sample_ms': actor_sample_ms,
                'speech_sample_ms': speech_sample_ms,
                'actor_clock_ms': actor_clock_ms,
                'speech_clock_ms': speech_clock_ms,
                'tick_ms': 60,
            },
            'timing_ms': {
                'simulation_tick': 60,
                'character_frame': 360,
                'effect_frame': 240,
                'humanball_frame': 240,
                'bubble_visible': 4000,
                'bubble_fade': 300,
            },
            'dialogue_layout_policy': 'direct_head_anchor_overlay_paint_order',
            'actors': actors,
            'active_speech_sessions': sessions,
            'paint_order': {
                'characters': character_order,
                'dialogue_bubbles': bubble_order,
            },
        }

    def render_floor_with_work_effects(
        self,
        floor_id: str,
        assignments: list[dict[str, Any]],
        *,
        frame_index: int = 0,
        character_frame_index: int | None = None,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
        pc_frame_index: int | None = None,
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
                pc_frame_index=pc_frame_index,
            )
        except (WorkSeatError, KeyError, ValueError) as exc:
            raise CentralGameCoreError(str(exc)) from exc
