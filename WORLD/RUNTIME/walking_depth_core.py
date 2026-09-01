from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from WORLD.RUNTIME.floor_renderer import FloorRenderer
from WORLD.RUNTIME.layout_core import LayoutCore
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore


class WalkingDepthError(ValueError):
    pass


class WalkingDepthCore:
    """Resolve and render walking occlusion from existing world metadata.

    Navigation footprints define object ground depth only; they are not modified.
    Visual-only workstation components inherit depth from their physical parent.
    """

    FOOTPRINT_TYPES = frozenset({'desk', 'chair', 'reception'})

    def __init__(
        self,
        world_root: str | Path,
        *,
        layout: LayoutCore | None = None,
        occupancy: NavigationOccupancyCore | None = None,
        floor_renderer: FloorRenderer | None = None,
    ):
        self.root = Path(world_root).resolve()
        self.layout = layout or LayoutCore(self.root)
        self.occupancy = occupancy or NavigationOccupancyCore(self.root)
        self.floor_renderer = floor_renderer or FloorRenderer(self.root)
        depth_registry_path = self.root / 'REGISTRY' / 'walking_depth_profiles.json'
        if depth_registry_path.is_file():
            depth_registry = json.loads(depth_registry_path.read_text(encoding='utf-8'))
        else:
            depth_registry = {}
        self.depth_profiles = depth_registry.get('profiles', {})
        self.depth_floor_bindings = depth_registry.get('floor_bindings', {})
        self.depth_layout_bindings = depth_registry.get('layout_bindings', {})
        self._occluder_cache: dict[str, list[dict[str, Any]]] = {}
        self._occluder_visual_cache: dict[tuple[str, bool], Image.Image] = {}

    def _slot_map(self, floor_id: str) -> dict[str, dict[str, Any]]:
        layout = self.layout.floor_layout(floor_id)
        slots = list(layout.get('slots', [])) + list(layout.get('semantic_slots', []))
        return {slot['slot_id']: slot for slot in slots}

    def _footprint_instance_map(self, floor_id: str) -> dict[str, dict[str, Any]]:
        return {
            rec['placement_id']: rec
            for rec in self.occupancy.resolve_floor_instances(floor_id)
            if rec['object_type'] in self.FOOTPRINT_TYPES
        }

    def _depth_profile(self, floor_id: str, placement_id: str) -> dict[str, Any] | None:
        profile_id = self.depth_floor_bindings.get(floor_id, {}).get(placement_id)
        if profile_id is None:
            layout_id = self.layout.floor_record(floor_id)['layout_id']
            profile_id = self.depth_layout_bindings.get(layout_id, {}).get(placement_id)
        if profile_id is None:
            return None
        try:
            profile = deepcopy(self.depth_profiles[profile_id])
        except KeyError as exc:
            raise WalkingDepthError(
                f'{floor_id}.{placement_id}: unknown walking depth profile {profile_id}'
            ) from exc
        if profile.get('profile_id') != profile_id:
            raise WalkingDepthError(
                f'{floor_id}.{placement_id}: walking depth profile id mismatch for {profile_id}'
            )
        return profile

    def _footprint_record(
        self,
        placement: dict[str, Any],
        instance: dict[str, Any],
    ) -> dict[str, Any]:
        corners = [list(pt) for pt in instance['outer_corners_world_px']]
        if not corners:
            raise WalkingDepthError(f"Missing footprint corners for {placement['canonical_placement_id']}")
        depth_profile = self._depth_profile(placement['floor_id'], placement['placement_id'])
        if depth_profile is None:
            depth_mode = 'ground_footprint'
            depth_profile_id = None
            depth_corners = deepcopy(corners)
            front_edge = None
        else:
            if depth_profile.get('object_type') != placement['object_type']:
                raise WalkingDepthError(
                    f"{placement['canonical_placement_id']}: depth profile object type mismatch"
                )
            if depth_profile.get('depth_test') != 'front_edge_by_ground_x':
                raise WalkingDepthError(
                    f"{placement['canonical_placement_id']}: unsupported depth test "
                    f"{depth_profile.get('depth_test')!r}"
                )
            depth_mode = 'ground_front_envelope'
            depth_profile_id = depth_profile['profile_id']
            depth_corners = [list(pt) for pt in depth_profile['outer_corners_world_px']]
            front_edge = [list(pt) for pt in depth_profile['front_edge_world_px']]
            if len(front_edge) < 2:
                raise WalkingDepthError(
                    f"{placement['canonical_placement_id']}: depth front edge requires two points"
                )
        return {
            'floor_id': placement['floor_id'],
            'placement_id': placement['placement_id'],
            'object_type': placement['object_type'],
            'asset_id': placement['asset_id'],
            'variant_id': placement['variant_id'],
            'authored_layer': int(placement['layer']),
            'depth_mode': depth_mode,
            'depth_profile_id': depth_profile_id,
            'depth_anchor_y_px': max(int(y) for _, y in depth_corners),
            'depth_source_placement_id': placement['placement_id'],
            'footprint_corners_world_px': corners,
            'depth_footprint_corners_world_px': depth_corners,
            'depth_front_edge_world_px': front_edge,
            'foreground_fragment': False,
            'always_foreground': False,
            'placement': deepcopy(placement),
        }

    def resolve_occluders(self, floor_id: str) -> list[dict[str, Any]]:
        cached = self._occluder_cache.get(floor_id)
        if cached is not None:
            return deepcopy(cached)

        placements = self.layout.resolve_floor_placements(floor_id)
        by_id = {p['placement_id']: p for p in placements}
        slots = self._slot_map(floor_id)
        footprint_instances = self._footprint_instance_map(floor_id)
        resolved: dict[str, dict[str, Any]] = {}

        # Physical world objects own their ground depth directly.
        for placement_id, instance in footprint_instances.items():
            placement = by_id.get(placement_id)
            if placement is None:
                continue
            resolved[placement_id] = self._footprint_record(placement, instance)

        # Visual workstation components inherit the depth of the parent object.
        for placement in placements:
            placement_id = placement['placement_id']
            object_type = placement['object_type']
            slot = slots.get(placement_id, {})
            workstation_id = slot.get('workstation_id')
            component_role = slot.get('component_role')

            if object_type == 'pc' and workstation_id is not None:
                group = self.layout.workstation_group(floor_id, workstation_id)
                source_id = group['component_slots']['desk']
                source = resolved.get(source_id)
                if source is None:
                    raise WalkingDepthError(
                        f'{floor_id}.{placement_id}: missing desk depth source {source_id}'
                    )
                resolved[placement_id] = {
                    'floor_id': floor_id,
                    'placement_id': placement_id,
                    'object_type': object_type,
                    'asset_id': placement['asset_id'],
                    'variant_id': placement['variant_id'],
                    'authored_layer': int(placement['layer']),
                    'depth_mode': 'inherit_workstation_desk',
                    'depth_profile_id': source.get('depth_profile_id'),
                    'depth_anchor_y_px': int(source['depth_anchor_y_px']),
                    'depth_source_placement_id': source_id,
                    'footprint_corners_world_px': deepcopy(source['footprint_corners_world_px']),
                    'depth_footprint_corners_world_px': deepcopy(source.get('depth_footprint_corners_world_px')),
                    'depth_front_edge_world_px': deepcopy(source.get('depth_front_edge_world_px')),
                    'foreground_fragment': False,
                    'always_foreground': False,
                    'placement': deepcopy(placement),
                }
                continue

            if object_type == 'chair_sub' and workstation_id is not None and component_role == 'chair_foreground':
                group = self.layout.workstation_group(floor_id, workstation_id)
                source_id = group['component_slots']['chair_main']
                source = resolved.get(source_id)
                if source is None:
                    raise WalkingDepthError(
                        f'{floor_id}.{placement_id}: missing chair depth source {source_id}'
                    )
                resolved[placement_id] = {
                    'floor_id': floor_id,
                    'placement_id': placement_id,
                    'object_type': object_type,
                    'asset_id': placement['asset_id'],
                    'variant_id': placement['variant_id'],
                    'authored_layer': int(placement['layer']),
                    'depth_mode': 'inherit_workstation_chair',
                    'depth_profile_id': source.get('depth_profile_id'),
                    'depth_anchor_y_px': int(source['depth_anchor_y_px']),
                    'depth_source_placement_id': source_id,
                    'footprint_corners_world_px': deepcopy(source['footprint_corners_world_px']),
                    'depth_footprint_corners_world_px': deepcopy(source.get('depth_footprint_corners_world_px')),
                    'depth_front_edge_world_px': deepcopy(source.get('depth_front_edge_world_px')),
                    'foreground_fragment': True,
                    'always_foreground': False,
                    'placement': deepcopy(placement),
                }
                continue

            legacy = placement.get('legacy_metadata') or {}
            if object_type == 'foreground_overlay' and legacy.get('role') == 'top_character_occluder':
                resolved[placement_id] = {
                    'floor_id': floor_id,
                    'placement_id': placement_id,
                    'object_type': object_type,
                    'asset_id': placement['asset_id'],
                    'variant_id': placement['variant_id'],
                    'authored_layer': int(placement['layer']),
                    'depth_mode': 'always_foreground',
                    'depth_profile_id': None,
                    'depth_anchor_y_px': None,
                    'depth_source_placement_id': None,
                    'footprint_corners_world_px': None,
                    'depth_footprint_corners_world_px': None,
                    'depth_front_edge_world_px': None,
                    'foreground_fragment': True,
                    'always_foreground': True,
                    'placement': deepcopy(placement),
                }

        rows = sorted(
            resolved.values(),
            key=lambda row: (int(row['authored_layer']), row['placement_id']),
        )
        self._occluder_cache[floor_id] = deepcopy(rows)
        return deepcopy(rows)

    @staticmethod
    def _front_edge_y_at_x(front_edge: list[list[int]], world_x: float) -> float:
        points = sorted(
            ((float(x), float(y)) for x, y in front_edge),
            key=lambda point: (point[0], point[1]),
        )
        x = min(max(float(world_x), points[0][0]), points[-1][0])
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                if x1 == x0:
                    return max(y0, y1)
                progress = (x - x0) / (x1 - x0)
                return y0 + (y1 - y0) * progress
        return points[-1][1]

    def occluders_in_front(
        self,
        floor_id: str,
        character_ground: float | tuple[float, float] | list[float],
    ) -> list[dict[str, Any]]:
        if isinstance(character_ground, (tuple, list)):
            if len(character_ground) != 2:
                raise WalkingDepthError('character ground position requires x and y')
            depth_x = float(character_ground[0])
            depth_y = float(character_ground[1])
        else:
            # Backward-compatible scalar query for callers that only need the
            # legacy max-Y approximation. Runtime composition always supplies X/Y.
            depth_x = None
            depth_y = float(character_ground)
        selected = []
        for row in self.resolve_occluders(floor_id):
            if row['always_foreground']:
                selected.append(row)
                continue
            front_edge = row.get('depth_front_edge_world_px')
            if front_edge is not None and depth_x is not None:
                anchor_y = self._front_edge_y_at_x(front_edge, depth_x)
            else:
                anchor_y = row['depth_anchor_y_px']
            if anchor_y is not None and float(anchor_y) > depth_y:
                selected.append(row)
        return selected

    def actor_draws_over_reception(
        self,
        floor_id: str,
        character_ground: tuple[float, float] | list[float],
    ) -> bool:
        """Return whether an actor's ground depth is in front of reception.

        This is the authored render-depth trigger used by the speech scheduler
        for the one-shot ``leaving`` line.  It intentionally does not compare
        a raw U/V threshold: the reception's own front-edge envelope and X
        range decide when the actor may paint over it.
        """
        if not isinstance(character_ground, (tuple, list)) or len(character_ground) != 2:
            raise WalkingDepthError('character ground position requires x and y')
        x, y = float(character_ground[0]), float(character_ground[1])
        reception = next(
            (row for row in self.resolve_occluders(floor_id) if row['placement_id'] == 'reception'),
            None,
        )
        if reception is None:
            return False
        # Use the full authored footprint for X overlap.  The depth front edge
        # itself is allowed to clamp at its end points, matching
        # ``occluders_in_front`` exactly for padded reception sprites.
        corners = reception.get('footprint_corners_world_px') or reception.get('depth_footprint_corners_world_px') or []
        if corners:
            min_x = min(float(point[0]) for point in corners)
            max_x = max(float(point[0]) for point in corners)
            if not (min_x <= x <= max_x):
                return False
        front_edge = reception.get('depth_front_edge_world_px')
        if front_edge:
            front_y = self._front_edge_y_at_x(front_edge, x)
        else:
            front_y = reception.get('depth_anchor_y_px')
        return front_y is not None and y >= float(front_y)

    @staticmethod
    def _actor_bbox(
        sprite: Image.Image,
        ground_xy: tuple[float, float],
        ground_anchor_px: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        gx, gy = float(ground_xy[0]), float(ground_xy[1])
        ax, ay = int(ground_anchor_px[0]), int(ground_anchor_px[1])
        x = int(round(gx - ax))
        y = int(round(gy - ay))
        return x, y, x + sprite.width, y + sprite.height

    def _mask_character_by_world_occluders(
        self,
        floor_id: str,
        sprite: Image.Image,
        ground_xy: tuple[float, float],
        *,
        ground_anchor_px: tuple[int, int],
    ) -> Image.Image:
        """Return the actor with front-world pixels removed from actor alpha.

        The completed floor is never redrawn here. Furniture shadows and other
        semi-transparent world pixels therefore remain byte-stable across
        frames regardless of how many actors pass behind the same object.
        """
        actor = sprite.convert('RGBA').copy()
        actor_alpha = actor.getchannel('A')
        ax0, ay0, ax1, ay1 = self._actor_bbox(actor, ground_xy, ground_anchor_px)
        for row in self.occluders_in_front(floor_id, ground_xy):
            placement = row['placement']
            occluder = self._load_occluder_visual(row)
            ox0 = int(placement['x_px'])
            oy0 = int(placement['y_px'])
            ox1 = ox0 + occluder.width
            oy1 = oy0 + occluder.height
            ix0 = max(ax0, ox0)
            iy0 = max(ay0, oy0)
            ix1 = min(ax1, ox1)
            iy1 = min(ay1, oy1)
            if ix0 >= ix1 or iy0 >= iy1:
                continue

            actor_box = (ix0 - ax0, iy0 - ay0, ix1 - ax0, iy1 - ay0)
            occ_box = (ix0 - ox0, iy0 - oy0, ix1 - ox0, iy1 - oy0)
            actor_crop = actor_alpha.crop(actor_box)
            occ_alpha = occluder.getchannel('A').crop(occ_box)
            inverse_occ = Image.eval(occ_alpha, lambda value: 255 - value)
            actor_alpha.paste(ImageChops.multiply(actor_crop, inverse_occ), actor_box)

        actor.putalpha(actor_alpha)
        return actor

    def composite_characters(
        self,
        floor_id: str,
        actors: list[dict[str, Any]],
    ) -> Image.Image:
        """Composite one or more walking actors without redrawing world assets.

        Each actor record requires ``sprite``, ``ground_xy`` and
        ``ground_anchor_px``. Actors are sorted by ground Y for actor/actor
        ordering; world occlusion is applied as an actor alpha mask.
        """
        canvas = self.floor_renderer.render(floor_id).convert('RGBA')
        normalized = []
        for index, actor in enumerate(actors):
            if 'sprite' not in actor or 'ground_xy' not in actor or 'ground_anchor_px' not in actor:
                raise WalkingDepthError('actor requires sprite, ground_xy, and ground_anchor_px')
            gx, gy = actor['ground_xy']
            normalized.append((float(gy), index, actor, (float(gx), float(gy))))

        for _gy, _index, actor, ground_xy in sorted(normalized, key=lambda row: (row[0], row[1])):
            anchor = tuple(map(int, actor['ground_anchor_px']))
            sprite = self._mask_character_by_world_occluders(
                floor_id,
                actor['sprite'],
                ground_xy,
                ground_anchor_px=anchor,
            )
            x0, y0, _x1, _y1 = self._actor_bbox(sprite, ground_xy, anchor)
            canvas.alpha_composite(sprite, (x0, y0))
        return canvas

    def composite_character(
        self,
        floor_id: str,
        sprite: Image.Image,
        ground_xy: tuple[float, float],
        *,
        ground_anchor_px: tuple[int, int],
    ) -> Image.Image:
        return self.composite_characters(
            floor_id,
            [{
                'sprite': sprite,
                'ground_xy': ground_xy,
                'ground_anchor_px': ground_anchor_px,
            }],
        )

    def _load_occluder_visual(self, row: dict[str, Any]) -> Image.Image:
        placement = row['placement']
        strip_shadow = not bool(row.get('always_foreground'))
        cache_key = (placement['variant_id'], strip_shadow)
        cached = self._occluder_visual_cache.get(cache_key)
        if cached is not None:
            return cached.copy()

        image = self.layout.load_variant(placement['variant_id']).convert('RGBA')
        if strip_shadow:
            # Furniture ground shadows are already present in the completed floor.
            # They are encoded as dark, partially-transparent pixels. Re-compositing
            # those pixels during the walking occlusion pass darkens the floor, so
            # the dynamic pass keeps the solid/colored visual body while stripping
            # only shadow-like pixels.
            cleaned = []
            # ``Image.get_flattened_data`` is not part of Pillow's public API
            # and is absent in current supported releases.  ``getdata`` gives
            # us the same RGBA pixel stream without changing the source image.
            for r, g, b, a in image.getdata():
                if 0 < a < 255 and max(r, g, b) <= 64:
                    cleaned.append((r, g, b, 0))
                else:
                    cleaned.append((r, g, b, a))
            image.putdata(cleaned)

        self._occluder_visual_cache[cache_key] = image.copy()
        return image
