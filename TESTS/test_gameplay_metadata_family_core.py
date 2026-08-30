from pathlib import Path

from RUNTIME.central_core import CentralGameCore

ROOT = Path(__file__).resolve().parents[1]


def test_f2_family_is_explicitly_canonicalized_to_floor02():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor02')
    assert family['family_id'] == 'gameplay.layout.floor02.large'
    assert family['canonical_floor_id'] == 'floor02'
    assert family['family_floor_count'] == 23
    assert family['derived_from_canonical'] is False


def test_f2_plus_floor_resolves_to_floor02_canonical_metadata():
    core = CentralGameCore(ROOT)
    family = core.resolve_gameplay_metadata_family('floor36')
    assert family['canonical_floor_id'] == 'floor02'
    assert family['layout_id'] == 'layout.floor02.large'
    assert family['derived_from_canonical'] is True


def test_visual_skin_is_allowed_to_differ_inside_f2_family():
    core = CentralGameCore(ROOT)
    assert core.world.floor_skin('floor02')['base_variant_id'] != core.world.floor_skin('floor03')['base_variant_id']
    family = core.resolve_gameplay_metadata_family('floor03')
    assert 'visual_assets' in family['skin_only_domains']


def test_f2_gameplay_metadata_family_audit_is_exact():
    core = CentralGameCore(ROOT)
    audit = core.audit_gameplay_metadata_family('floor02')
    assert audit['status'] == 'PASS'
    assert audit['mismatch_count'] == 0
    assert audit['checked_floor_count'] == 23
    assert all(audit['checks'].values())


def test_f0_and_f1_remain_unique_gameplay_metadata_families():
    core = CentralGameCore(ROOT)
    f0 = core.resolve_gameplay_metadata_family('floor00')
    f1 = core.resolve_gameplay_metadata_family('floor01')
    assert f0['family_floor_ids'] == ['floor00']
    assert f1['family_floor_ids'] == ['floor01']
    assert f0['canonical_floor_id'] == 'floor00'
    assert f1['canonical_floor_id'] == 'floor01'
