from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from WORLD.RUNTIME.ground_footprint_core import GroundFootprintCore
from WORLD.RUNTIME.layout_core import LayoutCore
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore
from WORLD.RUNTIME.occupancy_closure_core import OccupancyClosureCore
from WORLD.RUNTIME.navigation_clearance_core import NavigationClearanceCore


class NavigationOccupancyError(ValueError):
    pass


class NavigationOccupancyCore:
    """Compile and resolve walkability from room domain minus active object footprints."""

    ACTIVE_TYPES = frozenset({'desk', 'chair', 'reception'})

    def __init__(self, world_root: str | Path):
        self.root = Path(world_root).resolve()
        self.layout = LayoutCore(self.root)
        self.footprints = GroundFootprintCore(self.root)
        self.navigation = RoomNavigationCore(self.root)
        self.closures = OccupancyClosureCore(self.root, layout=self.layout)
        self.clearance = NavigationClearanceCore(self.root, layout=self.layout)
        bridge_path = self.root / 'REGISTRY' / 'navigation_placement_bridges.json'
        if bridge_path.exists():
            self.bridges = json.loads(bridge_path.read_text(encoding='utf-8')).get('bridges', {})
        else:
            self.bridges = {}
        family_path = self.root / 'REGISTRY' / 'gameplay_metadata_families.json'
        if family_path.exists():
            family_payload = json.loads(family_path.read_text(encoding='utf-8'))
            self._gameplay_family_by_layout = {
                row['layout_id']: row for row in family_payload.get('families', {}).values()
            }
        else:
            self._gameplay_family_by_layout = {}
        self.compiled_root = self.root / 'COMPILED_NAV' / 'OCCUPANCY'
        self._compiled_cache: dict[str, dict[str, Any]] = {}
        self._reachable_cache: dict[str, set[tuple[int, int]]] = {}

    def _continuous_uv(self, x: int, y: int) -> tuple[float, float]:
        g = self.navigation.grid
        ox, oy = g['grid_origin_px']
        ux, uy = g['u_step_px']
        vx, vy = g['v_step_px']
        dx, dy = int(x) - ox, int(y) - oy
        det = ux * vy - uy * vx
        return ((dx * vy - dy * vx) / det, (ux * dy - uy * dx) / det)

    @staticmethod
    def _cell_center_raster(corners_uv: list[tuple[float, float]]) -> list[list[int]]:
        min_u = min(u for u, _ in corners_uv)
        max_u = max(u for u, _ in corners_uv)
        min_v = min(v for _, v in corners_uv)
        max_v = max(v for _, v in corners_uv)
        u0 = math.ceil(min_u - 0.5)
        u1 = math.ceil(max_u - 0.5) - 1
        v0 = math.ceil(min_v - 0.5)
        v1 = math.ceil(max_v - 0.5) - 1
        return [[u, v] for v in range(v0, v1 + 1) for u in range(u0, u1 + 1)]

    def _bridge_placements(self, floor_id: str) -> list[dict[str, Any]]:
        out = []
        for rec in self.bridges.values():
            if rec.get('floor_id') != floor_id or not rec.get('navigation_occupancy_active', True):
                continue
            item = dict(rec)
            item['canonical_placement_id'] = f"{floor_id}.{item['placement_id']}"
            out.append(item)
        return out

    def resolve_instance(self, floor_id: str, placement: dict[str, Any]) -> dict[str, Any]:
        if placement.get('variant_id'):
            resolved = self.footprints.resolve_variant(placement['variant_id'])
        else:
            resolved = self.footprints.resolve_asset(placement['asset_id'], transform=placement.get('transform'))
        if resolved is None:
            raise NavigationOccupancyError(
                f"Placement has no active ground footprint: {floor_id}.{placement['placement_id']}"
            )
        ax, ay = int(placement['x_px']), int(placement['y_px'])
        floor_layout_id = self.layout.floor_record(floor_id)['layout_id']
        family = self._gameplay_family_by_layout.get(floor_layout_id, {})
        override = family.get('placement_overrides', {}).get(placement['placement_id'])
        if override is not None and override.get('navigation_ground_anchor_world_px') is not None:
            anchor_x, anchor_y = map(int, override['navigation_ground_anchor_world_px'])
            du, dv = map(int, override.get('footprint_origin_offset_uv_cells', [0, 0]))
            ux, uy = self.navigation.grid['u_step_px']
            vx, vy = self.navigation.grid['v_step_px']
            p0x = anchor_x + du * ux + dv * vx
            p0y = anchor_y + du * uy + dv * vy
            u_cells = int(resolved['axes']['u_cells'])
            v_cells = int(resolved['axes']['v_cells'])
            p0 = [p0x, p0y]
            p1 = [p0x + u_cells * ux, p0y + u_cells * uy]
            p2 = [p1[0] + v_cells * vx, p1[1] + v_cells * vy]
            p3 = [p0x + v_cells * vx, p0y + v_cells * vy]
            world_corners = [p0, p1, p2, p3]
            navigation_anchor_policy = override.get('policy', 'fixed_world_ground_anchor')
        else:
            world_corners = [[ax + x, ay + y] for x, y in resolved['outer_corners_asset_px']]
            navigation_anchor_policy = 'asset_projected'
        corners_uv = [self._continuous_uv(x, y) for x, y in world_corners]
        cells = self._cell_center_raster(corners_uv)
        return {
            'floor_id': floor_id,
            'placement_id': placement['placement_id'],
            'canonical_placement_id': placement.get('canonical_placement_id', f"{floor_id}.{placement['placement_id']}"),
            'object_type': placement['object_type'],
            'asset_id': placement['asset_id'],
            'variant_id': placement.get('variant_id'),
            'visual_transform': placement.get('transform', 'NORMAL'),
            'footprint_transform': resolved['derived_transform'],
            'profile_id': resolved['profile_id'],
            'asset_top_left_px': [ax, ay],
            'outer_corners_world_px': world_corners,
            'outer_corners_uv_continuous': [[round(u, 4), round(v, 4)] for u, v in corners_uv],
            'occupied_cells_uv': cells,
            'placement_source': placement.get('placement_source', 'active_layout_skin'),
            'navigation_anchor_policy': navigation_anchor_policy,
            'canonical_ground_anchor_world_px': (
                list(map(int, override['navigation_ground_anchor_world_px']))
                if override is not None and override.get('navigation_ground_anchor_world_px') is not None
                else None
            ),
            'profile_origin_offset_uv_cells': (
                list(map(int, override.get('footprint_origin_offset_uv_cells', [0, 0])))
                if override is not None and override.get('navigation_ground_anchor_world_px') is not None
                else None
            ),
        }

    def resolve_floor_instances(self, floor_id: str) -> list[dict[str, Any]]:
        placements = [
            p for p in self.layout.resolve_floor_placements(floor_id)
            if p['object_type'] in self.ACTIVE_TYPES
        ]
        existing_ids = {p['placement_id'] for p in placements}
        placements.extend(
            p for p in self._bridge_placements(floor_id)
            if p['placement_id'] not in existing_ids
        )
        out = []
        for placement in placements:
            if placement.get('variant_id'):
                bound = self.footprints.resolve_variant(placement['variant_id'])
            else:
                bound = self.footprints.resolve_asset(
                    placement['asset_id'], transform=placement.get('transform')
                )
            if bound is not None:
                out.append(self.resolve_instance(floor_id, placement))
        return sorted(out, key=lambda x: x['placement_id'])

    @staticmethod
    def _sorted_cells(cells: set[tuple[int, int]]) -> list[list[int]]:
        return [list(x) for x in sorted(cells, key=lambda z: (z[1], z[0]))]

    def compile_floor(self, floor_id: str) -> dict[str, Any]:
        room = self.navigation.room_cell_set(floor_id)
        portal = self.navigation.portal(floor_id)
        portal_inside = {tuple(x) for x in portal['inside_cells_uv']}
        instances = self.resolve_floor_instances(floor_id)
        instance_sets = {
            x['canonical_placement_id']: {tuple(c) for c in x['occupied_cells_uv']}
            for x in instances
        }
        closures = self.closures.resolve_floor_closures(floor_id, instances)
        closure_sets = {
            row['closure_id']: {tuple(c) for c in row['occupied_cells_uv']}
            for row in closures
        }
        base_occupied = set().union(*instance_sets.values()) if instance_sets else set()
        closure_cells = set().union(*closure_sets.values()) if closure_sets else set()
        supplemental_closure_cells = closure_cells - base_occupied
        clearance = self.clearance.resolve_floor_clearance(
            floor_id,
            instances,
            room_cells=room,
            portal_cells=portal_inside,
            base_occupied_cells=base_occupied,
            closure_cells=supplemental_closure_cells,
            closures=closures,
        )
        clearance_cells = {tuple(cell) for cell in clearance['clearance_cells_uv']}
        supplemental_clearance_cells = clearance_cells - base_occupied - supplemental_closure_cells
        occupied = base_occupied | supplemental_closure_cells | supplemental_clearance_cells
        outside_by_instance = {
            iid: cells - room for iid, cells in instance_sets.items() if cells - room
        }
        outside_by_closure = {
            cid: cells - room for cid, cells in closure_sets.items() if cells - room
        }
        occupied_in_room = occupied & room
        closure_in_room = supplemental_closure_cells & room
        clearance_in_room = supplemental_clearance_cells & room
        walkable = room - occupied_in_room
        portal_overlap = portal_inside & occupied_in_room
        return {
            'schema': 'gds_compiled_navigation_floor_v1',
            'floor_id': floor_id,
            'canonical_room_floor_id': self.navigation.family(floor_id)['canonical_floor_id'],
            'grid_profile_id': self.navigation.grid['profile_id'],
            'room_cell_count': len(room),
            'base_occupied_cell_count': len(base_occupied & room),
            'closure_cell_count': len(closure_in_room),
            'clearance_cell_count': len(clearance_in_room),
            'protected_ingress_cell_count': len(clearance['protected_ingress_cells_uv']),
            'sealed_pocket_cell_count': len(clearance.get('sealed_pocket_cells_uv', [])),
            'boundary_relief_cell_count': len(clearance.get('boundary_relief_cells_uv', [])),
            'chair_pair_relief_cell_count': len(clearance.get('chair_pair_relief_cells_uv', [])),
            'occupied_cell_count': len(occupied_in_room),
            'walkable_cell_count': len(walkable),
            'portal_inside_cell_count': len(portal_inside),
            'outside_room_instance_count': len(outside_by_instance),
            'outside_room_closure_count': len(outside_by_closure),
            'portal_overlap_cell_count': len(portal_overlap),
            'room_cells_uv': self._sorted_cells(room),
            'base_occupied_cells_uv': self._sorted_cells(base_occupied & room),
            'closure_cells_uv': self._sorted_cells(closure_in_room),
            'clearance_cells_uv': self._sorted_cells(clearance_in_room),
            'protected_ingress_cells_uv': clearance['protected_ingress_cells_uv'],
            'sealed_pocket_cells_uv': clearance.get('sealed_pocket_cells_uv', []),
            'boundary_relief_cells_uv': clearance.get('boundary_relief_cells_uv', []),
            'chair_pair_relief_cells_uv': clearance.get('chair_pair_relief_cells_uv', []),
            'occupied_cells_uv': self._sorted_cells(occupied_in_room),
            'walkable_cells_uv': self._sorted_cells(walkable),
            'portal_inside_cells_uv': self._sorted_cells(portal_inside),
            'outside_room_instances': {
                iid: self._sorted_cells(cells) for iid, cells in sorted(outside_by_instance.items())
            },
            'outside_room_closures': {
                cid: self._sorted_cells(cells) for cid, cells in sorted(outside_by_closure.items())
            },
            'portal_overlap_cells_uv': self._sorted_cells(portal_overlap),
            'instances': instances,
            'closures': closures,
            'clearance_records': clearance['clearance_records'],
            'boundary_relief_records': clearance.get('boundary_relief_records', []),
            'chair_pair_relief_records': clearance.get('chair_pair_relief_records', []),
            'protected_ingress': clearance['protected_ingress'],
        }

    def compiled_path(self, floor_id: str) -> Path:
        return self.compiled_root / f'{floor_id}_navigation_cells.json'

    def _compiled_floor_cached(self, floor_id: str) -> dict[str, Any]:
        if floor_id not in self._compiled_cache:
            path = self.compiled_path(floor_id)
            if path.exists():
                compiled = json.loads(path.read_text(encoding='utf-8'))
            else:
                compiled = self.compile_floor(floor_id)
            self._compiled_cache[floor_id] = compiled
        return self._compiled_cache[floor_id]

    def resolve_floor(self, floor_id: str) -> dict[str, Any]:
        return deepcopy(self._compiled_floor_cached(floor_id))

    def _reachable_walkable(self, floor_id: str, compiled: dict[str, Any] | None = None) -> set[tuple[int, int]]:
        if floor_id in self._reachable_cache:
            return set(self._reachable_cache[floor_id])
        compiled = compiled or self._compiled_floor_cached(floor_id)
        walkable = {tuple(x) for x in compiled['walkable_cells_uv']}
        starts = {tuple(x) for x in compiled['portal_inside_cells_uv']} & walkable
        seen = set(starts)
        stack = list(starts)
        while stack:
            u, v = stack.pop()
            for nxt in ((u + 1, v), (u - 1, v), (u, v + 1), (u, v - 1)):
                if nxt in walkable and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        self._reachable_cache[floor_id] = set(seen)
        return seen

    def validate_floor(self, floor_id: str) -> dict[str, Any]:
        compiled = self._compiled_floor_cached(floor_id)
        walkable = {tuple(x) for x in compiled['walkable_cells_uv']}
        reachable = self._reachable_walkable(floor_id, compiled)
        return {
            'floor_id': floor_id,
            'outside_room_instance_count': int(compiled['outside_room_instance_count']),
            'outside_room_closure_count': int(compiled.get('outside_room_closure_count', 0)),
            'closure_cell_count': int(compiled.get('closure_cell_count', 0)),
            'clearance_cell_count': int(compiled.get('clearance_cell_count', 0)),
            'protected_ingress_cell_count': int(compiled.get('protected_ingress_cell_count', 0)),
            'sealed_pocket_cell_count': int(compiled.get('sealed_pocket_cell_count', 0)),
            'portal_overlap_cell_count': int(compiled['portal_overlap_cell_count']),
            'walkable_cell_count': len(walkable),
            'reachable_walkable_cell_count': len(reachable),
            'isolated_walkable_cell_count': len(walkable - reachable),
            'portal_start_cell_count': len({tuple(x) for x in compiled['portal_inside_cells_uv']} & walkable),
            'valid': (
                int(compiled['outside_room_instance_count']) == 0
                and int(compiled.get('outside_room_closure_count', 0)) == 0
                and int(compiled['portal_overlap_cell_count']) == 0
                and len(walkable - reachable) == 0
            ),
        }

    def is_walkable(self, floor_id: str, u: int, v: int) -> bool:
        compiled = self._compiled_floor_cached(floor_id)
        return [int(u), int(v)] in compiled['walkable_cells_uv']

    def workstation_access(self, floor_id: str, workstation_id: str) -> dict[str, Any]:
        compiled = self._compiled_floor_cached(floor_id)
        layout = self.layout.floor_layout(floor_id)
        try:
            group = layout['workstation_groups'][workstation_id]
        except KeyError as exc:
            raise NavigationOccupancyError(f'Unknown workstation: {floor_id}.{workstation_id}') from exc
        chair_id = group['component_slots']['chair_main']
        by_id = {x['placement_id']: x for x in compiled['instances']}
        try:
            chair = by_id[chair_id]
        except KeyError as exc:
            raise NavigationOccupancyError(
                f'Chair footprint missing from compiled navigation: {floor_id}.{chair_id}'
            ) from exc
        chair_cells = {tuple(x) for x in chair['occupied_cells_uv']}
        room = {tuple(x) for x in compiled['room_cells_uv']}
        walkable = {tuple(x) for x in compiled['walkable_cells_uv']}
        reachable = self._reachable_walkable(floor_id, compiled)
        gate_row = next(
            (row for row in compiled.get('protected_ingress', []) if row['workstation_id'] == workstation_id),
            None,
        )
        if gate_row is None:
            approach: set[tuple[int, int]] = set()
        else:
            approach = {tuple(gate_row['cell_uv'])} & walkable
        reachable_approach = approach & reachable
        return {
            'floor_id': floor_id,
            'workstation_id': workstation_id,
            'chair_placement_id': chair_id,
            'chair_fully_inside_room': chair_cells <= room,
            'approach_policy': 'walk_to_reachable_outer_clearance_gate_then_work_seat_action_takeover',
            'transition_gate_uv': list(gate_row['cell_uv']) if gate_row is not None else None,
            'approach_cell_count': len(approach),
            'reachable_approach_cell_count': len(reachable_approach),
            'approach_cells_uv': self._sorted_cells(approach),
            'reachable_approach_cells_uv': self._sorted_cells(reachable_approach),
        }
