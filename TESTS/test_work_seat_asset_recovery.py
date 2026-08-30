from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))


def test_chair_family_registry_covers_original_catalog():
    data = _load('WORLD/REGISTRY/chair_families.json')
    assert data['schema'] == 'gds.chair_families.v1'
    assert data['family_count'] == 30
    assert len(data['families']) == 30

    referenced = 0
    transparent = []
    for idx in range(30):
        family_id = f'chair_{idx:03d}'
        family = data['families'][family_id]
        assert family['family_id'] == family_id
        assert set(family['parts']) == {'part_00', 'part_01', 'part_02', 'part_03'}
        for role, part in family['parts'].items():
            if part['asset_id'] is None:
                transparent.append(f'{family_id}.{role}')
                assert part['source_status'] == 'transparent_by_source'
            else:
                referenced += 1
                assert part['source_status'] == 'present'

    assert referenced == 115
    assert transparent == [
        'chair_004.part_03',
        'chair_005.part_03',
        'chair_025.part_03',
        'chair_026.part_03',
        'chair_027.part_03',
    ]


def test_all_chair_assets_match_frozen_source_reference():
    families = _load('WORLD/REGISTRY/chair_families.json')['families']
    assets = _load('WORLD/REGISTRY/world_assets.json')['assets']
    refs = _load('VALIDATION/chair_source_reference.json')['parts']

    assert len(refs) == 120
    nonempty = 0
    for part_id, ref in refs.items():
        family_id, role = part_id.split('.', 1)
        entry = families[family_id]['parts'][role]
        if ref['transparent']:
            assert entry['asset_id'] is None
            continue
        nonempty += 1
        asset_id = entry['asset_id']
        assert asset_id == part_id
        asset = assets[asset_id]
        assert asset['rgba_sha256'] == ref['rgba_sha256']
        blob = ROOT / 'WORLD' / 'ASSETS' / 'blobs' / f"{asset['blob_id']}.png"
        assert blob.is_file()
        with Image.open(blob) as im:
            rgba = im.convert('RGBA')
        assert rgba.size == (21, 32)

    assert nonempty == 115
