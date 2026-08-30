from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from PIL import Image


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def _rgba_sha256(image: Image.Image) -> str:
    rgba = image.convert('RGBA')
    payload = rgba.width.to_bytes(4, 'big') + rgba.height.to_bytes(4, 'big') + rgba.tobytes()
    return hashlib.sha256(payload).hexdigest()


def audit(core_root: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    root = Path(core_root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from CHARACTER.RUNTIME.character_system import CharacterSystem
    from RUNTIME.work_seat_core import WorkSeatCore
    from WORLD.RUNTIME.floor_renderer import FloorRenderer, png_sha256, rgba_sha256
    from WORLD.RUNTIME.room_navigation_core import RoomNavigationCore

    families = _load(root / 'WORLD' / 'REGISTRY' / 'chair_families.json')
    assets = _load(root / 'WORLD' / 'REGISTRY' / 'world_assets.json')['assets']
    refs = _load(root / 'VALIDATION' / 'chair_source_reference.json')['parts']
    floor_refs = _load(root / 'VALIDATION' / 'work_seat_floor_reference_hashes.json')['floors']
    pose = _load(root / 'CONTRACTS' / 'work_pose_profiles.json')

    schema_errors: list[dict[str, Any]] = []
    for schema_rel, data_rel in (
        ('SCHEMA/WORLD/chair_families.schema.json', 'WORLD/REGISTRY/chair_families.json'),
        ('SCHEMA/work_pose_profiles.schema.json', 'CONTRACTS/work_pose_profiles.json'),
    ):
        schema = _load(root / schema_rel)
        data = _load(root / data_rel)
        errors = list(Draft202012Validator(schema).iter_errors(data))
        if errors:
            schema_errors.append({
                'schema': schema_rel,
                'data': data_rel,
                'errors': [e.message for e in errors[:10]],
            })

    referenced_assets = 0
    transparent_parts: list[str] = []
    chair_hash_errors: list[dict[str, str]] = []
    for part_id, ref in refs.items():
        family_id, role = part_id.split('.', 1)
        part = families['families'][family_id]['parts'][role]
        if ref['transparent']:
            transparent_parts.append(part_id)
            if part['asset_id'] is not None or part['source_status'] != 'transparent_by_source':
                chair_hash_errors.append({'part_id': part_id, 'error': 'transparent_source_not_null'})
            continue
        referenced_assets += 1
        asset_id = part['asset_id']
        if asset_id != part_id:
            chair_hash_errors.append({'part_id': part_id, 'error': f'asset_id={asset_id}'})
            continue
        asset = assets.get(asset_id)
        if asset is None:
            chair_hash_errors.append({'part_id': part_id, 'error': 'missing_world_asset'})
            continue
        blob = root / 'WORLD' / 'ASSETS' / 'blobs' / f"{asset['blob_id']}.png"
        if not blob.is_file():
            chair_hash_errors.append({'part_id': part_id, 'error': 'missing_blob'})
            continue
        with Image.open(blob) as im:
            actual_rgba = _rgba_sha256(im.convert('RGBA'))
        if actual_rgba != ref['rgba_sha256'] or asset['rgba_sha256'] != ref['rgba_sha256']:
            chair_hash_errors.append({
                'part_id': part_id,
                'error': 'rgba_mismatch',
                'expected': ref['rgba_sha256'],
                'actual': actual_rgba,
            })

    expected_transparent = [
        'chair_004.part_03',
        'chair_005.part_03',
        'chair_025.part_03',
        'chair_026.part_03',
        'chair_027.part_03',
    ]
    chair_catalog_complete = (
        families['family_count'] == 30
        and len(families['families']) == 30
        and referenced_assets == 115
        and transparent_parts == expected_transparent
    )

    seat = WorkSeatCore(root)
    workstation_errors: list[dict[str, str]] = []
    workstation_count = 0
    for floor_id in sorted(seat.world.floors):
        layout = seat.world.floor_layout(floor_id)
        for workstation_id in layout['workstation_groups']:
            workstation_count += 1
            try:
                seat.resolve_workstation_seat(floor_id, workstation_id)
            except Exception as exc:  # audit records the exact contract failure
                workstation_errors.append({
                    'floor_id': floor_id,
                    'workstation_id': workstation_id,
                    'error': str(exc),
                })

    composition_errors: list[dict[str, str]] = []
    composition_requests = 0
    for floor_id in sorted(seat.world.floors):
        layout = seat.world.floor_layout(floor_id)
        for workstation_id in layout['workstation_groups']:
            seat_record = seat.resolve_workstation_seat(floor_id, workstation_id)
            for subaction in ('normal_work', 'turn_side_a', 'turn_side_b', 'happy'):
                composition_requests += 1
                try:
                    result = seat.compose_seat(
                        'TP_000',
                        seat_record['chair_family_id'],
                        seat_record['direction'],
                        subaction,
                    )
                    if not result.frames:
                        raise ValueError('no frames')
                except Exception as exc:
                    composition_errors.append({
                        'floor_id': floor_id,
                        'workstation_id': workstation_id,
                        'subaction': subaction,
                        'error': str(exc),
                    })

    floor_renderer = FloorRenderer(root / 'WORLD')
    floor_hash_errors: list[dict[str, str]] = []
    for floor_id, expected in floor_refs.items():
        image = floor_renderer.render(floor_id)
        actual_rgba = rgba_sha256(image)
        actual_png = png_sha256(image)
        if actual_rgba != expected['rgba_sha256'] or actual_png != expected['png_sha256']:
            floor_hash_errors.append({
                'floor_id': floor_id,
                'expected_rgba': expected['rgba_sha256'],
                'actual_rgba': actual_rgba,
                'expected_png': expected['png_sha256'],
                'actual_png': actual_png,
            })

    characters = CharacterSystem(root / 'CHARACTER')
    sw_mismatches: list[dict[str, Any]] = []
    sw_pairs_checked = 0
    character_ids = characters.list_characters()
    for character_id in character_ids:
        for subaction in ('normal_work', 'turn_side_a', 'turn_side_b', 'happy'):
            se = characters.render(character_id, 'work', 'SE', subaction)
            sw = characters.render(character_id, 'work', 'SW', subaction)
            if len(se.frames) != len(sw.frames):
                sw_mismatches.append({
                    'character_id': character_id,
                    'subaction': subaction,
                    'error': 'frame_count_mismatch',
                })
                continue
            for index, (se_frame, sw_frame) in enumerate(zip(se.frames, sw.frames)):
                sw_pairs_checked += 1
                expected = se_frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if expected.tobytes() != sw_frame.convert('RGBA').tobytes():
                    sw_mismatches.append({
                        'character_id': character_id,
                        'subaction': subaction,
                        'frame_index': index,
                        'error': 'pixel_mismatch',
                    })

    profiles_exact = (
        pose['profiles']['SE']['visual_character_offset_from_chair_px'] == [2, 2]
        and pose['profiles']['SE']['world_chair_role'] == 'part_01'
        and pose['profiles']['NW']['visual_character_offset_from_chair_px'] == [-10, -6]
        and pose['profiles']['NW']['world_chair_role'] == 'part_00'
        and pose['profiles']['NW']['world_chair_foreground_role'] == 'part_03'
        and pose['profiles']['SW']['derived_from'] == 'SE'
        and pose['profiles']['SW']['standalone_transform_scope'] == 'final_composite'
        and pose['profiles']['SW']['world_chair_role'] == 'part_02'
        and pose['coordinate_semantics']['gameplay_anchor_fields_populated'] is False
    )

    nav = RoomNavigationCore(root / 'WORLD')
    nav_checks = {
        'fine_grid_canonical': nav.grid_profile()['profile_id'] == 'grid.iso.occupancy_fine.v1' and nav.grid_profile()['tile_width_px'] == 4 and nav.grid_profile()['tile_height_px'] == 2,
        'floor00_family': nav.family('floor00')['canonical_floor_id'] == 'floor00',
        'floor01_family': nav.family('floor01')['canonical_floor_id'] == 'floor01',
        'floor02_family': nav.family('floor02')['canonical_floor_id'] == 'floor02',
        'f2_plus_family': nav.family('floor36')['canonical_floor_id'] == 'floor02',
        'legacy_grid_removed': not (root / 'WORLD/REGISTRY/grid_calibration.json').exists(),
        'legacy_solids_inactive': not (root / 'WORLD/REGISTRY/embedded_solids.json').exists(),
    }
    room_navigation = {'pass': all(nav_checks.values()), 'checks': nav_checks}

    checks = {
        'schemas_valid': not schema_errors,
        'chair_catalog_complete': chair_catalog_complete,
        'chair_source_hashes_exact': not chair_hash_errors,
        'work_pose_profiles_exact': profiles_exact,
        'all_219_workstations_chair_role_consistent': workstation_count == 219 and not workstation_errors,
        'all_876_workstation_subaction_compositions_renderable': composition_requests == 876 and not composition_errors,
        'static_floor_hashes_unchanged': len(floor_refs) == 25 and not floor_hash_errors,
        'sw_character_mirror_exact': len(character_ids) == 302 and sw_pairs_checked == 2114 and not sw_mismatches,
        'room_navigation_regression_pass': bool(room_navigation['pass']),
    }
    report = {
        'schema': 'gds.work_seat_recovery_audit.v1',
        'pass': all(checks.values()),
        'checks': checks,
        'counts': {
            'chair_families': len(families['families']),
            'chair_source_parts': len(refs),
            'chair_nontransparent_parts': referenced_assets,
            'chair_transparent_parts': len(transparent_parts),
            'workstations_checked': workstation_count,
            'workstation_subaction_compositions_checked': composition_requests,
            'static_floors_checked': len(floor_refs),
            'characters_checked': len(character_ids),
            'sw_frame_pairs_checked': sw_pairs_checked,
        },
        'schema_errors': schema_errors,
        'chair_hash_errors': chair_hash_errors,
        'workstation_errors': workstation_errors,
        'composition_errors': composition_errors,
        'floor_hash_errors': floor_hash_errors,
        'sw_mismatches': sw_mismatches,
        'room_navigation': room_navigation,
    }
    if write_report:
        out = root / 'REPORTS' / 'WORK_SEAT_RECOVERY_AUDIT.json'
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    result = audit(Path(__file__).resolve().parents[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['pass'] else 1)
