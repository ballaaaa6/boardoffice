from pathlib import Path

from TOOLS.render_phase8b_crowd_portal_qa import CrowdPortalRenderer


ROOT = Path(__file__).resolve().parents[1]


def test_crowd_preview_uses_runtime_profile_for_timing_and_walk_cadence():
    renderer = CrowdPortalRenderer(ROOT)
    floor_id = 'floor02'
    start = renderer.portal_starts(floor_id, 1)[0]
    target = renderer.distributed_targets(floor_id, 1)[0]
    states, outside, profile = renderer.states_for(floor_id, 0, start, target)

    assert outside == renderer.adjacent_outside(floor_id, start)
    assert profile == renderer.core.resolve_character_movement_profile(0)
    moving = [state for state in states if state['phase'] in {'outward', 'return'}]
    assert moving
    assert all(state['speed_percent'] == profile['speed_percent'] for state in moving)
    assert all('raw_direction' in state for state in moving)

    frame_index = renderer.move_sprite_index(
        0,
        moving[-1]['direction'],
        moving[-1]['cumulative_distance_px'],
        profile,
    )
    assert frame_index >= 0
