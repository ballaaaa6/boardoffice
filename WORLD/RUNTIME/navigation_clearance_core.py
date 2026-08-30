from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

from WORLD.RUNTIME.layout_core import LayoutCore


class NavigationClearanceError(ValueError):
    pass


class NavigationClearanceCore:
    """Derive navigation-only furniture clearance with edge-aware relief.

    Authored footprints and semantic closures stay immutable. Clearance is a
    navigation-only layer. Chairs may give back clearance at room boundaries or
    symmetrically between separate furniture islands so +4 buffers do not create
    artificial dead ends. WorkSeat transition gates always live on the reachable
    exterior of the final furniture-clearance island.
    """

    NEIGHBORS = ((1, 0), (-1, 0), (0, 1), (0, -1))
    OUTWARD = {
        'u_minus': (-1, 0),
        'u_plus': (1, 0),
        'v_minus': (0, -1),
        'v_plus': (0, 1),
    }

    def __init__(self, world_root: str | Path, *, layout: LayoutCore | None = None):
        self.root = Path(world_root).resolve()
        self.layout = layout or LayoutCore(self.root)
        path = self.root / 'REGISTRY' / 'navigation_clearance_profiles.json'
        self.config = json.loads(path.read_text(encoding='utf-8'))
        self.rules = self.config['rules']

    @staticmethod
    def _cell_set(instance: dict[str, Any]) -> set[tuple[int, int]]:
        return {tuple(cell) for cell in instance['occupied_cells_uv']}

    @staticmethod
    def _bbox(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
        if not cells:
            raise NavigationClearanceError('Cannot derive clearance from empty footprint')
        us = [u for u, _ in cells]
        vs = [v for _, v in cells]
        return min(us), max(us), min(vs), max(vs)

    @staticmethod
    def _sorted_cells(cells: set[tuple[int, int]]) -> list[list[int]]:
        return [list(cell) for cell in sorted(cells, key=lambda uv: (uv[1], uv[0]))]

    @classmethod
    def _expanded_bbox(cls, instance: dict[str, Any], expand: dict[str, int]) -> tuple[int, int, int, int]:
        u0, u1, v0, v1 = cls._bbox(cls._cell_set(instance))
        return (
            u0 - int(expand['u_minus']),
            u1 + int(expand['u_plus']),
            v0 - int(expand['v_minus']),
            v1 + int(expand['v_plus']),
        )

    @classmethod
    def _expanded_cells(cls, instance: dict[str, Any], expand: dict[str, int]) -> set[tuple[int, int]]:
        u0, u1, v0, v1 = cls._expanded_bbox(instance, expand)
        return {(u, v) for v in range(v0, v1 + 1) for u in range(u0, u1 + 1)}

    @classmethod
    def _center(cls, instance: dict[str, Any]) -> tuple[float, float]:
        u0, u1, v0, v1 = cls._bbox(cls._cell_set(instance))
        return ((u0 + u1) / 2.0, (v0 + v1) / 2.0)

    @classmethod
    def _reachable(
        cls,
        walkable: set[tuple[int, int]],
        starts: set[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        seen = set(starts) & walkable
        stack = list(seen)
        while stack:
            u, v = stack.pop()
            for du, dv in cls.NEIGHBORS:
                nxt = (u + du, v + dv)
                if nxt in walkable and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    @classmethod
    def _outer_boundary_candidates(
        cls,
        region: set[tuple[int, int]],
        reachable_walkable: set[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        out: set[tuple[int, int]] = set()
        for u, v in region:
            for du, dv in cls.NEIGHBORS:
                nxt = (u + du, v + dv)
                if nxt in reachable_walkable:
                    out.add(nxt)
        return out

    @classmethod
    def _boundary_touch_directions(
        cls,
        instance: dict[str, Any],
        expand: dict[str, int],
        room_cells: set[tuple[int, int]],
    ) -> set[str]:
        u0, u1, v0, v1 = cls._expanded_bbox(instance, expand)
        side_cells = {
            'u_minus': {(u0, v) for v in range(v0, v1 + 1)},
            'u_plus': {(u1, v) for v in range(v0, v1 + 1)},
            'v_minus': {(u, v0) for u in range(u0, u1 + 1)},
            'v_plus': {(u, v1) for u in range(u0, u1 + 1)},
        }
        touched: set[str] = set()
        for direction, cells in side_cells.items():
            du, dv = cls.OUTWARD[direction]
            if cells - room_cells:
                touched.add(direction)
                continue
            if any(
                cell in room_cells and (cell[0] + du, cell[1] + dv) not in room_cells
                for cell in cells
            ):
                touched.add(direction)
        return touched

    @staticmethod
    def _closure_components(
        instances: list[dict[str, Any]],
        closures: list[dict[str, Any]],
    ) -> dict[str, str]:
        parent = {row['placement_id']: row['placement_id'] for row in instances}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

        for row in closures:
            ids = [pid for pid in row.get('source_placement_ids', []) if pid in parent]
            for first, second in zip(ids, ids[1:]):
                union(first, second)
        return {pid: find(pid) for pid in parent}

    @classmethod
    def _chair_facing_relation(
        cls,
        first: dict[str, Any],
        second: dict[str, Any],
        first_expand: dict[str, int],
        second_expand: dict[str, int],
    ) -> tuple[str, str, int] | None:
        """Return facing expansion directions and current corridor width.

        Only axis-aligned chair pairs whose *base* footprints overlap on the
        orthogonal axis qualify. This avoids opening diagonal/corner shortcuts.
        corridor width 0 means clearance rectangles touch edge-to-edge; negative
        values mean they overlap.
        """
        au0, au1, av0, av1 = cls._bbox(cls._cell_set(first))
        bu0, bu1, bv0, bv1 = cls._bbox(cls._cell_set(second))
        aeu0, aeu1, aev0, aev1 = cls._expanded_bbox(first, first_expand)
        beu0, beu1, bev0, bev1 = cls._expanded_bbox(second, second_expand)

        base_v_overlap = min(av1, bv1) - max(av0, bv0) + 1
        if base_v_overlap > 0:
            if au1 < bu0:
                return 'u_plus', 'u_minus', beu0 - aeu1 - 1
            if bu1 < au0:
                return 'u_minus', 'u_plus', aeu0 - beu1 - 1

        base_u_overlap = min(au1, bu1) - max(au0, bu0) + 1
        if base_u_overlap > 0:
            if av1 < bv0:
                return 'v_plus', 'v_minus', bev0 - aev1 - 1
            if bv1 < av0:
                return 'v_minus', 'v_plus', aev0 - bev1 - 1
        return None

    def _workstation_transition_gates(
        self,
        floor_id: str,
        by_id: dict[str, dict[str, Any]],
        raw_clearance_by_placement: dict[str, set[tuple[int, int]]],
        reachable_walkable: set[tuple[int, int]],
    ) -> list[dict[str, Any]]:
        if not self.rules['chair'].get('preserve_workstation_ingress', False):
            return []

        rows: list[dict[str, Any]] = []
        layout = self.layout.floor_layout(floor_id)
        for workstation_id, group in sorted(layout['workstation_groups'].items()):
            chair_id = group['component_slots']['chair_main']
            desk_id = group['component_slots']['desk']
            chair = by_id.get(chair_id)
            desk = by_id.get(desk_id)
            if chair is None:
                continue

            chair_region = self._cell_set(chair) | set(raw_clearance_by_placement.get(chair_id, set()))
            candidates = self._outer_boundary_candidates(chair_region, reachable_walkable)
            gate_scope = 'chair_clearance_outer_boundary'
            if not candidates and desk is not None:
                workstation_region = (
                    chair_region
                    | self._cell_set(desk)
                    | set(raw_clearance_by_placement.get(desk_id, set()))
                )
                candidates = self._outer_boundary_candidates(workstation_region, reachable_walkable)
                gate_scope = 'workstation_clearance_outer_boundary'
            if not candidates:
                candidates = set(reachable_walkable)
                gate_scope = 'nearest_reachable_cell_outside_connected_furniture_cluster'
            if not candidates:
                raise NavigationClearanceError(
                    f'{floor_id}.{workstation_id}: floor has no reachable transition gate'
                )

            chair_center = self._center(chair)
            desk_center = self._center(desk) if desk is not None else chair_center

            def score(cell: tuple[int, int]):
                u, v = cell
                distance_to_chair = abs(u - chair_center[0]) + abs(v - chair_center[1])
                distance_from_desk = abs(u - desk_center[0]) + abs(v - desk_center[1])
                return (distance_to_chair, -distance_from_desk, v, u)

            gate = min(candidates, key=score)
            rows.append({
                'workstation_id': workstation_id,
                'chair_placement_id': chair_id,
                'desk_placement_id': desk_id,
                'cell_uv': list(gate),
                'gate_scope': gate_scope,
                'policy': 'reachable_outer_clearance_gate_then_workseat_state_takeover',
            })
        return rows

    def resolve_floor_clearance(
        self,
        floor_id: str,
        instances: list[dict[str, Any]],
        *,
        room_cells: set[tuple[int, int]],
        portal_cells: set[tuple[int, int]],
        base_occupied_cells: set[tuple[int, int]],
        closure_cells: set[tuple[int, int]],
        closures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        by_id = {instance['placement_id']: instance for instance in instances}
        existing_occupied = set(base_occupied_cells) | set(closure_cells)
        pre_clearance_walkable = set(room_cells) - existing_occupied
        closures = list(closures or [])

        chair_rule = self.rules.get('chair', {})
        boundary_amount = int(chair_rule.get('boundary_relief_cells', 0))
        pair_amount = int(chair_rule.get('pair_overlap_relief_cells', 0))
        target_corridor = int(chair_rule.get('pair_target_corridor_cells', 0))

        effective_expand: dict[str, dict[str, int]] = {}
        default_expand: dict[str, dict[str, int]] = {}
        boundary_relief_records: list[dict[str, Any]] = []
        boundary_relief_cells: set[tuple[int, int]] = set()

        # Stage 1: directional room-boundary relief for chairs only.
        for instance in sorted(instances, key=lambda row: row['placement_id']):
            object_type = instance['object_type']
            rule = self.rules.get(object_type)
            if rule is None or not rule.get('enabled', True):
                continue
            base_expand = {key: int(value) for key, value in rule['expand_cells'].items()}
            floor_overrides = self.config.get('placement_overrides', {}).get(floor_id, {})
            placement_override = floor_overrides.get(instance['placement_id'], {})
            for direction, value in placement_override.get('expand_cells', {}).items():
                if direction not in base_expand:
                    raise NavigationClearanceError(
                        f'{floor_id}.{instance["placement_id"]}: unknown clearance direction {direction}'
                    )
                base_expand[direction] = int(value)
            default_expand[instance['placement_id']] = dict(base_expand)
            current = dict(base_expand)
            if object_type == 'chair' and boundary_amount > 0:
                touched = self._boundary_touch_directions(instance, base_expand, room_cells)
                relieved: dict[str, int] = {}
                for direction in sorted(touched):
                    amount = min(boundary_amount, current[direction])
                    if amount <= 0:
                        continue
                    current[direction] -= amount
                    relieved[direction] = amount
                if relieved:
                    before = (self._expanded_cells(instance, base_expand) & room_cells) - existing_occupied
                    after = (self._expanded_cells(instance, current) & room_cells) - existing_occupied
                    restored = before - after
                    boundary_relief_cells.update(restored)
                    boundary_relief_records.append({
                        'relief_id': f"{floor_id}.boundary_relief.{instance['placement_id']}",
                        'source_placement_id': instance['placement_id'],
                        'relieved_directions': relieved,
                        'default_expand_cells': dict(base_expand),
                        'effective_expand_cells': dict(current),
                        'restored_cells_uv': self._sorted_cells(restored),
                        'policy': 'chair_clearance_clip_to_room_then_reduce_boundary_facing_side',
                    })
            effective_expand[instance['placement_id']] = current

        # Stage 2: separate furniture islands whose chair buffers touch/overlap.
        component_by_placement = self._closure_components(instances, closures)
        chairs = sorted(
            (row for row in instances if row['object_type'] == 'chair' and row['placement_id'] in effective_expand),
            key=lambda row: row['placement_id'],
        )
        pair_requests: list[dict[str, Any]] = []
        pair_reduction_by_side: dict[tuple[str, str], int] = {}
        if pair_amount > 0:
            for first, second in combinations(chairs, 2):
                first_id, second_id = first['placement_id'], second['placement_id']
                same_island = component_by_placement.get(first_id) == component_by_placement.get(second_id)
                if same_island:
                    continue
                relation = self._chair_facing_relation(
                    first, second, effective_expand[first_id], effective_expand[second_id]
                )
                if relation is None:
                    continue
                first_dir, second_dir, corridor_before = relation
                if corridor_before > 0:
                    continue
                first_relief = min(pair_amount, effective_expand[first_id][first_dir])
                second_relief = min(pair_amount, effective_expand[second_id][second_dir])
                if first_relief <= 0 or second_relief <= 0:
                    continue
                pair_reduction_by_side[(first_id, first_dir)] = max(
                    pair_reduction_by_side.get((first_id, first_dir), 0), first_relief
                )
                pair_reduction_by_side[(second_id, second_dir)] = max(
                    pair_reduction_by_side.get((second_id, second_dir), 0), second_relief
                )
                pair_requests.append({
                    'first': first,
                    'second': second,
                    'first_direction': first_dir,
                    'second_direction': second_dir,
                    'corridor_before': corridor_before,
                })

        before_pair_expand = {pid: dict(expand) for pid, expand in effective_expand.items()}
        for (placement_id, direction), amount in pair_reduction_by_side.items():
            effective_expand[placement_id][direction] -= amount

        chair_pair_relief_records: list[dict[str, Any]] = []
        chair_pair_relief_cells: set[tuple[int, int]] = set()
        for request in pair_requests:
            first, second = request['first'], request['second']
            first_id, second_id = first['placement_id'], second['placement_id']
            first_before = (self._expanded_cells(first, before_pair_expand[first_id]) & room_cells) - existing_occupied
            first_after = (self._expanded_cells(first, effective_expand[first_id]) & room_cells) - existing_occupied
            second_before = (self._expanded_cells(second, before_pair_expand[second_id]) & room_cells) - existing_occupied
            second_after = (self._expanded_cells(second, effective_expand[second_id]) & room_cells) - existing_occupied
            restored = (first_before - first_after) | (second_before - second_after)
            chair_pair_relief_cells.update(restored)
            relation_after = self._chair_facing_relation(
                first, second, effective_expand[first_id], effective_expand[second_id]
            )
            corridor_after = relation_after[2] if relation_after is not None else target_corridor
            if corridor_after < target_corridor:
                raise NavigationClearanceError(
                    f'{floor_id}: chair pair relief cannot open target corridor between '
                    f'{first_id} and {second_id}: {corridor_after} < {target_corridor}'
                )
            chair_pair_relief_records.append({
                'relief_id': f'{floor_id}.chair_pair_relief.{first_id}__{second_id}',
                'chair_placement_ids': [first_id, second_id],
                'first_direction': request['first_direction'],
                'second_direction': request['second_direction'],
                'relief_cells_per_chair': pair_amount,
                'target_corridor_cells': target_corridor,
                'corridor_width_before_cells': request['corridor_before'],
                'corridor_width_cells': corridor_after,
                'same_furniture_island': False,
                'restored_cells_uv': self._sorted_cells(restored),
                'policy': 'symmetric_chair_clearance_relief_between_separate_furniture_islands',
            })

        # Stage 3: final clearance cells after all directional relief.
        records: list[dict[str, Any]] = []
        raw_clearance_by_placement: dict[str, set[tuple[int, int]]] = {}
        raw_union: set[tuple[int, int]] = set()
        for instance in sorted(instances, key=lambda row: row['placement_id']):
            placement_id = instance['placement_id']
            object_type = instance['object_type']
            if placement_id not in effective_expand:
                continue
            supplemental = (self._expanded_cells(instance, effective_expand[placement_id]) & room_cells) - existing_occupied
            raw_clearance_by_placement[placement_id] = set(supplemental)
            raw_union.update(supplemental)
            if supplemental:
                records.append({
                    'clearance_id': f'{floor_id}.clearance.{placement_id}',
                    'clearance_type': f'{object_type}_clearance',
                    'source_placement_id': placement_id,
                    'object_type': object_type,
                    'expand_cells': dict(effective_expand[placement_id]),
                    'default_expand_cells': dict(default_expand[placement_id]),
                    'policy': self.rules[object_type]['policy'],
                    'occupied_cells_uv': self._sorted_cells(supplemental),
                })

        provisional_walkable = pre_clearance_walkable - raw_union
        reachable = self._reachable(provisional_walkable, set(portal_cells))
        sealed_pockets = provisional_walkable - reachable
        clearance_union = set(raw_union) | set(sealed_pockets)
        if sealed_pockets:
            records.append({
                'clearance_id': f'{floor_id}.clearance.isolated_pocket_seal',
                'clearance_type': 'isolated_pocket_seal',
                'source_placement_id': None,
                'object_type': 'derived_navigation',
                'expand_cells': None,
                'default_expand_cells': None,
                'policy': 'seal_walkable_cells_disconnected_from_main_portal_after_clearance',
                'occupied_cells_uv': self._sorted_cells(sealed_pockets),
            })

        final_walkable = pre_clearance_walkable - clearance_union
        final_reachable = self._reachable(final_walkable, set(portal_cells))
        if final_walkable != final_reachable:
            raise NavigationClearanceError(
                f'{floor_id}: clearance sealing failed to remove all disconnected navigation pockets'
            )

        transition_gates = self._workstation_transition_gates(
            floor_id,
            by_id,
            raw_clearance_by_placement,
            final_reachable,
        )
        gate_cells = {tuple(row['cell_uv']) for row in transition_gates}

        return {
            'clearance_cells_uv': self._sorted_cells(clearance_union),
            'clearance_records': sorted(records, key=lambda row: row['clearance_id']),
            'protected_ingress_cells_uv': self._sorted_cells(gate_cells),
            'protected_ingress': transition_gates,
            'sealed_pocket_cells_uv': self._sorted_cells(sealed_pockets),
            'boundary_relief_cells_uv': self._sorted_cells(boundary_relief_cells - existing_occupied),
            'boundary_relief_records': sorted(boundary_relief_records, key=lambda row: row['relief_id']),
            'chair_pair_relief_cells_uv': self._sorted_cells(chair_pair_relief_cells - existing_occupied),
            'chair_pair_relief_records': sorted(chair_pair_relief_records, key=lambda row: row['relief_id']),
        }
