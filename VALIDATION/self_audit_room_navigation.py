from __future__ import annotations
import json
from pathlib import Path

try:
    from VALIDATION._common import resolve_root
except ModuleNotFoundError:
    from _common import resolve_root


def audit(root: str | Path, *, write_report: bool = True) -> dict:
    root=resolve_root(root)
    from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore
    nav=RoomNavigationCore(root/'WORLD')
    floors=nav.floors
    errors=[]
    counts={'floor_count':len(floors),'f0_family':0,'f1_family':0,'f2_plus_family':0}
    for fid, frec in floors.items():
        fam=nav.family(fid)
        layout=frec['layout_id']
        expected={'layout.floor00.small':'floor00','layout.floor01.medium':'floor01','layout.floor02.large':'floor02'}[layout]
        if fam['canonical_floor_id'] != expected:
            errors.append(f'{fid}: expected {expected}, got {fam["canonical_floor_id"]}')
        if expected=='floor00': counts['f0_family']+=1
        elif expected=='floor01': counts['f1_family']+=1
        else: counts['f2_plus_family']+=1
        domain=nav.domain(fid); portal=nav.portal(fid); cells=nav.room_cells(fid)
        if domain['canonical_floor_id'] != expected or portal['canonical_floor_id'] != expected or cells['canonical_floor_id'] != expected:
            errors.append(f'{fid}: domain/portal/cells canonical mismatch')
        if cells['room_cell_count'] != domain['room_cell_count']:
            errors.append(f'{fid}: room cell count mismatch')
        if not portal['inside_cells_uv'] or len(portal['inside_cells_uv']) != len(portal['outside_cells_uv']):
            errors.append(f'{fid}: invalid portal strips')
    canonical_domains=set(nav.domain_registry['domains'])
    canonical_portals=set(nav.portal_registry['portals'])
    compiled=sorted(p.name for p in (root/'WORLD/COMPILED_NAV').glob('*.json'))
    active_absent=[
        'WORLD/REGISTRY/grid_calibration.json','WORLD/RUNTIME/grid_core.py',
        'WORLD/REGISTRY/embedded_solids.json','WORLD/REGISTRY/embedded_assets.json','WORLD/REGISTRY/pixel_collision_profiles.json',
        'WORLD/RUNTIME/embedded_solid_core.py','WORLD/RUNTIME/pixel_collision_core.py',
    ]
    for rel in active_absent:
        if (root/rel).exists(): errors.append(f'legacy active path still exists: {rel}')
    pointer_path=root/'LEGACY_ARCHIVE_POINTER.json'
    archive_pointer=json.load(open(pointer_path,encoding='utf-8')) if pointer_path.exists() else {}
    checks={
        'fine_grid_is_permanent_canonical': nav.grid['profile_id']=='grid.iso.occupancy_fine.v1' and nav.grid['tile_width_px']==4 and nav.grid['tile_height_px']==2 and 'subdivision_of' not in nav.grid,
        'only_three_canonical_domains': canonical_domains=={'floor00','floor01','floor02'},
        'only_three_canonical_portals': canonical_portals=={'floor00.main_exit','floor01.main_exit','floor02.main_exit'},
        'only_three_compiled_masks': compiled==['floor00_room_cells.json','floor01_room_cells.json','floor02_room_cells.json'],
        'all_25_floors_bound': len(nav.bindings['floor_bindings'])==25 and len(floors)==25,
        'f2_plus_family_count': counts['f2_plus_family']==23,
        'legacy_active_paths_removed': not any((root/p).exists() for p in active_absent),
        'legacy_solid_archive_externalized': not (root/'LEGACY_ARCHIVE').exists() and archive_pointer.get('status')=='EXTERNAL_ARCHIVE_INACTIVE' and archive_pointer.get('embedded_solid_asset_count')==14 and archive_pointer.get('navigation_dependency') is False and len(archive_pointer.get('zip_sha256',''))==64,
        'no_resolution_errors': not errors,
    }
    report={
        'schema':'gds.room_navigation_audit.v1',
        'status':'PASS' if all(checks.values()) else 'FAIL',
        'pass':all(checks.values()),
        'checks':checks,
        'counts':counts,
        'canonical_room_cell_counts':{fid:nav.domain(fid)['room_cell_count'] for fid in ('floor00','floor01','floor02')},
        'canonical_portal_widths':{fid:len(nav.portal(fid)['inside_cells_uv']) for fid in ('floor00','floor01','floor02')},
        'errors':errors,
    }
    if write_report:
        p=root/'REPORTS/ROOM_NAVIGATION_AUDIT.json'; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    r=audit(resolve_root(anchor=__file__)); print(json.dumps(r,indent=2,ensure_ascii=False)); raise SystemExit(0 if r['pass'] else 1)
