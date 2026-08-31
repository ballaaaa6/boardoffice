from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def audit(core_root: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    root = Path(core_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from RUNTIME.central_core import CentralGameCore
    from WORLD.RUNTIME.floor_renderer import png_sha256, rgba_sha256

    refs = _load(root / 'VALIDATION' / 'reference_hashes.json')
    core = CentralGameCore(root)

    # Room-navigation canonicalization evolves the coordinate-frame grid contract. All other
    # Phase 5 payload files remain byte-exact against the frozen references.
    evolved_payload_files = {
        'SCHEMA/WORLD/coordinate_frames.schema.json',
        'WORLD/REGISTRY/coordinate_frames.json',
        # v1.4.1 intentionally restores source-authentic chair assets that were
        # pruned by the lean world build. Their exact source fidelity is
        # validated by VALIDATION/self_audit_work_seat.py.
        'WORLD/REGISTRY/world_assets.json',
        # v1.6.1 intentionally adds the HumanBall popup channel to the
        # character asset registry and CharacterSystem facade. HumanBall is
        # visual-only and does not evolve world/navigation payloads.
        'CHARACTER/ASSETS/asset_registry.json',
        'CHARACTER/RUNTIME/character_system.py',
        # Phase 8E WorkSeat naming makes seated turn subactions direction-explicit
        # while preserving the underlying frame bindings.
        'CHARACTER/ACTIONS/gds_standard_v1.json',
        # Phase 8E character action completeness adds fixed-head alternating-body
        # Work turns and the derived NE character direction. The current source
        # world slots remain three-way, while the runtime bridge is now ready
        # to derive a future NE WorkSeat from NW.
        'CHARACTER/FRAME_RULES/frame_registry.json',
        'SCHEMA/CHARACTER/action_set.schema.json',
        # Four-way WorkSeat support derives NE from NW at runtime. It mirrors
        # the complete workstation composite without changing static assets,
        # authored floor placement hashes, or the current three-way slots.
        'CHARACTER/EFFECTS/gds_effects_v1.json',
        'CHARACTER/EFFECTS/humanball_v1.json',
        'CHARACTER/RUNTIME/effect_renderer.py',
        'CHARACTER/RUNTIME/humanball_renderer.py',
        'CHARACTER/RUNTIME/presentation_renderer.py',
        'CONTRACTS/central_contract.json',
        'CONTRACTS/work_pose_profiles.json',
        'RUNTIME/work_seat_core.py',
        'RUNTIME/work_seat_lifecycle.py',
        'SCHEMA/CHARACTER/humanball_registry.schema.json',
        'SCHEMA/WORLD/character_direction_bridge.schema.json',
        'SCHEMA/work_pose_profiles.schema.json',
        'WORLD/REGISTRY/character_direction_bridge.json',
        # Phase 8E dialogue presentation adds public runtime exports while
        # leaving the frozen character/world payloads unchanged.
        'CHARACTER/RUNTIME/__init__.py',
    }
    payload_mismatches: list[dict[str, str]] = []
    payload_missing: list[str] = []
    for rel, expected in refs['payload_files'].items():
        p = root / rel
        if not p.is_file():
            payload_missing.append(rel)
            continue
        actual = _sha(p)
        if actual != expected and rel not in evolved_payload_files:
            payload_mismatches.append({'path': rel, 'expected': expected, 'actual': actual})

    schema_pairs = [
        ('SCHEMA/central_manifest.schema.json', 'CENTRAL_MANIFEST.json'),
        ('SCHEMA/CHARACTER/action_set.schema.json', 'CHARACTER/ACTIONS/gds_standard_v1.json'),
        ('SCHEMA/CHARACTER/character_collections.schema.json', 'CHARACTER/CHARACTERS/collections.json'),
        ('SCHEMA/CHARACTER/character_registry.schema.json', 'CHARACTER/CHARACTERS/characters.json'),
        ('SCHEMA/CHARACTER/composition_index.schema.json', 'CHARACTER/CHARACTERS/composition_index.json'),
        ('SCHEMA/CHARACTER/effect_registry.schema.json', 'CHARACTER/EFFECTS/gds_effects_v1.json'),
        ('SCHEMA/CHARACTER/humanball_registry.schema.json', 'CHARACTER/EFFECTS/humanball_v1.json'),
        ('SCHEMA/CHARACTER/employee_metadata.schema.json', 'CHARACTER/EMPLOYEES/employee_metadata.json'),
        ('SCHEMA/CHARACTER/dialogue_bubble_registry.schema.json', 'CHARACTER/DIALOGUE/bubble_presets.json'),
        ('SCHEMA/CHARACTER/dialogue_font_registry.schema.json', 'CHARACTER/DIALOGUE/dialogue_fonts.json'),
        ('SCHEMA/CHARACTER/frame_registry.schema.json', 'CHARACTER/FRAME_RULES/frame_registry.json'),
        ('SCHEMA/CHARACTER/unified_asset_registry.schema.json', 'CHARACTER/ASSETS/asset_registry.json'),
        ('SCHEMA/CHARACTER/final_manifest.schema.json', 'CHARACTER/FINAL_MANIFEST.json'),
        ('SCHEMA/IDENTITY/identity_cards.schema.json', 'CHARACTER/IDENTITY/CHARACTERS/identity_cards.json'),
        ('SCHEMA/IDENTITY/identity_alias_index.schema.json', 'CHARACTER/IDENTITY/CHARACTERS/identity_alias_index.json'),
        ('SCHEMA/WORLD/world_assets.schema.json', 'WORLD/REGISTRY/world_assets.json'),
        ('SCHEMA/WORLD/visual_variants.schema.json', 'WORLD/REGISTRY/visual_variants.json'),
        ('SCHEMA/WORLD/coordinate_frames.schema.json', 'WORLD/REGISTRY/coordinate_frames.json'),
        ('SCHEMA/WORLD/layouts.schema.json', 'WORLD/REGISTRY/layouts.json'),
        ('SCHEMA/WORLD/floor_skins.schema.json', 'WORLD/REGISTRY/floor_skins.json'),
        ('SCHEMA/WORLD/floors.schema.json', 'WORLD/REGISTRY/floors.json'),
        ('SCHEMA/WORLD/workstation_directions.schema.json', 'WORLD/REGISTRY/workstation_directions.json'),
        ('SCHEMA/WORLD/gameplay_metadata_families.schema.json', 'WORLD/REGISTRY/gameplay_metadata_families.json'),
        ('SCHEMA/WORLD/character_direction_bridge.schema.json', 'WORLD/REGISTRY/character_direction_bridge.json'),
        ('SCHEMA/work_pose_profiles.schema.json', 'CONTRACTS/work_pose_profiles.json'),
        ('SCHEMA/WORLD/walking_depth_profiles.schema.json', 'WORLD/REGISTRY/walking_depth_profiles.json'),
        ('SCHEMA/work_seat_lifecycle.schema.json', 'CONTRACTS/work_seat_lifecycle.json'),
    ]
    schema_errors: list[dict[str, Any]] = []
    for schema_rel, data_rel in schema_pairs:
        schema = _load(root / schema_rel)
        data = _load(root / data_rel)
        errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
        if errors:
            schema_errors.append({
                'schema': schema_rel,
                'data': data_rel,
                'errors': [err.message for err in errors[:10]],
            })

    cards_payload = _load(root / 'CHARACTER' / 'IDENTITY' / 'CHARACTERS' / 'identity_cards.json')
    aliases_payload = _load(root / 'CHARACTER' / 'IDENTITY' / 'CHARACTERS' / 'identity_alias_index.json')
    cards = cards_payload['characters']
    card_by_id = {row['character_id']: row for row in cards}
    technical = _load(root / 'CHARACTER' / 'CHARACTERS' / 'characters.json')['characters']
    tech_by_id = {row['character_id']: row for row in technical}
    employee_rows = core.list_employees()
    employee_wave1 = core.list_employees(wave=1)
    employee_wave2 = core.list_employees(wave=2)
    employee_initial_roster = core.resolve_initial_employee_roster()

    composition_exact = sum(
        1 for cid, row in card_by_id.items()
        if cid in tech_by_id and row['composition'] == tech_by_id[cid]['composition']
    )
    alias_groups = aliases_payload['aliases']
    aliases_complete = all(len(alias_groups[name]) == 302 for name in (
        'character_no', 'character_code', 'full_name', 'nickname', 'character_id'
    ))

    character_ids = core.characters.list_characters()
    requests = core.characters.list_action_requests()
    action_request_count = 0
    frame_occurrence_count = 0
    action_resolution_errors: list[dict[str, Any]] = []
    for cid in character_ids:
        for req in requests:
            action_request_count += 1
            try:
                frame_occurrence_count += len(core.characters.resolve_frame_ids(
                    cid, req['action'], req['direction'], req['subaction']
                ))
            except Exception as exc:
                if len(action_resolution_errors) < 20:
                    action_resolution_errors.append({'character_id': cid, **req, 'error': repr(exc)})

    floor_rgba_exact = 0
    floor_png_exact = 0
    floor_errors: list[dict[str, str]] = []
    resolved_placements = 0
    workstation_resolved = 0
    workstation_errors: list[dict[str, str]] = []
    for floor_id in sorted(core.world.floors):
        try:
            image = core.render_floor(floor_id)
            if rgba_sha256(image) == refs['floor_reference_rgba_sha256'][floor_id]:
                floor_rgba_exact += 1
            if png_sha256(image) == refs['floor_reference_png_sha256'][floor_id]:
                floor_png_exact += 1
            resolved_placements += len(core.world.resolve_floor_placements(floor_id))
        except Exception as exc:
            floor_errors.append({'floor_id': floor_id, 'error': repr(exc)})
        groups = core.world.floor_layout(floor_id)['workstation_groups']
        for workstation_id in groups:
            try:
                direction = core.resolve_workstation_direction(floor_id, workstation_id)
                core.directions.map_world_direction_to_character_action(direction, 'work')
                workstation_resolved += 1
            except Exception as exc:
                workstation_errors.append({
                    'floor_id': floor_id,
                    'workstation_id': workstation_id,
                    'error': repr(exc),
                })

    # Integrated rendering proves identity -> world direction -> character work bridge.
    integrated_smoke = {}
    for floor_id, workstation_id in [('floor00', 'ws1'), ('floor02', 'ceo'), ('floor36', 'ws7')]:
        try:
            result = core.render_character_at_workstation(0, floor_id, workstation_id)
            integrated_smoke[f'{floor_id}.{workstation_id}'] = {
                'ok': bool(result.frames),
                'direction': result.direction,
                'frame_count': len(result.frames),
            }
        except Exception as exc:
            integrated_smoke[f'{floor_id}.{workstation_id}'] = {'ok': False, 'error': repr(exc)}

    cache_paths = [
        str(p.relative_to(root)) for p in root.rglob('*')
        if p.name in {'__pycache__', '.pytest_cache'} or p.suffix == '.pyc'
    ]
    lean = {
        'world_raw_present': (root / 'WORLD' / 'RAW').exists(),
        'materialized_floor_cache_present': any((root / name).exists() for name in ('FLOOR_OUTPUT', 'FLOOR_CACHE', 'EXPORTS')),
        'python_cache_path_count': len(cache_paths),
    }

    counts = {
        'characters': len(cards),
        'technical_characters': len(character_ids),
        'identity_full_name_unique': len({r['full_name'].casefold() for r in cards}),
        'identity_nickname_unique': len({r['nickname'].casefold() for r in cards}),
        'composition_exact': composition_exact,
        'action_requests': action_request_count,
        'frame_occurrences': frame_occurrence_count,
        'action_resolution_errors': len(action_resolution_errors),
        'floors': len(core.world.floors),
        'floors_render_exact': floor_rgba_exact,
        'floors_png_exact': floor_png_exact,
        'resolved_placements': resolved_placements,
        'workstations_resolved': workstation_resolved,
        'workstation_errors': len(workstation_errors),
        'employees': len(employee_rows),
        'employee_wave1': len(employee_wave1),
        'employee_wave2': len(employee_wave2),
        'employee_initial_roster': len(employee_initial_roster),
        'payload_hash_files': len(refs['payload_files']),
        'payload_hash_mismatches': len(payload_mismatches),
        'payload_missing': len(payload_missing),
        'schema_validation_errors': len(schema_errors),
        'schemas_validated': len(schema_pairs),
    }

    checks = {
        'payload_files_exact': not payload_mismatches and not payload_missing,
        'schemas_valid': not schema_errors,
        'characters_302': counts['characters'] == counts['technical_characters'] == 302,
        'identity_names_unique': counts['identity_full_name_unique'] == counts['identity_nickname_unique'] == 302,
        'identity_composition_exact': composition_exact == 302,
        'aliases_complete': aliases_complete,
        'action_resolution_exact': action_request_count == 9060 and frame_occurrence_count == 17516 and not action_resolution_errors,
        'floors_exact': len(core.world.floors) == floor_rgba_exact == floor_png_exact == 25 and not floor_errors,
        'placements_exact': resolved_placements == 766,
        'workstations_exact': workstation_resolved == 219 and not workstation_errors,
        'employee_metadata_exact': (
            len(employee_rows) == 604
            and len(employee_wave1) == 302
            and len(employee_wave2) == 302
        ),
        'employee_initial_roster_exact': len(employee_initial_roster) == 219,
        'integrated_smoke': all(row.get('ok') for row in integrated_smoke.values()),
        'world_raw_omitted': not lean['world_raw_present'],
        'no_materialized_floor_cache': not lean['materialized_floor_cache_present'],
    }

    report = {
        'schema': 'gds.phase5.central_audit.v1',
        'pass': all(checks.values()),
        'release_clean': lean['python_cache_path_count'] == 0,
        'checks': checks,
        'counts': counts,
        'lean': lean,
        'payload_mismatches': payload_mismatches[:20],
        'payload_missing': payload_missing[:20],
        'schema_errors': schema_errors[:20],
        'floor_errors': floor_errors[:20],
        'workstation_errors': workstation_errors[:20],
        'integrated_smoke': integrated_smoke,
        'sources': refs['source_zip_sha256'],
    }
    if write_report:
        out = root / 'REPORTS' / 'PHASE5_CENTRAL_AUDIT.json'
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
