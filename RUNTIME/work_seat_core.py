from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from CHARACTER.RUNTIME.character_system import CharacterSystem
from WORLD.RUNTIME.chair_family_core import ChairFamilyCore
from WORLD.RUNTIME.direction_core import DirectionCore
from WORLD.RUNTIME.layout_core import LayoutCore


class WorkSeatError(ValueError):
    pass


@dataclass
class WorkSeatRenderResult:
    character_id: str
    chair_family_id: str
    direction: str
    subaction: str
    frame_ids: list[str]
    frames: list[Image.Image]
    loop: bool
    viewport: tuple[int, int, int, int]
    chair_asset_id: str
    foreground_asset_id: str | None
    human_offset_from_chair_px: tuple[int, int]
    used_foreground: bool
    derived_from: str | None = None
    transform: str | None = None


@dataclass
class WorkPresentationResult:
    character_id: str
    direction: str
    subaction: str
    frame_ids: list[str]
    frames: list[Image.Image]
    loop: bool
    viewport: tuple[int, int, int, int]
    derived_from: str | None = None
    transform: str | None = None


class WorkSeatCore:
    SUPPORTED_DIRECTIONS = frozenset({'SE', 'SW', 'NW', 'NE'})
    PC_ANIMATED_DIRECTIONS = frozenset({'NW', 'NE'})
    TURN_SIDE_SUBACTIONS_BY_WORK_DIRECTION = {
        'SE': ('turn_side_sw', 'turn_side_ne'),
        'SW': ('turn_side_se', 'turn_side_nw'),
        'NW': ('turn_side_sw', 'turn_side_ne'),
        'NE': ('turn_side_se', 'turn_side_nw'),
    }
    DERIVED_SOURCE_SUBACTIONS = {
        'SW': {
            'turn_side_se': 'turn_side_sw',
            'turn_side_nw': 'turn_side_ne',
        },
        'NE': {
            'turn_side_se': 'turn_side_sw',
            'turn_side_nw': 'turn_side_ne',
        },
    }

    def __init__(
        self,
        central_root: str | Path,
        *,
        characters: CharacterSystem | None = None,
        world: LayoutCore | None = None,
        directions: DirectionCore | None = None,
    ):
        self.root = Path(central_root).resolve()
        payload = json.loads((self.root / 'CONTRACTS' / 'work_pose_profiles.json').read_text(encoding='utf-8'))
        self.contract = payload
        self.profiles = payload['profiles']
        self.characters = characters or CharacterSystem(self.root / 'CHARACTER')
        self.world = world or LayoutCore(self.root / 'WORLD')
        self.directions = directions or DirectionCore(self.root / 'WORLD')
        self.chairs = ChairFamilyCore(self.root / 'WORLD')
        effect_payload = json.loads((self.root / 'CHARACTER' / 'EFFECTS' / 'gds_effects_v1.json').read_text(encoding='utf-8'))
        self.effect_work_local_profile = effect_payload['work_local_profile']
        self.effect_work_local_canvas = tuple(self.effect_work_local_profile['canvas'])

    def resolve_profile(self, direction: str) -> dict[str, Any]:
        key = direction.upper()
        if key not in self.SUPPORTED_DIRECTIONS:
            raise WorkSeatError(f'Unsupported work seat direction: {direction}')
        return self.profiles[key]

    def resolve_pc_frame_count(self, direction: str) -> int:
        """Return the authored PC frame count for a work-facing direction.

        The source PC sheets contain one static SE/SW cell and five NW cells.
        NE is derived from NW at workstation composition time, so it uses the
        same five source frames before the final mirror relation.
        """
        key = self._normalize_direction(direction, name='PC work direction')
        if key in self.PC_ANIMATED_DIRECTIONS:
            return 5
        if key in {'SE', 'SW'}:
            return 1
        raise WorkSeatError(f'Unsupported PC work direction: {direction}')

    def _pc_family_id(self, asset_id: str) -> str:
        family_id = str(asset_id).split('.', 1)[0]
        if not family_id.startswith('pc_'):
            raise WorkSeatError(f'Expected a PC asset id, got {asset_id!r}')
        return family_id

    def resolve_pc_frame_asset(
        self,
        seat: dict[str, Any],
        frame_index: int = 0,
    ) -> tuple[str, str, int, int]:
        """Resolve one PC asset/variant for a seated workstation.

        ``frame_index`` is the independent PC animation channel.  Its zero
        value is the authored active slot (cell1) for NW/NE and the static
        cell0 for SE/SW.  The returned index is normalized to the direction's
        frame count so callers can safely pass a monotonically increasing loop
        counter.
        """
        if isinstance(frame_index, bool):
            raise WorkSeatError('PC frame index must be an integer')
        try:
            requested = int(frame_index)
        except (TypeError, ValueError) as exc:
            raise WorkSeatError(f'PC frame index must be an integer: {frame_index!r}') from exc
        if requested < 0:
            raise WorkSeatError('PC frame index must be >= 0')
        direction = self._normalize_direction(seat['direction'], name='PC work direction')
        placement = seat.get('component_placements', {}).get('pc')
        if not isinstance(placement, dict):
            raise WorkSeatError(
                f"{seat.get('floor_id', '<unknown>')}.{seat.get('workstation_id', '<unknown>')}: "
                'missing PC component placement'
            )
        frame_count = self.resolve_pc_frame_count(direction)
        normalized = requested % frame_count
        if direction in self.PC_ANIMATED_DIRECTIONS:
            family_id = self._pc_family_id(placement['asset_id'])
            family = self.world.pc_animation_family(family_id)
            frame_assets = list(family.get('animated_asset_ids', []))
            if len(frame_assets) != frame_count:
                raise WorkSeatError(
                    f'{family_id}: expected {frame_count} animated PC assets, '
                    f'got {len(frame_assets)}'
                )
            asset_id = str(frame_assets[normalized])
            variant_id = self.world.resolve_variant(asset_id, 'NORMAL')
        else:
            asset_id = str(placement['asset_id'])
            variant_id = str(placement['variant_id'])
        return asset_id, variant_id, normalized, frame_count

    def _derived_source_direction(self, direction: str) -> str | None:
        profile = self.resolve_profile(direction)
        if profile.get('mode') != 'derived':
            return None
        source = str(profile.get('derived_from', '')).strip().upper()
        if not source or source == direction.upper():
            raise WorkSeatError(f'{direction} has an invalid derived_from direction')
        if source not in self.SUPPORTED_DIRECTIONS:
            raise WorkSeatError(f'{direction} derives from unsupported direction: {source}')
        return source

    @classmethod
    def _source_subaction(cls, direction: str, subaction: str) -> str:
        return cls.DERIVED_SOURCE_SUBACTIONS.get(direction.upper(), {}).get(subaction, subaction)

    @staticmethod
    def _normalize_direction(value: str, *, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise WorkSeatError(f'{name} must be a non-empty direction string')
        return value.strip().upper()

    def resolve_turn_side_mapping(self, direction: str) -> dict[str, Any]:
        """Resolve the explicit axis meaning of direction-named seated turns.

        The subaction name carries the target idle direction (for example,
        ``turn_side_sw``). This contract supplies the axis/sign and UV delta
        for that direction. No partner position or fallback direction is
        guessed here.
        """
        key = self._normalize_direction(direction, name='work direction')
        profile = self.resolve_profile(key)
        convention = self.contract.get('axis_direction_convention')
        if not isinstance(convention, dict):
            raise WorkSeatError('Work pose contract is missing axis_direction_convention')
        source = profile.get('turn_side_mapping')
        if not isinstance(source, dict):
            raise WorkSeatError(f'{key} profile is missing turn_side_mapping')
        subactions = self.TURN_SIDE_SUBACTIONS_BY_WORK_DIRECTION.get(key)
        if subactions is None:
            raise WorkSeatError(f'{key} has no direction-named turn mapping')

        resolved: dict[str, Any] = {'work_direction': key}
        seen_axis_directions: set[str] = set()
        seen_targets: set[str] = set()
        for subaction in subactions:
            raw = source.get(subaction)
            if not isinstance(raw, dict):
                raise WorkSeatError(f'{key} profile is missing {subaction} axis mapping')

            axis = str(raw.get('axis', '')).strip().upper()
            sign = str(raw.get('sign', '')).strip()
            axis_direction = str(raw.get('axis_direction', '')).strip().upper()
            target = str(raw.get('target_idle_direction', '')).strip().upper()
            if axis not in {'U', 'V'} or sign not in {'+', '-'}:
                raise WorkSeatError(f'{key}/{subaction} has an invalid axis/sign mapping')
            if axis_direction != f'{axis}{sign}':
                raise WorkSeatError(
                    f'{key}/{subaction} axis_direction must match axis/sign: '
                    f'{axis}{sign}, got {axis_direction!r}'
                )
            expected_target = subaction.removeprefix('turn_side_').upper()
            if expected_target not in {'NE', 'SE', 'SW', 'NW'}:
                raise WorkSeatError(f'{key}/{subaction} has an invalid direction-named turn')
            if target != expected_target:
                raise WorkSeatError(
                    f'{key}/{subaction} target idle direction must match subaction name: '
                    f'{expected_target}, got {target!r}'
                )
            if axis_direction in seen_axis_directions:
                raise WorkSeatError(f'{key} turn-side mappings reuse axis direction {axis_direction}')
            if target in seen_targets:
                raise WorkSeatError(f'{key} turn-side mappings reuse target idle direction {target}')
            seen_axis_directions.add(axis_direction)
            seen_targets.add(target)

            canonical = convention.get(axis_direction)
            if not isinstance(canonical, dict):
                raise WorkSeatError(
                    f'{key}/{subaction} references unknown axis direction {axis_direction}'
                )
            if canonical.get('axis') != axis or canonical.get('sign') != sign:
                raise WorkSeatError(
                    f'{key}/{subaction} axis convention disagrees with axis/sign'
                )
            if canonical.get('direction') != target:
                raise WorkSeatError(
                    f'{key}/{subaction} target idle direction {target!r} does not match '
                    f'axis direction {axis_direction}'
                )
            uv_delta = canonical.get('uv_delta')
            if (
                not isinstance(uv_delta, list)
                or len(uv_delta) != 2
                or any(isinstance(value, bool) or not isinstance(value, int) for value in uv_delta)
            ):
                raise WorkSeatError(
                    f'{key}/{subaction} axis direction {axis_direction} has invalid uv_delta'
                )

            resolved[subaction] = {
                'action': 'work',
                'direction': key,
                'subaction': subaction,
                'axis': axis,
                'sign': sign,
                'axis_direction': axis_direction,
                'axis_delta_uv': list(uv_delta),
                'target_idle_direction': target,
                'direction_source': 'turn_axis_mapping',
            }
        return resolved

    def resolve_turn_side_for_target(
        self,
        direction: str,
        target_idle_direction: str,
    ) -> dict[str, Any]:
        """Select the direction-named turn when a target idle direction is known."""
        key = self._normalize_direction(direction, name='work direction')
        target = self._normalize_direction(target_idle_direction, name='target idle direction')
        mapping = self.resolve_turn_side_mapping(key)
        subactions = self.TURN_SIDE_SUBACTIONS_BY_WORK_DIRECTION[key]
        for subaction in subactions:
            entry = mapping[subaction]
            if entry['target_idle_direction'] == target:
                return dict(entry)
        supported = [mapping[subaction]['target_idle_direction'] for subaction in subactions]
        raise WorkSeatError(
            f'{key} does not have a direction-named turn mapping for target idle direction {target}; '
            f'supported={supported}'
        )

    def resolve_world_offset(
        self,
        direction: str,
        *,
        chair_size: tuple[int, int],
        human_size: tuple[int, int],
    ) -> tuple[int, int]:
        key = direction.upper()
        profile = self.resolve_profile(key)
        if profile['mode'] == 'native_verified':
            x, y = profile['visual_character_offset_from_chair_px']
            return int(x), int(y)
        source_direction = self._derived_source_direction(key)
        if source_direction is None:
            raise WorkSeatError(f'Unsupported derived world offset profile: {key}')
        source = self.resolve_profile(source_direction)
        if source.get('mode') != 'native_verified':
            raise WorkSeatError(f'{key} must derive from a native-verified profile: {source_direction}')
        dx, dy = source['visual_character_offset_from_chair_px']
        chair_w, _ = chair_size
        human_w, _ = human_size
        return int(chair_w) - int(dx) - int(human_w), int(dy)

    @staticmethod
    def _viewport_tuple(profile: dict[str, Any]) -> tuple[int, int, int, int]:
        vp = profile['composition_viewport']
        return int(vp['min_x']), int(vp['min_y']), int(vp['max_x']), int(vp['max_y'])

    def _world_viewport(
        self,
        direction: str,
        *,
        chair_size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        key = direction.upper()
        profile = self.resolve_profile(key)
        if profile.get('mode') == 'native_verified':
            return self._viewport_tuple(self.resolve_profile(key))
        source_direction = self._derived_source_direction(key)
        if source_direction is None:
            raise WorkSeatError(f'Unsupported work seat direction: {direction}')
        source = self.resolve_profile(source_direction)
        min_x, min_y, max_x, max_y = self._viewport_tuple(source)
        chair_w, _ = chair_size
        return chair_w - max_x, min_y, chair_w - min_x, max_y

    def _effect_local_offsets(
        self,
        direction: str,
        *,
        human_size: tuple[int, int],
        effect_size: tuple[int, int],
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        key = direction.upper()
        if key in {'NW', 'SE'}:
            node = self.effect_work_local_profile[key]
            return tuple(node['effect_pos']), tuple(node['character_pos'])
        source_direction = {'SW': 'SE', 'NE': 'NW'}.get(key)
        if source_direction is None:
            raise WorkSeatError(f'Unsupported VFX work direction: {direction}')
        canvas_w, _ = self.effect_work_local_canvas
        source = self.effect_work_local_profile[source_direction]
        source_effect = tuple(source['effect_pos'])
        source_character = tuple(source['character_pos'])
        effect_w, _ = effect_size
        human_w, _ = human_size
        effect_pos = (int(canvas_w) - int(source_effect[0]) - int(effect_w), int(source_effect[1]))
        character_pos = (int(canvas_w) - int(source_character[0]) - int(human_w), int(source_character[1]))
        return effect_pos, character_pos

    def resolve_effect_world_position(
        self,
        direction: str,
        *,
        human_top_left_px: tuple[int, int],
        human_size: tuple[int, int],
        effect_size: tuple[int, int],
    ) -> tuple[int, int]:
        effect_pos, character_pos = self._effect_local_offsets(
            direction, human_size=human_size, effect_size=effect_size
        )
        hx, hy = human_top_left_px
        return int(hx) - int(character_pos[0]) + int(effect_pos[0]), int(hy) - int(character_pos[1]) + int(effect_pos[1])

    def _resolve_floor_assignment_data(
        self,
        floor_id: str,
        assignments: list[dict[str, Any]],
        *,
        frame_index: int = 0,
        character_frame_index: int | None = None,
        effect_frame_index: int | None = None,
        humanball_frame_index: int | None = None,
        pc_frame_index: int | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        if frame_index < 0:
            raise WorkSeatError('frame_index must be >= 0')
        if character_frame_index is not None and character_frame_index < 0:
            raise WorkSeatError('character_frame_index must be >= 0')
        if effect_frame_index is not None and effect_frame_index < 0:
            raise WorkSeatError('effect_frame_index must be >= 0')
        if humanball_frame_index is not None and humanball_frame_index < 0:
            raise WorkSeatError('humanball_frame_index must be >= 0')
        character_frame_index = frame_index if character_frame_index is None else int(character_frame_index)
        effect_frame_index = frame_index if effect_frame_index is None else int(effect_frame_index)
        humanball_frame_index = frame_index if humanball_frame_index is None else int(humanball_frame_index)
        by_workstation: dict[str, dict[str, Any]] = {}
        rendered: dict[str, dict[str, Any]] = {}
        for assignment in assignments:
            workstation_id = assignment['workstation_id']
            if workstation_id in by_workstation:
                raise WorkSeatError(f'Duplicate workstation assignment: {workstation_id}')
            character_id = assignment['character_id']
            subaction = assignment.get('subaction', 'normal_work')
            seat = self.resolve_workstation_seat(floor_id, workstation_id)
            action = self.characters.render(character_id, 'work', seat['direction'], subaction)
            if not action.frames:
                raise WorkSeatError(f'{character_id} produced no work frames')
            human = action.frames[character_frame_index % len(action.frames)].convert('RGBA')
            chair = self.world.load_asset(seat['chair_asset_id']).convert('RGBA')
            offset = self.resolve_world_offset(
                seat['direction'], chair_size=chair.size, human_size=human.size
            )
            data = {
                **assignment,
                **seat,
                'subaction': subaction,
                'human': human,
                'human_x_px': seat['chair_x_px'] + offset[0],
                'human_y_px': seat['chair_y_px'] + offset[1],
                'human_offset_from_chair_px': offset,
            }
            requested_pc_frame_index = assignment.get('pc_frame_index')
            if requested_pc_frame_index is None:
                if pc_frame_index is not None:
                    requested_pc_frame_index = pc_frame_index
                else:
                    # ``frame_index`` is the caller's absolute work frame
                    # counter when no independent PC channel is supplied.
                    # Dividing by the action frame count advances the PC only
                    # after a complete looping work action.
                    requested_pc_frame_index = character_frame_index // len(action.frames)
            (
                pc_asset_id,
                pc_variant_id,
                resolved_pc_frame_index,
                pc_frame_count,
            ) = self.resolve_pc_frame_asset(seat, requested_pc_frame_index)
            data.update({
                'pc_frame_index': resolved_pc_frame_index,
                'pc_frame_count': pc_frame_count,
                'pc_asset_id': pc_asset_id,
                'pc_variant_id': pc_variant_id,
                'pc_frame_source': 'pc_animation_registry',
            })
            effect_id = assignment.get('effect_id')
            if effect_id is not None:
                if subaction != 'normal_work':
                    raise WorkSeatError('Work VFX floor composition currently supports only normal_work')
                effect = self.characters.render_effect(effect_id, seat['direction'])
                if not effect.frames:
                    raise WorkSeatError(f'{effect_id} produced no VFX frames')
                effect_frame = effect.frames[effect_frame_index % len(effect.frames)].convert('RGBA')
                effect_x, effect_y = self.resolve_effect_world_position(
                    seat['direction'],
                    human_top_left_px=(data['human_x_px'], data['human_y_px']),
                    human_size=human.size,
                    effect_size=effect_frame.size,
                )
                data.update({
                    'effect_id': effect_id,
                    'effect': effect_frame,
                    'effect_x_px': effect_x,
                    'effect_y_px': effect_y,
                    'effect_frame_ms': int(effect.frame_ms),
                    'effect_frame_count': len(effect.frames),
                })

            humanball_id = assignment.get('humanball_id')
            if humanball_id is not None:
                if subaction != 'normal_work':
                    raise WorkSeatError('HumanBall floor composition currently supports only normal_work')
                popup = self.characters.render_humanball(
                    humanball_id, seat['direction'], human_size=human.size
                )
                if not popup.frames:
                    raise WorkSeatError(f'{humanball_id} produced no HumanBall frames')
                popup_index = humanball_frame_index % len(popup.frames)
                popup_frame = popup.frames[popup_index]
                popup_offset = popup.offsets[popup_index]
                popup_x = popup_y = None
                if popup_frame is not None and popup_offset is not None:
                    popup_frame = popup_frame.convert('RGBA')
                    popup_x = int(data['human_x_px']) + int(popup_offset[0])
                    popup_y = int(data['human_y_px']) + int(popup_offset[1])
                data.update({
                    'humanball_id': humanball_id,
                    'humanball': popup_frame,
                    'humanball_x_px': popup_x,
                    'humanball_y_px': popup_y,
                    'humanball_frame_ms': int(popup.frame_ms),
                    'humanball_frame_count': len(popup.frames),
                    'humanball_visible_frame_count': int(popup.visible_frame_count),
                    'humanball_derived_from': popup.derived_from,
                    'humanball_transform': popup.transform,
                })
            by_workstation[workstation_id] = data
            rendered[seat['chair_placement_id']] = data
        return by_workstation, rendered


    def compose_seat(
        self,
        character_id: str,
        chair_family_id: str,
        direction: str,
        subaction: str = 'normal_work',
    ) -> WorkSeatRenderResult:
        key = direction.upper()
        profile = self.resolve_profile(key)
        if subaction not in self.contract['supported_subactions']:
            raise WorkSeatError(f'Unsupported work subaction: {subaction}')

        # SW keeps its authored chair part (part_02) and therefore retains the
        # established world-seat assembler below.  NE is the complete
        # workstation mirror derived from the native NW seat.
        if key == 'NE' and profile.get('mode') == 'derived':
            source_direction = self._derived_source_direction(key)
            if source_direction is None:
                raise WorkSeatError(f'Unsupported derived work seat profile: {key}')
            source_subaction = self._source_subaction(key, subaction)
            source_result = self.compose_seat(
                character_id,
                chair_family_id,
                source_direction,
                source_subaction,
            )
            target_action = self.characters.render(character_id, 'work', key, subaction)
            if len(source_result.frames) != len(target_action.frames):
                raise WorkSeatError(
                    f'{key}/{subaction} frame count does not match its source '
                    f'{source_direction}/{source_subaction}'
                )
            chair = self.world.load_asset(source_result.chair_asset_id).convert('RGBA')
            human_size = target_action.frames[0].size
            offset = self.resolve_world_offset(
                key,
                chair_size=chair.size,
                human_size=human_size,
            )
            viewport = self._world_viewport(key, chair_size=chair.size)
            return WorkSeatRenderResult(
                character_id=character_id,
                chair_family_id=chair_family_id,
                direction=key,
                subaction=subaction,
                frame_ids=list(target_action.frame_ids),
                frames=[frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in source_result.frames],
                loop=bool(target_action.loop),
                viewport=viewport,
                chair_asset_id=source_result.chair_asset_id,
                foreground_asset_id=source_result.foreground_asset_id,
                human_offset_from_chair_px=offset,
                used_foreground=source_result.used_foreground,
                derived_from=source_direction,
                transform='mirror_relation_within_chair_canvas',
            )

        chair_role = profile['world_chair_role']
        chair_asset_id = self.chairs.resolve_part_asset(chair_family_id, chair_role)
        if chair_asset_id is None:
            raise WorkSeatError(f'{chair_family_id}.{chair_role} is transparent/unavailable')
        chair = self.world.load_asset(chair_asset_id).convert('RGBA')

        foreground_asset_id: str | None = None
        foreground: Image.Image | None = None
        fg_role = profile.get('world_chair_foreground_role')
        if fg_role:
            foreground_asset_id = self.chairs.resolve_part_asset(chair_family_id, fg_role)
            if foreground_asset_id is not None:
                foreground = self.world.load_asset(foreground_asset_id).convert('RGBA')
            elif not profile.get('foreground_optional', False):
                raise WorkSeatError(f'Missing required foreground {chair_family_id}.{fg_role}')

        character_direction = profile.get('world_character_frame_direction', key)
        action = self.characters.render(character_id, 'work', character_direction, subaction)
        if not action.frames:
            raise WorkSeatError('Character action produced no frames')
        human_size = action.frames[0].size
        if any(frame.size != human_size for frame in action.frames):
            raise WorkSeatError('Work action frame sizes are inconsistent')

        offset = self.resolve_world_offset(key, chair_size=chair.size, human_size=human_size)
        viewport = self._world_viewport(key, chair_size=chair.size)
        min_x, min_y, max_x, max_y = viewport
        width, height = max_x - min_x, max_y - min_y
        if width <= 0 or height <= 0:
            raise WorkSeatError(f'Invalid viewport for {key}: {viewport}')
        origin = (-min_x, -min_y)

        frames: list[Image.Image] = []
        for human in action.frames:
            out = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            out.alpha_composite(chair, origin)
            out.alpha_composite(human.convert('RGBA'), (origin[0] + offset[0], origin[1] + offset[1]))
            if foreground is not None:
                out.alpha_composite(foreground, origin)
            frames.append(out)

        return WorkSeatRenderResult(
            character_id=character_id,
            chair_family_id=chair_family_id,
            direction=key,
            subaction=subaction,
            frame_ids=list(action.frame_ids),
            frames=frames,
            loop=bool(action.loop),
            viewport=viewport,
            chair_asset_id=chair_asset_id,
            foreground_asset_id=foreground_asset_id,
            human_offset_from_chair_px=offset,
            used_foreground=foreground is not None,
            derived_from=profile.get('derived_from'),
            transform=(
                'mirror_relation_within_chair_canvas'
                if key == 'SW'
                else None
            ),
        )

    def compose_reference_presentation(
        self,
        character_id: str,
        direction: str,
        subaction: str = 'normal_work',
    ) -> WorkPresentationResult:
        key = direction.upper()
        if subaction not in self.contract['supported_subactions']:
            raise WorkSeatError(f'Unsupported work subaction: {subaction}')

        if key == 'NW':
            seat = self.compose_seat(character_id, 'chair_000', 'NW', subaction)
            return WorkPresentationResult(
                character_id=character_id,
                direction='NW',
                subaction=subaction,
                frame_ids=list(seat.frame_ids),
                frames=[frame.copy() for frame in seat.frames],
                loop=seat.loop,
                viewport=seat.viewport,
            )

        if key == 'SE':
            profile = self.resolve_profile('SE')
            ref = profile['reference_workstation']
            viewport = self._viewport_tuple(profile)
            min_x, min_y, max_x, max_y = viewport
            origin = (-min_x, -min_y)
            width, height = max_x - min_x, max_y - min_y

            chair = self.world.load_asset(ref['chair_asset_id']).convert('RGBA')
            desk = self.world.load_asset(ref['desk_asset_id']).convert('RGBA')
            pc = self.world.load_asset(ref['pc_asset_id']).convert('RGBA')
            action = self.characters.render(character_id, 'work', 'SE', subaction)
            hdx, hdy = profile['visual_character_offset_from_chair_px']
            cdx, cdy = ref['chair_offset_px']
            ddx, ddy = ref['desk_offset_px']
            pdx, pdy = ref['pc_offset_px']
            frames: list[Image.Image] = []
            for human in action.frames:
                out = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                out.alpha_composite(chair, (origin[0] + cdx, origin[1] + cdy))
                out.alpha_composite(human.convert('RGBA'), (origin[0] + hdx, origin[1] + hdy))
                out.alpha_composite(desk, (origin[0] + ddx, origin[1] + ddy))
                out.alpha_composite(pc, (origin[0] + pdx, origin[1] + pdy))
                frames.append(out)
            return WorkPresentationResult(
                character_id=character_id,
                direction='SE',
                subaction=subaction,
                frame_ids=list(action.frame_ids),
                frames=frames,
                loop=bool(action.loop),
                viewport=viewport,
            )

        if key == 'SW':
            profile = self.resolve_profile('SW')
            se_subaction = {
                'turn_side_se': 'turn_side_sw',
                'turn_side_nw': 'turn_side_ne',
            }.get(subaction, subaction)
            se = self.compose_reference_presentation(character_id, 'SE', se_subaction)
            sw_action = self.characters.render(character_id, 'work', 'SW', subaction)
            frames = [frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in se.frames]
            return WorkPresentationResult(
                character_id=character_id,
                direction='SW',
                subaction=subaction,
                frame_ids=list(sw_action.frame_ids),
                frames=frames,
                loop=bool(sw_action.loop),
                viewport=se.viewport,
                derived_from=profile['derived_from'],
                transform=profile['standalone_transform'],
            )

        if key == 'NE':
            profile = self.resolve_profile('NE')
            nw_subaction = self._source_subaction('NE', subaction)
            nw = self.compose_reference_presentation(character_id, 'NW', nw_subaction)
            ne_action = self.characters.render(character_id, 'work', 'NE', subaction)
            if len(nw.frames) != len(ne_action.frames):
                raise WorkSeatError(
                    f'NE/{subaction} frame count does not match NW/{nw_subaction}'
                )
            return WorkPresentationResult(
                character_id=character_id,
                direction='NE',
                subaction=subaction,
                frame_ids=list(ne_action.frame_ids),
                frames=[frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in nw.frames],
                loop=bool(ne_action.loop),
                viewport=self._world_viewport(
                    'NE',
                    chair_size=self.world.load_asset('chair_000.part_00').size,
                ),
                derived_from=profile['derived_from'],
                transform=profile['standalone_transform'],
            )

        raise WorkSeatError(f'Unsupported work seat direction: {direction}')

    def _layout_slot(self, floor_id: str, slot_id: str) -> dict[str, Any] | None:
        layout = self.world.floor_layout(floor_id)
        for slot in layout.get('slots', []):
            if slot['slot_id'] == slot_id:
                return slot
        return None

    def resolve_workstation_seat(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        direction = self.directions.resolve_character_action_direction(
            floor_id, workstation_id, action_family='work'
        )
        profile = self.resolve_profile(direction)
        group = self.world.workstation_group(floor_id, workstation_id)
        chair_placement_id = group['component_slots']['chair_main']
        placements = {p['placement_id']: p for p in self.world.resolve_floor_placements(floor_id)}
        try:
            chair_placement = placements[chair_placement_id]
        except KeyError as exc:
            raise WorkSeatError(f'Missing chair placement {floor_id}.{chair_placement_id}') from exc
        chair_family_id = self.chairs.infer_family_from_asset_id(chair_placement['asset_id'])
        expected_chair_asset = self.chairs.resolve_part_asset(chair_family_id, profile['world_chair_role'])
        if expected_chair_asset != chair_placement['asset_id']:
            raise WorkSeatError(
                f'{floor_id}.{workstation_id}: authored chair {chair_placement["asset_id"]} '
                f'does not match {direction} role {expected_chair_asset}'
            )

        foreground_asset_id = None
        foreground_slot_id = group.get('optional_component_slots', {}).get('chair_foreground')
        foreground_placement_id = None
        foreground_static_present = False
        foreground_layer = None
        foreground_x = None
        foreground_y = None
        fg_role = profile.get('world_chair_foreground_role')
        if fg_role:
            foreground_asset_id = self.chairs.resolve_part_asset(chair_family_id, fg_role)
            if foreground_slot_id:
                slot = self._layout_slot(floor_id, foreground_slot_id)
                if slot is not None:
                    foreground_layer = int(slot['layer'])
                    foreground_x = int(slot['x_px'])
                    foreground_y = int(slot['y_px'])
                if foreground_slot_id in placements:
                    foreground_static_present = True
                    foreground_placement_id = foreground_slot_id
                    static = placements[foreground_slot_id]
                    if foreground_asset_id is not None and static['asset_id'] != foreground_asset_id:
                        raise WorkSeatError(
                            f'{floor_id}.{workstation_id}: static foreground {static["asset_id"]} '
                            f'does not match chair family foreground {foreground_asset_id}'
                        )
                    foreground_layer = int(static['layer'])
                    foreground_x = int(static['x_px'])
                    foreground_y = int(static['y_px'])

        component_placements: dict[str, dict[str, Any]] = {}
        static_component_placement_ids: list[str] = []
        for role in ('desk', 'pc', 'chair_main'):
            placement_id = group['component_slots'].get(role)
            if placement_id is None or placement_id not in placements:
                raise WorkSeatError(
                    f'{floor_id}.{workstation_id}: missing required {role} placement {placement_id}'
                )
            component_placements[role] = placements[placement_id]
            static_component_placement_ids.append(placement_id)

        if foreground_static_present and foreground_placement_id is not None:
            component_placements['chair_foreground'] = placements[foreground_placement_id]
            static_component_placement_ids.append(foreground_placement_id)
        elif profile.get('world_component_derivation') and foreground_asset_id is not None:
            # A source NW layout may keep the optional chair foreground as a
            # dynamic placement. Preserve that authored slot geometry, then
            # mirror it with the rest of the workstation at render time.
            if foreground_slot_id and foreground_layer is not None and foreground_x is not None and foreground_y is not None:
                slot = self._layout_slot(floor_id, foreground_slot_id)
                if slot is not None:
                    component_placements['chair_foreground'] = {
                        'floor_id': floor_id,
                        'placement_id': foreground_slot_id,
                        'canonical_placement_id': f'{floor_id}.{foreground_slot_id}',
                        'object_type': 'chair_sub',
                        'asset_id': foreground_asset_id,
                        'variant_id': self.world.resolve_variant(foreground_asset_id, slot['transform']),
                        'transform': slot['transform'],
                        'x_px': foreground_x,
                        'y_px': foreground_y,
                        'layer': foreground_layer,
                    }

        return {
            'floor_id': floor_id,
            'workstation_id': workstation_id,
            'direction': direction,
            'chair_placement_id': chair_placement_id,
            'chair_asset_id': chair_placement['asset_id'],
            'chair_family_id': chair_family_id,
            'chair_x_px': int(chair_placement['x_px']),
            'chair_y_px': int(chair_placement['y_px']),
            'chair_layer': int(chair_placement['layer']),
            'foreground_asset_id': foreground_asset_id,
            'foreground_slot_id': foreground_slot_id,
            'foreground_placement_id': foreground_placement_id,
            'foreground_static_present': foreground_static_present,
            'foreground_layer': foreground_layer,
            'foreground_x_px': foreground_x,
            'foreground_y_px': foreground_y,
            'source_direction': profile.get('derived_from'),
            'world_component_derivation': profile.get('world_component_derivation'),
            'component_placements': component_placements,
            'world_component_placement_ids': static_component_placement_ids,
            'visual_profile': profile,
        }

    @staticmethod
    def _effective_pc_placement(
        placement: dict[str, Any],
        data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Return an authored PC placement with its resolved frame variant."""
        if data is None:
            return placement
        pc_components = data.get('component_placements', {})
        pc_placement = pc_components.get('pc') if isinstance(pc_components, dict) else None
        if not isinstance(pc_placement, dict) or pc_placement.get('placement_id') != placement.get('placement_id'):
            return placement
        if data.get('pc_asset_id') is None or data.get('pc_variant_id') is None:
            return placement
        return {
            **placement,
            'asset_id': data['pc_asset_id'],
            'variant_id': data['pc_variant_id'],
        }

    def _derived_world_component_events(
        self,
        data: dict[str, Any],
    ) -> list[tuple[int, int, str, str, dict[str, Any]]]:
        """Mirror authored source-world components for a derived workstation.

        The source placement coordinates and draw layers remain authoritative.
        Only the resolved sprite and its x coordinate are mirrored around the
        source chair canvas; no static world asset or floor layout is mutated.
        """
        if not data.get('world_component_derivation'):
            return []
        components = data.get('component_placements')
        if not isinstance(components, dict):
            raise WorkSeatError(
                f"{data['floor_id']}.{data['workstation_id']}: derived workstation has no components"
            )
        chair = components.get('chair_main')
        if not isinstance(chair, dict):
            raise WorkSeatError(
                f"{data['floor_id']}.{data['workstation_id']}: derived workstation has no chair anchor"
            )
        chair_sprite = self.world.load_variant(chair['variant_id'])
        anchor_x = int(chair['x_px'])
        chair_width = int(chair_sprite.width)
        events: list[tuple[int, int, str, str, dict[str, Any]]] = []
        for role in ('desk', 'pc', 'chair_main', 'chair_foreground'):
            placement = components.get(role)
            if placement is None:
                continue
            variant_id = (
                data.get('pc_variant_id')
                if role == 'pc' and data.get('pc_variant_id') is not None
                else placement['variant_id']
            )
            sprite = self.world.load_variant(variant_id).convert('RGBA')
            mirrored = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            source_x = int(placement['x_px'])
            mirrored_x = anchor_x + chair_width - (source_x - anchor_x) - mirrored.width
            events.append((
                int(placement['layer']),
                0,
                f"{data['workstation_id']}:{role}",
                'derived_static',
                {
                    'sprite': mirrored,
                    'x_px': mirrored_x,
                    'y_px': int(placement['y_px']),
                },
            ))
        if not events:
            raise WorkSeatError(
                f"{data['floor_id']}.{data['workstation_id']}: derived workstation has no renderable components"
            )
        return events

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
    ) -> Image.Image:
        by_workstation, rendered = self._resolve_floor_assignment_data(
            floor_id,
            assignments,
            frame_index=frame_index,
            character_frame_index=character_frame_index,
            effect_frame_index=effect_frame_index,
            humanball_frame_index=humanball_frame_index,
            pc_frame_index=pc_frame_index,
        )

        skin = self.world.floor_skin(floor_id)
        canvas = self.world.load_variant(skin['base_variant_id']).copy().convert('RGBA')
        events: list[tuple[int, int, str, str, dict[str, Any]]] = []
        placements = self.world.resolve_floor_placements(floor_id)
        derived_data = [data for data in by_workstation.values() if data.get('world_component_derivation')]
        suppressed_placement_ids = {
            placement_id
            for data in derived_data
            for placement_id in data.get('world_component_placement_ids', [])
        }
        pc_data_by_placement = {
            data['component_placements']['pc']['placement_id']: data
            for data in by_workstation.values()
            if isinstance(data.get('component_placements', {}).get('pc'), dict)
        }
        for placement in placements:
            if placement['placement_id'] in suppressed_placement_ids:
                continue
            data = rendered.get(placement['placement_id'])
            pc_data = pc_data_by_placement.get(placement['placement_id'])
            static_payload = self._effective_pc_placement(placement, pc_data)
            events.append((int(static_payload['layer']), 0, placement['placement_id'], 'static', static_payload))
            if data is not None:
                events.append((int(placement['layer']), 1, data['workstation_id'], 'human', data))

        for data in derived_data:
            events.extend(self._derived_world_component_events(data))
            events.append((int(data['chair_layer']), 1, data['workstation_id'], 'human', data))

        for data in by_workstation.values():
            if (
                data['foreground_asset_id'] is not None
                and not data['foreground_static_present']
                and data['foreground_layer'] is not None
                and not data.get('world_component_derivation')
            ):
                events.append((
                    int(data['foreground_layer']),
                    1,
                    data['workstation_id'],
                    'foreground',
                    data,
                ))

        for _, _, _, kind, payload in sorted(events, key=lambda e: (e[0], e[1], e[2], e[3])):
            if kind == 'static':
                sprite = self.world.load_variant(payload['variant_id'])
                canvas.alpha_composite(sprite, (int(payload['x_px']), int(payload['y_px'])))
            elif kind == 'derived_static':
                canvas.alpha_composite(payload['sprite'], (int(payload['x_px']), int(payload['y_px'])))
            elif kind == 'human':
                canvas.alpha_composite(payload['human'], (payload['human_x_px'], payload['human_y_px']))
            elif kind == 'foreground':
                sprite = self.world.load_asset(payload['foreground_asset_id']).convert('RGBA')
                canvas.alpha_composite(
                    sprite,
                    (int(payload['foreground_x_px']), int(payload['foreground_y_px'])),
                )
            else:
                raise WorkSeatError(f'Unknown render event: {kind}')
        return canvas

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
    ) -> Image.Image:
        by_workstation, rendered = self._resolve_floor_assignment_data(
            floor_id,
            assignments,
            frame_index=frame_index,
            character_frame_index=character_frame_index,
            effect_frame_index=effect_frame_index,
            humanball_frame_index=humanball_frame_index,
            pc_frame_index=pc_frame_index,
        )

        skin = self.world.floor_skin(floor_id)
        canvas = self.world.load_variant(skin['base_variant_id']).copy().convert('RGBA')
        events: list[tuple[int, int, str, str, dict[str, Any]]] = []
        placements = self.world.resolve_floor_placements(floor_id)
        derived_data = [data for data in by_workstation.values() if data.get('world_component_derivation')]
        suppressed_placement_ids = {
            placement_id
            for data in derived_data
            for placement_id in data.get('world_component_placement_ids', [])
        }
        pc_data_by_placement = {
            data['component_placements']['pc']['placement_id']: data
            for data in by_workstation.values()
            if isinstance(data.get('component_placements', {}).get('pc'), dict)
        }
        for placement in placements:
            if placement['placement_id'] in suppressed_placement_ids:
                continue
            data = rendered.get(placement['placement_id'])
            pc_data = pc_data_by_placement.get(placement['placement_id'])
            if data is not None and data.get('effect') is not None:
                events.append((int(placement['layer']), -1, data['workstation_id'], 'effect', data))
            static_payload = self._effective_pc_placement(placement, pc_data)
            events.append((int(static_payload['layer']), 0, placement['placement_id'], 'static', static_payload))
            if data is not None:
                events.append((int(placement['layer']), 1, data['workstation_id'], 'human', data))

        for data in derived_data:
            if data.get('effect') is not None:
                events.append((int(data['chair_layer']), -1, data['workstation_id'], 'effect', data))
            events.extend(self._derived_world_component_events(data))
            events.append((int(data['chair_layer']), 1, data['workstation_id'], 'human', data))

        for data in by_workstation.values():
            if (
                data['foreground_asset_id'] is not None
                and not data['foreground_static_present']
                and data['foreground_layer'] is not None
                and not data.get('world_component_derivation')
            ):
                events.append((
                    int(data['foreground_layer']),
                    2,
                    data['workstation_id'],
                    'foreground',
                    data,
                ))

        for _, _, _, kind, payload in sorted(events, key=lambda e: (e[0], e[1], e[2], e[3])):
            if kind == 'effect':
                canvas.alpha_composite(payload['effect'], (payload['effect_x_px'], payload['effect_y_px']))
            elif kind == 'static':
                sprite = self.world.load_variant(payload['variant_id'])
                canvas.alpha_composite(sprite, (int(payload['x_px']), int(payload['y_px'])))
            elif kind == 'derived_static':
                canvas.alpha_composite(payload['sprite'], (int(payload['x_px']), int(payload['y_px'])))
            elif kind == 'human':
                canvas.alpha_composite(payload['human'], (payload['human_x_px'], payload['human_y_px']))
            elif kind == 'foreground':
                sprite = self.world.load_asset(payload['foreground_asset_id']).convert('RGBA')
                canvas.alpha_composite(
                    sprite,
                    (int(payload['foreground_x_px']), int(payload['foreground_y_px'])),
                )
            else:
                raise WorkSeatError(f'Unknown render event: {kind}')

        # HumanBall is a popup overlay channel. The source suite composites it
        # after the completed work scene, so it intentionally renders after
        # all static, human, and chair-foreground events.
        for workstation_id in sorted(by_workstation):
            payload = by_workstation[workstation_id]
            popup = payload.get('humanball')
            if popup is None:
                continue
            canvas.alpha_composite(
                popup,
                (int(payload['humanball_x_px']), int(payload['humanball_y_px'])),
            )
        return canvas
