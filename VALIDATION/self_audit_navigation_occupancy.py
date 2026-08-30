from __future__ import annotations

import json
import sys
from pathlib import Path

# Keep the audit runnable both as ``python -m VALIDATION...`` and as the
# documented direct script invocation from the repository root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from RUNTIME.central_core import CentralGameCore


def build_audit(root: str | Path) -> dict:
    root = Path(root).resolve()
    core = CentralGameCore(root)
    floor_rows = {}
    workstation_rows = {}
    failed_floors = []
    failed_workstations = []

    for floor_id in sorted(core.world.floors):
        floor_audit = core.validate_navigation_floor(floor_id)
        floor_rows[floor_id] = floor_audit
        if not floor_audit['valid']:
            failed_floors.append(floor_id)

        for workstation_id in core.world.floor_layout(floor_id)['workstation_groups']:
            access = core.resolve_workstation_navigation_access(floor_id, workstation_id)
            key = f'{floor_id}.{workstation_id}'
            row = {
                'floor_id': floor_id,
                'workstation_id': workstation_id,
                'chair_placement_id': access['chair_placement_id'],
                'work_seat_direction': access['work_seat_direction'],
                'chair_fully_inside_room': access['chair_fully_inside_room'],
                'approach_cell_count': access['approach_cell_count'],
                'reachable_approach_cell_count': access['reachable_approach_cell_count'],
                'seat_transition_ready': access['seat_transition_ready'],
            }
            workstation_rows[key] = row
            if not row['seat_transition_ready']:
                failed_workstations.append(key)

    rules = {
        'active_footprints_must_be_inside_room': all(
            row['outside_room_instance_count'] == 0 for row in floor_rows.values()
        ),
        'active_footprints_must_not_overlap_portal': all(
            row['portal_overlap_cell_count'] == 0 for row in floor_rows.values()
        ),
        'all_walkable_cells_must_reach_portal': all(
            row['isolated_walkable_cell_count'] == 0 for row in floor_rows.values()
        ),
        'workstations_need_reachable_approach_cell': all(
            row['seat_transition_ready'] for row in workstation_rows.values()
        ),
    }
    passed = not failed_floors and not failed_workstations and all(rules.values())
    return {
        'schema': 'gds_navigation_occupancy_audit_v1',
        'status': 'PASS' if passed else 'FAIL',
        'floor_count': len(floor_rows),
        'workstation_count': len(workstation_rows),
        'failed_floor_count': len(failed_floors),
        'failed_workstation_count': len(failed_workstations),
        'failed_floors': failed_floors,
        'failed_workstations': failed_workstations,
        'rules': rules,
        'floors': floor_rows,
        'workstations': workstation_rows,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = build_audit(root)
    out = root / 'REPORTS' / 'NAVIGATION_OCCUPANCY_AUDIT.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'status': report['status'],
        'floors': report['floor_count'],
        'workstations': report['workstation_count'],
        'failed_floors': report['failed_floor_count'],
        'failed_workstations': report['failed_workstation_count'],
    }, indent=2))
    if report['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
