from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

from WORLD.RUNTIME.layout_core import LayoutCore


class OccupancyClosureError(ValueError):
    pass


class OccupancyClosureCore:
    """Derive supplemental blocked cells that close semantic furniture seams.

    Base footprints remain the canonical object geometry. This core only fills
    narrow gaps that should not be traversable: desk↔chair gaps inside one
    workstation and seams between adjacent desk footprints. Pairwise desk
    closure naturally supports arbitrary desk chains/clusters.
    """

    def __init__(self, world_root: str | Path, *, layout: LayoutCore | None = None):
        self.root = Path(world_root).resolve()
        self.layout = layout or LayoutCore(self.root)
        config_path = self.root / 'REGISTRY' / 'navigation_closure_profiles.json'
        self.config = json.loads(config_path.read_text(encoding='utf-8'))
        self.rules = self.config['rules']

    @staticmethod
    def _cell_set(instance: dict[str, Any]) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in instance['occupied_cells_uv']}

    @staticmethod
    def _bbox(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
        if not cells:
            raise OccupancyClosureError('Cannot derive closure from an empty footprint')
        us = [u for u, _ in cells]
        vs = [v for _, v in cells]
        return min(us), max(us), min(vs), max(vs)

    @classmethod
    def _gap_cells(
        cls,
        first: dict[str, Any],
        second: dict[str, Any],
        *,
        max_gap_cells: int,
        min_overlap_cells: int,
    ) -> set[tuple[int, int]]:
        a = cls._bbox(cls._cell_set(first))
        b = cls._bbox(cls._cell_set(second))
        au0, au1, av0, av1 = a
        bu0, bu1, bv0, bv1 = b

        v_lo = max(av0, bv0)
        v_hi = min(av1, bv1)
        v_overlap = v_hi - v_lo + 1
        if au1 < bu0:
            gap = bu0 - au1 - 1
            if 1 <= gap <= max_gap_cells and v_overlap >= min_overlap_cells:
                return {(u, v) for u in range(au1 + 1, bu0) for v in range(v_lo, v_hi + 1)}
        if bu1 < au0:
            gap = au0 - bu1 - 1
            if 1 <= gap <= max_gap_cells and v_overlap >= min_overlap_cells:
                return {(u, v) for u in range(bu1 + 1, au0) for v in range(v_lo, v_hi + 1)}

        u_lo = max(au0, bu0)
        u_hi = min(au1, bu1)
        u_overlap = u_hi - u_lo + 1
        if av1 < bv0:
            gap = bv0 - av1 - 1
            if 1 <= gap <= max_gap_cells and u_overlap >= min_overlap_cells:
                return {(u, v) for v in range(av1 + 1, bv0) for u in range(u_lo, u_hi + 1)}
        if bv1 < av0:
            gap = av0 - bv1 - 1
            if 1 <= gap <= max_gap_cells and u_overlap >= min_overlap_cells:
                return {(u, v) for v in range(bv1 + 1, av0) for u in range(u_lo, u_hi + 1)}
        return set()

    @staticmethod
    def _sorted_cells(cells: set[tuple[int, int]]) -> list[list[int]]:
        return [list(cell) for cell in sorted(cells, key=lambda uv: (uv[1], uv[0]))]

    def resolve_floor_closures(self, floor_id: str, instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {instance['placement_id']: instance for instance in instances}
        rows: list[dict[str, Any]] = []

        workstation_rule = self.rules['workstation_desk_chair']
        if workstation_rule.get('enabled', True):
            layout = self.layout.floor_layout(floor_id)
            for workstation_id, group in sorted(layout['workstation_groups'].items()):
                desk_id = group['component_slots']['desk']
                chair_id = group['component_slots']['chair_main']
                desk = by_id.get(desk_id)
                chair = by_id.get(chair_id)
                if desk is None or chair is None:
                    continue
                cells = self._gap_cells(
                    desk,
                    chair,
                    max_gap_cells=int(workstation_rule['max_gap_cells']),
                    min_overlap_cells=int(workstation_rule['min_overlap_cells']),
                )
                if not cells:
                    continue
                rows.append({
                    'closure_id': f'{floor_id}.closure.workstation.{workstation_id}',
                    'closure_type': 'workstation_desk_chair',
                    'workstation_id': workstation_id,
                    'source_placement_ids': [desk_id, chair_id],
                    'occupied_cells_uv': self._sorted_cells(cells),
                    'policy': workstation_rule['policy'],
                })

        desk_rule = self.rules['desk_desk_seam']
        if desk_rule.get('enabled', True):
            desks = sorted(
                (instance for instance in instances if instance['object_type'] == 'desk'),
                key=lambda row: row['placement_id'],
            )
            for first, second in combinations(desks, 2):
                cells = self._gap_cells(
                    first,
                    second,
                    max_gap_cells=int(desk_rule['max_gap_cells']),
                    min_overlap_cells=int(desk_rule['min_overlap_cells']),
                )
                if not cells:
                    continue
                first_id, second_id = first['placement_id'], second['placement_id']
                rows.append({
                    'closure_id': f'{floor_id}.closure.desk_seam.{first_id}__{second_id}',
                    'closure_type': 'desk_desk_seam',
                    'source_placement_ids': [first_id, second_id],
                    'occupied_cells_uv': self._sorted_cells(cells),
                    'policy': desk_rule['policy'],
                })

        return sorted(rows, key=lambda row: row['closure_id'])
