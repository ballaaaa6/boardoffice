from __future__ import annotations

from VALIDATION._common import resolve_root

ROOT = resolve_root(anchor=__file__)


def test_floor06_preview_plan_covers_all_workstations_directions_and_humanballs():
    from RUNTIME.central_core import CentralGameCore
    from TOOLS.render_floor06_humanball_preview import build_review_assignments

    core = CentralGameCore(ROOT)
    primary, combined = build_review_assignments(core)
    assert [a['workstation_id'] for a in primary] == ['ceo', 'ws1', 'ws2', 'ws3', 'ws4', 'ws5', 'ws6', 'ws7', 'ws8']
    assert set(a['humanball_id'] for a in primary) == set(core.characters.list_humanballs())
    assert {core.resolve_work_seat('floor06', a['workstation_id'])['direction'] for a in primary} == {'SW', 'SE', 'NW'}
    assert {a['workstation_id'] for a in combined} == {'ceo', 'ws1', 'ws3'}
    assert all('effect_id' in a and 'humanball_id' in a for a in combined)
