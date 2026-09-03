from __future__ import annotations

import json
from collections import Counter

try:
    from VALIDATION._common import resolve_root
except ModuleNotFoundError:
    from _common import resolve_root

ROOT=resolve_root(anchor=__file__)
from WORLD.RUNTIME.ground_footprint_core import GroundFootprintCore

fp=GroundFootprintCore(ROOT/'WORLD')

def expected_ceo_transform(asset_id: str) -> str:
    return 'NORMAL' if asset_id in {'floor00.ceo_desk','floor01.ceo_desk'} else 'FLIP_X'

errors=[]
counts=Counter()

# Fine-grid contract
fine=fp.fine_grid_profile()
if fine['u_step_px'] != [2,1]: errors.append('fine u step drift')
if fine['v_step_px'] != [-2,1]: errors.append('fine v step drift')
if fine['tile_width_px'] != 4 or fine['tile_height_px'] != 2: errors.append('fine tile size drift')
if fine['grid_origin_px'] != [28,0]: errors.append('fine grid origin drift')
if 'subdivision_of' in fine: errors.append('fine grid must not depend on retired coarse grid')

# No mirrored duplicate profile
if 'footprint.desk.mirrored' in fp.profiles: errors.append('mirrored desk footprint must be derived, not stored')

# Validate all relevant canonical world assets.
for asset_id, rec in fp.world_assets.items():
    sem=rec.get('semantic_type')
    if sem not in {'desk','desk_ceo','chair','chair_sub','pc','reception'}: continue
    resolved=fp.resolve_asset(asset_id)
    if sem in {'desk','desk_ceo','chair','reception'}:
        if resolved is None:
            errors.append(f'{asset_id}: missing footprint')
        else:
            counts[resolved['profile_id']]+=1
            if sem=='desk_ceo' and resolved['derived_transform'] != expected_ceo_transform(asset_id):
                errors.append(f"{asset_id}: CEO desk footprint transform {resolved['derived_transform']} != expected {expected_ceo_transform(asset_id)}")
    else:
        if resolved is not None:
            errors.append(f'{asset_id}: visual-only asset unexpectedly has footprint')
        counts[f'visual_only.{sem}']+=1

# Floor00 promoted reception
r=fp.resolve_asset('floor00.reception')
if r is None or r['profile_id']!='footprint.reception.f0':
    errors.append('floor00 reception binding failed')
else:
    counts['footprint.reception.f0']+=1


variant_counts=Counter()
for variant_id, rec in fp.visual_variants.items():
    sem=rec.get('semantic_type')
    if sem not in {'desk','desk_ceo','chair','chair_sub','pc','reception'}:
        continue
    try:
        resolved=fp.resolve_variant(variant_id)
    except Exception as exc:
        errors.append(f'{variant_id}: variant resolution error: {exc}')
        continue
    if sem in {'desk','desk_ceo','chair','reception'}:
        if resolved is None:
            errors.append(f'{variant_id}: expected variant footprint for semantic {sem}')
        else:
            variant_counts[resolved['profile_id']]+=1
            if sem=='desk_ceo' and resolved['derived_transform'] != expected_ceo_transform(rec['asset_id']):
                errors.append(f"{variant_id}: CEO variant footprint transform {resolved['derived_transform']} != expected {expected_ceo_transform(rec['asset_id'])}")
    else:
        if resolved is not None:
            errors.append(f'{variant_id}: visual-only variant unexpectedly has footprint')
        variant_counts[f'visual_only.{sem}']+=1

# Approved dimensions
approved={
 'footprint.desk.standard':[18,7],
 'footprint.chair.standard':[4,4],
 'footprint.reception.f0':[15,19],
 'footprint.reception.f1':[20,16],
 'footprint.reception.f2_plus':[22,34],
}
for pid,size in approved.items():
    if fp.profiles[pid]['author_size_fine_cells']!=size:
        errors.append(f'{pid}: approved size drift')

if fp.profiles['footprint.reception.f2_plus'].get('origin_basis') != 'visual_bounds_top_left':
    errors.append('footprint.reception.f2_plus: origin basis must track visual bounds top-left')

profile = fp.profiles['footprint.reception.f2_plus']
if profile.get('canonical_navigation_ground_anchor_world_px') != [259,376]:
    errors.append('footprint.reception.f2_plus: canonical navigation ground anchor drift')
if profile.get('canonical_navigation_origin_offset_uv_cells') != [-12,-4]:
    errors.append('footprint.reception.f2_plus: canonical navigation origin offset drift')

report={
 'schema':'gds_ground_footprint_audit_v1',
 'status':'PASS' if not errors else 'FAIL',
 'fine_grid_profile':'grid.iso.occupancy_fine.v1',
 'profile_count':len(fp.profiles),
 'binding_rule_count':len(fp.bindings),
 'coverage_counts':dict(sorted(counts.items())),
 'variant_coverage_counts':dict(sorted(variant_counts.items())),
 'errors':errors,
}
(ROOT/'REPORTS'/'GROUND_FOOTPRINT_AUDIT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if not errors else 1)
