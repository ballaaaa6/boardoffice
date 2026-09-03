from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from VALIDATION._common import resolve_root
except ModuleNotFoundError:
    from _common import resolve_root


ACTOR_SIZE = (32, 42)
ACTOR_ANCHOR = (16, 31)
CHECKED_OBJECT_TYPES = frozenset({'desk', 'chair', 'reception'})


def _local_front_y(corners: list[list[int]], world_x: float) -> float | None:
    points = [(float(x), float(y)) for x, y in corners]
    if not points:
        return None
    world_x = min(
        max(float(world_x), min(x for x, _ in points)),
        max(x for x, _ in points),
    )
    intersections: list[float] = []
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        if x0 == x1:
            if world_x == x0:
                intersections.extend([y0, y1])
            continue
        if min(x0, x1) <= world_x <= max(x0, x1):
            progress = (world_x - x0) / (x1 - x0)
            intersections.append(y0 + (y1 - y0) * progress)
    return max(intersections) if intersections else None


def _actor_overlaps_alpha(depth, row: dict[str, Any], ground_xy: tuple[int, int]) -> bool:
    sprite = depth._load_occluder_visual(row)
    placement = row['placement']
    actor_x0 = int(round(float(ground_xy[0]) - ACTOR_ANCHOR[0]))
    actor_y0 = int(round(float(ground_xy[1]) - ACTOR_ANCHOR[1]))
    object_x0 = int(placement['x_px'])
    object_y0 = int(placement['y_px'])
    ix0 = max(actor_x0, object_x0)
    iy0 = max(actor_y0, object_y0)
    ix1 = min(actor_x0 + ACTOR_SIZE[0], object_x0 + sprite.width)
    iy1 = min(actor_y0 + ACTOR_SIZE[1], object_y0 + sprite.height)
    if ix0 >= ix1 or iy0 >= iy1:
        return False
    crop = sprite.getchannel('A').crop(
        (ix0 - object_x0, iy0 - object_y0, ix1 - object_x0, iy1 - object_y0)
    )
    return crop.getbbox() is not None


def audit(core_root: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    root = resolve_root(core_root)

    from RUNTIME.character_movement_core import CharacterMovementCore
    from WORLD.RUNTIME.walking_depth_core import WalkingDepthCore

    movement = CharacterMovementCore(root)
    depth = WalkingDepthCore(root / 'WORLD')
    issues: list[dict[str, Any]] = []
    checked_floors = 0
    checked_rows = 0
    skipped_profiled_rows = 0
    candidate_counts = Counter()

    for floor_id in sorted(depth.layout.floors):
        checked_floors += 1
        compiled = depth.occupancy.resolve_floor(floor_id)
        walkable_points = [
            movement.uv_cell_center_to_pixel(*cell)
            for cell in compiled['walkable_cells_uv']
        ]
        rows = [
            row
            for row in depth.resolve_occluders(floor_id)
            if (
                not row['always_foreground']
                and row['object_type'] in CHECKED_OBJECT_TYPES
                and row['depth_footprint_corners_world_px']
            )
        ]
        for row in rows:
            checked_rows += 1
            if row['depth_front_edge_world_px'] is not None:
                skipped_profiled_rows += 1
                continue
            corners = row['depth_footprint_corners_world_px']
            min_x = min(x for x, _ in corners)
            max_x = max(x for x, _ in corners)
            scalar_anchor = float(row['depth_anchor_y_px'])
            row_candidates = []
            for ground_xy in walkable_points:
                world_x, world_y = ground_xy
                if not min_x <= world_x <= max_x:
                    continue
                front_y = _local_front_y(corners, world_x)
                if front_y is None:
                    continue
                if not (front_y <= world_y < scalar_anchor):
                    continue
                if not _actor_overlaps_alpha(depth, row, ground_xy):
                    continue
                row_candidates.append({
                    'ground_xy': [int(ground_xy[0]), int(ground_xy[1])],
                    'scalar_anchor_y_px': scalar_anchor,
                    'derived_front_y_px': round(front_y, 4),
                })
            if row_candidates:
                candidate_counts[row['object_type']] += len(row_candidates)
                issues.append({
                    'floor_id': floor_id,
                    'placement_id': row['placement_id'],
                    'object_type': row['object_type'],
                    'candidate_count': len(row_candidates),
                    'sample': row_candidates[:5],
                })

    report = {
        'schema': 'gds.walking_depth_profile_guard.v1',
        'status': 'PASS' if not issues else 'FAIL',
        'checked_floor_count': checked_floors,
        'checked_row_count': checked_rows,
        'profiled_row_count': skipped_profiled_rows,
        'unprofiled_front_envelope_issue_count': len(issues),
        'candidate_counts_by_object_type': dict(sorted(candidate_counts.items())),
        'issues': issues,
        'policy': (
            'reachable actor ground anchors inside each object footprint X span '
            'must not disagree between scalar depth and the local front envelope '
            'unless the object has an explicit front_edge_by_ground_x profile'
        ),
    }
    if write_report:
        output = root / 'REPORTS' / 'WALKING_DEPTH_PROFILE_GUARD.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
    return report


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--core-root', default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--no-write', action='store_true')
    args = parser.parse_args()
    result = audit(args.core_root, write_report=not args.no_write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
