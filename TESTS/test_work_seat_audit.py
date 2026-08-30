from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_work_seat_audit_passes():
    from VALIDATION.self_audit_work_seat import audit

    report = audit(ROOT, write_report=False)
    assert report['pass'] is True
    assert report['checks']['chair_catalog_complete'] is True
    assert report['checks']['chair_source_hashes_exact'] is True
    assert report['checks']['all_219_workstations_chair_role_consistent'] is True
    assert report['checks']['all_876_workstation_subaction_compositions_renderable'] is True
    assert report['checks']['static_floor_hashes_unchanged'] is True
    assert report['checks']['sw_character_mirror_exact'] is True
    assert report['checks']['room_navigation_regression_pass'] is True


def test_manifest_exposes_work_seat_patch_with_room_navigation_canonical():
    import json
    manifest = json.loads((ROOT / 'CENTRAL_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['version'] == '1.8.4'
    assert manifest['active_phase'] == 'PHASE8C_PORTAL_LIFECYCLE'
    assert manifest['status'] == 'PHASE8C_PORTAL_LIFECYCLE_CLOSED'
    assert manifest['runtime']['work_seat_queries'] is True
    assert manifest['runtime']['room_navigation_queries'] is True
    assert manifest['runtime']['f2_plus_room_navigation_reuses_floor02'] is True
    assert manifest['runtime']['navigation_occupancy_queries'] is True
    assert manifest['runtime']['walkability_compiled_cache_optional'] is True
    assert manifest['runtime']['walkability_runtime_derivation'] is True
    assert manifest['validation']['work_seat_recovery_included'] is True
    assert manifest['counts']['chair_families'] == 30
    assert manifest['counts']['chair_logical_assets'] == 115


def test_lean_release_excludes_materialized_review_and_occupancy_cache():
    import json

    manifest = json.loads((ROOT / 'CENTRAL_MANIFEST.json').read_text(encoding='utf-8'))
    assert not (ROOT / 'PREVIEW').exists()
    assert not (ROOT / 'WORLD' / 'COMPILED_NAV' / 'OCCUPANCY').exists()
    assert manifest['counts']['navigation_occupancy_materialized_cache_floors'] == 0
    assert manifest['counts']['navigation_occupancy_runtime_derivable_floors'] == 25
    assert manifest['lean_policy']['review_previews_packaged'] is False
    assert manifest['lean_policy']['navigation_occupancy_cache_packaged'] is False
