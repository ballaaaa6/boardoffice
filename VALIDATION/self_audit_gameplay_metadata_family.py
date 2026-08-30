from __future__ import annotations

import json
import sys
from pathlib import Path


def audit(core_root: str | Path, *, write_report: bool = True) -> dict:
    root = Path(core_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from RUNTIME.central_core import CentralGameCore

    core = CentralGameCore(root)
    family = core.resolve_gameplay_metadata_family('floor02')
    family_audit = core.audit_gameplay_metadata_family('floor02')
    expected_corners = [[241, 359], [311, 394], [265, 417], [195, 382]]
    reception_errors = []
    for floor_id in family['family_floor_ids']:
        compiled = core.resolve_navigation_cells(floor_id)
        receptions = [r for r in compiled['instances'] if r['placement_id'] == 'reception']
        if len(receptions) != 1:
            reception_errors.append({'floor_id': floor_id, 'error': f'reception count {len(receptions)}'})
            continue
        row = receptions[0]
        if row['outer_corners_world_px'] != expected_corners:
            reception_errors.append({'floor_id': floor_id, 'error': 'world corners drift'})
        if len(row['occupied_cells_uv']) != 805:
            reception_errors.append({'floor_id': floor_id, 'error': 'occupied cell count drift'})
        if row.get('canonical_ground_anchor_world_px') != [259, 376]:
            reception_errors.append({'floor_id': floor_id, 'error': 'ground anchor drift'})
        nav_audit = core.validate_navigation_floor(floor_id)
        if not nav_audit['valid']:
            reception_errors.append({'floor_id': floor_id, 'error': 'navigation invalid'})

    report = {
        'schema': 'gds_phase8b_hardened_family_audit_v1',
        'status': 'PASS' if family_audit['status'] == 'PASS' and not reception_errors else 'FAIL',
        'family': family,
        'family_audit': family_audit,
        'reception_expected': {
            'canonical_ground_anchor_world_px': [259, 376],
            'profile_origin_offset_uv_cells': [-13, -4],
            'effective_outer_corners_world_px': expected_corners,
            'occupied_cell_count': 805,
            'profile_axes': {'u_cells': 35, 'v_cells': 23}
        },
        'reception_error_count': len(reception_errors),
        'reception_errors': reception_errors,
    }
    if write_report:
        out = root / 'REPORTS' / 'PHASE8B_F2_CANONICAL_RECEPTION_AUDIT.json'
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--core-root', default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--no-write', action='store_true')
    ns = ap.parse_args()
    result = audit(ns.core_root, write_report=not ns.no_write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
