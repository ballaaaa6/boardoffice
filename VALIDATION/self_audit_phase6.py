from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def audit(core_root: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    root = Path(core_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from VALIDATION.self_audit_central import audit as audit_base
    from RUNTIME.central_core import CentralGameCore

    base = audit_base(root, write_report=False)
    core = CentralGameCore(root)

    spatial_registry = _load(root / 'WORLD' / 'REGISTRY' / 'spatial_profiles.json')
    spatial_schema = _load(root / 'SCHEMA' / 'WORLD' / 'spatial_profiles.schema.json')
    schema_errors = sorted(
        Draft202012Validator(spatial_schema).iter_errors(spatial_registry),
        key=lambda e: list(e.path),
    )

    profile_null_policy_errors = []
    for variant_id, profile in spatial_registry['profiles'].items():
        if profile['spatial']['footprint'] is not None:
            profile_null_policy_errors.append(f'{variant_id}: spatial.footprint')
        if profile['physics']['solid'] is not None:
            profile_null_policy_errors.append(f'{variant_id}: physics.solid')
        if profile['physics']['collision_shape'] is not None:
            profile_null_policy_errors.append(f'{variant_id}: physics.collision_shape')
        if profile['interaction']['anchor'] is not None:
            profile_null_policy_errors.append(f'{variant_id}: interaction.anchor')
        if profile['interaction']['radius_px'] is not None:
            profile_null_policy_errors.append(f'{variant_id}: interaction.radius_px')

    resolved_primary_objects = 0
    foreground_fragments = 0
    object_errors = []
    large_reception_semantic_exact = 0
    primary_type_counts = {'chair': 0, 'desk': 0, 'pc': 0, 'reception': 0}

    for floor_id in sorted(core.world.floors):
        try:
            objects = core.list_spatial_objects(floor_id)
            resolved_primary_objects += len(objects)
            for obj in objects:
                primary_type_counts[obj['object_type']] += 1
                if obj['relationships']['foreground_fragment'] is not None:
                    foreground_fragments += 1
                if obj['spatial']['footprint'] is not None:
                    object_errors.append(f"{obj['object_id']}: footprint not null")
                if obj['physics']['solid'] is not None or obj['physics']['collision_shape'] is not None:
                    object_errors.append(f"{obj['object_id']}: physics guessed")
                if obj['interaction']['anchor'] is not None or obj['interaction']['radius_px'] is not None:
                    object_errors.append(f"{obj['object_id']}: interaction guessed")
        except Exception as exc:
            object_errors.append(f'{floor_id}: {exc!r}')

        floor = core.world.floor_record(floor_id)
        if floor['layout_id'] == 'layout.floor02.large':
            try:
                rec = core.resolve_spatial_object(floor_id, 'reception')
                anchor = rec['spatial']['semantic_anchor']
                bounds = rec['visual']['visual_bounds_world_px']
                if (
                    anchor == {
                        'x_basis': 'sprite_left', 'x_px': 221,
                        'y_basis': 'alpha_top', 'y_px': 355,
                    }
                    and bounds is not None
                    and bounds['top'] == 355
                ):
                    large_reception_semantic_exact += 1
                else:
                    object_errors.append(f'{floor_id}.reception: semantic anchor mismatch')
            except Exception as exc:
                object_errors.append(f'{floor_id}.reception: {exc!r}')

    # Floor01 must remain explicit; no large-layout anchor may be invented.
    floor01_reception = core.resolve_spatial_object('floor01', 'reception')
    floor01_explicit_ok = (
        floor01_reception['render']['x_px'] == 218
        and floor01_reception['render']['y_px'] == 353
        and floor01_reception['spatial']['semantic_anchor'] is None
    )

    # Profile coverage must equal the set of variants used by the primary scope.
    used_variants = set()
    for floor_id in sorted(core.world.floors):
        for placement in core.world.resolve_floor_placements(floor_id):
            if placement['object_type'] in {'chair', 'desk', 'pc', 'reception'}:
                used_variants.add(placement['variant_id'])
    profile_coverage_exact = used_variants == set(spatial_registry['profiles'])

    spatial = {
        'profile_count': len(spatial_registry['profiles']),
        'resolved_primary_objects': resolved_primary_objects,
        'primary_type_counts': primary_type_counts,
        'foreground_fragments': foreground_fragments,
        'large_reception_semantic_exact': large_reception_semantic_exact,
        'floor01_reception_explicit_ok': floor01_explicit_ok,
        'profile_coverage_exact': profile_coverage_exact,
        'spatial_schema_errors': len(schema_errors),
        'profile_null_policy_errors': len(profile_null_policy_errors),
        'object_errors': len(object_errors),
    }

    checks = {
        'phase5_base_pass': bool(base['pass']),
        'spatial_schema_valid': not schema_errors,
        'spatial_profiles_224': spatial['profile_count'] == 224,
        'profile_coverage_exact': profile_coverage_exact,
        'resolved_primary_objects_681': resolved_primary_objects == 681,
        'primary_type_counts_exact': primary_type_counts == {
            'chair': 219, 'desk': 219, 'pc': 219, 'reception': 24,
        },
        'foreground_fragments_8': foreground_fragments == 8,
        'large_reception_semantic_23': large_reception_semantic_exact == 23,
        'floor01_reception_explicit': floor01_explicit_ok,
        'null_policy_exact': not profile_null_policy_errors and not object_errors,
    }

    report = {
        'schema': 'gds.phase6.spatial_audit.v1',
        'pass': all(checks.values()),
        'checks': checks,
        'spatial': spatial,
        'spatial_schema_error_messages': [e.message for e in schema_errors[:20]],
        'profile_null_policy_error_examples': profile_null_policy_errors[:20],
        'object_error_examples': object_errors[:20],
        'base': base,
    }
    if write_report:
        out = root / 'REPORTS' / 'PHASE6_SPATIAL_AUDIT.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--core-root', default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--no-write', action='store_true')
    ns = ap.parse_args()
    result = audit(ns.core_root, write_report=not ns.no_write)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['pass'] else 1)
