from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from TOOLS._bootstrap import ensure_project_root
except ModuleNotFoundError:
    from _bootstrap import ensure_project_root

ensure_project_root(__file__)

from RUNTIME.asset_utils import (  # noqa: E402
    file_sha256,
    load_json,
    png_bytes,
    rgba_sha256,
    write_json,
)


def build(core_root: Path, source_office: Path) -> dict[str, Any]:
    assets_path = core_root / 'WORLD' / 'REGISTRY' / 'world_assets.json'
    assets_payload = load_json(assets_path)
    assets = assets_payload['assets']
    blobs_dir = core_root / 'WORLD' / 'ASSETS' / 'blobs'
    blobs_dir.mkdir(parents=True, exist_ok=True)

    families: dict[str, Any] = {}
    source_refs: dict[str, Any] = {}
    restored: list[str] = []
    existing_verified: list[str] = []
    transparent: list[str] = []
    new_blob_ids: set[str] = set()

    for family_no in range(30):
        family_id = f'chair_{family_no:03d}'
        source_sheet = source_office / f'{family_id}.png'
        if not source_sheet.is_file():
            raise FileNotFoundError(source_sheet)
        source_sheet_hash = file_sha256(source_sheet)
        with Image.open(source_sheet) as im:
            sheet = im.convert('RGBA')
        if sheet.size != (84, 32):
            raise ValueError(f'{source_sheet}: expected 84x32, got {sheet.size}')

        parts: dict[str, Any] = {}
        for part_no in range(4):
            role = f'part_{part_no:02d}'
            part_id = f'{family_id}.{role}'
            rect = [part_no * 21, 0, (part_no + 1) * 21, 32]
            crop = sheet.crop(tuple(rect)).convert('RGBA')
            is_transparent = crop.getbbox() is None
            rgba_hash = rgba_sha256(crop)
            source_refs[part_id] = {
                'family_id': family_id,
                'role': role,
                'source_sheet': f'01_KAIRO_SPRITE_PACKS/office/{family_id}.png',
                'source_sheet_sha256': source_sheet_hash,
                'source_rect': rect,
                'transparent': is_transparent,
                'rgba_sha256': rgba_hash,
                'width': 21,
                'height': 32,
            }

            if is_transparent:
                transparent.append(part_id)
                parts[role] = {
                    'asset_id': None,
                    'source_status': 'transparent_by_source',
                    'source_rect': rect,
                }
                continue

            parts[role] = {
                'asset_id': part_id,
                'source_status': 'present',
                'source_rect': rect,
            }

            if part_id in assets:
                entry = assets[part_id]
                if entry['rgba_sha256'] != rgba_hash:
                    raise ValueError(
                        f'{part_id}: existing rgba hash {entry["rgba_sha256"]} != source {rgba_hash}'
                    )
                blob_path = blobs_dir / f'{entry["blob_id"]}.png'
                if not blob_path.is_file():
                    raise FileNotFoundError(blob_path)
                with Image.open(blob_path) as bim:
                    existing = bim.convert('RGBA')
                if existing.size != crop.size or existing.tobytes() != crop.tobytes():
                    raise ValueError(f'{part_id}: existing blob pixels differ from source crop')
                existing_verified.append(part_id)
                continue

            blob_id = rgba_hash
            blob_path = blobs_dir / f'{blob_id}.png'
            payload = png_bytes(crop)
            if blob_path.exists():
                with Image.open(blob_path) as bim:
                    existing_blob = bim.convert('RGBA')
                if existing_blob.size != crop.size or existing_blob.tobytes() != crop.tobytes():
                    raise ValueError(f'blob collision for {blob_id}')
            else:
                blob_path.write_bytes(payload)
                new_blob_ids.add(blob_id)

            assets[part_id] = {
                'asset_id': part_id,
                'blob_id': blob_id,
                'height': 32,
                'legacy_shared_path': f'office/chair/{family_id}/{role}.png',
                'rgba_sha256': rgba_hash,
                'semantic_type': 'chair_sub' if role == 'part_03' else 'chair',
                'source_class': 'recovered_original_sheet_cell',
                'source_png_sha256': source_sheet_hash,
                'width': 21,
                'recipe': {
                    'type': 'source_sheet_cell_crop',
                    'source_package': 'Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS_2',
                    'source_path': f'01_KAIRO_SPRITE_PACKS/office/{family_id}.png',
                    'source_rect': rect,
                },
                'recipe_validation': {
                    'status': 'exact',
                    'source_rgba_sha256': rgba_hash,
                    'canonical_rgba_sha256': blob_id,
                },
            }
            restored.append(part_id)

        families[family_id] = {
            'family_id': family_id,
            'source_sheet': f'01_KAIRO_SPRITE_PACKS/office/{family_id}.png',
            'source_sheet_sha256': source_sheet_hash,
            'cell_size_px': [21, 32],
            'parts': parts,
        }

    assets_payload['assets'] = dict(sorted(assets.items()))
    write_json(assets_path, assets_payload)

    family_payload = {
        'schema': 'gds.chair_families.v1',
        'source_package': 'Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS_2',
        'family_count': 30,
        'nontransparent_part_count': 115,
        'transparent_source_part_count': 5,
        'families': families,
    }
    write_json(core_root / 'WORLD' / 'REGISTRY' / 'chair_families.json', family_payload)

    ref_payload = {
        'schema': 'gds.chair_source_reference.v1',
        'source_package': 'Game_Dev_Story_v2.6.9_EXTRACTED_ASSETS_2',
        'parts': source_refs,
    }
    write_json(core_root / 'VALIDATION' / 'chair_source_reference.json', ref_payload)

    return {
        'source_family_count': 30,
        'source_part_count': 120,
        'source_nontransparent_part_count': 115,
        'transparent_part_count': len(transparent),
        'transparent_parts': transparent,
        'existing_verified_count': len(existing_verified),
        'restored_logical_asset_count': len(restored),
        'restored_logical_assets': restored,
        'new_unique_blob_count': len(new_blob_ids),
        'world_logical_asset_count': len(assets_payload['assets']),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--core-root', required=True)
    parser.add_argument('--source-office', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = build(Path(args.core_root).resolve(), Path(args.source_office).resolve())
    if args.report:
        write_json(Path(args.report), report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
