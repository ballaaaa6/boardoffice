from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from WORLD.RUNTIME.direction_core import DirectionCore
from WORLD.RUNTIME.layout_core import LayoutCore
from WORLD.RUNTIME.navigation_occupancy_core import NavigationOccupancyCore
from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore


class GameplayMetadataFamilyError(ValueError):
    pass


class GameplayMetadataFamilyCore:
    """Resolve and audit gameplay/spatial metadata inheritance by layout family.

    Visual skins may vary per floor. Gameplay geometry for a shared layout is
    canonicalized here so F2 is the single source of truth for all F2+ skins.
    """

    def __init__(
        self,
        world_root: str | Path,
        *,
        layout: LayoutCore | None = None,
        room_navigation: RoomNavigationCore | None = None,
        occupancy: NavigationOccupancyCore | None = None,
        directions: DirectionCore | None = None,
    ):
        self.root = Path(world_root).resolve()
        self.layout = layout or LayoutCore(self.root)
        self.room_navigation = room_navigation or RoomNavigationCore(self.root)
        self.occupancy = occupancy or NavigationOccupancyCore(self.root)
        self.directions = directions or DirectionCore(self.root)
        payload = json.loads(
            (self.root / 'REGISTRY' / 'gameplay_metadata_families.json').read_text(encoding='utf-8')
        )
        self.families = payload['families']
        self._family_by_layout = {row['layout_id']: row for row in self.families.values()}

    def family_for_floor(self, floor_id: str) -> dict[str, Any]:
        floor = self.layout.floor_record(floor_id)
        layout_id = floor['layout_id']
        try:
            family = deepcopy(self._family_by_layout[layout_id])
        except KeyError as exc:
            raise GameplayMetadataFamilyError(f'No gameplay metadata family for layout {layout_id}') from exc
        members = sorted(
            fid for fid, row in self.layout.floors.items() if row['layout_id'] == layout_id
        )
        family['floor_id'] = floor_id
        family['derived_from_canonical'] = floor_id != family['canonical_floor_id']
        family['family_floor_ids'] = members
        family['family_floor_count'] = len(members)
        return family

    def placement_override(self, floor_id: str, placement_id: str) -> dict[str, Any] | None:
        family = self.family_for_floor(floor_id)
        row = family.get('placement_overrides', {}).get(placement_id)
        return deepcopy(row) if row is not None else None

    @staticmethod
    def _cell_set(rows: list[list[int]]) -> set[tuple[int, int]]:
        return {tuple(map(int, row)) for row in rows}

    def _direction_map(self, floor_id: str) -> dict[str, str]:
        groups = self.layout.floor_layout(floor_id)['workstation_groups']
        return {
            workstation_id: self.directions.resolve_workstation_direction(floor_id, workstation_id)
            for workstation_id in sorted(groups)
        }

    def _instance_geometry(self, compiled: dict[str, Any]) -> dict[str, tuple]:
        out: dict[str, tuple] = {}
        for row in compiled['instances']:
            out[row['placement_id']] = (
                row['object_type'],
                row['profile_id'],
                tuple(tuple(pt) for pt in row['outer_corners_world_px']),
                frozenset(tuple(cell) for cell in row['occupied_cells_uv']),
            )
        return out

    def audit_family(self, floor_or_family_id: str) -> dict[str, Any]:
        if floor_or_family_id in self.families:
            family = deepcopy(self.families[floor_or_family_id])
            members = sorted(
                fid for fid, row in self.layout.floors.items() if row['layout_id'] == family['layout_id']
            )
        else:
            family = self.family_for_floor(floor_or_family_id)
            members = family['family_floor_ids']

        canonical_id = family['canonical_floor_id']
        canonical_room_cells = self.room_navigation.room_cell_set(canonical_id)
        canonical_portal = self.room_navigation.portal(canonical_id)
        canonical_occ = self.occupancy.resolve_floor(canonical_id)
        canonical_dirs = self._direction_map(canonical_id)
        canonical_layout = self.layout.floor_layout(canonical_id)

        checks = {
            'room_cells_exact': True,
            'portal_geometry_exact': True,
            'layout_geometry_shared': True,
            'workstation_directions_exact': True,
            'base_occupancy_exact': True,
            'closure_exact': True,
            'clearance_exact': True,
            'final_walkable_exact': True,
            'instance_footprint_geometry_exact': True,
        }
        mismatches: list[dict[str, Any]] = []

        canonical_portal_geom = {
            'edge_uv': canonical_portal['edge_uv'],
            'inside_cells_uv': canonical_portal['inside_cells_uv'],
            'outside_cells_uv': canonical_portal['outside_cells_uv'],
        }
        canonical_sets = {
            'base_occupancy_exact': self._cell_set(canonical_occ['base_occupied_cells_uv']),
            'closure_exact': self._cell_set(canonical_occ['closure_cells_uv']),
            'clearance_exact': self._cell_set(canonical_occ['clearance_cells_uv']),
            'final_walkable_exact': self._cell_set(canonical_occ['walkable_cells_uv']),
        }
        canonical_instances = self._instance_geometry(canonical_occ)

        for floor_id in members:
            floor_portal = self.room_navigation.portal(floor_id)
            floor_occ = self.occupancy.resolve_floor(floor_id)

            current = {
                'room_cells_exact': self.room_navigation.room_cell_set(floor_id) == canonical_room_cells,
                'portal_geometry_exact': {
                    'edge_uv': floor_portal['edge_uv'],
                    'inside_cells_uv': floor_portal['inside_cells_uv'],
                    'outside_cells_uv': floor_portal['outside_cells_uv'],
                } == canonical_portal_geom,
                'layout_geometry_shared': self.layout.floor_record(floor_id)['layout_id'] == family['layout_id']
                    and self.layout.floor_layout(floor_id) == canonical_layout,
                'workstation_directions_exact': self._direction_map(floor_id) == canonical_dirs,
                'base_occupancy_exact': self._cell_set(floor_occ['base_occupied_cells_uv']) == canonical_sets['base_occupancy_exact'],
                'closure_exact': self._cell_set(floor_occ['closure_cells_uv']) == canonical_sets['closure_exact'],
                'clearance_exact': self._cell_set(floor_occ['clearance_cells_uv']) == canonical_sets['clearance_exact'],
                'final_walkable_exact': self._cell_set(floor_occ['walkable_cells_uv']) == canonical_sets['final_walkable_exact'],
                'instance_footprint_geometry_exact': self._instance_geometry(floor_occ) == canonical_instances,
            }
            for name, ok in current.items():
                if not ok:
                    checks[name] = False
                    mismatches.append({'floor_id': floor_id, 'check': name})

        return {
            'schema': 'gds_gameplay_metadata_family_audit_v1',
            'status': 'PASS' if not mismatches else 'FAIL',
            'family_id': family['family_id'],
            'layout_id': family['layout_id'],
            'canonical_floor_id': canonical_id,
            'family_floor_count': len(members),
            'checked_floor_count': len(members),
            'family_floor_ids': members,
            'checks': checks,
            'mismatch_count': len(mismatches),
            'mismatches': mismatches,
            'synchronized_domains': deepcopy(family['synchronized_domains']),
            'skin_only_domains': deepcopy(family['skin_only_domains']),
        }
